# 66 — Module review 5: Task Board (`kanban`)

**Risk rank 5 of 68** (score 20), 844 lines. The 4 "stub markers" the risk
instrument counted were false positives — the string `'todo'` used as a column
id.

---

## The defect: a drag that silently reverted on refresh

One `ORDER BY` carried two faults:

```sql
ORDER BY CASE status ... END, sort_order ASC, id DESC
```

**1. The COALESCE was ignored.** The SELECT aliases
`COALESCE(sort_order, id) AS sort_order`, but `ORDER BY` binds to the **raw
column** — so a task with a NULL `sort_order` sorted as NULL (first in SQLite)
rather than as its id. That alias exists precisely to give un-dragged tasks a
stable position, and it never took effect.

**2. Ties broke the wrong way.** `id DESC` contradicts the frontend, which
sorts `sort_order` then `id` **ascending** (`28-kanban.js:152`, `:402`). Two
cards sharing a `sort_order` rendered in one order and reloaded in the other.

### Measured against a live board

| Step | Result |
|---|---|
| Drag to Gamma, Beta, Alpha | rows written correctly — verified in SQLite |
| Read back via `/api/kanban` | **Gamma, edge-probe, Beta, Alpha** |

**The write was fine; the read reversed it.** A drag that appears to work and
silently reverts on refresh is worse than one that visibly fails — the user
does not know the change was lost, so they do it again.

After the fix: reorder round-trips exactly; a NULL `sort_order` sorts as its
id; a tie at `sort_order 5` breaks Alpha-before-Beta, matching the board.

---

## Verified as already correct

The rest of the module is in good shape:

- Full lifecycle: create → move → patch → delete.
- `/api/kanban/move` rejects an unknown column (**400**), a missing task
  (**404**) and a non-integer id (**400**) — real status codes, not
  200-with-`ok:false`.
- `bulk_update` counts affected **rows** and returns `missing[]`.
- The empty board carries a real first-run explanation.

## One copy fix

`/api/kanban/move` accepts `id`/`task_id` and `to_status`/`status`, but the
error named only one spelling of each — telling a caller to supply fields it
had already supplied.

---

## Mistakes of mine

**Six of my own tests proved nothing.** `_board_order()` hardcoded the *fixed*
SQL, so those tests passed against the reverted router — they were testing
SQLite's correctness, not the product's. Only the four source-level assertions
caught the revert. The helper now **extracts the clause from `tasks.py`**, and
the revert-proof went 4 → **6** failures.

**A pre-existing test broke on window size, not behaviour.**
`test_move_checks_rowcount` sliced a fixed 1,200 characters from the handler;
the longer error message pushed `cur.rowcount` past it. Behaviour was
unchanged. Updated to slice to the next route so it survives future copy edits.

---

## Cross-module impact

- `tasks.py` also backs the Dashboard's task KPIs and the Goals pane's linked
  tasks. Ordering is board-only, but `bulk_update` is shared.
- The Kanban pane is an absorbed workstation tab, so the fix is visible
  wherever the board is embedded.

## Verification

| Check | Result |
|---|---|
| Reorder round-trip | reversed → **exact** |
| NULL `sort_order` | sorted first → sorts as its id |
| Tie-break | `id DESC` → `id ASC`, matching the frontend |
| Revert the fix | **6 of 12** tests fail |
| Full suite | 3,468 unit (2 skipped) + 655 (10 skipped), 0 failures |
