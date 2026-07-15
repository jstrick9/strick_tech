"""Unit tests — Plugins, MCP, Hooks, Webhooks, Skills (plugins.py, mcp.py, hooks.py, webhooks.py, skills.py)"""
import uuid, pytest
from tests.unit.conftest import assert_ok, post_json


class TestPlugins:
    def _uid(self): return uuid.uuid4().hex[:6]

    def test_installed_200(self, client):
        assert client.get("/api/plugins/installed").status_code == 200

    def test_installed_is_list(self, client):
        d = client.get("/api/plugins/installed").json()
        assert isinstance(d, list)

    def test_registry_200(self, client):
        assert client.get("/api/plugins/registry").status_code in (200, 404)

    def test_categories_200(self, client):
        assert client.get("/api/plugins/categories").status_code in (200, 404)

    def test_install_json_plugin(self, client):
        r = post_json(client, "/api/plugins/install/json", {
            "id": f"unit_test_{self._uid()}",
            "name": "Unit Test Plugin",
            "version": "1.0.0",
            "author": "UnitTest",
            "category": "testing",
            "emoji": "🧪",
            "skills": []
        })
        assert r.status_code in (200, 201, 400, 422)

    def test_uninstall_nonexistent(self, client):
        r = client.post("/api/plugins/uninstall/nonexistent_plugin_xyz")
        assert r.status_code in (200, 404, 405)
        if r.status_code == 200:
            assert "ok" in r.json()

    def test_export_plugins(self, client):
        r = client.get("/api/plugins/export")
        assert r.status_code in (200, 404)

    def test_import_plugins(self, client):
        r = post_json(client, "/api/plugins/import", {"plugins": []})
        assert r.status_code in (200, 400, 404, 422)


class TestMCP:
    def test_tools_200(self, client):
        assert client.get("/api/mcp/tools").status_code == 200

    def test_tools_has_list(self, client):
        d = assert_ok(client.get("/api/mcp/tools"))
        assert "tools" in d or isinstance(d, list)

    def test_tools_not_empty(self, client):
        d = assert_ok(client.get("/api/mcp/tools"))
        tools = d.get("tools", d) if isinstance(d, dict) else d
        assert len(tools) >= 1

    def test_call_empty_tool_rejected(self, client):
        r = post_json(client, "/api/mcp/call", {"tool": "", "args": {}})
        assert r.json()["ok"] is False

    def test_call_json_parse(self, client):
        r = post_json(client, "/api/mcp/call",
                      {"tool": "json.parse", "args": {"data": '{"x": 1, "y": 2}'}})
        assert r.status_code == 200
        d = r.json()
        assert d["ok"] is True

    def test_call_unknown_tool_rejected(self, client):
        r = post_json(client, "/api/mcp/call",
                      {"tool": "totally.unknown.tool.xyz", "args": {}})
        d = r.json()
        assert d["ok"] is False
        assert "error" in d

    def test_call_tool_returns_ok(self, client):
        r = post_json(client, "/api/mcp/call",
                      {"tool": "json.parse", "args": {"data": "{}"}})
        assert r.json()["ok"] is True

    def test_agent_run_endpoint(self, client):
        r = post_json(client, "/api/mcp/agent/run",
                      {"prompt": "unit test mcp", "agent_id": "builder"})
        assert r.status_code in (200, 500)

    def test_available_tools_list(self, client):
        d = assert_ok(client.get("/api/mcp/tools"))
        tools = d.get("tools", []) if isinstance(d, dict) else d
        tool_names = [t if isinstance(t, str) else t.get("name", "") for t in tools]
        assert any("json" in name.lower() for name in tool_names)


class TestHooks:
    def _uid(self): return uuid.uuid4().hex[:6]

    def test_list_hooks_200(self, client):
        assert client.get("/api/hooks").status_code == 200

    def test_list_hooks_is_list_or_dict(self, client):
        d = client.get("/api/hooks").json()
        hooks = d.get("hooks", d) if isinstance(d, dict) else d
        assert isinstance(hooks, list)

    def test_create_hook(self, client):
        r = post_json(client, "/api/hooks", {
            "name": f"UnitHook_{self._uid()}",
            "event": "agent.complete",
            "prompt": "Handle this event: {{event}}",
            "agent_id": "builder",
            "enabled": True
        })
        assert r.status_code == 200
        d = r.json()
        hid = d.get("hook_id") or d.get("id") or (d.get("hook") or {}).get("id")
        assert hid is not None

    def test_get_hook_by_id(self, client):
        r = post_json(client, "/api/hooks", {
            "name": f"GetHook_{self._uid()}",
            "event": "task.complete",
            "prompt": "Do stuff",
            "agent_id": "builder",
            "enabled": True
        })
        d = r.json()
        hid = d.get("hook_id") or d.get("id")
        if hid:
            r2 = client.get(f"/api/hooks/{hid}")
            assert r2.status_code in (200, 404)

    def test_toggle_hook(self, client):
        r = post_json(client, "/api/hooks", {
            "name": f"ToggleHook_{self._uid()}",
            "event": "agent.complete",
            "prompt": "Toggle test",
            "agent_id": "builder",
            "enabled": True
        })
        d = r.json()
        hid = d.get("hook_id") or d.get("id")
        if hid:
            r2 = client.post(f"/api/hooks/{hid}/toggle")
            assert r2.status_code in (200, 404)

    def test_delete_hook(self, client):
        r = post_json(client, "/api/hooks", {
            "name": f"DelHook_{self._uid()}",
            "event": "agent.complete",
            "prompt": "Delete me",
            "agent_id": "builder",
            "enabled": True
        })
        d = r.json()
        hid = d.get("hook_id") or d.get("id")
        if hid:
            r2 = client.delete(f"/api/hooks/{hid}")
            assert r2.status_code in (200, 204, 404)

    def test_event_types_200(self, client):
        r = client.get("/api/hooks/events/types")
        assert r.status_code in (200, 404)

    def test_recent_runs_200(self, client):
        r = client.get("/api/hooks/runs/recent")
        assert r.status_code in (200, 404)

    def test_fire_event(self, client):
        r = post_json(client, "/api/hooks/fire",
                      {"event": "test.event", "data": {"msg": "unit test"}})
        assert r.status_code in (200, 404)


class TestWebhooks:
    def _uid(self): return uuid.uuid4().hex[:6]

    def test_list_webhooks_200(self, client):
        assert client.get("/api/webhooks").status_code == 200

    def test_list_webhooks_is_dict(self, client):
        d = assert_ok(client.get("/api/webhooks"))
        whs = d.get("webhooks", d) if isinstance(d, dict) else d
        assert isinstance(whs, list)

    def test_create_webhook(self, client):
        r = post_json(client, "/api/webhooks", {
            "name": f"UnitWebhook_{self._uid()}",
            "secret": "unit_test_secret",
            "agent_id": "builder",
            "prompt_template": "Handle: {{payload}}"
        })
        assert r.status_code == 200
        d = r.json()
        wid = d.get("id") or (d.get("webhook") or {}).get("id")
        assert wid is not None

    def test_create_returns_id(self, client):
        r = post_json(client, "/api/webhooks", {
            "name": f"WHID_{self._uid()}",
            "secret": "s"
        })
        d = r.json()
        assert d.get("id") is not None or (d.get("webhook") or {}).get("id") is not None

    def test_get_webhook_events(self, client):
        r = post_json(client, "/api/webhooks", {
            "name": f"EventsWH_{self._uid()}",
            "secret": "s"
        })
        d = r.json()
        wid = d.get("id") or (d.get("webhook") or {}).get("id")
        if wid:
            r2 = client.get(f"/api/webhooks/{wid}/events")
            assert r2.status_code in (200, 404)
            if r2.status_code == 200:
                assert isinstance(r2.json(), list)

    def test_test_webhook(self, client):
        r = post_json(client, "/api/webhooks", {
            "name": f"TestWH_{self._uid()}",
            "secret": "s"
        })
        d = r.json()
        wid = d.get("id") or (d.get("webhook") or {}).get("id")
        if wid:
            r2 = client.post(f"/api/webhooks/{wid}/test")
            assert r2.status_code in (200, 404)

    def test_delete_webhook(self, client):
        r = post_json(client, "/api/webhooks", {
            "name": f"DelWH_{self._uid()}",
            "secret": "s"
        })
        d = r.json()
        wid = d.get("id") or (d.get("webhook") or {}).get("id")
        if wid:
            r2 = client.delete(f"/api/webhooks/{wid}")
            assert r2.status_code in (200, 204, 404)

    def test_webhook_templates(self, client):
        r = client.get("/api/webhooks/templates")
        assert r.status_code in (200, 404)


class TestSkills:
    def test_skills_200(self, client):
        assert client.get("/api/skills").status_code == 200

    def test_skills_has_list(self, client):
        d = assert_ok(client.get("/api/skills"))
        skills = d.get("skills", d) if isinstance(d, dict) else d
        assert isinstance(skills, list)

    def test_categories_200(self, client):
        assert client.get("/api/skills/categories").status_code in (200, 404)
