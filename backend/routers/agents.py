"""
Agentic OS — Agents Router
Full CRUD for custom agent definitions. Users can create, rename,
recolor, change model, write system prompts, and delete agents.
"""

from __future__ import annotations

import contextlib

import re
import uuid

from fastapi import APIRouter, Request

from ..services import llm, memory_db

router = APIRouter(prefix='/api/agents', tags=['agents'])


@router.get('')
def list_agents():
    """List all agents."""
    return memory_db.agents_list()


@router.get('/models')
async def list_models():
    """Return available models (OpenRouter registry + ollama if running)."""
    or_models = list(llm.OPENROUTER_MODELS.items())
    ollama = await llm.ollama_health()
    return {
        'openrouter': [{'id': k, 'model': v} for k, v in or_models],
        'ollama': {'running': ollama['running'], 'models': ollama.get('models', [])},
    }


@router.post('')
async def create_agent(req: Request):
    """Create a new custom agent."""
    try:
        body = await req.json()
    except (json.JSONDecodeError, TypeError, ValueError):
        body = {}
    name = (body.get('name') or '').strip()
    if not name:
        return {'ok': False, 'error': 'name is required'}

    # auto-generate id from name
    agent_id = body.get('id') or re.sub(r'[^a-z0-9_-]', '_', name.lower())[:32]
    # ensure uniqueness
    existing = {a['id'] for a in memory_db.agents_list()}
    if agent_id in existing:
        agent_id = f'{agent_id}_{uuid.uuid4().hex[:4]}'

    data = {
        'id': agent_id,
        'name': name[:80],
        'role': (body.get('role') or 'AI assistant')[:200],
        'model': (body.get('model') or 'default')[:100],
        'provider': (body.get('provider') or 'openrouter')[:32],
        'color': (body.get('color') or _random_color())[:16],
        'avatar': (body.get('avatar') or '🤖')[:8],
        'system_prompt': (body.get('system_prompt') or '')[:4000],
        'status': 'idle',
        'enabled': 1,
    }
    result = memory_db.agent_upsert(data)
    memory_db.audit_log('agent_create', f'{agent_id}: {name}')
    return {'ok': True, 'agent': result}


@router.get('/{agent_id}')
def get_agent(agent_id: str):
    """Get a single agent by ID."""
    from ..services.memory_db import get_conn

    con = get_conn()
    try:
        row = con.execute('SELECT * FROM agents WHERE id=?', (agent_id,)).fetchone()
    finally:
        con.close()
    if not row:
        return {'ok': False, 'error': 'Agent not found'}
    return {'ok': True, 'agent': dict(row), 'id': dict(row)['id']}


@router.patch('/{agent_id}')
async def update_agent(agent_id: str, req: Request):
    """Update any fields on an existing agent."""
    try:
        body = await req.json()
    except (json.JSONDecodeError, TypeError, ValueError):
        body = {}
    # whitelist editable fields
    allowed = {'name', 'role', 'model', 'provider', 'color', 'avatar', 'system_prompt', 'status', 'enabled'}
    data = {'id': agent_id}
    for k in allowed:
        if k in body:
            v = body[k]
            if k == 'name':
                v = str(v).strip()[:80]
            elif k == 'role':
                v = str(v)[:200]
            elif k == 'model':
                v = str(v)[:100]
            elif k == 'provider':
                v = str(v)[:32]
            elif k == 'color':
                v = str(v)[:16]
            elif k == 'avatar':
                v = str(v)[:8]
            elif k == 'system_prompt':
                v = str(v)[:4000]
            elif k == 'enabled':
                v = int(bool(v))
            data[k] = v

    if len(data) == 1:
        return {'ok': False, 'error': 'no valid fields to update'}

    result = memory_db.agent_upsert(data)
    memory_db.audit_log('agent_update', str(agent_id))
    return {'ok': bool(result), 'agent': result}


@router.delete('/{agent_id}')
def delete_agent(agent_id: str):
    """Delete a custom agent."""
    # prevent deletion of core defaults
    protected = {'orchestrator', 'brain', 'builder', 'memory'}
    if agent_id in protected:
        return {'ok': False, 'error': f"'{agent_id}' is a core agent and cannot be deleted. Disable it instead."}
    deleted = memory_db.agent_delete(agent_id)
    memory_db.audit_log('agent_delete', agent_id)
    return {'ok': deleted}


@router.post('/{agent_id}/test')
async def test_agent(agent_id: str, req: Request):
    """Quick-test an agent with a single message."""
    try:
        body = await req.json()
    except (json.JSONDecodeError, TypeError, ValueError):
        body = {}
    message = (body.get('message') or 'Say hello and describe your role.').strip()

    agents = {a['id']: a for a in memory_db.agents_list()}
    agent = agents.get(agent_id, {'id': agent_id, 'name': agent_id, 'model': '', 'system_prompt': ''})

    system = agent.get('system_prompt') or f'You are {agent.get("name", agent_id)}. Role: {agent.get("role", "AI")}.'
    messages = [
        {'role': 'system', 'content': system},
        {'role': 'user', 'content': message},
    ]
    result = await llm.complete(
        messages,
        agent_id=agent.get('model') or agent_id,
        model=agent.get('model', ''),
        max_tokens=512,
        inject_steering=False,
    )
    return {
        'ok': result.get('ok'),
        'reply': result.get('text', ''),
        'model': result.get('model', ''),
        'latency_ms': result.get('latency_ms', 0),
        'tokens': result.get('tokens', 0),
    }


def _random_color() -> str:
    import random

    colors = [
        '#7aa2f7',
        '#bb9af7',
        '#9ece6a',
        '#f7768e',
        '#e0af68',
        '#2ac3de',
        '#ff9e64',
        '#c084fc',
        '#7dd3a7',
        '#f5c542',
    ]
    return random.choice(colors)
