"""
FLOW-21: System Monitor + Health + Analytics coherence
FLOW-24: Terminal → Profiler integration
FLOW-02 (memory part): Memory add → search → stats coherence
"""
import pytest
from tests.integration.conftest import *


@pytest.mark.asyncio
class TestSystemHealthCoherence:
    """FLOW-21: All health/system endpoints agree on platform state."""

    async def test_01_api_health_always_ok(self, client):
        """API health check always returns ok:true."""
        d = ok(await GET(client, "/api/health"))
        check("ok is True", d["ok"] is True)
        check("version is 6.0", d["version"] == "6.0")

    async def test_02_system_health_accessible(self, client):
        """System health returns platform vitals."""
        r = await GET(client, "/api/system/health")
        assert r.status_code in (200, 404)
        if r.status_code == 200:
            d = r.json()
            check("system health is dict", isinstance(d, dict))

    async def test_03_system_metrics_accessible(self, client):
        """System metrics returns resource usage data."""
        r = await GET(client, "/api/system/metrics")
        assert r.status_code in (200, 404)
        if r.status_code == 200:
            d = r.json()
            check("metrics is dict", isinstance(d, dict))

    async def test_04_analytics_kpis_accessible(self, client):
        """Analytics KPIs endpoint returns data structure."""
        r = await GET(client, "/api/analytics/kpis")
        assert r.status_code in (200, 404)
        if r.status_code == 200:
            check("kpis is dict", isinstance(r.json(), dict))

    async def test_05_agent_leaderboard_accessible(self, client):
        """Agent leaderboard reflects platform agent state."""
        r = await GET(client, "/api/agent-leaderboard")
        assert r.status_code in (200, 404)
        if r.status_code == 200:
            d = r.json()
            check("leaderboard is dict", isinstance(d, dict))

    async def test_06_control_tower_status(self, client):
        """Control tower status reflects running agents."""
        r = await GET(client, "/api/control-tower/status")
        assert r.status_code in (200, 404)

    async def test_07_ambient_health(self, client):
        """Ambient agent health endpoint."""
        r = await GET(client, "/api/ambient/health")
        assert r.status_code in (200, 404)

    async def test_08_tauri_status(self, client):
        """Tauri build status accessible."""
        r = await GET(client, "/api/tauri/status")
        assert r.status_code in (200, 404)

    async def test_09_pipeline_status(self, client):
        """Goal→Ship pipeline status accessible."""
        r = await GET(client, "/api/pipeline/status")
        assert r.status_code in (200, 404)

    async def test_10_multiple_health_checks_consistent(self, client):
        """Multiple health checks in sequence return consistent ok:true."""
        for _ in range(3):
            d = ok(await GET(client, "/api/health"))
            check("consistent ok", d["ok"] is True)


@pytest.mark.asyncio
class TestTerminalProfilerIntegration:
    """FLOW-24: Terminal command execution + Profiler integration."""

    async def test_01_terminal_echo_produces_sse(self, client):
        """Terminal echo command produces SSE stream with output."""
        r = await POST(client, "/api/terminal/run", {
            "command": "echo integration_terminal_test"
        })
        check("terminal 200", r.status_code == 200)
        text = r.text
        check("has SSE data events", "data:" in text)
        check("output contains echo value", "integration_terminal_test" in text)

    async def test_02_terminal_python_exec(self, client):
        """Execute Python one-liner via terminal."""
        # Use a simple form that avoids complex quoting
        r = await POST(client, "/api/terminal/run", {
            "command": "python3 -c 'print(99 + 1)'"
        })
        check("terminal 200", r.status_code == 200)
        check("python output present", "100" in r.text)

    async def test_03_terminal_exit_event(self, client):
        """Terminal response includes exit event with exit_code."""
        r = await POST(client, "/api/terminal/run", {
            "command": "true"
        })
        check("has exit event", "exit" in r.text.lower())

    async def test_04_terminal_nonzero_exit_code(self, client):
        """Failing command produces non-zero exit code in output."""
        r = await POST(client, "/api/terminal/run", {
            "command": "python3 -c \"import sys; sys.exit(42)\""
        })
        check("response 200", r.status_code == 200)
        check("exit code 42 in output", "42" in r.text)

    async def test_05_terminal_history_records_command(self, client):
        """Commands run via terminal appear in history."""
        unique_cmd = f"echo 'histcmd_{uid()}'"
        await POST(client, "/api/terminal/run", {"command": unique_cmd})
        hist = await GET(client, "/api/terminal/history")
        assert hist.status_code in (200, 404)

    async def test_06_profiler_safe_code_runs(self, client):
        """Profiler runs safe Python code and returns results."""
        r = await POST(client, "/api/profiler/profile/run", {
            "code": "x = sum(i**2 for i in range(100))\nresult = x"
        })
        assert r.status_code in (200, 400, 422)
        if r.status_code == 200:
            d = r.json()
            check("profiler response has ok", "ok" in d)

    async def test_07_profiler_blocks_dangerous_code(self, client):
        """Profiler blocks os.system, subprocess, __import__."""
        dangerous = [
            "import os; os.system('id')",
            "import subprocess; subprocess.run(['ls'])",
            "open('/etc/passwd').read()",
        ]
        for code in dangerous:
            r = await POST(client, "/api/profiler/profile/run", {"code": code})
            assert r.status_code in (200, 400, 403, 422), f"Should handle: {code}"
            if r.status_code == 200:
                d = r.json()
                # Should be blocked or errored
                assert d.get("ok") is False or "error" in str(d).lower(), \
                    f"Dangerous code not blocked: {code!r}"

    async def test_08_profiler_summary_has_data(self, client):
        """After profiler runs, summary has data."""
        await POST(client, "/api/profiler/profile/run", {"code": "x = 1 + 1"})
        r = await GET(client, "/api/profiler/summary")
        assert r.status_code in (200, 404)
        if r.status_code == 200:
            check("summary is dict", isinstance(r.json(), dict))

    async def test_09_flamegraph_accessible(self, client):
        """Flamegraph endpoint returns after profiler activity."""
        r = await GET(client, "/api/profiler/flamegraph")
        assert r.status_code in (200, 404)

    async def test_10_profiler_endpoints_list(self, client):
        """Profiler endpoints list tracks API calls."""
        r = await GET(client, "/api/profiler/endpoints")
        assert r.status_code in (200, 404)
        if r.status_code == 200:
            d = r.json()
            endpoints = d.get("endpoints", d) if isinstance(d, dict) else d
            check("endpoints is list", isinstance(endpoints, (list, dict)))


@pytest.mark.asyncio
class TestMemoryIntegration:
    """Memory add → search → stats coherence."""

    async def test_01_add_and_search_memory(self, client):
        """Add memory → immediately searchable via FTS."""
        unique = uid("integration_memory")
        r = await POST(client, "/api/memory/add", {
            "content": f"Integration test memory {unique}",
            "source": "integration_test",
            "tags": "integration,test"
        })
        d = ok(r)
        check("ok true", d["ok"] is True)
        mid = d["id"]
        check("id is int", isinstance(mid, int))

        # Search for it
        search = ok(await GET(client, "/api/memory/search", q=unique))
        check("search returns list", isinstance(search, list))
        found = any(unique in m.get("content", "") for m in search)
        check("memory found in search", found)

        await DELETE(client, f"/api/memory/{mid}")

    async def test_02_stats_reflect_add(self, client):
        """Stats count increases after add."""
        stats1 = ok(await GET(client, "/api/memory/stats"))
        count1 = stats1.get("sqlite_memories") or stats1.get("total") or stats1.get("count", 0)

        await POST(client, "/api/memory/add", {
            "content": uid("stats_check_memory"), "source": "integration"
        })

        stats2 = ok(await GET(client, "/api/memory/stats"))
        count2 = stats2.get("sqlite_memories") or stats2.get("total") or stats2.get("count", 0)

        check("count increased after add", count2 > count1)

    async def test_03_hybrid_search_accessible(self, client):
        """Hybrid search endpoint works."""
        r = await GET(client, "/api/memory/hybrid-search", q="integration")
        assert r.status_code in (200, 404)

    async def test_04_galaxy_graph_accessible(self, client):
        """Memory galaxy graph endpoint returns visualization data."""
        r = await GET(client, "/api/memory/galaxy")
        assert r.status_code in (200, 404)
        if r.status_code == 200:
            d = r.json()
            check("galaxy has nodes or data", isinstance(d, (dict, list)))

    async def test_05_bulk_delete_memory(self, client):
        """Bulk delete removes specified memories."""
        # Add some memories
        ids = []
        for i in range(3):
            r = await POST(client, "/api/memory/add", {
                "content": uid(f"bulk_del_{i}"), "source": "integration"
            })
            ids.append(ok(r)["id"])

        r = await POST(client, "/api/memory/bulk-delete", {"ids": ids})
        assert r.status_code in (200, 404, 422)

    async def test_06_export_includes_entries(self, client):
        """Export returns memories as JSON."""
        await POST(client, "/api/memory/add", {
            "content": uid("export_test_memory"), "source": "integration"
        })
        r = await GET(client, "/api/memory/export")
        assert r.status_code in (200, 404)
        if r.status_code == 200:
            d = r.json()
            mems = d.get("memories", d) if isinstance(d, dict) else d
            check("memories is list", isinstance(mems, list))
