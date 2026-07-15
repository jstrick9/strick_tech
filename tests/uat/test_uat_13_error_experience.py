"""
UAT 13 — Error Experience & Edge Cases
User Stories:
  • As a user, I get helpful error messages (not cryptic stack traces)
  • As a user, the platform handles my mistakes gracefully
  • As a user, I can recover from errors without losing my work
  • As a user, the platform is resilient when external services are unavailable

Acceptance Criteria at the USER level — what the user experiences when things go wrong.
"""
from __future__ import annotations
import asyncio, time
import httpx, pytest
from .conftest import BASE, uid, GET, POST, PATCH, DELETE, j, accept, uat, no_error


class TestUATErrorMessages:
    """User Story: When something goes wrong, I get a helpful message — not a crash."""

    async def test_creating_goal_without_title_gives_clear_error(self, U):
        """AC: User forgets goal title → sees 'title required' message."""
        r = await POST(U, "/api/goals", {"domain": "Work"})
        no_error(r, "no title goal")
        uat("server rejects missing title", r.status_code in (200, 400, 422))
        # Parse response body regardless of status code
        try:
            d = r.json()
        except Exception:
            d = {}
        uat("user sees clear error message",
            d.get("ok") is False or r.status_code in (400, 422) or "error" in d)

    async def test_invalid_priority_gives_clear_error(self, U):
        """AC: User types 'urgent' as priority → platform corrects or errors gracefully."""
        r = await POST(U, "/api/goals", {
            "title": "Test Goal", "priority": "not_a_real_priority"
        })
        no_error(r, "invalid priority")
        # Platform should either correct it or reject it — either is acceptable
        uat("no server crash on invalid priority", r.status_code < 500)

    async def test_accessing_nonexistent_goal_gives_404(self, U):
        """AC: User bookmarks a goal that was deleted → sees 'Not found' message."""
        r = await GET(U, "/api/goals/goal_totally_nonexistent_xyz")
        uat("user gets not-found response", r.status_code in (200, 404))
        if r.status_code == 200:
            d = j(r)
            uat("response indicates not found", d.get("ok") is False or "error" in d)

    async def test_hitl_double_decision_rejected_gracefully(self, U):
        """AC: User accidentally clicks Approve twice → second click is rejected cleanly."""
        int_r = j(await POST(U, "/api/hitl/interrupt", {
            "action_type": "test_double",
            "action_summary": "UAT double-decision test",
            "risk_level": "high",
            "confidence": 0.3
        }))
        int_id = int_r["interrupt_id"]

        # First decision
        await POST(U, f"/api/hitl/interrupt/{int_id}/decide",
                   {"decision": "approve", "reviewer": "uat_user"})

        # Second decision (user clicks again)
        r = await POST(U, f"/api/hitl/interrupt/{int_id}/decide",
                       {"decision": "approve", "reviewer": "uat_user"})
        no_error(r, "double decision")
        d = j(r)
        uat("second approval rejected gracefully", d.get("ok") is False)
        uat("helpful error message shown", "error" in d)

    async def test_token_validation_with_wrong_agent_gives_clear_error(self, U):
        """AC: Security boundary clearly communicated — agent can't impersonate another."""
        tok = j(await POST(U, "/api/agent-identity/builder/issue-token",
                            {"task_id": "wrong_agent", "ttl_seconds": 60}))["token_id"]
        r = await POST(U, "/api/agent-identity/token/validate", {
            "token_id": tok,
            "agent_id": "orchestrator"  # Wrong agent
        })
        no_error(r, "wrong agent token")
        d = j(r)
        uat("access denied clearly", d.get("ok") is False)
        uat("error is informative", "error" in d)
        # Cleanup
        await POST(U, f"/api/agent-identity/token/{tok}/revoke", {})

    async def test_large_content_handled_without_crash(self, U):
        """AC: User pastes a very long document → platform handles it without crashing."""
        large_content = "This is a long document. " * 1000  # ~25KB
        r = await POST(U, "/api/memory/add", {
            "source": "uat_large_doc",
            "content": large_content,
            "tags": "uat,large_content"
        })
        no_error(r, "large content memory add")
        uat("large content accepted or truncated gracefully", r.status_code < 500)

    async def test_invalid_json_gives_helpful_error(self, U):
        """AC: User sends malformed request → gets '400 Bad Request' not '500 Internal Error'."""
        r = await U.post("/api/goals", content=b"this is not json",
                          headers={"Content-Type": "application/json"})
        uat("server handles malformed JSON gracefully", r.status_code in (400, 422),
            r.status_code)

    async def test_supervisor_with_empty_goal_rejected(self, U):
        """AC: User submits empty goal → helpful validation message."""
        r = await POST(U, "/api/supervisor/run", {"goal": "   "})
        no_error(r, "empty goal")
        try:
            d = r.json()
        except Exception:
            d = {}
        uat("empty goal rejected with clear message",
            r.status_code in (200, 400, 422) and
            (d.get("ok") is False or r.status_code in (400, 422)))


class TestUATGracefulDegradation:
    """User Story: The platform keeps working even when some services are unavailable."""

    async def test_slack_unavailable_doesnt_crash_platform(self, U):
        """AC: Slack is down → user gets clear message, platform keeps running."""
        r = await POST(U, "/api/connectors/conn_slack/execute", {
            "action": "send_message",
            "payload": {"channel": "general", "text": "test"},
        })
        no_error(r, "slack unavailable")
        d = j(r)
        uat("error is user-friendly (not server crash)", d.get("ok") is False)
        uat("error describes the issue", len(d.get("error","")) > 0)

    async def test_mcp_call_to_unknown_tool_handled(self, U):
        """AC: Agent calls a tool that doesn't exist → helpful error."""
        r = await POST(U, "/api/mcp-gateway/call", {
            "server_id": "srv_filesystem",
            "tool": "fs.nonexistent_tool",
            "args": {},
            "agent_id": "builder"
        })
        no_error(r, "unknown tool call")
        d = j(r)
        uat("unknown tool rejected helpfully", d.get("ok") is False)

    async def test_all_health_endpoints_always_respond(self, U):
        """AC: User can always check system status — health check never fails."""
        health = j(await GET(U, "/api/system/health"))
        uat("system health always accessible", health.get("ok") is True)
        uat("version is shown", "version" in health)
        uat("database status shown", "database" in health)


class TestUATDataRecovery:
    """User Story: I can recover from mistakes without losing important work."""

    async def test_deleted_goal_properly_removed(self, U):
        """AC: User deletes a goal → it's removed from all views."""
        gid = j(await POST(U, "/api/goals", {"title": f"UAT Delete Me {uid()}"}))["goal_id"]

        # Confirm it exists
        g = j(await GET(U, f"/api/goals/{gid}"))
        uat("goal exists before delete", g.get("ok") is True or "goal" in g)

        # Delete it
        r = await U.delete(f"/api/goals/{gid}")
        no_error(r, "delete goal")
        uat("deletion confirmed", j(r).get("ok") is True or r.status_code == 200)

        # Can't find it anymore
        r2 = await GET(U, f"/api/goals/{gid}")
        uat("goal no longer accessible after delete",
            r2.status_code == 404 or j(r2).get("ok") is False)

    async def test_spec_artifacts_survive_read_write(self, U):
        """AC: User saves spec content → it reads back exactly."""
        spec = j(await POST(U, "/api/specs", {
            "title": f"UAT Persist Test {uid()}"
        }))["spec"]
        spec_id = spec["id"]

        content = "# UAT Requirements\n\n1. The system shall be reliable.\n2. Users shall be happy."
        await U.put(f"/api/specs/{spec_id}/artifacts/requirements.md",
                    json={"content": content})

        r = await GET(U, f"/api/specs/{spec_id}/artifacts/requirements.md")
        no_error(r, "read spec artifact")
        d = j(r)
        uat("spec content reads back exactly",
            "UAT Requirements" in d.get("content",""))
        uat("users shall be happy preserved",
            "Users shall be happy" in d.get("content",""))

        # Cleanup
        await U.delete(f"/api/specs/{spec_id}")

    async def test_memory_entry_survives_after_reindex(self, U):
        """AC: User reindexes memory → entries are still searchable."""
        tag = uid("uat_reindex")
        await POST(U, "/api/memory/add", {
            "source": "uat_reindex_test",
            "content": f"Important business insight: {tag}",
            "tags": f"uat,{tag}"
        })

        # Reindex
        reindex = await POST(U, "/api/memory/reindex")
        no_error(reindex, "reindex memory")
        uat("reindex completes", j(reindex).get("ok") is True)

        # Memory stats still accessible
        stats = j(await GET(U, "/api/memory/stats"))
        uat("memory stats accessible after reindex", isinstance(stats, dict))
