"""
Agentic OS — Agent Control Tower
The #1 enterprise differentiator: live observability, kill switch, budget guardrails.
Every agent run gets a trace with per-step cost/token/latency breakdown.
Kill any agent instantly. Set budget limits. View real-time execution logs.

PASS-1 AUDIT FIXES:
  - ROOT: parents[2] (was parents[3])
  - All get_conn() calls wrapped in try/finally: con.close()
"""

from __future__ import annotations

import asyncio
import json
import logging
import time
import uuid

from fastapi import APIRouter, Request
from fastapi.responses import JSONResponse, StreamingResponse

from ..services.memory_db import audit_log, get_conn

router = APIRouter(prefix='/api/control', tags=['control-tower'])
log = logging.getLogger('agentic.control')

from backend.config import get_data_dir

from ..services.request_body import as_text, json_body_or_error

ROOT = get_data_dir()

# ── In-memory run registry ─────────────────────────────────────────────────────
_active_runs: dict[str, dict] = {}
_kill_flags: set[str] = set()
_run_queues: dict[str, asyncio.Queue] = {}


# ── Schema ─────────────────────────────────────────────────────────────────────
def _ensure_traces_table():
    con = get_conn()
    try:
        con.execute("""
            CREATE TABLE IF NOT EXISTS agent_traces (
                id          INTEGER PRIMARY KEY,
                run_id      TEXT NOT NULL,
                agent_id    TEXT,
                agent_name  TEXT,
                prompt      TEXT,
                status      TEXT DEFAULT 'running',
                total_cost  REAL DEFAULT 0,
                total_tokens INTEGER DEFAULT 0,
                duration_ms INTEGER DEFAULT 0,
                step_count  INTEGER DEFAULT 0,
                error       TEXT,
                created_at  TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                updated_at  TIMESTAMP DEFAULT CURRENT_TIMESTAMP
            )
        """)
        con.execute("""
            CREATE TABLE IF NOT EXISTS agent_trace_steps (
                id          INTEGER PRIMARY KEY,
                run_id      TEXT NOT NULL,
                step_no     INTEGER,
                step_type   TEXT,
                name        TEXT,
                input_text  TEXT,
                output_text TEXT,
                model       TEXT,
                tokens_in   INTEGER DEFAULT 0,
                tokens_out  INTEGER DEFAULT 0,
                cost        REAL DEFAULT 0,
                duration_ms INTEGER DEFAULT 0,
                status      TEXT DEFAULT 'done',
                created_at  TIMESTAMP DEFAULT CURRENT_TIMESTAMP
            )
        """)
        con.execute("""
            CREATE TABLE IF NOT EXISTS budget_rules (
                id          INTEGER PRIMARY KEY,
                name        TEXT,
                agent_id    TEXT DEFAULT '*',
                max_cost    REAL DEFAULT 1.0,
                max_tokens  INTEGER DEFAULT 100000,
                action      TEXT DEFAULT 'stop',
                enabled     INTEGER DEFAULT 1,
                created_at  TIMESTAMP DEFAULT CURRENT_TIMESTAMP
            )
        """)
        con.execute("""
            CREATE TABLE IF NOT EXISTS notifications (
                id          INTEGER PRIMARY KEY,
                type        TEXT,
                title       TEXT,
                body        TEXT,
                run_id      TEXT,
                read_at     TIMESTAMP,
                created_at  TIMESTAMP DEFAULT CURRENT_TIMESTAMP
            )
        """)
        con.commit()
    finally:
        con.close()


_ensure_traces_table()

def reconcile_orphaned_runs() -> int:
    """Mark agent_traces rows abandoned by a restart as failed. Returns count.

    `_active_runs` is an in-memory dict and agent_traces.status DEFAULTS to
    'running', so a run in flight when the process stopped stayed 'running' in
    the database forever -- nothing owned it across the restart and nothing
    swept it afterwards. Reproduced: start_run() then discarding the process
    leaves a permanently-'running' row the Control Tower still shows as active.

    Same fix and same reasoning as supervisor.reconcile_orphaned_runs(): a run
    the UI reports as in-progress, for a process that no longer exists, makes
    an operator wait indefinitely for something that will never finish.

    Never raises -- housekeeping must not block startup.
    """
    try:
        con = get_conn()
        try:
            rows = con.execute(
                "SELECT run_id FROM agent_traces WHERE status='running'"
            ).fetchall()
            if not rows:
                return 0
            run_ids = [r['run_id'] for r in rows]
            con.execute(
                """UPDATE agent_traces
                      SET status='failed',
                          error='Interrupted by a server restart - not resumable.'
                    WHERE status='running'"""
            )
            con.commit()
        finally:
            con.close()
        log.warning(
            'Reconciled %d Control Tower run(s) orphaned by a restart: %s',
            len(run_ids), ', '.join(run_ids[:10]),
        )
        return len(run_ids)
    except Exception as exc:  # noqa: BLE001 - never block startup on housekeeping
        log.error('Control Tower run reconciliation failed: %s', exc)
        return 0


reconcile_orphaned_runs()


# ── Run lifecycle ──────────────────────────────────────────────────────────────
def start_run(agent_id: str, agent_name: str, prompt: str, budget: float = 0) -> str:
    """Register a new agent run. Returns run_id."""
    run_id = f'run_{uuid.uuid4().hex[:12]}'
    _active_runs[run_id] = {
        'run_id': run_id,
        'agent_id': agent_id,
        'agent_name': agent_name,
        'prompt': prompt[:500],
        'status': 'running',
        'total_cost': 0.0,
        'total_tokens': 0,
        'step_count': 0,
        'steps': [],
        'budget': budget,
        'start_time': time.time(),
        'duration_ms': 0,
    }
    _run_queues[run_id] = asyncio.Queue(maxsize=500)
    con = get_conn()
    try:
        con.execute(
            'INSERT INTO agent_traces(run_id,agent_id,agent_name,prompt) VALUES(?,?,?,?)',
            (run_id, agent_id, agent_name, prompt[:500]),
        )
        con.commit()
    finally:
        con.close()
    _broadcast(run_id, {'type': 'run_started', 'run_id': run_id, 'agent': agent_name})
    return run_id


def record_step(
    run_id: str,
    step_type: str,
    name: str,
    input_text: str = '',
    output_text: str = '',
    model: str = '',
    tokens_in: int = 0,
    tokens_out: int = 0,
    cost: float = 0.0,
    duration_ms: int = 0,
    status: str = 'done',
):
    """Record a step in a run's trace."""
    if run_id not in _active_runs:
        return False
    if run_id in _kill_flags:
        return False

    run = _active_runs[run_id]
    step_no = len(run['steps']) + 1
    step = {
        'step_no': step_no,
        'step_type': step_type,
        'name': name,
        'input_text': input_text[:500],
        'output_text': output_text[:1000],
        'model': model,
        'tokens_in': tokens_in,
        'tokens_out': tokens_out,
        'cost': cost,
        'duration_ms': duration_ms,
        'status': status,
    }
    run['steps'].append(step)
    run['total_cost'] += cost
    run['total_tokens'] += tokens_in + tokens_out
    run['step_count'] += 1

    # Check per-run budget
    budget = run.get('budget', 0)
    if budget > 0 and run['total_cost'] >= budget:
        _kill_flags.add(run_id)
        log.warning('Budget exceeded for run %s: $%.4f >= $%.4f', run_id, run['total_cost'], budget)
        _push_notification(
            'budget_alert',
            'Budget limit hit',
            f'Run {run_id} stopped: ${run["total_cost"]:.4f} ≥ ${budget:.4f}',
            run_id,
        )
        return False

    # Check global budget rules
    con = get_conn()
    try:
        rules = con.execute(
            "SELECT * FROM budget_rules WHERE enabled=1 AND (agent_id=? OR agent_id='*')", (run.get('agent_id', ''),)
        ).fetchall()
    finally:
        con.close()

    for rule in rules:
        if run['total_cost'] >= rule['max_cost']:
            if rule['action'] == 'stop':
                _kill_flags.add(run_id)
                return False
            elif rule['action'] == 'warn':
                _broadcast(run_id, {'type': 'budget_warning', 'rule': dict(rule), 'run_id': run_id})

    # Persist step
    try:
        con = get_conn()
        try:
            con.execute(
                """INSERT INTO agent_trace_steps
                   (run_id,step_no,step_type,name,input_text,output_text,model,tokens_in,tokens_out,cost,duration_ms,status)
                   VALUES(?,?,?,?,?,?,?,?,?,?,?,?)""",
                (
                    run_id,
                    step_no,
                    step_type,
                    name,
                    input_text[:500],
                    output_text[:1000],
                    model,
                    tokens_in,
                    tokens_out,
                    cost,
                    duration_ms,
                    status,
                ),
            )
            con.commit()
        finally:
            con.close()
    except (KeyError, TypeError, ValueError, json.JSONDecodeError, OSError, AttributeError):
        pass

    _broadcast(run_id, {'type': 'step', 'run_id': run_id, 'step': step})
    return run_id not in _kill_flags


def finish_run(run_id: str, status: str = 'done', error: str = ''):
    """Mark a run as complete."""
    if run_id not in _active_runs:
        return
    run = _active_runs[run_id]
    run['status'] = status
    run['duration_ms'] = round((time.time() - run['start_time']) * 1000)
    run['error'] = error

    con = get_conn()
    try:
        con.execute(
            """UPDATE agent_traces SET status=?,total_cost=?,total_tokens=?,
               duration_ms=?,step_count=?,error=?,updated_at=CURRENT_TIMESTAMP WHERE run_id=?""",
            (
                status,
                run['total_cost'],
                run['total_tokens'],
                run['duration_ms'],
                run['step_count'],
                error[:500] if error else '',
                run_id,
            ),
        )
        con.commit()
    finally:
        con.close()

    _broadcast(
        run_id,
        {
            'type': 'run_complete',
            'run_id': run_id,
            'status': status,
            'cost': run['total_cost'],
            'tokens': run['total_tokens'],
            'duration_ms': run['duration_ms'],
        },
    )
    _kill_flags.discard(run_id)
    _run_queues.pop(run_id, None)
    _active_runs.pop(run_id, None)

    if status == 'done':
        _push_notification(
            'run_complete',
            f'✅ Run complete — {run["agent_name"]}',
            f'{run["step_count"]} steps · ${run["total_cost"]:.4f} · {run["duration_ms"]}ms',
            run_id,
        )
    elif status == 'error':
        _push_notification('error', f'❌ Run failed — {run["agent_name"]}', error[:200], run_id)


def is_killed(run_id: str) -> bool:
    """Execute or process is killed operation."""
    return run_id in _kill_flags


def _broadcast(run_id: str, event: dict):
    q = _run_queues.get(run_id)
    if q:
        try:
            q.put_nowait(event)
        except asyncio.QueueFull:
            pass


def _push_notification(notif_type: str, title: str, body: str, run_id: str = ''):
    try:
        con = get_conn()
        try:
            con.execute(
                'INSERT INTO notifications(type,title,body,run_id) VALUES(?,?,?,?)',
                (notif_type, title[:120], body[:500], run_id),
            )
            con.commit()
        finally:
            con.close()
        import asyncio as _aio

        from .websocket import manager

        try:
            loop = _aio.get_event_loop()
            if loop.is_running():
                loop.create_task(
                    manager.broadcast(
                        {
                            'type': 'notification',
                            'notif_type': notif_type,
                            'title': title,
                            'body': body,
                            'run_id': run_id,
                            'ts': time.time(),
                        }
                    )
                )
        except (KeyError, TypeError, ValueError, json.JSONDecodeError, OSError):
            pass
    except Exception as e:
        log.warning('Failed to push notification: %s', e)


# ── Endpoints ──────────────────────────────────────────────────────────────────
@router.get('/runs')
def list_runs(status: str = '', limit: int = 50):
    """Retrieve and return list runs."""
    con = get_conn()
    try:
        if status:
            rows = con.execute(
                'SELECT * FROM agent_traces WHERE status=? ORDER BY created_at DESC LIMIT ?', (status, max(1, min(limit, 200)))
            ).fetchall()
        else:
            rows = con.execute(
                'SELECT * FROM agent_traces ORDER BY created_at DESC LIMIT ?', (max(1, min(limit, 200)),)
            ).fetchall()
    finally:
        con.close()
    result = [dict(r) for r in rows]
    for run_id, run in list(_active_runs.items()):
        if not any(r['run_id'] == run_id for r in result):
            result.insert(0, {**run, 'created_at': time.strftime('%Y-%m-%d %H:%M:%S')})
    return result


@router.get('/runs/{run_id}')
def get_run(run_id: str):
    """Retrieve and return get run."""
    if run_id in _active_runs:
        run = dict(_active_runs[run_id])
        return {'run': run, 'steps': run.get('steps', []), 'active': True}
    con = get_conn()
    try:
        run = con.execute('SELECT * FROM agent_traces WHERE run_id=?', (run_id,)).fetchone()
        steps = con.execute('SELECT * FROM agent_trace_steps WHERE run_id=? ORDER BY step_no', (run_id,)).fetchall()
    finally:
        con.close()
    if not run:
        return JSONResponse({'ok': False, 'error': 'Run not found'}, status_code=404)
    return {'run': dict(run), 'steps': [dict(s) for s in steps], 'active': False}


@router.get('/runs/{run_id}/stream')
async def stream_run(run_id: str, request: Request):
    """Stream real-time responses or events for run."""
    q = _run_queues.get(run_id)
    if not q:

        async def static():
            """Execute or process static operation."""
            yield f'data: {json.dumps({"type": "not_active", "run_id": run_id})}\n\n'

        return StreamingResponse(static(), media_type='text/event-stream')

    async def generate():
        """Execute or process generate operation."""
        try:
            yield f'data: {json.dumps({"type": "connected", "run_id": run_id})}\n\n'
            while True:
                if await request.is_disconnected():
                    break
                try:
                    event = await asyncio.wait_for(q.get(), timeout=10.0)
                    yield f'data: {json.dumps(event, default=str)}\n\n'
                    if event.get('type') == 'run_complete':
                        break
                except asyncio.TimeoutError:
                    yield 'data: {"type":"ping"}\n\n'
        except (KeyError, TypeError, ValueError, json.JSONDecodeError, OSError):
            pass

    return StreamingResponse(
        generate(), media_type='text/event-stream', headers={'Cache-Control': 'no-cache', 'X-Accel-Buffering': 'no'}
    )


@router.post('/runs/{run_id}/kill')
async def kill_run(run_id: str, req: Request):
    """Stop an active run. Refuses ids that are not currently running.

    TWO BUGS, both verified:

    1. Reported success for a run that never existed:
           POST /api/control/runs/nonexistent_run/kill
           -> {"ok": true, "run_id": "nonexistent_run", "status": "killed"}
       Nothing was killed. This is the Module 15 "reporting success while doing
       nothing" pattern -- an operator hitting the kill switch on a runaway
       agent gets the same green answer whether or not anything stopped, which
       is exactly the moment they most need the truth.

    2. Worse, the flag LEAKED PERMANENTLY. `_kill_flags.add(run_id)` ran
       unconditionally, but `finish_run()` -- the only place that discards the
       flag -- returns immediately when the run is not in `_active_runs`. So an
       unknown id left a tombstone in an unbounded in-memory set forever.
       Proven: after killing 'run_ghost', creating a real run with that id and
       calling record_step() returned False -- dead on arrival, because
       record_step() checks `run_id in _kill_flags` before doing anything.
       Run ids are `run_<uuid4[:12]>` so a natural collision is remote, but a
       replayed or user-supplied id is not, and the set grows without bound
       from typos and stale UI retries regardless.

    The flag is now only set for a run that is actually active, so it is always
    paired with the finish_run() that clears it.
    """
    run = _active_runs.get(run_id)
    if not run:
        return JSONResponse(
            {
                'ok': False,
                'error': 'No active run with that id — it may have already finished.',
                'run_id': run_id,
            },
            status_code=404,
        )

    _kill_flags.add(run_id)
    finish_run(run_id, 'killed', 'Killed by user')
    audit_log('kill_run', run_id)
    log.warning('Run %s killed by user', run_id)
    _push_notification('system', '🛑 Run killed', f'Run {run_id} was stopped by user', run_id)
    return {'ok': True, 'run_id': run_id, 'status': 'killed'}


@router.post('/runs/kill-all')
async def kill_all_runs():
    """Execute or process kill all runs operation."""
    count = 0
    for run_id in list(_active_runs.keys()):
        if _active_runs[run_id].get('status') == 'running':
            _kill_flags.add(run_id)
            finish_run(run_id, 'killed', 'Killed by global kill switch')
            count += 1
    audit_log('kill_all_runs', f'{count} runs stopped')
    return {'ok': True, 'killed': count}


@router.get('/active')
def active_runs():
    """Execute or process active runs operation."""
    return [run for run in _active_runs.values() if run.get('status') == 'running']


@router.get('/stats')
def control_stats():
    """Execute or process control stats operation."""
    con = get_conn()
    try:
        total = con.execute('SELECT COUNT(*) FROM agent_traces').fetchone()[0]
        running = len([r for r in _active_runs.values() if r.get('status') == 'running'])
        cost_row = con.execute('SELECT SUM(total_cost) as c, SUM(total_tokens) as t FROM agent_traces').fetchone()
        errors = con.execute("SELECT COUNT(*) FROM agent_traces WHERE status='error'").fetchone()[0]
        killed = con.execute("SELECT COUNT(*) FROM agent_traces WHERE status='killed'").fetchone()[0]
        today = con.execute(
            "SELECT COUNT(*),SUM(total_cost) FROM agent_traces WHERE date(created_at)=date('now')"
        ).fetchone()
    finally:
        con.close()
    return {
        'total_runs': total,
        'active_runs': running,
        'total_cost': round(cost_row['c'] or 0, 6),
        'total_tokens': cost_row['t'] or 0,
        'error_count': errors,
        'killed_count': killed,
        'today_runs': today[0] or 0,
        'today_cost': round(today[1] or 0, 6),
        'kill_available': running > 0,
    }


# ── Budget rules ───────────────────────────────────────────────────────────────
@router.get('/budget-rules')
def list_budget_rules():
    """Retrieve and return list budget rules."""
    con = get_conn()
    try:
        rows = con.execute('SELECT * FROM budget_rules ORDER BY id').fetchall()
        try:
            live = {
                r['cap_id']: r
                for r in con.execute(
                    "SELECT cap_id, on_breach, enabled FROM budget_caps WHERE cap_id LIKE 'ctrl_rule_%'"
                ).fetchall()
            }
        except Exception:
            live = {}
    finally:
        con.close()
    out = []
    for r in rows:
        d = dict(r)
        cap = live.get(f'ctrl_rule_{d["id"]}')
        # `enforced` is measured against the table that actually gates spending,
        # not inferred from the rule's own `action`. If the mirror is missing
        # the rule is inert, and the UI must be able to say so.
        d['enforced'] = bool(cap and cap['enabled'] and cap['on_breach'] == 'pause')
        out.append(d)
    return out


_RULE_ACTIONS = ('stop', 'warn', 'notify')


def _coerce_limit(value, default, kind):
    """Coerce a budget limit, or return None to signal a bad value.

    `float(body.get('max_cost', 1.0))` raised ValueError on any non-numeric
    input and took the endpoint out with HTTP 500 -- verified with
    {"max_cost": "abc"}. And nothing checked the sign, so a cap of -5 dollars
    was stored happily: a limit that can never be satisfied, configured by
    someone who meant to restrict spending.
    """
    if value is None:
        return default
    try:
        n = float(value) if kind is float else int(value)
    except (TypeError, ValueError):
        return None
    if n < 0:
        return None
    return n


def _sync_rule_to_cap(rule_id: int) -> None:
    """Mirror a Control Tower budget rule into the table that ENFORCES caps.

    THE BUG THIS EXISTS FOR. The platform had two unrelated budget stores:

      * `budget_rules`  — written by this router, rendered by the Control Tower
                          pane, and read by NOTHING. Confirmed by grep across
                          the whole backend: zero readers outside this file.
      * `budget_caps`   — what finops.check_budget_before_spend() actually
                          consults before every LLM call.

    So a user who opened the Control Tower, set "max_cost 0.01, action: stop",
    and saw it listed had configured nothing at all. Verified live: created that
    exact rule, then asked the enforcer directly -> {'allowed': True}. The pane
    that exists to stop runaway spending was decorative.

    Writing through to `budget_caps` is the smaller, safer fix: the enforcement
    logic, its period handling and its fail-open behaviour are already reviewed
    and tested, so this makes the UI drive the real mechanism rather than
    introducing a second enforcement path that could drift again.

    `action` maps onto `on_breach`: 'stop' becomes a hard 'pause' (the enforcer
    denies the spend), while 'warn' and 'notify' become 'alert' (notify-only),
    matching what those words promise.
    """
    con = get_conn()
    try:
        rule = con.execute('SELECT * FROM budget_rules WHERE id=?', (rule_id,)).fetchone()
        if not rule:
            return
        r = dict(rule)
        cap_id = f'ctrl_rule_{rule_id}'
        on_breach = 'pause' if r.get('action') == 'stop' else 'alert'
        scope_type = 'platform' if (r.get('agent_id') or '*') == '*' else 'agent'
        con.execute(
            """INSERT INTO budget_caps
                 (cap_id,name,scope_type,scope_id,period,limit_usd,limit_tokens,on_breach,enabled)
               VALUES (?,?,?,?,'day',?,?,?,?)
               ON CONFLICT(cap_id) DO UPDATE SET
                 name=excluded.name, scope_type=excluded.scope_type, scope_id=excluded.scope_id,
                 limit_usd=excluded.limit_usd, limit_tokens=excluded.limit_tokens,
                 on_breach=excluded.on_breach, enabled=excluded.enabled,
                 updated_at=CURRENT_TIMESTAMP""",
            (
                cap_id,
                r.get('name') or 'Budget limit',
                scope_type,
                r.get('agent_id') or '*',
                float(r.get('max_cost') or 0),
                int(r.get('max_tokens') or 0),
                on_breach,
                int(r.get('enabled', 1) or 0),
            ),
        )
        con.commit()
    except Exception as e:  # pragma: no cover - mirroring must never break CRUD
        log.error('Could not sync budget rule %s into budget_caps: %s', rule_id, e)
    finally:
        con.close()


def _delete_rule_cap(rule_id: int) -> None:
    con = get_conn()
    try:
        con.execute('DELETE FROM budget_caps WHERE cap_id=?', (f'ctrl_rule_{rule_id}',))
        con.commit()
    except Exception as e:  # pragma: no cover
        log.error('Could not remove cap for budget rule %s: %s', rule_id, e)
    finally:
        con.close()


@router.post('/budget-rules')
async def create_budget_rule(req: Request):
    """Create and initialize a new budget rule."""
    body, _body_err = await json_body_or_error(req)
    if _body_err:
        return _body_err
    name = (as_text(body.get('name')) or 'Budget limit')[:80]
    agent_id = str(body.get('agent_id') or '*')[:64]

    max_cost = _coerce_limit(body.get('max_cost'), 1.0, float)
    if max_cost is None:
        return JSONResponse(
            {'ok': False, 'error': 'max_cost must be a non-negative number of dollars'}, status_code=400
        )
    max_tok = _coerce_limit(body.get('max_tokens'), 100000, int)
    if max_tok is None:
        return JSONResponse(
            {'ok': False, 'error': 'max_tokens must be a non-negative whole number'}, status_code=400
        )

    action = body.get('action', 'stop')
    if action not in _RULE_ACTIONS:
        # Silently rewriting an unrecognised action to 'stop' hid typos and made
        # the stored rule disagree with what the caller asked for.
        return JSONResponse(
            {'ok': False, 'error': f"action must be one of {', '.join(_RULE_ACTIONS)}"}, status_code=400
        )

    con = get_conn()
    try:
        cur = con.execute(
            'INSERT INTO budget_rules(name,agent_id,max_cost,max_tokens,action) VALUES(?,?,?,?,?)',
            (name, agent_id, max_cost, max_tok, action),
        )
        rid = cur.lastrowid
        con.commit()
    finally:
        con.close()
    _sync_rule_to_cap(rid)
    return {
        'ok': True,
        'id': rid,
        'enforced': action == 'stop',
        'note': (
            'This rule will block spending once the limit is reached.'
            if action == 'stop'
            else 'This rule only raises an alert; it does not block spending.'
        ),
    }


@router.patch('/budget-rules/{rule_id}')
async def update_budget_rule(rule_id: int, req: Request):
    """Update existing budget rule record or state."""
    body, _body_err = await json_body_or_error(req)
    if _body_err:
        return _body_err
    allowed = {'name', 'agent_id', 'max_cost', 'max_tokens', 'action', 'enabled'}

    # BUG FIX: this wrote body values straight through with no validation at
    # all, so PATCH bypassed every check the create path performs. Verified
    # live: a rule ended up with max_cost='not-a-number' and
    # action='ignore_everything', both stored and listed as if valid. A budget
    # cap holding a string cannot be compared against a number -- the rule is
    # inert and looks configured.
    if 'max_cost' in body:
        v = _coerce_limit(body['max_cost'], None, float)
        if v is None:
            return JSONResponse(
                {'ok': False, 'error': 'max_cost must be a non-negative number of dollars'}, status_code=400
            )
        body['max_cost'] = v
    if 'max_tokens' in body:
        v = _coerce_limit(body['max_tokens'], None, int)
        if v is None:
            return JSONResponse(
                {'ok': False, 'error': 'max_tokens must be a non-negative whole number'}, status_code=400
            )
        body['max_tokens'] = v
    if 'action' in body and body['action'] not in _RULE_ACTIONS:
        return JSONResponse(
            {'ok': False, 'error': f"action must be one of {', '.join(_RULE_ACTIONS)}"}, status_code=400
        )

    sets, vals = [], []
    for k in allowed:
        if k in body:
            sets.append(f'{k}=?')
            vals.append(body[k])
    if not sets:
        return JSONResponse({'ok': False, 'error': 'No updatable fields supplied'}, status_code=400)
    vals.append(rule_id)
    con = get_conn()
    try:
        cur = con.execute(f'UPDATE budget_rules SET {", ".join(sets)} WHERE id=?', vals)
        con.commit()
        changed = cur.rowcount
    finally:
        con.close()
    if not changed:
        return JSONResponse({'ok': False, 'error': f'No budget rule with id {rule_id}'}, status_code=404)
    _sync_rule_to_cap(rule_id)
    return {'ok': True}


@router.delete('/budget-rules/{rule_id}')
def delete_budget_rule(rule_id: int):
    """Delete or remove specified budget rule."""
    con = get_conn()
    try:
        exists = con.execute('SELECT id FROM budget_rules WHERE id=?', (rule_id,)).fetchone()
        con.execute('DELETE FROM budget_rules WHERE id=?', (rule_id,))
        con.commit()
    finally:
        con.close()
    if not exists:
        # Reporting deleted:false with HTTP 200 told status-code-aware clients
        # the delete had succeeded. Same fix already applied to loops and the
        # vault.
        return JSONResponse(
            {'ok': False, 'deleted': False, 'error': f'No budget rule with id {rule_id}'},
            status_code=404,
        )
    # The mirrored cap must go too, or a deleted rule keeps blocking spend.
    _delete_rule_cap(rule_id)
    return {'ok': True, 'deleted': True}


# ── Notifications ──────────────────────────────────────────────────────────────
@router.get('/notifications')
def list_notifications(unread_only: bool = False, limit: int = 50):
    """Retrieve and return list notifications."""
    con = get_conn()
    try:
        if unread_only:
            rows = con.execute(
                'SELECT * FROM notifications WHERE read_at IS NULL ORDER BY id DESC LIMIT ?', (max(1, min(limit, 200)),)
            ).fetchall()
        else:
            rows = con.execute('SELECT * FROM notifications ORDER BY id DESC LIMIT ?', (max(1, min(limit, 200)),)).fetchall()
        unread_count = con.execute('SELECT COUNT(*) FROM notifications WHERE read_at IS NULL').fetchone()[0]
    finally:
        con.close()
    return {'notifications': [dict(r) for r in rows], 'unread_count': unread_count}


@router.post('/notifications/read-all')
def mark_all_read():
    """Execute or process mark all read operation."""
    con = get_conn()
    try:
        con.execute('UPDATE notifications SET read_at=CURRENT_TIMESTAMP WHERE read_at IS NULL')
        con.commit()
    finally:
        con.close()
    return {'ok': True}


@router.patch('/notifications/{notif_id}/read')
def mark_read(notif_id: int):
    """Execute or process mark read operation."""
    con = get_conn()
    try:
        con.execute('UPDATE notifications SET read_at=CURRENT_TIMESTAMP WHERE id=?', (notif_id,))
        con.commit()
    finally:
        con.close()
    return {'ok': True}


@router.delete('/notifications')
def clear_notifications():
    """Delete or remove specified clear notifications."""
    con = get_conn()
    try:
        con.execute('DELETE FROM notifications WHERE read_at IS NOT NULL')
        con.commit()
    finally:
        con.close()
    return {'ok': True}


@router.get('/budget')
def budget_alias():
    """Alias for /budget-rules."""
    con = get_conn()
    try:
        rows = con.execute('SELECT * FROM budget_rules ORDER BY id').fetchall()
    except (KeyError, TypeError, ValueError, json.JSONDecodeError, OSError, AttributeError):
        rows = []
    finally:
        con.close()
    return {'rules': [dict(r) for r in rows], 'count': len(rows)}
