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


# ── Frontend (FE) fixture ──────────────────────────────────────────────────────
import pathlib as _pl

@pytest.fixture(scope="session")
def FE() -> str:
    """Load the frontend index.html as a string for HTML-level UX checks."""
    fe_path = _pl.Path(__file__).resolve().parents[2] / "frontend" / "index.html"
    if not fe_path.exists():
        pytest.skip(f"frontend/index.html not found at {fe_path}")
    return fe_path.read_text(encoding="utf-8", errors="replace")


def fe_has(fe: str, needle: str, label: str, case_sensitive: bool = True):
    """Assert that frontend HTML contains a pattern."""
    haystack = fe if case_sensitive else fe.lower()
    pattern  = needle if case_sensitive else needle.lower()
    assert pattern in haystack, f"✗ UX: {label} — '{needle}' not found in frontend"


def ux_check(label: str, cond: bool, details=None):
    """UX-level assertion — communicates what the user would experience."""
    msg = f"✗ UX: {label}"
    if details:
        msg += f"\n  Details: {details}"
    assert cond, msg


# ── Sync HTTP client fixture (C) ───────────────────────────────────────────────
import httpx as _httpx

@pytest.fixture
async def C():
    """Async HTTP client for UX interaction tests (used with await GET/POST)."""
    async with _httpx.AsyncClient(base_url=BASE, timeout=TIMEOUT) as c:
        yield c

# alias F → U for tests that use a sync-style fixture named F
@pytest.fixture
async def F():
    """Alias for tests that use 'F' as the fixture name (same as U)."""
    async with _httpx.AsyncClient(base_url=BASE, timeout=TIMEOUT) as c:
        yield c


# ── ux_ok helper (used by test_ux_04 interaction tests) ───────────────────────
def ux_ok(r, label: str) -> dict:
    """Assert response is OK and return parsed JSON — UX-level check."""
    assert r.status_code < 500, \
        f"✗ UX: {label} → server error {r.status_code}: {r.text[:300]}"
    ct = r.headers.get("content-type", "")
    if "event-stream" in ct or r.status_code != 200:
        return {}
    try:
        return r.json()
    except Exception:
        return {}


def fe_count(fe: str, needle: str, case_sensitive: bool = True) -> int:
    """Count occurrences of needle in the frontend HTML."""
    haystack = fe if case_sensitive else fe.lower()
    pattern  = needle if case_sensitive else needle.lower()
    return haystack.count(pattern)


def sse_events(text: str) -> list:
    """Parse SSE text → list of parsed event dicts (alias for sse())."""
    return sse(text)
