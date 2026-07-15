"""
Agentic OS — Chat Sessions Router
Persistent named chat sessions with search, export, branching, and stats.
Sessions survive page reloads, can be renamed, pinned, searched, and exported.
"""
from __future__ import annotations
import json, time, uuid
from pathlib import Path
from fastapi import APIRouter, Request
from fastapi.responses import PlainTextResponse
from ..services.memory_db import get_conn, audit_log

router = APIRouter(prefix="/api/sessions", tags=["sessions"])
ROOT   = Path(__file__).resolve().parents[2]   # /home/user/agentic-os


def _ensure_sessions_table():
    con = get_conn()
    try:
        con.executescript("""
            CREATE TABLE IF NOT EXISTS chat_sessions (
                id            TEXT PRIMARY KEY,
                name          TEXT NOT NULL,
                agent_id      TEXT DEFAULT 'brain',
                created_at    TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                updated_at    TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                message_count INTEGER DEFAULT 0,
                pinned        INTEGER DEFAULT 0,
                description   TEXT DEFAULT ''
            );
            CREATE INDEX IF NOT EXISTS idx_cs_updated ON chat_sessions(updated_at DESC);
            CREATE INDEX IF NOT EXISTS idx_cs_pinned  ON chat_sessions(pinned DESC);
        """)
        con.commit()
    finally:
        con.close()


_ensure_sessions_table()


# ── List ───────────────────────────────────────────────────────────────────────

@router.get("")
def list_sessions(limit: int = 50, q: str = "", agent_id: str = ""):
    """List all chat sessions, pinned first then most recent."""
    limit = min(max(1, int(limit)), 200)
    con = get_conn()
    try:
        where_clauses = []
        params: list  = []

        if q:
            where_clauses.append("""(s.name LIKE ? OR s.description LIKE ? OR EXISTS (
                SELECT 1 FROM chat_log c WHERE c.session_id=s.id AND c.message LIKE ?
            ))""")
            params.extend([f"%{q}%", f"%{q}%", f"%{q}%"])

        if agent_id:
            where_clauses.append("s.agent_id=?")
            params.append(agent_id)

        where_sql = ("WHERE " + " AND ".join(where_clauses)) if where_clauses else ""

        rows = con.execute(
            f"""SELECT s.id, s.name, s.agent_id, s.pinned, s.message_count,
                       s.description,
                       datetime(s.created_at,'localtime') as created_at,
                       datetime(s.updated_at,'localtime') as updated_at
                FROM chat_sessions s
                {where_sql}
                ORDER BY s.pinned DESC, s.updated_at DESC
                LIMIT ?""",
            params + [limit]
        ).fetchall()
        total = con.execute(
            f"SELECT COUNT(*) FROM chat_sessions s {where_sql}", params
        ).fetchone()[0]
    finally:
        con.close()

    return {
        "sessions": [dict(r) for r in rows],
        "count":    len(rows),
        "total":    total,
    }


# ── Single session ─────────────────────────────────────────────────────────────

@router.get("/{session_id}")
def get_session(session_id: str):
    """Get details of a single session."""
    con = get_conn()
    try:
        row = con.execute(
            """SELECT id, name, agent_id, pinned, message_count, description,
                      datetime(created_at,'localtime') as created_at,
                      datetime(updated_at,'localtime') as updated_at
               FROM chat_sessions WHERE id=?""",
            (session_id,)
        ).fetchone()
    finally:
        con.close()
    if not row:
        return {"ok": False, "error": "Session not found"}
    return {**dict(row), "ok": True}


# ── Create ─────────────────────────────────────────────────────────────────────

@router.post("")
async def create_session(req: Request):
    """Create a new named chat session."""
    try:
        try:
            body        = await req.json()
        except Exception:
            body        = {}
    except Exception:
        body        = {}
    name        = (body.get("name") or f"Chat {time.strftime('%b %d %H:%M')}").strip()[:120]
    agent_id    = (body.get("agent_id") or "brain").strip()[:64]
    sid         = (body.get("id") or str(uuid.uuid4())).strip()
    description = (body.get("description") or "").strip()[:500]

    if not name:
        return {"ok": False, "error": "name required"}

    con = get_conn()
    try:
        con.execute(
            "INSERT OR REPLACE INTO chat_sessions(id, name, agent_id, description) VALUES (?,?,?,?)",
            (sid, name, agent_id, description)
        )
        con.commit()
        audit_log("session_create", f"{sid}: {name}")
    finally:
        con.close()

    return {"ok": True, "id": sid, "name": name, "agent_id": agent_id}


# ── Update ─────────────────────────────────────────────────────────────────────

@router.patch("/{session_id}")
async def update_session(session_id: str, req: Request):
    """Rename, pin/unpin, change agent, or update description."""
    try:
        try:
            body   = await req.json()
        except Exception:
            body   = {}
    except Exception:
        body   = {}
    fields: list = []
    vals:   list = []

    if "name" in body:
        name = str(body["name"]).strip()[:120]
        if not name:
            return {"ok": False, "error": "name cannot be empty"}
        fields.append("name=?"); vals.append(name)
    if "pinned" in body:
        fields.append("pinned=?"); vals.append(int(bool(body["pinned"])))
    if "agent_id" in body:
        fields.append("agent_id=?"); vals.append(str(body["agent_id"])[:64])
    if "description" in body:
        fields.append("description=?"); vals.append(str(body["description"])[:500])

    if not fields:
        return {"ok": False, "error": "no fields to update"}

    fields.append("updated_at=CURRENT_TIMESTAMP")
    vals.append(session_id)

    con = get_conn()
    try:
        cur = con.execute(
            f"UPDATE chat_sessions SET {', '.join(fields)} WHERE id=?", vals
        )
        con.commit()
        updated = cur.rowcount > 0
    finally:
        con.close()

    if not updated:
        return {"ok": False, "error": "Session not found"}
    return {"ok": True}


# ── Delete ─────────────────────────────────────────────────────────────────────

@router.delete("/{session_id}")
def delete_session(session_id: str):
    """Delete a session and all its messages."""
    con = get_conn()
    try:
        cur = con.execute("DELETE FROM chat_sessions WHERE id=?", (session_id,))
        con.execute("DELETE FROM chat_log WHERE session_id=?", (session_id,))
        con.commit()
        deleted = cur.rowcount > 0
    finally:
        con.close()
    if not deleted:
        return {"ok": False, "error": "Session not found"}
    audit_log("session_delete", session_id)
    return {"ok": True, "deleted": session_id}


@router.delete("")
async def bulk_delete_sessions(req: Request):
    """Delete multiple sessions at once."""
    try:
        try:
            body = await req.json()
        except Exception:
            body = {}
    except Exception:
        body = {}
    ids  = body.get("ids", [])
    if not isinstance(ids, list):
        return {"ok": False, "error": "ids list required"}
    if not ids:
        # Clear all sessions
        con = get_conn()
        try:
            deleted = con.execute("SELECT COUNT(*) FROM chat_sessions").fetchone()[0]
            con.execute("DELETE FROM chat_log")
            con.execute("DELETE FROM chat_sessions")
            con.commit()
        finally:
            con.close()
        audit_log("session_clear_all", f"{deleted} sessions cleared")
        return {"ok": True, "deleted": deleted}
    ids = [str(i) for i in ids if i][:50]
    con = get_conn()
    try:
        deleted = 0
        for sid in ids:
            cur = con.execute("DELETE FROM chat_sessions WHERE id=?", (sid,))
            con.execute("DELETE FROM chat_log WHERE session_id=?", (sid,))
            deleted += cur.rowcount
        con.commit()
    finally:
        con.close()
    audit_log("session_bulk_delete", f"{deleted} sessions")
    return {"ok": True, "deleted": deleted}


# ── Messages ───────────────────────────────────────────────────────────────────

@router.get("/{session_id}/messages")
def session_messages(session_id: str, limit: int = 200, offset: int = 0):
    """Get messages for a session with pagination."""
    limit  = min(max(1, int(limit)), 1000)
    offset = max(0, int(offset))
    con = get_conn()
    try:
        # Verify session exists
        exists = con.execute(
            "SELECT id FROM chat_sessions WHERE id=?", (session_id,)
        ).fetchone()
        if not exists:
            return {"ok": False, "error": "Session not found"}

        rows  = con.execute(
            """SELECT id, agent, role, message, tokens, cost,
                      datetime(created_at,'localtime') as created_at
               FROM chat_log WHERE session_id=? ORDER BY id ASC LIMIT ? OFFSET ?""",
            (session_id, limit, offset)
        ).fetchall()
        total = con.execute(
            "SELECT COUNT(*) FROM chat_log WHERE session_id=?", (session_id,)
        ).fetchone()[0]
    finally:
        con.close()

    return {
        "messages": [dict(r) for r in rows],
        "count":    len(rows),
        "total":    total,
        "offset":   offset,
    }


# ── Export ─────────────────────────────────────────────────────────────────────

@router.get("/{session_id}/export")
def export_session(session_id: str, fmt: str = "markdown"):
    """Export a session as Markdown or JSON."""
    con = get_conn()
    try:
        info = con.execute(
            "SELECT * FROM chat_sessions WHERE id=?", (session_id,)
        ).fetchone()
        if not info:
            return {"ok": False, "error": "Session not found"}

        msgs = con.execute(
            """SELECT agent, role, message,
                      datetime(created_at,'localtime') as ts
               FROM chat_log WHERE session_id=? ORDER BY id ASC""",
            (session_id,)
        ).fetchall()
    finally:
        con.close()

    info_dict = dict(info)
    name      = info_dict.get("name", "Chat")

    if fmt == "json":
        return {"session": info_dict, "messages": [dict(m) for m in msgs]}

    # Markdown export
    lines = [
        f"# {name}",
        f"*Agent: {info_dict.get('agent_id','?')} · Exported from Agentic OS — {time.strftime('%Y-%m-%d')}*",
        f"*Messages: {len(msgs)}*",
        "",
        "---",
        "",
    ]
    for m in msgs:
        d    = dict(m)
        role = "**You**" if d["role"] == "user" else f"**{d['agent'].title() if d['agent'] else 'Agent'}**"
        lines.append(f"### {role} — {d['ts']}")
        lines.append(d["message"] or "")
        lines.append("")

    md = "\n".join(lines)
    return PlainTextResponse(md, media_type="text/markdown; charset=utf-8",
                             headers={"Content-Disposition": f'attachment; filename="{name[:40]}.md"'})


# ── Branch ─────────────────────────────────────────────────────────────────────

@router.post("/{session_id}/branch")
async def branch_session(session_id: str, req: Request):
    """Fork a session at a given message ID — create a new conversation branch."""
    try:
        body         = await req.json()
    except Exception:
        body         = {}
    branch_from  = body.get("from_message_id")  # inclusive cutoff
    new_name     = (body.get("name") or "Branched conversation").strip()[:120]

    con = get_conn()
    try:
        # Verify source session exists
        parent = con.execute(
            "SELECT name, agent_id FROM chat_sessions WHERE id=?", (session_id,)
        ).fetchone()
        if not parent:
            return {"ok": False, "error": "Source session not found"}

        # Get messages up to the fork point
        if branch_from:
            msgs = con.execute(
                """SELECT agent, role, message FROM chat_log
                   WHERE session_id=? AND id<=? ORDER BY id ASC""",
                (session_id, branch_from)
            ).fetchall()
        else:
            msgs = con.execute(
                "SELECT agent, role, message FROM chat_log WHERE session_id=? ORDER BY id ASC",
                (session_id,)
            ).fetchall()

        new_sid  = str(uuid.uuid4())
        agent_id = dict(parent).get("agent_id", "brain")
        description = f"Branched from '{dict(parent).get('name','?')}'"

        con.execute(
            "INSERT INTO chat_sessions(id, name, agent_id, description) VALUES (?,?,?,?)",
            (new_sid, new_name, agent_id, description)
        )
        for m in msgs:
            con.execute(
                "INSERT INTO chat_log(session_id, agent, role, message) VALUES (?,?,?,?)",
                (new_sid, m["agent"], m["role"], m["message"])
            )
        con.execute(
            "UPDATE chat_sessions SET message_count=? WHERE id=?", (len(msgs), new_sid)
        )
        con.commit()
        audit_log("session_branch", f"{session_id} → {new_sid}")
    finally:
        con.close()

    return {
        "ok":             True,
        "id":             new_sid,   # standard id field
        "new_session_id": new_sid,
        "name":           new_name,
        "agent_id":       agent_id,
        "messages_copied": len(msgs),
        "branched_from":  session_id,
    }


# ── Touch ──────────────────────────────────────────────────────────────────────

@router.post("/{session_id}/touch")
def touch_session(session_id: str):
    """Update session timestamp and message count (called after each message)."""
    con = get_conn()
    try:
        existing = con.execute(
            "SELECT id FROM chat_sessions WHERE id=?", (session_id,)
        ).fetchone()
        count = con.execute(
            "SELECT COUNT(*) FROM chat_log WHERE session_id=?", (session_id,)
        ).fetchone()[0]

        if existing:
            con.execute(
                "UPDATE chat_sessions SET updated_at=CURRENT_TIMESTAMP, message_count=? WHERE id=?",
                (count, session_id)
            )
        else:
            con.execute(
                "INSERT INTO chat_sessions(id, name, message_count) VALUES (?,?,?)",
                (session_id, f"Chat {time.strftime('%b %d %H:%M')}", count)
            )
        con.commit()
    finally:
        con.close()
    return {"ok": True, "message_count": count}


# ── Stats ──────────────────────────────────────────────────────────────────────

@router.get("/stats/overview")
def sessions_stats():
    """Return aggregate stats: total sessions, messages, cost."""
    con = get_conn()
    try:
        total_sessions = con.execute("SELECT COUNT(*) FROM chat_sessions").fetchone()[0]
        total_messages = con.execute("SELECT COUNT(*) FROM chat_log").fetchone()[0]
        total_cost     = con.execute(
            "SELECT COALESCE(SUM(cost),0) FROM chat_log"
        ).fetchone()[0] or 0.0
        total_tokens   = con.execute(
            "SELECT COALESCE(SUM(tokens),0) FROM chat_log"
        ).fetchone()[0] or 0
        pinned_count   = con.execute(
            "SELECT COUNT(*) FROM chat_sessions WHERE pinned=1"
        ).fetchone()[0]
        active_today   = con.execute(
            "SELECT COUNT(DISTINCT session_id) FROM chat_log WHERE date(created_at)=date('now')"
        ).fetchone()[0]
        by_agent       = con.execute(
            """SELECT agent_id, COUNT(*) as count FROM chat_sessions
               GROUP BY agent_id ORDER BY count DESC"""
        ).fetchall()
    finally:
        con.close()

    return {
        "total_sessions": total_sessions,
        "total_messages": total_messages,
        "total_cost":     round(float(total_cost), 6),
        "total_tokens":   int(total_tokens),
        "pinned_count":   pinned_count,
        "active_today":   active_today,
        "by_agent":       [dict(r) for r in by_agent],
    }
