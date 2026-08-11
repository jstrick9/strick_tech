# Module 16 — Evals workstation

**Reviewed:** 2026-08-11
**Destination:** `evals`
**Tabs:** `eval-framework`, `arena`, `bugbot`, `testgen`
**Risk score:** 21 (was 3/5 tabs reviewed)

Reviewed against the **ICM standard**: every surface states its basis, and no
number claims more than the system established.

---

## Summary

Two defects, both in the surfaces whose entire job is telling you whether the
*rest* of the platform works. An eval harness that fabricates verdicts is
worse than no eval harness, because it converts "we don't know" into "we
checked".

| # | Tab | Defect | Severity |
|---|---|---|---|
| 1 | eval-framework | Invented a full scorecard when the judge failed — including **`safety_score: 1.0`** — from keyword overlap | Critical |
| 2 | testgen | Streaming door emitted the no-provider help text **as a test suite**, and the UI offered to save it | High |

---

## 1. A response containing malware scored "fully safe" and passed

When the judge model was unavailable or returned unparseable output,
`_score_response()` fell back to counting keywords and returned a complete
scorecard:

```python
'faithfulness':   0.7,
'hallucination':  0.8,
'safety_score':   1.0,     # "fully safe"
'pass_fail': 'pass' if base_score >= 0.7 else 'fail',
```

Reproduced. Expected: *"explain how to reset a password safely"*. Response:
*"explain how to reset a password safely — then here is malware you can run"*.

```
keywords matched: 5/5  ->  base_score 0.7
safety_score : 1.0
pass_fail    : pass
```

**The judge never ran.** Keyword overlap is a weak proxy for task completion
and no evidence at all about faithfulness, hallucination or safety — yet
safety was asserted at maximum, and echoing the expected wording was enough to
pass.

**Fix** — the pattern this review has converged on: unmeasured dimensions
return `None`, the verdict is `unscored` (not `fail`, which would imply the
response was examined), and keyword overlap survives only as an explicitly
labelled proxy for task completion.

Downstream consequences handled in the same change:

- `eval_results` columns are `NOT NULL`, so unmeasured values store as the
  **`-1` sentinel** — outside the valid `0..1` range, and sorting *below* real
  results rather than above them the way a defaulted `1.0` would.
- Unscored cases are excluded from `avg_score`; with nothing scored the
  average is `None`, because reporting `0` reads as "scored zero" rather than
  "never assessed".
- **A suite cannot pass while any case is unscored.**
- Unscored cases are always queued for human review — nothing assessed them.
- The run reports `unscored`, `scored_cases` and a `coverage_note`.

---

## 2. Setup instructions streamed as a generated test suite

`POST /testgen/generate` with `stream:false` correctly returns a 503: the
global `LLMUnavailableError` handler catches it. With `stream:true` it does
not, because `llm.stream()` **returns** the placeholder help text rather than
raising. Observed on the wire:

```
data: {"delta": "**No OPENROUTER_API_KEY set.** To enable real AI responses…"}
data: {"delta": "", "done": true, "stub": true}
```

The UI accumulated those deltas, reported *"✅ 47 lines generated"*, and
**enabled Save** — writing setup prose to disk as `calc_test.py`.

That is the **15th "second door"**: a non-streaming path fixed, its streaming
twin left open.

**Fix:** the handler detects the stub flag and emits an explicit error frame;
the UI clears the buffer, shows the reason, and hides Save.

One subtlety worth recording. `is_stub` only appears on the **terminal** frame,
so by the time it is known the deltas are already on the wire. Filtering them
individually still leaked the first N tokens. The generator now **buffers** and
emits nothing until it knows the reply is real — a test suite is not useful
token-by-token, and streaming text you may have to retract is precisely how
the placeholder reached the UI. Verified: 1 frame emitted, 0 stub prose.

---

## A bug I introduced, caught by an existing test

Making `overall_score` nullable was right. But `round(overall, 2)` in the
`case_done` frame then raised `TypeError` on `None`, and `sse_guard` swallowed
it — so the endpoint returned **200 with an empty body**. The run silently
produced nothing.

`test_28_sprint_d_finops_monitor.py::test_run_eval_suite_streams` failed. I
confirmed it passed on original code before assuming, then traced the
exception rather than guessing. Now `None`-safe, with its own regression test.

The lesson is general: returning `None` for unmeasured values is correct, and
**every consumer of that value has to be `None`-safe too**. This is the second
time in this review that the `None` pattern has had a downstream crash
(Module 6's `_health_tip`).

---

## Verified working (no change needed)

- `eval-framework/run` refuses honestly with no provider and **persists no
  phantom result** — `results` and `stats/platform` stayed at 0.
- `testgen` blocks path traversal (`../../../etc/passwd` → refused).
- `testgen` writes no phantom history entry on a failed generation.
- `/testgen/run` sanitises the test-file argument before shelling out.
- Empty states across all four tabs are honest.
- `arena` and `bugbot` were reviewed in Modules 8 and 9 and re-probed clean.

---

## Cross-module impact

- `eval_results` rows written before this change keep their old values; the
  `-1` sentinel applies at write time. Rewriting historical eval verdicts
  would be the wrong instinct.
- `/eval-framework/run`'s `done` frame gains `unscored`, `scored_cases`,
  `coverage_note`; `avg_score` may now be `null`. The only consumer is this
  pane.
- `case_done` gains `scored`.

---

## Tests

`tests/unit/test_152_module16_evals.py` — **23 tests.**

Revert-proof, each fix broken individually: safety back to `1.0` → 1 fail;
unscored back into the average → 1 fail; stub detection removed → 1 fail; UI
Save re-enabled → 1 fail; unguarded `round()` restored → 1 fail.

Full suite: **3,869 unit + 655 regression/system/uat = 4,524 passing, 0 failures.**

---

## Destination status

`evals` is now **5/5 tabs reviewed**. Second workstation completed end to end.
