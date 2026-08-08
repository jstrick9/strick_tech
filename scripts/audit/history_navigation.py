#!/usr/bin/env python3
"""Browser Back and Forward.

Back is a reflex. A user who presses it expects the previous screen, and the
worst possible outcome is losing the session -- which is exactly what this
app did before this audit existed.

WHAT IS MEASURED
────────────────
  NO-HISTORY   navigating between panes creates no history entry, so Back
               leaves the application entirely

  BACK-EXITS   pressing Back lands outside the app (about:blank, or window.nav
               undefined)

  NO-RESTORE   Back changes the URL but the pane does not actually render

  BOUNCE       Back pushes a new entry, so the user can never step further
               back -- an infinite loop between two panes

  DUPE-ENTRY   re-navigating to the pane you are already on stacks identical
               entries, making Back appear to do nothing several times

WHAT THIS FOUND
───────────────
Every navigation used `history.replaceState()`, never `pushState`. Four pane
changes produced ZERO history entries and Back went to about:blank with
`window.nav` undefined -- the whole session gone. A `hashchange` handler that
routes correctly already existed; it simply never fired, because replaceState
does not produce a hashchange.
"""

from __future__ import annotations

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
from _harness import AuditResult, browser_page, emit, pane_text, preflight, visit  # noqa: E402

# A mix of top-level panes and absorbed workstation tabs, because a tab
# restores through a different path than a plain pane.
TRAIL = ['kanban', 'specs', 'goals', 'terminal']

IN_APP_JS = "() => typeof window.nav === 'function'"
HASH_JS = "() => location.hash"


def run() -> AuditResult:
    preflight()
    findings = []

    with browser_page('desktop') as (page, _ctx):
        start_len = page.evaluate("() => history.length")
        for pane in TRAIL:
            visit(page, pane, settle=600)
        after_len = page.evaluate("() => history.length")

        gained = after_len - start_len
        if gained == 0:
            findings.append(
                f'NO-HISTORY  {len(TRAIL)} navigations created 0 history '
                f'entries; Back will leave the app')
        elif gained < len(TRAIL) - 1:
            findings.append(
                f'NO-HISTORY  {len(TRAIL)} navigations created only {gained} '
                f'history entries')

        # Walk backwards through the trail.
        for step in range(len(TRAIL) - 1):
            expected = TRAIL[len(TRAIL) - 2 - step]
            page.go_back()
            page.wait_for_timeout(1400)

            if not page.evaluate(IN_APP_JS):
                findings.append(
                    f'BACK-EXITS  Back #{step + 1} left the application '
                    f'(url={page.url[:48]})')
                break

            current = page.evaluate(HASH_JS)
            if current != f'#/{expected}':
                findings.append(
                    f'NO-RESTORE  Back #{step + 1} expected #/{expected}, '
                    f'got {current or "(no hash)"}')
                break

            if len(pane_text(page, expected)) < 40:
                findings.append(
                    f'NO-RESTORE  Back #{step + 1} reached {current} but the '
                    f'pane rendered nothing')

        # Back must not append entries, or the user is trapped.
        if page.evaluate(IN_APP_JS):
            length_before = page.evaluate("() => history.length")
            page.go_back()
            page.wait_for_timeout(1200)
            if page.evaluate("() => history.length") > length_before:
                findings.append(
                    'BOUNCE      Back added a history entry; the user can '
                    'never step further back')

        # Re-navigating to the current pane must not stack entries.
        if page.evaluate(IN_APP_JS):
            visit(page, 'kanban', settle=600)
            length_before = page.evaluate("() => history.length")
            for _ in range(4):
                page.evaluate("window.nav && window.nav('kanban')")
                page.wait_for_timeout(250)
            grew = page.evaluate("() => history.length") - length_before
            if grew:
                findings.append(
                    f'DUPE-ENTRY  4 navigations to the CURRENT pane added '
                    f'{grew} history entries')

    return AuditResult(
        'history-navigation',
        len(findings),
        findings,
        note='Back/Forward: entries created, panes restored, no bounce loop',
    )


if __name__ == '__main__':
    raise SystemExit(emit(run()))
