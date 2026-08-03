"""
Agentic OS — System Test Configuration

System tests treat the platform as a BLACK BOX.
No knowledge of internals — only the public HTTP API.
Tests real end-to-end user scenarios, not components in isolation.

Layered above unit and integration tests:
  Unit       → single function/endpoint correctness
  Integration → cross-component data flow
  System     → real user journeys, security, concurrency, resilience
"""
from __future__ import annotations
import asyncio, json, re, time, uuid, sys
from pathlib import Path
import httpx
import pytest

BASE    = "http://127.0.0.1:8787"
TIMEOUT = 30          # system tests may involve more steps

# ── Shared per-test async client ─────────────────────────────────────────────
@pytest.fixture
async def C():
    """Fresh async client for every system test."""
    async with httpx.AsyncClient(base_url=BASE, timeout=TIMEOUT) as c:
        yield c


# ── System-test helpers ───────────────────────────────────────────────────────
def uid(prefix="sys"):
    return f"{prefix}_{uuid.uuid4().hex[:10]}"

def ts():
    return int(time.time())

async def GET(c, path, **kw):   return await c.get(path,  params=kw or None)
async def POST(c, path, j=None): return await c.post(path, json=j or {})
async def PATCH(c, path, j):    return await c.patch(path, json=j)
async def PUT(c, path, j):      return await c.put(path,   json=j)
async def DELETE(c, path, j=None):
    return await (c.request("DELETE", path, json=j) if j else c.delete(path))

# ── No-AI-provider handling ───────────────────────────────────────────────────
# llm.complete() raises LLMUnavailableError rather than returning placeholder
# help text that callers mistook for a real reply; the app maps that to a 503
# {"code": "llm_unavailable"}, and sse_guard() emits the same code as a final
# frame on streams. With no API key and no local model that is the *correct*
# response, not a defect in the endpoint under test.
def _no_provider(r) -> bool:
    if r.status_code != 503:
        return False
    try:
        return r.json().get("code") == "llm_unavailable"
    except Exception:
        return False


def skip_if_no_provider(r, label=""):
    if _no_provider(r):
        import pytest as _pt

        _pt.skip(f"no AI provider configured{' for ' + label if label else ''} — endpoint correctly returned 503")


def skip_if_no_provider_events(events, label=""):
    """Same, for SSE runs that closed cleanly with an llm_unavailable frame."""
    if any(e.get("code") == "llm_unavailable" for e in events):
        import pytest as _pt

        _pt.skip(f"no AI provider configured{' for ' + label if label else ''} — stream reported llm_unavailable")


def must(r, *codes, label=""):
    codes = codes or (200,)
    skip_if_no_provider(r, label)
    assert r.status_code in codes, \
        f"[{label}] Expected {codes}, got {r.status_code}: {r.text[:300]}"
    ct = r.headers.get("content-type", "")
    if "event-stream" in ct or "text/plain" in ct:
        return {}  # SSE/text response - caller must use r.text directly
    try:
        return r.json()
    except Exception:
        return {}

def check(label, cond, got=None):
    msg = f"\n✗ SYS: {label}"
    if got is not None: msg += f"\n  got={got!r}"
    assert cond, msg

def sse_events(text: str) -> list[dict]:
    """Parse SSE text → list of event dicts."""
    events = []
    for line in text.split("\n"):
        if line.startswith("data:"):
            try:
                events.append(json.loads(line[5:].strip()))
            except Exception:
                pass
    return events

def no_server_error(r, label=""):
    assert r.status_code < 500, \
        f"[{label}] SERVER ERROR {r.status_code}: {r.text[:400]}"

# ── pytest-asyncio config ─────────────────────────────────────────────────────
pytest_plugins = ('pytest_asyncio',)


import pytest as _pytest, httpx as _httpx
_CORE = {"brain":{"name":"Brain"},"builder":{"name":"Builder"},"researcher":{"name":"Researcher"},
         "reviewer":{"name":"Reviewer"},"creative":{"name":"Creative"},"memory":{"name":"Memory"},
         "local":{"name":"Local LLM"},"orchestrator":{"name":"Orchestrator"}}
@_pytest.fixture(autouse=True, scope="session")
def _restore_agents_system():
    with _httpx.Client(base_url="http://127.0.0.1:8787", timeout=10) as c:
        for aid, d in _CORE.items():
            try: c.patch(f"/api/agents/{aid}", json=d)
            except: pass
    yield


@_pytest.fixture(autouse=True, scope="session")
def _ensure_agent_identities_provisioned():
    """This suite is documented as treating the platform as a black box that
    tests real end-to-end journeys without depending on other suites having
    run first. Agent-identity provisioning is a deliberate, explicit
    Zero-Trust action (POST /api/agent-identity/provision-all) rather than
    something the app does automatically at startup, so tests that exercise
    identity/token endpoints for existing agents (e.g. rotating "reviewer"'s
    keys) would otherwise only pass when tests/integration or tests/uat
    happened to provision those identities first in the same test run.
    Provisioning here makes this suite self-sufficient, matching its own
    "black box" / order-independence design intent, regardless of which
    other suites ran before it.
    """
    with _httpx.Client(base_url="http://127.0.0.1:8787", timeout=10) as c:
        try:
            c.post("/api/agent-identity/provision-all")
        except Exception:
            pass
    yield
