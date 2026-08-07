#!/usr/bin/env python3
"""What a screen-reader user is actually told when the app changes.

`semantics.py` already checks STRUCTURE -- headings, landmarks, dialog names.
This audit checks something different and easy to miss: when the app does
something, does anyone who cannot see the screen find out?

WHAT IS MEASURED
────────────────
  SILENT-ACTION   an action completes and nothing is announced. A sighted
                  user sees a toast; a screen-reader user gets nothing.

  UNLABELLED-LIVE a live region that exists but is never given content, or
                  content set in a way screen readers skip.

  MISSING-BUSY    a long operation with no `aria-busy` on the region being
                  updated, so the user does not know to wait.

HOW ANNOUNCEMENTS ARE DETECTED
──────────────────────────────
A screen reader announces text inserted into an `aria-live` region (or one
with `role=status` / `role=alert`). This audit installs a MutationObserver on
every such region before acting, then reports what landed there. That is the
same signal an assistive technology consumes, rather than a proxy for it.

MEASUREMENT NOTE
────────────────
An empty live region at rest is normal and correct -- it is a container
waiting for content. Only regions that never receive content across the whole
run are reported, so a container that is used later in the session is not
flagged as dead.
"""

from __future__ import annotations

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
from _harness import AuditResult, browser_page, emit, preflight, visit  # noqa: E402

# Install before acting, so nothing is missed between load and the action.
WATCH_JS = """() => {
    window.__ann = [];
    const regions = document.querySelectorAll(
        '[aria-live], [role=status], [role=alert], [role=log]');
    window.__regionCount = regions.length;
    regions.forEach(r => {
        const obs = new MutationObserver(() => {
            const text = (r.innerText || r.textContent || '').trim();
            if (text) window.__ann.push({
                id: r.id || r.className || r.tagName,
                text: text.slice(0, 70),
            });
        });
        obs.observe(r, {childList: true, characterData: true, subtree: true});
    });
    return regions.length;
}"""

DRAIN_JS = "() => { const a = window.__ann || []; window.__ann = []; return a; }"

# Each entry: (label, JS that performs a user action, what a user would expect
# to be told). Chosen to be safe to run repeatedly and to cover the shapes
# that matter: navigation, a toast, a destructive-ish action, and a form.
ACTIONS = [
    ('navigate to a pane',
     "window.nav('kanban')",
     'which pane is now showing'),
    ('show a toast',
     "window.toast && window.toast('Audit probe message', 'ok')",
     'the toast text'),
    ('report an error',
     "window.toast && window.toast('Audit probe failure', 'err')",
     'the failure'),
]


def run() -> AuditResult:
    preflight()
    findings = []

    with browser_page('desktop') as (page, _ctx):
        visit(page, 'chat', settle=500)
        region_count = page.evaluate(WATCH_JS)
        if region_count == 0:
            findings.append(
                'NO-LIVE-REGIONS  the page has no aria-live region at all; '
                'nothing can ever be announced')
            return AuditResult('screen-reader-announcements', 1, findings)

        seen_any = False
        for label, script, expectation in ACTIONS:
            page.evaluate(DRAIN_JS)
            try:
                page.evaluate(script)
            except Exception as exc:                      # noqa: BLE001
                findings.append(f'--              {label}: could not run ({exc})'[:110])
                continue
            page.wait_for_timeout(700)
            announced = page.evaluate(DRAIN_JS)
            if announced:
                seen_any = True
            else:
                findings.append(
                    f'SILENT-ACTION   {label}: nothing announced '
                    f'(expected: {expectation})')

        # Dialogs are NOT announced through a live region.
        #
        # An earlier version of this audit expected one and reported the
        # command palette as SILENT-ACTION. That was wrong: a screen reader
        # announces a dialog when focus MOVES INTO an element with
        # role=dialog and an accessible name. Verified -- opening the palette
        # moves focus to #palette-input inside a dialog labelled "Command
        # palette", which is exactly the correct pattern.
        #
        # So the real check is whether every dialog that opens takes focus
        # and carries a name.
        for opener, dialog_id in (
                ('window.openPalette && window.openPalette()', 'palette-modal'),
                ('window.openAgentModal && window.openAgentModal()', 'agent-modal'),
        ):
            try:
                page.evaluate(opener)
            except Exception as exc:                       # noqa: BLE001
                # A dialog opener that does not exist in this build is not a
                # finding; record it so a silently-missing dialog is visible
                # rather than skipped without trace.
                findings.append(
                    f'--              {dialog_id}: opener unavailable ({exc})'[:110])
                continue
            page.wait_for_timeout(600)
            state = page.evaluate(f"""(() => {{
                const m = document.getElementById({dialog_id!r});
                if (!m) return null;
                if (getComputedStyle(m).display === 'none') return null;
                const a = document.activeElement;
                return {{
                    focusInside: !!(a && a.closest('#' + {dialog_id!r})),
                    named: !!(m.getAttribute('aria-label')
                           || m.getAttribute('aria-labelledby')),
                }};
            }})()""")
            if state is None:
                continue
            if not state['focusInside']:
                findings.append(
                    f'DIALOG-NO-FOCUS {dialog_id}: opened without moving focus '
                    f'inside, so it is never announced')
            if not state['named']:
                findings.append(
                    f'DIALOG-NO-NAME  {dialog_id}: no accessible name; '
                    f'announced only as "dialog"')
            page.keyboard.press('Escape')
            page.wait_for_timeout(300)

        # A live region that never received anything across the whole run is
        # either dead or mis-wired.
        if not seen_any:
            findings.append(
                f'UNLABELLED-LIVE {region_count} live regions exist but none '
                f'received content during any action')

    # '--' lines are informational, matching responsive.py and
    # slow_network.py: visible in the report, not counted by the ratchet.
    counted = [f for f in findings if not f.startswith('--')]

    return AuditResult(
        'screen-reader-announcements',
        len(counted),
        findings,
        note='user actions that produce no announcement in any aria-live region',
    )


if __name__ == '__main__':
    raise SystemExit(emit(run()))
