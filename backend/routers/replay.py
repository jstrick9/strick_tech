"""
Agentic OS — Workflow Execution Replay Router
Records every run step with full context snapshots.
Enables frame-by-frame scrubbing, diff view, and re-run from any point.

Tables used: workflow_runs, workflow_run_frames (created here)
"""

from __future__ import annotations

import contextlib

import asyncio
import json
import logging
import time
import uuid
from pathlib import Path

from fastapi import APIRouter, Request
from fastapi.responses import StreamingResponse

router = APIRouter(prefix='/api/replay', tags=['replay'])
log = logging.getLogger('agentic.replay')

ROOT = Path(__file__).resolve().parents[2]
WF_DIR = ROOT / 'workspaces' / 'workflows'

# ── DB schema ──────────────────────────────────────────────────────────────────
_SCHEMA = """
CREATE TABLE IF NOT EXISTS workflow_runs (
    id          TEXT PRIMARY KEY,
    workflow_id TEXT NOT NULL,
    workflow_nm TEXT,
    input       TEXT,
    status      TEXT DEFAULT 'running',
    total_ms    INTEGER DEFAULT 0,
    node_count  INTEGER DEFAULT 0,
    created_at  TIMESTAMP DEFAULT CURRENT_TIMESTAMP
);
CREATE TABLE IF NOT EXISTS workflow_run_frames (
    id          INTEGER PRIMARY KEY AUTOINCREMENT,
    run_id      TEXT NOT NULL,
    frame_no    INTEGER NOT NULL,
    node_id     TEXT NOT NULL,
    node_type   TEXT,
    node_label  TEXT,
    event_type  TEXT,
    input_ctx   TEXT,
    output      TEXT,
    error       TEXT,
    duration_ms INTEGER DEFAULT 0,
    timestamp   REAL,
    FOREIGN KEY (run_id) REFERENCES workflow_runs(id)
);
CREATE INDEX IF NOT EXISTS idx_wrf_run ON workflow_run_frames(run_id, frame_no);
"""


def _ensure_schema():
    from ..services.memory_db import get_conn

    con = get_conn()
    try:
        con.executescript(_SCHEMA)
        con.commit()
    finally:
        con.close()


_ensure_schema()


# ── Run recording helpers ──────────────────────────────────────────────────────
def _create_run(run_id: str, wf_id: str, wf_name: str, user_input: str):
    from ..services.memory_db import get_conn

    con = get_conn()
    try:
        con.execute(
            "INSERT OR REPLACE INTO workflow_runs(id,workflow_id,workflow_nm,input,status) VALUES (?,?,?,?,'running')",
            (run_id, wf_id, wf_name, user_input[:2000]),
        )
        con.commit()
    finally:
        con.close()


def _record_frame(
    run_id: str,
    frame_no: int,
    node_id: str,
    node_type: str,
    node_label: str,
    event_type: str,
    input_ctx: dict,
    output: str,
    error: str,
    duration_ms: int,
):
    from ..services.memory_db import get_conn

    con = get_conn()
    try:
        con.execute(
            """INSERT INTO workflow_run_frames
        (run_id,frame_no,node_id,node_type,node_label,event_type,
        input_ctx,output,error,duration_ms,timestamp)
        VALUES (?,?,?,?,?,?,?,?,?,?,?)""",
            (
                run_id,
                frame_no,
                node_id,
                node_type,
                node_label,
                event_type,
                json.dumps(input_ctx, default=str)[:4000],
                (output or '')[:4000],
                (error or '')[:1000],
                duration_ms,
                time.time(),
            ),
        )
        con.commit()
    finally:
        con.close()


def _finish_run(run_id: str, status: str, total_ms: int, node_count: int):
    from ..services.memory_db import get_conn

    con = get_conn()
    try:
        con.execute(
            'UPDATE workflow_runs SET status=?,total_ms=?,node_count=? WHERE id=?',
            (status, total_ms, node_count, run_id),
        )
        con.commit()
    finally:
        con.close()


# ── Recorded Run endpoint (SSE + persist every frame) ─────────────────────────
@router.post('/workflow/{wf_id}/run')
async def recorded_run(wf_id: str, req: Request):
    """
    Like /api/workflow/{id}/run but records every frame to DB for later replay.
    Returns SSE stream identical to normal run PLUS frame snapshots.
    """
    try:
        body = await req.json()
    except (json.JSONDecodeError, TypeError, ValueError):
        body = {}
    user_input = body.get('input', '')

    # Load workflow
    wf_path = WF_DIR / f'{wf_id}.json'
    if not wf_path.exists():
        return {'ok': False, 'error': 'Workflow not found'}
    wf = json.loads(wf_path.read_text())

    run_id = f'run_{uuid.uuid4().hex[:10]}'
    _create_run(run_id, wf_id, wf.get('name', ''), user_input)

    async def _stream():
        nodes = {n['id']: n for n in wf.get('nodes', [])}
        edges = wf.get('edges', [])
        adj: dict[str, list[str]] = {}
        for e in edges:
            adj.setdefault(e['from'], []).append(e['to'])

        triggers = [n for n in nodes.values() if n['type'] == 'trigger']
        if not triggers:
            _finish_run(run_id, 'failed', 0, 0)
            yield f'data: {json.dumps({"type": "error", "msg": "No trigger node"})}\n\n'
            return

        context = {'input': user_input, 'prev_output': user_input, 'all_outputs': {}}
        frame_no = 0
        visited: set[str] = set()
        queue = [triggers[0]['id']]
        run_start = time.perf_counter()

        yield f'data: {json.dumps({"type": "start", "run_id": run_id, "workflow": wf["name"], "wf_id": wf_id})}\n\n'

        from ..services import llm as llm_svc

        while queue:
            nid = queue.pop(0)
            if nid in visited:
                continue
            visited.add(nid)
            node = nodes.get(nid)
            if not node:
                continue

            cfg = node.get('config', {})
            node_type = node['type']
            label = node.get('label', node_type)
            t0 = time.perf_counter()

            # Emit node_start
            frame_no += 1
            start_ev = {
                'type': 'node_start',
                'run_id': run_id,
                'frame': frame_no,
                'node_id': nid,
                'node_type': node_type,
                'label': label,
                'context_snapshot': {'input': context['input'], 'prev_output': context['prev_output'][:200]},
            }
            yield f'data: {json.dumps(start_ev)}\n\n'
            _record_frame(
                run_id,
                frame_no,
                nid,
                node_type,
                label,
                'node_start',
                {'input': context['input'], 'prev_output': context['prev_output'][:500]},
                '',
                '',
                0,
            )
            await asyncio.sleep(0.03)

            output = ''
            error = ''

            # Execute node
            if node_type == 'trigger':
                context['prev_output'] = context['input']
                output = context['input']

            elif node_type == 'agent':
                prompt = cfg.get('prompt', '{{input}}')
                prompt = prompt.replace('{{input}}', context['input']).replace(
                    '{{prev_output}}', context['prev_output']
                )
                try:
                    msgs = [{'role': 'user', 'content': prompt}]
                    result = await llm_svc.complete(
                        msgs, agent_id=cfg.get('agent_id', 'builder'), max_tokens=1024, inject_steering=False
                    )
                    output = result.get('text', '')
                    context['prev_output'] = output
                    context['all_outputs'][nid] = output
                except Exception as ex:
                    error = str(ex)
                    output = f'[error] {ex}'

            elif node_type == 'condition':
                passed = any(kw in context['prev_output'].lower() for kw in ['yes', 'pass', 'true', 'success', 'ok'])
                output = 'true' if passed else 'false'
                context['_condition'] = passed

            elif node_type == 'transform':
                mode = cfg.get('mode', 'passthrough')
                if mode == 'merge':
                    all_out = '\n---\n'.join(context['all_outputs'].values())
                    context['prev_output'] = all_out or context['prev_output']
                output = 'transform applied'

            elif node_type == 'delay':
                secs = min(int(cfg.get('seconds', 1)), 10)
                await asyncio.sleep(secs)
                output = f'waited {secs}s'

            elif node_type == 'webhook':
                url = cfg.get('url', '')
                if url:
                    import httpx

                    try:
                        async with httpx.AsyncClient(timeout=10) as client:
                            r = await client.post(url, json=context)
                            output = r.text[:500]
                            context['prev_output'] = output
                    except Exception as ex:
                        error = str(ex)
                        output = f'[webhook error] {ex}'

            elif node_type == 'memory':
                from ..services.memory_db import get_conn

                if cfg.get('action') == 'write':
                    con = get_conn()
                    try:
                        con.execute(
                            'INSERT INTO memory(source,content,tags) VALUES (?,?,?)',
                            ('workflow', context['prev_output'][:2000], 'workflow,replay'),
                        )
                        con.commit()
                    finally:
                        con.close()
                    output = 'saved to memory'
                else:
                    output = 'memory read'

            elif node_type == 'output':
                target = cfg.get('target', 'chat')
                output = f'→ {target}: {context["prev_output"][:300]}'
                yield f'data: {json.dumps({"type": "final_output", "run_id": run_id, "target": target, "result": context["prev_output"]})}\n\n'

            elif node_type == 'code':
                code = cfg.get('code', '')
                if code:
                    try:
                        # FIX: restrict exec() to safe builtins only — prevent RCE
                        _SAFE_BUILTINS = {
                            'print': print,
                            'len': len,
                            'range': range,
                            'list': list,
                            'dict': dict,
                            'set': set,
                            'tuple': tuple,
                            'str': str,
                            'int': int,
                            'float': float,
                            'bool': bool,
                            'abs': abs,
                            'sum': sum,
                            'min': min,
                            'max': max,
                            'sorted': sorted,
                            'enumerate': enumerate,
                            'zip': zip,
                            'map': map,
                            'filter': filter,
                            'round': round,
                            'isinstance': isinstance,
                            'type': type,
                            '__builtins__': None,
                        }
                        loc = {'input': context['prev_output'], 'output': ''}
                        exec(compile(code, '<workflow_node>', 'exec'), {'__builtins__': _SAFE_BUILTINS}, loc)
                        output = str(loc.get('output', context['prev_output']))[:500]
                        context['prev_output'] = output
                    except Exception as ex:
                        error = str(ex)
                        output = f'[code error] {ex}'
                else:
                    output = 'no code'

            # Record frame
            dur_ms = int((time.perf_counter() - t0) * 1000)
            frame_no += 1
            _record_frame(
                run_id,
                frame_no,
                nid,
                node_type,
                label,
                'node_output',
                {'input': context['input'], 'prev_output': context['prev_output'][:500]},
                output,
                error,
                dur_ms,
            )

            done_ev = {
                'type': 'node_output',
                'run_id': run_id,
                'frame': frame_no,
                'node_id': nid,
                'node_type': node_type,
                'label': label,
                'output': output[:300],
                'error': error,
                'duration_ms': dur_ms,
                'context_snapshot': {'prev_output': context['prev_output'][:200]},
            }
            yield f'data: {json.dumps(done_ev)}\n\n'

            for nxt in adj.get(nid, []):
                queue.append(nxt)

        total_ms = int((time.perf_counter() - run_start) * 1000)
        _finish_run(run_id, 'done', total_ms, len(visited))
        yield f'data: {json.dumps({"type": "done", "run_id": run_id, "total_ms": total_ms, "frames": frame_no})}\n\n'

    return StreamingResponse(
        _stream(), media_type='text/event-stream', headers={'Cache-Control': 'no-cache', 'X-Accel-Buffering': 'no'}
    )


# ── List runs ──────────────────────────────────────────────────────────────────
@router.get('/runs')
def list_runs(wf_id: str = '', limit: int = 50):
    """Retrieve and return list runs."""
    from ..services.memory_db import get_conn

    con = get_conn()
    try:
        if wf_id:
            rows = con.execute(
                'SELECT * FROM workflow_runs WHERE workflow_id=? ORDER BY created_at DESC LIMIT ?',
                (wf_id, min(limit, 200)),
            ).fetchall()
        else:
            rows = con.execute(
                'SELECT * FROM workflow_runs ORDER BY created_at DESC LIMIT ?', (min(limit, 200),)
            ).fetchall()
    finally:
        con.close()
    return {'runs': [dict(r) for r in rows], 'count': len(rows)}


@router.get('/runs/{run_id}')
def get_run(run_id: str):
    """Retrieve and return get run."""
    from ..services.memory_db import get_conn

    con = get_conn()
    try:
        run = con.execute('SELECT * FROM workflow_runs WHERE id=?', (run_id,)).fetchone()
        frames = con.execute('SELECT * FROM workflow_run_frames WHERE run_id=? ORDER BY frame_no', (run_id,)).fetchall()
    finally:
        con.close()
    if not run:
        return {'ok': False, 'error': 'Run not found'}
    return {
        'run': dict(run),
        'frames': [dict(f) for f in frames],
        'count': len(frames),
    }


@router.get('/runs/{run_id}/frames')
def get_frames(run_id: str, event_type: str = ''):
    """Retrieve and return get frames."""
    from ..services.memory_db import get_conn

    con = get_conn()
    try:
        if event_type:
            rows = con.execute(
                'SELECT * FROM workflow_run_frames WHERE run_id=? AND event_type=? ORDER BY frame_no',
                (run_id, event_type),
            ).fetchall()
        else:
            rows = con.execute(
                'SELECT * FROM workflow_run_frames WHERE run_id=? ORDER BY frame_no', (run_id,)
            ).fetchall()
    finally:
        con.close()
    return {'frames': [dict(r) for r in rows], 'count': len(rows)}


@router.get('/runs/{run_id}/frame/{frame_no}')
def get_frame(run_id: str, frame_no: int):
    """Retrieve and return get frame."""
    from ..services.memory_db import get_conn

    con = get_conn()
    try:
        row = con.execute(
            'SELECT * FROM workflow_run_frames WHERE run_id=? AND frame_no=?', (run_id, frame_no)
        ).fetchone()
    finally:
        con.close()
    if not row:
        return {'ok': False, 'error': 'Frame not found'}
    return dict(row)


@router.delete('/runs/{run_id}')
def delete_run(run_id: str):
    """Delete or remove specified run."""
    from ..services.memory_db import get_conn

    con = get_conn()
    try:
        con.execute('DELETE FROM workflow_run_frames WHERE run_id=?', (run_id,))
        con.execute('DELETE FROM workflow_runs WHERE id=?', (run_id,))
        con.commit()
    finally:
        con.close()
    return {'ok': True}


# ── Re-run from a specific frame ───────────────────────────────────────────────
@router.post('/runs/{run_id}/rerun-from/{frame_no}')
async def rerun_from_frame(run_id: str, frame_no: int, req: Request):
    """
    Re-run a workflow starting from a specific frame's node, using the
    context captured at that frame. Useful for debugging failures.
    """
    from ..services.memory_db import get_conn

    con = get_conn()
    try:
        run = con.execute('SELECT * FROM workflow_runs WHERE id=?', (run_id,)).fetchone()
        frame = con.execute(
            'SELECT * FROM workflow_run_frames WHERE run_id=? AND frame_no=?', (run_id, frame_no)
        ).fetchone()
    finally:
        con.close()

    if not run or not frame:
        return {'ok': False, 'error': 'Run or frame not found'}

    # Load saved context from frame
    saved_ctx = {}
    try:
        saved_ctx = json.loads(frame['input_ctx'] or '{}')
    except (KeyError, TypeError, ValueError, json.JSONDecodeError, OSError, AttributeError, RuntimeError):
        saved_ctx = {'input': run['input'] or '', 'prev_output': ''}

    # Load workflow
    wf_path = WF_DIR / f'{run["workflow_id"]}.json'
    if not wf_path.exists():
        return {'ok': False, 'error': 'Workflow file not found'}
    wf = json.loads(wf_path.read_text())

    new_run_id = f'run_{uuid.uuid4().hex[:10]}_rerun'
    _create_run(new_run_id, run['workflow_id'], wf.get('name', ''), saved_ctx.get('input', ''))

    async def _stream():
        nodes = {n['id']: n for n in wf.get('nodes', [])}
        edges = wf.get('edges', [])
        adj: dict[str, list[str]] = {}
        for e in edges:
            adj.setdefault(e['from'], []).append(e['to'])

        start_nid = frame['node_id']
        context = {**saved_ctx}
        visited: set[str] = set()
        queue = [start_nid]
        fn = 0
        run_start = time.perf_counter()

        yield f'data: {json.dumps({"type": "rerun_start", "run_id": new_run_id, "from_frame": frame_no, "node_id": start_nid})}\n\n'

        from ..services import llm as llm_svc

        while queue:
            nid = queue.pop(0)
            if nid in visited:
                continue
            visited.add(nid)
            node = nodes.get(nid)
            if not node:
                continue

            cfg = node.get('config', {})
            t0 = time.perf_counter()
            fn += 1
            label = node.get('label', node['type'])

            yield f'data: {json.dumps({"type": "node_start", "run_id": new_run_id, "frame": fn, "node_id": nid, "label": label})}\n\n'

            output = error = ''
            if node['type'] == 'agent':
                prompt = cfg.get('prompt', '{{input}}')
                prompt = prompt.replace('{{input}}', context.get('input', '')).replace(
                    '{{prev_output}}', context.get('prev_output', '')
                )
                try:
                    result = await llm_svc.complete(
                        [{'role': 'user', 'content': prompt}],
                        agent_id=cfg.get('agent_id', 'builder'),
                        max_tokens=1024,
                        inject_steering=False,
                    )
                    output = result.get('text', '')
                    context['prev_output'] = output
                except Exception as ex:
                    error = str(ex)
            else:
                output = f'[{node["type"]}] rerun'

            dur_ms = int((time.perf_counter() - t0) * 1000)
            fn += 1
            _record_frame(new_run_id, fn, nid, node['type'], label, 'node_output', context, output, error, dur_ms)
            yield f'data: {json.dumps({"type": "node_output", "run_id": new_run_id, "frame": fn, "node_id": nid, "output": output[:300], "duration_ms": dur_ms})}\n\n'

            for nxt in adj.get(nid, []):
                queue.append(nxt)

        total_ms = int((time.perf_counter() - run_start) * 1000)
        _finish_run(new_run_id, 'done', total_ms, len(visited))
        yield f'data: {json.dumps({"type": "done", "run_id": new_run_id, "original_run_id": run_id})}\n\n'

    return StreamingResponse(
        _stream(), media_type='text/event-stream', headers={'Cache-Control': 'no-cache', 'X-Accel-Buffering': 'no'}
    )


# ── Timeline data (for scrubber UI) ───────────────────────────────────────────
@router.get('/runs/{run_id}/timeline')
def get_timeline(run_id: str):
    """Return timeline-optimised data for the scrubber UI."""
    from ..services.memory_db import get_conn

    con = get_conn()
    try:
        run = con.execute('SELECT * FROM workflow_runs WHERE id=?', (run_id,)).fetchone()
        frames = con.execute(
            """SELECT id,frame_no,node_id,node_type,node_label,event_type,
                      output,error,duration_ms,timestamp
               FROM workflow_run_frames WHERE run_id=? ORDER BY frame_no""",
            (run_id,),
        ).fetchall()
    finally:
        con.close()
    if not run:
        return {'ok': False, 'error': 'Run not found'}

    run_d = dict(run)
    frames_d = [dict(f) for f in frames]

    # Build per-node groups for timeline lanes
    node_lanes: dict[str, list[dict]] = {}
    for f in frames_d:
        nid = f['node_id']
        node_lanes.setdefault(nid, []).append(f)

    # Compute relative timestamps
    if frames_d:
        t0 = frames_d[0]['timestamp'] or time.time()
        for f in frames_d:
            f['rel_ms'] = int((f['timestamp'] - t0) * 1000) if f['timestamp'] else 0

    return {
        'run': run_d,
        'frames': frames_d,
        'node_lanes': node_lanes,
        'duration_ms': run_d.get('total_ms', 0),
        'frame_count': len(frames_d),
    }


# ── Diff two runs ──────────────────────────────────────────────────────────────
@router.get('/diff/{run_id_a}/{run_id_b}')
def diff_runs(run_id_a: str, run_id_b: str):
    """Compare outputs of two runs node-by-node."""
    from ..services.memory_db import get_conn

    con = get_conn()
    try:
        a_frames = {
            r['node_id']: dict(r)
            for r in con.execute(
                "SELECT * FROM workflow_run_frames WHERE run_id=? AND event_type='node_output' ORDER BY frame_no",
                (run_id_a,),
            ).fetchall()
        }
        b_frames = {
            r['node_id']: dict(r)
            for r in con.execute(
                "SELECT * FROM workflow_run_frames WHERE run_id=? AND event_type='node_output' ORDER BY frame_no",
                (run_id_b,),
            ).fetchall()
        }
    finally:
        con.close()

    all_nodes = sorted(set(list(a_frames.keys()) + list(b_frames.keys())))
    diffs = []
    for nid in all_nodes:
        a = a_frames.get(nid)
        b = b_frames.get(nid)
        diffs.append(
            {
                'node_id': nid,
                'node_label': (a or b or {}).get('node_label', ''),
                'a_output': a['output'] if a else None,
                'b_output': b['output'] if b else None,
                'a_duration': a['duration_ms'] if a else None,
                'b_duration': b['duration_ms'] if b else None,
                'changed': (a['output'] if a else '') != (b['output'] if b else ''),
                'only_in': 'a' if not b else ('b' if not a else 'both'),
            }
        )

    return {
        'run_id_a': run_id_a,
        'run_id_b': run_id_b,
        'diffs': diffs,
        'changed_count': sum(1 for d in diffs if d['changed']),
    }
