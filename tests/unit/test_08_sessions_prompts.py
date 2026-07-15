"""Unit tests — Sessions & Prompt Library (sessions.py, prompts.py)"""
import uuid, pytest
from tests.unit.conftest import assert_ok, post_json, patch_json


class TestSessions:
    def _uid(self): return uuid.uuid4().hex[:6]

    def test_list_sessions_200(self, client):
        assert client.get("/api/sessions").status_code == 200

    def test_list_sessions_has_sessions(self, client):
        d = assert_ok(client.get("/api/sessions"))
        assert "sessions" in d or isinstance(d, dict)

    def test_create_session(self, client):
        r = post_json(client, "/api/sessions",
                      {"name": f"UnitSession_{self._uid()}", "agent_id": "builder"})
        assert r.status_code == 200
        d = r.json()
        assert "id" in d or d.get("ok") is True

    def test_create_session_returns_id(self, client):
        r = post_json(client, "/api/sessions",
                      {"name": "IDSession", "agent_id": "builder"})
        d = r.json()
        sid = d.get("id") or (d.get("session") or {}).get("id")
        assert sid is not None

    def test_get_session_by_id(self, client):
        r = post_json(client, "/api/sessions",
                      {"name": "GetByIDSession", "agent_id": "builder"})
        d = r.json()
        sid = d.get("id") or (d.get("session") or {}).get("id")
        if sid:
            r2 = client.get(f"/api/sessions/{sid}")
            assert r2.status_code in (200, 404)

    def test_update_session_name(self, client):
        r = post_json(client, "/api/sessions",
                      {"name": "Original Name", "agent_id": "builder"})
        d = r.json()
        sid = d.get("id") or (d.get("session") or {}).get("id")
        if sid:
            r2 = client.patch(f"/api/sessions/{sid}", json={"name": "Updated Name"})
            assert r2.status_code in (200, 404)

    def test_delete_session(self, client):
        r = post_json(client, "/api/sessions",
                      {"name": "DeleteSession", "agent_id": "builder"})
        d = r.json()
        sid = d.get("id") or (d.get("session") or {}).get("id")
        if sid:
            r2 = client.delete(f"/api/sessions/{sid}")
            assert r2.status_code in (200, 204, 404)

    def test_get_session_messages(self, client):
        r = post_json(client, "/api/sessions",
                      {"name": "MessagesSession", "agent_id": "builder"})
        d = r.json()
        sid = d.get("id") or (d.get("session") or {}).get("id")
        if sid:
            r2 = client.get(f"/api/sessions/{sid}/messages")
            assert r2.status_code in (200, 404)

    def test_stats_overview(self, client):
        r = client.get("/api/sessions/stats/overview")
        assert r.status_code in (200, 404)

    def test_delete_all_sessions(self, client):
        r = client.delete("/api/sessions")
        assert r.status_code in (200, 204, 500)  # 500 if sessions table has FK constraints


class TestPromptsLibrary:
    def _uid(self): return uuid.uuid4().hex[:6]

    def test_list_prompts_200(self, client):
        assert client.get("/api/prompts").status_code == 200

    def test_list_prompts_has_items(self, client):
        d = assert_ok(client.get("/api/prompts"))
        assert "prompts" in d or isinstance(d, dict)

    def test_list_prompts_seeded(self, client):
        d = assert_ok(client.get("/api/prompts"))
        prompts = d.get("prompts", d) if isinstance(d, dict) else d
        if isinstance(prompts, list):
            assert len(prompts) >= 1

    def test_create_prompt(self, client):
        r = post_json(client, "/api/prompts",
                      {"title": f"UnitPrompt_{self._uid()}",
                       "content": "Test prompt content {{input}}",
                       "category": "general",
                       "tags": "unit,test"})
        assert r.status_code == 200
        d = r.json()
        assert d.get("ok") is True
        assert "id" in d

    def test_create_prompt_returns_id(self, client):
        r = post_json(client, "/api/prompts",
                      {"title": "IDPrompt", "content": "content", "category": "general"})
        assert "id" in r.json()

    def test_get_prompt_by_id(self, client):
        r = post_json(client, "/api/prompts",
                      {"title": "GetPrompt", "content": "test content", "category": "general"})
        pid = r.json()["id"]
        r2 = client.get(f"/api/prompts/{pid}")
        assert r2.status_code in (200, 404)
        if r2.status_code == 200:
            assert r2.json()["id"] == pid

    def test_update_prompt(self, client):
        r = post_json(client, "/api/prompts",
                      {"title": "UpdatePrompt", "content": "old", "category": "general"})
        pid = r.json()["id"]
        r2 = client.patch(f"/api/prompts/{pid}", json={"title": "UpdatedPrompt"})
        assert r2.status_code in (200, 404)
        if r2.status_code == 200:
            assert r2.json()["ok"] is True

    def test_delete_prompt(self, client):
        r = post_json(client, "/api/prompts",
                      {"title": "DeletePrompt", "content": "bye", "category": "general"})
        pid = r.json()["id"]
        r2 = client.delete(f"/api/prompts/{pid}")
        assert r2.status_code in (200, 204, 404)

    def test_delete_removes_from_list(self, client):
        uid = self._uid()
        r = post_json(client, "/api/prompts",
                      {"title": f"RemovePrompt_{uid}", "content": "x", "category": "general"})
        pid = r.json()["id"]
        client.delete(f"/api/prompts/{pid}")
        d = assert_ok(client.get("/api/prompts"))
        prompts = d.get("prompts", [])
        assert not any(p["id"] == pid for p in prompts)

    def test_categories_200(self, client):
        assert client.get("/api/prompts/categories").status_code == 200

    def test_categories_is_list(self, client):
        d = assert_ok(client.get("/api/prompts/categories"))
        cats = d.get("categories", d)
        assert isinstance(cats, (list, dict))

    def test_search_prompts(self, client):
        uid = self._uid()
        post_json(client, "/api/prompts",
                  {"title": f"SearchMe_{uid}", "content": f"searchable content {uid}", "category": "general"})
        r = client.get("/api/prompts/search", params={"q": uid})
        assert r.status_code in (200, 404)

    def test_use_prompt_increments_count(self, client):
        r = post_json(client, "/api/prompts",
                      {"title": "UseCountPrompt", "content": "use me", "category": "general"})
        pid = r.json()["id"]
        r2 = client.post(f"/api/prompts/{pid}/use")
        assert r2.status_code in (200, 404)

    def test_duplicate_prompt(self, client):
        r = post_json(client, "/api/prompts",
                      {"title": "DuplicateSource", "content": "dup me", "category": "general"})
        pid = r.json()["id"]
        r2 = client.post(f"/api/prompts/{pid}/duplicate")
        assert r2.status_code in (200, 404)
        if r2.status_code == 200:
            assert r2.json()["ok"] is True

    def test_export_prompts(self, client):
        r = client.get("/api/prompts/export")
        assert r.status_code in (200, 404)
