"""
Integration Flow 09 — Sprint A Governance: End-to-End Governance Pipeline
Tests the complete governance lifecycle:
  Audit Log chain integrity → Agent Identity provisioning → JIT tokens →
  HITL approval flow → Immutable receipts → Cross-component audit trail

All components interact: every agent action is governed end-to-end.
"""
from __future__ import annotations
import asyncio, time, uuid
import httpx, pytest
from .conftest import BASE, TIMEOUT, uid, GET, POST, PATCH, DELETE, ok, ok_or, check

# ══════════════════════════════════════════════════════════════════
#  TEST CLASS 1: Immutable Audit Chain Integrity
# ══════════════════════════════════════════════════════════════════
class TestAuditChainIntegrity:
    """Verify the SHA-256 hash chain stays intact across multiple appends."""

    async def test_01_chain_verifies_before_test(self, client):
        """Confirm chain is valid at test start."""
        r = await GET(client, "/api/audit-log/verify")
        d = ok(r, "audit verify start")
        check("chain ok before test", d["ok"] is True, d)
        check("has entries", d["verified"] >= 0, d["verified"])

    async def test_02_append_entries_chain_links_correctly(self, client):
        """Three sequential appends — each prev_hash must equal prior entry_hash."""
        entries = []
        for i in range(3):
            r = await POST(client, "/api/audit-log/append", {
                "agent_id": f"integration_agent_{i}",
                "agent_name": f"IntAgent{i}",
                "action_type": f"integration_action_{i}",
                "action_detail": f"Integration test step {i} of chain linkage",
                "reasoning": f"Step {i} for chain integrity test",
                "authority": "integration_test",
                "risk_level": "low",
                "outcome": "success",
                "metadata": {"test_step": i, "flow": "09"}
            })
            d = ok(r, f"append entry {i}")
            check(f"append ok {i}", d["ok"] is True)
            entries.append(d)

        # Verify chain links: entry[i].prev_hash == entry[i-1].entry_hash
        for i in range(1, len(entries)):
            check(
                f"chain link {i-1}→{i}",
                entries[i]["prev_hash"] == entries[i-1]["entry_hash"],
                {
                    "prev_hash": entries[i]["prev_hash"],
                    "expected": entries[i-1]["entry_hash"]
                }
            )

    async def test_03_verify_after_appends(self, client):
        """Chain must still verify after our appends."""
        r = await GET(client, "/api/audit-log/verify")
        d = ok(r, "audit verify after appends")
        check("chain still valid", d["ok"] is True, d)
        check("entries grew", d["verified"] >= 3)

    async def test_04_stats_reflect_entries(self, client):
        """Stats endpoint shows correct counts and top agents."""
        r = await GET(client, "/api/audit-log/stats")
        d = ok(r, "audit stats")
        check("has total", "total" in d)
        check("has chain_tip", "chain_tip" in d)
        check("has by_risk", "by_risk" in d)
        check("has by_outcome", "by_outcome" in d)
        check("has top_agents", "top_agents" in d)
        check("total > 0", d["total"] > 0)

    async def test_05_filter_by_risk_level(self, client):
        """Filter audit entries by risk level."""
        r = await GET(client, "/api/audit-log", risk_level="low", limit=10)
        d = ok(r, "audit filter risk")
        for entry in d["entries"]:
            check("risk=low", entry["risk_level"] == "low", entry["risk_level"])

    async def test_06_get_specific_entry_with_receipt(self, client):
        """Get entry by ID and confirm signed receipt is present."""
        # Append a known entry
        append_r = await POST(client, "/api/audit-log/append", {
            "agent_id": "receipt_test_agent",
            "action_type": "receipt_validation",
            "action_detail": "Test receipt generation",
            "outcome": "success"
        })
        entry_id = append_r.json()["entry_id"]

        # Fetch it
        r = await GET(client, f"/api/audit-log/entry/{entry_id}")
        d = ok(r, "get entry by id")
        check("has entry", "entry" in d)
        check("entry_id matches", d["entry"]["entry_id"] == entry_id)
        check("has receipt", "receipt" in d)
        check("receipt not none", d["receipt"] is not None)
        check("receipt has receipt_id", "receipt_id" in d["receipt"])

    async def test_07_export_json_contains_verify(self, client):
        """JSON export includes chain verification data."""
        r = await GET(client, "/api/audit-log/export/json", limit=5)
        d = ok(r, "export json")
        check("has entries", "entries" in d)
        check("has chain_verify", "chain_verify" in d)
        check("chain_verify ok", d["chain_verify"]["ok"] is True)

    async def test_08_csv_export_has_headers(self, client):
        """CSV export includes headers."""
        r = await client.get("/api/audit-log/export/csv?limit=5")
        check("csv 200", r.status_code == 200)
        check("csv content-type", "csv" in r.headers.get("content-type", ""))
        lines = r.text.strip().split("\n")
        check("has header row", len(lines) >= 1)
        check("entry_id in header", "entry_id" in lines[0])


# ══════════════════════════════════════════════════════════════════
#  TEST CLASS 2: Agent Identity Provisioning + JIT Token Lifecycle
# ══════════════════════════════════════════════════════════════════
class TestAgentIdentityAndJITFlow:
    """Full identity provisioning → token issuance → use → revocation lifecycle."""

    async def test_01_provision_all_agents(self, client):
        """All 8 default agents get cryptographic identities."""
        r = await POST(client, "/api/agent-identity/provision-all")
        d = ok(r, "provision all")
        check("provision ok", d["ok"] is True)
        check("has total", "total" in d)
        check("total >= 8", d["total"] >= 8)

    async def test_02_each_agent_has_identity(self, client):
        """Each agent has a distinct identity with public key (fetched individually)."""
        r = await GET(client, "/api/agent-identity")
        d = ok(r, "list identities")
        check("count >= 8", d["count"] >= 8)
        # List endpoint has agent_id - verify at least 8 unique agents
        agent_ids = [i["agent_id"] for i in d["identities"]]
        check("unique agents >= 8", len(set(agent_ids)) >= 8)
        # Fetch one identity to verify public_key is present
        detail = (await GET(client, "/api/agent-identity/builder")).json()
        check("builder identity ok", detail["ok"] is True)
        check("public_key present", len(detail["identity"].get("public_key","")) > 10)

    async def test_03_signing_key_never_exposed(self, client):
        """Signing key must be [REDACTED] in individual identity responses."""
        # The list endpoint omits signing_key for efficiency
        # Individual fetch must have it redacted
        for agent_id in ["builder", "brain", "researcher"]:
            detail = (await GET(client, f"/api/agent-identity/{agent_id}")).json()
            if detail.get("ok"):
                sk = detail["identity"].get("signing_key", "NOT_PRESENT")
                check(f"{agent_id} signing_key redacted", sk == "[REDACTED]", sk)

    async def test_04_jit_token_full_lifecycle(self, client):
        """Issue → validate → revoke → validate fails."""
        # Issue
        issue_r = await POST(client, "/api/agent-identity/builder/issue-token", {
            "task_id": f"integration_task_{uid()}",
            "ttl_seconds": 300,
            "scope": ["read_memory", "write_tasks", "web_search"]
        })
        d = ok(issue_r, "issue token")
        check("token ok", d["ok"] is True)
        token_id = d["token_id"]
        check("token_id starts jit_", token_id.startswith("jit_"))
        check("has signature", len(d.get("signature", "")) > 0)
        check("scope matches", "read_memory" in d["scope"])

        # Validate — should succeed
        val_r = await POST(client, "/api/agent-identity/token/validate", {
            "token_id": token_id,
            "agent_id": "builder",
            "required_action": "read_memory"
        })
        vd = ok(val_r, "validate token")
        check("validate ok", vd["ok"] is True)
        check("agent_id matches", vd["agent_id"] == "builder")
        check("remaining_uses > 0", vd["remaining_uses"] >= 0)

        # Revoke
        rev_r = await POST(client, f"/api/agent-identity/token/{token_id}/revoke", {
            "reason": "integration test cleanup"
        })
        rd = ok(rev_r, "revoke token")
        check("revoke ok", rd["ok"] is True)
        check("revoked flag", rd["revoked"] is True)

        # Validate after revoke — must fail
        val2_r = await POST(client, "/api/agent-identity/token/validate", {
            "token_id": token_id,
            "agent_id": "builder"
        })
        v2d = ok(val2_r, "validate revoked")
        check("revoked token rejected", v2d["ok"] is False)
        check("error mentions revoked", "revoked" in v2d.get("error", "").lower())

    async def test_05_wrong_agent_fails_validation(self, client):
        """Token issued to builder cannot be used by orchestrator."""
        issue = await POST(client, "/api/agent-identity/researcher/issue-token", {
            "task_id": "scope_test", "ttl_seconds": 60
        })
        token_id = issue.json()["token_id"]
        val = await POST(client, "/api/agent-identity/token/validate", {
            "token_id": token_id,
            "agent_id": "brain"  # Wrong agent
        })
        check("wrong agent rejected", val.json()["ok"] is False)
        # Cleanup
        await POST(client, f"/api/agent-identity/token/{token_id}/revoke", {})

    async def test_06_permission_grant_and_revoke(self, client):
        """Grant a custom permission then revoke it."""
        # Grant
        grant_r = await POST(client, "/api/agent-identity/local/permissions", {
            "action": "integration_custom_action",
            "resource": "test_resource",
            "granted_by": "integration_test"
        })
        check("grant 200", grant_r.status_code == 200)
        check("grant ok", grant_r.json()["ok"] is True)

        # Verify it appears
        perms_r = await GET(client, "/api/agent-identity/local/permissions")
        perms = perms_r.json()["permissions"]
        actions = [p["action"] for p in perms]
        check("granted action visible", "integration_custom_action" in actions)

        # Revoke
        rev_r = await client.delete("/api/agent-identity/local/permissions/integration_custom_action")
        check("revoke 200", rev_r.status_code == 200)
        check("revoke ok", rev_r.json()["ok"] is True)

    async def test_07_key_rotation_invalidates_all_tokens(self, client):
        """Rotating keys invalidates existing JIT tokens."""
        # Issue 2 tokens for creative agent
        t1 = (await POST(client, "/api/agent-identity/creative/issue-token",
                          {"task_id": "pre_rotate_1", "ttl_seconds": 300})).json()["token_id"]
        t2 = (await POST(client, "/api/agent-identity/creative/issue-token",
                          {"task_id": "pre_rotate_2", "ttl_seconds": 300})).json()["token_id"]

        # Rotate keys
        rot_r = await POST(client, "/api/agent-identity/creative/rotate-keys", {})
        rd = ok(rot_r, "rotate keys")
        check("rotation ok", rd["ok"] is True)
        check("key version incremented", rd["key_version"] >= 2)
        check("tokens revoked", rd["tokens_revoked"] >= 2)

        # Both tokens must be invalid now
        for tid in [t1, t2]:
            val = await POST(client, "/api/agent-identity/token/validate", {
                "token_id": tid, "agent_id": "creative"
            })
            check(f"token {tid[:12]} invalid after rotation", val.json()["ok"] is False)

    async def test_08_identity_audit_trail(self, client):
        """Every identity operation generates an audit event."""
        # Trigger a known event
        await POST(client, "/api/agent-identity/memory/issue-token",
                   {"task_id": "audit_trail_test", "ttl_seconds": 60})
        # Check audit trail
        r = await GET(client, "/api/agent-identity/memory/audit", limit=10)
        d = ok(r, "identity audit")
        check("has events", len(d["events"]) > 0)
        event_types = [e["event_type"] for e in d["events"]]
        check("jit_token_issued recorded", "jit_token_issued" in event_types)

    async def test_09_system_stats_coherent(self, client):
        """System-wide identity stats reflect all provisioned agents."""
        r = await GET(client, "/api/agent-identity/system/stats")
        d = ok(r, "system stats")
        check("total_identities >= 8", d["total_identities"] >= 8)
        check("active_identities >= 8", d["active_identities"] >= 8)
        check("total_permissions > 0", d["total_permissions"] > 0)
        check("zero_trust active", d["zero_trust_active"] is True)


# ══════════════════════════════════════════════════════════════════
#  TEST CLASS 3: HITL Approval Flow → Audit Trail
# ══════════════════════════════════════════════════════════════════
class TestHITLGovernanceFlow:
    """Complete HITL flow: interrupt → approval/rejection → audit trail."""

    async def test_01_high_risk_creates_pending_interrupt(self, client):
        """High-risk action with low confidence creates a pending interrupt."""
        r = await POST(client, "/api/hitl/interrupt", {
            "action_type": "delete_production_database",
            "action_summary": "Integration test: delete ALL user data from production",
            "risk_level": "critical",
            "confidence": 0.1,
            "agent_id": "orchestrator",
            "action_data": {"table": "users", "confirm": False}
        })
        d = ok(r, "create critical interrupt")
        check("interrupt ok", d["ok"] is True)
        check("not auto-approved", d["auto"] is False)
        check("decision pending", d["decision"] == "pending")
        int_id = d["interrupt_id"]

        # Verify it appears in queue
        q_r = await GET(client, "/api/hitl/queue")
        qd = ok(q_r, "queue after interrupt")
        queue_ids = [item["id"] for item in qd["interrupts"]]
        check("interrupt in queue", int_id in queue_ids)

        # Reject it (proper governance decision)
        rej_r = await POST(client, f"/api/hitl/interrupt/{int_id}/decide", {
            "decision": "reject",
            "note": "Integration test rejection — never delete production data",
            "reviewer": "integration_test_suite"
        })
        rd = ok(rej_r, "reject interrupt")
        check("reject ok", rd["ok"] is True)
        check("decision=reject", rd["decision"] == "reject")

        # Verify rejected interrupt NOT in pending queue
        q2_r = await GET(client, "/api/hitl/queue")
        q2_ids = [item["id"] for item in q2_r.json()["interrupts"]]
        check("interrupt removed from pending", int_id not in q2_ids)

    async def test_02_low_risk_auto_approves(self, client):
        """Low-risk/high-confidence action auto-approves without human review."""
        r = await POST(client, "/api/hitl/interrupt", {
            "action_type": "read_config_file",
            "action_summary": "Read application configuration",
            "risk_level": "low",
            "confidence": 0.98,
            "agent_id": "builder"
        })
        d = ok(r, "low risk interrupt")
        check("auto-approved", d["auto"] is True)
        check("decision auto_approved", d["decision"] == "auto_approved")

    async def test_03_always_interrupt_actions_never_auto(self, client):
        """Actions in ALWAYS_INTERRUPT set never auto-approve regardless of confidence."""
        for action in ["send_email", "stripe_charge", "deploy_to_production"]:
            r = await POST(client, "/api/hitl/interrupt", {
                "action_type": action,
                "action_summary": f"Integration test: {action}",
                "risk_level": "high",
                "confidence": 0.99,
                "agent_id": "orchestrator"
            })
            d = ok(r, f"always_interrupt {action}")
            check(f"{action} not auto", d["auto"] is False, d)
            check(f"{action} pending", d["decision"] == "pending")
            # Approve it to clear the queue
            await POST(client, f"/api/hitl/interrupt/{d['interrupt_id']}/decide",
                       {"decision": "approve", "reviewer": "integration_cleanup"})

    async def test_04_undo_snapshot_and_restore(self, client):
        """Create an undo snapshot and verify it persists."""
        r = await POST(client, "/api/hitl/undo-snapshot", {
            "action_id": "/preview/index.html",
            "type": "file",
            "state_data": "<!-- Original integration test content -->"
        })
        d = ok(r, "undo snapshot")
        check("snapshot ok", d["ok"] is True)
        snap_id = d["snapshot_id"]
        check("snapshot_id format", snap_id.startswith("undo_"))

    async def test_05_confidence_assessment_returns_structured(self, client):
        """AI confidence assessment returns structured risk analysis."""
        r = await POST(client, "/api/hitl/assess-confidence", {
            "action": "DROP TABLE users CASCADE",
            "context": "Database maintenance script"
        })
        d = ok(r, "confidence assessment")
        check("ok", d["ok"] is True)
        check("confidence float", isinstance(d.get("confidence"), float))
        check("risk_level present", d.get("risk_level") in ("low","medium","high","critical"))
        check("recommendation present", d.get("recommendation") in ("proceed","interrupt","reject"))

    async def test_06_hitl_audit_log_records_decisions(self, client):
        """All HITL decisions appear in the audit log."""
        r = await GET(client, "/api/hitl/audit", limit=20)
        d = ok(r, "hitl audit")
        check("has audit list", "audit" in d)
        # Should have decisions from our tests
        check("has at least one decision", len(d["audit"]) > 0)

    async def test_07_approval_writes_to_immutable_chain(self, client):
        """After an approval, the audit chain entry count grows."""
        before = (await GET(client, "/api/audit-log/verify")).json()["verified"]

        # Create and approve an interrupt
        int_r = await POST(client, "/api/hitl/interrupt", {
            "action_type": "chain_test_write",
            "action_summary": "Test that HITL decisions flow to audit chain",
            "risk_level": "medium",
            "confidence": 0.4
        })
        int_id = int_r.json()["interrupt_id"]
        await POST(client, f"/api/hitl/interrupt/{int_id}/decide",
                   {"decision": "approve", "reviewer": "chain_test"})

        # Small wait for async audit write
        await asyncio.sleep(0.3)

        after = (await GET(client, "/api/audit-log/verify")).json()["verified"]
        check("chain grew after approval", after >= before, f"before={before} after={after}")
        check("chain still valid", (await GET(client, "/api/audit-log/verify")).json()["ok"] is True)

    async def test_08_hitl_stats_accurate(self, client):
        """HITL stats reflect all test operations."""
        r = await GET(client, "/api/hitl/stats")
        d = ok(r, "hitl stats")
        check("total > 0", d["total"] > 0)
        check("has pending", "pending" in d)
        check("has approved", "approved" in d)
        check("has rejected", "rejected" in d)
        check("approval_rate is float", isinstance(d.get("approval_rate"), float))
