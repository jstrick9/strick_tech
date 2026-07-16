"""
Agentic OS — Sprint B · Feature 2: Goal Manager
════════════════════════════════════════════════
Structured goal lifecycle management:
  - Create goals with deadline, priority, success criteria, assigned agents
  - Decompose goals into specs and tasks
  - Track progress: 0–100% with status transitions
  - Link goals to supervisor runs for autonomous execution
  - Proactive check-ins and progress broadcasting
  - Life domain organization (Work, Health, Finance, Learning, Home, Travel)
"""

from __future__ import annotations

import contextlib

import json
import logging
import uuid
from datetime import datetime, timezone
from pathlib import Path

from fastapi import APIRouter, Request
from fastapi.responses import JSONResponse

router = APIRouter(prefix='/api/goals', tags=['goal-manager'])
log = logging.getLogger('agentic.goals')

from backend.config import get_data_dir
ROOT = get_data_dir()

# ── Schema ─────────────────────────────────────────────────────────────────────
_SCHEMA = """
CREATE TABLE IF NOT EXISTS goals_v2 (
    id              TEXT PRIMARY KEY,
    title           TEXT NOT NULL DEFAULT '',
    description     TEXT NOT NULL DEFAULT '',
    success_criteria TEXT NOT NULL DEFAULT '',
    domain          TEXT NOT NULL DEFAULT 'Work',
    priority        TEXT NOT NULL DEFAULT 'medium',
    status          TEXT NOT NULL DEFAULT 'active',
    progress        INTEGER NOT NULL DEFAULT 0,
    assigned_agents TEXT NOT NULL DEFAULT '[]',
    deadline        TEXT NOT NULL DEFAULT '',
    tags            TEXT NOT NULL DEFAULT '',
    parent_goal_id  TEXT NOT NULL DEFAULT '',
    supervisor_run_id TEXT NOT NULL DEFAULT '',
    spec_id         TEXT NOT NULL DEFAULT '',
    notes           TEXT NOT NULL DEFAULT '',
    created_at      TEXT NOT NULL DEFAULT '',
    updated_at      TEXT NOT NULL DEFAULT '',
    completed_at    TEXT NOT NULL DEFAULT ''
);
CREATE INDEX IF NOT EXISTS idx_goals_status   ON goals_v2(status);
CREATE INDEX IF NOT EXISTS idx_goals_domain   ON goals_v2(domain);
CREATE INDEX IF NOT EXISTS idx_goals_priority ON goals_v2(priority);

CREATE TABLE IF NOT EXISTS goal_milestones (
    id          TEXT PRIMARY KEY,
    goal_id     TEXT NOT NULL,
    title       TEXT NOT NULL DEFAULT '',
    description TEXT NOT NULL DEFAULT '',
    completed   INTEGER NOT NULL DEFAULT 0,
    due_date    TEXT NOT NULL DEFAULT '',
    created_at  TEXT NOT NULL DEFAULT '',
    completed_at TEXT NOT NULL DEFAULT '',
    FOREIGN KEY (goal_id) REFERENCES goals_v2(id)
);
CREATE INDEX IF NOT EXISTS idx_milestones_goal ON goal_milestones(goal_id);

CREATE TABLE IF NOT EXISTS goal_checkins (
    id          INTEGER PRIMARY KEY AUTOINCREMENT,
    goal_id     TEXT NOT NULL,
    agent_id    TEXT NOT NULL DEFAULT 'supervisor',
    note        TEXT NOT NULL DEFAULT '',
    progress    INTEGER NOT NULL DEFAULT 0,
    created_at  TEXT NOT NULL DEFAULT ''
);
CREATE INDEX IF NOT EXISTS idx_checkins_goal ON goal_checkins(goal_id);
"""

DOMAINS = ['Work', 'Health', 'Finance', 'Learning', 'Home', 'Travel', 'Personal', 'Research']
PRIORITIES = ['critical', 'high', 'medium', 'low']
STATUSES = ['active', 'paused', 'done', 'cancelled', 'blocked']


def _get_conn():
    from ..services.memory_db import get_conn

    return get_conn()


def _ensure_schema():
    con = _get_conn()
    try:
        con.executescript(_SCHEMA)
        con.commit()
    finally:
        con.close()


_ensure_schema()


def _now() -> str:
    return datetime.now(timezone.utc).isoformat()


def _goal_dict(row) -> dict:
    d = dict(row)
    try:
        d['assigned_agents'] = json.loads(d.get('assigned_agents', '[]'))
    except (KeyError, TypeError, ValueError, json.JSONDecodeError, OSError, AttributeError, RuntimeError):
        d['assigned_agents'] = []
    return d


# ── Routes ─────────────────────────────────────────────────────────────────────
@router.get('')
def list_goals(
    status: str = '',
    domain: str = '',
    priority: str = '',
    limit: int = 100,
):
    """Retrieve and return list goals."""
    where, params = [], []
    if status:
        where.append('status=?')
        params.append(status)
    if domain:
        where.append('domain=?')
        params.append(domain)
    if priority:
        where.append('priority=?')
        params.append(priority)

    where_sql = ('WHERE ' + ' AND '.join(where)) if where else ''
    params += [min(limit, 500)]

    con = _get_conn()
    try:
        rows = con.execute(
            f"SELECT * FROM goals_v2 {where_sql} ORDER BY CASE priority WHEN 'critical' THEN 0 WHEN 'high' THEN 1 WHEN 'medium' THEN 2 ELSE 3 END, created_at DESC LIMIT ?",
            params,
        ).fetchall()
        total = con.execute(f'SELECT COUNT(*) FROM goals_v2 {where_sql}', params[:-1]).fetchone()[0]
    finally:
        con.close()

    return {'goals': [_goal_dict(r) for r in rows], 'total': total}


@router.post('')
async def create_goal(req: Request):
    """Create and initialize a new goal."""
    try:
        try:
            body = await req.json()
        except (KeyError, TypeError, ValueError, json.JSONDecodeError, OSError, AttributeError, RuntimeError):
            body = {}
    except (KeyError, TypeError, ValueError, json.JSONDecodeError, OSError, AttributeError, RuntimeError):
        return JSONResponse({'ok': False, 'error': 'Invalid JSON'}, status_code=400)

    title = (body.get('title') or '').strip()
    if not title:
        return JSONResponse({'ok': False, 'error': 'title required'}, status_code=400)

    goal_id = f'goal_{uuid.uuid4().hex[:10]}'
    now = _now()

    domain = body.get('domain', 'Work')
    if domain not in DOMAINS:
        domain = 'Work'
    priority = body.get('priority', 'medium')
    if priority not in PRIORITIES:
        priority = 'medium'

    agents = body.get('assigned_agents') or []
    if isinstance(agents, str):
        agents = [a.strip() for a in agents.split(',') if a.strip()]

    con = _get_conn()
    try:
        con.execute(
            """
            INSERT INTO goals_v2
              (id,title,description,success_criteria,domain,priority,status,
               progress,assigned_agents,deadline,tags,parent_goal_id,notes,created_at,updated_at)
            VALUES (?,?,?,?,?,?,?,0,?,?,?,?,?,?,?)
        """,
            (
                goal_id,
                title[:300],
                (body.get('description') or '')[:2000],
                (body.get('success_criteria') or '')[:1000],
                domain,
                priority,
                'active',
                json.dumps(agents),
                (body.get('deadline') or '')[:30],
                (body.get('tags') or '')[:200],
                (body.get('parent_goal_id') or '')[:50],
                (body.get('notes') or '')[:2000],
                now,
                now,
            ),
        )

        # Seed milestones if provided
        for ms in body.get('milestones') or []:
            ms_id = f'ms_{uuid.uuid4().hex[:8]}'
            con.execute(
                """
                INSERT INTO goal_milestones (id,goal_id,title,description,due_date,created_at)
                VALUES (?,?,?,?,?,?)
            """,
                (
                    ms_id,
                    goal_id,
                    (ms.get('title') or 'Milestone')[:200],
                    (ms.get('description') or '')[:500],
                    (ms.get('due_date') or '')[:30],
                    now,
                ),
            )

        con.commit()
    finally:
        con.close()

    # Record in audit log
    try:
        from ..routers.audit_log import append_entry

        append_entry(
            'user',
            'User',
            'goal_created',
            f'Goal: {title}',
            reasoning='User created a new goal',
            authority='user',
            risk_level='low',
            outcome='success',
            metadata={'goal_id': goal_id, 'domain': domain, 'priority': priority},
        )
    except (KeyError, TypeError, ValueError, json.JSONDecodeError, OSError, AttributeError, RuntimeError):
        pass

    log.info('Goal created: %s — %s', goal_id, title)
    return {'ok': True, 'id': goal_id, 'goal_id': goal_id, 'title': title}


@router.get('/{goal_id}')
def get_goal(goal_id: str):
    """Retrieve and return get goal."""
    con = _get_conn()
    try:
        row = con.execute('SELECT * FROM goals_v2 WHERE id=?', (goal_id,)).fetchone()
        if not row:
            return JSONResponse({'ok': False, 'error': 'Goal not found'}, status_code=404)
        milestones = con.execute(
            'SELECT * FROM goal_milestones WHERE goal_id=? ORDER BY created_at', (goal_id,)
        ).fetchall()
        checkins = con.execute(
            'SELECT * FROM goal_checkins WHERE goal_id=? ORDER BY id DESC LIMIT 10', (goal_id,)
        ).fetchall()
    finally:
        con.close()

    g = _goal_dict(row)
    g['milestones'] = [dict(m) for m in milestones]
    g['checkins'] = [dict(c) for c in checkins]
    return {'ok': True, 'goal': g}


@router.patch('/{goal_id}')
async def update_goal(goal_id: str, req: Request):
    """Update existing goal record or state."""
    try:
        try:
            body = await req.json()
        except (KeyError, TypeError, ValueError, json.JSONDecodeError, OSError, AttributeError, RuntimeError):
            body = {}
    except (KeyError, TypeError, ValueError, json.JSONDecodeError, OSError, AttributeError, RuntimeError):
        return JSONResponse({'ok': False, 'error': 'Invalid JSON'}, status_code=400)

    allowed = {
        'title',
        'description',
        'success_criteria',
        'domain',
        'priority',
        'status',
        'progress',
        'deadline',
        'tags',
        'notes',
        'supervisor_run_id',
        'spec_id',
    }
    updates = {}
    for k, v in body.items():
        if k in allowed:
            if k == 'progress':
                updates[k] = max(0, min(100, int(v or 0)))
            elif k == 'status' and v not in STATUSES or k == 'domain' and v not in DOMAINS:
                continue
            else:
                updates[k] = str(v)[:2000] if v is not None else ''

    if not updates:
        return JSONResponse({'ok': False, 'error': 'No valid fields to update'}, status_code=400)

    # Auto-complete if progress hits 100
    if updates.get('progress') == 100 and 'status' not in updates:
        updates['status'] = 'done'
        updates['completed_at'] = _now()

    updates['updated_at'] = _now()

    con = _get_conn()
    try:
        row = con.execute('SELECT id FROM goals_v2 WHERE id=?', (goal_id,)).fetchone()
        if not row:
            return JSONResponse({'ok': False, 'error': 'Goal not found'}, status_code=404)

        sets = ', '.join(f'{k}=?' for k in updates)
        con.execute(f'UPDATE goals_v2 SET {sets} WHERE id=?', list(updates.values()) + [goal_id])
        con.commit()
    finally:
        con.close()

    # Broadcast progress
    try:
        import asyncio

        from ..routers.websocket import broadcast

        asyncio.create_task(
            broadcast(
                {
                    'type': 'goal_updated',
                    'goal_id': goal_id,
                    'progress': updates.get('progress'),
                    'status': updates.get('status'),
                }
            )
        )
    except (KeyError, TypeError, ValueError, json.JSONDecodeError, OSError, AttributeError, RuntimeError):
        pass

    return {'ok': True, 'goal_id': goal_id, 'updated': list(updates.keys())}


@router.delete('/{goal_id}')
def delete_goal(goal_id: str):
    """Delete or remove specified goal."""
    con = _get_conn()
    try:
        con.execute('DELETE FROM goal_milestones WHERE goal_id=?', (goal_id,))
        con.execute('DELETE FROM goal_checkins WHERE goal_id=?', (goal_id,))
        con.execute('DELETE FROM goals_v2 WHERE id=?', (goal_id,))
        con.commit()
    finally:
        con.close()
    return {'ok': True, 'deleted': goal_id}


@router.post('/{goal_id}/launch')
async def launch_goal(goal_id: str, req: Request):
    """Launch a supervisor run to autonomously execute this goal."""
    try:
        try:
            body = await req.json()
        except (KeyError, TypeError, ValueError, json.JSONDecodeError, OSError, AttributeError, RuntimeError):
            body = {}
    except (KeyError, TypeError, ValueError, json.JSONDecodeError, OSError, AttributeError, RuntimeError):
        body = {}

    con = _get_conn()
    try:
        row = con.execute('SELECT * FROM goals_v2 WHERE id=?', (goal_id,)).fetchone()
        if not row:
            return JSONResponse({'ok': False, 'error': 'Goal not found'}, status_code=404)
    finally:
        con.close()

    g = _goal_dict(row)
    goal_text = g['title']
    if g.get('description'):
        goal_text += f'\n\n{g["description"]}'
    if g.get('success_criteria'):
        goal_text += f'\n\nSuccess Criteria: {g["success_criteria"]}'

    import httpx

    port = int(__import__('os').getenv('AGENTIC_OS_PORT', '8787'))
    try:
        async with httpx.AsyncClient(timeout=10) as client:
            r = await client.post(
                f'http://127.0.0.1:{port}/api/supervisor/run',
                json={'goal': goal_text, 'goal_id': goal_id, 'goal_title': g['title']},
            )
            run_data = r.json()
    except Exception as e:
        return JSONResponse({'ok': False, 'error': f'Supervisor launch failed: {e}'}, status_code=500)

    if run_data.get('ok'):
        run_id = run_data['run_id']
        con = _get_conn()
        try:
            con.execute(
                "UPDATE goals_v2 SET supervisor_run_id=?, status='active', updated_at=? WHERE id=?",
                (run_id, _now(), goal_id),
            )
            con.commit()
        finally:
            con.close()
        log.info('Goal %s launched as supervisor run %s', goal_id, run_id)
        return {'ok': True, 'goal_id': goal_id, 'run_id': run_id}

    return JSONResponse({'ok': False, 'error': run_data.get('error', 'Launch failed')}, status_code=500)


@router.post('/{goal_id}/checkin')
async def add_checkin(goal_id: str, req: Request):
    """Add a progress check-in note to a goal."""
    try:
        try:
            body = await req.json()
        except (KeyError, TypeError, ValueError, json.JSONDecodeError, OSError, AttributeError, RuntimeError):
            body = {}
    except (KeyError, TypeError, ValueError, json.JSONDecodeError, OSError, AttributeError, RuntimeError):
        return JSONResponse({'ok': False, 'error': 'Invalid JSON'}, status_code=400)

    note = (body.get('note') or '').strip()[:1000]
    progress = max(0, min(100, int(body.get('progress') or 0)))
    agent_id = (body.get('agent_id') or 'user')[:50]

    con = _get_conn()
    try:
        row = con.execute('SELECT id, progress FROM goals_v2 WHERE id=?', (goal_id,)).fetchone()
        if not row:
            return JSONResponse({'ok': False, 'error': 'Goal not found'}, status_code=404)

        con.execute(
            'INSERT INTO goal_checkins (goal_id,agent_id,note,progress,created_at) VALUES (?,?,?,?,?)',
            (goal_id, agent_id, note, progress, _now()),
        )
        if progress > 0:
            con.execute('UPDATE goals_v2 SET progress=?, updated_at=? WHERE id=?', (progress, _now(), goal_id))
        con.commit()
    finally:
        con.close()

    return {'ok': True, 'goal_id': goal_id, 'progress': progress}


@router.post('/{goal_id}/milestones')
async def add_milestone(goal_id: str, req: Request):
    """Create and initialize a new milestone."""
    try:
        try:
            body = await req.json()
        except (KeyError, TypeError, ValueError, json.JSONDecodeError, OSError, AttributeError, RuntimeError):
            body = {}
    except (KeyError, TypeError, ValueError, json.JSONDecodeError, OSError, AttributeError, RuntimeError):
        return JSONResponse({'ok': False, 'error': 'Invalid JSON'}, status_code=400)

    title = (body.get('title') or '').strip()
    if not title:
        return JSONResponse({'ok': False, 'error': 'title required'}, status_code=400)

    ms_id = f'ms_{uuid.uuid4().hex[:8]}'
    con = _get_conn()
    try:
        con.execute(
            """
            INSERT INTO goal_milestones (id,goal_id,title,description,due_date,created_at)
            VALUES (?,?,?,?,?,?)
        """,
            (
                ms_id,
                goal_id,
                title[:200],
                (body.get('description') or '')[:500],
                (body.get('due_date') or '')[:30],
                _now(),
            ),
        )
        con.commit()
    finally:
        con.close()
    return {'ok': True, 'id': ms_id, 'goal_id': goal_id}


@router.post('/{goal_id}/milestones/{ms_id}/complete')
def complete_milestone(goal_id: str, ms_id: str):
    """Execute or process complete milestone operation."""
    con = _get_conn()
    try:
        con.execute(
            'UPDATE goal_milestones SET completed=1, completed_at=? WHERE id=? AND goal_id=?', (_now(), ms_id, goal_id)
        )
        # Recompute progress from milestones
        total = con.execute('SELECT COUNT(*) FROM goal_milestones WHERE goal_id=?', (goal_id,)).fetchone()[0]
        done = con.execute(
            'SELECT COUNT(*) FROM goal_milestones WHERE goal_id=? AND completed=1', (goal_id,)
        ).fetchone()[0]
        if total > 0:
            progress = int((done / total) * 100)
            status = 'done' if progress >= 100 else 'active'
            con.execute(
                'UPDATE goals_v2 SET progress=?, status=?, updated_at=? WHERE id=?', (progress, status, _now(), goal_id)
            )
        con.commit()
    finally:
        con.close()
    return {'ok': True, 'milestone_id': ms_id, 'completed': True}


@router.get('/stats/summary')
def goals_summary():
    """Dashboard summary of all goals."""
    con = _get_conn()
    try:
        total = con.execute('SELECT COUNT(*) FROM goals_v2').fetchone()[0]
        by_status = con.execute('SELECT status, COUNT(*) as cnt FROM goals_v2 GROUP BY status').fetchall()
        by_domain = con.execute(
            'SELECT domain, COUNT(*) as cnt FROM goals_v2 GROUP BY domain ORDER BY cnt DESC'
        ).fetchall()
        by_prio = con.execute('SELECT priority, COUNT(*) as cnt FROM goals_v2 GROUP BY priority').fetchall()
        avg_prog = con.execute("SELECT AVG(progress) FROM goals_v2 WHERE status='active'").fetchone()[0]
        upcoming = con.execute(
            "SELECT id, title, deadline, priority FROM goals_v2 WHERE deadline != '' AND status='active' ORDER BY deadline LIMIT 5"
        ).fetchall()
    finally:
        con.close()

    return {
        'total': total,
        'by_status': {r['status']: r['cnt'] for r in by_status},
        'by_domain': {r['domain']: r['cnt'] for r in by_domain},
        'by_priority': {r['priority']: r['cnt'] for r in by_prio},
        'avg_progress': round(avg_prog or 0, 1),
        'upcoming_deadlines': [dict(r) for r in upcoming],
    }


@router.get('/domains/list')
def list_domains():
    """Retrieve and return list domains."""
    return {'domains': DOMAINS, 'priorities': PRIORITIES, 'statuses': STATUSES}


# ── NEW: Goal Decomposition ─────────────────────────────────────────────────────
_DECOMPOSE_SYSTEM = """You are an expert project decomposer. Break the given goal into 3–8 concrete, actionable sub-tasks.

Return ONLY valid JSON (no markdown fences):
{
  "tasks": [
    {
      "seq": 1,
      "title": "Short action title",
      "description": "What this task accomplishes and how",
      "agent_hint": "researcher|builder|reviewer|creative|memory|brain|orchestrator",
      "depends_on": [],
      "risk_level": "low|medium|high",
      "est_tokens": 400
    }
  ]
}

Rules:
- seq must start at 1 and increase sequentially
- depends_on contains seq numbers of tasks this task depends on (empty for first tasks)
- Maximize parallelism: independent tasks should run in parallel (same depends_on scope)
- agent_hint must match a specialist role
- risk_level is "high" only for tasks involving external actions, payments, or irreversible changes
- est_tokens is rough estimate (200–1500)"""


@router.post('/{goal_id}/decompose')
async def decompose_goal(goal_id: str, req: Request):
    """
    AI-powered goal decomposition:
    - Calls Brain LLM to break the goal into a task DAG
    - Saves sub-tasks to goal_decompositions table
    - Updates goals_v2.decomposition column
    - Returns structured task list with dependency edges
    """
    try:
        body = await req.json()
    except (json.JSONDecodeError, TypeError, ValueError):
        body = {}

    con = _get_conn()
    try:
        row = con.execute('SELECT * FROM goals_v2 WHERE id=?', (goal_id,)).fetchone()
        if not row:
            return JSONResponse({'ok': False, 'error': 'Goal not found'}, status_code=404)
    finally:
        con.close()

    g = _goal_dict(row)
    force = body.get('force', False)

    # Return cached decomposition unless force=true
    if not force:
        con = _get_conn()
        try:
            existing = con.execute(
                'SELECT * FROM goal_decompositions WHERE goal_id=? ORDER BY seq', (goal_id,)
            ).fetchall()
        finally:
            con.close()
        if existing:
            tasks = []
            for t in existing:
                td = dict(t)
                try:
                    td['depends_on'] = json.loads(td.get('depends_on', '[]'))
                except (KeyError, TypeError, ValueError, json.JSONDecodeError, OSError, AttributeError, RuntimeError):
                    td['depends_on'] = []
                tasks.append(td)
            edges = _build_decomp_edges(tasks)
            return {
                'ok': True,
                'goal_id': goal_id,
                'tasks': tasks,
                'edges': edges,
                'cached': True,
                'task_count': len(tasks),
            }

    # Call Brain LLM to decompose
    goal_text = g['title']
    if g.get('description'):
        goal_text += f'\n\nDescription: {g["description"]}'
    if g.get('success_criteria'):
        goal_text += f'\n\nSuccess criteria: {g["success_criteria"]}'

    try:
        import re

        from ..services.llm import complete

        result = await complete(
            [{'role': 'system', 'content': _DECOMPOSE_SYSTEM}, {'role': 'user', 'content': f'Goal: {goal_text}'}],
            agent_id='brain',
            max_tokens=1500,
            temperature=0.3,
            inject_steering=False,
        )
        text = result.get('text', '')
        m = re.search(r'\{.*\}', text, re.DOTALL)
        if m:
            parsed = json.loads(m.group(0))
            raw_tasks = parsed.get('tasks', [])
        else:
            raw_tasks = []
    except Exception as e:
        log.warning('Decomposition LLM failed: %s — using fallback', e)
        raw_tasks = []

    # Fallback if LLM fails or returns empty
    if not raw_tasks:
        raw_tasks = [
            {
                'seq': 1,
                'title': 'Research & Plan',
                'description': f'Research best approaches for: {g["title"]}',
                'agent_hint': 'researcher',
                'depends_on': [],
                'risk_level': 'low',
                'est_tokens': 500,
            },
            {
                'seq': 2,
                'title': 'Design Solution',
                'description': f'Design a concrete solution for: {g["title"]}',
                'agent_hint': 'brain',
                'depends_on': [1],
                'risk_level': 'low',
                'est_tokens': 600,
            },
            {
                'seq': 3,
                'title': 'Execute',
                'description': 'Implement the designed solution',
                'agent_hint': 'builder',
                'depends_on': [2],
                'risk_level': 'low',
                'est_tokens': 800,
            },
            {
                'seq': 4,
                'title': 'Review & Finalize',
                'description': 'Review, verify, and finalize the result',
                'agent_hint': 'reviewer',
                'depends_on': [3],
                'risk_level': 'low',
                'est_tokens': 400,
            },
        ]

    # Persist to goal_decompositions
    now = _now()
    con = _get_conn()
    try:
        con.execute('DELETE FROM goal_decompositions WHERE goal_id=?', (goal_id,))
        tasks_out = []
        for rt in raw_tasks:
            tid = f'gd_{uuid.uuid4().hex[:10]}'
            deps = rt.get('depends_on', [])
            if not isinstance(deps, list):
                deps = []
            con.execute(
                """
                INSERT INTO goal_decompositions
                  (id,goal_id,seq,title,description,agent_hint,depends_on,risk_level,est_tokens,status,created_at)
                VALUES (?,?,?,?,?,?,?,?,?,?,?)
            """,
                (
                    tid,
                    goal_id,
                    int(rt.get('seq', 0)),
                    str(rt.get('title', 'Task'))[:200],
                    str(rt.get('description', ''))[:2000],
                    str(rt.get('agent_hint', 'builder'))[:50],
                    json.dumps(deps),
                    str(rt.get('risk_level', 'low'))[:20],
                    int(rt.get('est_tokens', 400)),
                    'pending',
                    now,
                ),
            )
            tasks_out.append(
                {
                    'id': tid,
                    'goal_id': goal_id,
                    'seq': int(rt.get('seq', 0)),
                    'title': str(rt.get('title', 'Task'))[:200],
                    'description': str(rt.get('description', ''))[:2000],
                    'agent_hint': str(rt.get('agent_hint', 'builder'))[:50],
                    'depends_on': deps,
                    'risk_level': str(rt.get('risk_level', 'low')),
                    'est_tokens': int(rt.get('est_tokens', 400)),
                    'status': 'pending',
                }
            )

        # Store summary in goals_v2
        con.execute(
            'UPDATE goals_v2 SET decomposition=?, updated_at=? WHERE id=?',
            (
                json.dumps([{'seq': t['seq'], 'title': t['title'], 'agent_hint': t['agent_hint']} for t in tasks_out]),
                now,
                goal_id,
            ),
        )
        con.commit()
    finally:
        con.close()

    edges = _build_decomp_edges(tasks_out)
    return {
        'ok': True,
        'goal_id': goal_id,
        'tasks': tasks_out,
        'edges': edges,
        'cached': False,
        'task_count': len(tasks_out),
    }


def _build_decomp_edges(tasks: list[dict]) -> list[dict]:
    """Build edge list from task depends_on fields."""
    seq_map = {t['seq']: t for t in tasks}
    edges = []
    for t in tasks:
        for dep_seq in t.get('depends_on') or []:
            src = seq_map.get(dep_seq)
            if src:
                edges.append(
                    {
                        'id': f'e_{dep_seq}_{t["seq"]}',
                        'from_id': src['id'],
                        'to_id': t['id'],
                        'from_seq': dep_seq,
                        'to_seq': t['seq'],
                    }
                )
    return edges


@router.get('/{goal_id}/decompose')
def get_decomposition(goal_id: str):
    """Return the saved decomposition for a goal (no LLM call)."""
    con = _get_conn()
    try:
        tasks = con.execute('SELECT * FROM goal_decompositions WHERE goal_id=? ORDER BY seq', (goal_id,)).fetchall()
    finally:
        con.close()

    tasks_out = []
    for t in tasks:
        td = dict(t)
        try:
            td['depends_on'] = json.loads(td.get('depends_on', '[]'))
        except (KeyError, TypeError, ValueError, json.JSONDecodeError, OSError, AttributeError, RuntimeError):
            td['depends_on'] = []
        tasks_out.append(td)

    edges = _build_decomp_edges(tasks_out)
    return {'ok': True, 'goal_id': goal_id, 'tasks': tasks_out, 'edges': edges, 'task_count': len(tasks_out)}


# ── NEW: Outcome Scoring ────────────────────────────────────────────────────────
_SCORE_SYSTEM = """You are a rigorous goal outcome evaluator. Score how well the provided evidence shows progress toward the goal.

Return ONLY valid JSON (no markdown fences):
{
  "overall": 0.72,
  "dimensions": {
    "completion":   0.80,
    "quality":      0.75,
    "on_schedule":  0.60,
    "criteria_met": 0.70,
    "momentum":     0.75
  },
  "grade": "B+",
  "summary": "One sentence summary of overall standing",
  "strengths": ["strength 1", "strength 2"],
  "gaps": ["gap 1", "gap 2"],
  "next_actions": ["action 1", "action 2", "action 3"],
  "recommended_progress": 65
}

Scoring rules:
- overall: weighted average of dimensions (0.0–1.0)
- completion: how much of the defined work is done
- quality: quality signals from check-in notes and outputs
- on_schedule: relative to deadline (1.0 if no deadline set)
- criteria_met: how well success criteria are satisfied
- momentum: trend — improving, stalling, or regressing
- grade: letter grade A+/A/A-/B+/B/B-/C+/C/D/F
- recommended_progress: integer 0–100 to update goal progress field"""


@router.post('/{goal_id}/score')
async def score_goal_outcome(goal_id: str, req: Request):
    """
    AI-powered outcome scoring:
    - Collects all evidence: check-ins, milestones, supervisor run outputs
    - Calls Evaluator LLM to score 5 dimensions
    - Saves score to goal_score_history
    - Updates goals_v2 outcome_score, score_breakdown, iteration, progress
    - Returns full scoring breakdown
    """
    try:
        body = await req.json()
    except (json.JSONDecodeError, TypeError, ValueError):
        body = {}

    con = _get_conn()
    try:
        row = con.execute('SELECT * FROM goals_v2 WHERE id=?', (goal_id,)).fetchone()
        if not row:
            return JSONResponse({'ok': False, 'error': 'Goal not found'}, status_code=404)
        checkins = con.execute(
            'SELECT * FROM goal_checkins WHERE goal_id=? ORDER BY id DESC LIMIT 20', (goal_id,)
        ).fetchall()
        milestones = con.execute(
            'SELECT * FROM goal_milestones WHERE goal_id=? ORDER BY created_at', (goal_id,)
        ).fetchall()
    finally:
        con.close()

    g = _goal_dict(row)

    # Build evidence package for the LLM
    evidence_parts = [f'**Goal:** {g["title"]}']
    if g.get('description'):
        evidence_parts.append(f'**Description:** {g["description"][:500]}')
    if g.get('success_criteria'):
        evidence_parts.append(f'**Success Criteria:** {g["success_criteria"][:500]}')
    if g.get('deadline'):
        from datetime import date

        evidence_parts.append(f'**Deadline:** {g["deadline"]}')
        try:
            dl = date.fromisoformat(g['deadline'])
            days_left = (dl - date.today()).days
            evidence_parts.append(f'**Days remaining:** {days_left}')
        except (KeyError, TypeError, ValueError, json.JSONDecodeError, OSError, AttributeError, RuntimeError):
            pass
    evidence_parts.append(f'**Current progress:** {g.get("progress", 0)}%')
    evidence_parts.append(f'**Status:** {g.get("status", "active")}')

    ms_list = [dict(m) for m in milestones]
    if ms_list:
        done_ms = sum(1 for m in ms_list if m.get('completed'))
        total_ms = len(ms_list)
        evidence_parts.append(f'\n**Milestones ({done_ms}/{total_ms} complete):**')
        for m in ms_list:
            evidence_parts.append(f'  {"✅" if m.get("completed") else "⬜"} {m["title"]}')

    ci_list = [dict(c) for c in checkins]
    if ci_list:
        evidence_parts.append(f'\n**Recent check-ins ({len(ci_list)}):**')
        for c in ci_list[:10]:
            evidence_parts.append(f'  [{c["agent_id"]}] {c.get("note", "")} (progress={c.get("progress", 0)}%)')

    # Pull supervisor run output if linked
    run_id = g.get('supervisor_run_id', '')
    if run_id:
        try:
            con = _get_conn()
            try:
                sv_run = con.execute(
                    'SELECT final_output, eval_score FROM supervisor_runs WHERE run_id=?', (run_id,)
                ).fetchone()
            finally:
                con.close()
            if sv_run and sv_run['final_output']:
                evidence_parts.append(f'\n**Supervisor run output (score {sv_run["eval_score"] or "?"}):**')
                evidence_parts.append(sv_run['final_output'][:800])
        except (KeyError, TypeError, ValueError, json.JSONDecodeError, OSError, AttributeError, RuntimeError):
            pass

    evidence = '\n'.join(evidence_parts)

    # Call evaluator LLM
    try:
        import re

        from ..services.llm import complete

        result = await complete(
            [{'role': 'system', 'content': _SCORE_SYSTEM}, {'role': 'user', 'content': f'Evidence:\n{evidence}'}],
            agent_id='reviewer',
            max_tokens=500,
            temperature=0.1,
            inject_steering=False,
        )
        text = result.get('text', '')
        m = re.search(r'\{.*\}', text, re.DOTALL)
        if m:
            scored = json.loads(m.group(0))
        else:
            scored = {}
    except Exception as e:
        log.warning('Outcome scoring LLM failed: %s', e)
        scored = {}

    # Compute safe defaults if LLM fails or partial
    ms_pct = (sum(1 for m in ms_list if m.get('completed')) / max(len(ms_list), 1)) if ms_list else 0
    ci_prog = (ci_list[0].get('progress', 0) / 100) if ci_list else (g.get('progress', 0) / 100)
    fallback_score = round((ms_pct * 0.4 + ci_prog * 0.6), 2)

    overall = float(scored.get('overall', fallback_score))
    dims = scored.get(
        'dimensions',
        {
            'completion': round(ms_pct, 2),
            'quality': 0.70,
            'on_schedule': 1.0,
            'criteria_met': round(ci_prog, 2),
            'momentum': 0.70,
        },
    )
    grade = scored.get('grade', _score_to_grade(overall))
    summary = scored.get('summary', f'Goal at {int(overall * 100)}% outcome score')
    strengths = scored.get('strengths', [])
    gaps = scored.get('gaps', [])
    next_actions = scored.get('next_actions', [])
    rec_progress = int(scored.get('recommended_progress', min(100, int(overall * 100))))

    # Ensure all values are in valid range
    overall = max(0.0, min(1.0, overall))
    for k in dims:
        dims[k] = max(0.0, min(1.0, float(dims.get(k, 0.5))))

    # Save score history
    now = _now()
    iteration = int(g.get('iteration', 0)) + 1
    con = _get_conn()
    try:
        con.execute(
            """
            INSERT INTO goal_score_history
              (goal_id,iteration,score,breakdown,notes,scored_by,run_id,created_at)
            VALUES (?,?,?,?,?,?,?,?)
        """,
            (goal_id, iteration, overall, json.dumps(dims), summary, 'evaluator', run_id or '', now),
        )

        # Update goal
        con.execute(
            """
            UPDATE goals_v2
            SET outcome_score=?, score_breakdown=?, last_scored_at=?,
                iteration=?, progress=?, updated_at=?
            WHERE id=?
        """,
            (overall, json.dumps(dims), now, iteration, rec_progress, now, goal_id),
        )
        con.commit()
    finally:
        con.close()

    # Add check-in record
    con = _get_conn()
    try:
        con.execute(
            'INSERT INTO goal_checkins (goal_id,agent_id,note,progress,created_at) VALUES (?,?,?,?,?)',
            (
                goal_id,
                'evaluator',
                f'Outcome score: {int(overall * 100)}% ({grade}) — {summary[:200]}',
                rec_progress,
                now,
            ),
        )
        con.commit()
    finally:
        con.close()

    return {
        'ok': True,
        'goal_id': goal_id,
        'iteration': iteration,
        'overall': overall,
        'overall_pct': int(overall * 100),
        'grade': grade,
        'dimensions': dims,
        'summary': summary,
        'strengths': strengths[:5],
        'gaps': gaps[:5],
        'next_actions': next_actions[:5],
        'recommended_progress': rec_progress,
        'scored_at': now,
    }


def _score_to_grade(score: float) -> str:
    if score >= 0.97:
        return 'A+'
    if score >= 0.93:
        return 'A'
    if score >= 0.90:
        return 'A-'
    if score >= 0.87:
        return 'B+'
    if score >= 0.83:
        return 'B'
    if score >= 0.80:
        return 'B-'
    if score >= 0.77:
        return 'C+'
    if score >= 0.73:
        return 'C'
    if score >= 0.70:
        return 'C-'
    if score >= 0.60:
        return 'D'
    return 'F'


@router.get('/{goal_id}/score/history')
def get_score_history(goal_id: str):
    """Return full scoring history for a goal (all iterations)."""
    con = _get_conn()
    try:
        row = con.execute('SELECT id FROM goals_v2 WHERE id=?', (goal_id,)).fetchone()
        if not row:
            return JSONResponse({'ok': False, 'error': 'Goal not found'}, status_code=404)
        history = con.execute(
            'SELECT * FROM goal_score_history WHERE goal_id=? ORDER BY iteration', (goal_id,)
        ).fetchall()
    finally:
        con.close()

    hist_out = []
    for h in history:
        hd = dict(h)
        try:
            hd['breakdown'] = json.loads(hd.get('breakdown', '{}'))
        except (KeyError, TypeError, ValueError, json.JSONDecodeError, OSError, AttributeError, RuntimeError):
            hd['breakdown'] = {}
        hist_out.append(hd)

    return {'ok': True, 'goal_id': goal_id, 'history': hist_out, 'count': len(hist_out)}


@router.get('/{goal_id}/score/latest')
def get_latest_score(goal_id: str):
    """Return the most recent outcome score for a goal."""
    con = _get_conn()
    try:
        row = con.execute('SELECT * FROM goals_v2 WHERE id=?', (goal_id,)).fetchone()
        if not row:
            return JSONResponse({'ok': False, 'error': 'Goal not found'}, status_code=404)
        latest = con.execute(
            'SELECT * FROM goal_score_history WHERE goal_id=? ORDER BY iteration DESC LIMIT 1', (goal_id,)
        ).fetchone()
    finally:
        con.close()

    g = _goal_dict(row)
    if not latest:
        return {
            'ok': True,
            'goal_id': goal_id,
            'scored': False,
            'outcome_score': g.get('outcome_score'),
            'iteration': 0,
        }

    hd = dict(latest)
    try:
        hd['breakdown'] = json.loads(hd.get('breakdown', '{}'))
    except (KeyError, TypeError, ValueError, json.JSONDecodeError, OSError, AttributeError, RuntimeError):
        hd['breakdown'] = {}

    return {
        'ok': True,
        'goal_id': goal_id,
        'scored': True,
        'iteration': hd['iteration'],
        'overall': hd['score'],
        'grade': _score_to_grade(hd['score']),
        'breakdown': hd['breakdown'],
        'notes': hd['notes'],
        'scored_at': hd['created_at'],
    }


@router.get('/{goal_id}/full')
def get_goal_full(goal_id: str):
    """
    Full goal detail: goal + milestones + checkins + decomposition + score history.
    Used by the Goal Detail panel.
    """
    con = _get_conn()
    try:
        row = con.execute('SELECT * FROM goals_v2 WHERE id=?', (goal_id,)).fetchone()
        if not row:
            return JSONResponse({'ok': False, 'error': 'Goal not found'}, status_code=404)
        milestones = con.execute(
            'SELECT * FROM goal_milestones WHERE goal_id=? ORDER BY created_at', (goal_id,)
        ).fetchall()
        checkins = con.execute(
            'SELECT * FROM goal_checkins WHERE goal_id=? ORDER BY id DESC LIMIT 30', (goal_id,)
        ).fetchall()
        decomp = con.execute('SELECT * FROM goal_decompositions WHERE goal_id=? ORDER BY seq', (goal_id,)).fetchall()
        scores = con.execute(
            'SELECT * FROM goal_score_history WHERE goal_id=? ORDER BY iteration', (goal_id,)
        ).fetchall()
    finally:
        con.close()

    g = _goal_dict(row)
    for field in ('score_breakdown', 'decomposition'):
        try:
            g[field] = (
                json.loads(g.get(field) or '{}') if field == 'score_breakdown' else json.loads(g.get(field) or '[]')
            )
        except (KeyError, TypeError, ValueError, json.JSONDecodeError, OSError, AttributeError, RuntimeError):
            g[field] = {} if field == 'score_breakdown' else []

    decomp_out = []
    for d in decomp:
        dd = dict(d)
        try:
            dd['depends_on'] = json.loads(dd.get('depends_on', '[]'))
        except (KeyError, TypeError, ValueError, json.JSONDecodeError, OSError, AttributeError, RuntimeError):
            dd['depends_on'] = []
        decomp_out.append(dd)

    scores_out = []
    for s in scores:
        sd = dict(s)
        try:
            sd['breakdown'] = json.loads(sd.get('breakdown', '{}'))
        except (KeyError, TypeError, ValueError, json.JSONDecodeError, OSError, AttributeError, RuntimeError):
            sd['breakdown'] = {}
        scores_out.append(sd)

    return {
        'ok': True,
        'goal': g,
        'milestones': [dict(m) for m in milestones],
        'checkins': [dict(c) for c in checkins],
        'decomposition': decomp_out,
        'score_history': scores_out,
    }
