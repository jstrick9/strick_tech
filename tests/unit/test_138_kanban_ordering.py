"""Module review 5: Task Board (`kanban`).

Risk rank 5 of 68 (score 20), 844 lines. The 4 "stub markers" the risk
instrument counted were false positives -- the string `'todo'` as a column id.

THE DEFECT: A DRAG THAT SILENTLY REVERTED ON REFRESH
────────────────────────────────────────────────────
One ORDER BY carried two faults:

    ORDER BY CASE status ... END, sort_order ASC, id DESC

**1. The COALESCE was ignored.** The SELECT aliases
`COALESCE(sort_order, id) AS sort_order`, but ORDER BY binds to the RAW
column, so a task whose `sort_order` is NULL sorted as NULL -- first in SQLite
-- rather than as its id. That alias exists precisely to give un-dragged tasks
a stable position, and it never took effect.

**2. Ties broke the wrong way.** `id DESC` contradicts the frontend, which
sorts `sort_order` then `id` **ascending** (`28-kanban.js:152` and `:402`). Two
cards sharing a `sort_order` rendered in one order and reloaded in the
opposite one.

Measured against a live board: reordering three cards wrote the correct rows
(verified directly in SQLite) and the API returned them rearranged. **The write
was fine; the read reversed it.** A drag that appears to work and silently
reverts on refresh is worse than one that visibly fails -- the user does not
know their change was lost, and re-does it.

VERIFIED AS ALREADY CORRECT
───────────────────────────
The rest of the module is in good shape, and that is a result worth stating:

  * Full lifecycle works: create -> move -> patch -> delete.
  * `/api/kanban/move` rejects an unknown column (400), a missing task (404),
    and a non-integer id (400) -- all with the right status codes rather than
    200-with-ok:false.
  * `bulk_update` counts affected ROWS and reports `missing[]`, so a partially
    stale board can be reconciled.
  * The empty board carries a real first-run explanation (added in the
    first-run review) rather than four columns of "No tasks".

ONE COPY FIX
────────────
`/api/kanban/move` accepts `id`/`task_id` and `to_status`/`status`, but the
error named only one spelling of each -- so a caller sending the other pair was
told to supply fields it had already supplied.
"""

from __future__ import annotations

import re
import sqlite3
from pathlib import Path

REPO = Path(__file__).resolve().parent.parent.parent
TASKS = (REPO / 'backend' / 'routers' / 'tasks.py').read_text(encoding='utf-8')
JS = (REPO / 'frontend' / 'js' / '28-kanban.js').read_text(encoding='utf-8')


def _order_sql() -> str:
    """The ORDER BY clause of the board query, comments stripped.

    Comments are removed first because the fix documents the OLD clause
    verbatim so the next reader knows what changed -- asserting against raw
    source would match that explanation. Thirteenth occurrence of that trap in
    this review.
    """
    block = TASKS[TASKS.index('def kanban('):]
    block = block[:block.index('.fetchall()')]
    return re.sub(r'(?m)^\s*--.*$', '', block)


def _board_order(rows: list[tuple]) -> list[int]:
    """Run the router's OWN ORDER BY against an in-memory board.

    The clause is EXTRACTED from tasks.py rather than retyped here. My first
    version hardcoded the fixed SQL, so all six ordering tests passed against
    the reverted router -- they were testing SQLite's correctness, not the
    product's. Only the four source-level assertions caught the revert.

    Exercising real SQL rather than re-implementing the comparison in Python
    still matters: the bug WAS the difference between what the clause said and
    what everyone assumed it said.
    """
    clause = _order_sql()
    marker = 'ORDER BY'
    order_by = clause[clause.index(marker):].strip()
    # Keep only the ORDER BY itself, dropping the trailing SQL string quoting.
    order_by = order_by.split('"""')[0].strip().rstrip(',')

    con = sqlite3.connect(':memory:')
    con.execute('CREATE TABLE tasks (id INTEGER PRIMARY KEY, title TEXT, '
                'status TEXT, sort_order INTEGER)')
    con.executemany('INSERT INTO tasks (id,title,status,sort_order) VALUES (?,?,?,?)',
                    rows)
    out = [r[0] for r in con.execute(
        f"SELECT id FROM tasks WHERE status='todo' {order_by}")]
    con.close()
    return out


# ──────────────────────────────────────────────────────────────────────
#  Ordering
# ──────────────────────────────────────────────────────────────────────
def test_the_order_by_uses_the_coalesced_expression():
    """A bare `sort_order` ignores the COALESCE in the SELECT, so a NULL
    sorted first instead of as the task's id."""
    clause = _order_sql()
    assert 'COALESCE(sort_order, id) ASC' in clause


def test_ties_break_ascending_to_match_the_board():
    """`id DESC` contradicted 28-kanban.js, which sorts id ASCENDING."""
    clause = _order_sql()
    assert 'id DESC' not in clause, (
        'ties must break the same way the frontend breaks them')
    assert 'id ASC' in clause


def test_the_frontend_still_sorts_ascending():
    """If the board ever flips, the server must flip with it -- this test is
    the thing that would notice."""
    assert 'a.sort_order' in JS
    block = JS[JS.index('const ao = Number.isFinite'):][:400]
    assert 'ao - bo' in block, 'frontend sorts sort_order ascending'


def test_a_null_sort_order_falls_back_to_the_id():
    """Un-dragged tasks must hold a stable position, not jump to the top."""
    order = _board_order([
        (3, 'Gamma', 'todo', 1),
        (4, 'NullOrder', 'todo', None),
        (1, 'Alpha', 'todo', 5),
    ])
    assert order == [3, 4, 1], f'NULL did not sort as its id: {order}'


def test_a_tie_is_broken_by_id_ascending():
    order = _board_order([
        (1, 'Alpha', 'todo', 5),
        (2, 'Beta', 'todo', 5),
        (3, 'Gamma', 'todo', 1),
    ])
    assert order == [3, 1, 2], f'tie broke the wrong way: {order}'


def test_a_reorder_round_trips():
    """The exact scenario that failed: drag three cards into reverse order."""
    order = _board_order([
        (1, 'Alpha', 'todo', 3),
        (2, 'Beta', 'todo', 2),
        (3, 'Gamma', 'todo', 1),
    ])
    assert order == [3, 2, 1], f'reorder did not persist: {order}'


def test_the_fallback_query_orders_the_same_way():
    """A fallback that sorts differently makes the board silently rearrange
    itself whenever the richer SELECT fails."""
    block = TASKS[TASKS.index('def kanban('):]
    block = block[:block.index('cols = {')]
    fallback = block[block.index('except '):]
    assert 'COALESCE(sort_order, id) ASC' in fallback
    assert 'ORDER BY id DESC' not in fallback


# ──────────────────────────────────────────────────────────────────────
#  Guards on what was already right
# ──────────────────────────────────────────────────────────────────────
def test_move_rejects_an_unknown_column():
    assert "to not in ('todo', 'doing', 'blocked', 'done')" in TASKS


def test_move_reports_a_missing_task_as_404():
    """It used to answer {'ok': True} for a task that does not exist."""
    block = TASKS[TASKS.index("@router.post('/api/kanban/move')"):]
    assert 'status_code=404' in block


def test_move_rejects_a_non_integer_id():
    """`int(tid)` on a non-numeric id raised an unhandled ValueError -> 500."""
    block = TASKS[TASKS.index("@router.post('/api/kanban/move')"):]
    assert 'id must be an integer' in block


def test_bulk_update_counts_rows_not_statements():
    """It counted UPDATEs ISSUED, so ids that do not exist still reported
    success."""
    block = TASKS[TASKS.index('async def tasks_bulk_update'):]
    assert 'cur.rowcount' in block
    assert "'missing': missing" in block


def test_the_move_error_names_the_real_problem():
    """The endpoint accepts id/task_id and to_status/status, but the message
    named one spelling of each -- telling a caller to supply fields it had
    already supplied."""
    block = TASKS[TASKS.index("@router.post('/api/kanban/move')"):]
    assert 'id + to_status required' not in block
    assert 'destination column' in block
