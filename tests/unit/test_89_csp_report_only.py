"""Phase 3 (first half) — the strict CSP in Report-Only mode.

The enforcing policy still carries script-src 'unsafe-inline' because 859
inline handlers and 5 inline <script> blocks depend on it. Dropping it now
would break the product, and a CSP that breaks the product is reverted within a
day — worse than not shipping it, because it burns the option.

Report-Only is the step that can ship safely today: browsers evaluate both
headers, enforce the permissive one and only REPORT on the strict one. Nothing
breaks, and every violation the strict policy would have caused is collected.

That converts "we think 313 handlers still need work" into a measured list from
real usage — the evidence needed to decide when the switch is safe.
"""

from __future__ import annotations

from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[2]
APP_PY = (ROOT / 'backend' / 'app.py').read_text(encoding='utf-8')


# ══ The two policies ══════════════════════════════════════════════════════════
def test_report_only_policy_drops_unsafe_inline_for_scripts():
    """The entire point of the exercise."""
    from backend.app import CSP_REPORT_ONLY

    script_src = next(
        d for d in CSP_REPORT_ONLY.split(';') if d.strip().startswith('script-src')
    )
    assert "'unsafe-inline'" not in script_src, (
        'the report-only policy is not actually strict'
    )


def test_enforcing_policy_no_longer_permits_inline_script():
    """This test previously asserted the OPPOSITE — that the enforcing policy
    still allowed inline script "so nothing breaks". That was correct while
    1107 inline handlers existed, but it encoded a temporary state as a
    contract, so completing phase 2 made it fail.

    The handlers are now migrated to the delegation shim and the inline
    <script> blocks are extracted, so the directive is gone. The report-only
    policy remains useful as an early-warning channel for anything that still
    trips the rules.
    """
    from backend.app import SECURITY_HEADERS

    enforcing = SECURITY_HEADERS['Content-Security-Policy']
    script_src = next(
        d for d in enforcing.split(';') if d.strip().startswith('script-src')
    )
    assert "'unsafe-inline'" not in script_src
    assert "'unsafe-eval'" not in script_src


def test_report_only_keeps_style_unsafe_inline():
    """Deliberate: the codebase sets element.style extensively, inline STYLE is
    a far smaller risk than inline SCRIPT, and bundling the two would stall
    both."""
    from backend.app import CSP_REPORT_ONLY

    style_src = next(
        d for d in CSP_REPORT_ONLY.split(';') if d.strip().startswith('style-src')
    )
    assert "'unsafe-inline'" in style_src


def test_report_only_points_at_a_real_endpoint():
    """A report-uri pointing nowhere collects nothing and looks like progress."""
    from backend.app import CSP_REPORT_ONLY

    assert 'report-uri /api/security/csp-report' in CSP_REPORT_ONLY


def test_report_only_is_sent_on_the_app_shell(client):
    r = client.get('/')
    assert r.status_code == 200
    header = r.headers.get('content-security-policy-report-only')
    assert header, 'the Report-Only header is not being sent'
    assert "script-src 'self'" in header
    assert "script-src 'self' 'unsafe-inline'" not in header


def test_both_headers_are_present_together(client):
    """Enforce permissive, report strict — that combination is what makes this
    safe to ship before the migration is done."""
    r = client.get('/')
    assert r.headers.get('content-security-policy')
    assert r.headers.get('content-security-policy-report-only')


def test_preview_routes_are_excluded(client):
    """/preview/ serves user- and agent-generated pages that legitimately carry
    inline script; reporting on them would bury the application's own
    violations."""
    assert "path.startswith('/preview/')" in APP_PY


def test_report_only_can_be_disabled():
    assert 'AGENTIC_CSP_REPORT_ONLY' in APP_PY


# ══ The collection endpoint ═══════════════════════════════════════════════════
@pytest.fixture()
def clean_reports(client):
    client.delete('/api/security/csp-report')
    yield
    client.delete('/api/security/csp-report')


def _post(client, **over):
    body = {
        'effective-directive': 'script-src',
        'blocked-uri': 'inline',
        'source-file': 'http://localhost:8787/',
        'line-number': 42,
        'script-sample': 'doThing()',
    }
    body.update(over)
    return client.post('/api/security/csp-report', json={'csp-report': body})


def test_a_violation_is_collected(client, clean_reports):
    assert _post(client).status_code == 200
    d = client.get('/api/security/csp-report').json()
    assert d['distinct'] == 1
    assert d['violations'][0]['directive'] == 'script-src'
    assert d['violations'][0]['sample'] == 'doThing()'


def test_identical_violations_aggregate(client, clean_reports):
    """500 clicks on one button must not flood the buffer and hide the long
    tail — the long tail is the part that tells you what still needs work."""
    for _ in range(5):
        _post(client)
    d = client.get('/api/security/csp-report').json()
    assert d['distinct'] == 1
    assert d['violations'][0]['count'] == 5
    assert d['total'] == 5


def test_distinct_violations_are_kept_separate(client, clean_reports):
    _post(client, **{'line-number': 1})
    _post(client, **{'line-number': 2})
    assert client.get('/api/security/csp-report').json()['distinct'] == 2


def test_violations_sort_by_frequency(client, clean_reports):
    _post(client, **{'line-number': 1})
    for _ in range(3):
        _post(client, **{'line-number': 2})
    v = client.get('/api/security/csp-report').json()['violations']
    assert v[0]['count'] == 3


def test_malformed_reports_do_not_error(client, clean_reports):
    """A browser will not retry a failed report, and a 500 here would be a
    self-inflicted noise source."""
    assert client.post('/api/security/csp-report', content=b'not json').status_code == 200
    assert client.post('/api/security/csp-report', json={'nonsense': 1}).status_code == 200


def test_buffer_is_capped(client):
    """In-memory and unbounded is how a diagnostic becomes an outage."""
    from backend.routers.security import _CSP_REPORT_CAP

    assert _CSP_REPORT_CAP > 0
    assert 'len(_CSP_REPORTS) < _CSP_REPORT_CAP' in (
        (ROOT / 'backend' / 'routers' / 'security.py').read_text(encoding='utf-8')
    )


def test_reports_can_be_cleared(client, clean_reports):
    _post(client)
    assert client.delete('/api/security/csp-report').json()['cleared'] >= 1
    assert client.get('/api/security/csp-report').json()['distinct'] == 0


def test_the_endpoint_explains_what_an_empty_list_means(client):
    """The whole exercise exists to answer one question; the answer should not
    require reading the source."""
    note = client.get('/api/security/csp-report').json()['note']
    assert 'nothing was blocked' in note.lower()
    assert 'unsafe-inline' in note
