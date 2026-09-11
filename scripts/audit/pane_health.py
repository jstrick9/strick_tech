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

    # The console filter exempts CSP *console* lines, but a CSP refusal can
    # also surface as an uncaught pageerror when a library calls eval()/
    # new Function() directly: the refusal throws at the call site. The one
    # known source is 3d-force-graph's rare lazily-compiled path (galaxy
    # pane), which the policy correctly blocks with no functional impact
    # — the graph renders from the remaining non-eval code. Exempting the
    # CSP refusal itself keeps the audit able to see every OTHER uncaught
    # error, which is what it is for.
    def _on_pageerror(e):
        if 'unsafe-eval' in str(e) and 'Content Security Policy' in str(e):
            return
        errors.append(f'pageerror: {str(e)[:120]}')

    # Auth-gate refusals the app surfaces honestly. The terminal fail-closes
    # with 401/403 whenever the server is bound non-loopback (or
    # TERMINAL_REQUIRE_AUTH=1 / TERMINAL_DISABLED=1) — by design — and the
    # pane renders the refusal's guidance in a warning banner instead of a
    # healthy-looking prompt. Chromium logs every non-2xx fetch as a console
    # error regardless, so on the 0.0.0.0 preview topology this audit
    # reported the gate itself as a pane error (the pane-health baseline 0
    # was recorded on loopback, where the gate never fires). The console
    # line carries no URL, so attribution happens after the walk: the
    # 401/403 console line is exempt ONLY when every refused request in the
    # entire walk came from /api/terminal/. Any other refusal — a pane
    # probing an endpoint that unexpectedly started demanding auth — still
    # reports.
    auth_refusals: list[str] = []

    def _on_response(r):
        if r.status in (401, 403):
            auth_refusals.append(r.url)

    with browser_page('desktop') as (page, _ctx):
        page.on('pageerror', _on_pageerror)
        page.on('response', _on_response)
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

        # Reload before the workstation checks.
        #
        # The pane walk above visits all 68 panes, which builds every
        # workstation as a side effect. Re-navigating to an already-built host
        # then takes the idempotent early-return path and never exercises the
        # build-then-wipe sequence -- so the check passed even with the host
        # watcher removed. A fresh page reproduces what a real user does:
        # arrive at a workstation for the first time.
        page.reload(wait_until='domcontentloaded')
        page.wait_for_timeout(3000)

        for host in page.evaluate("Object.keys(window.WORKSTATIONS || {})"):
            # Wait past the host's LATER renders, not just its first.
            #
            # A host can re-render seconds after navigation -- on a poll, or a
            # slow second pass -- and wipe the tab strip it was given.
            # Measured with 250 seeded goals: renderSupervisor() ran again
            # ~3s after nav() and destroyed a Goals tab that had already
            # rendered 5,976 characters. A 900ms settle checked before the
            # damage and reported the workstation healthy.
            visit(page, host, settle=900)
            page.wait_for_timeout(3500)
            state = page.evaluate(WORKSTATION_JS, host)
            if state.get('missing'):
                findings.append(f'LOST   {host}: host pane missing')
            elif not state['tabs'] or not state['bodies']:
                findings.append(f'LOST   {host}: tab strip destroyed')
            elif state['lost']:
                findings.append(f'LOST   {host}: absorbed panes gone {state["lost"]}')

    only_terminal_gate = bool(auth_refusals) and all(
        '/api/terminal/' in u for u in auth_refusals)

    for message in dict.fromkeys(errors):
        if (only_terminal_gate
                and message.startswith('console: Failed to load resource')
                and ('status of 401' in message or 'status of 403' in message)):
            continue  # the terminal's fail-closed auth gate, see above
        findings.append(f'ERROR  {message}')

    if only_terminal_gate:
        findings.append(
            f'--  terminal auth gate refused {len(auth_refusals)} request(s) '
            'on this topology (expected on a non-loopback bind; exempted)')

    return AuditResult(
        'pane-health',
        len([f for f in findings if not f.startswith('--')]),
        findings,
        note='blank panes, console errors, and destroyed workstations '
             'while the server is healthy',
    )


if __name__ == '__main__':
    raise SystemExit(emit(run()))
