"""Module 18 — the Workflow workstation: the `loops` and `pipeline` tabs.

Destination: `workflow`, hosting pipeline, loops, specs and ambient. `specs`
(doc 69) and `ambient` (doc 67) were reviewed earlier; this pass closes the two
remaining tabs, which are the two that actually spend money autonomously.

Nine defects, all reproduced against a live server before the fix:

1. EVERY AUTONOMOUS LOOP WAS DESTROYED BY A RESTART, SILENTLY. `_jobs` was a
   bare in-process dict over APScheduler's default in-memory jobstore. Create a
   loop, restart, GET /api/loops -> []. The pane promises an agent that "wakes
   on a timer, continues working, and commits results"; the user got no signal
   at all, just an empty list indistinguishable from never having created one.

2. THE KILL SWITCHES WERE UNREACHABLE. add_loop() has taken max_runs and
   kill_after_success since Sprint B and the router read neither off the
   request. POST {max_runs: 1} returned ok:true and created an UNBOUNDED loop
   that calls the LLM forever. Silently discarding a safety limit while
   reporting success is the worst available handling of one.

3. kill_after_success was stored and never read by anything, even when set
   directly on the service.

4. max_runs retired the loop one wake-up LATE — the budget check ran before an
   iteration, so an N-run loop sat scheduled until its N+1th tick.

5. PAUSE AND STOP WERE DEAD IN THE UI. The buttons interpolated
   `JSON.stringify(l.id)` into a double-quoted HTML attribute, so the emitted
   markup was `data-act-click="pauseLoop("` — truncated at the first inner
   quote. Chromium confirmed: `[delegate] not a plain call, refusing:
   pauseLoop(`. There was no way to stop a running autonomous agent from its
   own pane.

6. Loop endpoints answered HTTP 200 for refusals and missing jobs; the paused
   state lived only in APScheduler's memory, so a restart silently RESUMED a
   loop the user had deliberately paused.

7. run-now reported ok:True whenever the loop merely existed, even when the
   iteration it had just run failed and was recorded in history as an error.

8. THE PIPELINE CALLED EVERY RUN A SUCCESS. Both the SSE and non-streaming
   doors hardcoded `ok: True` / `status: 'complete'` on the terminal event.
   With no provider configured all five stages errored with empty output and
   the run still reported complete — the UI printed "✅ Done" and toasted
   "Pipeline complete".

9. The built-in job panel drew four hardcoded green dots. If APScheduler is
   absent or the scheduler failed to start, none of those jobs exist and the
   panel asserted four healthy workers that were not running.
"""

from __future__ import annotations

import json

import pytest

from backend.routers import pipeline as pipe
from backend.services import scheduler as sched_svc


@pytest.fixture(autouse=True)
def _isolate_loops(tmp_path, monkeypatch):
    """Give every test its own loop registry and a clean in-memory job table."""
    monkeypatch.setattr(sched_svc, 'LOOPS_PATH', tmp_path / 'loops.json')
    saved = dict(sched_svc._jobs)
    for jid in [j for j in sched_svc._jobs if j not in sched_svc._BUILTIN_JOB_IDS]:
        sched_svc._jobs.pop(jid, None)
    yield
    for jid in [j for j in sched_svc._jobs if j not in sched_svc._BUILTIN_JOB_IDS]:
        sched = sched_svc.get_scheduler()
        if sched:
            try:
                sched.remove_job(jid)
            except Exception:
                pass
    sched_svc._jobs.clear()
    sched_svc._jobs.update(saved)


def _mk(job_id='t154_a', **kw):
    kw.setdefault('interval_minutes', 60)
    return sched_svc.add_loop(job_id, kw.pop('prompt', 'probe goal'), **kw)


# ── 1. loops survive a restart ────────────────────────────────────────────────
def test_a_created_loop_is_written_to_disk():
    _mk('t154_persist', prompt='keep me')
    assert sched_svc.LOOPS_PATH.exists(), 'the loop registry was never persisted'
    data = json.loads(sched_svc.LOOPS_PATH.read_text())
    assert 't154_persist' in data
    assert data['t154_persist']['prompt'] == 'keep me'


def test_loops_are_restored_after_a_restart():
    _mk('t154_restart', prompt='survive the bounce', max_runs=4)
    # Simulate a process restart: the in-memory registry is gone, the file is not.
    sched_svc._jobs.pop('t154_restart', None)
    sched = sched_svc.get_scheduler()
    if sched:
        try:
            sched.remove_job('t154_restart')
        except Exception:
            pass

    assert sched_svc.restore_loops() == 1
    loops = {loop['id']: loop for loop in sched_svc.list_loops()}
    assert 't154_restart' in loops, 'the autonomous loop was silently destroyed by the restart'
    assert loops['t154_restart']['prompt'] == 'survive the bounce'
    assert loops['t154_restart']['max_runs'] == 4


def test_run_counters_and_history_survive_a_restart():
    _mk('t154_counters')
    sched_svc._jobs['t154_counters']['run_count'] = 7
    sched_svc._jobs['t154_counters']['history'] = [{'iteration': 7, 'status': 'success', 'output': 'x'}]
    sched_svc._save_loops()
    sched_svc._jobs.pop('t154_counters', None)

    sched_svc.restore_loops()
    hist = sched_svc.get_loop_history('t154_counters')
    assert hist['run_count'] == 7
    assert len(hist['history']) == 1


def test_a_paused_loop_comes_back_paused_not_running(monkeypatch):
    """Resuming someone's autonomous agent because the process bounced is worse
    than leaving it stopped.

    Asserts the pause CALL, not list_loops()'s derived status: the scheduler is
    never started in this harness, so every job reads back as "paused" from
    next_run_time=None and a status assertion here passes whether or not the
    restore actually paused anything. (It did exactly that until this test was
    revert-proven and found not to fail.)
    """
    _mk('t154_paused')
    sched_svc.set_loop_status('t154_paused', 'paused')
    sched_svc._jobs.pop('t154_paused', None)

    paused: list[str] = []
    real = sched_svc.get_scheduler()
    monkeypatch.setattr(real, 'pause_job', lambda jid, *a, **k: paused.append(jid))

    sched_svc.restore_loops()
    assert 't154_paused' in paused, 'a deliberately paused loop was silently restarted'
    assert sched_svc._jobs['t154_paused']['status'] == 'paused'


def test_a_running_loop_is_not_paused_by_the_restore():
    """The mirror case: restore must not pause loops that were running."""
    _mk('t154_running')
    sched_svc.set_loop_status('t154_running', 'running')
    sched_svc._jobs.pop('t154_running', None)

    paused: list[str] = []
    real = sched_svc.get_scheduler()
    orig = real.pause_job
    real.pause_job = lambda jid, *a, **k: (paused.append(jid), orig(jid))[1]
    try:
        sched_svc.restore_loops()
    finally:
        real.pause_job = orig
    assert 't154_running' not in paused
    assert sched_svc._jobs['t154_running']['status'] == 'running'


def test_a_deleted_loop_does_not_come_back():
    _mk('t154_deleted')
    sched_svc.remove_loop('t154_deleted')
    sched_svc._jobs.pop('t154_deleted', None)
    sched_svc.restore_loops()
    assert 't154_deleted' not in {loop['id'] for loop in sched_svc.list_loops()}


def test_a_corrupt_registry_does_not_break_startup():
    sched_svc.LOOPS_PATH.parent.mkdir(parents=True, exist_ok=True)
    sched_svc.LOOPS_PATH.write_text('{ this is not json')
    assert sched_svc.restore_loops() == 0  # must not raise


# ── 2/3/4. the kill switches ──────────────────────────────────────────────────
def test_the_router_forwards_max_runs_instead_of_discarding_it(client):
    r = client.post(
        '/api/loops',
        json={'prompt': 'bounded', 'interval_minutes': 60, 'max_runs': 3, 'job_id': 't154_bound'},
    )
    assert r.status_code == 200
    assert r.json()['max_runs'] == 3, 'the safety limit was accepted and thrown away'
    assert sched_svc._jobs['t154_bound']['max_runs'] == 3


def test_the_router_forwards_kill_after_success(client):
    r = client.post(
        '/api/loops',
        json={'prompt': 'once', 'interval_minutes': 60, 'kill_after_success': True, 'job_id': 't154_kill'},
    )
    assert r.json()['kill_after_success'] is True
    assert sched_svc._jobs['t154_kill']['kill_after_success'] is True


def test_the_stopping_condition_is_visible_in_the_listing(client):
    client.post(
        '/api/loops',
        json={'prompt': 'p', 'interval_minutes': 60, 'max_runs': 2, 'job_id': 't154_vis'},
    )
    row = next(loop for loop in sched_svc.list_loops() if loop['id'] == 't154_vis')
    assert row['max_runs'] == 2, 'a bounded loop looked identical to an unbounded one'
    assert 'kill_after_success' in row


def test_a_negative_max_runs_is_rejected(client):
    r = client.post('/api/loops', json={'prompt': 'p', 'max_runs': -5, 'job_id': 't154_neg'})
    assert r.status_code == 400
    assert 't154_neg' not in sched_svc._jobs


def test_a_nonnumeric_max_runs_is_rejected(client):
    r = client.post('/api/loops', json={'prompt': 'p', 'max_runs': 'lots', 'job_id': 't154_nan'})
    assert r.status_code == 400


def test_a_missing_prompt_is_a_400_not_a_200(client):
    """Both the handler and the global ok:false middleware produce 400 here, so
    the status alone cannot distinguish them; assert the handler's own response
    directly as well."""
    r = client.post('/api/loops', json={'prompt': '   '})
    assert r.status_code == 400
    assert r.json()['error'] == 'prompt required'
    assert 't154' not in str(sched_svc._jobs.keys())


def test_an_out_of_range_interval_is_clamped_but_disclosed(client):
    r = client.post('/api/loops', json={'prompt': 'p', 'interval_minutes': 0, 'job_id': 't154_clamp'})
    body = r.json()
    assert body['interval_minutes'] == 1
    assert body['interval_adjusted'] is True, 'the user was not told their interval had been changed'
    assert body['requested_interval_minutes'] == 0


def test_an_in_range_interval_is_not_flagged_as_adjusted(client):
    body = client.post(
        '/api/loops', json={'prompt': 'p', 'interval_minutes': 30, 'job_id': 't154_ok'}
    ).json()
    assert 'interval_adjusted' not in body


@pytest.mark.asyncio
async def test_kill_after_success_retires_the_loop_after_a_good_iteration(monkeypatch):
    """It was stored and read by nothing; the loop ran forever."""
    _mk('t154_ks', kill_after_success=True)

    async def fake_run(job_id, *a, **k):
        sched_svc._jobs[job_id]['run_count'] = sched_svc._jobs[job_id].get('run_count', 0) + 1
        sched_svc._jobs[job_id].pop('last_error', None)  # success

    monkeypatch.setattr(sched_svc, '_run_goal_loop', fake_run)
    job = sched_svc.get_scheduler().get_job('t154_ks')
    await job.func()
    assert 't154_ks' not in sched_svc._jobs, 'kill_after_success did not stop the loop'


@pytest.mark.asyncio
async def test_kill_after_success_keeps_the_loop_alive_after_a_failure(monkeypatch):
    _mk('t154_ksf', kill_after_success=True)

    async def fake_run(job_id, *a, **k):
        sched_svc._jobs[job_id]['run_count'] = sched_svc._jobs[job_id].get('run_count', 0) + 1
        sched_svc._jobs[job_id]['last_error'] = 'boom'

    monkeypatch.setattr(sched_svc, '_run_goal_loop', fake_run)
    await sched_svc.get_scheduler().get_job('t154_ksf').func()
    assert 't154_ksf' in sched_svc._jobs, 'a failed iteration must not count as the success it waits for'


@pytest.mark.asyncio
async def test_max_runs_retires_the_loop_as_soon_as_the_budget_is_spent(monkeypatch):
    """The check ran BEFORE an iteration, so an N-run loop stayed scheduled
    until its N+1th wake-up -- with interval=1440 that is a day of a finished
    loop still listed as running."""
    _mk('t154_budget', max_runs=1)

    async def fake_run(job_id, *a, **k):
        sched_svc._jobs[job_id]['run_count'] = sched_svc._jobs[job_id].get('run_count', 0) + 1
        sched_svc._jobs[job_id].pop('last_error', None)

    monkeypatch.setattr(sched_svc, '_run_goal_loop', fake_run)
    await sched_svc.get_scheduler().get_job('t154_budget').func()
    assert 't154_budget' not in sched_svc._jobs


@pytest.mark.asyncio
async def test_an_unbounded_loop_keeps_running(monkeypatch):
    """max_runs=0 means unlimited; the retirement logic must not fire on it."""
    _mk('t154_unbounded', max_runs=0)

    async def fake_run(job_id, *a, **k):
        sched_svc._jobs[job_id]['run_count'] = sched_svc._jobs[job_id].get('run_count', 0) + 1
        sched_svc._jobs[job_id].pop('last_error', None)

    monkeypatch.setattr(sched_svc, '_run_goal_loop', fake_run)
    for _ in range(3):
        await sched_svc.get_scheduler().get_job('t154_unbounded').func()
    assert sched_svc._jobs['t154_unbounded']['run_count'] == 3


# ── 10. the listing must not die when the scheduler is not running ────────────
def test_listing_loops_works_before_the_scheduler_has_started():
    """`job.next_run_time` only exists once the scheduler has STARTED. start()
    swallows and logs its exceptions, so a scheduler that failed to come up left
    GET /api/loops raising AttributeError -> HTTP 500. The listing died at
    exactly the moment the user most needed to see it."""
    _mk('t154_nostart')
    sched = sched_svc.get_scheduler()
    job = sched.get_job('t154_nostart')
    had = hasattr(job, 'next_run_time')
    if had:
        # Reproduce the pre-start shape: the attribute is simply absent.
        try:
            del job.next_run_time
        except Exception:
            object.__setattr__(job, '__dict__', {k: v for k, v in job.__dict__.items() if k != 'next_run_time'})
    rows = sched_svc.list_loops()  # must not raise
    row = next(r for r in rows if r['id'] == 't154_nostart')
    assert row['next_run'] is None
    assert row['status'] == 'paused'


def test_the_listing_endpoint_survives_an_unstarted_scheduler(client):
    client.post('/api/loops', json={'prompt': 'p', 'interval_minutes': 60, 'job_id': 't154_ep'})
    job = sched_svc.get_scheduler().get_job('t154_ep')
    if hasattr(job, 'next_run_time'):
        try:
            del job.next_run_time
        except Exception:
            object.__setattr__(job, '__dict__', {k: v for k, v in job.__dict__.items() if k != 'next_run_time'})
    r = client.get('/api/loops')
    assert r.status_code == 200, 'the loop listing answered HTTP 500'


# ── 6. honest status codes, and pause that persists ───────────────────────────
def test_pausing_a_missing_loop_is_a_404(client):
    r = client.post('/api/loops/t154_ghost/pause')
    assert r.status_code == 404


def test_resuming_a_missing_loop_is_a_404(client):
    assert client.post('/api/loops/t154_ghost/resume').status_code == 404


def test_history_for_a_missing_loop_is_a_404(client):
    r = client.get('/api/loops/t154_ghost/history')
    assert r.status_code == 404, 'a missing loop answered HTTP 200 with ok:false'


def test_run_now_on_a_missing_loop_is_a_404(client):
    assert client.post('/api/loops/t154_ghost/run-now').status_code == 404


def test_pausing_a_protected_builtin_job_is_a_403(client):
    r = client.post('/api/loops/memory_index/pause')
    assert r.status_code == 403, 'a refusal answered 200, telling clients it had succeeded'
    assert r.json()['ok'] is False


def test_pausing_records_the_state_so_a_restart_respects_it(client):
    client.post('/api/loops', json={'prompt': 'p', 'interval_minutes': 60, 'job_id': 't154_pp'})
    assert client.post('/api/loops/t154_pp/pause').status_code == 200
    assert json.loads(sched_svc.LOOPS_PATH.read_text())['t154_pp']['status'] == 'paused'
    client.post('/api/loops/t154_pp/resume')
    assert json.loads(sched_svc.LOOPS_PATH.read_text())['t154_pp']['status'] == 'running'


# ── 7. run-now must not claim a failed iteration succeeded ────────────────────
def test_run_now_reports_a_failed_iteration_as_a_failure(client, monkeypatch):
    client.post('/api/loops', json={'prompt': 'p', 'interval_minutes': 60, 'job_id': 't154_rn'})

    async def failing(job_id, *a, **k):
        sched_svc._jobs[job_id].setdefault('history', []).append(
            {'iteration': 1, 'status': 'error', 'output': 'Error: no provider'}
        )

    monkeypatch.setattr(sched_svc, '_run_goal_loop', failing)
    r = client.post('/api/loops/t154_rn/run-now')
    assert r.status_code == 502, 'the button said it worked while history said it failed'
    assert r.json()['ok'] is False


def test_run_now_still_reports_a_good_iteration_as_success(client, monkeypatch):
    client.post('/api/loops', json={'prompt': 'p', 'interval_minutes': 60, 'job_id': 't154_rn2'})

    async def working(job_id, *a, **k):
        sched_svc._jobs[job_id].setdefault('history', []).append(
            {'iteration': 1, 'status': 'success', 'output': 'did the thing'}
        )

    monkeypatch.setattr(sched_svc, '_run_goal_loop', working)
    r = client.post('/api/loops/t154_rn2/run-now')
    assert r.status_code == 200 and r.json()['ok'] is True


# ── 9. the built-in job panel reports real registrations ──────────────────────
def test_status_reports_the_builtin_jobs_that_actually_exist(client):
    body = client.get('/api/loops/status').json()
    assert 'builtin_jobs' in body, 'the UI drew four green dots with nothing behind them'
    assert body['scheduler_available'] is True
    ids = {j['id'] for j in body['builtin_jobs']}
    assert ids <= set(sched_svc._BUILTIN_JOB_IDS)


# ── 8. the pipeline must not call a failed run a success ──────────────────────
def _summary(statuses):
    results = [{'stage': f's{i}', 'status': st, 'tokens': 1, 'cost': 0.1} for i, st in enumerate(statuses)]
    return pipe._summarise(results, [f's{i}' for i in range(len(statuses))], 0.0, 'run1')


def test_a_run_where_every_stage_failed_is_not_ok():
    s = _summary(['error', 'error'])
    assert s['ok'] is False, 'a pipeline that produced nothing reported complete'
    assert s['status'] == 'failed'
    assert s['stages_succeeded'] == 0
    assert s['failed_stages'] == ['s0', 's1']


def test_a_partial_run_is_reported_as_partial():
    s = _summary(['done', 'error'])
    assert s['ok'] is False
    assert s['status'] == 'partial'
    assert s['stages_succeeded'] == 1 and s['stages_failed'] == 1


def test_a_fully_successful_run_is_still_reported_complete():
    s = _summary(['done', 'done'])
    assert s['ok'] is True and s['status'] == 'complete'
    assert s['failed_stages'] == []


def test_the_non_streaming_door_reports_stage_failures(client):
    """Both doors were wrong in the same way; both are covered."""
    r = client.post(
        '/api/pipeline/run', json={'goal': 'probe', 'stages': ['goal'], 'stream': False}
    )
    body = r.json()
    assert set(['ok', 'status', 'stages_succeeded', 'stages_failed', 'failed_stages']) <= set(body)
    # With the suite's stubbed LLM the stage may pass or fail; what must hold is
    # that the verdict AGREES with the per-stage results rather than being fixed.
    failed = [x for x in body['results'] if x.get('status') != 'done']
    assert body['ok'] is (not failed)
    assert body['stages_failed'] == len(failed)


def test_the_streaming_door_reports_stage_failures(client):
    with client.stream(
        'POST', '/api/pipeline/run', json={'goal': 'probe', 'stages': ['goal'], 'stream': True}
    ) as r:
        events = [
            json.loads(line.removeprefix('data: '))
            for line in r.iter_lines()
            if line.startswith('data: ')
        ]
    done = next(e for e in events if e.get('type') == 'complete')
    failed = [x for x in done['results'] if x.get('status') != 'done']
    assert done['ok'] is (not failed), 'the SSE terminal event hardcoded ok:true'
    assert done['stages_failed'] == len(failed)


def test_pipeline_requires_a_goal(client):
    r = client.post('/api/pipeline/run', json={'goal': '', 'stream': False})
    assert r.status_code == 400


def test_pipeline_history_timestamps_are_utc_not_local(client):
    """Same defect as the Secrets Vault list: SQLite `localtime` then stamped Z."""
    client.post('/api/pipeline/run', json={'goal': 'ts probe', 'stages': ['goal'], 'stream': False})
    rows = client.get('/api/pipeline/history').json()
    assert rows, 'a completed run left no history entry'
    from backend.services import memory_db

    con = memory_db.get_conn()
    try:
        raw = con.execute(
            "SELECT created_at FROM audit WHERE action='pipeline_run' ORDER BY id DESC LIMIT 1"
        ).fetchone()[0]
    finally:
        con.close()
    assert rows[0]['ts'].replace('T', ' ').rstrip('Z') == raw


def test_pipeline_history_records_how_many_stages_actually_worked(client):
    client.post('/api/pipeline/run', json={'goal': 'audit probe', 'stages': ['goal'], 'stream': False})
    rows = client.get('/api/pipeline/history').json()
    assert 'stages ok' in rows[0]['detail'], (
        'history said "(N stages)" whether they worked or not'
    )
