"""
Agentic OS — LLM Service
Supports: OpenRouter (primary), Ollama (local), direct Anthropic/OpenAI fallbacks.
All calls are async. Streaming via async generators.
"""

from __future__ import annotations

import contextlib

import asyncio
import json
import logging
import os
import time
from collections.abc import AsyncGenerator

import httpx

log = logging.getLogger('agentic.llm')

# ── Model registry ─────────────────────────────────────────────────────────────
OPENROUTER_MODELS = {
    # id used in agents config → openrouter model string
    'claude': 'anthropic/claude-3.5-sonnet',
    'claude-opus': 'anthropic/claude-opus-4',
    'gpt4o': 'openai/gpt-4o',
    'gpt4o-mini': 'openai/gpt-4o-mini',
    'gemini': 'google/gemini-2.5-pro',
    'gemini-flash': 'google/gemini-2.0-flash-exp:free',
    'grok': 'x-ai/grok-3',
    'grok-mini': 'x-ai/grok-3-mini',
    'hermes': 'nousresearch/hermes-3-llama-3.1-405b',
    'llama': 'meta-llama/llama-3.3-70b-instruct:free',
    'mistral': 'mistralai/mistral-small-3.2-24b-instruct:free',
    'qwen': 'qwen/qwen3-235b-a22b:free',
    # generic fallback
    'default': 'anthropic/claude-3.5-sonnet',
    'free': 'google/gemini-2.0-flash-exp:free',
}

OPENROUTER_BASE = 'https://openrouter.ai/api/v1'
OLLAMA_BASE = os.getenv('OLLAMA_BASE_URL', 'http://localhost:11434')


def _or_key() -> str:
    return os.getenv('OPENROUTER_API_KEY', '')


def _or_headers() -> dict:
    return {
        'Authorization': f'Bearer {_or_key()}',
        'HTTP-Referer': f'http://localhost:{int(__import__("os").getenv("AGENTIC_OS_PORT", "8787"))}',
        'X-Title': 'Agentic OS',
        'Content-Type': 'application/json',
    }


def resolve_model(agent_id: str, custom_model: str = '') -> tuple[str, str]:
    """Returns (provider, model_string). custom_model explicitly chosen by user overrides agent defaults."""
    target = (custom_model or '').strip()
    if target:
        if target.startswith('ollama:'):
            return 'ollama', target.replace('ollama:', '', 1).strip()
        if target.startswith('custom_url:'):
            return 'custom_url', target.replace('custom_url:', '', 1).strip()
        if target.lower() in OPENROUTER_MODELS:
            return 'openrouter', OPENROUTER_MODELS[target.lower()]
        if '/' in target:
            return 'openrouter', target
        # Any unslashed custom model string (e.g. 'local', 'llama3.2:3b', 'mistral:7b', 'deepseek-r1:8b', 'qwen2.5:7b') routes to local Ollama!
        return 'ollama', target
    model = OPENROUTER_MODELS.get(agent_id.lower(), OPENROUTER_MODELS['default'])
    return 'openrouter', model


# ── Non-streaming completion ────────────────────────────────────────────────────
def _inject_steering(messages: list[dict]) -> list[dict]:
    """Prepend steering context to the system prompt if steering files are enabled."""
    try:
        from ..routers.steering import compile_steering_context

        ctx = compile_steering_context(max_chars=4000)
        if not ctx:
            return messages
        msgs = list(messages)
        # Find existing system message or prepend one
        for i, m in enumerate(msgs):
            if m.get('role') == 'system':
                msgs[i] = {**m, 'content': ctx + '\n\n---\n\n' + m['content']}
                return msgs
        return [{'role': 'system', 'content': ctx}] + msgs
    except (KeyError, TypeError, ValueError, json.JSONDecodeError, OSError, AttributeError, RuntimeError):
        return messages


async def complete(
    messages: list[dict],
    agent_id: str = 'default',
    model: str = '',
    temperature: float = 0.7,
    max_tokens: int = 2048,
    timeout: float = 60.0,
    inject_steering: bool = True,
) -> dict:
    """Single-shot completion. Returns {text, tokens, cost, model, latency_ms}"""
    if inject_steering and agent_id not in ('steering', 'gitai', 'bugbot', 'specs'):
        messages = _inject_steering(messages)
    t0 = time.time()
    provider, model_str = resolve_model(agent_id, model)

    if provider == 'ollama':
        return await _ollama_complete(messages, model_str, temperature, max_tokens, timeout)

    key = _or_key()
    if not key:
        try:
            base_check = os.getenv('OLLAMA_BASE_URL', OLLAMA_BASE).rstrip('/').removesuffix('/v1').rstrip('/')
            async with httpx.AsyncClient(timeout=1.5) as client:
                t_resp = await client.get(f'{base_check}/api/tags')
                if t_resp.status_code == 200:
                    models_data = t_resp.json().get('models', [])
                    if models_data:
                        fb_model = models_data[0].get('name', 'llama3.2:3b')
                        return await _ollama_complete(messages, fb_model, temperature, max_tokens, timeout)
        except Exception:
            pass
        return _stub_reply(messages, agent_id, model_str)

    payload = {
        'model': model_str,
        'messages': messages,
        'temperature': temperature,
        'max_tokens': max_tokens,
    }
    try:
        async with httpx.AsyncClient(timeout=timeout) as client:
            resp = await client.post(
                f'{OPENROUTER_BASE}/chat/completions',
                headers=_or_headers(),
                json=payload,
            )
            resp.raise_for_status()
            data = resp.json()
            text = data['choices'][0]['message']['content']
            usage = data.get('usage', {})
            latency = round((time.time() - t0) * 1000)
            return {
                'text': text,
                'tokens': usage.get('total_tokens', 0),
                'prompt_tokens': usage.get('prompt_tokens', 0),
                'completion_tokens': usage.get('completion_tokens', 0),
                'cost': _estimate_cost(model_str, usage),
                'model': model_str,
                'provider': 'openrouter',
                'latency_ms': latency,
                'ok': True,
            }
    except httpx.HTTPStatusError as e:
        log.error('OpenRouter HTTP error: %s %s', e.response.status_code, e.response.text[:300])
        try:
            fallback_model = os.getenv('OLLAMA_FALLBACK_MODEL', 'llama3.1:8b')
            res = await _ollama_complete(messages, fallback_model, temperature, max_tokens, timeout)
            if res.get('ok'):
                res['telemetry_note'] = f'OpenRouter fallback (HTTP {e.response.status_code}) -> Local Ollama ({fallback_model})'
                return res
        except Exception as fe:
            log.error('Local Ollama fallback also failed: %s', fe)
        return {'text': f'[LLM error {e.response.status_code}]: {e.response.text[:200]}', 'ok': False, 'error': str(e)}
    except Exception as e:
        log.error('LLM complete error: %s', e)
        try:
            fallback_model = os.getenv('OLLAMA_FALLBACK_MODEL', 'llama3.1:8b')
            res = await _ollama_complete(messages, fallback_model, temperature, max_tokens, timeout)
            if res.get('ok'):
                res['telemetry_note'] = f'OpenRouter fallback ({e}) -> Local Ollama ({fallback_model})'
                return res
        except Exception as fe:
            log.error('Local Ollama fallback also failed: %s', fe)
        return {'text': f'[LLM error]: {e}', 'ok': False, 'error': str(e)}


# ── Streaming completion ────────────────────────────────────────────────────────
async def stream(
    messages: list[dict],
    agent_id: str = 'default',
    model: str = '',
    temperature: float = 0.7,
    max_tokens: int = 4096,
    timeout: float = 120.0,
    inject_steering: bool = True,
) -> AsyncGenerator[str, None]:
    """Yields SSE-formatted chunks: 'data: {json}\n\n'"""
    if inject_steering and agent_id not in ('steering', 'gitai', 'bugbot', 'specs'):
        messages = _inject_steering(messages)
    provider, model_str = resolve_model(agent_id, model)

    if provider == 'ollama':
        async for chunk in _ollama_stream(messages, model_str, temperature, max_tokens, timeout):
            yield chunk
        return

    key = _or_key()
    if not key:
        try:
            base_check = os.getenv('OLLAMA_BASE_URL', OLLAMA_BASE).rstrip('/').removesuffix('/v1').rstrip('/')
            async with httpx.AsyncClient(timeout=1.5) as client:
                t_resp = await client.get(f'{base_check}/api/tags')
                if t_resp.status_code == 200:
                    models_data = t_resp.json().get('models', [])
                    if models_data:
                        fb_model = models_data[0].get('name', 'llama3.2:3b')
                        async for chunk in _ollama_stream(messages, fb_model, temperature, max_tokens, timeout):
                            yield chunk
                        return
        except Exception:
            pass
        # stream a helpful stub
        stub = _stub_reply(messages, agent_id, model_str)['text']
        for word in stub.split(' '):
            yield f'data: {json.dumps({"delta": word + " ", "done": False})}\n\n'
            await asyncio.sleep(0.02)
        yield f'data: {json.dumps({"delta": "", "done": True, "model": model_str})}\n\n'
        return

    payload = {
        'model': model_str,
        'messages': messages,
        'temperature': temperature,
        'max_tokens': max_tokens,
        'stream': True,
    }
    try:
        async with (
            httpx.AsyncClient(timeout=timeout) as client,
            client.stream(
                'POST',
                f'{OPENROUTER_BASE}/chat/completions',
                headers=_or_headers(),
                json=payload,
            ) as resp,
        ):
            resp.raise_for_status()
            async for line in resp.aiter_lines():
                if not line or not line.startswith('data:'):
                    continue
                raw = line[5:].strip()
                if raw == '[DONE]':
                    yield f'data: {json.dumps({"delta": "", "done": True, "model": model_str})}\n\n'
                    break
                try:
                    chunk = json.loads(raw)
                    delta = chunk['choices'][0]['delta'].get('content', '')
                    if delta:
                        yield f'data: {json.dumps({"delta": delta, "done": False})}\n\n'
                except (KeyError, TypeError, ValueError, json.JSONDecodeError, OSError, AttributeError, RuntimeError):
                    pass
    except Exception as e:
        log.error('LLM stream error: %s', e)
        try:
            fallback_model = os.getenv('OLLAMA_FALLBACK_MODEL', 'llama3.1:8b')
            yield f'data: {json.dumps({"delta": f" [OpenRouter disconnected ({e}). Auto-falling back to local {fallback_model}...]\n\n", "done": False})}\n\n'
            async for chunk in _ollama_stream(messages, fallback_model, temperature, max_tokens, timeout):
                yield chunk
            return
        except Exception as fe:
            log.error('Local Ollama fallback stream also failed: %s', fe)
        yield f'data: {json.dumps({"delta": f"[stream error]: {e}", "done": True, "error": str(e)})}\n\n'


# ── Ollama ─────────────────────────────────────────────────────────────────────
async def _ollama_complete(messages, model, temperature, max_tokens, timeout) -> dict:
    t0 = time.time()
    base_clean = os.getenv('OLLAMA_BASE_URL', OLLAMA_BASE).rstrip('/').removesuffix('/v1').rstrip('/')
    clean_model = model.replace('ollama:', '', 1).strip()
    candidates = [base_clean]
    if 'localhost' in base_clean:
        candidates.append(base_clean.replace('localhost', '127.0.0.1'))
    elif '127.0.0.1' in base_clean:
        candidates.append(base_clean.replace('127.0.0.1', 'localhost'))

    prompt_lines = []
    for m in messages:
        role = m.get('role', 'user')
        content = m.get('content', '')
        prompt_lines.append(f'[{role.upper()}]: {content}')
    prompt_lines.append('[ASSISTANT]:')
    formatted_prompt = '\n\n'.join(prompt_lines)

    last_error = None

    for base in candidates:
        payload_chat = {
            'model': clean_model,
            'messages': messages,
            'stream': False,
            'options': {'temperature': temperature, 'num_predict': max_tokens},
        }
        try:
            async with httpx.AsyncClient(timeout=timeout) as client:
                resp = await client.post(f'{base}/api/chat', json=payload_chat)
                if resp.status_code == 200:
                    data = resp.json()
                    text = data.get('message', {}).get('content', '')
                    return {
                        'text': text,
                        'tokens': data.get('eval_count', 0),
                        'cost': 0.0,
                        'model': clean_model,
                        'provider': 'ollama',
                        'latency_ms': round((time.time() - t0) * 1000),
                        'ok': True,
                    }
                last_error = f'HTTP {resp.status_code} on {base}/api/chat'
        except Exception as e:
            last_error = str(e)

        payload_gen = {
            'model': clean_model,
            'prompt': formatted_prompt,
            'stream': False,
            'options': {'temperature': temperature, 'num_predict': max_tokens},
        }
        try:
            async with httpx.AsyncClient(timeout=timeout) as client:
                resp_gen = await client.post(f'{base}/api/generate', json=payload_gen)
                if resp_gen.status_code == 200:
                    data_gen = resp_gen.json()
                    text_gen = data_gen.get('response', '')
                    return {
                        'text': text_gen,
                        'tokens': data_gen.get('eval_count', 0),
                        'cost': 0.0,
                        'model': clean_model,
                        'provider': 'ollama',
                        'latency_ms': round((time.time() - t0) * 1000),
                        'ok': True,
                    }
                last_error = f'HTTP {resp_gen.status_code} on {base}/api/generate'
        except Exception as e:
            last_error = str(e)

        payload_oai = {
            'model': clean_model,
            'messages': messages,
            'stream': False,
            'temperature': temperature,
            'max_tokens': max_tokens,
        }
        try:
            async with httpx.AsyncClient(timeout=timeout) as client:
                resp_oai = await client.post(f'{base}/v1/chat/completions', json=payload_oai)
                if resp_oai.status_code == 200:
                    data_oai = resp_oai.json()
                    text_oai = data_oai.get('choices', [{}])[0].get('message', {}).get('content', '')
                    return {
                        'text': text_oai,
                        'tokens': data_oai.get('usage', {}).get('total_tokens', 0),
                        'cost': 0.0,
                        'model': clean_model,
                        'provider': 'ollama',
                        'latency_ms': round((time.time() - t0) * 1000),
                        'ok': True,
                    }
                last_error = f'HTTP {resp_oai.status_code} on {base}/v1/chat/completions'
        except Exception as e:
            last_error = str(e)

        try:
            async with httpx.AsyncClient(timeout=4.0) as client:
                installed = []
                try:
                    t_resp = await client.get(f'{base}/api/tags')
                    if t_resp.status_code == 200:
                        installed = [m.get('name') for m in t_resp.json().get('models', []) if m.get('name')]
                except Exception:
                    pass
                if not installed:
                    try:
                        v_resp = await client.get(f'{base}/v1/models')
                        if v_resp.status_code == 200:
                            installed = [m.get('id', m.get('name')) for m in v_resp.json().get('data', []) if m.get('id') or m.get('name')]
                    except Exception:
                        pass
                if installed:
                    fallback_local = next((m for m in installed if clean_model.split(':')[0] in m), installed[0])
                    payload_chat['model'] = fallback_local
                    try:
                        resp_fb = await client.post(f'{base}/api/chat', json=payload_chat)
                        if resp_fb.status_code == 200:
                            data_fb = resp_fb.json()
                            return {
                                'text': data_fb.get('message', {}).get('content', ''),
                                'tokens': data_fb.get('eval_count', 0),
                                'cost': 0.0,
                                'model': fallback_local,
                                'provider': 'ollama',
                                'latency_ms': round((time.time() - t0) * 1000),
                                'ok': True,
                            }
                    except Exception:
                        pass
                    payload_gen['model'] = fallback_local
                    try:
                        resp_gen_fb = await client.post(f'{base}/api/generate', json=payload_gen)
                        if resp_gen_fb.status_code == 200:
                            data_gen_fb = resp_gen_fb.json()
                            return {
                                'text': data_gen_fb.get('response', ''),
                                'tokens': data_gen_fb.get('eval_count', 0),
                                'cost': 0.0,
                                'model': fallback_local,
                                'provider': 'ollama',
                                'latency_ms': round((time.time() - t0) * 1000),
                                'ok': True,
                            }
                    except Exception:
                        pass
                    payload_oai['model'] = fallback_local
                    try:
                        resp_oai_fb = await client.post(f'{base}/v1/chat/completions', json=payload_oai)
                        if resp_oai_fb.status_code == 200:
                            data_oai_fb = resp_oai_fb.json()
                            return {
                                'text': data_oai_fb.get('choices', [{}])[0].get('message', {}).get('content', ''),
                                'tokens': data_oai_fb.get('usage', {}).get('total_tokens', 0),
                                'cost': 0.0,
                                'model': fallback_local,
                                'provider': 'ollama',
                                'latency_ms': round((time.time() - t0) * 1000),
                                'ok': True,
                            }
                    except Exception:
                        pass
        except Exception:
            pass

    return {
        'text': f'[Ollama complete error — could not connect or generate on `{base_clean}` ({last_error}). Verify Ollama is running and model `{clean_model}` is installed via `ollama list`]',
        'ok': False,
        'error': str(last_error),
        'provider': 'ollama',
    }


async def _ollama_stream(messages, model, temperature, max_tokens, timeout) -> AsyncGenerator[str, None]:
    base_clean = os.getenv('OLLAMA_BASE_URL', OLLAMA_BASE).rstrip('/').removesuffix('/v1').rstrip('/')
    clean_model = model.replace('ollama:', '', 1).strip()
    candidates = [base_clean]
    if 'localhost' in base_clean:
        candidates.append(base_clean.replace('localhost', '127.0.0.1'))
    elif '127.0.0.1' in base_clean:
        candidates.append(base_clean.replace('127.0.0.1', 'localhost'))

    prompt_lines = []
    for m in messages:
        role = m.get('role', 'user')
        content = m.get('content', '')
        prompt_lines.append(f'[{role.upper()}]: {content}')
    prompt_lines.append('[ASSISTANT]:')
    formatted_prompt = '\n\n'.join(prompt_lines)

    last_error = None

    for base in candidates:
        payload_chat = {
            'model': clean_model,
            'messages': messages,
            'stream': True,
            'options': {'temperature': temperature, 'num_predict': max_tokens},
        }
        try:
            async with httpx.AsyncClient(timeout=timeout) as client:
                async with client.stream('POST', f'{base}/api/chat', json=payload_chat) as resp:
                    if resp.status_code == 200:
                        async for line in resp.aiter_lines():
                            if not line:
                                continue
                            try:
                                chunk = json.loads(line)
                                delta = chunk.get('message', {}).get('content', '')
                                done = chunk.get('done', False)
                                if delta:
                                    yield f'data: {json.dumps({"delta": delta, "done": False})}\n\n'
                                if done:
                                    yield f'data: {json.dumps({"delta": "", "done": True, "model": clean_model})}\n\n'
                            except Exception:
                                pass
                        return
                    last_error = f'HTTP {resp.status_code} on {base}/api/chat'
        except Exception as e:
            last_error = str(e)

        payload_gen = {
            'model': clean_model,
            'prompt': formatted_prompt,
            'stream': True,
            'options': {'temperature': temperature, 'num_predict': max_tokens},
        }
        try:
            async with httpx.AsyncClient(timeout=timeout) as client:
                async with client.stream('POST', f'{base}/api/generate', json=payload_gen) as resp_gen:
                    if resp_gen.status_code == 200:
                        async for line in resp_gen.aiter_lines():
                            if not line:
                                continue
                            try:
                                chunk = json.loads(line)
                                delta = chunk.get('response', '')
                                done = chunk.get('done', False)
                                if delta:
                                    yield f'data: {json.dumps({"delta": delta, "done": False})}\n\n'
                                if done:
                                    yield f'data: {json.dumps({"delta": "", "done": True, "model": clean_model})}\n\n'
                            except Exception:
                                pass
                        return
                    last_error = f'HTTP {resp_gen.status_code} on {base}/api/generate'
        except Exception as e:
            last_error = str(e)

        payload_oai = {
            'model': clean_model,
            'messages': messages,
            'stream': True,
            'temperature': temperature,
            'max_tokens': max_tokens,
        }
        try:
            async with httpx.AsyncClient(timeout=timeout) as client:
                async with client.stream('POST', f'{base}/v1/chat/completions', json=payload_oai) as resp_oai:
                    if resp_oai.status_code == 200:
                        async for line in resp_oai.aiter_lines():
                            if not line.startswith('data: '):
                                continue
                            raw = line[6:].strip()
                            if raw == '[DONE]':
                                yield f'data: {json.dumps({"delta": "", "done": True, "model": clean_model})}\n\n'
                                break
                            try:
                                chunk = json.loads(raw)
                                delta = chunk['choices'][0]['delta'].get('content', '')
                                if delta:
                                    yield f'data: {json.dumps({"delta": delta, "done": False})}\n\n'
                            except Exception:
                                pass
                        return
                    last_error = f'HTTP {resp_oai.status_code} on {base}/v1/chat/completions'
        except Exception as e:
            last_error = str(e)

        try:
            async with httpx.AsyncClient(timeout=4.0) as client:
                installed = []
                try:
                    t_resp = await client.get(f'{base}/api/tags')
                    if t_resp.status_code == 200:
                        installed = [m.get('name') for m in t_resp.json().get('models', []) if m.get('name')]
                except Exception:
                    pass
                if not installed:
                    try:
                        v_resp = await client.get(f'{base}/v1/models')
                        if v_resp.status_code == 200:
                            installed = [m.get('id', m.get('name')) for m in v_resp.json().get('data', []) if m.get('id') or m.get('name')]
                    except Exception:
                        pass
                if installed:
                    fallback_local = next((m for m in installed if clean_model.split(':')[0] in m), installed[0])
                    payload_chat['model'] = fallback_local
                    try:
                        async with client.stream('POST', f'{base}/api/chat', json=payload_chat) as resp_fb:
                            if resp_fb.status_code == 200:
                                async for line in resp_fb.aiter_lines():
                                    if not line:
                                        continue
                                    try:
                                        chunk = json.loads(line)
                                        delta = chunk.get('message', {}).get('content', '')
                                        done = chunk.get('done', False)
                                        if delta:
                                            yield f'data: {json.dumps({"delta": delta, "done": False})}\n\n'
                                        if done:
                                            yield f'data: {json.dumps({"delta": "", "done": True, "model": fallback_local})}\n\n'
                                    except Exception:
                                        pass
                                return
                    except Exception:
                        pass
                    payload_gen['model'] = fallback_local
                    try:
                        async with client.stream('POST', f'{base}/api/generate', json=payload_gen) as resp_gen_fb:
                            if resp_gen_fb.status_code == 200:
                                async for line in resp_gen_fb.aiter_lines():
                                    if not line:
                                        continue
                                    try:
                                        chunk = json.loads(line)
                                        delta = chunk.get('response', '')
                                        done = chunk.get('done', False)
                                        if delta:
                                            yield f'data: {json.dumps({"delta": delta, "done": False})}\n\n'
                                        if done:
                                            yield f'data: {json.dumps({"delta": "", "done": True, "model": fallback_local})}\n\n'
                                    except Exception:
                                        pass
                                return
                    except Exception:
                        pass
                    payload_oai['model'] = fallback_local
                    try:
                        async with client.stream('POST', f'{base}/v1/chat/completions', json=payload_oai) as resp_oai_fb:
                            if resp_oai_fb.status_code == 200:
                                async for line in resp_oai_fb.aiter_lines():
                                    if not line.startswith('data: '):
                                        continue
                                    raw = line[6:].strip()
                                    if raw == '[DONE]':
                                        yield f'data: {json.dumps({"delta": "", "done": True, "model": fallback_local})}\n\n'
                                        break
                                    try:
                                        chunk = json.loads(raw)
                                        delta = chunk['choices'][0]['delta'].get('content', '')
                                        if delta:
                                            yield f'data: {json.dumps({"delta": delta, "done": False})}\n\n'
                                    except Exception:
                                        pass
                                return
                    except Exception:
                        pass
        except Exception:
            pass

    yield f'data: {json.dumps({"delta": f"[Ollama stream error]: Could not stream or connect on `{base_clean}` ({last_error}).\n\nMake sure Ollama (`ollama serve`) is running and model `{clean_model}` is installed via `ollama list`.", "done": True})}\n\n'


# ── Ollama health check ─────────────────────────────────────────────────────────
async def ollama_health() -> dict:
    """Execute or process ollama health operation."""
    base_clean = os.getenv('OLLAMA_BASE_URL', OLLAMA_BASE).rstrip('/').removesuffix('/v1').rstrip('/')
    try:
        async with httpx.AsyncClient(timeout=4.0) as client:
            try:
                resp = await client.get(f'{base_clean}/api/tags')
                if resp.status_code == 404:
                    raise httpx.HTTPStatusError('404 Not Found', request=resp.request, response=resp)
                resp.raise_for_status()
                data = resp.json()
                models = [m['name'] for m in data.get('models', [])]
                return {'running': True, 'models': models, 'url': base_clean}
            except (httpx.HTTPStatusError, httpx.RequestError) as e:
                if isinstance(e, httpx.HTTPStatusError) and e.response.status_code != 404:
                    raise
                resp2 = await client.get(f'{base_clean}/v1/models')
                resp2.raise_for_status()
                data2 = resp2.json()
                models = [m.get('id', m.get('name', 'unknown')) for m in data2.get('data', [])]
                return {'running': True, 'models': models, 'url': base_clean}
    except Exception as e:
        return {'running': False, 'models': [], 'url': base_clean, 'error': str(e)}


# ── Cost estimation ─────────────────────────────────────────────────────────────
_COST_PER_1K = {
    'anthropic/claude-3.5-sonnet': {'in': 0.003, 'out': 0.015},
    'anthropic/claude-opus-4': {'in': 0.015, 'out': 0.075},
    'openai/gpt-4o': {'in': 0.005, 'out': 0.015},
    'openai/gpt-4o-mini': {'in': 0.00015, 'out': 0.0006},
    'google/gemini-2.5-pro': {'in': 0.00125, 'out': 0.005},
}


def _estimate_cost(model: str, usage: dict) -> float:
    rates = _COST_PER_1K.get(model, {'in': 0.001, 'out': 0.003})
    inp = usage.get('prompt_tokens', 0) / 1000 * rates['in']
    out = usage.get('completion_tokens', 0) / 1000 * rates['out']
    return round(inp + out, 6)


# ── Stub (no key) ──────────────────────────────────────────────────────────────
def _stub_reply(messages: list[dict], agent_id: str, model: str) -> dict:
    last = next((m['content'] for m in reversed(messages) if m['role'] == 'user'), '')
    return {
        'text': (
            f'⚠️ **No OPENROUTER_API_KEY set.**\n\n'
            f'To enable real AI responses:\n'
            f'1. Get a free key at https://openrouter.ai/keys\n'
            f'2. Add it to your `.env` file: `OPENROUTER_API_KEY=sk-or-...`\n'
            f'3. Or use the 🔐 Vault tab to store it securely\n\n'
            f'**Your message:** {last[:200]}\n\n'
            f'*Model that would be used: `{model}`*'
        ),
        'tokens': 0,
        'cost': 0.0,
        'model': model,
        'provider': 'stub',
        'latency_ms': 0,
        'ok': False,
    }


# ── Available models list ──────────────────────────────────────────────────────
async def list_openrouter_models() -> list[dict]:
    """Fetch current model list from OpenRouter."""
    key = _or_key()
    if not key:
        return [{'id': k, 'model': v} for k, v in OPENROUTER_MODELS.items()]
    try:
        async with httpx.AsyncClient(timeout=10.0) as client:
            resp = await client.get(f'{OPENROUTER_BASE}/models', headers=_or_headers())
            data = resp.json()
            return data.get('data', [])
    except (KeyError, TypeError, ValueError, json.JSONDecodeError, OSError, AttributeError, RuntimeError):
        return [{'id': k, 'model': v} for k, v in OPENROUTER_MODELS.items()]
