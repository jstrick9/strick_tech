"""
Agentic OS — Autonomous Loops Router
/goal --watch, scheduled agent tasks, standup journal.
"""

from __future__ import annotations

import contextlib

import uuid

from fastapi import APIRouter, Request

from ..services import scheduler as sched_svc
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
    try:
        body = await req.json()
    except (json.JSONDecodeError, TypeError, ValueError):
        body = {}
    prompt = (body.get('prompt') or '').strip()
    interval = int(body.get('interval_minutes', 15))
    agent_id = body.get('agent_id', 'builder')
    target = body.get('target', 'web')
    job_id = body.get('job_id') or f'loop_{uuid.uuid4().hex[:8]}'

    if not prompt:
        return {'ok': False, 'error': 'prompt required'}

    interval = max(1, min(interval, 10080))  # 1 min to 1 week
    result = sched_svc.add_loop(job_id, prompt, interval, agent_id, target)
    return result


@router.delete('/{job_id}')
def delete_loop(job_id: str):
    """Stop and remove a loop."""
    if job_id in _BUILTIN_JOB_IDS:
        return {'ok': False, 'error': f"'{job_id}' is a protected system job and cannot be deleted"}
    return sched_svc.remove_loop(job_id)


@router.post('/{job_id}/pause')
def pause_loop(job_id: str):
    """Execute or process pause loop operation."""
    if job_id in _BUILTIN_JOB_IDS:
        return {'ok': False, 'error': f"'{job_id}' is a protected system job and cannot be paused"}
    sched = sched_svc.get_scheduler()
    if sched:
        try:
            sched.pause_job(job_id)
            return {'ok': True, 'status': 'paused'}
        except Exception as e:
            return {'ok': False, 'error': str(e)}
    return {'ok': False, 'error': 'Scheduler not available'}


@router.post('/{job_id}/resume')
def resume_loop(job_id: str):
    """Execute or process resume loop operation."""
    if job_id in _BUILTIN_JOB_IDS:
        return {'ok': False, 'error': f"'{job_id}' is a protected system job and cannot be paused/resumed"}
    sched = sched_svc.get_scheduler()
    if sched:
        try:
            sched.resume_job(job_id)
            return {'ok': True, 'status': 'running'}
        except Exception as e:
            return {'ok': False, 'error': str(e)}
    return {'ok': False, 'error': 'Scheduler not available'}


@router.post('/{job_id}/run-now')
async def run_loop_immediately(job_id: str):
    """Trigger immediate execution of an autonomous loop."""
    return await sched_svc.run_loop_now(job_id)


@router.get('/{job_id}/history')
def get_loop_history_endpoint(job_id: str):
    """Get the execution history and outcomes of a loop."""
    return sched_svc.get_loop_history(job_id)


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
        'loops': sched_svc.list_loops(),
    }
