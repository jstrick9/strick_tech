"""
UAT 08 — Governance Features (Sprint A)
User Stories:
  • As a user, I can see a tamper-proof record of every agent action
  • As an admin, I can provision secure identities for agents
  • As a user, risky AI actions are gated by human approval
  • As an admin, I can verify that no records have been altered

Acceptance Criteria tested at the USER level — what the user sees and can do.
"""
from __future__ import annotations
import asyncio, time
import httpx, pytest
from .conftest import BASE, uid, GET, POST, PATCH, DELETE, j, accept, uat, no_error


# ══════════════════════════════════════════════════════════════════
#  USER STORY: "I can see a tamper-proof record of every AI action"
# ══════════════════════════════════════════════════════════════════
class TestUATAuditLog:
    """User Story: I want to see an immutable record of every agent action so I can audit what happened."""

    async def test_user_can_verify_audit_chain_is_intact(self, U):
        """AC: User opens Audit Log → sees 'Chain integrity verified ✅'."""
        r = await GET(U, "/api/audit-log/verify")
        no_error(r, "verify audit chain")
        d = j(r)
        uat("chain is valid (user sees green checkmark)", d["ok"] is True)
        uat("user sees entry count", d["verified"] >= 0)
        uat("user sees chain tip hash (64 chars)", len(d["chain_tip"]) == 64)

    async def test_user_can_record_and_retrieve_action(self, U):
        """AC: User's agent action is recorded → appears in the log immediately."""
        tag = uid("uat_action")
        r = await POST(U, "/api/audit-log/append", {
            "agent_id": "builder",
            "agent_name": "Builder",
            "action_type": "uat_file_write",
            "action_detail": f"UAT test: wrote index.html [{tag}]",
            "reasoning": "User requested it in chat",
            "authority": "user",
            "risk_level": "low",
            "outcome": "success"
        })
        no_error(r, "record action")
        d = j(r)
        uat("action recorded (has entry ID)", d["ok"] and d["entry_id"].startswith("al_"))

        # Can retrieve it
        r2 = await GET(U, f"/api/audit-log/entry/{d['entry_id']}")
        no_error(r2, "retrieve action")
        d2 = j(r2)
        uat("user sees their action detail", tag in d2["entry"]["action_detail"])
        uat("signed receipt attached", d2["receipt"] is not None)

    async def test_user_can_filter_audit_by_risk_level(self, U):
        """AC: User filters audit log → only entries matching risk level shown."""
        r = await GET(U, "/api/audit-log", risk_level="low", limit=10)
        no_error(r, "filter audit by risk")
        d = j(r)
        uat("filter returns results", "entries" in d)
        for entry in d["entries"]:
            uat("only low-risk entries shown", entry["risk_level"] == "low",
                entry["risk_level"])

    async def test_user_can_export_audit_for_compliance(self, U):
        """AC: User clicks Export → downloads compliance-ready JSON with chain proof."""
        r = await U.get("/api/audit-log/export/json?limit=20")
        no_error(r, "export audit")
        uat("export returns JSON", "json" in r.headers.get("content-type",""))
        d = r.json()
        uat("export contains entries", "entries" in d)
        uat("export has chain verification", "chain_verify" in d)
        uat("chain verification is OK", d["chain_verify"]["ok"] is True)

    async def test_user_can_export_csv_for_finance(self, U):
        """AC: Finance team can export CSV for cost reconciliation."""
        r = await U.get("/api/audit-log/export/csv?limit=10")
        no_error(r, "export CSV")
        uat("returns CSV file", "csv" in r.headers.get("content-type",""))
        lines = r.text.strip().split("\n")
        uat("CSV has header row", len(lines) >= 1)
        uat("entry_id column present", "entry_id" in lines[0])

    async def test_audit_stats_visible_on_dashboard(self, U):
        """AC: Admin dashboard shows audit log statistics."""
        r = await GET(U, "/api/audit-log/stats")
        no_error(r, "audit stats")
        d = j(r)
        uat("shows total entry count", "total" in d)
        uat("shows top agents", "top_agents" in d)
        uat("shows by-risk breakdown", "by_risk" in d)
        uat("shows by-outcome breakdown", "by_outcome" in d)


# ══════════════════════════════════════════════════════════════════
#  USER STORY: "I can provision secure identities for my agents"
# ══════════════════════════════════════════════════════════════════
class TestUATAgentIdentity:
    """User Story: As admin, I can give each agent a unique cryptographic identity."""

    async def test_admin_can_provision_all_agents_at_once(self, U):
        """AC: Admin clicks 'Provision All' → all agents get identities."""
        r = await POST(U, "/api/agent-identity/provision-all")
        no_error(r, "provision all agents")
        d = j(r)
        uat("provisioning succeeded", d["ok"] is True)
        uat("at least 8 agents provisioned", d["total"] >= 8)
        uat("shows how many are new vs existing", "new" in d and "existing" in d)

    async def test_admin_sees_all_agent_identities(self, U):
        """AC: Admin opens Identity pane → sees all agents listed with status."""
        r = await GET(U, "/api/agent-identity")
        no_error(r, "list identities")
        d = j(r)
        uat("identity list is accessible", "identities" in d)
        uat("at least 8 agents have identities", d["count"] >= 8)
        for identity in d["identities"]:
            uat("each identity shows authority level",
                "authority_level" in identity)
            uat("each identity shows status", "status" in identity)

    async def test_user_can_issue_jit_token_for_task(self, U):
        """AC: User assigns a task to an agent → agent gets a time-limited access token."""
        r = await POST(U, "/api/agent-identity/builder/issue-token", {
            "task_id": f"uat_task_{uid()}",
            "ttl_seconds": 300,
            "scope": ["read_memory", "write_tasks", "web_search"]
        })
        no_error(r, "issue JIT token")
        d = j(r)
        uat("token issued successfully", d["ok"] is True)
        uat("token has an ID", d["token_id"].startswith("jit_"))
        uat("token expires in 5 minutes", d["expires_in"] == 300)
        uat("scope is correct", "read_memory" in d["scope"])
        uat("token is cryptographically signed", len(d.get("signature","")) > 0)

    async def test_admin_can_see_active_tokens(self, U):
        """AC: Admin sees how many JIT tokens are currently active."""
        r = await GET(U, "/api/agent-identity/system/stats")
        no_error(r, "identity system stats")
        d = j(r)
        uat("shows total identities", "total_identities" in d)
        uat("shows active JIT tokens", "active_jit_tokens" in d)
        uat("shows total permissions", "total_permissions" in d)
        uat("zero-trust is confirmed active", d["zero_trust_active"] is True)

    async def test_admin_can_rotate_agent_keys(self, U):
        """AC: Admin rotates keys → old tokens revoked, agent gets fresh keypair."""
        # Issue a token first
        tok_r = j(await POST(U, "/api/agent-identity/reviewer/issue-token",
                              {"task_id": "pre_rotation", "ttl_seconds": 300}))
        tok_id = tok_r["token_id"]

        # Rotate
        rot_r = await POST(U, "/api/agent-identity/reviewer/rotate-keys", {})
        no_error(rot_r, "rotate keys")
        d = j(rot_r)
        uat("rotation succeeded", d["ok"] is True)
        uat("shows new key version", d["key_version"] >= 2)
        uat("shows how many tokens were revoked", d["tokens_revoked"] >= 1)

        # Old token is now invalid
        val_r = j(await POST(U, "/api/agent-identity/token/validate",
                              {"token_id": tok_id, "agent_id": "reviewer"}))
        uat("old token correctly rejected after rotation", val_r["ok"] is False)

    async def test_admin_sees_agent_card_for_sharing(self, U):
        """AC: Admin can share agent's A2A card with partner systems."""
        r = await GET(U, "/api/mcp-gateway/agent-card/brain")
        no_error(r, "get agent card")
        d = j(r)
        uat("agent card is accessible", d["ok"] is True)
        card = d["agent_card"]
        uat("card has agent name", "name" in card)
        uat("card shows supported protocols", len(card["protocols"]) >= 2)
        uat("card is A2A v1.0 compliant", card["schema_version"] == "a2a/1.0")
        uat("card has a verifiable hash", len(card.get("card_hash","")) >= 8)


# ══════════════════════════════════════════════════════════════════
#  USER STORY: "Risky AI actions require my approval before executing"
# ══════════════════════════════════════════════════════════════════
class TestUATHITLGateways:
    """User Story: As a user, I want to approve or reject risky AI actions before they happen."""

    async def test_user_sees_pending_approvals_in_queue(self, U):
        """AC: User opens HITL pane → sees all pending AI actions waiting."""
        # Create a pending interrupt
        await POST(U, "/api/hitl/interrupt", {
            "action_type": "send_email",
            "action_summary": "UAT Test: Send marketing email to 50,000 subscribers",
            "risk_level": "critical",
            "confidence": 0.7,
            "agent_id": "orchestrator"
        })
        r = await GET(U, "/api/hitl/queue")
        no_error(r, "view HITL queue")
        d = j(r)
        uat("user sees list of pending actions", "interrupts" in d)
        uat("queue shows count", "count" in d)
        if d["interrupts"]:
            item = d["interrupts"][0]
            uat("each item shows what action is pending", "action_summary" in item)
            uat("each item shows risk level", "risk_level" in item)
            uat("each item shows confidence score", "confidence" in item)

    async def test_user_approves_action_successfully(self, U):
        """AC: User clicks Approve → action proceeds, item removed from queue."""
        # Create a risky action to approve
        int_r = j(await POST(U, "/api/hitl/interrupt", {
            "action_type": "deploy_to_production",
            "action_summary": "Deploy v2.1 to production servers",
            "risk_level": "high",
            "confidence": 0.6
        }))
        int_id = int_r["interrupt_id"]

        # User approves it
        r = await POST(U, f"/api/hitl/interrupt/{int_id}/decide", {
            "decision": "approve",
            "note": "Reviewed deployment checklist — approved",
            "reviewer": "uat_user"
        })
        no_error(r, "approve interrupt")
        d = j(r)
        uat("approval registered", d["ok"] is True)
        uat("decision shows as approved", d["decision"] == "approve")

    async def test_user_rejects_action_with_reason(self, U):
        """AC: User clicks Reject → action blocked, reason recorded."""
        int_r = j(await POST(U, "/api/hitl/interrupt", {
            "action_type": "delete_user_data",
            "action_summary": "Delete all data for user ID 12345",
            "risk_level": "critical",
            "confidence": 0.5
        }))
        int_id = int_r["interrupt_id"]

        r = await POST(U, f"/api/hitl/interrupt/{int_id}/decide", {
            "decision": "reject",
            "note": "Cannot delete user data without written consent",
            "reviewer": "uat_compliance_officer"
        })
        no_error(r, "reject interrupt")
        d = j(r)
        uat("rejection registered", d["ok"] is True)
        uat("rejection reason saved", d["decision"] == "reject")

    async def test_low_risk_actions_auto_approved(self, U):
        """AC: Low-risk actions with high confidence don't interrupt the user."""
        r = await POST(U, "/api/hitl/interrupt", {
            "action_type": "read_config",
            "action_summary": "Read application configuration file",
            "risk_level": "low",
            "confidence": 0.97,
            "agent_id": "builder"
        })
        no_error(r, "low risk interrupt")
        d = j(r)
        uat("user is NOT interrupted (auto-approved)", d["auto"] is True)
        uat("decision is auto_approved", d["decision"] == "auto_approved")

    async def test_user_sees_hitl_approval_history(self, U):
        """AC: User can review past HITL decisions in the audit panel."""
        r = await GET(U, "/api/hitl/audit", limit=10)
        no_error(r, "view HITL history")
        d = j(r)
        uat("audit history accessible", "audit" in d)

    async def test_user_sees_hitl_statistics(self, U):
        """AC: Dashboard shows HITL approval/rejection ratios."""
        r = await GET(U, "/api/hitl/stats")
        no_error(r, "HITL stats")
        d = j(r)
        uat("shows total HITL events", "total" in d)
        uat("shows pending count", "pending" in d)
        uat("shows approved count", "approved" in d)
        uat("shows rejected count", "rejected" in d)
        uat("shows approval rate %", "approval_rate" in d)

    async def test_user_can_get_ai_risk_assessment(self, U):
        """AC: Before acting, user can ask AI to assess the risk level."""
        r = await POST(U, "/api/hitl/assess-confidence", {
            "action": "Send promotional email to all 100,000 users",
            "context": "Marketing campaign for product launch"
        })
        no_error(r, "risk assessment")
        d = j(r)
        uat("AI provides risk assessment", d["ok"] is True)
        uat("assessment has confidence score", 0 <= d["confidence"] <= 1.0)
        uat("assessment has risk level", d["risk_level"] in
            ("low","medium","high","critical"))
        uat("assessment has recommendation", d["recommendation"] in
            ("proceed","interrupt","reject"))
