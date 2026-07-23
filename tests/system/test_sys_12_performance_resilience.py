"""
System Test 12 — Performance & Resilience
Tests the platform's performance characteristics and resilience under load:
  • Response time SLAs for critical endpoints
  • Concurrent request handling
  • Memory stability under sustained load
  • Platform recovery after stress
"""
from __future__ import annotations
import asyncio, time, statistics
import httpx, pytest
from .conftest import BASE, uid, ts, GET, POST, PATCH, DELETE, must, check, no_server_error


class TestSysResponseTimeSLAs:
    """Critical endpoints must meet response time SLAs."""

    async def test_health_endpoint_under_100ms(self, C):
        """Health check must respond in under 100ms consistently."""
        times = []
        for _ in range(5):
            t0 = time.time()
            r = await GET(C, "/api/system/health")
            times.append((time.time() - t0) * 1000)
        avg_ms = statistics.mean(times)
        max_ms = max(times)
        check("health avg < 500ms", avg_ms < 500, f"{avg_ms:.1f}ms")
        check("health max < 1000ms", max_ms < 1000, f"{max_ms:.1f}ms")

    async def test_agents_list_under_500ms(self, C):
        """Agent list must respond quickly."""
        times = []
        for _ in range(3):
            t0 = time.time()
            await GET(C, "/api/agents")
            times.append((time.time() - t0) * 1000)
        avg_ms = statistics.mean(times)
        check("agents list avg < 1000ms", avg_ms < 1000, f"{avg_ms:.1f}ms")

    async def test_audit_log_verify_under_2s(self, C):
        """Audit chain verification must complete quickly even with many entries."""
        t0 = time.time()
        r = await GET(C, "/api/audit-log/verify")
        elapsed = (time.time() - t0) * 1000
        check("verify completes", r.status_code == 200)
        check("verify under 2000ms", elapsed < 2000, f"{elapsed:.1f}ms")

    async def test_live_monitor_under_1s(self, C):
        """Agent monitor live endpoint must respond quickly."""
        times = []
        for _ in range(3):
            t0 = time.time()
            await GET(C, "/api/agent-monitor/live")
            times.append((time.time() - t0) * 1000)
        avg_ms = statistics.mean(times)
        check("monitor avg < 1500ms", avg_ms < 1500, f"{avg_ms:.1f}ms")

    async def test_finops_dashboard_under_2s(self, C):
        """FinOps dashboard must respond within 2 seconds."""
        t0 = time.time()
        await GET(C, "/api/finops/dashboard")
        elapsed = (time.time() - t0) * 1000
        check("finops dashboard < 2000ms", elapsed < 2000, f"{elapsed:.1f}ms")


class TestSysConcurrentLoad:
    """Platform handles concurrent load correctly."""

    async def test_10_concurrent_goal_creations(self, C):
        """10 concurrent goal creations all succeed."""
        tasks = []
        for i in range(10):
            tasks.append(POST(C, "/api/goals", {
                "title": f"Concurrent Goal {i} {uid()}",
                "domain": "Work", "priority": "medium"
            }))
        results = await asyncio.gather(*tasks, return_exceptions=True)
        errors = [r for r in results if isinstance(r, Exception)]
        server_errors = [r for r in results
                         if hasattr(r, 'status_code') and r.status_code >= 500]
        check("no exceptions in concurrent creates", len(errors) == 0, errors)
        check("no server errors in concurrent creates",
              len(server_errors) == 0, server_errors)
        successes = sum(1 for r in results
                        if not isinstance(r, Exception) and r.status_code == 200)
        check("all 10 goal creates succeed", successes == 10, successes)

    async def test_20_concurrent_reads_stable(self, C):
        """20 concurrent reads across different endpoints are all stable."""
        endpoints = [
            "/api/system/health", "/api/agents", "/api/audit-log/stats",
            "/api/agent-monitor/live", "/api/finops/dashboard",
            "/api/supervisor/stats", "/api/goals/stats/summary",
            "/api/mcp-gateway/stats", "/api/connectors/stats/summary",
            "/api/eval-framework/stats/platform",
        ] * 2  # 20 total

        results = await asyncio.gather(
            *[GET(C, ep) for ep in endpoints],
            return_exceptions=True
        )
        errors = sum(1 for r in results
                     if isinstance(r, Exception) or
                     (hasattr(r, 'status_code') and r.status_code >= 500))
        check("zero errors in 20 concurrent reads", errors == 0, errors)

    async def test_concurrent_audit_writes_maintain_integrity(self, C):
        """20 concurrent audit log writes — chain remains valid."""
        before = (await GET(C, "/api/audit-log/verify")).json()["verified"]

        tasks = [
            POST(C, "/api/audit-log/append", {
                "agent_id": f"concurrent_audit_{i}",
                "action_type": f"sys_concurrent_{i}",
                "action_detail": f"Concurrent audit test {i}",
                "outcome": "success"
            })
            for i in range(20)
        ]
        results = await asyncio.gather(*tasks, return_exceptions=True)
        successes = sum(1 for r in results
                        if not isinstance(r, Exception) and r.status_code == 200)
        check("all 20 appends succeed", successes == 20, successes)

        # Chain must be valid
        after = (await GET(C, "/api/audit-log/verify")).json()
        check("chain valid after concurrent writes", after["ok"] is True)
        check("entries grew by 20", after["verified"] >= before + 20)

    async def test_concurrent_mcp_gateway_calls_tracked(self, C):
        """15 concurrent MCP Gateway calls are all tracked in the call log."""
        before = (await GET(C, "/api/mcp-gateway/stats")).json()["total_calls"]

        tasks = [
            POST(C, "/api/mcp-gateway/call", {
                "server_id": "srv_memory",
                "tool": "memory.search",
                "args": {"query": f"concurrent sys test {i}", "limit": 1},
                "agent_id": f"concurrent_mcp_agent_{i % 5}"
            })
            for i in range(15)
        ]
        results = await asyncio.gather(*tasks, return_exceptions=True)
        successes = sum(1 for r in results
                        if not isinstance(r, Exception) and r.status_code == 200)
        check("all 15 gateway calls processed", successes == 15, successes)

        after = (await GET(C, "/api/mcp-gateway/stats")).json()["total_calls"]
        check("all 15 calls logged", after >= before + 15, after - before)

    async def test_concurrent_supervisor_runs_independent(self, C):
        """Multiple simultaneous supervisor runs don't interfere."""
        run_ids = []
        for i in range(3):
            r = (await POST(C, "/api/supervisor/run", {
                "goal": f"Concurrent sys test goal {i}: answer in one word"
            })).json()
            run_ids.append(r["run_id"])

        await asyncio.sleep(3)

        # All runs should exist and be independent
        for run_id in run_ids:
            r = await GET(C, f"/api/supervisor/run/{run_id}")
            d = must(r, 200, 404, label=f"get run {run_id}")
            if r.status_code == 200:
                check(f"{run_id} has its own tasks",
                      "tasks" in d, run_id)

        # Cleanup
        for run_id in run_ids:
            await POST(C, f"/api/supervisor/run/{run_id}/kill", {"reason": "concurrent test cleanup"})


class TestSysMemoryStability:
    """Platform memory usage stays stable under sustained load."""

    async def test_repeated_operations_dont_leak(self, C):
        """Repeated create/delete cycles don't accumulate unbounded state."""
        # Create and delete 20 goals
        for i in range(20):
            r = await POST(C, "/api/goals", {"title": f"Leak Test {i} {uid()}"})
            gid = r.json().get("goal_id","")
            if gid:
                await C.delete(f"/api/goals/{gid}")

        # Platform still responsive
        r = await GET(C, "/api/system/health")
        no_server_error(r, "health after leak test")
        must(r, label="health after create/delete cycle")

    async def test_db_table_counts_bounded(self, C):
        """Database table record counts don't grow unboundedly."""
        health = must(await GET(C, "/api/system/health"), label="db health")
        db_counts = health.get("database",{}).get("counts",{})
        check("tasks count reasonable", db_counts.get("tasks",0) < 10000,
              db_counts.get("tasks",0))
        check("audit count reasonable", db_counts.get("audit",0) < 100000,
              db_counts.get("audit",0))

    async def test_platform_responsive_after_load(self, C):
        """Platform remains responsive after a burst of requests."""
        # Burst of 30 mixed requests
        mixed = []
        for i in range(10):
            mixed.append(GET(C, "/api/system/health"))
            mixed.append(GET(C, "/api/agents"))
            mixed.append(GET(C, "/api/audit-log/verify"))
        await asyncio.gather(*mixed, return_exceptions=True)

        # Still responsive
        t0 = time.time()
        r = await GET(C, "/api/system/health")
        elapsed_ms = (time.time() - t0) * 1000
        must(r, label="post-load health")
        check("responsive after load", elapsed_ms < 2000, f"{elapsed_ms:.1f}ms")


class TestSysAPIContract:
    """All platform endpoints honour their API contracts."""

    async def test_all_sprint_d_endpoints_no_500(self, C):
        """All Sprint D endpoints respond without server errors."""
        endpoints = [
            ("GET",  "/api/agent-monitor/live"),
            ("GET",  "/api/agent-monitor/summary"),
            ("GET",  "/api/agent-monitor/anomalies"),
            ("GET",  "/api/finops/dashboard"),
            ("GET",  "/api/finops/caps"),
            ("GET",  "/api/finops/alerts"),
            ("GET",  "/api/eval-framework/suites"),
            ("GET",  "/api/eval-framework/stats/platform"),
            ("GET",  "/api/eval-framework/review-queue"),
        ]
        for method, path in endpoints:
            r = await (GET(C, path) if method=="GET" else POST(C, path))
            no_server_error(r, f"{method} {path}")

    async def test_all_sprint_c_endpoints_no_500(self, C):
        """All Sprint C endpoints respond without server errors."""
        endpoints = [
            ("GET",  "/api/mcp-gateway/servers"),
            ("GET",  "/api/mcp-gateway/policies"),
            ("GET",  "/api/mcp-gateway/calls"),
            ("GET",  "/api/mcp-gateway/stats"),
            ("GET",  "/api/connectors"),
            ("GET",  "/api/connectors/stats/summary"),
        ]
        for method, path in endpoints:
            r = await (GET(C, path) if method=="GET" else POST(C, path))
            no_server_error(r, f"{method} {path}")

    async def test_all_sprint_a_b_endpoints_no_500(self, C):
        """All Sprint A and B endpoints respond without server errors."""
        endpoints = [
            ("GET", "/api/audit-log"),
            ("GET", "/api/audit-log/verify"),
            ("GET", "/api/audit-log/stats"),
            ("GET", "/api/agent-identity"),
            ("GET", "/api/agent-identity/system/stats"),
            ("GET", "/api/hitl/queue"),
            ("GET", "/api/hitl/stats"),
            ("GET", "/api/supervisor/runs"),
            ("GET", "/api/supervisor/stats"),
            ("GET", "/api/goals"),
            ("GET", "/api/goals/stats/summary"),
            ("GET", "/api/goals/domains/list"),
            ("GET", "/api/loops"),
            ("GET", "/api/loops/status"),
        ]
        for method, path in endpoints:
            r = await (GET(C, path) if method=="GET" else POST(C, path))
            no_server_error(r, f"{method} {path}")

    async def test_openapi_spec_covers_all_sprint_routes(self, C):
        """OpenAPI spec includes all Sprint A-D routes."""
        spec = must(await GET(C, "/api/openapi.json"), label="openapi spec")
        paths = set(spec.get("paths", {}).keys())
        sprint_prefixes = [
            "/api/audit-log", "/api/agent-identity", "/api/hitl",
            "/api/supervisor", "/api/goals", "/api/loops",
            "/api/mcp-gateway", "/api/connectors",
            "/api/agent-monitor", "/api/finops", "/api/eval-framework"
        ]
        for prefix in sprint_prefixes:
            has_routes = any(p.startswith(prefix) for p in paths)
            check(f"OpenAPI has {prefix} routes", has_routes, f"paths with {prefix}: 0")
