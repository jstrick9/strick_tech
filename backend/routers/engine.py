"""
Agentic OS — Agent Execution Engine API
Exposes the execution engine, loop engineering, and harness engineering
via REST endpoints for the frontend and other services.
"""
from __future__ import annotations

import json
import logging
import uuid

from fastapi import APIRouter, Request
from fastapi.responses import JSONResponse

from ..services import llm
from ..services.agent_engine import (
    HarnessConfig,
    LoopConfig,
    RetryConfig,
    RetryStrategy,
    get_engine,
    get_harness_engine,
    get_loop_engine,
)

router = APIRouter(prefix='/api/engine', tags=['engine'])
log = logging.getLogger('agentic.engine.api')


# ── Execution Engine ──────────────────────────────────────────────────────

@router.get('/status')
def engine_status():
    """Get execution engine status including circuit breakers and active traces."""
    engine = get_engine()
    return {
        'ok': True,
        'circuit_breakers': engine.get_all_circuit_breakers(),
        'active_traces': len(engine.active_traces),
    }


@router.get('/traces')
def list_traces(limit: int = 50):
    """List recent execution traces."""
    engine = get_engine()
    return {'ok': True, 'traces': engine.list_traces(limit)}


@router.get('/traces/{trace_id}')
def get_trace(trace_id: str):
    """Get a specific execution trace."""
    engine = get_engine()
    trace = engine.get_trace(trace_id)
    if not trace:
        return JSONResponse({'ok': False, 'error': 'Trace not found'}, status_code=404)
    return {'ok': True, 'trace': trace}


@router.post('/execute')
async def execute_with_retry(req: Request):
    """Execute an LLM call with retry, circuit breaker, and tracing.

    Body: {prompt, agent_id, model, max_retries, temperature, max_tokens}
    """
    try:
        body = await req.json()
    except Exception:
        return JSONResponse({'ok': False, 'error': 'Invalid JSON'}, status_code=400)

    prompt = body.get('prompt', '')
    agent_id = body.get('agent_id', 'default')
    model = body.get('model', '')
    max_retries = min(body.get('max_retries', 3), 10)
    temperature = body.get('temperature', 0.7)
    max_tokens = body.get('max_tokens', 2048)

    if not prompt:
        return JSONResponse({'ok': False, 'error': 'prompt required'}, status_code=400)

    engine = get_engine()
    retry_config = RetryConfig(
        strategy=RetryStrategy.EXPONENTIAL,
        max_retries=max_retries,
        base_delay_ms=1000,
        max_delay_ms=15000,
    )

    from ..services.agent_engine import ExecutionStrategy, ExecutionTrace
    trace = ExecutionTrace(
        trace_id=f"exec_{uuid.uuid4().hex[:8]}",
        agent_id=agent_id,
        strategy=ExecutionStrategy.SEQUENTIAL,
        started_at=__import__('time').time(),
    )

    result = await engine.execute_with_retry(
        llm.complete,
        messages=[{'role': 'user', 'content': prompt}],
        agent_id=agent_id,
        model=model,
        temperature=temperature,
        max_tokens=max_tokens,
        retry_config=retry_config,
        circuit_breaker_key='openrouter' if not model else '',
        trace=trace,
        step_name=f'llm_call:{agent_id}',
    )

    trace.completed_at = __import__('time').time()
    trace.status = 'completed' if result.get('ok') else 'failed'
    engine.active_traces[trace.trace_id] = trace

    return {
        'ok': result.get('ok', False),
        'result': result.get('result'),
        'attempts': result.get('attempts', 0),
        'circuit_breaker': result.get('circuit_breaker'),
        'trace_id': trace.trace_id,
        'duration_ms': round(trace.duration_ms, 1),
    }


@router.post('/fan-out')
async def fan_out(req: Request):
    """Fan-out: send a prompt to multiple agents in parallel.

    Body: {prompt, agents: [{id, model, system_prompt}], judge: bool}
    """
    try:
        body = await req.json()
    except Exception:
        return JSONResponse({'ok': False, 'error': 'Invalid JSON'}, status_code=400)

    prompt = body.get('prompt', '')
    agents = body.get('agents', [])
    if not prompt or not agents:
        return JSONResponse({'ok': False, 'error': 'prompt and agents required'}, status_code=400)

    engine = get_engine()

    async def agent_fn(agent_config, p):
        return await llm.complete(
            messages=[{'role': 'user', 'content': p}],
            agent_id=agent_config.get('id', 'default'),
            model=agent_config.get('model', ''),
        )

    result = await engine.execute_fan_out(
        prompt=prompt,
        agents=agents,
        llm_fn=agent_fn,
    )

    return result


@router.post('/map-reduce')
async def map_reduce(req: Request):
    """Map-reduce: process items in parallel then combine results.

    Body: {items: [...], map_prompt, reduce_prompt}
    """
    try:
        body = await req.json()
    except Exception:
        return JSONResponse({'ok': False, 'error': 'Invalid JSON'}, status_code=400)

    items = body.get('items', [])
    map_prompt = body.get('map_prompt', '')
    reduce_prompt = body.get('reduce_prompt', '')

    if not items or not map_prompt:
        return JSONResponse({'ok': False, 'error': 'items and map_prompt required'}, status_code=400)

    engine = get_engine()

    async def map_fn(item):
        return await llm.complete(
            messages=[{'role': 'user', 'content': f'{map_prompt}\n\nItem: {json.dumps(item)}'}],
        )

    async def reduce_fn(results):
        return await llm.complete(
            messages=[{'role': 'user', 'content': f'{reduce_prompt}\n\nResults: {json.dumps(results, default=str)[:4000]}'}],
        )

    return await engine.execute_map_reduce(items, map_fn, reduce_fn)


# ── Loop Engineering ──────────────────────────────────────────────────────

@router.get('/loops')
def list_engine_loops():
    """List all engine-managed loops with health metrics."""
    loop_engine = get_loop_engine()
    return {'ok': True, 'loops': loop_engine.list_loops()}


@router.post('/loops')
async def create_engine_loop(req: Request):
    """Create an advanced autonomous loop with adaptive intervals and backoff.

    Body: {name, prompt, interval_s, adaptive, agent_id, backoff_on_error}
    """
    try:
        body = await req.json()
    except Exception:
        return JSONResponse({'ok': False, 'error': 'Invalid JSON'}, status_code=400)

    name = body.get('name', 'Untitled Loop')
    prompt = body.get('prompt', '')
    interval_s = body.get('interval_s', 60)
    adaptive = body.get('adaptive', False)
    agent_id = body.get('agent_id', 'default')
    backoff = body.get('backoff_on_error', True)

    if not prompt:
        return JSONResponse({'ok': False, 'error': 'prompt required'}, status_code=400)

    loop_id = f"eloop_{uuid.uuid4().hex[:8]}"
    loop_engine = get_loop_engine()

    config = LoopConfig(
        interval_s=max(5, min(interval_s, 86400)),
        adaptive=adaptive,
        backoff_on_error=backoff,
    )

    async def loop_fn():
        return await llm.complete(
            messages=[{'role': 'user', 'content': prompt}],
            agent_id=agent_id,
        )

    return loop_engine.create_loop(loop_id, name, loop_fn, config, agent_id)


@router.post('/loops/{loop_id}/run')
async def run_engine_loop(loop_id: str):
    """Run a single iteration of an engine loop."""
    loop_engine = get_loop_engine()
    return await loop_engine.run_loop_iteration(loop_id)


@router.get('/loops/{loop_id}')
def get_engine_loop(loop_id: str):
    """Get detailed loop status including health metrics."""
    loop_engine = get_loop_engine()
    status = loop_engine.get_loop_status(loop_id)
    if not status:
        return JSONResponse({'ok': False, 'error': 'Loop not found'}, status_code=404)
    return {'ok': True, 'loop': status}


# ── Harness Engineering ───────────────────────────────────────────────────

@router.post('/harness/test')
async def run_test_harness(req: Request):
    """Run a test harness against an agent.

    Body: {harness_id, test_cases: [{id, input, expected, assertions}], pass_threshold}
    """
    try:
        body = await req.json()
    except Exception:
        return JSONResponse({'ok': False, 'error': 'Invalid JSON'}, status_code=400)

    harness_id = body.get('harness_id', f"test_{uuid.uuid4().hex[:6]}")
    test_cases = body.get('test_cases', [])
    pass_threshold = body.get('pass_threshold', 0.8)
    timeout_per_case = body.get('timeout_per_case_s', 30)

    if not test_cases:
        return JSONResponse({'ok': False, 'error': 'test_cases required'}, status_code=400)

    config = HarnessConfig(
        name=harness_id,
        test_cases=test_cases,
        pass_threshold=pass_threshold,
        timeout_per_case_s=timeout_per_case,
    )

    async def agent_fn(tc):
        return await llm.complete(
            messages=[{'role': 'user', 'content': tc.get('input', '')}],
            agent_id=tc.get('agent_id', 'default'),
        )

    harness = get_harness_engine()
    return await harness.run_test_harness(harness_id, agent_fn, test_cases, config)


@router.post('/harness/benchmark')
async def run_benchmark_harness(req: Request):
    """Run a benchmark harness to measure agent performance.

    Body: {harness_id, prompt, iterations, concurrency, agent_id, model}
    """
    try:
        body = await req.json()
    except Exception:
        return JSONResponse({'ok': False, 'error': 'Invalid JSON'}, status_code=400)

    harness_id = body.get('harness_id', f"bench_{uuid.uuid4().hex[:6]}")
    prompt = body.get('prompt', 'Hello')
    iterations = min(body.get('iterations', 10), 200)
    concurrency = min(body.get('concurrency', 1), 20)
    agent_id = body.get('agent_id', 'default')
    model = body.get('model', '')

    async def agent_fn():
        return await llm.complete(
            messages=[{'role': 'user', 'content': prompt}],
            agent_id=agent_id,
            model=model,
        )

    harness = get_harness_engine()
    return await harness.run_benchmark_harness(harness_id, agent_fn, iterations, concurrency)


@router.get('/harness/{harness_id}/regression')
def harness_regression(harness_id: str):
    """Get regression report for a harness."""
    harness = get_harness_engine()
    return harness.get_regression_report(harness_id)


# ── Circuit Breakers ──────────────────────────────────────────────────────

@router.get('/circuit-breakers')
def list_circuit_breakers():
    """List all circuit breaker states."""
    engine = get_engine()
    return {'ok': True, 'circuit_breakers': engine.get_all_circuit_breakers()}


@router.post('/circuit-breakers/{provider}/reset')
def reset_circuit_breaker(provider: str):
    """Reset a circuit breaker to closed state."""
    engine = get_engine()
    cb = engine.get_circuit_breaker(provider)
    from ..services.agent_engine import CircuitState
    cb.state = CircuitState.CLOSED
    cb.failure_count = 0
    cb.success_count = 0
    return {'ok': True, 'provider': provider, 'state': 'closed'}
