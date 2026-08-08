# 52 — Browser history, and realistic data volumes

**Status:** shipped
**Batch:** 39
**Scope:** `scripts/audit/history_navigation.py` (new),
`scripts/audit/large_data.py` (new), `scripts/audit/pane_health.py`,
`frontend/js/00-workstations.js`, `frontend/js/01-app-core.js`,
`frontend/js/49-goals.js`, `tests/unit/test_123_history_and_large_data.py`,
`tests/unit/test_101_list_truncation.py` (updated)

Two more seams from the register. Both had never been examined, and both
contained real bugs.

---

## Note on the session

The sandbox rolled the local clone back to batch 37 mid-session. Batch 38 was
already on the remote, and every file was verified **byte-identical** before
resetting, so nothing was lost. Recorded because the recovery step — check the
remote first, diff before discarding — is what made it safe.

---

## Seam 1 — Browser Back exited the application

Every navigation used `history.replaceState()`, never `pushState`. Measured:

```
history.length after 4 navigations:  unchanged (0 entries created)
pressing Back:                       about:blank, window.nav undefined
```

The whole session gone. Back is a reflex action, so this is the worst possible
outcome for a muscle-memory keystroke.

A `hashchange` handler that routes correctly **already existed** in
`01-app-core.js`. It simply never fired, because `replaceState` does not
produce a hashchange.

### The fix

A single owner, `recordPaneInUrl(pane, userInitiated)`:

- **User navigation** (sidebar click, workstation tab click) → `pushState`
- **Programmatic restore** (a workstation re-opening its last tab) →
  `replaceState`, so Back does not step through states the user never chose
- **Identical consecutive entries collapsed** — `nav()` runs repeatedly for
  the same pane, and stacking duplicates makes Back appear to do nothing
  several times in a row

`_navFromHistory` prevents the bounce trap: without it, Back triggers
`hashchange` → `nav()` → `pushState`, appending an entry for the state just
left, and the user can never escape.

Verified live:

| | |
|---|---|
| 4 navigations | history 3 → 7 |
| Back ×3 | `#/goals` → `#/specs` → `#/kanban`, in-app throughout |
| Forward | `#/specs` |
| Pane content after Back | renders (153 chars) |
| 4× nav to the current pane | history unchanged |
| Workstation tab (`#/goals`) | restores inside its Supervisor host, 421 chars |

---

## Seam 2 — A host re-render destroyed 7 workstations

Batch 30 fixed the **first** render: `nav()` now awaits an async host renderer
before building the tab strip. But a host can re-render *later*.

Measured with 250 seeded goals:

```
t~1000ms  pane-goals visible, 5,976 chars
t~2500ms  pane-goals visible, 5,976 chars
t~5000ms  pane-goals GONE
```

`renderSupervisor()` ran again ~3 s after `nav()` and replaced
`#pane-supervisor`'s innerHTML, destroying the Goals tab that had already
rendered. The user watched the list appear and then vanish.

**Fixed** with `watchWorkstationHost()`: a MutationObserver on the host
rebuilds the workstation if its tab strip disappears. `initWorkstation()` is
already idempotent and DOM-driven, so re-running it is safe.

Removing the fix and re-auditing reported **7 destroyed workstations** — far
broader than the single case that exposed it.

---

## Seam 2b — Goals capped at 100 of 250 with no way out

It disclosed the count but offered only *"narrow the filters to find them"* —
useless advice when all 250 match the current filters. 150 records were
unreachable through the UI.

Added a growable limit and a **Load more** control, with the page size reset
on any filter change. Verified: `Showing 100 of 250` → `200 of 250` → all 250,
with the notice disappearing once nothing is hidden.

---

## Five audit bugs found before the numbers could be trusted

The pattern from the register held again: **when a probe disagrees with the
app, suspect the probe first.**

1. **Timed a fixed sleep against a budget.** A 2500 ms `settle` measured
   against a 2500 ms budget reported 2556 ms and 2521 ms — the sleep *was* the
   measurement. Both would have been filed as performance findings. Now waits
   for the DOM node count to stabilise.

2. **Queried the API with a higher limit than the UI uses.**
   `?limit=1000` returns all 250 rows, so `len(rows) < total` was never true
   and the truncation check could never fire. `/api/specs` returns 100 of 250
   by default.

3. **Conflated two facts in one check.** "Showing X of Y" and "Load more" were
   tested together, so deleting the disclosure still passed because the button
   survived. Split into `countDisclosed` (do you know how many are missing?)
   and `hasMoreControl` (can you reach them?).

4. **Checked workstations after the pane walk.** The walk visits all 68 panes,
   which builds every workstation as a side effect; re-navigating then takes
   the idempotent early-return path and never exercises build-then-wipe. With
   a reload first: **7 destroyed**. Without: **0**.

5. **Reported findings from an empty workspace.** The audit now seeds 250
   records and reports `BROKEN` rather than `ok` when no write is accepted —
   the failure mode the concurrency audit shipped with once.

---

## A pre-existing test updated, not deleted

`test_101_list_truncation.py` pinned the literal string `"723 more are
hidden"`. The wording changed to `"723 more not shown"` because *hidden*
implied the records were unreachable — true before, not now.

The requirement is unchanged, so the assertion was relaxed to `/723 more/`
**and strengthened** with a new one: the list must also offer a way to reach
the remaining records. The test is stricter than it was.

---

## Tests

`tests/unit/test_123_history_and_large_data.py` — 17 tests, each fix proven to
fail when reverted:

| Reverted | Result |
|---|---|
| `pushState` → `replaceState` | 1 failed |
| Host watcher removed | 1 failed, and `pane_health` 0 → 7 |
| Load more removed | 1 failed, and `large_data` 0 → 1 |

Three of my own assertions were wrong on first run — brace-matching that
sliced past a nested arrow function, and a marker string that did not exist.
Fixed rather than worked around.

---

## Verification

- **Full suite: 3,258 unit + 655 regression/system/uat = 3,913 passing**,
  0 failures, 2 skips.
- **All twelve audits at 0.**
- `ruff`, `lint_inline_handlers`, `lint_globals` clean.

**A skip is not a pass:** a rollback wiped `jsdom` mid-run and skips jumped to
**151**. Reinstalled and re-ran rather than accepting the green result — which
then surfaced the genuine `test_101` failure above.

## Seam register

`browser back/forward` and `large data volumes` move to **covered**. Eight
seams remain; session expiry and offline/reconnect are next by expected value.
