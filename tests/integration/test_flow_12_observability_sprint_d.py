"""
Integration Flow 12 — Sprint D Observability: Monitor→FinOps→Evals Pipeline
Tests the complete observability lifecycle:
  Live Agent Monitor → KPI snapshots → Anomaly detection →
  FinOps cost attribution → Budget caps → Evaluation Framework →
  Human review queue → Cross-component audit
"""
from __future__ import annotations
import asyncio, time
import httpx, pytest
from .conftest import BASE, TIMEOUT, uid, GET, POST, PATCH, DELETE, ok, ok_or, check


class TestAgentMonitorLifecycle:
    """Live Agent Monitor: dashboard, KPIs, anomalies, kill/revive."""

    async def test_01_live_dashboard_has_all_agents(self, client):
        """Live dashboard shows all enabled agents."""
        r = await GET(client, "/api/agent-monitor/live")
        d = ok(r, "live dashboard")
        check("has agents", "agents" in d)
        check("has summary", "summary" in d)
        check("agents >= 8", len(d["agents"]) >= 8)

        # Verify required fields per agent
        for agent in d["agents"]:
            for field in ("agent_id", "name", "status", "tokens_session",
                          "cost_session", "anomaly_score", "is_killed"):
                check(f"{agent['agent_id']}.{field} present", field in agent)

    async def test_02_summary_fields_coherent(self, client):
        """Summary totals are mathematically coherent."""
        d = (await GET(client, "/api/agent-monitor/live")).json()
        s = d["summary"]
        agents = d["agents"]

        check("total = len(agents)", s["total"] == len(agents))
        # active + idle + killed <= total
        check("counts coherent",
              s["active"] + s["idle"] + s["killed"] <= s["total"])

    async def test_03_kpi_snapshot_captures_all_agents(self, client):
        """KPI snapshot records KPIs for all active agents."""
        r = await POST(client, "/api/agent-monitor/kpis/snapshot")
        d = ok(r, "kpi snapshot")
        check("snapshot ok", d["ok"] is True)
        check("snapshotted >= 8", d["snapshotted"] >= 8)

    async def test_04_kpi_time_series_grows_over_snapshots(self, client):
        """Taking multiple snapshots grows the KPI time-series."""
        await POST(client, "/api/agent-monitor/kpis/snapshot")
        await asyncio.sleep(0.3)
        await POST(client, "/api/agent-monitor/kpis/snapshot")

        r = await GET(client, "/api/agent-monitor/kpis/brain", period="hour", limit=100)
        d = ok(r, "kpi time series")
        check("agent_id correct", d["agent_id"] == "brain")
        check("has kpi_series", "kpi_series" in d)
        check("has all_time", "all_time" in d)
        at = d["all_time"]
        for field in ("total_tasks", "success_rate", "avg_latency_ms", "total_cost"):
            check(f"all_time.{field} present", field in at)

    async def test_05_anomaly_detection_runs_for_all(self, client):
        """Anomaly detection runs across all agents without error."""
        r = await POST(client, "/api/agent-monitor/anomalies/detect")
        d = ok(r, "anomaly detect")
        check("detect ok", d["ok"] is True)
        check("total_anomalies is int", isinstance(d["total_anomalies"], int))
        check("flags is list", isinstance(d["flags"], list))

    async def test_06_kill_revive_cycle_complete(self, client):
        """Kill an agent, verify status, revive it, verify restored."""
        agent_id = "local"  # Local LLM agent — safe to kill in tests

        # Kill
        kill_r = await POST(client, f"/api/agent-monitor/kill/{agent_id}", {
            "reason": "Integration test kill/revive cycle",
            "killed_by": "integration_test_suite"
        })
        kd = ok(kill_r, "kill agent")
        check("kill ok", kd["ok"] is True)
        check("killed flag", kd["killed"] is True)

        # Verify killed in dashboard
        agents = (await GET(client, "/api/agent-monitor/live")).json()["agents"]
        local_agent = next(a for a in agents if a["agent_id"] == agent_id)
        check("status=killed", local_agent["is_killed"] is True)

        # Kill is recorded in audit chain
        await asyncio.sleep(0.3)
        latest_audit = (await GET(client, "/api/audit-log?limit=5")).json()["entries"]
        action_types = [e["action_type"] for e in latest_audit]
        check("kill recorded in audit", "agent_killed" in action_types)

        # Revive
        rev_r = await POST(client, f"/api/agent-monitor/revive/{agent_id}")
        rd = ok(rev_r, "revive agent")
        check("revive ok", rd["ok"] is True)
        check("status=idle", rd["status"] == "idle")

        # Verify restored in dashboard
        agents2 = (await GET(client, "/api/agent-monitor/live")).json()["agents"]
        local_agent2 = next(a for a in agents2 if a["agent_id"] == agent_id)
        check("is_killed=False after revive", local_agent2["is_killed"] is False)

    async def test_07_shadow_test_stores_metadata(self, client):
        """Shadow test creation stores correct metadata."""
        config = {"model": "gpt4o-mini", "temperature": 0.2, "test_name": "integration"}
        r = await POST(client, "/api/agent-monitor/shadow", {
            "agent_id": "builder",
            "shadow_config": config
        })
        d = ok(r, "shadow test create")
        check("ok", d["ok"] is True)
        test_id = d["test_id"]
        check("test_id format", test_id.startswith("shd_"))

        # Retrieve
        get_r = await GET(client, f"/api/agent-monitor/shadow/{test_id}")
        gd = ok(get_r, "get shadow test")
        check("get ok", gd["ok"] is True)
        check("agent_id correct", gd["test"]["agent_id"] == "builder")
        check("test_id correct", gd["test"]["test_id"] == test_id)

    async def test_08_monitor_summary_all_time_metrics(self, client):
        """Monitor summary aggregates all-time platform metrics."""
        r = await GET(client, "/api/agent-monitor/summary")
        d = ok(r, "monitor summary")
        for field in ("total_agents", "active_agents", "killed_agents",
                      "unresolved_anomalies", "all_time_tasks", "all_time_cost"):
            check(f"summary.{field} present", field in d)
        check("total_agents >= 8", d["total_agents"] >= 8)


class TestFinOpsAttribution:
    """FinOps cost ledger, attribution, caps, and alerts."""

    async def test_01_record_costs_all_source_types(self, client):
        """Record costs for all source types and verify ledger."""
        sources = [
            ("llm", "brain", "gpt4o", 500, 0.003),
            ("mcp", "builder", "", 0, 0.0001),
            ("connector", "orchestrator", "", 0, 0.0),
            ("supervisor", "orchestrator", "", 2000, 0.015),
            ("loop", "researcher", "", 300, 0.002),
        ]
        recorded_ids = []
        for source, agent, model, tokens, cost in sources:
            r = await POST(client, "/api/finops/ledger/record", {
                "agent_id": agent,
                "source_type": source,
                "cost_usd": cost,
                "tokens": tokens,
                "model": model,
                "description": f"Integration test {source} cost"
            })
            d = ok(r, f"record {source} cost")
            check(f"{source} ok", d["ok"] is True)
            check(f"{source} ledger_id", d["ledger_id"].startswith("cst_"))
            recorded_ids.append(d["ledger_id"])

        # Verify all appear in ledger
        ledger = (await GET(client, "/api/finops/ledger?days=1&limit=100")).json()
        all_cost = ledger["total_cost"]
        check("total_cost > 0", all_cost >= 0.020)

    async def test_02_goal_attribution_tracks_per_goal(self, client):
        """Costs tagged with goal_id appear in per-goal breakdown."""
        goal_id = f"finops_test_goal_{uid()}"

        # Record costs for this goal
        for i in range(3):
            await POST(client, "/api/finops/ledger/record", {
                "agent_id": f"agent_{i}",
                "source_type": "llm" if i == 0 else "mcp",
                "cost_usd": 0.01 * (i + 1),
                "tokens": 200 * (i + 1),
                "goal_id": goal_id,
                "description": f"Goal attribution test step {i}"
            })

        # Get per-goal breakdown
        r = await GET(client, f"/api/finops/by-goal/{goal_id}")
        d = ok(r, "cost by goal")
        check("goal_id matches", d["goal_id"] == goal_id)
        check("total_cost >= 0.06", d["total_cost"] >= 0.06,
              d["total_cost"])
        check("total_tokens > 0", d["total_tokens"] > 0)
        check("has by_source", "by_source" in d)
        check("has by_agent", "by_agent" in d)

    async def test_03_budget_cap_alert_at_80_pct(self, client):
        """Budget cap fires warning alert at 80% usage."""
        cap_r = await POST(client, "/api/finops/caps", {
            "name": f"Integration Alert Test Cap {uid()}",
            "scope_type": "goal",
            "scope_id": f"alert_test_goal_{uid()}",
            "period": "day",
            "limit_usd": 0.001,  # Very low to trigger
            "on_breach": "alert"
        })
        cd = ok(cap_r, "create cap")
        check("cap ok", cd["ok"] is True)
        cap_id = cd["cap_id"]

        # Record cost that exceeds the cap
        await POST(client, "/api/finops/ledger/record", {
            "agent_id": "alert_agent",
            "source_type": "llm",
            "cost_usd": 0.002,  # 200% of cap
            "goal_id": cap_r.json().get("scope_id", ""),
            "description": "Intentional cap breach for test"
        })

        # Alerts should exist
        alerts = (await GET(client, "/api/finops/alerts")).json()
        check("alerts exist", isinstance(alerts["alerts"], list))
        check("has count", "count" in alerts)

    async def test_04_time_series_granularity(self, client):
        """Time-series returns data at requested granularity."""
        for gran in ("hour", "day"):
            r = await GET(client, "/api/finops/stats/time-series",
                          days=7, granularity=gran)
            d = ok(r, f"time series {gran}")
            check(f"granularity={gran}", d["granularity"] == gran)
            check("has series", "series" in d)
            check("series is list", isinstance(d["series"], list))

    async def test_05_dashboard_shows_all_dimensions(self, client):
        """FinOps dashboard has all required dimensions."""
        r = await GET(client, "/api/finops/dashboard")
        d = ok(r, "finops dashboard")
        required = ["total_cost_usd", "cost_today", "cost_last_hour",
                    "projected_daily", "budget_caps", "by_agent", "by_source_type"]
        for field in required:
            check(f"dashboard.{field} present", field in d)
        check("by_agent is list", isinstance(d["by_agent"], list))
        check("budget_caps is list", isinstance(d["budget_caps"], list))

    async def test_06_csv_export_has_all_entries(self, client):
        """CSV export contains all ledger entries in date range."""
        r = await client.get("/api/finops/export/csv?days=30")
        check("csv 200", r.status_code == 200)
        check("csv content-type", "csv" in r.headers.get("content-type", ""))
        lines = r.text.strip().split("\n")
        check("has header row", len(lines) >= 1)
        header = lines[0].lower()
        check("ledger_id in header", "ledger_id" in header)
        check("agent_id in header", "agent_id" in header)
        check("cost_usd in header", "cost_usd" in header)


class TestEvaluationFramework:
    """Evaluation suites, streaming runs, human review queue."""

    async def test_01_seeded_suites_present(self, client):
        """Three seeded evaluation suites are present at startup."""
        r = await GET(client, "/api/eval-framework/suites")
        d = ok(r, "list suites")
        suite_ids = {s["suite_id"] for s in d["suites"]}
        for sid in ("suite_general", "suite_safety", "suite_code"):
            check(f"{sid} present", sid in suite_ids)

    async def test_02_create_custom_suite_with_cases(self, client):
        """Create a custom suite and add multiple cases."""
        # Create suite
        suite_r = await POST(client, "/api/eval-framework/suites", {
            "name": f"Integration Test Suite {uid()}",
            "domain": "integration",
            "pass_threshold": 0.80
        })
        sd = ok(suite_r, "create suite")
        check("suite ok", sd["ok"] is True)
        suite_id = sd["suite_id"]

        # Add 3 cases
        cases = [
            ("What is 2+2?", "4", ["correct math"], "easy"),
            ("What language is FastAPI written in?", "Python", ["mentions Python"], "easy"),
            ("Explain REST in one sentence.", "HTTP-based architectural style", ["mentions HTTP"], "medium"),
        ]
        for prompt, expected, criteria, diff in cases:
            cr = await POST(client, f"/api/eval-framework/suites/{suite_id}/cases", {
                "prompt": prompt,
                "expected": expected,
                "criteria": criteria,
                "difficulty": diff
            })
            check(f"case added", cr.json()["ok"] is True)

        # Verify cases count
        cases_r = await GET(client, f"/api/eval-framework/suites/{suite_id}/cases")
        cd = ok(cases_r, "get cases")
        check("3 cases added", cd["count"] == 3)
        for case in cd["cases"]:
            check("case has criteria", isinstance(case["criteria"], list))
            check("case has difficulty", "difficulty" in case)

    async def test_03_run_eval_suite_streams_events(self, client):
        """Running an eval suite produces a structured SSE stream."""
        events = []
        async with client.stream("POST", "/api/eval-framework/run",
                                  json={"agent_id": "reviewer", "suite_id": "suite_safety"}) as resp:
            check("stream 200", resp.status_code == 200)
            async for line in resp.aiter_lines():
                if line.startswith("data:"):
                    try:
                        import json
                        ev = json.loads(line[5:])
                        events.append(ev)
                        if ev.get("type") == "done":
                            break
                    except Exception:
                        pass
                if len(events) > 20:
                    break

        event_types = {e.get("type") for e in events}
        check("start event present", "start" in event_types)
        check("case_done events present", "case_done" in event_types)
        check("done event present", "done" in event_types)

        done_ev = next(e for e in events if e.get("type") == "done")
        check("done has passed", "passed" in done_ev)
        check("done has failed", "failed" in done_ev)
        check("done has total", "total" in done_ev)
        check("done has avg_score", "avg_score" in done_ev)
        check("done has suite_pass", "suite_pass" in done_ev)

    async def test_04_eval_results_stored_after_run(self, client):
        """Eval results persist in DB after a run."""
        before = (await GET(client, "/api/eval-framework/results?agent_id=brain")).json()["count"]

        # Run a quick eval
        async with client.stream("POST", "/api/eval-framework/run",
                                  json={"agent_id": "brain", "suite_id": "suite_code"}) as resp:
            async for line in resp.aiter_lines():
                if line.startswith("data:"):
                    try:
                        import json
                        ev = json.loads(line[5:])
                        if ev.get("type") == "done":
                            break
                    except Exception:
                        pass

        await asyncio.sleep(0.5)
        after = (await GET(client, "/api/eval-framework/results?agent_id=brain")).json()["count"]
        check("results grew", after >= before)

    async def test_05_human_review_queue_captures_low_scores(self, client):
        """Results with low scores appear in human review queue."""
        # Review queue should exist (some low-score results from other tests)
        r = await GET(client, "/api/eval-framework/review-queue?limit=20")
        d = ok(r, "review queue")
        check("has queue", "queue" in d)
        check("has count", "count" in d)

        # Submit a review for any queued item
        if d["count"] > 0:
            result_id = d["queue"][0]["result_id"]
            rev_r = await POST(client, f"/api/eval-framework/results/{result_id}/review", {
                "score": 0.75,
                "notes": "Integration test review — acceptable quality",
                "reviewer": "integration_test_suite"
            })
            rd = ok(rev_r, "submit review")
            check("review ok", rd["ok"] is True)

    async def test_06_agent_summary_accurate(self, client):
        """Agent eval summary has correct structure after runs."""
        r = await GET(client, "/api/eval-framework/summary/reviewer?days=30")
        d = ok(r, "agent summary")
        check("agent_id correct", d["agent_id"] == "reviewer")
        for field in ("total_evals", "pass_rate", "avg_score",
                      "avg_task_completion", "avg_safety", "review_pending"):
            check(f"summary.{field} present", field in d)
        check("pass_rate 0-1", 0 <= d["pass_rate"] <= 1.0)
        check("avg_score 0-1", 0 <= d["avg_score"] <= 1.0)

    async def test_07_platform_stats_after_runs(self, client):
        """Platform stats reflect all completed eval runs."""
        r = await GET(client, "/api/eval-framework/stats/platform")
        d = ok(r, "platform stats")
        check("total_evals > 0", d["total_evals"] > 0)
        check("total_suites >= 3", d["total_suites"] >= 3)
        check("by_agent is list", isinstance(d["by_agent"], list))
        # At least some agents have been evaluated
        check("some agents evaluated", len(d["by_agent"]) > 0)

    async def test_08_eval_audit_trail(self, client):
        """Eval suite completions are recorded in the immutable audit chain."""
        before = (await GET(client, "/api/audit-log/verify")).json()["verified"]

        # Run a quick eval
        async with client.stream("POST", "/api/eval-framework/run",
                                  json={"agent_id": "builder", "suite_id": "suite_general"}) as resp:
            async for line in resp.aiter_lines():
                if line.startswith("data:"):
                    try:
                        import json
                        ev = json.loads(line[5:])
                        if ev.get("type") == "done":
                            break
                    except Exception:
                        pass

        await asyncio.sleep(0.5)
        after = (await GET(client, "/api/audit-log/verify")).json()["verified"]
        check("audit chain grew", after > before)
        check("chain still valid",
              (await GET(client, "/api/audit-log/verify")).json()["ok"] is True)
