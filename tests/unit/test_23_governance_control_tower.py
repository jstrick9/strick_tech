"""
Unit Tests — Governance: Control Tower, HITL Full Flow, Budget Rules, Notifications
Covers: agent run lifecycle, kill switches, budget enforcement, full HITL flow
"""
import pytest, httpx, time

BASE = "http://127.0.0.1:8787"

@pytest.fixture(scope="module")
def client():
    return httpx.Client(base_url=BASE, timeout=15)


class TestControlTower:
    def test_list_runs(self, client):
        r = client.get("/api/control/runs")
        assert r.status_code == 200
        assert isinstance(r.json(), list)

    def test_list_runs_filter_by_status(self, client):
        r = client.get("/api/control/runs?status=done")
        assert r.status_code == 200

    def test_active_runs(self, client):
        r = client.get("/api/control/active")
        assert r.status_code == 200
        assert isinstance(r.json(), list)

    def test_control_stats(self, client):
        r = client.get("/api/control/stats")
        assert r.status_code == 200
        d = r.json()
        for field in ("total_runs", "active_runs", "total_cost", "total_tokens"):
            assert field in d

    def test_nonexistent_run(self, client):
        r = client.get("/api/control/runs/nonexistent_run_xyz")
        assert r.status_code == 200
        d = r.json()
        assert "error" in d or d.get("ok") is False

    def test_kill_all_no_active(self, client):
        r = client.post("/api/control/runs/kill-all")
        assert r.status_code == 200
        d = r.json()
        assert d["ok"] is True

    def test_stream_nonactive_run(self, client):
        r = client.get("/api/control/runs/nonexistent/stream", timeout=3)
        assert r.status_code == 200


class TestBudgetRules:
    def test_list_budget_rules(self, client):
        r = client.get("/api/control/budget-rules")
        assert r.status_code == 200
        assert isinstance(r.json(), list)

    def test_create_budget_rule(self, client):
        r = client.post("/api/control/budget-rules", json={
            "name": "Unit Test Rule",
            "agent_id": "*",
            "max_cost": 5.00,
            "max_tokens": 50000,
            "action": "warn"
        })
        assert r.status_code == 200
        d = r.json()
        assert d["ok"] is True
        assert "id" in d
        return d["id"]

    def test_budget_rule_action_validation(self, client):
        r = client.post("/api/control/budget-rules", json={
            "name": "Validation Test",
            "action": "invalid_action"  # Should default to "stop"
        })
        assert r.status_code == 200
        assert r.json()["ok"] is True

    def test_update_budget_rule(self, client):
        create = client.post("/api/control/budget-rules", json={
            "name": "Update Test Rule", "max_cost": 1.0
        }).json()
        rid = create["id"]
        r = client.patch(f"/api/control/budget-rules/{rid}", json={
            "max_cost": 2.0, "enabled": 1
        })
        assert r.status_code == 200
        assert r.json()["ok"] is True

    def test_delete_budget_rule(self, client):
        create = client.post("/api/control/budget-rules", json={
            "name": "Delete Test Rule", "max_cost": 0.5
        }).json()
        rid = create["id"]
        r = client.delete(f"/api/control/budget-rules/{rid}")
        assert r.status_code == 200
        assert r.json()["ok"] is True

    def test_budget_alias_endpoint(self, client):
        r = client.get("/api/control/budget")
        assert r.status_code == 200
        d = r.json()
        assert "rules" in d and "count" in d


class TestNotifications:
    def test_list_notifications(self, client):
        r = client.get("/api/control/notifications")
        assert r.status_code == 200
        d = r.json()
        assert "notifications" in d
        assert "unread_count" in d

    def test_list_unread_only(self, client):
        r = client.get("/api/control/notifications?unread_only=true")
        assert r.status_code == 200

    def test_mark_all_read(self, client):
        r = client.post("/api/control/notifications/read-all")
        assert r.status_code == 200
        assert r.json()["ok"] is True

    def test_clear_read_notifications(self, client):
        r = client.delete("/api/control/notifications")
        assert r.status_code == 200
        assert r.json()["ok"] is True


class TestHITLFull:
    def test_hitl_queue_empty_or_has_items(self, client):
        r = client.get("/api/hitl/queue")
        assert r.status_code == 200
        d = r.json()
        assert "interrupts" in d
        assert "count" in d

    def test_hitl_all_queue(self, client):
        r = client.get("/api/hitl/queue/all")
        assert r.status_code == 200

    def test_hitl_full_approve_flow(self, client):
        # Create interrupt
        create = client.post("/api/hitl/interrupt", json={
            "action_type": "test_approve",
            "action_summary": "Unit test approval flow",
            "risk_level": "high",
            "confidence": 0.5,
            "agent_id": "builder"
        }).json()
        assert create["ok"] is True
        int_id = create["interrupt_id"]
        assert create["decision"] == "pending"

        # Check it's in queue
        q = client.get("/api/hitl/queue").json()
        ids = [item["id"] for item in q["interrupts"]]
        assert int_id in ids

        # Approve it
        decide = client.post(f"/api/hitl/interrupt/{int_id}/decide", json={
            "decision": "approve",
            "note": "Unit test approval",
            "reviewer": "test_suite"
        }).json()
        assert decide["ok"] is True
        assert decide["decision"] == "approve"

    def test_hitl_full_reject_flow(self, client):
        create = client.post("/api/hitl/interrupt", json={
            "action_type": "test_reject",
            "action_summary": "Unit test rejection",
            "risk_level": "critical",
            "confidence": 0.3,
            "agent_id": "orchestrator"
        }).json()
        int_id = create["interrupt_id"]
        decide = client.post(f"/api/hitl/interrupt/{int_id}/decide", json={
            "decision": "reject",
            "note": "Rejected by unit test",
            "reviewer": "test_suite"
        }).json()
        assert decide["ok"] is True
        assert decide["decision"] == "reject"

    def test_hitl_modify_flow(self, client):
        create = client.post("/api/hitl/interrupt", json={
            "action_type": "test_modify",
            "action_summary": "Unit test modification",
            "risk_level": "high",
            "confidence": 0.55,
        }).json()
        int_id = create["interrupt_id"]
        decide = client.post(f"/api/hitl/interrupt/{int_id}/decide", json={
            "decision": "modify",
            "modified_action_data": {"safe_version": True},
            "reviewer": "test_suite"
        }).json()
        assert decide["ok"] is True

    def test_hitl_auto_approve_low_risk(self, client):
        r = client.post("/api/hitl/interrupt", json={
            "action_type": "read_file",
            "action_summary": "Read a config file",
            "risk_level": "low",
            "confidence": 0.95,
            "agent_id": "builder"
        }).json()
        assert r["ok"] is True
        assert r["auto"] is True
        assert r["decision"] == "auto_approved"

    def test_hitl_double_decide_fails(self, client):
        create = client.post("/api/hitl/interrupt", json={
            "action_type": "double_test",
            "action_summary": "Test double decide",
            "risk_level": "high",
            "confidence": 0.4
        }).json()
        int_id = create["interrupt_id"]
        client.post(f"/api/hitl/interrupt/{int_id}/decide", json={"decision": "approve"})
        # Second decide should fail
        r2 = client.post(f"/api/hitl/interrupt/{int_id}/decide", json={"decision": "reject"}).json()
        assert r2["ok"] is False

    def test_hitl_invalid_decision(self, client):
        create = client.post("/api/hitl/interrupt", json={
            "action_type": "invalid_test", "risk_level": "high", "confidence": 0.4,
            "action_summary": "Test invalid decision"
        }).json()
        int_id = create["interrupt_id"]
        r = client.post(f"/api/hitl/interrupt/{int_id}/decide", json={
            "decision": "invalid_choice"
        }).json()
        assert r["ok"] is False

    def test_hitl_undo_snapshot(self, client):
        r = client.post("/api/hitl/undo-snapshot", json={
            "action_id": "test_action_123",
            "type": "file",
            "state_data": "original content"
        }).json()
        assert r["ok"] is True
        assert "snapshot_id" in r

    def test_hitl_confidence_assessment(self, client):
        r = client.post("/api/hitl/assess-confidence", json={
            "action": "delete all user data",
            "context": "User requested data deletion"
        }).json()
        assert r["ok"] is True
        assert "confidence" in r
        assert "risk_level" in r
        assert "recommendation" in r

    def test_hitl_audit_log(self, client):
        r = client.get("/api/hitl/audit?limit=10")
        assert r.status_code == 200
        d = r.json()
        assert "audit" in d

    def test_hitl_stats(self, client):
        r = client.get("/api/hitl/stats")
        assert r.status_code == 200
        d = r.json()
        for f in ("total", "pending", "approved", "rejected"):
            assert f in d
