"""
Agentic OS — Sprint A · Feature 3: Agent Identity & Zero-Trust System
═══════════════════════════════════════════════════════════════════════
Every agent receives a unique cryptographic identity.
JIT (Just-In-Time) access tokens are issued per-task, revoked on completion.
Zero-trust: every inter-agent call must present a valid token.

Architecture:
  • agent_identities table — stores RSA public key + HMAC signing key per agent
  • agent_jit_tokens — short-lived access tokens (TTL-based, task-scoped)
  • agent_permissions — which actions each agent is authorized for
  • Zero-trust middleware callable from any router

Based on:
  • Deloitte Tech Trends 2026: ephemeral authentication, silicon-based workforce
  • Cloud Security Alliance AIUC-1 Q2 2026: distinct cryptographic identity per agent
  • IBM ADLC: least-privilege, task-scoped permissions
"""
from __future__ import annotations
import hashlib, hmac, json, logging, secrets, time, uuid
from datetime import datetime, timezone
from pathlib import Path
from fastapi import APIRouter, Request
from fastapi.responses import JSONResponse

router = APIRouter(prefix="/api/agent-identity", tags=["agent-identity"])
log    = logging.getLogger("agentic.identity")

ROOT = Path(__file__).resolve().parents[2]

# ── Schema ─────────────────────────────────────────────────────────────────────
_SCHEMA = """
CREATE TABLE IF NOT EXISTS agent_identities (
    agent_id      TEXT PRIMARY KEY,
    display_name  TEXT NOT NULL DEFAULT '',
    public_key    TEXT NOT NULL DEFAULT '',
    signing_key   TEXT NOT NULL DEFAULT '',
    key_version   INTEGER NOT NULL DEFAULT 1,
    status        TEXT NOT NULL DEFAULT 'active',
    authority_level TEXT NOT NULL DEFAULT 'standard',
    allowed_actions TEXT NOT NULL DEFAULT '[]',
    created_at    TEXT NOT NULL DEFAULT '',
    rotated_at    TEXT NOT NULL DEFAULT '',
    last_seen_at  TEXT NOT NULL DEFAULT ''
);

CREATE TABLE IF NOT EXISTS agent_jit_tokens (
    token_id      TEXT PRIMARY KEY,
    agent_id      TEXT NOT NULL,
    task_id       TEXT NOT NULL DEFAULT '',
    scope         TEXT NOT NULL DEFAULT '[]',
    issued_at     INTEGER NOT NULL DEFAULT 0,
    expires_at    INTEGER NOT NULL DEFAULT 0,
    revoked       INTEGER NOT NULL DEFAULT 0,
    revoked_at    TEXT NOT NULL DEFAULT '',
    used_count    INTEGER NOT NULL DEFAULT 0,
    max_uses      INTEGER NOT NULL DEFAULT 100,
    FOREIGN KEY (agent_id) REFERENCES agent_identities(agent_id)
);
CREATE INDEX IF NOT EXISTS idx_jit_agent   ON agent_jit_tokens(agent_id, revoked);
CREATE INDEX IF NOT EXISTS idx_jit_expires ON agent_jit_tokens(expires_at);

CREATE TABLE IF NOT EXISTS agent_permissions (
    id          INTEGER PRIMARY KEY AUTOINCREMENT,
    agent_id    TEXT NOT NULL,
    action      TEXT NOT NULL,
    resource    TEXT NOT NULL DEFAULT '*',
    granted_by  TEXT NOT NULL DEFAULT 'system',
    granted_at  TEXT NOT NULL DEFAULT '',
    expires_at  TEXT NOT NULL DEFAULT '',
    UNIQUE(agent_id, action, resource)
);
CREATE INDEX IF NOT EXISTS idx_perm_agent ON agent_permissions(agent_id);

CREATE TABLE IF NOT EXISTS identity_audit (
    id          INTEGER PRIMARY KEY AUTOINCREMENT,
    agent_id    TEXT NOT NULL,
    event_type  TEXT NOT NULL,
    detail      TEXT NOT NULL DEFAULT '',
    ip_hint     TEXT NOT NULL DEFAULT '',
    created_at  TEXT NOT NULL DEFAULT ''
);
CREATE INDEX IF NOT EXISTS idx_id_audit_agent ON identity_audit(agent_id);
"""

# Default token TTL: 1 hour (can be overridden per-task)
DEFAULT_TOKEN_TTL_SECONDS = 3600
# Default max token uses before forced re-issue
DEFAULT_MAX_USES = 500


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


# ── Crypto helpers ─────────────────────────────────────────────────────────────
def _generate_keypair() -> tuple[str, str]:
    """
    Generate a public/private keypair.
    Uses RSA-2048 if cryptography package available, falls back to HMAC-SHA256 shared secret.
    Returns (public_key_hex, signing_key_hex).
    """
    try:
        from cryptography.hazmat.primitives.asymmetric import rsa, padding
        from cryptography.hazmat.primitives import serialization, hashes

        private_key = rsa.generate_private_key(public_exponent=65537, key_size=2048)
        pub_pem = private_key.public_key().public_bytes(
            serialization.Encoding.PEM,
            serialization.PublicFormat.SubjectPublicKeyInfo
        ).decode("utf-8")
        # Store private key as PEM for signing (in production this would be in HSM)
        priv_pem = private_key.private_bytes(
            serialization.Encoding.PEM,
            serialization.PrivateFormat.PKCS8,
            serialization.NoEncryption()
        ).decode("utf-8")
        return pub_pem, priv_pem
    except Exception:
        # Fallback: HMAC-SHA256 shared secret
        signing_key = secrets.token_hex(32)
        public_key  = hashlib.sha256(signing_key.encode()).hexdigest()
        return public_key, signing_key

def _sign_payload(signing_key: str, payload: str) -> str:
    """Sign a payload string. Returns hex signature."""
    try:
        from cryptography.hazmat.primitives.asymmetric import padding
        from cryptography.hazmat.primitives import hashes, serialization
        private_key = serialization.load_pem_private_key(signing_key.encode(), password=None)
        sig = private_key.sign(payload.encode("utf-8"), padding.PKCS1v15(), hashes.SHA256())
        return sig.hex()
    except Exception:
        # HMAC fallback
        return hmac.new(
            signing_key.encode("utf-8"),
            payload.encode("utf-8"),
            hashlib.sha256
        ).hexdigest()

def _now_iso() -> str:
    return datetime.now(timezone.utc).isoformat()

def _now_epoch() -> int:
    return int(time.time())

def _log_identity_event(con, agent_id: str, event_type: str, detail: str = ""):
    con.execute(
        "INSERT INTO identity_audit(agent_id,event_type,detail,created_at) VALUES (?,?,?,?)",
        (agent_id, event_type, detail[:500], _now_iso())
    )


# ── Core identity operations ───────────────────────────────────────────────────
def provision_agent_identity(agent_id: str, display_name: str = "", authority_level: str = "standard") -> dict:
    """
    Create or refresh cryptographic identity for an agent.
    Idempotent — safe to call multiple times, will not overwrite existing.
    """
    pub_key, signing_key = _generate_keypair()
    now = _now_iso()

    con = _get_conn()
    try:
        existing = con.execute(
            "SELECT agent_id FROM agent_identities WHERE agent_id=?", (agent_id,)
        ).fetchone()

        if existing:
            con.close()
            return get_agent_identity(agent_id)

        con.execute("""
            INSERT INTO agent_identities
              (agent_id, display_name, public_key, signing_key, key_version,
               status, authority_level, allowed_actions, created_at, rotated_at, last_seen_at)
            VALUES (?,?,?,?,1,'active',?,'[]',?,?,?)
        """, (agent_id, display_name or agent_id, pub_key, signing_key, authority_level, now, now, now))

        # Seed default permissions based on authority level
        _seed_default_permissions(con, agent_id, authority_level)
        _log_identity_event(con, agent_id, "identity_provisioned", f"authority={authority_level}")
        con.commit()

        log.info("Identity provisioned: %s (%s)", agent_id, authority_level)
    finally:
        con.close()

    return get_agent_identity(agent_id)

def _seed_default_permissions(con, agent_id: str, authority_level: str):
    """Grant default permissions by authority level."""
    now = _now_iso()
    base_actions = ["read_memory", "write_chat", "read_tasks", "use_tools"]
    standard_extra = ["write_tasks", "read_files", "web_search", "run_code"]
    elevated_extra = ["write_files", "delete_tasks", "send_webhook", "manage_agents"]
    admin_extra    = ["delete_files", "deploy", "manage_policies", "system_config"]

    actions = list(base_actions)
    if authority_level in ("standard", "elevated", "admin"):
        actions += standard_extra
    if authority_level in ("elevated", "admin"):
        actions += elevated_extra
    if authority_level == "admin":
        actions += admin_extra

    for action in actions:
        con.execute("""
            INSERT OR IGNORE INTO agent_permissions
              (agent_id, action, resource, granted_by, granted_at)
            VALUES (?,?,'*','system',?)
        """, (agent_id, action, now))

def get_agent_identity(agent_id: str) -> dict | None:
    """Fetch identity record (without signing_key for security)."""
    con = _get_conn()
    try:
        row = con.execute("""
            SELECT agent_id, display_name, public_key, key_version,
                   status, authority_level, allowed_actions,
                   created_at, rotated_at, last_seen_at
            FROM agent_identities WHERE agent_id=?
        """, (agent_id,)).fetchone()
        if not row:
            return None
        perms = con.execute(
            "SELECT action, resource FROM agent_permissions WHERE agent_id=?", (agent_id,)
        ).fetchall()
        # Build result inside try block while connection is still open
        d = dict(row)
        d["permissions"] = [{"action": p["action"], "resource": p["resource"]} for p in perms]
        d["signing_key"]  = "[REDACTED]"
        return d
    finally:
        con.close()

def issue_jit_token(
    agent_id: str,
    task_id: str = "",
    scope: list[str] | None = None,
    ttl_seconds: int = DEFAULT_TOKEN_TTL_SECONDS,
    max_uses: int = DEFAULT_MAX_USES,
) -> dict:
    """Issue a short-lived JIT access token for an agent+task combination."""
    now_epoch = _now_epoch()
    expires_at = now_epoch + ttl_seconds
    token_id = f"jit_{secrets.token_hex(16)}"

    con = _get_conn()
    try:
        identity = con.execute(
            "SELECT agent_id, status, signing_key FROM agent_identities WHERE agent_id=?",
            (agent_id,)
        ).fetchone()
        if not identity:
            con.close()
            return {"ok": False, "error": f"Agent identity not found: {agent_id}. Call /provision first."}
        if identity["status"] != "active":
            con.close()
            return {"ok": False, "error": f"Agent identity is {identity['status']}, not active"}

        scope_str = json.dumps(scope or [])
        con.execute("""
            INSERT INTO agent_jit_tokens
              (token_id, agent_id, task_id, scope, issued_at, expires_at, max_uses)
            VALUES (?,?,?,?,?,?,?)
        """, (token_id, agent_id, task_id or "", scope_str, now_epoch, expires_at, max_uses))

        # Sign the token payload
        payload  = f"{token_id}|{agent_id}|{task_id}|{expires_at}"
        sig = _sign_payload(identity["signing_key"], payload)

        # Update last_seen
        con.execute("UPDATE agent_identities SET last_seen_at=? WHERE agent_id=?",
                    (_now_iso(), agent_id))
        _log_identity_event(con, agent_id, "jit_token_issued",
                            f"task={task_id} ttl={ttl_seconds}s scope={scope_str}")
        con.commit()
    finally:
        con.close()

    return {
        "ok":        True,
        "token_id":  token_id,
        "agent_id":  agent_id,
        "task_id":   task_id,
        "scope":     scope or [],
        "expires_at": expires_at,
        "expires_in": ttl_seconds,
        "signature": sig,
    }

def validate_jit_token(token_id: str, agent_id: str, required_action: str = "") -> dict:
    """
    Validate a JIT token. Returns {ok, agent_id, scope, remaining_uses}.
    Call this from any route that requires agent authentication.
    """
    now_epoch = _now_epoch()
    con = _get_conn()
    try:
        row = con.execute(
            "SELECT * FROM agent_jit_tokens WHERE token_id=? AND agent_id=?",
            (token_id, agent_id)
        ).fetchone()
        if not row:
            return {"ok": False, "error": "Token not found"}
        if row["revoked"]:
            return {"ok": False, "error": "Token has been revoked"}
        if row["expires_at"] < now_epoch:
            return {"ok": False, "error": "Token has expired"}
        if row["used_count"] >= row["max_uses"]:
            return {"ok": False, "error": "Token max uses exceeded"}

        scope = json.loads(row["scope"] or "[]")
        if required_action and scope and required_action not in scope:
            return {"ok": False, "error": f"Token scope does not include: {required_action}"}

        # Increment use count
        con.execute("UPDATE agent_jit_tokens SET used_count=used_count+1 WHERE token_id=?", (token_id,))
        con.commit()
    finally:
        con.close()

    return {
        "ok":            True,
        "agent_id":      agent_id,
        "task_id":       row["task_id"],
        "scope":         scope,
        "remaining_uses": max(0, row["max_uses"] - row["used_count"] - 1),
        "expires_at":    row["expires_at"],
    }

def revoke_jit_token(token_id: str, reason: str = "") -> dict:
    """Revoke a JIT token immediately."""
    con = _get_conn()
    try:
        row = con.execute("SELECT agent_id FROM agent_jit_tokens WHERE token_id=?", (token_id,)).fetchone()
        if not row:
            con.close()
            return {"ok": False, "error": "Token not found"}
        con.execute(
            "UPDATE agent_jit_tokens SET revoked=1, revoked_at=? WHERE token_id=?",
            (_now_iso(), token_id)
        )
        _log_identity_event(con, row["agent_id"], "jit_token_revoked",
                            f"token={token_id} reason={reason}")
        con.commit()
    finally:
        con.close()
    return {"ok": True, "token_id": token_id, "revoked": True}


def provision_all_agents() -> list[dict]:
    """Auto-provision identities for all existing agents that don't have one."""
    con = _get_conn()
    try:
        agents = con.execute("SELECT id, name, role FROM agents WHERE enabled=1").fetchall()
    finally:
        con.close()

    results = []
    for agent in agents:
        # Map roles to authority levels
        authority = "standard"
        if agent["id"] in ("orchestrator", "brain"):
            authority = "elevated"

        existing = get_agent_identity(agent["id"])
        if not existing:
            result = provision_agent_identity(
                agent["id"], agent["name"], authority
            )
            results.append({**result, "provisioned": True})
        else:
            results.append({**existing, "provisioned": False})
    return results


# ── API Routes ─────────────────────────────────────────────────────────────────
@router.get("")
def list_identities():
    """List all agent identities."""
    con = _get_conn()
    try:
        rows = con.execute("""
            SELECT ai.agent_id, ai.display_name, ai.key_version, ai.status,
                   ai.authority_level, ai.created_at, ai.last_seen_at,
                   (SELECT COUNT(*) FROM agent_jit_tokens j WHERE j.agent_id=ai.agent_id AND j.revoked=0 AND j.expires_at > ?) as active_tokens,
                   (SELECT COUNT(*) FROM agent_permissions p WHERE p.agent_id=ai.agent_id) as permission_count
            FROM agent_identities ai
            ORDER BY ai.created_at DESC
        """, (_now_epoch(),)).fetchall()
    finally:
        con.close()
    return {"identities": [dict(r) for r in rows], "count": len(rows)}


@router.post("/provision")
async def provision_identity(req: Request):
    """Provision cryptographic identity for an agent."""
    try:
        try:
            body = await req.json()
        except Exception:
            body = {}
    except Exception:
        return JSONResponse({"ok": False, "error": "Invalid JSON"}, status_code=400)

    agent_id      = (body.get("agent_id") or "").strip()
    display_name  = (body.get("display_name") or "").strip()
    authority_lvl = (body.get("authority_level") or "standard").strip()

    if not agent_id:
        return JSONResponse({"ok": False, "error": "agent_id required"}, status_code=400)
    if authority_lvl not in ("minimal", "standard", "elevated", "admin"):
        authority_lvl = "standard"

    result = provision_agent_identity(agent_id, display_name, authority_lvl)
    return {"ok": True, "identity": result}


@router.post("/provision-all")
def provision_all():
    """Auto-provision identities for all agents in the system."""
    results = provision_all_agents()
    new_count = sum(1 for r in results if r.get("provisioned"))
    return {
        "ok":         True,
        "total":      len(results),
        "new":        new_count,
        "existing":   len(results) - new_count,
        "identities": results,
    }


@router.get("/{agent_id}")
def get_identity(agent_id: str):
    """Get an agent's identity (public key, permissions, token count)."""
    identity = get_agent_identity(agent_id)
    if not identity:
        return JSONResponse({"ok": False, "error": "Identity not found"}, status_code=404)
    return {"ok": True, "identity": identity}


@router.post("/{agent_id}/rotate-keys")
async def rotate_keys(agent_id: str, req: Request):
    """Rotate an agent's cryptographic keys (invalidates all existing JIT tokens)."""
    pub_key, signing_key = _generate_keypair()
    now = _now_iso()

    con = _get_conn()
    try:
        existing = con.execute(
            "SELECT key_version FROM agent_identities WHERE agent_id=?", (agent_id,)
        ).fetchone()
        if not existing:
            con.close()
            return JSONResponse({"ok": False, "error": "Identity not found"}, status_code=404)

        new_version = existing["key_version"] + 1
        con.execute("""
            UPDATE agent_identities
            SET public_key=?, signing_key=?, key_version=?, rotated_at=?
            WHERE agent_id=?
        """, (pub_key, signing_key, new_version, now, agent_id))

        # Revoke all existing JIT tokens
        con.execute(
            "UPDATE agent_jit_tokens SET revoked=1, revoked_at=? WHERE agent_id=? AND revoked=0",
            (now, agent_id)
        )
        revoked_count = con.execute("SELECT changes()").fetchone()[0]
        _log_identity_event(con, agent_id, "keys_rotated",
                            f"new_version={new_version} revoked_tokens={revoked_count}")
        con.commit()
    finally:
        con.close()

    log.info("Keys rotated: %s (v%s, %s tokens revoked)", agent_id, new_version, revoked_count)
    return {
        "ok":           True,
        "agent_id":     agent_id,
        "key_version":  new_version,
        "tokens_revoked": revoked_count,
    }


@router.post("/{agent_id}/issue-token")
async def issue_token(agent_id: str, req: Request):
    """Issue a JIT access token for an agent+task."""
    try:
        try:
            body = await req.json()
        except Exception:
            body = {}
    except Exception:
        body = {}

    task_id  = (body.get("task_id") or "")[:64]
    scope    = body.get("scope") or []
    ttl      = min(int(body.get("ttl_seconds") or DEFAULT_TOKEN_TTL_SECONDS), 86400)
    max_uses = min(int(body.get("max_uses") or DEFAULT_MAX_USES), 10000)

    result = issue_jit_token(agent_id, task_id, scope, ttl, max_uses)
    return result


@router.post("/token/validate")
async def validate_token(req: Request):
    """Validate a JIT token (zero-trust check)."""
    try:
        try:
            body = await req.json()
        except Exception:
            body = {}
    except Exception:
        return JSONResponse({"ok": False, "error": "Invalid JSON"}, status_code=400)

    token_id = (body.get("token_id") or "").strip()
    agent_id = (body.get("agent_id") or "").strip()
    action   = (body.get("required_action") or "").strip()

    if not token_id or not agent_id:
        return JSONResponse({"ok": False, "error": "token_id and agent_id required"}, status_code=400)

    return validate_jit_token(token_id, agent_id, action)


@router.post("/token/{token_id}/revoke")
async def revoke_token(token_id: str, req: Request):
    """Revoke a JIT token immediately."""
    try:
        try:
            body = await req.json()
        except Exception:
            body = {}
        reason = body.get("reason", "")
    except Exception:
        reason = ""
    return revoke_jit_token(token_id, reason)


@router.get("/{agent_id}/tokens")
def list_agent_tokens(agent_id: str, active_only: bool = True):
    """List JIT tokens for an agent."""
    now_epoch = _now_epoch()
    con = _get_conn()
    try:
        if active_only:
            rows = con.execute(
                "SELECT token_id, task_id, scope, issued_at, expires_at, used_count, max_uses FROM agent_jit_tokens WHERE agent_id=? AND revoked=0 AND expires_at>? ORDER BY issued_at DESC LIMIT 50",
                (agent_id, now_epoch)
            ).fetchall()
        else:
            rows = con.execute(
                "SELECT token_id, task_id, scope, issued_at, expires_at, revoked, used_count, max_uses FROM agent_jit_tokens WHERE agent_id=? ORDER BY issued_at DESC LIMIT 100",
                (agent_id,)
            ).fetchall()
    finally:
        con.close()
    return {"tokens": [dict(r) for r in rows], "count": len(rows)}


@router.get("/{agent_id}/permissions")
def list_permissions(agent_id: str):
    """List all permissions for an agent."""
    con = _get_conn()
    try:
        perms = con.execute(
            "SELECT * FROM agent_permissions WHERE agent_id=? ORDER BY action",
            (agent_id,)
        ).fetchall()
    finally:
        con.close()
    return {"agent_id": agent_id, "permissions": [dict(p) for p in perms], "count": len(perms)}


@router.post("/{agent_id}/permissions")
async def grant_permission(agent_id: str, req: Request):
    """Grant a permission to an agent."""
    try:
        try:
            body = await req.json()
        except Exception:
            body = {}
    except Exception:
        return JSONResponse({"ok": False, "error": "Invalid JSON"}, status_code=400)

    action      = (body.get("action") or "").strip()
    resource    = (body.get("resource") or "*").strip()
    granted_by  = (body.get("granted_by") or "user").strip()

    if not action:
        return JSONResponse({"ok": False, "error": "action required"}, status_code=400)

    con = _get_conn()
    try:
        con.execute("""
            INSERT OR IGNORE INTO agent_permissions
              (agent_id, action, resource, granted_by, granted_at)
            VALUES (?,?,?,?,?)
        """, (agent_id, action, resource, granted_by, _now_iso()))
        _log_identity_event(con, agent_id, "permission_granted", f"{action} on {resource}")
        con.commit()
    finally:
        con.close()
    return {"ok": True, "agent_id": agent_id, "action": action, "resource": resource}


@router.delete("/{agent_id}/permissions/{action}")
def revoke_permission(agent_id: str, action: str):
    """Revoke a permission from an agent."""
    con = _get_conn()
    try:
        con.execute(
            "DELETE FROM agent_permissions WHERE agent_id=? AND action=?",
            (agent_id, action)
        )
        _log_identity_event(con, agent_id, "permission_revoked", f"{action}")
        con.commit()
    finally:
        con.close()
    return {"ok": True, "agent_id": agent_id, "action": action, "revoked": True}


@router.get("/{agent_id}/audit")
def identity_audit_log(agent_id: str, limit: int = 50):
    """Identity event audit trail for an agent."""
    con = _get_conn()
    try:
        rows = con.execute(
            "SELECT * FROM identity_audit WHERE agent_id=? ORDER BY id DESC LIMIT ?",
            (agent_id, min(limit, 500))
        ).fetchall()
    finally:
        con.close()
    return {"agent_id": agent_id, "events": [dict(r) for r in rows], "count": len(rows)}


@router.get("/system/stats")
def identity_system_stats():
    """Overall identity system statistics."""
    now_epoch = _now_epoch()
    con = _get_conn()
    try:
        total_identities = con.execute("SELECT COUNT(*) FROM agent_identities").fetchone()[0]
        active_identities = con.execute("SELECT COUNT(*) FROM agent_identities WHERE status='active'").fetchone()[0]
        active_tokens = con.execute(
            "SELECT COUNT(*) FROM agent_jit_tokens WHERE revoked=0 AND expires_at>?", (now_epoch,)
        ).fetchone()[0]
        total_permissions = con.execute("SELECT COUNT(*) FROM agent_permissions").fetchone()[0]
        recent_events = con.execute(
            "SELECT COUNT(*) FROM identity_audit WHERE created_at > datetime('now','-1 hour')"
        ).fetchone()[0]
    finally:
        con.close()

    return {
        "total_identities":  total_identities,
        "active_identities": active_identities,
        "active_jit_tokens": active_tokens,
        "total_permissions": total_permissions,
        "events_last_hour":  recent_events,
        "zero_trust_active": True,
    }
