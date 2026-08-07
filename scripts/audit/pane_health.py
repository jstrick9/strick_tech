#!/usr/bin/env python3
"""Every pane renders, with no console errors and no destroyed workstations.

This is the broadest smoke test in the set. It walks all panes with the server
healthy and reports:

  ERROR    an uncaught page error or console error while rendering
  BLANK    a pane that renders almost nothing
  LOST     a workstation whose tab strip or absorbed panes were destroyed

WHAT THIS AUDIT FOUND
─────────────────────
7 of 11 workstations were destroyed on first open, removing 28 absorbed pane
elements from the DOM. The cause was a duplicate render: nav() built the
workstation, then a second async render of the host replaced its innerHTML and
deleted everything inside. That produced four "Cannot set properties of null"
errors whose real meaning was "the pane element no longer exists".

MEASUREMENT NOTE
────────────────
CSP style violations are excluded. The app enforces `style-src 'self'` and
hydrates refused inline styles at runtime; those reports are expected and
would otherwise drown every real error.
"""

from __future__ import annotations

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
from _harness import AuditResult, all_panes, browser_page, emit, pane_text, preflight, visit  # noqa: E402

WORKSTATION_JS = """(host) => {
    const el = document.getElementById('pane-' + host);
    if (!el) return {missing: true};
    const kids = (window.WORKSTATIONS || {})[host] || [];
    return {
        tabs: !!el.querySelector(':scope > .ws-tabs'),
        bodies: !!el.querySelector(':scope > .ws-bodies'),
        lost: kids.filter(k => !document.getElementById('pane-' + k)),
    };
}"""


def run() -> AuditResult:
    preflight()
    findings = []
    errors: list[str] = []

    with browser_page('desktop') as (page, _ctx):
        page.on('pageerror', lambda e: errors.append(f'pageerror: {str(e)[:120]}'))
        page.on('console', lambda m: errors.append(f'console: {m.text[:120]}')
                if m.type == 'error'
                and 'Content Security Policy' not in m.text
                and 'status of 404' not in m.text else None)

        for pane in all_panes(page):
            visit(page, pane, settle=500)
            text = pane_text(page, pane)
            # "Blank" means nothing rendered, not "less text than average".
            # A character threshold flagged `multitab` -- a browser-tab UI
            # whose entire legitimate render is 39 characters of chrome.
            # Interactive content present means the pane rendered.
            controls = page.evaluate(f"""(() => {{
                const el = document.getElementById('pane-' + {pane!r});
                if (!el) return 0;
                return el.querySelectorAll(
                    'button, a[href], input, select, textarea, [data-act-click]').length;
            }})()""")
            if len(text) < 15 and controls == 0:
                findings.append(f'BLANK  {pane}  ({len(text)} chars, no controls)')

        for host in page.evaluate("Object.keys(window.WORKSTATIONS || {})"):
            visit(page, host, settle=900)
            state = page.evaluate(WORKSTATION_JS, host)
            if state.get('missing'):
                findings.append(f'LOST   {host}: host pane missing')
            elif not state['tabs'] or not state['bodies']:
                findings.append(f'LOST   {host}: tab strip destroyed')
            elif state['lost']:
                findings.append(f'LOST   {host}: absorbed panes gone {state["lost"]}')

    for message in dict.fromkeys(errors):
        findings.append(f'ERROR  {message}')

    return AuditResult(
        'pane-health',
        len(findings),
        findings,
        note='blank panes, console errors, and destroyed workstations '
             'while the server is healthy',
    )


if __name__ == '__main__':
    raise SystemExit(emit(run()))
