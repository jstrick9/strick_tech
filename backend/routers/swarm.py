"""
Agentic OS — Swarm Router
Real multi-agent fan-out: sends same prompt to N agents in parallel,
judges best response, optionally merges top-2.
"""

from __future__ import annotations

import contextlib

import asyncio
import json
import time
import uuid

from fastapi import APIRouter, Request

from ..services import llm, memory_db

router = APIRouter(prefix='/api/swarm', tags=['swarm'])

def _bounded_int(value, default: int, minimum: int, maximum: int) -> int:
    try:
        return min(maximum, max(minimum, int(value)))
    except (TypeError, ValueError):
        return default


JUDGE_SYSTEM = """You are a neutral judge evaluating AI responses. 
Score each response 0.0–1.0 on: accuracy, depth, clarity, and usefulness.
Return ONLY valid JSON: {"winner": "<agent_id>", "scores": {"<agent_id>": <float>}, "reason": "<one sentence>"}
No markdown fences, no explanation outside the JSON."""

MERGE_SYSTEM = """You are a synthesis expert. 
Merge the best ideas from the provided agent responses into one superior, coherent response.
Preserve the strongest points from each. Output clean Markdown."""


@router.get('/agents')
def swarm_agents():
    """Return all enabled agents for swarm selection."""
    agents = memory_db.agents_list()
    return [a for a in agents if a.get('enabled', 1)]


@router.post('/run')
async def swarm_run(req: Request):
    """
    POST /api/swarm/run
    Body: {prompt, agents: [agent_id, ...], strategy: "judge"|"merge"|"fanout"}
    Returns: {ok, runs, winner, winner_output, merged?, judge_reason, total_latency_ms, total_tokens}
    """
    try:
        body = await req.json()
    except (json.JSONDecodeError, TypeError, ValueError):
        body = {}
    prompt = str(body.get('prompt') or '').strip()[:16000]
    raw_agents = body.get('agents') or ['brain', 'builder', 'researcher', 'creative']
    agent_ids = raw_agents if isinstance(raw_agents, list) else [raw_agents]
    agent_ids = [str(agent_id)[:64] for agent_id in agent_ids if str(agent_id).strip()]
    strategy = str(body.get('strategy') or 'judge').lower()
    if strategy not in {'judge', 'merge', 'fanout'}:
        strategy = 'judge'
    max_tokens = _bounded_int(body.get('max_tokens', 800), 800, 1, 4096)

    if not prompt:
        return {'ok': False, 'error': 'prompt required'}
    if len(agent_ids) < 2:
        return {'ok': False, 'error': 'select at least 2 agents'}

    agent_ids = agent_ids[:16]  # cap at 16 for full multi-agent swarm teams
    all_agents = {a['id']: a for a in memory_db.agents_list()}

    run_id = f'swarm_{uuid.uuid4().hex[:8]}'
    t0 = time.time()

    # ── Fan-out: run all agents in parallel ──────────────────────────────────
    async def run_agent(agent_id: str) -> dict:
        """Execute and run agent operation."""
        agent = all_agents.get(agent_id, {'id': agent_id, 'name': agent_id, 'model': '', 'system_prompt': ''})
        system = agent.get('system_prompt') or (
            f'You are {agent.get("name", agent_id)}, an expert AI agent. '
            f'Role: {agent.get("role", "AI assistant")}. '
            f'Give your best, focused response. Use Markdown.'
        )
        messages = [
            {'role': 'system', 'content': system},
            {'role': 'user', 'content': prompt},
        ]
        t_agent = time.time()
        result = await llm.complete(
            messages,
            agent_id=agent.get('model') or agent_id,
            model=agent.get('model', ''),
            max_tokens=max_tokens,
            temperature=0.7,
            inject_steering=True,  # Enforce runtime .agenticrules and steering context across all swarm agents
        )
        return {
            'agent': agent_id,
            'name': agent.get('name', agent_id),
            'color': agent.get('color', '#7aa2f7'),
            'output': result.get('text', ''),
            'tokens': result.get('tokens', 0),
            'latency_ms': round((time.time() - t_agent) * 1000),
            'model': result.get('model', ''),
            'ok': result.get('ok', False),
        }

    tasks = [run_agent(aid) for aid in agent_ids]
    results = await asyncio.gather(*tasks, return_exceptions=True)

    runs = []
    for r in results:
        if isinstance(r, Exception):
            runs.append({'agent': '?', 'output': str(r), 'tokens': 0, 'latency_ms': 0, 'ok': False})
        else:
            runs.append(r)

    total_tokens = sum(r.get('tokens', 0) for r in runs)
    total_latency = round((time.time() - t0) * 1000)

    winner_id = None
    winner_output = ''
    judge_reason = ''
    merged = None
    scores = {}

    # ── Judge ────────────────────────────────────────────────────────────────
    if strategy in ('judge', 'merge') and len(runs) >= 2:
        valid_runs = [r for r in runs if r.get('ok') and r.get('output')]
        if valid_runs:
            # build judge prompt
            responses_text = '\n\n'.join(f'=== {r["agent"]} ===\n{r["output"][:1200]}' for r in valid_runs)
            judge_messages = [
                {'role': 'system', 'content': JUDGE_SYSTEM},
                {'role': 'user', 'content': f'PROMPT: {prompt[:500]}\n\nRESPONSES:\n{responses_text}'},
            ]
            judge_result = await llm.complete(
                judge_messages,
                agent_id='free',
                max_tokens=256,
                temperature=0.1,
                inject_steering=False,
            )
            try:
                j = json.loads(judge_result.get('text', '{}'))
                winner_id = j.get('winner')
                scores = j.get('scores', {})
                judge_reason = j.get('reason', '')
            except (KeyError, TypeError, ValueError, json.JSONDecodeError, OSError, AttributeError, RuntimeError):
                # fallback: pick longest response
                winner_id = max(valid_runs, key=lambda r: len(r.get('output', '')))['agent']
                judge_reason = 'Fallback: selected longest response'

            if winner_id:
                wr = next((r for r in runs if r['agent'] == winner_id), None)
                winner_output = wr['output'] if wr else ''

            # score into runs
            for r in runs:
                r['score'] = scores.get(r['agent'], 0.5)

    # ── Merge ────────────────────────────────────────────────────────────────
    if strategy == 'merge' and len(runs) >= 2:
        top2 = sorted(
            [r for r in runs if r.get('ok') and r.get('output')], key=lambda r: r.get('score', 0), reverse=True
        )[:2]
        if len(top2) >= 2:
            merge_messages = [
                {'role': 'system', 'content': MERGE_SYSTEM},
                {
                    'role': 'user',
                    'content': f'PROMPT: {prompt[:400]}\n\n'
                    f'RESPONSE A ({top2[0]["agent"]}):\n{top2[0]["output"][:1500]}\n\n'
                    f'RESPONSE B ({top2[1]["agent"]}):\n{top2[1]["output"][:1500]}',
                },
            ]
            merge_result = await llm.complete(
                merge_messages,
                agent_id='free',
                max_tokens=1000,
                temperature=0.4,
                inject_steering=False,
            )
            merged = merge_result.get('text', '')

    # ── Fan-out only ──────────────────────────────────────────────────────────
    if strategy == 'fanout' and not winner_id:
        # just pick the first successful one
        first_ok = next((r for r in runs if r.get('ok')), runs[0] if runs else {})
        winner_id = first_ok.get('agent', '')
        winner_output = first_ok.get('output', '')

    # ── Persist to swarm_history ──────────────────────────────────────────────
    try:
        con = memory_db.get_conn()
        try:
            con.execute(
                """INSERT INTO swarm_history(run_id,prompt,agents,strategy,winner,winner_output,judge_reason,total_latency_ms,total_tokens)
            VALUES (?,?,?,?,?,?,?,?,?)""",
                (
                    run_id,
                    prompt[:500],
                    json.dumps(agent_ids),
                    strategy,
                    winner_id or '',
                    winner_output[:2000],
                    judge_reason,
                    total_latency,
                    total_tokens,
                ),
            )
            con.commit()
        finally:
            con.close()
    except Exception as _pe:
        import logging as _plog

        _plog.getLogger('agentic.swarm').warning('swarm_history persist failed: %s', _pe)

    # ingest to memory — only when winner run actually succeeded
    winner_run_ok = next((r.get('ok') for r in runs if r.get('agent') == winner_id), False)
    if winner_output and winner_run_ok:
        memory_db.memory_add(
            source=f'swarm:{winner_id}',
            content=winner_output[:600],
            tags=f'swarm,{strategy},{winner_id}',
        )

    winner_score = scores.get(winner_id, None) if scores else None

    return {
        'ok': True,
        'run_id': run_id,
        'strategy': strategy,
        'runs': runs,
        'winner': winner_id,
        'winner_output': winner_output,
        'winner_score': winner_score,
        'judge_reason': judge_reason,
        'merged': merged,
        'total_latency_ms': total_latency,
        'total_tokens': total_tokens,
        'improvement_vs_single': f'score: {round(winner_score * 100)}%' if winner_score is not None else '',
    }


@router.get('/history')
def swarm_history(limit: int = 20):
    """Execute or process swarm history operation."""
    con = memory_db.get_conn()
    try:
        rows = con.execute(
            """SELECT run_id, prompt, agents, strategy, winner, judge_reason,
                      total_latency_ms, total_tokens,
                      datetime(created_at,'localtime') as ts
               FROM swarm_history ORDER BY id DESC LIMIT ?""",
            (min(limit, 100),),
        ).fetchall()
    except (KeyError, TypeError, ValueError, json.JSONDecodeError, OSError, AttributeError, RuntimeError):
        return []
    finally:
        con.close()
    out = []
    for r in rows:
        d = dict(r)
        try:
            d['agents'] = json.loads(d.get('agents') or '[]')
        except (KeyError, TypeError, ValueError, json.JSONDecodeError, OSError, AttributeError, RuntimeError):
            d['agents'] = []
        out.append(d)
    return out
