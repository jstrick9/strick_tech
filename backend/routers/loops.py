"""
Agentic OS — Autonomous Loops Router
/goal --watch, scheduled agent tasks, standup journal.
"""

from __future__ import annotations

import uuid

from fastapi import APIRouter, Request
from fastapi.responses import JSONResponse

from ..services import scheduler as sched_svc
from ..services.request_body import as_text, json_body_or_error
from ..services.scheduler import _BUILTIN_JOB_IDS

router = APIRouter(prefix='/api/loops', tags=['loops'])


@router.get('')
def list_loops():
    """List all running autonomous loops."""
    return sched_svc.list_loops()


@router.post('')
async def create_loop(req: Request):
    """
    POST /api/loops
    Body: {prompt, interval_minutes, agent_id, target}
    Creates a repeating autonomous agent loop.
    """
    body, _body_err = await json_body_or_error(req)
    if _body_err:
        return _body_err
    prompt = as_text(body.get('prompt'))[:4000]
    try:
        interval = int(body.get('interval_minutes', 15))
    except (TypeError, ValueError):
        interval = 15
    agent_id = str(body.get('agent_id', 'builder'))[:64]
    target = str(body.get('target', 'web'))[:64]
    job_id = str(body.get('job_id') or f'loop_{uuid.uuid4().hex[:8]}')[:128]

    # BUG FIX: add_loop() has supported max_runs and kill_after_success -- the
    # two kill switches for an autonomous agent -- since Sprint B, and this
    # router never read either one off the request. A caller asking for
    # max_runs=1 got {'ok': True} and an UNBOUNDED loop that would call the LLM
    # every N minutes forever. Verified live: POST with max_runs=1 returned ok
    # and the stored job had no bound. Silently discarding a safety limit while
    # reporting success is the worst possible handling of one.
    try:
        max_runs = int(body.get('max_runs', 0) or 0)
    except (TypeError, ValueError):
        return JSONResponse(
            {'ok': False, 'error': 'max_runs must be a whole number'}, status_code=400
        )
    if max_runs < 0:
        return JSONResponse({'ok': False, 'error': 'max_runs cannot be negative'}, status_code=400)
    kill_after_success = bool(body.get('kill_after_success', False))
    goal_id = str(body.get('goal_id', ''))[:128]

    if not prompt:
        # Deliberately a plain dict, not a JSONResponse: app.py's
        # _restatus_refused_write already turns an ok:false on a mutating /api/
        # route into a 400, and /api/loops is not exempt. Setting the status
        # here too was proven redundant by revert-proof (breaking it changed no
        # test outcome), so the explicit version is dead weight that implies the
        # middleware does not cover this path.
        return {'ok': False, 'error': 'prompt required'}

    # The interval is clamped rather than rejected, but say so -- a user who
    # asked for "every 0 minutes" and silently got 1 has been misled about how
    # much their agent will spend.
    requested_interval = interval
    interval = max(1, min(interval, 10080))  # 1 min to 1 week
    result = sched_svc.add_loop(
        job_id,
        prompt,
        interval,
        agent_id,
        target,
        goal_id=goal_id,
        max_runs=max_runs,
        kill_after_success=kill_after_success,
    )
    if isinstance(result, dict) and result.get('ok') and requested_interval != interval:
        result['interval_adjusted'] = True
        result['requested_interval_minutes'] = requested_interval
        result['note'] = (
            f'Interval clamped from {requested_interval} to {interval} minutes '
            '(allowed range is 1 minute to 1 week).'
        )
    if isinstance(result, dict) and not result.get('ok'):
        return JSONResponse(result, status_code=503)
    return result


@router.delete('/{job_id}')
def delete_loop(job_id: str):
    """Stop and remove a loop."""
    if job_id in _BUILTIN_JOB_IDS:
        # BUG FIX: refusing a delete with HTTP 200 told every status-code-aware
        # client the protected job had been removed. 403 is the accurate answer
        # -- the request was understood and deliberately refused.
        return JSONResponse(
            {'ok': False, 'error': f"'{job_id}' is a protected system job and cannot be deleted"},
            status_code=403,
        )
    result = sched_svc.remove_loop(job_id)
    # A real scheduler failure is a 500, not a 200 carrying ok:false.
    if not result.get('ok'):
        return JSONResponse(result, status_code=500)
    return result


@router.post('/{job_id}/pause')
def pause_loop(job_id: str):
    """Pause a running loop."""
    # BUG FIX (x3, shared with resume below):
    #  1. A refusal on a protected job answered HTTP 200 with ok:false -- the
    #     same shape the delete path was already fixed for (403 is accurate).
    #  2. "No job by the id of X" answered 200/400 as a generic error; a missing
    #     loop is a 404.
    #  3. The paused state lived only in APScheduler's in-memory job table, so
    #     it was lost on restart along with everything else. It is now recorded,
    #     and restore_loops() brings the loop back PAUSED rather than quietly
    #     restarting somebody's autonomous agent because the process bounced.
    if job_id in _BUILTIN_JOB_IDS:
        return JSONResponse(
            {'ok': False, 'error': f"'{job_id}' is a protected system job and cannot be paused"},
            status_code=403,
        )
    sched = sched_svc.get_scheduler()
    if not sched:
        return JSONResponse({'ok': False, 'error': 'Scheduler not available'}, status_code=503)
    try:
        sched.pause_job(job_id)
    except Exception as e:
        if 'No job by the id' in str(e):
            return JSONResponse({'ok': False, 'error': f"Loop '{job_id}' not found"}, status_code=404)
        return JSONResponse({'ok': False, 'error': str(e)}, status_code=500)
    sched_svc.set_loop_status(job_id, 'paused')
    return {'ok': True, 'status': 'paused'}


@router.post('/{job_id}/resume')
def resume_loop(job_id: str):
    """Resume a paused loop."""
    if job_id in _BUILTIN_JOB_IDS:
        return JSONResponse(
            {'ok': False, 'error': f"'{job_id}' is a protected system job and cannot be paused/resumed"},
            status_code=403,
        )
    sched = sched_svc.get_scheduler()
    if not sched:
        return JSONResponse({'ok': False, 'error': 'Scheduler not available'}, status_code=503)
    try:
        sched.resume_job(job_id)
    except Exception as e:
        if 'No job by the id' in str(e):
            return JSONResponse({'ok': False, 'error': f"Loop '{job_id}' not found"}, status_code=404)
        return JSONResponse({'ok': False, 'error': str(e)}, status_code=500)
    sched_svc.set_loop_status(job_id, 'running')
    return {'ok': True, 'status': 'running'}


@router.post('/{job_id}/run-now')
async def run_loop_immediately(job_id: str):
    """Trigger immediate execution of an autonomous loop."""
    result = await sched_svc.run_loop_now(job_id)
    if not result.get('ok'):
        return JSONResponse(result, status_code=404)
    # BUG FIX: this reported ok:True as long as the loop EXISTED, regardless of
    # whether the iteration it just ran succeeded. With no AI provider
    # configured the run raised, was recorded in history as an error, and the
    # endpoint still answered "triggered immediately" with ok:True. The button
    # said it worked; the history said it failed.
    job = result.get('job') or {}
    last = (job.get('history') or [])[-1] if job.get('history') else None
    if last and last.get('status') == 'error':
        return JSONResponse(
            {
                'ok': False,
                'job_id': job_id,
                'error': last.get('output', 'Loop iteration failed'),
                'iteration': last.get('iteration'),
                'job': job,
            },
            status_code=502,
        )
    return result


@router.get('/{job_id}/history')
def get_loop_history_endpoint(job_id: str):
    """Get the execution history and outcomes of a loop."""
    result = sched_svc.get_loop_history(job_id)
    # A missing loop answered HTTP 200 with ok:false. Verified live.
    if not result.get('ok'):
        return JSONResponse(result, status_code=404)
    return result


@router.get('/status')
def scheduler_status():
    """Execute or process scheduler status operation."""
    sched = sched_svc.get_scheduler()
    user_jobs = [j for j in (sched.get_jobs() if sched else []) if j.id not in _BUILTIN_JOB_IDS]
    builtin_jobs = [j for j in (sched.get_jobs() if sched else []) if j.id in _BUILTIN_JOB_IDS]
    return {
        'running': sched.running if sched else False,
        'jobs': len(sched.get_jobs()) if sched else 0,
        'user_loop_count': len(user_jobs),
        'builtin_job_count': len(builtin_jobs),
        # The built-in job panel in the UI drew four hardcoded green dots. If
        # APScheduler is missing or the scheduler failed to start, none of those
        # jobs exist and the panel was pure decoration. Report what is actually
        # registered so the UI can render the real state.
        'builtin_jobs': [
            {'id': j.id, 'next_run': j.next_run_time.isoformat() if j.next_run_time else None}
            for j in builtin_jobs
        ],
        'scheduler_available': sched is not None,
        'persisted': True,
        'loops': sched_svc.list_loops(),
    }
