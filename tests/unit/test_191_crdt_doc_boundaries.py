"""CRDT doc boundaries: unknown doc ids must not fabricate phantom documents.

Discovered live in r70: every /api/crdt/docs/{doc_id}/... entry point called
_get_doc(), which lazily fabricates an in-memory doc for ANY id. A typo'd id
therefore got a working-looking phantom: the WS served init, acked every op,
and then every op INSERT failed against the crdt_ops → crdt_docs FOREIGN KEY
('crdt op persist failed: FOREIGN KEY constraint failed' in the server log
only) — the op log was silently lost while the client believed it was synced.
Content half-survived via the disconnect upsert; history did not.

Now every entry point proves the doc exists first: HTTP routes answer 404,
the socket closes 1008 'Unknown document' at the handshake (the same close
the auth gate uses). DELETE stays idempotent-200 by design.
"""
import json

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient

from backend.routers import crdt as crdt_module
from backend.routers.crdt import router as crdt_router

UNKNOWN = "no_such_doc_zz9p"


@pytest.fixture(scope="module")
def client():
    app = FastAPI()
    app.include_router(crdt_router)
    with TestClient(app) as c:
        yield c


@pytest.fixture()
def real_doc(client):
    r = client.post("/api/crdt/docs", json={"title": "boundary", "content": "seed"})
    assert r.status_code == 200, r.text
    doc_id = r.json()["doc"]["id"]
    yield doc_id
    client.delete(f"/api/crdt/docs/{doc_id}")


class TestUnknownDocIds:
    def test_get_doc_404(self, client):
        r = client.get(f"/api/crdt/docs/{UNKNOWN}")
        assert r.status_code == 404
        assert r.json()["error"] == "Document not found"

    def test_submit_op_404(self, client):
        r = client.post(f"/api/crdt/docs/{UNKNOWN}/op", json={"op": ["x"], "revision": 0})
        assert r.status_code == 404
        assert r.json()["ok"] is False

    def test_get_ops_404(self, client):
        assert client.get(f"/api/crdt/docs/{UNKNOWN}/ops").status_code == 404

    def test_history_404(self, client):
        assert client.get(f"/api/crdt/docs/{UNKNOWN}/history").status_code == 404

    def test_snapshot_404(self, client):
        assert client.post(f"/api/crdt/docs/{UNKNOWN}/snapshot").status_code == 404

    def test_restore_404(self, client):
        assert client.post(f"/api/crdt/docs/{UNKNOWN}/restore/0").status_code == 404

    def test_delete_stays_idempotent(self, client):
        """DELETE is documented-safe to retry: 200 with deleted=false, not 404."""
        r = client.delete(f"/api/crdt/docs/{UNKNOWN}")
        assert r.status_code == 200
        assert r.json()["deleted"] is False

    def test_websocket_rejects_unknown_doc_at_handshake(self, client):
        """The socket is the door the UI uses; a phantom must not be created
        for it. Expect the handshake to be refused, not an init frame."""
        from starlette.websockets import WebSocketDisconnect

        with pytest.raises(WebSocketDisconnect):
            with client.websocket_connect(f"/api/crdt/docs/{UNKNOWN}/ws"):
                pass

    def test_rejected_handshake_leaves_no_phantom_behind(self, client):
        """A rejected WS must not pollute the in-memory cache (a later GET
        would then answer 200 for a doc that was never created)."""
        crdt_module._docs.pop(UNKNOWN, None)  # prove the state is clean first
        with pytest.raises(Exception):
            with client.websocket_connect(f"/api/crdt/docs/{UNKNOWN}/ws"):
                pass
        assert UNKNOWN not in crdt_module._docs


class TestRealDocStillWorks:
    def test_all_routes_serve_a_created_doc(self, client, real_doc):
        assert client.get(f"/api/crdt/docs/{real_doc}").status_code == 200
        assert client.get(f"/api/crdt/docs/{real_doc}/ops").status_code == 200
        assert client.get(f"/api/crdt/docs/{real_doc}/history").status_code == 200
        assert client.post(f"/api/crdt/docs/{real_doc}/snapshot").status_code == 200

    def test_ws_op_acks_and_persists(self, client, real_doc):
        """The data-loss pin: an acked op on a REAL doc must reach the op
        log — that is exactly what failed for phantom docs."""
        with client.websocket_connect(f"/api/crdt/docs/{real_doc}/ws") as ws:
            ws.send_text(json.dumps({"name": "boundary"}))
            init = json.loads(ws.receive_text())
            assert init["type"] == "init"
            ws.send_text(json.dumps({"type": "op", "op": ["!"], "revision": 0}))
            ack = json.loads(ws.receive_text())
            assert ack["type"] == "ack"

        from backend.services.memory_db import get_conn

        con = get_conn()
        try:
            n = con.execute(
                "SELECT COUNT(*) FROM crdt_ops WHERE doc_id=?", (real_doc,)
            ).fetchone()[0]
        finally:
            con.close()
        assert n >= 1, "an acked op on a real doc must persist to the op log"
