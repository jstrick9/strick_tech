"""
Sprint B — Test Suite 2: Goal Manager
Tests: CRUD, domains, priorities, milestones, check-ins, progress, launch
"""
import pytest, httpx

BASE = "http://127.0.0.1:8787"

@pytest.fixture(scope="module")
def client():
    return httpx.Client(base_url=BASE, timeout=10)

@pytest.fixture(scope="module")
def sample_goal(client):
    r = client.post("/api/goals", json={
        "title": "Test Goal for Sprint B",
        "domain": "Research",
        "priority": "high",
        "description": "Testing the Goal Manager API",
        "success_criteria": "All tests pass",
        "deadline": "2026-12-31",
        "tags": "test,sprint-b",
    })
    return r.json()["goal_id"]


class TestGoalCRUD:
    def test_create_goal_minimal(self, client):
        r = client.post("/api/goals", json={"title": "Minimal goal"})
        assert r.status_code == 200
        d = r.json()
        assert d["ok"] is True
        assert d["goal_id"].startswith("goal_")

    def test_create_goal_full(self, client):
        r = client.post("/api/goals", json={
            "title": "Full goal", "domain": "Finance",
            "priority": "critical", "description": "Full test",
            "success_criteria": "Works perfectly",
            "deadline": "2026-08-01", "tags": "finance,test",
        })
        assert r.status_code == 200
        assert r.json()["ok"] is True

    def test_create_goal_requires_title(self, client):
        r = client.post("/api/goals", json={"domain": "Work"})
        assert r.json()["ok"] is False

    def test_create_goal_invalid_domain_defaults(self, client):
        r = client.post("/api/goals", json={"title": "Bad domain", "domain": "INVALID"})
        assert r.json()["ok"] is True  # Falls back to 'Work'

    def test_get_goal(self, client, sample_goal):
        r = client.get(f"/api/goals/{sample_goal}")
        assert r.status_code == 200
        d = r.json()
        assert d["ok"] is True
        assert d["goal"]["id"] == sample_goal
        assert d["goal"]["domain"] == "Research"
        assert d["goal"]["priority"] == "high"

    def test_get_goal_has_milestones_key(self, client, sample_goal):
        d = client.get(f"/api/goals/{sample_goal}").json()
        assert "milestones" in d["goal"]
        assert "checkins" in d["goal"]

    def test_get_goal_404(self, client):
        r = client.get("/api/goals/nonexistent_goal_xyz")
        assert r.status_code == 404

    def test_list_goals(self, client, sample_goal):
        r = client.get("/api/goals")
        assert r.status_code == 200
        d = r.json()
        assert "goals" in d
        assert d["total"] >= 1

    def test_list_goals_filter_status(self, client, sample_goal):
        r = client.get("/api/goals?status=active")
        d = r.json()
        for g in d["goals"]:
            assert g["status"] == "active"

    def test_list_goals_filter_domain(self, client, sample_goal):
        r = client.get("/api/goals?domain=Research")
        d = r.json()
        for g in d["goals"]:
            assert g["domain"] == "Research"

    def test_delete_goal(self, client):
        r = client.post("/api/goals", json={"title": "To delete"})
        gid = r.json()["goal_id"]
        del_r = client.delete(f"/api/goals/{gid}")
        assert del_r.json()["ok"] is True
        assert client.get(f"/api/goals/{gid}").status_code == 404


class TestGoalUpdate:
    def test_update_progress(self, client, sample_goal):
        r = client.patch(f"/api/goals/{sample_goal}",
                         json={"progress": 42})
        assert r.json()["ok"] is True

    def test_update_progress_clamped(self, client, sample_goal):
        r = client.patch(f"/api/goals/{sample_goal}",
                         json={"progress": 150})
        d = client.get(f"/api/goals/{sample_goal}").json()
        assert d["goal"]["progress"] == 100

    def test_update_status(self, client, sample_goal):
        r = client.patch(f"/api/goals/{sample_goal}",
                         json={"status": "paused"})
        assert r.json()["ok"] is True
        d = client.get(f"/api/goals/{sample_goal}").json()
        assert d["goal"]["status"] == "paused"
        # Restore
        client.patch(f"/api/goals/{sample_goal}", json={"status": "active"})

    def test_update_100_progress_sets_done(self, client):
        r = client.post("/api/goals", json={"title": "Complete me"})
        gid = r.json()["goal_id"]
        client.patch(f"/api/goals/{gid}", json={"progress": 100})
        d = client.get(f"/api/goals/{gid}").json()
        assert d["goal"]["status"] == "done"
        assert d["goal"]["completed_at"] != ""

    def test_update_no_fields(self, client, sample_goal):
        r = client.patch(f"/api/goals/{sample_goal}", json={})
        assert r.json()["ok"] is False

    def test_update_404(self, client):
        r = client.patch("/api/goals/nonexistent_xyz", json={"progress": 10})
        assert r.status_code == 404


class TestGoalMilestones:
    def test_add_milestone(self, client, sample_goal):
        r = client.post(f"/api/goals/{sample_goal}/milestones", json={
            "title": "First milestone",
            "description": "Get the foundation in place",
            "due_date": "2026-08-15",
        })
        assert r.status_code == 200
        assert r.json()["ok"] is True
        assert r.json()["id"].startswith("ms_")

    def test_milestone_requires_title(self, client, sample_goal):
        r = client.post(f"/api/goals/{sample_goal}/milestones", json={})
        assert r.json()["ok"] is False

    def test_multiple_milestones(self, client, sample_goal):
        for i in range(3):
            client.post(f"/api/goals/{sample_goal}/milestones",
                        json={"title": f"Milestone {i+1}"})
        d = client.get(f"/api/goals/{sample_goal}").json()
        assert len(d["goal"]["milestones"]) >= 3

    def test_complete_milestone_updates_progress(self, client, sample_goal):
        # Add milestones
        ms_ids = []
        for i in range(2):
            r = client.post(f"/api/goals/{sample_goal}/milestones",
                            json={"title": f"Progress MS {i}"})
            ms_ids.append(r.json()["id"])

        # Complete one
        r = client.post(f"/api/goals/{sample_goal}/milestones/{ms_ids[0]}/complete")
        assert r.json()["ok"] is True
        assert r.json()["completed"] is True

        # Progress should update
        d = client.get(f"/api/goals/{sample_goal}").json()
        assert d["goal"]["progress"] > 0


class TestGoalCheckins:
    def test_add_checkin(self, client, sample_goal):
        r = client.post(f"/api/goals/{sample_goal}/checkin", json={
            "note": "Good progress today",
            "progress": 60,
            "agent_id": "supervisor",
        })
        assert r.status_code == 200
        assert r.json()["ok"] is True

    def test_checkin_updates_progress(self, client, sample_goal):
        client.post(f"/api/goals/{sample_goal}/checkin",
                    json={"progress": 75, "agent_id": "builder"})
        d = client.get(f"/api/goals/{sample_goal}").json()
        assert d["goal"]["progress"] >= 75

    def test_checkin_appears_in_goal(self, client, sample_goal):
        client.post(f"/api/goals/{sample_goal}/checkin",
                    json={"note": "Test note visible", "progress": 0})
        d = client.get(f"/api/goals/{sample_goal}").json()
        notes = [c["note"] for c in d["goal"]["checkins"]]
        assert any("Test note" in n for n in notes)

    def test_checkin_404_goal(self, client):
        r = client.post("/api/goals/nonexistent_xyz/checkin",
                        json={"note": "x", "progress": 0})
        assert r.status_code == 404


class TestGoalSummary:
    def test_summary_endpoint(self, client):
        r = client.get("/api/goals/stats/summary")
        assert r.status_code == 200
        d = r.json()
        assert "total" in d
        assert "by_status" in d
        assert "by_domain" in d
        assert "avg_progress" in d

    def test_summary_total_gte_1(self, client):
        d = client.get("/api/goals/stats/summary").json()
        assert d["total"] >= 1

    def test_domains_list(self, client):
        r = client.get("/api/goals/domains/list")
        assert r.status_code == 200
        d = r.json()
        assert "domains" in d
        assert "priorities" in d
        assert len(d["domains"]) == 8
        assert "Work" in d["domains"]
        assert "Health" in d["domains"]
        assert len(d["priorities"]) == 4


class TestGoalLaunch:
    def test_launch_creates_supervisor_run(self, client):
        # Create a goal
        r = client.post("/api/goals", json={
            "title": "Launched supervisor goal",
            "domain": "Research",
            "description": "Test launching a supervisor from a goal",
        })
        gid = r.json()["goal_id"]

        # Launch
        launch = client.post(f"/api/goals/{gid}/launch", json={})
        d = launch.json()
        assert d["ok"] is True
        assert "run_id" in d
        assert d["run_id"].startswith("srun_")

    def test_launch_404_goal(self, client):
        r = client.post("/api/goals/nonexistent_xyz/launch", json={})
        assert r.status_code == 500 or r.json()["ok"] is False
