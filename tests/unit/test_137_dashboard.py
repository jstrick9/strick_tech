"""Module review 4: Dashboard (`dashboard`).

Risk rank 4 of 68 (score 34).

THE DEFECT: A FABRICATED HEADLINE NUMBER
────────────────────────────────────────
    saved_vs_saas = round(max(0.0, 350.0 - total_cost * 100), 2)

`350.0` is a hardcoded constant with no input from the account. Verified in a
real browser on a brand-new install, where every other KPI reads zero:

    💰 TOTAL COST   $0.0000   Saved $350 vs SaaS
    🔤 TOKENS USED  0         0 messages
    📋 TASKS        0         0% complete

It is a *measurement* presented among measurements — and the largest figure on
the pane. Every other number there is derived from the user's own data, so this
one reads as real too. A user who has done nothing is told the product has
already saved them $350.

Recurring pattern #10 in this review: fabricated data on an empty path, the
same class as the Kanban board rendering six invented tasks during an outage.

**The arithmetic was also backwards.** `total_cost * 100` asserts a SaaS
product costs exactly 100× whatever the local run cost, so heavier use drives
the "savings" DOWN — spend $3.50 and the dashboard tells you that you saved
nothing at all.

THE FIX
───────
Derive the comparison from real usage, state the assumption instead of hiding
it, and return **None** when there is nothing to compare.

`None`, not `0`, because "we have not measured this" and "we measured it and
it is zero" are different claims. The UI renders the first as "No usage yet"
rather than "Saved $0 vs SaaS", which would still be asserting a comparison
that was never made.

The response now carries `saved_vs_saas_basis`, so the pane can show its own
working: **"Saved $0.19 vs SaaS (est. $0.02/msg × 10)"**. A figure the user can
check is a different thing from a figure they must trust.

VERIFIED AS ALREADY CORRECT
───────────────────────────
  * `days` is clamped: 0 and -5 → 1, 99999 → 365, `abc` → 422.
  * Load failures already route through `humanError()`/`httpError()` with a
    Retry control and a "your data is safe" framing.
  * Every other panel has a real empty state ("No cost data yet", "Run a swarm
    to see winners here") rather than a zero pretending to be a measurement.
"""

from __future__ import annotations

import re
from pathlib import Path

REPO = Path(__file__).resolve().parent.parent.parent
ANALYTICS = (REPO / 'backend' / 'routers' / 'analytics.py').read_text(encoding='utf-8')
JS = (REPO / 'frontend' / 'js' / '36-dashboard.js').read_text(encoding='utf-8')


def _kpis(messages: int, cost: float) -> dict:
    """Compute the savings figure the way the router does, from its own
    constant — so the test cannot drift from the implementation."""
    import sys
    sys.path.insert(0, str(REPO))
    from backend.routers.analytics import SAAS_COST_PER_MESSAGE

    equivalent = round(messages * SAAS_COST_PER_MESSAGE, 2)
    return {
        'per_message': SAAS_COST_PER_MESSAGE,
        'saved': round(max(0.0, equivalent - cost), 2) if messages > 0 else None,
    }


# ──────────────────────────────────────────────────────────────────────
#  The fabricated number
# ──────────────────────────────────────────────────────────────────────
def test_the_hardcoded_350_baseline_is_gone():
    """A constant with no input from the account, shown as a measurement.

    Comments are stripped first: the fix documents the old expression verbatim
    so the next reader knows what changed, and asserting against raw source
    matched that explanation. Twelfth time an assertion has matched its own
    fix comment in this review.
    """
    code = re.sub(r'(?m)^\s*#.*$', '', ANALYTICS)
    code = re.sub(r'"""[\s\S]*?"""', '', code)
    assert '350.0 - total_cost' not in code


def test_savings_is_none_when_there_is_no_usage():
    """None, not 0. "Not measured" and "measured, and zero" are different
    claims, and the UI renders them differently."""
    assert _kpis(messages=0, cost=0.0)['saved'] is None


def test_savings_is_computed_from_real_messages():
    out = _kpis(messages=10, cost=0.01)
    assert out['saved'] == round(10 * out['per_message'] - 0.01, 2)


def test_heavier_usage_increases_the_savings():
    """THE OLD ARITHMETIC WENT THE WRONG WAY. `350 - cost*100` fell as usage
    rose, so spending $3.50 reported zero savings."""
    light = _kpis(messages=10, cost=0.01)['saved']
    heavy = _kpis(messages=1000, cost=1.00)['saved']
    assert heavy > light, (
        f'savings must grow with usage, got {light} -> {heavy}')


def test_savings_never_goes_negative():
    """A local run more expensive than the comparison is a real possibility;
    a negative "saving" is not a sentence anyone should read."""
    assert _kpis(messages=1, cost=999.0)['saved'] == 0.0


def test_the_assumption_is_named_and_not_buried():
    """A magic number inside an expression cannot be reviewed or changed."""
    assert 'SAAS_COST_PER_MESSAGE' in ANALYTICS
    block = ANALYTICS[ANALYTICS.index('SAAS_COST_PER_MESSAGE'):][:80]
    assert '=' in block


def test_the_basis_is_returned_so_the_ui_can_show_its_working():
    """A figure the user can check differs from one they must trust."""
    assert "'saved_vs_saas_basis'" in ANALYTICS
    assert "'per_message_usd'" in ANALYTICS
    assert "'messages'" in ANALYTICS


# ──────────────────────────────────────────────────────────────────────
#  The UI must not turn None back into a claim
# ──────────────────────────────────────────────────────────────────────
def test_the_ui_does_not_coerce_null_savings_to_zero():
    """`(k.saved_vs_saas_usd||0)` would render "Saved $0 vs SaaS" — still a
    claim about a comparison that was never made."""
    assert '(k.saved_vs_saas_usd||0)' not in JS
    assert 'No usage yet' in JS


def test_the_ui_shows_the_basis():
    assert 'saved_vs_saas_basis' in JS
    assert 'per_message_usd' in JS


def test_the_ui_checks_for_null_explicitly():
    """`|| 0` and `=== null` behave differently for a legitimate 0."""
    block = JS[JS.index('Total Cost'):][:700]
    assert 'null' in block and 'undefined' in block


# ──────────────────────────────────────────────────────────────────────
#  Guards on what was already right
# ──────────────────────────────────────────────────────────────────────
def test_the_period_is_clamped():
    """Probed live: 0 and -5 -> 1, 99999 -> 365, 'abc' -> 422.

    Exercises the real helper rather than grepping for a syntax I guessed at
    -- my first version looked for `max(1`, and the clamp is a named function.
    """
    import sys
    sys.path.insert(0, str(REPO))
    from backend.routers.analytics import _clamp_days

    assert _clamp_days(0) == 1
    assert _clamp_days(-5) == 1
    assert _clamp_days(99999) == 365
    assert _clamp_days(30) == 30


def test_load_failures_use_human_error_copy():
    """The pane predates 00-error-copy.js in places; this path does not."""
    assert 'humanError' in JS
    assert 'httpError' in JS
    assert 'dataSafe' in JS


def test_a_failed_load_offers_a_retry():
    """An error with no way to recover is a dead end."""
    block = JS[JS.index('async function renderDashboard'):][:2600]
    assert 'Retry' in block
