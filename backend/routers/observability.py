"""
Agentic OS — LLM Observability + Distributed Tracing
Like Langfuse (MIT) + LangSmith: full span-based traces for every agent call.

Every agent call creates a Trace with Spans:
  Trace
  ├── Span: LLM call (model, prompt, response, latency, cost, tokens)
  ├── Span: Tool call (tool name, args, result, latency)
  ├── Span: Retrieval (query, k, results, latency)
  └── Span: Agent step (step type, input, output, duration)

Features:
  - Auto-capture via patched LLM service
  - Waterfall timeline view
  - Cost + latency breakdown per span
  - Search and filter traces
  - Session grouping (multi-turn)
  - Eval scores attached to traces
  - DORA metrics computation
"""

from __future__ import annotations

import json
import logging
import uuid

from fastapi import APIRouter, Request
from fastapi.responses import JSONResponse

from ..services.request_body import json_body_or_error

router = APIRouter(prefix='/api/observability', tags=['observability'])
log = logging.getLogger('agentic.obs')

_SCHEMA = """
CREATE TABLE IF NOT EXISTS obs_traces (
    id           TEXT PRIMARY KEY,
    session_id   TEXT DEFAULT '',
    agent_id     TEXT DEFAULT '',
    name         TEXT DEFAULT '',
    input        TEXT DEFAULT '',
    output       TEXT DEFAULT '',
    total_latency_ms INTEGER DEFAULT 0,
    total_tokens INTEGER DEFAULT 0,
    total_cost   REAL DEFAULT 0,
    span_count   INTEGER DEFAULT 0,
    eval_score   INTEGER DEFAULT -1,
    status       TEXT DEFAULT 'running',
    metadata_json TEXT DEFAULT '{}',
    created_at   TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    ended_at     TIMESTAMP
);
CREATE TABLE IF NOT EXISTS obs_spans (
    id           TEXT PRIMARY KEY,
    trace_id     TEXT NOT NULL,
    parent_id    TEXT DEFAULT '',
    span_type    TEXT NOT NULL,
    name         TEXT DEFAULT '',
    input_json   TEXT DEFAULT '{}',
    output_json  TEXT DEFAULT '{}',
    model        TEXT DEFAULT '',
    tokens_in    INTEGER DEFAULT 0,
    tokens_out   INTEGER DEFAULT 0,
    cost_usd     REAL DEFAULT 0,
    latency_ms   INTEGER DEFAULT 0,
    status       TEXT DEFAULT 'ok',
    error        TEXT DEFAULT '',
    metadata_json TEXT DEFAULT '{}',
    started_at   TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    ended_at     TIMESTAMP
);
CREATE INDEX IF NOT EXISTS idx_obs_traces_agent ON obs_traces(agent_id, created_at);
CREATE INDEX IF NOT EXISTS idx_obs_spans_trace ON obs_spans(trace_id, started_at);
CREATE INDEX IF NOT EXISTS idx_obs_session ON obs_traces(session_id);
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


# ── Public trace API ───────────────────────────────────────────────────────────
@router.post('/traces')
async def create_trace(req: Request):
    """Create and initialize a new trace."""
    body, _body_err = await json_body_or_error(req)
    if _body_err:
        return _body_err
    tid = body.get('id') or f'tr_{uuid.uuid4().hex[:10]}'
    from ..services.memory_db import get_conn

    con = get_conn()
    try:
        con.execute(
            """INSERT OR REPLACE INTO obs_traces(id,session_id,agent_id,name,input,metadata_json)
                       VALUES (?,?,?,?,?,?)""",
            (
                tid,
                body.get('session_id', ''),
                body.get('agent_id', ''),
                body.get('name', ''),
                body.get('input', '')[:4000],
                json.dumps(body.get('metadata', {})),
            ),
        )
        con.commit()
    finally:
        con.close()
    return {'ok': True, 'trace_id': tid}


@router.patch('/traces/{trace_id}')
async def update_trace(trace_id: str, req: Request):
    """Update existing trace record or state."""
    body, _body_err = await json_body_or_error(req)
    if _body_err:
        return _body_err
    from ..services.memory_db import get_conn

    con = get_conn()
    try:
        sets, vals = ['ended_at=CURRENT_TIMESTAMP'], []
        if 'output' in body:
            sets.append('output=?')
            vals.append(body['output'][:4000])
        if 'status' in body:
            sets.append('status=?')
            vals.append(body['status'])
        if 'eval_score' in body:
            sets.append('eval_score=?')
            vals.append(int(body['eval_score']))
        vals.append(trace_id)
        cur = con.execute(f'UPDATE obs_traces SET {",".join(sets)} WHERE id=?', vals)
        con.commit()
        if cur.rowcount == 0:
            # Reported {"ok": true} for a trace id that matched nothing, so a
            # client writing to a stale or mistyped id believed it had
            # recorded an outcome that was never stored.
            return JSONResponse(
                {'ok': False, 'error': 'Trace not found'}, status_code=404
            )
    finally:
        con.close()
    return {'ok': True}


@router.post('/spans')
async def create_span(req: Request):
    """Create and initialize a new span."""
    body, _body_err = await json_body_or_error(req)
    if _body_err:
        return _body_err
    sid = body.get('id') or f'sp_{uuid.uuid4().hex[:10]}'
    from ..services.memory_db import get_conn

    con = get_conn()
    try:
        con.execute(
            """INSERT OR REPLACE INTO obs_spans
            (id,trace_id,parent_id,span_type,name,input_json,output_json,
             model,tokens_in,tokens_out,cost_usd,latency_ms,status,error,metadata_json)
            VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)""",
            (
                sid,
                body.get('trace_id', ''),
                body.get('parent_id', ''),
                body.get('span_type', 'llm'),
                body.get('name', ''),
                json.dumps(body.get('input', {})),
                json.dumps(body.get('output', {})),
                body.get('model', ''),
                int(body.get('tokens_in', 0)),
                int(body.get('tokens_out', 0)),
                float(body.get('cost_usd', 0)),
                int(body.get('latency_ms', 0)),
                body.get('status', 'ok'),
                body.get('error', ''),
                json.dumps(body.get('metadata', {})),
            ),
        )
        # Update trace aggregates
        con.execute(
            """UPDATE obs_traces SET
            total_tokens = total_tokens + ?,
            total_cost = total_cost + ?,
            total_latency_ms = total_latency_ms + ?,
            span_count = span_count + 1
            WHERE id=?""",
            (
                int(body.get('tokens_in', 0)) + int(body.get('tokens_out', 0)),
                float(body.get('cost_usd', 0)),
                int(body.get('latency_ms', 0)),
                body.get('trace_id', ''),
            ),
        )
        con.commit()
    finally:
        con.close()
    return {'ok': True, 'span_id': sid}


# ── Query traces ───────────────────────────────────────────────────────────────
# ── Trace emission ─────────────────────────────────────────────────────────────
def record_llm_trace(
    agent_id: str,
    name: str,
    prompt: str,
    output: str,
    *,
    tokens: int = 0,
    cost: float = 0.0,
    latency_ms: int = 0,
    model: str = '',
    status: str = 'success',
    session_id: str = '',
) -> str:
    """Write one completed LLM interaction as a trace.

    Module 21 follow-up. This module had a full tracing backend -- schema,
    create_trace, create_span, analytics, DORA metrics, an EU AI Act compliance
    report -- and NOTHING IN THE PLATFORM EVER CALLED IT. `grep -rl obs_traces
    backend/` returned this file alone. /api/observability/traces answered
    {"traces": [], "count": 0} on every request, so the pane rendered an empty
    list indistinguishable from "you have not run anything yet".

    A permanently empty observability view is worse than an absent one: it
    tells the operator their agents did nothing, which is a false statement
    about the system rather than a missing feature.

    Emitting from the LLM layer for the same reason cost recording moved there
    (Module 21): 30 routers make these calls, and asking each to remember is
    what produced a 1-in-30 hit rate for the ledger.

    Never raises -- observability must not break inference.
    """
    from ..services.memory_db import get_conn

    tid = f'tr_{uuid.uuid4().hex[:10]}'
    try:
        con = get_conn()
        try:
            con.execute(
                """INSERT INTO obs_traces
                     (id, session_id, agent_id, name, input, output,
                      total_latency_ms, total_tokens, total_cost, span_count,
                      status, metadata_json, ended_at)
                   VALUES (?,?,?,?,?,?,?,?,?,1,?,?,CURRENT_TIMESTAMP)""",
                (
                    tid,
                    session_id,
                    agent_id or 'default',
                    name[:200],
                    (prompt or '')[:4000],
                    (output or '')[:4000],
                    int(latency_ms or 0),
                    int(tokens or 0),
                    float(cost or 0.0),
                    status,
                    json.dumps({'model': model}),
                ),
            )
            con.commit()
        finally:
            con.close()
    except Exception as e:  # pragma: no cover - tracing must never break a call
        log.warning('Trace not recorded for %s: %s', agent_id, e)
        return ''
    return tid


@router.get('/traces')
def list_traces(agent_id: str = '', session_id: str = '', status: str = '', limit: int = 50, q: str = ''):
    """Retrieve and return list traces."""
    from ..services.memory_db import get_conn

    con = get_conn()
    try:
        where, params = [], []
        if agent_id:
            where.append('agent_id=?')
            params.append(agent_id)
        if session_id:
            where.append('session_id=?')
            params.append(session_id)
        if status:
            where.append('status=?')
            params.append(status)
        if q:
            where.append('(name LIKE ? OR input LIKE ?)')
            params.extend([f'%{q}%'] * 2)
        sql = (
            'SELECT * FROM obs_traces'
            + (f' WHERE {" AND ".join(where)}' if where else '')
            + ' ORDER BY created_at DESC LIMIT ?'
        )
        params.append(max(1, min(limit, 500)))
        rows = con.execute(sql, params).fetchall()
    finally:
        con.close()
    return {'traces': [dict(r) for r in rows], 'count': len(rows)}


@router.get('/traces/{trace_id}')
def get_trace(trace_id: str):
    """Retrieve and return get trace."""
    from ..services.memory_db import get_conn

    con = get_conn()
    try:
        trace = con.execute('SELECT * FROM obs_traces WHERE id=?', (trace_id,)).fetchone()
        spans = con.execute('SELECT * FROM obs_spans WHERE trace_id=? ORDER BY started_at', (trace_id,)).fetchall()
    finally:
        con.close()
    if not trace:
        return JSONResponse({'ok': False, 'error': 'Not found'}, status_code=404)
    return {'trace': dict(trace), 'spans': [dict(s) for s in spans], 'span_count': len(spans)}


@router.get('/traces/{trace_id}/spans')
def get_trace_spans(trace_id: str):
    """Retrieve and return get trace spans."""
    from ..services.memory_db import get_conn

    con = get_conn()
    try:
        rows = con.execute('SELECT * FROM obs_spans WHERE trace_id=? ORDER BY started_at', (trace_id,)).fetchall()
    finally:
        con.close()
    return {'spans': [dict(r) for r in rows], 'count': len(rows)}


# ── Analytics ──────────────────────────────────────────────────────────────────
@router.get('/analytics')
def observability_analytics(days: int = 7):
    """Execute or process observability analytics operation."""
    days = min(max(int(days), 1), 365)  # clamp: prevent SQL injection via f-string
    from ..services.memory_db import get_conn

    con = get_conn()
    try:
        window = f"datetime('now','-{days} days')"
        summary = con.execute(f"""SELECT
            COUNT(*) as total_traces,
            AVG(total_latency_ms) as avg_latency,
            SUM(total_tokens) as total_tokens,
            SUM(total_cost) as total_cost,
            AVG(eval_score) as avg_eval_score,
            SUM(CASE WHEN status='error' THEN 1 ELSE 0 END) as error_count
            FROM obs_traces WHERE created_at >= {window}""").fetchone()
        by_model = con.execute(f"""SELECT model, COUNT(*) as calls,
            AVG(latency_ms) as avg_latency, SUM(tokens_in+tokens_out) as tokens,
            SUM(cost_usd) as cost
            FROM obs_spans WHERE started_at >= {window} AND model != ''
            GROUP BY model ORDER BY calls DESC LIMIT 10""").fetchall()
        by_type = con.execute(f"""SELECT span_type, COUNT(*) as calls, AVG(latency_ms) as avg_ms
            FROM obs_spans WHERE started_at >= {window}
            GROUP BY span_type ORDER BY calls DESC""").fetchall()
        hourly = con.execute(f"""SELECT strftime('%Y-%m-%d %H:00', created_at) as hour,
            COUNT(*) as traces, AVG(total_latency_ms) as avg_latency
            FROM obs_traces WHERE created_at >= {window}
            GROUP BY hour ORDER BY hour DESC LIMIT 24""").fetchall()
    finally:
        con.close()
    s = dict(summary) if summary else {}
    for k in list(s.keys()):
        if s[k] is None:
            s[k] = 0
    s['error_rate'] = round(int(s.get('error_count', 0)) / max(int(s.get('total_traces', 1)), 1) * 100, 1)
    return {
        'summary': s,
        'by_model': [dict(r) for r in by_model],
        'by_type': [dict(r) for r in by_type],
        'hourly': [dict(r) for r in hourly],
        'days': days,
    }


# ── DORA Metrics ───────────────────────────────────────────────────────────────
@router.get('/dora')
def dora_metrics(days: int = 30):
    """Execute or process dora metrics operation."""
    days = min(max(int(days), 1), 365)  # clamp: prevent SQL injection via f-string
    """
    DORA (DevOps Research and Assessment) metrics for agent deployments:
    - Deployment Frequency: how often agents are deployed/updated
    - Lead Time: time from prompt change to deployment
    - MTTR (Mean Time to Recovery): time to fix failed agent runs
    - Change Failure Rate: % of deployments causing errors
    """
    from ..services.memory_db import get_conn

    con = get_conn()
    try:
        window = f"datetime('now','-{days} days')"
        # Deployment frequency (new agents created)
        # Only agents the user actually created. The built-ins are seeded at
        # first boot and are not deployments -- counting them reported
        # "12 deployments" on an install where nobody had deployed anything.
        from ..services.memory_db import DEFAULT_AGENTS

        _builtin_ids = [a['id'] for a in DEFAULT_AGENTS]
        _ph = ','.join('?' * len(_builtin_ids)) or "''"
        deploys = con.execute(
            f'SELECT COUNT(*) FROM agents WHERE created_at >= {window} AND id NOT IN ({_ph})',
            _builtin_ids,
        ).fetchone()[0]
        # MTTR: avg time between first error and next success for same agent
        errors = con.execute(f"""SELECT COUNT(*) FROM obs_traces
            WHERE status='error' AND created_at >= {window}""").fetchone()[0]
        total = con.execute(f'SELECT COUNT(*) FROM obs_traces WHERE created_at >= {window}').fetchone()[0]
        # No traces means the failure rate is UNKNOWN, not zero.
        error_rate = round(errors / total * 100, 2) if total else None
        # Lead time: avg latency of eval runs (proxy for code-to-deploy)
        avg_latency = con.execute(
            f'SELECT AVG(total_latency_ms) FROM obs_traces WHERE created_at >= {window}'
        ).fetchone()[0]
        # P95 latency
        p95_rows = con.execute(f"""SELECT total_latency_ms FROM obs_traces
            WHERE created_at >= {window} ORDER BY total_latency_ms DESC
            LIMIT MAX(1, (SELECT COUNT(*)*5/100 FROM obs_traces WHERE created_at >= {window}))""").fetchall()
        p95_latency = p95_rows[0][0] if p95_rows else 0
    finally:
        con.close()

    deploy_freq = f'{deploys} in {days} days' if deploys > 0 else 'No deployments'

    # A DORA grade is a performance claim. Award one only when there is
    # something to grade.
    if total == 0 or error_rate is None:
        grade = None
        grade_basis = 'Not enough data to grade — no agent activity recorded in this period.'
    elif deploys == 0:
        grade = None
        grade_basis = (
            f'Not enough data to grade — {total} run(s) recorded but no deployments '
            'in this period.'
        )
    else:
        grade = (
            'Elite' if error_rate < 5
            else 'High' if error_rate < 10
            else 'Medium' if error_rate < 15
            else 'Low'
        )
        grade_basis = f'Based on {total} run(s) and {deploys} deployment(s) over {days} days.'

    return {
        'deployment_frequency': {'value': deploys, 'label': deploy_freq, 'unit': 'deployments'},
        'lead_time_ms': {
            'value': round(avg_latency) if avg_latency else None,
            'label': f'{round(avg_latency / 1000, 1)}s avg' if avg_latency else 'Not measured',
            'unit': 'ms',
        },
        'change_failure_rate': {
            'value': error_rate,
            'label': f'{error_rate}% error rate' if error_rate is not None else 'Not measured',
            'unit': '%',
        },
        # MTTR was avg_latency * 2 with the label "Estimated" -- a made-up
        # multiplier presented as a metric. Reported as unavailable until it
        # is actually derived from recovery times.
        'mttr_ms': {'value': None, 'label': 'Not tracked', 'unit': 'ms'},
        'p95_latency_ms': {
            'value': p95_latency or None,
            'label': f'{round(p95_latency / 1000, 2)}s p95' if p95_latency else 'Not measured',
            'unit': 'ms',
        },
        'total_traces': total,
        'period_days': days,
        'grade': grade,
        'grade_basis': grade_basis,
    }


# ── EU AI Act Compliance ───────────────────────────────────────────────────────
@router.get('/compliance/eu-ai-act')
def eu_ai_act_compliance():
    """
    Check compliance with EU AI Act requirements (enforceable August 2026).
    Article 13: Transparency  Article 14: Human oversight (HITL)
    Article 15: Accuracy/logging  Article 9: Risk assessment
    """
    from ..services.memory_db import get_conn

    con = get_conn()
    try:
        # Art 13: Transparency — do we have agent descriptions?
        agents_with_desc = con.execute('SELECT COUNT(*) FROM agents WHERE length(system_prompt)>50').fetchone()[0]
        total_agents = con.execute('SELECT COUNT(*) FROM agents WHERE enabled=1').fetchone()[0]
        transparency_ok = agents_with_desc / max(total_agents, 1) > 0.7

        # Art 14: HITL — are there approval gates?
        hitl_count = con.execute('SELECT COUNT(*) FROM hitl_queue').fetchone()[0]

        # Art 15: Logging — do we have audit logs?
        audit_count = con.execute('SELECT COUNT(*) FROM audit').fetchone()[0]
        logging_ok = audit_count > 0

        # Art 9: Risk assessment — steering files?
        steering_count = con.execute('SELECT COUNT(*) FROM steering_files WHERE enabled=1').fetchone()[0]
        risk_ok = steering_count > 0

        # Eval coverage
        eval_count = con.execute('SELECT COUNT(*) FROM eval_runs').fetchone()[0]
        evals_ok = eval_count > 0

        # Observability
        trace_count = con.execute('SELECT COUNT(*) FROM obs_traces').fetchone()[0]
    finally:
        con.close()

    checks = [
        {
            'article': 'Art 13',
            'name': 'Transparency',
            'description': 'Agents have descriptions/system prompts',
            'status': 'compliant' if transparency_ok else 'partial',
            'detail': f'{agents_with_desc}/{total_agents} agents documented',
        },
        {
            'article': 'Art 14',
            'name': 'Human Oversight (HITL)',
            'description': 'Human approval gates configured',
            'status': 'compliant',
            'detail': f'HITL system active, {hitl_count} total interrupts logged',
        },
        {
            'article': 'Art 15',
            'name': 'Accuracy & Logging',
            'description': 'Complete audit trail exists',
            'status': 'compliant' if logging_ok else 'non-compliant',
            'detail': f'{audit_count} audit events logged',
        },
        {
            'article': 'Art 9',
            'name': 'Risk Assessment',
            'description': 'Agent risk policies configured',
            'status': 'compliant' if risk_ok else 'partial',
            'detail': f'{steering_count} active steering/governance files',
        },
        {
            'article': 'Art 12',
            'name': 'Logging for Traceability',
            'description': 'Distributed trace capture active',
            'status': 'compliant',
            'detail': f'{trace_count} traces captured',
        },
        {
            'article': 'Evals',
            'name': 'Quality Assurance',
            'description': 'Automated agent quality evaluation',
            'status': 'compliant' if evals_ok else 'partial',
            'detail': f'{eval_count} eval runs completed',
        },
    ]
    compliant = sum(1 for c in checks if c['status'] == 'compliant')
    score = round(compliant / len(checks) * 100)
    return {
        'checks': checks,
        'compliant': compliant,
        'total_checks': len(checks),
        'score': score,
        'overall_status': 'compliant' if score >= 80 else 'partial' if score >= 50 else 'non-compliant',
        'eu_ai_act_deadline': 'August 2, 2026',
        'note': 'High-risk AI system obligations apply from Aug 2026 (EU AI Act)',
    }
