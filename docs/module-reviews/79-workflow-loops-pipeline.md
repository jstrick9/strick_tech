# 79 — Workflow workstation: `loops` and `pipeline`

**Destination:** `workflow`
**Tabs:** `pipeline`, `loops` (this doc) · `specs` (doc 69) · `ambient` (doc 67) — 5/5 covered
**Frontend:** `frontend/js/40-loops.js`, `frontend/js/37-pipeline.js`
**Backend:** `backend/routers/loops.py`, `backend/routers/pipeline.py`, `backend/services/scheduler.py`
**Tests:** `tests/unit/test_154_module18_workflow_loops_pipeline.py` (38)
**Status:** reviewed, fixed, verified live

Destination 7 of 20.

---

## Why these two tabs

`specs` and `ambient` were covered by earlier passes. The two that remained are
the two that **spend money without a human present**: `loops` schedules an agent
to wake on a timer forever, and `pipeline` chains five LLM stages in one click.
Measured against ICM, an autonomous runtime has a higher bar than a read-only
screen — it must be honest about *whether it is still running* and *whether what
it ran actually worked*.

Ten defects. All reproduced against a live server before any code changed.

---

## Findings

### 1. Every autonomous loop was destroyed by a restart — silently

`_jobs` was a bare in-process dict sitting on APScheduler's default in-memory
jobstore. Nothing was ever written to disk. Verified live:

```
POST /api/loops {"prompt":"probe goal","interval_minutes":1}   -> ok, job created
GET  /api/loops                                                -> 1 loop
<restart>
GET  /api/loops                                                -> []
```

The pane calls these *"Autonomous Loops"* and tells the user the agent *"wakes on
a timer, continues working, and commits results"*. A background worker that
evaporates on every deploy is the opposite of autonomous — and the failure is
**silent**: the list is simply empty, indistinguishable from never having
created one. A user who set up a monitoring loop would discover weeks later that
it stopped the first time the process bounced.

**Fix:** a JSON registry at `<data>/memory/loops.json`, written atomically on
create/delete/pause/iteration, and `restore_loops()` called from `start()`. Run
counters and history survive too, so the history pane is no longer reset by a
deploy. A loop that was **paused** when the server went down is restored
**paused** — silently resuming somebody's autonomous agent because the process
bounced would be worse than leaving it stopped.

### 2. The kill switches were unreachable

`add_loop()` has accepted `max_runs` and `kill_after_success` since Sprint B.
`routers/loops.py` read **neither** off the request body. Verified live:

```
POST /api/loops {"prompt":"...","max_runs":1,"kill_after_success":true}
  -> {"ok":true,"job_id":"loop_336aa00d"}
GET  /api/loops -> no bound of any kind stored
```

So a user who asked for *"run this once"* got `ok: true` and an **unbounded**
loop calling the LLM every N minutes forever. Silently discarding a safety limit
while reporting success is the worst available handling of one — it is strictly
worse than rejecting the request, because the user believes the bound is active.

**Fix:** both are read, validated (negative and non-numeric `max_runs` are
rejected 400 and store nothing) and echoed back in the response and the listing,
so a bounded loop is no longer visually identical to an unbounded one.

### 3. `kill_after_success` was read by nothing

Even set directly on the service it did nothing: no code path ever inspected it.
Now a successful iteration (`last_error` cleared) retires the loop; a **failed**
iteration does not, since a failure is not the success it is waiting for.

### 4. `max_runs` retired the loop one wake-up late

The budget check ran *before* an iteration, so an N-run loop completed its N
runs and then sat scheduled until its N+1th tick before removing itself. At
`interval=1440` that is a full day of a finished loop listed as running. The
budget is now also checked immediately after the iteration that spends it.

### 5. Pause and Stop were completely dead in the UI

```js
data-act-click="pauseLoop(${JSON.stringify(l.id)})"
```

`JSON.stringify` emits `"loop_x"` **with double quotes**, inside a
double-quoted HTML attribute — the attribute terminates at the first inner
quote. The emitted markup was literally `data-act-click="pauseLoop("`. Confirmed
in Chromium:

```
attribute: pauseLoop(
console:   [delegate] not a plain call, refusing: pauseLoop(
```

**There was no way to stop a running autonomous agent from its own pane.** The
repo's own convention documents `jsArg()` for exactly this and warns against
`JSON.stringify` in attributes; both buttons predated it. After the fix the
attribute reads `pauseLoop("loop_fcd1125c")` and a real click pauses the loop.

### 6. Refusals and missing jobs answered HTTP 200

`pause`/`resume` returned 200 with `ok:false` for a protected built-in job (403
is accurate — understood and deliberately refused) and for a job that does not
exist (404). `/history` did the same. The delete path had already been fixed for
precisely this; its siblings were missed — the **"second door"** pattern, now 17
occurrences. Pause state also lived only in APScheduler's memory, so it was lost
with everything else on restart.

### 7. `run-now` reported success for a failed iteration

It answered `ok: True, "triggered immediately"` whenever the loop merely
**existed**. With no provider configured the iteration raised, was recorded in
history as an `error`, and the endpoint still said it worked. The button said
success; the history said failure. Now returns **502** with the iteration's own
error when the run it just performed failed.

### 8. The pipeline called every run a success

Both doors hardcoded `ok: True` and `status: 'complete'` on the terminal event.
Verified live with no provider configured — every stage errored with empty
output:

```
non-streaming: ok=True  status=complete   (stages: error, error)
streaming:     "type":"complete","ok":true  (stage: error)
```

The UI then printed **"✅ Done"** and toasted **"Pipeline complete — 5 stages"**.
A five-stage build that produced nothing was indistinguishable from one that
worked. Both doors now share `_summarise()`, which reports
`complete` / `partial` / `failed` with `stages_succeeded`, `stages_failed` and
`failed_stages`; the UI renders all three states distinctly. The audit entry
records `(N/M stages ok)` instead of just `(M stages)`.

### 9. The built-in job panel drew four hardcoded green dots

Four rows with `color:var(--green)` were literal HTML with nothing behind them.
If APScheduler is missing or `start()` failed — it catches and logs its own
exception — none of those jobs exist and the panel asserted four healthy
background workers that were not running. `/api/loops/status` now returns the
real registry (`builtin_jobs`, `scheduler_available`) and the panel renders it,
including an explicit warning when the scheduler is down.

### 10. The loop listing crashed when the scheduler had not started

Found while writing the tests, then confirmed as a genuine pre-existing bug
rather than a harness artifact:

```python
next_run = job.next_run_time.isoformat() if job.next_run_time else None
# AttributeError: 'Job' object has no attribute 'next_run_time'
```

APScheduler only attaches `next_run_time` once the scheduler has **started**.
Since `start()` swallows and logs its exception, a scheduler that failed to come
up left `GET /api/loops` raising → **HTTP 500**. The listing died at exactly the
moment the user most needed to see it. Now read via `getattr(..., None)`, which
also correctly reports such jobs as not scheduled.

---

## Revert-proof

Each fix was individually reverted with `__pycache__` cleared, against the
finished test file. **19 of 19 real breakages caught**, baseline green before
and after.

| # | Breakage | Tests failed |
|---|---|---|
| 1 | loops never persisted | 2 |
| 1b | loops never restored | 2 |
| 1c | paused loop restarts itself | 1 |
| 2 | router discards the kill switches | 3 |
| 2b | listing hides `max_runs` | 2 |
| 2c | `max_runs` not validated | 2 |
| 2d | interval clamp hidden | 1 |
| 3 | `kill_after_success` ignored | 1 |
| 4 | `max_runs` retires a tick late | 1 |
| 6 | pause of a missing loop returns 200 | 1 |
| 6b | built-in refusal returns 200 | 1 |
| 6c | history of a missing loop returns 200 | 1 |
| 6d | pause state not persisted | 1 |
| 7 | run-now claims a failed iteration worked | 1 |
| 8 | pipeline hardcodes `ok:true` | 4 |
| 8c | pipeline history off UTC | 1 |
| 8d | history drops the success count | 1 |
| 9 | status hides the real built-in jobs | 1 |
| 10 | listing crashes without a started scheduler | 5 |

### Two corrections the revert-proof forced

**A test that passed for the wrong reason.** `test_a_paused_loop_comes_back_
paused_not_running` did **not** fail when I broke the restore's pause branch.
Cause: the scheduler is never started in the unit harness, so `next_run_time` is
`None` for *every* job and `list_loops()` reports them all as `paused` — the
assertion was reading an artifact, not the behaviour. Rewritten to assert the
`pause_job` call itself, plus a mirror test proving running loops are *not*
paused by the restore. It now fails correctly when broken.

**Two "fixes" that fixed nothing.** Converting `{'ok': False, 'error': ...}` to
an explicit `JSONResponse(..., 400)` in `loops.create` and `pipeline.run`
changed no test outcome when reverted. Investigating rather than assuming: the
global `_restatus_refused_write` middleware in `app.py` already re-statuses
`ok:false` on mutating `/api/` routes to 400, and neither path is exempt. Both
changes were **reverted** with a comment explaining why — leaving them would
imply the middleware does not cover these routes and invite the next person to
add the same redundant code elsewhere.

## Live verification

Server + real Chromium:

```
attribute:  pauseLoop("loop_fcd1125c")          (was: pauseLoop( )
click Pause -> list re-renders, loop shows PAUSED
loop row:   Runs: 0 / 3 · Next: 2:36:00 AM · stops on success
failed row: ⚠ Last run failed: No AI provider is configured or reachable…
built-ins:  4 rows rendered from /api/loops/status, not hardcoded
console:    no errors, no [delegate] refusals
persistence: create -> restart -> loop still present, bounds intact
             pause  -> restart -> still paused, next_run None
```

## Cross-module impact

- **New file on disk:** `<data_dir>/memory/loops.json`. Written atomically via a
  `.tmp` + `replace`; a corrupt file is logged and skipped, never fatal
  (`test_a_corrupt_registry_does_not_break_startup`).
- **`scheduler.start()`** now calls `restore_loops()`. Loops resume on boot —
  intended, and the whole point of the fix, but it does mean a box that has been
  down for a week will start its loops again on the next boot.
- **New service function** `set_loop_status()`; `add_loop()` gained a private
  `_persist` flag so restore does not rewrite the file it is reading.
- **API changes:** `/api/loops` (POST) accepts `max_runs`, `kill_after_success`,
  `goal_id` and may return `interval_adjusted`/`note`; the listing gains
  `max_runs`/`kill_after_success`; `/status` gains `builtin_jobs`,
  `scheduler_available`, `persisted`. `pause`/`resume`/`history`/`run-now` can
  now return 403/404/502 where they previously always returned 200. Pipeline's
  terminal event gains `status`, `stages_total`, `stages_succeeded`,
  `stages_failed`, `failed_stages`, and `ok` is now computed.
- **`workflow`'s other tabs** (`specs`, `ambient`) untouched.

## Suite

`3936 unit (2 skipped)` + `655 regression/system/uat (10 skipped)` =
**4,591 passing, 0 failures**. Linters clean.
