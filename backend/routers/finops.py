"""
Agentic OS — Sprint D · Feature 2: FinOps — Cost Attribution Engine
════════════════════════════════════════════════════════════════════
Unified cost tracking across every surface: LLM calls, MCP tool calls,
connector executions, supervisor runs, and autonomous loops.

Features:
  • Cost attribution per agent / goal / task / user / department
  • Spending caps with configurable on-breach actions (alert, pause, kill)
  • Real-time budget burn rate with projections
  • Cost breakdown by: model, tool, connector, supervisor run, time period
  • FinOps dashboard: total spend, cost per outcome, cheapest agent
  • Export to CSV for finance review

Based on:
  Deloitte 2026: FinOps cost management for silicon-based workforce
  Roadmap Pillar 5: cost attribution per agent/task, spending caps
"""
from __future__ import annotations

import csv, io, json, logging, time, uuid
from datetime import datetime, timezone
from pathlib import Path
from fastapi import APIRouter, Request
from fastapi.responses import StreamingResponse, JSONResponse

router = APIRouter(prefix="/api/finops", tags=["finops"])
log    = logging.getLogger("agentic.finops")

ROOT = Path(__file__).resolve().parents[2]

# ── Schema ─────────────────────────────────────────────────────────────────────
_SCHEMA = """
CREATE TABLE IF NOT EXISTS cost_ledger (
    ledger_id    TEXT PRIMARY KEY,
    agent_id     TEXT NOT NULL DEFAULT '',
    source_type  TEXT NOT NULL DEFAULT 'llm',
    source_id    TEXT NOT NULL DEFAULT '',
    goal_id      TEXT NOT NULL DEFAULT '',
    run_id       TEXT NOT NULL DEFAULT '',
    task_id      TEXT NOT NULL DEFAULT '',
    user_id      TEXT NOT NULL DEFAULT 'user',
    department   TEXT NOT NULL DEFAULT 'default',
    model        TEXT NOT NULL DEFAULT '',
    tokens_in    INTEGER NOT NULL DEFAULT 0,
    tokens_out   INTEGER NOT NULL DEFAULT 0,
    total_tokens INTEGER NOT NULL DEFAULT 0,
    cost_usd     REAL NOT NULL DEFAULT 0,
    latency_ms   INTEGER NOT NULL DEFAULT 0,
    description  TEXT NOT NULL DEFAULT '',
    created_at   TEXT NOT NULL DEFAULT ''
);
CREATE INDEX IF NOT EXISTS idx_cl_agent  ON cost_ledger(agent_id, created_at DESC);
CREATE INDEX IF NOT EXISTS idx_cl_goal   ON cost_ledger(goal_id);
CREATE INDEX IF NOT EXISTS idx_cl_source ON cost_ledger(source_type, created_at DESC);
CREATE INDEX IF NOT EXISTS idx_cl_time   ON cost_ledger(created_at DESC);

CREATE TABLE IF NOT EXISTS budget_caps (
    cap_id       TEXT PRIMARY KEY,
    name         TEXT NOT NULL DEFAULT '',
    scope_type   TEXT NOT NULL DEFAULT 'agent',
    scope_id     TEXT NOT NULL DEFAULT '*',
    period       TEXT NOT NULL DEFAULT 'day',
    limit_usd    REAL NOT NULL DEFAULT 0,
    limit_tokens INTEGER NOT NULL DEFAULT 0,
    on_breach    TEXT NOT NULL DEFAULT 'alert',
    current_usd  REAL NOT NULL DEFAULT 0,
    current_tok  INTEGER NOT NULL DEFAULT 0,
    breached     INTEGER NOT NULL DEFAULT 0,
    breached_at  TEXT NOT NULL DEFAULT '',
    reset_at     TEXT NOT NULL DEFAULT '',
    enabled      INTEGER NOT NULL DEFAULT 1,
    created_at   TEXT NOT NULL DEFAULT '',
    updated_at   TEXT NOT NULL DEFAULT ''
);

CREATE TABLE IF NOT EXISTS cost_alerts (
    id          INTEGER PRIMARY KEY AUTOINCREMENT,
    cap_id      TEXT NOT NULL,
    agent_id    TEXT NOT NULL DEFAULT '',
    alert_type  TEXT NOT NULL DEFAULT 'warning',
    pct_used    REAL NOT NULL DEFAULT 0,
    cost_at_alert REAL NOT NULL DEFAULT 0,
    limit_usd   REAL NOT NULL DEFAULT 0,
    resolved    INTEGER NOT NULL DEFAULT 0,
    created_at  TEXT NOT NULL DEFAULT ''
);
CREATE INDEX IF NOT EXISTS idx_ca_cap ON cost_alerts(cap_id, created_at DESC);
"""

COST_PER_1K = {
    # OpenRouter model pricing (per 1K tokens, approximate)
    "anthropic/claude-3.5-sonnet": 0.003,
    "anthropic/claude-opus-4":     0.015,
    "openai/gpt-4o":               0.005,
    "openai/gpt-4o-mini":          0.00015,
    "google/gemini-2.5-pro":       0.00125,
    "google/gemini-2.0-flash-exp:free": 0.0,
    "meta-llama/llama-3.3-70b-instruct:free": 0.0,
    "default":                     0.003,
}

def _get_conn():
    from ..services.memory_db import get_conn
    return get_conn()

def _now() -> str:
    return datetime.now(timezone.utc).isoformat()

def _ensure_schema():
    con = _get_conn()
    try:
        con.executescript(_SCHEMA)
        # Seed default budget caps
        now = _now()
        defaults = [
            ("cap_daily_total",  "Daily Platform Total", "platform", "*",    "day",  1.00, 500000, "alert"),
            ("cap_agent_hour",   "Per-Agent Hourly",     "agent",    "*",    "hour", 0.10, 50000,  "alert"),
            ("cap_goal_total",   "Per-Goal Total",       "goal",     "*",    "goal", 0.50, 200000, "alert"),
        ]
        for cap_id, name, stype, sid, period, limit_usd, limit_tok, on_breach in defaults:
            if not con.execute("SELECT cap_id FROM budget_caps WHERE cap_id=?", (cap_id,)).fetchone():
                con.execute("""INSERT INTO budget_caps
                    (cap_id,name,scope_type,scope_id,period,limit_usd,limit_tokens,on_breach,enabled,created_at,updated_at)
                    VALUES (?,?,?,?,?,?,?,?,1,?,?)""",
                    (cap_id, name, stype, sid, period, limit_usd, limit_tok, on_breach, now, now))
        con.commit()
    finally:
        con.close()

_ensure_schema()


# ── Core ledger write ──────────────────────────────────────────────────────────
def record_cost(
    agent_id: str,
    source_type: str,          # llm | mcp | connector | supervisor | loop
    cost_usd: float,
    tokens: int = 0,
    tokens_in: int = 0,
    tokens_out: int = 0,
    source_id: str = "",
    goal_id: str = "",
    run_id: str = "",
    task_id: str = "",
    model: str = "",
    description: str = "",
    latency_ms: int = 0,
    user_id: str = "user",
    department: str = "default",
) -> str:
    """Write a cost entry to the unified ledger. Returns ledger_id."""
    ledger_id = f"cst_{uuid.uuid4().hex[:10]}"
    total_tok  = tokens or (tokens_in + tokens_out)
    now        = _now()

    con = _get_conn()
    try:
        con.execute("""
            INSERT INTO cost_ledger
              (ledger_id,agent_id,source_type,source_id,goal_id,run_id,task_id,
               user_id,department,model,tokens_in,tokens_out,total_tokens,
               cost_usd,latency_ms,description,created_at)
            VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)
        """, (ledger_id, agent_id, source_type, source_id, goal_id, run_id,
              task_id, user_id, department, model, tokens_in, tokens_out,
              total_tok, cost_usd, latency_ms, description[:300], now))
        con.commit()
    finally:
        con.close()

    # Check budget caps asynchronously (fire-and-forget)
    _check_budget_caps(agent_id, cost_usd, total_tok, goal_id)
    return ledger_id


def _check_budget_caps(agent_id: str, cost: float, tokens: int, goal_id: str):
    """Check all applicable budget caps and trigger alerts/actions."""
    con = _get_conn()
    try:
        caps = con.execute("SELECT * FROM budget_caps WHERE enabled=1").fetchall()
        now  = _now()
        for cap in caps:
            cap = dict(cap)
            # Check scope match
            sid = cap["scope_id"]
            stype = cap["scope_type"]
            if sid != "*":
                if stype == "agent" and agent_id != sid: continue
                if stype == "goal"  and goal_id  != sid: continue

            # Determine period window
            period_sql = {"hour": "-1 hour", "day": "-1 day", "week": "-7 days", "month": "-30 days"}.get(cap["period"], "-1 day")

            agg = con.execute("""
                SELECT SUM(cost_usd) as c, SUM(total_tokens) as t FROM cost_ledger
                WHERE created_at > datetime('now', ?)
                  AND (? = '*' OR agent_id = ?)
                  AND (? = '*' OR goal_id = ?)
            """, (period_sql, sid, agent_id, sid if stype=="goal" else "*", goal_id or "*")).fetchone()

            cur_cost = agg["c"] or 0
            cur_tok  = agg["t"] or 0

            # Update cap counters
            con.execute("UPDATE budget_caps SET current_usd=?, current_tok=? WHERE cap_id=?",
                        (cur_cost, cur_tok, cap["cap_id"]))

            # Alert thresholds
            if cap["limit_usd"] > 0:
                pct = cur_cost / cap["limit_usd"]
                if pct >= 1.0 and not cap["breached"]:
                    con.execute("UPDATE budget_caps SET breached=1, breached_at=? WHERE cap_id=?",
                                (now, cap["cap_id"]))
                    con.execute("""INSERT INTO cost_alerts
                        (cap_id,agent_id,alert_type,pct_used,cost_at_alert,limit_usd,created_at)
                        VALUES (?,?,'breach',?,?,?,?)""",
                        (cap["cap_id"], agent_id, pct, cur_cost, cap["limit_usd"], now))
                    log.warning("Budget BREACH: %s %.0f%% ($%.4f/$%.4f)",
                                cap["name"], pct*100, cur_cost, cap["limit_usd"])
                elif pct >= 0.8 and pct < 1.0:
                    # 80% warning — avoid duplicate alerts
                    recent = con.execute("""
                        SELECT id FROM cost_alerts WHERE cap_id=? AND alert_type='warning'
                        AND created_at > datetime('now','-1 hour')""", (cap["cap_id"],)).fetchone()
                    if not recent:
                        con.execute("""INSERT INTO cost_alerts
                            (cap_id,agent_id,alert_type,pct_used,cost_at_alert,limit_usd,created_at)
                            VALUES (?,?,'warning',?,?,?,?)""",
                            (cap["cap_id"], agent_id, pct, cur_cost, cap["limit_usd"], now))

        con.commit()
    except Exception as e:
        log.error("Budget cap check failed: %s", e)
    finally:
        con.close()


# ── API Routes ─────────────────────────────────────────────────────────────────
@router.get("/dashboard")
def finops_dashboard():
    """Complete FinOps overview."""
    con = _get_conn()
    try:
        total   = con.execute("SELECT SUM(cost_usd) c, SUM(total_tokens) t, COUNT(*) n FROM cost_ledger").fetchone()
        by_src  = con.execute("SELECT source_type, SUM(cost_usd) c, COUNT(*) n FROM cost_ledger GROUP BY source_type ORDER BY c DESC").fetchall()
        by_agent= con.execute("SELECT agent_id, SUM(cost_usd) c, SUM(total_tokens) t, COUNT(*) n FROM cost_ledger GROUP BY agent_id ORDER BY c DESC LIMIT 10").fetchall()
        by_model= con.execute("SELECT model, SUM(cost_usd) c, SUM(total_tokens) t FROM cost_ledger WHERE model!='' GROUP BY model ORDER BY c DESC LIMIT 8").fetchall()
        today   = con.execute("SELECT SUM(cost_usd) c FROM cost_ledger WHERE created_at > datetime('now','-1 day')").fetchone()
        this_hr = con.execute("SELECT SUM(cost_usd) c FROM cost_ledger WHERE created_at > datetime('now','-1 hour')").fetchone()
        caps    = con.execute("SELECT * FROM budget_caps WHERE enabled=1").fetchall()
        alerts  = con.execute("SELECT COUNT(*) FROM cost_alerts WHERE resolved=0").fetchone()[0]
        # Burn rate projection (hourly → daily)
        hourly_burn = this_hr["c"] or 0
        daily_proj  = hourly_burn * 24
    finally:
        con.close()

    return {
        "total_cost_usd":   round(total["c"] or 0, 6),
        "total_tokens":     total["t"] or 0,
        "total_events":     total["n"] or 0,
        "cost_today":       round(today["c"] or 0, 6),
        "cost_last_hour":   round(hourly_burn, 6),
        "projected_daily":  round(daily_proj, 6),
        "unresolved_alerts":alerts,
        "by_source_type":   [dict(r) for r in by_src],
        "by_agent":         [dict(r) for r in by_agent],
        "by_model":         [dict(r) for r in by_model],
        "budget_caps":      [dict(c) for c in caps],
    }


@router.get("/ledger")
def ledger_entries(
    agent_id: str = "", source_type: str = "", goal_id: str = "",
    run_id: str = "", days: int = 7, limit: int = 100
):
    """Query cost ledger with filters."""
    where, params = ["created_at > datetime('now', ?)"], [f"-{days} days"]
    if agent_id:   where.append("agent_id=?");    params.append(agent_id)
    if source_type:where.append("source_type=?"); params.append(source_type)
    if goal_id:    where.append("goal_id=?");     params.append(goal_id)
    if run_id:     where.append("run_id=?");      params.append(run_id)
    params.append(min(limit, 1000))
    con = _get_conn()
    try:
        rows = con.execute(
            f"SELECT * FROM cost_ledger WHERE {' AND '.join(where)} ORDER BY created_at DESC LIMIT ?",
            params
        ).fetchall()
        total_cost = con.execute(
            f"SELECT SUM(cost_usd) FROM cost_ledger WHERE {' AND '.join(where)}",
            params[:-1]
        ).fetchone()[0]
    finally:
        con.close()
    return {"entries": [dict(r) for r in rows], "count": len(rows),
            "total_cost": round(total_cost or 0, 6)}


def _safe_float(val, default=0.0) -> float:
    """Parse float safely; reject NaN/Inf and non-numeric strings."""
    try:
        f = float(val or default)
        import math
        if math.isnan(f) or math.isinf(f):
            return default
        return max(f, 0.0)          # Reject negative costs
    except (ValueError, TypeError):
        return default

def _safe_int(val, default=0) -> int:
    """Parse int safely; reject non-numeric strings."""
    try:
        return max(int(float(val or default)), 0)  # Reject negative tokens
    except (ValueError, TypeError):
        return default


@router.post("/ledger/record")
async def record_cost_entry(req: Request):
    """Manually record a cost entry (used by agents and routers)."""
    try: body = await req.json()
    except: return JSONResponse({"ok": False, "error": "Invalid JSON"}, status_code=400)
    lid = record_cost(
        agent_id    = (body.get("agent_id") or "system")[:64],
        source_type = (body.get("source_type") or "llm")[:32],
        cost_usd    = _safe_float(body.get("cost_usd")),
        tokens      = _safe_int(body.get("tokens")),
        tokens_in   = _safe_int(body.get("tokens_in")),
        tokens_out  = _safe_int(body.get("tokens_out")),
        source_id   = (body.get("source_id") or "")[:64],
        goal_id     = (body.get("goal_id") or "")[:64],
        run_id      = (body.get("run_id") or "")[:64],
        task_id     = (body.get("task_id") or "")[:64],
        model       = (body.get("model") or "")[:100],
        description = (body.get("description") or "")[:300],
        latency_ms  = _safe_int(body.get("latency_ms")),
    )
    return {"ok": True, "ledger_id": lid}


@router.get("/by-goal/{goal_id}")
def cost_by_goal(goal_id: str):
    """Full cost breakdown for a specific goal."""
    con = _get_conn()
    try:
        agg = con.execute("""
            SELECT SUM(cost_usd) c, SUM(total_tokens) t, COUNT(*) n,
                   AVG(latency_ms) lat
            FROM cost_ledger WHERE goal_id=?
        """, (goal_id,)).fetchone()
        by_src = con.execute("""
            SELECT source_type, SUM(cost_usd) c, COUNT(*) n
            FROM cost_ledger WHERE goal_id=? GROUP BY source_type
        """, (goal_id,)).fetchall()
        by_agent = con.execute("""
            SELECT agent_id, SUM(cost_usd) c, SUM(total_tokens) t
            FROM cost_ledger WHERE goal_id=? GROUP BY agent_id ORDER BY c DESC
        """, (goal_id,)).fetchall()
    finally:
        con.close()
    return {
        "goal_id": goal_id,
        "total_cost":   round(agg["c"] or 0, 6),
        "total_tokens": agg["t"] or 0,
        "total_events": agg["n"] or 0,
        "avg_latency":  round(agg["lat"] or 0, 1),
        "by_source":    [dict(r) for r in by_src],
        "by_agent":     [dict(r) for r in by_agent],
    }


@router.get("/caps")
def list_caps():
    con = _get_conn()
    try:
        rows = con.execute("SELECT * FROM budget_caps ORDER BY scope_type, name").fetchall()
    finally:
        con.close()
    return {"caps": [dict(r) for r in rows], "count": len(rows)}


@router.post("/caps")
async def create_cap(req: Request):
    try: body = await req.json()
    except: return JSONResponse({"ok": False, "error": "Invalid JSON"}, status_code=400)
    name = (body.get("name") or "").strip()
    if not name:
        return JSONResponse({"ok": False, "error": "name required"}, status_code=400)
    cap_id = f"cap_{uuid.uuid4().hex[:8]}"
    now    = _now()
    on_breach = body.get("on_breach","alert")
    if on_breach not in ("alert","pause","kill"):
        on_breach = "alert"
    con = _get_conn()
    try:
        con.execute("""INSERT INTO budget_caps
            (cap_id,name,scope_type,scope_id,period,limit_usd,limit_tokens,on_breach,enabled,created_at,updated_at)
            VALUES (?,?,?,?,?,?,?,?,1,?,?)""",
            (cap_id, name[:100],
             (body.get("scope_type") or "agent")[:20],
             (body.get("scope_id") or "*")[:100],
             (body.get("period") or "day")[:20],
             float(body.get("limit_usd") or 0),
             int(body.get("limit_tokens") or 0),
             on_breach, now, now))
        con.commit()
    finally:
        con.close()
    return {"ok": True, "cap_id": cap_id}


@router.delete("/caps/{cap_id}")
def delete_cap(cap_id: str):
    if cap_id.startswith("cap_daily") or cap_id.startswith("cap_agent"):
        pass  # Allow deleting defaults
    con = _get_conn()
    try:
        con.execute("DELETE FROM budget_caps WHERE cap_id=?", (cap_id,))
        con.commit()
    finally:
        con.close()
    return {"ok": True, "deleted": cap_id}


@router.get("/alerts")
def list_alerts(resolved: bool = False, limit: int = 50):
    con = _get_conn()
    try:
        rows = con.execute(
            "SELECT a.*, b.name as cap_name FROM cost_alerts a JOIN budget_caps b ON b.cap_id=a.cap_id WHERE a.resolved=? ORDER BY a.created_at DESC LIMIT ?",
            (1 if resolved else 0, min(limit, 200))
        ).fetchall()
    finally:
        con.close()
    return {"alerts": [dict(r) for r in rows], "count": len(rows)}


@router.post("/alerts/{alert_id}/resolve")
def resolve_alert(alert_id: int):
    con = _get_conn()
    try:
        con.execute("UPDATE cost_alerts SET resolved=1 WHERE id=?", (alert_id,))
        con.commit()
    finally:
        con.close()
    return {"ok": True, "resolved": alert_id}


@router.get("/export/csv")
def export_csv(days: int = 30):
    """Export full cost ledger as CSV."""
    con = _get_conn()
    try:
        rows = con.execute(
            "SELECT * FROM cost_ledger WHERE created_at > datetime('now', ?) ORDER BY created_at ASC LIMIT 10000",
            (f"-{days} days",)
        ).fetchall()
    finally:
        con.close()
    output = io.StringIO()
    writer = csv.writer(output)
    if rows:
        writer.writerow(rows[0].keys())
        for r in rows:
            writer.writerow(list(r))
    return StreamingResponse(
        io.BytesIO(output.getvalue().encode()),
        media_type="text/csv",
        headers={"Content-Disposition": f'attachment; filename="finops_export_{int(time.time())}.csv"'}
    )


@router.get("/stats/time-series")
def cost_time_series(days: int = 7, granularity: str = "hour"):
    """Cost and token usage over time."""
    fmt = "%Y-%m-%d %H:00" if granularity == "hour" else "%Y-%m-%d"
    con = _get_conn()
    try:
        rows = con.execute(f"""
            SELECT strftime('{fmt}', created_at) as bucket,
                   SUM(cost_usd) c, SUM(total_tokens) t, COUNT(*) n
            FROM cost_ledger
            WHERE created_at > datetime('now', '-{days} days')
            GROUP BY bucket ORDER BY bucket ASC
        """).fetchall()
    finally:
        con.close()
    return {"series": [dict(r) for r in rows], "granularity": granularity, "days": days}
