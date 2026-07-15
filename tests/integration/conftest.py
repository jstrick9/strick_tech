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


def ok(r, label=""):
    assert r.status_code == 200, \
        f"{label}: Expected 200, got {r.status_code}: {r.text[:200]}"
    return r.json()


def ok_or(r, *codes):
    assert r.status_code in codes, \
        f"Expected {codes}, got {r.status_code}: {r.text[:150]}"
    return r.json() if r.status_code == 200 else {}


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
