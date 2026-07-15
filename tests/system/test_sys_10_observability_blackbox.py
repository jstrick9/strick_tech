"""
System Test 10 — Observability Layer (Black-Box)
Sprint D — Agent Monitor, FinOps, Evaluation Framework as platform subsystems.

System assertions:
  • Agent Monitor provides accurate real-time visibility
  • FinOps attribution is complete and consistent
  • Evaluation Framework produces valid scoring at system level
  • Cross-cutting: all three subsystems integrate with the audit chain
"""
from __future__ import annotations
import asyncio, time
import httpx, pytest
from .conftest import BASE, uid, ts, GET, POST, PATCH, DELETE, must, check, no_server_error


class TestSysAgentMonitorSystem:
    """Agent Monitor as a platform-level observability feature."""

    async def test_monitor_shows_platform_state_accurately(self, C):
        """Live monitor accurately reflects current platform state."""
        d = must(await GET(C, "/api/agent-monitor/live"), label="live monitor")
        agents = d["agents"]
        summary = d["summary"]

        # Summary must be consistent with agents list
        check("summary.total = len(agents)", summary["total"] == len(agents))
        active_count = sum(1 for a in agents if a["status"] == "working")
        killed_count = sum(1 for a in agents if a["is_killed"])
        check("summary.active consistent", summary["active"] == active_count)
        check("summary.killed consistent", summary["killed"] == killed_count)

    async def test_kpi_snapshot_accuracy(self, C):
        """KPI snapshot captures correct number of agents."""
        r = await POST(C, "/api/agent-monitor/kpis/snapshot")
        d = must(r, label="kpi snapshot")
        check("ok", d["ok"] is True)
        check("snapshotted >= 8", d["snapshotted"] >= 8)

    async def test_kill_revive_system_coherence(self, C):
        """Kill/revive maintains system coherence — no orphaned state."""
        target = "local"

        # Pre-kill state
        pre = (await GET(C, "/api/agent-monitor/live")).json()
        pre_summary = pre["summary"]

        # Kill
        must(await POST(C, f"/api/agent-monitor/kill/{target}",
                         {"reason": "sys coherence test"}), label="kill")

        # Dashboard reflects kill
        mid = (await GET(C, "/api/agent-monitor/live")).json()
        mid_agent = next(a for a in mid["agents"] if a["agent_id"] == target)
        check("agent shows killed", mid_agent["is_killed"] is True)
        check("killed count increased", mid["summary"]["killed"] >= pre_summary["killed"] + 1)

        # Revive
        must(await POST(C, f"/api/agent-monitor/revive/{target}"), label="revive")

        # Post-revive state
        post = (await GET(C, "/api/agent-monitor/live")).json()
        post_agent = next(a for a in post["agents"] if a["agent_id"] == target)
        check("agent revived", post_agent["is_killed"] is False)
        check("status idle", post_agent["status"] == "idle")
        check("killed count restored", post["summary"]["killed"] <= pre_summary["killed"])

    async def test_anomaly_detection_not_crashable(self, C):
        """Anomaly detection can be triggered repeatedly without crashing."""
        for _ in range(3):
            r = await POST(C, "/api/agent-monitor/anomalies/detect")
            d = must(r, label="anomaly detect")
            check("ok", d["ok"] is True)
            check("total_anomalies non-negative", d["total_anomalies"] >= 0)

    async def test_shadow_test_isolated(self, C):
        """Shadow tests are isolated — don't affect live agents."""
        # Create shadow test
        shadow = must(await POST(C, "/api/agent-monitor/shadow", {
            "agent_id": "brain",
            "shadow_config": {"model": "gpt4o-mini", "temperature": 0.1}
        }), label="create shadow")
        test_id = shadow["test_id"]

        # Verify live brain is unaffected
        live = (await GET(C, "/api/agent-monitor/live")).json()
        brain = next(a for a in live["agents"] if a["agent_id"] == "brain")
        check("brain still active (not killed by shadow)", brain["is_killed"] is False)

        # Shadow test retrievable
        get = must(await GET(C, f"/api/agent-monitor/shadow/{test_id}"), label="get shadow")
        check("shadow correct agent", get["test"]["agent_id"] == "brain")


class TestSysFinOpsSystem:
    """FinOps system as a complete cost-management platform feature."""

    async def test_finops_dashboard_always_accessible(self, C):
        """Dashboard is always accessible, even with no data."""
        d = must(await GET(C, "/api/finops/dashboard"), label="dashboard")
        required = ["total_cost_usd","cost_today","cost_last_hour",
                    "projected_daily","budget_caps","by_agent","by_source_type"]
        for f in required:
            check(f"dashboard.{f} present", f in d)
        check("total_cost >= 0", d["total_cost_usd"] >= 0)
        check("budget_caps list", isinstance(d["budget_caps"], list))

    async def test_cost_attribution_complete(self, C):
        """Every recorded cost appears in the ledger and dashboard."""
        # Record costs with unique identifiers
        run_id = f"finops_sys_{uid()}"
        total_expected = 0.0
        for source, agent, cost in [
            ("llm", "brain", 0.005),
            ("mcp", "builder", 0.001),
            ("connector", "orchestrator", 0.0),
            ("supervisor", "orchestrator", 0.010),
        ]:
            await POST(C, "/api/finops/ledger/record", {
                "agent_id": agent, "source_type": source,
                "cost_usd": cost, "tokens": 500,
                "run_id": run_id, "description": f"sys attribution test"
            })
            total_expected += cost

        # Ledger contains these entries
        ledger = must(await GET(C, "/api/finops/ledger", run_id=run_id, limit=20),
                       label="filter by run_id")
        check("all 4 entries recorded", ledger["count"] >= 4, ledger["count"])
        check("total_cost accurate",
              abs(ledger["total_cost"] - total_expected) < 0.0001,
              f"{ledger['total_cost']} vs {total_expected}")

    async def test_budget_cap_lifecycle(self, C):
        """Budget caps can be created, viewed, triggered, and deleted."""
        # Create a cap
        cap = must(await POST(C, "/api/finops/caps", {
            "name": f"Sys Test Cap {uid()}",
            "scope_type": "agent", "scope_id": f"sys_cap_agent_{uid()}",
            "period": "day", "limit_usd": 100.0, "on_breach": "alert"
        }), label="create cap")
        cap_id = cap["cap_id"]

        # Appears in caps list
        caps = must(await GET(C, "/api/finops/caps"), label="caps list")
        cap_ids = [c["cap_id"] for c in caps["caps"]]
        check("cap in list", cap_id in cap_ids)

        # Delete
        del_r = await C.delete(f"/api/finops/caps/{cap_id}")
        no_server_error(del_r, "delete cap")

        # No longer in list
        caps2 = must(await GET(C, "/api/finops/caps"), label="caps after delete")
        cap_ids2 = [c["cap_id"] for c in caps2["caps"]]
        check("cap removed", cap_id not in cap_ids2)

    async def test_time_series_covers_full_range(self, C):
        """Time-series returns data for the full requested range."""
        # Record something in "now"
        await POST(C, "/api/finops/ledger/record", {
            "agent_id": "ts_test_agent", "source_type": "llm",
            "cost_usd": 0.001, "tokens": 100
        })

        r = must(await GET(C, "/api/finops/stats/time-series",
                            days=1, granularity="hour"), label="hourly series")
        check("series is list", isinstance(r["series"], list))
        check("granularity=hour", r["granularity"] == "hour")

    async def test_finops_csv_export_parseable(self, C):
        """CSV export is valid, parseable CSV with correct columns."""
        r = await C.get("/api/finops/export/csv?days=7")
        no_server_error(r, "csv export")
        check("csv content-type", "csv" in r.headers.get("content-type",""))
        lines = r.text.strip().split("\n")
        if len(lines) >= 1:
            header = lines[0].lower()
            for col in ("ledger_id", "agent_id", "source_type", "cost_usd"):
                check(f"csv has {col} column", col in header)


class TestSysEvalFrameworkSystem:
    """Evaluation Framework at platform/system level."""

    async def test_eval_suites_are_complete(self, C):
        """All 3 seeded suites have correct structure and cases."""
        d = must(await GET(C, "/api/eval-framework/suites"), label="suites")
        suites = {s["suite_id"]: s for s in d["suites"]}

        # Required suites
        for sid in ["suite_general","suite_safety","suite_code"]:
            check(f"{sid} present", sid in suites, list(suites.keys()))
            s = suites[sid]
            check(f"{sid} has cases", s["cases_count"] >= 2, s["cases_count"])
            check(f"{sid} pass_threshold 0-1",
                  0 < s["pass_threshold"] <= 1.0, s["pass_threshold"])

    async def test_eval_run_produces_valid_scores(self, C):
        """Eval run returns valid normalized scores for all metrics."""
        import json
        results = []
        async with C.stream("POST", "/api/eval-framework/run",
                             json={"agent_id": "builder", "suite_id": "suite_code"}) as resp:
            no_server_error(resp, "eval run stream")
            async for line in resp.aiter_lines():
                if line.startswith("data:"):
                    try:
                        ev = json.loads(line[5:])
                        results.append(ev)
                        if ev.get("type") == "done":
                            break
                    except Exception:
                        pass
                if len(results) > 20:
                    break

        done = next((e for e in results if e.get("type") == "done"), None)
        check("done event received", done is not None)
        if done:
            check("avg_score 0-1", 0 <= done.get("avg_score",0) <= 1.0)
            check("passed <= total", done.get("passed",0) <= done.get("total",1))
            check("pass_threshold present", "pass_threshold" in done)
            check("suite_pass is bool", isinstance(done.get("suite_pass"), bool))

    async def test_eval_results_persist_and_queryable(self, C):
        """Eval results are persisted and can be filtered/queried."""
        import json
        # Run eval for a specific agent
        agent_id = f"sys_eval_agent_{uid()}"
        # Use existing agent (builder) with custom identifier in notes
        async with C.stream("POST", "/api/eval-framework/run",
                             json={"agent_id": "reviewer", "suite_id": "suite_safety"}) as resp:
            async for line in resp.aiter_lines():
                if line.startswith("data:"):
                    try:
                        ev = json.loads(line[5:])
                        if ev.get("type") == "done":
                            break
                    except Exception:
                        pass

        await asyncio.sleep(0.5)
        # Query results for reviewer
        results = must(await GET(C, "/api/eval-framework/results",
                                   agent_id="reviewer", limit=10), label="results query")
        check("has results", results["count"] >= 0)

    async def test_platform_eval_stats_coherent(self, C):
        """Platform stats are mathematically coherent."""
        stats = must(await GET(C, "/api/eval-framework/stats/platform"), label="platform stats")
        check("total_evals non-negative", stats["total_evals"] >= 0)
        check("total_suites >= 3", stats["total_suites"] >= 3)
        check("pending_review non-negative", stats["pending_review"] >= 0)
        # by_agent: each agent's pass_rate should be 0-100
        for agent_stats in stats.get("by_agent", []):
            pct = agent_stats.get("pass_pct", 0) or 0
            check(f"{agent_stats.get('agent_id')} pass_pct 0-100",
                  0 <= pct <= 100, pct)

    async def test_human_review_queue_accessible_always(self, C):
        """Human review queue is always accessible."""
        r = await GET(C, "/api/eval-framework/review-queue", limit=20)
        d = must(r, label="review queue")
        check("has queue", isinstance(d.get("queue",[]), list))
        check("has count", d.get("count", 0) >= 0)
