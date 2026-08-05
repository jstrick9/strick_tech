"""
Agentic OS — Tasks / Kanban Router

Task CRUD, the Kanban board projection, bulk reordering and column moves.

ARCHITECTURE: these endpoints previously lived inline in backend/app.py, which
had grown to ~990 lines mixing 150 router imports, two middlewares, WebSocket
endpoints and CRUD for several unrelated features. Extracting them here matches
how every other feature in the platform is organised (one router per feature)
and keeps app.py to wiring.
"""

from __future__ import annotations

import json
import logging

from fastapi import APIRouter, Request
from fastapi.responses import JSONResponse

from ..services.memory_db import get_conn
from ..services.request_body import as_text

router = APIRouter(tags=['tasks'])
log = logging.getLogger('agentic.tasks')


# ── Kanban / Tasks ─────────────────────────────────────────────────────────────
def _task_dict(r) -> dict:
    d = dict(r)
    d['status'] = d.get('status', 'todo') if d.get('status') in ('todo', 'doing', 'blocked', 'done') else 'todo'
    d['priority'] = d.get('priority', 'medium') if d.get('priority') in ('high', 'medium', 'low') else 'medium'
    d['agent'] = d.get('agent') or 'builder'
    d['layer'] = d.get('layer') or 'Tasks'
    d['description'] = d.get('description') or ''
    d['sort_order'] = d.get('sort_order') or d.get('id') or 0
    return d


@router.get('/api/kanban')
def kanban():
    """Execute or process kanban operation."""
    con = get_conn()
    try:
        rows = con.execute("""
            SELECT id, title, status, priority, agent,
                   COALESCE(layer,'Tasks') as layer,
                   COALESCE(description,'') as description,
                   created_at,
                   COALESCE(updated_at, created_at) as updated_at,
                   COALESCE(sort_order, id) as sort_order
            FROM tasks
            ORDER BY CASE status WHEN 'doing' THEN 0 WHEN 'todo' THEN 1
                                 WHEN 'blocked' THEN 2 WHEN 'done' THEN 3 ELSE 4 END,
                     sort_order ASC, id DESC
        """).fetchall()
    except (KeyError, TypeError, ValueError, json.JSONDecodeError, OSError, AttributeError, RuntimeError):
        rows = con.execute('SELECT id,title,status,priority,agent,created_at FROM tasks ORDER BY id DESC').fetchall()
    con.close()
    cols = {'todo': [], 'doing': [], 'blocked': [], 'done': []}
    for r in rows:
        t = _task_dict(r)
        cols.get(t['status'], cols['todo']).append(t)
    return cols


@router.get('/api/tasks')
def tasks_list(status: str = '', agent: str = '', limit: int = 200, q: str = ''):
    """Execute or process tasks list operation."""
    con = get_conn()
    where, params = [], []
    if status:
        where.append('status=?')
        params.append(status)
    if agent:
        where.append('agent=?')
        params.append(agent)
    if q:
        where.append('title LIKE ?')
        params.append(f'%{q}%')
    sql = (
        "SELECT id,title,status,priority,agent,COALESCE(layer,'Tasks') as layer,"
        "COALESCE(description,'') as description,created_at,COALESCE(sort_order,id) as sort_order FROM tasks"
    )
    if where:
        sql += ' WHERE ' + ' AND '.join(where)
    sql += ' ORDER BY sort_order ASC, id DESC LIMIT ?'
    params.append(min(limit, 500))
    try:
        rows = con.execute(sql, params).fetchall()
    finally:
        con.close()
    return [_task_dict(r) for r in rows]


@router.post('/api/tasks')
async def tasks_create(req: Request):
    """Execute or process tasks create operation."""
    try:
        d = await req.json()
    except (KeyError, TypeError, ValueError, json.JSONDecodeError, OSError, AttributeError, RuntimeError):
        return JSONResponse({'ok': False, 'error': 'Invalid JSON body'}, status_code=400)
    title = (as_text(d.get('title')) or '')[:240]
    if not title:
        # Validation failures are 400, matching the rest of the task API.
        return JSONResponse({'ok': False, 'error': 'title required'}, status_code=400)
    status = d.get('status', 'todo')
    priority = d.get('priority', 'medium')
    agent = (d.get('agent', 'builder') or 'builder')[:32]
    layer = (d.get('layer', 'Tasks') or 'Tasks')[:48]
    desc = (d.get('description', '') or '')[:2000]
    if status not in ('todo', 'doing', 'blocked', 'done'):
        status = 'todo'
    if priority not in ('high', 'medium', 'low'):
        priority = 'medium'
    con = get_conn()
    cur = con.execute(
        'INSERT INTO tasks(title,status,priority,agent,layer,description,sort_order,updated_at) VALUES (?,?,?,?,?,?,?,CURRENT_TIMESTAMP)',
        (title, status, priority, agent, layer, desc, d.get('sort_order', 0)),
    )
    tid = cur.lastrowid
    con.execute("INSERT INTO audit(action,detail) VALUES ('task_create',?)", (f'{tid}:{title[:80]}',))
    con.commit()
    con.close()
    # broadcast via WS
    try:
        import asyncio

        from .websocket import broadcast_task_update

        asyncio.create_task(broadcast_task_update({'id': tid, 'title': title, 'status': status, 'action': 'created'}))
    except (KeyError, TypeError, ValueError, json.JSONDecodeError, OSError, AttributeError, RuntimeError):
        pass
    return {'ok': True, 'id': tid, 'title': title, 'status': status}


@router.post('/api/tasks/bulk_update')
async def tasks_bulk_update(req: Request):
    """Execute or process tasks bulk update operation."""
    try:
        d = await req.json()
    except (KeyError, TypeError, ValueError, json.JSONDecodeError, OSError, AttributeError, RuntimeError):
        return JSONResponse({'ok': False, 'error': 'Invalid JSON body'}, status_code=400)
    updates = d.get('updates', [])
    if not isinstance(updates, list):
        return JSONResponse({'ok': False, 'error': 'updates[] required'}, status_code=400)
    # BUG FIX: `updated` counted UPDATE statements ISSUED, not rows changed, so
    # a payload referencing ids that do not exist still reported
    # {'ok': True, 'updated': 2}. It now counts affected rows and reports which
    # ids were not found, so a partially-stale board can be reconciled.
    con = get_conn()
    ok = 0
    missing: list = []
    try:
        for u in updates[:200]:
            tid = u.get('id')
            if not tid:
                continue
            sets, vals = [], []
            if 'status' in u and u['status'] in ('todo', 'doing', 'blocked', 'done'):
                sets.append('status=?')
                vals.append(u['status'])
            if 'sort_order' in u:
                try:
                    vals.append(int(u['sort_order']))
                    sets.append('sort_order=?')
                except (TypeError, ValueError):
                    pass
            if sets:
                sets.append('updated_at=CURRENT_TIMESTAMP')
                vals.append(tid)
                cur = con.execute(f'UPDATE tasks SET {", ".join(sets)} WHERE id=?', vals)
                if cur.rowcount:
                    ok += 1
                else:
                    missing.append(tid)
        con.commit()
    finally:
        con.close()
    return {'ok': True, 'updated': ok, 'missing': missing}


@router.patch('/api/tasks/{task_id}')
async def tasks_update(task_id: int, req: Request):
    """Execute or process tasks update operation."""
    try:
        d = await req.json()
    except (KeyError, TypeError, ValueError, json.JSONDecodeError, OSError, AttributeError, RuntimeError):
        return JSONResponse({'ok': False, 'error': 'Invalid JSON body'}, status_code=400)
    allowed = {'title', 'status', 'priority', 'agent', 'layer', 'description', 'sort_order'}
    sets, vals = [], []
    for k in allowed:
        if k not in d:
            continue
        v = d[k]
        if k == 'status' and v not in ('todo', 'doing', 'blocked', 'done'):
            continue
        if k == 'priority' and v not in ('high', 'medium', 'low'):
            continue
        if k == 'title':
            v = str(v)[:240]
        if k == 'agent':
            v = str(v)[:32]
        if k == 'layer':
            v = str(v)[:48]
        if k == 'description':
            v = str(v)[:2000]
        sets.append(f'{k}=?')
        vals.append(v)
    if not sets:
        return JSONResponse({'ok': False, 'error': 'no valid fields'}, status_code=400)
    sets.append('updated_at=CURRENT_TIMESTAMP')
    vals.append(task_id)
    # BUG FIX: this reported {'ok': True, 'task': {}} for a task id that does
    # not exist — an HTTP 200 success for an update that changed nothing. The
    # Kanban board relies on response.ok to decide whether a drag-and-drop was
    # persisted, so moving a card that had been deleted elsewhere showed
    # "Task moved" and left the card in its new column until the next reload.
    # Also wrapped in try/finally: an exception between execute() and close()
    # leaked the SQLite connection.
    con = get_conn()
    try:
        cur = con.execute(f'UPDATE tasks SET {", ".join(sets)} WHERE id=?', vals)
        if cur.rowcount == 0:
            return JSONResponse({'ok': False, 'error': 'Task not found'}, status_code=404)
        con.execute("INSERT INTO audit(action,detail) VALUES ('task_update',?)", (str(task_id),))
        con.commit()
        row = con.execute(
            "SELECT id,title,status,priority,agent,COALESCE(layer,'Tasks') as layer FROM tasks WHERE id=?",
            (task_id,),
        ).fetchone()
    finally:
        con.close()
    return {'ok': True, 'task': _task_dict(row) if row else {}}


@router.post('/api/tasks/{task_id}')
async def tasks_update_post(task_id: int, req: Request):
    """Execute or process tasks update post operation."""
    return await tasks_update(task_id, req)


@router.delete('/api/tasks/{task_id}')
def tasks_delete(task_id: int):
    """Execute or process tasks delete operation."""
    # BUG FIX: returned {'ok': True, 'deleted': <id>} even when no such task
    # existed, so a double-delete (or a stale board) looked like a success.
    con = get_conn()
    try:
        cur = con.execute('DELETE FROM tasks WHERE id=?', (task_id,))
        if cur.rowcount == 0:
            return JSONResponse({'ok': False, 'error': 'Task not found'}, status_code=404)
        con.execute("INSERT INTO audit(action,detail) VALUES ('task_delete',?)", (str(task_id),))
        con.commit()
    finally:
        con.close()
    return {'ok': True, 'deleted': task_id}


@router.post('/api/kanban/move')
async def kanban_move(req: Request):
    """Execute or process kanban move operation."""
    try:
        d = await req.json()
    except (KeyError, TypeError, ValueError, json.JSONDecodeError, OSError, AttributeError, RuntimeError):
        return JSONResponse({'ok': False, 'error': 'Invalid JSON body'}, status_code=400)
    tid = d.get('id') or d.get('task_id')
    to = d.get('to_status') or d.get('status')
    if not tid or to not in ('todo', 'doing', 'blocked', 'done'):
        return JSONResponse({'ok': False, 'error': 'id + to_status required'}, status_code=400)
    try:
        tid_int = int(tid)
    except (TypeError, ValueError):
        return JSONResponse({'ok': False, 'error': 'id must be an integer'}, status_code=400)
    # BUG FIX: reported {'ok': True} for a task that does not exist, and
    # int(tid) on a non-numeric id raised an unhandled ValueError -> HTTP 500.
    con = get_conn()
    try:
        cur = con.execute('UPDATE tasks SET status=?, updated_at=CURRENT_TIMESTAMP WHERE id=?', (to, tid_int))
        if cur.rowcount == 0:
            return JSONResponse({'ok': False, 'error': 'Task not found'}, status_code=404)
        con.commit()
    finally:
        con.close()
    return {'ok': True}
