"""
Agentic OS — Chat Router
Real LLM chat with streaming SSE, session history, slash command routing.
"""

from __future__ import annotations

import contextlib

import json
import time
import uuid

from fastapi import APIRouter, Request
from fastapi.responses import StreamingResponse

from ..services import llm, memory_db

router = APIRouter(tags=['chat'])

# ── Slash command registry ─────────────────────────────────────────────────────
SLASH_COMMANDS = {
    '/help': 'Show available commands',
    '/goal': 'Plan a goal → Apollo breaks into Kanban tasks',
    '/research': 'Deep research on a topic → Researcher agent',
    '/code': 'Build something → Builder agent',
    '/review': 'Review code or plan → Reviewer agent',
    '/ship': 'Deploy to Vercel → Ship pipeline',
    '/swarm': 'Fan-out to all agents in parallel → judge best',
    '/memory': 'Search Memory Galaxy',
    '/models': 'List available LLM models',
    '/clear': 'Clear chat history (this session)',
}


def _bounded_temperature(value) -> float:
    """Keep provider temperature within the portable 0..2 API range."""
    try:
        return min(2.0, max(0.0, float(value)))
    except (TypeError, ValueError):
        return 0.7


def _bounded_max_tokens(value, default: int = 2048) -> int:
    """Bound user-controlled generation size to protect providers and cost."""
    try:
        return min(16384, max(1, int(value)))
    except (TypeError, ValueError):
        return default


def _parse_slash(message: str) -> tuple[str, str]:
    """Returns (command_or_empty, rest_of_message)"""
    stripped = message.strip()
    if stripped.startswith('/'):
        parts = stripped.split(' ', 1)
        cmd = parts[0].lower()
        rest = parts[1] if len(parts) > 1 else ''
        return cmd, rest
    return '', stripped


def _system_prompt_for_agent(agent: dict) -> str:
    agent_id = (agent.get('id') or '').lower()
    if agent_id in ('default', 'direct ai chat', ''):
        return (
            'You are a helpful, intelligent, and accurate AI assistant. '
            'Provide clear, well-structured, and concise responses in Markdown format. '
            'When writing code, use proper syntax blocks. '
            'Answer questions directly and naturally, exactly like ChatGPT or Claude.'
        )
    custom = (agent.get('system_prompt') or '').strip()
    if custom:
        return custom
    name = agent.get('name', 'AI')
    role = agent.get('role', 'AI assistant')
    return (
        f'You are {name}, a specialized AI assistant. '
        f'Your role: {role}. '
        f'You are helpful, direct, and technically precise. '
        f'Format responses in Markdown. '
        f'When writing code, use proper code blocks with language tags. '
        f'Keep responses focused and actionable.'
    )


# ── Chat endpoint (streaming) ─────────────────────────────────────────────────
@router.post('/api/chat')
async def chat_stream(req: Request):
    """
    POST /api/chat
    Body: {message, agent_id, session_id?, history?}
    Returns: SSE stream of {delta, done, tokens?, cost?, model?}
    """
    try:
        body = await req.json()
    except (json.JSONDecodeError, TypeError, ValueError):
        body = {}
    message = (body.get('message') or '').strip()[:16000]
    agent_id = (body.get('agent_id') or 'default').lower()[:64]
    req_model = (body.get('model') or '').strip()[:200]
    session_id = str(body.get('session_id') or str(uuid.uuid4()))[:128]
    history = body.get('history') or []  # [{role, content}, ...]
    temperature = _bounded_temperature(body.get('temperature', 0.7))
    max_tokens = _bounded_max_tokens(body.get('max_tokens', 2048))

    if not message:

        async def _empty():
            yield f'data: {json.dumps({"delta": "Please enter a message.", "done": True})}\n\n'

        return StreamingResponse(_empty(), media_type='text/event-stream')

    # resolve agent
    agents = memory_db.agents_list()
    agent = next(
        (a for a in agents if a['id'] == agent_id),
        {
            'id': agent_id,
            'name': agent_id.title(),
            'role': 'AI assistant',
            'model': '',
            'provider': 'openrouter',
            'system_prompt': '',
        },
    )

    # slash command routing
    cmd, rest = _parse_slash(message)
    if cmd == '/help':
        help_text = '**Available commands:**\n\n' + '\n'.join(f'- `{k}` — {v}' for k, v in SLASH_COMMANDS.items())

        async def _help():
            yield f'data: {json.dumps({"delta": help_text, "done": True})}\n\n'

        return StreamingResponse(_help(), media_type='text/event-stream')

    if cmd == '/clear':

        async def _clear():
            yield f'data: {json.dumps({"delta": "✅ Chat history cleared.", "done": True, "action": "clear_history"})}\n\n'

        return StreamingResponse(_clear(), media_type='text/event-stream')

    if cmd == '/models':
        models = llm.OPENROUTER_MODELS
        text = '**Available models:**\n\n' + '\n'.join(f'- `{k}` → `{v}`' for k, v in models.items())

        async def _models():
            yield f'data: {json.dumps({"delta": text, "done": True})}\n\n'

        return StreamingResponse(_models(), media_type='text/event-stream')

    if cmd == '/memory':
        results = memory_db.memory_search_fts(rest or 'recent', limit=10)
        text = f'**Memory search:** `{rest}`\n\n'
        if results:
            for r in results:
                text += f'- [{r["source"]}] {r["content"][:120]}\n'
        else:
            text += '_No results found._'

        async def _mem():
            yield f'data: {json.dumps({"delta": text, "done": True})}\n\n'

        return StreamingResponse(_mem(), media_type='text/event-stream')

    # build messages list
    system_prompt = _system_prompt_for_agent(agent)

    # memory-augment: search galaxy for relevant context if use_rag is True
    use_rag = bool(body.get('use_rag', True))
    if use_rag:
        mem_results = memory_db.memory_search_fts(message[:200], limit=4)
        if mem_results:
            filtered = [r for r in mem_results if 'agentic os' not in r.get('content', '').lower() or agent_id not in ('default', 'direct ai chat', '')]
            if filtered:
                ctx = '\n'.join(f'- [{r["source"]}] {r["content"][:200]}' for r in filtered)
                system_prompt += f'\n\n**Relevant memories:**\n{ctx}'

    # Auto-inject compounding 2-Tier Information Hierarchy (Universal Context + Project IVREN)
    try:
        from .hierarchy import get_compiled_context, list_projects
        project_match = None
        for p in list_projects().get('projects', []):
            if p['project_id'] in message.lower() or p['name'].lower() in message.lower():
                project_match = p['project_id']
                break
        if project_match:
            hierarchy_ctx = get_compiled_context(project_match).get('compiled_context', '')
            if hierarchy_ctx:
                system_prompt += f'\n\n{hierarchy_ctx}'
    except (KeyError, TypeError, ValueError, json.JSONDecodeError, OSError, AttributeError, RuntimeError):
        pass

    messages = [{'role': 'system', 'content': system_prompt}]
    # include history (last 20 turns)
    for h in history[-20:]:
        if h.get('role') in ('user', 'assistant') and h.get('content'):
            content = str(h['content'])[:16000]
            if not messages or messages[-1].get('role') != h['role'] or messages[-1].get('content') != content:
                messages.append({'role': h['role'], 'content': content})
    if not messages or messages[-1].get('role') != 'user' or messages[-1].get('content') != message:
        messages.append({'role': 'user', 'content': message})

    # log user message
    _log_chat(session_id, agent_id, 'user', message, model=req_model or agent.get('model', ''))

    # update agent status
    _set_agent_status(agent_id, 'working')

    async def generate():
        """Execute or process generate operation."""
        full_text = ''
        t0 = time.time()
        try:
            async for chunk in llm.stream(
                messages,
                agent_id=agent_id if req_model else (agent.get('model') or agent_id),
                model=req_model or agent.get('model', ''),
                temperature=temperature,
                max_tokens=max_tokens,
                inject_steering=False,
            ):
                yield chunk
                # accumulate text for logging
                try:
                    data = json.loads(chunk.split('data: ', 1)[1])
                    full_text += data.get('delta', '')
                except (KeyError, TypeError, ValueError, json.JSONDecodeError, OSError, AttributeError, RuntimeError):
                    pass
        finally:
            # log assistant reply
            _log_chat(session_id, agent_id, 'assistant', full_text, model=req_model or agent.get('model', ''))
            _set_agent_status(agent_id, 'idle')
            # ingest to memory
            if full_text and len(full_text) > 50:
                memory_db.memory_add(
                    source=f'chat:{agent_id}',
                    content=full_text[:800],
                    tags=f'chat,{agent_id}',
                )

    return StreamingResponse(
        generate(), media_type='text/event-stream', headers={'Cache-Control': 'no-cache', 'X-Accel-Buffering': 'no'}
    )


# ── Non-streaming chat (for swarm internal use) ───────────────────────────────
@router.post('/api/chat/complete')
async def chat_complete(req: Request):
    """Non-streaming single completion — used by swarm fan-out."""
    try:
        body = await req.json()
    except (json.JSONDecodeError, TypeError, ValueError):
        body = {}
    message = (body.get('message') or '').strip()[:16000]
    agent_id = str(body.get('agent_id') or 'default')[:64]
    model = str(body.get('model') or '')[:200]
    system = str(body.get('system') or '')[:16000]
    history = body.get('history') or []
    temperature = _bounded_temperature(body.get('temperature', 0.7))
    max_tokens = _bounded_max_tokens(body.get('max_tokens', 1024), default=1024)

    messages = []
    if system:
        messages.append({'role': 'system', 'content': system})
    for h in history[-10:]:
        if h.get('role') in ('user', 'assistant'):
            messages.append(h)
    messages.append({'role': 'user', 'content': message})

    result = await llm.complete(
        messages, agent_id=agent_id, model=model, temperature=temperature, max_tokens=max_tokens, inject_steering=False
    )
    return result


# ── Chat history ──────────────────────────────────────────────────────────────
@router.get('/api/chat/history')
def chat_history(session_id: str = '', agent: str = '', limit: int = 100):
    """Execute or process chat history operation."""
    con = memory_db.get_conn()
    try:
        where, params = [], []
        if session_id:
            where.append('session_id=?')
            params.append(session_id)
        if agent:
            where.append('agent=?')
            params.append(agent)
        sql = 'SELECT * FROM chat_log'
        if where:
            sql += ' WHERE ' + ' AND '.join(where)
        sql += ' ORDER BY id DESC LIMIT ?'
        params.append(min(limit, 500))
        rows = con.execute(sql, params).fetchall()
    finally:
        con.close()
    return [dict(r) for r in rows]


# ── Helpers ────────────────────────────────────────────────────────────────────
def _log_chat(session_id: str, agent: str, role: str, message: str, tokens: int = 0, cost: float = 0.0, model: str = ''):
    try:
        con = memory_db.get_conn()
        try:
            con.execute(
                'INSERT INTO chat_log(session_id, agent, role, message, tokens, cost, model) VALUES (?,?,?,?,?,?,?)',
                (session_id, agent, role, message[:4000], tokens, cost, model),
            )
            con.execute('UPDATE chat_sessions SET message_count = (SELECT COUNT(*) FROM chat_log WHERE session_id=?), updated_at = CURRENT_TIMESTAMP WHERE id=?', (session_id, session_id))
            con.commit()
        finally:
            con.close()
    except Exception as e:
        import logging

        logging.getLogger('agentic.chat').warning('Failed to log chat: %s', e)


def _set_agent_status(agent_id: str, status: str):
    try:
        con = memory_db.get_conn()
        try:
            con.execute('UPDATE agents SET status=?, updated_at=CURRENT_TIMESTAMP WHERE id=?', (status, agent_id))
            con.commit()
        finally:
            con.close()
    except (KeyError, TypeError, ValueError, json.JSONDecodeError, OSError, AttributeError, RuntimeError):
        pass


@router.post('/api/chat/clear')
async def chat_clear(req: Request):
    """Clear chat history. POST body: {session_id?: str}"""
    try:
        try:
            body = await req.json()
        except (KeyError, TypeError, ValueError, json.JSONDecodeError, OSError, AttributeError, RuntimeError):
            body = {}
    except (KeyError, TypeError, ValueError, json.JSONDecodeError, OSError, AttributeError, RuntimeError):
        body = {}
    session_id = (body.get('session_id') or '').strip()
    con = memory_db.get_conn()
    try:
        if session_id:
            deleted = con.execute('DELETE FROM chat_log WHERE session_id=?', (session_id,)).rowcount
        else:
            # Clear all chat_log entries (full history clear)
            deleted = con.execute('DELETE FROM chat_log').rowcount
        con.commit()
    finally:
        con.close()
    memory_db.audit_log('chat_clear', f'session:{session_id or "all"} deleted:{deleted}')
    return {'ok': True, 'cleared': deleted}
