"""
Performance Test Suite — SLA Compliance Report
Final consolidated test that runs ALL components and produces a pass/fail
summary against defined SLAs for the entire platform.
"""
import pytest, asyncio, time, json
from pathlib import Path
from tests.perf.perf_engine import *


class TestSLACompliance:
    """Comprehensive SLA compliance check across all platform components."""

    async def test_sla_tier1_health_endpoints(self):
        """Tier 1: Health & bootstrap endpoints. Strictest SLAs."""
        report = PerfReport("Tier-1 Health Endpoints")
        
        tests = [
            ("GET /api/health",            "/api/health",            "GET",  None,                50),  # HTTP roundtrip SLA
            ("GET /api/license/status",    "/api/license/status",    "GET",  None,                50),
            ("GET /api/profile/ui-config", "/api/profile/ui-config", "GET",  None,                100),
            ("GET /api/profile",           "/api/profile",           "GET",  None,                50),
        ]
        
        for label, path, method, body, threshold in tests:
            r = await measure_latency(path, method, body, n=20)
            ok, msg = r.check_sla(threshold, label)
            if ok: report.ok(msg)
            else:  report.fail(msg)
        
        print(report.summary())
        assert report.pass_rate == 100.0, f"Tier-1 SLA: {report.pass_rate:.1f}%\n{report.summary()}"

    async def test_sla_tier2_read_endpoints(self):
        """Tier 2: All read endpoints. P99 ≤ 50-150ms."""
        report = PerfReport("Tier-2 Read Endpoints")
        
        tests = [
            ("GET /api/agents",               "/api/agents",                "GET",  None, 50),
            ("GET /api/tasks",                "/api/tasks",                 "GET",  None, 50),
            ("GET /api/memory/list",          "/api/memory/list",           "GET",  None, 50),
            ("GET /api/memory/stats",         "/api/memory/stats",          "GET",  None, 50),
            ("GET /api/sessions",             "/api/sessions",              "GET",  None, 50),
            ("GET /api/prompts",              "/api/prompts",               "GET",  None, 150),
            ("GET /api/steering",             "/api/steering",              "GET",  None, 100),
            ("GET /api/workflow",             "/api/workflow",              "GET",  None, 150),
            ("GET /api/websearch/history",    "/api/websearch/history",     "GET",  None, 100),
            ("GET /api/docs/quick-starts",    "/api/docs/quick-starts",     "GET",  None, 30),
            ("GET /api/docs/features",        "/api/docs/features",         "GET",  None, 30),
            ("GET /api/docs/faq",             "/api/docs/faq",              "GET",  None, 30),
            ("GET /api/docs/shortcuts",       "/api/docs/shortcuts",        "GET",  None, 30),
            ("GET /api/workspaces",           "/api/workspaces",            "GET",  None, 200),
            ("GET /api/secrets/list",         "/api/secrets/list",          "GET",  None, 200),
            ("GET /api/hooks",                "/api/hooks",                 "GET",  None, 200),
            ("GET /api/webhooks",             "/api/webhooks",              "GET",  None, 200),
            ("GET /api/mcp/tools",            "/api/mcp/tools",             "GET",  None, 200),
            ("GET /api/skills",               "/api/skills",                "GET",  None, 200),
            ("GET /api/analytics/kpis",       "/api/analytics/kpis",        "GET",  None, 200),
            ("GET /api/knowledge-graph/stats","/api/knowledge-graph/stats", "GET",  None, 100),
        ]
        
        for label, path, method, body, threshold in tests:
            r = await measure_latency(path, method, body, n=15)
            ok, msg = r.check_sla(threshold, label)
            if ok: report.ok(msg)
            else:  report.fail(msg)
        
        print(report.summary())
        assert report.pass_rate >= 95.0, f"Tier-2 SLA: {report.pass_rate:.1f}%\n{report.summary()}"

    async def test_sla_tier3_write_endpoints(self):
        """Tier 3: Write endpoints. P99 ≤ 100-200ms."""
        report = PerfReport("Tier-3 Write Endpoints")
        
        write_tests = [
            ("POST /api/memory/add",    "/api/memory/add",    "POST", {"content": uid("sla_mem"), "source": "perf"}, 100),
            ("POST /api/docs/feedback", "/api/docs/feedback", "POST", {"doc_id": "qs_chat", "doc_type": "quickstart", "helpful": True}, 50),
            ("PATCH /api/profile",      "/api/profile",       "PATCH", {"name": uid("sla")}, 200),
        ]
        
        for label, path, method, body, threshold in write_tests:
            r = await measure_latency(path, method, body, n=15)
            ok, msg = r.check_sla(threshold, label)
            if ok: report.ok(msg)
            else:  report.fail(msg)
        
        print(report.summary())
        assert report.pass_rate == 100.0, f"Tier-3 SLA: {report.pass_rate:.1f}%\n{report.summary()}"

    async def test_sla_tier4_database_endpoints(self):
        """Tier 4: Database Studio queries."""
        report = PerfReport("Tier-4 Database Endpoints")
        
        db_tests = [
            ("DB tables",      "/api/db/sqlite/tables", "GET",  None,                             100),
            ("DB SELECT 1",    "/api/db/sqlite/query",  "POST", {"sql": "SELECT 1"},              50),
            ("DB COUNT tasks", "/api/db/sqlite/query",  "POST", {"sql": "SELECT COUNT(*) FROM tasks"}, 100),
        ]
        
        for label, path, method, body, threshold in db_tests:
            r = await measure_latency(path, method, body, n=20)
            ok, msg = r.check_sla(threshold, label)
            if ok: report.ok(msg)
            else:  report.fail(msg)
        
        print(report.summary())
        assert report.pass_rate == 100.0, f"Tier-4 SLA: {report.pass_rate:.1f}%\n{report.summary()}"

    async def test_sla_throughput_all_components(self):
        """Throughput SLA: All key endpoints must sustain minimum RPS."""
        report = PerfReport("Throughput SLA")
        
        throughput_tests = [
            ("Health RPS",        "/api/health",            "GET",  None,                 SLA.HEALTH_MIN_RPS),
            ("Agents RPS",        "/api/agents",            "GET",  None,                 SLA.READ_MIN_RPS),
            ("Tasks RPS",         "/api/tasks",             "GET",  None,                 SLA.READ_MIN_RPS),
            ("Memory list RPS",   "/api/memory/list",       "GET",  None,                 SLA.READ_MIN_RPS),
            ("License status RPS","/api/license/status",    "GET",  None,                 200),
            ("Profile RPS",       "/api/profile",           "GET",  None,                 200),
            ("DB query RPS",      "/api/db/sqlite/query",   "POST", {"sql":"SELECT 1"},   200),
            ("Docs RPS",          "/api/docs/quick-starts", "GET",  None,                 300),
        ]
        
        for label, path, method, body, min_rps in throughput_tests:
            r = await measure_throughput(path, method, body, concurrency=10, duration_s=3)
            ok, msg = r.check_sla(min_rps, label)
            if ok: report.ok(msg)
            else:  report.fail(msg)
        
        print(report.summary())
        assert report.pass_rate >= 90.0, f"Throughput SLA: {report.pass_rate:.1f}%\n{report.summary()}"

    async def test_sla_reliability_all_endpoints(self):
        """Reliability SLA: All endpoints must have ≥99.9% success rate."""
        report = PerfReport("Reliability SLA")
        
        reliability_tests = [
            "/api/health", "/api/agents", "/api/tasks",
            "/api/memory/list", "/api/sessions", "/api/prompts",
            "/api/license/status", "/api/profile", "/api/websearch/history",
            "/api/docs/quick-starts", "/api/docs/features",
        ]
        
        for path in reliability_tests:
            r = await measure_latency(path, n=50)
            ok = r.success_rate >= SLA.MIN_SUCCESS_RATE
            msg = f"GET {path}: {r.success_rate:.1f}% success rate"
            if ok: report.ok(msg)
            else:  report.fail(msg)
        
        print(report.summary())
        assert report.pass_rate == 100.0, f"Reliability SLA: {report.pass_rate:.1f}%\n{report.summary()}"

    async def test_sla_concurrency_no_errors(self):
        """Concurrency SLA: No errors under 20 concurrent users."""
        report = PerfReport("Concurrency SLA")
        
        # 20 concurrent requests to 10 endpoints
        endpoints = [
            "/api/health", "/api/agents", "/api/tasks", "/api/memory/list",
            "/api/sessions", "/api/prompts", "/api/license/status", "/api/profile",
            "/api/docs/quick-starts", "/api/docs/features",
        ]
        
        async def check_endpoint(path):
            errors = 0
            async with httpx.AsyncClient(base_url=BASE, timeout=15) as c:
                for _ in range(20):
                    r = await c.get(path)
                    if r.status_code >= 500:
                        errors += 1
            return path, errors
        
        results = await asyncio.gather(*[check_endpoint(p) for p in endpoints])
        
        for path, errors in results:
            ok = errors == 0
            msg = f"GET {path}: {errors} server errors in 20 requests"
            if ok: report.ok(msg)
            else:  report.fail(msg)
        
        print(report.summary())
        assert report.pass_rate == 100.0, f"Concurrency SLA: {report.pass_rate:.1f}%\n{report.summary()}"

    async def test_generate_full_performance_report(self):
        """Generate and save comprehensive performance report."""
        print("\n" + "="*70)
        print("  AGENTIC OS — PERFORMANCE BENCHMARK REPORT")
        print("="*70)
        
        # Collect all key metrics
        benchmarks = {}
        endpoints = {
            "health":           ("/api/health", "GET", None),
            "agents":           ("/api/agents", "GET", None),
            "tasks":            ("/api/tasks",  "GET", None),
            "memory_list":      ("/api/memory/list", "GET", None),
            "sessions":         ("/api/sessions", "GET", None),
            "prompts":          ("/api/prompts", "GET", None),
            "license_status":   ("/api/license/status", "GET", None),
            "profile":          ("/api/profile", "GET", None),
            "profile_ui_config":("/api/profile/ui-config", "GET", None),
            "docs_quickstarts": ("/api/docs/quick-starts", "GET", None),
            "docs_features":    ("/api/docs/features", "GET", None),
            "db_tables":        ("/api/db/sqlite/tables", "GET", None),
            "db_simple_query":  ("/api/db/sqlite/query", "POST", {"sql":"SELECT 1"}),
            "ws_history":       ("/api/websearch/history", "GET", None),
            "kg_stats":         ("/api/knowledge-graph/stats", "GET", None),
        }
        
        print(f"\n  {'Endpoint':<25} {'Avg':>7} {'P50':>7} {'P95':>7} {'P99':>7} {'Max':>8} {'OK%':>6}")
        print("  " + "-"*67)
        
        all_passed = True
        for name, (path, method, body) in endpoints.items():
            r = await measure_latency(path, method, body, n=20)
            benchmarks[name] = {
                "p50": r.p50, "p95": r.p95, "p99": r.p99,
                "avg": r.avg, "min": r.min_, "max": r.max_,
                "success_rate": r.success_rate
            }
            
            # Determine threshold
            threshold = 200
            if "health" in name:       threshold = 50  # HTTP roundtrip (includes TCP)
            elif "docs_" in name:      threshold = 30
            elif "license" in name:    threshold = 50
            elif "profile" in name:    threshold = 100
            elif "db_" in name:        threshold = 100
            elif name in ("agents","memory_list","sessions"): threshold = 50
            
            sla_ok = r.p99 <= threshold and r.success_rate >= SLA.MIN_SUCCESS_RATE
            status = "✅" if sla_ok else "❌"
            if not sla_ok: all_passed = False
            
            label = f"{method[:4]} {path}"[-25:]
            print(f"  {status} {label:<24} {r.avg:>7.1f} {r.p50:>7.1f} {r.p95:>7.1f} {r.p99:>7.1f} {r.max_:>8.1f} {r.success_rate:>6.1f}")
        
        # Throughput summary
        print(f"\n  {'Throughput (10 concurrent)'}")
        print(f"  {'Endpoint':<25} {'RPS':>8} {'P50ms':>7} {'P95ms':>7} {'OK%':>6}")
        print("  " + "-"*55)
        
        tp_tests = [
            ("Health",   "/api/health",           "GET",  None),
            ("Agents",   "/api/agents",           "GET",  None),
            ("Tasks",    "/api/tasks",            "GET",  None),
            ("Profile",  "/api/profile",          "GET",  None),
            ("Docs QS",  "/api/docs/quick-starts","GET",  None),
        ]
        tp_benchmarks = {}
        for name, path, method, body in tp_tests:
            tr = await measure_throughput(path, method, body, concurrency=10, duration_s=3)
            tp_benchmarks[name] = {"rps": tr.rps, "p50": tr.p50, "p95": tr.p95, "ok_rate": tr.success_rate}
            print(f"  {name:<25} {tr.rps:>8.1f} {tr.p50:>7.1f} {tr.p95:>7.1f} {tr.success_rate:>6.1f}")
        
        print("\n" + "="*70)
        
        # Save to file
        report_data = {
            "timestamp":  time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime()),
            "latency":    benchmarks,
            "throughput": tp_benchmarks,
            "all_sla_passed": all_passed,
        }
        
        Path("/home/user/agentic-os/tests/perf_results.json").write_text(
            json.dumps(report_data, indent=2)
        )
        print(f"\n  Full results → tests/perf_results.json")
        print("="*70)
        
        assert all_passed, "One or more endpoints exceeded SLA thresholds"
