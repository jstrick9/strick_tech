"""
Agentic OS — Autonomous Scheduler Service  (Sprint B Enhanced)
APScheduler-based autonomous agent loops:
  - /goal --watch: Hermes wakes every N min, continues tasks, commits, runs E2E
  - Daily standup journal / Memory auto-index / Cost digest
  - Sprint B: per-agent loop config, goal-linked loops, kill switches
  - Sprint B: loop run history, outcome tracking, broadcast on fire
"""

from __future__ import annotations

import asyncio
import contextlib
import datetime
import json
import logging
from typing import Any

log = logging.getLogger('agentic.scheduler')

from backend.config import get_data_dir

ROOT = get_data_dir()

_scheduler = None
_jobs: dict[str, Any] = {}

# Where user-created loops are persisted between restarts.
#
# BUG FIX: `_jobs` was a bare in-process dict and the APScheduler instance used
# the default in-memory jobstore, so EVERY autonomous loop was destroyed by a
# restart -- silently. Verified live: create a loop, restart, GET /api/loops
# returns []. The pane calls these "Autonomous Loops" and tells the user the
# agent "wakes on a timer, continues working, and commits results"; a background
# worker that disappears on deploy is the opposite of autonomous, and the user
# gets no signal at all -- the list is simply empty, indistinguishable from
# never having created one.
LOOPS_PATH = ROOT / 'memory' / 'loops.json'

# Fields that define a loop. Runtime counters (run_count, history, last_*) are
# persisted too so the history pane survives a restart.
_PERSIST_FIELDS = (
    'id', 'prompt', 'interval_minutes', 'agent_id', 'target', 'goal_id',
    'max_runs', 'kill_after_success', 'created_at', 'run_count',
    'last_run_at', 'last_error', 'history', 'status',
)


def _save_loops() -> None:
    """Write the user loop registry to disk. Never raises into a caller."""
    try:
        LOOPS_PATH.parent.mkdir(parents=True, exist_ok=True)
        payload = {
            jid: {k: v for k, v in meta.items() if k in _PERSIST_FIELDS}
            for jid, meta in _jobs.items()
            if jid not in _BUILTIN_JOB_IDS
        }
        tmp = LOOPS_PATH.with_suffix('.json.tmp')
        tmp.write_text(json.dumps(payload, indent=2))
        tmp.replace(LOOPS_PATH)
    except Exception as e:  # pragma: no cover - disk failure
        log.error('Could not persist loops to %s: %s', LOOPS_PATH, e)


def _load_persisted_loops() -> dict:
    try:
        if LOOPS_PATH.exists():
            data = json.loads(LOOPS_PATH.read_text())
            if isinstance(data, dict):
                return data
    except Exception as e:
        log.error('Could not read persisted loops from %s: %s', LOOPS_PATH, e)
    return {}


def restore_loops() -> int:
    """Re-register every persisted loop with the scheduler. Returns the count.

    Called from start(). A loop that was paused when the server went down is
    restored paused -- resuming someone's autonomous agent behind their back
    because the process bounced would be worse than leaving it stopped.
    """
    restored = 0
    for job_id, meta in _load_persisted_loops().items():
        try:
            result = add_loop(
                job_id,
                meta.get('prompt', ''),
                int(meta.get('interval_minutes', 15) or 15),
                meta.get('agent_id', 'builder'),
                meta.get('target', 'web'),
                goal_id=meta.get('goal_id', ''),
                max_runs=int(meta.get('max_runs', 0) or 0),
                kill_after_success=bool(meta.get('kill_after_success', False)),
                _persist=False,
            )
            if not result.get('ok'):
                continue
            # Carry the counters forward; add_loop resets them for a new loop.
            _jobs[job_id].update({
                'run_count': int(meta.get('run_count', 0) or 0),
                'last_run_at': meta.get('last_run_at', ''),
                'last_error': meta.get('last_error', ''),
                'history': meta.get('history', []) or [],
                'created_at': meta.get('created_at') or _jobs[job_id]['created_at'],
            })
            if meta.get('status') == 'paused':
                sched = get_scheduler()
                if sched:
                    with contextlib.suppress(Exception):
                        sched.pause_job(job_id)
                _jobs[job_id]['status'] = 'paused'
            restored += 1
        except Exception as e:
            log.error('Could not restore loop %s: %s', job_id, e)
    if restored:
        log.info('Restored %d autonomous loop(s) from %s', restored, LOOPS_PATH)
    return restored


def get_scheduler():
    """Retrieve and return get scheduler."""
    global _scheduler
    if _scheduler is None:
        try:
            from apscheduler.executors.asyncio import AsyncIOExecutor
            from apscheduler.schedulers.asyncio import AsyncIOScheduler

            _scheduler = AsyncIOScheduler(
                executors={'default': AsyncIOExecutor()},
                job_defaults={'coalesce': True, 'max_instances': 1, 'misfire_grace_time': 60},
            )
        except ImportError:
            log.warning('APScheduler not installed — autonomous loops disabled')
    return _scheduler


def start():
    """Start the scheduler. Called from app startup."""
    sched = get_scheduler()
    if sched is None:
        return
    if not sched.running:
        try:
            # Built-in periodic jobs
            sched.add_job(_memory_auto_index, 'interval', minutes=30, id='memory_index', replace_existing=True)
            sched.add_job(_daily_standup, 'cron', hour=8, minute=0, id='standup', replace_existing=True)
            sched.add_job(_cost_digest, 'interval', hours=6, id='cost_digest', replace_existing=True)
            sched.add_job(_agent_status_cleanup, 'interval', minutes=5, id='status_cleanup', replace_existing=True)
            sched.start()
            # Bring back the user's loops before announcing we are active.
            restore_loops()
            log.info('Scheduler started — autonomous loops active')
        except Exception as e:
            log.error('Scheduler start failed: %s', e)


def stop():
    """Execute or process stop operation."""
    sched = get_scheduler()
    if sched and sched.running:
        sched.shutdown(wait=False)


# ── Job: add a custom loop ────────────────────────────────────────────────────
def add_loop(
    job_id: str,
    prompt: str,
    interval_minutes: int = 15,
    agent_id: str = 'builder',
    target: str = 'web',
    goal_id: str = '',
    max_runs: int = 0,  # 0 = unlimited
    kill_after_success: bool = False,
    _persist: bool = True,
) -> dict:
    """Create and initialize a new loop."""
    sched = get_scheduler()
    if sched is None:
        return {'ok': False, 'error': 'Scheduler not available (install apscheduler)'}
    try:

        async def _loop():
            meta = _jobs.get(job_id, {})
            # Kill-switch: max_runs check
            max_r = meta.get('max_runs', 0)
            run_c = meta.get('run_count', 0)
            if max_r > 0 and run_c >= max_r:
                log.info('Loop %s reached max_runs=%d — auto-removing', job_id, max_r)
                remove_loop(job_id)
                return
            await _run_goal_loop(job_id, prompt, agent_id, target)
            meta = _jobs.get(job_id, {})
            # BUG FIX: the max_runs check above runs BEFORE an iteration, so a
            # loop with max_runs=N ran N times and then sat scheduled until its
            # N+1th wake-up before removing itself. With interval=1440 that is a
            # day of a "finished" loop still listed as running. Retire it as
            # soon as the budget is spent.
            if max_r > 0 and meta.get('run_count', 0) >= max_r:
                log.info('Loop %s spent its max_runs=%d budget — auto-removing', job_id, max_r)
                remove_loop(job_id)
                return
            # BUG FIX: kill_after_success was accepted, stored and never read by
            # anything. A loop told to stop after its first successful iteration
            # ran forever. `last_error` is cleared by a successful iteration and
            # set by a failing one, so it is the success signal.
            if meta.get('kill_after_success') and not meta.get('last_error'):
                log.info('Loop %s succeeded and kill_after_success is set — auto-removing', job_id)
                remove_loop(job_id)
                return
            # Broadcast loop fired
            try:
                from ..routers.websocket import broadcast

                asyncio.ensure_future(
                    broadcast(
                        {
                            'type': 'loop_fired',
                            'job_id': job_id,
                            'run_count': _jobs.get(job_id, {}).get('run_count', 0),
                            'agent_id': agent_id,
                            'prompt_preview': prompt[:80],
                        }
                    )
                )
            except (KeyError, TypeError, ValueError, json.JSONDecodeError, OSError, AttributeError, RuntimeError):
                pass

        sched.add_job(
            _loop,
            'interval',
            minutes=max(1, min(interval_minutes, 10080)),
            id=job_id,
            replace_existing=True,
        )
        _jobs[job_id] = {
            'id': job_id,
            'prompt': prompt,
            'interval_minutes': interval_minutes,
            'agent_id': agent_id,
            'target': target,
            'status': 'running',
            'goal_id': goal_id,
            'max_runs': max_runs,
            'kill_after_success': kill_after_success,
            'created_at': datetime.datetime.now().isoformat(),
            'run_count': 0,
        }
        if _persist:
            _save_loops()
        log.info('Loop added: %s every %dmin (agent=%s goal=%s)', job_id, interval_minutes, agent_id, goal_id or 'none')
        return {
            'ok': True,
            'job_id': job_id,
            'max_runs': max_runs,
            'kill_after_success': kill_after_success,
            'interval_minutes': interval_minutes,
        }
    except Exception as e:
        return {'ok': False, 'error': str(e)}


def remove_loop(job_id: str) -> dict:
    """Delete or remove specified remove loop."""
    sched = get_scheduler()
    existed = job_id in _jobs

    # BUG FIX, two of them.
    #
    # 1. APScheduler raises JobLookupError when the job is not registered, so
    #    deleting a loop that had already stopped returned
    #    {'ok': False, 'error': "'No job by the id of X was found'"} -- and the
    #    router passed that straight out with HTTP 200. A DELETE of something
    #    already gone is a SUCCESS: the caller asked for it to not exist, and
    #    it does not. It is now reported as such.
    #
    # 2. `_jobs.pop` was inside the try, AFTER the call that raises. So on that
    #    same path the local registry was never cleaned up: the job stayed
    #    listed in /api/loops forever, and every retry hit the same error. The
    #    pop now happens regardless.
    error: str | None = None
    if sched:
        try:
            sched.remove_job(job_id)
        except Exception as exc:  # JobLookupError and anything else
            message = str(exc)
            # Only a genuine failure is reported; "no such job" is the
            # idempotent case.
            if 'No job by the id' not in message:
                error = message

    _jobs.pop(job_id, None)
    _save_loops()

    if error:
        return {'ok': False, 'error': error}
    return {'ok': True, 'deleted': existed, 'job_id': job_id}


_BUILTIN_JOB_IDS = frozenset({'memory_index', 'standup', 'cost_digest', 'status_cleanup'})


def list_loops() -> list[dict]:
    """Retrieve and return list loops."""
    sched = get_scheduler()
    result = []
    if sched:
        for job in sched.get_jobs():
            # Skip built-in system jobs — they are not user-managed loops
            if job.id in _BUILTIN_JOB_IDS:
                continue
            info = _jobs.get(job.id, {})
            # BUG FIX: `job.next_run_time` only exists once the scheduler has
            # STARTED -- APScheduler adds the attribute when it schedules the
            # job. If start() failed (it swallows its exception and logs) or the
            # process is still booting, this raised AttributeError and the whole
            # of GET /api/loops answered HTTP 500. The one moment a user most
            # needs to see their autonomous loops -- the scheduler is broken --
            # is exactly when the listing died. A paused job has the attribute
            # set to None, so getattr's default correctly reads "not scheduled".
            raw_next = getattr(job, 'next_run_time', None)
            next_run = raw_next.isoformat() if raw_next else None
            # Detect paused state: APScheduler sets next_run_time=None for paused jobs
            is_paused = raw_next is None
            result.append(
                {
                    'id': job.id,
                    'next_run': next_run,
                    'prompt': info.get('prompt', ''),
                    'interval_minutes': info.get('interval_minutes', 0),
                    'agent_id': info.get('agent_id', ''),
                    'target': info.get('target', ''),
                    'run_count': info.get('run_count', 0),
                    'status': 'paused' if is_paused else 'running',
                    'created_at': info.get('created_at', ''),
                    'last_run_at': info.get('last_run_at', ''),
                    'last_error': info.get('last_error', ''),
                    # Surfaced so the UI can show a loop's stopping condition.
                    # These were stored and never sent, so a bounded loop was
                    # indistinguishable from an unbounded one on screen.
                    'max_runs': info.get('max_runs', 0),
                    'kill_after_success': bool(info.get('kill_after_success', False)),
                }
            )
    return result


# ── Built-in jobs ─────────────────────────────────────────────────────────────
async def _memory_auto_index():
    """Re-index FTS every 30 minutes."""
    try:
        from .memory_db import get_conn

        con = get_conn()
        try:
            con.execute("INSERT INTO memory_fts(memory_fts) VALUES('rebuild')")
            con.commit()
        finally:
            con.close()
        log.info('Memory FTS auto-indexed')
    except Exception as e:
        log.warning('Memory index failed: %s', e)


async def _daily_standup():
    """Generate a daily standup summary at 8am."""
    try:
        from .memory_db import get_conn, memory_add

        con = get_conn()
        try:
            # Gather yesterday's tasks
            tasks = con.execute(
                "SELECT title, status, agent FROM tasks WHERE updated_at >= date('now', '-1 day') ORDER BY updated_at DESC LIMIT 10"
            ).fetchall()
            cost_row = con.execute("SELECT SUM(cost) FROM chat_log WHERE created_at >= date('now','-1 day')").fetchone()
        finally:
            con.close()

        lines = [f'- [{t["status"].upper()}] {t["title"]} ({t["agent"]})' for t in tasks]
        cost = cost_row[0] or 0.0

        summary = (
            f'**Daily Standup — {datetime.date.today()}**\n\n'
            f'**Yesterday ({len(tasks)} tasks moved):**\n' + ('\n'.join(lines) or '- No tasks moved') + '\n\n'
            f'**LLM Cost:** ${cost:.4f}\n'
            f'**Autonomous loops:** {len(_jobs)} running\n'
        )
        memory_add('standup', summary, 'standup,daily,auto')
        log.info('Daily standup generated')
    except Exception as e:
        log.warning('Standup failed: %s', e)


async def _cost_digest():
    """Log cost summary every 6 hours."""
    try:
        from .memory_db import get_conn

        con = get_conn()
        try:
            row = con.execute('SELECT SUM(tokens) as t, SUM(cost) as c FROM chat_log').fetchone()
        finally:
            con.close()
        log.info('Cost digest: %d tokens, $%.4f', row['t'] or 0, row['c'] or 0.0)
    except Exception as e:
        log.warning('Cost digest failed: %s', e)


async def _agent_status_cleanup():
    """Reset stuck 'working' agents to 'idle' after 10 minutes."""
    try:
        from .memory_db import get_conn

        con = get_conn()
        try:
            con.execute(
                "UPDATE agents SET status='idle' WHERE status='working' AND updated_at < datetime('now', '-10 minutes')"
            )
            con.commit()
        finally:
            con.close()
    except Exception as e:
        log.warning('Status cleanup failed: %s', e)


async def _run_goal_loop(job_id: str, prompt: str, agent_id: str, target: str):
    """Execute one iteration of a /goal --watch loop."""
    if job_id in _jobs:
        _jobs[job_id]['run_count'] = _jobs[job_id].get('run_count', 0) + 1
    try:
        from .llm import NO_PROVIDER_MESSAGE, complete
        from .llm import is_stub as llm_is_stub
        from .memory_db import audit_log, memory_add

        messages = [
            {
                'role': 'system',
                'content': 'You are an autonomous agent in Agentic OS. '
                'Continue working on the assigned goal. Be concise and action-oriented. '
                'Output a brief status update of what you did this iteration.',
            },
            {
                'role': 'user',
                'content': f'Goal: {prompt}\n\nIteration {_jobs.get(job_id, {}).get("run_count", 1)} — '
                f'continue working. Check current state and take the next step.',
            },
        ]
        # Background loop: no HTTP response exists to carry a 503, so take the
        # placeholder explicitly and record the iteration as an error rather
        # than logging setup help as if it were the agent's work product.
        result = await complete(
            messages, agent_id=agent_id, max_tokens=512, inject_steering=False, allow_stub=True
        )
        if llm_is_stub(result):
            raise RuntimeError(NO_PROVIDER_MESSAGE)
        output = result.get('text', '')
        if output:
            memory_add(f'loop:{job_id}', output[:600], f'loop,auto,{agent_id}')
            audit_log('loop_run', f'{job_id}: iter {_jobs.get(job_id, {}).get("run_count", 1)}')
            log.info('Loop %s iter complete: %s', job_id, output[:80])
        if job_id in _jobs:
            _jobs[job_id]['last_run_at'] = datetime.datetime.now().isoformat()
            _jobs[job_id].pop('last_error', None)
            _jobs[job_id].setdefault('history', []).append({
                'iteration': _jobs[job_id].get('run_count', 1),
                'timestamp': datetime.datetime.now().isoformat(),
                'output': output[:600],
                'status': 'success',
            })
            if len(_jobs[job_id]['history']) > 50:
                _jobs[job_id]['history'] = _jobs[job_id]['history'][-50:]
            _save_loops()
    except Exception as e:
        log.error('Goal loop %s failed: %s', job_id, e)
        if job_id in _jobs:
            _jobs[job_id]['last_error'] = str(e)
            _jobs[job_id]['last_run_at'] = datetime.datetime.now().isoformat()
            _jobs[job_id].setdefault('history', []).append({
                'iteration': _jobs[job_id].get('run_count', 1),
                'timestamp': datetime.datetime.now().isoformat(),
                'output': f'Error: {e}',
                'status': 'error',
            })
            if len(_jobs[job_id]['history']) > 50:
                _jobs[job_id]['history'] = _jobs[job_id]['history'][-50:]
            _save_loops()


async def run_loop_now(job_id: str) -> dict:
    """Manually trigger immediate execution of a specific loop."""
    if job_id not in _jobs:
        return {'ok': False, 'error': f"Loop '{job_id}' not found"}
    job_info = _jobs[job_id]
    await _run_goal_loop(
        job_id,
        job_info.get('prompt', ''),
        job_info.get('agent_id', 'builder'),
        job_info.get('target', 'web'),
    )
    return {'ok': True, 'message': f"Loop '{job_id}' triggered immediately", 'job': _jobs.get(job_id)}


def set_loop_status(job_id: str, status: str) -> None:
    """Record a pause/resume so a restart does not silently restart the loop."""
    if job_id in _jobs:
        _jobs[job_id]['status'] = status
        _save_loops()


def get_loop_history(job_id: str) -> dict:
    """Retrieve execution history for a specific loop."""
    if job_id not in _jobs:
        return {'ok': False, 'error': f"Loop '{job_id}' not found"}
    return {
        'ok': True,
        'job_id': job_id,
        'run_count': _jobs[job_id].get('run_count', 0),
        'last_run_at': _jobs[job_id].get('last_run_at'),
        'history': _jobs[job_id].get('history', []),
    }
