"""CSP violation reports must actually reach the server.

THE BUG
───────
`/api/security/csp-report` was not in the CSRF exemption list. The BROWSER
posts these reports itself, from its own network stack, with no JavaScript
involved — so it cannot attach a CSRF token, and there is no way to make it.

The result, measured against the running app: the browser console showed
**1740 style violations** while the endpoint reported **0**.

A measurement channel that silently reads zero is worse than no channel,
because the zero looks like good news. This one had been reading zero since
CSRF enforcement was turned on, and the entire point of the Report-Only header
is to answer "what would break if we enforced this?" — a question it was
answering with "nothing".

Exempting it is safe: the endpoint appends to a bounded in-memory ring buffer,
returns nothing to the poster, and performs no state change a forged request
could exploit.
"""

from __future__ import annotations

import json


def test_the_report_endpoint_is_csrf_exempt():
    from backend.app import _CSRF_EXEMPT

    assert '/api/security/csp-report' in _CSRF_EXEMPT, (
        'the browser cannot attach a CSRF token to a violation report, so '
        'enforcing CSRF here discards every one of them'
    )


def test_a_browser_style_report_is_accepted(client):
    """Exactly the shape a browser sends: no token, no cookies, its own
    content type."""
    r = client.post(
        '/api/security/csp-report',
        content=json.dumps({
            'csp-report': {
                'violated-directive': 'style-src-attr',
                'blocked-uri': 'inline',
                'source-file': 'http://127.0.0.1:8787/',
                'line-number': 1311,
            }
        }),
        headers={'Content-Type': 'application/csp-report'},
    )
    assert r.status_code == 200, (
        f'a browser CSP report was rejected with {r.status_code}; the '
        f'measurement channel is dead'
    )


def test_a_reported_violation_is_retrievable(client):
    client.delete('/api/security/csp-report')
    client.post(
        '/api/security/csp-report',
        content=json.dumps({'csp-report': {
            'violated-directive': 'style-src-attr',
            'blocked-uri': 'inline',
            'source-file': 'probe.js',
            'line-number': 42,
        }}),
        headers={'Content-Type': 'application/csp-report'},
    )
    body = client.get('/api/security/csp-report').json()
    assert body['total'] >= 1, 'the report was accepted but not stored'
    assert any(v.get('line_number') == 42 for v in body['violations'])
    client.delete('/api/security/csp-report')


def test_repeated_violations_aggregate_rather_than_flood(client):
    """One broken selector on a polling render would otherwise fill the
    buffer with identical entries and evict everything useful."""
    client.delete('/api/security/csp-report')
    payload = json.dumps({'csp-report': {
        'violated-directive': 'style-src-attr',
        'blocked-uri': 'inline',
        'source-file': 'same.js',
        'line-number': 7,
    }})
    for _ in range(12):
        client.post('/api/security/csp-report', content=payload,
                    headers={'Content-Type': 'application/csp-report'})
    body = client.get('/api/security/csp-report').json()
    assert body['distinct'] == 1, f'12 identical reports made {body["distinct"]} entries'
    assert body['total'] >= 12
    client.delete('/api/security/csp-report')


# ══ The Report-Only header must test something ════════════════════════════════
def test_report_only_is_stricter_than_the_enforcing_policy():
    """The header's only job is to measure the NEXT tightening. Once the
    enforcing policy caught up with it — which happened when script-src
    dropped 'unsafe-inline' — the two were byte-identical apart from
    report-uri, so it reported on rules already in force and collected nothing.

    It must always be strictly ahead of what is enforced, or it is dead weight
    that looks like coverage.
    """
    from backend.app import CSP_REPORT_ONLY, SECURITY_HEADERS

    def directives(policy: str) -> dict[str, str]:
        out = {}
        for part in policy.split(';'):
            part = part.strip()
            if part:
                out[part.split(' ')[0]] = part
        return out

    enforcing = directives(SECURITY_HEADERS['Content-Security-Policy'])
    report_only = directives(CSP_REPORT_ONLY)

    stricter = [
        k for k in report_only
        if k in enforcing and report_only[k] != enforcing[k]
    ]
    assert stricter, (
        'the Report-Only policy is identical to the enforcing one; it is '
        'measuring nothing. Point it at the next tightening.'
    )


def test_report_only_does_not_re_report_the_enforced_style_src():
    """UPDATED: strict style-src is now ENFORCED, so previewing it in
    Report-Only collects nothing and floods the endpoint.

    00-style-hydrate.js re-applies each refused style attribute through the
    CSSOM, but the parser refuses it FIRST -- so every one of ~660 attributes
    emitted a violation report. Measured: 662 reports per page load, 86% of all
    load traffic, burying every real signal in the dashboard.

    style-src must be listed EXPLICITLY as permissive here. Merely omitting it
    falls back to `default-src 'self'`, which still governs styles -- that was
    tried first and changed nothing.
    """
    from backend.app import CSP_REPORT_ONLY

    style = next(
        (d for d in CSP_REPORT_ONLY.split(';') if d.strip().startswith('style-src')), None
    )
    assert style is not None, (
        'style-src must be listed explicitly; omitting it falls back to '
        "default-src 'self' and the reports keep firing"
    )
    assert "'unsafe-inline'" in style, (
        f'Report-Only restricts styles again, which floods the endpoint: {style}'
    )


def test_the_report_only_policy_is_a_ratchet_not_a_copy(client):
    """REPLACED. This asserted the enforcing style-src still had
    'unsafe-inline', on the grounds that dropping it "would break 4494 static
    inline styles". It has now been dropped, and nothing broke -- see
    frontend/js/00-style-hydrate.js and
    tests/e2e_browser/test_e2e_browser_08_strict_style_src.py.

    What must remain true is the reason this header exists: Report-Only is for
    measuring the NEXT tightening. The moment it matches the enforcing policy
    it reports on rules already in force and collects nothing, which is the
    trap it fell into once before. It must differ in at least one directive.
    """
    resp = client.get('/api/health')
    enforcing = resp.headers.get('content-security-policy', '')
    report_only = resp.headers.get('content-security-policy-report-only', '')
    assert report_only, 'the Report-Only header is gone'

    def directives(policy):
        return {d.strip().split(' ')[0]: d.strip() for d in policy.split(';') if d.strip()}

    enf, ro = directives(enforcing), directives(report_only)
    differing = [k for k in ro if k in enf and ro[k] != enf[k]]
    assert differing, (
        'Report-Only is identical to the enforcing policy, so it measures '
        'nothing. Point it at the next directive to tighten.'
    )
    # It is currently pointed at img-src, which still allows `https:` -- the
    # last directive that lets a request leave the machine.
    assert 'img-src' in differing, f'expected img-src to be the ratchet, got {differing}'


# ══ The dashboard ═════════════════════════════════════════════════════════════
# The reports had been collected since the header was introduced and were
# invisible to anyone who did not curl the endpoint. That is how the channel
# managed to sit at zero for weeks: the only way to notice was to ask the API.
def test_the_monitor_module_exists_and_is_loaded():
    import pathlib

    root = pathlib.Path(__file__).resolve().parents[2]
    assert (root / 'frontend' / 'js' / '58-csp-monitor.js').exists()
    index = (root / 'frontend' / 'index.html').read_text(encoding='utf-8')
    assert '58-csp-monitor.js' in index


def test_the_security_tab_is_reachable():
    import pathlib

    index = (pathlib.Path(__file__).resolve().parents[2]
             / 'frontend' / 'index.html').read_text(encoding='utf-8')
    assert 'id="settings-nav-security"' in index, 'no way to reach the panel'
    assert 'id="settings-tab-security"' in index
    assert "switchSettingsTab('security')" in index


def test_the_panel_loads_lazily():
    """The endpoint is cheap, but polling it on every settings visit would be
    noise for a panel most users never open."""
    import pathlib

    core = (pathlib.Path(__file__).resolve().parents[2]
            / 'frontend' / 'js' / '01-app-core.js').read_text(encoding='utf-8')
    assert "tabId === 'security'" in core
    assert 'renderCspMonitor' in core


def test_the_panel_separates_our_code_from_third_party():
    """Third-party violations come from vendored libraries injecting their own
    styles. They cannot be fixed here, so counting them alongside our own would
    overstate the migration cost."""
    import pathlib

    src = (pathlib.Path(__file__).resolve().parents[2]
           / 'frontend' / 'js' / '58-csp-monitor.js').read_text(encoding='utf-8')
    assert 'isThirdParty' in src
    assert 'In our code' in src


def test_an_empty_report_list_does_not_read_as_success():
    """The failure this whole fix is about: zero violations can mean 'safe to
    enforce' OR 'the channel is broken / nothing was exercised'. The panel must
    not let the reader assume the first."""
    import pathlib

    src = (pathlib.Path(__file__).resolve().parents[2]
           / 'frontend' / 'js' / '58-csp-monitor.js').read_text(encoding='utf-8')
    assert 'has not been exercised' in src, (
        'an empty list must say what else it could mean'
    )
