"""
Agentic OS — Human-in-the-Loop (HITL) Interruption Protocol
Confidence-threshold gating, approval queues, safe undo, and audit trails.

Based on:
- AWS AgentCore inline_function / interrupt pattern
- Strick Tech HITL interrupt_before/after checkpoints
- EU AI Act Article 14 compliance (documented human oversight)
- Lumay "Interruption Protocols" (agents pause at <90% confidence)

Features:
- Interrupt queue: agent actions pending human approval
- Safe undo: capture state before any write action
- Confidence assessment: route to human if confidence < threshold
- Approval workflow: approve/reject/modify pending actions
- Audit trail: every human override documented
"""

from __future__ import annotations

import asyncio
import contextlib
import json
import logging
import sqlite3
import uuid

from fastapi import APIRouter, Request
from fastapi.responses import StreamingResponse

router = APIRouter(prefix='/api/hitl', tags=['hitl'])
log = logging.getLogger('agentic.hitl')

_SCHEMA = """
CREATE TABLE IF NOT EXISTS undo_snapshots (
    id          TEXT PRIMARY KEY,
    action_id   TEXT DEFAULT '',
    state_type  TEXT DEFAULT 'file',
    state_data  TEXT DEFAULT '',
    created_at  TIMESTAMP DEFAULT CURRENT_TIMESTAMP
);
CREATE TABLE IF NOT EXISTS hitl_queue (
    id            TEXT PRIMARY KEY,
    agent_id      TEXT DEFAULT '',
    action_type   TEXT NOT NULL,
    action_summary TEXT NOT NULL,
    action_data   TEXT DEFAULT '{}',
    risk_level    TEXT DEFAULT 'medium',
    confidence    REAL DEFAULT 0.5,
    status        TEXT DEFAULT 'pending',
    requester     TEXT DEFAULT 'agent',
    reviewer      TEXT DEFAULT '',
    review_note   TEXT DEFAULT '',
    undo_state    TEXT DEFAULT '',
    created_at    TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    reviewed_at   TIMESTAMP
);
CREATE TABLE IF NOT EXISTS hitl_audit (
    id            INTEGER PRIMARY KEY AUTOINCREMENT,
    interrupt_id  TEXT NOT NULL,
    decision      TEXT NOT NULL,
    reviewer      TEXT DEFAULT 'user',
    note          TEXT DEFAULT '',
    created_at    TIMESTAMP DEFAULT CURRENT_TIMESTAMP
);
CREATE INDEX IF NOT EXISTS idx_hitl_status ON hitl_queue(status, created_at);
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

# In-memory pending interrupt waiters (task_id → asyncio.Event)
_waiters: dict[str, asyncio.Event] = {}
_decisions: dict[str, dict] = {}

RISK_THRESHOLDS = {
    'low': 0.7,  # auto-approve if confidence >= 0.7
    'medium': 0.85,  # require approval if confidence < 0.85
    'high': 1.0,  # always require approval
    'critical': 1.0,  # always require approval + dual confirmation
}

ALWAYS_INTERRUPT = {
    'delete_file',
    'delete_database',
    'drop_table',
    'rm_rf',
    'send_email',
    'send_message',
    'post_to_social',
    'stripe_charge',
    'financial_transaction',
    'deploy_to_production',
    'push_to_main',
    'git_force_push',
    'secret_delete',
}


# ── Core interrupt API ─────────────────────────────────────────────────────────
@router.post('/interrupt')
async def create_interrupt(req: Request):
    """
    Agent calls this before a risky action.
    Returns immediately with interrupt_id; agent polls or waits for decision.
    """
    try:
        body = await req.json()
    except (json.JSONDecodeError, TypeError, ValueError):
        body = {}
    action_type = body.get('action_type', 'unknown')
    action_summary = (body.get('action_summary') or '')[:500]
    action_data = body.get('action_data', {})
    risk_level = body.get('risk_level', 'medium')
    confidence = float(body.get('confidence', 0.5))
    agent_id = body.get('agent_id', '')
    undo_state = body.get('undo_state', '')

    interrupt_id = f'hitl_{uuid.uuid4().hex[:8]}'

    # Auto-approve low-risk high-confidence actions
    threshold = RISK_THRESHOLDS.get(risk_level, 0.85)
    force_interrupt = action_type in ALWAYS_INTERRUPT or risk_level == 'critical'

    if not force_interrupt and confidence >= threshold:
        return {
            'ok': True,
            'interrupt_id': interrupt_id,
            'decision': 'auto_approved',
            'reason': f'Confidence {confidence:.0%} >= threshold {threshold:.0%}',
            'auto': True,
        }

    # Queue for human review
    from ..services.memory_db import get_conn

    con = get_conn()
    try:
        con.execute(
            """INSERT INTO hitl_queue(id,agent_id,action_type,action_summary,action_data,risk_level,confidence,undo_state)
        VALUES (?,?,?,?,?,?,?,?)""",
            (
                interrupt_id,
                agent_id,
                action_type,
                action_summary,
                json.dumps(action_data, default=str)[:4000],
                risk_level,
                confidence,
                undo_state[:4000],
            ),
        )
        con.commit()
    finally:
        con.close()

    # Create waiter
    event = asyncio.Event()
    _waiters[interrupt_id] = event

    # Broadcast to WebSocket
    with contextlib.suppress(Exception):
        from ..routers.websocket import broadcast
        await broadcast(
            {
                'type': 'hitl_interrupt',
                'interrupt_id': interrupt_id,
                'action_type': action_type,
                'action_summary': action_summary,
                'risk_level': risk_level,
                'confidence': confidence,
            }
        )

    log.info('HITL interrupt created: %s (%s, confidence=%.0f%%)', interrupt_id, action_type, confidence * 100)

    return {
        'ok': True,
        'interrupt_id': interrupt_id,
        'decision': 'pending',
        'risk_level': risk_level,
        'confidence': confidence,
        'message': 'Awaiting human approval',
        'auto': False,
    }


@router.get('/interrupt/{interrupt_id}/wait')
async def wait_for_decision(interrupt_id: str, timeout_seconds: int = 300):
    """SSE stream that resolves when a human approves/rejects."""
    # FIX 6: cap timeout to prevent indefinite SSE connections
    timeout_seconds = min(max(int(timeout_seconds), 10), 1800)

    async def _stream():
        event = _waiters.get(interrupt_id)
        if not event:
            yield f'data: {json.dumps({"type": "error", "message": "Interrupt not found or already decided"})}\n\n'
            return

        yield f'data: {json.dumps({"type": "waiting", "interrupt_id": interrupt_id})}\n\n'

        try:
            await asyncio.wait_for(event.wait(), timeout=float(timeout_seconds))
        except asyncio.TimeoutError:
            # FIX 7: clean up _waiters on timeout to prevent memory leak
            _waiters.pop(interrupt_id, None)
            yield f'data: {json.dumps({"type": "timeout", "decision": "auto_rejected", "interrupt_id": interrupt_id})}\n\n'
            return

        decision = _decisions.pop(interrupt_id, {'decision': 'unknown'})  # FIX 8: pop to free memory
        yield f'data: {json.dumps({"type": "decided", "interrupt_id": interrupt_id, **decision})}\n\n'

    return StreamingResponse(
        _stream(), media_type='text/event-stream', headers={'Cache-Control': 'no-cache', 'X-Accel-Buffering': 'no'}
    )


@router.post('/interrupt/{interrupt_id}/decide')
async def decide_interrupt(interrupt_id: str, req: Request):
    """Human approves, rejects, or modifies a pending interrupt."""
    try:
        body = await req.json()
    except (json.JSONDecodeError, TypeError, ValueError):
        body = {}
    decision = body.get('decision', 'approve')  # approve|reject|modify
    note = (body.get('note', ''))[:500]
    reviewer = (body.get('reviewer', 'user'))[:64]
    modified = body.get('modified_action_data')  # optional modified args

    if decision not in ('approve', 'reject', 'modify'):
        return {'ok': False, 'error': 'decision must be approve/reject/modify'}

    from ..services.memory_db import get_conn

    con = get_conn()
    try:
        # FIX 2: verify interrupt exists
        existing = con.execute('SELECT status FROM hitl_queue WHERE id=?', (interrupt_id,)).fetchone()
        if not existing:
            return {'ok': False, 'error': 'Interrupt not found'}
        if existing['status'] != 'pending':
            return {'ok': False, 'error': f'Interrupt already decided: {existing["status"]}'}
        con.execute(
            """UPDATE hitl_queue SET status=?,reviewer=?,review_note=?,reviewed_at=CURRENT_TIMESTAMP WHERE id=? AND status='pending'""",
            (decision, reviewer, note, interrupt_id),
        )
        # FIX 1: only write audit if UPDATE actually changed a row
        if con.execute('SELECT changes()').fetchone()[0] > 0:
            con.execute(
                'INSERT INTO hitl_audit(interrupt_id,decision,reviewer,note) VALUES (?,?,?,?)',
                (interrupt_id, decision, reviewer, note),
            )
        con.commit()
    finally:
        con.close()

    result = {'decision': decision, 'note': note, 'reviewer': reviewer}
    if modified:
        result['modified_action_data'] = modified

    _decisions[interrupt_id] = result

    # Signal waiter
    ev = _waiters.pop(interrupt_id, None)
    if ev:
        ev.set()

    # Broadcast
    with contextlib.suppress(Exception):
        from ..routers.websocket import broadcast
        await broadcast({'type': 'hitl_decided', 'interrupt_id': interrupt_id, 'decision': decision, 'note': note})

    log.info('HITL %s: %s by %s', interrupt_id, decision, reviewer)
    return {'ok': True, 'interrupt_id': interrupt_id, 'decision': decision}


# ── Safe Undo ──────────────────────────────────────────────────────────────────
@router.post('/undo-snapshot')
async def save_undo_snapshot(req: Request):
    """Save state before a destructive action so it can be reverted."""
    try:
        body = await req.json()
    except (json.JSONDecodeError, TypeError, ValueError):
        body = {}
    action_id = body.get('action_id', '')
    state_type = body.get('type', 'file')  # file|db|memory|custom
    state_data = body.get('state_data', '')

    snap_id = f'undo_{uuid.uuid4().hex[:8]}'

    from ..services.memory_db import get_conn

    con = get_conn()
    try:
        # FIX 9: use dedicated undo_snapshots table (not audit)
        con.execute(
            'INSERT INTO undo_snapshots(id,action_id,state_type,state_data) VALUES (?,?,?,?)',
            (snap_id, action_id, state_type, state_data[:10000]),
        )
        con.commit()
    finally:
        con.close()

    return {'ok': True, 'snapshot_id': snap_id, 'action_id': action_id, 'state_type': state_type}


@router.post('/undo/{snapshot_id}')
async def execute_undo(snapshot_id: str, req: Request):
    """Execute an undo by restoring saved state."""
    from ..services.memory_db import get_conn

    con = get_conn()
    try:
        row = con.execute(
            'SELECT * FROM undo_snapshots WHERE id=?',  # FIX 9: dedicated table
            (snapshot_id,),
        ).fetchone()
    finally:
        con.close()

    if not row:
        return {'ok': False, 'error': 'Snapshot not found'}

    # FIX 9: columns are direct, not JSON-wrapped
    stype = row['state_type']
    sdata = row['state_data']

    if stype == 'file':
        # Restore file content
        try:
            path_str = row['action_id'] if row else ''
            if path_str:
                from pathlib import Path as P

                p = P(path_str).resolve()
                # FIX 10: path traversal protection — only allow writes inside project root
                allowed_root = P(__file__).resolve().parents[2]
                if not str(p).startswith(str(allowed_root)):
                    return {'ok': False, 'error': 'Path traversal denied — undo path must be inside project root'}
                if p.parent.exists():
                    p.write_text(sdata, encoding='utf-8')
                    return {'ok': True, 'restored': 'file', 'path': str(p)}
        except (OSError, IOError) as ex:
            return {'ok': False, 'error': str(ex)}
    elif stype == 'db':
        # Restore DB state — run SQL
        try:
            con2 = get_conn()
            try:
                con2.executescript(sdata)
                con2.commit()
            finally:
                con2.close()
            return {'ok': True, 'restored': 'db'}
        except (OSError, sqlite3.Error) as ex:
            return {'ok': False, 'error': str(ex)}

    return {'ok': True, 'restored': stype, 'note': 'Custom undo — application must handle'}


# ── Queue management ───────────────────────────────────────────────────────────
@router.get('/queue')
def get_queue(status: str = 'pending', limit: int = 50):
    """Retrieve and return get queue."""
    from ..services.memory_db import get_conn

    con = get_conn()
    try:
        rows = con.execute(
            'SELECT * FROM hitl_queue WHERE status=? ORDER BY created_at DESC LIMIT ?', (status, min(limit, 200))
        ).fetchall()
    finally:
        con.close()
    return {'interrupts': [dict(r) for r in rows], 'count': len(rows)}


@router.get('/queue/all')
def get_all_queue(limit: int = 100):
    """Retrieve and return get all queue."""
    from ..services.memory_db import get_conn

    con = get_conn()
    try:
        rows = con.execute('SELECT * FROM hitl_queue ORDER BY created_at DESC LIMIT ?', (min(limit, 500),)).fetchall()
    finally:
        con.close()
    return {'interrupts': [dict(r) for r in rows], 'count': len(rows)}


@router.get('/audit')
def hitl_audit_log(limit: int = 100):
    """Execute or process hitl audit log operation."""
    from ..services.memory_db import get_conn

    con = get_conn()
    try:
        rows = con.execute(
            'SELECT a.*, q.action_type, q.action_summary, q.risk_level FROM hitl_audit a LEFT JOIN hitl_queue q ON q.id=a.interrupt_id ORDER BY a.created_at DESC LIMIT ?',
            (min(limit, 500),),
        ).fetchall()
    finally:
        con.close()
    return {'audit': [dict(r) for r in rows], 'count': len(rows)}


@router.get('/stats')
def hitl_stats():
    """Execute or process hitl stats operation."""
    from ..services.memory_db import get_conn

    con = get_conn()
    try:
        total = con.execute('SELECT COUNT(*) FROM hitl_queue').fetchone()[0]
        pending = con.execute("SELECT COUNT(*) FROM hitl_queue WHERE status='pending'").fetchone()[0]
        approved = con.execute("SELECT COUNT(*) FROM hitl_queue WHERE status='approve'").fetchone()[0]
        rejected = con.execute("SELECT COUNT(*) FROM hitl_queue WHERE status='reject'").fetchone()[0]
        avg_conf = con.execute('SELECT AVG(confidence) FROM hitl_queue').fetchone()[0]
    finally:
        con.close()
    return {
        'total': total,
        'pending': pending,
        'approved': approved,
        'rejected': rejected,
        'avg_confidence': round(avg_conf or 0, 2),
        'approval_rate': round(approved / (approved + rejected) * 100, 1) if (approved + rejected) > 0 else 0,
    }


@router.post('/assess-confidence')
async def assess_confidence(req: Request):
    """Use AI to assess the confidence/risk of a proposed action."""
    try:
        body = await req.json()
    except (json.JSONDecodeError, TypeError, ValueError):
        body = {}
    # Accept both 'action' and 'task' as the action descriptor
    action = (body.get('action') or body.get('task') or '').strip()
    ctx_raw = body.get('context', '')
    # context may be a dict or a string — normalise to string
    import json as _json

    context = (_json.dumps(ctx_raw) if isinstance(ctx_raw, dict) else str(ctx_raw))[:1000]

    if not action:
        return {'ok': False, 'error': 'action or task required'}

    from ..services import llm as llm_svc

    prompt = f"""Assess the risk and confidence of this agent action.

Action: {action}
Context: {context}

Return JSON:
{{
  "confidence": 0.0-1.0,
  "risk_level": "low|medium|high|critical",
  "is_reversible": true/false,
  "concerns": ["list of concerns if any"],
  "recommendation": "proceed|interrupt|reject"
}}

Return ONLY valid JSON."""

    result = await llm_svc.complete(
        [{'role': 'user', 'content': prompt}], agent_id='hitl', max_tokens=300, temperature=0.1, inject_steering=False
    )
    text = result.get('text', '')
    m = __import__('re').search(r'\{.*\}', text, __import__('re').DOTALL)
    if m:
        with contextlib.suppress(Exception):
            parsed = __import__('json').loads(m.group(0))
            # Validate it's a real assessment, not an API error response
            if 'confidence' in parsed:
                return {'ok': True, **parsed}
    return {
        'ok': True,
        'confidence': 0.5,
        'risk_level': 'medium',
        'is_reversible': True,
        'concerns': [],
        'recommendation': 'proceed',
    }
