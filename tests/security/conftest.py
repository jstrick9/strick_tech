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
import sqlite3
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


# ── Live-instance pollution guard ─────────────────────────────────────────────
#
# WHY THIS EXISTS
#
# The security suite drives a real server against the operator's real
# memory/agentic.db — that is the point of it (the enforced CSRF path, the
# rate limiter, the real middleware stack). But the tests create rows to probe
# with: injection payloads become task titles, webhook names, MCP server URLs,
# supervisor goals, eval suites, memories, chat sessions… One measured run
# left +2,300 rows across 43 tables, plus payload-named files under
# preview/templates/, six lines on the ICM route log, and (before its own
# fixture) a stack of real git commits. After a few rounds the operator's
# kanban shows 800+ `flood_N` cards and the webhooks pane lists 150+
# payload-named endpoints — the suite's residue actively degrades the very
# product UI it is supposed to be protecting.
#
# WHAT THIS DOES
#
# An autouse fixture snapshots the rowid set of every table the suite is known
# to dirty (measured, see the list below), the set of files under preview/,
# and the byte size of the ICM route log, before each test. After the test it
# removes exactly what appeared: rows with rowids not in the snapshot, files
# not in the snapshot, route-log bytes past the mark. Pre-existing data is
# never touched — a rowid SET is used rather than a max-rowid threshold
# precisely because SQLite reuses rowids after tail deletions, and because
# the operator may legitimately write to the same tables while a run is in
# flight.
#
# The one deliberate pairing: memory_fts is an external-content FTS5 table
# (content='memory'), so deleting a memory row must be mirrored by deleting
# its FTS row — the same dual delete the /api/memory router performs. Every
# other table is a plain row delete.
#
# Logs (audit, observability, cost ledger) are included: they are append-only
# from the app's point of view, and deleting the TAIL of an append-only log
# (or of the hash-chained audit log, which is a linked list where any prefix
# is valid) is safe.

_POLLUTABLE_TABLES = [
    # user-visible content the suite fills with payloads
    'tasks', 'webhooks', 'mcp_servers', 'connector_registry',
    'supervisor_tasks', 'supervisor_runs', 'goals_v2', 'goal_milestones',
    'eval_suites', 'eval_cases', 'memory', 'agents', 'agent_identities',
    'agent_permissions', 'agent_performance', 'agent_hooks', 'workspaces',
    'chat_sessions', 'chat_log', 'specs', 'steering_files', 'secrets',
    'prompt_library', 'crdt_docs', 'hitl_queue', 'rag_pipelines',
    'arena_battles', 'mkt_reviews', 'shadow_tests', 'agent_kill_switches',
    'mcp_gateway_policies', 'mcp_gateway_calls', 'budget_caps',
    'ws_search_history',
    # session lifecycle (the auth-rebinding test registers real users)
    'auth_users', 'auth_sessions',
    # logs the suite appends to
    'audit', 'audit_log_chain', 'audit_receipts', 'obs_traces', 'obs_spans',
    'e2e_traces', 'cost_ledger', 'cost_alerts', 'identity_audit',
    'health_snapshots',
]

_REPO_ROOT = _pathlib.Path(__file__).resolve().parents[2]
_DB_PATH = _REPO_ROOT / 'memory' / 'agentic.db'
_ROUTE_LOG = _REPO_ROOT / 'memory' / 'icm' / 'route-log.jsonl'
_PREVIEW_DIR = _REPO_ROOT / 'preview'


def _snapshot_rowids(con):
    snap = {}
    for t in _POLLUTABLE_TABLES:
        try:
            snap[t] = set(r[0] for r in con.execute(f'SELECT rowid FROM "{t}"'))
        except Exception:
            snap[t] = None  # table missing on this install — nothing to guard
    return snap


def _remove_new_rows(con, before):
    for t, ids in before.items():
        if ids is None:
            continue
        try:
            now = set(r[0] for r in con.execute(f'SELECT rowid FROM "{t}"'))
        except Exception:
            continue
        new = now - ids
        if not new:
            continue
        marks = ','.join('?' * len(new))
        con.execute(f'DELETE FROM "{t}" WHERE rowid IN ({marks})', tuple(new))
        if t == 'memory':  # external-content FTS5 pairing (see docstring)
            try:
                con.execute(f'DELETE FROM memory_fts WHERE rowid IN ({marks})', tuple(new))
            except Exception:
                pass


# Tables whose EXISTING rows the suite can mutate in place (measured: an
# agent-update test overwrote the seed `brain` agent's name and system_prompt
# with an injection payload — the row was still "the same row", so the
# row-addition guard saw nothing). These tables are small and seed-defined, so
# the guard snapshots their full content and restores any changed row.
_CONTENT_GUARDED_TABLES = {
    'agents': 'id',
    'eval_suites': 'suite_id',
    'mcp_servers': 'server_id',
    'connector_registry': 'connector_id',
    'budget_caps': 'cap_id',
}


def _snapshot_table_content(con, table, key):
    try:
        old_rf = con.row_factory
        con.row_factory = sqlite3.Row
        try:
            return {r[key]: dict(r) for r in con.execute(f'SELECT * FROM "{table}"')}
        finally:
            con.row_factory = old_rf
    except Exception:
        return None


def _restore_table_content(con, table, key, before):
    if not before:
        return
    try:
        old_rf = con.row_factory
        con.row_factory = sqlite3.Row
        try:
            cols = [r[1] for r in con.execute(f'PRAGMA table_info("{table}")')]
            now = {r[key]: dict(r) for r in con.execute(f'SELECT * FROM "{table}"')}
        finally:
            con.row_factory = old_rf
    except Exception:
        return
    for k, old in before.items():
        cur = now.get(k)
        if cur is None:
            ph = ','.join('?' * len(cols))
            con.execute(
                f'INSERT INTO "{table}" ({",".join(cols)}) VALUES ({ph})',
                tuple(old.get(c) for c in cols),
            )
        elif any(cur.get(c) != old.get(c) for c in cols):
            sets = ','.join(f'"{c}"=?' for c in cols if c != key)
            vals = tuple(old.get(c) for c in cols if c != key) + (k,)
            con.execute(f'UPDATE "{table}" SET {sets} WHERE "{key}"=?', vals)


_TELEMETRY_TABLES = [
    # Async-written logs: the server records traces/ledger/audit entries AFTER
    # the HTTP response is delivered, so a row can land between a test's last
    # assertion and the per-test teardown — measured as 2 obs_traces + 3
    # cost_ledger rows surviving a full green run. The per-test guard cannot
    # close that window; this session-final sweep can. Telemetry only: content
    # tables are written synchronously with the response and are fully covered
    # per-test, and restricting the sweep means operator data written during
    # the run in CONTENT tables is never touched by it.
    'obs_traces', 'obs_spans', 'cost_ledger', 'cost_alerts',
    'audit', 'audit_log_chain', 'audit_receipts', 'e2e_traces',
    'identity_audit', 'health_snapshots', 'mcp_gateway_calls',
]


@pytest.fixture(scope='session', autouse=True)
def _guard_session_stragglers():
    """Final sweep for rows the server wrote asynchronously after a teardown."""
    import sqlite3 as _s3

    if not _DB_PATH.exists():
        yield
        return

    try:
        con = _s3.connect(str(_DB_PATH), timeout=5)
        con.execute('PRAGMA busy_timeout=5000')
        before = _snapshot_rowids(con)
        con.commit()
        con.close()
    except Exception:
        before = None

    yield

    if before is None:
        return
    try:
        con = _s3.connect(str(_DB_PATH), timeout=5)
        con.execute('PRAGMA busy_timeout=5000')
        _remove_new_rows(con, {t: before.get(t) for t in _TELEMETRY_TABLES})
        con.commit()
        con.close()
    except Exception:
        pass


@pytest.fixture(autouse=True)
def _guard_live_instance():
    """Remove whatever this test writes into the operator's live instance."""
    import sqlite3 as _s3

    if not _DB_PATH.exists():
        yield
        return

    try:
        con = _s3.connect(str(_DB_PATH), timeout=5)
        con.execute('PRAGMA busy_timeout=5000')
        before_rows = _snapshot_rowids(con)
        content_before = {
            t: _snapshot_table_content(con, t, key)
            for t, key in _CONTENT_GUARDED_TABLES.items()
        }
        con.commit()
        con.close()
    except Exception:
        before_rows = None
        content_before = {}

    def _list_preview():
        try:
            return {str(p) for p in _PREVIEW_DIR.rglob('*') if p.is_file()}
        except Exception:
            return set()

    files_before = _list_preview()
    route_size = _ROUTE_LOG.stat().st_size if _ROUTE_LOG.exists() else None

    # JSON stores the app rewrites wholesale on any touch (a skill run bumps
    # use_count and re-serialises the whole file with shuffled key order).
    # Probe runs must not bump the operator's counters or leave ordering churn
    # in the working tree, so both are restored byte-for-byte.
    _json_stores = [
        _REPO_ROOT / 'skills' / 'skills.json',
        _REPO_ROOT / 'docs' / 'module-risk.json',
    ]
    _json_before = {}
    for jp in _json_stores:
        try:
            _json_before[jp] = jp.read_bytes()
        except OSError:
            _json_before[jp] = None

    yield

    # ── teardown: put the instance back the way we found it ────────────────
    try:
        if before_rows is not None:
            con = _s3.connect(str(_DB_PATH), timeout=5)
            con.execute('PRAGMA busy_timeout=5000')
            _remove_new_rows(con, before_rows)
            for t, key in _CONTENT_GUARDED_TABLES.items():
                _restore_table_content(con, t, key, content_before.get(t))
            con.commit()
            con.close()
    except Exception:
        pass

    # payload-named scaffold files (/scaffold-custom writes into preview/)
    for f in _list_preview() - files_before:
        try:
            _pathlib.Path(f).unlink()
        except OSError:
            pass

    # ICM route log: truncate appended lines
    if route_size is not None and _ROUTE_LOG.exists():
        try:
            if _ROUTE_LOG.stat().st_size > route_size:
                with open(_ROUTE_LOG, 'r+b') as fh:
                    fh.truncate(route_size)
        except OSError:
            pass

    # whole-file JSON stores: restore the exact bytes we started with
    for jp, blob in _json_before.items():
        if blob is None:
            continue
        try:
            jp.write_bytes(blob)
        except OSError:
            pass
