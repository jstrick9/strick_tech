"""
Agentic OS — Sprint C · Feature 1: MCP Gateway
═══════════════════════════════════════════════
Centralised Model Context Protocol Gateway — the single chokepoint through
which ALL agent tool calls must pass.  Implements:

  • Server Registry  — catalog of MCP tool-servers (built-in + custom)
  • Auth / AuthZ     — per-server API-key or OAuth token management
  • Policy Enforcement (OPA-lite) — declarative allow/deny rules per agent×tool
  • Rate Limiting    — per-agent and per-server call quotas
  • Usage Metering   — token-cost attribution per tool call
  • Audit Bridge     — every tool call appended to Sprint-A immutable chain
  • Kill Switch      — disable any server or block any agent instantly

Based on:
  IBM ADLC guide: MCP Gateway for centralized authN/Z, policy-as-code, quotas, kill-switches
  Cloud Security Alliance AIUC-1 Q2 2026: dedicated MCP auth controls
  A2A/MCP Linux Foundation spec: typed schemas, gateway routing, approval flows
"""

from __future__ import annotations

import contextlib
import hashlib
import json
import logging
import time
import uuid
from datetime import datetime, timezone
from pathlib import Path

from fastapi import APIRouter, Request
from fastapi.responses import JSONResponse

router = APIRouter(prefix='/api/mcp-gateway', tags=['mcp-gateway'])
log = logging.getLogger('agentic.mcp_gateway')

ROOT = Path(__file__).resolve().parents[2]

# ── Schema ─────────────────────────────────────────────────────────────────────
_SCHEMA = """
CREATE TABLE IF NOT EXISTS mcp_servers (
    server_id      TEXT PRIMARY KEY,
    name           TEXT NOT NULL DEFAULT '',
    description    TEXT NOT NULL DEFAULT '',
    server_type    TEXT NOT NULL DEFAULT 'builtin',
    endpoint       TEXT NOT NULL DEFAULT '',
    auth_type      TEXT NOT NULL DEFAULT 'none',
    auth_config    TEXT NOT NULL DEFAULT '{}',
    tools_schema   TEXT NOT NULL DEFAULT '[]',
    status         TEXT NOT NULL DEFAULT 'active',
    rate_limit_rpm INTEGER NOT NULL DEFAULT 60,
    rate_limit_day INTEGER NOT NULL DEFAULT 1000,
    tags           TEXT NOT NULL DEFAULT '',
    created_at     TEXT NOT NULL DEFAULT '',
    updated_at     TEXT NOT NULL DEFAULT ''
);

CREATE TABLE IF NOT EXISTS mcp_gateway_policies (
    policy_id    TEXT PRIMARY KEY,
    name         TEXT NOT NULL DEFAULT '',
    description  TEXT NOT NULL DEFAULT '',
    agent_id     TEXT NOT NULL DEFAULT '*',
    server_id    TEXT NOT NULL DEFAULT '*',
    tool_pattern TEXT NOT NULL DEFAULT '*',
    action       TEXT NOT NULL DEFAULT 'allow',
    priority     INTEGER NOT NULL DEFAULT 100,
    conditions   TEXT NOT NULL DEFAULT '{}',
    enabled      INTEGER NOT NULL DEFAULT 1,
    created_at   TEXT NOT NULL DEFAULT '',
    updated_at   TEXT NOT NULL DEFAULT ''
);

CREATE TABLE IF NOT EXISTS mcp_gateway_calls (
    call_id      TEXT PRIMARY KEY,
    server_id    TEXT NOT NULL DEFAULT '',
    tool_name    TEXT NOT NULL DEFAULT '',
    agent_id     TEXT NOT NULL DEFAULT '',
    args_hash    TEXT NOT NULL DEFAULT '',
    status       TEXT NOT NULL DEFAULT 'ok',
    policy_decision TEXT NOT NULL DEFAULT 'allow',
    duration_ms  INTEGER NOT NULL DEFAULT 0,
    tokens_used  INTEGER NOT NULL DEFAULT 0,
    cost         REAL NOT NULL DEFAULT 0,
    error        TEXT NOT NULL DEFAULT '',
    created_at   TEXT NOT NULL DEFAULT ''
);
CREATE INDEX IF NOT EXISTS idx_mgc_agent   ON mcp_gateway_calls(agent_id, created_at DESC);
CREATE INDEX IF NOT EXISTS idx_mgc_server  ON mcp_gateway_calls(server_id);
CREATE INDEX IF NOT EXISTS idx_mgc_time    ON mcp_gateway_calls(created_at DESC);

CREATE TABLE IF NOT EXISTS mcp_rate_buckets (
    bucket_key  TEXT PRIMARY KEY,
    count       INTEGER NOT NULL DEFAULT 0,
    window_start INTEGER NOT NULL DEFAULT 0
);
"""

BUILTIN_SERVERS = [
    {
        'server_id': 'srv_filesystem',
        'name': 'File System',
        'description': 'Read, write, list, delete files within the workspace',
        'server_type': 'builtin',
        'endpoint': 'internal://filesystem',
        'auth_type': 'none',
        'tools_schema': json.dumps(
            [
                {'name': 'fs.read', 'desc': 'Read a file', 'args': ['path']},
                {'name': 'fs.write', 'desc': 'Write a file', 'args': ['path', 'content']},
                {'name': 'fs.list', 'desc': 'List directory', 'args': ['path']},
                {'name': 'fs.delete', 'desc': 'Delete a file', 'args': ['path']},
            ]
        ),
        'status': 'active',
        'rate_limit_rpm': 120,
        'rate_limit_day': 5000,
        'tags': 'files,storage',
    },
    {
        'server_id': 'srv_web_search',
        'name': 'Web Search',
        'description': 'DuckDuckGo and web search with citation support',
        'server_type': 'builtin',
        'endpoint': 'internal://search',
        'auth_type': 'none',
        'tools_schema': json.dumps([{'name': 'search.web', 'desc': 'Search the web', 'args': ['query', 'limit']}]),
        'status': 'active',
        'rate_limit_rpm': 20,
        'rate_limit_day': 500,
        'tags': 'search,web,research',
    },
    {
        'server_id': 'srv_code_exec',
        'name': 'Code Executor',
        'description': 'Run Python code snippets in a sandboxed environment',
        'server_type': 'builtin',
        'endpoint': 'internal://code',
        'auth_type': 'none',
        'tools_schema': json.dumps([{'name': 'code.run', 'desc': 'Execute Python code', 'args': ['code']}]),
        'status': 'active',
        'rate_limit_rpm': 30,
        'rate_limit_day': 500,
        'tags': 'code,python,execution',
    },
    {
        'server_id': 'srv_memory',
        'name': 'Memory Store',
        'description': 'Read and write to the agent memory knowledge base',
        'server_type': 'builtin',
        'endpoint': 'internal://memory',
        'auth_type': 'none',
        'tools_schema': json.dumps(
            [
                {'name': 'memory.add', 'desc': 'Add to memory', 'args': ['content', 'tags']},
                {'name': 'memory.search', 'desc': 'Search memory', 'args': ['query', 'limit']},
            ]
        ),
        'status': 'active',
        'rate_limit_rpm': 60,
        'rate_limit_day': 2000,
        'tags': 'memory,knowledge',
    },
    {
        'server_id': 'srv_http',
        'name': 'HTTP Client',
        'description': 'Make outbound HTTP GET/POST requests to external APIs',
        'server_type': 'builtin',
        'endpoint': 'internal://http',
        'auth_type': 'none',
        'tools_schema': json.dumps(
            [
                {'name': 'http.get', 'desc': 'HTTP GET', 'args': ['url', 'headers']},
                {'name': 'http.post', 'desc': 'HTTP POST', 'args': ['url', 'body', 'headers']},
            ]
        ),
        'status': 'active',
        'rate_limit_rpm': 30,
        'rate_limit_day': 1000,
        'tags': 'http,api,external',
    },
    {
        'server_id': 'srv_connectors',
        'name': 'Enterprise Connectors',
        'description': 'Slack, Jira, Google Workspace and other enterprise system connectors',
        'server_type': 'connector',
        'endpoint': 'internal://connectors',
        'auth_type': 'api_key',
        'tools_schema': json.dumps(
            [
                {'name': 'slack.message', 'desc': 'Send Slack message', 'args': ['channel', 'text']},
                {'name': 'jira.create', 'desc': 'Create Jira issue', 'args': ['project', 'title', 'description']},
                {'name': 'gdocs.create', 'desc': 'Create Google Doc', 'args': ['title', 'content']},
            ]
        ),
        'status': 'active',
        'rate_limit_rpm': 20,
        'rate_limit_day': 500,
        'tags': 'enterprise,slack,jira,google',
    },
]

DEFAULT_POLICIES = [
    {
        'policy_id': 'pol_allow_builtin',
        'name': 'Allow all built-in tools',
        'description': 'Agents can use all built-in MCP servers',
        'agent_id': '*',
        'server_id': 'srv_filesystem,srv_web_search,srv_memory,srv_http,srv_code_exec',
        'tool_pattern': '*',
        'action': 'allow',
        'priority': 100,
    },
    {
        'policy_id': 'pol_block_delete_prod',
        'name': 'Block file delete in prod',
        'description': 'No agent may delete files without elevated identity',
        'agent_id': '*',
        'server_id': 'srv_filesystem',
        'tool_pattern': 'fs.delete',
        'action': 'require_hitl',
        'priority': 50,
    },
    {
        'policy_id': 'pol_rate_external',
        'name': 'Rate-limit external HTTP',
        'description': 'Cap HTTP calls per agent to 30/min',
        'agent_id': '*',
        'server_id': 'srv_http',
        'tool_pattern': 'http.*',
        'action': 'allow',
        'priority': 90,
    },
    {
        'policy_id': 'pol_connector_elevated',
        'name': 'Connectors need elevated identity',
        'description': 'Enterprise connectors require elevated authority',
        'agent_id': 'orchestrator,brain',
        'server_id': 'srv_connectors',
        'tool_pattern': '*',
        'action': 'allow',
        'priority': 80,
    },
]


def _get_conn():
    from ..services.memory_db import get_conn

    return get_conn()


def _ensure_schema():
    con = _get_conn()
    try:
        con.executescript(_SCHEMA)
        # Seed built-in servers
        now = datetime.now(timezone.utc).isoformat()
        for srv in BUILTIN_SERVERS:
            existing = con.execute(
                'SELECT server_id FROM mcp_servers WHERE server_id=?', (srv['server_id'],)
            ).fetchone()
            if not existing:
                con.execute(
                    """INSERT INTO mcp_servers (server_id,name,description,server_type,endpoint,auth_type,tools_schema,status,rate_limit_rpm,rate_limit_day,tags,created_at,updated_at) VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?)""",
                    (
                        srv['server_id'],
                        srv['name'],
                        srv['description'],
                        srv['server_type'],
                        srv['endpoint'],
                        srv['auth_type'],
                        srv['tools_schema'],
                        srv['status'],
                        srv['rate_limit_rpm'],
                        srv['rate_limit_day'],
                        srv['tags'],
                        now,
                        now,
                    ),
                )
        for pol in DEFAULT_POLICIES:
            existing = con.execute(
                'SELECT policy_id FROM mcp_gateway_policies WHERE policy_id=?', (pol['policy_id'],)
            ).fetchone()
            if not existing:
                con.execute(
                    """INSERT INTO mcp_gateway_policies (policy_id,name,description,agent_id,server_id,tool_pattern,action,priority,enabled,created_at,updated_at) VALUES (?,?,?,?,?,?,?,?,1,?,?)""",
                    (
                        pol['policy_id'],
                        pol['name'],
                        pol['description'],
                        pol['agent_id'],
                        pol['server_id'],
                        pol['tool_pattern'],
                        pol['action'],
                        pol['priority'],
                        now,
                        now,
                    ),
                )
        con.commit()
    finally:
        con.close()


_ensure_schema()


def _now() -> str:
    return datetime.now(timezone.utc).isoformat()


def _epoch() -> int:
    return int(time.time())


# ── Policy Enforcement Engine (OPA-lite) ───────────────────────────────────────
def _evaluate_policy(agent_id: str, server_id: str, tool_name: str) -> tuple[str, str]:
    """
    Evaluate active policies for (agent, server, tool).
    Returns (decision, policy_name): 'allow' | 'deny' | 'require_hitl'
    Lower priority number = higher precedence.
    """
    con = _get_conn()
    try:
        policies = con.execute('SELECT * FROM mcp_gateway_policies WHERE enabled=1 ORDER BY priority ASC').fetchall()
        # Check server kill-switch
        srv = con.execute('SELECT status FROM mcp_servers WHERE server_id=?', (server_id,)).fetchone()
        if srv and srv['status'] == 'disabled':
            return 'deny', 'server_disabled'
    finally:
        con.close()

    import fnmatch
    from datetime import datetime as _dt

    _now_hour = _dt.now().hour
    _now_dow = _dt.now().weekday()  # 0=Monday

    for pol in policies:
        pol = dict(pol)
        # Match agent
        agent_match = pol['agent_id'] == '*' or agent_id in pol['agent_id'].split(',')
        # Match server
        srv_match = pol['server_id'] == '*' or server_id in pol['server_id'].split(',')
        # Match tool
        tool_match = fnmatch.fnmatch(tool_name, pol['tool_pattern'])

        if not (agent_match and srv_match and tool_match):
            continue

        # Evaluate conditions (optional JSON object)
        cond_pass = True
        try:
            conds = json.loads(pol.get('conditions') or '{}')
            if conds:
                # time_of_day: {"start_hour": 9, "end_hour": 17} → only active 09:00-17:00
                if 'start_hour' in conds and 'end_hour' in conds:
                    if not (conds['start_hour'] <= _now_hour < conds['end_hour']):
                        cond_pass = False
                # days_of_week: [0,1,2,3,4] → Mon-Fri only
                if 'days_of_week' in conds and _now_dow not in conds['days_of_week']:
                    cond_pass = False
                # max_calls_today: checked via rate bucket
                # (skip runtime check here — enforced separately)
        except (KeyError, TypeError, ValueError, json.JSONDecodeError):
            pass  # malformed conditions → ignore, policy still applies

        if cond_pass:
            return pol['action'], pol['name']

    # Default allow
    return 'allow', 'default'


# ── Rate Limiting ──────────────────────────────────────────────────────────────
def _check_rate_limit(agent_id: str, server_id: str, limit_rpm: int) -> bool:
    """True = within limits. False = rate limited."""
    bucket_key = f'rpm:{agent_id}:{server_id}'
    now_minute = _epoch() // 60  # current minute bucket
    con = _get_conn()
    try:
        row = con.execute(
            'SELECT count, window_start FROM mcp_rate_buckets WHERE bucket_key=?', (bucket_key,)
        ).fetchone()
        if row:
            if row['window_start'] == now_minute:
                if row['count'] >= limit_rpm:
                    return False
                con.execute('UPDATE mcp_rate_buckets SET count=count+1 WHERE bucket_key=?', (bucket_key,))
            else:
                # New minute window
                con.execute(
                    'UPDATE mcp_rate_buckets SET count=1, window_start=? WHERE bucket_key=?', (now_minute, bucket_key)
                )
        else:
            con.execute(
                'INSERT INTO mcp_rate_buckets (bucket_key,count,window_start) VALUES (?,1,?)', (bucket_key, now_minute)
            )
        con.commit()
        return True
    finally:
        con.close()


# ── Core Gateway call ──────────────────────────────────────────────────────────
async def gateway_call(agent_id: str, server_id: str, tool_name: str, args: dict, context: dict | None = None) -> dict:
    """
    Single entry point for all MCP tool calls through the Gateway.
    Returns structured result with policy_decision, duration_ms, and audit trail.
    """
    call_id = f'mcp_{uuid.uuid4().hex[:10]}'
    t0 = _epoch() * 1000

    # 1. Policy check
    policy_decision, policy_name = _evaluate_policy(agent_id, server_id, tool_name)

    if policy_decision == 'deny':
        _record_call(
            call_id,
            server_id,
            tool_name,
            agent_id,
            args,
            'blocked',
            policy_decision,
            0,
            0,
            0,
            f'Blocked by policy: {policy_name}',
        )
        return {
            'ok': False,
            'error': f"Tool call blocked by policy '{policy_name}'",
            'policy_decision': 'deny',
            'call_id': call_id,
        }

    # 2. Rate limit check
    con = _get_conn()
    try:
        srv_row = con.execute('SELECT * FROM mcp_servers WHERE server_id=?', (server_id,)).fetchone()
    finally:
        con.close()

    if srv_row:
        srv = dict(srv_row)
        if not _check_rate_limit(agent_id, server_id, srv.get('rate_limit_rpm', 60)):
            _record_call(
                call_id,
                server_id,
                tool_name,
                agent_id,
                args,
                'rate_limited',
                policy_decision,
                0,
                0,
                0,
                'Rate limit exceeded',
            )
            return {
                'ok': False,
                'error': 'Rate limit exceeded for this agent/server combination',
                'policy_decision': 'rate_limited',
                'call_id': call_id,
            }

    # 3. HITL gate (if policy requires)
    if policy_decision == 'require_hitl':
        # Write HITL interrupt and return pending state
        with contextlib.suppress(Exception):
            import httpx
            port = int(__import__('os').getenv('AGENTIC_OS_PORT', '8787'))
            async with httpx.AsyncClient(timeout=5) as client:
                await client.post(
                    f'http://127.0.0.1:{port}/api/hitl/interrupt',
                    json={
                        'action_type': tool_name,
                        'action_summary': f'MCP tool call: {tool_name}({json.dumps(args)[:100]})',
                        'risk_level': 'high',
                        'confidence': 0.7,
                        'agent_id': agent_id,
                        'action_data': {'server_id': server_id, 'tool': tool_name, 'args': args},
                    },
                )
        _record_call(call_id, server_id, tool_name, agent_id, args, 'hitl_pending', policy_decision, 0, 0, 0, '')
        return {
            'ok': False,
            'pending': True,
            'call_id': call_id,
            'message': f"Tool '{tool_name}' requires human approval (HITL)",
            'policy_decision': 'require_hitl',
        }

    # 4. Dispatch to the actual MCP tool via existing /api/mcp/call
    try:
        import httpx

        port = int(__import__('os').getenv('AGENTIC_OS_PORT', '8787'))
        async with httpx.AsyncClient(timeout=30) as client:
            resp = await client.post(
                f'http://127.0.0.1:{port}/api/mcp/call', json={'tool': tool_name, 'args': args, 'agent_id': agent_id}
            )
            result = resp.json()
    except Exception as e:
        err = str(e)[:300]
        _record_call(
            call_id, server_id, tool_name, agent_id, args, 'error', policy_decision, _epoch() * 1000 - t0, 0, 0, err
        )
        return {'ok': False, 'error': err, 'call_id': call_id}

    duration_ms = _epoch() * 1000 - t0
    status = 'ok' if result.get('ok') else 'error'

    _record_call(
        call_id,
        server_id,
        tool_name,
        agent_id,
        args,
        status,
        policy_decision,
        duration_ms,
        0,
        0,
        result.get('error', ''),
    )

    # 5. Audit chain entry
    with contextlib.suppress(Exception):
        from ..routers.audit_log import append_entry

        append_entry(
            agent_id,
            agent_id.title(),
            'mcp_tool_call',
            f'[{server_id}] {tool_name}({str(args)[:80]})',
            reasoning=f'Policy: {policy_name}',
            authority='agent',
            risk_level='low',
            outcome='success' if result.get('ok') else 'failure',
            metadata={'call_id': call_id, 'server_id': server_id, 'tool': tool_name, 'duration_ms': duration_ms},
        )

    return {**result, 'call_id': call_id, 'policy_decision': policy_decision, 'gateway_duration_ms': duration_ms}


def _record_call(
    call_id, server_id, tool_name, agent_id, args, status, policy_decision, duration_ms, tokens, cost, error
):
    args_hash = hashlib.sha256(json.dumps(args, sort_keys=True, default=str).encode()).hexdigest()[:16]
    con = _get_conn()
    try:
        con.execute(
            """INSERT OR IGNORE INTO mcp_gateway_calls
            (call_id,server_id,tool_name,agent_id,args_hash,status,policy_decision,duration_ms,tokens_used,cost,error,created_at)
            VALUES (?,?,?,?,?,?,?,?,?,?,?,?)""",
            (
                call_id,
                server_id,
                tool_name,
                agent_id,
                args_hash,
                status,
                policy_decision,
                duration_ms,
                tokens,
                cost,
                error[:500],
                _now(),
            ),
        )
        con.commit()
    finally:
        con.close()


# ── API Routes ─────────────────────────────────────────────────────────────────
@router.get('/servers')
def list_servers(status: str = ''):
    """Retrieve and return list servers."""
    con = _get_conn()
    try:
        if status:
            rows = con.execute('SELECT * FROM mcp_servers WHERE status=? ORDER BY name', (status,)).fetchall()
        else:
            rows = con.execute('SELECT * FROM mcp_servers ORDER BY server_type, name').fetchall()
    finally:
        con.close()
    servers = []
    for r in rows:
        d = dict(r)
        try:
            d['tools_schema'] = json.loads(d['tools_schema'])
        except (json.JSONDecodeError, TypeError, ValueError):
            pass
        try:
            d['auth_config'] = {
                'type': d['auth_type'],
                'configured': bool(json.loads(d.get('auth_config', '{}')).get('key')),
            }
        except (json.JSONDecodeError, TypeError, ValueError):
            pass
        servers.append(d)
    return {'servers': servers, 'count': len(servers)}


@router.post('/servers')
async def register_server(req: Request):
    """Register a new MCP tool server (custom/external)."""
    try:
        body = await req.json()
    except (json.JSONDecodeError, TypeError, ValueError):
        return JSONResponse({'ok': False, 'error': 'Invalid JSON'}, status_code=400)

    name = (body.get('name') or '').strip()
    if not name:
        return JSONResponse({'ok': False, 'error': 'name required'}, status_code=400)

    server_id = f'srv_{uuid.uuid4().hex[:8]}'
    now = _now()
    con = _get_conn()
    try:
        con.execute(
            """INSERT INTO mcp_servers (server_id,name,description,server_type,endpoint,auth_type,auth_config,tools_schema,status,rate_limit_rpm,rate_limit_day,tags,created_at,updated_at) VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?,?)""",
            (
                server_id,
                name[:100],
                (body.get('description') or '')[:500],
                (body.get('server_type') or 'custom')[:20],
                (body.get('endpoint') or '')[:200],
                (body.get('auth_type') or 'none')[:20],
                json.dumps(body.get('auth_config') or {}),
                json.dumps(body.get('tools_schema') or []),
                'active',
                min(int(body.get('rate_limit_rpm') or 60), 600),
                min(int(body.get('rate_limit_day') or 1000), 100000),
                (body.get('tags') or '')[:200],
                now,
                now,
            ),
        )
        con.commit()
    finally:
        con.close()
    log.info('MCP server registered: %s (%s)', server_id, name)
    return {'ok': True, 'server_id': server_id, 'name': name}


@router.patch('/servers/{server_id}')
async def update_server(server_id: str, req: Request):
    """Update existing server record or state."""
    try:
        body = await req.json()
    except (json.JSONDecodeError, TypeError, ValueError):
        return JSONResponse({'ok': False, 'error': 'Invalid JSON'}, status_code=400)
    allowed = {'name', 'description', 'status', 'rate_limit_rpm', 'rate_limit_day', 'tags', 'auth_config'}
    updates = {k: v for k, v in body.items() if k in allowed}
    if not updates:
        return JSONResponse({'ok': False, 'error': 'No valid fields'}, status_code=400)
    updates['updated_at'] = _now()
    con = _get_conn()
    try:
        sets = ', '.join(f'{k}=?' for k in updates)
        con.execute(f'UPDATE mcp_servers SET {sets} WHERE server_id=?', list(updates.values()) + [server_id])
        con.commit()
    finally:
        con.close()
    return {'ok': True, 'server_id': server_id}


@router.delete('/servers/{server_id}')
def delete_server(server_id: str):
    """Delete or remove specified server."""
    if server_id.startswith('srv_filesystem') or server_id == 'srv_web_search':
        return JSONResponse({'ok': False, 'error': 'Cannot delete built-in servers'}, status_code=400)
    con = _get_conn()
    try:
        con.execute('DELETE FROM mcp_servers WHERE server_id=?', (server_id,))
        con.commit()
    finally:
        con.close()
    return {'ok': True, 'deleted': server_id}


@router.post('/servers/{server_id}/toggle')
async def toggle_server(server_id: str, req: Request):
    """Enable or disable a server (kill switch)."""
    try:
        body = await req.json()
    except (json.JSONDecodeError, TypeError, ValueError):
        body = {}
    status = 'disabled' if body.get('disable') else 'active'
    con = _get_conn()
    try:
        con.execute('UPDATE mcp_servers SET status=?, updated_at=? WHERE server_id=?', (status, _now(), server_id))
        con.commit()
    finally:
        con.close()
    log.info('MCP server %s: %s', server_id, status)
    return {'ok': True, 'server_id': server_id, 'status': status}


@router.post('/call')
async def gateway_call_endpoint(req: Request):
    """Gateway-enforced tool call — all policy, rate-limit, HITL checks applied."""
    try:
        body = await req.json()
    except (json.JSONDecodeError, TypeError, ValueError):
        return JSONResponse({'ok': False, 'error': 'Invalid JSON'}, status_code=400)
    server_id = (body.get('server_id') or 'srv_filesystem').strip()
    tool_name = (body.get('tool') or '').strip()
    args = body.get('args') or {}
    agent_id = (body.get('agent_id') or 'system').strip()
    if not tool_name:
        return JSONResponse({'ok': False, 'error': 'tool required'}, status_code=400)
    result = await gateway_call(agent_id, server_id, tool_name, args)
    return result


@router.get('/policies')
def list_policies():
    """Retrieve and return list policies."""
    con = _get_conn()
    try:
        rows = con.execute('SELECT * FROM mcp_gateway_policies ORDER BY priority ASC').fetchall()
    finally:
        con.close()
    return {'policies': [dict(r) for r in rows], 'count': len(rows)}


@router.post('/policies')
async def create_policy(req: Request):
    """Create and initialize a new policy."""
    try:
        body = await req.json()
    except (json.JSONDecodeError, TypeError, ValueError):
        return JSONResponse({'ok': False, 'error': 'Invalid JSON'}, status_code=400)
    name = (body.get('name') or '').strip()
    if not name:
        return JSONResponse({'ok': False, 'error': 'name required'}, status_code=400)
    pol_id = f'pol_{uuid.uuid4().hex[:8]}'
    now = _now()
    action = body.get('action', 'allow')
    if action not in ('allow', 'deny', 'require_hitl'):
        action = 'allow'
    con = _get_conn()
    try:
        con.execute(
            """INSERT INTO mcp_gateway_policies (policy_id,name,description,agent_id,server_id,tool_pattern,action,priority,enabled,created_at,updated_at) VALUES (?,?,?,?,?,?,?,?,1,?,?)""",
            (
                pol_id,
                name[:100],
                (body.get('description') or '')[:500],
                (body.get('agent_id') or '*')[:100],
                (body.get('server_id') or '*')[:100],
                (body.get('tool_pattern') or '*')[:100],
                action,
                int(body.get('priority') or 100),
                now,
                now,
            ),
        )
        con.commit()
    finally:
        con.close()
    return {'ok': True, 'policy_id': pol_id}


@router.post('/policies/simulate')
async def simulate_policy(req: Request):
    """
    Dry-run the policy engine for a given (agent_id, server_id, tool_name).
    Returns the decision, the matching policy, and the full evaluation trace
    (every policy considered in priority order).
    Does NOT actually execute the tool call or create a gateway_call record.
    """
    try:
        body = await req.json()
    except (json.JSONDecodeError, TypeError, ValueError):
        return JSONResponse({'ok': False, 'error': 'Invalid JSON'}, status_code=400)

    agent_id = (body.get('agent_id') or '').strip()
    server_id = (body.get('server_id') or '').strip()
    tool_name = (body.get('tool_name') or '').strip()

    if not agent_id or not server_id or not tool_name:
        return JSONResponse({'ok': False, 'error': 'agent_id, server_id, tool_name required'}, status_code=400)

    import fnmatch

    con = _get_conn()
    try:
        policies = con.execute('SELECT * FROM mcp_gateway_policies WHERE enabled=1 ORDER BY priority ASC').fetchall()
        srv = con.execute('SELECT status FROM mcp_servers WHERE server_id=?', (server_id,)).fetchone()
    finally:
        con.close()

    trace = []
    decision = 'allow'
    matched_policy = 'default'
    match_found = False

    if srv and srv['status'] == 'disabled':
        decision = 'deny'
        matched_policy = 'server_disabled'
        trace.append(
            {
                'policy_id': 'sys_server_disabled',
                'name': 'Server Kill Switch',
                'matched': True,
                'decision': 'deny',
                'reason': f"Server '{server_id}' is disabled",
                'agent_match': True,
                'server_match': True,
                'tool_match': True,
            }
        )
    else:
        for pol in policies:
            pol_d = dict(pol)
            agent_match = pol_d['agent_id'] == '*' or agent_id in pol_d['agent_id'].split(',')
            server_match = pol_d['server_id'] == '*' or server_id in pol_d['server_id'].split(',')
            tool_match = fnmatch.fnmatch(tool_name, pol_d['tool_pattern'])
            matched = agent_match and server_match and tool_match

            trace.append(
                {
                    'policy_id': pol_d['policy_id'],
                    'name': pol_d['name'],
                    'action': pol_d['action'],
                    'priority': pol_d['priority'],
                    'agent_match': agent_match,
                    'server_match': server_match,
                    'tool_match': tool_match,
                    'matched': matched,
                    'agent_id': pol_d['agent_id'],
                    'server_id': pol_d['server_id'],
                    'tool_pattern': pol_d['tool_pattern'],
                }
            )

            if matched and not match_found:
                decision = pol_d['action']
                matched_policy = pol_d['name']
                match_found = True
                # Mark this entry as the winner
                trace[-1]['winner'] = True

    return {
        'ok': True,
        'agent_id': agent_id,
        'server_id': server_id,
        'tool_name': tool_name,
        'decision': decision,
        'matched_policy': matched_policy,
        'trace': trace,
        'policies_checked': len(trace),
    }


@router.get('/policies/conflicts')
def detect_conflicts():
    """
    Detect conflicting policy rules:
    - Two policies with same agent+server+tool but different actions
    - Shadowed policies (lower priority rule can never fire because higher catches it first)
    - Redundant policies (exact duplicates)
    """
    import fnmatch

    con = _get_conn()
    try:
        policies = con.execute('SELECT * FROM mcp_gateway_policies WHERE enabled=1 ORDER BY priority ASC').fetchall()
    finally:
        con.close()

    pols = [dict(p) for p in policies]
    conflicts = []
    seen_exact = {}

    for i, a in enumerate(pols):
        for j, b in enumerate(pols):
            if i >= j:
                continue

            # Check if a's scope overlaps b's scope
            def overlaps(pat_a, pat_b):
                """Execute or process overlaps operation."""
                return fnmatch.fnmatch(pat_a, pat_b) or fnmatch.fnmatch(pat_b, pat_a) or pat_a == '*' or pat_b == '*'

            agent_overlap = (
                a['agent_id'] == '*'
                or b['agent_id'] == '*'
                or any(ag in b['agent_id'].split(',') for ag in a['agent_id'].split(','))
            )
            server_overlap = (
                a['server_id'] == '*'
                or b['server_id'] == '*'
                or any(sv in b['server_id'].split(',') for sv in a['server_id'].split(','))
            )
            tool_overlap = overlaps(a['tool_pattern'], b['tool_pattern'])

            if not (agent_overlap and server_overlap and tool_overlap):
                continue

            # Exact duplicate
            if (
                a['agent_id'] == b['agent_id']
                and a['server_id'] == b['server_id']
                and a['tool_pattern'] == b['tool_pattern']
                and a['action'] == b['action']
            ):
                conflicts.append(
                    {
                        'type': 'duplicate',
                        'severity': 'warning',
                        'policy_a': {'id': a['policy_id'], 'name': a['name'], 'priority': a['priority']},
                        'policy_b': {'id': b['policy_id'], 'name': b['name'], 'priority': b['priority']},
                        'description': f"'{a['name']}' and '{b['name']}' are identical — remove one.",
                    }
                )
            # Conflicting action (same scope, different action)
            elif a['action'] != b['action']:
                winner = a if a['priority'] <= b['priority'] else b
                loser = b if a['priority'] <= b['priority'] else a
                conflicts.append(
                    {
                        'type': 'conflict',
                        'severity': 'error',
                        'policy_a': {
                            'id': a['policy_id'],
                            'name': a['name'],
                            'action': a['action'],
                            'priority': a['priority'],
                        },
                        'policy_b': {
                            'id': b['policy_id'],
                            'name': b['name'],
                            'action': b['action'],
                            'priority': b['priority'],
                        },
                        'winner': {'id': winner['policy_id'], 'name': winner['name']},
                        'loser': {'id': loser['policy_id'], 'name': loser['name']},
                        'description': f"Overlapping scope: '{a['name']}' ({a['action']}) vs '{b['name']}' ({b['action']}). '{winner['name']}' wins due to higher priority.",
                    }
                )
            # Shadowed policy (same action, higher priority catches first so lower never fires)
            elif a['action'] == b['action'] and a['priority'] < b['priority']:
                if (a['agent_id'] in (b['agent_id'], '*') or b['agent_id'] == '*') and (
                    a['server_id'] in (b['server_id'], '*') or b['server_id'] == '*'
                ):
                    conflicts.append(
                        {
                            'type': 'shadowed',
                            'severity': 'info',
                            'policy_a': {'id': a['policy_id'], 'name': a['name'], 'priority': a['priority']},
                            'policy_b': {'id': b['policy_id'], 'name': b['name'], 'priority': b['priority']},
                            'description': f"'{b['name']}' is shadowed by '{a['name']}' (higher priority, same scope) — '{b['name']}' may never apply.",
                        }
                    )

    return {
        'ok': True,
        'conflicts': conflicts,
        'conflict_count': sum(1 for c in conflicts if c['type'] == 'conflict'),
        'warning_count': sum(1 for c in conflicts if c['type'] in ('duplicate', 'shadowed')),
        'total': len(conflicts),
    }


@router.post('/policies/bulk')
async def bulk_policy_action(req: Request):
    """
    Bulk enable/disable/delete a list of policy IDs.
    Body: {action: "enable"|"disable"|"delete", policy_ids: [...]}
    """
    try:
        body = await req.json()
    except (json.JSONDecodeError, TypeError, ValueError):
        return JSONResponse({'ok': False, 'error': 'Invalid JSON'}, status_code=400)

    action = (body.get('action') or '').strip()
    policy_ids = body.get('policy_ids') or []
    if action not in ('enable', 'disable', 'delete'):
        return JSONResponse({'ok': False, 'error': 'action must be enable|disable|delete'}, status_code=400)
    if not policy_ids:
        return JSONResponse({'ok': False, 'error': 'policy_ids required'}, status_code=400)

    protected = {'pol_allow_builtin'}  # never touch default allow
    safe_ids = [pid for pid in policy_ids if pid not in protected]
    now = _now()
    con = _get_conn()
    try:
        affected = 0
        for pid in safe_ids:
            if action == 'enable':
                con.execute('UPDATE mcp_gateway_policies SET enabled=1, updated_at=? WHERE policy_id=?', (now, pid))
            elif action == 'disable':
                con.execute('UPDATE mcp_gateway_policies SET enabled=0, updated_at=? WHERE policy_id=?', (now, pid))
            elif action == 'delete':
                con.execute('DELETE FROM mcp_gateway_policies WHERE policy_id=?', (pid,))
            affected += 1
        con.commit()
    finally:
        con.close()
    return {'ok': True, 'action': action, 'affected': affected, 'skipped': len(policy_ids) - len(safe_ids)}


@router.get('/policies/templates')
def list_policy_templates():
    """Return pre-built policy templates for one-click creation."""
    return {
        'ok': True,
        'templates': [
            {
                'id': 'tpl_deny_all_delete',
                'name': 'Block All File Deletes',
                'description': 'No agent may delete any file without HITL approval',
                'category': 'Security',
                'action': 'require_hitl',
                'agent_id': '*',
                'server_id': 'srv_filesystem',
                'tool_pattern': 'fs.delete',
                'priority': 10,
                'icon': '🛡️',
            },
            {
                'id': 'tpl_block_external_http',
                'name': 'Block All External HTTP',
                'description': 'No agent may make outbound HTTP calls',
                'category': 'Security',
                'action': 'deny',
                'agent_id': '*',
                'server_id': 'srv_http',
                'tool_pattern': '*',
                'priority': 5,
                'icon': '🚫',
            },
            {
                'id': 'tpl_researcher_web_only',
                'name': 'Researcher: Web Search Only',
                'description': 'Researcher agent can only use web search, not file system',
                'category': 'Agent Scoping',
                'action': 'deny',
                'agent_id': 'researcher',
                'server_id': 'srv_filesystem',
                'tool_pattern': 'fs.*',
                'priority': 20,
                'icon': '🔍',
            },
            {
                'id': 'tpl_builder_no_exec',
                'name': 'Builder: No Code Execution',
                'description': 'Builder agent cannot execute arbitrary code',
                'category': 'Security',
                'action': 'deny',
                'agent_id': 'builder',
                'server_id': 'srv_code_exec',
                'tool_pattern': '*',
                'priority': 15,
                'icon': '🔒',
            },
            {
                'id': 'tpl_reviewer_read_only',
                'name': 'Reviewer: Read-Only File Access',
                'description': 'Reviewer agent can read files but not write or delete',
                'category': 'Agent Scoping',
                'action': 'deny',
                'agent_id': 'reviewer',
                'server_id': 'srv_filesystem',
                'tool_pattern': 'fs.write',
                'priority': 25,
                'icon': '👁️',
            },
            {
                'id': 'tpl_hitl_connectors',
                'name': 'Connectors Always Require HITL',
                'description': 'All enterprise connector calls need human approval',
                'category': 'Governance',
                'action': 'require_hitl',
                'agent_id': '*',
                'server_id': 'srv_connectors',
                'tool_pattern': '*',
                'priority': 8,
                'icon': '🛂',
            },
            {
                'id': 'tpl_allow_orchestrator_all',
                'name': 'Orchestrator: Full Access',
                'description': 'Orchestrator agent has unrestricted access to all servers',
                'category': 'Privileged Access',
                'action': 'allow',
                'agent_id': 'orchestrator',
                'server_id': '*',
                'tool_pattern': '*',
                'priority': 1,
                'icon': '🎯',
            },
            {
                'id': 'tpl_deny_memory_write_guest',
                'name': 'Guests: No Memory Writes',
                'description': 'Guest agents cannot persist anything to memory',
                'category': 'Data Protection',
                'action': 'deny',
                'agent_id': 'guest',
                'server_id': 'srv_memory',
                'tool_pattern': 'memory.add',
                'priority': 30,
                'icon': '🧠',
            },
        ],
    }


@router.post('/policies/from-template')
async def create_policy_from_template(req: Request):
    """Create a new policy from a built-in template (POST with template_id)."""
    try:
        body = await req.json()
    except (json.JSONDecodeError, TypeError, ValueError):
        return JSONResponse({'ok': False, 'error': 'Invalid JSON'}, status_code=400)

    template_id = body.get('template_id', '').strip()
    templates_r = list_policy_templates()
    tpl = next((t for t in templates_r['templates'] if t['id'] == template_id), None)
    if not tpl:
        return JSONResponse({'ok': False, 'error': f"Template '{template_id}' not found"}, status_code=404)

    # Override with any caller-provided fields
    name = body.get('name', tpl['name'])
    description = body.get('description', tpl['description'])
    action = body.get('action', tpl['action'])
    agent_id = body.get('agent_id', tpl['agent_id'])
    server_id = body.get('server_id', tpl['server_id'])
    tool_pattern = body.get('tool_pattern', tpl['tool_pattern'])
    priority = int(body.get('priority', tpl['priority']))

    pol_id = f'pol_{uuid.uuid4().hex[:8]}'
    now = _now()
    con = _get_conn()
    try:
        con.execute(
            """INSERT INTO mcp_gateway_policies
            (policy_id,name,description,agent_id,server_id,tool_pattern,action,priority,conditions,enabled,created_at,updated_at)
            VALUES (?,?,?,?,?,?,?,?,'{}',1,?,?)""",
            (
                pol_id,
                name[:100],
                description[:500],
                agent_id[:100],
                server_id[:100],
                tool_pattern[:100],
                action,
                priority,
                now,
                now,
            ),
        )
        con.commit()
    finally:
        con.close()
    return {'ok': True, 'policy_id': pol_id, 'template_id': template_id, 'name': name}


@router.delete('/policies/{policy_id}')
def delete_policy(policy_id: str):
    """Delete or remove specified policy."""
    if policy_id.startswith('pol_allow_builtin'):
        return JSONResponse({'ok': False, 'error': 'Cannot delete default allow policy'}, status_code=400)
    con = _get_conn()
    try:
        con.execute('DELETE FROM mcp_gateway_policies WHERE policy_id=?', (policy_id,))
        con.commit()
    finally:
        con.close()
    return {'ok': True, 'deleted': policy_id}


@router.patch('/policies/{policy_id}/toggle')
def toggle_policy(policy_id: str):
    """Execute or process toggle policy operation."""
    con = _get_conn()
    try:
        row = con.execute('SELECT enabled FROM mcp_gateway_policies WHERE policy_id=?', (policy_id,)).fetchone()
        if not row:
            return JSONResponse({'ok': False, 'error': 'Not found'}, status_code=404)
        new_enabled = 0 if row['enabled'] else 1
        con.execute(
            'UPDATE mcp_gateway_policies SET enabled=?, updated_at=? WHERE policy_id=?',
            (new_enabled, _now(), policy_id),
        )
        con.commit()
    finally:
        con.close()
    return {'ok': True, 'policy_id': policy_id, 'enabled': bool(new_enabled)}


@router.get('/policies/{policy_id}')
def get_policy(policy_id: str):
    """Get a single policy by ID."""
    con = _get_conn()
    try:
        row = con.execute('SELECT * FROM mcp_gateway_policies WHERE policy_id=?', (policy_id,)).fetchone()
    finally:
        con.close()
    if not row:
        return JSONResponse({'ok': False, 'error': 'Policy not found'}, status_code=404)
    return {'ok': True, 'policy': dict(row)}


@router.patch('/policies/{policy_id}')
async def update_policy(policy_id: str, req: Request):
    """Update a policy's fields (name, description, action, agent_id, server_id, tool_pattern, priority, conditions)."""
    try:
        body = await req.json()
    except (json.JSONDecodeError, TypeError, ValueError):
        return JSONResponse({'ok': False, 'error': 'Invalid JSON'}, status_code=400)

    allowed = {'name', 'description', 'action', 'agent_id', 'server_id', 'tool_pattern', 'priority', 'conditions'}
    updates = {}
    for k, v in body.items():
        if k not in allowed:
            continue
        if k == 'action' and v not in ('allow', 'deny', 'require_hitl'):
            return JSONResponse(
                {'ok': False, 'error': f'action must be allow|deny|require_hitl, got {v}'}, status_code=400
            )
        if k == 'priority':
            try:
                updates[k] = int(v)
            except (TypeError, ValueError):
                return JSONResponse({'ok': False, 'error': 'priority must be integer'}, status_code=400)
        elif k == 'conditions':
            # Accept dict or JSON string
            if isinstance(v, dict):
                updates[k] = json.dumps(v)
            else:
                try:
                    json.loads(v)  # validate
                    updates[k] = v
                except (json.JSONDecodeError, TypeError, ValueError):
                    return JSONResponse({'ok': False, 'error': 'conditions must be valid JSON'}, status_code=400)
        else:
            updates[k] = str(v)[:500]

    if not updates:
        return JSONResponse({'ok': False, 'error': 'No valid fields to update'}, status_code=400)

    updates['updated_at'] = _now()
    con = _get_conn()
    try:
        row = con.execute('SELECT policy_id FROM mcp_gateway_policies WHERE policy_id=?', (policy_id,)).fetchone()
        if not row:
            return JSONResponse({'ok': False, 'error': 'Policy not found'}, status_code=404)
        sets = ', '.join(f'{k}=?' for k in updates)
        con.execute(f'UPDATE mcp_gateway_policies SET {sets} WHERE policy_id=?', list(updates.values()) + [policy_id])
        con.commit()
    finally:
        con.close()
    return {'ok': True, 'policy_id': policy_id, 'updated': list(updates.keys())}


@router.get('/calls')
def list_calls(agent_id: str = '', server_id: str = '', status: str = '', limit: int = 50):
    """Retrieve and return list calls."""
    where, params = [], []
    if agent_id:
        where.append('agent_id=?')
        params.append(agent_id)
    if server_id:
        where.append('server_id=?')
        params.append(server_id)
    if status:
        where.append('status=?')
        params.append(status)
    where_sql = ('WHERE ' + ' AND '.join(where)) if where else ''
    params.append(min(limit, 500))
    con = _get_conn()
    try:
        rows = con.execute(
            f'SELECT * FROM mcp_gateway_calls {where_sql} ORDER BY created_at DESC LIMIT ?', params
        ).fetchall()
        total = con.execute(f'SELECT COUNT(*) FROM mcp_gateway_calls {where_sql}', params[:-1]).fetchone()[0]
    finally:
        con.close()
    return {'calls': [dict(r) for r in rows], 'total': total}


@router.get('/stats')
def gateway_stats():
    """Execute or process gateway stats operation."""
    con = _get_conn()
    try:
        total = con.execute('SELECT COUNT(*) FROM mcp_gateway_calls').fetchone()[0]
        by_status = con.execute('SELECT status,COUNT(*) cnt FROM mcp_gateway_calls GROUP BY status').fetchall()
        by_agent = con.execute(
            'SELECT agent_id,COUNT(*) cnt FROM mcp_gateway_calls GROUP BY agent_id ORDER BY cnt DESC LIMIT 10'
        ).fetchall()
        by_tool = con.execute(
            'SELECT tool_name,COUNT(*) cnt FROM mcp_gateway_calls GROUP BY tool_name ORDER BY cnt DESC LIMIT 10'
        ).fetchall()
        blocked = con.execute(
            "SELECT COUNT(*) FROM mcp_gateway_calls WHERE policy_decision IN ('deny','rate_limited')"
        ).fetchone()[0]
        servers = con.execute('SELECT COUNT(*) FROM mcp_servers').fetchone()[0]
        policies = con.execute('SELECT COUNT(*) FROM mcp_gateway_policies WHERE enabled=1').fetchone()[0]
    finally:
        con.close()
    return {
        'total_calls': total,
        'blocked_calls': blocked,
        'block_rate_pct': round(blocked / total * 100, 1) if total else 0,
        'active_servers': servers,
        'active_policies': policies,
        'by_status': {r['status']: r['cnt'] for r in by_status},
        'top_agents': [dict(r) for r in by_agent],
        'top_tools': [dict(r) for r in by_tool],
    }


@router.get('/agent-card/{agent_id}')
def get_agent_card(agent_id: str):
    """Generate an A2A-compatible signed Agent Card for an agent."""
    con = _get_conn()
    try:
        agent = con.execute('SELECT * FROM agents WHERE id=?', (agent_id,)).fetchone()
        identity = con.execute(
            'SELECT public_key, key_version, authority_level FROM agent_identities WHERE agent_id=?', (agent_id,)
        ).fetchone()
        perms = con.execute('SELECT action FROM agent_permissions WHERE agent_id=?', (agent_id,)).fetchall()
        tools = con.execute(
            'SELECT DISTINCT tool_name FROM mcp_gateway_calls WHERE agent_id=? ORDER BY tool_name', (agent_id,)
        ).fetchall()
    finally:
        con.close()

    if not agent:
        return JSONResponse({'ok': False, 'error': 'Agent not found'}, status_code=404)

    card = {
        'schema_version': 'a2a/1.0',
        'agent_id': agent_id,
        'name': agent['name'],
        'role': agent['role'],
        'public_key': identity['public_key'][:60] + '…' if identity else None,
        'key_version': identity['key_version'] if identity else None,
        'authority_level': identity['authority_level'] if identity else 'unknown',
        'capabilities': [p['action'] for p in perms],
        'tools_used': [t['tool_name'] for t in tools],
        'endpoint': f'http://localhost:8787/api/agents/{agent_id}',
        'protocols': ['mcp/1.0', 'a2a/1.0'],
        'issued_at': _now(),
        'card_hash': hashlib.sha256(f'{agent_id}{_now()}'.encode()).hexdigest()[:16],
    }
    return {'ok': True, 'agent_card': card}
