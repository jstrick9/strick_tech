"""Live Preview under the enforcing CSP, and a vault audit that can fail.

Both bugs found by driving the real app in Chromium and reading what the
browser actually reported, rather than by reading code.
"""
import pytest

BASE = "http://127.0.0.1:8787"

_DISMISS = """
() => {
  for (const id of ['onboarding-overlay', 'onboarding-modal', 'welcome-banner']) {
    const el = document.getElementById(id);
    if (el) el.remove();
  }
  try { localStorage.setItem('agentic_os_onboarded', '1'); } catch (_) {}
}
"""


def _boot(page):
    page.goto(BASE)
    page.wait_for_load_state('domcontentloaded')
    page.wait_for_function('typeof window.__delegateDispatch === "function"', timeout=15000)
    page.wait_for_timeout(800)
    page.evaluate(_DISMISS)
    page.wait_for_timeout(200)
    return page


# ══ Live Preview ══════════════════════════════════════════════════════════════

def test_inline_script_runs_in_a_preview_document(page, tmp_path):
    """CSP phase 2 killed the entire Live Preview feature.

    Phase 2 dropped script-src 'unsafe-inline' from the enforcing policy, which
    was right for the application — but the middleware applied that same policy
    to /preview/, and /preview/ is not the application. It serves the HTML the
    user writes in Code Studio and the HTML the agent generates, essentially
    all of which carries inline <script>.

    Measured in Chromium before the fix: a preview page whose inline script
    rewrites an <h1> still showed the pre-script text, with
    "Refused to execute inline script ... script-src 'self'" in the console.

    The Report-Only policy already carried a /preview/ exemption. The enforcing
    one never got the matching change — the "second door" pattern.
    """
    import os
    data_dir = os.environ.get('AGENTIC_OS_DATA_DIR', '/tmp/agentic-test-data')
    preview_dir = os.path.join(data_dir, 'preview')
    if not os.path.isdir(preview_dir):
        pytest.skip(f'no preview directory at {preview_dir}')

    target = os.path.join(preview_dir, '_csp_probe.html')
    with open(target, 'w') as fh:
        fh.write(
            '<!doctype html><html><body><h1 id="h">BEFORE</h1>'
            '<script>document.getElementById("h").textContent="INLINE SCRIPT RAN";</script>'
            '</body></html>'
        )
    try:
        blocked = []
        page.on('console', lambda m: blocked.append(m.text[:200])
                if 'Refused to execute inline script' in m.text else None)
        page.goto(f'{BASE}/preview/_csp_probe.html')
        page.wait_for_load_state('domcontentloaded')
        page.wait_for_timeout(600)

        assert not blocked, 'CSP blocked inline script in a preview document:\n' + '\n'.join(blocked)
        assert page.text_content('#h') == 'INLINE SCRIPT RAN', (
            'inline script did not execute in the preview frame — Live Preview '
            'cannot render any generated page that contains script'
        )
    finally:
        try:
            os.remove(target)
        except OSError:
            pass


def test_the_preview_policy_is_still_tighter_where_it_matters(page):
    """Restoring inline script must not turn /preview/ into an open origin.

    Preview documents are untrusted content, so the directives that matter for
    untrusted content stay locked: it may not be framed by another origin, it
    may not submit a form anywhere, it may not load plugin content, and an
    injected <base> may not reroute the page.
    """
    resp = page.request.get(f'{BASE}/preview/index.html')
    csp = resp.headers.get('content-security-policy', '')
    assert csp, '/preview/ is served with no CSP at all'

    for directive in ["form-action 'none'", "object-src 'none'",
                      "base-uri 'none'", "frame-ancestors 'self'"]:
        assert directive in csp, f'preview CSP is missing `{directive}`: {csp}'


def test_the_application_itself_still_forbids_inline_script(page):
    """The preview exemption must not leak back onto the app.

    If it did, it would undo CSP phases 1-3 in a single header.
    """
    resp = page.request.get(BASE + '/')
    csp = resp.headers.get('content-security-policy', '')
    script_src = next((d for d in csp.split(';') if d.strip().startswith('script-src')), '')
    assert script_src, f'no script-src in the application CSP: {csp}'
    assert "'unsafe-inline'" not in script_src, (
        f"'unsafe-inline' is back in the application's script-src: {script_src}"
    )


def test_svg_hardening_still_wins_over_the_preview_policy(page):
    """Order matters: the SVG override is applied after the preview policy.

    An SVG served from our own origin is executable XML. If the looser preview
    policy overwrote the SVG lockdown, a stored SVG would regain the ability to
    run same-origin script — a strictly worse bug than the one being fixed.
    """
    import os
    data_dir = os.environ.get('AGENTIC_OS_DATA_DIR', '/tmp/agentic-test-data')
    preview_dir = os.path.join(data_dir, 'preview')
    if not os.path.isdir(preview_dir):
        pytest.skip(f'no preview directory at {preview_dir}')

    target = os.path.join(preview_dir, '_probe.svg')
    with open(target, 'w') as fh:
        fh.write('<svg xmlns="http://www.w3.org/2000/svg"></svg>')
    try:
        resp = page.request.get(f'{BASE}/preview/_probe.svg')
        csp = resp.headers.get('content-security-policy', '')
        assert "default-src 'none'" in csp, (
            f'the preview policy overwrote the SVG lockdown: {csp}'
        )
        assert "'unsafe-inline'" not in csp.split('style-src')[0], (
            f'script execution is no longer denied for SVG: {csp}'
        )
    finally:
        try:
            os.remove(target)
        except OSError:
            pass


# ══ Vault audit ═══════════════════════════════════════════════════════════════

def test_the_vault_audit_reports_failure_when_the_vault_is_not_encrypted(page):
    """The audit could not fail.

    Whatever /api/secrets/get returned, it rendered "✅ Local Cryptographic
    Secret Vault Verified (100% Zero-Trust)" and toasted "vault audit green".
    A 404 produced a pass. So did a vault running with no encryption at all.
    It also asserted a macOS storage root, a "Hardware Master Key" and
    "Kyber-1024 hybrid wrapping" that nothing ever checked.

    A security control that always reports success is worse than none: it
    tells the user their secrets are encrypted when they may not be.
    """
    _boot(page)
    page.route("**/api/secrets/list", lambda route: route.fulfill(
        status=200, content_type="application/json",
        body='{"ok":true,"count":3,"items":[],"encrypted":false,'
             '"engine":"Base64 (install cryptography for encryption)",'
             '"vault_path":"/tmp/x/.vault_key",'
             '"warning":"Install cryptography for real encryption"}'))

    page.evaluate('() => window.checkVaultIntegrity()')
    page.wait_for_timeout(1200)
    text = page.evaluate("() => document.getElementById('vault-audit-result').innerText")

    assert 'NOT encrypted' in text, (
        f'an unencrypted vault was not reported as a failure. Rendered:\n{text}'
    )
    assert '✅' not in text, f'an unencrypted vault still rendered a pass marker:\n{text}'
    assert 'Base64' in text, 'the audit does not report which engine is actually in use'
    assert 'Install cryptography' in text, "the backend's remediation warning is not surfaced"


def test_the_vault_audit_reports_failure_when_the_vault_cannot_be_read(page):
    _boot(page)
    page.route("**/api/secrets/list", lambda route: route.fulfill(status=500, body='boom'))

    page.evaluate('() => window.checkVaultIntegrity()')
    page.wait_for_timeout(1200)
    text = page.evaluate("() => document.getElementById('vault-audit-result').innerText")

    assert 'failed' in text.lower(), f'an unreadable vault was not reported as a failure:\n{text}'
    assert '500' in text, f'the audit hides why it failed:\n{text}'


def test_the_vault_audit_passes_honestly_when_encryption_is_on(page):
    """And it must still pass in the good case, reporting real values.

    In particular "no OpenRouter key stored" is a normal state and must read as
    "not configured" rather than as an audit failure.
    """
    _boot(page)
    page.evaluate('() => window.checkVaultIntegrity()')
    page.wait_for_timeout(1500)
    text = page.evaluate("() => document.getElementById('vault-audit-result').innerText")

    assert 'encrypted at rest' in text, f'a healthy vault did not pass:\n{text}'
    assert 'NOT encrypted' not in text
    # The old version hardcoded a macOS path the backend never reported.
    assert 'Library/Application Support' not in text, (
        'the audit is still printing a hardcoded storage path it never verified'
    )
    assert 'Kyber' not in text, 'the audit still claims post-quantum wrapping it never checks'
