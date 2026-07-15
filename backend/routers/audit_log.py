"""
Agentic OS — Sprint A · Feature 1: Immutable Audit Log
═══════════════════════════════════════════════════════
Append-only, SHA-256 hash-chained decision receipts for every agent action.

Architecture:
  • Every agent action writes a signed receipt: agent_id, action, reasoning,
    authority context, timestamp, and SHA-256 of the previous record.
  • The chain can be verified at any time — tampering breaks the hash sequence.
  • Exports to JSON/CSV for compliance and regulatory review.
  • No UPDATE or DELETE is ever issued against audit_log_chain.

Tables:
  audit_log_chain   — the immutable ledger
  audit_receipts    — cryptographically signed per-action receipts
"""
from __future__ import annotations
import hashlib, hmac, json, time, uuid, csv, io, logging
from datetime import datetime, timezone
from pathlib import Path
from fastapi import APIRouter, Request
from fastapi.responses import StreamingResponse, JSONResponse

router = APIRouter(prefix="/api/audit-log", tags=["audit-log"])
log    = logging.getLogger("agentic.audit_log")

ROOT = Path(__file__).resolve().parents[2]

# ── Schema ─────────────────────────────────────────────────────────────────────
_SCHEMA = """
CREATE TABLE IF NOT EXISTS audit_log_chain (
    seq          INTEGER PRIMARY KEY AUTOINCREMENT,
    entry_id     TEXT    NOT NULL UNIQUE,
    agent_id     TEXT    NOT NULL DEFAULT '',
    agent_name   TEXT    NOT NULL DEFAULT '',
    action_type  TEXT    NOT NULL DEFAULT '',
    action_detail TEXT   NOT NULL DEFAULT '',
    reasoning    TEXT    NOT NULL DEFAULT '',
    authority    TEXT    NOT NULL DEFAULT 'user',
    risk_level   TEXT    NOT NULL DEFAULT 'low',
    outcome      TEXT    NOT NULL DEFAULT 'success',
    metadata     TEXT    NOT NULL DEFAULT '{}',
    prev_hash    TEXT    NOT NULL DEFAULT '',
    entry_hash   TEXT    NOT NULL DEFAULT '',
    created_at   TEXT    NOT NULL DEFAULT '',
    epoch_ms     INTEGER NOT NULL DEFAULT 0
);
CREATE INDEX IF NOT EXISTS idx_alc_agent  ON audit_log_chain(agent_id);
CREATE INDEX IF NOT EXISTS idx_alc_action ON audit_log_chain(action_type);
CREATE INDEX IF NOT EXISTS idx_alc_time   ON audit_log_chain(epoch_ms DESC);

CREATE TABLE IF NOT EXISTS audit_receipts (
    receipt_id   TEXT PRIMARY KEY,
    entry_id     TEXT NOT NULL,
    agent_id     TEXT NOT NULL,
    signature    TEXT NOT NULL,
    public_key   TEXT NOT NULL DEFAULT '',
    issued_at    TEXT NOT NULL,
    FOREIGN KEY (entry_id) REFERENCES audit_log_chain(entry_id)
);
CREATE INDEX IF NOT EXISTS idx_ar_agent ON audit_receipts(agent_id);
"""

def _get_conn():
    from ..services.memory_db import get_conn
    return get_conn()

def _ensure_schema():
    con = _get_conn()
    try:
        con.executescript(_SCHEMA)
        con.commit()
    finally:
        con.close()

_ensure_schema()


# ── Core chain logic ───────────────────────────────────────────────────────────
def _sha256(text: str) -> str:
    return hashlib.sha256(text.encode("utf-8")).hexdigest()

def _get_chain_tip() -> tuple[int, str]:
    """Return (last_seq, last_hash). Returns (0, genesis_hash) if chain is empty."""
    con = _get_conn()
    try:
        row = con.execute(
            "SELECT seq, entry_hash FROM audit_log_chain ORDER BY seq DESC LIMIT 1"
        ).fetchone()
    finally:
        con.close()
    if row:
        return row["seq"], row["entry_hash"]
    # Genesis block: hash of a fixed string
    genesis = _sha256("AGENTIC_OS_AUDIT_CHAIN_GENESIS_v1")
    return 0, genesis

def _compute_entry_hash(entry_id: str, agent_id: str, action_type: str,
                         action_detail: str, reasoning: str, authority: str,
                         risk_level: str, outcome: str, prev_hash: str,
                         epoch_ms: int) -> str:
    """Deterministic hash of all critical fields + prev_hash."""
    payload = "|".join([
        entry_id, agent_id, action_type, action_detail[:500],
        reasoning[:500], authority, risk_level, outcome,
        prev_hash, str(epoch_ms)
    ])
    return _sha256(payload)

def append_entry(
    agent_id: str,
    agent_name: str,
    action_type: str,
    action_detail: str,
    reasoning: str = "",
    authority: str = "user",
    risk_level: str = "low",
    outcome: str = "success",
    metadata: dict | None = None,
) -> dict:
    """
    Append a new entry to the immutable audit chain.
    Returns the full entry including hash and receipt_id.
    Callable from any router: from .audit_log import append_entry
    """
    entry_id  = f"al_{uuid.uuid4().hex}"
    epoch_ms  = int(time.time() * 1000)
    created_at = datetime.now(timezone.utc).isoformat()
    meta_str  = json.dumps(metadata or {}, default=str)

    _, prev_hash = _get_chain_tip()

    entry_hash = _compute_entry_hash(
        entry_id, agent_id, action_type, action_detail,
        reasoning, authority, risk_level, outcome, prev_hash, epoch_ms
    )

    con = _get_conn()
    try:
        con.execute("""
            INSERT INTO audit_log_chain
              (entry_id,agent_id,agent_name,action_type,action_detail,
               reasoning,authority,risk_level,outcome,metadata,
               prev_hash,entry_hash,created_at,epoch_ms)
            VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?,?)
        """, (
            entry_id, agent_id, agent_name, action_type,
            action_detail[:2000], reasoning[:1000], authority,
            risk_level, outcome, meta_str[:4000],
            prev_hash, entry_hash, created_at, epoch_ms
        ))

        # Issue a signed receipt using agent's keypair if available
        receipt_id = _issue_receipt(con, entry_id, agent_id, entry_hash)
        con.commit()
    finally:
        con.close()

    log.info("AUDIT CHAIN +%s | %s | %s | %s", entry_id[:12], agent_id, action_type, outcome)

    return {
        "entry_id":    entry_id,
        "receipt_id":  receipt_id,
        "entry_hash":  entry_hash,
        "prev_hash":   prev_hash,
        "agent_id":    agent_id,
        "action_type": action_type,
        "outcome":     outcome,
        "epoch_ms":    epoch_ms,
    }

def _issue_receipt(con, entry_id: str, agent_id: str, entry_hash: str) -> str:
    """Sign the entry hash with the agent's stored signing key."""
    receipt_id = f"rcpt_{uuid.uuid4().hex[:12]}"
    issued_at  = datetime.now(timezone.utc).isoformat()

    # Fetch agent's public key (may be empty if identity not provisioned yet)
    pub_key = ""
    sig     = ""
    try:
        row = con.execute(
            "SELECT public_key, signing_key FROM agent_identities WHERE agent_id=?",
            (agent_id,)
        ).fetchone()
        if row and row["signing_key"]:
            # HMAC-SHA256 signature using the stored signing key
            sig = hmac.new(
                row["signing_key"].encode("utf-8"),
                entry_hash.encode("utf-8"),
                hashlib.sha256
            ).hexdigest()
            pub_key = row["public_key"] or ""
    except Exception:
        pass  # identity not provisioned — receipt still issued, just unsigned

    con.execute("""
        INSERT OR IGNORE INTO audit_receipts
          (receipt_id, entry_id, agent_id, signature, public_key, issued_at)
        VALUES (?,?,?,?,?,?)
    """, (receipt_id, entry_id, agent_id, sig, pub_key, issued_at))

    return receipt_id


# ── Verification ───────────────────────────────────────────────────────────────
def verify_chain() -> dict:
    """Walk the entire chain and verify every hash link."""
    con = _get_conn()
    try:
        rows = con.execute(
            "SELECT * FROM audit_log_chain ORDER BY seq ASC"
        ).fetchall()
    finally:
        con.close()

    if not rows:
        return {"ok": True, "verified": 0, "broken_at": None, "message": "Chain is empty"}

    genesis_hash = _sha256("AGENTIC_OS_AUDIT_CHAIN_GENESIS_v1")
    expected_prev = genesis_hash
    broken_at = None

    for row in rows:
        r = dict(row)
        # Check prev_hash linkage
        if r["prev_hash"] != expected_prev:
            broken_at = r["seq"]
            break

        # Recompute entry_hash
        recomputed = _compute_entry_hash(
            r["entry_id"], r["agent_id"], r["action_type"],
            r["action_detail"][:500], r["reasoning"][:500],
            r["authority"], r["risk_level"], r["outcome"],
            r["prev_hash"], r["epoch_ms"]
        )
        if recomputed != r["entry_hash"]:
            broken_at = r["seq"]
            break

        expected_prev = r["entry_hash"]

    return {
        "ok":       broken_at is None,
        "verified": len(rows),
        "broken_at": broken_at,
        "chain_tip": rows[-1]["entry_hash"] if rows else genesis_hash,
        "total_entries": len(rows),
        "message":  "Chain integrity verified ✅" if broken_at is None else f"⚠️ Chain broken at seq={broken_at}",
    }


# ── API Routes ─────────────────────────────────────────────────────────────────
@router.get("")
def list_entries(
    agent_id: str = "",
    action_type: str = "",
    risk_level: str = "",
    outcome: str = "",
    limit: int = 100,
    offset: int = 0,
):
    """List audit log entries with optional filters."""
    where_clauses = []
    params: list = []

    if agent_id:
        where_clauses.append("agent_id = ?")
        params.append(agent_id)
    if action_type:
        where_clauses.append("action_type = ?")
        params.append(action_type)
    if risk_level:
        where_clauses.append("risk_level = ?")
        params.append(risk_level)
    if outcome:
        where_clauses.append("outcome = ?")
        params.append(outcome)

    where_sql = ("WHERE " + " AND ".join(where_clauses)) if where_clauses else ""
    params += [min(limit, 500), max(offset, 0)]

    con = _get_conn()
    try:
        rows = con.execute(
            f"SELECT * FROM audit_log_chain {where_sql} ORDER BY seq DESC LIMIT ? OFFSET ?",
            params
        ).fetchall()
        total = con.execute(
            f"SELECT COUNT(*) FROM audit_log_chain {where_sql}",
            params[:-2]
        ).fetchone()[0]
    finally:
        con.close()

    return {
        "entries": [dict(r) for r in rows],
        "total":   total,
        "limit":   limit,
        "offset":  offset,
    }


@router.get("/entry/{entry_id}")
def get_entry(entry_id: str):
    """Get a specific audit entry with its receipt."""
    con = _get_conn()
    try:
        entry = con.execute(
            "SELECT * FROM audit_log_chain WHERE entry_id=?", (entry_id,)
        ).fetchone()
        receipt = con.execute(
            "SELECT * FROM audit_receipts WHERE entry_id=?", (entry_id,)
        ).fetchone()
    finally:
        con.close()

    if not entry:
        return JSONResponse({"ok": False, "error": "Entry not found"}, status_code=404)

    return {
        "entry":   dict(entry),
        "receipt": dict(receipt) if receipt else None,
    }


@router.get("/verify")
def verify_chain_integrity():
    """Verify the full hash chain integrity."""
    return verify_chain()


@router.post("/append")
async def append_log_entry(req: Request):
    """Manually append an audit entry (used by agents and internal services)."""
    try:
        try:
            body = await req.json()
        except Exception:
            body = {}
    except Exception:
        return JSONResponse({"ok": False, "error": "Invalid JSON"}, status_code=400)

    agent_id     = (body.get("agent_id") or "system")[:64]
    agent_name   = (body.get("agent_name") or agent_id)[:64]
    action_type  = (body.get("action_type") or "unknown")[:64]
    action_detail= (body.get("action_detail") or "")[:2000]
    reasoning    = (body.get("reasoning") or "")[:1000]
    authority    = (body.get("authority") or "user")[:64]
    risk_level   = (body.get("risk_level") or "low")[:16]
    outcome      = (body.get("outcome") or "success")[:32]
    metadata     = body.get("metadata") or {}

    result = append_entry(
        agent_id=agent_id, agent_name=agent_name,
        action_type=action_type, action_detail=action_detail,
        reasoning=reasoning, authority=authority,
        risk_level=risk_level, outcome=outcome,
        metadata=metadata,
    )
    return {"ok": True, **result}


@router.get("/stats")
def audit_stats():
    """Summary statistics for the audit log."""
    con = _get_conn()
    try:
        total   = con.execute("SELECT COUNT(*) FROM audit_log_chain").fetchone()[0]
        by_risk = con.execute(
            "SELECT risk_level, COUNT(*) as cnt FROM audit_log_chain GROUP BY risk_level"
        ).fetchall()
        by_outcome = con.execute(
            "SELECT outcome, COUNT(*) as cnt FROM audit_log_chain GROUP BY outcome"
        ).fetchall()
        by_agent = con.execute(
            "SELECT agent_id, agent_name, COUNT(*) as cnt FROM audit_log_chain GROUP BY agent_id ORDER BY cnt DESC LIMIT 10"
        ).fetchall()
        recent_hash = con.execute(
            "SELECT entry_hash FROM audit_log_chain ORDER BY seq DESC LIMIT 1"
        ).fetchone()
    finally:
        con.close()

    return {
        "total":      total,
        "chain_tip":  recent_hash["entry_hash"] if recent_hash else None,
        "by_risk":    {r["risk_level"]: r["cnt"] for r in by_risk},
        "by_outcome": {r["outcome"]: r["cnt"] for r in by_outcome},
        "top_agents": [dict(r) for r in by_agent],
    }


@router.get("/export/json")
def export_json(limit: int = 1000):
    """Export audit log as JSON (compliance download)."""
    con = _get_conn()
    try:
        rows = con.execute(
            "SELECT * FROM audit_log_chain ORDER BY seq ASC LIMIT ?",
            (min(limit, 10000),)
        ).fetchall()
    finally:
        con.close()

    payload = json.dumps({
        "export_type":  "agentic_os_audit_log",
        "exported_at":  datetime.now(timezone.utc).isoformat(),
        "total":        len(rows),
        "entries":      [dict(r) for r in rows],
        "chain_verify": verify_chain(),
    }, indent=2, default=str)

    return StreamingResponse(
        io.BytesIO(payload.encode("utf-8")),
        media_type="application/json",
        headers={"Content-Disposition": f'attachment; filename="audit_log_{int(time.time())}.json"'}
    )


@router.get("/export/csv")
def export_csv(limit: int = 1000):
    """Export audit log as CSV (compliance download)."""
    con = _get_conn()
    try:
        rows = con.execute(
            "SELECT seq,entry_id,agent_id,agent_name,action_type,action_detail,reasoning,authority,risk_level,outcome,prev_hash,entry_hash,created_at FROM audit_log_chain ORDER BY seq ASC LIMIT ?",
            (min(limit, 10000),)
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
        io.BytesIO(output.getvalue().encode("utf-8")),
        media_type="text/csv",
        headers={"Content-Disposition": f'attachment; filename="audit_log_{int(time.time())}.csv"'}
    )


@router.get("/receipt/{receipt_id}")
def get_receipt(receipt_id: str):
    """Get a specific signed receipt."""
    con = _get_conn()
    try:
        receipt = con.execute(
            "SELECT r.*, l.action_type, l.action_detail, l.agent_name, l.entry_hash, l.created_at as entry_created_at FROM audit_receipts r JOIN audit_log_chain l ON l.entry_id=r.entry_id WHERE r.receipt_id=?",
            (receipt_id,)
        ).fetchone()
    finally:
        con.close()

    if not receipt:
        return JSONResponse({"ok": False, "error": "Receipt not found"}, status_code=404)
    return {"ok": True, "receipt": dict(receipt)}
