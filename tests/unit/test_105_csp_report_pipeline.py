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

import pytest


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


def test_report_only_currently_tests_strict_style_src():
    """The specific next ratchet, so a future edit that loosens it is visible."""
    from backend.app import CSP_REPORT_ONLY

    style = next(
        d for d in CSP_REPORT_ONLY.split(';') if d.strip().startswith('style-src')
    )
    assert "'unsafe-inline'" not in style, (
        'Report-Only should be measuring what strict style-src would break'
    )


def test_the_enforcing_style_src_is_unchanged(client):
    """Report-Only must not accidentally become enforcing. Dropping
    style-src 'unsafe-inline' for real would break 4494 static inline styles
    across the product."""
    csp = client.get('/api/health').headers.get('content-security-policy', '')
    style = next(d for d in csp.split(';') if d.strip().startswith('style-src'))
    assert "'unsafe-inline'" in style, (
        'style-src was tightened in the ENFORCING policy; that is a separate, '
        'much larger migration'
    )
