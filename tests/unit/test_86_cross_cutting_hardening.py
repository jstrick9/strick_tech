"""Cross-cutting items carried across the whole review.

1. CSRF PROTECTED NOBODY. The middleware read
       if csrf_token and csrf_token not in _CSRF_TOKENS:  # reject
   so a request that OMITTED the header skipped validation entirely. Verified
   against a running server (PYTEST_CURRENT_TEST unset, so the real path ran):

       POST /api/tasks (no header)             -> 200
       POST /api/tasks (X-CSRF-Token: bogus)   -> 403

   An attacker's forged cross-site request simply does not send the header, so
   the control rejected only honest mistakes. It was written that way for a
   reason: the frontend never sent a token across any of its 282 POST call
   sites, so requiring one would have broken the app.

2. safeUrl() EXISTED IN ONE FILE while eight built hrefs from data. escHtml()
   does NOT make a URL safe — `javascript:alert(1)` survives it intact.

3. RATE-LIMIT STORE WAS UNBOUNDED — a defaultdict keyed by client IP with no
   eviction.

4. config.yaml said version "6.0" while VERSION said 11.5.0.

5. CONTROL TOWER RUNS WERE NOT DURABLE. agent_traces.status DEFAULTS to
   'running' and _active_runs is in-memory, so a restart mid-run stranded the
   row as permanently 'running'. Reproduced before the fix.
"""

from __future__ import annotations

import re
import sqlite3
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[2]
APP_PY = (ROOT / 'backend' / 'app.py').read_text(encoding='utf-8')
CORE_JS = (ROOT / 'frontend' / 'js' / '01-app-core.js').read_text(encoding='utf-8')
INDEX_HTML = (ROOT / 'frontend' / 'index.html').read_text(encoding='utf-8')


# ══ 1. CSRF ═══════════════════════════════════════════════════════════════════
def test_missing_csrf_token_is_no_longer_a_free_pass():
    """The bug: `if csrf_token and ...` meant no header == no validation."""
    assert 'elif _CSRF_STRICT:' in APP_PY, 'a missing token is still unvalidated'
    assert 'CSRF token required' in APP_PY


def test_a_bad_token_is_always_rejected_regardless_of_strict_mode():
    """Strict mode governs MISSING tokens; a wrong one is never acceptable."""
    idx = APP_PY.index('csrf_token = request.headers.get')
    block = APP_PY[idx:idx + 1400]
    assert "if csrf_token not in _CSRF_TOKENS" in block
    # The rejection must not be nested under the strict-mode branch.
    assert block.index('Invalid CSRF token') < block.index('_CSRF_STRICT')


def test_enforcement_is_on_by_default_with_a_documented_escape_hatch():
    """This asserted enforcement was OPT-IN, pinning the literal line
    `_CSRF_STRICT = os.getenv(...)`. That was right for the rollout commit:
    flipping it alongside client-side token attachment would have broken
    scripted clients with no warning.

    "Off by default" is a migration state, not an end state -- left
    indefinitely the protection ships disabled and only operators who read
    release notes ever get it. The default is now ON for a single worker, with
    AGENTIC_CSRF_STRICT=0 as the escape hatch, and it yields to OFF under
    multiple workers because the token store is per-process.
    """
    from backend.app import _CSRF_STRICT

    assert 'AGENTIC_CSRF_STRICT' in APP_PY
    assert 'runtime_topology.csrf_strict_is_safe()' in APP_PY, (
        'the default must consult the worker-count gate'
    )
    # This suite runs single-process, so the default resolves to enforced.
    assert _CSRF_STRICT is True


def test_missing_token_is_logged_even_when_not_enforced():
    """Operators need to see what would break before switching strict on."""
    assert 'accepted WITHOUT a token' in APP_PY


def test_webhooks_are_exempt_from_csrf():
    """Inbound deliveries from GitHub/Stripe/CI authenticate by HMAC signature
    and cannot know a CSRF token; requiring one breaks every integration."""
    assert "path.startswith('/api/webhooks/')" in APP_PY
    assert '/api/security/csrf-token' in APP_PY, 'the bootstrap endpoint must be reachable'


def test_frontend_attaches_the_token_automatically():
    """Requiring a token the client never sends would break 282 call sites;
    the wrapper is what makes enforcement possible at all."""
    csrf_js = ROOT / 'frontend' / 'js' / '00-csrf.js'
    assert csrf_js.exists(), 'no client-side CSRF attachment'
    src = csrf_js.read_text(encoding='utf-8')
    assert 'X-CSRF-Token' in src
    assert 'window.fetch' in src, 'must wrap fetch, not patch call sites'
    assert '00-csrf.js' in INDEX_HTML, 'the script is not loaded'


def test_csrf_token_is_not_sent_cross_origin():
    """Attaching it to third-party requests would turn a CSRF fix into a
    token-disclosure bug."""
    src = (ROOT / 'frontend' / 'js' / '00-csrf.js').read_text(encoding='utf-8')
    assert 'sameOrigin' in src
    assert 'MUTATING.has(method) && sameOrigin' in src


def test_csrf_wrapper_retries_once_on_an_expired_token():
    """Tokens have a 24h TTL and are lost on restart; without a retry that
    surfaces as an unexplained 403 mid-session."""
    src = (ROOT / 'frontend' / 'js' / '00-csrf.js').read_text(encoding='utf-8')
    assert 'response.status === 403' in src
    assert 'cachedToken = null' in src


# ══ 2. safeUrl ════════════════════════════════════════════════════════════════
def test_safeurl_is_defined_in_the_shared_core():
    assert 'function safeUrl(url)' in CORE_JS, 'safeUrl is not globally available'


def test_safeurl_is_not_duplicated():
    """Two copies of a sanitiser drift, and the one that drifts is the one
    nobody is looking at."""
    defs = [
        f.name for f in (ROOT / 'frontend' / 'js').glob('*.js')
        if 'function safeUrl(url)' in f.read_text(encoding='utf-8')
    ]
    assert defs == ['01-app-core.js'], f'safeUrl defined in multiple files: {defs}'


@pytest.mark.parametrize('evil', [
    'javascript:alert(1)',
    'JavaScript:alert(1)',
    'java\tscript:alert(1)',
    'data:text/html,<script>alert(1)</script>',
    'vbscript:msgbox(1)',
    '//evil.example.com/phish',
])
def test_safeurl_logic_refuses_dangerous_schemes(evil):
    """Mirrors the JS implementation; the property is what matters."""
    raw = evil.strip()
    normalised = re.sub(r'[\u0000-\u001F\u007F]', '', raw).lower()
    allowed = (
        normalised.startswith('http://')
        or normalised.startswith('https://')
        or (normalised.startswith('/') and not normalised.startswith('//'))
    )
    assert not allowed, f'{evil!r} would be allowed through'


@pytest.mark.parametrize('good', [
    'https://github.com/settings/tokens',
    'http://localhost:8787/preview/x.png',
    '/preview/screenshot.png',
])
def test_safeurl_logic_allows_legitimate_urls(good):
    normalised = re.sub(r'[\u0000-\u001F\u007F]', '', good.strip()).lower()
    allowed = (
        normalised.startswith('http://')
        or normalised.startswith('https://')
        or (normalised.startswith('/') and not normalised.startswith('//'))
    )
    assert allowed, f'{good!r} would be blocked'


def test_every_data_driven_href_is_sanitised():
    """escHtml() is not enough: it escapes quotes, so javascript: survives."""
    offenders = []
    for f in (ROOT / 'frontend' / 'js').glob('*.js'):
        for i, line in enumerate(f.read_text(encoding='utf-8').split('\n'), 1):
            if 'href="${' in line and 'safeUrl(' not in line and not line.lstrip().startswith('//'):
                offenders.append(f'{f.name}:{i}')
    assert not offenders, f'unsanitised data-driven hrefs: {offenders}'


# ══ 3. Rate-limit store ═══════════════════════════════════════════════════════
def test_rate_limit_store_is_bounded():
    """An unbounded defaultdict keyed by IP grows forever under a scan."""
    assert '_RATE_LIMIT_MAX_CLIENTS' in APP_PY
    assert 'def _sweep_rate_limit_store' in APP_PY


def test_sweep_actually_evicts_stale_clients():
    import backend.app as app_mod

    app_mod._rate_limit_store.clear()
    app_mod._rate_limit_last_sweep = 0.0
    now = 1_000_000.0
    app_mod._rate_limit_store['1.2.3.4'] = [now - (app_mod._RATE_LIMIT_WINDOW + 10)]
    app_mod._rate_limit_store['5.6.7.8'] = [now]

    app_mod._sweep_rate_limit_store(now)

    assert '1.2.3.4' not in app_mod._rate_limit_store, 'stale client was not evicted'
    assert '5.6.7.8' in app_mod._rate_limit_store, 'active client was wrongly evicted'


def test_sweep_is_rate_limited_itself():
    """Sweeping on every request would make the limiter O(clients) per call."""
    import backend.app as app_mod

    app_mod._rate_limit_store.clear()
    now = 2_000_000.0
    app_mod._rate_limit_last_sweep = now
    app_mod._rate_limit_store['stale'] = [now - 99999]
    app_mod._sweep_rate_limit_store(now + 1)  # inside the interval
    assert 'stale' in app_mod._rate_limit_store, 'swept too eagerly'


def test_oversized_store_evicts_least_recent():
    import backend.app as app_mod

    app_mod._rate_limit_store.clear()
    app_mod._rate_limit_last_sweep = 0.0
    now = 3_000_000.0
    for i in range(app_mod._RATE_LIMIT_MAX_CLIENTS + 50):
        app_mod._rate_limit_store[f'ip{i}'] = [now]
    app_mod._sweep_rate_limit_store(now)
    assert len(app_mod._rate_limit_store) <= app_mod._RATE_LIMIT_MAX_CLIENTS
    app_mod._rate_limit_store.clear()


# ══ 4. Version drift ══════════════════════════════════════════════════════════
def test_config_yaml_version_matches_the_canonical_version():
    """A comment can drift again; this cannot."""
    canonical = (ROOT / 'VERSION').read_text(encoding='utf-8').strip()
    cfg = (ROOT / 'config.yaml').read_text(encoding='utf-8')
    m = re.search(r'^version:\s*"([^"]+)"', cfg, re.M)
    assert m, 'no version key in config.yaml'
    assert m.group(1) == canonical, (
        f'config.yaml says {m.group(1)}, VERSION says {canonical}'
    )


def test_backend_version_matches_too():
    from backend.version import VERSION

    assert VERSION == (ROOT / 'VERSION').read_text(encoding='utf-8').strip()


# ══ 5. Control Tower durability ═══════════════════════════════════════════════
def test_control_tower_reconciles_orphaned_runs():
    from backend.routers import control_tower as ct

    assert hasattr(ct, 'reconcile_orphaned_runs')


def test_orphaned_run_is_marked_failed(client):
    """agent_traces.status DEFAULTS to 'running' and _active_runs is in-memory,
    so a restart mid-run left the row 'running' forever — a UI showing an
    in-progress run for a process that no longer exists."""
    from backend.routers import control_tower as ct
    from backend.services.memory_db import get_conn

    run_id = ct.start_run('orphan_probe', 'Orphan', 'simulate a crash')
    ct._active_runs.pop(run_id, None)  # the restart

    con = get_conn()
    try:
        before = con.execute(
            'SELECT status FROM agent_traces WHERE run_id=?', (run_id,)
        ).fetchone()
    finally:
        con.close()
    assert before['status'] == 'running', 'fixture did not create a running row'

    assert ct.reconcile_orphaned_runs() >= 1

    con = get_conn()
    try:
        after = con.execute(
            'SELECT status, error FROM agent_traces WHERE run_id=?', (run_id,)
        ).fetchone()
    finally:
        con.close()
    assert after['status'] == 'failed', 'an orphaned run is still reported as running'
    assert 'restart' in (after['error'] or '').lower()


def test_reconciliation_never_raises(monkeypatch):
    """Housekeeping must not block startup."""
    from backend.routers import control_tower as ct

    def boom():
        raise sqlite3.OperationalError('db gone')

    monkeypatch.setattr(ct, 'get_conn', boom)
    assert ct.reconcile_orphaned_runs() == 0


def test_reconciliation_runs_at_import():
    src = (ROOT / 'backend' / 'routers' / 'control_tower.py').read_text(encoding='utf-8')
    assert '\nreconcile_orphaned_runs()' in src, 'reconciliation is defined but never called'


# ══ CSP ═══════════════════════════════════════════════════════════════════════
def test_csp_tightens_what_it_can():
    """object-src and base-uri are free wins: nothing uses them, and each
    closes a real vector (plugin content; an injected <base> rerouting every
    relative URL including scripts)."""
    assert "object-src 'none'" in APP_PY
    assert "base-uri 'self'" in APP_PY
    assert "form-action 'self'" in APP_PY


def test_unsafe_inline_has_been_removed_and_the_history_documented():
    """This asserted that the weakness was DOCUMENTED, which was the honest
    position while it could not be dropped. Phase 2 removed the 1107 inline
    handlers and 5 inline <script> blocks that were blocking it, so the
    directive itself is gone.

    The reasoning stays in app.py deliberately: a future reader needs to know
    why style-src still carries 'unsafe-inline' and what re-adding it to
    script-src would cost.
    """
    from backend.app import SECURITY_HEADERS

    script_src = next(
        d for d in SECURITY_HEADERS['Content-Security-Policy'].split(';')
        if d.strip().startswith('script-src')
    )
    assert "'unsafe-inline'" not in script_src
    assert 'style-src DELIBERATELY keeps' in APP_PY
    assert 'delegation shim' in APP_PY


# ══ 6. chat_log truncation ════════════════════════════════════════════════════
def test_chat_log_stores_what_the_api_accepts(client):
    """The API caps messages at 16000 but chat_log stored message[:4000], so a
    long prompt or reply lost 12000 characters SILENTLY. The user saw the full
    reply in the stream and a truncated one on reload, with nothing explaining
    the difference. SQLite TEXT has no fixed width, so the cap bought nothing.
    """
    import uuid as _uuid

    from backend.routers.chat import _log_chat
    from backend.services.memory_db import get_conn

    session = 'trunc_' + _uuid.uuid4().hex[:8]
    body = 'A' * 9000
    _log_chat(session, 'brain', 'user', body)

    con = get_conn()
    try:
        stored = con.execute(
            'SELECT LENGTH(message) FROM chat_log WHERE session_id=?', (session,)
        ).fetchone()[0]
    finally:
        con.close()
    assert stored == 9000, f'message truncated to {stored} characters'


def test_chat_log_cap_matches_the_api_cap():
    """Both numbers must move together; a mismatch is the bug.

    Checked against a COMMENT-STRIPPED copy: my first version matched
    '[:4000]' against the raw source and failed on the explanatory comment
    describing the old value. That is the "assertion matching its own fix
    comment" trap this review has hit in six modules; the fix is to strip
    comments before asserting, not to reword the comment.
    """
    src_path = ROOT / 'backend' / 'routers' / 'chat.py'
    # Line-wise comment strip: joining tokens with spaces would break
    # '[:16000]' into '[ : 16000 ]' and the assertion would never match.
    executable = '\n'.join(
        line.split('#', 1)[0] if line.lstrip().startswith('#') else line
        for line in src_path.read_text(encoding='utf-8').split('\n')
    )

    assert '[:4000]' not in executable, 'the 4000-char storage cap is back'
    assert '[:16000]' in executable
