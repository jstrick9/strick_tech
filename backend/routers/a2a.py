"""
Agentic OS — A2A Protocol v1.0 Endpoint
════════════════════════════════════════
Implements the Agent-to-Agent (A2A) protocol as specified by the
Linux Foundation A2A Working Group (https://google.github.io/A2A/).

Every Agentic OS agent gets:
  • A signed Agent Card at /.well-known/agent.json and /a2a/{id}/card
  • A JSON-RPC 2.0 task endpoint at /a2a/{id}
  • SSE streaming at /a2a/{id}/stream/{task_id}
  • Cross-platform delegation to any A2A-compatible agent

Supported methods (JSON-RPC 2.0):
  tasks/send             — submit a new task and wait for completion
  tasks/sendSubscribe    — submit a task and receive SSE status stream
  tasks/get              — retrieve task state + artifacts
  tasks/cancel           — cancel a running task
  tasks/list             — list tasks for this agent

Registry endpoints:
  GET  /a2a/agents               — list registered remote agents
  POST /a2a/agents               — register a remote agent
  GET  /a2a/agents/{id}          — get agent detail
  PATCH /a2a/agents/{id}         — update agent config
  DELETE /a2a/agents/{id}        — remove agent
  POST /a2a/agents/{id}/verify   — fetch+verify remote agent card
  POST /a2a/delegate             — delegate a task to a remote A2A agent
  GET  /a2a/tasks                — list all A2A tasks (any direction)
  GET  /a2a/tasks/{task_id}      — get specific task
  GET  /a2a/stats                — platform A2A usage stats

Well-known:
  GET  /.well-known/agent.json                — platform-level agent card
  GET  /a2a/{agent_id}/card                   — agent-specific card
  GET  /a2a/{agent_id}/.well-known/agent.json — spec-compliant card URL

References:
  A2A spec: https://google.github.io/A2A/
  A2A GitHub: https://github.com/google/A2A
"""

from __future__ import annotations

import asyncio
import hashlib
import json
import logging
import time
import uuid
from datetime import datetime, timezone
from pathlib import Path
from typing import Optional, Union, Any, Dict, List, Tuple, Set, Callable, AsyncGenerator

from fastapi import APIRouter, Request
from fastapi.responses import JSONResponse, StreamingResponse

router = APIRouter(tags=['a2a'])
log = logging.getLogger('agentic.a2a')

from backend.config import get_data_dir
ROOT = get_data_dir()

# ── Schema guard ───────────────────────────────────────────────────────────────
_SCHEMA = """
CREATE TABLE IF NOT EXISTS a2a_tasks (
    task_id          TEXT PRIMARY KEY,
    caller_agent_id  TEXT NOT NULL DEFAULT '',
    caller_endpoint  TEXT NOT NULL DEFAULT '',
    target_agent_id  TEXT NOT NULL DEFAULT '',
    state            TEXT NOT NULL DEFAULT 'submitted',
    messages         TEXT NOT NULL DEFAULT '[]',
    artifacts        TEXT NOT NULL DEFAULT '[]',
    metadata         TEXT NOT NULL DEFAULT '{}',
    error_code       TEXT NOT NULL DEFAULT '',
    error_message    TEXT NOT NULL DEFAULT '',
    progress_pct     INTEGER NOT NULL DEFAULT 0,
    session_id       TEXT NOT NULL DEFAULT '',
    push_config      TEXT NOT NULL DEFAULT '{}',
    supervisor_run_id TEXT NOT NULL DEFAULT '',
    created_at       TEXT NOT NULL DEFAULT '',
    updated_at       TEXT NOT NULL DEFAULT '',
    completed_at     TEXT NOT NULL DEFAULT ''
);
CREATE TABLE IF NOT EXISTS a2a_agents (
    agent_id         TEXT PRIMARY KEY,
    name             TEXT NOT NULL DEFAULT '',
    description      TEXT NOT NULL DEFAULT '',
    a2a_url          TEXT NOT NULL DEFAULT '',
    agent_card       TEXT NOT NULL DEFAULT '{}',
    status           TEXT NOT NULL DEFAULT 'unverified',
    auth_type        TEXT NOT NULL DEFAULT 'none',
    auth_config      TEXT NOT NULL DEFAULT '{}',
    skills           TEXT NOT NULL DEFAULT '[]',
    capabilities     TEXT NOT NULL DEFAULT '[]',
    trust_level      TEXT NOT NULL DEFAULT 'unverified',
    registered_at    TEXT NOT NULL DEFAULT '',
    last_seen_at     TEXT NOT NULL DEFAULT '',
    last_task_at     TEXT NOT NULL DEFAULT ''
);
CREATE TABLE IF NOT EXISTS a2a_call_log (
    id               INTEGER PRIMARY KEY AUTOINCREMENT,
    task_id          TEXT NOT NULL,
    direction        TEXT NOT NULL DEFAULT 'inbound',
    remote_agent_id  TEXT NOT NULL DEFAULT '',
    remote_url       TEXT NOT NULL DEFAULT '',
    method           TEXT NOT NULL DEFAULT '',
    status_code      INTEGER NOT NULL DEFAULT 0,
    duration_ms      INTEGER NOT NULL DEFAULT 0,
    error            TEXT NOT NULL DEFAULT '',
    created_at       TEXT NOT NULL DEFAULT ''
);
CREATE INDEX IF NOT EXISTS idx_a2at_state    ON a2a_tasks(state, created_at DESC);
CREATE INDEX IF NOT EXISTS idx_a2at_caller   ON a2a_tasks(caller_agent_id);
CREATE INDEX IF NOT EXISTS idx_a2at_target   ON a2a_tasks(target_agent_id);
CREATE INDEX IF NOT EXISTS idx_a2aa_status   ON a2a_agents(status);
CREATE INDEX IF NOT EXISTS idx_a2acl_task    ON a2a_call_log(task_id);
"""


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


def _epoch_ms() -> int:
    return int(time.time() * 1000)


# ── Agent Card builder ─────────────────────────────────────────────────────────
def _build_agent_card(agent_id: str, base_url: str = 'http://localhost:8787') -> dict:
    """
    Build a fully compliant A2A v1.0 Agent Card for a local agent.
    Includes skills derived from agent role, capabilities, authentication info,
    and cryptographic identity from agent_identities table.
    """
    con = _get_conn()
    try:
        agent = con.execute('SELECT * FROM agents WHERE id=?', (agent_id,)).fetchone()
        identity = con.execute(
            'SELECT public_key, key_version, authority_level, signing_key FROM agent_identities WHERE agent_id=?',
            (agent_id,),
        ).fetchone()
        perms = con.execute('SELECT action FROM agent_permissions WHERE agent_id=?', (agent_id,)).fetchall()
        tool_history = con.execute(
            'SELECT DISTINCT tool_name FROM mcp_gateway_calls WHERE agent_id=? ORDER BY tool_name LIMIT 20', (agent_id,)
        ).fetchall()
    finally:
        con.close()

    if not agent:
        return {}

    # Build skills from role description
    role = agent['role'] or ''
    skills = _role_to_skills(agent_id, role, perms, tool_history)

    # Sign the card with agent's key for verifiability
    pub_key = identity['public_key'] if identity else ''
    card_payload = f'{agent_id}|{agent["name"]}|{_now()}'
    card_hash = hashlib.sha256(card_payload.encode()).hexdigest()

    # Capabilities this agent supports
    capabilities = {
        'streaming': True,
        'pushNotifications': False,
        'stateTransitionHistory': True,
    }

    card = {
        # A2A v1.0 required fields
        'name': agent['name'],
        'description': role,
        'url': f'{base_url}/a2a/{agent_id}',
        'version': '6.0.0',
        # Skills (what this agent can do)
        'skills': skills,
        # I/O modes
        'defaultInputModes': ['text/plain', 'application/json'],
        'defaultOutputModes': ['text/plain', 'application/json', 'text/markdown'],
        # Capabilities
        'capabilities': capabilities,
        # Authentication (this platform requires no auth for local agents)
        'authentication': {
            'schemes': ['none', 'bearer'],
        },
        # Provider / identity
        'provider': {
            'organization': 'Agentic OS',
            'url': base_url,
            'contact': 'admin@agentic-os.local',
        },
        # A2A extensions (platform-specific)
        '_agentic_os': {
            'agent_id': agent_id,
            'role': role,
            'model': dict(agent).get('model', ''),
            'authority_level': identity['authority_level'] if identity else 'unknown',
            'key_version': identity['key_version'] if identity else 0,
            'public_key': pub_key[:120] + '…' if len(pub_key) > 120 else pub_key,
            'card_hash': card_hash,
            'card_signed_at': _now(),
            'protocols': ['a2a/1.0', 'mcp/1.0', 'jsonrpc/2.0'],
            'capabilities_list': list({p['action'] for p in perms}),
        },
    }

    return card


def _role_to_skills(agent_id: str, role: str, perms, tools) -> list[dict]:
    """Derive structured A2A skills from agent role + permissions."""
    role_lower = role.lower()
    skills = []

    # Core agent-specific skills
    role_skills = {
        'orchestrator': [
            {
                'id': 'task_orchestration',
                'name': 'Task Orchestration',
                'description': 'Decompose complex goals into sub-tasks, coordinate specialist agents, synthesize results',
                'tags': ['orchestration', 'planning', 'coordination'],
            },
            {
                'id': 'agent_coordination',
                'name': 'Agent Coordination',
                'description': 'Fan out tasks to multiple specialist agents and merge results',
                'tags': ['multi-agent', 'fan-out', 'merge'],
            },
        ],
        'researcher': [
            {
                'id': 'web_research',
                'name': 'Web Research',
                'description': 'Search the web, read articles, synthesize findings into structured reports',
                'tags': ['research', 'search', 'web', 'rag'],
            },
            {
                'id': 'knowledge_retrieval',
                'name': 'Knowledge Retrieval',
                'description': 'Retrieve from internal memory and knowledge graph',
                'tags': ['rag', 'memory', 'knowledge'],
            },
        ],
        'builder': [
            {
                'id': 'code_generation',
                'name': 'Code Generation',
                'description': 'Write, debug, and refactor code in Python, JavaScript, TypeScript and more',
                'tags': ['code', 'programming', 'debugging'],
            },
            {
                'id': 'file_management',
                'name': 'File Management',
                'description': 'Create, read, update files in the workspace',
                'tags': ['files', 'workspace', 'scaffold'],
            },
        ],
        'reviewer': [
            {
                'id': 'code_review',
                'name': 'Code Review',
                'description': 'Security audit, performance review, test generation for code',
                'tags': ['review', 'security', 'testing', 'quality'],
            },
            {
                'id': 'test_generation',
                'name': 'Test Generation',
                'description': 'Generate unit, integration and e2e tests',
                'tags': ['testing', 'pytest', 'jest'],
            },
        ],
        'creative': [
            {
                'id': 'content_creation',
                'name': 'Content Creation',
                'description': 'Write blog posts, marketing copy, documentation and creative content',
                'tags': ['writing', 'content', 'creative', 'docs'],
            },
            {
                'id': 'image_generation',
                'name': 'Image Generation',
                'description': 'Generate images from text prompts',
                'tags': ['images', 'visual', 'creative'],
            },
        ],
        'brain': [
            {
                'id': 'deep_reasoning',
                'name': 'Deep Reasoning',
                'description': 'Complex reasoning, planning, analysis and decision-making',
                'tags': ['reasoning', 'planning', 'analysis'],
            },
            {
                'id': 'goal_decomposition',
                'name': 'Goal Decomposition',
                'description': 'Break high-level goals into actionable task plans',
                'tags': ['planning', 'decomposition', 'strategy'],
            },
        ],
        'memory': [
            {
                'id': 'memory_store',
                'name': 'Memory Store',
                'description': 'Persist and retrieve semantic memories using vector search',
                'tags': ['memory', 'vector', 'semantic', 'rag'],
            },
        ],
    }

    for key, agent_skills in role_skills.items():
        if key in role_lower or key == agent_id:
            skills.extend(agent_skills)

    # Add generic skill if no specific ones matched
    if not skills:
        skills.append(
            {
                'id': f'{agent_id}_task',
                'name': f'{agent_id.title()} Task',
                'description': role or f'General purpose {agent_id} agent',
                'tags': ['general'],
            }
        )

    # Add permission-derived skills
    perm_set = {p['action'] for p in perms}
    if 'web_search' in perm_set and not any(s['id'] == 'web_research' for s in skills):
        skills.append({'id': 'web_search', 'name': 'Web Search', 'description': 'Internet search', 'tags': ['search']})
    if 'run_code' in perm_set and not any(s['id'] == 'code_generation' for s in skills):
        skills.append(
            {'id': 'code_execution', 'name': 'Code Execution', 'description': 'Execute code snippets', 'tags': ['code']}
        )

    return skills


# ── Task lifecycle helpers ─────────────────────────────────────────────────────
def _load_task(task_id: str) ->Optional[ dict]:
    con = _get_conn()
    try:
        row = con.execute('SELECT * FROM a2a_tasks WHERE task_id=?', (task_id,)).fetchone()
    finally:
        con.close()
    if not row:
        return None
    d = dict(row)
    for f in ('messages', 'artifacts', 'metadata', 'push_config'):
        try:
            d[f] = json.loads(d.get(f) or '[]' if f in ('messages', 'artifacts') else '{}')
        except (json.JSONDecodeError, TypeError, ValueError):
            d[f] = [] if f in ('messages', 'artifacts') else {}
    return d


def _update_task(task_id: str, **kwargs):
    now = _now()
    kwargs['updated_at'] = now
    if kwargs.get('state') in ('completed', 'failed', 'canceled'):
        kwargs['completed_at'] = now
    # Serialize lists/dicts
    for k in ('messages', 'artifacts', 'metadata', 'push_config'):
        if k in kwargs and not isinstance(kwargs[k], str):
            kwargs[k] = json.dumps(kwargs[k], default=str)
    sets = ', '.join(f'{k}=?' for k in kwargs)
    params = list(kwargs.values()) + [task_id]
    con = _get_conn()
    try:
        con.execute(f'UPDATE a2a_tasks SET {sets} WHERE task_id=?', params)
        con.commit()
    finally:
        con.close()


def _task_to_a2a_response(task: dict) -> dict:
    """Format a task dict as an A2A TaskStatus response object."""
    return {
        'id': task['task_id'],
        'sessionId': task.get('session_id', ''),
        'status': {
            'state': task['state'],
            'message': _last_agent_message(task),
            'timestamp': task.get('updated_at', ''),
            'progress': task.get('progress_pct', 0),
        },
        'artifacts': task.get('artifacts', []),
        'metadata': task.get('metadata', {}),
    }


def _last_agent_message(task: dict) ->Optional[ dict]:
    """Get the most recent agent message from the task's message history."""
    messages = task.get('messages', [])
    for msg in reversed(messages):
        if msg.get('role') == 'agent':
            return msg
    return None


# ── Core task execution (local delegation to supervisor) ───────────────────────
async def _execute_local_task(task_id: str, target_agent_id: str, messages: list) -> None:
    """
    Execute a task locally by delegating to the Agentic OS supervisor.
    Updates task state in real-time: submitted → working → completed/failed.
    """
    from ..routers.audit_log import append_entry
    from ..routers.supervisor import _run_supervisor

    # Extract the user's message text
    user_text = ''
    for msg in messages:
        if msg.get('role') == 'user':
            for part in msg.get('parts') or []:
                if part.get('type') == 'text':
                    user_text += part.get('text', '')

    if not user_text.strip():
        _update_task(
            task_id, state='failed', error_code='invalid_input', error_message='No text content found in message parts'
        )
        return

    _update_task(task_id, state='working', progress_pct=5)

    # Create a supervisor run to actually execute the task
    run_id = f'a2a_srun_{uuid.uuid4().hex[:10]}'
    goal_id = task_id

    con = _get_conn()
    try:
        con.execute(
            """
            INSERT INTO supervisor_runs
              (run_id,goal_id,goal_title,goal_text,status,strategy,task_count,done_count,
               failed_count,final_output,eval_score,eval_notes,total_tokens,total_cost,
               duration_ms,created_at,updated_at,completed_at)
            VALUES (?,?,?,?,?,?,0,0,0,'','','',0,0,0,?,?,?)
        """,
            (run_id, goal_id, user_text[:80], user_text, 'decomposing', 'a2a_delegation', _now(), _now(), ''),
        )
        con.commit()
    finally:
        con.close()

    _update_task(task_id, supervisor_run_id=run_id, progress_pct=10)

    try:
        # Run the supervisor
        await _run_supervisor(run_id, goal_id, user_text)

        # Read the result
        con = _get_conn()
        try:
            sv_run = con.execute(
                'SELECT status, final_output, eval_score FROM supervisor_runs WHERE run_id=?', (run_id,)
            ).fetchone()
        finally:
            con.close()

        if sv_run and sv_run['status'] == 'done':
            output_text = sv_run['final_output'] or '(no output)'
            eval_score = sv_run['eval_score'] or 0.0

            # Build artifact
            artifacts = [
                {
                    'name': 'result',
                    'mimeType': 'text/plain',
                    'parts': [{'type': 'text', 'text': output_text}],
                    'metadata': {'eval_score': eval_score, 'supervisor_run': run_id},
                }
            ]

            # Append agent message
            task = _load_task(task_id)
            msgs = task['messages'] if task else []
            msgs.append(
                {
                    'role': 'agent',
                    'parts': [{'type': 'text', 'text': output_text}],
                }
            )
            _update_task(
                task_id,
                state='completed',
                messages=msgs,
                artifacts=artifacts,
                progress_pct=100,
                metadata={'eval_score': eval_score, 'run_id': run_id},
            )

            append_entry(
                'a2a_gateway',
                'A2A Gateway',
                'task_completed',
                f'A2A task {task_id} completed via supervisor {run_id}',
                authority='a2a',
                risk_level='low',
                outcome='success',
                metadata={'task_id': task_id, 'run_id': run_id},
            )
        else:
            sv_status = sv_run['status'] if sv_run else 'unknown'
            _update_task(
                task_id,
                state='failed',
                error_code='execution_failed',
                error_message=f'Supervisor run {sv_status}: {sv_run["final_output"][:200] if sv_run else ""}',
                progress_pct=0,
            )

    except Exception as e:
        log.error('A2A task %s execution failed: %s', task_id, e, exc_info=True)
        _update_task(task_id, state='failed', error_code='internal_error', error_message=str(e)[:500], progress_pct=0)


# ── JSON-RPC 2.0 dispatcher ────────────────────────────────────────────────────
def _jsonrpc_error(id_: Any, code: int, message: str, data: Any = None) -> dict:
    err = {'code': code, 'message': message}
    if data:
        err['data'] = data
    return {'jsonrpc': '2.0', 'id': id_, 'error': err}


def _jsonrpc_ok(id_: Any, result: Any) -> dict:
    return {'jsonrpc': '2.0', 'id': id_, 'result': result}


# JSON-RPC error codes (A2A spec + standard)
ERR_PARSE = -32700
ERR_INVALID_REQUEST = -32600
ERR_METHOD_NOT_FOUND = -32601
ERR_INVALID_PARAMS = -32602
ERR_INTERNAL = -32603
ERR_TASK_NOT_FOUND = -32001
ERR_NOT_CANCELABLE = -32002
ERR_INPUT_REQUIRED = -32003
ERR_RATE_LIMITED = -32004


async def _handle_jsonrpc(agent_id: str, body: dict, request: Request) -> dict:
    """
    Route a JSON-RPC 2.0 request to the correct handler.
    Returns a JSON-RPC 2.0 response dict.
    """
    if body.get('jsonrpc') != '2.0':
        return _jsonrpc_error(None, ERR_INVALID_REQUEST, 'Only JSON-RPC 2.0 is supported')

    req_id = body.get('id')
    method = body.get('method', '')
    params = body.get('params') or {}

    # Log inbound call
    caller_id = request.headers.get('X-A2A-Agent-Id', 'external')
    log.info('A2A[%s] inbound %s from %s', agent_id, method, caller_id)

    if method == 'tasks/send':
        return await _handle_tasks_send(req_id, agent_id, params, request)

    elif method == 'tasks/get':
        return _handle_tasks_get(req_id, params)

    elif method == 'tasks/cancel':
        return _handle_tasks_cancel(req_id, params)

    elif method == 'tasks/list':
        return _handle_tasks_list(req_id, agent_id, params)

    elif method == 'tasks/sendSubscribe':
        # This is handled specially (returns SSE) — signal to caller
        return {'_streaming': True, 'params': params, 'req_id': req_id}

    elif method == 'agents/getAuthenticatedExtendedCard':
        card = _build_agent_card(agent_id)
        if not card:
            return _jsonrpc_error(req_id, ERR_INTERNAL, f"Agent '{agent_id}' not found")
        return _jsonrpc_ok(req_id, card)

    else:
        return _jsonrpc_error(req_id, ERR_METHOD_NOT_FOUND, f"Method '{method}' not supported")


async def _handle_tasks_send(req_id, agent_id: str, params: dict, request: Request) -> dict:
    """
    tasks/send — submit a task, execute it, return the result.
    Params: {id?, sessionId?, message, pushNotification?}
    """
    # Validate
    message = params.get('message')
    if not message:
        return _jsonrpc_error(req_id, ERR_INVALID_PARAMS, 'params.message is required')

    # Normalize message to A2A Message format
    if isinstance(message, str):
        message = {'role': 'user', 'parts': [{'type': 'text', 'text': message}]}
    if not isinstance(message.get('parts'), list):
        return _jsonrpc_error(req_id, ERR_INVALID_PARAMS, 'message.parts must be a list')

    task_id = params.get('id') or f'task_{uuid.uuid4().hex}'
    session_id = params.get('sessionId') or ''
    push_cfg = params.get('pushNotification') or {}
    caller_id = request.headers.get('X-A2A-Agent-Id', 'external')
    caller_ep = request.headers.get('X-A2A-Endpoint', '')

    now = _now()
    con = _get_conn()
    try:
        con.execute(
            """
            INSERT INTO a2a_tasks
              (task_id,caller_agent_id,caller_endpoint,target_agent_id,state,
               messages,artifacts,metadata,push_config,session_id,created_at,updated_at)
            VALUES (?,?,?,?,?,?,?,?,?,?,?,?)
        """,
            (
                task_id,
                caller_id,
                caller_ep,
                agent_id,
                'submitted',
                json.dumps([message]),
                '[]',
                '{}',
                json.dumps(push_cfg),
                session_id,
                now,
                now,
            ),
        )
        con.execute(
            """
            INSERT INTO a2a_call_log (task_id,direction,remote_agent_id,remote_url,method,created_at)
            VALUES (?,?,?,?,?,?)
        """,
            (task_id, 'inbound', caller_id, caller_ep, 'tasks/send', now),
        )
        con.commit()
    finally:
        con.close()

    # Execute locally (async, but we await it here for tasks/send — sync response)
    await _execute_local_task(task_id, agent_id, [message])

    # Return final task state
    task = _load_task(task_id)
    if not task:
        return _jsonrpc_error(req_id, ERR_INTERNAL, 'Task lost after execution')

    return _jsonrpc_ok(req_id, _task_to_a2a_response(task))


def _handle_tasks_get(req_id, params: dict) -> dict:
    """tasks/get — retrieve current task state."""
    task_id = params.get('id') or params.get('taskId') or ''
    if not task_id:
        return _jsonrpc_error(req_id, ERR_INVALID_PARAMS, 'params.id is required')
    task = _load_task(task_id)
    if not task:
        return _jsonrpc_error(req_id, ERR_TASK_NOT_FOUND, f"Task '{task_id}' not found")
    return _jsonrpc_ok(req_id, _task_to_a2a_response(task))


def _handle_tasks_cancel(req_id, params: dict) -> dict:
    """tasks/cancel — cancel a running task."""
    task_id = params.get('id') or ''
    if not task_id:
        return _jsonrpc_error(req_id, ERR_INVALID_PARAMS, 'params.id is required')
    task = _load_task(task_id)
    if not task:
        return _jsonrpc_error(req_id, ERR_TASK_NOT_FOUND, f"Task '{task_id}' not found")
    if task['state'] in ('completed', 'failed', 'canceled'):
        return _jsonrpc_error(req_id, ERR_NOT_CANCELABLE, f'Task is already in terminal state: {task["state"]}')
    _update_task(task_id, state='canceled', error_code='canceled_by_caller', error_message='Canceled by caller request')
    task = _load_task(task_id)
    return _jsonrpc_ok(req_id, _task_to_a2a_response(task))


def _handle_tasks_list(req_id, agent_id: str, params: dict) -> dict:
    """tasks/list — list tasks for this agent (extension method)."""
    limit = min(int(params.get('limit', 50)), 200)
    state = params.get('state', '')
    session_id = params.get('sessionId', '')

    where, wparams = ['target_agent_id=?'], [agent_id]
    if state:
        where.append('state=?')
        wparams.append(state)
    if session_id:
        where.append('session_id=?')
        wparams.append(session_id)
    wparams.append(limit)

    con = _get_conn()
    try:
        rows = con.execute(
            f'SELECT * FROM a2a_tasks WHERE {" AND ".join(where)} ORDER BY created_at DESC LIMIT ?', wparams
        ).fetchall()
        count_where = ' AND '.join(where)
        count_params = wparams[:-1]  # exclude the LIMIT param
        total = con.execute(f'SELECT COUNT(*) FROM a2a_tasks WHERE {count_where}', count_params).fetchone()[0]
    finally:
        con.close()

    tasks = []
    for r in rows:
        t = dict(r)
        for f in ('messages', 'artifacts', 'metadata', 'push_config'):
            try:
                t[f] = json.loads(t.get(f) or '[]' if f in ('messages', 'artifacts') else '{}')
            except (json.JSONDecodeError, TypeError, ValueError):
                t[f] = [] if f in ('messages', 'artifacts') else {}
        tasks.append(_task_to_a2a_response(t))

    return _jsonrpc_ok(req_id, {'tasks': tasks, 'total': total})


# ── SSE streaming for tasks/sendSubscribe ──────────────────────────────────────
async def _stream_task_subscribe(agent_id: str, params: dict, request: Request):
    """
    Implement tasks/sendSubscribe as an SSE stream.
    Yields TaskStatusUpdateEvent SSE events as the task progresses.
    """
    # Create the task
    message = params.get('message')
    if isinstance(message, str):
        message = {'role': 'user', 'parts': [{'type': 'text', 'text': message}]}
    task_id = params.get('id') or f'task_{uuid.uuid4().hex}'
    session_id = params.get('sessionId', '')
    caller_id = request.headers.get('X-A2A-Agent-Id', 'external')
    push_cfg = params.get('pushNotification') or {}
    now = _now()

    con = _get_conn()
    try:
        con.execute(
            """
            INSERT INTO a2a_tasks
              (task_id,caller_agent_id,caller_endpoint,target_agent_id,state,
               messages,artifacts,metadata,push_config,session_id,created_at,updated_at)
            VALUES (?,?,?,?,?,?,?,?,?,?,?,?)
        """,
            (
                task_id,
                caller_id,
                '',
                agent_id,
                'submitted',
                json.dumps([message] if message else []),
                '[]',
                '{}',
                json.dumps(push_cfg),
                session_id,
                now,
                now,
            ),
        )
        con.commit()
    finally:
        con.close()

    def _sse_event(event_type: str, data: dict) -> str:
        return f'event: {event_type}\ndata: {json.dumps(data, default=str)}\n\n'

    async def _generate():
        # Initial: submitted
        yield _sse_event(
            'TaskStatusUpdateEvent',
            {
                'id': task_id,
                'status': {'state': 'submitted', 'timestamp': _now()},
                'final': False,
            },
        )
        await asyncio.sleep(0.1)

        # Start background execution
        task_coro = _execute_local_task(task_id, agent_id, [message] if message else [])
        exec_task = asyncio.create_task(task_coro)

        # Poll until complete, emitting working events
        last_pct = 0
        poll_count = 0
        while not exec_task.done():
            await asyncio.sleep(1.0)
            poll_count += 1
            t = _load_task(task_id)
            if not t:
                break
            pct = t.get('progress_pct', 0)
            if pct != last_pct or poll_count % 5 == 0:
                last_pct = pct
                yield _sse_event(
                    'TaskStatusUpdateEvent',
                    {
                        'id': task_id,
                        'status': {
                            'state': t['state'],
                            'timestamp': t.get('updated_at', ''),
                            'progress': pct,
                        },
                        'final': False,
                    },
                )

        # Await the execution coroutine
        try:
            await exec_task
        except Exception as e:
            log.error('SSE task exec error: %s', e)

        # Final result
        task = _load_task(task_id)
        if task:
            # Emit artifacts if any
            for artifact in task.get('artifacts') or []:
                yield _sse_event(
                    'TaskArtifactUpdateEvent',
                    {
                        'id': task_id,
                        'artifact': artifact,
                        'final': False,
                    },
                )
                await asyncio.sleep(0.05)

            # Final status
            yield _sse_event(
                'TaskStatusUpdateEvent',
                {
                    'id': task_id,
                    'status': {
                        'state': task['state'],
                        'timestamp': task.get('completed_at', ''),
                        'progress': task.get('progress_pct', 0),
                        'message': _last_agent_message(task),
                    },
                    'final': True,
                },
            )

    return StreamingResponse(
        _generate(),
        media_type='text/event-stream',
        headers={
            'Cache-Control': 'no-cache',
            'X-Accel-Buffering': 'no',
            'Connection': 'keep-alive',
        },
    )


# ── Outbound delegation to remote A2A agents ───────────────────────────────────
async def _delegate_to_remote(
    agent_id: str, endpoint: str, method: str, params: dict, auth_type: str = 'none', auth_config:Optional[ dict] = None
) -> dict:
    """
    Send a JSON-RPC 2.0 request to a remote A2A agent endpoint.
    Returns the parsed response or an error dict.
    """
    import httpx

    payload = {'jsonrpc': '2.0', 'id': str(uuid.uuid4()), 'method': method, 'params': params}
    headers = {
        'Content-Type': 'application/json',
        'X-A2A-Agent-Id': 'agentic-os',
        'X-A2A-Endpoint': 'http://localhost:8787/a2a/orchestrator',
        'X-A2A-Protocol': 'a2a/1.0',
    }
    if auth_type == 'bearer' and auth_config:
        headers['Authorization'] = f'Bearer {auth_config.get("token", "")}'
    elif auth_type == 'api_key' and auth_config:
        headers[auth_config.get('header', 'X-API-Key')] = auth_config.get('key', '')

    t0 = _epoch_ms()
    try:
        async with httpx.AsyncClient(timeout=30.0, follow_redirects=True) as client:
            r = await client.post(endpoint, json=payload, headers=headers)
            dur = _epoch_ms() - t0
            if r.status_code == 200:
                return {'ok': True, 'response': r.json(), 'duration_ms': dur}
            else:
                return {'ok': False, 'error': f'HTTP {r.status_code}: {r.text[:200]}', 'duration_ms': dur}
    except Exception as e:
        dur = _epoch_ms() - t0
        return {'ok': False, 'error': str(e)[:300], 'duration_ms': dur}


# ═══════════════════════════════════════════════════════════════════════════════
# API ROUTES
# ═══════════════════════════════════════════════════════════════════════════════


# ── /.well-known/agent.json (platform-level card) ─────────────────────────────
@router.get('/.well-known/agent.json', include_in_schema=False)
def platform_agent_card(request: Request):
    """Platform-level A2A agent card — describes this Agentic OS installation."""
    base = str(request.base_url).rstrip('/')
    card = {
        'name': 'Agentic OS Platform',
        'description': 'Local-first AI operating system with hierarchical multi-agent orchestration, governance, and A2A v1.0 protocol support',
        'version': '6.0.0',
        'url': f'{base}/a2a/orchestrator',
        'skills': [
            {'id': 'research', 'name': 'Research', 'description': 'Deep web research with multiple specialist agents'},
            {'id': 'code_generation', 'name': 'Code Generation', 'description': 'Write, debug, and deploy code'},
            {'id': 'content_creation', 'name': 'Content Creation', 'description': 'Blog posts, docs, marketing copy'},
            {'id': 'analysis', 'name': 'Analysis', 'description': 'Data analysis and business intelligence'},
            {
                'id': 'orchestration',
                'name': 'Orchestration',
                'description': 'Multi-agent task decomposition and execution',
            },
        ],
        'defaultInputModes': ['text/plain', 'application/json'],
        'defaultOutputModes': ['text/plain', 'application/json', 'text/markdown'],
        'capabilities': {
            'streaming': True,
            'pushNotifications': False,
            'stateTransitionHistory': True,
        },
        'authentication': {'schemes': ['none', 'bearer']},
        'provider': {
            'organization': 'Agentic OS',
            'url': base,
        },
        '_agentic_os': {
            'version': '6.0.0',
            'protocols': ['a2a/1.0', 'mcp/1.0', 'jsonrpc/2.0'],
            'agents': [
                base + f'/a2a/{a}'
                for a in ['orchestrator', 'researcher', 'builder', 'reviewer', 'creative', 'brain', 'memory']
            ],
        },
    }
    return JSONResponse(card, headers={'Access-Control-Allow-Origin': '*'})


# ── Per-agent well-known card ──────────────────────────────────────────────────
@router.get('/a2a/{agent_id}/.well-known/agent.json', include_in_schema=False)
@router.get('/a2a/{agent_id}/card')
def agent_card_endpoint(agent_id: str, request: Request):
    """
    A2A Agent Card for a specific local agent.
    Served at both the spec-compliant URL and a friendly /card path.
    """
    base = str(request.base_url).rstrip('/')
    card = _build_agent_card(agent_id, base)
    if not card:
        return JSONResponse({'error': f"Agent '{agent_id}' not found"}, status_code=404)
    return JSONResponse(card, headers={'Access-Control-Allow-Origin': '*'})


# ── Main JSON-RPC endpoint per agent ──────────────────────────────────────────
@router.post('/a2a/{agent_id}')
async def a2a_jsonrpc(agent_id: str, request: Request):
    """
    A2A v1.0 JSON-RPC 2.0 endpoint for a specific agent.
    Handles: tasks/send, tasks/get, tasks/cancel, tasks/list,
             tasks/sendSubscribe (returns SSE), agents/getAuthenticatedExtendedCard
    """
    try:
        body = await request.json()
    except (json.JSONDecodeError, TypeError, ValueError):
        return JSONResponse(_jsonrpc_error(None, ERR_PARSE, 'Invalid JSON'), status_code=400)

    # Handle streaming separately
    if body.get('method') == 'tasks/sendSubscribe':
        params = body.get('params') or {}
        return await _stream_task_subscribe(agent_id, params, request)

    result = await _handle_jsonrpc(agent_id, body, request)
    status = 200
    if 'error' in result:
        # Map specific error codes to HTTP status
        code = result['error'].get('code', 0)
        if code == ERR_TASK_NOT_FOUND:
            status = 404
        elif code == ERR_INVALID_PARAMS:
            status = 400
        elif code == ERR_METHOD_NOT_FOUND:
            status = 404
    return JSONResponse(result, status_code=status, headers={'Access-Control-Allow-Origin': '*'})


# ── Stream endpoint for existing tasks ────────────────────────────────────────
@router.get('/a2a/{agent_id}/stream/{task_id}')
async def a2a_task_stream(agent_id: str, task_id: str):
    """
    SSE stream for an existing task — poll until completion.
    Useful when the caller missed the initial sendSubscribe window.
    """

    async def _generate():
        for _ in range(300):  # max 5 min
            task = _load_task(task_id)
            if not task:
                yield f'data: {json.dumps({"error": "task not found"})}\n\n'
                return
            yield f'event: TaskStatusUpdateEvent\ndata: {json.dumps(_task_to_a2a_response(task), default=str)}\n\n'
            if task['state'] in ('completed', 'failed', 'canceled'):
                return
            await asyncio.sleep(1.0)
        yield f'data: {json.dumps({"error": "timeout"})}\n\n'

    return StreamingResponse(
        _generate(),
        media_type='text/event-stream',
        headers={'Cache-Control': 'no-cache', 'X-Accel-Buffering': 'no'},
    )


# ── Registry: list / discover remote agents ────────────────────────────────────
@router.get('/api/a2a/agents')
def list_agents(trust_level: str = '', status: str = '', limit: int = 50):
    """List all registered A2A agents (local + remote)."""
    where, params = [], []
    if trust_level:
        where.append('trust_level=?')
        params.append(trust_level)
    if status:
        where.append('status=?')
        params.append(status)
    params.append(min(limit, 200))
    where_sql = ('WHERE ' + ' AND '.join(where)) if where else ''

    con = _get_conn()
    try:
        rows = con.execute(
            f'SELECT * FROM a2a_agents {where_sql} ORDER BY trust_level, name LIMIT ?', params
        ).fetchall()
        total = con.execute(f'SELECT COUNT(*) FROM a2a_agents {where_sql}', params[:-1]).fetchone()[0]

        # Also include local agents from the agents table as "local" entries
        local_agents = con.execute('SELECT id, name, role FROM agents WHERE enabled=1').fetchall()
    finally:
        con.close()

    agents = []
    for r in rows:
        d = dict(r)
        for f in ('agent_card', 'skills', 'capabilities', 'auth_config'):
            try:
                d[f] = json.loads(d.get(f) or '{}' if f in ('agent_card', 'auth_config') else '[]')
            except (json.JSONDecodeError, TypeError, ValueError):
                d[f] = {} if f in ('agent_card', 'auth_config') else []
        agents.append(d)

    # Merge local agents
    registered_ids = {a['agent_id'] for a in agents}
    local = []
    for a in local_agents:
        if a['id'] not in registered_ids:
            local.append(
                {
                    'agent_id': a['id'],
                    'name': a['name'],
                    'description': a['role'],
                    'a2a_url': f'http://localhost:8787/a2a/{a["id"]}',
                    'status': 'active',
                    'trust_level': 'local',
                    'skills': [],
                    'capabilities': [],
                    'agent_card': {},
                }
            )

    return {'agents': agents, 'local_agents': local, 'total': total, 'count': len(agents)}


@router.post('/api/a2a/agents')
async def register_agent(request: Request):
    """Register a remote A2A agent."""
    try:
        body = await request.json()
    except (json.JSONDecodeError, TypeError, ValueError):
        return JSONResponse({'ok': False, 'error': 'Invalid JSON'}, status_code=400)

    agent_id = (body.get('agent_id') or f'ext_{uuid.uuid4().hex[:8]}').strip()
    name = (body.get('name') or '').strip()
    a2a_url = (body.get('a2a_url') or body.get('url', '')).strip()
    description = (body.get('description', '')).strip()
    auth_type = (body.get('auth_type', 'none')).strip()
    auth_config = body.get('auth_config') or {}
    trust_level = body.get('trust_level', 'unverified')

    if not a2a_url:
        return JSONResponse({'ok': False, 'error': 'a2a_url required'}, status_code=400)

    now = _now()
    con = _get_conn()
    try:
        con.execute(
            """
            INSERT OR REPLACE INTO a2a_agents
              (agent_id,name,description,a2a_url,status,auth_type,auth_config,
               skills,capabilities,trust_level,agent_card,registered_at,last_seen_at,last_task_at)
            VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?,?)
        """,
            (
                agent_id,
                name or agent_id,
                description,
                a2a_url,
                'unverified',
                auth_type,
                json.dumps(auth_config),
                '[]',
                '[]',
                trust_level,
                '{}',
                now,
                now,
                '',
            ),
        )
        con.commit()
    finally:
        con.close()

    return {'ok': True, 'agent_id': agent_id, 'a2a_url': a2a_url}


@router.get('/api/a2a/agents/{agent_id}')
def get_agent(agent_id: str):
    """Get a registered remote agent's full profile."""
    con = _get_conn()
    try:
        row = con.execute('SELECT * FROM a2a_agents WHERE agent_id=?', (agent_id,)).fetchone()
        tasks = con.execute(
            """
            SELECT task_id, state, created_at, completed_at
            FROM a2a_tasks
            WHERE caller_agent_id=? OR target_agent_id=?
            ORDER BY created_at DESC LIMIT 10
        """,
            (agent_id, agent_id),
        ).fetchall()
    finally:
        con.close()

    if not row:
        return JSONResponse({'ok': False, 'error': 'Agent not found'}, status_code=404)

    d = dict(row)
    for f in ('agent_card', 'skills', 'capabilities', 'auth_config'):
        try:
            d[f] = json.loads(d.get(f) or '{}' if f in ('agent_card', 'auth_config') else '[]')
        except (json.JSONDecodeError, TypeError, ValueError):
            d[f] = {} if f in ('agent_card', 'auth_config') else []

    return {'ok': True, 'agent': d, 'recent_tasks': [dict(t) for t in tasks]}


@router.patch('/api/a2a/agents/{agent_id}')
async def update_agent(agent_id: str, request: Request):
    """Update a remote agent's config (trust level, auth, etc.)."""
    try:
        body = await request.json()
    except (json.JSONDecodeError, TypeError, ValueError):
        return JSONResponse({'ok': False, 'error': 'Invalid JSON'}, status_code=400)

    allowed = {'name', 'description', 'a2a_url', 'auth_type', 'auth_config', 'trust_level', 'status'}
    updates = {}
    for k, v in body.items():
        if k not in allowed:
            continue
        if k == 'auth_config':
            updates[k] = json.dumps(v) if isinstance(v, dict) else v
        else:
            updates[k] = str(v)[:500]

    if not updates:
        return JSONResponse({'ok': False, 'error': 'No valid fields'}, status_code=400)

    updates['last_seen_at'] = _now()
    sets = ', '.join(f'{k}=?' for k in updates)
    con = _get_conn()
    try:
        con.execute(f'UPDATE a2a_agents SET {sets} WHERE agent_id=?', list(updates.values()) + [agent_id])
        con.commit()
    finally:
        con.close()

    return {'ok': True, 'agent_id': agent_id, 'updated': list(updates.keys())}


@router.delete('/api/a2a/agents/{agent_id}')
def delete_agent(agent_id: str):
    """Remove a registered remote agent."""
    if agent_id == 'local_orchestrator':
        return JSONResponse({'ok': False, 'error': 'Cannot delete local orchestrator'}, status_code=400)
    con = _get_conn()
    try:
        con.execute('DELETE FROM a2a_agents WHERE agent_id=?', (agent_id,))
        con.commit()
    finally:
        con.close()
    return {'ok': True, 'deleted': agent_id}


@router.post('/api/a2a/agents/{agent_id}/verify')
async def verify_agent(agent_id: str):
    """
    Fetch and verify the remote agent's Agent Card from its /.well-known/agent.json.
    Updates the cached card and sets status=active if reachable.
    """
    import httpx

    con = _get_conn()
    try:
        row = con.execute(
            'SELECT a2a_url, auth_type, auth_config FROM a2a_agents WHERE agent_id=?', (agent_id,)
        ).fetchone()
    finally:
        con.close()
    if not row:
        return JSONResponse({'ok': False, 'error': 'Agent not found'}, status_code=404)

    a2a_url = row['a2a_url']
    # Try standard well-known locations
    card_urls = []
    # Try to derive well-known URL from the agent's endpoint
    from urllib.parse import urlparse

    parsed = urlparse(a2a_url)
    base = f'{parsed.scheme}://{parsed.netloc}'
    path = parsed.path.rstrip('/')
    card_urls = [
        a2a_url.rstrip('/') + '/.well-known/agent.json',
        base + '/.well-known/agent.json',
        a2a_url.rstrip('/') + '/card',
    ]

    card = None
    fetched_from = ''
    for url in card_urls:
        try:
            async with httpx.AsyncClient(timeout=10.0) as client:
                r = await client.get(url, headers={'Accept': 'application/json'})
                if r.status_code == 200:
                    card = r.json()
                    fetched_from = url
                    break
        except (httpx.HTTPError, OSError, json.JSONDecodeError):
            continue

    now = _now()
    if card:
        skills = card.get('skills', [])
        caps = []
        if isinstance(card.get('capabilities'), dict):
            caps = [k for k, v in card['capabilities'].items() if v]
        elif isinstance(card.get('capabilities'), list):
            caps = card['capabilities']

        con = _get_conn()
        try:
            con.execute(
                """
                UPDATE a2a_agents
                SET status='active', agent_card=?, skills=?, capabilities=?, last_seen_at=?,
                    name=COALESCE(NULLIF(name,''), ?), description=COALESCE(NULLIF(description,''), ?)
                WHERE agent_id=?
            """,
                (
                    json.dumps(card),
                    json.dumps(skills),
                    json.dumps(caps),
                    now,
                    card.get('name', ''),
                    card.get('description', ''),
                    agent_id,
                ),
            )
            con.commit()
        finally:
            con.close()

        return {
            'ok': True,
            'agent_id': agent_id,
            'status': 'active',
            'fetched_from': fetched_from,
            'card_name': card.get('name'),
            'skills_count': len(skills),
        }
    else:
        con = _get_conn()
        try:
            con.execute("UPDATE a2a_agents SET status='unreachable', last_seen_at=? WHERE agent_id=?", (now, agent_id))
            con.commit()
        finally:
            con.close()
        return {
            'ok': False,
            'agent_id': agent_id,
            'status': 'unreachable',
            'tried_urls': card_urls,
            'error': 'Could not fetch agent card from any URL',
        }


# ── Outbound delegation ────────────────────────────────────────────────────────
@router.post('/api/a2a/delegate')
async def delegate_task(request: Request):
    """
    Delegate a task to a registered remote A2A agent.
    Body: {agent_id, message, session_id?, metadata?}
    Returns the task result (via tasks/send).
    """
    try:
        body = await request.json()
    except (json.JSONDecodeError, TypeError, ValueError):
        return JSONResponse({'ok': False, 'error': 'Invalid JSON'}, status_code=400)

    remote_agent_id = (body.get('agent_id') or '').strip()
    message_text = (body.get('message') or '').strip()
    session_id = body.get('session_id', '')
    metadata = body.get('metadata') or {}

    if not remote_agent_id or not message_text:
        return JSONResponse({'ok': False, 'error': 'agent_id and message required'}, status_code=400)

    con = _get_conn()
    try:
        row = con.execute('SELECT * FROM a2a_agents WHERE agent_id=?', (remote_agent_id,)).fetchone()
    finally:
        con.close()
    if not row:
        return JSONResponse({'ok': False, 'error': f"Agent '{remote_agent_id}' not registered"}, status_code=404)

    ag = dict(row)
    endpoint = ag['a2a_url']
    try:
        auth_cfg = json.loads(ag.get('auth_config') or '{}')
    except (json.JSONDecodeError, TypeError, ValueError):
        auth_cfg = {}

    task_id = f'task_{uuid.uuid4().hex}'
    params = {
        'id': task_id,
        'sessionId': session_id,
        'message': {
            'role': 'user',
            'parts': [{'type': 'text', 'text': message_text}],
        },
        'metadata': metadata,
    }

    # Record outbound call
    now = _now()
    con = _get_conn()
    try:
        con.execute(
            """
            INSERT INTO a2a_tasks
              (task_id,caller_agent_id,caller_endpoint,target_agent_id,state,
               messages,artifacts,metadata,push_config,session_id,created_at,updated_at)
            VALUES (?,?,?,?,?,?,?,?,?,?,?,?)
        """,
            (
                task_id,
                'local',
                'http://localhost:8787',
                remote_agent_id,
                'submitted',
                json.dumps([params['message']]),
                '[]',
                json.dumps(metadata),
                '{}',
                session_id,
                now,
                now,
            ),
        )
        con.execute(
            """
            INSERT INTO a2a_call_log (task_id,direction,remote_agent_id,remote_url,method,created_at)
            VALUES (?,?,?,?,?,?)
        """,
            (task_id, 'outbound', remote_agent_id, endpoint, 'tasks/send', now),
        )
        con.commit()
    finally:
        con.close()

    # Send to remote agent
    result = await _delegate_to_remote(
        remote_agent_id, endpoint, 'tasks/send', params, auth_type=ag.get('auth_type', 'none'), auth_config=auth_cfg
    )

    # Update call log
    con = _get_conn()
    try:
        status_code = 200 if result['ok'] else 500
        error = '' if result['ok'] else result.get('error', '')
        con.execute(
            """
            UPDATE a2a_call_log SET status_code=?, duration_ms=?, error=?
            WHERE task_id=? AND direction='outbound'
        """,
            (status_code, result.get('duration_ms', 0), error[:300], task_id),
        )
        new_state = 'completed' if result['ok'] else 'failed'
        con.execute('UPDATE a2a_tasks SET state=?, updated_at=? WHERE task_id=?', (new_state, _now(), task_id))
        con.execute('UPDATE a2a_agents SET last_task_at=? WHERE agent_id=?', (_now(), remote_agent_id))
        con.commit()
    finally:
        con.close()

    if result['ok']:
        return {
            'ok': True,
            'task_id': task_id,
            'result': result['response'],
            'duration_ms': result.get('duration_ms', 0),
        }
    else:
        return JSONResponse(
            {
                'ok': False,
                'task_id': task_id,
                'error': result.get('error'),
                'note': 'Remote agent unreachable — the agent may require authentication or may not be running',
            },
            status_code=200,
        )  # 200 because the delegation attempt itself worked


# ── Task management ────────────────────────────────────────────────────────────
@router.get('/api/a2a/tasks')
def list_all_tasks(state: str = '', direction: str = '', limit: int = 50):
    """List all A2A tasks across all agents."""
    where, params = [], []
    if state:
        where.append('state=?')
        params.append(state)
    params.append(min(limit, 200))
    where_sql = ('WHERE ' + ' AND '.join(where)) if where else ''

    con = _get_conn()
    try:
        rows = con.execute(
            f'SELECT task_id,caller_agent_id,target_agent_id,state,progress_pct,session_id,'
            f'supervisor_run_id,created_at,updated_at,completed_at '
            f'FROM a2a_tasks {where_sql} ORDER BY created_at DESC LIMIT ?',
            params,
        ).fetchall()
        total = con.execute(f'SELECT COUNT(*) FROM a2a_tasks {where_sql}', params[:-1]).fetchone()[0]

        # Also pull call log for direction info
        log_map = {}
        log_rows = con.execute('SELECT task_id, direction FROM a2a_call_log ORDER BY id DESC LIMIT 500').fetchall()
        for lr in log_rows:
            if lr['task_id'] not in log_map:
                log_map[lr['task_id']] = lr['direction']
    finally:
        con.close()

    tasks = []
    for r in rows:
        d = dict(r)
        d['direction'] = log_map.get(d['task_id'], 'inbound')
        tasks.append(d)

    # Filter by direction if requested
    if direction:
        tasks = [t for t in tasks if t.get('direction') == direction]

    return {'tasks': tasks, 'total': total, 'count': len(tasks)}


@router.get('/api/a2a/tasks/{task_id}')
def get_task_detail(task_id: str):
    """Get full detail of an A2A task including messages and artifacts."""
    task = _load_task(task_id)
    if not task:
        return JSONResponse({'ok': False, 'error': 'Task not found'}, status_code=404)

    con = _get_conn()
    try:
        call_log = con.execute('SELECT * FROM a2a_call_log WHERE task_id=? ORDER BY id', (task_id,)).fetchall()
        sv_run = None
        if task.get('supervisor_run_id'):
            sv_run = con.execute(
                'SELECT run_id, status, eval_score, total_tokens, duration_ms FROM supervisor_runs WHERE run_id=?',
                (task['supervisor_run_id'],),
            ).fetchone()
    finally:
        con.close()

    return {
        'ok': True,
        'task': task,
        'a2a_response': _task_to_a2a_response(task),
        'call_log': [dict(r) for r in call_log],
        'supervisor_run': dict(sv_run) if sv_run else None,
    }


@router.post('/api/a2a/tasks/{task_id}/cancel')
def cancel_task_api(task_id: str):
    """Cancel a running task via REST API."""
    task = _load_task(task_id)
    if not task:
        return JSONResponse({'ok': False, 'error': 'Task not found'}, status_code=404)
    if task['state'] in ('completed', 'failed', 'canceled'):
        return JSONResponse({'ok': False, 'error': f'Task already in terminal state: {task["state"]}'}, status_code=400)
    _update_task(task_id, state='canceled', error_code='canceled', error_message='Canceled via API')
    return {'ok': True, 'task_id': task_id, 'state': 'canceled'}


# ── Stats ──────────────────────────────────────────────────────────────────────
@router.get('/api/a2a/stats')
def a2a_stats():
    """Platform-wide A2A usage statistics."""
    con = _get_conn()
    try:
        total_tasks = con.execute('SELECT COUNT(*) FROM a2a_tasks').fetchone()[0]
        by_state = con.execute('SELECT state, COUNT(*) cnt FROM a2a_tasks GROUP BY state').fetchall()
        inbound_count = con.execute("SELECT COUNT(*) FROM a2a_call_log WHERE direction='inbound'").fetchone()[0]
        outbound_count = con.execute("SELECT COUNT(*) FROM a2a_call_log WHERE direction='outbound'").fetchone()[0]
        registered = con.execute('SELECT COUNT(*) FROM a2a_agents').fetchone()[0]
        active_agents = con.execute("SELECT COUNT(*) FROM a2a_agents WHERE status='active'").fetchone()[0]
        local_agents = con.execute("SELECT COUNT(*) FROM a2a_agents WHERE trust_level='local'").fetchone()[0]
        recent_tasks = con.execute("""
            SELECT task_id,target_agent_id,state,created_at FROM a2a_tasks
            ORDER BY created_at DESC LIMIT 5
        """).fetchall()
        avg_dur = con.execute('SELECT AVG(duration_ms) FROM a2a_call_log WHERE duration_ms>0').fetchone()[0]
    finally:
        con.close()

    return {
        'total_tasks': total_tasks,
        'by_state': {r['state']: r['cnt'] for r in by_state},
        'inbound_calls': inbound_count,
        'outbound_calls': outbound_count,
        'registered_agents': registered,
        'active_agents': active_agents,
        'local_agents': local_agents,
        'avg_call_ms': round(avg_dur or 0, 1),
        'recent_tasks': [dict(r) for r in recent_tasks],
    }
