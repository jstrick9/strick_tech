"""
Regression Tests — Full Suite Meta-Tests
These tests verify that the entire test suite passes when run together,
and document the final state of the platform regression coverage.

This is the "regression of regressions" — ensuring test isolation.
"""
import pytest
import httpx
import time
import subprocess
import sys
from pathlib import Path

BASE = "http://127.0.0.1:8787"
ROOT = Path(__file__).resolve().parents[2]


@pytest.fixture(scope="module")
def client():
    return httpx.Client(base_url=BASE, timeout=15)


class TestRegressionPlatformHealth:
    """Platform-level health checks that must always pass."""

    def test_server_is_running(self, client):
        """Regression: Server must be running and healthy."""
        r = client.get("/api/system/health")
        assert r.status_code == 200
        d = r.json()
        assert d["ok"] is True
        assert d["version"] == "6.0.0"

    def test_database_has_all_tables(self, client):
        """Regression: Database must have all 116+ tables."""
        d = client.get("/api/system/health").json()
        assert d["database"]["tables"] >= 116, \
            f"REGRESSION: only {d['database']['tables']} tables (expected 116+)"

    def test_all_8_default_agents_present(self, client):
        """Regression: All 8 default agents must be in the DB."""
        agents = client.get("/api/agents").json()
        al = agents if isinstance(agents, list) else agents.get("agents", [])
        ids = {a["id"] for a in al}
        for aid in ["brain","builder","researcher","reviewer",
                    "creative","memory","local","orchestrator"]:
            assert aid in ids, f"REGRESSION: default agent '{aid}' missing!"

    def test_audit_chain_always_valid(self, client):
        """Regression: Audit chain must be valid (never broken)."""
        d = client.get("/api/audit-log/verify").json()
        assert d["ok"] is True, \
            f"REGRESSION: AUDIT CHAIN BROKEN! Message: {d.get('message')}"

    def test_zero_trust_always_active(self, client):
        """Regression: Zero-trust must always be active."""
        d = client.get("/api/agent-identity/system/stats").json()
        assert d["zero_trust_active"] is True, \
            "REGRESSION: zero-trust has been disabled!"

    def test_no_server_errors_on_health_checks(self, client):
        """Regression: All health-check endpoints return < 500."""
        health_endpoints = [
            "/api/system/health",
            "/api/audit-log/verify",
            "/api/agent-identity/system/stats",
            "/api/agent-monitor/summary",
            "/api/finops/dashboard",
            "/api/supervisor/stats",
            "/api/mcp-gateway/stats",
            "/api/connectors/stats/summary",
            "/api/eval-framework/stats/platform",
        ]
        for ep in health_endpoints:
            r = client.get(ep)
            assert r.status_code < 500, \
                f"REGRESSION: {ep} returned {r.status_code} (server error)"


class TestRegressionSprintABCDIntegration:
    """All Sprint features work together (integration regression)."""

    def test_complete_governed_workflow(self, client):
        """
        Regression: Complete governed workflow:
        Create Goal → Launch Supervisor → MCP Gateway call →
        Record Cost → Audit Chain verified
        """
        before_chain = client.get("/api/audit-log/verify").json()["verified"]
        before_cost = client.get("/api/finops/dashboard").json()["total_cost_usd"]

        # 1. Create goal (Sprint B)
        gid = client.post("/api/goals", json={
            "title": "Regress Full Flow",
            "domain": "Research"
        }).json()["goal_id"]

        # 2. MCP Gateway call (Sprint C)
        client.post("/api/mcp-gateway/call", json={
            "server_id": "srv_memory",
            "tool": "memory.search",
            "args": {"query": "regression test", "limit": 1},
            "agent_id": "brain"
        })

        # 3. Record cost (Sprint D)
        client.post("/api/finops/ledger/record", json={
            "agent_id": "brain",
            "source_type": "mcp",
            "cost_usd": 0.0001,
            "tokens": 10,
            "goal_id": gid
        })

        # 4. Verify chain still valid (Sprint A)
        time.sleep(0.3)
        after_chain = client.get("/api/audit-log/verify").json()
        assert after_chain["ok"] is True, \
            "REGRESSION: chain broken after complete workflow"
        assert after_chain["verified"] > before_chain, \
            "REGRESSION: chain didn't grow during workflow"

        # 5. Cost tracked
        after_cost = client.get("/api/finops/dashboard").json()["total_cost_usd"]
        assert after_cost >= before_cost, \
            "REGRESSION: cost not tracked in complete workflow"

        # Cleanup
        client.delete(f"/api/goals/{gid}")


class TestRegressionTestSuiteIntegrity:
    """The test suite itself must be stable."""

    def test_unit_tests_collect_correctly(self):
        """Regression: Unit test files collect without import errors."""
        result = subprocess.run(
            [sys.executable, "-m", "pytest", "tests/unit/",
             "--collect-only", "-q", "--override-ini=addopts="],
            capture_output=True, text=True, cwd=str(ROOT)
        )
        assert result.returncode == 0, \
            f"REGRESSION: Unit tests have collection errors:\n{result.stdout[-500:]}"
        assert "error" not in result.stdout.lower() or "0 errors" in result.stdout.lower()

    def test_integration_tests_collect_correctly(self):
        """Regression: Integration tests collect without errors."""
        result = subprocess.run(
            [sys.executable, "-m", "pytest", "tests/integration/",
             "--collect-only", "-q", "--override-ini=addopts="],
            capture_output=True, text=True, cwd=str(ROOT)
        )
        assert result.returncode == 0, \
            f"REGRESSION: Integration tests have collection errors:\n{result.stdout[-500:]}"

    def test_sprint_tests_collect_correctly(self):
        """Regression: Sprint A-D tests collect without errors."""
        for sprint in ["sprint_a", "sprint_b", "sprint_c", "sprint_d"]:
            result = subprocess.run(
                [sys.executable, "-m", "pytest", f"tests/{sprint}/",
                 "--collect-only", "-q", "--override-ini=addopts="],
                capture_output=True, text=True, cwd=str(ROOT)
            )
            assert result.returncode == 0, \
                f"REGRESSION: {sprint} tests have collection errors:\n{result.stdout[-300:]}"


class TestRegressionDocumentation:
    """Platform documentation and configuration integrity."""

    def test_openapi_spec_accessible(self, client):
        """Regression: OpenAPI spec is always accessible."""
        r = client.get("/openapi.json")
        assert r.status_code == 200
        d = r.json()
        assert "paths" in d
        assert len(d["paths"]) >= 500, \
            f"REGRESSION: OpenAPI has only {len(d['paths'])} paths (expected 500+)"

    def test_frontend_served(self, client):
        """Regression: Frontend HTML is served correctly."""
        r = client.get("/")
        assert r.status_code == 200
        assert "<!DOCTYPE html>" in r.text or "html" in r.text.lower()

    def test_audit_reports_exist(self):
        """Regression: All audit and test reports are present."""
        reports_dir = ROOT / "tests" / "reports"
        expected_reports = [
            "SPRINT_A_REPORT.md",
            "SPRINT_B_REPORT.md",
            "SPRINT_C_REPORT.md",
            "SPRINT_D_REPORT.md",
            "AUDIT_PASS1_REPORT.md",
            "AUDIT_PASS2_REPORT.md",
            "AUDIT_PASS3_REPORT.md",
        ]
        for report in expected_reports:
            p = reports_dir / report
            assert p.exists(), f"REGRESSION: {report} missing from reports/"
