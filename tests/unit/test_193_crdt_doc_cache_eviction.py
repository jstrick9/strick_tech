"""CRDT doc cache eviction: _docs must not retain every doc forever.

Measured live (r71 probe): 100 connectionless 1MB docs → +97MB RSS, never
returned. Nothing removed a _docs entry except an explicit DELETE — WS
disconnects persist the doc but keep it cached, and HTTP-created docs are
cached at creation. Every doc ever touched since process start stayed in
memory with its content, its op log (up to 5000 entries) and its undo/redo
stacks. The collab session registry got exactly this fix in #217.

Now idle docs are evicted (mirroring #217): connectionless + idle past the
TTL → persisted and dropped; over the cap → oldest connectionless first.
Everything is durable per-op (apply_and_broadcast writes op AND doc), so an
evicted doc reloads byte-identical from the DB.

All ageing is done by manipulating doc.last_active / calling the sweep
directly — no sleeps.
"""
import json
import threading

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient

from backend.routers import crdt as crdt_module
from backend.routers.crdt import router as crdt_router


@pytest.fixture()
def client():
    app = FastAPI()
    app.include_router(crdt_router)
    with TestClient(app) as c:
        crdt_module._docs.clear()
        yield c
        crdt_module._docs.clear()


def _make_doc(client, content="seed", title="t"):
    r = client.post("/api/crdt/docs", json={"title": title, "content": content})
    assert r.status_code == 200
    return r.json()["doc"]["id"]


def _age(doc_id, seconds=None):
    doc = crdt_module._docs[doc_id]
    doc.last_active -= (crdt_module._DOC_IDLE_TTL_SECONDS + 60) if seconds is None else seconds


class TestIdleDocEviction:
    def test_idle_connectionless_doc_is_evicted_and_reloads_identical(self, client):
        doc_id = _make_doc(client, content="hello world")
        client.post(f"/api/crdt/docs/{doc_id}/op", json={"op": [" big"], "revision": 0})
        before = client.get(f"/api/crdt/docs/{doc_id}").json()
        assert doc_id in crdt_module._docs

        _age(doc_id)
        crdt_module._evict_idle_docs()

        assert doc_id not in crdt_module._docs, "idle connectionless doc must be dropped"
        after = client.get(f"/api/crdt/docs/{doc_id}").json()
        assert after == before, "evicted doc must reload byte-identical from the DB"
        assert doc_id in crdt_module._docs, "GET reloads the doc into the cache"

    def test_sweep_is_wired_into_list_and_create(self, client):
        doc_id = _make_doc(client)
        _age(doc_id)
        client.get("/api/crdt/docs")  # list triggers the sweep
        assert doc_id not in crdt_module._docs
        doc_id2 = _make_doc(client)
        _age(doc_id2)
        client.post("/api/crdt/docs", json={"title": "x"})  # create triggers it too
        assert doc_id2 not in crdt_module._docs

    def test_connected_doc_is_never_evicted(self, client):
        doc_id = _make_doc(client, content="live")
        with client.websocket_connect(f"/api/crdt/docs/{doc_id}/ws") as ws:
            ws.send_text(json.dumps({"name": "held"}))
            json.loads(ws.receive_text())  # init
            _age(doc_id)
            crdt_module._evict_idle_docs()
            assert doc_id in crdt_module._docs, "a doc with a live connection must stay"

    def test_recently_active_doc_survives(self, client):
        doc_id = _make_doc(client)
        _age(doc_id, seconds=crdt_module._DOC_IDLE_TTL_SECONDS - 1)
        crdt_module._evict_idle_docs()
        assert doc_id in crdt_module._docs

    def test_http_op_refreshes_activity(self, client):
        """A doc edited only over HTTP (no connections) must not be swept
        out from under its author mid-session."""
        doc_id = _make_doc(client)
        _age(doc_id)  # old…
        client.post(f"/api/crdt/docs/{doc_id}/op", json={"op": ["!"], "revision": 0})  # …then used
        crdt_module._evict_idle_docs()
        assert doc_id in crdt_module._docs, "apply must refresh last_active"

    def test_get_doc_touch_protects_a_handshake_in_flight(self, client):
        """The WS handler loads the doc before adding a connection; the
        load itself must postpone eviction past the sweep."""
        doc_id = _make_doc(client)
        _age(doc_id)
        crdt_module._get_doc(doc_id)  # what the handshake does first
        crdt_module._evict_idle_docs()
        assert doc_id in crdt_module._docs

    def test_eviction_persists_before_dropping(self, client):
        """Belt-and-braces: whatever is in memory goes to the DB at eviction."""
        doc_id = _make_doc(client, content="original")
        crdt_module._docs[doc_id].content = "mutated outside apply"
        crdt_module._docs[doc_id].revision = 42
        _age(doc_id)
        crdt_module._evict_idle_docs()
        row = client.get(f"/api/crdt/docs/{doc_id}").json()
        assert row["content"] == "mutated outside apply"
        assert row["revision"] == 42

    def test_cap_evicts_oldest_connectionless_first(self, client, monkeypatch):
        # create FIRST, patch the cap after — otherwise the create-time sweep
        # itself (correctly) evicts while we are still setting up
        ids = [_make_doc(client, title=f"d{i}") for i in range(5)]
        monkeypatch.setattr(crdt_module, "_MAX_CACHED_DOCS", 3)
        # age all of them well UNDER the TTL so only the cap path can evict
        for i, doc_id in enumerate(ids):  # stagger: ids[0] oldest
            crdt_module._docs[doc_id].last_active -= 500 - i * 100
        crdt_module._evict_idle_docs()
        remaining = set(crdt_module._docs)
        assert remaining == set(ids[2:]), (
            f"cap must drop the OLDEST connectionless docs; kept {sorted(remaining)}"
        )
        assert len(crdt_module._docs) == 3


class TestColdLoadAtomicity:
    def test_concurrent_cold_loads_return_one_object(self, client):
        """Two threads missing the cache for the same id used to build two
        CRDTDoc objects and fork the document (divergent revision counters).
        The miss path is serialised; hits stay lock-free."""
        doc_id = _make_doc(client, content="cold")
        client.post(f"/api/crdt/docs/{doc_id}/op", json={"op": ["!"], "revision": 0})
        crdt_module._docs.pop(doc_id, None)  # force a cold load

        loaded = []
        barrier = threading.Barrier(8)

        def load():
            barrier.wait()
            loaded.append(crdt_module._get_doc(doc_id))

        threads = [threading.Thread(target=load) for _ in range(8)]
        for t in threads:
            t.start()
        for t in threads:
            t.join()
        assert len({id(d) for d in loaded}) == 1, "cold loads must all return the same object"
        assert loaded[0].revision == 1
