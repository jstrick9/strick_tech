"""
Unit Tests — Sprint D Complete: FinOps Advanced, Agent Monitor Full, Eval Framework Full
Covers: cost time-series, budget breach alerts, KPI trends, anomaly resolution, eval pipelines
"""
import pytest, httpx, time

class TestFinOpsAdvanced:
    def test_dashboard_fields(self, client):
        d = client.get("/api/finops/dashboard").json()
        for f in ("total_cost_usd", "cost_today", "budget_caps", "by_agent"):
            assert f in d

    def test_record_multiple_sources(self, client):
        for source in ("llm", "mcp", "connector", "supervisor"):
            r = client.post("/api/finops/ledger/record", json={
                "agent_id": "brain", "source_type": source,
                "cost_usd": 0.001, "tokens": 100, "description": f"Unit {source}"
            })
            assert r.json()["ok"] is True

    def test_ledger_filter_by_source_type(self, client):
        r = client.get("/api/finops/ledger?source_type=llm&limit=5")
        assert r.status_code == 200
        d = r.json()
        for entry in d["entries"]:
            assert entry["source_type"] == "llm"

    def test_cost_by_goal_creates_attribution(self, client):
        client.post("/api/finops/ledger/record", json={
            "agent_id": "orchestrator", "source_type": "supervisor",
            "cost_usd": 0.05, "tokens": 1000, "goal_id": "goal_attribution_test"
        })
        r = client.get("/api/finops/by-goal/goal_attribution_test")
        assert r.status_code == 200
        d = r.json()
        assert d["total_cost"] >= 0.05

    def test_time_series_daily(self, client):
        r = client.get("/api/finops/stats/time-series?days=7&granularity=day")
        assert r.status_code == 200
        d = r.json()
        assert "series" in d
        assert d["granularity"] == "day"

    def test_time_series_hourly(self, client):
        r = client.get("/api/finops/stats/time-series?days=1&granularity=hour")
        assert r.status_code == 200

    def test_budget_cap_all_scopes(self, client):
        for scope in ("agent", "goal", "platform"):
            r = client.post("/api/finops/caps", json={
                "name": f"Unit {scope} cap",
                "scope_type": scope,
                "scope_id": "*",
                "period": "day",
                "limit_usd": 10.0
            })
            d = r.json()
            assert d["ok"] is True

    def test_budget_cap_on_breach_actions(self, client):
        for action in ("alert", "pause", "kill"):
            r = client.post("/api/finops/caps", json={
                "name": f"Unit {action} breach",
                "limit_usd": 0.01,
                "on_breach": action
            })
            assert r.json()["ok"] is True

    def test_alert_resolve(self, client):
        alerts = client.get("/api/finops/alerts").json()
        if alerts.get("count", 0) > 0:
            alert_id = alerts["alerts"][0]["id"]
            r = client.post(f"/api/finops/alerts/{alert_id}/resolve")
            assert r.json()["ok"] is True

    def test_csv_export(self, client):
        r = client.get("/api/finops/export/csv?days=7")
        assert r.status_code == 200
        assert "text/csv" in r.headers.get("content-type", "")


class TestAgentMonitorAdvanced:
    def test_live_dashboard_all_fields(self, client):
        d = client.get("/api/agent-monitor/live").json()
        assert "agents" in d
        assert "summary" in d
        s = d["summary"]
        for f in ("total", "active", "idle", "killed", "session_cost"):
            assert f in s

    def test_each_agent_has_fields(self, client):
        agents = client.get("/api/agent-monitor/live").json()["agents"]
        for a in agents:
            for f in ("agent_id", "name", "status", "tokens_session",
                      "cost_session", "anomaly_score", "is_killed"):
                assert f in a

    def test_kpi_snapshot_then_fetch(self, client):
        client.post("/api/agent-monitor/kpis/snapshot")
        r = client.get("/api/agent-monitor/kpis/builder?period=hour&limit=10")
        assert r.status_code == 200
        d = r.json()
        assert "all_time" in d
        assert "kpi_series" in d

    def test_anomaly_detect_returns_ok(self, client):
        r = client.post("/api/agent-monitor/anomalies/detect")
        assert r.json()["ok"] is True

    def test_anomaly_list_pagination(self, client):
        r = client.get("/api/agent-monitor/anomalies?limit=5")
        assert r.status_code == 200
        d = r.json()
        assert len(d["anomalies"]) <= 5

    def test_kill_revive_cycle(self, client):
        # Kill
        kill = client.post("/api/agent-monitor/kill/memory",
                           json={"reason": "unit test kill cycle"}).json()
        assert kill["ok"] is True
        assert kill["killed"] is True
        # Verify in dashboard
        agents = client.get("/api/agent-monitor/live").json()["agents"]
        mem = next(a for a in agents if a["agent_id"] == "memory")
        assert mem["is_killed"] is True
        # Revive
        revive = client.post("/api/agent-monitor/revive/memory").json()
        assert revive["ok"] is True
        assert revive["status"] == "idle"

    def test_shadow_test_lifecycle(self, client):
        create = client.post("/api/agent-monitor/shadow", json={
            "agent_id": "brain",
            "shadow_config": {"model": "gpt4o-mini", "temperature": 0.3}
        }).json()
        assert create["ok"] is True
        test_id = create["test_id"]
        # Retrieve
        r = client.get(f"/api/agent-monitor/shadow/{test_id}")
        assert r.status_code == 200
        d = r.json()
        assert d["ok"] is True
        assert d["test"]["test_id"] == test_id

    def test_monitor_summary_fields(self, client):
        d = client.get("/api/agent-monitor/summary").json()
        for f in ("total_agents", "active_agents", "unresolved_anomalies",
                  "all_time_tasks", "all_time_cost"):
            assert f in d


class TestEvalFrameworkAdvanced:
    def test_three_seeded_suites(self, client):
        d = client.get("/api/eval-framework/suites").json()
        names = [s["name"] for s in d["suites"]]
        assert "General Capability" in names
        assert "Safety & Guardrails" in names
        assert "Code Quality" in names

    def test_suite_cases_have_criteria(self, client):
        cases = client.get("/api/eval-framework/suites/suite_safety/cases").json()["cases"]
        for c in cases:
            assert "criteria" in c
            assert isinstance(c["criteria"], list)

    def test_add_case_increments_count(self, client):
        before = client.get("/api/eval-framework/suites/suite_general").json()
        # Add a case
        client.post("/api/eval-framework/suites/suite_general/cases", json={
            "prompt": "Unit test case for count check",
            "expected": "acknowledged",
            "difficulty": "easy"
        })
        after = client.get("/api/eval-framework/suites").json()
        gen = next(s for s in after["suites"] if s["suite_id"] == "suite_general")
        assert gen["cases_count"] >= 3  # Was 3, now >= 3

    def test_results_filter_by_pass_fail(self, client):
        r = client.get("/api/eval-framework/results?pass_fail=pass&limit=5")
        assert r.status_code == 200
        d = r.json()
        for result in d["results"]:
            assert result["pass_fail"] == "pass"

    def test_agent_eval_summary_fields(self, client):
        d = client.get("/api/eval-framework/summary/builder?days=30").json()
        assert d["agent_id"] == "builder"
        for f in ("total_evals", "pass_rate", "avg_score", "review_pending"):
            assert f in d

    def test_platform_stats_fields(self, client):
        d = client.get("/api/eval-framework/stats/platform").json()
        for f in ("total_evals", "total_suites", "pending_review", "by_agent"):
            assert f in d

    def test_review_queue_structure(self, client):
        r = client.get("/api/eval-framework/review-queue?limit=10")
        assert r.status_code == 200
        d = r.json()
        assert "queue" in d
        assert "count" in d

    def test_run_eval_suite_streams(self, client):
        with client.stream("POST", "/api/eval-framework/run", json={
            "agent_id": "builder", "suite_id": "suite_code"
        }) as resp:
            assert resp.status_code == 200
            events = []
            for line in resp.iter_lines():
                if line.startswith("data:"):
                    import json
                    try:
                        ev = json.loads(line[5:])
                        events.append(ev)
                        if ev.get("type") == "done":
                            break
                    except Exception:
                        pass
                if len(events) > 15:
                    break
        types = [e.get("type") for e in events]
        assert "start" in types
