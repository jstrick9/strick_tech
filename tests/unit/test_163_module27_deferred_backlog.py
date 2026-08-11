"""Module 27 — the deferred backlog.

Three items carried over by earlier passes, each deferred because it sat outside
the destination being reviewed at the time. Deferral is reasonable; leaving them
deferred forever is not, and all three turned out to be the same defect families
this review has been tracking.

1. SUPABASE HAD NO AUDIT TRAIL AT ALL (noted in doc 86, not addressed there).
   The SQLite half of Database Studio has 18 audit_sql() call sites — every
   query, insert, delete and schema change recorded with an outcome and a risk
   level. The Supabase half had ZERO. Verified live: after driving an insert
   through the endpoint, `SELECT COUNT(*) FROM audit WHERE action LIKE
   'supabase%'` returned 0. An operator reading the audit log sees a complete
   history of local activity and unbroken silence where the remote database was
   written to, with nothing indicating a second surface exists.

2. A REJECTED SUPABASE WRITE RETURNED HTTP 200, AND PUT THE ERROR UNDER `data`
   — the same key a successful insert uses for returned rows. Reproduced with a
   403 "new row violates row-level security policy": a caller reading `data`
   got a denial string where it expected records.

3. /api/project/share OPENED AN UNTRACKED PUBLIC TUNNEL. Second door #21.
   deploy.py keeps `_active_tunnel` so a tunnel can be listed and stopped, and
   module 19 hardened that path. This endpoint spawns the identical cloudflared
   quick-tunnel and recorded it nowhere. Verified: /share returned a live
   trycloudflare URL while GET /api/deploy/tunnel reported no tunnel running and
   /api/deploy/tunnel/stop had nothing to terminate. A public tunnel you cannot
   see is bad; one you cannot CLOSE is worse.

4. /api/project/review INVENTED A PASSING SCORE. It defaulted to `score: 75`
   with an empty issues list and every failure path fell back to it. Reproduced
   against a file containing `eval(user_input)` and
   `os.system("rm -rf " + user_input)`: score 75, issues [], ok true. That is
   the module-9 gitai defect (graded an unscanned tree 100/A) and the module-16
   eval defect (scored a malware response "fully safe") in a third place — and
   the UI rendered it as a green 75/100 above the words "✅ No issues!".
"""

from __future__ import annotations

import asyncio
import json
from unittest.mock import AsyncMock, patch

import httpx
import pytest

from backend.routers import codesearch as cs
from backend.routers import database as db
from backend.routers import deploy as dp
from backend.services.memory_db import get_conn


class _Req:
    def __init__(self, body):
        self._b = body

    async def json(self):
        return self._b


def _run(coro):
    return asyncio.get_event_loop().run_until_complete(coro)


def _body(resp):
    if hasattr(resp, 'body'):
        return json.loads(bytes(resp.body).decode())
    return resp


def _audit_count(prefix: str) -> int:
    con = get_conn()
    try:
        return con.execute("SELECT COUNT(*) FROM audit WHERE action LIKE ?", (prefix + '%',)).fetchone()[0]
    finally:
        con.close()


@pytest.fixture(autouse=True)
def _clean_audit():
    def purge():
        con = get_conn()
        try:
            con.execute("DELETE FROM audit WHERE action LIKE 'supabase%'")
            con.commit()
        finally:
            con.close()

    purge()
    yield
    purge()


@pytest.fixture
def supabase_env(monkeypatch):
    monkeypatch.setenv('SUPABASE_URL', 'https://probe.supabase.co')
    monkeypatch.setenv('SUPABASE_ANON_KEY', 'probe-key')


# ── 1 & 2. the Supabase surface ───────────────────────────────────────────────
def test_a_successful_supabase_insert_is_audited(supabase_env, monkeypatch):
    async def ok(self, url, *a, **k):
        return httpx.Response(201, json=[{'id': 1}], request=httpx.Request('POST', url))

    monkeypatch.setattr(httpx.AsyncClient, 'post', ok)
    before = _audit_count('supabase')
    r = _run(db.supabase_insert(_Req({'table': 't163', 'row': {'a': 1}})))
    assert r['ok'] is True
    assert _audit_count('supabase') == before + 1, 'a write to the remote database left no record'


def test_a_rejected_supabase_insert_is_also_audited(supabase_env, monkeypatch):
    """A refused write is exactly the event an operator needs to find later."""

    async def denied(self, url, *a, **k):
        return httpx.Response(403, text='row-level security', request=httpx.Request('POST', url))

    monkeypatch.setattr(httpx.AsyncClient, 'post', denied)
    before = _audit_count('supabase')
    _run(db.supabase_insert(_Req({'table': 't163', 'row': {'a': 1}})))
    assert _audit_count('supabase') == before + 1


def test_a_rejected_insert_does_not_return_http_200(supabase_env, monkeypatch):
    async def denied(self, url, *a, **k):
        return httpx.Response(403, text='row-level security', request=httpx.Request('POST', url))

    monkeypatch.setattr(httpx.AsyncClient, 'post', denied)
    r = _run(db.supabase_insert(_Req({'table': 't163', 'row': {'a': 1}})))
    assert getattr(r, 'status_code', 200) == 400


def test_a_rejected_insert_does_not_put_the_error_under_data(supabase_env, monkeypatch):
    """`data` is where a SUCCESSFUL insert returns rows."""

    async def denied(self, url, *a, **k):
        return httpx.Response(403, text='row-level security', request=httpx.Request('POST', url))

    monkeypatch.setattr(httpx.AsyncClient, 'post', denied)
    body = _body(_run(db.supabase_insert(_Req({'table': 't163', 'row': {'a': 1}}))))
    assert body['ok'] is False
    assert 'data' not in body
    assert 'row-level security' in body['error']


def test_a_supabase_query_is_audited(supabase_env, monkeypatch):
    async def ok(self, url, *a, **k):
        return httpx.Response(200, json=[{'id': 1}], request=httpx.Request('GET', url))

    monkeypatch.setattr(httpx.AsyncClient, 'get', ok)
    before = _audit_count('supabase')
    r = _run(db.supabase_query(_Req({'table': 't163'})))
    assert r['ok'] is True and r['count'] == 1
    assert _audit_count('supabase') == before + 1


def test_a_failed_supabase_query_reports_a_real_status(supabase_env, monkeypatch):
    async def missing(self, url, *a, **k):
        return httpx.Response(404, text='no such table', request=httpx.Request('GET', url))

    monkeypatch.setattr(httpx.AsyncClient, 'get', missing)
    r = _run(db.supabase_query(_Req({'table': 't163'})))
    assert getattr(r, 'status_code', 200) == 400
    assert _body(r)['ok'] is False


def test_a_supabase_table_name_cannot_reshape_the_url(supabase_env):
    """The table name lands in the request PATH; SQLite endpoints validate it."""
    r = _run(db.supabase_insert(_Req({'table': '../rpc/evil', 'row': {'a': 1}})))
    assert getattr(r, 'status_code', 200) == 400
    assert 'Invalid table name' in _body(r)['error']


def test_a_non_object_supabase_row_is_refused(supabase_env):
    r = _run(db.supabase_insert(_Req({'table': 't163', 'row': ['a']})))
    assert getattr(r, 'status_code', 200) == 400


def test_ai_setup_records_that_schema_sql_was_generated(supabase_env):
    with patch(
        'backend.services.llm.complete',
        new=AsyncMock(return_value={'ok': True, 'text': 'CREATE TABLE t163(id int);', 'tokens': 20}),
    ):
        before = _audit_count('supabase')
        r = _run(db.supabase_ai_setup(_Req({'description': 'a blog'})))
        assert r['ok'] is True
        assert r['executed'] is False, 'the response must say the SQL was not run'
        assert _audit_count('supabase') == before + 1


def test_ai_setup_reports_failure_when_no_sql_was_produced(supabase_env):
    with patch(
        'backend.services.llm.complete',
        new=AsyncMock(return_value={'ok': True, 'text': "I'm sorry, I can't.", 'tokens': 8}),
    ):
        r = _run(db.supabase_ai_setup(_Req({'description': 'a blog'})))
        assert getattr(r, 'status_code', 200) == 502
        assert _body(r)['ok'] is False


# ── 3. the untracked public tunnel ────────────────────────────────────────────
class _FakeProc:
    def __init__(self):
        self.returncode = None
        self.terminated = False

    def terminate(self):
        self.terminated = True
        self.returncode = 0

    class _Err:
        def __init__(self, line):
            self._line = line
            self._sent = False

        async def readline(self):
            if self._sent:
                await asyncio.sleep(0)
                return b''
            self._sent = True
            return self._line

    @property
    def stderr(self):
        return self._stderr


def _fake_cloudflared(url_line: bytes):
    proc = _FakeProc()
    proc._stderr = _FakeProc._Err(url_line)

    async def spawn(*a, **k):
        return proc

    return proc, spawn


@pytest.fixture(autouse=True)
def _reset_tunnel():
    saved = dict(dp._active_tunnel)
    dp._active_tunnel['proc'] = None
    dp._active_tunnel['url'] = None
    yield
    dp._active_tunnel.update(saved)


def test_share_registers_the_tunnel_it_opens(monkeypatch):
    import shutil

    proc, spawn = _fake_cloudflared(b'INF https://t163.trycloudflare.com |\n')
    monkeypatch.setattr(shutil, 'which', lambda n: '/usr/bin/cloudflared')
    monkeypatch.setattr(asyncio, 'create_subprocess_exec', spawn)

    r = _run(cs.share_project(_Req({})))
    assert r['public_url'] == 'https://t163.trycloudflare.com'
    assert dp._active_tunnel['url'] == r['public_url'], (
        'a public tunnel was opened and recorded nowhere — nothing could stop it'
    )
    assert dp._active_tunnel['proc'] is proc


def test_a_tunnel_opened_by_share_is_visible_to_the_deploy_pane(monkeypatch):
    import shutil

    proc, spawn = _fake_cloudflared(b'INF https://t163b.trycloudflare.com |\n')
    monkeypatch.setattr(shutil, 'which', lambda n: '/usr/bin/cloudflared')
    monkeypatch.setattr(asyncio, 'create_subprocess_exec', spawn)
    _run(cs.share_project(_Req({})))
    assert dp.tunnel_status_get()['active'] is True


def test_a_tunnel_opened_by_share_can_be_stopped(monkeypatch):
    import shutil

    proc, spawn = _fake_cloudflared(b'INF https://t163c.trycloudflare.com |\n')
    monkeypatch.setattr(shutil, 'which', lambda n: '/usr/bin/cloudflared')
    monkeypatch.setattr(asyncio, 'create_subprocess_exec', spawn)
    _run(cs.share_project(_Req({})))
    body = dp.stop_tunnel()
    assert body['ok'] is True
    assert proc.terminated is True
    assert dp._active_tunnel['url'] is None


def test_share_reuses_a_running_tunnel_instead_of_duplicating_it(monkeypatch):
    import shutil

    proc, spawn = _fake_cloudflared(b'INF https://t163d.trycloudflare.com |\n')
    monkeypatch.setattr(shutil, 'which', lambda n: '/usr/bin/cloudflared')
    monkeypatch.setattr(asyncio, 'create_subprocess_exec', spawn)
    first = _run(cs.share_project(_Req({})))

    def explode(*a, **k):
        raise AssertionError('a second cloudflared process was spawned')

    monkeypatch.setattr(asyncio, 'create_subprocess_exec', explode)
    second = _run(cs.share_project(_Req({})))
    assert second['tunnel_reused'] is True
    assert second['public_url'] == first['public_url']


def test_share_tells_the_user_how_to_close_the_tunnel(monkeypatch):
    import shutil

    proc, spawn = _fake_cloudflared(b'INF https://t163e.trycloudflare.com |\n')
    monkeypatch.setattr(shutil, 'which', lambda n: '/usr/bin/cloudflared')
    monkeypatch.setattr(asyncio, 'create_subprocess_exec', spawn)
    r = _run(cs.share_project(_Req({})))
    assert r['stop_endpoint'] == '/api/deploy/tunnel/stop'


def test_share_without_cloudflared_still_returns_lan_urls(monkeypatch):
    """No tunnel is not an error — the LAN URL is the fallback."""
    import shutil

    monkeypatch.setattr(shutil, 'which', lambda n: None)
    r = _run(cs.share_project(_Req({})))
    assert r['ok'] is True
    assert r['is_public'] is False
    assert r['lan_url']
    assert r['stop_endpoint'] is None


# ── 4. the reviewer must not invent a passing score ───────────────────────────
@pytest.fixture
def unsafe_file():
    from backend.routers.codesearch import PREVIEW_DIR

    PREVIEW_DIR.mkdir(parents=True, exist_ok=True)
    f = PREVIEW_DIR / 't163_unsafe.py'
    f.write_text('import os\ndef run(x):\n    eval(x)\n    os.system("rm -rf " + x)\n')
    yield 't163_unsafe.py'
    f.unlink(missing_ok=True)


def _review(filepath, llm_text):
    with patch(
        'backend.services.llm.complete',
        new=AsyncMock(return_value={'ok': True, 'text': llm_text, 'tokens': 10}),
    ):
        return _run(cs.review_code(_Req({'filepath': filepath, 'force': True})))


def test_an_unrun_reviewer_does_not_report_a_score(unsafe_file):
    r = _review(unsafe_file, "I'm sorry, I can't review that.")
    body = _body(r)
    assert body['score'] is None, 'a file nobody examined was given a numeric grade'
    assert body['reviewed'] is False
    assert body['ok'] is False


def test_an_unrun_review_returns_502(unsafe_file):
    assert getattr(_review(unsafe_file, 'prose only'), 'status_code', 200) == 502


def test_an_unrun_review_says_the_empty_issue_list_is_not_a_pass(unsafe_file):
    body = _body(_review(unsafe_file, 'prose only'))
    assert body['issues'] == []
    assert 'not a pass' in body['error'].lower() or 'NOT been assessed' in body['error']


def test_a_real_review_is_passed_through(unsafe_file):
    payload = json.dumps(
        {
            'score': 12,
            'issues': [{'line': 3, 'severity': 'error', 'message': 'eval on user input', 'fix': 'remove it'}],
            'summary': 'unsafe',
            'highlights': [],
        }
    )
    r = _review(unsafe_file, payload)
    assert r['ok'] is True
    assert r['reviewed'] is True
    assert r['score'] == 12
    assert len(r['issues']) == 1


def test_a_real_review_of_clean_code_still_scores_well(unsafe_file):
    """The fix must not make every review a failure."""
    payload = json.dumps({'score': 95, 'issues': [], 'summary': 'clean', 'highlights': ['clear naming']})
    r = _review(unsafe_file, payload)
    assert r['ok'] is True and r['score'] == 95


def test_a_missing_file_is_still_refused():
    r = _run(cs.review_code(_Req({'filepath': 't163_does_not_exist.py'})))
    assert _body(r)['ok'] is False
