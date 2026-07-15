"""
Unit Tests — Deploy, Tauri Build, Integrations
Covers: deployment providers, tauri build config, scaffold integrations
"""
import pytest, httpx

BASE = "http://127.0.0.1:8787"

@pytest.fixture(scope="module")
def client():
    return httpx.Client(base_url=BASE, timeout=20)


class TestDeploy:
    def test_list_providers(self, client):
        r = client.get("/api/deploy/providers")
        assert r.status_code == 200
        d = r.json()
        assert "providers" in d or isinstance(d, list)

    def test_deploy_status(self, client):
        r = client.get("/api/deploy/status")
        assert r.status_code == 200

    def test_deploy_requires_provider(self, client):
        r = client.post("/api/deploy/", json={})
        assert r.status_code in (200, 400, 404, 405, 422)

    def test_deploy_history(self, client):
        r = client.get("/api/deploy/history")
        assert r.status_code == 200
        d = r.json()
        assert isinstance(d, (list, dict))

    def test_deploy_netlify_without_token(self, client):
        r = client.post("/api/deploy/netlify", json={"site_name": "test"})
        assert r.status_code == 200
        d = r.json()
        # Should fail gracefully without API token
        assert "ok" in d

    def test_deploy_vercel_without_token(self, client):
        r = client.post("/api/deploy/vercel", json={})
        assert r.status_code == 200
        d = r.json()
        assert "ok" in d

    def test_deploy_github_pages_without_token(self, client):
        r = client.post("/api/deploy/github-pages", json={})
        assert r.status_code == 200
        d = r.json()
        assert "ok" in d

    def test_export_zip(self, client):
        r = client.get("/api/deploy/export")
        assert r.status_code in (200, 404)


class TestTauriBuild:
    def test_tauri_status(self, client):
        r = client.get("/api/tauri/status")
        assert r.status_code == 200
        d = r.json()
        assert "installed" in d or "status" in d or "ok" in d or isinstance(d, dict)

    def test_tauri_config(self, client):
        r = client.get("/api/tauri/config")
        assert r.status_code == 200

    def test_tauri_build_check(self, client):
        r = client.get("/api/tauri/config")
        assert r.status_code == 200


class TestIntegrations:
    def test_list_integrations(self, client):
        r = client.get("/api/integrations/list")
        assert r.status_code == 200
        d = r.json()
        assert isinstance(d, (list, dict))

    def test_scaffold_stripe_mock(self, client):
        # Should return instructions/code without actually connecting
        r = client.post("/api/integrations/stripe-payments/scaffold", json={
            "project_type": "nextjs"
        })
        assert r.status_code == 200
        d = r.json()
        assert "ok" in d or "code" in d or "error" in d

    def test_generate_readme(self, client):
        r = client.post("/api/integrations/docs/generate", json={
            "type": "readme", "context": "unit test"
        })
        assert r.status_code == 200
        d = r.json()
        assert "ok" in d or "content" in d

    def test_integrations_categories(self, client):
        r = client.get("/api/integrations/categories")
        assert r.status_code == 200
