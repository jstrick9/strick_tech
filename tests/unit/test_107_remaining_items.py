"""The outstanding items from the review, closed.

Covers: stateless CSRF (multi-worker), the rate-limit budget split, vendored
CDN assets, the tightened CSP, idempotent DELETEs reporting what they did,
and the TTS preference-store bounds.
"""
import glob
import os
import re
import time

import pytest

REPO = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

def _read(path: str) -> str:
    with open(path, encoding='utf-8') as fh:
        return fh.read()




# ══ Stateless CSRF ════════════════════════════════════════════════════════════

def test_csrf_tokens_verify_without_any_server_side_store():
    """The multi-worker fix.

    Tokens used to live in a per-process dict, so a token minted by worker A
    was unknown to worker B. Measured with `--workers 4` and enforcement on:
    of 60 POSTs carrying a VALID token, 13 succeeded and 47 returned 403.

    Stateless signing removes the failure entirely -- re-measured on the same
    setup, 60 of 60 were accepted. This test is the unit-level equivalent: a
    token must verify with no store consulted, because there is no store.
    """
    from backend.routers import security

    assert not hasattr(security, '_CSRF_TOKENS'), (
        'the per-process token dict is back; multi-worker deployments will '
        'reject roughly (workers-1)/workers of all valid tokens'
    )
    token = security.mint_csrf_token()
    assert security.csrf_token_is_valid(token)


def test_a_forged_or_tampered_token_is_refused():
    from backend.routers import security

    token = security.mint_csrf_token()
    issued, nonce, sig = token.split('.')

    for bad in (
        None, '', 'garbage', f'{issued}.{nonce}',                  # malformed
        f'{issued}.{nonce}.{"0" * len(sig)}',                      # wrong signature
        f'{int(issued) + 1}.{nonce}.{sig}',                        # tampered timestamp
        f'{issued}.{nonce}x.{sig}',                                # tampered nonce
    ):
        assert not security.csrf_token_is_valid(bad), f'accepted a bad token: {bad!r}'


def test_an_expired_token_is_refused():
    """The signature alone is not enough; the payload carries the expiry."""
    from backend.routers import security

    stale = int(time.time()) - security._TOKEN_TTL - 60
    payload = f'{stale}.abcdefgh'
    forged = f'{payload}.{security._sign(payload)}'
    # Correctly signed, but too old.
    assert not security.csrf_token_is_valid(forged)


def test_a_token_from_the_future_is_refused():
    """Otherwise an attacker who can influence the timestamp picks their own expiry."""
    from backend.routers import security

    future = int(time.time()) + 86400
    payload = f'{future}.abcdefgh'
    assert not security.csrf_token_is_valid(f'{payload}.{security._sign(payload)}')


def test_the_signature_is_checked_before_the_timestamp_is_trusted():
    """Order matters: parsing an attacker-supplied expiry first would let them
    choose it. A token with a valid-looking timestamp but no valid signature
    must be refused."""
    from backend.routers import security

    assert not security.csrf_token_is_valid(f'{int(time.time())}.nonce.notasignature')


def test_every_worker_shares_one_signing_key(tmp_path, monkeypatch):
    """Two processes reading the same data directory must agree.

    This is the property that makes the multi-worker fix work; if the key were
    per-process the original bug would be back with extra steps.
    """
    from backend.services import csrf_secret

    monkeypatch.setenv('AGENTIC_OS_DATA_DIR', str(tmp_path))
    monkeypatch.delenv('AGENTIC_CSRF_SECRET', raising=False)
    monkeypatch.delenv('SECRET_KEY', raising=False)

    csrf_secret.reset_for_tests()
    first = csrf_secret.get_secret()
    csrf_secret.reset_for_tests()          # simulate a second worker starting
    second = csrf_secret.get_secret()

    assert first == second, 'two workers derived different signing keys'
    assert csrf_secret.secret_source().startswith('file:')
    key_file = tmp_path / '.csrf_secret'
    assert key_file.exists()
    assert oct(key_file.stat().st_mode)[-3:] == '600', 'the signing key is world-readable'
    csrf_secret.reset_for_tests()


def test_a_short_configured_secret_is_refused(tmp_path, monkeypatch):
    """A 4-character key looks configured while being trivially brute-forced."""
    from backend.services import csrf_secret

    monkeypatch.setenv('AGENTIC_OS_DATA_DIR', str(tmp_path))
    monkeypatch.setenv('AGENTIC_CSRF_SECRET', 'shrt')
    csrf_secret.reset_for_tests()
    csrf_secret.get_secret()
    assert csrf_secret.secret_source() != 'env:AGENTIC_CSRF_SECRET', (
        'a 4-character signing key was accepted'
    )
    csrf_secret.reset_for_tests()


def test_csrf_enforcement_is_safe_in_every_topology():
    from backend.services import runtime_topology

    assert runtime_topology.csrf_strict_is_safe() is True


# ══ Rate limiting under multiple workers ══════════════════════════════════════

@pytest.mark.parametrize('workers,configured,expected_per_worker', [
    (1, 300, 300),
    (2, 300, 150),
    (4, 300, 75),
    (4, 20, 10),      # the floor: never below 10
    (100, 300, 10),   # a silly worker count must not produce an unusable limit
])
def test_the_rate_limit_budget_is_divided_across_workers(workers, configured, expected_per_worker):
    """The configured ceiling must be the one that applies.

    Each worker kept its own counter, so N workers allowed N x the configured
    limit. An operator who set 300 and ran 4 workers got 1200 and was never
    told -- the control degraded silently, which is the worst way for a limit
    to be wrong.
    """
    src = _read(os.path.join(REPO, 'backend', 'app.py'))
    assert '_RATE_LIMIT_CONFIGURED' in src, 'the budget split has been removed'
    assert '_RATE_LIMIT_CONFIGURED // _rate_limit_workers' in src

    got = (max(10, configured // workers)) if workers > 1 else configured
    assert got == expected_per_worker


# ══ Vendored assets and the tightened CSP ═════════════════════════════════════

def test_no_frontend_file_references_a_cdn():
    """Every third-party origin in script-src was an origin that could execute
    script with full same-origin privileges. Vendoring removes all five."""
    offenders = []
    targets = [os.path.join(REPO, 'frontend', 'index.html')]
    js_dir = os.path.join(REPO, 'frontend', 'js')
    targets += sorted(glob.glob(os.path.join(js_dir, '*.js')))
    for path in targets:
        src = _read(path)
        # Strip comments so an assertion cannot match the text of its OWN fix.
        # This is the 10th time that trap has been hit in this review: the
        # first version of this test failed against the fixed build, because
        # the HTML comment explaining why the fonts were vendored names the
        # very hostnames it is asserting are gone. Multi-line HTML comments
        # must be removed as a block, not line-by-line.
        code = re.sub(r'<!--.*?-->', '', src, flags=re.DOTALL)
        code = re.sub(r'/\*.*?\*/', '', code, flags=re.DOTALL)
        code = '\n'.join(l for l in code.split('\n') if not l.strip().startswith('//'))
        for host in ('cdn.jsdelivr.net', 'cdnjs.cloudflare.com', 'cdn.tailwindcss.com',
                     'unpkg.com', 'cdn.monaco-editor.net', 'fonts.googleapis.com',
                     'fonts.gstatic.com'):
            if host in code:
                offenders.append(f'{os.path.basename(path)} -> {host}')
    assert not offenders, 'frontend still loads from a CDN:\n' + '\n'.join(offenders)


def test_the_vendored_files_are_actually_present():
    """A repointed URL with no file behind it is worse than the CDN."""
    base = os.path.join(REPO, 'frontend', 'vendor')
    for rel in ('three.min.js', '3d-force-graph.min.js', 'highlight.min.js',
                'highlight-github-dark.min.css', 'monaco/vs/loader.js',
                'monaco/vs/editor/editor.main.js', 'fonts/inter.css'):
        path = os.path.join(base, rel)
        assert os.path.exists(path), f'missing vendored asset: {rel}'
        assert os.path.getsize(path) > 200, f'vendored asset looks truncated: {rel}'


def test_the_vendored_font_css_has_no_remote_references():
    css = _read(os.path.join(REPO, 'frontend', 'vendor', 'fonts', 'inter.css'))
    assert 'fonts.gstatic.com' not in css, 'the font css still points at Google'
    assert '.woff2' in css


def test_the_enforcing_csp_names_no_third_party_origin():
    """script-src 'self' plus five CDNs is materially weaker than 'self'."""
    import backend.app as app_mod

    csp = app_mod.SECURITY_HEADERS['Content-Security-Policy']
    script_src = next(d for d in csp.split(';') if d.strip().startswith('script-src'))
    assert script_src.strip() == "script-src 'self'", f'script-src is not locked down: {script_src}'
    assert "'unsafe-inline'" not in script_src


def test_connect_src_lists_no_external_origin():
    """connect-src limits where injected script can send data.

    Nine external origins were allowed and the browser contacted none of them
    -- every integration is called server-side with httpx, where CSP does not
    apply. Each entry was an exfiltration channel that bought nothing.
    """
    import backend.app as app_mod

    csp = app_mod.SECURITY_HEADERS['Content-Security-Policy']
    connect = next(d for d in csp.split(';') if d.strip().startswith('connect-src'))
    for host in ('api.github.com', 'openrouter.ai', 'slack.com', 'googleapis.com',
                 'graph.microsoft.com', 'atlassian.net', 'api.notion.com'):
        assert host not in connect, f'connect-src still allows {host}: {connect}'
    # The legitimate ones stay.
    assert "'self'" in connect and 'ws:' in connect and '127.0.0.1' in connect


def test_the_preview_policy_still_allows_cdns():
    """Generated pages legitimately use them; only the APP is locked down."""
    import backend.app as app_mod

    assert 'cdn.jsdelivr.net' in app_mod.PREVIEW_CSP, (
        'the preview policy was locked down too, which breaks AI-generated '
        'pages that load a library from a CDN'
    )


# ══ Idempotent DELETEs ════════════════════════════════════════════════════════

def test_idempotent_deletes_report_whether_anything_was_removed():
    """200 for a DELETE of something absent is correct and is KEPT.

    What was wrong is that the response could not distinguish it from a real
    deletion, so the UI reported success after a typo or a stale list. Each
    endpoint has the number already -- sqlite's rowcount -- and threw it away.
    """
    checks = {
        'specs.py': "'deleted': removed > 0",
        'hooks.py': "'deleted': removed > 0",
        'crdt.py': "'deleted': removed > 0",
        'replay.py': "'deleted': removed > 0",
        'multitab.py': "'deleted': existed",
        'rag.py': "'deleted': removed > 0",
        'codesearch.py': "'deleted': removed > 0",
        'pluginsdk.py': "'deleted': existed",
        'ambient.py': "'deleted': removed > 0",
        'marketplace.py': "'deleted': removed > 0",
        'agent_identity.py': "'deleted': removed > 0",
        'tts.py': "'deleted': existed",
    }
    missing = []
    for name, needle in checks.items():
        src = _read(os.path.join(REPO, 'backend', 'routers', name))
        if needle not in src:
            missing.append(f'{name} (expected {needle})')
    assert not missing, 'DELETE endpoints no longer report what they did:\n' + '\n'.join(missing)


def test_removing_an_absent_loop_is_a_success_not_an_error():
    """APScheduler raises for an unknown job, and that surfaced as ok:false.

    A DELETE of something already gone is a success. The same bug also skipped
    the local registry cleanup, because the pop sat after the raising call --
    so the job stayed listed forever and every retry hit the same error.
    """
    from backend.services import scheduler

    result = scheduler.remove_loop('definitely-not-a-real-job-id-9999')
    assert result.get('ok') is True, f'removing an absent loop reported failure: {result}'
    assert result.get('deleted') is False


def test_the_registry_is_cleaned_up_even_when_the_scheduler_raises():
    from backend.services import scheduler

    scheduler._jobs['probe-job-xyz'] = {'id': 'probe-job-xyz'}
    scheduler.remove_loop('probe-job-xyz')
    assert 'probe-job-xyz' not in scheduler._jobs, (
        'the job stayed in the local registry, so it remains listed in '
        '/api/loops and every retry hits the same error'
    )


# ══ TTS preference store ══════════════════════════════════════════════════════

def test_the_voice_preference_store_is_bounded():
    """It accepted any agent_id and persisted it, rewriting the whole file each
    time. A loop over generated ids grew it until the disk filled."""
    src = _read(os.path.join(REPO, 'backend', 'routers', 'tts.py'))
    assert '_MAX_VOICE_PREFS' in src, 'the preference store is unbounded again'
    assert 'status_code=409' in src


def test_an_unknown_voice_is_rejected_with_a_4xx():
    """It returned HTTP 200 with ok:false -- the 200-on-failure pattern already
    corrected across ~180 other endpoints."""
    src = _read(os.path.join(REPO, 'backend', 'routers', 'tts.py'))
    assert re.search(r"Unknown voice[^\n]*\n[^\n]*status_code=400|status_code=400", src), (
        'an unknown voice no longer returns a 4xx'
    )


def test_resetting_a_voice_matches_the_key_the_setter_wrote():
    """DELETE looked up the raw agent_id while PATCH stored it lowercased, so a
    preference saved as "Researcher" could never be reset -- and the endpoint
    still answered ok:true while the setting silently persisted."""
    src = _read(os.path.join(REPO, 'backend', 'routers', 'tts.py'))
    body = src.split("def reset_agent_voice")[1][:900]
    assert 'strip().lower()' in body, (
        'the reset path no longer normalises agent_id the same way the setter does'
    )
