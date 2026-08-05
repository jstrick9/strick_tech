"""Gap test configuration — covers all untested routes and dimensions."""
from __future__ import annotations
import asyncio, json, uuid, time
import httpx, pytest

# CSRF enforcement is ON by default for a single-worker server. These suites
# talk to a server started separately, so they are scripted API clients from
# its point of view and must carry a token. See tests/_csrf_client.py.
import pathlib as _pathlib
import sys as _sys
_sys.path.insert(0, str(_pathlib.Path(__file__).resolve().parents[1]))
from _csrf_client import async_client as _csrf_async_client  # noqa: E402
from _csrf_client import client as _csrf_client  # noqa: E402


BASE    = "http://127.0.0.1:8787"
TIMEOUT = 20

@pytest.fixture
async def C():
    async with _csrf_async_client(BASE, timeout=TIMEOUT) as c:
        yield c

def uid(p="gap"): return f"{p}_{uuid.uuid4().hex[:8]}"
async def GET(c, path, **p): return await c.get(path, params=p or None)
async def POST(c, path, j=None): return await c.post(path, json=j or {})
async def PATCH(c, path, j): return await c.patch(path, json=j)
async def DELETE(c, path): return await c.delete(path)
async def PUT(c, path, j): return await c.put(path, json=j)

def ok(r, label=""):
    assert r.status_code < 500, f"GAP [{label}]: 5xx {r.status_code}: {r.text[:300]}"
    return r.json() if "json" in r.headers.get("content-type","") else {}

def chk(label, cond, got=None):
    msg = f"\n✗ GAP: {label}"
    if got is not None: msg += f"\n  got={got!r}"
    assert cond, msg

pytest_plugins = ('pytest_asyncio',)
