"""
Sprint A — Test Suite 2: Agent Identity & Zero-Trust System
Tests: provision, list, JIT tokens, validation, revocation, key rotation, permissions
"""
import pytest, httpx

BASE = "http://127.0.0.1:8787"

@pytest.fixture(scope="module")
def client():
    return httpx.Client(base_url=BASE, timeout=10)

@pytest.fixture(scope="module")
def provisioned(client):
    """Ensure all agents are provisioned before tests."""
    client.post("/api/agent-identity/provision-all")
    return True


# ── Provision ──────────────────────────────────────────────────────────────────
class TestProvision:
    def test_provision_all_returns_ok(self, client):
        r = client.post("/api/agent-identity/provision-all")
        assert r.status_code == 200
        d = r.json()
        assert d["ok"] is True
        assert isinstance(d["total"], int)
        assert d["total"] >= 8

    def test_provision_single_agent(self, client):
        r = client.post("/api/agent-identity/provision", json={
            "agent_id": "test_identity_agent",
            "display_name": "Test Identity Agent",
            "authority_level": "standard",
        })
        assert r.status_code == 200
        d = r.json()
        assert d["ok"] is True
        assert d["identity"]["agent_id"] == "test_identity_agent"
        assert d["identity"]["authority_level"] == "standard"
        assert d["identity"]["status"] == "active"

    def test_provision_idempotent(self, client, provisioned):
        """Provisioning twice should not create duplicates."""
        client.post("/api/agent-identity/provision", json={
            "agent_id": "idem_test", "authority_level": "standard",
        })
        client.post("/api/agent-identity/provision", json={
            "agent_id": "idem_test", "authority_level": "standard",
        })
        r = client.get("/api/agent-identity/idem_test")
        assert r.status_code == 200
        assert r.json()["ok"] is True

    def test_provision_all_authority_levels(self, client):
        for level in ("minimal", "standard", "elevated", "admin"):
            r = client.post("/api/agent-identity/provision", json={
                "agent_id": f"auth_test_{level}",
                "authority_level": level,
            })
            assert r.json()["ok"] is True

    def test_signing_key_is_redacted(self, client, provisioned):
        r = client.get("/api/agent-identity/builder")
        d = r.json()["identity"]
        assert d["signing_key"] == "[REDACTED]"

    def test_public_key_is_present(self, client, provisioned):
        r = client.get("/api/agent-identity/builder")
        d = r.json()["identity"]
        assert len(d["public_key"]) > 0


# ── List & Get ─────────────────────────────────────────────────────────────────
class TestListAndGet:
    def test_list_identities(self, client, provisioned):
        r = client.get("/api/agent-identity")
        assert r.status_code == 200
        d = r.json()
        assert "identities" in d
        assert d["count"] >= 8

    def test_get_existing_identity(self, client, provisioned):
        r = client.get("/api/agent-identity/builder")
        assert r.status_code == 200
        d = r.json()
        assert d["ok"] is True
        assert d["identity"]["agent_id"] == "builder"

    def test_get_missing_identity_404(self, client):
        r = client.get("/api/agent-identity/nonexistent_xyz_abc")
        assert r.status_code == 404

    def test_identity_has_permissions(self, client, provisioned):
        r = client.get("/api/agent-identity/builder")
        d = r.json()["identity"]
        assert len(d["permissions"]) > 0

    def test_elevated_has_more_perms_than_standard(self, client, provisioned):
        std_r = client.get("/api/agent-identity/auth_test_standard").json()
        elv_r = client.get("/api/agent-identity/auth_test_elevated").json()
        if std_r.get("ok") and elv_r.get("ok"):
            std_count = len(std_r["identity"]["permissions"])
            elv_count = len(elv_r["identity"]["permissions"])
            assert elv_count > std_count


# ── JIT Tokens ─────────────────────────────────────────────────────────────────
class TestJITTokens:
    def test_issue_token(self, client, provisioned):
        r = client.post("/api/agent-identity/builder/issue-token", json={
            "task_id": "test_task_001",
            "ttl_seconds": 300,
            "scope": ["read_memory", "write_tasks"],
        })
        assert r.status_code == 200
        d = r.json()
        assert d["ok"] is True
        assert d["token_id"].startswith("jit_")
        assert d["agent_id"] == "builder"
        assert "expires_at" in d
        assert "signature" in d

    def test_validate_valid_token(self, client, provisioned):
        # Issue
        issue = client.post("/api/agent-identity/builder/issue-token", json={
            "task_id": "validate_test",
            "ttl_seconds": 300,
            "scope": ["read_memory"],
        }).json()
        token_id = issue["token_id"]

        # Validate
        r = client.post("/api/agent-identity/token/validate", json={
            "token_id": token_id,
            "agent_id": "builder",
            "required_action": "read_memory",
        })
        d = r.json()
        assert d["ok"] is True
        assert d["agent_id"] == "builder"
        assert "read_memory" in d["scope"]

    def test_validate_wrong_agent_fails(self, client, provisioned):
        issue = client.post("/api/agent-identity/builder/issue-token", json={
            "task_id": "wrong_agent_test", "ttl_seconds": 300,
        }).json()
        r = client.post("/api/agent-identity/token/validate", json={
            "token_id": issue["token_id"],
            "agent_id": "orchestrator",  # wrong agent
        })
        assert r.json()["ok"] is False

    def test_validate_wrong_action_fails(self, client, provisioned):
        issue = client.post("/api/agent-identity/builder/issue-token", json={
            "task_id": "scope_test",
            "ttl_seconds": 300,
            "scope": ["read_memory"],  # only read_memory
        }).json()
        r = client.post("/api/agent-identity/token/validate", json={
            "token_id": issue["token_id"],
            "agent_id": "builder",
            "required_action": "delete_files",  # not in scope
        })
        assert r.json()["ok"] is False

    def test_revoke_token(self, client, provisioned):
        issue = client.post("/api/agent-identity/builder/issue-token", json={
            "task_id": "revoke_test", "ttl_seconds": 300,
        }).json()
        token_id = issue["token_id"]

        r = client.post(f"/api/agent-identity/token/{token_id}/revoke", json={
            "reason": "test complete",
        })
        assert r.json()["ok"] is True
        assert r.json()["revoked"] is True

    def test_revoked_token_invalid(self, client, provisioned):
        issue = client.post("/api/agent-identity/builder/issue-token", json={
            "task_id": "revoke_invalid_test", "ttl_seconds": 300,
        }).json()
        token_id = issue["token_id"]

        client.post(f"/api/agent-identity/token/{token_id}/revoke", json={})

        r = client.post("/api/agent-identity/token/validate", json={
            "token_id": token_id,
            "agent_id": "builder",
        })
        d = r.json()
        assert d["ok"] is False
        assert "revoked" in d["error"].lower()

    def test_list_agent_tokens(self, client, provisioned):
        client.post("/api/agent-identity/builder/issue-token", json={
            "task_id": "list_test", "ttl_seconds": 300,
        })
        r = client.get("/api/agent-identity/builder/tokens?active_only=true")
        assert r.status_code == 200
        d = r.json()
        assert "tokens" in d
        assert d["count"] >= 0

    def test_missing_token_id_returns_error(self, client):
        r = client.post("/api/agent-identity/token/validate", json={
            "agent_id": "builder"
            # missing token_id
        })
        assert r.json()["ok"] is False

    def test_missing_agent_id_returns_error(self, client):
        r = client.post("/api/agent-identity/token/validate", json={
            "token_id": "jit_abc123"
            # missing agent_id
        })
        assert r.json()["ok"] is False


# ── Key Rotation ───────────────────────────────────────────────────────────────
class TestKeyRotation:
    def test_rotate_keys(self, client, provisioned):
        # Issue a token first
        issue = client.post("/api/agent-identity/reviewer/issue-token", json={
            "task_id": "pre_rotate", "ttl_seconds": 300,
        }).json()
        token_id = issue["token_id"]

        # Rotate
        r = client.post("/api/agent-identity/reviewer/rotate-keys", json={})
        assert r.status_code == 200
        d = r.json()
        assert d["ok"] is True
        assert d["key_version"] >= 2
        assert d["tokens_revoked"] >= 1

    def test_token_invalid_after_rotation(self, client, provisioned):
        issue = client.post("/api/agent-identity/creative/issue-token", json={
            "task_id": "pre_rotate2", "ttl_seconds": 300,
        }).json()
        token_id = issue["token_id"]

        client.post("/api/agent-identity/creative/rotate-keys", json={})

        r = client.post("/api/agent-identity/token/validate", json={
            "token_id": token_id, "agent_id": "creative",
        })
        assert r.json()["ok"] is False

    def test_rotate_missing_agent_404(self, client):
        r = client.post("/api/agent-identity/nonexistent_zzz/rotate-keys", json={})
        assert r.status_code == 404


# ── Permissions ────────────────────────────────────────────────────────────────
class TestPermissions:
    def test_list_permissions(self, client, provisioned):
        r = client.get("/api/agent-identity/builder/permissions")
        assert r.status_code == 200
        d = r.json()
        assert "permissions" in d
        assert len(d["permissions"]) > 0

    def test_grant_permission(self, client, provisioned):
        r = client.post("/api/agent-identity/local/permissions", json={
            "action": "test_custom_action",
            "resource": "test_resource",
            "granted_by": "test_suite",
        })
        assert r.json()["ok"] is True

    def test_revoke_permission(self, client, provisioned):
        # Grant first
        client.post("/api/agent-identity/memory/permissions", json={
            "action": "revoke_test_action", "resource": "*",
        })
        # Revoke
        r = client.delete("/api/agent-identity/memory/permissions/revoke_test_action")
        assert r.json()["ok"] is True


# ── Identity Audit ─────────────────────────────────────────────────────────────
class TestIdentityAudit:
    def test_identity_audit_trail(self, client, provisioned):
        r = client.get("/api/agent-identity/builder/audit?limit=10")
        assert r.status_code == 200
        d = r.json()
        assert "events" in d
        assert len(d["events"]) > 0

    def test_audit_has_provisioned_event(self, client, provisioned):
        r = client.get("/api/agent-identity/test_identity_agent/audit?limit=20")
        events = r.json().get("events", [])
        event_types = [e["event_type"] for e in events]
        assert "identity_provisioned" in event_types


# ── System Stats ───────────────────────────────────────────────────────────────
class TestSystemStats:
    def test_system_stats(self, client, provisioned):
        r = client.get("/api/agent-identity/system/stats")
        assert r.status_code == 200
        d = r.json()
        assert d["total_identities"] >= 8
        assert d["active_identities"] >= 8
        assert d["total_permissions"] >= 64
        assert d["zero_trust_active"] is True

    def test_active_tokens_count(self, client, provisioned):
        # Issue a token
        client.post("/api/agent-identity/builder/issue-token", json={
            "task_id": "stats_test", "ttl_seconds": 600,
        })
        d = client.get("/api/agent-identity/system/stats").json()
        assert d["active_jit_tokens"] >= 1
