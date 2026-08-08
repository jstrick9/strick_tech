#!/usr/bin/env python3
"""Snapshot every element's computed style, and compare two snapshots.

WHY THIS EXISTS
───────────────
Refactoring 1,128 inline `style` attributes into 96 utility classes is a
mechanical change with a very large blast radius: a single mis-merged `class`
attribute silently drops either the component styling or the new utility, and
the result is a slightly-wrong pane nobody notices for months.

Arguing that the cascade is equivalent is not evidence. This measures it.

    python3 scripts/audit/computed_style_diff.py --save before.json
    …make the change, rebuild…
    python3 scripts/audit/computed_style_diff.py --compare before.json

WHAT IS COMPARED
────────────────
For every element in every pane, the properties a style attribute in this
codebase can actually set — layout, box, typography, colour. Compared as
COMPUTED values, so `color:var(--danger)` and `.u-color-1 { color:var(--danger) }`
resolve to the same `rgb(...)` and match, while a genuinely lost declaration
does not.

MEASUREMENT NOTES
─────────────────
  * Elements are keyed by a structural path (tag + index among siblings), not
    by class name — the class list is exactly what changes, so keying on it
    would make every element look new.
  * Panes are walked in a fixed order and given a fixed settle time, because
    an async renderer that has not finished yet produces a spurious diff.
  * Only VISIBLE elements. A hidden node's computed layout is not meaningful
    and varies with how it was hidden.

THE CONTROL RUN, AND WHY IT IS MANDATORY
────────────────────────────────────────
The first version of this probe reported 25 differing properties for a
migration — and then reported 25 differing properties for the **UNCHANGED
app compared against its own baseline**. Different paths each run.

A structural path is not stable in this application: several panes render
asynchronously, poll, and insert or reorder nodes after the settle window, so
`DIV:2/DIV:1/DIV:49` refers to a different element on the second run. The
probe was measuring its own timing, not the CSS.

Two changes make the verdict trustworthy:

  * `--compare` now runs the capture TWICE against the same build and
    subtracts the properties that differ between those two runs. Anything
    unstable in the app itself is excluded by construction, rather than by a
    hand-maintained list of flaky panes.
  * `--selftest` runs only the control and reports the noise floor, so the
    instrument can be checked without touching the code under test.

A probe that cannot reproduce its own result is not evidence. This one now
proves its noise floor before reporting anything.
"""

from __future__ import annotations

import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
from _harness import (  # noqa: E402
    BASE_URL,
    LAUNCH_ARGS,
    AuditResult,
    chrome_path,
    emit,
    preflight,
)

# The properties an inline style attribute in this codebase actually sets.
PROPS = [
    'display', 'position', 'flex-direction', 'flex-wrap', 'align-items',
    'justify-content', 'gap', 'grid-template-columns',
    'width', 'height', 'min-width', 'max-width', 'min-height', 'max-height',
    'margin-top', 'margin-right', 'margin-bottom', 'margin-left',
    'padding-top', 'padding-right', 'padding-bottom', 'padding-left',
    'color', 'background-color', 'border-radius', 'border-top-width',
    'border-top-color', 'border-top-style',
    'font-size', 'font-weight', 'font-family', 'line-height', 'text-align',
    'text-transform', 'opacity', 'overflow-x', 'overflow-y', 'white-space',
    'letter-spacing', 'cursor', 'z-index',
]

SNAPSHOT_JS = """(props) => {
    const out = {};
    const path = (el) => {
        const parts = [];
        for (let n = el; n && n !== document.body; n = n.parentElement) {
            const parent = n.parentElement;
            if (!parent) break;
            const idx = [...parent.children].indexOf(n);
            parts.unshift(n.tagName + ':' + idx);
        }
        return parts.join('/');
    };
    document.querySelectorAll('*').forEach(el => {
        if (el.offsetParent === null) return;
        const cs = getComputedStyle(el);
        const rec = {};
        props.forEach(p => { rec[p] = cs.getPropertyValue(p); });
        out[path(el)] = rec;
    });
    return out;
}"""


def _capture() -> dict:
    from playwright.sync_api import sync_playwright

    snapshot = {}
    with sync_playwright() as p:
        browser = p.chromium.launch(executable_path=chrome_path(), args=LAUNCH_ARGS)
        context = browser.new_context(viewport={'width': 1440, 'height': 900})
        page = context.new_page()
        page.goto(BASE_URL, wait_until='domcontentloaded', timeout=60000)
        page.wait_for_timeout(4500)
        page.evaluate("""() => {
            const m = document.getElementById('onboarding-modal')
                   || document.getElementById('onboarding-overlay');
            if (m) m.remove();
        }""")
        for pane in sorted(page.evaluate(
                "Object.keys(window.MASTER_PANE_REGISTRY || {})")):
            page.evaluate(f'window.nav && window.nav({json.dumps(pane)})')
            page.wait_for_timeout(450)
            snapshot[pane] = page.evaluate(SNAPSHOT_JS, PROPS)
        browser.close()
    return snapshot


def run() -> AuditResult:
    preflight()

    if '--save' in sys.argv:
        target = Path(sys.argv[sys.argv.index('--save') + 1])
        target.write_text(json.dumps(_capture()), encoding='utf-8')
        return AuditResult('computed-style-diff', 0,
                           [f'-- snapshot written to {target}'],
                           note='baseline captured')

    if '--compare' not in sys.argv and '--selftest' not in sys.argv:
        return AuditResult('computed-style-diff', 0,
                           ['-- pass --save FILE then --compare FILE, '
                            'or --selftest for the noise floor'],
                           note='no snapshot given')

    def _diff_keys(a: dict, b: dict) -> set:
        """Every (pane, path, prop) whose computed value differs."""
        out = set()
        for pane, elements in a.items():
            other = b.get(pane)
            if other is None:
                continue
            for path, props in elements.items():
                current = other.get(path)
                if current is None:
                    continue      # DOM shape moved; not a style regression
                for prop, value in props.items():
                    if current.get(prop) != value:
                        out.add((pane, path, prop))
        return out

    findings = []

    if '--selftest' in sys.argv:
        first, second = _capture(), _capture()
        noise = _diff_keys(first, second)
        findings.append(
            f'-- noise floor: {len(noise)} propert(ies) differ between two '
            'captures of the SAME build')
        for pane, path, prop in sorted(noise)[:10]:
            findings.append(f'-- unstable: {pane} {path[-40:]} {prop}')
        return AuditResult('computed-style-diff', 0, findings,
                           note='instrument self-test')

    source = Path(sys.argv[sys.argv.index('--compare') + 1])
    before = json.loads(source.read_text(encoding='utf-8'))

    # Capture twice and subtract the app's own instability. Several panes
    # render asynchronously and reorder nodes after the settle window, so a
    # structural path can address a different element on the second run --
    # which made the first version of this probe report 25 differences for an
    # UNCHANGED build. See the control-run note in the module docstring.
    after_a = _capture()
    after_b = _capture()
    unstable = _diff_keys(after_a, after_b)

    real = _diff_keys(before, after_a) - unstable

    for pane in before:
        if pane not in after_a:
            findings.append(f'MISSING-PANE   {pane} did not render after the change')

    for pane, path, prop in sorted(real)[:25]:
        was = before[pane][path][prop]
        now = after_a[pane][path].get(prop)
        findings.append(
            f'STYLE-DIFF     {pane} {path[-48:]} {prop}: {was!r} -> {now!r}')

    if len(real) > 25:
        findings.append(f'-- and {len(real) - 25} more differing properties')
    findings.append(
        f'-- {len(unstable)} propert(ies) excluded as app-side render noise '
        '(differed between two captures of the same build)')

    return AuditResult(
        'computed-style-diff',
        len([f for f in findings if not f.startswith('--')]),
        findings,
        note='computed styles compared property-by-property against a snapshot',
    )


if __name__ == '__main__':
    raise SystemExit(emit(run()))
