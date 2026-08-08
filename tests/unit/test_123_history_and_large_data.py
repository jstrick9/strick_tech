"""Browser Back/Forward, and behaviour at realistic data volumes.

TWO SEAMS, TWO REAL BUGS
────────────────────────

**Back exited the application.** Every navigation used
`history.replaceState()`, never `pushState`. Four pane changes produced ZERO
history entries and pressing Back went to `about:blank` with `window.nav`
undefined -- the whole session gone. Back is a reflex action, so losing
everything is the worst possible outcome.

A `hashchange` handler that routes correctly already existed; it simply never
fired, because `replaceState` does not produce a hashchange.

**A workstation host wiped its own tabs after they were built.** Batch 30
fixed the FIRST render by making nav() await an async host renderer. But a
host can re-render later. Measured with 250 seeded goals: `renderSupervisor()`
ran again ~3s after nav(), replaced `#pane-supervisor`'s innerHTML, and
destroyed a Goals tab that had already rendered 5,976 characters. The user saw
the list appear and then vanish.

Removing the fix and re-auditing showed **7 workstations destroyed**, so this
was far broader than the one case that exposed it.

**Goals capped at 100 of 250 with no way to reach the rest.** It disclosed the
count but told the user to "narrow the filters" -- useless when all 250 match.
"""

from __future__ import annotations

import re
from pathlib import Path

REPO = Path(__file__).resolve().parent.parent.parent
JS = REPO / 'frontend' / 'js'
AUDIT = REPO / 'scripts' / 'audit'


def _strip_comments(source: str) -> str:
    """So an assertion cannot be satisfied by the comment explaining it."""
    source = re.sub(r'/\*.*?\*/', '', source, flags=re.S)
    return re.sub(r'(?m)^\s*//.*$', '', source)


WORKSTATIONS = _strip_comments((JS / '00-workstations.js').read_text(encoding='utf-8'))
APP_CORE = _strip_comments((JS / '01-app-core.js').read_text(encoding='utf-8'))
GOALS = _strip_comments((JS / '49-goals.js').read_text(encoding='utf-8'))
HISTORY_AUDIT = (AUDIT / 'history_navigation.py').read_text(encoding='utf-8')
LARGE_AUDIT = (AUDIT / 'large_data.py').read_text(encoding='utf-8')
PANE_HEALTH = (AUDIT / 'pane_health.py').read_text(encoding='utf-8')


# ──────────────────────────────────────────────────────────────────────
#  History navigation
# ──────────────────────────────────────────────────────────────────────
def test_user_navigation_creates_history_entries():
    """Without pushState, Back leaves the app entirely."""
    assert 'history.pushState' in WORKSTATIONS, (
        'user navigation must create a history entry')
    assert 'recordPaneInUrl' in WORKSTATIONS
    assert 'recordPaneInUrl' in APP_CORE, 'nav() must route through it'


def test_programmatic_restores_do_not_create_entries():
    """A workstation re-opening its last tab is not a user navigation.

    Pushing there would make Back step through states the user never chose.
    """
    body = WORKSTATIONS[WORKSTATIONS.index('window.recordPaneInUrl'):]
    body = body[:body.index('\n};')]
    assert 'userInitiated' in body
    assert 'history.replaceState' in body, (
        'programmatic updates must still use replaceState')


def test_duplicate_entries_are_collapsed():
    """nav() runs repeatedly for the same pane; stacking identical entries
    makes Back appear to do nothing several times in a row."""
    body = WORKSTATIONS[WORKSTATIONS.index('window.recordPaneInUrl'):]
    body = body[:body.index('\n};')]
    assert 'location.hash === target' in body


def test_history_driven_navigation_does_not_push():
    """Otherwise Back triggers hashchange -> nav() -> pushState, appending an
    entry for the state just left, and the user bounces forever."""
    assert '_navFromHistory' in APP_CORE
    handler = APP_CORE[APP_CORE.index("addEventListener('hashchange'"):]
    handler = handler[:handler.index('\n  });')]
    assert 'window._navFromHistory = true' in handler
    assert 'finally' in handler, 'the flag must be cleared even if nav() throws'


def test_tab_clicks_are_user_initiated():
    assert 'showWorkstationTab(host, pane, true)' in WORKSTATIONS, (
        'clicking a workstation tab is a user navigation')
    assert 'showWorkstationTab(pane, last, false)' in APP_CORE, (
        'restoring the last tab is not')


# ──────────────────────────────────────────────────────────────────────
#  The workstation-wipe recovery
# ──────────────────────────────────────────────────────────────────────
def test_workstation_recovers_from_a_later_host_render():
    """Batch 30 covered the first render only."""
    assert 'watchWorkstationHost' in WORKSTATIONS
    assert 'MutationObserver' in WORKSTATIONS
    body = WORKSTATIONS[WORKSTATIONS.index('window.watchWorkstationHost'):]
    body = body[:body.index('window.setWorkstationTab')]
    assert "querySelector(':scope > .ws-tabs')" in body, (
        'recovery must trigger on the tab strip disappearing')
    assert 'initWorkstation' in body


def test_recovery_cannot_break_a_render():
    body = WORKSTATIONS[WORKSTATIONS.index('window.watchWorkstationHost'):]
    body = body[:body.index('window.setWorkstationTab')]
    assert 'try {' in body and 'catch' in body


def test_recovery_is_installed_when_the_workstation_is_built():
    assert 'window.watchWorkstationHost(host);' in WORKSTATIONS


def test_pane_health_reloads_before_checking_workstations():
    """The pane walk builds every workstation as a side effect.

    Re-navigating to an already-built host takes the idempotent early-return
    path and never exercises build-then-wipe -- so the check passed even with
    the recovery removed. Verified: with a reload it reports 7 destroyed
    workstations, without it reports 0.
    """
    assert 'page.reload(' in PANE_HEALTH
    marker = 'Object.keys(window.WORKSTATIONS'
    assert marker in PANE_HEALTH
    assert PANE_HEALTH.index('page.reload(') < PANE_HEALTH.index(marker), (
        'the reload must happen before the workstation checks, or every host '
        'is already built and the build-then-wipe path is never exercised')


# ──────────────────────────────────────────────────────────────────────
#  Large data volumes
# ──────────────────────────────────────────────────────────────────────
def test_goals_can_reach_records_beyond_the_first_page():
    """"Narrow the filters" is not an escape route when all 250 match."""
    assert '_goalLimit' in GOALS
    assert 'gmLoadMoreGoals' in GOALS
    assert 'Load more' in GOALS
    assert 'limit=${_goalLimit}' in GOALS, (
        'the request must use the growable limit, not a hard-coded 100')


def test_changing_a_filter_resets_paging():
    """Otherwise narrowing after Load more keeps requesting the large page."""
    body = GOALS[GOALS.index('function gmFilterChange'):]
    body = body[:body.index('\n}')]
    assert '_goalLimit = GOAL_PAGE_SIZE' in body


def test_goals_still_states_the_total():
    """A Load more button alone does not tell the user how many are hidden."""
    assert 'Showing ${_goalList.length} of ${_goalTotal}' in GOALS


def test_large_data_audit_queries_what_the_ui_requests():
    """Querying with limit=1000 returns every row, so `len(rows) < total` is
    never true and the truncation check can never fire.

    Verified: /api/specs returns 100 of 250 by default, but
    /api/specs?limit=1000 returns all 250. The audit was blind for exactly
    that reason.
    """
    assert "('specs', '/api/specs', 'title', '/api/specs'," in LARGE_AUDIT


def test_large_data_audit_separates_disclosure_from_navigation():
    """A surviving "Load more" satisfied a combined check even with
    "Showing X of Y" deleted, so removing the disclosure produced no finding.
    """
    assert 'countDisclosed' in LARGE_AUDIT
    assert 'hasMoreControl' in LARGE_AUDIT


def test_large_data_audit_measures_settle_not_sleep():
    """A first version timed a fixed 2500ms wait against a 2500ms budget and
    reported 2556ms and 2521ms -- the sleep WAS the measurement."""
    assert 'stable' in LARGE_AUDIT
    assert 'node count unchanged' in LARGE_AUDIT or 'stable >= 3' in LARGE_AUDIT


def test_large_data_audit_cleans_up():
    """A run must not leave hundreds of records for the next one."""
    assert 'finally:' in LARGE_AUDIT
    assert '_cleanup(' in LARGE_AUDIT


def test_large_data_audit_reports_broken_seeding():
    """Zero accepted writes means the probe is broken, not that the pane is
    fast -- the failure mode the concurrency audit shipped with once."""
    assert 'BROKEN' in LARGE_AUDIT
    assert 'accepted == 0' in LARGE_AUDIT
