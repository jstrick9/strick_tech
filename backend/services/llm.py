"""
Agentic OS — LLM Service
Supports: OpenRouter (primary), Ollama (local), direct Anthropic/OpenAI fallbacks.
All calls are async. Streaming via async generators.
"""
from __future__ import annotations
import os, json, asyncio, time, logging
from typing import AsyncGenerator, Optional
import httpx

log = logging.getLogger("agentic.llm")

# ── Model registry ─────────────────────────────────────────────────────────────
OPENROUTER_MODELS = {
    # id used in agents config → openrouter model string
    "claude":       "anthropic/claude-3.5-sonnet",
    "claude-opus":  "anthropic/claude-opus-4",
    "gpt4o":        "openai/gpt-4o",
    "gpt4o-mini":   "openai/gpt-4o-mini",
    "gemini":       "google/gemini-2.5-pro",
    "gemini-flash": "google/gemini-2.0-flash-exp:free",
    "grok":         "x-ai/grok-3",
    "grok-mini":    "x-ai/grok-3-mini",
    "hermes":       "nousresearch/hermes-3-llama-3.1-405b",
    "llama":        "meta-llama/llama-3.3-70b-instruct:free",
    "mistral":      "mistralai/mistral-small-3.2-24b-instruct:free",
    "qwen":         "qwen/qwen3-235b-a22b:free",
    # generic fallback
    "default":      "anthropic/claude-3.5-sonnet",
    "free":         "google/gemini-2.0-flash-exp:free",
}

OPENROUTER_BASE = "https://openrouter.ai/api/v1"
OLLAMA_BASE     = os.getenv("OLLAMA_BASE_URL", "http://localhost:11434")


def _or_key() -> str:
    return os.getenv("OPENROUTER_API_KEY", "")


def _or_headers() -> dict:
    return {
        "Authorization": f"Bearer {_or_key()}",
        "HTTP-Referer":  f"http://localhost:{int(__import__("os").getenv("AGENTIC_OS_PORT", "8787"))}",
        "X-Title":       "Agentic OS",
        "Content-Type":  "application/json",
    }


def resolve_model(agent_id: str, custom_model: str = "") -> tuple[str, str]:
    """Returns (provider, model_string). custom_model overrides registry."""
    if custom_model:
        # if it looks like an ollama model (no slash), route to ollama
        if "/" not in custom_model and not custom_model.startswith("ollama:"):
            return "ollama", custom_model
        return "openrouter", custom_model
    model = OPENROUTER_MODELS.get(agent_id.lower(), OPENROUTER_MODELS["default"])
    return "openrouter", model


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
            if m.get("role") == "system":
                msgs[i] = {**m, "content": ctx + "\n\n---\n\n" + m["content"]}
                return msgs
        return [{"role": "system", "content": ctx}] + msgs
    except Exception:
        return messages


async def complete(
    messages: list[dict],
    agent_id: str = "default",
    model: str = "",
    temperature: float = 0.7,
    max_tokens: int = 2048,
    timeout: float = 60.0,
    inject_steering: bool = True,
) -> dict:
    """Single-shot completion. Returns {text, tokens, cost, model, latency_ms}"""
    if inject_steering and agent_id not in ("steering","gitai","bugbot","specs"):
        messages = _inject_steering(messages)
    t0 = time.time()
    provider, model_str = resolve_model(agent_id, model)

    if provider == "ollama":
        return await _ollama_complete(messages, model_str, temperature, max_tokens, timeout)

    key = _or_key()
    if not key:
        return _stub_reply(messages, agent_id, model_str)

    payload = {
        "model": model_str,
        "messages": messages,
        "temperature": temperature,
        "max_tokens": max_tokens,
    }
    try:
        async with httpx.AsyncClient(timeout=timeout) as client:
            resp = await client.post(
                f"{OPENROUTER_BASE}/chat/completions",
                headers=_or_headers(),
                json=payload,
            )
            resp.raise_for_status()
            data = resp.json()
            text = data["choices"][0]["message"]["content"]
            usage = data.get("usage", {})
            latency = round((time.time() - t0) * 1000)
            return {
                "text": text,
                "tokens": usage.get("total_tokens", 0),
                "prompt_tokens": usage.get("prompt_tokens", 0),
                "completion_tokens": usage.get("completion_tokens", 0),
                "cost": _estimate_cost(model_str, usage),
                "model": model_str,
                "provider": "openrouter",
                "latency_ms": latency,
                "ok": True,
            }
    except httpx.HTTPStatusError as e:
        log.error("OpenRouter HTTP error: %s %s", e.response.status_code, e.response.text[:300])
        return {"text": f"[LLM error {e.response.status_code}]: {e.response.text[:200]}", "ok": False, "error": str(e)}
    except Exception as e:
        log.error("LLM complete error: %s", e)
        return {"text": f"[LLM error]: {e}", "ok": False, "error": str(e)}


# ── Streaming completion ────────────────────────────────────────────────────────
async def stream(
    messages: list[dict],
    agent_id: str = "default",
    model: str = "",
    temperature: float = 0.7,
    max_tokens: int = 4096,
    timeout: float = 120.0,
    inject_steering: bool = True,
) -> AsyncGenerator[str, None]:
    """Yields SSE-formatted chunks: 'data: {json}\n\n'"""
    if inject_steering and agent_id not in ("steering","gitai","bugbot","specs"):
        messages = _inject_steering(messages)
    provider, model_str = resolve_model(agent_id, model)

    if provider == "ollama":
        async for chunk in _ollama_stream(messages, model_str, temperature, max_tokens, timeout):
            yield chunk
        return

    key = _or_key()
    if not key:
        # stream a helpful stub
        stub = _stub_reply(messages, agent_id, model_str)["text"]
        for word in stub.split(" "):
            yield f'data: {json.dumps({"delta": word + " ", "done": False})}\n\n'
            await asyncio.sleep(0.02)
        yield f'data: {json.dumps({"delta": "", "done": True, "model": model_str})}\n\n'
        return

    payload = {
        "model": model_str,
        "messages": messages,
        "temperature": temperature,
        "max_tokens": max_tokens,
        "stream": True,
    }
    try:
        async with httpx.AsyncClient(timeout=timeout) as client:
            async with client.stream(
                "POST",
                f"{OPENROUTER_BASE}/chat/completions",
                headers=_or_headers(),
                json=payload,
            ) as resp:
                resp.raise_for_status()
                async for line in resp.aiter_lines():
                    if not line or not line.startswith("data:"):
                        continue
                    raw = line[5:].strip()
                    if raw == "[DONE]":
                        yield f'data: {json.dumps({"delta": "", "done": True, "model": model_str})}\n\n'
                        break
                    try:
                        chunk = json.loads(raw)
                        delta = chunk["choices"][0]["delta"].get("content", "")
                        if delta:
                            yield f'data: {json.dumps({"delta": delta, "done": False})}\n\n'
                    except Exception:
                        pass
    except Exception as e:
        log.error("LLM stream error: %s", e)
        yield f'data: {json.dumps({"delta": f"[stream error]: {e}", "done": True, "error": str(e)})}\n\n'


# ── Ollama ─────────────────────────────────────────────────────────────────────
async def _ollama_complete(messages, model, temperature, max_tokens, timeout) -> dict:
    t0 = time.time()
    try:
        payload = {
            "model": model,
            "messages": messages,
            "stream": False,
            "options": {"temperature": temperature, "num_predict": max_tokens},
        }
        async with httpx.AsyncClient(timeout=timeout) as client:
            resp = await client.post(f"{OLLAMA_BASE}/api/chat", json=payload)
            resp.raise_for_status()
            data = resp.json()
            text = data.get("message", {}).get("content", "")
            return {
                "text": text,
                "tokens": data.get("eval_count", 0),
                "cost": 0.0,
                "model": model,
                "provider": "ollama",
                "latency_ms": round((time.time() - t0) * 1000),
                "ok": True,
            }
    except Exception as e:
        return {
            "text": f"[Ollama error — is Ollama running? Install: https://ollama.com]\n\n{e}",
            "ok": False,
            "error": str(e),
            "provider": "ollama",
        }


async def _ollama_stream(messages, model, temperature, max_tokens, timeout) -> AsyncGenerator[str, None]:
    payload = {
        "model": model,
        "messages": messages,
        "stream": True,
        "options": {"temperature": temperature, "num_predict": max_tokens},
    }
    try:
        async with httpx.AsyncClient(timeout=timeout) as client:
            async with client.stream("POST", f"{OLLAMA_BASE}/api/chat", json=payload) as resp:
                resp.raise_for_status()
                async for line in resp.aiter_lines():
                    if not line:
                        continue
                    try:
                        chunk = json.loads(line)
                        delta = chunk.get("message", {}).get("content", "")
                        done = chunk.get("done", False)
                        if delta:
                            yield f'data: {json.dumps({"delta": delta, "done": False})}\n\n'
                        if done:
                            yield f'data: {json.dumps({"delta": "", "done": True, "model": model})}\n\n'
                    except Exception:
                        pass
    except Exception as e:
        yield f'data: {json.dumps({"delta": f"[Ollama stream error]: {e}", "done": True})}\n\n'


# ── Ollama health check ─────────────────────────────────────────────────────────
async def ollama_health() -> dict:
    try:
        async with httpx.AsyncClient(timeout=4.0) as client:
            resp = await client.get(f"{OLLAMA_BASE}/api/tags")
            data = resp.json()
            models = [m["name"] for m in data.get("models", [])]
            return {"running": True, "models": models, "url": OLLAMA_BASE}
    except Exception as e:
        return {"running": False, "models": [], "url": OLLAMA_BASE, "error": str(e)}


# ── Cost estimation ─────────────────────────────────────────────────────────────
_COST_PER_1K = {
    "anthropic/claude-3.5-sonnet":  {"in": 0.003, "out": 0.015},
    "anthropic/claude-opus-4":      {"in": 0.015, "out": 0.075},
    "openai/gpt-4o":                {"in": 0.005, "out": 0.015},
    "openai/gpt-4o-mini":           {"in": 0.00015, "out": 0.0006},
    "google/gemini-2.5-pro":        {"in": 0.00125, "out": 0.005},
}

def _estimate_cost(model: str, usage: dict) -> float:
    rates = _COST_PER_1K.get(model, {"in": 0.001, "out": 0.003})
    inp = usage.get("prompt_tokens", 0) / 1000 * rates["in"]
    out = usage.get("completion_tokens", 0) / 1000 * rates["out"]
    return round(inp + out, 6)


# ── Stub (no key) ──────────────────────────────────────────────────────────────
def _stub_reply(messages: list[dict], agent_id: str, model: str) -> dict:
    last = next((m["content"] for m in reversed(messages) if m["role"] == "user"), "")
    return {
        "text": (
            f"⚠️ **No OPENROUTER_API_KEY set.**\n\n"
            f"To enable real AI responses:\n"
            f"1. Get a free key at https://openrouter.ai/keys\n"
            f"2. Add it to your `.env` file: `OPENROUTER_API_KEY=sk-or-...`\n"
            f"3. Or use the 🔐 Vault tab to store it securely\n\n"
            f"**Your message:** {last[:200]}\n\n"
            f"*Model that would be used: `{model}`*"
        ),
        "tokens": 0,
        "cost": 0.0,
        "model": model,
        "provider": "stub",
        "latency_ms": 0,
        "ok": False,
    }


# ── Available models list ──────────────────────────────────────────────────────
async def list_openrouter_models() -> list[dict]:
    """Fetch current model list from OpenRouter."""
    key = _or_key()
    if not key:
        return [{"id": k, "model": v} for k, v in OPENROUTER_MODELS.items()]
    try:
        async with httpx.AsyncClient(timeout=10.0) as client:
            resp = await client.get(f"{OPENROUTER_BASE}/models", headers=_or_headers())
            data = resp.json()
            return data.get("data", [])
    except Exception:
        return [{"id": k, "model": v} for k, v in OPENROUTER_MODELS.items()]
