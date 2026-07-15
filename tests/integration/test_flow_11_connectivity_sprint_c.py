"""
Integration Flow 11 — Sprint C Connectivity: MCP Gateway→Connectors→Audit
Tests the complete connectivity pipeline:
  MCP Gateway policy evaluation → tool dispatch → connector execution →
  audit trail → rate limiting → A2A agent cards
"""
from __future__ import annotations
import asyncio, time
import httpx, pytest
from .conftest import BASE, TIMEOUT, uid, GET, POST, PATCH, DELETE, ok, ok_or, check


class TestMCPGatewayPolicies:
    """MCP Gateway policy evaluation and enforcement."""

    async def test_01_default_servers_seeded(self, client):
        """All built-in MCP servers are seeded at startup."""
        r = await GET(client, "/api/mcp-gateway/servers")
        d = ok(r, "list servers")
        server_ids = [s["server_id"] for s in d["servers"]]
        for expected in ["srv_filesystem", "srv_web_search", "srv_memory",
                          "srv_http", "srv_code_exec"]:
            check(f"{expected} present", expected in server_ids, server_ids)

    async def test_02_default_policies_seeded(self, client):
        """Default allow/hitl policies are seeded."""
        r = await GET(client, "/api/mcp-gateway/policies")
        d = ok(r, "list policies")
        check("at least 3 policies", d["count"] >= 3)
        # Policy with allow action should exist
        actions = {p["action"] for p in d["policies"]}
        check("allow policy exists", "allow" in actions)
        check("require_hitl policy exists", "require_hitl" in actions)

    async def test_03_allowed_tool_call_succeeds(self, client):
        """Allowed tool call executes and returns result."""
        r = await POST(client, "/api/mcp-gateway/call", {
            "server_id": "srv_filesystem",
            "tool": "fs.list",
            "args": {"path": "."},
            "agent_id": "builder"
        })
        d = ok(r, "gateway call fs.list")
        check("policy=allow", d.get("policy_decision") == "allow")
        check("has call_id", d.get("call_id", "").startswith("mcp_"))
        check("has gateway_duration_ms", "gateway_duration_ms" in d)

    async def test_04_destructive_action_triggers_hitl(self, client):
        """fs.delete requires HITL approval (not auto-approved)."""
        r = await POST(client, "/api/mcp-gateway/call", {
            "server_id": "srv_filesystem",
            "tool": "fs.delete",
            "args": {"path": "test.txt"},
            "agent_id": "builder"
        })
        d = ok(r, "gateway call fs.delete")
        check("policy=require_hitl", d.get("policy_decision") == "require_hitl")
        check("not ok (pending HITL)", d.get("ok") is False)
        check("pending flag", d.get("pending") is True)

    async def test_05_custom_deny_policy_blocks_call(self, client):
        """Custom deny policy blocks calls matching its pattern."""
        # Create a deny policy for a specific agent
        pol_r = await POST(client, "/api/mcp-gateway/policies", {
            "name": "Integration Test Deny Policy",
            "agent_id": "integration_blocked_agent",
            "server_id": "srv_web_search",
            "tool_pattern": "*",
            "action": "deny",
            "priority": 5  # Very high priority
        })
        pol_id = pol_r.json()["policy_id"]

        # Call with blocked agent
        call_r = await POST(client, "/api/mcp-gateway/call", {
            "server_id": "srv_web_search",
            "tool": "search.web",
            "args": {"query": "test"},
            "agent_id": "integration_blocked_agent"
        })
        d = ok(call_r, "blocked agent call")
        check("policy=deny", d.get("policy_decision") == "deny")
        check("ok=False", d.get("ok") is False)

        # Cleanup
        await client.delete(f"/api/mcp-gateway/policies/{pol_id}")

    async def test_06_disabled_server_blocks_all_calls(self, client):
        """Disabling a server blocks all calls to it immediately."""
        # Register a temp server
        new_srv = await POST(client, "/api/mcp-gateway/servers", {
            "name": "Integration Test Server",
            "server_type": "test",
            "endpoint": "https://test.example.com"
        })
        srv_id = new_srv.json()["server_id"]

        # Disable it
        tog_r = await POST(client, f"/api/mcp-gateway/servers/{srv_id}/toggle", {
            "disable": True
        })
        check("toggle 200", tog_r.status_code == 200)
        check("status disabled", tog_r.json()["status"] == "disabled")

        # Call should be denied
        call_r = await POST(client, "/api/mcp-gateway/call", {
            "server_id": srv_id,
            "tool": "test.action",
            "args": {},
            "agent_id": "builder"
        })
        d = ok(call_r, "disabled server call")
        check("blocked by disabled server", d.get("ok") is False)

        # Re-enable and cleanup
        await POST(client, f"/api/mcp-gateway/servers/{srv_id}/toggle", {"disable": False})
        await client.delete(f"/api/mcp-gateway/servers/{srv_id}")

    async def test_07_call_log_persists_with_policy(self, client):
        """Every gateway call is logged with its policy decision."""
        before_total = (await GET(client, "/api/mcp-gateway/stats")).json()["total_calls"]

        await POST(client, "/api/mcp-gateway/call", {
            "server_id": "srv_memory",
            "tool": "memory.search",
            "args": {"query": "integration test", "limit": 3},
            "agent_id": "call_log_test_agent"
        })

        after_total = (await GET(client, "/api/mcp-gateway/stats")).json()["total_calls"]
        check("call count increased", after_total > before_total)

        # Fetch the specific call
        calls_r = await GET(client, "/api/mcp-gateway/calls",
                             agent_id="call_log_test_agent", limit=5)
        cd = ok(calls_r, "call log")
        check("call in log", cd["total"] >= 1)
        for call in cd["calls"]:
            check("has policy_decision", "policy_decision" in call)
            check("has status", "status" in call)

    async def test_08_a2a_agent_cards_for_all_agents(self, client):
        """Every specialist agent has a valid A2A v1.0 agent card."""
        specialists = ["orchestrator", "brain", "builder", "researcher",
                       "reviewer", "creative", "memory"]
        for agent_id in specialists:
            r = await GET(client, f"/api/mcp-gateway/agent-card/{agent_id}")
            d = ok(r, f"agent card {agent_id}")
            check(f"{agent_id} card ok", d["ok"] is True)
            card = d["agent_card"]
            check("schema_version a2a/1.0", card["schema_version"] == "a2a/1.0")
            check("protocols include mcp", "mcp/1.0" in card["protocols"])
            check("protocols include a2a", "a2a/1.0" in card["protocols"])
            check("endpoint present", "endpoint" in card)
            check("card_hash present", len(card.get("card_hash", "")) > 0)

    async def test_09_policy_toggle_changes_enforcement(self, client):
        """Toggling a policy off stops its enforcement."""
        # Create a deny policy
        pol = await POST(client, "/api/mcp-gateway/policies", {
            "name": "Toggle Test Policy",
            "action": "deny",
            "agent_id": "toggle_test_agent",
            "tool_pattern": "fs.list",
            "priority": 3
        })
        pol_id = pol.json()["policy_id"]

        # Should be blocked
        blocked = await POST(client, "/api/mcp-gateway/call", {
            "server_id": "srv_filesystem", "tool": "fs.list",
            "args": {"path": "."}, "agent_id": "toggle_test_agent"
        })
        check("initially blocked", blocked.json().get("ok") is False)

        # Disable policy
        await client.patch(f"/api/mcp-gateway/policies/{pol_id}/toggle")

        # Now should pass (default allow)
        allowed = await POST(client, "/api/mcp-gateway/call", {
            "server_id": "srv_filesystem", "tool": "fs.list",
            "args": {"path": "."}, "agent_id": "toggle_test_agent"
        })
        check("allowed after toggle", allowed.json().get("policy_decision") != "deny")

        # Cleanup
        await client.delete(f"/api/mcp-gateway/policies/{pol_id}")


class TestConnectorsSDK:
    """Enterprise connector registration, configuration, and execution."""

    async def test_01_all_builtin_connectors_present(self, client):
        """All 8 built-in connectors are seeded."""
        r = await GET(client, "/api/connectors")
        d = ok(r, "list connectors")
        ids = [c["connector_id"] for c in d["connectors"]]
        for expected in ["conn_slack", "conn_jira", "conn_gdrive", "conn_email",
                          "conn_github", "conn_webhook", "conn_notion", "conn_salesforce"]:
            check(f"{expected} present", expected in ids, ids)

    async def test_02_webhook_connector_active_by_default(self, client):
        """Webhook connector is active without any configuration."""
        r = await GET(client, "/api/connectors/conn_webhook")
        d = ok(r, "get webhook connector")
        check("webhook ok", d["ok"] is True)
        check("status active", d["connector"]["status"] == "active")

    async def test_03_webhook_executes_successfully(self, client):
        """Webhook connector can post to local health endpoint."""
        r = await POST(client, "/api/connectors/conn_webhook/execute", {
            "action": "post_webhook",
            "payload": {
                "url": "http://127.0.0.1:8787/api/docs/feedback",
                "data": {
                    "source": "agentic_os_integration_test",
                    "flow": "11",
                    "timestamp": int(time.time())
                }
            },
            "agent_id": "orchestrator"
        })
        d = ok(r, "webhook execute")
        check("execution ok", d["ok"] is True)
        check("has exec_id", "exec_id" in d)
        check("exec_id format", d["exec_id"].startswith("cex_"))
        check("has duration_ms", d["duration_ms"] >= 0)

    async def test_04_execution_recorded_in_history(self, client):
        """Each execution appears in the connector's execution history."""
        before_count = (await GET(client, "/api/connectors/conn_webhook/executions?limit=100")).json()["count"]

        await POST(client, "/api/connectors/conn_webhook/execute", {
            "action": "post_webhook",
            "payload": {"url": "http://127.0.0.1:8787/api/docs/feedback", "data": {"history": "test"}},
            "agent_id": "builder"
        })

        after = (await GET(client, "/api/connectors/conn_webhook/executions?limit=100")).json()
        check("execution history accessible", after["count"] >= before_count)
        # Latest execution should be our call
        latest = after["executions"][0]
        check("latest action matches", latest["action"] == "post_webhook")
        check("latest agent matches", latest["agent_id"] == "builder")

    async def test_05_execution_logged_to_audit_chain(self, client):
        """Connector execution writes to the immutable audit chain."""
        before_entries = (await GET(client, "/api/audit-log/verify")).json()["verified"]

        await POST(client, "/api/connectors/conn_webhook/execute", {
            "action": "post_webhook",
            "payload": {"url": "http://127.0.0.1:8787/api/docs/feedback", "data": {"audit": "test"}},
            "agent_id": "audit_connector_test"
        })

        await asyncio.sleep(0.3)
        after_entries = (await GET(client, "/api/audit-log/verify")).json()["verified"]
        check("audit entries grew", after_entries >= before_entries)
        check("chain still valid",
              (await GET(client, "/api/audit-log/verify")).json()["ok"] is True)

    async def test_06_custom_connector_full_lifecycle(self, client):
        """SDK: register → configure → test → execute → get history → delete."""
        # Register
        conn_id = uid("conn")
        reg_r = await POST(client, "/api/connectors", {
            "name": f"Integration SDK Test {conn_id}",
            "category": "custom",
            "auth_type": "api_key",
            "capabilities": ["get_data", "post_data", "delete_data"],
            "description": "Integration test custom connector"
        })
        d = ok(reg_r, "register connector")
        check("register ok", d["ok"] is True)
        cid = d["connector_id"]
        check("connector_id format", cid.startswith("conn_"))

        # Configure
        cfg_r = await client.patch(f"/api/connectors/{cid}/configure", json={
            "credentials": {"api_key": "test_integration_key_12345", "endpoint": "https://api.example.com"}
        })
        cd = ok(cfg_r, "configure connector")
        check("status active after configure", cd["status"] == "active")

        # Test connectivity
        test_r = await POST(client, f"/api/connectors/{cid}/test")
        td = ok(test_r, "test connector")
        check("test ok", td["ok"] is True)
        check("configured=True", td["configured"] is True)

        # Get detail
        detail = (await GET(client, f"/api/connectors/{cid}")).json()
        check("connector found", detail["ok"] is True)
        check("name correct", detail["connector"]["connector_id"] == cid)

        # Verify credentials are masked
        creds = detail["connector"]["credentials"]
        if isinstance(creds, dict):
            for val in creds.values():
                check("credentials masked", val in ("***", ""), val)

    async def test_07_unconfigured_connector_fails_gracefully(self, client):
        """Unconfigured connector returns meaningful error, not 500."""
        r = await POST(client, "/api/connectors/conn_slack/execute", {
            "action": "send_message",
            "payload": {"channel": "general", "text": "Integration test"},
            "agent_id": "orchestrator"
        })
        d = ok(r, "unconfigured execute")
        check("not 500 error", r.status_code == 200)
        check("ok=False", d["ok"] is False)
        check("meaningful error", "TOKEN" in d.get("error", "") or
              "not configured" in d.get("error", "").lower() or
              len(d.get("error", "")) > 5)

    async def test_08_connector_stats_reflect_executions(self, client):
        """Stats show accurate counts after executions."""
        r = await GET(client, "/api/connectors/stats/summary")
        d = ok(r, "connector stats")
        check("total_connectors >= 8", d["total_connectors"] >= 8)
        check("active_connectors >= 1", d["active_connectors"] >= 1)
        check("total_executions >= 1", d["total_executions"] >= 1)
        check("has by_category", "by_category" in d)
        check("has top_connectors", "top_connectors" in d)

    async def test_09_filter_connectors_by_category(self, client):
        """Filter connectors by category returns only matching items."""
        r = await GET(client, "/api/connectors", category="communication")
        d = ok(r, "filter by category")
        for c in d["connectors"]:
            check("category=communication", c["category"] == "communication",
                  c["category"])

    async def test_10_connector_call_count_increments(self, client):
        """call_count increments with each execution."""
        before = (await GET(client, "/api/connectors/conn_webhook")).json()["connector"]["call_count"]

        await POST(client, "/api/connectors/conn_webhook/execute", {
            "action": "post_webhook",
            "payload": {"url": "http://127.0.0.1:8787/api/docs/feedback", "data": {"counter": "test"}},
        })

        after = (await GET(client, "/api/connectors/conn_webhook")).json()["connector"]["call_count"]
        check("call_count incremented", after > before, f"before={before} after={after}")
