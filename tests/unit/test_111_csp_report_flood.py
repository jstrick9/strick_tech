"""A page load must not fire hundreds of CSP violation reports.

THE BUG
───────
Measured in Chromium: one page load fired **775 HTTP requests, 662 of them
POSTs to /api/security/csp-report** -- 86% of all load traffic.

Cause: batch 22 enforced strict `style-src 'self'` and added
00-style-hydrate.js, which re-applies each refused style attribute through the
CSSOM. The parser still REFUSES the attribute first (that is the mechanism), so
the browser emits a report for each of ~660 style attributes, and the hydrator
then silently fixes it.

The Report-Only policy was still governing styles, so it reported a rule that
was both already enforced AND already handled -- exactly the trap its own
comment warns about ("reported on rules already in force and collected nothing
actionable").

THE SUBTLETY THAT COST A ROUND TRIP
───────────────────────────────────
Deleting the `style-src` line from Report-Only changed NOTHING: with no
style-src, `default-src 'self'` takes over as the fallback and still governs
styles. Verified against the live header -- the reports kept firing. It has to
be listed EXPLICITLY as permissive, not merely omitted.

MEASURED IMPACT
───────────────
    requests on load   775  ->  113   (-85%)
    domInteractive    1053ms -> 543ms
    first contentful   272ms ->  98ms
"""
import re


def _directives(policy: str) -> dict:
    return {d.strip().split(' ')[0]: d.strip() for d in policy.split(';') if d.strip()}


def test_report_only_does_not_re_report_the_enforced_style_src(client):
    """style-src is enforced and handled by the hydrator; reporting it again
    produced 662 requests per load and buried every real signal."""
    resp = client.get('/api/health')
    ro = resp.headers.get('content-security-policy-report-only', '')
    assert ro, 'the Report-Only header is gone'

    d = _directives(ro)
    assert 'style-src' in d, (
        "style-src must be listed EXPLICITLY in Report-Only. Omitting it falls "
        "back to default-src 'self', which still governs styles -- so the "
        "reports keep firing. This exact mistake was made once already."
    )
    assert "'unsafe-inline'" in d['style-src'], (
        f"Report-Only still restricts styles, so every hydrated attribute will "
        f"report: {d['style-src']}"
    )


def test_the_enforcing_policy_is_still_locked_down(client):
    """The Report-Only relaxation must not have leaked into the real policy."""
    csp = client.get('/api/health').headers.get('content-security-policy', '')
    d = _directives(csp)
    assert d.get('style-src') == "style-src 'self'", (
        f"the ENFORCING style-src was relaxed: {d.get('style-src')}"
    )
    assert d.get('script-src') == "script-src 'self'"


def test_report_only_still_measures_something(client):
    """A Report-Only header identical to the enforcing one collects nothing.

    Its whole purpose is to preview the NEXT tightening, so it must differ in
    at least one directive -- currently img-src, the last directive that still
    lets a request leave the machine.
    """
    resp = client.get('/api/health')
    enf = _directives(resp.headers.get('content-security-policy', ''))
    ro = _directives(resp.headers.get('content-security-policy-report-only', ''))
    differing = [k for k in ro if k in enf and ro[k] != enf[k]]
    assert differing, 'Report-Only matches the enforcing policy, so it measures nothing'
    assert 'img-src' in differing, f'expected img-src to be the ratchet, got {differing}'


def test_the_report_endpoint_still_collects_real_violations(client):
    """Silencing the noise must not silence the channel."""
    from backend.routers.security import _CSP_REPORTS

    _CSP_REPORTS.clear()
    r = client.post('/api/security/csp-report', json={'csp-report': {
        'effective-directive': 'img-src',
        'blocked-uri': 'https://evil.example/x.png',
        'source-file': 'http://localhost:8787/',
        'line-number': 42,
    }})
    assert r.status_code == 200

    body = client.get('/api/security/csp-report').json()
    hits = [v for v in body.get('violations', []) if 'evil.example' in v.get('blocked_uri', '')]
    assert hits, 'a genuine violation was not recorded'
    assert hits[0]['directive'] == 'img-src'
    _CSP_REPORTS.clear()


def test_repeated_identical_reports_are_bounded(client):
    """Even with style-src quiet, a future ratchet matching many nodes would
    flood the same way. The count keeps rising; the work stops."""
    from backend.routers.security import _CSP_REPORT_CEILING, _CSP_REPORTS

    _CSP_REPORTS.clear()
    payload = {'csp-report': {
        'effective-directive': 'img-src', 'blocked-uri': 'https://x.example/a.png',
        'source-file': 'http://localhost:8787/', 'line-number': 1,
    }}
    for _ in range(_CSP_REPORT_CEILING + 15):
        client.post('/api/security/csp-report', json=payload)

    entries = [v for v in client.get('/api/security/csp-report').json()['violations']
               if 'x.example' in v.get('blocked_uri', '')]
    assert len(entries) == 1, 'identical reports were not de-duplicated'
    assert entries[0]['count'] > _CSP_REPORT_CEILING, (
        'the count must keep rising -- frequency is the signal'
    )
    _CSP_REPORTS.clear()


def test_the_ceiling_is_documented_in_source():
    """A magic number here would be re-tuned by someone with no idea why."""
    import os

    repo = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
    with open(os.path.join(repo, 'backend', 'routers', 'security.py'), encoding='utf-8') as fh:
        src = fh.read()
    assert '_CSP_REPORT_CEILING' in src
    block = src[max(0, src.index('_CSP_REPORT_CEILING') - 900):src.index('_CSP_REPORT_CEILING')]
    assert re.search(r'662|flood|ceiling', block, re.I), (
        'the ceiling has no explanation of what it is protecting against'
    )
