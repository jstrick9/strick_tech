# 68 — Module review 7: `finetune`, `pluginsdk`, `pqc`, `profiler`

All four render from `frontend/js/03-features-a.js` (3,006 lines, 30
endpoints) and were reviewed as one unit. All score **20**.

---

## The defect: the server said "synthetic" and the UI never listened

`/api/profiler/flamegraph` returns a hand-written call tree:

```
main 1000 → handle_request 850 → chat_router 400 → llm.complete() 320
         → httpx.post() 280 → ssl_connect() 60 / stream_response() 190
```

An earlier batch had already fixed the **backend**, which now reports:

```json
{ "synthetic": true, "has_real_data": false,
  "note": "The base tree is illustrative sample data, not a measurement…" }
```

**`renderFlamegraph()` read none of it.** It rendered `d.flamegraph[0]` and
stopped, so the pane showed an unlabelled fake profile beside genuinely
measured panels — process RSS, DB row counts, agent timings — with nothing to
tell them apart.

Fixing the server and not the client leaves the user exactly where the server
fix was meant to move them. That is the **"second door"** pattern in its API/UI
form — 9+ occurrences in this review.

A flamegraph is *acted on*: a developer reads "ssl_connect 60ms" and goes
looking for it. Labelling costs one banner.

### Following the convention already in the repo

The PQC pane, one file away, reads `algos.simulated` and badges itself
**SIMULATED**, with a comment saying that being honest about it is the point.
This follows that treatment rather than inventing a second one:

> **SAMPLE DATA** — The base tree is illustrative sample data, not a
> measurement of this process… *No requests profiled yet — use the app, then
> refresh.*

The banner is conditional on `synthetic`, so a future real profiler is not
libelled as fake, and it distinguishes "no requests profiled yet" from
"observed latency is included".

---

## A correction to my own finding

I first reported the **backend** as fabricating data and began patching it. It
had already been fixed — the response carried `synthetic`, `note` and
`has_real_data`, and it merges real endpoint latencies under a `real_endpoints`
subtree when `_endpoint_stats` has data. I reverted that edit. **The gap was
only ever on the client.**

---

## Verified as already correct

| Check | Result |
|---|---|
| 13 GET endpoints across the four panes | all 200 on an empty account |
| `/api/pqc/algorithms` | `simulated: true`, pane badges it |
| `/api/finetune/hardware` | real detection; honest notice when unavailable |
| All four panes | render with **zero page errors** |

`finetune` is a good example of the pattern done right: it reports
`training_available: false` with *"No local training backend is installed
(needs PyTorch or MLX, plus peft)… datasets can still be prepared"* rather than
claiming a capability the machine lacks.

---

## Cross-module impact

- `03-features-a.js` also hosts `workflow`, `multitab` and `tauri`, which were
  **not** reviewed here and remain unexamined.
- The `real_endpoints` subtree depends on `_endpoint_stats`, populated by
  middleware — if that is ever disabled the banner correctly falls back to
  "No requests profiled yet".

## Verification

| Check | Result |
|---|---|
| Flamegraph banner | absent → **SAMPLE DATA** with the server's own note |
| Revert the UI fix | **6 of 11** tests fail |
| Full suite | 3,494 unit (2 skipped) + 655 (10 skipped), 0 failures |
