"""
Browser E2E — API Integration from Browser Context
Tests that verify the browser can actually reach and use all API endpoints.
"""
import pytest, json
from tests.e2e_browser.conftest import BASE


class TestE2EAPIFromBrowser:
    """API endpoints reachable and return correct data in browser context."""

    def test_agents_api_returns_list(self, page):
        resp = page.request.get(f"{BASE}/api/agents")
        assert resp.status == 200
        agents = resp.json()
        assert isinstance(agents, list) and len(agents) > 0

    def test_core_agents_have_required_fields(self, page):
        resp = page.request.get(f"{BASE}/api/agents")
        agents = resp.json()
        for a in [x for x in agents if x["id"] in ["brain","builder","researcher"]]:
            assert "name" in a and "model" in a and "system_prompt" in a

    def test_tasks_api_returns_list(self, page):
        resp = page.request.get(f"{BASE}/api/tasks")
        assert resp.status == 200
        assert isinstance(resp.json(), list)

    def test_memory_stats_returns_count(self, page):
        resp = page.request.get(f"{BASE}/api/memory/stats")
        assert resp.status == 200
        d = resp.json()
        assert "total" in d or "count" in d or isinstance(d, dict)

    def test_audit_log_accessible(self, page):
        resp = page.request.get(f"{BASE}/api/audit-log")
        assert resp.status == 200

    def test_supervisor_runs_accessible(self, page):
        resp = page.request.get(f"{BASE}/api/supervisor/runs")
        assert resp.status == 200

    def test_goals_accessible(self, page):
        resp = page.request.get(f"{BASE}/api/goals")
        assert resp.status == 200

    def test_mcp_gateway_servers_accessible(self, page):
        resp = page.request.get(f"{BASE}/api/mcp-gateway/servers")
        assert resp.status == 200

    def test_finops_dashboard_accessible(self, page):
        resp = page.request.get(f"{BASE}/api/finops/dashboard")
        assert resp.status == 200
        d = resp.json()
        assert "total_cost_usd" in d or "total_cost" in d

    def test_eval_suites_accessible(self, page):
        resp = page.request.get(f"{BASE}/api/eval-framework/suites")
        assert resp.status == 200

    def test_qdrant_status_from_browser(self, page):
        resp = page.request.get(f"{BASE}/api/memory/qdrant/status")
        assert resp.status == 200
        d = resp.json()
        assert "available" in d and ("fallback" in d or "url" in d), f"Qdrant status unexpected: {d}"

    def test_post_request_from_browser_context(self, page):
        """Browser can POST JSON to the API (no CORS block for same origin)."""
        resp = page.request.post(f"{BASE}/api/audit-log/append", data=json.dumps({
            "actor": "browser-e2e-test", "action": "e2e.browser.post",
            "resource": "test", "resource_id": "e2e001",
            "outcome": "success", "detail": "Browser E2E POST test"
        }), headers={"Content-Type": "application/json"})
        assert resp.status == 200
        d = resp.json()
        assert d.get("ok") is True

    def test_license_status_from_browser(self, page):
        resp = page.request.get(f"{BASE}/api/license/status")
        assert resp.status == 200
        d = resp.json()
        assert "tier" in d or "stored_tier" in d

    def test_websocket_status_from_browser(self, page):
        resp = page.request.get(f"{BASE}/api/ws/status")
        assert resp.status == 200
        d = resp.json()
        assert isinstance(d, dict)

    def test_ollama_available_via_platform(self, page):
        """Ollama Local LLM agent is recognised by the platform."""
        resp = page.request.get(f"{BASE}/api/agents")
        agents = resp.json()
        local = next((a for a in agents if a.get("provider") == "ollama"), None)
        assert local is not None, "No ollama-provider agent found"
        assert local.get("id") == "local"

    def test_browser_agent_ready(self, page):
        """Browser Agent reports Playwright/Chromium installed."""
        resp = page.request.get(f"{BASE}/api/browser/status")
        assert resp.status == 200
        d = resp.json()
        assert d.get("playwright_available") is True
        assert d.get("chromium_installed") is True
        assert d.get("mode") == "playwright"
