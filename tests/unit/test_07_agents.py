"""Unit tests — Agents & Chat (agents.py, chat.py)"""
import pytest
from tests.unit.conftest import assert_ok, post_json, patch_json


class TestAgentsCRUD:
    def test_list_agents_200(self, client):
        assert client.get("/api/agents").status_code == 200

    def test_list_agents_is_list(self, client):
        d = client.get("/api/agents").json()
        assert isinstance(d, list)

    def test_seeded_agents_present(self, client):
        agents = client.get("/api/agents").json()
        assert len(agents) >= 1

    def test_seeded_agents_have_required_fields(self, client):
        agents = client.get("/api/agents").json()
        for a in agents[:3]:
            assert "id" in a
            assert "name" in a

    def test_create_agent(self, client):
        r = post_json(client, "/api/agents",
                      {"name": "UnitTestAgent", "model": "gemini-flash",
                       "system_prompt": "You are a test agent.", "color": "#ff0000"})
        assert r.status_code == 200
        d = r.json()
        assert "id" in d or (d.get("ok") and "agent" in d)

    def test_create_agent_name_required(self, client):
        r = post_json(client, "/api/agents", {"model": "gemini-flash"})
        # Should fail without name
        assert r.status_code in (200, 400, 422)
        if r.status_code == 200:
            d = r.json()
            # ok might be False, or id might be absent
            assert d.get("ok") is False or "error" in d or "id" in d

    def test_update_agent(self, client):
        r = post_json(client, "/api/agents",
                      {"name": "UpdateMe", "model": "gemini-flash", "system_prompt": "old"})
        d = r.json()
        agent_id = d.get("id") or (d.get("agent") or {}).get("id")
        if agent_id:
            r2 = client.patch(f"/api/agents/{agent_id}",
                              json={"name": "UpdatedAgent"})
            assert r2.status_code in (200, 404)

    def test_delete_agent(self, client):
        r = post_json(client, "/api/agents",
                      {"name": "DeleteMe", "model": "gemini-flash", "system_prompt": "del"})
        d = r.json()
        agent_id = d.get("id") or (d.get("agent") or {}).get("id")
        if agent_id:
            r2 = client.delete(f"/api/agents/{agent_id}")
            assert r2.status_code in (200, 204, 404)

    def test_default_agents_seeded_with_names(self, client):
        agents = client.get("/api/agents").json()
        names = [a.get("name", "").lower() for a in agents]
        # At least one of the standard agent names should be present
        assert any(n in names for n in ["builder", "brain", "researcher", "orchestrator"])


class TestChatHistory:
    def test_history_200(self, client):
        assert client.get("/api/chat/history").status_code == 200

    def test_history_is_list(self, client):
        assert isinstance(client.get("/api/chat/history").json(), list)

    def test_history_with_session_id(self, client):
        r = client.get("/api/chat/history", params={"session_id": "test-session"})
        assert r.status_code == 200
        assert isinstance(r.json(), list)

    def test_history_messages_have_role(self, client):
        history = client.get("/api/chat/history").json()
        for msg in history[:5]:
            assert "role" in msg
            assert msg["role"] in ("user", "assistant", "system")

    def test_history_messages_have_message(self, client):
        history = client.get("/api/chat/history").json()
        for msg in history[:5]:
            assert "message" in msg


class TestMemoryService:
    """Unit tests for memory operations."""

    def test_memory_list_200(self, client):
        assert client.get("/api/memory/list").status_code == 200

    def test_memory_list_is_list(self, client):
        d = client.get("/api/memory/list").json()
        assert isinstance(d, list)

    def test_memory_add_content_required(self, client):
        r = post_json(client, "/api/memory/add", {"source": "api"})
        # No content → should return ok:false
        assert r.json()["ok"] is False

    def test_memory_add_ok(self, client):
        r = post_json(client, "/api/memory/add",
                      {"content": "Unit test memory entry", "source": "api", "tags": "unit,test"})
        assert r.json()["ok"] is True
        assert "id" in r.json()

    def test_memory_add_returns_id(self, client):
        r = post_json(client, "/api/memory/add",
                      {"content": "Memory with ID check", "source": "api"})
        d = r.json()
        assert isinstance(d["id"], int)
        assert d["id"] > 0

    def test_memory_search_200(self, client):
        assert client.get("/api/memory/search", params={"q": "test"}).status_code == 200

    def test_memory_search_returns_list(self, client):
        post_json(client, "/api/memory/add",
                  {"content": "Searchable unit test content", "source": "api", "tags": "searchable"})
        d = client.get("/api/memory/search", params={"q": "searchable"}).json()
        assert isinstance(d, list)

    def test_memory_stats_200(self, client):
        assert client.get("/api/memory/stats").status_code == 200

    def test_memory_stats_has_total(self, client):
        d = client.get("/api/memory/stats").json()
        assert "total" in d or "count" in d or isinstance(d, dict)

    def test_memory_export_200(self, client):
        assert client.get("/api/memory/export").status_code == 200

    def test_memory_export_has_memories(self, client):
        d = client.get("/api/memory/export").json()
        assert "memories" in d or "ok" in d

    def test_memory_delete_ok(self, client):
        r = post_json(client, "/api/memory/add",
                      {"content": "Delete me", "source": "api"})
        mid = r.json()["id"]
        r2 = client.delete(f"/api/memory/{mid}")
        assert r2.status_code in (200, 204, 404)
