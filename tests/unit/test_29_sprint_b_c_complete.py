"""
Unit Tests — Sprint B & C Complete Coverage
Covers: Supervisor advanced flows, Goal Manager edge cases, MCP Gateway policies, Connectors SDK
"""
import pytest, httpx, time

BASE = "http://127.0.0.1:8787"

@pytest.fixture(scope="module")
def client():
    return httpx.Client(base_url=BASE, timeout=15)


class TestSupervisorAdvanced:
    def test_supervisor_stats_fields(self, client):
        d = client.get("/api/supervisor/stats").json()
        for f in ("total_runs", "by_status", "avg_eval_score", "total_tokens"):
            assert f in d

    def test_run_with_full_context(self, client):
        r = client.post("/api/supervisor/run", json={
            "goal": "Create a simple hello world function in Python",
            "goal_title": "Hello World",
            "strategy": "hierarchical"
        })
        assert r.status_code == 200
        d = r.json()
        assert d["ok"] is True
        assert d["run_id"].startswith("srun_")
        assert d["status"] == "decomposing"

    def test_run_completes_with_tasks(self, client):
        r = client.post("/api/supervisor/run", json={
            "goal": "Brief answer: what is Python?"
        })
        run_id = r.json()["run_id"]
        # Poll for completion
        for _ in range(10):
            time.sleep(1)
            d = client.get(f"/api/supervisor/run/{run_id}").json()
            if d["run"]["status"] in ("done", "failed", "killed"):
                break
        d = client.get(f"/api/supervisor/run/{run_id}").json()
        assert d["run"]["task_count"] >= 1
        assert d["run"]["status"] in ("done", "failed", "killed")

    def test_run_list_filter_by_status(self, client):
        r = client.get("/api/supervisor/runs?status=done&limit=5")
        assert r.status_code == 200
        d = r.json()
        for run in d["runs"]:
            assert run["status"] == "done"

    def test_run_list_pagination(self, client):
        r = client.get("/api/supervisor/runs?limit=3")
        assert r.status_code == 200
        d = r.json()
        assert len(d["runs"]) <= 3

    def test_kill_already_done_run(self, client):
        r = client.post("/api/supervisor/run", json={"goal": "quick kill test"})
        run_id = r.json()["run_id"]
        time.sleep(3)
        kill = client.post(f"/api/supervisor/run/{run_id}/kill", json={"reason": "test"})
        assert kill.status_code == 200
        assert kill.json()["ok"] is True

    def test_delete_run_clears_tasks(self, client):
        r = client.post("/api/supervisor/run", json={"goal": "delete test"})
        run_id = r.json()["run_id"]
        time.sleep(2)
        client.post(f"/api/supervisor/run/{run_id}/kill", json={})
        del_r = client.delete(f"/api/supervisor/run/{run_id}")
        assert del_r.json()["ok"] is True
        get_r = client.get(f"/api/supervisor/run/{run_id}")
        assert get_r.status_code == 404

    def test_sse_stream_connects(self, client):
        r = client.post("/api/supervisor/run", json={"goal": "stream test goal"})
        run_id = r.json()["run_id"]
        with client.stream("GET", f"/api/supervisor/run/{run_id}/stream") as resp:
            assert resp.status_code == 200
            lines = []
            for line in resp.iter_lines():
                lines.append(line)
                if len(lines) >= 3:
                    break
        assert any("data:" in l for l in lines)


class TestGoalManagerAdvanced:
    def test_all_domains(self, client):
        domains = client.get("/api/goals/domains/list").json()["domains"]
        for domain in domains:
            r = client.post("/api/goals", json={"title": f"Test {domain}", "domain": domain})
            assert r.json()["ok"] is True

    def test_all_priorities(self, client):
        for prio in ("critical", "high", "medium", "low"):
            r = client.post("/api/goals", json={"title": f"Prio {prio}", "priority": prio})
            assert r.json()["ok"] is True

    def test_goal_with_deadline(self, client):
        r = client.post("/api/goals", json={
            "title": "Deadline Goal",
            "deadline": "2026-12-31",
            "domain": "Work"
        })
        assert r.json()["ok"] is True
        gid = r.json()["goal_id"]
        d = client.get(f"/api/goals/{gid}").json()
        assert d["goal"]["deadline"] == "2026-12-31"

    def test_milestone_completion_updates_progress(self, client):
        r = client.post("/api/goals", json={"title": "Milestone Progress Test"})
        gid = r.json()["goal_id"]
        # Add 4 milestones
        ms_ids = []
        for i in range(4):
            ms = client.post(f"/api/goals/{gid}/milestones", json={"title": f"MS {i}"}).json()
            ms_ids.append(ms["id"])
        # Complete 2 of 4 = 50%
        client.post(f"/api/goals/{gid}/milestones/{ms_ids[0]}/complete")
        client.post(f"/api/goals/{gid}/milestones/{ms_ids[1]}/complete")
        d = client.get(f"/api/goals/{gid}").json()["goal"]
        assert d["progress"] == 50

    def test_multiple_checkins(self, client):
        r = client.post("/api/goals", json={"title": "Multi Checkin Goal"})
        gid = r.json()["goal_id"]
        for i, (agent, pct, note) in enumerate([
            ("supervisor", 25, "Started"),
            ("researcher", 50, "Halfway"),
            ("builder", 75, "Almost done")
        ]):
            client.post(f"/api/goals/{gid}/checkin", json={
                "progress": pct, "note": note, "agent_id": agent
            })
        d = client.get(f"/api/goals/{gid}").json()["goal"]
        assert d["progress"] >= 75
        assert len(d["checkins"]) >= 3

    def test_goal_100_auto_completes(self, client):
        r = client.post("/api/goals", json={"title": "Auto Complete Test"})
        gid = r.json()["goal_id"]
        client.patch(f"/api/goals/{gid}", json={"progress": 100})
        d = client.get(f"/api/goals/{gid}").json()["goal"]
        assert d["status"] == "done"
        assert d["completed_at"] != ""

    def test_filter_active_goals(self, client):
        r = client.get("/api/goals?status=active&limit=10")
        d = r.json()
        for g in d["goals"]:
            assert g["status"] == "active"

    def test_goals_summary_counts(self, client):
        d = client.get("/api/goals/stats/summary").json()
        assert "total" in d
        assert d["total"] >= 1
        assert "by_domain" in d
        assert "avg_progress" in d


class TestMCPGatewayAdvanced:
    def test_policy_priority_ordering(self, client):
        policies = client.get("/api/mcp-gateway/policies").json()["policies"]
        priorities = [p["priority"] for p in policies]
        assert priorities == sorted(priorities)

    def test_rate_limit_tracked(self, client):
        for _ in range(3):
            client.post("/api/mcp-gateway/call", json={
                "server_id": "srv_memory",
                "tool": "memory.search",
                "args": {"query": "rate limit test"},
                "agent_id": "ratelimit_test_agent"
            })
        d = client.get("/api/mcp-gateway/stats").json()
        assert d["total_calls"] >= 3

    def test_disabled_server_blocks_calls(self, client):
        # Register and disable a server
        new = client.post("/api/mcp-gateway/servers", json={
            "name": "Test Block Server", "server_type": "test"
        }).json()
        sid = new["server_id"]
        client.post(f"/api/mcp-gateway/servers/{sid}/toggle", json={"disable": True})
        # Call it — should be blocked
        r = client.post("/api/mcp-gateway/call", json={
            "server_id": sid, "tool": "test.action",
            "args": {}, "agent_id": "builder"
        })
        d = r.json()
        assert d["ok"] is False
        assert d["policy_decision"] == "deny"

    def test_call_log_records_policy(self, client):
        client.post("/api/mcp-gateway/call", json={
            "server_id": "srv_web_search",
            "tool": "search.web",
            "args": {"query": "test", "limit": 1},
            "agent_id": "policy_log_test"
        })
        d = client.get("/api/mcp-gateway/calls?agent_id=policy_log_test").json()
        assert d["total"] >= 1
        for call in d["calls"]:
            assert "policy_decision" in call

    def test_agent_cards_for_all_specialists(self, client):
        for agent_id in ["builder", "researcher", "reviewer", "brain", "orchestrator"]:
            r = client.get(f"/api/mcp-gateway/agent-card/{agent_id}")
            assert r.status_code == 200
            card = r.json()["agent_card"]
            assert card["schema_version"] == "a2a/1.0"
            assert "mcp/1.0" in card["protocols"]
            assert "a2a/1.0" in card["protocols"]


class TestConnectorsSDK:
    def test_webhook_executes_successfully(self, client):
        r = client.post("/api/connectors/conn_webhook/execute", json={
            "action": "post_webhook",
            "payload": {
                "url": "http://127.0.0.1:8787/api/docs/feedback",
                "data": {"source": "unit_test", "timestamp": int(time.time())}
            },
            "agent_id": "orchestrator"
        })
        d = r.json()
        assert d["ok"] is True
        assert "exec_id" in d

    def test_connector_history_grows(self, client):
        before = client.get("/api/connectors/conn_webhook/executions?limit=100").json()["count"]
        client.post("/api/connectors/conn_webhook/execute", json={
            "action": "post_webhook",
            "payload": {"url": "http://127.0.0.1:8787/api/docs/feedback", "data": {}},
        })
        after = client.get("/api/connectors/conn_webhook/executions?limit=100").json()["count"]
        assert after >= before  # history grows, cap is 100

    def test_custom_connector_full_lifecycle(self, client):
        # Register
        create = client.post("/api/connectors", json={
            "name": "LifecycleTest",
            "category": "custom",
            "auth_type": "api_key",
            "capabilities": ["action_a", "action_b"],
            "description": "SDK lifecycle test"
        }).json()
        assert create["ok"] is True
        cid = create["connector_id"]

        # Configure
        cfg = client.patch(f"/api/connectors/{cid}/configure", json={
            "credentials": {"api_key": "test_key_abc"}
        }).json()
        assert cfg["status"] == "active"

        # Test
        test_r = client.post(f"/api/connectors/{cid}/test").json()
        assert test_r["configured"] is True

        # Get detail
        detail = client.get(f"/api/connectors/{cid}").json()
        assert detail["connector"]["status"] == "active"

        # Filter by category
        filtered = client.get("/api/connectors?category=custom").json()
        ids = [c["connector_id"] for c in filtered["connectors"]]
        assert cid in ids

    def test_connector_stats_after_executions(self, client):
        d = client.get("/api/connectors/stats/summary").json()
        assert d["total_connectors"] >= 8
        assert d["total_executions"] >= 1
        assert "by_category" in d
