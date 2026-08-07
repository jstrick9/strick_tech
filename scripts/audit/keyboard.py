#!/usr/bin/env python3
"""Controls that cannot be reached or seen by a keyboard user.

Reports two things:

  UNREACHABLE  an element with a click handler that is not a native control,
               has no tabindex and no button role. Invisible to Tab, not
               announced as a control, inoperable by keyboard, switch or
               voice input.

  NO-RING      a tab stop that renders no visible focus indicator (WCAG 2.4.7).
               Focus lands somewhere the user cannot see.

WHAT THIS AUDIT FOUND
─────────────────────
884 clickable elements were mouse-only, dominated by `.agent-row` -- how you
choose which agent to chat with, a core interaction of the product.

TWO MEASUREMENT TRAPS, ENCODED HERE SO THEY ARE NOT REPEATED
────────────────────────────────────────────────────────────
Both produced a confident "the focus ring is missing" finding that was wrong.

  1. `:focus-visible` does not match programmatic `.focus()`. Reading computed
     style after calling `.focus()` reports NO ring for every element,
     including ones that demonstrably have one. This audit uses real Tab
     presses.

  2. Focus styles transition over 150ms. Reading immediately after Tab reports
     the START of the animation -- 0px. This audit waits for the transition.
"""

from __future__ import annotations

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
from _harness import TRANSITION_MS, AuditResult, all_panes, browser_page, emit, preflight, visit  # noqa: E402

UNREACHABLE_JS = """() => {
    const out = [];
    document.querySelectorAll('[data-act-click]').forEach(el => {
        if (el.offsetParent === null) return;
        if (['A','BUTTON','INPUT','SELECT','TEXTAREA','SUMMARY'].includes(el.tagName)) return;
        if (el.hasAttribute('tabindex')) return;
        if (el.getAttribute('role') === 'button') return;
        // Modal backdrops use data-act-click for click-outside-to-close.
        // They are not controls and must not become tab stops.
        if (el.getAttribute('data-click-self') === '1') return;
        out.push(el.tagName + '.' + ((el.className||'').toString().split(' ')[0] || ''));
    });
    return out;
}"""

# Read while the element is STILL focused, in the same evaluate call.
FOCUS_JS = """() => {
    const a = document.activeElement;
    if (!a || a === document.body) return null;
    const cs = getComputedStyle(a);
    const ring = parseFloat(cs.outlineWidth) > 0
              || (cs.boxShadow && cs.boxShadow !== 'none');
    return {
        who: (a.id || a.className || a.tagName).toString().slice(0, 34),
        ring,
    };
}"""


def run() -> AuditResult:
    preflight()
    findings = []

    with browser_page('desktop') as (page, _ctx):
        # 1. Unreachable clickables, across every pane.
        unreachable: dict[str, int] = {}
        for pane in all_panes(page):
            # The delegate upgrades clickable non-controls via a
            # MutationObserver debounced by 50ms, so a render that finishes
            # just before measurement looks unreachable when it is not.
            # Waiting past the debounce is the difference between measuring
            # the app and measuring the race.
            visit(page, pane, settle=400)
            hits = page.evaluate(UNREACHABLE_JS)
            if hits:
                # Re-check before reporting. The upgrade is debounced and some
                # panes render in stages, so a first read can catch elements
                # mid-flight. Reporting a transient state as a finding sends
                # the next session chasing a bug that does not exist -- which
                # is exactly what happened here before this guard was added.
                page.wait_for_timeout(600)
                hits = page.evaluate(UNREACHABLE_JS)
            for key in hits:
                unreachable[key] = unreachable.get(key, 0) + 1
        for key, count in sorted(unreachable.items(), key=lambda kv: -kv[1]):
            findings.append(f'UNREACHABLE {count:5}x  {key}')

        # 2. Focus rings, using real Tab presses on the default pane.
        visit(page, 'chat')
        page.evaluate("document.body.focus()")
        seen: dict[str, bool] = {}
        for _ in range(60):
            page.keyboard.press('Tab')
            page.wait_for_timeout(TRANSITION_MS)
            state = page.evaluate(FOCUS_JS)
            if state and state['who'] not in seen:
                seen[state['who']] = state['ring']
        for who, ring in seen.items():
            if not ring:
                findings.append(f'NO-RING     {who}')

    return AuditResult(
        'keyboard-operability',
        len(findings),
        findings,
        note='clickable non-controls with no keyboard path, plus tab stops '
             'with no visible focus ring',
    )


if __name__ == '__main__':
    raise SystemExit(emit(run()))
