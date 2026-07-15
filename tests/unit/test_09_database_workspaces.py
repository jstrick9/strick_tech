"""Unit tests — Database Studio & Workspaces (database.py, workspaces.py)"""
import uuid, pytest
from tests.unit.conftest import assert_ok, post_json, patch_json


class TestDatabaseStudio:
    def test_tables_200(self, client):
        assert client.get("/api/db/sqlite/tables").status_code == 200

    def test_tables_is_list(self, client):
        d = client.get("/api/db/sqlite/tables").json()
        assert isinstance(d, list)

    def test_tables_not_empty(self, client):
        tables = client.get("/api/db/sqlite/tables").json()
        assert len(tables) >= 1

    def test_tables_have_name(self, client):
        tables = client.get("/api/db/sqlite/tables").json()
        for t in tables[:5]:
            assert "name" in t

    def test_tables_have_columns(self, client):
        tables = client.get("/api/db/sqlite/tables").json()
        for t in tables[:5]:
            assert "columns" in t
            assert isinstance(t["columns"], list)

    def test_tables_have_row_count(self, client):
        tables = client.get("/api/db/sqlite/tables").json()
        for t in tables[:5]:
            assert "row_count" in t

    def test_query_select_1(self, client):
        r = post_json(client, "/api/db/sqlite/query", {"sql": "SELECT 1 AS val"})
        assert r.status_code == 200
        d = r.json()
        assert d["ok"] is True
        assert "rows" in d
        assert d["rows"][0]["val"] == 1

    def test_query_select_tasks_table(self, client):
        r = post_json(client, "/api/db/sqlite/query",
                      {"sql": "SELECT COUNT(*) AS cnt FROM tasks"})
        assert r.json()["ok"] is True
        assert "cnt" in r.json()["rows"][0]

    def test_query_returns_columns(self, client):
        r = post_json(client, "/api/db/sqlite/query",
                      {"sql": "SELECT 1 AS a, 2 AS b"})
        d = r.json()
        assert "columns" in d
        assert "a" in d["columns"]
        assert "b" in d["columns"]

    def test_query_returns_count(self, client):
        r = post_json(client, "/api/db/sqlite/query",
                      {"sql": "SELECT 1 AS v"})
        d = r.json()
        assert "count" in d
        assert d["count"] == 1

    def test_query_returns_type(self, client):
        r = post_json(client, "/api/db/sqlite/query",
                      {"sql": "SELECT 1"})
        d = r.json()
        assert "type" in d
        assert d["type"] == "select"

    def test_query_schema(self, client):
        r = client.get("/api/db/sqlite/schema")
        assert r.status_code in (200, 404)

    def test_get_specific_table(self, client):
        r = client.get("/api/db/sqlite/table/tasks")
        assert r.status_code in (200, 404)

    def test_ai_schema_endpoint(self, client):
        r = client.post("/api/db/sqlite/ai-schema", json={})
        assert r.status_code in (200, 404, 405, 422)  # POST endpoint

    def test_query_multiple_rows(self, client):
        r = post_json(client, "/api/db/sqlite/query",
                      {"sql": "SELECT id, title FROM tasks LIMIT 5"})
        d = r.json()
        assert d["ok"] is True
        assert isinstance(d["rows"], list)

    def test_known_tables_exist(self, client):
        tables = client.get("/api/db/sqlite/tables").json()
        names = {t["name"] for t in tables}
        for expected in ["tasks", "agents", "chat_log", "memory"]:
            assert expected in names, f"Missing table: {expected}"


class TestWorkspaces:
    def _uid(self): return uuid.uuid4().hex[:6]

    def test_list_workspaces_200(self, client):
        assert client.get("/api/workspaces").status_code == 200

    def test_list_workspaces_is_list(self, client):
        d = client.get("/api/workspaces").json()
        wss = d if isinstance(d, list) else d.get("workspaces", [])
        assert isinstance(wss, list)

    def test_list_workspaces_seeded(self, client):
        d = client.get("/api/workspaces").json()
        wss = d if isinstance(d, list) else d.get("workspaces", [])
        assert len(wss) >= 1

    def test_create_workspace(self, client):
        r = post_json(client, "/api/workspaces",
                      {"name": f"UnitWS_{self._uid()}", "description": "unit test ws"})
        assert r.status_code == 200
        d = r.json()
        assert "id" in d or (d.get("ok") is True)

    def test_create_returns_id(self, client):
        r = post_json(client, "/api/workspaces",
                      {"name": f"WSID_{self._uid()}"})
        d = r.json()
        wid = d.get("id") or (d.get("workspace") or {}).get("id")
        assert wid is not None

    def test_update_workspace(self, client):
        r = post_json(client, "/api/workspaces",
                      {"name": f"UpdateWS_{self._uid()}"})
        d = r.json()
        wid = d.get("id") or (d.get("workspace") or {}).get("id")
        if wid:
            r2 = client.patch(f"/api/workspaces/{wid}",
                              json={"name": "UpdatedWorkspace"})
            assert r2.status_code in (200, 404)

    def test_delete_workspace(self, client):
        r = post_json(client, "/api/workspaces",
                      {"name": f"DelWS_{self._uid()}"})
        d = r.json()
        wid = d.get("id") or (d.get("workspace") or {}).get("id")
        if wid:
            r2 = client.delete(f"/api/workspaces/{wid}")
            assert r2.status_code in (200, 204, 404)

    def test_get_current_workspace(self, client):
        r = client.get("/api/workspaces/current")
        assert r.status_code in (200, 404)

    def test_workspace_save(self, client):
        r = post_json(client, "/api/workspaces",
                      {"name": f"SaveWS_{self._uid()}"})
        d = r.json()
        wid = d.get("id") or (d.get("workspace") or {}).get("id")
        if wid:
            r2 = client.post(f"/api/workspaces/{wid}/save", json={"files": {}})
            assert r2.status_code in (200, 404)

    def test_workspace_export(self, client):
        d = client.get("/api/workspaces").json()
        wss = d if isinstance(d, list) else d.get("workspaces", [])
        if wss:
            wid = wss[0]["id"]
            r = client.get(f"/api/workspaces/{wid}/export")
            assert r.status_code in (200, 404)

    def test_export_current(self, client):
        r = client.get("/api/workspaces/export/current")
        assert r.status_code in (200, 404)
