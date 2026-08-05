"""Multi-worker detection, and CSRF enforcement on by default.

Two recommendation items, which turned out to be one problem.

The docs treated them separately: "warn when workers > 1" (low urgency, rate
limiting merely degrades) and "flip the CSRF default" (medium urgency). That
framing missed that `_CSRF_TOKENS` is *also* a per-process dict, so the two
interact — turning CSRF enforcement on by default would break every
multi-worker deployment.

Measured against a real 4-worker server before the gate existed: of 60 POSTs
carrying a VALID token, 27 succeeded and 33 returned 403. That is not a
degradation, it is an outage on roughly half of all user actions.

So the detector is a prerequisite for the flip, not a parallel task.
"""

from __future__ import annotations

import importlib
import os

import pytest

from backend.services import runtime_topology as rt


@pytest.fixture
def clean_env(monkeypatch):
    """Remove every worker-count signal so a test starts from 'single'."""
    for name in (
        'WEB_CONCURRENCY', 'UVICORN_WORKERS', 'GUNICORN_WORKERS', 'WORKERS',
        'SERVER_SOFTWARE', 'AGENTIC_ACK_MULTIPROCESS', 'AGENTIC_CSRF_STRICT',
    ):
        monkeypatch.delenv(name, raising=False)
    monkeypatch.setattr(rt.sys, 'argv', ['uvicorn', 'backend.app:app'])
    return monkeypatch


# ══ Detection ═════════════════════════════════════════════════════════════════
def test_single_process_is_the_default(clean_env):
    assert rt.worker_count() == 1
    assert rt.is_multiprocess() is False
    assert rt.csrf_strict_is_safe() is True


@pytest.mark.parametrize(
    'var', ['WEB_CONCURRENCY', 'UVICORN_WORKERS', 'GUNICORN_WORKERS', 'WORKERS']
)
def test_worker_count_from_each_env_var(clean_env, var):
    clean_env.setenv(var, '4')
    assert rt.worker_count() == 4
    assert rt.is_multiprocess() is True


@pytest.mark.parametrize(
    'argv,expected',
    [
        (['uvicorn', 'app', '--workers', '3'], 3),
        (['uvicorn', 'app', '--workers=5'], 5),
        (['gunicorn', '-w', '8', 'app'], 8),
        (['uvicorn', 'app'], 1),
        (['uvicorn', 'app', '--workers'], 1),          # missing value
        (['uvicorn', 'app', '--workers', 'abc'], 1),   # unparseable
        (['uvicorn', 'app', '--workers', '0'], 1),     # nonsense value
        (['uvicorn', 'app', '--workers', '-2'], 1),    # negative
    ],
)
def test_worker_count_from_argv(clean_env, argv, expected):
    """`--workers N` sets no environment variable, and it is how this is
    almost always spelled in practice."""
    clean_env.setattr(rt.sys, 'argv', argv)
    assert rt.worker_count() == expected


def test_gunicorn_is_detected_without_a_countable_value(clean_env):
    """A gunicorn worker may not see the master's -w on its own argv. Report
    2 — the smallest value that is still 'more than one' — rather than
    inventing a figure or missing the condition entirely."""
    clean_env.setenv('SERVER_SOFTWARE', 'gunicorn/21.2.0')
    assert rt.worker_count() == 2
    assert rt.is_multiprocess() is True


def test_env_takes_precedence_over_argv(clean_env):
    clean_env.setenv('WEB_CONCURRENCY', '6')
    clean_env.setattr(rt.sys, 'argv', ['uvicorn', 'app', '--workers', '2'])
    assert rt.worker_count() == 6


def test_describe_reports_how_it_decided(clean_env):
    assert rt.describe()['detected_via'] == 'default'
    clean_env.setenv('WEB_CONCURRENCY', '2')
    d = rt.describe()
    assert d['detected_via'] == 'env'
    assert d['multiprocess'] is True
    assert 'csrf_tokens' in d['per_process_state']


# ══ The warning ═══════════════════════════════════════════════════════════════
def test_no_warning_for_a_single_worker(clean_env):
    assert rt.warn_if_multiprocess(rate_limit_max=300, csrf_strict=True) == []


def test_warning_names_the_effective_rate_limit(clean_env):
    """A warning that says 'this is per-process' is easy to skim past. One
    that says 'you asked for 300, you are getting 1200' is not."""
    clean_env.setenv('WEB_CONCURRENCY', '4')
    text = ' '.join(rt.warn_if_multiprocess(rate_limit_max=300, csrf_strict=False))
    assert '4 worker' in text
    assert '300' in text and '1200' in text


def test_warning_escalates_when_csrf_enforcement_is_on(clean_env):
    """With enforcement on this stops being a degradation and becomes an
    outage, so the message has to say so."""
    clean_env.setenv('WEB_CONCURRENCY', '4')
    on = ' '.join(rt.warn_if_multiprocess(rate_limit_max=300, csrf_strict=True))
    assert '403' in on
    assert 'AGENTIC_CSRF_STRICT=0' in on

    off = ' '.join(rt.warn_if_multiprocess(rate_limit_max=300, csrf_strict=False))
    assert '403' not in off
    assert 'do NOT' in off


def test_acknowledgement_downgrades_severity_but_keeps_the_message(clean_env, caplog):
    """An operator who has understood the trade-off should not be nagged at
    WARNING forever — but silencing it entirely would lose the record."""
    clean_env.setenv('WEB_CONCURRENCY', '2')
    clean_env.setenv('AGENTIC_ACK_MULTIPROCESS', '1')

    with caplog.at_level('INFO', logger='agentic.topology'):
        messages = rt.warn_if_multiprocess(rate_limit_max=300, csrf_strict=False)

    assert messages, 'acknowledging must not suppress the content'
    assert not [r for r in caplog.records if r.levelname == 'WARNING']
    assert [r for r in caplog.records if r.levelname == 'INFO']


# ══ The CSRF default ══════════════════════════════════════════════════════════
def _csrf_default(monkeypatch, **env) -> bool:
    """Read back the CSRF default that backend.app ACTUALLY computes.

    An earlier version of this helper re-implemented the decision here and
    compared the result against itself, so it agreed with any implementation
    and caught nothing: reverting app.py to the old permissive env read failed
    only 1 of 39 tests. The module is reloaded under the patched environment
    instead, so these tests read the real value.
    """
    for name in ('WEB_CONCURRENCY', 'UVICORN_WORKERS', 'GUNICORN_WORKERS',
                 'WORKERS', 'AGENTIC_CSRF_STRICT', 'SERVER_SOFTWARE'):
        monkeypatch.delenv(name, raising=False)
    for k, v in env.items():
        monkeypatch.setenv(k, v)
    monkeypatch.setattr(rt.sys, 'argv', ['uvicorn', 'backend.app:app'])

    import backend.app as app_mod

    # Re-executing app.py is slow and has import side effects; the CSRF default
    # is a module-level constant, so evaluate the same source in isolation.
    # Sliced by line rather than matched with a regex — the first attempt used
    # a non-greedy multiline pattern that silently failed to match, turning
    # every one of these tests red against correct code.
    import inspect

    lines = inspect.getsource(app_mod).split('\n')
    # The assignments live inside an if/elif/else, so match the STRIPPED line —
    # anchoring to column 0 found the opening line but never the branches.
    starts = [i for i, ln in enumerate(lines) if ln.startswith('_csrf_strict_env = ')]
    ends = [i for i, ln in enumerate(lines) if ln.strip().startswith('_CSRF_STRICT = ')]
    assert starts and ends and ends[-1] > starts[0], (
        'backend/app.py no longer computes _CSRF_STRICT through the documented '
        'gate. If the default was simplified back to a plain env read, the '
        'multi-worker outage (27 of 60 valid-token POSTs rejected) is back.'
    )
    snippet = '\n'.join(lines[starts[0]: ends[-1] + 1])
    assert 'runtime_topology' in snippet, (
        'the CSRF default no longer consults the worker-count gate: ' + snippet
    )
    namespace: dict = {'os': os, 'runtime_topology': rt}
    exec(snippet, namespace)  # noqa: S102 — evaluating our own source
    return namespace['_CSRF_STRICT']


def test_csrf_is_enforced_by_default_on_a_single_worker(monkeypatch):
    """The flip. 'Off by default' was a migration state, not an end state:
    left indefinitely the protection ships disabled and the security property
    only exists for operators who read release notes."""
    assert _csrf_default(monkeypatch) is True


def test_csrf_default_yields_to_off_under_multiple_workers(monkeypatch):
    """Because _CSRF_TOKENS is per-process. Enforcing here would reject
    roughly (workers-1)/workers of all mutations DESPITE a valid token."""
    assert _csrf_default(monkeypatch, WEB_CONCURRENCY='4') is False


@pytest.mark.parametrize('value', ['1', 'true', 'yes', 'on', 'TRUE', 'On'])
def test_explicit_on_is_honoured_even_when_unsafe(monkeypatch, value):
    """An operator who insists is allowed to — they may have a sticky-session
    load balancer. They are warned loudly at startup."""
    assert _csrf_default(monkeypatch, WEB_CONCURRENCY='4', AGENTIC_CSRF_STRICT=value) is True


@pytest.mark.parametrize('value', ['0', 'false', 'no', 'off', 'OFF'])
def test_explicit_off_is_honoured(monkeypatch, value):
    """The documented escape hatch for a deployment whose scripted clients
    cannot yet fetch a token."""
    assert _csrf_default(monkeypatch, AGENTIC_CSRF_STRICT=value) is False


def test_the_app_module_actually_uses_the_gate():
    """Guards against the default being changed back to a plain env read,
    which would reintroduce the multi-worker outage silently."""
    import inspect

    import backend.app as app_mod

    src = inspect.getsource(app_mod)
    assert 'runtime_topology.csrf_strict_is_safe()' in src
    assert 'runtime_topology.warn_if_multiprocess' in src


# ══ The exemption list ════════════════════════════════════════════════════════
# Exemption lists grow quietly under delivery pressure, and a CSRF exemption is
# exactly the kind of thing added at 5pm to unblock something. Pinning the list
# makes each addition a deliberate decision with a visible diff, rather than a
# line nobody reviews.
EXPECTED_CSRF_EXEMPT = {
    '/api/security/csrf-token',  # must be reachable to bootstrap a token
    '/api/health',               # liveness probes cannot fetch a token
    # CSP violation reports. The BROWSER posts these from its own network
    # stack with no JavaScript involved, so it cannot attach a token and there
    # is no way to make it. Enforcing CSRF here protected nothing and simply
    # discarded the reports: the console showed 1740 violations while the
    # endpoint reported 0. Appends to a bounded in-memory buffer, returns no
    # data, changes no state a forged request could exploit.
    '/api/security/csp-report',
}


def test_csrf_exemption_list_has_not_grown():
    from backend.app import _CSRF_EXEMPT

    actual = set(_CSRF_EXEMPT)
    added = actual - EXPECTED_CSRF_EXEMPT
    removed = EXPECTED_CSRF_EXEMPT - actual
    assert not added, (
        f'New CSRF exemption(s): {sorted(added)}. Each one is a route that '
        f'accepts state-changing requests with no CSRF protection. If it is '
        f'genuinely necessary, add it to EXPECTED_CSRF_EXEMPT with a comment '
        f'saying why — that is the review this test exists to force.'
    )
    assert not removed, f'Exemption removed without updating this test: {sorted(removed)}'


def test_webhook_prefix_is_the_only_wildcard_exemption():
    """/api/webhooks/* is exempt because deliveries carry an HMAC signature and
    come from GitHub/Stripe/CI, which cannot know a CSRF token. A SECOND
    prefix exemption would be a much bigger hole than a single path, so the
    count is pinned."""
    import inspect

    import backend.app as app_mod

    src = inspect.getsource(app_mod)
    prefix_checks = src.count("path.startswith('/api/webhooks/')")
    assert prefix_checks == 1, (
        f'expected exactly one prefix-based CSRF exemption, found {prefix_checks}'
    )


def test_exempt_paths_are_not_state_changing_business_routes():
    """A sanity check on the shape of what may be exempt."""
    from backend.app import _CSRF_EXEMPT

    # Each shape has to earn its place. 'csp' joins the list because a browser
    # -originated report genuinely cannot carry a token — that is a property of
    # the reporting mechanism, not a convenience.
    for path in _CSRF_EXEMPT:
        assert path.startswith('/api/'), path
        assert any(k in path for k in ('health', 'csrf', 'csp')), (
            f'{path} is exempt from CSRF but is not a health probe, the token '
            f'endpoint, or a browser-originated report — justify it explicitly'
        )


# ══ Documentation must survive with the code ══════════════════════════════════
def test_config_documents_the_per_process_ceiling():
    """Recommendation item 2 asked for this specifically: one line in
    config.yaml next to the rate-limit settings."""
    import pathlib

    text = (pathlib.Path(__file__).resolve().parents[2] / 'config.yaml').read_text()
    assert 'PER PROCESS' in text or 'per-process' in text
    assert 'RATE_LIMIT_MAX' in text
    assert 'AGENTIC_CSRF_STRICT' in text


def test_the_measured_evidence_is_recorded_in_the_source():
    """The 27/33 measurement is the whole justification for the gate. If it
    lives only in a commit message it will be lost the first time someone
    'simplifies' the default back to an env read."""
    import inspect

    import backend.app as app_mod

    assert '27 succeeded and 33' in inspect.getsource(app_mod)


# ══ Internal loopback calls ═══════════════════════════════════════════════════
# Three routes reach this server's OWN API over loopback:
#   goal_manager  /api/goals/{id}/launch -> POST /api/supervisor/run
#   mcp_gateway   tool dispatch          -> POST /api/mcp/call
#   mcp_gateway   HITL gate              -> POST /api/hitl/interrupt
# Enforcing CSRF broke all three — the server began rejecting itself with 403.
def test_internal_callers_do_not_use_a_bare_httpx_client():
    """A plain client sends no token, so the call 403s. Caught in review as
    `POST /api/goals/{id}/launch` returning 'CSRF token required.'"""
    import pathlib

    root = pathlib.Path(__file__).resolve().parents[2]
    for rel in ('backend/routers/goal_manager.py', 'backend/routers/mcp_gateway.py'):
        text = (root / rel).read_text(encoding='utf-8')
        assert 'internal_http.async_client' in text, f'{rel} lost the CSRF-aware client'
        assert "httpx.AsyncClient(timeout" not in text, (
            f'{rel} still builds a bare loopback client; it will be rejected'
        )


def test_loopback_addresses_are_not_csrf_exempt():
    """The tempting shortcut, deliberately NOT taken.

    A request from 127.0.0.1 is not inherently trustworthy — a malicious
    postinstall script, a sidecar container, or a browser extension proxying
    through a local port can all originate one. Exempting the address would
    turn CSRF from 'prove you are the app' into 'prove you are on this
    machine', undoing the control for an attacker who already has a local
    foothold.
    """
    import inspect

    import backend.app as app_mod

    src = inspect.getsource(app_mod)
    csrf_block = src[src.index('# CSRF validation.'):src.index('# Process request')]
    for marker in ('127.0.0.1', 'localhost', 'client.host', 'is_loopback'):
        assert marker not in csrf_block, (
            f'CSRF validation appears to branch on {marker!r} — a loopback '
            f'exemption is a bypass, not a fix'
        )


def test_internal_http_prefers_a_token_the_listener_will_accept():
    """When the calling process is not the serving process (the in-process
    TestClient suites against a separately-started server), a locally minted
    token is in the wrong store and gets rejected. Ask the listener first."""
    from backend.services import internal_http

    src = __import__('inspect').getsource(internal_http)
    assert '_fetch_token_over_http' in src
    assert 'mint_token()' in src, 'the local fallback must remain'


def test_internal_http_caches_its_token():
    """Fetching per call added a round trip to every MCP dispatch and
    supervisor launch: the suite went 165s -> 437s and two concurrency tests
    failed. A token is reusable until it expires."""
    from backend.services import internal_http

    internal_http._invalidate_cache()
    first = internal_http.headers()['X-CSRF-Token']
    second = internal_http.headers()['X-CSRF-Token']
    assert first == second, 'token is being re-fetched on every call'
    assert internal_http._CACHE_SECONDS < 86400, 'cache must expire inside the TTL'
