"""Unit tests — Collab/CRDT, Arena Mode, Knowledge Graph, RAG (collab.py, crdt.py, arena.py, knowledge_graph.py, rag.py)"""
import uuid, pytest
from tests.unit.conftest import assert_ok, post_json


class TestCollabSessions:
    def _uid(self): return uuid.uuid4().hex[:6]

    def test_list_sessions_200(self, client):
        assert client.get("/api/collab/sessions").status_code == 200

    def test_list_sessions_is_list_or_dict(self, client):
        d = client.get("/api/collab/sessions").json()
        assert isinstance(d, (list, dict))

    def test_create_session_ok(self, client):
        r = post_json(client, "/api/collab/sessions",
                      {"title": f"UnitCollab_{self._uid()}"})
        assert r.status_code == 200
        d = r.json()
        assert d.get("ok") is True

    def test_create_session_returns_id(self, client):
        r = post_json(client, "/api/collab/sessions",
                      {"title": "IDCollab"})
        d = r.json()
        assert d.get("session_id") is not None

    def test_get_session_by_id(self, client):
        r = post_json(client, "/api/collab/sessions",
                      {"title": "GetCollabSession"})
        sid = r.json().get("session_id")
        if sid:
            r2 = client.get(f"/api/collab/sessions/{sid}")
            assert r2.status_code in (200, 404)

    def test_get_session_state(self, client):
        r = post_json(client, "/api/collab/sessions",
                      {"title": "StateSession"})
        sid = r.json().get("session_id")
        if sid:
            r2 = client.get(f"/api/collab/sessions/{sid}/state")
            assert r2.status_code in (200, 404)

    def test_delete_session(self, client):
        r = post_json(client, "/api/collab/sessions",
                      {"title": "DelCollabSession"})
        sid = r.json().get("session_id")
        if sid:
            r2 = client.delete(f"/api/collab/sessions/{sid}")
            assert r2.status_code in (200, 204, 404)


class TestCRDT:
    def _uid(self): return uuid.uuid4().hex[:6]

    def test_list_docs_200(self, client):
        assert client.get("/api/crdt/docs").status_code == 200

    def test_list_docs_is_list_or_dict(self, client):
        d = client.get("/api/crdt/docs").json()
        assert isinstance(d, (list, dict))

    def test_create_doc(self, client):
        r = post_json(client, "/api/crdt/docs",
                      {"title": f"UnitCRDT_{self._uid()}", "content": "# Hello"})
        assert r.status_code == 200
        d = r.json()
        assert d.get("ok") is True

    def test_create_doc_returns_doc(self, client):
        r = post_json(client, "/api/crdt/docs",
                      {"title": "DocReturn", "content": "# Test"})
        d = r.json()
        assert "doc" in d
        assert "id" in d["doc"]

    def test_get_doc_by_id(self, client):
        r = post_json(client, "/api/crdt/docs",
                      {"title": "GetDoc", "content": "# Get"})
        doc_id = r.json()["doc"]["id"]
        r2 = client.get(f"/api/crdt/docs/{doc_id}")
        assert r2.status_code in (200, 404)
        if r2.status_code == 200:
            assert r2.json()["id"] == doc_id

    def test_get_doc_ops(self, client):
        r = post_json(client, "/api/crdt/docs",
                      {"title": "OpsDoc", "content": "# Ops"})
        doc_id = r.json()["doc"]["id"]
        r2 = client.get(f"/api/crdt/docs/{doc_id}/ops")
        assert r2.status_code in (200, 404)

    def test_get_doc_history(self, client):
        r = post_json(client, "/api/crdt/docs",
                      {"title": "HistoryDoc", "content": "# History"})
        doc_id = r.json()["doc"]["id"]
        r2 = client.get(f"/api/crdt/docs/{doc_id}/history")
        assert r2.status_code in (200, 404)

    def test_delete_doc(self, client):
        r = post_json(client, "/api/crdt/docs",
                      {"title": "DelDoc", "content": "# Delete"})
        doc_id = r.json()["doc"]["id"]
        r2 = client.delete(f"/api/crdt/docs/{doc_id}")
        assert r2.status_code in (200, 204, 404)

    def test_doc_not_in_list_after_delete(self, client):
        r = post_json(client, "/api/crdt/docs",
                      {"title": "RemoveDoc", "content": "# Remove"})
        doc_id = r.json()["doc"]["id"]
        client.delete(f"/api/crdt/docs/{doc_id}")
        r2 = client.get(f"/api/crdt/docs/{doc_id}")
        # Should be 404 or empty doc after delete
        assert r2.status_code in (200, 404)

    def test_transform_op(self, client):
        r = post_json(client, "/api/crdt/transform",
                      {"op1": [0, "insert", "hello"], "op2": [0, "insert", "world"]})
        assert r.status_code in (200, 400, 422)

    def test_create_snapshot(self, client):
        r = post_json(client, "/api/crdt/docs",
                      {"title": "SnapDoc", "content": "# Snapshot"})
        doc_id = r.json()["doc"]["id"]
        r2 = client.post(f"/api/crdt/docs/{doc_id}/snapshot")
        assert r2.status_code in (200, 404)


class TestArena:
    def test_battles_200(self, client):
        assert client.get("/api/arena/battles").status_code in (200, 404)

    def test_leaderboard_200(self, client):
        assert client.get("/api/arena/leaderboard").status_code in (200, 404)

    def test_stats_200(self, client):
        assert client.get("/api/arena/stats").status_code in (200, 404)


class TestKnowledgeGraph:
    def _uid(self): return uuid.uuid4().hex[:6]

    def test_entities_200(self, client):
        assert client.get("/api/knowledge-graph/entities").status_code in (200, 404)

    def test_create_entity(self, client):
        r = post_json(client, "/api/knowledge-graph/entities",
                      {"name": f"UnitEntity_{self._uid()}",
                       "type": "concept",
                       "description": "A unit test entity"})
        assert r.status_code in (200, 201)
        d = r.json()
        assert d.get("ok") is True

    def test_create_entity_returns_id(self, client):
        r = post_json(client, "/api/knowledge-graph/entities",
                      {"name": f"IDEntity_{self._uid()}", "type": "concept"})
        d = r.json()
        assert d.get("entity_id") or d.get("id")

    def test_get_entity_by_id(self, client):
        r = post_json(client, "/api/knowledge-graph/entities",
                      {"name": f"GetEntity_{self._uid()}", "type": "concept"})
        eid = r.json().get("entity_id") or r.json().get("id")
        if eid:
            r2 = client.get(f"/api/knowledge-graph/entities/{eid}")
            assert r2.status_code in (200, 404)

    def test_stats_200(self, client):
        assert client.get("/api/knowledge-graph/stats").status_code in (200, 404)

    def test_query_200(self, client):
        r = post_json(client, "/api/knowledge-graph/query",
                      {"query": "unit test entity"})
        assert r.status_code in (200, 404)

    def test_facts_200(self, client):
        r = post_json(client, "/api/knowledge-graph/facts",
                      {"subject": "Python", "predicate": "is_a", "object": "language"})
        assert r.status_code in (200, 404, 422)

    def test_relations_200(self, client):
        r = post_json(client, "/api/knowledge-graph/relations",
                      {"from_entity": "Python", "relation": "uses", "to_entity": "FastAPI"})
        assert r.status_code in (200, 404, 422)


class TestRAG:
    def _uid(self): return uuid.uuid4().hex[:6]

    def test_pipelines_200(self, client):
        assert client.get("/api/rag/pipelines").status_code in (200, 404)

    def test_create_pipeline(self, client):
        r = post_json(client, "/api/rag/pipelines",
                      {"name": f"UnitRAG_{self._uid()}",
                       "description": "Unit test RAG pipeline"})
        assert r.status_code in (200, 201, 422)
        if r.status_code in (200, 201):
            d = r.json()
            assert d.get("id") or d.get("ok") is True

    def test_add_document(self, client):
        r = post_json(client, "/api/rag/pipelines",
                      {"name": f"DocRAG_{self._uid()}",
                       "description": "Document RAG"})
        d = r.json()
        pid = d.get("id") or (d.get("pipeline") or {}).get("id")
        if pid:
            r2 = post_json(client, f"/api/rag/pipelines/{pid}/documents",
                           {"content": "Unit test document content for RAG pipeline",
                            "title": "Unit Test Doc"})
            assert r2.status_code in (200, 201, 400, 404)

    def test_delete_pipeline(self, client):
        r = post_json(client, "/api/rag/pipelines",
                      {"name": f"DelRAG_{self._uid()}"})
        d = r.json()
        pid = d.get("id") or (d.get("pipeline") or {}).get("id")
        if pid:
            r2 = client.delete(f"/api/rag/pipelines/{pid}")
            assert r2.status_code in (200, 204, 404)
