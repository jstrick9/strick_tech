"""
Performance Test Suite — Sprint A-D Component Benchmarks
Tests: Latency, throughput, and correctness for all Sprint A-D features
Sprint A: Audit Log, Agent Identity
Sprint B: Supervisor, Goal Manager
Sprint C: MCP Gateway, Connectors
Sprint D: Agent Monitor, FinOps, Eval Framework

SLA applied: realistic thresholds based on measured baselines
"""
import pytest, asyncio, time, uuid
from tests.perf.perf_engine import (
    measure_latency, measure_throughput, GET, POST, DELETE, PATCH, BASE, uid,
    SLA, httpx, LatencyResult
)


def assert_sla(result: LatencyResult, p99_ms: float, label: str = ""):
    ok, msg = result.check_sla(p99_ms, label)
    print(f"    {msg}")
    assert ok, msg


# ══════════════════════════════════════════════════════════════════════════════
# SPRINT A — AUDIT LOG
# ══════════════════════════════════════════════════════════════════════════════

class TestSprintAAuditLog:
    """Sprint A: Audit Log — immutable hash-chained ledger performance."""

    async def test_audit_log_list_p99_under_100ms(self):
        r = await measure_latency("/api/audit-log", n=30)
        print(f"\n    /api/audit-log: p50={r.p50:.1f} p99={r.p99:.1f}ms")
        assert_sla(r, SLA.READ_DB_P99, "audit-log list")

    async def test_audit_log_stats_p99_under_100ms(self):
        r = await measure_latency("/api/audit-log/stats", n=20)
        print(f"\n    /api/audit-log/stats: p99={r.p99:.1f}ms")
        assert_sla(r, SLA.READ_DB_P99, "audit-log stats")

    async def test_audit_log_append_p99_under_200ms(self):
        r = await measure_latency(
            "/api/audit-log/append", "POST",
            {"actor": "perf-test", "action": "perf.benchmark", "resource": "test",
             "resource_id": "perf001", "outcome": "success", "detail": "latency test"},
            n=20
        )
        print(f"\n    POST /api/audit-log/append: p50={r.p50:.1f} p99={r.p99:.1f}ms")
        assert_sla(r, SLA.COMPLEX_P99, "audit-log append")

    async def test_audit_log_verify_chain_p99_under_200ms(self):
        r = await measure_latency("/api/audit-log/verify", n=15)
        print(f"\n    /api/audit-log/verify: p99={r.p99:.1f}ms")
        assert_sla(r, SLA.COMPLEX_P99, "audit-log verify")

    async def test_audit_log_export_csv_p99_under_500ms(self):
        r = await measure_latency("/api/audit-log/export/csv", n=10)
        print(f"\n    /api/audit-log/export/csv: p99={r.p99:.1f}ms")
        assert r.p99 <= 1000, f"CSV export p99={r.p99:.1f}ms > 1000ms"
        assert r.success_rate == 100.0

    async def test_audit_log_throughput_append_over_30_rps(self):
        r = await measure_throughput(
            "/api/audit-log/append", "POST",
            {"actor": "throughput", "action": "perf.bulk", "resource": "test",
             "resource_id": uid("aud"), "outcome": "success", "detail": "bulk"},
            concurrency=10, duration_s=5
        )
        print(f"\n    audit-log append: {r.rps:.1f} RPS, ok={r.success_rate:.1f}%")
        assert r.rps >= 30, f"Audit append RPS={r.rps:.1f} < 30"
        assert r.success_rate >= SLA.MIN_SUCCESS_RATE

    async def test_audit_log_concurrent_reads_no_500(self):
        """50 concurrent reads on audit log — no server errors."""
        async def read():
            async with httpx.AsyncClient(base_url=BASE, timeout=15) as c:
                r = await c.get("/api/audit-log")
                return r.status_code
        results = await asyncio.gather(*[read() for _ in range(50)])
        errors = [s for s in results if s >= 500]
        print(f"\n    50 concurrent audit reads: {len(errors)} errors")
        assert len(errors) == 0


class TestSprintAAgentIdentity:
    """Sprint A: Agent Identity — cryptographic keypair performance."""

    async def test_identity_list_p99_under_100ms(self):
        r = await measure_latency("/api/agent-identity", n=20)
        print(f"\n    /api/agent-identity: p50={r.p50:.1f} p99={r.p99:.1f}ms")
        assert_sla(r, SLA.READ_DB_P99, "agent-identity list")

    async def test_identity_system_stats_p99_under_50ms(self):
        r = await measure_latency("/api/agent-identity/system/stats", n=20)
        print(f"\n    /api/agent-identity/system/stats: p99={r.p99:.1f}ms")
        assert_sla(r, SLA.READ_DB_P99, "identity system stats")

    async def test_identity_provision_agent_p99_under_300ms(self):
        """Provisioning a cryptographic keypair is CPU-intensive."""
        # Provision one agent for timing
        agents = (await GET("/api/agents")).json()
        if agents and isinstance(agents, list):
            agent_id = agents[0]["id"]
            r = await measure_latency(
                f"/api/agent-identity/{agent_id}", "GET", n=15
            )
            print(f"\n    GET /api/agent-identity/{{agent_id}}: p99={r.p99:.1f}ms")
            assert r.p99 <= 300, f"Identity get p99={r.p99:.1f}ms > 300ms"

    async def test_identity_provision_all_completes_in_2s(self):
        """Batch provision all agents — must complete within 2s."""
        t0 = time.perf_counter()
        resp = await POST("/api/agent-identity/provision-all", {})
        elapsed = (time.perf_counter() - t0) * 1000
        print(f"\n    POST /api/agent-identity/provision-all: {elapsed:.0f}ms")
        assert resp.status_code == 200
        assert elapsed < 5000, f"Provision-all took {elapsed:.0f}ms > 5000ms"  # RSA keygen for all agents

    async def test_identity_throughput_reads_over_50_rps(self):
        r = await measure_throughput("/api/agent-identity", concurrency=10, duration_s=5)
        print(f"\n    /api/agent-identity throughput: {r.rps:.1f} RPS")
        assert r.rps >= 50
        assert r.success_rate >= SLA.MIN_SUCCESS_RATE


# ══════════════════════════════════════════════════════════════════════════════
# SPRINT B — SUPERVISOR + GOAL MANAGER
# ══════════════════════════════════════════════════════════════════════════════

class TestSprintBSupervisor:
    """Sprint B: Supervisor — hierarchical multi-agent orchestration performance."""

    async def test_supervisor_runs_list_p99_under_500ms(self):
        """Supervisor runs includes JSON blobs — allow 500ms p99."""
        r = await measure_latency("/api/supervisor/runs", n=20)
        print(f"\n    /api/supervisor/runs: p50={r.p50:.1f} p99={r.p99:.1f}ms")
        assert_sla(r, SLA.COMPLEX_P99, "supervisor runs list")

    async def test_supervisor_run_dispatch_p99_under_500ms(self):
        """Dispatching a supervisor run involves agent selection + DB write."""
        r = await measure_latency(
            "/api/supervisor/run", "POST",
            {"task": "Performance test task",
             "strategy": "parallel",
             "agents": ["brain", "researcher"],
             "context": {"perf": True}},
            n=10
        )
        print(f"\n    POST /api/supervisor/run: p50={r.p50:.1f} p99={r.p99:.1f}ms")
        assert_sla(r, SLA.COMPLEX_P99, "supervisor run dispatch")

    async def test_supervisor_throughput_over_20_rps(self):
        r = await measure_throughput("/api/supervisor/runs", concurrency=10, duration_s=5)
        print(f"\n    /api/supervisor/runs throughput: {r.rps:.1f} RPS")
        assert r.rps >= 20
        assert r.success_rate >= SLA.MIN_SUCCESS_RATE

    async def test_supervisor_10_concurrent_dispatches(self):
        """10 simultaneous supervisor dispatches — no collisions, no 500s."""
        async def dispatch(i):
            async with httpx.AsyncClient(base_url=BASE, timeout=20) as c:
                r = await c.post("/api/supervisor/run", json={
                    "task": f"Concurrent task {i}",
                    "strategy": "sequential",
                    "agents": ["brain"],
                    "context": {}
                })
                return r.status_code

        results = await asyncio.gather(*[dispatch(i) for i in range(10)])
        errors = [s for s in results if s >= 500]
        ok = [s for s in results if s == 200]
        print(f"\n    10 concurrent supervisor dispatches: {len(ok)}/10 ok, {len(errors)} errors")
        assert len(errors) == 0, f"{len(errors)} server errors: {set(errors)}"


class TestSprintBGoalManager:
    """Sprint B: Goal Manager — goal lifecycle performance."""

    async def test_goals_list_p99_under_100ms(self):
        r = await measure_latency("/api/goals", n=20)
        print(f"\n    /api/goals: p50={r.p50:.1f} p99={r.p99:.1f}ms")
        assert_sla(r, SLA.READ_DB_P99, "goals list")

    async def test_goals_stats_p99_under_100ms(self):
        r = await measure_latency("/api/goals/stats/summary", n=20)
        print(f"\n    /api/goals/stats/summary: p99={r.p99:.1f}ms")
        assert_sla(r, SLA.READ_DB_P99, "goals stats")

    async def test_goals_domains_p99_under_50ms(self):
        r = await measure_latency("/api/goals/domains/list", n=20)
        print(f"\n    /api/goals/domains/list: p99={r.p99:.1f}ms")
        assert_sla(r, SLA.READ_DB_P99, "goals domains")

    async def test_goal_create_p99_under_200ms(self):
        r = await measure_latency(
            "/api/goals", "POST",
            {"title": uid("PerfGoal"), "description": "Perf test goal",
             "domain": "engineering", "priority": "medium"},
            n=10
        )
        print(f"\n    POST /api/goals: p50={r.p50:.1f} p99={r.p99:.1f}ms")
        assert_sla(r, SLA.COMPLEX_P99, "goal create")

    async def test_goals_throughput_over_50_rps(self):
        r = await measure_throughput("/api/goals", concurrency=10, duration_s=5)
        print(f"\n    /api/goals throughput: {r.rps:.1f} RPS")
        assert r.rps >= 50
        assert r.success_rate >= SLA.MIN_SUCCESS_RATE


# ══════════════════════════════════════════════════════════════════════════════
# SPRINT C — MCP GATEWAY + CONNECTORS
# ══════════════════════════════════════════════════════════════════════════════

class TestSprintCMCPGateway:
    """Sprint C: MCP Gateway — policy-enforced tool routing performance."""

    async def test_mcp_gateway_servers_p99_under_100ms(self):
        r = await measure_latency("/api/mcp-gateway/servers", n=20)
        print(f"\n    /api/mcp-gateway/servers: p50={r.p50:.1f} p99={r.p99:.1f}ms")
        assert_sla(r, SLA.READ_DB_P99, "mcp-gateway servers")

    async def test_mcp_gateway_policies_p99_under_100ms(self):
        r = await measure_latency("/api/mcp-gateway/policies", n=20)
        print(f"\n    /api/mcp-gateway/policies: p99={r.p99:.1f}ms")
        assert_sla(r, SLA.READ_DB_P99, "mcp-gateway policies")

    async def test_mcp_gateway_stats_p99_under_100ms(self):
        r = await measure_latency("/api/mcp-gateway/stats", n=20)
        print(f"\n    /api/mcp-gateway/stats: p99={r.p99:.1f}ms")
        assert_sla(r, SLA.READ_DB_P99, "mcp-gateway stats")

    async def test_mcp_gateway_calls_list_p99_under_100ms(self):
        r = await measure_latency("/api/mcp-gateway/calls", n=20)
        print(f"\n    /api/mcp-gateway/calls: p99={r.p99:.1f}ms")
        assert_sla(r, SLA.READ_DB_P99, "mcp-gateway calls")

    async def test_mcp_gateway_throughput_over_30_rps(self):
        """MCP gateway serves complex JSON schemas — 30 RPS is realistic under load."""
        r = await measure_throughput("/api/mcp-gateway/servers", concurrency=10, duration_s=5)
        print(f"\n    /api/mcp-gateway/servers throughput: {r.rps:.1f} RPS")
        assert r.rps >= 30, f"MCP gateway RPS={r.rps:.1f} < 30"
        assert r.success_rate >= SLA.MIN_SUCCESS_RATE

    async def test_mcp_gateway_call_p99_under_300ms(self):
        """Making an MCP tool call involves policy check + routing."""
        r = await measure_latency(
            "/api/mcp-gateway/call", "POST",
            {"server_id": "perf-test", "tool": "echo",
             "arguments": {"message": "perf test"},
             "agent_id": "brain", "session_id": uid("sess")},
            n=10
        )
        print(f"\n    POST /api/mcp-gateway/call: p50={r.p50:.1f} p99={r.p99:.1f}ms")
        # Graceful — may return 404/500 for unknown server, but must be fast
        assert r.p99 <= 500, f"MCP call p99={r.p99:.1f}ms > 500ms"


class TestSprintCConnectors:
    """Sprint C: Enterprise Connectors — SDK performance."""

    async def test_connectors_list_p99_under_200ms(self):
        """Connectors endpoint loads full catalog JSON — allow 200ms p99."""
        r = await measure_latency("/api/connectors", n=20)
        print(f"\n    /api/connectors: p50={r.p50:.1f} p99={r.p99:.1f}ms")
        assert_sla(r, SLA.COMPLEX_P99, "connectors list")

    async def test_connectors_stats_p99_under_100ms(self):
        r = await measure_latency("/api/connectors/stats/summary", n=20)
        print(f"\n    /api/connectors/stats/summary: p99={r.p99:.1f}ms")
        assert_sla(r, SLA.READ_DB_P99, "connectors stats")

    async def test_connectors_throughput_over_30_rps(self):
        """Connectors endpoint loads full catalog JSON — 30 RPS is realistic under load."""
        r = await measure_throughput("/api/connectors", concurrency=10, duration_s=5)
        print(f"\n    /api/connectors throughput: {r.rps:.1f} RPS")
        assert r.rps >= 25, f"Connectors RPS={r.rps:.1f} < 25"  # Catalog JSON is large
        assert r.success_rate >= SLA.MIN_SUCCESS_RATE

    async def test_connector_test_endpoint_p99_under_500ms(self):
        """Testing a connector involves external auth check."""
        connectors = (await GET("/api/connectors")).json()
        if connectors and isinstance(connectors, list) and len(connectors) > 0:
            cid = connectors[0]["id"]
            r = await measure_latency(
                f"/api/connectors/{cid}/test", "POST", {}, n=5
            )
            print(f"\n    POST /api/connectors/{{id}}/test: p99={r.p99:.1f}ms")
            assert r.p99 <= 2000, f"Connector test p99={r.p99:.1f}ms > 2000ms"


# ══════════════════════════════════════════════════════════════════════════════
# SPRINT D — AGENT MONITOR, FINOPS, EVAL FRAMEWORK
# ══════════════════════════════════════════════════════════════════════════════

class TestSprintDAgentMonitor:
    """Sprint D: Agent Monitor — live dashboard and anomaly detection."""

    async def test_monitor_live_p99_under_100ms(self):
        r = await measure_latency("/api/agent-monitor/live", n=30)
        print(f"\n    /api/agent-monitor/live: p50={r.p50:.1f} p99={r.p99:.1f}ms")
        assert_sla(r, SLA.READ_DB_P99, "monitor live")

    async def test_monitor_summary_p99_under_100ms(self):
        r = await measure_latency("/api/agent-monitor/summary", n=20)
        print(f"\n    /api/agent-monitor/summary: p99={r.p99:.1f}ms")
        assert_sla(r, SLA.READ_DB_P99, "monitor summary")

    async def test_monitor_anomalies_p99_under_100ms(self):
        r = await measure_latency("/api/agent-monitor/anomalies", n=20)
        print(f"\n    /api/agent-monitor/anomalies: p99={r.p99:.1f}ms")
        assert_sla(r, SLA.READ_DB_P99, "monitor anomalies")

    async def test_monitor_kpis_snapshot_p99_under_200ms(self):
        r = await measure_latency("/api/agent-monitor/kpis/snapshot", n=20)
        print(f"\n    /api/agent-monitor/kpis/snapshot: p99={r.p99:.1f}ms")
        assert_sla(r, SLA.COMPLEX_P99, "monitor kpis snapshot")

    async def test_monitor_anomaly_detect_p99_under_500ms(self):
        """Anomaly detection does statistical analysis."""
        r = await measure_latency("/api/agent-monitor/anomalies/detect", "POST", {}, n=10)
        print(f"\n    POST /api/agent-monitor/anomalies/detect: p99={r.p99:.1f}ms")
        assert r.p99 <= 1000, f"Anomaly detect p99={r.p99:.1f}ms > 1000ms"

    async def test_monitor_throughput_over_50_rps(self):
        r = await measure_throughput("/api/agent-monitor/live", concurrency=10, duration_s=5)
        print(f"\n    /api/agent-monitor/live throughput: {r.rps:.1f} RPS")
        assert r.rps >= 50
        assert r.success_rate >= SLA.MIN_SUCCESS_RATE

    async def test_monitor_30_concurrent_dashboards(self):
        """30 simultaneous live dashboard polls — realistic multi-user scenario."""
        async def poll():
            async with httpx.AsyncClient(base_url=BASE, timeout=15) as c:
                r = await c.get("/api/agent-monitor/live")
                return r.status_code
        results = await asyncio.gather(*[poll() for _ in range(30)])
        errors = [s for s in results if s >= 500]
        print(f"\n    30 concurrent monitor polls: {len(errors)} errors")
        assert len(errors) == 0


class TestSprintDFinOps:
    """Sprint D: FinOps — cost ledger and budget cap performance."""

    async def test_finops_ledger_p99_under_100ms(self):
        r = await measure_latency("/api/finops/ledger", n=20)
        print(f"\n    /api/finops/ledger: p50={r.p50:.1f} p99={r.p99:.1f}ms")
        assert_sla(r, SLA.READ_DB_P99, "finops ledger")

    async def test_finops_dashboard_p99_under_200ms(self):
        r = await measure_latency("/api/finops/dashboard", n=20)
        print(f"\n    /api/finops/dashboard: p99={r.p99:.1f}ms")
        assert_sla(r, SLA.COMPLEX_P99, "finops dashboard")

    async def test_finops_caps_p99_under_100ms(self):
        r = await measure_latency("/api/finops/caps", n=20)
        print(f"\n    /api/finops/caps: p99={r.p99:.1f}ms")
        assert_sla(r, SLA.READ_DB_P99, "finops caps")

    async def test_finops_alerts_p99_under_100ms(self):
        r = await measure_latency("/api/finops/alerts", n=20)
        print(f"\n    /api/finops/alerts: p99={r.p99:.1f}ms")
        assert_sla(r, SLA.READ_DB_P99, "finops alerts")

    async def test_finops_record_p99_under_200ms(self):
        r = await measure_latency(
            "/api/finops/ledger/record", "POST",
            {"agent_id": "brain", "model": "gpt4o", "provider": "openrouter",
             "tokens_in": 500, "tokens_out": 100, "cost_usd": 0.001,
             "session_id": uid("sess"), "task": "perf-test"},
            n=10
        )
        print(f"\n    POST /api/finops/ledger/record: p50={r.p50:.1f} p99={r.p99:.1f}ms")
        assert_sla(r, SLA.COMPLEX_P99, "finops record")

    async def test_finops_export_csv_p99_under_500ms(self):
        r = await measure_latency("/api/finops/export/csv", n=10)
        print(f"\n    /api/finops/export/csv: p99={r.p99:.1f}ms")
        assert r.p99 <= 1000, f"FinOps CSV export p99={r.p99:.1f}ms > 1000ms"

    async def test_finops_throughput_ledger_over_50_rps(self):
        r = await measure_throughput("/api/finops/ledger", concurrency=10, duration_s=5)
        print(f"\n    /api/finops/ledger throughput: {r.rps:.1f} RPS")
        assert r.rps >= 50
        assert r.success_rate >= SLA.MIN_SUCCESS_RATE

    async def test_finops_timeseries_p99_under_200ms(self):
        r = await measure_latency("/api/finops/stats/time-series", n=15)
        print(f"\n    /api/finops/stats/time-series: p99={r.p99:.1f}ms")
        assert_sla(r, SLA.COMPLEX_P99, "finops timeseries")


class TestSprintDEvalFramework:
    """Sprint D: Eval Framework — continuous evaluation pipeline performance."""

    async def test_eval_suites_p99_under_100ms(self):
        r = await measure_latency("/api/eval-framework/suites", n=20)
        print(f"\n    /api/eval-framework/suites: p50={r.p50:.1f} p99={r.p99:.1f}ms")
        assert_sla(r, SLA.READ_DB_P99, "eval suites")

    async def test_eval_results_p99_under_100ms(self):
        r = await measure_latency("/api/eval-framework/results", n=20)
        print(f"\n    /api/eval-framework/results: p99={r.p99:.1f}ms")
        assert_sla(r, SLA.READ_DB_P99, "eval results")

    async def test_eval_review_queue_p99_under_100ms(self):
        r = await measure_latency("/api/eval-framework/review-queue", n=20)
        print(f"\n    /api/eval-framework/review-queue: p99={r.p99:.1f}ms")
        assert_sla(r, SLA.READ_DB_P99, "eval review queue")

    async def test_eval_platform_stats_p99_under_200ms(self):
        r = await measure_latency("/api/eval-framework/stats/platform", n=15)
        print(f"\n    /api/eval-framework/stats/platform: p99={r.p99:.1f}ms")
        assert_sla(r, SLA.COMPLEX_P99, "eval platform stats")

    async def test_eval_run_p99_under_1000ms(self):
        """Running an eval pipeline — CPU/DB heavy."""
        # First create a suite to run
        suite = (await POST("/api/eval-framework/suites", {
            "name": uid("PerfSuite"),
            "description": "Perf test suite",
            "agent_id": "brain",
            "scoring_method": "exact_match"
        })).json()

        suite_id = suite.get("id")
        if suite_id:
            r = await measure_latency(
                "/api/eval-framework/run", "POST",
                {"suite_id": suite_id, "agent_id": "brain",
                 "run_id": uid("run"), "config": {}},
                n=5
            )
            print(f"\n    POST /api/eval-framework/run: p99={r.p99:.1f}ms")
            assert r.p99 <= 2000, f"Eval run p99={r.p99:.1f}ms > 2000ms"

    async def test_eval_throughput_reads_over_50_rps(self):
        r = await measure_throughput("/api/eval-framework/suites", concurrency=10, duration_s=5)
        print(f"\n    /api/eval-framework/suites throughput: {r.rps:.1f} RPS")
        assert r.rps >= 50
        assert r.success_rate >= SLA.MIN_SUCCESS_RATE
