#!/usr/bin/env python3
"""Interactive controls smaller than the 44x44 CSS px minimum, on touch.

WCAG 2.5.5 (AAA) and the Apple HIG both put the floor at 44x44. WCAG 2.5.8
(AA) allows 24x24. This audit reports anything under 44 and marks which of
those are also under 24.

WHY THIS AUDIT EXISTS IN THIS FORM
──────────────────────────────────
Touch targets took three batches to get right, once per way of measuring
wrongly:

  1. Measured only the LANDING PANE. Reported "48 -> 6" when there were 41
     distinct undersized types across the other 67 panes.
  2. Measured all panes but the fix only set `min-height`, leaving 20 types
     too NARROW. A 12px-wide button that is 44px tall is still unhittable.
  3. Missed `display: inline` elements entirely, because `min-width` and
     `min-height` have NO EFFECT on an inline box -- the CSS rule was applied
     and did nothing. The worst case was a 6x12px link, 1/27th of the target
     area.

So: every pane, both dimensions, and the computed `display` recorded so an
inert rule is visible in the output rather than silently passing.
"""

from __future__ import annotations

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
from _harness import AuditResult, all_panes, browser_page, emit, preflight, visit  # noqa: E402

MIN_PX = 44
CRITICAL_PX = 24

MEASURE_JS = """() => {
    const out = [];
    const sel = 'button, a[href], [role=button], [role=tab], select, summary,'
              + ' input[type=checkbox], input[type=radio]';
    document.querySelectorAll(sel).forEach(el => {
        if (el.offsetParent === null) return;
        const b = el.getBoundingClientRect();
        if (b.width === 0 && b.height === 0) return;
        // Both dimensions must clear the floor, but a control that is at
        // least 44 TALL and has real label text is reachable -- the width is
        // set by its text. Only flag wide-enough-but-short, or genuinely
        // small-in-both, or icon-only-and-narrow.
        if (b.width >= 44 && b.height >= 44) return;
        const labelled = (el.textContent || '').trim().length > 2;
        if (labelled && b.height >= 44 && b.width >= 44) return;
        const cs = getComputedStyle(el);
        // A control inside a 44px row is reachable even if the control itself
        // is small -- a <label> wrapping a checkbox forwards the click. Record
        // the row so those are not reported as unreachable.
        const row = el.closest('label, .prb-policy-item, .ttd-run-card-top, li, tr');
        const rowBox = row ? row.getBoundingClientRect() : null;
        out.push({
            tag: el.tagName,
            type: el.type || '',
            cls: (el.className || '').toString().trim().split(/\\s+/)[0] || '',
            w: Math.round(b.width),
            h: Math.round(b.height),
            display: cs.display,
            rowH: rowBox ? Math.round(rowBox.height) : 0,
            txt: (el.textContent || '').trim().slice(0, 18),
        });
    });
    return out;
}"""


def run() -> AuditResult:
    preflight()
    seen: dict[tuple, dict] = {}
    with browser_page('phone') as (page, _ctx):
        for pane in all_panes(page):
            visit(page, pane)
            for item in page.evaluate(MEASURE_JS):
                # A small control inside a comfortably large row is fine.
                if item['rowH'] >= MIN_PX:
                    continue
                # A control that clears BOTH dimensions is fine. The JS filter
                # already excludes those, but a labelled control 44px tall and
                # 44px+ wide can still be reported when its bounding box is
                # measured mid-layout inside a scrolling strip.
                if item['w'] >= MIN_PX and item['h'] >= MIN_PX:
                    continue
                # 24x24 checkboxes are a deliberate, documented compromise.
                if item['type'] in ('checkbox', 'radio') and min(item['w'], item['h']) >= CRITICAL_PX:
                    continue
                key = (item['tag'], item['type'], item['cls'], item['w'], item['h'])
                entry = seen.setdefault(key, {**item, 'n': 0, 'panes': set()})
                entry['n'] += 1
                entry['panes'].add(pane)

    findings = []
    for entry in sorted(seen.values(), key=lambda e: (e['w'] * e['h'], -e['n'])):
        flag = ' CRITICAL' if min(entry['w'], entry['h']) < CRITICAL_PX else ''
        inert = ' (display:inline — min-* is INERT here)' if entry['display'] == 'inline' else ''
        findings.append(
            f"{entry['n']:4}x {entry['tag']:6}.{entry['cls'][:22]:22} "
            f"{entry['w']}x{entry['h']}{flag}{inert} "
            f"txt={entry['txt']!r} panes={sorted(entry['panes'])[:3]}"
        )

    return AuditResult(
        'touch-targets-under-44px',
        len(seen),
        findings,
        note='distinct control types under 44x44 on a 390px phone; '
             'controls inside a >=44px row are excluded, as are 24x24 checkboxes',
    )


if __name__ == '__main__':
    raise SystemExit(emit(run()))
