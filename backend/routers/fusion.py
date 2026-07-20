"""
Agentic OS — OpenRouter Fusion + Multi-Model Synthesis
Like OpenRouter Fusion: fan prompt out to N models in parallel,
judge synthesizes into one best answer.

Also includes:
- Multi-model router (auto-pick cheapest/best model per task type)
- Subagent delegation (big model delegates subtasks to smaller models)
- Cost optimizer
- Classify endpoint
- Run history
"""

from __future__ import annotations
from typing import Optional, Union, Any, Dict, List

import contextlib

import asyncio
import json
import logging
import os
import re
import time

from fastapi import APIRouter, Request
from fastapi.responses import StreamingResponse

router = APIRouter(prefix='/api/fusion', tags=['fusion'])
log = logging.getLogger('agentic.fusion')

OR_BASE = 'https://openrouter.ai/api/v1'

# ── Model presets (mirroring OpenRouter Fusion presets) ────────────────────────
FUSION_PRESETS = {
    'quality': {
        'panel': ['anthropic/claude-3.5-sonnet', 'openai/gpt-4o', 'google/gemini-2.5-pro'],
        'judge': 'anthropic/claude-3.5-sonnet',
        'desc': 'Best quality — 3 frontier models + Claude judge',
    },
    'budget': {
        'panel': [
            'google/gemini-2.0-flash-exp:free',
            'meta-llama/llama-3.3-70b-instruct:free',
            'qwen/qwen-2.5-72b-instruct:free',
        ],
        'judge': 'google/gemini-2.0-flash-exp:free',
        'desc': 'Free/cheap models — still better than single model',
    },
    'code': {
        'panel': ['anthropic/claude-3.5-sonnet', 'deepseek/deepseek-chat', 'qwen/qwen-2.5-72b-instruct:free'],
        'judge': 'anthropic/claude-3.5-sonnet',
        'desc': 'Code-optimized panel',
    },
    'research': {
        'panel': ['anthropic/claude-3.5-sonnet', 'openai/gpt-4o', 'google/gemini-2.5-pro'],
        'judge': 'openai/gpt-4o',
        'desc': 'Deep research and analysis',
    },
}

# ── Task-type to model router ──────────────────────────────────────────────────
TASK_ROUTER = {
    # task_type → (model_alias, reasoning)
    'simple': ('google/gemini-2.0-flash-exp:free', 'Simple questions → free model'),
    'code': ('anthropic/claude-3.5-sonnet', 'Code → Claude Sonnet'),
    'research': ('google/gemini-2.5-pro', 'Research → Gemini Pro'),
    'creative': ('anthropic/claude-3.5-sonnet', 'Creative → Claude'),
    'analysis': ('openai/gpt-4o', 'Analysis → GPT-4o'),
    'math': ('deepseek/deepseek-chat', 'Math/logic → DeepSeek'),
    'translation': ('google/gemini-2.0-flash-exp:free', 'Translation → free model'),
    'summary': ('google/gemini-2.0-flash-exp:free', 'Summary → free model'),
    'chat': ('meta-llama/llama-3.3-70b-instruct:free', 'Chat → free Llama'),
}

# Rough cost estimates per 1K tokens (USD)
MODEL_COSTS = {
    'anthropic/claude-3.5-sonnet': 0.003,
    'openai/gpt-4o': 0.005,
    'google/gemini-2.5-pro': 0.002,
    'deepseek/deepseek-chat': 0.0003,
    'google/gemini-2.0-flash-exp:free': 0.0,
    'meta-llama/llama-3.3-70b-instruct:free': 0.0,
    'qwen/qwen-2.5-72b-instruct:free': 0.0,
}


def _or_headers() -> dict:
    return {
        'Authorization': f'Bearer {os.getenv("OPENROUTER_API_KEY", "")}',
        'HTTP-Referer': f'http://localhost:{os.getenv("AGENTIC_OS_PORT", "8787")}',
        'X-Title': 'Agentic OS Fusion',
        'Content-Type': 'application/json',
    }


async def _call_model(model: str, messages: list, max_tokens: int = 1024, temperature: float = 0.7) -> dict:
    """Call a single model and return its response."""
    import httpx

    key = os.getenv('OPENROUTER_API_KEY', '')
    if not key:
        return {
            'model': model,
            'text': f'[Stub: {model} — set OPENROUTER_API_KEY]',
            'tokens': 0,
            'latency_ms': 0,
            'error': False,
        }
    t0 = time.perf_counter()
    try:
        async with httpx.AsyncClient(timeout=60) as client:
            r = await client.post(
                f'{OR_BASE}/chat/completions',
                headers=_or_headers(),
                json={'model': model, 'messages': messages, 'max_tokens': max_tokens, 'temperature': temperature},
            )
            latency_ms = int((time.perf_counter() - t0) * 1000)
            if r.status_code == 200:
                data = r.json()
                text = data['choices'][0]['message']['content']
                usage = data.get('usage', {})
                return {
                    'model': model,
                    'text': text,
                    'tokens': usage.get('total_tokens', 0),
                    'latency_ms': latency_ms,
                    'error': False,
                }
            else:
                return {
                    'model': model,
                    'text': f'[Error {r.status_code}: {r.text[:200]}]',
                    'tokens': 0,
                    'latency_ms': latency_ms,
                    'error': True,
                }
    except Exception as ex:
        return {
            'model': model,
            'text': f'[Error: {ex}]',
            'tokens': 0,
            'latency_ms': int((time.perf_counter() - t0) * 1000),
            'error': True,
        }


async def _judge_responses(panel_responses: list[dict], original_prompt: str, judge_model: str) -> str:
    """Synthesize panel responses into one best answer."""
    panel_text = '\n\n'.join(f'=== {r["model"]} ===\n{r["text"][:1500]}' for r in panel_responses)
    judge_prompt = f"""You are a synthesis judge. Multiple AI models answered the same question.
Synthesize their responses into ONE best answer that:
1. Takes the consensus points all models agree on
2. Includes unique insights from individual models
3. Notes any contradictions and resolves them
4. Is better than any single response alone

Original question: {original_prompt[:500]}

Panel responses:
{panel_text}

Synthesize into one optimal answer:"""

    result = await _call_model(judge_model, [{'role': 'user', 'content': judge_prompt}], max_tokens=2000)
    return result.get('text', '')


def _validate_prompt_or_messages(prompt: str, messages:Optional[ list]) ->Optional[ str]:
    """Return error string if neither prompt nor messages are usable."""
    if prompt:
        return None
    if messages and any((m.get('content') or '').strip() for m in messages):
        return None
    return 'prompt required'


def _save_run_history(
    run_type: str, preset: str, prompt: str, panel: list, synthesis: str, total_ms: int, total_tokens: int
):
    """Persist a fusion run to the memory DB for history."""
    try:
        from ..services.memory_db import get_conn

        con = get_conn()
        try:
            con.execute("""
                CREATE TABLE IF NOT EXISTS fusion_history (
                    id          INTEGER PRIMARY KEY AUTOINCREMENT,
                    run_type    TEXT DEFAULT 'fusion',
                    preset      TEXT DEFAULT 'budget',
                    prompt      TEXT,
                    panel       TEXT,
                    synthesis   TEXT,
                    total_ms    INTEGER DEFAULT 0,
                    total_tokens INTEGER DEFAULT 0,
                    created_at  TIMESTAMP DEFAULT CURRENT_TIMESTAMP
                )
            """)
            con.execute(
                'INSERT INTO fusion_history(run_type,preset,prompt,panel,synthesis,total_ms,total_tokens) VALUES (?,?,?,?,?,?,?)',
                (run_type, preset, prompt[:500], json.dumps(panel), synthesis[:2000], total_ms, total_tokens),
            )
            con.commit()
        finally:
            con.close()
    except Exception as ex:
        log.warning('fusion history save failed: %s', ex)


# ── REST endpoints ─────────────────────────────────────────────────────────────


@router.get('/presets')
def list_presets():
    """Retrieve and return list presets."""
    return {'presets': FUSION_PRESETS}


@router.get('/history')
def get_history(limit: int = 20):
    """Return recent fusion run history."""
    try:
        from ..services.memory_db import get_conn

        con = get_conn()
        try:
            con.execute("""
                CREATE TABLE IF NOT EXISTS fusion_history (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    run_type TEXT DEFAULT 'fusion',
                    preset TEXT DEFAULT 'budget',
                    prompt TEXT,
                    panel TEXT,
                    synthesis TEXT,
                    total_ms INTEGER DEFAULT 0,
                    total_tokens INTEGER DEFAULT 0,
                    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
                )
            """)
            rows = con.execute('SELECT * FROM fusion_history ORDER BY id DESC LIMIT ?', (min(limit, 100),)).fetchall()
            return {'history': [dict(r) for r in rows], 'count': len(rows)}
        finally:
            con.close()
    except Exception as ex:
        return {'history': [], 'count': 0, 'error': str(ex)}


@router.get('/classify')
def classify_prompt(q: str = ''):
    """Classify a prompt to its task type and recommended model."""
    if not q:
        return {'ok': False, 'error': 'q parameter required'}
    task_type = _classify_task(q)
    model, reason = TASK_ROUTER.get(task_type, ('google/gemini-2.0-flash-exp:free', 'default'))
    est_tokens = max(len(q.split()) * 2, 200)
    est_cost = MODEL_COSTS.get(model, 0.001) * est_tokens / 1000
    return {
        'ok': True,
        'task_type': task_type,
        'model': model,
        'reason': reason,
        'est_tokens': est_tokens,
        'est_cost_usd': round(est_cost, 6),
    }


@router.post('/run')
async def fusion_run(req: Request):
    """
    Run OpenRouter Fusion: fan prompt to N models, synthesize with judge.
    Body: {prompt, preset?, panel_models?, judge_model?, max_tokens?, system_prompt?, messages?}
    """
    try:
        body = await req.json()
    except (json.JSONDecodeError, TypeError, ValueError):
        body = {}
    prompt = (body.get('prompt') or '').strip()
    preset = body.get('preset', 'budget')
    messages_in = body.get('messages') or None
    max_tok = min(int(body.get('max_tokens', 1024)), 4096)
    system_prompt = (body.get('system_prompt') or '').strip()

    err = _validate_prompt_or_messages(prompt, messages_in)
    if err:

        async def _err_stream():
            yield f'data: {json.dumps({"type": "error", "error": err})}\n\n'

        return StreamingResponse(_err_stream(), media_type='text/event-stream')

    cfg = FUSION_PRESETS.get(preset, FUSION_PRESETS['budget'])
    panel = body.get('panel_models') or cfg['panel']
    judge_model = body.get('judge_model') or cfg['judge']

    # Build message list
    if messages_in:
        msgs = messages_in
    else:
        msgs = []
        if system_prompt:
            msgs.append({'role': 'system', 'content': system_prompt})
        msgs.append({'role': 'user', 'content': prompt})

    async def _stream():
        yield f'data: {json.dumps({"type": "fusion_start", "preset": preset, "panel": panel, "judge": judge_model})}\n\n'

        t0 = time.perf_counter()
        tasks = [_call_model(m, msgs, max_tok) for m in panel]
        responses = await asyncio.gather(*tasks)

        for r in responses:
            yield f'data: {json.dumps({"type": "panel_response", "model": r["model"], "text": r["text"][:500], "latency_ms": r["latency_ms"], "tokens": r["tokens"], "error": r.get("error", False)})}\n\n'

        yield f'data: {json.dumps({"type": "judging", "judge": judge_model})}\n\n'
        synthesis = await _judge_responses(list(responses), prompt, judge_model)

        total_ms = int((time.perf_counter() - t0) * 1000)
        total_tokens = sum(r.get('tokens', 0) for r in responses)

        # Save to history
        _save_run_history('fusion', preset, prompt, panel, synthesis, total_ms, total_tokens)

        yield f'data: {json.dumps({"type": "synthesis", "text": synthesis, "total_ms": total_ms, "total_tokens": total_tokens, "panel_count": len(panel)})}\n\n'
        yield f'data: {json.dumps({"type": "done"})}\n\n'

    return StreamingResponse(
        _stream(), media_type='text/event-stream', headers={'Cache-Control': 'no-cache', 'X-Accel-Buffering': 'no'}
    )


@router.post('/run/simple')
async def fusion_simple(req: Request):
    """Non-streaming fusion for simple use cases."""
    try:
        body = await req.json()
    except (json.JSONDecodeError, TypeError, ValueError):
        body = {}
    prompt = (body.get('prompt') or '').strip()
    preset = body.get('preset', 'budget')
    max_tok = min(int(body.get('max_tokens', 512)), 4096)

    if not prompt:
        return {'ok': False, 'error': 'prompt required'}

    cfg = FUSION_PRESETS.get(preset, FUSION_PRESETS['budget'])
    panel = body.get('panel_models') or cfg['panel']
    judge = body.get('judge_model') or cfg['judge']
    msgs = [{'role': 'user', 'content': prompt}]

    t0 = time.perf_counter()
    tasks = [_call_model(m, msgs, max_tok) for m in panel]
    responses = await asyncio.gather(*tasks)
    synthesis = await _judge_responses(list(responses), prompt, judge)
    total_ms = int((time.perf_counter() - t0) * 1000)

    _save_run_history(
        'fusion_simple', preset, prompt, panel, synthesis, total_ms, sum(r.get('tokens', 0) for r in responses)
    )

    return {
        'ok': True,
        'synthesis': synthesis,
        'panel': [
            {'model': r['model'], 'preview': r['text'][:200], 'tokens': r['tokens'], 'error': r.get('error', False)}
            for r in responses
        ],
        'preset': preset,
        'total_ms': total_ms,
    }


# ── Multi-model router ─────────────────────────────────────────────────────────
@router.post('/route')
async def smart_route(req: Request):
    """
    Classify the prompt and route to the optimal model automatically.
    """
    try:
        body = await req.json()
    except (json.JSONDecodeError, TypeError, ValueError):
        body = {}
    prompt = (body.get('prompt') or '').strip()
    max_tok = min(int(body.get('max_tokens', 1024)), 4096)
    if not prompt:
        return {'ok': False, 'error': 'prompt required'}

    task_type = _classify_task(prompt)
    model, reason = TASK_ROUTER.get(task_type, ('google/gemini-2.0-flash-exp:free', 'default fallback'))

    result = await _call_model(model, [{'role': 'user', 'content': prompt}], max_tok)
    return {
        'ok': True,
        'task_type': task_type,
        'model': model,
        'reason': reason,
        'text': result.get('text', ''),
        'tokens': result.get('tokens', 0),
        'latency_ms': result.get('latency_ms', 0),
        'error': result.get('error', False),
    }


def _classify_task(prompt: str) -> str:
    """Heuristic task classifier. Summary check runs before research to avoid overlap."""
    p = prompt.lower()
    # Check summary BEFORE research (both share 'summarize' keyword)
    if any(
        w in p
        for w in ['tldr', 'tl;dr', 'tl dr', 'brief summary', 'short summary', 'give me a summary', 'can you summarize']
    ):
        return 'summary'
    if any(
        w in p
        for w in [
            'def ',
            'class ',
            'function',
            'import ',
            '```python',
            '```js',
            'code',
            'bug',
            'debug',
            'error',
            'traceback',
            'fix this',
            'write a function',
            'write a class',
            'implement',
            'refactor',
        ]
    ):
        return 'code'
    if any(
        w in p
        for w in [
            'research',
            'explain',
            'what is',
            'who is',
            'history of',
            'tell me about',
            'overview',
            'compare',
            'how does',
            'what are',
        ]
    ):
        return 'research'
    if any(w in p for w in ['write a story', 'poem', 'creative', 'imagine', 'describe', 'narrative', 'fiction']):
        return 'creative'
    if any(
        w in p
        for w in [
            'analyze',
            'analysis',
            'pros and cons',
            'evaluate',
            'assess',
            'review',
            'critique',
            'strengths',
            'weaknesses',
        ]
    ):
        return 'analysis'
    if any(
        w in p
        for w in [
            'calculate',
            'solve',
            'math',
            'equation',
            'proof',
            'formula',
            'algebra',
            'compute',
            'integral',
            'derivative',
        ]
    ):
        return 'math'
    if any(
        w in p for w in ['translate', 'in french', 'in spanish', 'in chinese', 'in german', 'in japanese', 'in arabic']
    ):
        return 'translation'
    if any(w in p for w in ['summarize', 'summary', 'tldr', 'brief', 'short version', 'key points', 'main points']):
        return 'summary'
    if len(prompt) < 100:
        return 'simple'
    return 'chat'


@router.get('/route/models')
def router_models():
    """Execute or process router models operation."""
    return {
        'task_types': [
            {'type': k, 'model': v[0], 'reason': v[1], 'est_cost_per_1k': MODEL_COSTS.get(v[0], 0.001)}
            for k, v in TASK_ROUTER.items()
        ]
    }


# ── Subagent delegation ────────────────────────────────────────────────────────
@router.post('/subagent')
async def subagent_delegate(req: Request):
    """
    Like OpenRouter Subagent: a large 'orchestrator' model breaks a task
    into subtasks, then delegates each to a smaller/cheaper model.
    """
    try:
        body = await req.json()
    except (json.JSONDecodeError, TypeError, ValueError):
        body = {}
    task = (body.get('task') or '').strip()
    orchestrator = body.get('orchestrator', 'anthropic/claude-3.5-sonnet')
    worker = body.get('worker', 'google/gemini-2.0-flash-exp:free')
    max_subtasks = max(1, min(int(body.get('max_subtasks', 5)), 8))

    if not task:
        return {'ok': False, 'error': 'task required'}

    async def _stream():
        yield f'data: {json.dumps({"type": "subagent_start", "task": task[:100], "orchestrator": orchestrator, "worker": worker})}\n\n'

        # Step 1: Orchestrator breaks task into subtasks
        decompose_prompt = f"""Break this task into {max_subtasks} independent subtasks that can be done in parallel.
Each subtask should be self-contained and achievable by a single focused AI call.

Task: {task}

Return JSON: {{"subtasks": ["subtask 1", "subtask 2", ...]}}
Return ONLY the JSON, no explanation."""

        orch_result = await _call_model(orchestrator, [{'role': 'user', 'content': decompose_prompt}], 500)
        orch_text = orch_result.get('text', '')

        subtasks = []
        # Try to extract JSON from response
        m = re.search(r'\{.*?\}', orch_text, re.DOTALL)
        if m:
            try:
                subtasks = json.loads(m.group(0)).get('subtasks', [])
            except (KeyError, TypeError, ValueError, json.JSONDecodeError, OSError, AttributeError, RuntimeError):
                pass
        # Fallback: split by newlines/numbers if JSON failed
        if not subtasks:
            lines = [l.strip() for l in orch_text.split('\n') if l.strip()]
            subtasks = [re.sub(r'^\d+[\.\)]\s*', '', l) for l in lines if l][:max_subtasks]
        if not subtasks:
            subtasks = [task]  # final fallback: treat as single task

        subtasks = [s for s in subtasks if s][:max_subtasks]

        yield f'data: {json.dumps({"type": "subtasks_planned", "subtasks": subtasks, "count": len(subtasks)})}\n\n'

        # Step 2: Run each subtask with the worker model in parallel
        worker_tasks = [_call_model(worker, [{'role': 'user', 'content': st}], 600) for st in subtasks]
        worker_results = await asyncio.gather(*worker_tasks)

        subtask_results = []
        for i, (st, wr) in enumerate(zip(subtasks, worker_results)):
            subtask_results.append({'subtask': st, 'result': wr.get('text', ''), 'tokens': wr.get('tokens', 0)})
            yield f'data: {json.dumps({"type": "subtask_done", "index": i, "subtask": st[:80], "result_len": len(wr.get("text", "")), "error": wr.get("error", False)})}\n\n'

        # Step 3: Orchestrator synthesizes all results
        synth_parts = '\n'.join(
            f'Subtask {i + 1}: {r["subtask"]}\nResult: {r["result"][:500]}' for i, r in enumerate(subtask_results)
        )
        synth_prompt = f"""You delegated this task: {task}

Your worker agents completed these subtasks:
{synth_parts}

Synthesize all results into a complete, unified answer to the original task."""

        t0 = time.perf_counter()
        final = await _call_model(orchestrator, [{'role': 'user', 'content': synth_prompt}], 1500)
        total_ms = int((time.perf_counter() - t0) * 1000)
        total_tokens = sum(r.get('tokens', 0) for r in worker_results)

        _save_run_history(
            'subagent', 'N/A', task, [orchestrator, worker], final.get('text', ''), total_ms, total_tokens
        )

        yield f'data: {json.dumps({"type": "synthesis", "text": final.get("text", ""), "subtask_count": len(subtasks), "total_ms": total_ms, "total_tokens": total_tokens})}\n\n'
        yield f'data: {json.dumps({"type": "done"})}\n\n'

    return StreamingResponse(
        _stream(), media_type='text/event-stream', headers={'Cache-Control': 'no-cache', 'X-Accel-Buffering': 'no'}
    )


# ── Cost optimizer ─────────────────────────────────────────────────────────────
@router.post('/optimize-cost')
async def cost_optimize(req: Request):
    """Suggest which model to use based on task complexity and budget."""
    try:
        body = await req.json()
    except (json.JSONDecodeError, TypeError, ValueError):
        body = {}
    prompt = (body.get('prompt') or '').strip()
    budget = float(body.get('budget_usd', 0.01))
    max_tok = int(body.get('max_tokens', 1024))

    if not prompt:
        return {'ok': False, 'error': 'prompt required'}

    task_type = _classify_task(prompt)
    model, reason = TASK_ROUTER.get(task_type, ('google/gemini-2.0-flash-exp:free', 'default'))
    est_tokens = max(len(prompt.split()) * 2 + max_tok, 200)
    est_cost = MODEL_COSTS.get(model, 0.001) * est_tokens / 1000
    downgraded = False
    original_model = model

    if est_cost > budget:
        model = 'google/gemini-2.0-flash-exp:free'
        reason = f'Budget ${budget:.6f} exceeded for {original_model} (est ${est_cost:.6f}) — using free model'
        est_cost = 0.0
        downgraded = True

    return {
        'ok': True,
        'task_type': task_type,
        'recommended': model,
        'original_model': original_model,
        'reason': reason,
        'est_tokens': est_tokens,
        'est_cost_usd': round(est_cost, 6),
        'budget_usd': budget,
        'within_budget': True,  # always true — we downgrade to free if needed
        'downgraded': downgraded,
    }
