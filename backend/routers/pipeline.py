"""
Agentic OS — Real Pipeline Router
/goal → /research → /code → /review → /ship
Each stage runs a real LLM call with specialized agent + memory RAG.
Results stream back with live progress events.
"""

from __future__ import annotations

import json
import logging
import time
import uuid

from fastapi import APIRouter, Request
from fastapi.responses import StreamingResponse

from ..services import llm, memory_db
from ..services.llm import sse_guard
from ..services.request_body import as_text, json_body_or_error

router = APIRouter(prefix='/api/pipeline', tags=['pipeline'])
log = logging.getLogger('agentic.pipeline')

# ── Stage definitions ──────────────────────────────────────────────────────────
STAGE_AGENTS = {
    'goal': (
        'orchestrator',
        'You are a strategic planner. Break the goal into clear, actionable sub-tasks. Output a numbered plan.',
    ),
    'research': (
        'researcher',
        'You are a research specialist. Research the topic thoroughly. Find relevant patterns, examples, and best practices.',
    ),
    'code': (
        'builder',
        'You are an expert developer. Write clean, production-ready code. Include all necessary files.',
    ),
    'review': (
        'reviewer',
        'You are a code reviewer. Identify bugs, security issues, and improvements. Provide specific fixes.',
    ),
    'ship': (
        'orchestrator',
        'You are a deployment specialist. Summarize what was built, how to deploy it, and next steps.',
    ),
}

STAGE_ORDER = ['goal', 'research', 'code', 'review', 'ship']


def _summarise(all_results: list[dict], stages: list[str], t_total: float, run_id: str) -> dict:
    """Build the terminal event for a pipeline run.

    BUG FIX: both doors hardcoded `ok: True` and `status: 'complete'` on the
    final event, no matter what happened inside. Verified live with no AI
    provider configured: every stage returned status='error' with empty output,
    and the run still reported ok:true / "complete" -- the UI then printed
    "✅ Done" and toasted "Pipeline complete". A five-stage build that produced
    nothing at all was indistinguishable from one that worked.

    `ok` now means "every stage ran"; a partial run is reported as such with the
    counts and the failed stage names, so the caller can tell the three cases
    apart instead of guessing from the results array.
    """
    succeeded = [r for r in all_results if r.get('status') == 'done']
    failed = [r for r in all_results if r.get('status') != 'done']
    if not failed:
        status = 'complete'
    elif succeeded:
        status = 'partial'
    else:
        status = 'failed'
    return {
        'ok': not failed,
        'run_id': run_id,
        'status': status,
        'stages_total': len(stages),
        'stages_succeeded': len(succeeded),
        'stages_failed': len(failed),
        'failed_stages': [r.get('stage') for r in failed],
        'results': all_results,
        'total_tokens': sum(r.get('tokens', 0) for r in all_results),
        'total_cost': sum(r.get('cost', 0.0) for r in all_results),
        'duration_ms': round((time.time() - t_total) * 1000),
    }


@router.post('/run')
async def pipeline_run(req: Request):
    """
    POST /api/pipeline/run
    Body: {goal, stages?, target?, auto_fix?}
    Returns: SSE stream with stage-by-stage progress + final results
    """
    body, _body_err = await json_body_or_error(req)
    if _body_err:
        return _body_err
    goal = as_text(body.get('goal')) or as_text(body.get('prompt'))
    stages = body.get('stages') or STAGE_ORDER
    body.get('target', 'web')
    stream_out = body.get('stream', True)
    run_id = f'pipe_{uuid.uuid4().hex[:8]}'
    t_total = time.time()

    if not goal:
        # See the note in routers/loops.py: the ok:false middleware already
        # returns 400 for this, verified by revert-proof.
        return {'ok': False, 'error': 'goal required'}

    # Filter stages to valid ones in order
    stages = [s for s in STAGE_ORDER if s in stages]
    if not stages:
        stages = ['goal', 'code']

    agents = {a['id']: a for a in memory_db.agents_list()}

    # Build initial context from memory
    mem_hits = memory_db.memory_search_fts(goal[:200], limit=4)
    mem_ctx = '\n'.join(f'- [{r["source"]}] {r["content"][:120]}' for r in mem_hits)
    base_ctx = f'Goal: {goal}\n\nRelevant memory:\n{mem_ctx}' if mem_ctx else f'Goal: {goal}'

    async def run_stage(stage: str, prior_outputs: dict) -> dict:
        """Execute and run stage operation."""
        agent_id, system_suffix = STAGE_AGENTS.get(stage, ('brain', ''))
        agent = agents.get(agent_id, {'name': agent_id, 'model': '', 'system_prompt': ''})
        system = (agent.get('system_prompt') or '') or system_suffix

        # Build contextual prompt incorporating prior stages
        context_parts = [base_ctx]
        for prev_stage, prev_out in prior_outputs.items():
            if prev_out.get('output'):
                context_parts.append(f'\n## {prev_stage.upper()} output:\n{prev_out["output"][:1500]}')
        context_parts.append(
            f'\n## Your task — {stage.upper()}:\nBased on everything above, execute the {stage} stage now.'
        )
        prompt = '\n'.join(context_parts)

        messages = [
            {'role': 'system', 'content': system or f'You are an expert {agent_id} agent. Be thorough and precise.'},
            {'role': 'user', 'content': prompt},
        ]
        t0 = time.time()
        result = await llm.complete(
            messages, agent_id=agent.get('model') or agent_id, max_tokens=2048, temperature=0.7, inject_steering=False
        )
        latency = round((time.time() - t0) * 1000)
        output = result.get('text', '')

        # Store to memory only on successful (non-error) output
        if output and result.get('ok'):
            memory_db.memory_add(f'pipeline:{run_id}:{stage}', output[:600], f'pipeline,{stage},{run_id}')

        return {
            'stage': stage,
            'agent': agent_id,
            'agent_name': agent.get('name', agent_id),
            'status': 'done' if result.get('ok') else 'error',
            'output': output,
            'tokens': result.get('tokens', 0),
            'cost': result.get('cost', 0.0),
            'latency_ms': latency,
            'model': result.get('model', ''),
            'ok': result.get('ok', False),
        }

    if stream_out:

        async def generate():
            """Execute or process generate operation."""
            prior_outputs = {}
            all_results = []

            yield f'data: {json.dumps({"type": "start", "run_id": run_id, "stages": stages, "goal": goal[:200]})}\n\n'

            for stage in stages:
                yield f'data: {json.dumps({"type": "stage_start", "stage": stage})}\n\n'
                try:
                    result = await run_stage(stage, prior_outputs)
                    prior_outputs[stage] = result
                    all_results.append(result)
                    yield f'data: {json.dumps({"type": "stage_done", "stage": stage, "result": result})}\n\n'
                except Exception as e:
                    err = {'stage': stage, 'status': 'error', 'error': str(e), 'output': ''}
                    all_results.append(err)
                    yield f'data: {json.dumps({"type": "stage_error", "stage": stage, "error": str(e)})}\n\n'

            summary = _summarise(all_results, stages, t_total, run_id)
            memory_db.audit_log(
                'pipeline_run',
                f'{run_id}: {goal[:80]} ({summary["stages_succeeded"]}/{len(stages)} stages ok)',
            )

            yield f'data: {json.dumps({"type": "complete", **summary})}\n\n'

        return StreamingResponse(sse_guard(generate()), media_type='text/event-stream', headers={'Cache-Control': 'no-cache', 'X-Accel-Buffering': 'no'}
        )

    # Non-streaming fallback
    prior_outputs = {}
    all_results = []
    for stage in stages:
        try:
            result = await run_stage(stage, prior_outputs)
            prior_outputs[stage] = result
            all_results.append(result)
        except Exception as e:
            all_results.append({'stage': stage, 'status': 'error', 'error': str(e)})

    summary = _summarise(all_results, stages, t_total, run_id)
    memory_db.audit_log(
        'pipeline_run',
        f'{run_id}: {goal[:80]} ({summary["stages_succeeded"]}/{len(stages)} stages ok)',
    )
    return {**summary, 'results': all_results, 'stages_run': stages}


@router.get('/history')
def pipeline_history(limit: int = 20):
    """Return pipeline run history from memory + audit."""
    con = memory_db.get_conn()
    try:
        rows = con.execute(
            # `localtime` here produced a local wall-clock value that the
            # response layer then stamped with a `Z`, publishing local time
            # labelled as UTC. Return the raw UTC column and let the normaliser
            # label it. (Same defect as the Secrets Vault list -- module 17.)
            "SELECT action, detail, created_at as ts FROM audit WHERE action='pipeline_run' ORDER BY id DESC LIMIT ?",
            (max(1, min(limit, 200)),),
        ).fetchall()
        return [dict(r) for r in rows]
    except (KeyError, TypeError, ValueError, json.JSONDecodeError, OSError, AttributeError, RuntimeError):
        return []
    finally:
        con.close()


@router.get('/templates')
def pipeline_templates():
    """Pre-built goal templates."""
    return [
        {
            'id': 'saas',
            'label': '🚀 SaaS Landing Page',
            'goal': 'Build a modern SaaS landing page with hero, features, pricing, and CTA sections. Use Tailwind CSS.',
        },
        {
            'id': 'api',
            'label': '🔌 REST API',
            'goal': 'Design and implement a RESTful API with authentication, CRUD endpoints, and OpenAPI documentation.',
        },
        {
            'id': 'mobile',
            'label': '📱 Mobile App Screen',
            'goal': 'Build an Expo React Native screen with navigation, data fetching, and a polished dark-mode UI.',
        },
        {
            'id': 'blog',
            'label': '✍️ Blog Post',
            'goal': 'Research and write a comprehensive, SEO-optimised blog post with introduction, sections, and conclusion.',
        },
        {
            'id': 'research',
            'label': '🔭 Market Research',
            'goal': 'Research the AI agent tools market: key players, pricing, features, gaps, and opportunities.',
        },
        {
            'id': 'review',
            'label': '🔨 Code Review',
            'goal': 'Review the current preview/index.html for bugs, performance issues, accessibility, and best practices.',
        },
    ]
