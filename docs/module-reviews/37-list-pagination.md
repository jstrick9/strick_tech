# 37 — Lists that grow without bound

Autonomous hunt, batch 24. You chose "proper list UX on the growable panes".

## The finding

**28 GET endpoints returned every row they had** — no `limit`, no paging in the
UI. Measured by seeding 331 specs:

| | Before |
|---|---|
| `GET /api/specs` | **81 KB** in one response |
| Rows rendered into `innerHTML` | **all 331**, one pass |
| Cap / search / paging | none |
| Any indication the list could be incomplete | none |

It does not freeze at 331. It grows without bound with use, and there is no
point at which the product tells the user anything is being left out.

Also found: **`/api/agents?limit=N` was silently ignored** — the parameter
looked supported and did nothing.

## The bug this sits between

The opposite failure is already on record in `26-autonomous-hunt.md`: goals
were capped at **100 of 724** and the UI said nothing, so **624 were
unreachable**.

Unbounded and silently-capped are the *same mistake*: **the response does not
describe its own completeness.** That is what the fix targets, not the cap.

## The envelope

`backend/services/pagination.py`. Every paginated list now returns:

```json
{ "specs": [...], "count": 50, "total": 250,
  "limit": 50, "offset": 0, "has_more": true }
```

`total` and `has_more` are the part that matters — a client can always tell
whether it is looking at everything. `count` keeps the meaning it had when the
list was always complete, so existing callers are unaffected.

### `clamp_limit` clamps on BOTH sides

A one-sided `min(limit, MAX)` still lets a negative through, and **`LIMIT -1`
in SQLite means UNLIMITED**. That exact bug let `/api/audit?limit=-1` return
1398 rows against a cap of 2. Verified: `/api/specs?limit=-1` now returns the
default 100, not the table.

## The UI half

The API fix alone would have produced the *other* bug — a capped list with no
way to see the rest. The spec list now has:

- a **search box**, debounced 250ms, filtering **server-side** (so it searches
  all 250, not the 50 on screen);
- a footer that always states **"Showing 50 of 250"**;
- a **Load more** control that appends the next page.

Verified in Chromium against 250 seeded specs:

```
initial : 50 rows  | "Showing 50 of 250  [Load more]"
load+1  : 100 rows | "Showing 100 of 250 [Load more]"
search  : 10 rows  | "Showing 10 of 10 matching"
cleared : 50 rows  | "Showing 50 of 250  [Load more]"
```

Zero page errors. Search also gets a real empty state — *No specs match "…"* —
distinct from *No specs yet*, because those mean different things to a user.

`specLoadList` also gained error handling: it previously swallowed everything
in `catch(e) {}`, so a failed load left "Loading…" on screen forever.

## Scope

Applied to `/api/specs` and `/api/rag/pipelines` — the two DB-backed lists that
grow with user activity and had no cap. The remaining 26 are mostly fixed
catalogues (model registries, connector definitions, doc features) that do not
grow with use; `pagination.py` is there for them when they need it.

## Tests

`tests/unit/test_109_pagination.py` — 23 tests: clamps on both sides, the
envelope contract, real paging through the API (verifying offset returns
non-overlapping rows), server-side search narrowing `total`, and that the UI
still reports what it is not showing.

**Proven to catch the bug: with the routers and UI reverted, 6 of 23 fail.**
The 17 that still pass are pure-helper tests that correctly do not depend on
the routers.

## Regression status

| Suite | Result |
|---|---|
| `tests/unit` | **2992 passed, 2 skipped, 0 failed** |
| `regression` + `system` + `integration` + `uat` | **1044 passed, 17 skipped, 0 failed** |
| ruff · inline-handler · globals linters | pass |

Browser suite remains unstable in this sandbox (documented in
`36-honest-responses.md`, confirmed pre-existing); the spec-list UI was instead
verified directly in Chromium as shown above.
