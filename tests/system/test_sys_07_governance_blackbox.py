"""
System Test 07 — Governance Layer (Black-Box)
Sprint A features treated as a complete, opaque subsystem.

System-level assertions:
  • Audit chain is cryptographically self-consistent from the outside
  • Agent identity system enforces access control end-to-end
  • HITL gates operate correctly under real workflow conditions
  • The governance layer survives concurrent pressure
"""
from __future__ import annotations
import asyncio, time
import httpx, pytest
from .conftest import BASE, uid, ts, GET, POST, PATCH, DELETE, must, check, no_server_error

# ══════════════════════════════════════════════════════════════════
#  AUDIT LOG — BLACK BOX SYSTEM TESTS
# ══════════════════════════════════════════════════════════════════
class TestSysAuditLogSystem:
    """Treat audit log as an opaque persistent ledger — verify from outside."""

    async def test_audit_chain_self_heals_across_platform_actions(self, C):
        """Any platform action that writes to audit log keeps chain valid."""
        # Record baseline
        before = must(await GET(C, "/api/audit-log/verify"), label="verify before")
        check("chain valid before", before.get("ok") is True)
        entries_before = before.get("verified", 0)

        # Trigger several platform actions that write to audit log
        await POST(C, "/api/audit-log/append", {
            "agent_id": "sys_test_agent", "agent_name": "SysTest",
            "action_type": "sys_test_platform_action",
            "action_detail": "System test platform action for chain validation",
            "reasoning": "Testing audit chain integrity under load",
            "authority": "system_test", "risk_level": "low", "outcome": "success"
        })
        await POST(C, "/api/goals", {"title": f"Sys audit test {uid()}", "domain": "Work"})
        await POST(C, "/api/agent-identity/provision", {
            "agent_id": f"sys_audit_agent_{uid()}", "authority_level": "standard"
        })

        # Chain must still be valid
        await asyncio.sleep(0.2)
        after = must(await GET(C, "/api/audit-log/verify"), label="verify after")
        check("chain valid after platform actions", after.get("ok") is True)
        check("entries grew", after.get("verified", 0) > entries_before,
              f"{entries_before} → {after.get('verified')}")

    async def test_audit_export_consistency(self, C):
        """JSON and CSV exports are consistent with live verify endpoint."""
        verify = must(await GET(C, "/api/audit-log/verify"), label="verify")
        total = verify.get("verified", 0)

        # JSON export should reflect same total
        r_json = await GET(C, "/api/audit-log/export/json", limit=1000)
        no_server_error(r_json, "json export")
        exp = r_json.json()
        check("export total <= verify total", len(exp.get("entries", [])) <= total)
        check("export chain_verify embedded", "chain_verify" in exp)
        check("export chain_verify ok", exp["chain_verify"]["ok"] is True)

        # CSV export has header
        r_csv = await C.get("/api/audit-log/export/csv?limit=100")
        no_server_error(r_csv, "csv export")
        check("csv content-type", "csv" in r_csv.headers.get("content-type",""))
        lines = r_csv.text.strip().split("\n")
        check("csv has header", len(lines) >= 1)
        check("csv header has entry_id", "entry_id" in lines[0])

    async def test_audit_filter_accuracy(self, C):
        """Filters return exactly matching entries."""
        tag = uid("sys_filter")
        await POST(C, "/api/audit-log/append", {
            "agent_id": tag, "action_type": "filter_test",
            "action_detail": "filter accuracy test", "risk_level": "medium", "outcome": "success"
        })
        await asyncio.sleep(0.1)

        r = await GET(C, "/api/audit-log", agent_id=tag, limit=5)
        d = must(r, label="filter by agent")
        for entry in d.get("entries", []):
            check("filter agent matches", entry["agent_id"] == tag, entry["agent_id"])

    async def test_audit_receipt_cryptographically_present(self, C):
        """Every appended entry gets a signed cryptographic receipt."""
        r = await POST(C, "/api/audit-log/append", {
            "agent_id": "receipt_sys_test", "action_type": "receipt_verification",
            "action_detail": "Verify receipt generation at system level",
            "outcome": "success"
        })
        d = must(r, label="append for receipt")
        entry_id = d.get("entry_id", "")
        check("has entry_id", entry_id.startswith("al_"))
        check("has receipt_id", d.get("receipt_id", "").startswith("rcpt_"))
        check("has entry_hash", len(d.get("entry_hash", "")) == 64)  # SHA-256 hex

        # Fetch receipt
        r2 = await GET(C, f"/api/audit-log/receipt/{d['receipt_id']}")
        no_server_error(r2, "get receipt")

    async def test_concurrent_audit_appends_chain_stays_valid(self, C):
        """Concurrent appends do not break the hash chain."""
        tasks = []
        for i in range(10):
            tasks.append(POST(C, "/api/audit-log/append", {
                "agent_id": f"concurrent_agent_{i}",
                "action_type": "concurrent_test",
                "action_detail": f"Concurrent append {i}",
                "outcome": "success"
            }))
        results = await asyncio.gather(*tasks, return_exceptions=True)
        successes = sum(1 for r in results if not isinstance(r, Exception) and r.status_code == 200)
        check("all concurrent appends succeeded", successes == 10, successes)

        # Chain must survive concurrent writes
        verify = must(await GET(C, "/api/audit-log/verify"), label="verify after concurrent")
        check("chain valid after concurrent appends", verify.get("ok") is True)


# ══════════════════════════════════════════════════════════════════
#  AGENT IDENTITY — BLACK BOX SYSTEM TESTS
# ══════════════════════════════════════════════════════════════════
class TestSysAgentIdentitySystem:
    """Verify identity system behaves correctly from a black-box perspective."""

    async def test_identity_system_up_with_all_agents(self, C):
        """Identity system has all platform agents at startup."""
        r = await GET(C, "/api/agent-identity")
        d = must(r, label="list identities")
        check("has identities", d.get("count", 0) >= 8)
        check("zero_trust active", (await GET(C, "/api/agent-identity/system/stats")).json()["zero_trust_active"])

    async def test_jit_token_enforces_agent_boundary(self, C):
        """A token issued to agent A cannot be used to authenticate as agent B."""
        # Provision two agents
        agent_a = f"sys_agent_a_{uid()}"
        agent_b = f"sys_agent_b_{uid()}"
        for aid in [agent_a, agent_b]:
            await POST(C, "/api/agent-identity/provision", {"agent_id": aid})

        # Issue token for A
        issue = must(await POST(C, f"/api/agent-identity/{agent_a}/issue-token",
                                 {"task_id": "boundary_test", "ttl_seconds": 120}),
                      label="issue token for A")
        token_id = issue["token_id"]

        # Use as A — must succeed
        val_a = must(await POST(C, "/api/agent-identity/token/validate",
                                  {"token_id": token_id, "agent_id": agent_a}),
                      label="validate as A")
        check("valid as A", val_a.get("ok") is True)

        # Use as B — must fail
        val_b = must(await POST(C, "/api/agent-identity/token/validate",
                                  {"token_id": token_id, "agent_id": agent_b}),
                      label="validate as B")
        check("rejected as B", val_b.get("ok") is False)

        # Cleanup
        await POST(C, f"/api/agent-identity/token/{token_id}/revoke", {})

    async def test_expired_token_rejected(self, C):
        """Token with TTL=0 cannot be used (or fails quickly after creation)."""
        aid = f"sys_exp_{uid()}"
        await POST(C, "/api/agent-identity/provision", {"agent_id": aid})
        issue = must(await POST(C, f"/api/agent-identity/{aid}/issue-token",
                                 {"task_id": "expire_test", "ttl_seconds": 1}),
                      label="issue 1s token")
        token_id = issue["token_id"]
        await asyncio.sleep(2)  # Let it expire

        val = must(await POST(C, "/api/agent-identity/token/validate",
                               {"token_id": token_id, "agent_id": aid}),
                    label="validate expired")
        check("expired token rejected", val.get("ok") is False)

    async def test_key_rotation_system_wide(self, C):
        """Key rotation is safe: new tokens work, old tokens don't."""
        aid = "reviewer"  # Use existing agent
        # Issue old token
        old_tok = (await POST(C, f"/api/agent-identity/{aid}/issue-token",
                               {"task_id": "pre_rotate", "ttl_seconds": 300})).json()["token_id"]

        # Rotate
        rot = must(await POST(C, f"/api/agent-identity/{aid}/rotate-keys", {}),
                    label="rotate keys")
        check("rotation ok", rot.get("ok") is True)
        check("tokens_revoked >= 1", rot.get("tokens_revoked", 0) >= 1)

        # Old token now invalid
        val_old = (await POST(C, "/api/agent-identity/token/validate",
                               {"token_id": old_tok, "agent_id": aid})).json()
        check("old token invalid", val_old.get("ok") is False)

        # New token works
        new_tok = (await POST(C, f"/api/agent-identity/{aid}/issue-token",
                               {"task_id": "post_rotate", "ttl_seconds": 300})).json()["token_id"]
        val_new = (await POST(C, "/api/agent-identity/token/validate",
                               {"token_id": new_tok, "agent_id": aid})).json()
        check("new token valid", val_new.get("ok") is True)
        await POST(C, f"/api/agent-identity/token/{new_tok}/revoke", {})


# ══════════════════════════════════════════════════════════════════
#  HITL — BLACK BOX SYSTEM TESTS
# ══════════════════════════════════════════════════════════════════
class TestSysHITLSystem:
    """HITL subsystem as a black-box gate in real workflows."""

    async def test_hitl_gates_high_risk_actions_system_wide(self, C):
        """System-wide: critical actions always wait for human approval."""
        critical_actions = [
            ("stripe_charge", "Charge $9999 to card ending 4242"),
            ("send_email", "Send mass email to all 50,000 users"),
            ("deploy_to_production", "Deploy untested code to production"),
            ("delete_database", "Drop all tables in production database"),
        ]
        for action_type, summary in critical_actions:
            r = await POST(C, "/api/hitl/interrupt", {
                "action_type": action_type,
                "action_summary": summary,
                "risk_level": "critical",
                "confidence": 0.99,  # Even 99% confidence
                "agent_id": "orchestrator"
            })
            d = must(r, label=f"critical interrupt {action_type}")
            check(f"{action_type} not auto-approved", d.get("auto") is False, d)
            check(f"{action_type} pending", d.get("decision") == "pending")
            # Approve to clear queue
            await POST(C, f"/api/hitl/interrupt/{d['interrupt_id']}/decide",
                       {"decision": "approve", "reviewer": "sys_test"})

    async def test_hitl_queue_ordering(self, C):
        """HITL queue items are returned and can be processed in order."""
        interrupt_ids = []
        for i in range(3):
            r = await POST(C, "/api/hitl/interrupt", {
                "action_type": f"queue_order_test_{i}",
                "action_summary": f"Queue ordering test item {i}",
                "risk_level": "high",
                "confidence": 0.4
            })
            interrupt_ids.append(r.json()["interrupt_id"])

        # All should be in pending queue
        queue = must(await GET(C, "/api/hitl/queue"), label="queue")
        pending_ids = {item["id"] for item in queue.get("interrupts", [])}
        for iid in interrupt_ids:
            check(f"interrupt {iid[:12]} in queue", iid in pending_ids)

        # Process all
        for iid in interrupt_ids:
            await POST(C, f"/api/hitl/interrupt/{iid}/decide",
                       {"decision": "approve", "reviewer": "sys_ordering_test"})

    async def test_hitl_stats_accuracy(self, C):
        """HITL stats accurately reflect approval/rejection ratios."""
        before = must(await GET(C, "/api/hitl/stats"), label="stats before")
        b_approved = before.get("approved", 0)
        b_rejected = before.get("rejected", 0)

        # Create and decide 2 approvals + 1 rejection
        for _ in range(2):
            r = await POST(C, "/api/hitl/interrupt", {
                "action_type": "stats_test_approve",
                "action_summary": "Stats accuracy test",
                "risk_level": "high", "confidence": 0.3
            })
            await POST(C, f"/api/hitl/interrupt/{r.json()['interrupt_id']}/decide",
                       {"decision": "approve", "reviewer": "sys_stats"})

        r_rej = await POST(C, "/api/hitl/interrupt", {
            "action_type": "stats_test_reject",
            "action_summary": "Stats accuracy rejection",
            "risk_level": "high", "confidence": 0.2
        })
        await POST(C, f"/api/hitl/interrupt/{r_rej.json()['interrupt_id']}/decide",
                   {"decision": "reject", "reviewer": "sys_stats"})

        after = must(await GET(C, "/api/hitl/stats"), label="stats after")
        check("approved increased by 2", after.get("approved", 0) >= b_approved + 2)
        check("rejected increased by 1", after.get("rejected", 0) >= b_rejected + 1)

    async def test_hitl_audit_every_decision_recorded(self, C):
        """Every HITL decision appears in the audit trail."""
        r = await POST(C, "/api/hitl/interrupt", {
            "action_type": "audit_trail_sys_test",
            "action_summary": "Verifying audit trail",
            "risk_level": "high", "confidence": 0.35
        })
        int_id = r.json()["interrupt_id"]
        await POST(C, f"/api/hitl/interrupt/{int_id}/decide",
                   {"decision": "reject", "reviewer": "sys_audit_trail",
                    "note": "System test rejection for audit verification"})

        audit = must(await GET(C, "/api/hitl/audit", limit=20), label="hitl audit")
        decisions = [a.get("decision") for a in audit.get("audit", [])]
        check("reject decision in audit", "reject" in decisions)

    async def test_hitl_concurrent_decisions_no_conflict(self, C):
        """Multiple HITL decisions can be processed concurrently."""
        interrupt_ids = []
        for i in range(5):
            r = await POST(C, "/api/hitl/interrupt", {
                "action_type": f"concurrent_hitl_{i}",
                "action_summary": f"Concurrent HITL test {i}",
                "risk_level": "medium", "confidence": 0.4
            })
            interrupt_ids.append(r.json()["interrupt_id"])

        # Approve all concurrently
        tasks = [
            POST(C, f"/api/hitl/interrupt/{iid}/decide",
                 {"decision": "approve", "reviewer": "concurrent_sys"})
            for iid in interrupt_ids
        ]
        results = await asyncio.gather(*tasks, return_exceptions=True)
        successes = sum(1 for r in results if not isinstance(r, Exception) and r.status_code == 200)
        check("all concurrent HITL decisions processed", successes == 5, successes)
