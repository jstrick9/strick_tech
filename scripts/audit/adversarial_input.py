#!/usr/bin/env python3
"""What the UI does with hostile, huge, or merely unusual text.

THE SEAM
────────
Every audit so far has driven the app with data the app itself produced. Users
type things the developer never did: a 10,000-character title pasted from a
document, a name in Arabic, an emoji, an apostrophe, `<script>`, `${}`.

Three distinct failures are measured, and they are deliberately separated
because they need different fixes:

  XSS-EXEC     markup in a stored value EXECUTED. The single most serious
               finding available anywhere in this review.

  LAYOUT-BREAK a long unbroken value overflowed its CONTAINER, or pushed the
               document wider than the viewport.

               Checking only the document width is not enough and nearly cost
               this finding: a 4,000-character title sat in a 235px card with
               `scrollWidth: 2137px` and `overflow: visible`, spilling across
               neighbouring cards -- while `documentElement.scrollWidth`
               stayed exactly 1440px. The page looked fine by the global
               measure and was unreadable on screen.

  LOST-VALUE   the value came back different in a way that loses meaning --
               an apostrophe returned as `&#39;`, an emoji mangled. Displaying
               `Ali&#39;s plan` is a bug even though it is a SAFE bug; it is
               double-escaping, and it tells the user their data is corrupted.

WHAT IS DELIBERATELY NOT MEASURED
─────────────────────────────────
Server-side rejection of oversized input. That is a valid design (and
`test_99_malformed_request_bodies.py` already covers the API surface). This
audit is about what the USER experiences, so a value the server truncates or
refuses is fine here as long as the UI says so rather than silently discarding
it.

MEASUREMENT NOTES
─────────────────
  * XSS is detected by a real side effect (`window.__xss`), not by looking for
    the payload text in the DOM. Searching for `<script>` in innerHTML finds
    correctly-escaped values and misses `onerror=` entirely -- it would report
    the safe case and miss the dangerous one.
  * Layout is measured against `documentElement.scrollWidth` AFTER the value
    is rendered, and compared to the width recorded BEFORE. An app that
    already overflows would otherwise make every payload look guilty.
  * Values are written through the API and read back through the UI, because
    the round trip is where escaping bugs live. Injecting straight into the
    DOM would test nothing but the browser.
"""

from __future__ import annotations

import json
import sys
import urllib.error
import urllib.request
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
from _harness import AuditResult, BASE_URL, browser_page, emit, preflight, visit  # noqa: E402

# Each payload names the property it is probing, so a finding says what broke.
PAYLOADS = [
    ('script-tag',   '<script>window.__xss=1</script>'),
    ('img-onerror',  '<img src=x onerror="window.__xss=1">'),
    ('svg-onload',   '<svg onload="window.__xss=1">'),
    ('apostrophe',   "Ali's Q3 plan"),
    ('emoji',        'Ship it 🚀🎉 done'),
    ('rtl',          'مرحبا بالعالم'),
    ('template',     '${constructor.constructor("window.__xss=1")()}'),
    ('long-unbroken', 'A' * 4000),
    ('long-prose',   'lorem ipsum dolor sit amet ' * 400),
]


def _csrf() -> str | None:
    try:
        with urllib.request.urlopen(f'{BASE_URL}/api/security/csrf-token', timeout=10) as r:  # noqa: S310
            body = json.loads(r.read())
        return body.get('csrf_token') or body.get('token')
    except (urllib.error.URLError, OSError, ValueError):
        return None


def _create_task(title: str, token: str) -> bool:
    """Write through the real API. A probe whose writes are all rejected
    reports a clean PASS while measuring nothing -- that exact failure hit the
    concurrency audit (see docs/SEAM-REGISTER.md), so the result is checked.
    """
    payload = json.dumps({'title': title}).encode()
    req = urllib.request.Request(
        f'{BASE_URL}/api/tasks', data=payload, method='POST',
        headers={'Content-Type': 'application/json', 'X-CSRF-Token': token})
    try:
        with urllib.request.urlopen(req, timeout=15) as r:  # noqa: S310
            return 200 <= r.status < 300
    except urllib.error.HTTPError:
        return False
    except (urllib.error.URLError, OSError):
        return False


def run() -> AuditResult:
    preflight()
    findings = []

    token = _csrf()
    if not token:
        return AuditResult('adversarial-input', 0,
                           ['-- could not obtain a CSRF token; audit skipped'],
                           note='hostile, huge and unusual text through the UI')

    written = [(name, value) for name, value in PAYLOADS
               if _create_task(value, token)]
    rejected = [name for name, _ in PAYLOADS
                if name not in {n for n, _ in written}]

    if not written:
        return AuditResult('adversarial-input', 0,
                           ['-- every write was rejected; audit measured '
                            'nothing and is reporting so rather than PASS'],
                           note='hostile, huge and unusual text through the UI')
    if rejected:
        # Not a finding: refusing hostile input at the API is a legitimate
        # design. Recorded so the coverage of this run is visible.
        findings.append(
            f'-- server refused {len(rejected)} payload(s), not rendered: '
            + ', '.join(rejected))

    with browser_page('desktop') as (page, _ctx):
        page.evaluate('window.__xss = 0')
        baseline_width = page.evaluate('document.documentElement.scrollWidth')

        visit(page, 'kanban', settle=1500)
        page.wait_for_timeout(1200)

        # ── 1. Execution ────────────────────────────────────────────────
        if page.evaluate('window.__xss'):
            findings.append(
                'XSS-EXEC       stored markup EXECUTED when the pane rendered')

        # ── 2. Layout ───────────────────────────────────────────────────
        width = page.evaluate('document.documentElement.scrollWidth')
        viewport = page.evaluate('document.documentElement.clientWidth')
        if width > max(baseline_width, viewport) + 4:
            findings.append(
                f'LAYOUT-BREAK   a long value widened the document to {width}px '
                f'against a {viewport}px viewport')

        # Element-level overflow. The document can stay exactly viewport-wide
        # while a value spills out of its own card over the top of its
        # neighbours, which is what actually happened here.
        spills = page.evaluate('''() => {
            const out = [];
            document.querySelectorAll('*').forEach(el => {
                if (el.children.length) return;
                const text = el.textContent || '';
                if (text.length < 200) return;
                if (el.scrollWidth <= el.clientWidth + 4) return;
                const cs = getComputedStyle(el);
                // A container that CLIPS or scrolls is a deliberate design
                // choice, not a break. Only visible overflow spills.
                if (cs.overflow !== 'visible' || cs.overflowX !== 'visible') return;
                out.push({w: el.clientWidth, sw: el.scrollWidth,
                          cls: String(el.className).slice(0, 40)});
            });
            return out;
        }''')
        if spills:
            worst = max(spills, key=lambda s: s['sw'])
            findings.append(
                f'LAYOUT-BREAK   {len(spills)} element(s) overflow their own '
                f'box with visible overflow; worst is {worst["sw"]}px of '
                f'content in a {worst["w"]}px box ({worst["cls"] or "no class"})')

        # ── 3. Fidelity ─────────────────────────────────────────────────
        # Read what the user SEES (innerText decodes entities), so a value
        # that survived the round trip intact reads back identical.
        shown = page.evaluate("""(() => {
            const el = document.getElementById('pane-kanban');
            return el ? el.innerText : document.body.innerText;
        })()""")
        for name, value in written:
            if name == 'apostrophe' and "Ali's Q3 plan" not in shown:
                if '&#39;' in shown or '&amp;' in shown:
                    findings.append(
                        'LOST-VALUE     apostrophe rendered as an HTML entity '
                        '(double-escaped)')
            if name == 'emoji' and '🚀' not in shown and 'Ship it' in shown:
                findings.append('LOST-VALUE     emoji stripped or mangled')
            if name == 'rtl' and 'مرحبا' not in shown and len(shown) > 60:
                findings.append('LOST-VALUE     right-to-left text lost')

    return AuditResult(
        'adversarial-input',
        len([f for f in findings if not f.startswith('--')]),
        findings,
        note='hostile, huge and unusual text written through the API and '
             'rendered by the UI',
    )


if __name__ == '__main__':
    raise SystemExit(emit(run()))
