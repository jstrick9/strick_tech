"""
Agentic OS — Integration Test Configuration
Tests cross-component interactions against the LIVE server on port 8787.
Uses function-scoped async client to avoid event loop issues with pytest-asyncio auto mode.
"""
from __future__ import annotations
import asyncio, json, time, uuid
import httpx
import pytest

BASE = "http://127.0.0.1:8787"
TIMEOUT = 20


# ── Per-test async client (function-scoped avoids event loop close errors) ──
@pytest.fixture
async def client():
    """Per-test async HTTP client."""
    async with httpx.AsyncClient(base_url=BASE, timeout=TIMEOUT) as c:
        yield c


# ── Helpers ─────────────────────────────────────────────────────────────────
def uid(prefix="it"):
    return f"{prefix}_{uuid.uuid4().hex[:8]}"


async def GET(client, path, **params):
    return await client.get(path, params=params or None)

async def POST(client, path, body=None):
    return await client.post(path, json=body or {})

async def PATCH(client, path, body):
    return await client.patch(path, json=body)

async def PUT(client, path, body):
    return await client.put(path, json=body)

async def DELETE(client, path, body=None):
    if body:
        return await client.request("DELETE", path, json=body)
    return await client.delete(path)


def check(label, condition, actual=None):
    msg = f"\n✗ {label}"
    if actual is not None:
        msg += f"\n  Got: {actual!r}"
    assert condition, msg


# ── No-AI-provider handling ───────────────────────────────────────────────────
# llm.complete() now raises LLMUnavailableError instead of returning placeholder
# help text that callers mistook for a real reply, and the app maps that to a
# 503 {"code": "llm_unavailable"}. That is the *correct* response in an
# environment with no API key and no local model — it is not a defect in the
# endpoint under test. Distinguish the two so these suites stay meaningful on a
# machine that does have a provider, and skip honestly on one that doesn't.
def _no_provider(r) -> bool:
    if r.status_code != 503:
        return False
    try:
        body = r.json()
    except Exception:
        return False
    return body.get('code') == 'llm_unavailable' or 'agent in the swarm failed' in str(body.get('error', ''))


def skip_if_no_provider(r, label=''):
    """Skip when the only thing standing in the way is a missing AI provider."""
    if _no_provider(r):
        import pytest as _pt

        _pt.skip(f'no AI provider configured{" for " + label if label else ""} — endpoint correctly returned 503')


def skip_if_no_provider_events(events, label=''):
    """Skip when an SSE run only reported that no AI provider is available.

    sse_guard() converts LLMUnavailableError into a terminal error frame rather
    than truncating the response mid-chunk, so the stream is well-formed but
    carries no work. That is correct behaviour, not a broken endpoint.
    """
    if any(e.get('code') == 'llm_unavailable' for e in events):
        import pytest as _pt

        _pt.skip(f'no AI provider configured{" for " + label if label else ""} — stream reported llm_unavailable')


def ok(r, label=""):
    skip_if_no_provider(r, label)
    assert r.status_code == 200, \
        f"{label}: Expected 200, got {r.status_code}: {r.text[:200]}"
    return r.json()


def ok_or(r, *codes):
    """Assert the status is one of `codes` and return the parsed body.

    This used to return {} for anything other than 200 — including the other
    codes the caller explicitly allowed — so `ok_or(r, 200, 201)["id"]` blew up
    on a 201 and every assertion about a non-200 body was silently vacuous.
    Same flaw already fixed in tests/uat/conftest.py's j() and
    tests/system/conftest.py's must().
    """
    skip_if_no_provider(r)
    assert r.status_code in codes, \
        f"Expected {codes}, got {r.status_code}: {r.text[:150]}"
    if "event-stream" in r.headers.get("content-type", ""):
        return {}
    try:
        return r.json()
    except Exception:
        return {}


# ── Core agent restoration (security tests may mutate names) ──────────────────
import pytest as _pytest, httpx as _httpx

_CORE_AGENTS = {
    "brain":        {"name": "Brain",        "system_prompt": "You are Brain — a deep reasoning and strategic planning agent."},
    "builder":      {"name": "Builder",      "system_prompt": "You are Builder — an expert software engineer."},
    "researcher":   {"name": "Researcher",   "system_prompt": "You are Researcher — a meticulous information gatherer."},
    "reviewer":     {"name": "Reviewer",     "system_prompt": "You are Reviewer — a senior code reviewer and QA engineer."},
    "creative":     {"name": "Creative",     "system_prompt": "You are Creative — a multi-modal creative director."},
    "memory":       {"name": "Memory",       "system_prompt": "You are Memory — a knowledge retrieval specialist."},
    "local":        {"name": "Local LLM",    "system_prompt": "You are Local — a private, offline AI assistant."},
    "orchestrator": {"name": "Orchestrator", "system_prompt": "You are the Orchestrator — a master coordinator."},
}

@_pytest.fixture(autouse=True, scope="session")
def _restore_core_agents_integration():
    with _httpx.Client(base_url="http://127.0.0.1:8787", timeout=10) as c:
        for aid, data in _CORE_AGENTS.items():
            try: c.patch(f"/api/agents/{aid}", json=data)
            except: pass
    yield
