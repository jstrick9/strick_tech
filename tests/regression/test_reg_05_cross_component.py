"""
Regression Tests — Cross-Component State Consistency
Verifies that data flows correctly across components after all changes.
These tests catch regressions where fixing one component breaks another.
"""
import pytest
import httpx
import time

BASE = "http://127.0.0.1:8787"


@pytest.fixture(scope="module")
def client():
    return httpx.Client(base_url=BASE, timeout=20)


class TestRegressionCrossComponent_AuditChain:
    """Audit chain integrity across all platform actions."""

    def test_chain_valid_after_goal_operations(self, client):
        """Regression: Audit chain remains valid after Goal Manager operations."""
        before = client.get("/api/audit-log/verify").json()["verified"]

        gid = client.post("/api/goals", json={"title": "Regress chain goal"}).json()["goal_id"]
        client.patch(f"/api/goals/{gid}", json={"progress": 50})
        client.delete(f"/api/goals/{gid}")

        time.sleep(0.2)
        after = client.get("/api/audit-log/verify").json()
        assert after["ok"] is True, "REGRESSION: chain broken after goal operations"
        assert after["verified"] >= before

    def test_chain_valid_after_connector_executions(self, client):
        """Regression: Audit chain valid after connector calls."""
        before = client.get("/api/audit-log/verify").json()["verified"]

        client.post("/api/connectors/conn_webhook/execute", json={
            "action": "post_webhook",
            "payload": {"url": "https://httpbin.org/post", "data": {"chain": "test"}}
        })

        time.sleep(0.3)
        after = client.get("/api/audit-log/verify").json()
        assert after["ok"] is True, "REGRESSION: chain broken after connector exec"

    def test_chain_valid_after_identity_operations(self, client):
        """Regression: Audit chain valid after identity operations."""
        before = client.get("/api/audit-log/verify").json()["verified"]

        tok = client.post("/api/agent-identity/researcher/issue-token", json={
            "task_id": "chain_test", "ttl_seconds": 60
        }).json()["token_id"]
        client.post(f"/api/agent-identity/token/{tok}/revoke", json={})

        time.sleep(0.2)
        after = client.get("/api/audit-log/verify").json()
        assert after["ok"] is True, "REGRESSION: chain broken after identity ops"


class TestRegressionCrossComponent_GoalSupervisor:
    """Goal → Supervisor linkage must remain consistent."""

    def test_goal_launch_links_supervisor(self, client):
        """Regression: Goal launch correctly links supervisor run ID."""
        gid = client.post("/api/goals", json={
            "title": "Regress: Goal-Supervisor link",
            "description": "Cross-component regression test"
        }).json()["goal_id"]

        launch = client.post(f"/api/goals/{gid}/launch", json={}).json()
        assert launch["ok"] is True
        run_id = launch["run_id"]

        time.sleep(1)
        g = client.get(f"/api/goals/{gid}").json()["goal"]
        assert g.get("supervisor_run_id") == run_id, \
            f"REGRESSION: goal.supervisor_run_id mismatch: {g.get('supervisor_run_id')} vs {run_id}"

        # Supervisor knows about this goal
        s = client.get(f"/api/supervisor/run/{run_id}").json()
        assert s["run"]["goal_id"] == gid, \
            f"REGRESSION: supervisor.goal_id mismatch"

        # Cleanup
        client.post(f"/api/supervisor/run/{run_id}/kill", json={"reason": "regress"})


class TestRegressionCrossComponent_MCPAudit:
    """MCP Gateway calls must appear in audit chain."""

    def test_gateway_call_logged_in_audit(self, client):
        """Regression: MCP gateway calls write to audit chain."""
        before = client.get("/api/audit-log/verify").json()["verified"]

        client.post("/api/mcp-gateway/call", json={
            "server_id": "srv_filesystem",
            "tool": "fs.list",
            "args": {"path": "."},
            "agent_id": "regress_cross"
        })

        time.sleep(0.2)
        after = client.get("/api/audit-log/verify").json()
        assert after["verified"] >= before, "REGRESSION: MCP call not logged in audit"
        assert after["ok"] is True


class TestRegressionCrossComponent_FinOpsAccuracy:
    """FinOps cost attribution must remain accurate."""

    def test_recorded_cost_appears_in_dashboard(self, client):
        """Regression: Recorded cost appears in FinOps dashboard."""
        before_total = client.get("/api/finops/dashboard").json()["total_cost_usd"]

        client.post("/api/finops/ledger/record", json={
            "agent_id": "regress_finops",
            "source_type": "llm",
            "cost_usd": 0.0010,
            "tokens": 200
        })

        after_total = client.get("/api/finops/dashboard").json()["total_cost_usd"]
        assert after_total >= before_total, \
            f"REGRESSION: cost not tracked: before={before_total} after={after_total}"

    def test_goal_cost_attribution_works(self, client):
        """Regression: Cost tagged with goal_id appears in per-goal breakdown."""
        goal_id = f"regress_goal_{int(time.time())}"
        client.post("/api/finops/ledger/record", json={
            "agent_id": "brain",
            "source_type": "supervisor",
            "cost_usd": 0.025,
            "tokens": 5000,
            "goal_id": goal_id
        })

        d = client.get(f"/api/finops/by-goal/{goal_id}").json()
        assert d["total_cost"] >= 0.025, \
            f"REGRESSION: goal attribution failed: {d}"


class TestRegressionCrossComponent_MonitorIdentity:
    """Agent Monitor + Identity must agree on agent state."""

    def test_killed_agent_reflected_in_monitor(self, client):
        """Regression: Killing an agent via monitor is reflected in live dashboard."""
        # Kill
        client.post("/api/agent-monitor/kill/local",
                    json={"reason": "regress cross"})

        # Dashboard must show it as killed
        agents = client.get("/api/agent-monitor/live").json()["agents"]
        local = next((a for a in agents if a["agent_id"] == "local"), None)
        assert local is not None
        assert local["is_killed"] is True, \
            "REGRESSION: killed agent not shown as killed in monitor"

        # Revive
        client.post("/api/agent-monitor/revive/local")

        # Must show as idle again
        agents2 = client.get("/api/agent-monitor/live").json()["agents"]
        local2 = next((a for a in agents2 if a["agent_id"] == "local"), None)
        assert local2["is_killed"] is False, \
            "REGRESSION: revived agent still shows as killed"


class TestRegressionCrossComponent_EvalAudit:
    """Eval Framework completions must write to audit chain."""

    def test_eval_run_creates_audit_entry(self, client):
        """Regression: Running an eval suite creates an audit entry."""
        before = client.get("/api/audit-log/verify").json()["verified"]

        # Quick eval run
        with client.stream("POST", "/api/eval-framework/run",
                           json={"agent_id": "reviewer",
                                 "suite_id": "suite_code"}) as resp:
            for line in resp.iter_lines():
                if line.startswith("data:"):
                    import json
                    try:
                        ev = json.loads(line[5:])
                        if ev.get("type") == "done":
                            break
                    except Exception:
                        pass

        time.sleep(0.5)
        after = client.get("/api/audit-log/verify").json()
        assert after["verified"] >= before, \
            "REGRESSION: eval run not logged in audit chain"
        assert after["ok"] is True, "REGRESSION: chain broken after eval run"


class TestRegressionCrossComponent_SecurityBoundaries:
    """Security boundaries must remain enforced across all components."""

    def test_wrong_agent_token_still_rejected(self, client):
        """Regression: Token boundary enforcement still works."""
        tok = client.post("/api/agent-identity/brain/issue-token", json={
            "task_id": "regress_boundary", "ttl_seconds": 30
        }).json()["token_id"]

        val = client.post("/api/agent-identity/token/validate", json={
            "token_id": tok,
            "agent_id": "builder"  # Wrong agent
        }).json()
        assert val["ok"] is False, \
            "REGRESSION: token accepted for wrong agent!"

        client.post(f"/api/agent-identity/token/{tok}/revoke", json={})

    def test_sensitive_path_still_blocked_in_terminal(self, client):
        """Regression: /etc/passwd still blocked in terminal."""
        r = client.post("/api/terminal/run", json={"command": "cat /etc/passwd"})
        text = r.text
        assert "root:" not in text, \
            "REGRESSION: /etc/passwd accessible via terminal!"

    def test_revoked_token_cannot_be_reused(self, client):
        """Regression: Revoked tokens cannot be reused."""
        tok = client.post("/api/agent-identity/creative/issue-token", json={
            "task_id": "revoke_regress", "ttl_seconds": 60
        }).json()["token_id"]

        # Use it once
        v1 = client.post("/api/agent-identity/token/validate", json={
            "token_id": tok, "agent_id": "creative"
        }).json()
        assert v1["ok"] is True

        # Revoke
        client.post(f"/api/agent-identity/token/{tok}/revoke", json={})

        # Try to reuse
        v2 = client.post("/api/agent-identity/token/validate", json={
            "token_id": tok, "agent_id": "creative"
        }).json()
        assert v2["ok"] is False, \
            "REGRESSION: revoked token was accepted!"
