"""A2A surface robustness + record correctness (round 28 journey finds).

WHAT THIS LOCKS IN
──────────────────
1. Non-object JSON bodies are answered, never crash. request.json() accepts
   ANY JSON value (string, number, list, bool, null); every /a2a/ and
   /api/a2a/ handler assumed a dict and dereferenced .get/.items on it, so
   a client sending e.g. a bare JSON string got an AttributeError traceback
   and a 500 with a non-JSON-RPC body. Verified live before the fix.

2. Stored task metadata / push_config actually surface. _load_task and the
   tasks/list loop shared `json.loads(v or '[]' if ... else '{}')` — Python
   binds the conditional looser than `or`, so metadata and push_config
   ALWAYS decoded to a literal '{}' and the stored JSON was silently
   discarded: task detail, tasks/get and tasks/list showed empty objects
   forever, no matter what was written.

3. Loopback delegation completes: the delegate no longer sends its local
   tracking id as the protocol task id (the receiver's duplicate-id guard
   rejected our own outbound row when the remote is co-hosted on this same
   database — the round trip could never finish), and the remote's id is
   linked back into the local record's metadata.

The CSRF boundary itself (the /a2a/ exemption) is enforced by middleware
that deliberately skips enforcement under PYTEST_CURRENT_TEST, so no
in-process test can observe it — it is locked in by
tests/security/test_sec_12_a2a_protocol_door.py against a live server.
"""
from __future__ import annotations

import uuid


def _uniq(prefix='zza2a'):
    return f'{prefix}_{uuid.uuid4().hex[:10]}'


def _csrf(client):
    """CSRF header for the API-write tests (register/delegate/delete)."""
    tok = client.get('/api/security/csrf-token').json().get('csrf_token', '')
    return {'X-CSRF-Token': tok}


# ── 1. Non-object JSON bodies ────────────────────────────────────────────────

class TestNonObjectJsonBodies:
    """Valid JSON that is not an object must get a 400, never a 500.

    Pre-fix: AttributeError ('str' object has no attribute 'get') raised
    through the middleware stack, logged as a traceback, answered with a
    500 whose body was not even JSON-RPC.
    """

    def test_jsonrpc_door_string(self, client):
        r = client.post('/a2a/researcher', content=b'"jsonrpc=2.0"',
                        headers={'Content-Type': 'application/json'})
        assert r.status_code == 400, r.text[:200]
        body = r.json()
        assert body.get('jsonrpc') == '2.0'
        assert body['error']['code'] == -32600

    def test_jsonrpc_door_list(self, client):
        r = client.post('/a2a/researcher', content=b'[1,2,3]',
                        headers={'Content-Type': 'application/json'})
        assert r.status_code == 400
        assert r.json()['error']['code'] == -32600

    def test_jsonrpc_door_null(self, client):
        r = client.post('/a2a/researcher', content=b'null',
                        headers={'Content-Type': 'application/json'})
        assert r.status_code == 400
        assert r.json()['error']['code'] == -32600

    def test_form_encoded_body_is_a_parse_error(self, client):
        # An HTML form cannot produce a JSON body — this is also what makes
        # the /a2a/ CSRF exemption structurally safe.
        r = client.post('/a2a/researcher', content=b'jsonrpc=2.0&method=tasks/send',
                        headers={'Content-Type': 'application/x-www-form-urlencoded'})
        assert r.status_code == 400
        assert r.json()['error']['code'] == -32700

    def test_register_agent_rejects_a_json_string(self, client):
        r = client.post('/api/a2a/agents', content=b'"oops"',
                        headers={'Content-Type': 'application/json'})
        assert r.status_code == 400, r.text[:200]
        assert r.json().get('ok') is False

    def test_update_agent_rejects_a_json_string(self, client):
        r = client.patch(f'/api/a2a/agents/{_uniq("ext")}', content=b'"oops"',
                         headers={'Content-Type': 'application/json'})
        assert r.status_code == 400, r.text[:200]
        assert r.json().get('ok') is False

    def test_delegate_rejects_a_json_string(self, client):
        r = client.post('/api/a2a/delegate', content=b'"oops"',
                        headers={'Content-Type': 'application/json'})
        assert r.status_code == 400, r.text[:200]
        assert r.json().get('ok') is False


# ── 2. Stored metadata / push_config must surface ────────────────────────────

class TestStoredMetadataSurfaces:
    """The `or '[]' if ... else '{}'` precedence bug always decoded
    metadata/push_config to a literal '{}' — stored JSON was silently
    discarded by _load_task and the tasks/list loop."""

    @staticmethod
    def _insert_task(tid: str):
        from backend.routers.a2a import _get_conn, _now
        con = _get_conn()
        try:
            con.execute(
                """
                INSERT INTO a2a_tasks
                  (task_id,caller_agent_id,caller_endpoint,target_agent_id,state,
                   messages,artifacts,metadata,push_config,session_id,created_at,updated_at)
                VALUES (?,?,?,?,?,?,?,?,?,?,?,?)
                """,
                (tid, 'zz_test', '', 'researcher', 'completed', '[]', '[]',
                 '{"zz_meta": 42, "tag": "surfaced"}', '{"zz_push": true}',
                 '', _now(), _now()),
            )
            con.commit()
        finally:
            con.close()

    @staticmethod
    def _delete_task(tid: str):
        from backend.routers.a2a import _get_conn
        con = _get_conn()
        try:
            con.execute('DELETE FROM a2a_tasks WHERE task_id=?', (tid,))
            con.execute('DELETE FROM a2a_call_log WHERE task_id=?', (tid,))
            con.commit()
        finally:
            con.close()

    def test_load_task_parses_metadata_and_push_config(self):
        from backend.routers.a2a import _load_task
        tid = f'task_zz{uuid.uuid4().hex[:12]}'
        self._insert_task(tid)
        try:
            t = _load_task(tid)
            assert t is not None
            assert t['metadata'] == {'zz_meta': 42, 'tag': 'surfaced'}, (
                f'stored metadata discarded: {t["metadata"]!r}'
            )
            assert t['push_config'] == {'zz_push': True}, (
                f'stored push_config discarded: {t["push_config"]!r}'
            )
        finally:
            self._delete_task(tid)

    def test_task_detail_api_surfaces_them(self, client):
        tid = f'task_zz{uuid.uuid4().hex[:12]}'
        self._insert_task(tid)
        try:
            r = client.get(f'/api/a2a/tasks/{tid}')
            assert r.status_code == 200, r.text[:200]
            task = r.json()['task']
            assert task['metadata'] == {'zz_meta': 42, 'tag': 'surfaced'}
            assert task['push_config'] == {'zz_push': True}
        finally:
            self._delete_task(tid)

    def test_jsonrpc_tasks_get_surfaces_metadata(self, client):
        tid = f'task_zz{uuid.uuid4().hex[:12]}'
        self._insert_task(tid)
        try:
            r = client.post('/a2a/researcher', json={
                'jsonrpc': '2.0', 'id': 1, 'method': 'tasks/get', 'params': {'id': tid},
            })
            assert r.status_code == 200, r.text[:200]
            assert r.json()['result']['metadata'] == {'zz_meta': 42, 'tag': 'surfaced'}
        finally:
            self._delete_task(tid)

    def test_jsonrpc_tasks_list_surfaces_metadata(self, client):
        tid = f'task_zz{uuid.uuid4().hex[:12]}'
        self._insert_task(tid)
        try:
            r = client.post('/a2a/researcher', json={
                'jsonrpc': '2.0', 'id': 2, 'method': 'tasks/list', 'params': {},
            })
            assert r.status_code == 200, r.text[:200]
            mine = [t for t in r.json()['result']['tasks'] if t['id'] == tid]
            assert mine, 'inserted task missing from tasks/list'
            assert mine[0]['metadata'] == {'zz_meta': 42, 'tag': 'surfaced'}
        finally:
            self._delete_task(tid)


# ── 3. Loopback delegation ───────────────────────────────────────────────────

class TestLoopbackDelegateIdDecoupling:
    """The delegate must not send its local tracking id as the protocol task
    id: a2a_tasks.task_id is the PRIMARY KEY of THIS database, and when the
    registered remote is co-hosted on it (registering our own /a2a/{agent}
    is a supported flow), the receiver's duplicate-id guard rejected our own
    outbound row — the round trip could never complete."""

    def test_delegate_sends_no_task_id_and_links_the_remote_one(self, client, monkeypatch):
        import json as _json
        from backend.routers import a2a as a2a_mod

        captured: dict = {}

        async def fake_remote(agent_id, endpoint, method, params,
                              auth_type='none', auth_config=None, self_base=''):
            captured['params'] = params
            captured['method'] = method
            return {
                'ok': True,
                'response': {
                    'jsonrpc': '2.0', 'id': 'x',
                    'result': {'id': 'task_ZZREMOTE', 'status': {'state': 'completed'}},
                },
                'duration_ms': 5,
            }

        monkeypatch.setattr(a2a_mod, '_delegate_to_remote', fake_remote)

        h = _csrf(client)
        reg = client.post('/api/a2a/agents', json={
            'name': _uniq('zz Agent'), 'a2a_url': 'http://127.0.0.1:8787/a2a/researcher',
            'description': 'probe',
        }, headers=h)
        assert reg.status_code == 200, reg.text[:200]
        agent_id = reg.json()['agent_id']
        try:
            r = client.post('/api/a2a/delegate', json={
                'agent_id': agent_id, 'message': 'zz delegate probe',
                'metadata': {'probe': 'zz'},
            }, headers=h)
            assert r.status_code == 200, r.text[:200]
            d = r.json()
            assert d['ok'] is True, d
            local_id = d['task_id']

            # The protocol task we sent carries NO id of ours.
            assert captured['method'] == 'tasks/send'
            assert 'id' not in captured['params'], (
                f"delegate sent its tracking id as the protocol id: "
                f"{captured['params'].get('id')!r} — loopback delegation will "
                "collide with the local tracking row again"
            )

            # Local tracking row completed, with the remote's id linked in.
            t = client.get(f'/api/a2a/tasks/{local_id}').json()['task']
            assert t['state'] == 'completed', t['state']
            assert t['metadata'].get('remote_task_id') == 'task_ZZREMOTE', t['metadata']
            assert t['metadata'].get('probe') == 'zz', (
                f"caller-supplied metadata lost: {t['metadata']!r}"
            )
            assert local_id != 'task_ZZREMOTE'
        finally:
            client.delete(f'/api/a2a/agents/{agent_id}', headers=h)
