"""The last undersized touch targets, and why the previous rule missed them.

THE FINDING
───────────
Batch 34 added `min-width: 44px; min-height: 44px` to every control under
`@media (pointer: coarse)`. Re-auditing all 68 panes at 390px found the rule
was **inert on 22 of them**, because:

    min-width and min-height have NO EFFECT on a `display: inline` box.

The rule was applied and did nothing. The worst case was a 6x12 px `🪪` link
on the A2A pane (15 instances) — roughly **1/27th** of the recommended target
area, and the smallest interactive element in the product. Also an 8x17 px
status toggle on MCP Gateway and two 386x21 px export links.

That is a real gap in the previous batch, not a leftover.

THE FIX
───────
Non-prose links and `[role=button]` become `inline-block` on touch, which is
what makes the minimum take effect. Prose links (`p a`, `li a`, `.prose a`,
`td a`) stay `inline` so they keep wrapping with the surrounding text — a
44px block dropped into the middle of a paragraph would break the line box.

CHECKBOXES: A CORRECTION
────────────────────────
An earlier note in this review said the remaining checkboxes sat in "dense
tables" and needed a design decision about visual weight. Measuring found
that was wrong — they are in `<label>` wrappers (Swarm) and list rows
(MCP Gateway, Replay), with `inTable: False`.

So they stay 24x24 (already ~3x the platform default, and WCAG 2.5.8 AA) and
the ROW becomes the target instead. A label wrapping a checkbox is already
clickable in HTML — the browser forwards the click — so a 44px min-height on
the row gives a comfortable tap area with the control's visual weight
completely unchanged. Measured: rows are 137x44 and 174x44 while the boxes
remain 24x24.
"""

from __future__ import annotations

import re
from pathlib import Path

REPO = Path(__file__).resolve().parent.parent.parent
CSS = (REPO / 'frontend' / 'styles-redesign.css').read_text(encoding='utf-8')
CSS_CODE = re.sub(r'/\*.*?\*/', '', CSS, flags=re.S)

COARSE = CSS_CODE[CSS_CODE.index('@media (pointer: coarse)'):]
_depth, _end = 0, None
for _i, _ch in enumerate(COARSE):
    if _ch == '{':
        _depth += 1
    elif _ch == '}':
        _depth -= 1
        if _depth == 0:
            _end = _i
            break
COARSE_BLOCK = COARSE[:_end]
AFTER_COARSE = COARSE[_end:]


# ──────────────────────────────────────────────────────────────────────
#  The inline-box gap
# ──────────────────────────────────────────────────────────────────────
def test_interactive_elements_are_promoted_out_of_inline_flow():
    """`min-width` is inert on `display: inline`, so the rule did nothing.

    Without this the 44px minimum silently fails on every inline control —
    which is exactly how a 6x12px link survived a batch that claimed to have
    fixed touch targets.
    """
    assert 'display: inline-block' in COARSE_BLOCK, (
        'inline controls must be promoted or the size minimum has no effect')
    promo = COARSE_BLOCK[COARSE_BLOCK.index('display: inline-block') - 220:
                         COARSE_BLOCK.index('display: inline-block')]
    assert 'a[href]' in promo and '[role="button"]' in promo


def test_prose_links_stay_inline():
    """A 44px block inside a sentence breaks the line box and text wrapping."""
    assert re.search(r'p a\[href\],\s*\n\s*li a\[href\]', COARSE_BLOCK), (
        'paragraph and list links must be excluded from block promotion')
    assert 'td a[href]' in COARSE_BLOCK, (
        'links inside table cells should also keep inline flow')
    tail = COARSE_BLOCK[COARSE_BLOCK.index('p a[href]'):]
    assert 'display: inline;' in tail


def test_the_exclusion_comes_after_the_promotion():
    """Both rules have equal specificity, so source order decides.

    If the exclusion were written first the promotion would override it and
    every prose link would become a block.
    """
    # Compare the START OF EACH RULE, not the position of a declaration.
    # An earlier version compared `index('display: inline-block')` against
    # `index('p a[href]')`; when the promotion block was physically moved to
    # sit just above the exclusion, its declaration was still "before" the
    # exclusion's selector and the test passed against the broken order.
    promo_decl = COARSE_BLOCK.index('display: inline-block')
    promo_rule_start = COARSE_BLOCK.rfind('}', 0, promo_decl) + 1
    prose_sel = COARSE_BLOCK.index('p a[href]')
    prose_rule_start = COARSE_BLOCK.rfind('}', 0, prose_sel) + 1
    assert promo_rule_start < prose_rule_start, (
        'the prose exclusion must come after the promotion to win the cascade')
    # And they must be genuinely separate rules, not one merged block.
    assert '}' in COARSE_BLOCK[promo_decl:prose_sel], (
        'promotion and exclusion must be distinct rules')


# ──────────────────────────────────────────────────────────────────────
#  Checkboxes: row target, not a bigger box
# ──────────────────────────────────────────────────────────────────────
def test_checkboxes_are_not_inflated():
    """24x24 is ~3x the platform default and satisfies WCAG 2.5.8 (AA).

    Growing them to 44x44 would dominate rows sitting next to 13px body text
    for no benefit, since the row itself is the target.
    """
    assert 'min-width: 24px' in COARSE_BLOCK

    # Locate the rule whose selector list is the bare inputs -- not the
    # `label:has(> input…)` row rule, which legitimately sets 44px. An
    # earlier version of this test used a loose regex that matched the
    # :has() rule and failed against correct CSS.
    match = re.search(
        r'(?m)^\s*input\[type="checkbox"\],\s*\n\s*input\[type="radio"\]\s*\{([^}]*)\}',
        COARSE_BLOCK)
    assert match, 'could not find the checkbox sizing rule'
    body = match.group(1)
    assert '24px' in body
    assert '44px' not in body, (
        'the checkbox itself should stay 24px; the row carries the 44px target')


def test_the_row_is_the_touch_target():
    for selector in ('.prb-policy-item', '.ttd-run-card-top',
                     'label:has(> input[type="checkbox"])'):
        assert selector in COARSE_BLOCK, f'{selector} should be a 44px row target'


def test_has_selector_is_isolated_in_its_own_rule():
    """A selector list is parsed as a unit.

    If any selector in a comma-separated list is unsupported, the browser
    discards the ENTIRE rule. Grouping `:has()` with the plain class selectors
    would silently drop their row sizing too on an engine without `:has()`
    support. Isolated, such a browser loses only this one enhancement.
    """
    # Slice BACKWARDS to the start of the rule, not forwards from `:has()`.
    # An earlier version scanned forward only, so a class selector listed
    # BEFORE `:has()` in the same list was invisible to it -- and the test
    # passed against exactly the grouping it was meant to forbid.
    has_at = COARSE_BLOCK.index('label:has(> input[type="checkbox"])')
    rule_start = COARSE_BLOCK.rfind('}', 0, has_at) + 1
    rule = COARSE_BLOCK[rule_start:COARSE_BLOCK.index('}', has_at)]
    assert '.prb-policy-item' not in rule, (
        ':has() must not share a selector list with plain class selectors; '
        'an engine without :has() support discards the whole rule')
    assert '.ttd-run-card-top' not in rule


# ──────────────────────────────────────────────────────────────────────
#  Containment
# ──────────────────────────────────────────────────────────────────────
def test_nothing_leaked_outside_the_coarse_pointer_query():
    """Desktop density was deliberately tuned and must not shift.

    Verified live: `matchMedia('(pointer: coarse)')` is false at 1440px, the
    A2A link is 21px tall there and the Swarm checkbox is 13px.
    """
    assert 'display: inline-block' not in AFTER_COARSE
    assert 'min-height: 44px' not in AFTER_COARSE
