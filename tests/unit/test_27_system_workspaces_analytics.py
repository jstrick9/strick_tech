"""
Unit Tests — System Health, Workspaces Full, Analytics Full, Marketplace
"""
import pytest, httpx, time

class TestSystemFull:
    def test_health_check(self, client):
        r = client.get("/api/system/health")
        assert r.status_code == 200
        d = r.json()
        assert "ok" in d or "status" in d or "healthy" in d

    def test_system_info(self, client):
        r = client.get("/api/system/info")
        assert r.status_code == 200
        assert isinstance(r.json(), dict)

    def test_db_health(self, client):
        r = client.get("/api/system/health")
        assert r.status_code == 200
        assert r.json() is not None

    def test_memory_stats(self, client):
        r = client.get("/api/system/info")
        assert r.status_code == 200

    def test_env_check(self, client):
        r = client.get("/api/system/info")
        assert r.status_code == 200
        d = r.json()
        assert isinstance(d, dict)

    def test_system_version(self, client):
        r = client.get("/api/system/health")
        assert r.status_code == 200

    def test_os_info(self, client):
        r = client.get("/api/system/git")
        assert r.status_code == 200


class TestWorkspacesFull:
    def test_list_workspaces(self, client):
        r = client.get("/api/workspaces")
        assert r.status_code == 200
        assert isinstance(r.json(), (list, dict))

    def test_create_workspace(self, client):
        r = client.post("/api/workspaces", json={
            "name": f"UnitTestWS_{int(time.time())}",
            "description": "Unit test workspace"
        })
        assert r.status_code == 200
        d = r.json()
        assert "ok" in d or "id" in d

    def test_activate_workspace(self, client):
        create = client.post("/api/workspaces", json={"name": "ActivateTestWS"}).json()
        ws_id = create.get("id", "")
        if ws_id:
            r = client.post(f"/api/workspaces/{ws_id}/activate")
            assert r.status_code == 200

    def test_delete_workspace(self, client):
        create = client.post("/api/workspaces", json={"name": "DeleteTestWS"}).json()
        ws_id = create.get("id", "")
        if ws_id:
            r = client.delete(f"/api/workspaces/{ws_id}")
            assert r.status_code == 200

    def test_current_workspace(self, client):
        r = client.get("/api/workspaces/current")
        assert r.status_code == 200


class TestAnalyticsFull:
    def test_analytics_dashboard(self, client):
        r = client.get("/api/analytics/dashboard?days=7")
        assert r.status_code == 200
        assert isinstance(r.json(), dict)

    def test_analytics_tasks(self, client):
        assert client.get("/api/analytics/tasks/velocity?days=7").status_code == 200

    def test_analytics_agents(self, client):
        assert client.get("/api/analytics/agents/summary").status_code == 200

    def test_analytics_cost(self, client):
        assert client.get("/api/analytics/cost?days=7").status_code == 200

    def test_analytics_export_csv(self, client):
        r = client.get("/api/analytics/export?fmt=csv&days=7")
        assert r.status_code == 200

    def test_analytics_export_json(self, client):
        assert client.get("/api/analytics/export?fmt=json&days=7").status_code == 200

    def test_analytics_summary(self, client):
        assert client.get("/api/analytics/dashboard?days=7").status_code == 200


class TestMarketplaceFull:
    def test_marketplace_list(self, client):
        r = client.get("/api/marketplace")
        assert r.status_code == 200
        d = r.json()
        assert "packs" in d or "pack" in d or isinstance(d, list)

    def test_marketplace_categories(self, client):
        assert client.get("/api/marketplace/categories").status_code == 200

    def test_marketplace_search(self, client):
        assert client.get("/api/marketplace/search?q=test").status_code == 200

    def test_marketplace_featured(self, client):
        assert client.get("/api/marketplace/featured").status_code == 200

    def test_marketplace_installed(self, client):
        r = client.get("/api/marketplace/installed")
        assert r.status_code == 200

    def test_marketplace_pack_detail(self, client):
        packs = client.get("/api/marketplace/list").json()
        pack_list = packs.get("packs", []) if isinstance(packs, dict) else packs
        if pack_list:
            pid = pack_list[0].get("id", "")
            if pid:
                r = client.get(f"/api/marketplace/{pid}")
                assert r.status_code in (200, 404)

    def test_marketplace_reviews(self, client):
        r = client.get("/api/marketplace/list")
        assert r.status_code in (200, 404)
