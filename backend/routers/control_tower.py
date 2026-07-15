"""
Agentic OS — Agent Control Tower
The #1 enterprise differentiator: live observability, kill switch, budget guardrails.
Every agent run gets a trace with per-step cost/token/latency breakdown.
Kill any agent instantly. Set budget limits. View real-time execution logs.

PASS-1 AUDIT FIXES:
  - ROOT: parents[2] (was parents[3])
  - All get_conn() calls wrapped in try/finally: con.close()
"""
from __future__ import annotations
import asyncio, json, logging, os, time, uuid
from pathlib import Path
from fastapi import APIRouter, Request
from fastapi.responses import StreamingResponse
from ..services.memory_db import get_conn, audit_log

router = APIRouter(prefix="/api/control", tags=["control-tower"])
log    = logging.getLogger("agentic.control")

ROOT = Path(__file__).resolve().parents[2]   # FIX A-1: was parents[3]

# ── In-memory run registry ─────────────────────────────────────────────────────
_active_runs: dict[str, dict] = {}
_kill_flags:  set[str]        = set()
_run_queues:  dict[str, asyncio.Queue] = {}

# ── Schema ─────────────────────────────────────────────────────────────────────
def _ensure_traces_table():
    con = get_conn()
    try:
        con.execute("""
            CREATE TABLE IF NOT EXISTS agent_traces (
                id          INTEGER PRIMARY KEY,
                run_id      TEXT NOT NULL,
                agent_id    TEXT,
                agent_name  TEXT,
                prompt      TEXT,
                status      TEXT DEFAULT 'running',
                total_cost  REAL DEFAULT 0,
                total_tokens INTEGER DEFAULT 0,
                duration_ms INTEGER DEFAULT 0,
                step_count  INTEGER DEFAULT 0,
                error       TEXT,
                created_at  TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                updated_at  TIMESTAMP DEFAULT CURRENT_TIMESTAMP
            )
        """)
        con.execute("""
            CREATE TABLE IF NOT EXISTS agent_trace_steps (
                id          INTEGER PRIMARY KEY,
                run_id      TEXT NOT NULL,
                step_no     INTEGER,
                step_type   TEXT,
                name        TEXT,
                input_text  TEXT,
                output_text TEXT,
                model       TEXT,
                tokens_in   INTEGER DEFAULT 0,
                tokens_out  INTEGER DEFAULT 0,
                cost        REAL DEFAULT 0,
                duration_ms INTEGER DEFAULT 0,
                status      TEXT DEFAULT 'done',
                created_at  TIMESTAMP DEFAULT CURRENT_TIMESTAMP
            )
        """)
        con.execute("""
            CREATE TABLE IF NOT EXISTS budget_rules (
                id          INTEGER PRIMARY KEY,
                name        TEXT,
                agent_id    TEXT DEFAULT '*',
                max_cost    REAL DEFAULT 1.0,
                max_tokens  INTEGER DEFAULT 100000,
                action      TEXT DEFAULT 'stop',
                enabled     INTEGER DEFAULT 1,
                created_at  TIMESTAMP DEFAULT CURRENT_TIMESTAMP
            )
        """)
        con.execute("""
            CREATE TABLE IF NOT EXISTS notifications (
                id          INTEGER PRIMARY KEY,
                type        TEXT,
                title       TEXT,
                body        TEXT,
                run_id      TEXT,
                read_at     TIMESTAMP,
                created_at  TIMESTAMP DEFAULT CURRENT_TIMESTAMP
            )
        """)
        con.commit()
    finally:
        con.close()

_ensure_traces_table()


# ── Run lifecycle ──────────────────────────────────────────────────────────────
def start_run(agent_id: str, agent_name: str, prompt: str, budget: float = 0) -> str:
    """Register a new agent run. Returns run_id."""
    run_id = f"run_{uuid.uuid4().hex[:12]}"
    _active_runs[run_id] = {
        "run_id":      run_id,
        "agent_id":    agent_id,
        "agent_name":  agent_name,
        "prompt":      prompt[:500],
        "status":      "running",
        "total_cost":  0.0,
        "total_tokens": 0,
        "step_count":  0,
        "steps":       [],
        "budget":      budget,
        "start_time":  time.time(),
        "duration_ms": 0,
    }
    _run_queues[run_id] = asyncio.Queue(maxsize=500)
    con = get_conn()
    try:
        con.execute(
            "INSERT INTO agent_traces(run_id,agent_id,agent_name,prompt) VALUES(?,?,?,?)",
            (run_id, agent_id, agent_name, prompt[:500])
        )
        con.commit()
    finally:
        con.close()
    _broadcast(run_id, {"type": "run_started", "run_id": run_id, "agent": agent_name})
    return run_id


def record_step(run_id: str, step_type: str, name: str,
                input_text: str = "", output_text: str = "",
                model: str = "", tokens_in: int = 0, tokens_out: int = 0,
                cost: float = 0.0, duration_ms: int = 0, status: str = "done"):
    """Record a step in a run's trace."""
    if run_id not in _active_runs:
        return False
    if run_id in _kill_flags:
        return False

    run    = _active_runs[run_id]
    step_no= len(run["steps"]) + 1
    step   = {
        "step_no": step_no, "step_type": step_type, "name": name,
        "input_text": input_text[:500], "output_text": output_text[:1000],
        "model": model, "tokens_in": tokens_in, "tokens_out": tokens_out,
        "cost": cost, "duration_ms": duration_ms, "status": status,
    }
    run["steps"].append(step)
    run["total_cost"]   += cost
    run["total_tokens"] += tokens_in + tokens_out
    run["step_count"]   += 1

    # Check per-run budget
    budget = run.get("budget", 0)
    if budget > 0 and run["total_cost"] >= budget:
        _kill_flags.add(run_id)
        log.warning("Budget exceeded for run %s: $%.4f >= $%.4f", run_id, run["total_cost"], budget)
        _push_notification("budget_alert", "Budget limit hit",
                           f"Run {run_id} stopped: ${run['total_cost']:.4f} ≥ ${budget:.4f}", run_id)
        return False

    # Check global budget rules
    con = get_conn()
    try:
        rules = con.execute(
            "SELECT * FROM budget_rules WHERE enabled=1 AND (agent_id=? OR agent_id='*')",
            (run.get("agent_id", ""),)
        ).fetchall()
    finally:
        con.close()

    for rule in rules:
        if run["total_cost"] >= rule["max_cost"]:
            if rule["action"] == "stop":
                _kill_flags.add(run_id)
                return False
            elif rule["action"] == "warn":
                _broadcast(run_id, {"type": "budget_warning", "rule": dict(rule), "run_id": run_id})

    # Persist step
    try:
        con = get_conn()
        try:
            con.execute(
                """INSERT INTO agent_trace_steps
                   (run_id,step_no,step_type,name,input_text,output_text,model,tokens_in,tokens_out,cost,duration_ms,status)
                   VALUES(?,?,?,?,?,?,?,?,?,?,?,?)""",
                (run_id, step_no, step_type, name, input_text[:500], output_text[:1000],
                 model, tokens_in, tokens_out, cost, duration_ms, status)
            )
            con.commit()
        finally:
            con.close()
    except Exception:
        pass

    _broadcast(run_id, {"type": "step", "run_id": run_id, "step": step})
    return run_id not in _kill_flags


def finish_run(run_id: str, status: str = "done", error: str = ""):
    """Mark a run as complete."""
    if run_id not in _active_runs:
        return
    run = _active_runs[run_id]
    run["status"]      = status
    run["duration_ms"] = round((time.time() - run["start_time"]) * 1000)
    run["error"]       = error

    con = get_conn()
    try:
        con.execute(
            """UPDATE agent_traces SET status=?,total_cost=?,total_tokens=?,
               duration_ms=?,step_count=?,error=?,updated_at=CURRENT_TIMESTAMP WHERE run_id=?""",
            (status, run["total_cost"], run["total_tokens"],
             run["duration_ms"], run["step_count"], error[:500] if error else "", run_id)
        )
        con.commit()
    finally:
        con.close()

    _broadcast(run_id, {"type": "run_complete", "run_id": run_id,
                        "status": status, "cost": run["total_cost"],
                        "tokens": run["total_tokens"], "duration_ms": run["duration_ms"]})
    _kill_flags.discard(run_id)
    _run_queues.pop(run_id, None)
    _active_runs.pop(run_id, None)

    if status == "done":
        _push_notification("run_complete",
                           f"✅ Run complete — {run['agent_name']}",
                           f"{run['step_count']} steps · ${run['total_cost']:.4f} · {run['duration_ms']}ms",
                           run_id)
    elif status == "error":
        _push_notification("error", f"❌ Run failed — {run['agent_name']}", error[:200], run_id)


def is_killed(run_id: str) -> bool:
    return run_id in _kill_flags


def _broadcast(run_id: str, event: dict):
    q = _run_queues.get(run_id)
    if q:
        try: q.put_nowait(event)
        except asyncio.QueueFull: pass

def _push_notification(notif_type: str, title: str, body: str, run_id: str = ""):
    try:
        con = get_conn()
        try:
            con.execute(
                "INSERT INTO notifications(type,title,body,run_id) VALUES(?,?,?,?)",
                (notif_type, title[:120], body[:500], run_id)
            )
            con.commit()
        finally:
            con.close()
        from .websocket import manager
        import asyncio as _aio
        try:
            loop = _aio.get_event_loop()
            if loop.is_running():
                loop.create_task(manager.broadcast({
                    "type": "notification",
                    "notif_type": notif_type,
                    "title": title, "body": body, "run_id": run_id,
                    "ts": time.time()
                }))
        except Exception:
            pass
    except Exception as e:
        log.warning("Failed to push notification: %s", e)


# ── Endpoints ──────────────────────────────────────────────────────────────────
@router.get("/runs")
def list_runs(status: str = "", limit: int = 50):
    con = get_conn()
    try:
        if status:
            rows = con.execute(
                "SELECT * FROM agent_traces WHERE status=? ORDER BY created_at DESC LIMIT ?",
                (status, min(limit, 200))
            ).fetchall()
        else:
            rows = con.execute(
                "SELECT * FROM agent_traces ORDER BY created_at DESC LIMIT ?",
                (min(limit, 200),)
            ).fetchall()
    finally:
        con.close()
    result = [dict(r) for r in rows]
    for run_id, run in list(_active_runs.items()):
        if not any(r["run_id"] == run_id for r in result):
            result.insert(0, {**run, "created_at": time.strftime("%Y-%m-%d %H:%M:%S")})
    return result


@router.get("/runs/{run_id}")
def get_run(run_id: str):
    if run_id in _active_runs:
        run = dict(_active_runs[run_id])
        return {"run": run, "steps": run.get("steps", []), "active": True}
    con = get_conn()
    try:
        run   = con.execute("SELECT * FROM agent_traces WHERE run_id=?", (run_id,)).fetchone()
        steps = con.execute(
            "SELECT * FROM agent_trace_steps WHERE run_id=? ORDER BY step_no",
            (run_id,)
        ).fetchall()
    finally:
        con.close()
    if not run:
        return {"ok": False, "error": "Run not found"}
    return {"run": dict(run), "steps": [dict(s) for s in steps], "active": False}


@router.get("/runs/{run_id}/stream")
async def stream_run(run_id: str, request: Request):
    q = _run_queues.get(run_id)
    if not q:
        async def static():
            yield f'data: {json.dumps({"type":"not_active","run_id":run_id})}\n\n'
        return StreamingResponse(static(), media_type="text/event-stream")

    async def generate():
        try:
            yield f'data: {json.dumps({"type":"connected","run_id":run_id})}\n\n'
            while True:
                if await request.is_disconnected():
                    break
                try:
                    event = await asyncio.wait_for(q.get(), timeout=10.0)
                    yield f'data: {json.dumps(event, default=str)}\n\n'
                    if event.get("type") == "run_complete":
                        break
                except asyncio.TimeoutError:
                    yield 'data: {"type":"ping"}\n\n'
        except Exception:
            pass

    return StreamingResponse(generate(), media_type="text/event-stream",
                             headers={"Cache-Control": "no-cache", "X-Accel-Buffering": "no"})


@router.post("/runs/{run_id}/kill")
async def kill_run(run_id: str, req: Request):
    _kill_flags.add(run_id)
    run = _active_runs.get(run_id)
    if run:
        finish_run(run_id, "killed", "Killed by user")
    audit_log("kill_run", run_id)
    log.warning("Run %s killed by user", run_id)
    _push_notification("system", "🛑 Run killed", f"Run {run_id} was stopped by user", run_id)
    return {"ok": True, "run_id": run_id, "status": "killed"}


@router.post("/runs/kill-all")
async def kill_all_runs():
    count = 0
    for run_id in list(_active_runs.keys()):
        if _active_runs[run_id].get("status") == "running":
            _kill_flags.add(run_id)
            finish_run(run_id, "killed", "Killed by global kill switch")
            count += 1
    audit_log("kill_all_runs", f"{count} runs stopped")
    return {"ok": True, "killed": count}


@router.get("/active")
def active_runs():
    return [run for run in _active_runs.values() if run.get("status") == "running"]


@router.get("/stats")
def control_stats():
    con = get_conn()
    try:
        total    = con.execute("SELECT COUNT(*) FROM agent_traces").fetchone()[0]
        running  = len([r for r in _active_runs.values() if r.get("status") == "running"])
        cost_row = con.execute("SELECT SUM(total_cost) as c, SUM(total_tokens) as t FROM agent_traces").fetchone()
        errors   = con.execute("SELECT COUNT(*) FROM agent_traces WHERE status='error'").fetchone()[0]
        killed   = con.execute("SELECT COUNT(*) FROM agent_traces WHERE status='killed'").fetchone()[0]
        today    = con.execute(
            "SELECT COUNT(*),SUM(total_cost) FROM agent_traces WHERE date(created_at)=date('now')"
        ).fetchone()
    finally:
        con.close()
    return {
        "total_runs":   total,
        "active_runs":  running,
        "total_cost":   round(cost_row["c"] or 0, 6),
        "total_tokens": cost_row["t"] or 0,
        "error_count":  errors,
        "killed_count": killed,
        "today_runs":   today[0] or 0,
        "today_cost":   round(today[1] or 0, 6),
        "kill_available": running > 0,
    }


# ── Budget rules ───────────────────────────────────────────────────────────────
@router.get("/budget-rules")
def list_budget_rules():
    con = get_conn()
    try:
        rows = con.execute("SELECT * FROM budget_rules ORDER BY id").fetchall()
    finally:
        con.close()
    return [dict(r) for r in rows]


@router.post("/budget-rules")
async def create_budget_rule(req: Request):
    try:
        body     = await req.json()
    except Exception:
        body     = {}
    name     = (body.get("name") or "Budget limit").strip()[:80]
    agent_id = body.get("agent_id", "*")
    max_cost = float(body.get("max_cost", 1.0))
    max_tok  = int(body.get("max_tokens", 100000))
    action   = body.get("action", "stop")
    if action not in ("stop", "warn", "notify"):
        action = "stop"
    con = get_conn()
    try:
        cur = con.execute(
            "INSERT INTO budget_rules(name,agent_id,max_cost,max_tokens,action) VALUES(?,?,?,?,?)",
            (name, agent_id, max_cost, max_tok, action)
        )
        rid = cur.lastrowid
        con.commit()
    finally:
        con.close()
    return {"ok": True, "id": rid}


@router.patch("/budget-rules/{rule_id}")
async def update_budget_rule(rule_id: int, req: Request):
    try:
        body    = await req.json()
    except Exception:
        body    = {}
    allowed = {"name","agent_id","max_cost","max_tokens","action","enabled"}
    sets, vals = [], []
    for k in allowed:
        if k in body:
            sets.append(f"{k}=?"); vals.append(body[k])
    if not sets:
        return {"ok": False}
    vals.append(rule_id)
    con = get_conn()
    try:
        con.execute(f"UPDATE budget_rules SET {', '.join(sets)} WHERE id=?", vals)
        con.commit()
    finally:
        con.close()
    return {"ok": True}


@router.delete("/budget-rules/{rule_id}")
def delete_budget_rule(rule_id: int):
    con = get_conn()
    try:
        exists = con.execute("SELECT id FROM budget_rules WHERE id=?", (rule_id,)).fetchone()
        con.execute("DELETE FROM budget_rules WHERE id=?", (rule_id,))
        con.commit()
    finally:
        con.close()
    return {"ok": True, "deleted": exists is not None}


# ── Notifications ──────────────────────────────────────────────────────────────
@router.get("/notifications")
def list_notifications(unread_only: bool = False, limit: int = 50):
    con = get_conn()
    try:
        if unread_only:
            rows = con.execute(
                "SELECT * FROM notifications WHERE read_at IS NULL ORDER BY id DESC LIMIT ?",
                (min(limit, 200),)
            ).fetchall()
        else:
            rows = con.execute(
                "SELECT * FROM notifications ORDER BY id DESC LIMIT ?",
                (min(limit, 200),)
            ).fetchall()
        unread_count = con.execute(
            "SELECT COUNT(*) FROM notifications WHERE read_at IS NULL"
        ).fetchone()[0]
    finally:
        con.close()
    return {"notifications": [dict(r) for r in rows], "unread_count": unread_count}


@router.post("/notifications/read-all")
def mark_all_read():
    con = get_conn()
    try:
        con.execute("UPDATE notifications SET read_at=CURRENT_TIMESTAMP WHERE read_at IS NULL")
        con.commit()
    finally:
        con.close()
    return {"ok": True}


@router.patch("/notifications/{notif_id}/read")
def mark_read(notif_id: int):
    con = get_conn()
    try:
        con.execute("UPDATE notifications SET read_at=CURRENT_TIMESTAMP WHERE id=?", (notif_id,))
        con.commit()
    finally:
        con.close()
    return {"ok": True}


@router.delete("/notifications")
def clear_notifications():
    con = get_conn()
    try:
        con.execute("DELETE FROM notifications WHERE read_at IS NOT NULL")
        con.commit()
    finally:
        con.close()
    return {"ok": True}


@router.get("/budget")
def budget_alias():
    """Alias for /budget-rules."""
    con = get_conn()
    try:
        rows = con.execute("SELECT * FROM budget_rules ORDER BY id").fetchall()
    except Exception:
        rows = []
    finally:
        con.close()
    return {"rules": [dict(r) for r in rows], "count": len(rows)}
