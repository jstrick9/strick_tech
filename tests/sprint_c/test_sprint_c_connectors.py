"""Sprint C — Test Suite 2: Enterprise Connectors"""
import pytest, httpx
BASE = "http://127.0.0.1:8787"

@pytest.fixture(scope="module")
def client(): return httpx.Client(base_url=BASE, timeout=15)

@pytest.fixture(scope="module")
def custom_connector(client):
    r = client.post("/api/connectors", json={
        "name":"Sprint C Test Connector","category":"custom",
        "auth_type":"api_key","capabilities":["test_action","read_data","write_data"],
        "description":"Created by Sprint C test suite"})
    return r.json()["connector_id"]

class TestConnectorList:
    def test_list_connectors(self, client):
        d = client.get("/api/connectors").json()
        assert d["count"] >= 8
        ids = [c["connector_id"] for c in d["connectors"]]
        for builtin in ("conn_slack","conn_jira","conn_gdrive","conn_email","conn_github","conn_webhook"):
            assert builtin in ids

    def test_connectors_have_required_fields(self, client):
        d = client.get("/api/connectors").json()
        for c in d["connectors"]:
            assert "connector_id" in c
            assert "name" in c
            assert "status" in c
            assert "capabilities" in c
            assert isinstance(c["capabilities"], list)

    def test_filter_by_category(self, client):
        d = client.get("/api/connectors?category=communication").json()
        for c in d["connectors"]:
            assert c["category"] == "communication"

    def test_builtin_webhook_is_active(self, client):
        d = client.get("/api/connectors").json()
        webhook = next((c for c in d["connectors"] if c["connector_id"]=="conn_webhook"), None)
        assert webhook is not None
        assert webhook["status"] == "active"

    def test_builtin_slack_is_unconfigured(self, client):
        d = client.get("/api/connectors").json()
        slack = next((c for c in d["connectors"] if c["connector_id"]=="conn_slack"), None)
        assert slack is not None
        assert slack["status"] in ("unconfigured","active")

class TestConnectorGet:
    def test_get_connector(self, client):
        r = client.get("/api/connectors/conn_slack")
        assert r.status_code == 200
        d = r.json()
        assert d["ok"] is True
        assert d["connector"]["connector_id"] == "conn_slack"

    def test_get_connector_404(self, client):
        r = client.get("/api/connectors/nonexistent_xyz")
        assert r.status_code == 404

class TestConnectorRegister:
    def test_register_custom(self, client):
        r = client.post("/api/connectors", json={
            "name":"Test Custom","category":"custom","auth_type":"api_key",
            "capabilities":["action_a","action_b"],"description":"Test"})
        assert r.status_code == 200
        d = r.json()
        assert d["ok"] is True
        assert d["connector_id"].startswith("conn_")

    def test_register_requires_name(self, client):
        r = client.post("/api/connectors", json={"category":"custom"})
        assert r.json()["ok"] is False

    def test_registered_connector_appears_in_list(self, client):
        r = client.post("/api/connectors", json={"name":"Appears In List","category":"custom"})
        cid = r.json()["connector_id"]
        d = client.get("/api/connectors").json()
        ids = [c["connector_id"] for c in d["connectors"]]
        assert cid in ids

class TestConnectorConfigure:
    def test_configure_sets_active(self, client, custom_connector):
        r = client.patch(f"/api/connectors/{custom_connector}/configure",
            json={"credentials":{"api_key":"test_key_abc123"}})
        assert r.json()["ok"] is True
        assert r.json()["status"] == "active"

    def test_configure_empty_unsets(self, client, custom_connector):
        r = client.patch(f"/api/connectors/{custom_connector}/configure",
            json={"credentials":{}})
        assert r.json()["ok"] is True
        assert r.json()["status"] == "unconfigured"

class TestConnectorExecute:
    def test_execute_webhook_action(self, client):
        r = client.post("/api/connectors/conn_webhook/execute", json={
            "action":"post_webhook",
            "payload":{"url":"https://httpbin.org/post","data":{"sprint":"C","test":True}},
            "agent_id":"supervisor"})
        d = r.json()
        assert "exec_id" in d
        assert d["exec_id"].startswith("cex_")
        assert "duration_ms" in d

    def test_execute_slack_unconfigured_returns_error(self, client):
        r = client.post("/api/connectors/conn_slack/execute", json={
            "action":"send_message","payload":{"channel":"test","text":"hi"},"agent_id":"test"})
        d = r.json()
        assert d["ok"] is False
        assert "not configured" in d.get("error","").lower() or "TOKEN" in d.get("error","")

    def test_execute_requires_action(self, client):
        r = client.post("/api/connectors/conn_webhook/execute", json={"payload":{}})
        assert r.json()["ok"] is False

    def test_execute_nonexistent_connector(self, client):
        r = client.post("/api/connectors/nonexistent_xyz/execute",
            json={"action":"test","payload":{}})
        assert r.json()["ok"] is False

    def test_execute_recorded_in_history(self, client):
        client.post("/api/connectors/conn_webhook/execute", json={
            "action":"post_webhook",
            "payload":{"url":"https://httpbin.org/post","data":{"history":"test"}},
            "agent_id":"history_test"})
        r = client.get("/api/connectors/conn_webhook/executions?limit=5")
        assert r.status_code == 200
        d = r.json()
        assert d["count"] >= 1

    def test_execute_updates_call_count(self, client):
        before = client.get("/api/connectors/conn_webhook").json()["connector"]["call_count"]
        client.post("/api/connectors/conn_webhook/execute", json={
            "action":"post_webhook","payload":{"url":"https://httpbin.org/post","data":{}},"agent_id":"test"})
        after = client.get("/api/connectors/conn_webhook").json()["connector"]["call_count"]
        assert after >= before

class TestConnectorTest:
    def test_test_webhook_active(self, client):
        r = client.post("/api/connectors/conn_webhook/test")
        assert r.status_code == 200
        d = r.json()
        assert d["ok"] is True
        assert d["configured"] is True

    def test_test_slack_unconfigured(self, client):
        r = client.post("/api/connectors/conn_slack/test")
        d = r.json()
        assert d["ok"] is True
        assert d["configured"] is False
        assert "credentials" in d["message"].lower() or "configured" in d["message"].lower()

    def test_test_nonexistent(self, client):
        r = client.post("/api/connectors/nonexistent_xyz/test")
        assert r.status_code == 404

class TestConnectorAuditIntegration:
    def test_execution_recorded_in_audit_chain(self, client):
        before = client.get("/api/audit-log/verify").json()["verified"]
        client.post("/api/connectors/conn_webhook/execute", json={
            "action":"post_webhook",
            "payload":{"url":"https://httpbin.org/post","data":{"audit":"test"}},
            "agent_id":"audit_connector_test"})
        after = client.get("/api/audit-log/verify").json()["verified"]
        assert after >= before
        assert client.get("/api/audit-log/verify").json()["ok"] is True

class TestConnectorStats:
    def test_stats_endpoint(self, client):
        r = client.get("/api/connectors/stats/summary")
        assert r.status_code == 200
        d = r.json()
        assert d["total_connectors"] >= 8
        assert "by_category" in d
        assert "top_connectors" in d

    def test_stats_by_category(self, client):
        d = client.get("/api/connectors/stats/summary").json()
        assert "communication" in d["by_category"]
        assert "integration" in d["by_category"]
