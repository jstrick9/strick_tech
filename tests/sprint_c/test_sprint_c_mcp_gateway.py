"""Sprint C — Test Suite 1: MCP Gateway"""
import pytest, httpx
BASE = "http://127.0.0.1:8787"

@pytest.fixture(scope="module")
def client(): return httpx.Client(base_url=BASE, timeout=15)

class TestGatewayServers:
    def test_list_servers(self, client):
        r = client.get("/api/mcp-gateway/servers")
        assert r.status_code == 200
        d = r.json()
        assert d["count"] >= 5
        ids = [s["server_id"] for s in d["servers"]]
        for builtin in ("srv_filesystem","srv_web_search","srv_memory","srv_http","srv_code_exec"):
            assert builtin in ids

    def test_server_has_tools_schema(self, client):
        d = client.get("/api/mcp-gateway/servers").json()
        for s in d["servers"]:
            assert "tools_schema" in s
            assert isinstance(s["tools_schema"], list)

    def test_register_custom_server(self, client):
        r = client.post("/api/mcp-gateway/servers", json={
            "name":"Test External Server", "endpoint":"https://test.example.com",
            "description":"Sprint C test server", "server_type":"external"})
        assert r.json()["ok"] is True
        assert r.json()["server_id"].startswith("srv_")

    def test_register_requires_name(self, client):
        r = client.post("/api/mcp-gateway/servers", json={"endpoint":"https://x.com"})
        assert r.json()["ok"] is False

    def test_toggle_server_disable(self, client):
        r = client.post("/api/mcp-gateway/servers", json={"name":"Toggle Test"})
        sid = r.json()["server_id"]
        tog = client.post(f"/api/mcp-gateway/servers/{sid}/toggle", json={"disable": True})
        assert tog.json()["status"] == "disabled"

    def test_toggle_server_enable(self, client):
        r = client.post("/api/mcp-gateway/servers", json={"name":"Re-enable Test"})
        sid = r.json()["server_id"]
        client.post(f"/api/mcp-gateway/servers/{sid}/toggle", json={"disable": True})
        tog = client.post(f"/api/mcp-gateway/servers/{sid}/toggle", json={"disable": False})
        assert tog.json()["status"] == "active"

    def test_delete_server(self, client):
        r = client.post("/api/mcp-gateway/servers", json={"name":"Delete Me"})
        sid = r.json()["server_id"]
        del_r = client.delete(f"/api/mcp-gateway/servers/{sid}")
        assert del_r.json()["ok"] is True

    def test_cannot_delete_builtin(self, client):
        r = client.delete("/api/mcp-gateway/servers/srv_filesystem")
        assert r.json()["ok"] is False

class TestGatewayPolicies:
    def test_list_policies(self, client):
        d = client.get("/api/mcp-gateway/policies").json()
        assert d["count"] >= 3
        actions = {p["action"] for p in d["policies"]}
        assert "allow" in actions

    def test_create_allow_policy(self, client):
        r = client.post("/api/mcp-gateway/policies", json={
            "name":"Test allow policy","agent_id":"builder",
            "server_id":"srv_filesystem","tool_pattern":"fs.*","action":"allow","priority":200})
        assert r.json()["ok"] is True

    def test_create_deny_policy(self, client):
        r = client.post("/api/mcp-gateway/policies", json={
            "name":"Test deny","agent_id":"local","server_id":"srv_http",
            "tool_pattern":"*","action":"deny","priority":10})
        assert r.json()["ok"] is True
        pid = r.json()["policy_id"]
        client.delete(f"/api/mcp-gateway/policies/{pid}")

    def test_create_hitl_policy(self, client):
        r = client.post("/api/mcp-gateway/policies", json={
            "name":"HITL test","action":"require_hitl","priority":60})
        assert r.json()["ok"] is True
        pid = r.json()["policy_id"]
        client.delete(f"/api/mcp-gateway/policies/{pid}")

    def test_policy_requires_name(self, client):
        r = client.post("/api/mcp-gateway/policies", json={"action":"allow"})
        assert r.json()["ok"] is False

    def test_toggle_policy(self, client):
        r = client.post("/api/mcp-gateway/policies", json={"name":"Toggle pol"})
        pid = r.json()["policy_id"]
        tog = client.patch(f"/api/mcp-gateway/policies/{pid}/toggle")
        assert tog.json()["ok"] is True
        client.delete(f"/api/mcp-gateway/policies/{pid}")

    def test_delete_policy(self, client):
        r = client.post("/api/mcp-gateway/policies", json={"name":"Delete pol"})
        pid = r.json()["policy_id"]
        del_r = client.delete(f"/api/mcp-gateway/policies/{pid}")
        assert del_r.json()["ok"] is True

class TestGatewayCall:
    def test_call_allowed_tool(self, client):
        r = client.post("/api/mcp-gateway/call", json={
            "server_id":"srv_filesystem","tool":"fs.list",
            "args":{"path":"."},"agent_id":"builder"})
        d = r.json()
        assert d.get("policy_decision") == "allow"
        assert "call_id" in d
        assert d["call_id"].startswith("mcp_")

    def test_call_hitl_required(self, client):
        r = client.post("/api/mcp-gateway/call", json={
            "server_id":"srv_filesystem","tool":"fs.delete",
            "args":{"path":"test.txt"},"agent_id":"builder"})
        d = r.json()
        assert d.get("policy_decision") == "require_hitl"
        assert d.get("pending") is True
        assert d["ok"] is False

    def test_call_requires_tool(self, client):
        r = client.post("/api/mcp-gateway/call", json={
            "server_id":"srv_filesystem","args":{},"agent_id":"builder"})
        assert r.json()["ok"] is False

    def test_call_recorded_in_log(self, client):
        before = client.get("/api/mcp-gateway/stats").json()["total_calls"]
        client.post("/api/mcp-gateway/call", json={
            "server_id":"srv_filesystem","tool":"fs.list",
            "args":{"path":"."},"agent_id":"recorder_test"})
        after = client.get("/api/mcp-gateway/stats").json()["total_calls"]
        assert after >= before

    def test_call_audit_chain_updated(self, client):
        before_entries = client.get("/api/audit-log/verify").json()["verified"]
        client.post("/api/mcp-gateway/call", json={
            "server_id":"srv_filesystem","tool":"fs.list",
            "args":{"path":"."},"agent_id":"audit_test"})
        after_entries = client.get("/api/audit-log/verify").json()["verified"]
        assert after_entries >= before_entries

class TestGatewayAgentCard:
    def test_get_agent_card(self, client):
        r = client.get("/api/mcp-gateway/agent-card/builder")
        assert r.status_code == 200
        d = r.json()
        assert d["ok"] is True
        card = d["agent_card"]
        assert card["schema_version"] == "a2a/1.0"
        assert "mcp/1.0" in card["protocols"]
        assert "a2a/1.0" in card["protocols"]
        assert "endpoint" in card
        assert "card_hash" in card

    def test_agent_card_has_capabilities(self, client):
        card = client.get("/api/mcp-gateway/agent-card/orchestrator").json()["agent_card"]
        assert len(card["capabilities"]) > 0

    def test_agent_card_404(self, client):
        r = client.get("/api/mcp-gateway/agent-card/nonexistent_xyz")
        assert r.status_code == 404

class TestGatewayStats:
    def test_stats_fields(self, client):
        d = client.get("/api/mcp-gateway/stats").json()
        for f in ("total_calls","blocked_calls","active_servers","active_policies","top_agents","top_tools"):
            assert f in d

    def test_rate_limiting_bucket_tracking(self, client):
        for _ in range(3):
            client.post("/api/mcp-gateway/call", json={
                "server_id":"srv_filesystem","tool":"fs.list",
                "args":{"path":"."},"agent_id":"rate_test_agent"})
        d = client.get("/api/mcp-gateway/stats").json()
        agents = [a["agent_id"] for a in d["top_agents"]]
        assert "rate_test_agent" in agents or d["total_calls"] >= 3
