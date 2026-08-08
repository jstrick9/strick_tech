"""Printing, and having the application open twice.

MULTI-TAB — NO DEFECTS
──────────────────────
Two independent browser contexts, a record created in one, that pane opened in
the other: the record was there. Recorded as a verified result rather than
silence. The check drives real UI in the second window rather than reading the
API, because the question is whether the second WINDOW learns, not whether the
server knows.

PRINT — THREE DEFECTS
─────────────────────
`frontend/styles-print.css` was loaded but had never been verified. Measured
with `emulate_media(media='print')`:

1. **PRINT-CHROME.** `#next-action-bar` printed as a floating strip across the
   first page. The original hide-list was written before that element existed
   — it is created at runtime by `04-workflow-specs.js` — along with the
   session, connection and offline banners, and the Studio toolbars.

2. **PRINT-CLIPPED — the one that loses data.** A scroll container prints only
   the slice that happens to be visible. `#kanban-col-todo` held **8,808px of
   tasks in a 600px box**, so the user got the first few and *nothing on the
   printed page said the rest existed*. That is strictly worse than a visible
   error: the output looks complete and is not. Same failure class as finding
   #9 in this review — "the response not describing its own completeness".

3. **PRINT-INVISIBLE.** The existing rule set `body { background: white; color:
   black }`, but every card, panel and pill kept its dark background. Body
   luminance under print emulation measured **0.04**. On paper that is a full
   page of toner with light text on top.

WHY `* { overflow: visible }` AND NOT A LIST OF CONTAINERS
──────────────────────────────────────────────────────────
Enumerating today's scroll containers misses every one added later, and there
is no cost to releasing the constraint in print: paper has no viewport to
scroll. The same argument applies to forcing the palette at the leaf level
rather than on `body`.

A NOTE ON THE FILE'S SCOPING
────────────────────────────
`styles-print.css` contains no `@media print` wrapper and does not need one —
it is scoped by `media="print"` on its `<link>` in index.html. That looked like
a bug on first reading and is not; the test below pins the arrangement so
nobody "fixes" it in either direction.
"""

from __future__ import annotations

import json
import re
from pathlib import Path

REPO = Path(__file__).resolve().parent.parent.parent
PRINT_CSS = (REPO / 'frontend' / 'styles-print.css').read_text(encoding='utf-8')
HTML = (REPO / 'frontend' / 'index.html').read_text(encoding='utf-8')
AUDIT = REPO / 'scripts' / 'audit'
AUDIT_SRC = (AUDIT / 'print_and_multitab.py').read_text(encoding='utf-8')

RULES = re.sub(r'/\*.*?\*/', '', PRINT_CSS, flags=re.S)


# ──────────────────────────────────────────────────────────────────────
#  Scoping
# ──────────────────────────────────────────────────────────────────────
def test_the_print_sheet_is_scoped_by_its_link():
    """No @media wrapper is needed, and adding one inside a media="print"
    sheet would be harmless but misleading. Pinned so the arrangement is not
    "fixed" in either direction."""
    assert re.search(r'<link[^>]*media="print"[^>]*styles-print\.css', HTML), (
        'the print sheet must be linked with media="print"')


# ──────────────────────────────────────────────────────────────────────
#  Chrome
# ──────────────────────────────────────────────────────────────────────
def test_runtime_created_chrome_is_hidden_when_printing():
    """#next-action-bar is created by JS and is position:fixed, so it printed
    as a floating strip across the first page."""
    for selector in ('#next-action-bar', '#session-banner',
                     '#connection-banner', '#net-offline-banner'):
        assert selector in RULES, f'{selector} still prints'


def test_studio_toolbars_are_hidden_when_printing():
    assert '.studio-toolbar' in RULES
    assert '#studio-console-drawer' in RULES


# ──────────────────────────────────────────────────────────────────────
#  Clipping — the data-loss case
# ──────────────────────────────────────────────────────────────────────
def test_scroll_containers_release_their_height_when_printing():
    """8,808px of tasks printed as 600px with nothing saying the rest existed.

    Asserted as a universal rule on purpose: enumerating today's scroll
    containers misses every one added later, and paper has no viewport to
    scroll, so there is no cost to releasing it everywhere.
    """
    assert 'overflow: visible !important' in RULES
    assert 'max-height: none !important' in RULES


def test_the_shell_returns_to_normal_flow_when_printing():
    """The app shell is a fixed-height flex layout built for a viewport; left
    alone it constrains the page even once overflow is released."""
    for selector in ('#shell', '#content', '.pane'):
        assert selector in RULES
    assert 'height: auto !important' in RULES
    assert 'position: static !important' in RULES


# ──────────────────────────────────────────────────────────────────────
#  Palette
# ──────────────────────────────────────────────────────────────────────
def test_the_dark_palette_is_forced_light_at_the_leaf_level():
    """`body { background: white }` alone left every card dark -- a full page
    of toner with light text on it. Measured body luminance: 0.04."""
    assert 'background: transparent !important' in RULES
    assert 'color: #000 !important' in RULES
    assert re.search(r'body\s*\{[^}]*background:\s*#fff', RULES)


def test_borders_survive_the_palette_flattening():
    """Once every fill is gone the page is an undifferentiated wall of text."""
    assert 'border: 1px solid' in RULES


def test_cards_are_not_split_across_a_page_break():
    assert 'break-inside: avoid' in RULES
    assert 'page-break-inside: avoid' in RULES, (
        'the legacy property is still required by some print engines')


def test_link_targets_are_printed():
    """A link's destination is invisible on paper."""
    assert "a[href^='http']::after" in RULES or 'a[href^="http"]::after' in RULES
    assert 'attr(href)' in RULES


# ──────────────────────────────────────────────────────────────────────
#  The probe
# ──────────────────────────────────────────────────────────────────────
def test_the_probe_emulates_the_print_medium():
    """Rendering to PDF and diffing pixels measures the rasteriser as much as
    the CSS; emulate_media changes the cascade, which is what a print
    stylesheet acts on."""
    assert "emulate_media(media='print')" in AUDIT_SRC


def test_the_probe_returns_to_screen_media():
    """Leaving the context in print mode would silently corrupt any later
    measurement made on the same page."""
    assert "emulate_media(media='screen')" in AUDIT_SRC


def test_the_multitab_check_drives_the_second_window(): 
    """Reading the API from tab B proves the server knows, not that the second
    WINDOW learns -- which is the actual question."""
    assert 'window.nav' in AUDIT_SRC
    assert 'ctx_b' in AUDIT_SRC


def test_the_multitab_check_verifies_its_own_write():
    """A probe whose write was rejected reports a clean pass while measuring
    nothing -- the exact failure that hit the concurrency audit."""
    assert 'measured nothing' in AUDIT_SRC


def test_the_audit_is_registered():
    assert 'print_and_multitab' in (AUDIT / 'run_all.py').read_text(encoding='utf-8')
    ratchet = (REPO / 'tests' / 'unit' / 'test_120_audit_ratchet.py').read_text(
        encoding='utf-8')
    assert 'print-and-multitab' in ratchet
    baseline = json.loads((AUDIT / 'baseline.json').read_text(encoding='utf-8'))
    assert baseline.get('print-and-multitab') == 0
