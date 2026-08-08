"""Long, hostile and merely unusual text.

WHAT WAS MEASURED
─────────────────
Nine payloads written through the real API and rendered by the UI: three XSS
vectors, a template-injection string, an apostrophe, an emoji, right-to-left
text, 4,000 unbroken characters, and 10,800 characters of prose.

**No XSS, and no data loss.** All three script vectors were inert, the
apostrophe was not double-escaped, and emoji and Arabic survived the round
trip. That is worth recording as a result rather than silence: escaping is the
thing most likely to be quietly wrong, and here it is right.

THE DEFECT: A LONG VALUE ESCAPED ITS CARD
─────────────────────────────────────────
A 4,000-character title rendered in a 235px card with `scrollWidth: 2137px`
and `overflow: visible` — spilling straight across neighbouring cards and
making the column unreadable.

`documentElement.scrollWidth` stayed at exactly **1440px** throughout. By the
global measure the page was perfect. This is why the audit checks element-level
overflow as well: the existing `responsive.py` audit, which measures document
width, reported 0 for this page and was right to — it is a different bug.

THE FIX, AND THE REGRESSION IT CAUSED
─────────────────────────────────────
A structural containment rule (`overflow-wrap: anywhere` plus `min-width: 0` on
flex/grid children), not a patch to `.kanban-card-title` — users paste long
values into every field, so fixing the one class that happened to be measured
leaves the bug everywhere else and does nothing about the next component.

The first version of that rule applied `min-width: 0` to **every** child and
immediately regressed the touch-target audit from **0 to 9**: it overrode the
structural 44px rule from batch 34 and collapsed buttons to 12–36px wide (a
bulk-delete button became 12×44). The rule now excludes interactive elements.
A containment rule must never shrink a tap target — text needs to wrap, a
control needs to stay hittable.

The ratchet caught this. It is exactly the case the ratchet was built for.
"""

from __future__ import annotations

import json
import re
from pathlib import Path

REPO = Path(__file__).resolve().parent.parent.parent
CSS = (REPO / 'frontend' / 'styles-redesign.css').read_text(encoding='utf-8')
AUDIT = REPO / 'scripts' / 'audit'
AUDIT_SRC = (AUDIT / 'adversarial_input.py').read_text(encoding='utf-8')


def _strip_css_comments(source: str) -> str:
    """So an assertion cannot be satisfied by the comment explaining it."""
    return re.sub(r'/\*.*?\*/', '', source, flags=re.S)


CSS_RULES = _strip_css_comments(CSS)


def _rule_after(needle: str) -> str:
    """The declaration block a selector belongs to."""
    idx = CSS_RULES.index(needle)
    return CSS_RULES[idx:CSS_RULES.index('}', idx)]


# ──────────────────────────────────────────────────────────────────────
#  Containment
# ──────────────────────────────────────────────────────────────────────
def test_long_values_are_allowed_to_wrap():
    """A 4000-char title overflowed a 235px card by 1900px."""
    assert 'overflow-wrap: anywhere' in CSS_RULES, (
        'a structural wrap rule is needed; long values escape their card')


def test_wrapping_uses_anywhere_not_break_all():
    """`break-all` chops ordinary words mid-letter even when they would fit,
    making normal text ugly to fix a rare case. `anywhere` only breaks a run
    that has no other way to fit."""
    assert 'word-break: break-all' not in CSS_RULES


def test_flex_children_may_shrink():
    """A flex item's default `min-width: auto` refuses to shrink below its
    content, so the wrap rule silently does nothing inside a flex row."""
    assert 'min-width: 0' in CSS_RULES


def test_the_containment_rule_does_not_shrink_controls():
    """THE REGRESSION. min-width:0 on every child overrode the structural 44px
    touch rule and collapsed buttons to 12-36px wide. The audit went 0 -> 9.
    """
    block = _rule_after("[class*='-row'] > *")
    for element in ('button', 'input', 'select', 'textarea'):
        assert f':not({element})' in block, (
            f'{element} must be excluded from min-width:0, or the touch-target '
            'rule is overridden and controls collapse')
    assert ":not(a)" in block


def test_there_is_an_opt_out():
    """Some values genuinely must stay on one line -- a code token being
    copied, a column with its own ellipsis."""
    assert '.no-wrap-guard' in CSS_RULES


def test_the_opt_out_does_not_restore_min_width_auto():
    """`min-width: auto` inside the opt-out would re-break flex layouts for
    anything using it, which is a bigger blast radius than the opt-out is
    meant to have."""
    block = _rule_after('.no-wrap-guard')
    assert 'min-width' not in block


# ──────────────────────────────────────────────────────────────────────
#  The probe
# ──────────────────────────────────────────────────────────────────────
def test_xss_is_detected_by_a_side_effect_not_by_string_search():
    """Searching innerHTML for `<script>` finds correctly-escaped values and
    misses `onerror=` entirely -- it reports the safe case and misses the
    dangerous one."""
    assert '__xss' in AUDIT_SRC
    assert 'onerror' in AUDIT_SRC, 'an attribute-based vector must be covered'
    assert 'svg onload' in AUDIT_SRC or 'onload' in AUDIT_SRC


def test_the_probe_checks_element_overflow_not_only_document_width():
    """The document stayed exactly 1440px while a value spilled 1900px out of
    its card. A document-level check alone reports clean."""
    assert 'scrollWidth' in AUDIT_SRC
    assert 'clientWidth' in AUDIT_SRC
    assert "overflow !== 'visible'" in AUDIT_SRC, (
        'a container that clips or scrolls is a design choice, not a break')


def test_the_probe_verifies_its_own_writes_landed():
    """A probe whose writes were all rejected reported a clean PASS while
    measuring nothing -- that exact failure hit the concurrency audit."""
    assert 'if not written' in AUDIT_SRC
    assert 'measured' in AUDIT_SRC


def test_the_probe_covers_non_latin_and_emoji():
    """Escaping bugs show up as mangled emoji and dropped RTL text long before
    they show up as anything a Latin-alphabet test would notice."""
    assert 'rtl' in AUDIT_SRC
    assert 'emoji' in AUDIT_SRC


def test_the_audit_is_registered():
    assert 'adversarial_input' in (AUDIT / 'run_all.py').read_text(encoding='utf-8')
    ratchet = (REPO / 'tests' / 'unit' / 'test_120_audit_ratchet.py').read_text(
        encoding='utf-8')
    assert 'adversarial-input' in ratchet
    baseline = json.loads((AUDIT / 'baseline.json').read_text(encoding='utf-8'))
    assert baseline.get('adversarial-input') == 0
