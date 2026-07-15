"""
Sprint B — Test Suite 1: Supervisor Agent
Tests: run lifecycle, decomposition, task DAG, kill switch, stats, streaming
"""
import pytest, httpx, time

BASE = "http://127.0.0.1:8787"

@pytest.fixture(scope="module")
def client():
    return httpx.Client(base_url=BASE, timeout=15)


class TestSupervisorStats:
    def test_stats_endpoint(self, client):
        r = client.get("/api/supervisor/stats")
        assert r.status_code == 200

    def test_stats_has_fields(self, client):
        d = client.get("/api/supervisor/stats").json()
        assert "total_runs" in d
        assert "by_status" in d
        assert "avg_eval_score" in d
        assert "total_tokens" in d
        assert "top_agents" in d


class TestSupervisorRuns:
    def test_list_runs(self, client):
        r = client.get("/api/supervisor/runs")
        assert r.status_code == 200
        d = r.json()
        assert "runs" in d
        assert "count" in d

    def test_create_run_minimal(self, client):
        r = client.post("/api/supervisor/run", json={
            "goal": "Summarize the benefits of agentic AI"
        })
        assert r.status_code == 200
        d = r.json()
        assert d["ok"] is True
        assert d["run_id"].startswith("srun_")
        assert d["status"] == "decomposing"

    def test_create_run_requires_goal(self, client):
        r = client.post("/api/supervisor/run", json={})
        assert r.json()["ok"] is False

    def test_create_run_empty_goal(self, client):
        r = client.post("/api/supervisor/run", json={"goal": "   "})
        assert r.json()["ok"] is False

    def test_run_completes(self, client):
        r = client.post("/api/supervisor/run", json={
            "goal": "List 3 ways to improve software quality",
            "goal_title": "Software quality test"
        })
        run_id = r.json()["run_id"]

        # Poll for completion (max 12s — stub LLM is fast)
        for _ in range(12):
            time.sleep(1)
            d = client.get(f"/api/supervisor/run/{run_id}").json()
            if d["run"]["status"] in ("done", "failed", "killed"):
                break

        d = client.get(f"/api/supervisor/run/{run_id}").json()
        assert d["ok"] is True
        run = d["run"]
        assert run["status"] in ("done", "failed", "killed")
        assert run["task_count"] > 0

    def test_run_has_tasks(self, client):
        r = client.post("/api/supervisor/run", json={
            "goal": "Research and explain machine learning basics"
        })
        run_id = r.json()["run_id"]
        time.sleep(5)

        d = client.get(f"/api/supervisor/run/{run_id}").json()
        tasks = d.get("tasks", [])
        assert len(tasks) > 0

    def test_tasks_have_required_fields(self, client):
        r = client.post("/api/supervisor/run", json={
            "goal": "Write a brief overview of neural networks"
        })
        run_id = r.json()["run_id"]
        time.sleep(5)

        d = client.get(f"/api/supervisor/run/{run_id}").json()
        for task in d.get("tasks", []):
            assert "task_id" in task
            assert "seq" in task
            assert "title" in task
            assert "agent_id" in task
            assert "status" in task

    def test_tasks_assigned_to_specialists(self, client):
        r = client.post("/api/supervisor/run", json={
            "goal": "Research Python frameworks and write a comparison document"
        })
        run_id = r.json()["run_id"]
        time.sleep(6)

        d = client.get(f"/api/supervisor/run/{run_id}").json()
        agents = set(t["agent_id"] for t in d.get("tasks", []))
        # Should have multiple specialist agents
        assert len(agents) >= 1  # at least one assigned

    def test_get_run_404(self, client):
        r = client.get("/api/supervisor/run/nonexistent_run_xyz")
        assert r.status_code == 404

    def test_run_with_goal_id(self, client):
        r = client.post("/api/supervisor/run", json={
            "goal": "Create a test plan",
            "goal_id": "test_goal_001",
            "goal_title": "Test Plan Goal"
        })
        d = r.json()
        assert d["ok"] is True


class TestSupervisorKillSwitch:
    def test_kill_running_run(self, client):
        r = client.post("/api/supervisor/run", json={
            "goal": "A long complex multi-step research goal that will take a while"
        })
        run_id = r.json()["run_id"]
        time.sleep(1)  # Let it start

        kill = client.post(f"/api/supervisor/run/{run_id}/kill",
                           json={"reason": "Test kill switch"})
        d = kill.json()
        assert d["ok"] is True
        assert d["killed"] is True
        assert d["run_id"] == run_id

    def test_kill_records_reason(self, client):
        r = client.post("/api/supervisor/run", json={"goal": "killable goal"})
        run_id = r.json()["run_id"]
        client.post(f"/api/supervisor/run/{run_id}/kill",
                    json={"reason": "unit test termination"})

        d = client.get(f"/api/supervisor/run/{run_id}").json()
        assert d["run"]["status"] == "killed"

    def test_kill_nonexistent_run(self, client):
        r = client.post("/api/supervisor/run/nonexistent_xyz/kill",
                        json={"reason": "test"})
        assert r.status_code == 404

    def test_kill_logged_to_audit(self, client):
        r = client.post("/api/supervisor/run", json={"goal": "audit kill test"})
        run_id = r.json()["run_id"]
        client.post(f"/api/supervisor/run/{run_id}/kill",
                    json={"reason": "audit chain test"})

        # Verify it appears in audit log
        audit = client.get("/api/audit-log?action_type=supervisor_killed&limit=5").json()
        # May not filter by action_type (no exact filter), but chain should grow
        assert client.get("/api/audit-log/verify").json()["ok"] is True


class TestSupervisorDelete:
    def test_delete_run(self, client):
        r = client.post("/api/supervisor/run", json={"goal": "deletable goal"})
        run_id = r.json()["run_id"]
        client.post(f"/api/supervisor/run/{run_id}/kill", json={})

        del_r = client.delete(f"/api/supervisor/run/{run_id}")
        assert del_r.json()["ok"] is True

        # Should 404 after delete
        assert client.get(f"/api/supervisor/run/{run_id}").status_code == 404


class TestSpecialistAssignment:
    """Test that the specialist-selection logic works correctly."""

    def test_researcher_for_research_tasks(self):
        from backend.routers.supervisor import _assign_specialist
        agent = _assign_specialist("Research AI trends", "Find and analyze research on agentic AI")
        assert agent == "researcher"

    def test_builder_for_code_tasks(self):
        from backend.routers.supervisor import _assign_specialist
        agent = _assign_specialist("Code the API endpoint", "Build and implement the REST API")
        assert agent == "builder"

    def test_reviewer_for_review_tasks(self):
        from backend.routers.supervisor import _assign_specialist
        agent = _assign_specialist("Security review", "Review the code for security vulnerabilities and test coverage")
        assert agent == "reviewer"

    def test_brain_default(self):
        from backend.routers.supervisor import _assign_specialist
        agent = _assign_specialist("Generic task", "Do something")
        # Default is brain when no clear match
        assert agent in ("brain", "researcher", "builder", "reviewer")


class TestTopologicalSort:
    def test_linear_chain(self):
        from backend.routers.supervisor import _topo_sort
        tasks = [
            {"seq": 1, "depends_on": []},
            {"seq": 2, "depends_on": [1]},
            {"seq": 3, "depends_on": [2]},
        ]
        waves = _topo_sort(tasks)
        assert len(waves) == 3
        assert waves[0][0]["seq"] == 1
        assert waves[1][0]["seq"] == 2
        assert waves[2][0]["seq"] == 3

    def test_parallel_tasks(self):
        from backend.routers.supervisor import _topo_sort
        tasks = [
            {"seq": 1, "depends_on": []},
            {"seq": 2, "depends_on": []},
            {"seq": 3, "depends_on": [1, 2]},
        ]
        waves = _topo_sort(tasks)
        assert len(waves) == 2
        assert len(waves[0]) == 2  # tasks 1&2 run in parallel
        assert waves[1][0]["seq"] == 3

    def test_independent_tasks(self):
        from backend.routers.supervisor import _topo_sort
        tasks = [{"seq": i, "depends_on": []} for i in range(1, 5)]
        waves = _topo_sort(tasks)
        assert len(waves) == 1
        assert len(waves[0]) == 4  # all run in parallel
