"""
Agentic OS — Chat Router
Real LLM chat with streaming SSE, session history, slash command routing.
"""

from __future__ import annotations

import json
import uuid

from fastapi import APIRouter, Request
from fastapi.responses import StreamingResponse

from ..services import llm, memory_db
from ..services.llm import sse_guard
from ..services.request_body import as_text, json_body_or_error

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


# Markers that identify platform-generated failure/placeholder text rather than
# genuine model output. Used to keep the long-term memory store clean — see the
# ingestion guard in chat_stream().
_ERROR_TEXT_MARKERS = (
    'no openrouter_api_key',
    '[stream error]',
    'openrouter disconnected',
    'auto-falling back to local',
    "i couldn't complete that request",
    'no usable model is configured',
)


def _looks_like_error_text(text: str) -> bool:
    """True if text is platform error/placeholder output, not a real completion."""
    low = (text or '').lower()
    return any(marker in low for marker in _ERROR_TEXT_MARKERS)


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
    custom = (as_text(agent.get('system_prompt')) or '')
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
    body, _body_err = await json_body_or_error(req)
    if _body_err:
        return _body_err
    # `message` is normally a string, but Chat sends an OpenAI-format list of
    # content parts when the user attaches images (see sendChat()). Keep the
    # structured form for the provider call while deriving a plain-text view
    # for logging, slash-command parsing and memory/RAG lookups — calling
    # .strip() on a list would raise before any of that could run.
    raw_message = body.get('message')
    message_parts = None
    if isinstance(raw_message, list):
        message_parts = raw_message
        message = ' '.join(
            str(p.get('text', ''))
            for p in raw_message
            if isinstance(p, dict) and p.get('type') == 'text'
        ).strip()[:16000]
    else:
        message = as_text(raw_message, limit=16000)[:16000]
    has_images = bool(
        message_parts
        and any(isinstance(p, dict) and p.get('type') == 'image_url' for p in message_parts)
    )
    agent_id = (body.get('agent_id') or 'default').lower()[:64]
    req_model = as_text(body.get('model'))[:200]
    session_id = str(body.get('session_id') or str(uuid.uuid4()))[:128]
    history = body.get('history') or []  # [{role, content}, ...]
    temperature = _bounded_temperature(body.get('temperature', 0.7))
    max_tokens = _bounded_max_tokens(body.get('max_tokens', 2048))

    if not message and not has_images:

        async def _empty():
            yield f'data: {json.dumps({"delta": "Please enter a message.", "done": True})}\n\n'

        return StreamingResponse(sse_guard(_empty()), media_type='text/event-stream')

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

        return StreamingResponse(sse_guard(_help()), media_type='text/event-stream')

    if cmd == '/clear':
        # BUG FIX: this used to report "✅ Chat history cleared." while doing
        # nothing server-side — only the browser's DOM was wiped. The rows
        # stayed in chat_log, so reloading the page (or reopening the session
        # from the history drawer) brought the "cleared" conversation straight
        # back, and the model kept receiving it as context. Now actually
        # deletes this session's messages, and reports honestly if it can't.
        deleted = 0
        clear_error = None
        try:
            con = memory_db.get_conn()
            try:
                deleted = con.execute('DELETE FROM chat_log WHERE session_id=?', (session_id,)).rowcount
                con.execute(
                    'UPDATE chat_sessions SET message_count=0, updated_at=CURRENT_TIMESTAMP WHERE id=?',
                    (session_id,),
                )
                con.commit()
            finally:
                con.close()
            memory_db.audit_log('chat_clear', f'session:{session_id} deleted:{deleted}')
        except Exception as e:  # noqa: BLE001 - surfaced to the user below
            clear_error = str(e)

        if clear_error:
            clear_text = f'⚠️ Could not clear this conversation: {clear_error}'
        elif deleted:
            clear_text = f'✅ Cleared {deleted} message{"s" if deleted != 1 else ""} from this conversation.'
        else:
            clear_text = 'ℹ️ This conversation was already empty.'

        async def _clear():
            payload = {'delta': clear_text, 'done': True}
            # Only wipe the transcript in the UI if the server really did.
            if not clear_error:
                payload['action'] = 'clear_history'
            yield f'data: {json.dumps(payload)}\n\n'

        return StreamingResponse(sse_guard(_clear()), media_type='text/event-stream')

    if cmd == '/models':
        # UX FIX: this only ever listed the hardcoded OpenRouter registry, so a
        # user running entirely on local Ollama models was shown a list of
        # cloud models they had no key for, and none of the models actually
        # installed and usable on their machine. Local models are now listed
        # first (they're the ones that will actually run), and the cloud
        # registry is annotated with whether a key is configured at all.
        text = ''
        try:
            health = await llm.ollama_health()
        except Exception:
            health = {'running': False, 'models': []}

        local_models = health.get('models') or []
        if health.get('running') and local_models:
            text += '**Local models (Ollama — ready to use):**\n\n'
            text += '\n'.join(f'- `{m}`' for m in local_models)
            text += '\n\n'

        has_key = bool(llm._or_key())
        if has_key:
            text += '**Cloud models (OpenRouter — key configured):**\n\n'
        else:
            text += '**Cloud models (OpenRouter — ⚠️ no API key set, these will not run):**\n\n'
        text += '\n'.join(f'- `{k}` → `{v}`' for k, v in llm.OPENROUTER_MODELS.items())

        if not has_key and not local_models:
            text += (
                '\n\n_No usable model is configured yet._ Add an OpenRouter key in '
                '**Settings → Connect AI**, or install a local model with `ollama pull llama3.2:3b`.'
            )

        async def _models():
            yield f'data: {json.dumps({"delta": text, "done": True})}\n\n'

        return StreamingResponse(sse_guard(_models()), media_type='text/event-stream')

    if cmd == '/goal':
        # NOTE: previously /help advertised /goal ("Plan a goal → Apollo
        # breaks into Kanban tasks") but there was no handler for it at
        # all here — it silently fell through to the plain LLM chat path,
        # so typing "/goal Build a SaaS landing page" just sent that
        # literal text (slash included) to whatever model was selected,
        # confusing it. Now genuinely creates a real goal via the same
        # goals_v2 table /api/goals uses, then tells the user it's ready
        # to decompose/launch from the Goals pane.
        goal_title = rest.strip() or message.strip()
        if not goal_title:
            async def _goal_empty():
                yield f'data: {json.dumps({"delta": "Usage: `/goal <what you want to accomplish>`", "done": True})}\n\n'
            return StreamingResponse(sse_guard(_goal_empty()), media_type='text/event-stream')

        from . import goal_manager

        goal_id = None
        try:
            goal_id = goal_manager._create_goal_record(title=goal_title[:300], domain='Work', priority='medium')
        except Exception:
            goal_id = None

        if goal_id:
            text = (
                f'✅ **Goal created:** {goal_title}\n\n'
                f'Opening the Goals workstation so you can decompose it into milestones, '
                f'assign agents, and launch it.'
            )
        else:
            text = f"⚠️ Couldn't create the goal automatically. Open the **Goals** pane and create it manually: {goal_title}"

        async def _goal():
            payload = {'delta': text, 'done': True, 'action': 'navigate', 'target': 'goals'}
            if goal_id:
                payload['goal_id'] = goal_id
            yield f'data: {json.dumps(payload)}\n\n'

        return StreamingResponse(sse_guard(_goal()), media_type='text/event-stream')

    if cmd in ('/research', '/code', '/review', '/ship', '/swarm'):
        # Same story as /goal above — these were listed in /help with no
        # actual implementation. Each now routes you to the workstation
        # built for that job, with your prompt carried over so you don't
        # have to retype it.
        target_pane = {
            '/research': 'websearch',
            '/code': 'studio',
            '/review': 'bugbot',
            '/ship': 'deploy',
            '/swarm': 'swarm',
        }[cmd]
        pane_label = {
            'websearch': 'Web Search',
            'studio': 'Code Studio',
            'bugbot': 'BugBot',
            'deploy': 'Deploy',
            'swarm': 'Multi-Agent Swarm',
        }[target_pane]
        carried_prompt = rest.strip() or message.strip()
        text = f'🚀 Opening **{pane_label}**' + (' with your prompt ready to go.' if carried_prompt else '.')

        async def _route():
            yield f'data: {json.dumps({"delta": text, "done": True, "action": "navigate", "target": target_pane, "carry_prompt": carried_prompt})}\n\n'

        return StreamingResponse(sse_guard(_route()), media_type='text/event-stream')

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

        return StreamingResponse(sse_guard(_mem()), media_type='text/event-stream')

    # build messages list
    system_prompt = _system_prompt_for_agent(agent)

    # memory-augment: search galaxy for relevant context if use_rag is True
    use_rag = bool(body.get('use_rag', True))
    if use_rag:
        # Over-fetch, then drop unusable rows before trimming to the budget —
        # otherwise a few junk hits silently consume the whole context window.
        mem_results = memory_db.memory_search_fts(message[:200], limit=12)
        if mem_results:
            is_generic_agent = agent_id in ('default', 'direct ai chat', '')
            filtered = []
            for r in mem_results:
                content = (as_text(r.get('content')) or '')
                if not content:
                    continue
                # BUG FIX: retrieval could surface platform error text that was
                # ingested from OTHER subsystems (e.g. source='webhook:…'
                # rows holding "⚠️ No OPENROUTER_API_KEY set…"), which then got
                # injected into the system prompt as if it were user knowledge.
                # Guarding only at chat-ingest time was not enough, because the
                # memory store is shared — so retrieval is filtered too.
                if _looks_like_error_text(content):
                    continue
                # Keep self-referential "Agentic OS" chatter out of generic
                # assistant conversations, where it derails unrelated answers.
                if is_generic_agent and 'agentic os' in content.lower():
                    continue
                filtered.append(r)
                if len(filtered) >= 4:
                    break
            if filtered:
                ctx = '\n'.join(f'- [{r["source"]}] {r["content"][:200]}' for r in filtered)
                system_prompt += f'\n\n**Relevant memories:**\n{ctx}'

    # Auto-inject compounding 2-Tier Information Hierarchy (Universal Context +
    # Project IVREN) AND the merged AI Guidelines (Steering Files) block —
    # get_compiled_context() now appends the compiled steering rules itself
    # (see backend/routers/hierarchy.py), so a single call here covers both.
    #
    # BUG FIX (Tier 1 / Universal Context): this used to ONLY fire when the
    # user's message text happened to contain a Tier-2 project's id/name as
    # a literal keyword match — meaning Tier 1 (About Me / Business / Voice /
    # Offers), which the pane's own UI explicitly advertises as
    # "automatically applies to every conversation", was in fact NEVER
    # injected into ordinary chat messages that didn't happen to name a
    # project. Per product decision: Chat now always receives Tier 1
    # unconditionally (matching what Swarm already effectively got via
    # inject_steering=True), with the Tier 2 project-keyword-match behavior
    # preserved as an ADDITIONAL delta on top when a project is mentioned.
    #
    # BUG FIX (Steering Files / AI Guidelines): /api/chat previously called
    # llm.stream()/llm.complete() with inject_steering=False, meaning
    # Steering Files NEVER made it into a single regular chat message
    # despite being advertised as "injected into every AI prompt" — only
    # non-Chat callers that didn't opt out (e.g. Swarm) actually received
    # them. Per product decision: Chat now includes this too, matching Swarm.
    try:
        from .hierarchy import get_compiled_context, list_projects
        project_match = None
        for p in list_projects().get('projects', []):
            if p['project_id'] in message.lower() or p['name'].lower() in message.lower():
                project_match = p['project_id']
                break
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
    # Send the structured multi-modal parts when images are attached, so the
    # provider actually receives the image; otherwise send the plain string.
    outgoing_content = message_parts if has_images else message
    if not messages or messages[-1].get('role') != 'user' or messages[-1].get('content') != outgoing_content:
        messages.append({'role': 'user', 'content': outgoing_content})

    # FEATURE: honour enforcing budget caps BEFORE spending. Caps were purely
    # retrospective — a breach wrote an alert row after the money was already
    # spent, and the 'pause'/'kill' actions the FinOps API accepts were never
    # read by anything. Chat now refuses to call a paid model once an enforcing
    # cap is reached, and says which cap and why.
    try:
        from .finops import check_budget_before_spend

        gate = check_budget_before_spend(agent_id=agent_id)
    except Exception:  # noqa: BLE001 - a guardrail failure must not block chat
        gate = {'allowed': True}

    if not gate.get('allowed'):
        blocked_text = (
            f'🛑 **Request blocked by a budget cap.**\n\n{gate.get("reason", "")}\n\n'
            'Raise or disable the cap in **Observability → Cost**, or switch to a '
            'local model (which is free and not subject to spend caps).'
        )

        async def _blocked():
            yield f'data: {json.dumps({"delta": blocked_text, "done": True, "blocked": True, "cap_id": gate.get("cap_id", "")})}\n\n'

        return StreamingResponse(sse_guard(_blocked()), media_type='text/event-stream')

    # log user message
    _log_chat(session_id, agent_id, 'user', message, model=req_model or agent.get('model', ''))

    # update agent status
    _set_agent_status(agent_id, 'working')

    # When the user turns the "⚡ Stream" toggle off, deltas are buffered and
    # delivered as a single frame instead of token-by-token. The transport is
    # still SSE so the client's parsing path is identical either way.
    want_stream = body.get('stream', True) is not False

    async def generate():
        """Execute or process generate operation."""
        full_text = ''
        buffered: list[str] = []
        # Real usage reported by the provider on the terminal SSE frame.
        # BUG FIX: these were never captured, so _log_chat() always stored
        # tokens=0/cost=0 and /api/cost, the status-bar spend readout and the
        # FinOps analytics were structurally incapable of showing anything.
        used_tokens = 0
        used_cost = 0.0
        resolved_model = req_model or agent.get('model', '')
        # Only genuine model output is eligible for long-term memory ingestion.
        is_real_completion = True
        try:
            async for chunk in llm.stream(
                messages,
                agent_id=agent_id if req_model else (agent.get('model') or agent_id),
                model=req_model or agent.get('model', ''),
                temperature=temperature,
                max_tokens=max_tokens,
                inject_steering=False,
            ):
                if want_stream:
                    yield chunk
                # accumulate text + usage for logging
                try:
                    data = json.loads(chunk.split('data: ', 1)[1])
                    full_text += data.get('delta', '')
                    if not want_stream and data.get('delta'):
                        buffered.append(data['delta'])
                    if data.get('done'):
                        used_tokens = int(data.get('tokens', 0) or 0)
                        used_cost = float(data.get('cost', 0.0) or 0.0)
                        resolved_model = data.get('model') or resolved_model
                        # llm.stream() flags placeholder replies (no API key
                        # configured) with stub=True, and hard failures with
                        # an 'error' key. Neither is real model output.
                        if data.get('stub') or data.get('error'):
                            is_real_completion = False
                        if not want_stream:
                            final_payload = {
                                'delta': ''.join(buffered),
                                'done': True,
                                'model': resolved_model,
                                'tokens': used_tokens,
                                'cost': used_cost,
                            }
                            if data.get('stub'):
                                final_payload['stub'] = True
                            if data.get('error'):
                                final_payload['error'] = data['error']
                            yield f'data: {json.dumps(final_payload)}\n\n'
                except (KeyError, TypeError, ValueError, json.JSONDecodeError, OSError, AttributeError, RuntimeError):
                    pass
        finally:
            # log assistant reply
            _log_chat(
                session_id,
                agent_id,
                'assistant',
                full_text,
                tokens=used_tokens,
                cost=used_cost,
                model=resolved_model,
            )
            _set_agent_status(agent_id, 'idle')

            # FEATURE: feed the FinOps cost ledger. Chat — by far the largest
            # source of spend — never wrote to cost_ledger at all, so budget
            # caps had nothing to measure and the FinOps dashboard could only
            # ever report zero. Now that real token counts are captured, record
            # them so caps, burn-rate projections and per-agent attribution work.
            # Cost is now recorded by llm.stream() itself (Module 21
            # follow-up), covering every streaming caller rather than only this
            # one. The explicit record_cost() that used to live here would now
            # be a DOUBLE count -- the two changes are inseparable, which is
            # why they land in the same commit.
            #
            # What changes for the user: source_type is uniformly 'llm' rather
            # than 'chat'. A per-caller label that only 1 of 30 callers ever set
            # was never a usable dimension, and session attribution remains
            # available from chat_log.
            # Ingest to long-term memory — but ONLY real model output.
            #
            # BUG FIX: the sole guard here used to be `len(full_text) > 50`, so
            # every failure mode got permanently written into the memory store
            # as if it were knowledge: "⚠️ No OPENROUTER_API_KEY set…" stubs,
            # "[stream error]…" text, and provider fallback notices. Those
            # memories were then retrieved by the use_rag lookup above and
            # injected into the system prompt of later conversations — a
            # self-poisoning loop. On this machine 18 of 19 stored chat
            # memories were error text before this fix.
            if full_text and len(full_text) > 50 and is_real_completion and not _looks_like_error_text(full_text):
                memory_db.memory_add(
                    source=f'chat:{agent_id}',
                    content=full_text[:800],
                    tags=f'chat,{agent_id}',
                )

    return StreamingResponse(sse_guard(generate()), media_type='text/event-stream', headers={'Cache-Control': 'no-cache', 'X-Accel-Buffering': 'no'}
    )


# ── Non-streaming chat (for swarm internal use) ───────────────────────────────
@router.post('/api/chat/complete')
async def chat_complete(req: Request):
    """Non-streaming single completion — used by swarm fan-out."""
    body, _body_err = await json_body_or_error(req)
    if _body_err:
        return _body_err
    message = as_text(body.get('message'))[:16000]
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
        params.append(max(1, min(limit, 500)))
        rows = con.execute(sql, params).fetchall()
    finally:
        con.close()
    return [dict(r) for r in rows]


@router.get('/api/chat/search')
def chat_search(q: str = '', limit: int = 20):
    """Search across all chat messages. Returns matching messages with session context."""
    if not q or len(q.strip()) < 2:
        return {'ok': True, 'results': [], 'count': 0}
    con = memory_db.get_conn()
    try:
        pattern = f'%{q.strip()}%'
        rows = con.execute(
            """SELECT cl.id, cl.session_id, cl.role, cl.message, cl.agent, cl.model,
                      cl.created_at, cs.name as session_name
               FROM chat_log cl
               LEFT JOIN chat_sessions cs ON cs.id = cl.session_id
               WHERE cl.message LIKE ?
               ORDER BY cl.created_at DESC
               LIMIT ?""",
            (pattern, max(1, min(limit, 50)))
        ).fetchall()
    finally:
        con.close()
    results = []
    for r in rows:
        d = dict(r)
        msg = d.get('message', '')
        # Highlight match context (80 chars around match)
        idx = msg.lower().find(q.strip().lower())
        if idx >= 0:
            start = max(0, idx - 40)
            end = min(len(msg), idx + len(q.strip()) + 40)
            snippet = ('…' if start > 0 else '') + msg[start:end] + ('…' if end < len(msg) else '')
        else:
            snippet = msg[:120]
        results.append({
            'id': d['id'],
            'session_id': d['session_id'],
            'session_name': d.get('session_name', ''),
            'role': d['role'],
            'agent': d.get('agent', ''),
            'snippet': snippet,
            'created_at': d.get('created_at', ''),
        })
    return {'ok': True, 'results': results, 'count': len(results)}


# ── Helpers ────────────────────────────────────────────────────────────────────
def _log_chat(session_id: str, agent: str, role: str, message: str, tokens: int = 0, cost: float = 0.0, model: str = ''):
    try:
        con = memory_db.get_conn()
        try:
            con.execute(
                'INSERT INTO chat_log(session_id, agent, role, message, tokens, cost, model) VALUES (?,?,?,?,?,?,?)',
                # 16000, matching what the API accepts. This was [:4000] while
                # both the inbound message and the replayed history are capped
                # at 16000, so a long prompt or a long model reply lost 12000
                # characters SILENTLY on the way into chat_log. The user saw
                # the full reply in the stream and a truncated one on reload,
                # with nothing to explain the difference; SQLite TEXT has no
                # fixed width, so the cap bought nothing.
                (session_id, agent, role, (message or '')[:16000], tokens, cost, model),
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
    session_id = as_text(body.get('session_id'))
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
