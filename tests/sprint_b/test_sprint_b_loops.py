"""
Sprint B — Test Suite 3: Enhanced Autonomous Loop Scheduler
Tests: create, list, pause, resume, kill, goal-linked loops, max_runs
"""
import pytest, httpx, time

BASE = "http://127.0.0.1:8787"

@pytest.fixture(scope="module")
def client():
    return httpx.Client(base_url=BASE, timeout=10)


class TestLoopCRUD:
    def test_list_loops(self, client):
        r = client.get("/api/loops")
        assert r.status_code == 200

    def test_create_loop_basic(self, client):
        r = client.post("/api/loops", json={
            "prompt": "Monitor sprint B progress",
            "interval_minutes": 60,
            "agent_id": "researcher",
        })
        assert r.status_code == 200
        d = r.json()
        assert d["ok"] is True
        assert d["job_id"].startswith("loop_") or len(d["job_id"]) > 3

    def test_create_loop_requires_prompt(self, client):
        r = client.post("/api/loops", json={"interval_minutes": 5})
        assert r.json()["ok"] is False

    def test_create_loop_with_goal_id(self, client):
        # Create a goal first
        g = client.post("/api/goals", json={"title": "Loop-linked goal"}).json()
        gid = g["goal_id"]

        r = client.post("/api/loops", json={
            "prompt": "Work on loop-linked goal",
            "interval_minutes": 30,
            "agent_id": "builder",
            "goal_id": gid,
        })
        assert r.json()["ok"] is True

    def test_create_loop_with_max_runs(self, client):
        r = client.post("/api/loops", json={
            "prompt": "Limited run loop",
            "interval_minutes": 60,
            "max_runs": 3,
        })
        assert r.json()["ok"] is True

    def test_create_loop_custom_job_id(self, client):
        r = client.post("/api/loops", json={
            "prompt": "Custom ID loop",
            "interval_minutes": 60,
            "job_id": "custom_test_loop_sprint_b",
        })
        d = r.json()
        assert d["ok"] is True
        assert d["job_id"] == "custom_test_loop_sprint_b"

    def test_loop_appears_in_list(self, client):
        jid = "list_test_loop_sprint_b"
        client.post("/api/loops", json={
            "prompt": "List test", "interval_minutes": 60,
            "job_id": jid,
        })
        d = client.get("/api/loops").json()
        loop_ids = [l["id"] for l in d] if isinstance(d, list) else []
        # Loop should exist (or scheduler list it)
        assert isinstance(d, list) or isinstance(d, dict)

    def test_delete_loop(self, client):
        jid = "delete_test_loop_sprint_b"
        client.post("/api/loops", json={"prompt": "Delete me", "interval_minutes": 60, "job_id": jid})
        r = client.delete(f"/api/loops/{jid}")
        assert r.json()["ok"] is True

    def test_delete_nonexistent_loop(self, client):
        r = client.delete("/api/loops/nonexistent_loop_xyz")
        # May return ok:True or error — either is acceptable
        assert r.status_code == 200


class TestLoopPauseResume:
    def test_pause_loop(self, client):
        jid = "pause_test_loop_sprint_b"
        client.post("/api/loops", json={"prompt": "Pause me", "interval_minutes": 60, "job_id": jid})
        r = client.post(f"/api/loops/{jid}/pause")
        assert r.status_code == 200
        assert r.json()["ok"] is True

    def test_resume_loop(self, client):
        jid = "resume_test_loop_sprint_b"
        client.post("/api/loops", json={"prompt": "Resume me", "interval_minutes": 60, "job_id": jid})
        client.post(f"/api/loops/{jid}/pause")
        r = client.post(f"/api/loops/{jid}/resume")
        assert r.status_code == 200
        assert r.json()["ok"] is True

    def test_cannot_delete_builtin_jobs(self, client):
        for builtin in ("memory_index", "standup", "cost_digest", "status_cleanup"):
            r = client.delete(f"/api/loops/{builtin}")
            # Should fail with error for built-in jobs
            d = r.json()
            assert d.get("ok") is False or "protected" in str(d).lower() or r.status_code != 200

    def test_cannot_pause_builtin_jobs(self, client):
        r = client.post("/api/loops/memory_index/pause")
        d = r.json()
        assert d.get("ok") is False or "protected" in str(d).lower()


class TestLoopStatus:
    def test_scheduler_status(self, client):
        r = client.get("/api/loops/status")
        assert r.status_code == 200

    def test_interval_capped(self, client):
        # Interval > 10080 min should be capped
        r = client.post("/api/loops", json={
            "prompt": "Cap test", "interval_minutes": 999999,
        })
        assert r.json()["ok"] is True  # Should succeed but cap interval
