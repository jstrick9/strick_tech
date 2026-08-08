"""Reduced motion, forced colours, and zoom to 200%.

Three seams sharing one probe, because each is the same shape: the user has
told the operating system how they need to be treated, and the question is
whether the application listens.

RESULT PER SEAM
───────────────

**Reduced motion — no defects.** Under `prefers-reduced-motion: reduce`, zero
elements still animated past 100ms across six panes. Recorded as a verified
result rather than silence.

**Forced colours — 2 real defects.** `.agent-status` and `.sb-dot` were empty
`<div>`s whose entire meaning was their background colour. Under
`forced-colors: active` (Windows High Contrast) the system replaces the
palette, so "green = healthy" becomes an unlabelled grey box. Both now carry
`role="img"` and an `aria-label`, which fixes screen readers at the same time.

**Zoom to 200% — 5 real defects, WCAG 1.4.4 (AA).** At 200% on a 1280x1024
desktop the CSS viewport is 640x512. Measured there:

| Container | Overflowed to | Controls lost |
|---|---|---|
| `#topbar` | 838px | notifications, settings, profile |
| `#next-action-bar` | 715px | trailing action |
| `#studio-editor-row` | 719px | Format, Find, Review |
| `.preview-toolbar` | 817px | Full / 375 / 768 / 1280 |
| `#studio-console-drawer` | 844px | Linter, Clear, Collapse |

**A fix for the topbar already existed and was inert.** It sat inside
`@media (pointer: coarse)` — and a desktop user at 200% zoom has a *fine*
pointer, so it never matched. The constraint here is available width, which is
exactly what zoom reduces, so the rules are keyed to width.

That is the second time in this file's history that a present, reasonable CSS
fix did nothing: the comment above the existing rule records a
`.topbar__actions` selector that pointed at markup which never existed.

THREE PROBE BUGS, ALL FOUND BEFORE THE APP'S
────────────────────────────────────────────
1. A closed off-canvas drawer is correct responsive design, not a WCAG
   failure. Counting the sidebar's 24 links as "unreachable" buried the real
   finding under noise.
2. The drawer was first detected by parsing its transform matrix literally,
   which would miss the same drawer moved by `left` or a percentage.
   Geometry is the real definition.
3. The sidebar parks at exactly `right: 0`, so a strict `<= 0` treated it as
   on screen. A 1px tolerance was needed.
"""

from __future__ import annotations

import json
import re
from pathlib import Path

REPO = Path(__file__).resolve().parent.parent.parent
CSS = (REPO / 'frontend' / 'styles-redesign.css').read_text(encoding='utf-8')
HTML = (REPO / 'frontend' / 'index.html').read_text(encoding='utf-8')
AUDIT = REPO / 'scripts' / 'audit'
AUDIT_SRC = (AUDIT / 'preferences.py').read_text(encoding='utf-8')


def _strip_css_comments(source: str) -> str:
    return re.sub(r'/\*.*?\*/', '', source, flags=re.S)


CSS_RULES = _strip_css_comments(CSS)


def _strip_js_comments(source: str) -> str:
    source = re.sub(r'/\*.*?\*/', '', source, flags=re.S)
    return re.sub(r'(?m)^\s*//.*$', '', source)


APP_CORE = _strip_js_comments(
    (REPO / 'frontend' / 'js' / '01-app-core.js').read_text(encoding='utf-8'))


def _width_media_blocks() -> str:
    """Every `@media (max-width: …)` block, concatenated.

    Rules keyed to `pointer: coarse` are deliberately NOT included: that is the
    exact mistake this batch fixed, and a test that accepted them would pass
    against the bug.
    """
    out = []
    for match in re.finditer(r'@media\s*\(max-width:[^)]*\)\s*\{', CSS_RULES):
        start = match.end()
        depth = 1
        i = start
        while i < len(CSS_RULES) and depth:
            if CSS_RULES[i] == '{':
                depth += 1
            elif CSS_RULES[i] == '}':
                depth -= 1
            i += 1
        out.append(CSS_RULES[start:i])
    return '\n'.join(out)


WIDTH_RULES = _width_media_blocks()


# ──────────────────────────────────────────────────────────────────────
#  Zoom / narrow viewport
# ──────────────────────────────────────────────────────────────────────
def test_topbar_actions_wrap_at_narrow_widths():
    """A rule existed but only under `pointer: coarse`, which a zoomed desktop
    user does not match."""
    assert '#topbar-actions' in WIDTH_RULES, (
        'the topbar fix must be keyed to WIDTH, not to a pointer type')


def test_the_topbar_itself_can_wrap():
    """Wrapping only the actions row is not enough when the bar is a
    fixed-height flex row."""
    assert '#topbar' in WIDTH_RULES
    assert 'flex-wrap: wrap' in WIDTH_RULES


def test_next_action_bar_left_inset_is_dropped():
    """It is created in JS with `left: var(--sidebar-w)` inline. Once the
    sidebar becomes an off-canvas drawer that inset points at nothing, and the
    bar's trailing control sat at x=715 in a 640px viewport."""
    assert '#next-action-bar' in WIDTH_RULES
    block = WIDTH_RULES[WIDTH_RULES.index('#next-action-bar'):]
    block = block[:block.index('}')]
    assert 'left: 0' in block
    assert '!important' in block, (
        'the declaration being overridden is inline on the element, so it '
        'cannot be beaten on specificity alone')


def test_studio_panels_stack_rather_than_overflow():
    """Studio kept a file panel and an editor side by side; at 640px the
    editor toolbar ran to x=719 with Format, Find and Review unreachable."""
    assert '#studio-editor-row' in WIDTH_RULES
    assert '.studio-toolbar' in WIDTH_RULES
    assert '.preview-toolbar' in WIDTH_RULES
    assert '#studio-console-drawer' in WIDTH_RULES


def test_the_inert_pointer_coarse_rule_is_not_the_only_fix():
    """Guard against someone 'simplifying' the width rules away again."""
    coarse_only = re.search(
        r'@media \(pointer: coarse\)[^@]*#topbar-actions', CSS_RULES)
    assert coarse_only is None or '#topbar-actions' in WIDTH_RULES, (
        'a pointer-based rule alone does not apply to a zoomed desktop')


# ──────────────────────────────────────────────────────────────────────
#  Forced colours
# ──────────────────────────────────────────────────────────────────────
def test_agent_status_dot_has_an_accessible_name():
    """An empty div whose only meaning is background-colour disappears under
    forced-colors and was never announced to a screen reader either."""
    assert 'agent-status' in APP_CORE
    block = APP_CORE[APP_CORE.index('class="agent-status'):]
    block = block[:block.index('>') + 1]
    assert 'aria-label' in block
    assert 'role="img"' in block


def test_status_dot_markup_has_an_accessible_name():
    assert 'sb-dot' in HTML
    tag = HTML[HTML.index('class="sb-dot"'):]
    tag = tag[:tag.index('>')]
    assert 'aria-label' in tag
    assert 'role="img"' in tag


def test_connection_dot_updates_its_label_not_only_its_colour():
    """Changing only `background` leaves the announced state stale -- the dot
    would say "Online" while showing red."""
    assert 'setDot' in APP_CORE
    block = APP_CORE[APP_CORE.index('const setDot'):]
    block = block[:block.index('};')]
    assert 'aria-label' in block
    assert 'background' in block


# ──────────────────────────────────────────────────────────────────────
#  The probe
# ──────────────────────────────────────────────────────────────────────
def test_the_probe_excludes_a_closed_drawer():
    """A closed off-canvas drawer is correct design. Counting its 24 links as
    unreachable buried the real finding under noise."""
    assert 'inClosedDrawer' in AUDIT_SRC


def test_the_drawer_is_detected_by_geometry_not_by_a_transform_string():
    """Matching `matrix(1, 0, 0, 1, -300, 0)` literally misses the same drawer
    moved by `left`, a percentage translate, or any matrix with a scale."""
    assert 'getBoundingClientRect' in AUDIT_SRC
    assert 'r.right <= 1' in AUDIT_SRC, (
        'the sidebar parks at exactly right:0; a strict <= 0 misses it')


def test_the_probe_ignores_vendored_third_party_ui():
    """`.monaco-status` is Monaco's own aria-live region -- deliberately empty
    and invisible, not a colour indicator. It matched only because the
    selector list looks for "status" in a class name."""
    assert 'monaco' in AUDIT_SRC
    assert "getAttribute('aria-live')" in AUDIT_SRC


def test_the_probe_measures_motion_from_computed_style():
    """A screenshot diff catches only what happens to be moving during the
    capture window, making the result depend on timing luck."""
    assert 'animationDuration' in AUDIT_SRC
    assert 'transitionDuration' in AUDIT_SRC


def test_the_probe_uses_the_wcag_zoom_viewport():
    """WCAG 1.4.4 at 200% on a 1280x1024 desktop is a 640x512 CSS viewport."""
    assert "'width': 640, 'height': 512" in AUDIT_SRC


def test_the_audit_is_registered():
    assert 'preferences' in (AUDIT / 'run_all.py').read_text(encoding='utf-8')
    ratchet = (REPO / 'tests' / 'unit' / 'test_120_audit_ratchet.py').read_text(
        encoding='utf-8')
    assert 'user-preferences' in ratchet
    baseline = json.loads((AUDIT / 'baseline.json').read_text(encoding='utf-8'))
    assert baseline.get('user-preferences') == 0
