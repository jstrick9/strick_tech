"""
Agentic OS — User Acceptance Test (UAT) Configuration

UAT validates the platform from the END USER's perspective:
  - Can a real person accomplish their goal?
  - Do UI flows make sense and complete correctly?
  - Does the data look right after each action?
  - Are error messages helpful, not technical?
  - Does the platform behave correctly under real-world usage patterns?

UAT is ABOVE system tests — it maps to actual user stories and acceptance criteria.
Each test represents a user's job-to-be-done.

Compared to other test layers:
  Unit        → code-level correctness (isolated)
  Integration → cross-component data flows
  System      → black-box: journeys, security, concurrency
  UAT         → user-story level: "As a user I can X and see Y"
"""
from __future__ import annotations
import asyncio, json, re, time, uuid
from typing import Any
import httpx
import pytest

BASE    = "http://127.0.0.1:8787"
TIMEOUT = 25

# ── Per-test fresh async client ───────────────────────────────────────────────
@pytest.fixture
async def U():
    """Fresh user-session client (simulates one browser tab)."""
    async with httpx.AsyncClient(base_url=BASE, timeout=TIMEOUT) as c:
        yield c


# ── UAT helpers ───────────────────────────────────────────────────────────────
def uid(prefix="uat"): return f"{prefix}_{uuid.uuid4().hex[:8]}"

async def GET(u, path, **kw):    return await u.get(path, params=kw or None)
async def POST(u, path, j=None): return await u.post(path, json=j or {})
async def PATCH(u, path, j):     return await u.patch(path, json=j)
async def PUT(u, path, j):       return await u.put(path, json=j)
async def DELETE(u, path, j=None):
    return await (u.request("DELETE", path, json=j) if j else u.delete(path))

def j(r) -> dict:
    """Parse JSON response — skip if event-stream."""
    ct = r.headers.get("content-type","")
    if "event-stream" in ct or r.status_code != 200:
        return {}
    try: return r.json()
    except: return {}

def sse(text: str) -> list[dict]:
    """Parse SSE text → list of event dicts."""
    out = []
    for line in text.split("\n"):
        if line.startswith("data:"):
            try: out.append(json.loads(line[5:].strip()))
            except: pass
    return out

def accept(r, label, *codes):
    codes = codes or (200,)
    assert r.status_code in codes, \
        f"UAT [{label}]: expected {codes}, got {r.status_code}:\n{r.text[:300]}"
    return j(r)

def uat(label, cond, got=None):
    """User-facing assertion: what the user should be able to do/see."""
    msg = f"\n✗ UAT: {label}"
    if got is not None: msg += f"\n  Actual: {got!r}"
    assert cond, msg

def no_error(r, label=""):
    """Assert no server error for any user action."""
    assert r.status_code < 500, \
        f"UAT: User action '{label}' caused server error {r.status_code}:\n{r.text[:400]}"

# ── pytest-asyncio ────────────────────────────────────────────────────────────
pytest_plugins = ('pytest_asyncio',)


# ── Agent restoration guard ────────────────────────────────────────────────────
CORE_AGENTS = {
    "brain":        {"name": "Brain",        "system_prompt": "You are Brain — a deep reasoning and strategic planning agent. You excel at long-form analysis, research synthesis, system design, and architectural decisions. Think step by step, consider edge cases, and provide thorough explanations."},
    "builder":      {"name": "Builder",      "system_prompt": "You are Builder — an expert software engineer specializing in clean, production-ready code. You write TypeScript, Python, React, FastAPI, and SQL. Always include type hints, error handling, and brief docstrings. Output runnable code, not pseudocode."},
    "researcher":   {"name": "Researcher",   "system_prompt": "You are Researcher — a meticulous information gatherer and analyst. You synthesize research from multiple sources, identify trends, compare options objectively, and present findings with citations."},
    "reviewer":     {"name": "Reviewer",     "system_prompt": "You are Reviewer — a senior code reviewer and QA engineer. You review code for bugs, security vulnerabilities, performance issues, and missing tests."},
    "creative":     {"name": "Creative",     "system_prompt": "You are Creative — a multi-modal creative director. You craft compelling copy, design UI layouts, generate image prompts, and develop brand voices."},
    "memory":       {"name": "Memory",       "system_prompt": "You are Memory — a knowledge retrieval specialist. You search the vector database for relevant context and synthesize stored knowledge."},
    "local":        {"name": "Local LLM",    "system_prompt": "You are Local — a private, offline AI assistant running entirely on the user's machine. You prioritize privacy and work without internet access."},
    "orchestrator": {"name": "Orchestrator", "system_prompt": "You are the Orchestrator — a master coordinator that breaks complex tasks into parallel sub-tasks, assigns them to specialized agents, judges their outputs, and synthesizes the best result."},
}

@pytest.fixture(autouse=True, scope="session")
def restore_core_agents():
    """Restore core agent names/prompts at session start (security tests may mutate them)."""
    import httpx as _httpx
    with _httpx.Client(base_url=BASE, timeout=10) as c:
        for aid, data in CORE_AGENTS.items():
            try:
                c.patch(f"/api/agents/{aid}", json=data)
            except Exception:
                pass
    yield
