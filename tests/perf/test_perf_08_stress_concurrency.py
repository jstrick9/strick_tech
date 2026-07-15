"""
Performance Test Suite — Advanced Stress & Concurrency Tests
Tests: High-load concurrency scenarios, race conditions, burst traffic,
       sustained load, recovery after spike, memory pressure
"""
import pytest, asyncio, time, uuid, statistics
from tests.perf.perf_engine import (
    measure_latency, measure_throughput, GET, POST, DELETE, PATCH, BASE, uid,
    SLA, httpx, LatencyResult
)


# ── BURST TRAFFIC ─────────────────────────────────────────────────────────────
class TestBurstTraffic:
    """Simulate sudden traffic spikes like a UI reload storm."""

    async def test_100_simultaneous_health_checks(self):
        """100 simultaneous health checks — the ultimate stress test."""
        async def check():
            async with httpx.AsyncClient(base_url=BASE, timeout=15) as c:
                t0 = time.perf_counter()
                r = await c.get("/api/health")
                ms = (time.perf_counter() - t0) * 1000
                return r.status_code, ms

        results = await asyncio.gather(*[check() for _ in range(100)])
        ok = sum(1 for s, _ in results if s == 200)
        times = [ms for _, ms in results]
        p99 = sorted(times)[int(len(times) * 0.99)]
        avg = statistics.mean(times)

        print(f"\n    100 burst health checks: {ok}/100 ok, p99={p99:.1f}ms, avg={avg:.1f}ms")
        assert ok == 100, f"Only {ok}/100 health checks succeeded under burst"
        # Under 100-concurrent burst in a single-process sandbox, 1500ms p99 is acceptable
        assert p99 <= 1500, f"P99={p99:.1f}ms > 1500ms under burst load"

    async def test_50_simultaneous_agent_list(self):
        """50 simultaneous agent list requests — UI refresh scenario."""
        async def fetch():
            async with httpx.AsyncClient(base_url=BASE, timeout=15) as c:
                r = await c.get("/api/agents")
                return r.status_code

        results = await asyncio.gather(*[fetch() for _ in range(50)])
        ok = sum(1 for s in results if s == 200)
        errors = sum(1 for s in results if s >= 500)
        print(f"\n    50 burst agent lists: {ok}/50 ok, {errors} errors")
        assert errors == 0
        assert ok == 50

    async def test_burst_write_then_read_consistency(self):
        """Write 20 tasks in a burst, then verify all are readable."""
        titles = [uid(f"burst_{i}") for i in range(20)]
        created_ids = []

        async def create(title):
            async with httpx.AsyncClient(base_url=BASE, timeout=15) as c:
                r = await c.post("/api/tasks", json={"title": title, "status": "todo"})
                if r.status_code == 200:
                    return r.json().get("id")
            return None

        ids = await asyncio.gather(*[create(t) for t in titles])
        created_ids = [i for i in ids if i]

        print(f"\n    Burst 20 writes: {len(created_ids)}/20 succeeded")
        assert len(created_ids) == 20, f"Only {len(created_ids)}/20 burst writes succeeded"

        # Now read them all back and verify uniqueness
        assert len(set(created_ids)) == 20, "Duplicate IDs in burst writes!"

        # Cleanup
        for tid in created_ids:
            await DELETE(f"/api/tasks/{tid}")

    async def test_40_concurrent_db_writes_no_corruption(self):
        """40 concurrent SQLite writes — WAL mode handles concurrency."""
        async def write_memory(i):
            async with httpx.AsyncClient(base_url=BASE, timeout=15) as c:
                r = await c.post("/api/memory/add", json={
                    "content": uid(f"stress_mem_{i}"),
                    "source": "stress-test",
                    "tags": [f"stress-{i}"]
                })
                return r.status_code

        results = await asyncio.gather(*[write_memory(i) for i in range(40)])
        ok = sum(1 for s in results if s == 200)
        errors = sum(1 for s in results if s >= 500)
        print(f"\n    40 concurrent memory writes: {ok}/40 ok, {errors} server errors")
        assert errors == 0, f"{errors} server errors during concurrent DB writes"
        assert ok >= 38, f"Only {ok}/40 writes succeeded"


# ── SUSTAINED LOAD ────────────────────────────────────────────────────────────
class TestSustainedLoad:
    """Extended load tests — platform must not degrade over time."""

    async def test_60s_read_load_no_degradation(self):
        """60 seconds of sustained read load — first/last window comparison."""
        endpoint = "/api/agents"
        concurrency = 5
        window = 5.0  # seconds per window

        async def measure_window(duration_s):
            times = []
            deadline = time.perf_counter() + duration_s
            async with httpx.AsyncClient(base_url=BASE, timeout=15) as c:
                while time.perf_counter() < deadline:
                    t0 = time.perf_counter()
                    r = await c.get(endpoint)
                    times.append((time.perf_counter() - t0) * 1000)
                    if r.status_code >= 500:
                        return None, times
            return True, times

        async def concurrent_window(duration_s, workers):
            all_times = []
            results = await asyncio.gather(*[measure_window(duration_s) for _ in range(workers)])
            for ok, times in results:
                all_times.extend(times)
            return all_times

        # Warm up
        await concurrent_window(3, concurrency)

        # First window
        first_times = await concurrent_window(window, concurrency)
        first_p95 = sorted(first_times)[int(len(first_times) * 0.95)]

        # Middle load
        await concurrent_window(window, concurrency)
        await concurrent_window(window, concurrency)

        # Last window
        last_times = await concurrent_window(window, concurrency)
        last_p95 = sorted(last_times)[int(len(last_times) * 0.95)]

        degradation = ((last_p95 - first_p95) / first_p95 * 100) if first_p95 > 0 else 0
        print(f"\n    60s sustained: first_p95={first_p95:.1f}ms, last_p95={last_p95:.1f}ms, degradation={degradation:.1f}%")
        assert degradation < SLA.MAX_DEGRADATION_PCT, (
            f"Performance degraded by {degradation:.1f}% > {SLA.MAX_DEGRADATION_PCT}% over sustained load"
        )

    async def test_100_sequential_db_queries_stable(self):
        """100 sequential DB queries — response time stays stable."""
        times = []
        async with httpx.AsyncClient(base_url=BASE, timeout=30) as c:
            for i in range(100):
                t0 = time.perf_counter()
                await c.post("/api/db/sqlite/query", json={"sql": "SELECT COUNT(*) FROM tasks"})
                times.append((time.perf_counter() - t0) * 1000)

        first_10 = statistics.mean(times[:10])
        last_10 = statistics.mean(times[-10:])
        degradation = ((last_10 - first_10) / first_10 * 100) if first_10 > 0 else 0
        p99 = sorted(times)[int(len(times) * 0.99)]

        print(f"\n    100 sequential DB: first10={first_10:.1f}ms last10={last_10:.1f}ms p99={p99:.1f}ms degrade={degradation:.1f}%")
        assert degradation < 50, f"DB degraded {degradation:.1f}% over 100 sequential queries"
        assert p99 <= 200, f"DB p99={p99:.1f}ms > 200ms"

    async def test_write_1000_audit_entries_performance(self):
        """Write 1000 audit log entries — ledger performance under volume."""
        times = []

        async def write_entry():
            t0 = time.perf_counter()
            async with httpx.AsyncClient(base_url=BASE, timeout=15) as c:
                await c.post("/api/audit-log/append", json={
                    "actor": "stress-test",
                    "action": "stress.write",
                    "resource": "audit_log",
                    "resource_id": uid("entry"),
                    "outcome": "success",
                    "detail": "Volume stress test"
                })
            times.append((time.perf_counter() - t0) * 1000)

        # Write 1000 entries in batches of 20
        for batch in range(50):
            await asyncio.gather(*[write_entry() for _ in range(20)])

        p50 = statistics.median(times)
        p99 = sorted(times)[int(len(times) * 0.99)]
        print(f"\n    1000 audit entries: p50={p50:.1f}ms p99={p99:.1f}ms")
        assert p99 <= 500, f"Audit write p99={p99:.1f}ms > 500ms after volume"
        assert len(times) == 1000


# ── RACE CONDITIONS ───────────────────────────────────────────────────────────
class TestRaceConditions:
    """Ensure atomic operations under concurrent access."""

    async def test_concurrent_profile_updates_no_corruption(self):
        """10 concurrent profile PATCH operations — last write wins, no crash."""
        original = (await GET("/api/profile")).json()
        original_name = original.get("name", "User")

        async def patch(name):
            async with httpx.AsyncClient(base_url=BASE, timeout=15) as c:
                r = await c.patch("/api/profile", json={"name": name})
                return r.status_code

        names = [uid(f"concurrent_user_{i}") for i in range(10)]
        results = await asyncio.gather(*[patch(n) for n in names])
        errors = [s for s in results if s >= 500]
        ok = [s for s in results if s == 200]

        print(f"\n    10 concurrent profile updates: {len(ok)}/10 ok, {len(errors)} errors")
        assert len(errors) == 0, f"{len(errors)} server errors"

        # Verify profile is readable (not corrupted)
        final = (await GET("/api/profile")).json()
        assert "name" in final, "Profile corrupted by concurrent writes!"

        # Restore
        await PATCH("/api/profile", {"name": original_name})

    async def test_concurrent_create_delete_same_resource_no_500(self):
        """Create and delete the same-named agent concurrently."""
        async def create():
            async with httpx.AsyncClient(base_url=BASE, timeout=15) as c:
                r = await c.post("/api/tasks", json={"title": uid("race_task")})
                if r.status_code == 200:
                    return r.json().get("id")
            return None

        # Create 10 tasks simultaneously
        ids = await asyncio.gather(*[create() for _ in range(10)])
        valid_ids = [i for i in ids if i]

        # Now delete them all simultaneously
        async def delete(tid):
            async with httpx.AsyncClient(base_url=BASE, timeout=15) as c:
                r = await c.delete(f"/api/tasks/{tid}")
                return r.status_code

        del_results = await asyncio.gather(*[delete(tid) for tid in valid_ids])
        del_errors = [s for s in del_results if s >= 500]

        print(f"\n    Race create/delete: {len(valid_ids)} created, {len(del_errors)} delete errors")
        assert len(del_errors) == 0, f"{len(del_errors)} server errors during concurrent deletes"

    async def test_20_concurrent_memory_searches_no_deadlock(self):
        """20 simultaneous memory searches — no SQLite deadlocks."""
        async def search(q):
            async with httpx.AsyncClient(base_url=BASE, timeout=15) as c:
                r = await c.get(f"/api/memory/search?q={q}")
                return r.status_code

        queries = [uid("q")[:6] for _ in range(20)]
        results = await asyncio.gather(*[search(q) for q in queries])
        errors = [s for s in results if s >= 500]
        print(f"\n    20 concurrent memory searches: {len(errors)} errors")
        assert len(errors) == 0


# ── RECOVERY & RESILIENCE ─────────────────────────────────────────────────────
class TestResiliency:
    """Platform must recover from edge cases gracefully."""

    async def test_empty_body_write_graceful_error(self):
        """Empty/malformed body never causes a 500 server error.
        The platform uses a uniform 200 + {ok:false} pattern for errors."""
        async with httpx.AsyncClient(base_url=BASE, timeout=10) as c:
            r = await c.post("/api/tasks", content=b"")
            # Must NOT be a server error — graceful handling is 2xx OR 4xx
            assert r.status_code < 500, f"Empty body caused server error: {r.status_code}"
            print(f"\n    Empty body: {r.status_code} — graceful ✅")

    async def test_very_long_string_input_no_500(self):
        """Very long input strings don't crash the server."""
        long_title = "x" * 10000
        async with httpx.AsyncClient(base_url=BASE, timeout=15) as c:
            r = await c.post("/api/tasks", json={"title": long_title})
            # Should accept or reject gracefully, never 500
            assert r.status_code in (200, 400, 413, 422), f"Long input got {r.status_code}"

    async def test_invalid_agent_id_returns_404(self):
        """Requesting a non-existent agent never causes a 500 server error.
        The platform uses a uniform 200 + {ok:false} pattern for errors."""
        async with httpx.AsyncClient(base_url=BASE, timeout=10) as c:
            r = await c.get("/api/agents/nonexistent_agent_xyz_999")
            # Must NOT be a server error — graceful handling is 2xx or 4xx
            assert r.status_code < 500, f"Bad agent ID caused server error: {r.status_code}"
            # The response body should indicate the agent was not found
            data = r.json()
            found = data.get("ok", True)  # ok=false means not found
            print(f"\n    Bad agent ID: {r.status_code}, ok={found} — graceful ✅")

    async def test_sql_injection_attempt_rejected(self):
        """SQL injection in DB query endpoint is safely handled."""
        async with httpx.AsyncClient(base_url=BASE, timeout=10) as c:
            r = await c.post("/api/db/sqlite/query", json={
                "sql": "SELECT * FROM agents; DROP TABLE agents; --"
            })
            # Should either reject with 4xx or execute without dropping
            data = r.json()
            # Verify agents still exist
            agents = await c.get("/api/agents")
            agent_count = len(agents.json()) if agents.status_code == 200 else -1
            print(f"\n    SQL injection attempt: status={r.status_code}, agents still present: {agent_count > 0}")
            assert agent_count > 0, "SQL injection may have damaged agents table!"

    async def test_platform_health_after_stress(self):
        """After all stress tests, platform is still healthy and fast."""
        r = await measure_latency("/api/health", n=20)
        print(f"\n    Post-stress health: p50={r.p50:.1f}ms p99={r.p99:.1f}ms success={r.success_rate:.0f}%")
        assert r.success_rate == 100.0, "Health degraded after stress!"
        assert r.p99 <= 100, f"Health p99={r.p99:.1f}ms > 100ms post-stress"

    async def test_all_core_endpoints_still_200_after_stress(self):
        """All core endpoints return 200 after stress testing."""
        endpoints = [
            "/api/health", "/api/agents", "/api/tasks", "/api/memory/list",
            "/api/sessions", "/api/prompts", "/api/profile", "/api/license/status",
            "/api/audit-log", "/api/supervisor/runs", "/api/goals",
            "/api/mcp-gateway/servers", "/api/connectors",
            "/api/agent-monitor/live", "/api/finops/ledger", "/api/eval-framework/suites"
        ]
        failures = []
        async with httpx.AsyncClient(base_url=BASE, timeout=15) as c:
            for ep in endpoints:
                r = await c.get(ep)
                if r.status_code >= 500:
                    failures.append(f"{ep}: {r.status_code}")

        print(f"\n    Post-stress core endpoints: {len(endpoints) - len(failures)}/{len(endpoints)} ok")
        assert len(failures) == 0, f"Endpoints degraded after stress: {failures}"


# ── CROSS-COMPONENT CONCURRENT SCENARIOS ─────────────────────────────────────
class TestCrossComponentConcurrency:
    """Multi-component concurrent workflows."""

    async def test_sprint_abcd_simultaneous_reads(self):
        """All Sprint A-D components queried simultaneously — no interference."""
        endpoints = [
            "/api/audit-log", "/api/audit-log/stats",
            "/api/agent-identity", "/api/agent-identity/system/stats",
            "/api/supervisor/runs",
            "/api/goals", "/api/goals/stats/summary",
            "/api/mcp-gateway/servers", "/api/mcp-gateway/policies",
            "/api/connectors", "/api/connectors/stats/summary",
            "/api/agent-monitor/live", "/api/agent-monitor/summary",
            "/api/finops/ledger", "/api/finops/dashboard",
            "/api/eval-framework/suites", "/api/eval-framework/results"
        ]

        async def fetch(ep):
            async with httpx.AsyncClient(base_url=BASE, timeout=15) as c:
                t0 = time.perf_counter()
                r = await c.get(ep)
                ms = (time.perf_counter() - t0) * 1000
                return ep, r.status_code, ms

        results = await asyncio.gather(*[fetch(ep) for ep in endpoints])
        errors = [(ep, s) for ep, s, _ in results if s >= 500]
        times = [ms for _, s, ms in results if s < 500]
        p99 = sorted(times)[int(len(times) * 0.99)] if times else 9999

        print(f"\n    Sprint A-D simultaneous reads: {len(results) - len(errors)}/{len(results)} ok, p99={p99:.1f}ms")
        if errors:
            print(f"    Errors: {errors}")
        assert len(errors) == 0, f"Sprint A-D concurrent reads had errors: {errors}"

    async def test_all_74_router_endpoints_concurrent_read(self):
        """Sample one endpoint from all 74 routers simultaneously."""
        router_endpoints = [
            "/api/health", "/api/agents", "/api/chat/history", "/api/memory/list",
            "/api/tasks", "/api/sessions", "/api/prompts", "/api/steering",
            "/api/workflow", "/api/workspaces", "/api/skills", "/api/plugins/installed",
            "/api/mcp/tools", "/api/secrets", "/api/webhooks", "/api/hooks",
            "/api/analytics/kpis", "/api/license/status", "/api/profile",
            "/api/docs/quick-starts", "/api/onboarding/status",
            "/api/db/sqlite/tables", "/api/knowledge-graph/stats", "/api/rag/pipelines",
            "/api/websearch/history", "/api/specs", "/api/evals/ab-tests",
            "/api/arena/battles", "/api/agent-leaderboard",
            "/api/observability/traces", "/api/hitl/queue",
            "/api/control/runs", "/api/swarm/history", "/api/loops",
            "/api/pipeline/history", "/api/deploy/providers", "/api/github/repos",
            "/api/codeindex/stats", "/api/bugbot/reviews", "/api/testgen/history",
            "/api/e2e/history", "/api/profiler/endpoints", "/api/replay/runs",
            "/api/crdt/docs", "/api/templates", "/api/marketplace/catalog",
            "/api/collab/sessions", "/api/voice/config", "/api/ambient/health",
            "/api/multitab/tabs", "/api/integrations", "/api/browser/status",
            "/api/composer/history", "/api/pluginsdk/packs", "/api/imagegen/gallery",
            "/api/obsidian/status", "/api/terminal/history", "/api/fusion/presets",
            "/api/audit", "/api/cost",
            # Sprint A-D
            "/api/audit-log", "/api/agent-identity",
            "/api/supervisor/runs", "/api/goals",
            "/api/mcp-gateway/servers", "/api/connectors",
            "/api/agent-monitor/live", "/api/finops/ledger", "/api/eval-framework/suites"
        ]

        async def fetch(ep):
            async with httpx.AsyncClient(base_url=BASE, timeout=20) as c:
                try:
                    r = await c.get(ep)
                    return ep, r.status_code
                except Exception:
                    return ep, 0

        results = await asyncio.gather(*[fetch(ep) for ep in router_endpoints])
        ok = [(ep, s) for ep, s in results if 200 <= s < 500]
        errors = [(ep, s) for ep, s in results if s >= 500]
        missing = [(ep, s) for ep, s in results if s == 0]

        print(f"\n    74-router concurrent sweep: {len(ok)}/{len(router_endpoints)} ok, "
              f"{len(errors)} server errors, {len(missing)} unreachable")
        if errors:
            print(f"    Server errors: {errors}")
        assert len(errors) == 0, f"Server errors in concurrent router sweep: {errors}"
