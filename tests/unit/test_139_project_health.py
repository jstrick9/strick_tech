"""Module review 6: the quality-tools group.

`ambient`, `bugbot`, `gitai` and `health` all render from
`frontend/js/07-quality-tools.js` (780 lines, 16 endpoints) and were reviewed
as one unit. All four score 20 in `scripts/audit/module_risk.py`.

THE DEFECT: A CONFIDENT GRADE FOR A CODEBASE NEVER ANALYSED
───────────────────────────────────────────────────────────
Two of the five health dimensions substituted an invented number when there
was nothing to measure:

    if total_syms > 0:  complexity_score = ...real calculation...
    else:               complexity_score = 70      # invented

    if total_fns  > 0:  doc_pct = int(with_docs / total_fns * 100)
    else:               doc_pct = 50               # invented

Those placeholders were then weighted into the overall score and rendered as a
letter grade. Measured live with an empty code index:

    overall 87, grade B
    complexity 70   "0 total symbols"
    docs       50   "0/0 functions have docstrings (50%)"

`0/0 ... (50%)` is the tell — a percentage printed beside the division that
could not have produced it.

This is recurring pattern #10 (fabricated data on an empty path) and #3 (a
module reporting success while doing nothing). It is worse here than on the
Dashboard, because a **health grade is the one number a user acts on**: "B,
good enough" is a decision, and it was never measured.

THE FIX
───────
An unmeasurable dimension scores None and is EXCLUDED from the weighted
average; the remaining weights are renormalised.

Renormalising matters as much as excluding. With complexity and docs unknown
the remaining weight is 0.65, and multiplying by that would cap the score at
65 — grading a healthy project "D" for the crime of not being indexed. Same
wrong answer, opposite direction.

THE OVERSTATEMENT THE FIX CREATED, AND ITS FIX
──────────────────────────────────────────────
Removing the placeholders left `100 / A` rendered from 65% of the weighting.
Honest arithmetic, still misleading: two fifths of the assessment never ran.
The pane now states its coverage — "Based on 65% of the assessment — complexity
and docs not measured yet" — with a button that runs Code Index.

A null overall also rendered as `0 / ?` via `||0`, which reads as a failing
grade rather than "not analysed". Not-measured and measured-and-bad must not
look alike.
"""

from __future__ import annotations

import re
from pathlib import Path

REPO = Path(__file__).resolve().parent.parent.parent
AMBIENT = (REPO / 'backend' / 'routers' / 'ambient.py').read_text(encoding='utf-8')
JS = (REPO / 'frontend' / 'js' / '07-quality-tools.js').read_text(encoding='utf-8')
CSS = (REPO / 'frontend' / 'styles-redesign.css').read_text(encoding='utf-8')


def _code_only(source: str) -> str:
    """Source without comments, so an assertion cannot match the explanation
    of the bug it is testing for. Thirteenth occurrence of that trap."""
    source = re.sub(r'"""[\s\S]*?"""', '', source)
    return re.sub(r'(?m)^\s*#.*$', '', source)


AMBIENT_CODE = _code_only(AMBIENT)


def _tip(scores: dict) -> str:
    import sys
    sys.path.insert(0, str(REPO))
    from backend.routers.ambient import _health_tip
    return _health_tip(scores)


# ──────────────────────────────────────────────────────────────────────
#  No invented scores
# ──────────────────────────────────────────────────────────────────────
def test_complexity_has_no_placeholder_score():
    """`complexity_score = 70` with zero symbols indexed."""
    assert 'complexity_score = 70' not in AMBIENT_CODE
    assert "scores['complexity'] = 70" not in AMBIENT_CODE


def test_docs_has_no_placeholder_score():
    """`doc_pct = 50` produced "0/0 functions have docstrings (50%)"."""
    assert 'doc_pct = 50' not in AMBIENT_CODE
    assert "scores['docs'] = 50" not in AMBIENT_CODE


def test_an_unmeasured_dimension_scores_none():
    """None is what lets the average exclude it; 0 would drag the grade down
    and any other number would be a guess."""
    assert "scores['complexity'] = None" in AMBIENT_CODE
    assert "scores['docs'] = None" in AMBIENT_CODE


def test_the_unmeasured_detail_says_what_to_do():
    """"Not measured" alone is a dead end; the user needs the next step."""
    assert 'Run Code Index' in AMBIENT


# ──────────────────────────────────────────────────────────────────────
#  Aggregation
# ──────────────────────────────────────────────────────────────────────
def test_the_average_excludes_unmeasured_dimensions():
    assert 'if v is not None' in AMBIENT_CODE


def test_the_weights_are_renormalised():
    """Without this the score is capped at the measured weight -- 65% here --
    grading a healthy project D for not being indexed."""
    assert '/ total_weight' in AMBIENT_CODE


def test_nothing_measured_yields_no_grade():
    """"Not analysed yet" and "analysed, and it is a B" must not render the
    same."""
    assert 'overall = None' in AMBIENT_CODE
    assert 'grade = None' in AMBIENT_CODE


def test_the_response_reports_its_own_coverage():
    """Without these the UI cannot tell "87 from all five" from "87 from
    three"."""
    assert "'unmeasured': unmeasured" in AMBIENT_CODE
    assert "'measured_weight'" in AMBIENT_CODE


def test_coverage_fields_are_on_the_response_not_the_snapshot_row():
    """My first patch put them beside 'overall_score', which belongs to the
    database row -- the UI would never have seen them."""
    block = AMBIENT[AMBIENT.index("        'overall': overall,"):]
    block = block[:block.index('}')]
    assert "'unmeasured'" in block


# ──────────────────────────────────────────────────────────────────────
#  The tip must survive None
# ──────────────────────────────────────────────────────────────────────
def test_the_tip_does_not_crash_on_an_unmeasured_dimension():
    """`min(scores, key=...)` raised TypeError once a dimension scored None --
    turning an honest "not measured" into a 500."""
    out = _tip({'complexity': None, 'security': 100, 'debt': 90,
                'docs': None, 'deps': 100})
    assert isinstance(out, str) and out


def test_the_tip_targets_a_measured_dimension():
    """Suggesting work on a dimension never assessed is wrong even when it
    does not crash."""
    out = _tip({'complexity': None, 'security': 40, 'debt': 90,
                'docs': None, 'deps': 100})
    assert 'security' in out.lower()


def test_the_tip_when_nothing_was_measured():
    out = _tip({'complexity': None, 'docs': None})
    assert 'Code Index' in out


# ──────────────────────────────────────────────────────────────────────
#  UI
# ──────────────────────────────────────────────────────────────────────
def test_the_pane_states_its_coverage():
    """Honest arithmetic over 65% of the assessment is still misleading if the
    pane renders a bare "A"."""
    assert 'health-coverage' in JS
    # Whitespace-normalised: the template literal wraps across lines, so the
    # phrase is not one contiguous string in the source. My first version
    # asserted the raw text and failed on my own line break.
    flat = ' '.join(JS.split())
    assert 'of the assessment' in flat
    assert 'not measured yet' in flat
    assert '.health-coverage' in CSS, 'the banner is unstyled'


def test_a_null_grade_is_not_rendered_as_zero():
    """`${h.overall||0}` and `${h.grade||'?'}` render "0 / ?", which reads as a
    failing grade rather than "not analysed"."""
    assert '${h.overall||0}' not in JS
    assert "${h.grade||'?'}" not in JS
    assert 'Not analysed yet' in JS


def test_the_coverage_banner_offers_the_fix():
    block = JS[JS.index('health-coverage'):][:600]
    assert "nav('codeindex')" in block
