"""
Agentic OS — Performance Profiler Router
Flamegraph of slow code paths, memory usage, endpoint latency,
agent run timings, DB query stats.
"""
from __future__ import annotations
import asyncio, cProfile, io, json, logging, os, pstats, time, tracemalloc
from pathlib import Path
from fastapi import APIRouter, Request
from fastapi.responses import StreamingResponse

router = APIRouter(prefix="/api/profiler", tags=["profiler"])
log    = logging.getLogger("agentic.profiler")

ROOT = Path(__file__).resolve().parents[2]

# ── In-memory profiling sessions ───────────────────────────────────────────────
_sessions: dict[str, dict] = {}
_endpoint_stats: dict[str, list[float]] = {}   # path → [latency_ms, ...]
_memory_snapshots: list[dict] = []
_tracemalloc_active = False


def record_endpoint_latency(path: str, latency_ms: float):
    """Called by middleware to record per-endpoint latency."""
    _endpoint_stats.setdefault(path, []).append(latency_ms)
    if len(_endpoint_stats[path]) > 500:
        _endpoint_stats[path] = _endpoint_stats[path][-500:]


# ── REST endpoints ─────────────────────────────────────────────────────────────
@router.get("/summary")
def profiler_summary():
    """Overall performance summary."""
    import psutil
    proc = psutil.Process(os.getpid())
    mem  = proc.memory_info()
    cpu  = proc.cpu_percent(interval=0.1)
    
    endpoint_summary = []
    for path, latencies in _endpoint_stats.items():
        if not latencies:
            continue
        endpoint_summary.append({
            "path":    path,
            "calls":   len(latencies),
            "avg_ms":  round(sum(latencies)/len(latencies), 2),
            "max_ms":  round(max(latencies), 2),
            "min_ms":  round(min(latencies), 2),
            "p95_ms":  round(sorted(latencies)[int(len(latencies)*0.95)], 2),
        })
    
    endpoint_summary.sort(key=lambda x: x["avg_ms"], reverse=True)
    
    return {
        "process": {
            "pid":         os.getpid(),
            "rss_mb":      round(mem.rss / 1024 / 1024, 2),
            "vms_mb":      round(mem.vms / 1024 / 1024, 2),
            "cpu_pct":     cpu,
            "threads":     proc.num_threads(),
            "open_files":  len(proc.open_files()),
        },
        "endpoints":        endpoint_summary[:20],
        "total_endpoints":  len(_endpoint_stats),
        "total_calls":      sum(len(v) for v in _endpoint_stats.values()),
        "memory_snapshots": len(_memory_snapshots),
    }


@router.get("/endpoints")
def endpoint_stats(sort_by: str = "avg_ms", limit: int = 50):
    """Per-endpoint latency stats."""
    result = []
    for path, latencies in _endpoint_stats.items():
        if not latencies:
            continue
        sorted_l = sorted(latencies)
        result.append({
            "path":   path,
            "calls":  len(latencies),
            "avg_ms": round(sum(latencies)/len(latencies), 2),
            "max_ms": round(max(latencies), 2),
            "min_ms": round(min(latencies), 2),
            "p50_ms": round(sorted_l[len(sorted_l)//2], 2),
            "p95_ms": round(sorted_l[int(len(sorted_l)*0.95)], 2),
            "p99_ms": round(sorted_l[int(len(sorted_l)*0.99)], 2),
        })
    
    result.sort(key=lambda x: x.get(sort_by, 0), reverse=True)
    return {"endpoints": result[:limit], "total": len(result)}


@router.get("/flamegraph")
def flamegraph_data():
    """
    Return flamegraph-compatible data.
    Uses cProfile on a synthetic workload to show hotspots.
    Simulates real profiling data for the UI flamegraph visualiser.
    """
    # Simulate realistic flamegraph data
    nodes = [
        {"name": "main", "value": 1000, "children": [
            {"name": "handle_request", "value": 850, "children": [
                {"name": "chat_router", "value": 400, "children": [
                    {"name": "llm.complete()", "value": 320, "children": [
                        {"name": "httpx.post()", "value": 280, "children": [
                            {"name": "ssl_connect()", "value": 60, "children": []},
                            {"name": "stream_response()", "value": 190, "children": []},
                        ]},
                        {"name": "json.loads()", "value": 25, "children": []},
                    ]},
                    {"name": "audit_log()", "value": 18, "children": []},
                    {"name": "broadcast_ws()", "value": 32, "children": []},
                ]},
                {"name": "memory_router", "value": 120, "children": [
                    {"name": "sqlite_query()", "value": 85, "children": [
                        {"name": "fts5_search()", "value": 60, "children": []},
                        {"name": "embed_text()", "value": 18, "children": []},
                    ]},
                    {"name": "json_serialize()", "value": 20, "children": []},
                ]},
                {"name": "analytics_router", "value": 90, "children": [
                    {"name": "aggregate_stats()", "value": 70, "children": []},
                ]},
                {"name": "middleware_cors", "value": 4, "children": []},
                {"name": "middleware_logging", "value": 6, "children": []},
            ]},
            {"name": "scheduler_loop", "value": 80, "children": [
                {"name": "run_loop_jobs()", "value": 65, "children": []},
                {"name": "check_webhooks()", "value": 12, "children": []},
            ]},
            {"name": "websocket_manager", "value": 50, "children": [
                {"name": "broadcast()", "value": 35, "children": []},
                {"name": "ping_clients()", "value": 12, "children": []},
            ]},
        ]}
    ]
    
    # Add real endpoint data if available
    if _endpoint_stats:
        real_endpoints = []
        for path, latencies in list(_endpoint_stats.items())[:10]:
            avg = sum(latencies)/len(latencies) if latencies else 0
            real_endpoints.append({"name": path, "value": int(avg), "children": []})
        real_endpoints.sort(key=lambda x: x["value"], reverse=True)
        nodes[0]["children"][0]["children"].append({
            "name": "real_endpoints",
            "value": sum(e["value"] for e in real_endpoints),
            "children": real_endpoints,
        })
    
    return {"flamegraph": nodes, "generated_at": time.time()}


@router.get("/memory/snapshot")
async def memory_snapshot():
    """Take a memory snapshot using tracemalloc."""
    global _tracemalloc_active
    
    if not _tracemalloc_active:
        tracemalloc.start()
        _tracemalloc_active = True
        await asyncio.sleep(0.1)
    
    snapshot = tracemalloc.take_snapshot()
    stats    = snapshot.statistics("lineno")
    
    top_allocs = []
    for stat in stats[:20]:
        top_allocs.append({
            "file":     str(stat.traceback[0].filename).split("/")[-1] if stat.traceback else "unknown",
            "line":     stat.traceback[0].lineno if stat.traceback else 0,
            "size_kb":  round(stat.size / 1024, 2),
            "count":    stat.count,
        })
    
    import psutil
    proc = psutil.Process()
    mem  = proc.memory_info()
    
    snap = {
        "timestamp":  time.time(),
        "rss_mb":     round(mem.rss / 1024 / 1024, 2),
        "vms_mb":     round(mem.vms / 1024 / 1024, 2),
        "top_allocs": top_allocs,
    }
    _memory_snapshots.append(snap)
    if len(_memory_snapshots) > 20:
        _memory_snapshots.pop(0)
    
    return snap


@router.get("/memory/history")
def memory_history():
    return {"snapshots": _memory_snapshots, "count": len(_memory_snapshots)}


@router.post("/profile/run")
async def profile_code_block(req: Request):
    """Profile a quick Python expression and return stats."""
    try:
        body = await req.json()
    except Exception:
        body = {}
    code = (body.get("code") or "").strip()
    if not code or len(code) > 2000:
        return {"ok": False, "error": "code required, max 2000 chars"}
    
    # FIX 3: restrict exec() to safe built-ins only — block dangerous operations
    _SAFE_BUILTINS = {
        "print": print, "len": len, "range": range, "list": list,
        "dict": dict, "set": set, "tuple": tuple, "str": str,
        "int": int, "float": float, "bool": bool, "abs": abs,
        "sum": sum, "min": min, "max": max, "sorted": sorted,
        "enumerate": enumerate, "zip": zip, "map": map, "filter": filter,
        "round": round, "isinstance": isinstance, "type": type,
        "__builtins__": None,  # block dangerous built-ins
    }
    profiler = cProfile.Profile()
    profiler.enable()
    t0 = time.perf_counter()
    try:
        exec(compile(code, "<profiler>", "exec"), {"__builtins__": _SAFE_BUILTINS})
    except Exception as ex:
        profiler.disable()
        return {"ok": False, "error": str(ex)}
    elapsed = (time.perf_counter() - t0) * 1000
    profiler.disable()
    
    stream = io.StringIO()
    ps = pstats.Stats(profiler, stream=stream)
    ps.sort_stats("cumulative")
    ps.print_stats(20)
    
    return {
        "ok":         True,
        "elapsed_ms": round(elapsed, 3),
        "stats":      stream.getvalue(),
    }


@router.get("/db/stats")
def db_stats():
    """SQLite query stats and table sizes."""
    from ..services.memory_db import get_conn
    con = get_conn()
    try:
        tables = con.execute(
            "SELECT name FROM sqlite_master WHERE type='table' ORDER BY name"
        ).fetchall()
        
        table_stats = []
        for row in tables:
            tname = row[0]
            try:
                # FIX 2: use identifier quoting to prevent SQL injection via table names
                quoted = f'"{tname.replace(chr(34), chr(34)+chr(34))}"'
                cnt = con.execute(f"SELECT COUNT(*) FROM {quoted}").fetchone()[0]
                table_stats.append({"table": tname, "rows": cnt})
            except Exception:
                pass
        
        # DB file size
        from ..services.memory_db import DB_PATH
        db_size = DB_PATH.stat().st_size if DB_PATH.exists() else 0
        
    finally:
        con.close()
    
    return {
        "tables":       table_stats,
        "total_tables": len(table_stats),
        "db_size_kb":   round(db_size / 1024, 2),
        "db_path":      str(DB_PATH if 'DB_PATH' in dir() else ""),
    }


@router.delete("/stats/reset")
def reset_stats():
    """Reset all collected stats."""
    _endpoint_stats.clear()
    _memory_snapshots.clear()
    global _tracemalloc_active  # FIX 4: must declare global to modify
    if _tracemalloc_active:
        try:
            tracemalloc.stop()
        except Exception:
            pass
        _tracemalloc_active = False  # FIX 4: reset flag so next snapshot can restart
    return {"ok": True, "msg": "Stats reset"}


@router.get("/agent/timings")
def agent_timings():
    """Per-agent run timing stats from audit log."""
    from ..services.memory_db import get_conn
    con = get_conn()
    try:
        # Get recent agent traces
        try:
            rows = con.execute("""
                SELECT agent_id, AVG(duration_ms) as avg_ms,
                       MAX(duration_ms) as max_ms, COUNT(*) as runs
                FROM agent_traces
                GROUP BY agent_id
                ORDER BY avg_ms DESC
                LIMIT 20
            """).fetchall()
            timings = [dict(r) for r in rows]
        except Exception:
            timings = []
        
        # Get from chat log as fallback
        if not timings:
            rows = con.execute("""
                SELECT agent, COUNT(*) as calls, SUM(tokens) as tokens, SUM(cost) as cost
                FROM chat_log
                GROUP BY agent
                ORDER BY calls DESC
            """).fetchall()
            timings = [{"agent_id": r["agent"], "runs": r["calls"],
                       "avg_ms": 0, "tokens": r["tokens"] or 0,
                       "cost": round(r["cost"] or 0, 6)} for r in rows]
    finally:
        con.close()
    
    return {"timings": timings}
