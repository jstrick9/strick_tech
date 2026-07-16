"""
Agentic OS — Arena Mode: A/B Model Testing (Windsurf exclusive feature)
Run two models side-by-side on the same prompt, vote on winner,
build personal + global leaderboard from real-task performance.
"""

from __future__ import annotations

import contextlib

import asyncio
import json
import logging
import time
import uuid

from fastapi import APIRouter, Request
from fastapi.responses import StreamingResponse

router = APIRouter(prefix='/api/arena', tags=['arena'])
log = logging.getLogger('agentic.arena')

# ── DB schema ──────────────────────────────────────────────────────────────────
_SCHEMA = """
CREATE TABLE IF NOT EXISTS arena_battles (
    id          TEXT PRIMARY KEY,
    prompt      TEXT NOT NULL,
    model_a     TEXT NOT NULL,
    model_b     TEXT NOT NULL,
    response_a  TEXT DEFAULT '',
    response_b  TEXT DEFAULT '',
    winner      TEXT DEFAULT '',
    vote_reason TEXT DEFAULT '',
    latency_a   INTEGER DEFAULT 0,
    latency_b   INTEGER DEFAULT 0,
    tokens_a    INTEGER DEFAULT 0,
    tokens_b    INTEGER DEFAULT 0,
    category    TEXT DEFAULT 'general',
    created_at  TIMESTAMP DEFAULT CURRENT_TIMESTAMP
);
CREATE TABLE IF NOT EXISTS arena_leaderboard (
    model       TEXT PRIMARY KEY,
    wins        INTEGER DEFAULT 0,
    losses      INTEGER DEFAULT 0,
    ties        INTEGER DEFAULT 0,
    battles     INTEGER DEFAULT 0,
    avg_latency INTEGER DEFAULT 0,
    elo         REAL DEFAULT 1000.0,
    updated_at  TIMESTAMP DEFAULT CURRENT_TIMESTAMP
);
CREATE INDEX IF NOT EXISTS idx_arena_battles_models ON arena_battles(model_a, model_b);
CREATE INDEX IF NOT EXISTS idx_arena_lb_elo ON arena_leaderboard(elo DESC);
"""

AVAILABLE_MODELS = {
    'claude-sonnet': 'anthropic/claude-3.5-sonnet',
    'claude-haiku': 'anthropic/claude-3-haiku',
    'gpt-4o': 'openai/gpt-4o',
    'gpt-4o-mini': 'openai/gpt-4o-mini',
    'gemini-pro': 'google/gemini-2.0-flash-exp:free',
    'gemini-flash': 'google/gemini-flash-1.5',
    'llama-70b': 'meta-llama/llama-3.3-70b-instruct:free',
    'qwen-72b': 'qwen/qwen-2.5-72b-instruct:free',
    'deepseek': 'deepseek/deepseek-chat',
    'mistral': 'mistralai/mistral-small',
}


def _ensure_schema():
    from ..services.memory_db import get_conn

    con = get_conn()
    try:
        con.executescript(_SCHEMA)
        # Seed leaderboard entries
        for model in AVAILABLE_MODELS:
            con.execute('INSERT OR IGNORE INTO arena_leaderboard(model) VALUES (?)', (model,))
        con.commit()
    finally:
        con.close()


_ensure_schema()


def _update_elo(winner: str, loser: str, k: float = 32.0):
    """Update ELO ratings after a battle."""
    from ..services.memory_db import get_conn

    con = get_conn()
    try:
        w = con.execute('SELECT elo FROM arena_leaderboard WHERE model=?', (winner,)).fetchone()
        l = con.execute('SELECT elo FROM arena_leaderboard WHERE model=?', (loser,)).fetchone()
        elo_w = w['elo'] if w else 1000.0
        elo_l = l['elo'] if l else 1000.0

        expected_w = 1 / (1 + 10 ** ((elo_l - elo_w) / 400))
        new_elo_w = elo_w + k * (1 - expected_w)
        new_elo_l = elo_l + k * (0 - (1 - expected_w))

        con.execute(
            'UPDATE arena_leaderboard SET elo=?,wins=wins+1,battles=battles+1,updated_at=CURRENT_TIMESTAMP WHERE model=?',
            (new_elo_w, winner),
        )
        con.execute(
            'UPDATE arena_leaderboard SET elo=?,losses=losses+1,battles=battles+1,updated_at=CURRENT_TIMESTAMP WHERE model=?',
            (new_elo_l, loser),
        )
        con.commit()
    finally:
        con.close()


# ── REST endpoints ─────────────────────────────────────────────────────────────
@router.get('/models')
def list_models():
    """Retrieve and return list models."""
    return {'models': [{'id': k, 'model': v} for k, v in AVAILABLE_MODELS.items()]}


@router.post('/battle')
async def create_battle(req: Request):
    """Start an A/B battle: stream both model responses in parallel."""
    try:
        body = await req.json()
    except (json.JSONDecodeError, TypeError, ValueError):
        body = {}
    prompt = (body.get('prompt') or '').strip()
    model_a = body.get('model_a', 'claude-sonnet')
    model_b = body.get('model_b', 'gpt-4o')
    category = body.get('category', 'general')
    system = body.get('system_prompt', 'You are a helpful AI assistant.')

    if not prompt:
        return {'ok': False, 'error': 'prompt required'}

    battle_id = f'battle_{uuid.uuid4().hex[:8]}'
    model_a_full = AVAILABLE_MODELS.get(model_a, model_a)
    model_b_full = AVAILABLE_MODELS.get(model_b, model_b)

    # Save battle record
    from ..services.memory_db import get_conn

    con = get_conn()
    try:
        con.execute(
            'INSERT INTO arena_battles(id,prompt,model_a,model_b,category) VALUES (?,?,?,?,?)',
            (battle_id, prompt[:2000], model_a, model_b, category),
        )
        con.commit()
    finally:
        con.close()

    async def _stream():

        yield f'data: {json.dumps({"type": "battle_start", "battle_id": battle_id, "model_a": model_a, "model_b": model_b})}\n\n'

        messages = [{'role': 'system', 'content': system}, {'role': 'user', 'content': prompt}]

        resp_a, resp_b = '', ''
        lat_a = lat_b = tok_a = tok_b = 0

        async def _run_model(model_id: str, model_full: str, side: str):
            nonlocal resp_a, resp_b, lat_a, lat_b, tok_a, tok_b
            t0 = time.perf_counter()
            text = ''
            try:
                import os

                import httpx

                key = os.getenv('OPENROUTER_API_KEY', '')
                if not key:
                    raise ValueError('No API key')
                async with httpx.AsyncClient(timeout=30) as client:
                    async with client.stream(
                        'POST',
                        'https://openrouter.ai/api/v1/chat/completions',
                        headers={'Authorization': f'Bearer {key}', 'Content-Type': 'application/json'},
                        json={'model': model_full, 'messages': messages, 'stream': True, 'max_tokens': 1024},
                    ) as resp:
                        async for line in resp.aiter_lines():
                            if not line.startswith('data:'):
                                continue
                            raw = line[5:].strip()
                            if raw == '[DONE]':
                                break
                            try:
                                d = json.loads(raw)
                                chunk = d['choices'][0]['delta'].get('content', '')
                                if chunk:
                                    text += chunk
                                    yield f'data: {json.dumps({"type": "chunk", "side": side, "text": chunk, "battle_id": battle_id})}\n\n'
                            except (KeyError, TypeError, ValueError, json.JSONDecodeError, OSError, AttributeError, RuntimeError):
                                pass
            except Exception as ex:
                text = f'[Error: {ex}]'
                yield f'data: {json.dumps({"type": "chunk", "side": side, "text": text, "battle_id": battle_id})}\n\n'

            lat = int((time.perf_counter() - t0) * 1000)
            toks = len(text.split())

            if side == 'a':
                resp_a = text
                lat_a = lat
                tok_a = toks
            else:
                resp_b = text
                lat_b = lat
                tok_b = toks

            yield f'data: {json.dumps({"type": "model_done", "side": side, "latency_ms": lat, "tokens": toks, "battle_id": battle_id})}\n\n'

        # Run both models in parallel
        async def _combined():
            gen_a = _run_model(model_a, model_a_full, 'a')
            gen_b = _run_model(model_b, model_b_full, 'b')
            # Interleave both generators
            queue: asyncio.Queue = asyncio.Queue()

            async def _drain(gen, q):
                async for item in gen:
                    await q.put(item)
                await q.put(None)

            t1 = asyncio.create_task(_drain(gen_a, queue))
            t2 = asyncio.create_task(_drain(gen_b, queue))
            done_count = 0
            while done_count < 2:
                item = await queue.get()
                if item is None:
                    done_count += 1
                else:
                    yield item
            await asyncio.gather(t1, t2, return_exceptions=True)

        async for event in _combined():
            yield event

        # Update DB with responses
        from ..services.memory_db import get_conn as _gc

        c2 = _gc()
        c2.execute(
            """UPDATE arena_battles SET response_a=?,response_b=?,latency_a=?,latency_b=?,tokens_a=?,tokens_b=?
                      WHERE id=?""",
            (resp_a[:4000], resp_b[:4000], lat_a, lat_b, tok_a, tok_b, battle_id),
        )
        c2.commit()
        c2.close()

        yield f'data: {json.dumps({"type": "battle_ready", "battle_id": battle_id, "ready_to_vote": True})}\n\n'

    return StreamingResponse(
        _stream(), media_type='text/event-stream', headers={'Cache-Control': 'no-cache', 'X-Accel-Buffering': 'no'}
    )


@router.post('/battle/{battle_id}/vote')
async def vote(battle_id: str, req: Request):
    """Cast a vote for the winner of a battle."""
    try:
        body = await req.json()
    except (json.JSONDecodeError, TypeError, ValueError):
        body = {}
    winner = body.get('winner', '')  # "a" | "b" | "tie"
    reason = body.get('reason', '')[:500]

    if winner not in ('a', 'b', 'tie'):
        return {'ok': False, 'error': "winner must be 'a', 'b', or 'tie'"}

    from ..services.memory_db import get_conn

    con = get_conn()
    try:
        battle = con.execute('SELECT * FROM arena_battles WHERE id=?', (battle_id,)).fetchone()
        if not battle:
            return {'ok': False, 'error': 'Battle not found'}
        b = dict(battle)
        if b.get('winner'):
            return {'ok': False, 'error': 'Already voted'}

        con.execute('UPDATE arena_battles SET winner=?,vote_reason=? WHERE id=?', (winner, reason, battle_id))
        con.commit()
    finally:
        con.close()

    # Update ELO
    if winner == 'a':
        _update_elo(b['model_a'], b['model_b'])
    elif winner == 'b':
        _update_elo(b['model_b'], b['model_a'])
    else:
        # Tie: both get 0.5
        from ..services.memory_db import get_conn as _gc

        c2 = _gc()
        c2.execute('UPDATE arena_leaderboard SET ties=ties+1,battles=battles+1 WHERE model=?', (b['model_a'],))
        c2.execute('UPDATE arena_leaderboard SET ties=ties+1,battles=battles+1 WHERE model=?', (b['model_b'],))
        c2.commit()
        c2.close()

    return {'ok': True, 'winner': winner, 'battle_id': battle_id}


@router.get('/leaderboard')
def leaderboard(limit: int = 20):
    """Global ELO leaderboard."""
    from ..services.memory_db import get_conn

    con = get_conn()
    try:
        rows = con.execute(
            'SELECT * FROM arena_leaderboard WHERE battles>0 ORDER BY elo DESC LIMIT ?', (min(limit, 50),)
        ).fetchall()
    finally:
        con.close()
    lb = []
    for i, r in enumerate(rows, 1):
        d = dict(r)
        d['rank'] = i
        d['win_rate'] = round(d['wins'] / max(d['battles'], 1) * 100, 1)
        lb.append(d)
    return {'leaderboard': lb, 'total_models': len(lb)}


@router.get('/battles')
def list_battles(limit: int = 20, voted_only: bool = False):
    """Retrieve and return list battles."""
    from ..services.memory_db import get_conn

    con = get_conn()
    try:
        sql = 'SELECT * FROM arena_battles'
        params = []
        if voted_only:
            sql += " WHERE winner != ''"
        sql += ' ORDER BY created_at DESC LIMIT ?'
        params.append(min(limit, 100))
        rows = con.execute(sql, params).fetchall()
    finally:
        con.close()
    return {'battles': [dict(r) for r in rows], 'count': len(rows)}


@router.get('/battles/{battle_id}')
def get_battle(battle_id: str):
    """Retrieve and return get battle."""
    from ..services.memory_db import get_conn

    con = get_conn()
    try:
        row = con.execute('SELECT * FROM arena_battles WHERE id=?', (battle_id,)).fetchone()
    finally:
        con.close()
    if not row:
        return {'ok': False, 'error': 'Not found'}
    return dict(row)


@router.get('/stats')
def arena_stats():
    """Execute or process arena stats operation."""
    from ..services.memory_db import get_conn

    con = get_conn()
    try:
        total = con.execute('SELECT COUNT(*) FROM arena_battles').fetchone()[0]
        voted = con.execute("SELECT COUNT(*) FROM arena_battles WHERE winner!=''").fetchone()[0]
        top_model = con.execute(
            'SELECT model FROM arena_leaderboard WHERE battles>0 ORDER BY elo DESC LIMIT 1'
        ).fetchone()
        most_used = con.execute(
            'SELECT model_a as m,COUNT(*) as c FROM arena_battles GROUP BY model_a ORDER BY c DESC LIMIT 1'
        ).fetchone()
    finally:
        con.close()
    return {
        'total_battles': total,
        'voted_battles': voted,
        'unvoted': total - voted,
        'top_model': top_model['model'] if top_model else None,
        'most_used': most_used['m'] if most_used else None,
    }


@router.post('/auto-judge')
async def auto_judge_battle(req: Request):
    """Use a third model to auto-judge a battle (for automated leaderboard building)."""
    try:
        body = await req.json()
    except (json.JSONDecodeError, TypeError, ValueError):
        body = {}
    battle_id = body.get('battle_id', '')
    from ..services.memory_db import get_conn

    con = get_conn()
    try:
        battle = con.execute('SELECT * FROM arena_battles WHERE id=?', (battle_id,)).fetchone()
    finally:
        con.close()
    if not battle:
        return {'ok': False, 'error': 'Battle not found'}
    b = dict(battle)

    from ..services import llm as llm_svc

    judge_prompt = f"""You are an impartial AI judge. Compare these two responses to the same prompt.

PROMPT: {b['prompt'][:500]}

RESPONSE A ({b['model_a']}):
{b['response_a'][:1000]}

RESPONSE B ({b['model_b']}):
{b['response_b'][:1000]}

Judge which response is better based on: accuracy, completeness, clarity, helpfulness.
Return JSON: {{"winner": "a"|"b"|"tie", "reason": "brief explanation", "scores": {{"a": 1-10, "b": 1-10}}}}"""

    result = await llm_svc.complete(
        [{'role': 'user', 'content': judge_prompt}],
        agent_id='judge',
        max_tokens=300,
        temperature=0.1,
        inject_steering=False,
    )
    text = result.get('text', '')

    import re

    m = re.search(r'\{.*\}', text, re.DOTALL)
    if m:
        try:
            j = json.loads(m.group(0))
            winner = j.get('winner', 'tie')
            reason = j.get('reason', 'Auto-judged')
            # Apply vote
            from ..services.memory_db import get_conn as _gc

            c2 = _gc()
            c2.execute(
                'UPDATE arena_battles SET winner=?,vote_reason=? WHERE id=?', (winner, f'[AUTO] {reason}', battle_id)
            )
            c2.commit()
            c2.close()
            if winner in ('a', 'b'):
                _update_elo(b[f'model_{winner}'], b['model_a' if winner == 'b' else 'model_b'])
            return {'ok': True, 'winner': winner, 'reason': reason, 'scores': j.get('scores', {})}
        except Exception as ex:
            return {'ok': False, 'error': f'Parse error: {ex}'}
    return {'ok': False, 'error': 'Could not parse judge response'}
