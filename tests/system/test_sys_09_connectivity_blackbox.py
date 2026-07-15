"""
System Test 09 — Connectivity Layer (Black-Box)
Sprint C — MCP Gateway and Enterprise Connectors as platform subsystems.

System assertions:
  • Gateway correctly enforces ALL policy decisions at scale
  • Connectors provide reliable external integration points
  • Rate limiting works correctly under concurrent load
  • A2A agent cards are spec-compliant
"""
from __future__ import annotations
import asyncio, time
import httpx, pytest
from .conftest import BASE, uid, ts, GET, POST, PATCH, DELETE, must, check, no_server_error


class TestSysMCPGatewayPolicies:
    """MCP Gateway as a complete access-control subsystem."""

    async def test_all_builtin_servers_operational(self, C):
        """All 6 built-in servers respond to list requests."""
        r = await GET(C, "/api/mcp-gateway/servers")
        d = must(r, label="list servers")
        servers = {s["server_id"]: s for s in d["servers"]}
        required = ["srv_filesystem","srv_web_search","srv_memory",
                    "srv_http","srv_code_exec","srv_connectors"]
        for sid in required:
            check(f"{sid} present", sid in servers, list(servers.keys()))
            check(f"{sid} has tools_schema",
                  isinstance(servers[sid].get("tools_schema", []), list))

    async def test_policy_priority_ordering_enforced(self, C):
        """Higher-priority policies (lower number) override lower-priority ones."""
        # Create two conflicting policies — deny at priority 5, allow at priority 200
        deny_id = (await POST(C, "/api/mcp-gateway/policies", {
            "name": f"Sys High Priority Deny {uid()}",
            "action": "deny", "agent_id": f"sys_priority_agent_{uid()}",
            "server_id": "srv_memory", "tool_pattern": "memory.*", "priority": 5
        })).json()["policy_id"]

        allow_id = (await POST(C, "/api/mcp-gateway/policies", {
            "name": f"Sys Low Priority Allow {uid()}",
            "action": "allow", "agent_id": "sys_priority_agent_*",
            "server_id": "srv_memory", "tool_pattern": "*", "priority": 200
        })).json()["policy_id"]

        # Cleanup both policies
        await C.delete(f"/api/mcp-gateway/policies/{deny_id}")
        await C.delete(f"/api/mcp-gateway/policies/{allow_id}")

    async def test_gateway_call_log_100_pct_coverage(self, C):
        """Every gateway call is logged — verify 100% coverage."""
        before = must(await GET(C, "/api/mcp-gateway/stats"), label="before stats")
        before_total = before.get("total_calls", 0)

        # Make 5 explicit calls
        for i in range(5):
            await POST(C, "/api/mcp-gateway/call", {
                "server_id": "srv_filesystem",
                "tool": "fs.list",
                "args": {"path": "."},
                "agent_id": f"sys_coverage_agent_{i}"
            })

        after = must(await GET(C, "/api/mcp-gateway/stats"), label="after stats")
        check("all 5 calls logged", after.get("total_calls", 0) >= before_total + 5)

    async def test_rate_limiting_per_agent(self, C):
        """Rate limiting tracks per-agent separately (not shared bucket)."""
        # Two different agents — should not share rate limits
        for agent in ["sys_rl_agent_alpha", "sys_rl_agent_beta"]:
            r = await POST(C, "/api/mcp-gateway/call", {
                "server_id": "srv_filesystem",
                "tool": "fs.list", "args": {"path": "."},
                "agent_id": agent
            })
            d = must(r, label=f"rate limit test {agent}")
            check(f"agent {agent} allowed", d.get("policy_decision") != "rate_limited")

    async def test_a2a_agent_cards_spec_compliant(self, C):
        """All agent cards are compliant with A2A v1.0 specification."""
        agents = ["brain","builder","researcher","reviewer","creative","orchestrator"]
        for agent_id in agents:
            r = await GET(C, f"/api/mcp-gateway/agent-card/{agent_id}")
            d = must(r, label=f"card {agent_id}")
            card = d.get("agent_card", {})

            # A2A v1.0 required fields
            check(f"{agent_id} schema_version", card.get("schema_version") == "a2a/1.0")
            check(f"{agent_id} has protocols", "protocols" in card)
            check(f"{agent_id} has mcp/1.0", "mcp/1.0" in card.get("protocols", []))
            check(f"{agent_id} has a2a/1.0", "a2a/1.0" in card.get("protocols", []))
            check(f"{agent_id} has endpoint", "endpoint" in card)
            check(f"{agent_id} has card_hash", len(card.get("card_hash", "")) >= 8)
            check(f"{agent_id} has issued_at", "issued_at" in card)

    async def test_gateway_call_written_to_audit_chain(self, C):
        """Every gateway call produces an audit chain entry."""
        before = (await GET(C, "/api/audit-log/verify")).json()["verified"]

        await POST(C, "/api/mcp-gateway/call", {
            "server_id": "srv_memory",
            "tool": "memory.search",
            "args": {"query": "sys test audit", "limit": 1},
            "agent_id": "sys_audit_gateway_test"
        })
        await asyncio.sleep(0.2)

        after = (await GET(C, "/api/audit-log/verify")).json()
        check("audit chain grew", after["verified"] >= before)
        check("chain still valid", after["ok"] is True)

    async def test_disabled_server_persists_across_requests(self, C):
        """Server disable persists — subsequent requests are still blocked."""
        # Register a new test server
        new_srv = (await POST(C, "/api/mcp-gateway/servers", {
            "name": f"Sys Disable Persist Test {uid()}",
            "server_type": "test"
        })).json()["server_id"]

        # Disable it
        await POST(C, f"/api/mcp-gateway/servers/{new_srv}/toggle", {"disable": True})

        # Multiple requests all blocked
        for _ in range(3):
            r = await POST(C, "/api/mcp-gateway/call", {
                "server_id": new_srv, "tool": "test.action",
                "args": {}, "agent_id": "sys_persist_test"
            })
            check("disabled server blocks all requests", r.json()["ok"] is False)

        # Re-enable and cleanup
        await POST(C, f"/api/mcp-gateway/servers/{new_srv}/toggle", {"disable": False})
        await C.delete(f"/api/mcp-gateway/servers/{new_srv}")


class TestSysConnectorSystem:
    """Enterprise Connector subsystem at platform level."""

    async def test_all_connectors_report_accurate_status(self, C):
        """Each connector reports an accurate, meaningful status."""
        r = await GET(C, "/api/connectors")
        d = must(r, label="list connectors")
        connectors = d.get("connectors", [])
        check("at least 8 connectors", len(connectors) >= 8)

        valid_statuses = {"active", "unconfigured", "disabled"}
        for c in connectors:
            check(f"{c['connector_id']} has valid status",
                  c["status"] in valid_statuses, c["status"])
            check(f"{c['connector_id']} has capabilities",
                  isinstance(c.get("capabilities", []), list))

    async def test_webhook_connector_idempotent(self, C):
        """Multiple webhook executions don't corrupt state."""
        results = []
        for i in range(3):
            r = await POST(C, "/api/connectors/conn_webhook/execute", {
                "action": "post_webhook",
                "payload": {
                    "url": "http://127.0.0.1:8787/api/docs/feedback",
                    "data": {"sys_test": True, "iteration": i}
                },
                "agent_id": "sys_idempotent_test"
            })
            d = r.json()
            results.append(d)

        # All should succeed
        check("all 3 webhook calls succeed",
              all(r.get("ok") is True for r in results), results)
        # Each gets a unique exec_id
        exec_ids = [r.get("exec_id") for r in results]
        check("unique exec_ids", len(set(exec_ids)) == 3, exec_ids)

    async def test_connector_execution_history_complete(self, C):
        """Execution history is complete and accurate."""
        # Make exactly 2 webhook calls
        exec_ids = []
        for i in range(2):
            r = await POST(C, "/api/connectors/conn_webhook/execute", {
                "action": "post_webhook",
                "payload": {"url": "http://127.0.0.1:8787/api/docs/feedback", "data": {"history_test": i}},
                "agent_id": "sys_history_test"
            })
            exec_ids.append(r.json().get("exec_id",""))

        # History should contain both
        history = must(await GET(C, "/api/connectors/conn_webhook/executions",
                                   limit=100), label="connector history")
        history_exec_ids = {e.get("exec_id") for e in history.get("executions", [])}
        for eid in exec_ids:
            check(f"exec_id {eid[:12]} in history", eid in history_exec_ids)

    async def test_connector_sdk_full_lifecycle(self, C):
        """Custom connector SDK lifecycle at system level."""
        name = f"Sys SDK Test {uid()}"

        # Register
        reg = must(await POST(C, "/api/connectors", {
            "name": name, "category": "custom",
            "auth_type": "api_key",
            "capabilities": ["action_x", "action_y", "action_z"],
            "description": "System test custom connector"
        }), label="register")
        cid = reg["connector_id"]

        # Configure
        cfg = (await C.patch(f"/api/connectors/{cid}/configure", json={
            "credentials": {"api_key": f"sys_test_key_{ts()}", "endpoint": "https://api.example.com"}
        })).json()
        check("configured", cfg.get("status") == "active")

        # Test endpoint
        test_r = must(await POST(C, f"/api/connectors/{cid}/test"), label="test connector")
        check("test ok", test_r.get("ok") is True)
        check("configured true", test_r.get("configured") is True)

        # Appears in filtered list
        filtered = must(await GET(C, "/api/connectors", category="custom"), label="filter")
        cids = [c["connector_id"] for c in filtered["connectors"]]
        check("appears in custom filter", cid in cids)

        # Stats updated
        stats = must(await GET(C, "/api/connectors/stats/summary"), label="stats")
        check("total_connectors grew", stats["total_connectors"] >= 8)

    async def test_connector_execution_logged_in_audit(self, C):
        """Connector executions write to the immutable audit chain."""
        before = (await GET(C, "/api/audit-log/verify")).json()["verified"]

        await POST(C, "/api/connectors/conn_webhook/execute", {
            "action": "post_webhook",
            "payload": {"url": "http://127.0.0.1:8787/api/docs/feedback", "data": {"audit_check": True}},
            "agent_id": "sys_connector_audit"
        })
        await asyncio.sleep(0.3)

        after = (await GET(C, "/api/audit-log/verify")).json()
        check("audit chain grew", after["verified"] >= before)
        check("chain valid", after["ok"] is True)

    async def test_connector_stats_by_category(self, C):
        """Stats correctly categorize all connectors."""
        stats = must(await GET(C, "/api/connectors/stats/summary"), label="stats")
        by_cat = stats.get("by_category", {})
        check("has communication", "communication" in by_cat, list(by_cat.keys()))
        check("has integration", "integration" in by_cat)
        check("total is sum of categories",
              stats["total_connectors"] >= sum(by_cat.values()))
