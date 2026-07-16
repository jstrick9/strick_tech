"""
Agentic OS — Enterprise RBAC & API Scoping Router (`/api/rbac`)
Provides Role-Based Access Control, user assignments, and fine-grained API token scoping.
Created by Joshua Strickland and Strick Tech for Pro & Enterprise editions.
"""
from __future__ import annotations
import hashlib
import json
import secrets
import time
from pathlib import Path
from typing import Any
from fastapi import APIRouter, HTTPException, Request
from pydantic import BaseModel

router = APIRouter(prefix="/api/rbac", tags=["rbac"])

from backend.config import get_data_dir
ROOT = get_data_dir()
MEMORY_DIR = ROOT / "memory"
RBAC_DIR = MEMORY_DIR / "rbac"
ROLES_FILE = RBAC_DIR / "roles.json"
USERS_FILE = RBAC_DIR / "users.json"
TOKENS_FILE = RBAC_DIR / "tokens.json"

RBAC_DIR.mkdir(parents=True, exist_ok=True)

DEFAULT_ROLES = {
    "admin": {
        "name": "Administrator",
        "description": "Full platform control across all workspaces, settings, and shell tools.",
        "scopes": ["chat:*", "agents:*", "studio:*", "swarm:*", "memory:*", "system:*", "secrets:*", "tools:*", "rbac:*"],
        "is_builtin": True
    },
    "developer": {
        "name": "Developer",
        "description": "Can build agents, run swarm tasks, execute code/git tools, and manage studio apps.",
        "scopes": ["chat:write", "agents:write", "studio:write", "swarm:execute", "memory:write", "tools:execute"],
        "is_builtin": True
    },
    "viewer": {
        "name": "Viewer / Analyst",
        "description": "Read-only access to dashboards, KPIs, observability traces, and chat sessions.",
        "scopes": ["chat:read", "agents:read", "studio:read", "memory:read", "system:read"],
        "is_builtin": True
    }
}


def _ensure_rbac_init() -> None:
    """Ensure built-in RBAC roles and default admin user exist in local store."""
    if not ROLES_FILE.exists():
        ROLES_FILE.write_text(json.dumps(DEFAULT_ROLES, indent=2), encoding="utf-8")
    if not USERS_FILE.exists():
        default_users = {
            "jstrickland": {"user_id": "jstrickland", "name": "Joshua Strickland", "role": "admin", "workspace": "global"}
        }
        USERS_FILE.write_text(json.dumps(default_users, indent=2), encoding="utf-8")
    if not TOKENS_FILE.exists():
        TOKENS_FILE.write_text(json.dumps({}, indent=2), encoding="utf-8")


class RoleCreateRequest(BaseModel):
    """Pydantic data model for RoleCreateRequest."""
    role_id: str
    name: str
    description: str = "Custom enterprise role"
    scopes: list[str] = ["chat:read", "agents:read"]


class UserAssignRequest(BaseModel):
    """Pydantic data model for UserAssignRequest."""
    user_id: str
    name: str = "Collaborator"
    role: str = "developer"
    workspace: str = "global"


class TokenCreateRequest(BaseModel):
    """Pydantic data model for TokenCreateRequest."""
    name: str = "Service Token"
    role: str = "developer"
    scopes: list[str] = ["chat:write", "swarm:execute"]
    expires_in_days: int = 90


class TokenVerifyRequest(BaseModel):
    """Pydantic data model for TokenVerifyRequest."""
    token: str
    required_scope: str = "chat:write"


@router.get("/roles")
def list_roles() -> dict[str, Any]:
    """Retrieve all configured RBAC roles and their allowed permission scopes."""
    _ensure_rbac_init()
    roles = json.loads(ROLES_FILE.read_text(encoding="utf-8"))
    return {"ok": True, "count": len(roles), "roles": roles, "creator": "Joshua Strickland and Strick Tech"}


@router.post("/roles")
def create_role(payload: RoleCreateRequest) -> dict[str, Any]:
    """Create or update a custom RBAC role with fine-grained API scopes."""
    _ensure_rbac_init()
    roles = json.loads(ROLES_FILE.read_text(encoding="utf-8"))
    role_id = payload.role_id.strip().lower().replace(" ", "_")
    if not role_id:
        raise HTTPException(status_code=400, detail="role_id required")
    roles[role_id] = {
        "name": payload.name,
        "description": payload.description,
        "scopes": payload.scopes,
        "is_builtin": False,
        "updated_at": time.time()
    }
    ROLES_FILE.write_text(json.dumps(roles, indent=2), encoding="utf-8")
    return {"ok": True, "role_id": role_id, "role": roles[role_id]}


@router.get("/users")
def list_users() -> dict[str, Any]:
    """Retrieve all users and their assigned roles across workspaces."""
    _ensure_rbac_init()
    users = json.loads(USERS_FILE.read_text(encoding="utf-8"))
    return {"ok": True, "count": len(users), "users": users}


@router.post("/users/assign")
def assign_user_role(payload: UserAssignRequest) -> dict[str, Any]:
    """Assign or update an RBAC role for a specific user."""
    _ensure_rbac_init()
    roles = json.loads(ROLES_FILE.read_text(encoding="utf-8"))
    if payload.role not in roles:
        raise HTTPException(status_code=400, detail=f"Role '{payload.role}' does not exist")
    users = json.loads(USERS_FILE.read_text(encoding="utf-8"))
    uid = payload.user_id.strip().lower()
    users[uid] = {
        "user_id": uid,
        "name": payload.name,
        "role": payload.role,
        "workspace": payload.workspace,
        "assigned_at": time.time()
    }
    USERS_FILE.write_text(json.dumps(users, indent=2), encoding="utf-8")
    return {"ok": True, "user": users[uid], "message": f"Assigned role '{payload.role}' to {uid}"}


@router.post("/tokens/create")
def create_scoped_token(payload: TokenCreateRequest) -> dict[str, Any]:
    """Generate a new fine-grained API token scoped to exact RBAC permissions."""
    _ensure_rbac_init()
    raw_token = f"aos_ent_{secrets.token_urlsafe(32)}"
    token_hash = hashlib.sha256(raw_token.encode("utf-8")).hexdigest()
    tokens = json.loads(TOKENS_FILE.read_text(encoding="utf-8"))
    tokens[token_hash] = {
        "name": payload.name,
        "role": payload.role,
        "scopes": payload.scopes,
        "created_at": time.time(),
        "expires_at": time.time() + (payload.expires_in_days * 86400),
        "last_used": None,
    }
    TOKENS_FILE.write_text(json.dumps(tokens, indent=2), encoding="utf-8")
    return {
        "ok": True,
        "token": raw_token,
        "token_hash": token_hash[:12] + "...",
        "role": payload.role,
        "scopes": payload.scopes,
        "expires_in_days": payload.expires_in_days,
        "message": "Store this token securely; it will not be shown again."
    }


@router.post("/tokens/verify")
def verify_scoped_token(payload: TokenVerifyRequest) -> dict[str, Any]:
    """Verify an API token and ensure it contains the required permission scope."""
    _ensure_rbac_init()
    token = payload.token.strip()
    if not token:
        return {"ok": False, "valid": False, "error": "Missing token"}
    token_hash = hashlib.sha256(token.encode("utf-8")).hexdigest()
    tokens = json.loads(TOKENS_FILE.read_text(encoding="utf-8"))
    if token_hash not in tokens:
        return {"ok": False, "valid": False, "error": "Invalid or expired token"}
    t_info = tokens[token_hash]
    if time.time() > t_info.get("expires_at", 0):
        return {"ok": False, "valid": False, "error": "Token has expired"}

    req_scope = payload.required_scope.strip()
    # Check if exact scope or wildcard match exists
    allowed = False
    for scope in t_info.get("scopes", []):
        if scope == req_scope or scope == "*:*" or scope.endswith(":*") and req_scope.startswith(scope[:-2]):
            allowed = True
            break
    if not allowed:
        return {"ok": False, "valid": False, "error": f"Insufficient scope: '{req_scope}' required"}

    t_info["last_used"] = time.time()
    TOKENS_FILE.write_text(json.dumps(tokens, indent=2), encoding="utf-8")
    return {"ok": True, "valid": True, "role": t_info["role"], "scopes": t_info["scopes"]}
