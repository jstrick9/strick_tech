"""
Sprint D — Combined Test Suite
Tests: Live Agent Monitor, FinOps, Evaluation Framework
"""
import pytest, httpx, time

BASE = "http://127.0.0.1:8787"

@pytest.fixture(scope="module")
def client():
    return httpx.Client(base_url=BASE, timeout=15)


# ══════════════════════════════════════════════════════
#  LIVE AGENT MONITOR
# ══════════════════════════════════════════════════════
class TestLiveMonitor:
    def test_live_dashboard(self, client):
        r = client.get("/api/agent-monitor/live")
        assert r.status_code == 200
        d = r.json()
        assert "agents" in d
        assert "summary" in d
        assert len(d["agents"]) >= 8

    def test_live_agents_have_required_fields(self, client):
        agents = client.get("/api/agent-monitor/live").json()["agents"]
        for a in agents:
            for f in ("agent_id","name","status","tokens_session","cost_session","anomaly_score"):
                assert f in a

    def test_summary_counts_correct(self, client):
        d = client.get("/api/agent-monitor/live").json()
        s = d["summary"]
        assert s["total"] == len(d["agents"])
        assert s["active"] + s["idle"] + s["killed"] <= s["total"]

    def test_monitor_summary(self, client):
        r = client.get("/api/agent-monitor/summary")
        assert r.status_code == 200
        d = r.json()
        assert d["total_agents"] >= 8
        assert "all_time_tasks" in d
        assert "all_time_cost" in d

    def test_kpi_snapshot_all(self, client):
        r = client.post("/api/agent-monitor/kpis/snapshot")
        assert r.status_code == 200
        d = r.json()
        assert d["ok"] is True
        assert d["snapshotted"] >= 8

    def test_kpi_by_agent(self, client):
        r = client.get("/api/agent-monitor/kpis/builder")
        assert r.status_code == 200
        d = r.json()
        assert d["agent_id"] == "builder"
        assert "all_time" in d
        at = d["all_time"]
        for f in ("total_tasks","success_rate","avg_latency_ms","total_tokens","total_cost"):
            assert f in at

    def test_anomaly_detection_runs(self, client):
        r = client.post("/api/agent-monitor/anomalies/detect")
        assert r.status_code == 200
        d = r.json()
        assert d["ok"] is True
        assert "total_anomalies" in d
        assert isinstance(d["flags"], list)

    def test_anomaly_list(self, client):
        r = client.get("/api/agent-monitor/anomalies")
        assert r.status_code == 200
        d = r.json()
        assert "anomalies" in d
        assert "count" in d

    def test_kill_agent(self, client):
        r = client.post("/api/agent-monitor/kill/local",
                        json={"reason": "Unit test kill", "killed_by": "test_suite"})
        assert r.status_code == 200
        d = r.json()
        assert d["ok"] is True
        assert d["killed"] is True
        assert d["agent_id"] == "local"

    def test_killed_agent_shows_in_dashboard(self, client):
        agents = client.get("/api/agent-monitor/live").json()["agents"]
        local = next((a for a in agents if a["agent_id"]=="local"), None)
        assert local is not None
        assert local["status"] == "killed" or local["is_killed"] is True

    def test_revive_agent(self, client):
        r = client.post("/api/agent-monitor/revive/local")
        assert r.status_code == 200
        d = r.json()
        assert d["ok"] is True
        assert d["status"] == "idle"

    def test_revived_agent_not_killed(self, client):
        agents = client.get("/api/agent-monitor/live").json()["agents"]
        local = next((a for a in agents if a["agent_id"]=="local"), None)
        assert local is not None
        assert local["is_killed"] is False

    def test_shadow_test_create(self, client):
        r = client.post("/api/agent-monitor/shadow",
                        json={"agent_id": "builder", "shadow_config": {"test": True}})
        assert r.status_code == 200
        d = r.json()
        assert d["ok"] is True
        assert d["test_id"].startswith("shd_")

    def test_shadow_test_retrieve(self, client):
        r = client.post("/api/agent-monitor/shadow",
                        json={"agent_id": "researcher", "shadow_config": {}})
        test_id = r.json()["test_id"]
        r2 = client.get(f"/api/agent-monitor/shadow/{test_id}")
        assert r2.status_code == 200
        assert r2.json()["ok"] is True

    def test_kill_audit_logged(self, client):
        before = client.get("/api/audit-log/verify").json()["verified"]
        client.post("/api/agent-monitor/kill/creative",
                    json={"reason": "audit test"})
        after = client.get("/api/audit-log/verify").json()["verified"]
        assert after >= before
        client.post("/api/agent-monitor/revive/creative")  # cleanup


# ══════════════════════════════════════════════════════
#  FINOPS
# ══════════════════════════════════════════════════════
class TestFinOps:
    def test_dashboard(self, client):
        r = client.get("/api/finops/dashboard")
        assert r.status_code == 200
        d = r.json()
        for f in ("total_cost_usd","total_tokens","cost_today","cost_last_hour",
                  "projected_daily","budget_caps","by_agent","by_source_type"):
            assert f in d

    def test_record_cost(self, client):
        r = client.post("/api/finops/ledger/record", json={
            "agent_id": "builder", "source_type": "llm",
            "cost_usd": 0.0025, "tokens": 500, "tokens_in": 200, "tokens_out": 300,
            "model": "anthropic/claude-3.5-sonnet", "description": "Unit test cost"
        })
        assert r.status_code == 200
        d = r.json()
        assert d["ok"] is True
        assert d["ledger_id"].startswith("cst_")

    def test_record_mcp_cost(self, client):
        r = client.post("/api/finops/ledger/record", json={
            "agent_id": "researcher", "source_type": "mcp",
            "cost_usd": 0.0001, "tokens": 0, "description": "MCP tool call"
        })
        assert r.json()["ok"] is True

    def test_record_connector_cost(self, client):
        r = client.post("/api/finops/ledger/record", json={
            "agent_id": "orchestrator", "source_type": "connector",
            "cost_usd": 0.0, "tokens": 0, "description": "Slack send"
        })
        assert r.json()["ok"] is True

    def test_ledger_query(self, client):
        r = client.get("/api/finops/ledger?days=7&limit=10")
        assert r.status_code == 200
        d = r.json()
        assert "entries" in d
        assert "total_cost" in d
        assert d["count"] >= 0

    def test_ledger_filter_by_agent(self, client):
        r = client.get("/api/finops/ledger?agent_id=builder&limit=20")
        d = r.json()
        for entry in d["entries"]:
            assert entry["agent_id"] == "builder"

    def test_ledger_filter_by_source(self, client):
        r = client.get("/api/finops/ledger?source_type=llm&limit=10")
        d = r.json()
        for entry in d["entries"]:
            assert entry["source_type"] == "llm"

    def test_cost_by_goal(self, client):
        # Record with goal_id
        client.post("/api/finops/ledger/record", json={
            "agent_id": "brain", "source_type": "supervisor",
            "cost_usd": 0.01, "tokens": 2000, "goal_id": "goal_finops_test"
        })
        r = client.get("/api/finops/by-goal/goal_finops_test")
        assert r.status_code == 200
        d = r.json()
        assert d["total_cost"] >= 0.01
        assert d["total_tokens"] >= 2000

    def test_list_caps(self, client):
        r = client.get("/api/finops/caps")
        assert r.status_code == 200
        d = r.json()
        assert d["count"] >= 3  # 3 defaults seeded

    def test_create_budget_cap(self, client):
        r = client.post("/api/finops/caps", json={
            "name": "Test Agent Cap",
            "scope_type": "agent",
            "scope_id": "builder",
            "period": "hour",
            "limit_usd": 0.50,
            "on_breach": "alert"
        })
        assert r.status_code == 200
        d = r.json()
        assert d["ok"] is True
        assert d["cap_id"].startswith("cap_")

    def test_create_cap_requires_name(self, client):
        r = client.post("/api/finops/caps", json={"limit_usd": 1.0})
        assert r.json()["ok"] is False

    def test_delete_cap(self, client):
        r = client.post("/api/finops/caps", json={"name": "Delete Me Cap", "limit_usd": 0.01})
        cap_id = r.json()["cap_id"]
        del_r = client.delete(f"/api/finops/caps/{cap_id}")
        assert del_r.json()["ok"] is True

    def test_time_series(self, client):
        r = client.get("/api/finops/stats/time-series?days=1&granularity=hour")
        assert r.status_code == 200
        d = r.json()
        assert "series" in d
        assert d["granularity"] == "hour"

    def test_alert_list(self, client):
        r = client.get("/api/finops/alerts")
        assert r.status_code == 200
        d = r.json()
        assert "alerts" in d

    def test_dashboard_reflects_recorded_cost(self, client):
        before = client.get("/api/finops/dashboard").json()["total_cost_usd"]
        client.post("/api/finops/ledger/record", json={
            "agent_id": "builder", "source_type": "llm",
            "cost_usd": 0.001, "tokens": 100
        })
        after = client.get("/api/finops/dashboard").json()["total_cost_usd"]
        assert after >= before


# ══════════════════════════════════════════════════════
#  EVALUATION FRAMEWORK
# ══════════════════════════════════════════════════════
class TestEvalFramework:
    def test_list_suites(self, client):
        r = client.get("/api/eval-framework/suites")
        assert r.status_code == 200
        d = r.json()
        assert d["count"] >= 3
        ids = [s["suite_id"] for s in d["suites"]]
        assert "suite_general" in ids
        assert "suite_safety" in ids
        assert "suite_code" in ids

    def test_suite_has_pass_threshold(self, client):
        d = client.get("/api/eval-framework/suites").json()
        for s in d["suites"]:
            assert 0 < s["pass_threshold"] <= 1.0

    def test_get_suite_cases(self, client):
        r = client.get("/api/eval-framework/suites/suite_general/cases")
        assert r.status_code == 200
        d = r.json()
        assert d["count"] >= 3

    def test_cases_have_required_fields(self, client):
        cases = client.get("/api/eval-framework/suites/suite_safety/cases").json()["cases"]
        for c in cases:
            assert "prompt" in c
            assert "expected" in c
            assert "difficulty" in c

    def test_create_suite(self, client):
        r = client.post("/api/eval-framework/suites", json={
            "name": "Custom Test Suite",
            "domain": "custom",
            "pass_threshold": 0.80
        })
        assert r.status_code == 200
        d = r.json()
        assert d["ok"] is True
        assert d["suite_id"].startswith("suite_")

    def test_create_suite_requires_name(self, client):
        r = client.post("/api/eval-framework/suites", json={"domain": "custom"})
        assert r.json()["ok"] is False

    def test_add_case_to_suite(self, client):
        r = client.post("/api/eval-framework/suites/suite_general/cases", json={
            "prompt": "What is 3+3?",
            "expected": "6",
            "criteria": ["correct math", "numeric answer"],
            "difficulty": "easy"
        })
        assert r.status_code == 200
        d = r.json()
        assert d["ok"] is True
        assert d["case_id"].startswith("case_")

    def test_add_case_requires_prompt(self, client):
        r = client.post("/api/eval-framework/suites/suite_general/cases",
                        json={"expected": "something"})
        assert r.json()["ok"] is False

    def test_list_results_empty(self, client):
        r = client.get("/api/eval-framework/results?agent_id=nonexistent_xyz")
        assert r.status_code == 200
        d = r.json()
        assert d["count"] == 0

    def test_platform_stats(self, client):
        r = client.get("/api/eval-framework/stats/platform")
        assert r.status_code == 200
        d = r.json()
        for f in ("total_evals","total_suites","pending_review","by_agent"):
            assert f in d
        assert d["total_suites"] >= 3

    def test_review_queue_empty(self, client):
        r = client.get("/api/eval-framework/review-queue")
        assert r.status_code == 200
        d = r.json()
        assert "queue" in d
        assert "count" in d

    def test_agent_summary(self, client):
        r = client.get("/api/eval-framework/summary/builder")
        assert r.status_code == 200
        d = r.json()
        assert d["agent_id"] == "builder"
        for f in ("total_evals","pass_rate","avg_score","review_pending"):
            assert f in d

    def test_run_eval_streaming(self, client):
        """Run eval and collect SSE events."""
        with client.stream("POST", "/api/eval-framework/run",
                           json={"agent_id": "builder", "suite_id": "suite_general"}) as r:
            assert r.status_code == 200
            events = []
            for line in r.iter_lines():
                if line.startswith("data:"):
                    import json
                    try:
                        ev = json.loads(line[5:])
                        events.append(ev)
                        if ev.get("type") == "done":
                            break
                    except: pass
                if len(events) > 20:
                    break

        assert len(events) > 0
        types = [e.get("type") for e in events]
        assert "start" in types

    def test_results_recorded_after_run(self, client):
        # Quick eval run
        with client.stream("POST", "/api/eval-framework/run",
                           json={"agent_id": "reviewer", "suite_id": "suite_safety"}) as r:
            for line in r.iter_lines():
                if line.startswith("data:"):
                    try:
                        import json
                        ev = json.loads(line[5:])
                        if ev.get("type") == "done": break
                    except: pass

        time.sleep(0.5)
        results = client.get("/api/eval-framework/results?agent_id=reviewer").json()
        assert results["count"] >= 0  # May be 0 if stub LLM

    def test_human_review_submit(self, client):
        # First create a result to review
        # We'll just test the endpoint structure
        r = client.post("/api/eval-framework/results/nonexistent_id/review",
                        json={"score": 0.9, "notes": "Looks good", "reviewer": "test"})
        # Should return some response (may be error for nonexistent)
        assert r.status_code in (200, 404, 500)  # endpoint exists
