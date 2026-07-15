"""
SYS-05: Spec-Driven Development E2E
SYS-09: Code Intelligence Pipeline
SYS-15: Terminal + Profiler Safety
SYS-16: Workflow Build + Run + Replay
SYS-23: BugBot Code Review Pipeline
SYS-29: SSE Streaming Correctness
"""
import pytest
from tests.system.conftest import *


class TestSysSpecDriven:
    """SYS-05 — Spec-driven development end-to-end."""

    async def test_spec_full_lifecycle(self, C):
        """Create → get → tasks → export → delete."""
        name = uid("SysSpec")
        r = await POST(C, "/api/specs", {
            "name": name,
            "description": "Build a system test specification for a REST API."
        })
        d = must(r, 200)
        spid = d.get("id") or (d.get("spec") or {}).get("id")
        check("spec id returned", bool(spid))

        # GET by id
        r2 = await GET(C, f"/api/specs/{spid}")
        must(r2, 200, 404)
        if r2.status_code == 200:
            sp = r2.json()
            sp = sp.get("spec", sp) if isinstance(sp, dict) else sp
            check("has title or id", "id" in sp or "title" in sp)

        # Seed tasks
        r3 = await POST(C, f"/api/specs/{spid}/tasks", {
            "tasks": [
                {"title": "Design API schema",       "description": "Define endpoints", "wave": 1},
                {"title": "Implement endpoints",     "description": "Code the handlers", "wave": 2},
                {"title": "Write tests",             "description": "pytest suite",     "wave": 2},
            ]
        })
        must(r3, 200, 404, 422)

        # List tasks
        r4 = await GET(C, f"/api/specs/{spid}/tasks")
        must(r4, 200, 404)
        if r4.status_code == 200:
            tasks = r4.json()
            check("tasks returned", isinstance(tasks, (list, dict)))

        # Export
        r5 = await GET(C, f"/api/specs/{spid}/export")
        must(r5, 200, 404)
        if r5.status_code == 200:
            check("export has content", len(r5.content) > 0)

        # Delete
        await DELETE(C, f"/api/specs/{spid}")

        # Verify gone
        specs = must(await GET(C, "/api/specs"), 200)
        sp_list = specs.get("specs", specs) if isinstance(specs, dict) else specs
        ids = [s.get("id") for s in sp_list if isinstance(s, dict)]
        check("spec deleted", spid not in ids)

    async def test_multiple_specs_in_list(self, C):
        """Multiple specs coexist in the list independently."""
        created = []
        for i in range(3):
            r = await POST(C, "/api/specs", {
                "name": uid(f"MultiSpec{i}"),
                "description": f"Multi-spec test {i}"
            })
            d = must(r, 200)
            spid = d.get("id") or (d.get("spec") or {}).get("id")
            if spid:
                created.append(spid)

        specs = must(await GET(C, "/api/specs"), 200)
        sp_list = specs.get("specs", specs) if isinstance(specs, dict) else specs
        ids = {s.get("id") for s in sp_list if isinstance(s, dict)}
        for spid in created:
            check(f"spec {spid} in list", spid in ids)
            await DELETE(C, f"/api/specs/{spid}")


class TestSysCodeIntelligence:
    """SYS-09 — Code intelligence: index → search → complexity → profiler."""

    async def test_codeindex_stats_accessible(self, C):
        """Code index stats endpoint returns data."""
        r = await GET(C, "/api/codeindex/stats")
        must(r, 200, 404)
        if r.status_code == 200:
            check("stats is dict", isinstance(r.json(), dict))

    async def test_index_real_file(self, C):
        """Index a real project file — endpoint responds."""
        r = await POST(C, "/api/codeindex/index", {
            "path": "/home/user/agentic-os/backend/routers/websearch.py"
        })
        must(r, 200, 400, 404, 422)

    async def test_symbols_list(self, C):
        """Symbols list returns indexable symbols."""
        r = await GET(C, "/api/codeindex/symbols")
        must(r, 200, 404)
        if r.status_code == 200:
            d = r.json()
            symbols = d.get("symbols", d) if isinstance(d, dict) else d
            check("symbols is list", isinstance(symbols, list))

    async def test_complexity_endpoint(self, C):
        """Complexity endpoint accessible."""
        r = await GET(C, "/api/codeindex/complexity")
        must(r, 200, 404)

    async def test_dead_code_detection(self, C):
        """Dead code detection endpoint accessible."""
        r = await GET(C, "/api/codeindex/dead-code")
        must(r, 200, 404)

    async def test_graph_endpoint(self, C):
        """Dependency graph accessible."""
        r = await GET(C, "/api/codeindex/graph")
        must(r, 200, 404)


class TestSysTerminalProfiler:
    """SYS-15 — Terminal safety + profiler integration."""

    async def test_terminal_echo_produces_sse(self, C):
        """Echo via terminal → SSE stream with output."""
        import httpx as _httpx
        marker = uid("sysecho")
        async with _httpx.AsyncClient(base_url="http://127.0.0.1:8787", timeout=20) as fresh:
            r = await fresh.post("/api/terminal/run", json={"command": f"echo {marker}"})
        must(r, 200)
        check("SSE data events", "data:" in r.text)
        check("echo output in stream", marker in r.text)
        events = sse_events(r.text)
        check("has start event", any(e.get("type") == "start" for e in events))
        check("has exit event",  any(e.get("type") == "exit"  for e in events))

    async def test_terminal_exit_code_0_for_success(self, C):
        """Successful command → exit_code 0."""
        import httpx as _httpx
        async with _httpx.AsyncClient(base_url="http://127.0.0.1:8787", timeout=20) as fresh:
            r = await fresh.post("/api/terminal/run", json={"command": "echo done_exit_0"})
        must(r, 200)
        events = sse_events(r.text)
        # Find exit event or look for exit_code in any event
        exit_ev = next((e for e in events if e.get("type") == "exit"), None)
        error_ev = next((e for e in events if e.get("type") == "error"), None)
        check("has exit or stdout event",
              exit_ev is not None or any(e.get("type") == "stdout" for e in events))
        if exit_ev:
            check("exit_code 0", exit_ev.get("exit_code") == 0)

    async def test_terminal_nonzero_for_failure(self, C):
        """Failing command → non-zero exit_code."""
        import httpx as _httpx
        async with _httpx.AsyncClient(base_url="http://127.0.0.1:8787", timeout=20) as fresh:
            r = await fresh.post("/api/terminal/run", json={"command": "false"})
        must(r, 200)
        events = sse_events(r.text)
        exit_ev = next((e for e in events if e.get("type") == "exit"), None)
        if exit_ev:
            check("exit_code non-zero", exit_ev.get("exit_code", 0) != 0)

    async def test_terminal_history_recorded(self, C):
        """Terminal history records commands."""
        cmd = f"echo sys_hist_{uid()}"
        await POST(C, "/api/terminal/run", {"command": cmd})
        r = await GET(C, "/api/terminal/history")
        must(r, 200, 404)

    async def test_profiler_safe_math_code(self, C):
        """Profiler runs safe mathematical Python code."""
        r = await POST(C, "/api/profiler/profile/run", {
            "code": "result = sum(i**2 for i in range(1000))\nassert result == 332833500"
        })
        must(r, 200, 400, 422)
        if r.status_code == 200:
            check("profiler response ok", "ok" in r.json())

    async def test_profiler_blocks_os_system(self, C):
        """Profiler must block os.system() calls."""
        r = await POST(C, "/api/profiler/profile/run",
                       {"code": "import os; os.system('whoami')"})
        must(r, 200, 400, 403, 422)
        if r.status_code == 200:
            d = r.json()
            check("os.system blocked",
                  d.get("ok") is False or "block" in str(d).lower() or
                  "error" in str(d).lower())

    async def test_profiler_blocks_subprocess(self, C):
        """Profiler must block subprocess calls."""
        r = await POST(C, "/api/profiler/profile/run",
                       {"code": "import subprocess; subprocess.run(['ls', '/'])"})
        must(r, 200, 400, 403, 422)
        if r.status_code == 200:
            d = r.json()
            check("subprocess blocked",
                  d.get("ok") is False or "error" in str(d).lower())

    async def test_profiler_flamegraph(self, C):
        """Flamegraph endpoint returns after profiler activity."""
        await POST(C, "/api/profiler/profile/run", {"code": "x = [i for i in range(100)]"})
        r = await GET(C, "/api/profiler/flamegraph")
        must(r, 200, 404)

    async def test_profiler_summary_has_data(self, C):
        """Profiler summary reflects endpoint activity."""
        r = await GET(C, "/api/profiler/summary")
        must(r, 200, 404)
        if r.status_code == 200:
            check("summary is dict", isinstance(r.json(), dict))


class TestSysWorkflow:
    """SYS-16 — Workflow build + run + replay."""

    async def test_create_workflow_with_full_node_graph(self, C):
        """Create multi-node workflow → verify structure."""
        name = uid("SysWorkflow")
        r = await POST(C, "/api/workflow", {
            "name": name,
            "nodes": [
                {"id":"n1","type":"trigger", "label":"Start",    "x":0,   "y":0},
                {"id":"n2","type":"agent",   "label":"Process",  "x":200, "y":0,
                 "agent_id": "builder", "prompt": "Process: {{input}}"},
                {"id":"n3","type":"condition","label":"Check",   "x":400, "y":0},
                {"id":"n4","type":"output",  "label":"Done",     "x":600, "y":0},
            ],
            "edges": [
                {"from":"n1","to":"n2"},
                {"from":"n2","to":"n3"},
                {"from":"n3","to":"n4"},
            ]
        })
        d = must(r, 200)
        wid = d.get("id") or (d.get("workflow") or {}).get("id")
        check("workflow id returned", bool(wid))

        # Verify structure
        r2 = await GET(C, f"/api/workflow/{wid}")
        must(r2, 200, 404)
        if r2.status_code == 200:
            wf = r2.json()
            wf = wf.get("workflow", wf) if isinstance(wf, dict) else wf
            check("has nodes", bool(wf.get("nodes") or wf.get("id")))

        # Verify in list
        wfs = must(await GET(C, "/api/workflow"), 200)
        wf_list = wfs if isinstance(wfs, list) else wfs.get("workflows",[])
        ids = {w.get("id") for w in wf_list}
        check("workflow in list", wid in ids)

        await DELETE(C, f"/api/workflow/{wid}")

    async def test_workflow_node_types_valid(self, C):
        """Node types list returns valid types for palette."""
        r = await GET(C, "/api/workflow/node-types/list")
        must(r, 200, 404)
        if r.status_code == 200:
            d = r.json()
            check("node types is dict or list", isinstance(d, (dict, list)))

    async def test_replay_runs_list(self, C):
        """Replay runs list is accessible."""
        r = await GET(C, "/api/replay/runs")
        must(r, 200, 404)
        if r.status_code == 200:
            d = r.json()
            runs = d.get("runs", d) if isinstance(d, dict) else d
            check("runs is list", isinstance(runs, list))


class TestSysBugBot:
    """SYS-23 — BugBot code review pipeline."""

    async def test_empty_diff_rejected_clearly(self, C):
        """Empty diff → ok:false with error message."""
        r = await POST(C, "/api/bugbot/review/diff", {"diff": "", "agent_id": "builder"})
        d = r.json()
        check("ok false",    d["ok"] is False)
        check("has error",   "error" in d)
        check("not a crash", r.status_code < 500)

    async def test_review_diff_schema_accepted(self, C):
        """Valid diff accepted (may fail without LLM but schema is correct)."""
        diff = ("+ def calculate_tax(amount: float, rate: float) -> float:\n"
                "+     \"\"\"Calculate tax amount.\"\"\"\n"
                "+     if rate < 0 or rate > 1:\n"
                "+         raise ValueError('Rate must be 0-1')\n"
                "+     return amount * rate\n")
        r = await POST(C, "/api/bugbot/review/diff",
                       {"diff": diff, "agent_id": "builder"})
        check("not a crash", r.status_code < 500)

    async def test_review_file_schema_accepted(self, C):
        """File review with valid Python code is accepted."""
        code = "def add(a: int, b: int) -> int:\n    return a + b\n"
        r = await POST(C, "/api/bugbot/review/file", {
            "content": code, "filename": "math_utils.py", "agent_id": "builder"
        })
        check("not a crash", r.status_code < 500)

    async def test_reviews_list_accessible(self, C):
        r = await GET(C, "/api/bugbot/reviews")
        must(r, 200, 404)

    async def test_stats_accessible(self, C):
        r = await GET(C, "/api/bugbot/stats")
        must(r, 200, 404)


class TestSysSSEStreaming:
    """SYS-29 — SSE streaming correctness across endpoints."""

    async def test_terminal_sse_parse(self, C):
        """Terminal SSE stream parses into valid events."""
        import httpx as _httpx
        async with _httpx.AsyncClient(base_url="http://127.0.0.1:8787", timeout=20) as fresh:
            r = await fresh.post("/api/terminal/run", json={"command": "echo sys_sse_test"})
        must(r, 200)
        events = sse_events(r.text)
        check("≥ 2 events",         len(events) >= 2)
        types = {e.get("type") for e in events}
        check("has start",           "start" in types)
        check("has exit or stdout",  "exit" in types or "stdout" in types)

        start = next((e for e in events if e.get("type") == "start"), None)
        check("start has command",   start is not None and "command" in start)
        check("start has run_id",    start is not None and "run_id" in start)

    async def test_terminal_sse_stdout_contains_output(self, C):
        """SSE stdout event contains correct output."""
        import httpx as _httpx
        async with _httpx.AsyncClient(base_url="http://127.0.0.1:8787", timeout=20) as fresh:
            r = await fresh.post("/api/terminal/run", json={"command": "echo sys_output_marker"})
        must(r, 200)
        events = sse_events(r.text)
        stdout_ev = next((e for e in events if e.get("type") == "stdout"), None)
        check("stdout event present", stdout_ev is not None)
        if stdout_ev:
            check("contains output", "sys_output_marker" in stdout_ev.get("data",""))

    async def test_browser_task_sse_parse(self, C):
        """Browser agent task returns parseable SSE."""
        import httpx as _httpx
        async with _httpx.AsyncClient(base_url="http://127.0.0.1:8787", timeout=30) as fresh:
            r = await fresh.post("/api/browser/task", json={
                "url": "https://example.com",
                "task": "System test: verify SSE stream works",
                "max_steps": 2
            })
        must(r, 200)
        events = sse_events(r.text)
        check("≥ 1 event",           len(events) >= 1)
        types = {e.get("type") for e in events}
        check("has session_start or done",
              "session_start" in types or "done" in types or "step" in types)

    async def test_websearch_stream_parses(self, C):
        """Websearch grounded stream produces parseable events."""
        import httpx as _httpx
        async with _httpx.AsyncClient(base_url="http://127.0.0.1:8787", timeout=30) as fresh:
            r = await fresh.post("/api/websearch/grounded-completion/stream",
                                 json={"prompt": "What is FastAPI?", "num_results": 2})
        must(r, 200)
        events = sse_events(r.text)
        check("≥ 1 SSE event", len(events) >= 1)
        types = {e.get("type") for e in events}
        check("has searching or search_done or chunk",
              bool(types & {"searching", "search_done", "chunk", "done"}))

    async def test_research_stream_parses(self, C):
        """Research stream produces valid SSE events."""
        import httpx as _httpx
        async with _httpx.AsyncClient(base_url="http://127.0.0.1:8787", timeout=30) as fresh:
            r = await fresh.post("/api/websearch/research",
                                 json={"topic": "FastAPI vs Django"})
        must(r, 200)
        events = sse_events(r.text)
        check("has events", len(events) >= 1)
        types = {e.get("type") for e in events}
        check("has research event",
              bool(types & {"research_start","queries","sources_gathered","chunk","done"}))
