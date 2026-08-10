# Module 13 — Evals · RAG · Knowledge Graph · Observability

**Reviewed:** 2026-08-10
**Panes:** `evals`, `rag`, `knowledge-graph`, `observability`
**Frontend:** `frontend/js/05-evals-observability.js` (970 lines)
**Backend:** `backend/routers/evals.py`, `rag.py`, `knowledge_graph.py`, `observability.py`
**Endpoints:** 42
**Risk score:** 17

---

## Summary

Four panes whose entire job is **measuring quality**. Three defects, all the
same failure: *reporting a score for something that was never measured.*

| # | Component | Defect | Severity |
|---|---|---|---|
| 1 | evals | An eval whose judge returned unparseable JSON reported **overall 71 → "pass"** | High |
| 2 | rag | Identical defect in `/eval` — **0.7/0.7 → grade "C"** (second door) | High |
| 3 | observability | DORA reported **"12 deployments, 0.0% failure rate, grade Elite"** with zero traces | High |

---

## 1. An evaluation that measured nothing reported a pass

`_eval_response()` asks a judge model for four JSON verdicts. Models routinely
wrap JSON in prose, so the parse fails often. Every dimension had an invented
fallback:

```python
faithfulness    = float(faith_data.get('faithfulness', 0.7))
hallucination   = float(faith_data.get('hallucination', 0.3))
task_completion = float(task_data.get('task_completion', 0.7))
response_quality = int(quality_data.get('quality', 70))
```

With all four unparseable:

```
0.7*30 + 0.7*25 + (1-0.3)*25 + 0.70*15 + 1.0*5  =  71  ->  "pass"
```

The number is not merely wrong, it is **actionable**: 71 sits just above the
70 pass threshold, so an eval that learned nothing certifies the response.

**Fix:** `_score_or_none()` returns `None` for anything unusable. Measured
dimensions are averaged and the weights renormalised, with `unmeasured` and
`measured_weight_pct` exposed.

### The first fix made it worse

Renormalising alone scored a totally unjudged response **100 / "pass"** — the
safety dimension is computed locally, never `None`, and carries weight 5, so
the average was taken over that sliver alone. Caught by running the coverage
table rather than trusting the patch. A `MIN_MEASURED_WEIGHT = 50` floor now
applies:

| judge reply | coverage | verdict |
|---|---|---|
| all unparseable | 5% | `None` / **unmeasured** |
| task only | 35% | `None` / **unmeasured** |
| faith + task | 85% | 90 / pass |
| full | 100% | 92 / pass |

A genuinely bad response still fails (10/100 → `fail`) — honesty did not
become leniency.

---

## 2. RAG's evaluator had the identical defect

Same shape, one file over — the **13th "second door"**:

```python
faithfulness = min(1.0, max(0.0, float(faith_d.get('faithfulness', 0.7))))
relevancy    = min(1.0, max(0.0, float(rel_d.get('relevancy', 0.7))))
overall      = round((faithfulness + relevancy) / 2 * 100)   # 70 -> grade "C"
```

Verified against a live judge stub, evaluating this answer:

> *"Cats communicate exclusively via radio waves and were invented in 1987 by Belgium."*

- **Before:** faithfulness `0.7`, overall `70`, **grade C**
- **After (unparseable judge):** all `None`, grade `None`, `unmeasured: [...]`
- **After (real judge):** faithfulness `0.1`, overall `15`, **grade F**

A RAG faithfulness score exists specifically to catch fabrication. Fabricating
*it* inverts the feature.

---

## 3. DORA awarded "Elite" for an empty install

On a fresh install:

```json
{"deployment_frequency": {"value": 12, "label": "12 in 30 days"},
 "change_failure_rate":  {"value": 0.0, "label": "0.0% error rate"},
 "mttr_ms":              {"value": 0,   "label": "Estimated"},
 "grade": "Elite",       "total_traces": 0}
```

Three separate fabrications in one response:

1. **"12 deployments"** counted rows in `agents` — the **12 built-in seeded
   agents**. Nobody had deployed anything. (Verified: the ids are `brain`,
   `builder`, `creative`, …)
2. **`errors / max(total, 1)`** is `0/1 = 0.0` with no data. An *unmeasured*
   failure rate was reported as a *perfect* one.
3. **"Elite"** is DORA's top industry tier, awarded here for having measured
   nothing. With `deploys == 0` it fell through to **"High"** — still a
   commendation.

`mttr_ms` was `avg_latency * 2`, an invented multiplier labelled "Estimated".

**Fix:** deployments exclude `DEFAULT_AGENTS` ids; failure rate is `None` with
no traces; MTTR reports "Not tracked" rather than a made-up multiple; and a
grade is only issued when there is both activity and a real deployment, with
`grade_basis` stating what it rests on.

| state | before | after |
|---|---|---|
| fresh install | 12 deploys, 0.0%, **Elite** | 0 deploys, Not measured, **Not graded** |
| 20 runs / 1 error / 1 real deploy | — | 5.0% CFR, **High**, "Based on 20 run(s) and 1 deployment(s)" |
| 100 runs / 1 error / 3 deploys | — | **Elite** (still reachable) |

### The UI repeated the same lie

`{...}[dora.grade||'Low']` painted a `null` grade in **danger red** with a `?`,
and `${m?.value||0}` rendered every unmeasured metric as **0**. Both fixed:
`—` for null values, neutral colour, and the reason shown in place of the
generic "Elite → High → Medium → Low" caption. Verified in Chromium.

---

## Verified working (no change needed)

- **RAG retrieval discriminates correctly.** "what sound do cats make" against
  a cats document returns the chunk; "quantum chromodynamics lattice gauge"
  returns **0 chunks**. No similarity floor bug.
- `/rag/pipelines/{id}/eval` and `/evals/run` both degrade to an honest 503
  with no provider (global `LLMUnavailableError` handler).
- Knowledge Graph entities/relations/facts/traverse/stats all behave; empty
  state returns honest zeroes.
- `/evals/summary`, `/observability/analytics` and `/observability/traces`
  report real zeroes on an empty install — no invented averages.
- PII detection in the eval safety check is local and deterministic (SSN,
  card, email patterns), so it is unaffected by judge failures.
- This file is **not** IIFE-wrapped, so its 27 handlers become globals via
  bundle concatenation — confirmed at runtime, 0 dead. My Module 11 rule
  correctly excluded it.

---

## Cross-module impact

- `overall_score` and `pass_fail` can now be `None` / `"unmeasured"`. Consumers:
  `/evals/summary` (aggregates over stored rows — unaffected, nulls are
  skipped by SQL `AVG`) and the evals pane.
- `dora.grade` can be `null`; the only consumer is this pane, fixed here.
- The **fabricated-confidence pattern** is now fixed in seven modules
  (dashboard, health, profiler, codeindex, bugbot, finetune, and these three).
  The shape is identical every time: a fallback constant standing in for a
  measurement that failed.

---

## Tests

`tests/unit/test_146_module13_evals_rag_observability.py` — **26 tests.**

Revert-proof (caches cleared, all three routers + the JS reverted):
**24 of 26 fail.** The two survivors are deliberate guards that the fix must
not break — `test_a_bad_response_still_fails` (honesty ≠ leniency) and
`test_dora_elite_still_reachable` (the grade must remain attainable).

Full suite: **3,655 unit + 655 regression/system/uat = 4,310 passing, 0 failures.**
