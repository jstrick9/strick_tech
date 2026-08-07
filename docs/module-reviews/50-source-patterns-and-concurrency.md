# 50 — Clearing source-patterns, and the concurrency seam

**Status:** shipped
**Batch:** 37
**Scope:** 14 frontend modules, `backend/services/idempotency.py` (new),
`backend/app.py`, `frontend/js/00-csrf.js`, `scripts/audit/concurrency.py`
(new), `scripts/audit/source_patterns.py`, `tests/unit/test_121_idempotency.py`

First use of the infrastructure from batch 36: drive a baseline to zero, then
open a seam that had never been examined.

---

## Part 1 — `source-patterns: 17 → 0`

### Six unguarded array accesses, confirmed as live crashes

A 200 response with an unexpected *shape* passes an `if (!r.ok)` check and
then throws when an array method is called on it. Verified in a browser by
returning `{"error":"unexpected shape"}` with status 200:

```
integrations   'Error loading integrations: cats.map is not a function'
webhooks       'whs.map is not a function'
testgen        'fws.map is not a function'
```

A raw JavaScript `TypeError` rendered where the explanation belongs. Fixed by
coercing at the destructuring point — once per response, so every later use is
covered rather than each call site needing its own guard.

Widening the detector afterwards found **five more**, including a confirmed
live crash on Workspaces (`ws.map is not a function`) and latent ones in swarm
history and the shortcuts list.

### Eleven raw-error headlines

`Failed to load profiler: ${e.message}`, `Styles load failed: HTTP 500`, and
similar — routed through `humanError()` / `httpError()` so the sentence
explains and the technical detail is demoted to trailing parentheses.

### Three corrections to the detector itself

The audit was wrong before the code was, in both directions:

1. **Line numbers were all wrong.** Comments were *deleted* before scanning,
   so every reported line was offset by however many comments preceded it. It
   sent me to the wrong line in all ten files. Comments are now blanked
   in place, preserving line positions.

2. **It missed a whole assignment form.** Only
   `const [a,b] = await Promise.all(...)` was recognised, so
   `const styles = await sR.json()` — which crashed the image generator
   exactly like the ones it did catch — was invisible.

3. **It went blind after a fix.** Reverting the Workspaces fix produced
   **no finding at all**: the crash had moved one alias away from the
   response (`const wsRaw = await r.json(); const ws = wsRaw;`) and provenance
   matching only looked at names syntactically adjacent to `await`. Caught
   only because reverting a real fix and re-running is part of the process.
   It now follows one level of aliasing.

It also produced five **false positives** — `.length` guards sitting between
the assignment and the use, which the detector could not see because it only
searched up to the assignment. Fixed rather than the code being padded with
unnecessary guards.

Proven both ways: **0 on a clean tree, 1 when a real bug is reintroduced.**

---

## Part 2 — Concurrency: the first never-examined seam

### The finding

`scripts/audit/concurrency.py` fires five identical POSTs concurrently at each
creating endpoint:

```
DUPE   specs      5 concurrent identical POSTs (5 accepted) created 5 records
DUPE   goals      5 concurrent identical POSTs (5 accepted) created 5 records
DUPE   webhooks   5 concurrent identical POSTs (5 accepted) created 5 records
       …          Idempotency-Key ignored (5 records for one key)
```

Every one of those is ordinary: a double-click on "Create", a retry after a
flaky connection, a request replayed when a mobile tab wakes, the same action
fired from two tabs. The user asked for one thing and got five.

This was flagged early in the review and deferred as *"lower priority
(client-side double-submit guard covers the common case)"*. A client-side
guard covers none of those four cases.

### The fix

`backend/services/idempotency.py` implements the Stripe/IETF
`Idempotency-Key` contract: first request executes and its response is
recorded; repeats replay it with `Idempotency-Replayed: true`; a request
already in flight for that key gets **409** rather than being allowed to race.

Wired into the existing security middleware, so all ~390 write endpoints are
covered by construction rather than one at a time.

`frontend/js/00-csrf.js` derives a key from method + path + body inside a
10-second window, so real clicks are protected and not merely protectable.

**Deliberate limits**, each with a reason:

| Limit | Why |
|---|---|
| Only 2xx is recorded | Replaying a failure would block a legitimate retry |
| No key ⇒ no change | Two genuinely-intended identical records must stay possible |
| 10s client window | Long enough for a double-click and a retry; short enough that repeating an action deliberately still works |
| In-process store | Local-first single instance; a multi-node deployment needs shared storage, and the code says so |

### Verified in a real browser

| Scenario | Result |
|---|---|
| 5 concurrent creates from the page | **1 record**, 4 marked `Idempotency-Replayed: true`, all 200 |
| 3 creates with **different** bodies | **3 records** — dedupe does not swallow distinct writes |
| Same body, 11 s apart | **2 records** — deliberate repeats still work |

---

## Two audit bugs that would have hidden the finding

Both are the same failure mode: **an audit that measures nothing looks exactly
like an audit that finds nothing.**

1. **Its first run reported `0 records created` on every endpoint — as a
   PASS.** Every write had been rejected with 403 for a missing CSRF token.
   The probe now authenticates, and reports `BROKEN` rather than `ok` when no
   write is accepted.

2. **A fixed idempotency key made the second run pass for the wrong reason.**
   The server remembered the key from the previous run, replayed that
   response, created nothing, and looked green. Each run now uses a fresh key.

The audit also now measures *both* paths — unkeyed (duplicates expected, by
design) and keyed (must dedupe) — and counts only the keyed case, so it cannot
be satisfied by the API simply refusing work.

---

## Tests

`tests/unit/test_121_idempotency.py` — 17 tests. Proven to fail when reverted:

| Reverted | Result |
|---|---|
| Failures become replayable | 1 failed |
| Frontend stops sending a key | 4 failed |
| Middleware stops claiming keys | audit 0 → 3 |

`test_store_is_bounded` **caught a real off-by-one**: pruning ran before the
new entry was inserted, leaving the store one over its ceiling.

`test_audit_authenticates` initially **passed against broken code** — removing
the CSRF header from `_post()` still left the string present in the DELETE
cleanup path. Rescoped to assert per-function; now fails correctly.

---

## Verification

- **Full suite: 3,229 unit + 655 regression/system/uat = 3,884 passing**,
  0 failures.
- **All eight audits at 0**, including the new concurrency audit.
- Ratchet + idempotency suites: 28 passed.
- `ruff`, `lint_inline_handlers`, `lint_globals` clean. Two genuine `B023`
  late-binding bugs in the audit's own lambdas were fixed, not suppressed.

## Seam register

`concurrency` moves from **never examined** to **covered**. Twelve seams
remain unexamined; screen-reader announcement and slow/flaky networks are next
by expected value.
