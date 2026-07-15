"""
Regression Tests — Sprint A/B/C/D Feature Integrity
Verifies that all Sprint A-D features continue to work correctly
after subsequent changes to the codebase.

These tests form a safety net: if any sprint feature breaks, this catches it.
"""
import pytest
import httpx
import asyncio
import time

BASE = "http://127.0.0.1:8787"


@pytest.fixture(scope="module")
def client():
    return httpx.Client(base_url=BASE, timeout=20)


# ── SPRINT A REGRESSION ────────────────────────────────────────────────────────
class TestRegressionSprintA_AuditLog:
    """Sprint A: Immutable Audit Log must maintain hash chain integrity."""

    def test_audit_log_chain_valid(self, client):
        """Regression: Hash chain must be valid at all times."""
        r = client.get("/api/audit-log/verify")
        assert r.status_code == 200
        d = r.json()
        assert d["ok"] is True, f"SPRINT-A REGRESSION: audit chain broken: {d['message']}"

    def test_audit_append_returns_entry_id(self, client):
        """Regression: Append returns entry_id, prev_hash, entry_hash."""
        r = client.post("/api/audit-log/append", json={
            "agent_id": "regress_agent",
            "action_type": "regression_test",
            "action_detail": "Sprint A regression test",
            "outcome": "success"
        })
        assert r.status_code == 200
        d = r.json()
        assert d["ok"] is True
        assert d["entry_id"].startswith("al_")
        assert len(d["entry_hash"]) == 64
        assert len(d["prev_hash"]) == 64
        assert "receipt_id" in d

    def test_audit_chain_grows_after_append(self, client):
        """Regression: Chain entry count grows after each append."""
        before = client.get("/api/audit-log/verify").json()["verified"]
        client.post("/api/audit-log/append", json={
            "agent_id": "regress", "action_type": "count_test", "outcome": "success"
        })
        after = client.get("/api/audit-log/verify").json()["verified"]
        assert after > before, f"SPRINT-A REGRESSION: chain didn't grow {before}→{after}"

    def test_audit_stats_have_all_fields(self, client):
        """Regression: Stats endpoint returns all required fields."""
        d = client.get("/api/audit-log/stats").json()
        for field in ("total", "chain_tip", "by_risk", "by_outcome", "top_agents"):
            assert field in d, f"SPRINT-A REGRESSION: '{field}' missing from audit stats"


class TestRegressionSprintA_AgentIdentity:
    """Sprint A: Agent Identity system must provision and verify correctly."""

    def test_provision_all_agents_works(self, client):
        """Regression: Provision-all still works."""
        r = client.post("/api/agent-identity/provision-all")
        assert r.status_code == 200
        d = r.json()
        assert d["ok"] is True
        assert d["total"] >= 8

    def test_jit_token_lifecycle(self, client):
        """Regression: Issue→Validate→Revoke lifecycle intact."""
        # Issue
        issue = client.post("/api/agent-identity/brain/issue-token", json={
            "task_id": "regress_a", "ttl_seconds": 60
        }).json()
        assert issue["ok"] is True
        tok = issue["token_id"]

        # Validate
        val = client.post("/api/agent-identity/token/validate", json={
            "token_id": tok, "agent_id": "brain"
        }).json()
        assert val["ok"] is True

        # Revoke
        rev = client.post(f"/api/agent-identity/token/{tok}/revoke", json={}).json()
        assert rev["ok"] is True

        # Post-revoke invalid
        val2 = client.post("/api/agent-identity/token/validate", json={
            "token_id": tok, "agent_id": "brain"
        }).json()
        assert val2["ok"] is False

    def test_system_stats_zero_trust_active(self, client):
        """Regression: zero_trust_active must always be True."""
        d = client.get("/api/agent-identity/system/stats").json()
        assert d["zero_trust_active"] is True, \
            "SPRINT-A REGRESSION: zero_trust_active is False"


class TestRegressionSprintA_HITL:
    """Sprint A: HITL gateway must correctly gate actions."""

    def test_critical_actions_not_auto_approved(self, client):
        """Regression: Critical actions always require human approval."""
        r = client.post("/api/hitl/interrupt", json={
            "action_type": "delete_database",
            "action_summary": "Regression test critical action",
            "risk_level": "critical",
            "confidence": 0.99
        })
        d = r.json()
        assert d["auto"] is False, \
            "SPRINT-A REGRESSION: critical action was auto-approved!"
        assert d["decision"] == "pending"
        # Clean up
        client.post(f"/api/hitl/interrupt/{d['interrupt_id']}/decide",
                    json={"decision": "reject", "reviewer": "regress"})

    def test_low_risk_auto_approves(self, client):
        """Regression: Low-risk/high-confidence still auto-approves."""
        r = client.post("/api/hitl/interrupt", json={
            "action_type": "read_file",
            "action_summary": "Read config",
            "risk_level": "low",
            "confidence": 0.99
        })
        d = r.json()
        assert d["auto"] is True, \
            "SPRINT-A REGRESSION: low-risk action requires manual approval"
        assert d["decision"] == "auto_approved"


# ── SPRINT B REGRESSION ────────────────────────────────────────────────────────
class TestRegressionSprintB_Goals:
    """Sprint B: Goal Manager state transitions must work correctly."""

    def test_goal_crud_complete(self, client):
        """Regression: Goal CRUD lifecycle."""
        # Create
        gid = client.post("/api/goals", json={
            "title": "Regress Sprint B Goal", "domain": "Research", "priority": "medium"
        }).json()["goal_id"]
        assert gid.startswith("goal_")

        # Read
        g = client.get(f"/api/goals/{gid}").json()["goal"]
        assert g["status"] == "active"
        assert g["progress"] == 0

        # Update progress
        client.patch(f"/api/goals/{gid}", json={"progress": 50})
        g2 = client.get(f"/api/goals/{gid}").json()["goal"]
        assert g2["progress"] == 50

        # 100% → auto-done
        client.patch(f"/api/goals/{gid}", json={"progress": 100})
        g3 = client.get(f"/api/goals/{gid}").json()["goal"]
        assert g3["status"] == "done"

        # Delete
        client.delete(f"/api/goals/{gid}")
        r4 = client.get(f"/api/goals/{gid}")
        assert r4.status_code in (200, 404)
        if r4.status_code == 200:
            assert r4.json().get("ok") is False

    def test_goal_domains_list(self, client):
        """Regression: All 8 domains still listed."""
        d = client.get("/api/goals/domains/list").json()
        assert len(d["domains"]) == 8
        assert "Work" in d["domains"]


class TestRegressionSprintB_Supervisor:
    """Sprint B: Supervisor must decompose goals into task DAGs."""

    def test_supervisor_creates_tasks(self, client):
        """Regression: Supervisor decomposes goal into tasks."""
        r = client.post("/api/supervisor/run", json={
            "goal": "Brief answer: what is Python?"
        })
        assert r.status_code == 200
        d = r.json()
        assert d["ok"] is True
        run_id = d["run_id"]
        assert run_id.startswith("srun_")

        # Wait and verify
        for _ in range(10):
            time.sleep(1)
            s = client.get(f"/api/supervisor/run/{run_id}").json()
            if s["run"]["status"] not in ("decomposing",):
                break

        final = client.get(f"/api/supervisor/run/{run_id}").json()
        assert final["run"]["task_count"] >= 1, \
            "SPRINT-B REGRESSION: supervisor created 0 tasks"

        # Kill and clean up
        client.post(f"/api/supervisor/run/{run_id}/kill", json={"reason": "regress"})

    def test_supervisor_stats_accessible(self, client):
        """Regression: Supervisor stats endpoint works."""
        d = client.get("/api/supervisor/stats").json()
        assert "total_runs" in d


# ── SPRINT C REGRESSION ────────────────────────────────────────────────────────
class TestRegressionSprintC_MCPGateway:
    """Sprint C: MCP Gateway must enforce policies correctly."""

    def test_all_builtin_servers_present(self, client):
        """Regression: All 6 built-in servers still seeded."""
        d = client.get("/api/mcp-gateway/servers").json()
        ids = {s["server_id"] for s in d["servers"]}
        for sid in ["srv_filesystem","srv_web_search","srv_memory","srv_http","srv_code_exec"]:
            assert sid in ids, f"SPRINT-C REGRESSION: {sid} missing from servers"

    def test_allowed_call_passes_through(self, client):
        """Regression: Allowed calls still execute."""
        r = client.post("/api/mcp-gateway/call", json={
            "server_id": "srv_filesystem",
            "tool": "fs.list",
            "args": {"path": "."},
            "agent_id": "regress_agent"
        })
        assert r.status_code == 200
        d = r.json()
        assert d.get("policy_decision") == "allow", \
            f"SPRINT-C REGRESSION: fs.list not allowed: {d}"

    def test_destructive_action_triggers_hitl(self, client):
        """Regression: fs.delete still requires HITL."""
        r = client.post("/api/mcp-gateway/call", json={
            "server_id": "srv_filesystem",
            "tool": "fs.delete",
            "args": {"path": "test.txt"},
            "agent_id": "regress_agent"
        })
        d = r.json()
        assert d.get("policy_decision") == "require_hitl", \
            f"SPRINT-C REGRESSION: fs.delete not gated: {d}"


class TestRegressionSprintC_Connectors:
    """Sprint C: Enterprise connectors must execute correctly."""

    def test_webhook_connector_active(self, client):
        """Regression: Webhook connector is active by default."""
        d = client.get("/api/connectors/conn_webhook").json()
        assert d["connector"]["status"] == "active", \
            "SPRINT-C REGRESSION: webhook connector not active"

    def test_webhook_execute_works(self, client):
        """Regression: Webhook execution still works."""
        r = client.post("/api/connectors/conn_webhook/execute", json={
            "action": "post_webhook",
            "payload": {"url": "http://127.0.0.1:8787/api/docs/feedback", "data": {"regress": True}}
        })
        d = r.json()
        assert d["ok"] is True, f"SPRINT-C REGRESSION: webhook failed: {d}"

    def test_all_8_connectors_present(self, client):
        """Regression: All 8 built-in connectors still seeded."""
        d = client.get("/api/connectors").json()
        assert d["count"] >= 8, \
            f"SPRINT-C REGRESSION: only {d['count']} connectors (expected 8+)"


# ── SPRINT D REGRESSION ────────────────────────────────────────────────────────
class TestRegressionSprintD_Monitor:
    """Sprint D: Agent Monitor must show correct agent data."""

    def test_live_dashboard_has_agents(self, client):
        """Regression: Live dashboard shows agents."""
        d = client.get("/api/agent-monitor/live").json()
        assert len(d["agents"]) >= 8, \
            f"SPRINT-D REGRESSION: only {len(d['agents'])} agents in monitor"

    def test_kill_revive_works(self, client):
        """Regression: Kill/revive cycle intact."""
        kill = client.post("/api/agent-monitor/kill/memory",
                           json={"reason": "regression test"}).json()
        assert kill["ok"] is True
        revive = client.post("/api/agent-monitor/revive/memory").json()
        assert revive["ok"] is True
        assert revive["status"] == "idle"

    def test_anomaly_detection_accessible(self, client):
        """Regression: Anomaly detection endpoint works."""
        r = client.post("/api/agent-monitor/anomalies/detect")
        assert r.status_code == 200
        assert r.json()["ok"] is True


class TestRegressionSprintD_FinOps:
    """Sprint D: FinOps must track costs accurately."""

    def test_finops_dashboard_accessible(self, client):
        """Regression: FinOps dashboard returns all required fields."""
        d = client.get("/api/finops/dashboard").json()
        for field in ("total_cost_usd", "budget_caps", "by_agent", "by_source_type"):
            assert field in d, f"SPRINT-D REGRESSION: '{field}' missing from finops"

    def test_cost_recording_works(self, client):
        """Regression: Cost ledger still accepts entries."""
        r = client.post("/api/finops/ledger/record", json={
            "agent_id": "regress_brain",
            "source_type": "llm",
            "cost_usd": 0.001,
            "tokens": 100
        })
        assert r.json()["ok"] is True


class TestRegressionSprintD_EvalFramework:
    """Sprint D: Evaluation Framework must score agents correctly."""

    def test_seeded_suites_present(self, client):
        """Regression: 3 seeded eval suites still present."""
        d = client.get("/api/eval-framework/suites").json()
        ids = {s["suite_id"] for s in d["suites"]}
        for sid in ["suite_general", "suite_safety", "suite_code"]:
            assert sid in ids, f"SPRINT-D REGRESSION: {sid} missing from eval suites"

    def test_agent_summary_accessible(self, client):
        """Regression: Agent eval summary works."""
        d = client.get("/api/eval-framework/summary/builder").json()
        assert "agent_id" in d
        assert d["agent_id"] == "builder"

    def test_platform_stats_accessible(self, client):
        """Regression: Platform eval stats work."""
        d = client.get("/api/eval-framework/stats/platform").json()
        assert "total_suites" in d
        assert d["total_suites"] >= 3
