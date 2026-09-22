"""WebSocket error frames: malformed input must be answered, never swallowed.

Verified live in r70 (probe: /tmp/probe70/ws_silence_probe.py) — before these
fixes, on the CRDT doc socket:
    invalid JSON frame       -> 0 frames, connection alive
    empty op list            -> 0 frames (the client waits for ack-or-error)
    missing op key           -> 0 frames
    non-numeric revision     -> 0 frames (ValueError hit a log-only catch)
    unknown message type     -> 0 frames
and on the collab session socket malformed JSON unwound the handler entirely,
leaving a ghost connection with nothing behind it.

The client contract (crdt docstring: every op gets an ack or an error frame;
test_134 already pins the refusal case for invalid ops) is now honoured for
every malformed shape on both sockets, and the loops survive bad frames.
"""
import json

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient

from backend.routers.collab import router as collab_router
from backend.routers.crdt import router as crdt_router


@pytest.fixture(scope="module")
def crdt_client():
    app = FastAPI()
    app.include_router(crdt_router)
    with TestClient(app) as c:
        yield c


@pytest.fixture(scope="module")
def collab_client():
    app = FastAPI()
    app.include_router(collab_router)
    with TestClient(app) as c:
        yield c


@pytest.fixture()
def doc_ws(crdt_client):
    """A connected, joined CRDT session on a real doc. Yields the ws."""
    r = crdt_client.post("/api/crdt/docs", json={"title": "errframes", "content": "seed"})
    doc_id = r.json()["doc"]["id"]
    with crdt_client.websocket_connect(f"/api/crdt/docs/{doc_id}/ws") as ws:
        ws.send_text(json.dumps({"name": "t"}))
        assert json.loads(ws.receive_text())["type"] == "init"
        yield ws
    crdt_client.delete(f"/api/crdt/docs/{doc_id}")


@pytest.fixture()
def collab_room(collab_client):
    """(session_id, joined ws) for the collab socket."""
    r = collab_client.post("/api/collab/sessions", json={})
    sess_id = r.json().get("session_id") or r.json().get("id")
    with collab_client.websocket_connect(f"/api/collab/sessions/{sess_id}/ws") as ws:
        ws.send_text(json.dumps({"name": "t1"}))
        assert json.loads(ws.receive_text())["type"] == "joined"
        yield sess_id, ws
    collab_client.post(f"/api/collab/sessions/{sess_id}/close")


def _recv_error(ws) -> dict:
    """The next frame must be an error frame — silence fails the test."""
    data = json.loads(ws.receive_text())
    assert data["type"] == "error", f"expected an error frame, got {data}"
    return data


class TestCrdtSocketErrorFrames:
    def test_invalid_json_is_answered(self, doc_ws):
        doc_ws.send_text("{not json at all")
        err = _recv_error(doc_ws)
        assert "malformed message" in err["error"]

    def test_non_dict_json_is_answered(self, doc_ws):
        doc_ws.send_text(json.dumps([1, 2, 3]))
        err = _recv_error(doc_ws)
        assert "JSON object" in err["error"]

    def test_empty_op_list_is_answered(self, doc_ws):
        doc_ws.send_text(json.dumps({"type": "op", "op": [], "revision": 0}))
        assert _recv_error(doc_ws)["error"] == "op required"

    def test_missing_op_key_is_answered(self, doc_ws):
        doc_ws.send_text(json.dumps({"type": "op", "revision": 0}))
        assert _recv_error(doc_ws)["error"] == "op required"

    def test_non_numeric_revision_is_answered(self, doc_ws):
        doc_ws.send_text(json.dumps({"type": "op", "op": [1], "revision": "abc"}))
        err = _recv_error(doc_ws)
        assert err["error"] == "revision must be a whole number"
        assert "revision" in err  # the server's current revision rides along

    def test_unknown_type_is_answered(self, doc_ws):
        doc_ws.send_text(json.dumps({"type": "bogus"}))
        err = _recv_error(doc_ws)
        assert "bogus" in err["error"]

    def test_loop_survives_bad_frames_and_acks_the_next_op(self, doc_ws):
        """The point of answering instead of dying: after a pile of garbage,
        a valid op must still get its ack."""
        doc_ws.send_text("{garbage")
        _recv_error(doc_ws)
        doc_ws.send_text(json.dumps({"type": "op", "op": [], "revision": 0}))
        _recv_error(doc_ws)
        doc_ws.send_text(json.dumps({"type": "op", "op": [1], "revision": "x"}))
        _recv_error(doc_ws)
        doc_ws.send_text(json.dumps({"type": "op", "op": ["!"], "revision": 0}))
        ack = json.loads(doc_ws.receive_text())
        assert ack["type"] == "ack"
        assert ack["revision"] >= 1


class TestCollabSocketErrorFrames:
    def test_invalid_json_is_answered(self, collab_room):
        _, ws = collab_room
        ws.send_text("{not json at all")
        err = _recv_error(ws)
        assert "malformed message" in err["error"]

    def test_non_dict_json_is_answered(self, collab_room):
        _, ws = collab_room
        ws.send_text(json.dumps([1, 2, 3]))
        _recv_error(ws)

    def test_unknown_type_is_answered(self, collab_room):
        _, ws = collab_room
        ws.send_text(json.dumps({"type": "bogus", "payload": {}}))
        err = _recv_error(ws)
        assert "bogus" in err["error"]

    def test_handler_survives_bad_frames(self, collab_client, collab_room):
        """Before the fix, one bad frame unwound the handler and the socket
        became a ghost. After a stream of garbage the session must still be
        processing: a second peer joining must reach us via broadcast."""
        sess_id, ws = collab_room
        ws.send_text("{garbage")
        _recv_error(ws)
        ws.send_text(json.dumps([None]))
        _recv_error(ws)
        ws.send_text(json.dumps({"type": "bogus"}))
        _recv_error(ws)
        with collab_client.websocket_connect(f"/api/collab/sessions/{sess_id}/ws") as ws2:
            ws2.send_text(json.dumps({"name": "t2"}))
            json.loads(ws2.receive_text())  # joined
            frame = json.loads(ws.receive_text())
            assert frame["type"] == "peer_joined", (
                f"session stopped processing after bad frames: {frame}"
            )
