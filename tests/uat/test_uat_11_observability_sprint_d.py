"""
UAT 11 — Observability Features (Sprint D)
User Stories:
  • As admin, I can see all agents and their real-time health
  • As admin, I track AI costs and set budgets per team/goal
  • As admin, I run evaluation suites to verify agent quality

Acceptance Criteria tested at the USER level.
"""
from __future__ import annotations
import asyncio, time, json as json_mod
import httpx, pytest
from .conftest import BASE, uid, GET, POST, PATCH, DELETE, j, accept, uat, no_error


# ══════════════════════════════════════════════════════════════════
#  USER STORY: "I can see all agents and their real-time health"
# ══════════════════════════════════════════════════════════════════
class TestUATAgentMonitor:
    """User Story: As admin, I want a real-time dashboard of all running agents."""

    async def test_admin_sees_all_agents_in_dashboard(self, U):
        """AC: Admin opens Monitor → sees all agents with status indicators."""
        r = await GET(U, "/api/agent-monitor/live")
        no_error(r, "live dashboard")
        d = j(r)
        uat("dashboard loads successfully", "agents" in d)
        uat("at least 8 agents visible", len(d["agents"]) >= 8)
        uat("summary metrics shown", "summary" in d)

        for agent in d["agents"]:
            uat(f"agent {agent['agent_id']} has status indicator", "status" in agent)
            uat(f"agent {agent['agent_id']} shows session cost", "cost_session" in agent)

    async def test_admin_can_take_kpi_snapshot(self, U):
        """AC: Admin clicks 'Snapshot KPIs' → all agent metrics captured."""
        r = await POST(U, "/api/agent-monitor/kpis/snapshot")
        no_error(r, "KPI snapshot")
        d = j(r)
        uat("snapshot captured for all agents", d["ok"] is True)
        uat("shows how many agents snapshotted", d["snapshotted"] >= 8)

    async def test_admin_can_view_agent_kpi_history(self, U):
        """AC: Admin selects an agent → sees performance trend over time."""
        r = await GET(U, "/api/agent-monitor/kpis/brain", period="hour", limit=24)
        no_error(r, "agent KPI history")
        d = j(r)
        uat("agent ID is correct", d["agent_id"] == "brain")
        uat("historical series accessible", "kpi_series" in d)
        uat("all-time metrics available", "all_time" in d)
        at = d["all_time"]
        uat("shows total tasks completed", "total_tasks" in at)
        uat("shows success rate", "success_rate" in at)
        uat("shows average latency", "avg_latency_ms" in at)

    async def test_admin_can_detect_anomalies(self, U):
        """AC: Admin clicks 'Detect Anomalies' → platform flags any unusual behavior."""
        r = await POST(U, "/api/agent-monitor/anomalies/detect")
        no_error(r, "anomaly detection")
        d = j(r)
        uat("anomaly detection ran", d["ok"] is True)
        uat("anomaly count is shown", "total_anomalies" in d)
        uat("anomaly details available", "flags" in d)

    async def test_admin_can_kill_and_revive_agent(self, U):
        """AC: Admin can immediately stop a misbehaving agent, then restore it."""
        target = "local"  # Local LLM agent

        # Kill it
        kill = await POST(U, f"/api/agent-monitor/kill/{target}", {
            "reason": "UAT testing — agent consuming too many resources"
        })
        no_error(kill, "kill agent")
        d = j(kill)
        uat("agent stopped immediately", d["ok"] is True)
        uat("agent ID confirmed in response", d["agent_id"] == target)

        # Verify stopped
        live = j(await GET(U, "/api/agent-monitor/live"))
        agent = next(a for a in live["agents"] if a["agent_id"] == target)
        uat("monitor shows agent as killed", agent["is_killed"] is True)

        # Revive it
        revive = await POST(U, f"/api/agent-monitor/revive/{target}")
        no_error(revive, "revive agent")
        uat("agent restored to idle", j(revive)["status"] == "idle")

    async def test_admin_sees_platform_health_summary(self, U):
        """AC: Platform health summary gives overall state at a glance."""
        r = await GET(U, "/api/agent-monitor/summary")
        no_error(r, "monitor summary")
        d = j(r)
        uat("shows total agent count", "total_agents" in d)
        uat("shows active agent count", "active_agents" in d)
        uat("shows unresolved anomalies", "unresolved_anomalies" in d)
        uat("shows all-time task count", "all_time_tasks" in d)
        uat("shows all-time cost", "all_time_cost" in d)


# ══════════════════════════════════════════════════════════════════
#  USER STORY: "I track AI costs and set budgets per team/goal"
# ══════════════════════════════════════════════════════════════════
class TestUATFinOps:
    """User Story: As admin, I want full visibility into AI spending and the ability to set limits."""

    async def test_admin_sees_cost_dashboard(self, U):
        """AC: Admin opens FinOps → sees total spend, daily spend, projections."""
        r = await GET(U, "/api/finops/dashboard")
        no_error(r, "finops dashboard")
        d = j(r)
        uat("shows all-time total cost", "total_cost_usd" in d)
        uat("shows today's spend", "cost_today" in d)
        uat("shows last-hour spend", "cost_last_hour" in d)
        uat("shows daily spend projection", "projected_daily" in d)
        uat("shows spending by agent", "by_agent" in d)
        uat("shows spending by source type", "by_source_type" in d)
        uat("shows active budget caps", "budget_caps" in d)

    async def test_admin_can_record_cost_attribution(self, U):
        """AC: Admin attributes cost to a specific goal/project."""
        goal_id = f"uat_cost_goal_{uid()}"
        r = await POST(U, "/api/finops/ledger/record", {
            "agent_id": "brain",
            "source_type": "llm",
            "cost_usd": 0.0125,
            "tokens": 2500,
            "tokens_in": 1000,
            "tokens_out": 1500,
            "model": "anthropic/claude-3.5-sonnet",
            "goal_id": goal_id,
            "description": "UAT: Research task for product launch"
        })
        no_error(r, "record cost")
        d = j(r)
        uat("cost recorded successfully", d["ok"] is True)
        uat("cost entry has ledger ID", d["ledger_id"].startswith("cst_"))

        # See it in goal breakdown
        rb = j(await GET(U, f"/api/finops/by-goal/{goal_id}"))
        uat("cost visible under that goal", rb["total_cost"] >= 0.0125)
        uat("token count tracked", rb["total_tokens"] >= 2500)

    async def test_admin_sets_budget_cap_per_agent(self, U):
        """AC: Admin sets daily spending limit per agent → alerts when exceeded."""
        r = await POST(U, "/api/finops/caps", {
            "name": f"UAT Agent Daily Cap [{uid()}]",
            "scope_type": "agent",
            "scope_id": "brain",
            "period": "day",
            "limit_usd": 10.00,
            "limit_tokens": 100000,
            "on_breach": "alert"
        })
        no_error(r, "create budget cap")
        d = j(r)
        uat("budget cap created", d["ok"] is True)
        cap_id = d["cap_id"]

        # See it in caps list
        caps = j(await GET(U, "/api/finops/caps"))
        cap_ids = [c["cap_id"] for c in caps["caps"]]
        uat("cap visible in admin panel", cap_id in cap_ids)

        # Cleanup
        await U.delete(f"/api/finops/caps/{cap_id}")

    async def test_admin_can_view_cost_time_series(self, U):
        """AC: Admin sees spending trend chart (hourly/daily)."""
        r = await GET(U, "/api/finops/stats/time-series", days=7, granularity="hour")
        no_error(r, "cost time series")
        d = j(r)
        uat("time series data accessible", "series" in d)
        uat("granularity matches request", d["granularity"] == "hour")

    async def test_admin_can_download_cost_report(self, U):
        """AC: Finance team can download CSV cost report."""
        r = await U.get("/api/finops/export/csv?days=30")
        no_error(r, "export cost CSV")
        uat("CSV file returned", "csv" in r.headers.get("content-type",""))
        lines = r.text.strip().split("\n")
        uat("CSV has header row", len(lines) >= 1)
        uat("cost_usd column present", "cost_usd" in lines[0])

    async def test_admin_sees_budget_alerts(self, U):
        """AC: Budget alerts appear when spending approaches limits."""
        r = await GET(U, "/api/finops/alerts")
        no_error(r, "budget alerts")
        d = j(r)
        uat("alert list accessible", "alerts" in d)
        uat("alert count shown", "count" in d)


# ══════════════════════════════════════════════════════════════════
#  USER STORY: "I run evaluation suites to verify agent quality"
# ══════════════════════════════════════════════════════════════════
class TestUATEvalFramework:
    """User Story: As admin, I want to verify that my agents are performing well."""

    async def test_admin_sees_eval_suites(self, U):
        """AC: Admin opens Evals → sees pre-built test suites ready to run."""
        r = await GET(U, "/api/eval-framework/suites")
        no_error(r, "eval suites")
        d = j(r)
        uat("eval suites accessible", "suites" in d)
        # Seeded suites plus any created during testing
        uat("eval suites available", d["count"] >= 3)
        suite_names = [s["name"] for s in d["suites"]]
        uat("General Capability suite present",
            any("General" in n or "general" in n.lower() for n in suite_names))
        for suite in d["suites"][:3]:
            uat("suite shows name", "name" in suite)
            uat("suite shows pass threshold", 0 < suite["pass_threshold"] <= 1.0)

    async def test_admin_can_add_test_case(self, U):
        """AC: Admin adds a custom test case to a suite."""
        r = await POST(U, "/api/eval-framework/suites/suite_general/cases", {
            "prompt": "What is the capital of France?",
            "expected": "Paris",
            "criteria": ["correct city", "specific answer"],
            "difficulty": "easy"
        })
        no_error(r, "add test case")
        d = j(r)
        uat("test case added", d["ok"] is True)
        uat("case has ID", d["case_id"].startswith("case_"))

    async def test_admin_runs_eval_suite_and_sees_results(self, U):
        """AC: Admin clicks Run → sees pass/fail results for each test case."""
        events = []
        async with U.stream("POST", "/api/eval-framework/run",
                             json={"agent_id": "builder", "suite_id": "suite_code"}) as resp:
            no_error(resp, "run eval suite")
            async for line in resp.aiter_lines():
                if line.startswith("data:"):
                    try:
                        ev = json_mod.loads(line[5:])
                        events.append(ev)
                        if ev.get("type") in ("done", "case_done"):
                            break
                    except Exception:
                        pass
                if len(events) >= 3:
                    break

        uat("eval run produces streaming events", len(events) > 0)
        event_types = {e.get("type") for e in events}
        uat("eval run streams start or case_done events",
            "start" in event_types or "case_done" in event_types)

    async def test_admin_sees_review_queue_for_low_scores(self, U):
        """AC: Low-scoring results appear in Human Review queue for inspection."""
        r = await GET(U, "/api/eval-framework/review-queue", limit=10)
        no_error(r, "review queue")
        d = j(r)
        uat("review queue accessible", "queue" in d)
        uat("queue count visible", "count" in d)

    async def test_admin_sees_agent_eval_summary(self, U):
        """AC: Admin selects an agent → sees their eval performance history."""
        r = await GET(U, "/api/eval-framework/summary/builder", days=30)
        no_error(r, "agent eval summary")
        d = j(r)
        uat("agent ID correct", d["agent_id"] == "builder")
        uat("total evals count shown", "total_evals" in d)
        uat("pass rate shown", "pass_rate" in d and 0 <= d["pass_rate"] <= 1.0)
        uat("avg score shown", "avg_score" in d)
        uat("safety score shown", "avg_safety" in d)
        uat("pending reviews count shown", "review_pending" in d)

    async def test_admin_creates_custom_eval_suite(self, U):
        """AC: Admin creates domain-specific test suite for their use case."""
        r = await POST(U, "/api/eval-framework/suites", {
            "name": f"UAT Custom Suite: Customer Support [{uid()}]",
            "domain": "customer_support",
            "pass_threshold": 0.85
        })
        no_error(r, "create custom suite")
        d = j(r)
        uat("custom suite created", d["ok"] is True)
        uat("suite has ID", d["suite_id"].startswith("suite_"))

    async def test_platform_eval_stats_visible(self, U):
        """AC: Platform-wide eval statistics are accessible to admins."""
        r = await GET(U, "/api/eval-framework/stats/platform")
        no_error(r, "platform eval stats")
        d = j(r)
        uat("total evals count", "total_evals" in d)
        uat("total suites count", "total_suites" in d)
        uat("by-agent breakdown", "by_agent" in d)
        uat("pending review count", "pending_review" in d)
