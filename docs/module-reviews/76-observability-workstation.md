# Module 15 — Observability workstation

**Reviewed:** 2026-08-11
**Destination:** `observability`
**Panes:** `observability`, `agent-monitor`, `profiler`, `health`, `system`, `audit-log`, `replay`, `finops`, `dashboard`, `leaderboard`
**Risk score:** 21 (largest host; was 4/10 tabs reviewed)

First destination reviewed against the **ICM standard**: every surface must
state its basis, and a number a reader treats as a trust signal must not claim
more than the system actually established.

---

## Summary

Three defects, all the same shape — a confident number the system had not
earned. In a workstation whose entire purpose is telling you the truth about
the platform, that is the defect that matters most.

| # | Tab | Defect | Severity |
|---|---|---|---|
| 1 | audit-log | `verify` reported rows **present** as rows **verified** — a chain broken at seq 2 of 3 still said "verified: 3" | High |
| 2 | leaderboard | Ranked on the raw success ratio: **1 call at 100% outranked 50 calls at 94%**, painted bright green at #1 | High |
| 3 | replay | `status='done'` hardcoded — a run whose every agent node errored was recorded as done | Medium |

---

## 1. "Verified" meant "counted"

`verify_chain()` walks the hash chain and breaks at the first bad link, then
returned `'verified': len(rows)`. Reproduced live: three entries, tamper with
seq 2, verify:

```json
{"ok": false, "verified": 3, "broken_at": 2, "message": "⚠️ Chain broken at seq=2"}
```

The chain **correctly** detected the tamper and named the row — that part is
genuinely good work. But `verified: 3` is the number a reader takes as the
trust signal, and only one link had actually been checked.

Now counts links walked, and reports `total_checked` separately:

```json
{"ok": false, "verified": 1, "total_checked": 3, "broken_at": 2}
```

---

## 2. A single lucky call ranked above fifty

Reproduced against the running server — one `builder` call (success), fifty
`brain` calls (47 successes):

```
#1 builder   100.0%  from   1 calls
#2 brain      94.0%  from  50 calls
```

`ORDER BY success_rate DESC` treats 1/1 as better than 47/50, and the UI
painted it `var(--success)` bright green at the top of the board. A
leaderboard that rewards being untested is worse than no leaderboard.

**Fix:** rank on the **Wilson lower bound** (95%) — the standard remedy. The
bound rises towards the observed ratio as the sample grows, so an agent earns
its position by being tested:

```
1/1   -> 20.7      50 calls at 94% -> 83.8
```

After:

```
#1 brain     raw= 94.0%  score=83.8  n=50  low_conf=False
#2 builder   raw=100.0%  score=20.7  n= 1  low_conf=True
```

`success_rate` is still reported verbatim — it is the true observed ratio, and
hiding it would be its own dishonesty. It just no longer decides the order.
The response carries `ranking_basis` and `low_confidence`, and the UI colours
on the adjusted score, greys out low-confidence rows, and states the basis
above the table.

**Second door:** the same raw-ratio colouring existed in a second renderer in
the same file. Caught by the test, not by reading — see below.

---

## 3. A failed replay recorded as "done"

`_finish_run(run_id, 'done', ...)` was hardcoded at both completion sites.
Reproduced: a workflow run with no LLM provider produced

```
frame 4: node_output n2  err=No AI provider is configured…
frame 6: node_output n3  err=No AI provider is configured…
run status: done
```

The replay list exists so someone can audit a past run. Showing a green result
for a run where every agent node errored defeats it. This is the Module 14
workflow-status defect one surface over — the **14th "second door"**.

Status is now derived from the recorded frames via `_run_had_errors()`, read
from the frames rather than tracked in each loop, because two loops
maintaining their own counters is how they drift apart.

---

## Verified working (no change needed)

- **The audit hash chain genuinely detects tampering** and names the exact
  row. Tested by mutating a row directly in SQLite.
- **FinOps declares its cost basis** unprompted: *"Costs are estimated from a
  static rate card, not provider-reported billing. Cached-token and batch
  discounts are not modelled."* It also names `unpriced_models`. This is
  exactly the honesty standard the rest of the review has been imposing, and
  it was already here.
- `agent-monitor` live/anomalies/KPI snapshot, `system/info`, `profiler`,
  `health`, `dashboard` — all behave, all honest on empty state.

---

## Two mistakes of mine, recorded

**My first tests were blind.** Three of them grepped the source for
`ranking_score` / `frame_errors` rather than checking behaviour. The
revert-proof exposed it: breaking the sort and re-hardcoding `'done'` left all
20 tests **passing**, because the strings were still in the file. Rewritten as
behavioural tests that construct a fake leaderboard and a real frame table.
Re-proven: breaking each fix now fails a specific test.

**I polluted the shared test database.** 19 regression/system/UAT tests failed
after my changes. The cause was the audit row I had tampered with while
probing — still sitting in `/tmp/agentic-test.db`, so every chain-verification
test in the suite correctly reported a broken chain. Not a code defect;
cleared the probe rows and the suite returned to green. Worth recording
because a destructive probe against a shared DB looks exactly like a
regression.

---

## Cross-module impact

- `/api/agent-leaderboard` gains `ranking_score`, `sample_size`,
  `low_confidence`, `ranking_basis`; ordering changes. The only consumer is
  this pane.
- `/api/audit-log/verify` gains `total_checked`; `verified` now means what it
  says. Compliance export is unaffected.
- Replay rows written before this fix keep their old `done` status — the fix
  applies at write time, and rewriting history in an audit surface would be
  the wrong instinct.

---

## Tests

`tests/unit/test_151_module15_observability.py` — **21 tests.**

Revert-proof, each fix broken individually: `verified` back to `len(rows)`
→ 1 fail; sort back to the raw ratio → 1 fail; `'done'` re-hardcoded → 1 fail;
UI colour back to the raw ratio → 1 fail.

Full suite: **3,846 unit + 655 regression/system/uat = 4,501 passing, 0 failures.**

---

## Destination status

`observability` is now **10/10 tabs reviewed** — the first workstation
completed end to end rather than in fragments.
