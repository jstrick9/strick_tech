# Module Review 05 — Tasks (Kanban)

**Reviewed:** 2026-08-03 · **Commit:** `c19c921` · **Sidebar position:** Tasks (ESSENTIALS)

**Scope:** the 8 task/Kanban endpoints (previously inline in `backend/app.py`, now
`backend/routers/tasks.py`) and `frontend/js/28-kanban.js` (616 lines).

**Verification:** every finding reproduced against a running server, and the XSS
reproduced in a real DOM before and after the fix.

---

## Findings

### 🔴 1. Stored XSS on the Kanban board

`task.agent` is fully user-controlled — `POST /api/tasks` accepts any string for it. An
unrecognised agent fell through to `label: task.agent`, and that label was interpolated
into **both** the `title=""` attribute and the card body **without escaping**:

```js
<span class="kanban-card-agent" title="${agent.label}">${agent.icon} ${agent.label}</span>
```

The task title and description immediately beside it *were* correctly escaped — so this
was an isolated gap, not a missing convention.

I created a task with `agent='"><img src=x onerror=alert(1)>'`, confirmed the payload
persisted in the database, then rendered the shipped `kanbanRenderCard` in jsdom:

```
injected <img onerror> elements: 2
*** STORED XSS CONFIRMED — payload became live DOM ***
```

Any user opening the Tasks board would execute it. **Fixed** — attribute via
`kanbanEscapeAttr`, body via `kanbanEscapeHtml`, and the icon escaped on the
unknown-agent branch too.

### 🟠 2. Four endpoints reported success for tasks that don't exist

`PATCH`, `DELETE` and `/api/kanban/move` all returned **HTTP 200 with `ok: true`** for a
nonexistent id. `bulk_update` counted UPDATE statements *issued* rather than rows changed,
so a payload of pure garbage returned `{"ok": true, "updated": 2}`.

This wasn't cosmetic: the board uses `response.ok` to decide whether a drag was persisted.
Moving a card that had been deleted in another tab showed **"Task moved"**, left it in the
new column, and silently snapped back on reload.

All four now check `rowcount` and return 404; `bulk_update` returns a `missing` list so a
stale board can be reconciled. `kanban/move` no longer 500s on a non-numeric id, and
validation failures return 400.

Also wrapped in `try/finally` — an exception between `execute()` and `close()` leaked the
SQLite connection.

### 🟠 3. The UI never rolled back optimistic updates

All four mutation paths updated local state and re-rendered *before* the request, then did
nothing useful on failure:

| Action | Old behaviour on failure |
|---|---|
| Drag & drop | `console.warn` only — card stayed in the wrong column |
| Edit | Error toast, but edited values stayed on screen |
| Delete | **Never inspected the response** — a 500 still removed the card and said "Task deleted" |
| Create | Fabricated a local task with `id: Date.now()`, toasted "Task created (local)" |

The create path had a second bug: it trusted `response.ok` alone, but `POST /api/tasks`
returns 200 with `{"ok": false}` for a rejected payload — so a rejected task was added to
the board with `id: undefined`, and every later edit or delete hit `/api/tasks/undefined`.

All four now revert on failure, surface the real reason, and resync from the server on 404.

### 🟡 4. Card ordering was never persisted

`sort_order` exists in the schema, is returned by the API, and is accepted by
`bulk_update` — but **no UI code ever read or wrote it**. Cards rendered in whatever order
the API returned, and dropping a card inside its own column was explicitly ignored
(*"Task already in this column"*).

The board now sorts by `sort_order` (falling back to `id`, preserving existing behaviour
for never-reordered tasks), computes the drop index from pointer position against card
midpoints, and persists via the existing `bulk_update` endpoint. Verified a reorder
survives a reload.

### 🟡 5. Endpoints extracted out of `app.py`

The 8 task endpoints lived inline in `app.py` — the structural issue flagged in the
initial repo review. Moved to `backend/routers/tasks.py`, matching every other feature.
**app.py: 988 → 732 lines.**

The move surfaced a latent bug worth noting: `from .routers.websocket import` was correct
in `app.py` but wrong one level deeper, and **the surrounding broad `except` swallowed the
`ModuleNotFoundError`** — task creation 500'd with no clear cause until I traced it through
the server log. A concrete example of the over-broad exception handling I flagged in the
initial review.

---

## Verified working (no change needed)

- Board projection, filtering by priority, task counts, column grouping
- Create/edit modals, `gmDanger` confirm (Tauri-safe), toast system
- Title and description escaping
- Drag-and-drop mechanics (dataTransfer, drop zones, visual feedback)

---

## Cross-module impact

| Module | Impact |
|---|---|
| **Chat** | `/goal` creates tasks — those now get honest status codes. |
| **Supervisor / Goals** | Share the `tasks` table; the rowcount fixes apply to any caller. |
| **app.py** | 256 lines lighter; one fewer feature mixed into the entry point. |
| **Any API consumer** | PATCH/DELETE/move now 404 instead of always 200 — breaking only for code that relied on the lie. |

---

## Tests added

- `tests/unit/test_54_tasks_module_review.py` — **29 contracts** covering the router
  extraction, rowcount checks, status codes, connection handling, escaping, rollback
  behaviour and ordering persistence.
- `frontend/tests/kanban-card-escaping.test.js` — **6 jsdom tests** running the *shipped*
  `kanbanRenderCard` against a real DOM. **Verified to fail 4/6 against the pre-fix code**,
  so they genuinely guard the XSS rather than just passing.

Three existing contracts were updated: two regression tests pinned `bulk_update`'s
rejection to HTTP 200 (the behaviour they guard — `ok: False` rather than a silent
`updated: 0` — is unchanged and still asserted), and one unit test expected a PATCH
containing *only* an invalid status to return 200; with no valid fields left to apply that
is now 400, and I extended it to also prove a bad status is still ignored when sent
alongside a valid field.

**Suite:** 2831 backend passed / 12 skipped / **0 failed** · 75 vitest passed · ruff clean.

---

## Recommended follow-ups

1. **Audit the remaining `escHtml`-free interpolations platform-wide.** This XSS existed
   because one field was missed while its neighbours were escaped. With 685 `innerHTML`
   assignments across the frontend, a lint rule banning raw `${}` inside `innerHTML`
   templates would be far more reliable than review.
2. **The broad `except (KeyError, TypeError, ...)` tuples hide real bugs** — this module
   produced a concrete example (a swallowed `ModuleNotFoundError` presenting as a 500).
   Still the highest-value cleanup outstanding from the initial review.
3. **No task filtering by agent or layer in the UI**, though the API supports both. Worth
   adding alongside the existing priority filter.
4. **`bulk_update` is capped at 200 rows** with no pagination signal — fine today, but a
   large board reorder would silently truncate.
