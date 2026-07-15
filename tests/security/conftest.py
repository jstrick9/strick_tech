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
"""
from __future__ import annotations
import asyncio, json, uuid
import httpx
import pytest

BASE    = "http://127.0.0.1:8787"
TIMEOUT = 20

@pytest.fixture
async def C():
    async with httpx.AsyncClient(base_url=BASE, timeout=TIMEOUT) as c:
        yield c

def uid(p="sec"): return f"{p}_{uuid.uuid4().hex[:8]}"

async def GET(c, path, **kw):    return await c.get(path, params=kw or None)
async def POST(c, path, j=None): return await c.post(path, json=j or {})
async def PATCH(c, path, j):     return await c.patch(path, json=j)
async def DELETE(c, path):       return await c.delete(path)

def sec_ok(r, label):
    """Assert no server crash (5xx) for security-probing input."""
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
