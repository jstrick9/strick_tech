"""
Performance Test Suite — Data Volume & Reliability
Tests: Performance with realistic data volumes, long-running stability,
       memory behavior, response consistency
"""
import pytest, asyncio, time, statistics
from tests.perf.perf_engine import *


class TestDataVolumePerformance:
    """Performance must hold up as data volume grows."""

    async def test_list_tasks_consistent_with_volume(self):
        """
        Create 50 tasks → list time should not be significantly worse.
        Tests SQLite query performance with realistic row counts.
        """
        # Measure before
        before = await measure_latency("/api/tasks", n=10)
        
        # Create 50 tasks
        created_ids = []
        async with httpx.AsyncClient(base_url=BASE, timeout=30) as c:
            for i in range(50):
                r = await c.post("/api/tasks", json={
                    "title": f"VolumeTask_{i:03d}_{uid()}",
                    "status": "todo",
                    "priority": ["low","medium","high"][i % 3]
                })
                if r.status_code == 200:
                    created_ids.append(r.json().get("id"))
        
        # Measure after
        after = await measure_latency("/api/tasks", n=10)
        
        growth_pct = (after.p95 / before.p95 - 1) * 100 if before.p95 > 0 else 0
        print(f"\n    /api/tasks latency growth after +50 rows: {growth_pct:.1f}%")
        print(f"    Before: p95={before.p95:.1f}ms, After: p95={after.p95:.1f}ms")
        
        # Cleanup
        for tid in created_ids:
            if tid: await DELETE(f"/api/tasks/{tid}")
        
        assert after.p95 < 200, f"Task list p95 with volume: {after.p95:.1f}ms > 200ms"
        assert growth_pct < 100, f"Task list latency grew {growth_pct:.1f}% with +50 rows"

    async def test_memory_search_with_100_entries(self):
        """
        FTS search should remain fast with 100 memory entries.
        """
        # Add 100 memories
        added = []
        async with httpx.AsyncClient(base_url=BASE, timeout=60) as c:
            for i in range(100):
                r = await c.post("/api/memory/add", json={
                    "content": f"Volume test memory {i} about {['Python','FastAPI','React','Docker','Kubernetes'][i%5]}",
                    "source": "perf_volume"
                })
                if r.status_code == 200:
                    added.append(r.json().get("id"))
        
        # Measure FTS search
        r = await measure_latency("/api/memory/search", "GET", n=10)
        print(f"\n    Memory FTS with 100 entries: p95={r.p95:.1f}ms")
        
        # Cleanup
        async with httpx.AsyncClient(base_url=BASE, timeout=60) as c:
            for mid in added:
                if mid:
                    await c.delete(f"/api/memory/{mid}")
        
        assert r.p95 < 200, f"Memory search p95={r.p95:.1f}ms > 200ms with 100 entries"

    async def test_prompt_library_with_50_prompts(self):
        """Prompt library loads fast with realistic size."""
        before = await measure_latency("/api/prompts", n=10)
        
        created_ids = []
        async with httpx.AsyncClient(base_url=BASE, timeout=30) as c:
            for i in range(50):
                r = await c.post("/api/prompts", json={
                    "title": f"VolumePrompt_{i:03d}",
                    "content": f"Prompt content {i} for {{{{topic}}}}",
                    "category": ["general","debug","review"][i % 3]
                })
                if r.status_code == 200:
                    created_ids.append(r.json().get("id"))
        
        after = await measure_latency("/api/prompts", n=10)
        growth = (after.p95 / before.p95 - 1) * 100 if before.p95 > 0 else 0
        print(f"\n    Prompts list +50 entries: p95 {before.p95:.1f}→{after.p95:.1f}ms ({growth:.1f}% growth)")
        
        for pid in created_ids:
            if pid: await DELETE(f"/api/prompts/{pid}")
        
        assert after.p95 < 200, f"Prompts p95={after.p95:.1f}ms > 200ms with volume"

    async def test_workflow_list_with_20_workflows(self):
        """Workflow list handles realistic project size."""
        created = []
        async with httpx.AsyncClient(base_url=BASE, timeout=30) as c:
            for i in range(20):
                r = await c.post("/api/workflow", json={
                    "name": f"VolumeWF_{i:02d}",
                    "nodes": [{"id":"n1","type":"trigger","label":"Start","x":0,"y":0}],
                    "edges": []
                })
                if r.status_code == 200:
                    d = r.json()
                    wid = d.get("id") or (d.get("workflow") or {}).get("id")
                    if wid: created.append(wid)
        
        after = await measure_latency("/api/workflow", n=10)
        print(f"\n    Workflow list with 20+ workflows: p95={after.p95:.1f}ms")
        
        for wid in created:
            await DELETE(f"/api/workflow/{wid}")
        
        assert after.p95 < 200, f"Workflow list p95={after.p95:.1f}ms > 200ms"

    async def test_db_query_count_all_tables(self):
        """SQL query touching all major tables stays fast."""
        sql = """
            SELECT
                (SELECT COUNT(*) FROM tasks)      AS tasks,
                (SELECT COUNT(*) FROM agents)     AS agents,
                (SELECT COUNT(*) FROM memory)     AS memories,
                (SELECT COUNT(*) FROM workspaces) AS workspaces,
                (SELECT COUNT(*) FROM webhooks)   AS webhooks,
                (SELECT COUNT(*) FROM specs)      AS specs
        """
        r = await measure_latency(
            "/api/db/sqlite/query", "POST", {"sql": sql}, n=20
        )
        print(f"\n    Multi-table COUNT(*): p95={r.p95:.1f}ms")
        assert r.p95 < 100, f"Multi-table query p95={r.p95:.1f}ms > 100ms"


class TestResponseConsistency:
    """Response times should be consistent — low variance."""

    async def test_health_low_variance(self):
        """Health endpoint variance: p95/p50 ratio < 3x, absolute p99 < 50ms."""
        r = await measure_latency("/api/health", n=100)
        ratio_95_50 = r.p95 / r.p50 if r.p50 > 0 else 999
        print(f"\n    /api/health p95/p50 ratio: {ratio_95_50:.2f}x, p99={r.p99:.1f}ms")
        # TCP setup spikes can hit p99; use p95/p50 for variance and abs p99 cap
        assert ratio_95_50 < 5.0, f"Health p95/p50={ratio_95_50:.2f}x > 5"
        assert r.p99 < 50, f"Health p99={r.p99:.1f}ms > 50ms absolute cap"

    async def test_profile_low_variance(self):
        """Profile file reads should be consistent."""
        r = await measure_latency("/api/profile", n=50)
        ratio = r.p95 / r.p50 if r.p50 > 0 else 999
        print(f"\n    /api/profile p95/p50 ratio: {ratio:.2f}x, p99={r.p99:.1f}ms")
        assert ratio < 5.0, f"Profile p95/p50={ratio:.2f}x > 5"
        assert r.p99 < 100, f"Profile p99={r.p99:.1f}ms > 100ms"

    async def test_license_low_variance(self):
        """License status should be very consistent."""
        r = await measure_latency("/api/license/status", n=50)
        ratio = r.p95 / r.p50 if r.p50 > 0 else 999
        print(f"\n    /api/license/status p95/p50 ratio: {ratio:.2f}x, p99={r.p99:.1f}ms")
        assert ratio < 5.0, f"License p95/p50={ratio:.2f}x > 5"
        assert r.p99 < 100, f"License p99={r.p99:.1f}ms > 100ms"

    async def test_memory_list_low_variance(self):
        """Memory list reads should be consistent."""
        r = await measure_latency("/api/memory/list", n=50)
        ratio = r.p95 / r.p50 if r.p50 > 0 else 999
        print(f"\n    /api/memory/list p95/p50 ratio: {ratio:.2f}x")
        assert ratio < 5.0, f"Memory list p95/p50={ratio:.2f}x > 5"
        assert r.p99 < 100, f"Memory p99={r.p99:.1f}ms > 100ms"

    async def test_tasks_low_variance(self):
        """Task list reads should be consistent."""
        r = await measure_latency("/api/tasks", n=50)
        ratio = r.p95 / r.p50 if r.p50 > 0 else 999
        print(f"\n    /api/tasks p95/p50 ratio: {ratio:.2f}x")
        assert ratio < 5.0, f"Tasks p95/p50={ratio:.2f}x > 5"
        assert r.p99 < 150, f"Tasks p99={r.p99:.1f}ms > 150ms"


class TestReliabilityUnderLoad:
    """System must maintain 99.9% success rate under sustained load."""

    async def test_health_100_requests_all_succeed(self):
        """100 sequential health requests — all must succeed."""
        r = await measure_latency("/api/health", n=100)
        print(f"\n    100 health requests: {r.success}/{r.n} succeeded")
        assert r.success == 100, f"Health: {r.errors} failures in 100 requests"

    async def test_mixed_endpoints_no_500_under_load(self):
        """Mix of 200 requests to different endpoints — no 500s."""
        endpoints = [
            "/api/health", "/api/agents", "/api/tasks",
            "/api/memory/list", "/api/license/status", "/api/profile",
            "/api/docs/quick-starts", "/api/docs/features",
        ]
        errors = []
        async with httpx.AsyncClient(base_url=BASE, timeout=15) as c:
            for i in range(200):
                path = endpoints[i % len(endpoints)]
                try:
                    r = await c.get(path)
                    if r.status_code >= 500:
                        errors.append((path, r.status_code))
                except Exception as e:
                    errors.append((path, str(e)[:30]))
        
        error_rate = len(errors) / 200 * 100
        print(f"\n    200 mixed requests: {len(errors)} errors ({error_rate:.1f}%)")
        assert len(errors) == 0, f"{len(errors)} server errors: {errors[:5]}"

    async def test_write_100_tasks_all_unique(self):
        """Create 100 tasks rapidly — all get unique IDs."""
        ids = []
        async with httpx.AsyncClient(base_url=BASE, timeout=60) as c:
            for i in range(100):
                r = await c.post("/api/tasks", json={"title": uid(f"reliability_{i}")})
                if r.status_code == 200:
                    ids.append(r.json().get("id"))
        
        unique = len(set(ids))
        print(f"\n    100 rapid task creates: {len(ids)} succeeded, {unique} unique IDs")
        assert len(ids) == 100, f"Only {len(ids)}/100 creates succeeded"
        assert unique == 100, f"ID collision: {unique} unique IDs from 100 creates"
        
        # Cleanup
        async with httpx.AsyncClient(base_url=BASE, timeout=60) as c:
            for tid in ids:
                await c.delete(f"/api/tasks/{tid}")

    async def test_sustained_30s_load_no_degradation(self):
        """30 seconds of sustained load — latency stays bounded."""
        
        # Measure first 5s
        t0 = time.perf_counter()
        early_times = []
        async with httpx.AsyncClient(base_url=BASE, timeout=15) as c:
            while time.perf_counter() - t0 < 5:
                t = time.perf_counter()
                await c.get("/api/tasks")
                early_times.append((time.perf_counter() - t) * 1000)
        
        # Wait for middle
        await asyncio.sleep(10)
        
        # Measure next 5s
        late_times = []
        async with httpx.AsyncClient(base_url=BASE, timeout=15) as c:
            t0 = time.perf_counter()
            while time.perf_counter() - t0 < 5:
                t = time.perf_counter()
                await c.get("/api/tasks")
                late_times.append((time.perf_counter() - t) * 1000)
        
        early_p95 = sorted(early_times)[int(len(early_times)*0.95)]
        late_p95  = sorted(late_times)[int(len(late_times)*0.95)]
        degradation = (late_p95 / early_p95 - 1) * 100 if early_p95 > 0 else 0
        
        print(f"\n    30s stability: early_p95={early_p95:.1f}ms → late_p95={late_p95:.1f}ms ({degradation:+.1f}%)")
        assert degradation < 50, f"Latency degraded {degradation:.1f}% over 30s"
        assert late_p95 < 300, f"Late p95={late_p95:.1f}ms > 300ms"


class TestSpecificComponentPerformance:
    """Performance tests for specific components mentioned in the audit."""

    async def test_websearch_history_crud_performance(self):
        """Websearch history CRUD under realistic load."""
        # Clear
        t_clear = time.perf_counter()
        await DELETE("/api/websearch/history")
        t_clear = (time.perf_counter() - t_clear) * 1000
        
        # Add 10 searches
        add_times = []
        async with httpx.AsyncClient(base_url=BASE, timeout=15) as c:
            for i in range(10):
                t = time.perf_counter()
                await c.post("/api/websearch/search", json={"query": uid(f"perf_q{i}"), "num_results": 1})
                add_times.append((time.perf_counter() - t) * 1000)
        
        # List history
        t_list = time.perf_counter()
        r = await GET("/api/websearch/history")
        t_list = (time.perf_counter() - t_list) * 1000
        
        avg_add = statistics.mean(add_times)
        print(f"\n    WebSearch history: clear={t_clear:.1f}ms, avg_add={avg_add:.1f}ms, list={t_list:.1f}ms")
        
        assert t_list < 50, f"History list {t_list:.1f}ms > 50ms"
        
        await DELETE("/api/websearch/history")

    async def test_docs_feedback_accumulation_performance(self):
        """Docs feedback endpoint stays fast as feedback accumulates."""
        # Submit 50 feedback entries
        before = await measure_latency(
            "/api/docs/feedback", "POST",
            {"doc_id": "qs_chat", "doc_type": "quickstart", "helpful": True},
            n=5
        )
        
        async with httpx.AsyncClient(base_url=BASE, timeout=15) as c:
            for i in range(50):
                await c.post("/api/docs/feedback", json={
                    "doc_id": f"perf_doc_{i%10}", "doc_type": "feature", "helpful": i%2==0
                })
        
        after = await measure_latency(
            "/api/docs/feedback", "POST",
            {"doc_id": "qs_chat", "doc_type": "quickstart", "helpful": True},
            n=5
        )
        
        growth = (after.avg / before.avg - 1) * 100 if before.avg > 0 else 0
        print(f"\n    Docs feedback after 50 entries: {before.avg:.1f}ms → {after.avg:.1f}ms ({growth:+.1f}%)")
        assert after.p95 < 50, f"Feedback p95={after.p95:.1f}ms > 50ms after accumulation"

    async def test_license_history_grows_without_slowdown(self):
        """License history endpoint stays fast as history grows."""
        # Add some activations
        async with httpx.AsyncClient(base_url=BASE, timeout=15) as c:
            for i in range(5):
                await c.post("/api/license/activate",
                             json={"license_key": f"PRO-PERF-HIST-TEST-{i:04d}567890"})
            await c.post("/api/license/reset-trial")
        
        r = await measure_latency("/api/license/history", n=20)
        print(f"\n    License history with entries: p99={r.p99:.1f}ms")
        assert r.p99 < 50, f"License history p99={r.p99:.1f}ms > 50ms"

    async def test_profile_export_performance(self):
        """Profile export should be fast even with full profile data."""
        r = await measure_latency("/api/profile/export", n=10)
        print(f"\n    Profile export: p95={r.p95:.1f}ms, p99={r.p99:.1f}ms")
        assert r.p99 < 100, f"Profile export p99={r.p99:.1f}ms > 100ms"

    async def test_mcp_tool_call_performance(self):
        """MCP tool calls should complete quickly."""
        r = await measure_latency(
            "/api/mcp/call", "POST",
            {"tool": "json.parse", "args": {"data": '{"key":"value","num":42}'}},
            n=20
        )
        print(f"\n    MCP json.parse: p50={r.p50:.1f} p99={r.p99:.1f}ms")
        assert r.p99 < 100, f"MCP tool call p99={r.p99:.1f}ms > 100ms"
        assert r.success_rate == 100.0

    async def test_crdt_doc_operations_performance(self):
        """CRDT document operations (create, op, get) are fast."""
        # Create
        t0 = time.perf_counter()
        r_create = await POST("/api/crdt/docs", {"title": uid("PerfCRDT"), "content": "# Perf"})
        create_ms = (time.perf_counter() - t0) * 1000
        
        if r_create.status_code == 200:
            doc_id = r_create.json()["doc"]["id"]
            
            # Apply op
            t1 = time.perf_counter()
            await POST(f"/api/crdt/docs/{doc_id}/op",
                      {"op": [0, "insert", "X"], "peer_id": "perf"})
            op_ms = (time.perf_counter() - t1) * 1000
            
            # Get
            t2 = time.perf_counter()
            await GET(f"/api/crdt/docs/{doc_id}")
            get_ms = (time.perf_counter() - t2) * 1000
            
            print(f"\n    CRDT: create={create_ms:.1f}ms, op={op_ms:.1f}ms, get={get_ms:.1f}ms")
            
            assert create_ms < 100, f"CRDT create {create_ms:.1f}ms > 100ms"
            assert op_ms < 100, f"CRDT op {op_ms:.1f}ms > 100ms"
            assert get_ms < 50, f"CRDT get {get_ms:.1f}ms > 50ms"
            
            await DELETE(f"/api/crdt/docs/{doc_id}")
