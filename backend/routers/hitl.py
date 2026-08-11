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
from fastapi.responses import JSONResponse, StreamingResponse

from ..services.llm import sse_guard
from ..services.request_body import json_body_or_error

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

def _normalise_action(action_type: str) -> str:
    """Canonical form of an action name, for matching against ALWAYS_INTERRUPT.

    SECURITY FIX. `ALWAYS_INTERRUPT` is the hard list of actions that must reach
    a human no matter how confident the agent claims to be -- deleting files,
    sending email, charging cards, force-pushing. It was matched with a bare
    `in` against the caller's raw string, while `risk_level` right beside it was
    already `.lower()`ed. So the safety net was case- and punctuation-sensitive.

    Verified live, same action, confidence 0.99, risk_level 'low':

        action_type 'delete_file'  -> pending        (correct)
        action_type 'DELETE_FILE'  -> auto_approved  (!!)
        action_type 'delete_file ' -> auto_approved  (!!)
        action_type 'delete-file'  -> auto_approved  (!!)

    The caller is an AGENT emitting a free-form string, so exact-match was never
    a safe assumption: a model that writes "Delete_File" defeats the gate with
    no intent to. Case, surrounding whitespace, and the hyphen/underscore/dot/
    space split are all folded before the check.
    """
    canon = (action_type or '').strip().lower()
    for ch in ('-', '.', ' ', '/', ':'):
        canon = canon.replace(ch, '_')
    while '__' in canon:
        canon = canon.replace('__', '_')
    return canon.strip('_')


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


def _record_auto_approval(
    interrupt_id: str,
    agent_id: str,
    action_type: str,
    action_summary: str,
    action_data: dict,
    risk_level: str,
    confidence: float,
    reason: str,
) -> None:
    """Write a machine-approved action into the same records a human one uses.

    Best-effort: an audit write must never be the thing that stops an agent, so
    failures are logged rather than raised. Status is 'auto_approved', distinct
    from the human 'approve', so approval_rate can separate the two.
    """
    from ..services.memory_db import get_conn

    try:
        con = get_conn()
        try:
            con.execute(
                """INSERT INTO hitl_queue(id,agent_id,action_type,action_summary,action_data,
                                          risk_level,confidence,status,reviewer,review_note,reviewed_at)
                   VALUES (?,?,?,?,?,?,?,'auto_approved','system',?,CURRENT_TIMESTAMP)""",
                (
                    interrupt_id,
                    agent_id,
                    action_type,
                    action_summary,
                    json.dumps(action_data, default=str)[:4000],
                    risk_level,
                    confidence,
                    reason,
                ),
            )
            con.execute(
                'INSERT INTO hitl_audit(interrupt_id,decision,reviewer,note) VALUES (?,?,?,?)',
                (interrupt_id, 'auto_approved', 'system', reason),
            )
            con.commit()
        finally:
            con.close()
    except Exception as e:  # pragma: no cover - audit must not break the agent
        log.error('Could not record auto-approval %s: %s', interrupt_id, e)


# ── Core interrupt API ─────────────────────────────────────────────────────────
@router.post('/interrupt')
async def create_interrupt(req: Request):
    """
    Agent calls this before a risky action.
    Returns immediately with interrupt_id; agent polls or waits for decision.
    """
    body, _body_err = await json_body_or_error(req)
    if _body_err:
        return _body_err
    action_type = str(body.get('action_type', 'unknown'))[:100]
    action_summary = str(body.get('action_summary') or '')[:500]
    action_data = body.get('action_data', {}) if isinstance(body.get('action_data', {}), dict) else {}
    raw_risk = str(body.get('risk_level', 'medium')).lower().strip()
    risk_level = raw_risk
    risk_unrecognised = False
    if risk_level not in RISK_THRESHOLDS:
        # An unrecognised level silently became 'medium', which is the SECOND
        # most permissive setting. A caller that sends 'severe' or 'CRITICAL '
        # believes it has asked for the strictest gate and gets a 0.85 auto-
        # approve threshold instead. Fail towards oversight, not away from it,
        # and say that the value was not understood.
        risk_level = 'high'
        risk_unrecognised = bool(raw_risk)
    try:
        confidence = min(1.0, max(0.0, float(body.get('confidence', 0.5))))
    except (TypeError, ValueError):
        confidence = 0.5
    agent_id = str(body.get('agent_id', ''))[:64]
    undo_state = str(body.get('undo_state', ''))[:10000]

    interrupt_id = f'hitl_{uuid.uuid4().hex[:8]}'

    # Auto-approve low-risk high-confidence actions
    threshold = RISK_THRESHOLDS.get(risk_level, 1.0)
    canonical_action = _normalise_action(action_type)
    force_interrupt = canonical_action in ALWAYS_INTERRUPT or risk_level in ('high', 'critical')

    if not force_interrupt and confidence >= threshold:
        reason = f'Confidence {confidence:.0%} >= threshold {threshold:.0%}'
        # AUDIT FIX: an auto-approval was returned and then forgotten -- no row
        # in hitl_queue, none in hitl_audit, nothing in /stats. Verified live:
        # three destructive actions auto-approved, and the oversight record
        # moved by zero rows. This module's own docstring cites "EU AI Act
        # Article 14 compliance (documented human oversight)"; an approval
        # decision the system cannot show you afterwards is not documented
        # oversight, and it is precisely the decision most worth reviewing,
        # because no human saw it. Recorded as status='auto_approved' so it is
        # visible but never confused with a human 'approve'.
        _record_auto_approval(
            interrupt_id, agent_id, action_type, action_summary,
            action_data, risk_level, confidence, reason,
        )
        return {
            'ok': True,
            'interrupt_id': interrupt_id,
            'decision': 'auto_approved',
            'reason': reason,
            'auto': True,
            'recorded': True,
            'risk_level': risk_level,
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

    out = {
        'ok': True,
        'interrupt_id': interrupt_id,
        'decision': 'pending',
        'risk_level': risk_level,
        'confidence': confidence,
        'message': 'Awaiting human approval',
        'auto': False,
    }
    if risk_unrecognised:
        out['risk_level_note'] = (
            f"Unrecognised risk_level '{raw_risk}' — treated as 'high' (human review required). "
            f"Valid values: {', '.join(sorted(RISK_THRESHOLDS))}."
        )
    return out


@router.get('/interrupt/{interrupt_id}/wait')
async def wait_for_decision(interrupt_id: str, timeout_seconds: str = '300'):
    """SSE stream that resolves when a human approves/rejects."""
    # FIX 6: cap timeout to prevent indefinite SSE connections
    try:
        timeout_seconds = min(max(int(timeout_seconds), 10), 1800)
    except (TypeError, ValueError):
        timeout_seconds = 300

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

    return StreamingResponse(sse_guard(_stream()), media_type='text/event-stream', headers={'Cache-Control': 'no-cache', 'X-Accel-Buffering': 'no'}
    )


@router.post('/interrupt/{interrupt_id}/decide')
async def decide_interrupt(interrupt_id: str, req: Request):
    """Human approves, rejects, or modifies a pending interrupt."""
    body, _body_err = await json_body_or_error(req)
    if _body_err:
        return _body_err
    decision = body.get('decision', 'approve')  # approve|reject|modify
    note = (body.get('note', ''))[:500]
    reviewer = (body.get('reviewer', 'user'))[:64]
    modified = body.get('modified_action_data')  # optional modified args

    if decision not in ('approve', 'reject', 'modify'):
        return JSONResponse({'ok': False, 'error': 'decision must be approve/reject/modify'}, status_code=400)

    from ..services.memory_db import get_conn

    con = get_conn()
    try:
        # FIX 2: verify interrupt exists
        existing = con.execute('SELECT status FROM hitl_queue WHERE id=?', (interrupt_id,)).fetchone()
        if not existing:
            return JSONResponse({'ok': False, 'error': 'Interrupt not found'}, status_code=404)
        if existing['status'] != 'pending':
            return JSONResponse({'ok': False, 'error': f'Interrupt already decided: {existing["status"]}'}, status_code=409)
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
def _record_undo(snapshot_id: str, kind: str, target: str) -> None:
    """An undo reverses a human-approved action; that belongs in the audit trail.

    Nothing recorded undo execution anywhere, so the record showed the action
    approved and never showed it reverted.
    """
    from ..services.memory_db import get_conn

    try:
        con = get_conn()
        try:
            con.execute(
                'INSERT INTO hitl_audit(interrupt_id,decision,reviewer,note) VALUES (?,?,?,?)',
                (snapshot_id, 'undo', 'user', f'{kind} {target}'.strip()[:500]),
            )
            con.commit()
        finally:
            con.close()
    except Exception as e:  # pragma: no cover
        log.error('Could not record undo %s: %s', snapshot_id, e)


@router.post('/undo-snapshot')
async def save_undo_snapshot(req: Request):
    """Save state before a destructive action so it can be reverted."""
    body, _body_err = await json_body_or_error(req)
    if _body_err:
        return _body_err
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
        return JSONResponse({'ok': False, 'error': 'Snapshot not found'}, status_code=404)

    # FIX 9: columns are direct, not JSON-wrapped
    stype = row['state_type']
    sdata = row['state_data']

    if stype == 'file':
        # BUG FIX: every failure path here fell through to the generic
        # `{'ok': True, 'restored': stype}` at the bottom of the function, so an
        # undo that wrote NOTHING reported success. Verified live, both cases:
        #   snapshot with no action_id      -> {"ok":true,"restored":"file"}
        #   snapshot whose parent is missing -> {"ok":true,"restored":"file"}
        # This is the most damaging possible place for a false success: the user
        # has just been told their destructive action was reverted, so they stop
        # looking. Each failure now says what went wrong.
        path_str = row['action_id'] if row else ''
        if not path_str:
            return JSONResponse(
                {
                    'ok': False,
                    'error': 'This snapshot has no target path recorded, so the file cannot be restored. '
                    'Nothing was changed.',
                    'restored': None,
                },
                status_code=422,
            )
        from pathlib import Path as P

        try:
            p = P(path_str).resolve()
        except OSError as ex:
            return JSONResponse({'ok': False, 'error': f'Invalid undo path: {ex}'}, status_code=422)
        # FIX 10: path traversal protection — only allow writes inside project root
        allowed_root = P(__file__).resolve().parents[2]
        try:
            p.relative_to(allowed_root)
        except ValueError:
            return JSONResponse({'ok': False, 'error': 'Path traversal denied — undo path must be inside project root'}, status_code=403)
        if not p.parent.exists():
            return JSONResponse(
                {
                    'ok': False,
                    'error': f'Cannot restore {p}: its directory no longer exists. Nothing was changed.',
                    'restored': None,
                },
                status_code=422,
            )
        try:
            p.write_text(sdata, encoding='utf-8')
        except OSError as ex:
            return JSONResponse({'ok': False, 'error': str(ex), 'restored': None}, status_code=500)
        _record_undo(snapshot_id, 'file', str(p))
        return {'ok': True, 'restored': 'file', 'path': str(p)}
    elif stype == 'db':
        # Restore DB state — run SQL
        try:
            con2 = get_conn()
            try:
                con2.executescript(sdata)
                con2.commit()
            finally:
                con2.close()
            _record_undo(snapshot_id, 'db', '')
            return {'ok': True, 'restored': 'db'}
        except (OSError, sqlite3.Error) as ex:
            return JSONResponse({'ok': False, 'error': str(ex)}, status_code=500)

    # A custom type is genuinely not restorable by this endpoint. Saying
    # `ok: True, restored: <type>` implied it had been. `applied: False` makes
    # the distinction explicit for a caller that only checks `ok`.
    _record_undo(snapshot_id, stype, '')
    return {
        'ok': True,
        'applied': False,
        'restored': None,
        'state_type': stype,
        'note': f"No built-in undo for state_type '{stype}' — the application must apply this itself. "
        'Nothing was changed by this call.',
    }


# ── Queue management ───────────────────────────────────────────────────────────
@router.get('/queue')
def get_queue(status: str = 'pending', limit: int = 50):
    """Retrieve and return get queue."""
    from ..services.memory_db import get_conn

    con = get_conn()
    try:
        rows = con.execute(
            'SELECT * FROM hitl_queue WHERE status=? ORDER BY created_at DESC LIMIT ?', (status, max(1, min(limit, 200)))
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
        rows = con.execute('SELECT * FROM hitl_queue ORDER BY created_at DESC LIMIT ?', (max(1, min(limit, 500)),)).fetchall()
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
            (max(1, min(limit, 500)),),
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
        auto = con.execute("SELECT COUNT(*) FROM hitl_queue WHERE status='auto_approved'").fetchone()[0]
        avg_conf = con.execute('SELECT AVG(confidence) FROM hitl_queue').fetchone()[0]
    finally:
        con.close()
    reviewed = approved + rejected
    return {
        'total': total,
        'pending': pending,
        'approved': approved,
        'rejected': rejected,
        # Machine approvals are reported SEPARATELY and deliberately excluded
        # from approval_rate. Folding them in would let a flood of auto-approvals
        # push the rate towards 100% and read as "humans approve almost
        # everything" when in fact humans saw almost none of it. The share the
        # machine decided is the number an oversight reviewer actually wants.
        'auto_approved': auto,
        'human_reviewed': reviewed,
        'approval_rate': round(approved / reviewed * 100, 1) if reviewed else None,
        'approval_rate_basis': 'human decisions only; auto-approvals excluded',
        'auto_approval_share': round(auto / total * 100, 1) if total else 0.0,
        'avg_confidence': round(avg_conf, 2) if avg_conf is not None else None,
    }


@router.post('/assess-confidence')
async def assess_confidence(req: Request):
    """Use AI to assess the confidence/risk of a proposed action."""
    body, _body_err = await json_body_or_error(req)
    if _body_err:
        return _body_err
    # Accept both 'action' and 'task' as the action descriptor
    action = (body.get('action') or body.get('task') or '').strip()
    ctx_raw = body.get('context', '')
    # context may be a dict or a string — normalise to string
    import json as _json

    context = (_json.dumps(ctx_raw) if isinstance(ctx_raw, dict) else str(ctx_raw))[:1000]

    if not action:
        return JSONResponse({'ok': False, 'error': 'action or task required'}, status_code=400)

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
                return {'ok': True, 'assessed': True, **parsed}

    # BUG FIX: this used to fabricate a full assessment when the judge produced
    # nothing usable -- confidence 0.5, is_reversible True, and
    # recommendation 'proceed', returned with ok:true and no indication that no
    # assessment had taken place. Reproduced with a judge that answers in prose:
    #
    #   action: "rm -rf / on the production database"
    #   result: {"ok": true, "recommendation": "proceed", "is_reversible": true}
    #
    # That is the module-16 defect (an unrun judge scoring a malware response
    # "fully safe") in the one place it matters most: the component whose job is
    # deciding whether a human needs to look. An unavailable assessor must
    # escalate, never wave things through.
    log.warning('Confidence assessment unavailable — judge returned unusable output for: %s', action[:120])
    return JSONResponse(
        {
            'ok': False,
            'assessed': False,
            'error': 'The risk assessor did not return a usable assessment. '
            'This action has NOT been assessed — route it to a human.',
            'confidence': None,
            'risk_level': None,
            'is_reversible': None,
            'concerns': [],
            'recommendation': 'interrupt',
        },
        status_code=503,
    )
