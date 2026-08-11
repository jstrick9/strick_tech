# 85 — Workspaces workstation: Control Tower and the pull target

**Destination:** `workspaces`
**Tabs:** `workspaces` (host), `collabedit`, `control` — 3/3 covered
**Frontend:** `frontend/js/30-workspaces.js`, `32-collaboration.js`, `31-control-tower.js`
**Backend:** `backend/routers/control_tower.py`, `backend/routers/github.py`, `backend/routers/workspaces.py`
**Tests:** `tests/unit/test_160_module24_workspaces_control.py` (28)
**Status:** reviewed, fixed, verified live

Destination 12 of 20.

---

## The headline

**The Control Tower's budget caps were never enforced.** This is the most
consequential class of defect this review can find: a guardrail the UI presents
as configured, that nothing reads.

The platform had **two unrelated budget stores**:

| Table | Written by | Read by |
|---|---|---|
| `budget_rules` | `/api/control/budget-rules` (the Control Tower pane) | **nothing** |
| `budget_caps` | FinOps | `finops.check_budget_before_spend()`, called before every LLM call |

Confirmed by grep across the whole backend: `budget_rules` has **zero readers**
outside its own router. Verified end to end:

```
POST /api/control/budget-rules {"max_cost": 0.01, "action": "stop"}
  -> {"ok": true, "id": 3}          and it appears in the pane

check_budget_before_spend(agent_id='brain')
  -> {'allowed': True}              nothing was capped
```

A user who opened the Control Tower — the pane whose entire stated purpose is
*"live agent traces · kill switch · budget"* — set a hard stop, saw it listed,
and believed their spending was capped. It was not. Given the platform runs
autonomous loops that call paid models on a timer, this is the guardrail most
likely to be relied on and least likely to be tested by the user before they
need it.

**Fix:** rules now write through to `budget_caps`, so the UI drives the
mechanism that already exists rather than a parallel one. That is deliberately
the smaller change: the enforcement logic, its period windows and its fail-open
behaviour are already reviewed and tested, and adding a second enforcement path
would just recreate the drift. `action: 'stop'` maps to `on_breach: 'pause'`
(a real block); `'warn'`/`'notify'` map to `'alert'` (notify-only), matching
what those words promise. Update and delete keep the mirror in step.

Verified after the fix, same steps:

```
check_budget_before_spend(agent_id='brain')
  -> {'allowed': False, 'reason': 'Budget cap "t160 hardstop" reached —
      $20.11 of $0.01 per day', 'action': 'pause'}
```

The listing now reports `enforced` **measured against `budget_caps`**, not
inferred from the rule's own `action` — so a rule whose mirror is missing is
shown as inert rather than assumed live.

---

## Other findings

### 2. `float(max_cost)` returned HTTP 500 on garbage

`float(body.get('max_cost', 1.0))` raised `ValueError` for `{"max_cost": "abc"}`.
Now a 400 with an explanation.

### 3. Negative limits were accepted

A cap of `-5` dollars was stored as though sensible. It can never be satisfied,
and it was configured by someone trying to *restrict* spending. Zero is still
allowed — "block everything" is a legitimate cap; only negatives are absurd.

### 4. PATCH bypassed every check the create path performs

Verified live: a rule ended up holding `max_cost: 'not-a-number'` and
`action: 'ignore_everything'`, both stored and listed as valid. A cap holding a
string cannot be compared against a number — the rule is inert while looking
configured, which is exactly the headline defect in miniature. PATCH now runs
the same validation, and a PATCH/DELETE of a missing rule returns 404 instead of
`{'ok': true}`.

### 5. The GitHub pull target escaped the data directory

```python
target_dir = ROOT / 'preview' if target == 'preview' else ROOT / target
target_dir.mkdir(parents=True, exist_ok=True)
```

`target` is caller-supplied. `'../../../tmp/x'` resolves to `/tmp/x`, and
`mkdir(parents=True)` creates it. The per-blob `is_within()` check below guards
each *file* against a malicious path inside the repo — nobody guarded the
destination **root**, so every pulled file landed wherever the caller pointed.
`/api/workspaces/import/github` passes a server-computed target, but
`/api/github/pull` is public and takes its own.

The revert-proof produced the proof: with the guard removed, `/tmp/t160_escape`
was genuinely created on disk.

---

## Revert-proof

**15 of 15 breakages caught**, baseline green before and after.

| # | Breakage | Tests failed |
|---|---|---|
| 1 | stop rule never reaches `budget_caps` | 4 |
| 1b | stop rule mirrored as alert only | 2 |
| 1c | warn rule wrongly blocks | 1 |
| 1d | update does not resync the cap | 2 |
| 1e | delete leaves the cap enforcing | 1 |
| 1f | `enforced` inferred, not measured | 1 |
| 2 | max_cost 500 / negative allowed | 2 |
| 2b | max_tokens 500 / negative allowed | 2 |
| 3b | negative limits accepted | 3 |
| 3c | unknown action silently rewritten | 1 |
| 4 | PATCH skips max_cost validation | 2 |
| 4b | PATCH skips action validation | 1 |
| 4c | PATCH of missing rule returns 200 | 1 |
| 4d | DELETE of missing rule returns 200 | 1 |
| 5 | pull target escapes the data dir | 5 |

Both directions are pinned on enforcement: 1b (a `stop` rule failing to block)
and 1c (a `warn` rule blocking anyway) each fail their own tests.

### Two of my own test mistakes, both caught by running

1. **A guessed schema.** My ledger insert used `prompt_tokens`/`completion_tokens`;
   the real columns are `tokens_in`/`tokens_out`. Caught immediately by the test
   erroring rather than passing.
2. **A test that would have passed on ambient data.** After fixing the schema it
   still failed, because `cost_ledger.created_at` defaults to `''` and the
   enforcer's window is `created_at > datetime('now','-1 day')` — a row without
   an explicit timestamp is invisible to it. Rather than relax the assertion I
   set the timestamp explicitly and added a precondition check that the probe
   spend is actually visible, so the test cannot pass on whatever spend happens
   to be in the shared database.

   Its mirror (`allows spending below the limit`) originally cleared
   `cost_ledger` — a destructive probe against a shared table, which has caused
   false failures elsewhere in this review. Rewritten to set the limit above
   current spend instead.

3. **A self-poisoning test.** `test_an_escaping_target_creates_no_directory`
   created `/tmp/t160_escape` during the revert-proof (correctly — the guard was
   off), which then failed the *next* run on its own precondition. Now cleans up
   before and after.

## Fallout from earlier modules, surfaced here

`seg2` reported 2 failures and, notably, **skips dropped from 10 to 1** — these
cases had been skipping and were now running for the first time. Both were
**pre-existing failures from modules 16 and 21**, confirmed by re-running with
this module's work stashed (both still failed):

- `test_sys_10_...::test_eval_run_produces_valid_scores` — `0 <= done.get("avg_score", 0)`
  raised `TypeError` against `None`. Module 16 made `avg_score` **None** when no
  case could be scored; the assertion was written against the buggy contract.
- `test_uat_08_...::test_user_can_get_ai_risk_assessment` — asserted `ok is True`
  with no provider configured, which only held while `assess-confidence`
  fabricated a verdict. Module 21 replaced that with a 503 that escalates.

Both **updated in place** to assert the honest contract in both directions. This
is the third and fourth consumer of a nullable value found not to be None-safe;
the pattern now has a standing note in the architecture doc.

## Live verification

```
garbage max_cost   -> 400 (was 500)
negative cap       -> 400
bogus action       -> 400, names the valid ones
stop rule          -> enforcer returns allowed:False with the cap name
warn rule          -> enforced:false, "does not block spending"
delete rule 1      -> enforcement correctly falls through to rule 2
PATCH bad value    -> 400 ; PATCH/DELETE missing id -> 404
pull target ../../ -> 400 "Invalid target", no directory created
pull target preview-> accepted (no over-blocking)

3 tabs render in Chromium, 0 dead handlers, no console errors.
```

## Cross-module impact

- **`budget_caps` gains rows with `cap_id` prefixed `ctrl_rule_`.** FinOps and
  compliance read this table and will now see Control Tower rules. That is the
  fix, but it means a user who had configured rules believing them inert will
  find them **live** after this deploy — the release note matters.
- **`/api/control/budget-rules`** can now return 400/404 where it previously
  always returned 200, and the listing gains `enforced`.
- **`/api/github/pull`** rejects targets outside the data directory. Workspace
  import passes a valid path and is unaffected.
- `workspaces.py` itself was reviewed and left alone — its activate/save path is
  already carefully hardened, with prior data-loss fixes documented inline.

## Suite

`4121 unit (2 skipped)` + `664 regression/system/uat (1 skipped)` =
**4,785 passing, 0 failures**. Linters clean.
