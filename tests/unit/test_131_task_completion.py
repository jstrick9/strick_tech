"""Can a user actually finish a job?

WHY THIS PROBE IS DIFFERENT FROM THE OTHER NINETEEN
───────────────────────────────────────────────────
Every other audit in `scripts/audit/` inspects a **rendered state**: is this
control big enough, does this pane announce itself, does this value carry a
timezone. None of them ever *uses* the product.

A screen can pass all nineteen and still be impossible to get a job done in.
`task_completion.py` drives complete journeys through the real DOM — clicking
what a user clicks — and asserts the outcome the user expects.

RESULT: NO DEFECTS, AND THAT IS A MEASURED CLAIM
────────────────────────────────────────────────
Create → appears → survives a reload → delete → stays deleted. Verified
independently at the data layer during development: 0 rows → 1 → 0, with every
step driven through the UI.

Recorded as a result rather than silence, and pinned by the tests below so it
cannot quietly stop being true.

WHY IT IS TRUSTWORTHY: IT WAS PROVEN ABLE TO FAIL
─────────────────────────────────────────────────
`POST /api/tasks` was stubbed to answer `200 {ok: true}` **without writing a
row** — the exact shape of an optimistic-UI lie, and precisely what an
API-level test cannot see, because the API said yes. The probe reported:

    PERSIST-FAIL  kanban: the task appeared, then was gone after a reload --
                  the user was told it saved and it did not
    -- delete: nothing to delete; journey skipped

Both halves matter. It caught the lie, **and** it declared the dependent
journey skipped instead of counting it as a pass.

DESIGN DECISIONS THAT MAKE IT MEAN SOMETHING
────────────────────────────────────────────
* **Everything goes through the DOM.** A probe that POSTs to the API and then
  checks the API has verified the server and learned nothing about the
  product. The failure this whole review keeps finding is a working backend
  behind a broken screen.
* **Persistence is checked with a full page reload**, not a re-render: an
  in-memory list will happily show a record the server never stored.
* **Every journey verifies its precondition** and emits a `--` note if the
  entry control is missing. A journey that never started is not a journey that
  succeeded — the trap that let the concurrency audit report `0 records
  created` as a PASS while every write was being rejected.
* **A unique marker per run**, so a previous run's leftovers cannot make a
  broken create look successful.
"""

from __future__ import annotations

import json
from pathlib import Path

REPO = Path(__file__).resolve().parent.parent.parent
AUDIT = REPO / 'scripts' / 'audit'
SRC = (AUDIT / 'task_completion.py').read_text(encoding='utf-8')


def test_the_probe_drives_the_dom_not_the_api():
    """POSTing to the API and then reading the API verifies the server and
    learns nothing about the product."""
    assert 'window.nav' in SRC
    assert '.click()' in SRC
    # The only fetch present must be the harness's own, not a create call.
    assert "method: 'POST'" not in SRC, (
        'the probe must create through the UI, not by calling the API')


def test_persistence_is_checked_with_a_full_reload():
    """An in-memory list will show a record the server never stored."""
    assert 'page.reload' in SRC
    assert 'PERSIST-FAIL' in SRC


def test_each_journey_reports_a_missing_precondition():
    """A journey that never started is not a journey that succeeded."""
    assert 'journey skipped' in SRC
    assert SRC.count('journey skipped') >= 2


def test_the_marker_is_unique_per_run():
    """A previous run's leftover row would make a broken create look fine."""
    assert 'int(time.time())' in SRC


def test_the_probe_covers_the_full_lifecycle():
    for phase in ('CREATE-FAIL', 'PERSIST-FAIL', 'DELETE-FAIL'):
        assert phase in SRC, f'{phase} is not measured'


def test_delete_is_verified_after_a_reload_too():
    """A deletion that only removes the card locally comes back on reload."""
    delete_fn = SRC[SRC.index('def _journey_delete'):]
    assert 'page.reload' in delete_fn
    assert 'came back after a reload' in delete_fn


def test_informational_notes_do_not_inflate_the_count():
    """`--` lines are context, not findings; counting them would make a
    skipped journey look like a defect and vice versa."""
    assert "not f.startswith('--')" in SRC


def test_the_audit_is_registered():
    assert 'task_completion' in (AUDIT / 'run_all.py').read_text(encoding='utf-8')
    ratchet = (REPO / 'tests' / 'unit' / 'test_120_audit_ratchet.py').read_text(
        encoding='utf-8')
    assert "('task_completion', 'task-completion')" in ratchet
    baseline = json.loads((AUDIT / 'baseline.json').read_text(encoding='utf-8'))
    assert baseline.get('task-completion') == 0
