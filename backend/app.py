"""
Agentic OS v6.0 — Backend Entry Point
Local-first Agentic AI Operating System
"""
from __future__ import annotations
import os, logging
from pathlib import Path
from contextlib import asynccontextmanager
from dotenv import load_dotenv

# ── Load .env FIRST before any service imports ─────────────────────────────────
_ROOT = Path(__file__).resolve().parent.parent
load_dotenv(_ROOT / ".env", override=False)

from fastapi import FastAPI, Request
from fastapi.middleware.cors import CORSMiddleware
from fastapi.staticfiles import StaticFiles
from fastapi.responses import FileResponse
from fastapi.websockets import WebSocket
from starlette.websockets import WebSocketDisconnect
import sqlite3

logging.basicConfig(level=logging.INFO, format="%(asctime)s [%(name)s] %(levelname)s: %(message)s")
log = logging.getLogger("agentic.app")

# ── Services ───────────────────────────────────────────────────────────────────
from .services.memory_db import (
    ensure_schema, agents_seed_defaults, audit_log, audit_list,
    memory_stats, agents_list, get_conn,
)
from .services import scheduler as sched_svc

# ── Routers ────────────────────────────────────────────────────────────────────
from .routers.chat      import router as chat_router
from .routers.swarm     import router as swarm_router
from .routers.memory    import router as memory_router
from .routers.agents    import router as agents_router
from .routers.secrets   import router as secrets_router
from .routers.builder   import router as builder_router
from .routers.mcp       import router as mcp_router
from .routers.loops     import router as loops_router
from .routers.websocket import router as ws_router
from .routers.tts       import router as tts_router
from .routers.deploy    import router as deploy_router
from .routers.e2e       import router as e2e_router
from .routers.skills    import router as skills_router
from .routers.analytics import router as analytics_router
from .routers.pipeline  import router as pipeline_router
from .routers.obsidian  import router as obsidian_router
from .routers.system    import router as system_router
from .routers.plugins   import router as plugins_router
from .routers.onboarding import router as onboarding_router
from .routers.collab    import router as collab_router
from .routers.github    import router as github_router
from .routers.database  import router as database_router
from .routers.multifile_agent import router as composer_router
from .routers.sessions     import router as sessions_router
from .routers.templates    import router as templates_router
from .routers.control_tower import router as control_tower_router
from .routers.workspaces   import router as workspaces_router
from .routers.webhooks     import router as webhooks_router
from .routers.testgen      import router as testgen_router
from .routers.terminal     import router as terminal_router
from .routers.imagegen     import router as imagegen_router
from .routers.integrations import router as integrations_router
from .routers.prompts      import router as prompts_router
from .routers.codesearch   import router as codesearch_router
from .routers.workflow     import router as workflow_router
from .routers.profiler     import router as profiler_router
from .routers.pluginsdk    import router as pluginsdk_router
from .routers.multitab     import router as multitab_router
from .routers.tauri_build  import router as tauri_router
from .routers.replay       import router as replay_router
from .routers.crdt         import router as crdt_router
from .routers.marketplace  import router as marketplace_router
from .routers.specs        import router as specs_router
from .routers.hooks        import router as hooks_router
from .routers.codeindex    import router as codeindex_router
from .routers.arena        import router as arena_router
from .routers.voice        import router as voice_router
from .routers.steering          import router as steering_router
from .routers.bugbot            import router as bugbot_router
from .routers.ambient           import router as ambient_router
from .routers.gitai             import router as gitai_router
from .routers.fusion            import router as fusion_router
from .routers.hitl              import router as hitl_router
from .routers.browser_agent     import router as browser_router
from .routers.websearch         import router as websearch_router
from .routers.agent_leaderboard import router as leaderboard_router
from .routers.evals             import router as evals_router
from .routers.observability     import router as observability_router
from .routers.knowledge_graph   import router as knowledge_graph_router
from .routers.rag               import router as rag_router
from .routers.license           import router as license_router
from .routers.userprofile       import router as userprofile_router
from .routers.docs_center       import router as docs_router
# ── Sprint A: Governance Foundation ───────────────────────────────────────────
from .routers.audit_log         import router as audit_log_router
from .routers.compliance         import router as compliance_router
from .routers.drift              import router as drift_router
from .routers.a2a                import router as a2a_router
from .routers.agent_identity    import router as agent_identity_router


# ── Lifespan (startup / shutdown) ──────────────────────────────────────────────
@asynccontextmanager
async def lifespan(app: FastAPI):
    # ── Startup ──
    log.info("Agentic OS v6.0 starting…")
    ensure_schema()
    agents_seed_defaults()
    # Inject vault secrets into env
    try:
        from .routers.secrets import _inject_to_env
        _inject_to_env()
        log.info("Vault secrets injected into env")
    except Exception as e:
        log.warning("Vault inject failed: %s", e)
    # Start autonomous scheduler
    try:
        sched_svc.start()
        log.info("Autonomous scheduler started")
    except Exception as e:
        log.warning("Scheduler failed: %s", e)
    log.info("Agentic OS ready → http://localhost:%s", os.getenv("AGENTIC_OS_PORT", "8787"))
    yield
    # ── Shutdown ──
    log.info("Agentic OS shutting down…")
    sched_svc.stop()


# ── FastAPI App ────────────────────────────────────────────────────────────────
app = FastAPI(
    title="Agentic OS v6.0",
    description="Local-first Agentic AI Operating System",
    version="6.0.0",
    lifespan=lifespan,
)

app.add_middleware(
    CORSMiddleware,
    # SECURITY FIX: Never combine allow_credentials=True with wildcard origin ("*").
    # Explicit local-only origins; credentials are safe only with these known origins.
    allow_origins=[
        "http://localhost:8787", "http://127.0.0.1:8787",
        "http://localhost:3000", "http://localhost:5173",
        "http://localhost:1420",  # Tauri dev
        "tauri://localhost",      # Tauri production
    ],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# ── Static files ───────────────────────────────────────────────────────────────
FRONTEND_DIR = _ROOT / "frontend"
PREVIEW_DIR  = _ROOT / "preview"
PREVIEW_DIR.mkdir(exist_ok=True)

app.mount("/static",  StaticFiles(directory=str(FRONTEND_DIR)), name="static")
app.mount("/preview", StaticFiles(directory=str(PREVIEW_DIR), html=True), name="preview")

# ── Routers ────────────────────────────────────────────────────────────────────
app.include_router(chat_router)
app.include_router(swarm_router)
app.include_router(memory_router)
app.include_router(agents_router)
app.include_router(secrets_router)
app.include_router(builder_router)
app.include_router(mcp_router)
app.include_router(loops_router)
app.include_router(ws_router)
app.include_router(tts_router)
app.include_router(deploy_router)
app.include_router(e2e_router)
app.include_router(skills_router)
app.include_router(analytics_router)
app.include_router(pipeline_router)
app.include_router(obsidian_router)
app.include_router(system_router)
app.include_router(plugins_router)
app.include_router(onboarding_router)
app.include_router(collab_router)
app.include_router(github_router)
app.include_router(database_router)
app.include_router(composer_router)
app.include_router(sessions_router)
app.include_router(templates_router)
app.include_router(control_tower_router)
app.include_router(workspaces_router)
app.include_router(webhooks_router)
app.include_router(testgen_router)
app.include_router(terminal_router)
app.include_router(imagegen_router)
app.include_router(integrations_router)
app.include_router(prompts_router)
app.include_router(codesearch_router)
app.include_router(workflow_router)
app.include_router(profiler_router)

# FIX 1: Timing middleware to populate _endpoint_stats for the profiler
from .routers.profiler import record_endpoint_latency as _record_latency
import time as _time
@app.middleware("http")
async def _latency_middleware(request, call_next):
    t0 = _time.perf_counter()
    response = await call_next(request)
    ms = (_time.perf_counter() - t0) * 1000
    _record_latency(request.url.path, ms)
    return response

app.include_router(pluginsdk_router)
app.include_router(multitab_router)
app.include_router(tauri_router)
app.include_router(replay_router)
app.include_router(crdt_router)
app.include_router(marketplace_router)
app.include_router(specs_router)
app.include_router(hooks_router)
app.include_router(codeindex_router)
app.include_router(arena_router)
app.include_router(voice_router)
app.include_router(steering_router)
app.include_router(bugbot_router)
app.include_router(ambient_router)
app.include_router(gitai_router)
app.include_router(fusion_router)
app.include_router(hitl_router)
app.include_router(browser_router)
app.include_router(websearch_router)
app.include_router(leaderboard_router)
app.include_router(evals_router)
app.include_router(observability_router)
app.include_router(knowledge_graph_router)
app.include_router(rag_router)
app.include_router(license_router)
app.include_router(userprofile_router)
app.include_router(docs_router)
# Sprint A
app.include_router(audit_log_router)
app.include_router(compliance_router)
app.include_router(drift_router)
app.include_router(a2a_router)
app.include_router(agent_identity_router)
# Sprint B
from .routers.supervisor   import router as supervisor_router
from .routers.goal_manager import router as goal_manager_router
app.include_router(supervisor_router)
app.include_router(goal_manager_router)
# Sprint C
from .routers.mcp_gateway import router as mcp_gateway_router
from .routers.connectors  import router as connectors_router
app.include_router(mcp_gateway_router)
app.include_router(connectors_router)
# Sprint D
from .routers.agent_monitor  import router as agent_monitor_router
from .routers.finops         import router as finops_router
from .routers.eval_framework import router as eval_framework_router
app.include_router(agent_monitor_router)
app.include_router(finops_router)
app.include_router(eval_framework_router)

# ── WebSocket endpoint registered directly on app (include_router may not work for WS in FastAPI 0.139+) ──
from .routers.websocket import manager as _ws_manager, _send_init as _ws_send_init
from .routers.websocket import _handle_message as _ws_handle_msg, _get_agent_statuses, _get_memory_stats

@app.websocket("/ws")
async def websocket_endpoint_direct(ws: WebSocket):
    """Primary WebSocket endpoint for real-time updates."""
    await _ws_manager.connect(ws)
    tasks = []
    try:
        await _ws_send_init(ws)

        async def heartbeat():
            import time
            while True:
                await asyncio.sleep(5)
                try:
                    await _ws_manager.send_to(ws, {"type": "ping", "ts": time.time()})
                except Exception:
                    break

        async def status_updates():
            while True:
                await asyncio.sleep(8)
                try:
                    agents = await _get_agent_statuses()
                    await _ws_manager.send_to(ws, {"type": "agent_status", "agents": agents})
                    stats = await _get_memory_stats()
                    await _ws_manager.send_to(ws, {"type": "memory_stats", **stats})
                except Exception:
                    break

        tasks = [
            asyncio.create_task(heartbeat()),
            asyncio.create_task(status_updates()),
        ]

        while True:
            try:
                data = await ws.receive_text()
                msg = json.loads(data)
                await _ws_handle_msg(ws, msg)
            except WebSocketDisconnect:
                break
            except Exception as e:
                logging.getLogger("agentic.ws").warning("WS msg error: %s", e)
                break

    except WebSocketDisconnect:
        pass
    finally:
        _ws_manager.disconnect(ws)
        for t in tasks:
            t.cancel()


# ── HITL WebSocket endpoint ────────────────────────────────────────────────────
@app.websocket("/api/ws")
async def hitl_ws_endpoint(ws: WebSocket):
    """Secondary WebSocket for HITL interrupts (frontend at /api/ws)."""
    await _ws_manager.connect(ws)
    try:
        await _ws_send_init(ws)
        while True:
            try:
                data = await ws.receive_text()
                msg = json.loads(data)
                await _ws_handle_msg(ws, msg)
            except WebSocketDisconnect:
                break
            except Exception:
                break
    except WebSocketDisconnect:
        pass
    finally:
        _ws_manager.disconnect(ws)


# ── Core routes ────────────────────────────────────────────────────────────────
@app.get("/")
def index():
    return FileResponse(FRONTEND_DIR / "index.html")

@app.get("/manifest.json")
def manifest():
    return FileResponse(FRONTEND_DIR / "manifest.json", media_type="application/manifest+json")

@app.get("/sw.js")
def service_worker():
    return FileResponse(FRONTEND_DIR / "sw.js", media_type="application/javascript")


@app.get("/api/goals")
def goals():
    con = get_conn()
    try:
        rows = con.execute("SELECT * FROM goals ORDER BY id").fetchall()
    finally:
        con.close()
    result = [dict(r) for r in rows]
    if not result:
        result = [
            {"id":1,"title":"Wire OpenRouter chat (streaming)","layer":"Goals","progress":100,"status":"done"},
            {"id":2,"title":"Multi-agent swarm + AI judge","layer":"Execution","progress":100,"status":"done"},
            {"id":3,"title":"Memory Galaxy 3D","layer":"Memory","progress":100,"status":"done"},
            {"id":4,"title":"MCP Tool Router","layer":"Ship","progress":100,"status":"done"},
            {"id":5,"title":"Autonomous scheduler loops","layer":"Execution","progress":100,"status":"done"},
            {"id":6,"title":"WebSocket real-time updates","layer":"Goals","progress":100,"status":"done"},
            {"id":7,"title":"Tauri desktop app","layer":"Ship","progress":65,"status":"active"},
            {"id":8,"title":"Voice agent (Whisper + TTS)","layer":"Execution","progress":20,"status":"active"},
        ]
    return result


@app.get("/api/cost")
def cost():
    con = get_conn()
    try:
        rows = con.execute(
            "SELECT agent, SUM(tokens) as t, SUM(cost) as c FROM chat_log GROUP BY agent"
        ).fetchall()
        by_agent     = [dict(r) for r in rows]
        total_tokens = sum(r["t"] or 0 for r in by_agent)
        total_cost   = sum(r["c"] or 0.0 for r in by_agent)
    except Exception:
        by_agent, total_tokens, total_cost = [], 0, 0.0
    finally:
        con.close()
    return {
        "total_tokens":    total_tokens,
        "total_cost_usd":  round(total_cost, 6),
        "saved_vs_saas":   round(max(0, 350 - total_cost * 100), 2),
        "by_agent":        by_agent,
    }


@app.get("/api/audit")
def audit(limit: int = 100):
    return audit_list(limit)


# /api/skills and /api/skills/run now handled by skills_router


@app.post("/api/backup")
def backup():
    import shutil, datetime
    ts   = datetime.datetime.now().strftime("%Y%m%d_%H%M%S")
    dest = _ROOT / "memory" / f"backup_{ts}.db"
    try:
        shutil.copy2(_ROOT / "memory" / "agentic.db", dest)
        return {"ok": True, "path": str(dest), "filename": dest.name}
    except Exception as e:
        return {"ok": False, "error": str(e)}


# ── Kanban / Tasks ─────────────────────────────────────────────────────────────
def _task_dict(r) -> dict:
    d = dict(r)
    d["status"]      = d.get("status", "todo") if d.get("status") in ("todo","doing","blocked","done") else "todo"
    d["priority"]    = d.get("priority", "medium") if d.get("priority") in ("high","medium","low") else "medium"
    d["agent"]       = d.get("agent") or "builder"
    d["layer"]       = d.get("layer") or "Tasks"
    d["description"] = d.get("description") or ""
    d["sort_order"]  = d.get("sort_order") or d.get("id") or 0
    return d


@app.get("/api/kanban")
def kanban():
    con = get_conn()
    try:
        rows = con.execute("""
            SELECT id, title, status, priority, agent,
                   COALESCE(layer,'Tasks') as layer,
                   COALESCE(description,'') as description,
                   created_at,
                   COALESCE(updated_at, created_at) as updated_at,
                   COALESCE(sort_order, id) as sort_order
            FROM tasks
            ORDER BY CASE status WHEN 'doing' THEN 0 WHEN 'todo' THEN 1
                                 WHEN 'blocked' THEN 2 WHEN 'done' THEN 3 ELSE 4 END,
                     sort_order ASC, id DESC
        """).fetchall()
    except Exception:
        rows = con.execute("SELECT id,title,status,priority,agent,created_at FROM tasks ORDER BY id DESC").fetchall()
    con.close()
    cols = {"todo":[],"doing":[],"blocked":[],"done":[]}
    for r in rows:
        t = _task_dict(r)
        cols.get(t["status"], cols["todo"]).append(t)
    return cols


@app.get("/api/tasks")
def tasks_list(status: str = "", agent: str = "", limit: int = 200, q: str = ""):
    con = get_conn()
    where, params = [], []
    if status: where.append("status=?");    params.append(status)
    if agent:  where.append("agent=?");     params.append(agent)
    if q:      where.append("title LIKE ?"); params.append(f"%{q}%")
    sql = ("SELECT id,title,status,priority,agent,COALESCE(layer,'Tasks') as layer,"
           "COALESCE(description,'') as description,created_at,COALESCE(sort_order,id) as sort_order FROM tasks")
    if where: sql += " WHERE " + " AND ".join(where)
    sql += " ORDER BY sort_order ASC, id DESC LIMIT ?"
    params.append(min(limit, 500))
    try:
        rows = con.execute(sql, params).fetchall()
    finally:
        con.close()
    return [_task_dict(r) for r in rows]


@app.post("/api/tasks")
async def tasks_create(req: Request):
    try:
        d = await req.json()
    except Exception:
        return {"ok": False, "error": "Invalid JSON body"}
    title    = (d.get("title") or "").strip()[:240]
    if not title: return {"ok": False, "error": "title required"}
    status   = d.get("status", "todo")
    priority = d.get("priority", "medium")
    agent    = (d.get("agent", "builder") or "builder")[:32]
    layer    = (d.get("layer", "Tasks") or "Tasks")[:48]
    desc     = (d.get("description", "") or "")[:2000]
    if status   not in ("todo","doing","blocked","done"):   status   = "todo"
    if priority not in ("high","medium","low"):             priority = "medium"
    con = get_conn()
    cur = con.execute(
        "INSERT INTO tasks(title,status,priority,agent,layer,description,sort_order,updated_at) VALUES (?,?,?,?,?,?,?,CURRENT_TIMESTAMP)",
        (title, status, priority, agent, layer, desc, d.get("sort_order", 0))
    )
    tid = cur.lastrowid
    con.execute("INSERT INTO audit(action,detail) VALUES ('task_create',?)", (f"{tid}:{title[:80]}",))
    con.commit()
    con.close()
    # broadcast via WS
    try:
        from .routers.websocket import broadcast_task_update
        import asyncio
        asyncio.create_task(broadcast_task_update({"id": tid, "title": title, "status": status, "action": "created"}))
    except Exception:
        pass
    return {"ok": True, "id": tid, "title": title, "status": status}


@app.post("/api/tasks/bulk_update")
async def tasks_bulk_update(req: Request):
    try:
        d = await req.json()
    except Exception:
        return {"ok": False, "error": "Invalid JSON body"}
    updates = d.get("updates", [])
    if not isinstance(updates, list): return {"ok": False, "error": "updates[] required"}
    con = get_conn()
    ok  = 0
    for u in updates[:200]:
        tid = u.get("id")
        if not tid: continue
        sets, vals = [], []
        if "status" in u and u["status"] in ("todo","doing","blocked","done"):
            sets.append("status=?"); vals.append(u["status"])
        if "sort_order" in u:
            try: sets.append("sort_order=?"); vals.append(int(u["sort_order"]))
            except: pass
        if sets:
            sets.append("updated_at=CURRENT_TIMESTAMP")
            vals.append(tid)
            con.execute(f"UPDATE tasks SET {', '.join(sets)} WHERE id=?", vals)
            ok += 1
    con.commit()
    con.close()
    return {"ok": True, "updated": ok}


@app.patch("/api/tasks/{task_id}")
async def tasks_update(task_id: int, req: Request):
    try:
        d = await req.json()
    except Exception:
        return {"ok": False, "error": "Invalid JSON body"}
    allowed = {"title","status","priority","agent","layer","description","sort_order"}
    sets, vals = [], []
    for k in allowed:
        if k not in d: continue
        v = d[k]
        if k == "status"      and v not in ("todo","doing","blocked","done"): continue
        if k == "priority"    and v not in ("high","medium","low"):           continue
        if k == "title":       v = str(v)[:240]
        if k == "agent":       v = str(v)[:32]
        if k == "layer":       v = str(v)[:48]
        if k == "description": v = str(v)[:2000]
        sets.append(f"{k}=?"); vals.append(v)
    if not sets: return {"ok": False, "error": "no valid fields"}
    sets.append("updated_at=CURRENT_TIMESTAMP")
    vals.append(task_id)
    con = get_conn()
    con.execute(f"UPDATE tasks SET {', '.join(sets)} WHERE id=?", vals)
    con.execute("INSERT INTO audit(action,detail) VALUES ('task_update',?)", (str(task_id),))
    con.commit()
    row = con.execute(
        "SELECT id,title,status,priority,agent,COALESCE(layer,'Tasks') as layer FROM tasks WHERE id=?",
        (task_id,)
    ).fetchone()
    con.close()
    return {"ok": True, "task": _task_dict(row) if row else {}}


@app.post("/api/tasks/{task_id}")
async def tasks_update_post(task_id: int, req: Request):
    return await tasks_update(task_id, req)


@app.delete("/api/tasks/{task_id}")
def tasks_delete(task_id: int):
    con = get_conn()
    cur = con.execute("DELETE FROM tasks WHERE id=?", (task_id,))
    con.execute("INSERT INTO audit(action,detail) VALUES ('task_delete',?)", (str(task_id),))
    con.commit()
    con.close()
    return {"ok": True, "deleted": task_id}


@app.post("/api/kanban/move")
async def kanban_move(req: Request):
    try:
        d = await req.json()
    except Exception:
        return {"ok": False, "error": "Invalid JSON body"}
    tid = d.get("id") or d.get("task_id")
    to  = d.get("to_status") or d.get("status")
    if not tid or to not in ("todo","doing","blocked","done"):
        return {"ok": False, "error": "id + to_status required"}
    con = get_conn()
    con.execute("UPDATE tasks SET status=?, updated_at=CURRENT_TIMESTAMP WHERE id=?", (to, int(tid)))
    con.commit()
    con.close()
    return {"ok": True}



# Pipeline now handled by pipeline_router (/api/pipeline/run)
