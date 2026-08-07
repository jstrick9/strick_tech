#!/usr/bin/env python3
"""Horizontal overflow and oversized elements, at three viewports.

Horizontal scrolling on a phone is one of the most obvious signs an app was
never used at that size. This audit reports:

  OVERFLOW  the document scrolls sideways
  WIDE      an element wider than the viewport that is not an intentional
            internally-scrolling region

MEASUREMENT NOTE
────────────────
Tab strips and data tables are DESIGNED to scroll inside themselves, so a
child wider than the viewport is not automatically a bug. What matters is
whether the DOCUMENT overflows. Both numbers are reported; only document
overflow is counted, because that is the one that is unambiguously wrong.

This audit also caught a regression introduced by a touch-target fix: widening
the top bar buttons pushed #topbar-actions past the viewport edge.
"""

from __future__ import annotations

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
from _harness import VIEWPORTS, AuditResult, all_panes, browser_page, emit, preflight, visit  # noqa: E402

MEASURE_JS = """() => {
    const de = document.documentElement;
    const overflow = de.scrollWidth - de.clientWidth;
    const wide = [...document.querySelectorAll('*')].filter(e => {
        if (e.offsetParent === null) return false;
        const b = e.getBoundingClientRect();
        return b.width > de.clientWidth + 2 && b.width > 120;
    }).map(e => (e.id || e.className || e.tagName).toString().slice(0, 30));
    return {overflow, wide: [...new Set(wide)].slice(0, 3)};
}"""


def run() -> AuditResult:
    preflight()
    findings = []
    overflow_count = 0

    for viewport in VIEWPORTS:
        with browser_page(viewport) as (page, _ctx):
            wide_panes = 0
            for pane in all_panes(page):
                visit(page, pane, settle=240)
                state = page.evaluate(MEASURE_JS)
                if state['overflow'] > 2:
                    overflow_count += 1
                    findings.append(
                        f'OVERFLOW {viewport:8} {pane:16} {state["overflow"]}px '
                        f'{state["wide"]}')
                elif state['wide']:
                    wide_panes += 1
            findings.append(
                f'--       {viewport:8} {wide_panes} panes have internally-'
                f'scrolling wide children (informational)')

    return AuditResult(
        'responsive-overflow',
        overflow_count,
        findings,
        note='panes where the DOCUMENT scrolls sideways; wide children that '
             'scroll internally are reported but not counted',
    )


if __name__ == '__main__':
    raise SystemExit(emit(run()))
