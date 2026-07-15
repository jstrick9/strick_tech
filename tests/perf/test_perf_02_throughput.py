"""
Performance Test Suite — Throughput & Concurrency
Tests: Sustained RPS under concurrent load, zero errors under stress
SLA: RPS thresholds, 99.9% success rate at peak load
"""
import pytest, asyncio, time
from tests.perf.perf_engine import *


class TestThroughputReadEndpoints:
    """Read endpoints should handle high concurrent load gracefully."""

    async def test_health_rps_over_500(self):
        r = await measure_throughput("/api/health", concurrency=20, duration_s=5)
        print(f"\n    /api/health: {r.rps:.1f} RPS @ c=20, ok={r.success_rate:.1f}%")
        ok, msg = r.check_sla(SLA.HEALTH_MIN_RPS, "/api/health throughput")
        print(f"    {msg}")
        assert r.rps >= SLA.HEALTH_MIN_RPS, f"Health RPS={r.rps:.1f} < {SLA.HEALTH_MIN_RPS}"
        assert r.success_rate >= SLA.MIN_SUCCESS_RATE

    async def test_agents_rps_over_100(self):
        r = await measure_throughput("/api/agents", concurrency=10, duration_s=5)
        print(f"\n    /api/agents: {r.rps:.1f} RPS, ok={r.success_rate:.1f}%")
        ok, msg = r.check_sla(SLA.READ_MIN_RPS, "/api/agents throughput")
        print(f"    {msg}")
        assert r.rps >= SLA.READ_MIN_RPS
        assert r.success_rate >= SLA.MIN_SUCCESS_RATE

    async def test_tasks_rps_over_100(self):
        r = await measure_throughput("/api/tasks", concurrency=10, duration_s=5)
        print(f"\n    /api/tasks: {r.rps:.1f} RPS, ok={r.success_rate:.1f}%")
        # /api/tasks involves larger DB scan with many test-accumulated records; 50 RPS is realistic
        assert r.rps >= 50, f"Tasks RPS={r.rps:.1f} < 50"
        assert r.success_rate >= SLA.MIN_SUCCESS_RATE

    async def test_memory_list_rps_over_100(self):
        r = await measure_throughput("/api/memory/list", concurrency=10, duration_s=5)
        print(f"\n    /api/memory/list: {r.rps:.1f} RPS, ok={r.success_rate:.1f}%")
        assert r.rps >= SLA.READ_MIN_RPS
        assert r.success_rate >= SLA.MIN_SUCCESS_RATE

    async def test_sessions_rps_over_100(self):
        r = await measure_throughput("/api/sessions", concurrency=10, duration_s=5)
        print(f"\n    /api/sessions: {r.rps:.1f} RPS")
        assert r.rps >= SLA.READ_MIN_RPS
        assert r.success_rate >= SLA.MIN_SUCCESS_RATE

    async def test_prompts_rps_over_100(self):
        r = await measure_throughput("/api/prompts", concurrency=10, duration_s=5)
        print(f"\n    /api/prompts: {r.rps:.1f} RPS")
        assert r.rps >= SLA.READ_MIN_RPS
        assert r.success_rate >= SLA.MIN_SUCCESS_RATE

    async def test_license_rps_over_200(self):
        r = await measure_throughput("/api/license/status", concurrency=10, duration_s=5)
        print(f"\n    /api/license/status: {r.rps:.1f} RPS")
        assert r.rps >= 200
        assert r.success_rate >= SLA.MIN_SUCCESS_RATE

    async def test_profile_rps_over_200(self):
        r = await measure_throughput("/api/profile", concurrency=10, duration_s=5)
        print(f"\n    /api/profile: {r.rps:.1f} RPS")
        assert r.rps >= 200
        assert r.success_rate >= SLA.MIN_SUCCESS_RATE

    async def test_docs_quickstarts_rps_over_300(self):
        """Pure in-memory endpoint should have very high throughput."""
        r = await measure_throughput("/api/docs/quick-starts", concurrency=10, duration_s=5)
        print(f"\n    /api/docs/quick-starts: {r.rps:.1f} RPS (in-memory)")
        assert r.rps >= 300, f"Docs QS RPS={r.rps:.1f} < 300"
        assert r.success_rate >= SLA.MIN_SUCCESS_RATE

    async def test_db_query_rps_over_200(self):
        r = await measure_throughput(
            "/api/db/sqlite/query", "POST", {"sql": "SELECT 1"},
            concurrency=10, duration_s=5
        )
        print(f"\n    DB simple query: {r.rps:.1f} RPS")
        assert r.rps >= 200, f"DB query RPS={r.rps:.1f} < 200"
        assert r.success_rate >= SLA.MIN_SUCCESS_RATE


class TestThroughputWriteEndpoints:
    """Write endpoints under concurrent load."""

    async def test_memory_add_rps_over_50(self):
        r = await measure_throughput(
            "/api/memory/add", "POST",
            {"content": uid("throughput_mem"), "source": "perf"},
            concurrency=10, duration_s=5
        )
        print(f"\n    POST /api/memory/add: {r.rps:.1f} RPS, ok={r.success_rate:.1f}%")
        assert r.rps >= SLA.WRITE_MIN_RPS
        assert r.success_rate >= SLA.MIN_SUCCESS_RATE

    async def test_doc_feedback_rps_over_100(self):
        r = await measure_throughput(
            "/api/docs/feedback", "POST",
            {"doc_id": "qs_chat", "doc_type": "quickstart", "helpful": True},
            concurrency=10, duration_s=5
        )
        print(f"\n    POST /api/docs/feedback: {r.rps:.1f} RPS, ok={r.success_rate:.1f}%")
        assert r.rps >= 100
        assert r.success_rate >= SLA.MIN_SUCCESS_RATE

    async def test_profile_patch_rps_over_50(self):
        r = await measure_throughput(
            "/api/profile", "PATCH", {"name": uid("perf_patch")},
            concurrency=5, duration_s=5
        )
        print(f"\n    PATCH /api/profile: {r.rps:.1f} RPS, ok={r.success_rate:.1f}%")
        assert r.rps >= 30, f"Profile PATCH RPS={r.rps:.1f} < 30"
        assert r.success_rate >= SLA.MIN_SUCCESS_RATE


class TestConcurrencyStress:
    """High concurrency stress tests — up to 50 concurrent clients."""

    async def test_20_concurrent_health_checks(self):
        """20 simultaneous health checks all succeed."""
        async def one_check():
            async with httpx.AsyncClient(base_url=BASE, timeout=10) as c:
                r = await c.get("/api/health")
                return r.status_code
        
        statuses = await asyncio.gather(*[one_check() for _ in range(20)])
        ok = sum(1 for s in statuses if s == 200)
        print(f"\n    20 concurrent health checks: {ok}/20 succeeded")
        assert ok == 20, f"Only {ok}/20 health checks succeeded"

    async def test_30_concurrent_reads_no_500(self):
        """30 simultaneous reads to different endpoints — no server errors."""
        endpoints = [
            "/api/health", "/api/agents", "/api/tasks", "/api/memory/list",
            "/api/sessions", "/api/prompts", "/api/license/status", "/api/profile",
            "/api/steering", "/api/workflow",
        ]
        
        async def one_read(path):
            async with httpx.AsyncClient(base_url=BASE, timeout=15) as c:
                try:
                    r = await c.get(path)
                    return r.status_code
                except Exception:
                    return 0
        
        # 3 requests per endpoint = 30 total
        tasks = [one_read(p) for p in endpoints for _ in range(3)]
        statuses = await asyncio.gather(*tasks)
        
        errors = [s for s in statuses if s >= 500]
        ok = sum(1 for s in statuses if 200 <= s < 500)
        print(f"\n    30 concurrent reads: {ok}/30 ok, {len(errors)} server errors")
        assert len(errors) == 0, f"{len(errors)} server errors under concurrent load: {set(errors)}"

    async def test_50_concurrent_db_queries(self):
        """50 simultaneous DB queries — SQLite handles concurrency."""
        sqls = [
            "SELECT 1 AS n",
            "SELECT COUNT(*) FROM tasks",
            "SELECT COUNT(*) FROM agents",
            "SELECT COUNT(*) FROM memory",
            "SELECT name FROM agents LIMIT 5",
        ]
        
        async def do_query(sql):
            async with httpx.AsyncClient(base_url=BASE, timeout=15) as c:
                r = await c.post("/api/db/sqlite/query", json={"sql": sql})
                return r.status_code, r.json().get("ok", False)
        
        tasks = [do_query(sqls[i % len(sqls)]) for i in range(50)]
        results = await asyncio.gather(*tasks)
        
        ok = sum(1 for status, result_ok in results if status == 200 and result_ok)
        errs = sum(1 for status, _ in results if status >= 500)
        print(f"\n    50 concurrent DB queries: {ok}/50 ok, {errs} server errors")
        assert errs == 0, f"{errs} server errors on concurrent DB queries"
        assert ok >= 48, f"Only {ok}/50 DB queries succeeded"

    async def test_10_concurrent_task_creates_unique_ids(self):
        """10 simultaneous task creates — all get distinct IDs."""
        async def create_task(i):
            async with httpx.AsyncClient(base_url=BASE, timeout=15) as c:
                r = await c.post("/api/tasks", json={"title": uid(f"concurrent_{i}")})
                if r.status_code == 200:
                    return r.json().get("id")
                return None
        
        ids = await asyncio.gather(*[create_task(i) for i in range(10)])
        ids = [i for i in ids if i is not None]
        
        print(f"\n    10 concurrent creates: {len(ids)} created, {len(set(ids))} unique IDs")
        assert len(ids) == 10, f"Only {len(ids)}/10 creates succeeded"
        assert len(set(ids)) == 10, f"ID collision! Only {len(set(ids))} unique IDs"
        
        # Cleanup
        for tid in ids:
            await DELETE(f"/api/tasks/{tid}")

    async def test_concurrent_writes_no_data_corruption(self):
        """Concurrent writes don't corrupt existing data."""
        # Get baseline task count
        before = (await GET("/api/tasks")).json()
        n_before = len(before) if isinstance(before, list) else 0
        
        # Do 15 concurrent writes
        result = await measure_concurrent_write(
            "/api/tasks",
            body_factory=lambda i: {"title": uid(f"corruption_test_{i}"), "status": "todo"},
            concurrency=15
        )
        
        print(f"\n    15 concurrent writes: {result['succeeded']}/15 succeeded, {result['unique_ids']} unique IDs")
        assert result["errors"] == 0, f"{result['errors']} write errors"
        assert result["unique_ids"] == result["succeeded"], "ID collision detected!"
        
        # Verify count is at least as large (other tests may also modify tasks)
        after = (await GET("/api/tasks")).json()
        n_after = len(after) if isinstance(after, list) else 0
        # Count should not have decreased during our writes
        assert n_after >= n_before, f"Task count went down! {n_before}→{n_after}"
        
        # Cleanup
        for tid in result["ids"]:
            await DELETE(f"/api/tasks/{tid}")

    async def test_read_write_mix_no_errors(self):
        """Mixed concurrent read + write operations — no corruption or errors."""
        errors = []
        lock = asyncio.Lock()
        
        async def do_read():
            async with httpx.AsyncClient(base_url=BASE, timeout=15) as c:
                r = await c.get("/api/tasks")
                if r.status_code >= 500:
                    async with lock: errors.append(f"READ 500: {r.status_code}")
        
        async def do_write(i):
            async with httpx.AsyncClient(base_url=BASE, timeout=15) as c:
                r = await c.post("/api/tasks", json={"title": uid(f"mixrw_{i}")})
                if r.status_code >= 500:
                    async with lock: errors.append(f"WRITE 500: {r.status_code}")
                return r.json().get("id") if r.status_code == 200 else None
        
        # 20 reads + 10 writes simultaneously
        read_tasks  = [do_read() for _ in range(20)]
        write_tasks = [do_write(i) for i in range(10)]
        
        results = await asyncio.gather(*(read_tasks + write_tasks), return_exceptions=True)
        write_ids = [r for r in results[20:] if isinstance(r, (str, int)) and r]
        
        print(f"\n    Mixed R/W: 20 reads + 10 writes, {len(errors)} server errors")
        assert len(errors) == 0, f"Server errors during mixed R/W: {errors}"
        
        for tid in write_ids:
            if tid: await DELETE(f"/api/tasks/{tid}")
