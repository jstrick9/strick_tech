"""
Agentic OS — Security Test Configuration

Security tests verify that the platform correctly resists:
  - SQL injection (OWASP A03:2021)
  - XSS / HTML injection (OWASP A03:2021)
  - Path traversal (OWASP A01:2021)
  - Code injection / Remote Code Execution
  - Secrets exposure
  - Input validation failures
  - License / tier bypass
  - Command injection
  - SSRF attacks
  - Information disclosure

DESIGN PHILOSOPHY:
  This platform is LOCAL-FIRST (no multi-user auth). Security focus is:
  - Prevent code execution (RCE) via profiler/terminal
  - Prevent filesystem escapes via path traversal
  - Prevent SQLi in DB Studio (user-controlled SQL)
  - Prevent secrets leakage (values masked in API)
  - Prevent resource exhaustion
  - Prevent SSRF via websearch fetch-content
  - Ensure data isolation and integrity

HOW TO RUN (live server recipe):
  These tests talk to a real server on 127.0.0.1:8787. Start it with:

      AGENTIC_OS_HOST=127.0.0.1 RATE_LIMIT_MAX=100000 python3 run.py

  * AGENTIC_OS_HOST=127.0.0.1 — the terminal's auth gate fail-closes when the
    server is bound beyond loopback and no users are registered, which would
    401 the terminal tests for a reason that is not the thing under test.
  * RATE_LIMIT_MAX=100000 — the suite bursts ~350 requests from one IP; the
    default per-IP ceiling (300/60s) saturates mid-run and every subsequent
    CSRF-token fetch 429s, cascading into unrelated failures. (The
    PYTEST_CURRENT_TEST bypass in the middleware only applies when tests run
    in-process; a separately started server never sees that variable.)
  Measured with both set: 329 passed / 2 skipped; with neither: 26 failures,
  none of them the behaviour the failing tests were written to check.
"""
from __future__ import annotations
import asyncio, json, uuid
import httpx
import pytest

# CSRF enforcement is ON by default for a single-worker server. These suites
# talk to a server started separately, so they are scripted API clients from
# its point of view and must carry a token. See tests/_csrf_client.py.
import pathlib as _pathlib
import sys as _sys
_sys.path.insert(0, str(_pathlib.Path(__file__).resolve().parents[1]))
from _csrf_client import async_client as _csrf_async_client  # noqa: E402
from _csrf_client import client as _csrf_client  # noqa: E402


BASE    = "http://127.0.0.1:8787"
# 30s, not 20: /api/websearch/search makes up to two outbound fetches (DDG
# results at 12s + instant answers at 8s) before answering. On a network where
# egress is blackholed rather than refused, both timeouts run their FULL
# course back to back (~20s) and a 20s client ceiling races the server to the
# wire — measured as httpx.ReadTimeout on tests that pass on a healthy
# network. 30s keeps the client slower than the server's own worst case.
TIMEOUT = 30

@pytest.fixture
async def C():
    async with _csrf_async_client(BASE, timeout=TIMEOUT) as c:
        yield c

def uid(p="sec"): return f"{p}_{uuid.uuid4().hex[:8]}"

async def GET(c, path, **kw):    return await c.get(path, params=kw or None)
async def POST(c, path, j=None): return await c.post(path, json=j or {})
async def PATCH(c, path, j):     return await c.patch(path, json=j)
async def DELETE(c, path):       return await c.delete(path)

def sec_ok(r, label):
    """Assert no server crash (5xx) for security-probing input.

    One deliberate exception: HTTP 503 with ``code: "llm_unavailable"`` is the
    platform's DOCUMENTED degradation shape (services/llm.py raises
    LLMUnavailableError and the routers translate it) for "no AI provider is
    configured" — an honest refusal, not a fault. Without this carve-out the
    whole suite hard-depends on a live LLM provider: on a provider-less
    server, nine LLM-backed endpoints answer 503 and are reported as crashes
    they are not. Anything else in the 5xx range (unhandled exception, 500,
    bad gateway) still fails exactly as before.
    """
    if r.status_code == 503:
        try:
            body = r.json()
        except ValueError:
            body = {}
        if body.get("code") == "llm_unavailable" and body.get("ok") is False:
            return r
    assert r.status_code < 500, \
        f"SEC: {label} → Server crashed (HTTP {r.status_code}): {r.text[:300]}"
    return r

def sec_blocked(r, label):
    """Assert malicious input was rejected (not 200 with success)."""
    body = r.text.lower()
    assert not (r.status_code == 200 and '"ok": true' in body and
                '"error"' not in body), \
        f"SEC FAIL: {label} should have been rejected, got: {r.text[:200]}"

def no_rce(r, label, markers=None):
    """Assert response doesn't contain RCE evidence."""
    markers = markers or ["root:", "uid=", "/etc/passwd", "bin/sh", "command not found: whoami"]
    text = r.text.lower()
    for marker in markers:
        assert marker not in text, \
            f"SEC RCE: {label} — Found '{marker}' in response: {r.text[:300]}"

def no_path_escape(r, label):
    """Assert path traversal didn't succeed."""
    dangerous = ["root:", "passwd", "/etc/", "secret", "private", "shadow"]
    text = r.text.lower()
    for d in dangerous:
        assert d not in text, \
            f"SEC PATH: {label} — Found '{d}' in response (path traversal?): {r.text[:200]}"

pytest_plugins = ('pytest_asyncio',)
