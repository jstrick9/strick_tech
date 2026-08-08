# 56 — Timezones and dates

**Seam:** *timezones & dates*
**Audit:** `scripts/audit/timezones.py` · **key:** `timezone-correctness` ·
**baseline:** 2 → **0**
**Tests:** `tests/unit/test_127_timezones.py` (16) — 4 fail on revert, 1 pinned
to the gate bug specifically.

---

## The defect

SQLite's `CURRENT_TIMESTAMP` — used as a column default **141 times** in this
codebase — stores UTC as `YYYY-MM-DD HH:MM:SS`, with **no timezone
designator**. A handful of routers also call naive `datetime.now().isoformat()`.

`2026-08-08 14:42:08` is not a moment in time. It is a moment in an unstated
place, and every consumer has to guess. The browser's guess is the damaging
one:

```js
new Date('2026-08-08 14:42:08')   // interpreted as LOCAL time
```

A UTC timestamp written by the server is rendered **unshifted** in the user's
zone. Nothing throws. The clock is simply wrong by the size of the offset —
and wrong in the direction that produces the most confusing possible output.
Measured live with Chromium in Australia/Eucla, a task created *that second*
displayed as:

> **in 3 minutes**

An event in the future that had already happened.

### Why UTC+8:45

A whole-hour zone makes an off-by-one-hour bug and a correct rendering look
identical whenever the server clock sits near the hour. A **45-minute** offset
cannot be produced by any rounding error, so the measurement is unambiguous.

---

## The fix

`backend/services/timestamps.py`, applied inside the middleware's **existing**
JSON buffering pass.

The alternatives are worse. Rewriting 141 schema defaults changes stored data
and every query that compares against it, with no way to stop the 142nd being
written. Editing each router's serialisation is ~60 files and misses new ones.
Normalising on the way out covers every existing endpoint, every endpoint added
later, and cannot corrupt anything at rest because it never writes.

It shares the existing pass rather than adding a second middleware, because a
second one would buffer the body again — with a second chance to break SSE,
the trap already recorded in `_restatus_refused_write`.

**Scope, deliberately narrow:**

- Only exact `YYYY-MM-DD[ T]HH:MM:SS[.ffffff]` — already ISO-8601 with the
  designator missing. Anchored at both ends, so prose containing a date is not
  rewritten.
- **Date-only values are left alone.** `2026-08-08` is usually a calendar date
  (a due date, a birthday); pinning it to a UTC instant shifts it across
  midnight for half the world, turning a correct date into a wrong one.
- Only keys that name a moment in time — `timeout` and `date_format` do not
  match.
- Values already carrying `Z` or an offset are untouched.

---

## The gate bug found while fixing it

The buffering pass was gated to `POST/PUT/PATCH/DELETE`, which is **correct**
for its original job. Timestamps are returned almost entirely by **GET**, so
with the gate unchanged the fix was live and did nothing — `/api/tasks` still
returned `2026-08-08 14:42:08`. Verified before and after.

Widening the gate required care: a GET reporting `ok: false` is *describing
state*, not refusing work, so restatusing stays limited to mutating methods via
an explicit `allow_restatus` flag.

---

## A test of mine that proved nothing

Recorded prominently because the revert-proof caught it.

`test_reads_go_through_the_normaliser` originally read whatever `/api/tasks`
happened to contain. The unit-test database is empty, so the list was empty,
the naive-value list was empty, and the test **passed against the reverted
gate**.

It now creates its own row and asserts that it actually measured something.
This is the **eighth** time a test that could not fail has appeared in this
review — a test that cannot fail is worse than no test, because it is counted
as coverage.

---

## A probe false positive, caught before it was reported

The relative-label check searched all body text for `in \d+ minutes` and
matched the **onboarding modal's marketing copy** ("…set up in 3 minutes").
Now scoped to elements that actually carry a timestamp.

This is the identical trap the offline audit hit with
`Private • Ollama • Offline`, one seam earlier. It fails in both directions:
prose can create a false finding, and prose can equally satisfy a presence
check and hide a real absence.

---

## Verification

| Check | Result |
|---|---|
| `scripts/audit/timezones.py` | 2 → **0** (15 fields inspected, all now aware) |
| Disable the normaliser | audit reports `AMBIGUOUS-API` again |
| Revert the normaliser | **4 of 16** tests fail |
| Revert *only* the method gate | `test_reads_go_through_the_normaliser` fails |
| Full suite | 3,308 unit (2 skipped) + 655 (10 skipped), 0 failures |
