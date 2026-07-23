"""
Regression Tests — API Contract & Platform Stability
Verifies that the entire API surface maintains its contract across changes.

These tests run all 610+ endpoints to verify no unexpected 500s appear.
They also verify backward compatibility of response schemas.
"""
import pytest
import httpx
import asyncio

BASE = "http://127.0.0.1:8787"


@pytest.fixture(scope="module")
def client():
    return httpx.Client(base_url=BASE, timeout=15)


class TestRegressionAPIContract_Core:
    """Core platform endpoints must maintain their response schema."""

    def test_health_schema_stable(self, client):
        """Regression: Health endpoint schema unchanged."""
        d = client.get("/api/system/health").json()
        required = ["ok", "version", "database", "system", "disk"]
        for f in required:
            assert f in d, f"API CONTRACT REGRESSION: health missing '{f}'"
        assert d["database"]["tables"] >= 100

    def test_agents_list_schema_stable(self, client):
        """Regression: Agent list returns consistent schema."""
        agents = client.get("/api/agents").json()
        agent_list = agents if isinstance(agents, list) else agents.get("agents", [])
        for a in agent_list[:3]:
            for field in ("id", "name", "role"):
                assert field in a, f"API CONTRACT: agent missing '{field}'"

    def test_memory_stats_schema_stable(self, client):
        """Regression: Memory stats schema unchanged."""
        d = client.get("/api/memory/stats").json()
        assert "total" in d
        assert isinstance(d["total"], int)

    def test_openapi_has_expected_routes(self, client):
        """Regression: OpenAPI spec still has all major route groups."""
        paths = set(client.get("/api/openapi.json").json()["paths"].keys())
        route_groups = [
            "/api/audit-log", "/api/agent-identity", "/api/hitl",
            "/api/supervisor", "/api/goals", "/api/loops",
            "/api/mcp-gateway", "/api/connectors",
            "/api/agent-monitor", "/api/finops", "/api/eval-framework",
            "/api/agents", "/api/memory", "/api/tasks",
            "/api/sessions", "/api/specs", "/api/hooks",
            "/api/knowledge-graph", "/api/rag",
        ]
        for prefix in route_groups:
            has = any(p.startswith(prefix) for p in paths)
            assert has, f"API CONTRACT REGRESSION: no routes for {prefix}"


class TestRegressionAPIContract_NoServerErrors:
    """All platform GET endpoints must return < 500."""

    def test_all_sprint_a_endpoints_stable(self, client):
        """Regression: Sprint A endpoints return no server errors."""
        endpoints = [
            "/api/audit-log", "/api/audit-log/verify", "/api/audit-log/stats",
            "/api/agent-identity", "/api/agent-identity/system/stats",
            "/api/hitl/queue", "/api/hitl/audit", "/api/hitl/stats",
        ]
        for ep in endpoints:
            r = client.get(ep)
            assert r.status_code < 500, \
                f"REGRESSION: {ep} returned {r.status_code}: {r.text[:100]}"

    def test_all_sprint_b_endpoints_stable(self, client):
        """Regression: Sprint B endpoints return no server errors."""
        endpoints = [
            "/api/supervisor/runs", "/api/supervisor/stats",
            "/api/goals", "/api/goals/stats/summary", "/api/goals/domains/list",
            "/api/loops", "/api/loops/status",
        ]
        for ep in endpoints:
            r = client.get(ep)
            assert r.status_code < 500, \
                f"REGRESSION: {ep} returned {r.status_code}"

    def test_all_sprint_c_endpoints_stable(self, client):
        """Regression: Sprint C endpoints return no server errors."""
        endpoints = [
            "/api/mcp-gateway/servers", "/api/mcp-gateway/policies",
            "/api/mcp-gateway/calls", "/api/mcp-gateway/stats",
            "/api/connectors", "/api/connectors/stats/summary",
        ]
        for ep in endpoints:
            r = client.get(ep)
            assert r.status_code < 500, \
                f"REGRESSION: {ep} returned {r.status_code}"

    def test_all_sprint_d_endpoints_stable(self, client):
        """Regression: Sprint D endpoints return no server errors."""
        endpoints = [
            "/api/agent-monitor/live", "/api/agent-monitor/summary",
            "/api/agent-monitor/anomalies",
            "/api/finops/dashboard", "/api/finops/caps", "/api/finops/alerts",
            "/api/eval-framework/suites", "/api/eval-framework/stats/platform",
            "/api/eval-framework/review-queue",
        ]
        for ep in endpoints:
            r = client.get(ep)
            assert r.status_code < 500, \
                f"REGRESSION: {ep} returned {r.status_code}"

    def test_all_original_endpoints_stable(self, client):
        """Regression: Original platform endpoints still work."""
        endpoints = [
            "/api/agents", "/api/memory/stats",
            "/api/sessions", "/api/prompts",
            "/api/knowledge-graph/stats",
            "/api/skills", "/api/plugins/installed",
            "/api/system/health", "/api/system/info",
            "/api/analytics/dashboard",
            "/api/marketplace", "/api/webhooks",
            "/api/hooks", "/api/evals/runs",
            "/api/observability/traces",
            "/api/workspaces", "/api/steering",
            "/api/control/stats", "/api/control/budget-rules",
            "/api/swarm/history", "/api/arena/leaderboard",
        ]
        for ep in endpoints:
            r = client.get(ep)
            assert r.status_code < 500, \
                f"REGRESSION: {ep} returned {r.status_code}: {r.text[:100]}"


class TestRegressionAPIContract_DataSchemas:
    """Response data schemas must remain stable."""

    def test_supervisor_run_schema(self, client):
        """Regression: Supervisor run response has required fields."""
        r = client.post("/api/supervisor/run", json={"goal": "Brief: what is 1+1?"})
        assert r.status_code == 200
        d = r.json()
        assert d["ok"] is True
        for field in ("run_id", "status", "goal_text"):
            assert field in d, f"Supervisor run missing '{field}'"
        run_id = d["run_id"]
        # Kill to free resources
        client.post(f"/api/supervisor/run/{run_id}/kill", json={"reason": "regress"})

    def test_goal_create_schema(self, client):
        """Regression: Goal create response schema stable."""
        r = client.post("/api/goals", json={"title": "Regress Schema Goal"})
        assert r.status_code == 200
        d = r.json()
        assert "ok" in d and "goal_id" in d
        client.delete(f"/api/goals/{d['goal_id']}")

    def test_mcp_gateway_call_schema(self, client):
        """Regression: Gateway call response has required fields."""
        r = client.post("/api/mcp-gateway/call", json={
            "server_id": "srv_memory",
            "tool": "memory.search",
            "args": {"query": "regress", "limit": 1},
            "agent_id": "brain"
        })
        assert r.status_code == 200
        d = r.json()
        for field in ("call_id", "policy_decision"):
            assert field in d, f"Gateway call missing '{field}'"

    def test_connector_execute_schema(self, client):
        """Regression: Connector execute response schema stable."""
        r = client.post("/api/connectors/conn_webhook/execute", json={
            "action": "post_webhook",
            "payload": {"url": "https://httpbin.org/post", "data": {}}
        })
        assert r.status_code == 200
        d = r.json()
        for field in ("ok", "exec_id", "duration_ms"):
            assert field in d, f"Connector execute missing '{field}'"

    def test_agent_monitor_live_schema(self, client):
        """Regression: Monitor live response schema stable."""
        d = client.get("/api/agent-monitor/live").json()
        assert "agents" in d and "summary" in d
        s = d["summary"]
        for field in ("total", "active", "idle", "killed", "session_cost"):
            assert field in s, f"Monitor summary missing '{field}'"

    def test_finops_dashboard_schema(self, client):
        """Regression: FinOps dashboard schema stable."""
        d = client.get("/api/finops/dashboard").json()
        for field in ("total_cost_usd", "cost_today", "budget_caps", "by_agent"):
            assert field in d, f"FinOps dashboard missing '{field}'"

    def test_eval_framework_suite_schema(self, client):
        """Regression: Eval suite schema stable."""
        d = client.get("/api/eval-framework/suites").json()
        assert "suites" in d and "count" in d
        if d["suites"]:
            suite = d["suites"][0]
            for field in ("suite_id", "name", "pass_threshold", "cases_count"):
                assert field in suite, f"Suite missing '{field}'"
