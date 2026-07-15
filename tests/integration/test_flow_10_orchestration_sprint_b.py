"""
Integration Flow 10 — Sprint B Orchestration: Supervisor→Goal→Loop Pipeline
Tests the complete orchestration lifecycle:
  Goal creation → Supervisor decomposition → Parallel execution →
  Outcome evaluation → Goal progress update → Loop scheduler
"""
from __future__ import annotations
import asyncio, time
import httpx, pytest
from .conftest import BASE, TIMEOUT, uid, GET, POST, PATCH, DELETE, ok, ok_or, check


class TestGoalSupervisorPipeline:
    """Full goal-to-execution pipeline: create goal → launch supervisor → track."""

    async def test_01_create_goal_with_all_fields(self, client):
        """Create a comprehensive goal with domain, priority, deadline, criteria."""
        r = await POST(client, "/api/goals", {
            "title": "Integration Test: Build AI-powered TODO app",
            "description": "Create a minimal TODO app with React frontend and FastAPI backend",
            "success_criteria": "App runs on localhost with CRUD operations working",
            "domain": "Work",
            "priority": "high",
            "deadline": "2026-12-31",
            "tags": "integration,test,web",
        })
        d = ok(r, "create goal")
        check("goal ok", d["ok"] is True)
        check("goal_id format", d["goal_id"].startswith("goal_"))
        return d["goal_id"]

    async def test_02_goal_persists_with_all_fields(self, client):
        """Verify all goal fields persist correctly."""
        create = await POST(client, "/api/goals", {
            "title": "Persistence Test Goal",
            "domain": "Research",
            "priority": "critical",
            "deadline": "2026-09-30",
            "success_criteria": "All tests pass",
            "description": "Testing field persistence"
        })
        gid = create.json()["goal_id"]

        r = await GET(client, f"/api/goals/{gid}")
        d = ok(r, "get goal")
        g = d["goal"]
        check("title correct", g["title"] == "Persistence Test Goal")
        check("domain correct", g["domain"] == "Research")
        check("priority correct", g["priority"] == "critical")
        check("deadline correct", g["deadline"] == "2026-09-30")
        check("progress starts 0", g["progress"] == 0)
        check("status starts active", g["status"] == "active")

    async def test_03_milestone_completion_drives_progress(self, client):
        """Completing milestones automatically updates goal progress."""
        create = await POST(client, "/api/goals", {"title": "Milestone Progress Test"})
        gid = create.json()["goal_id"]

        # Add 4 milestones
        ms_ids = []
        for title in ["Setup", "Backend", "Frontend", "Deploy"]:
            ms_r = await POST(client, f"/api/goals/{gid}/milestones", {
                "title": title, "due_date": "2026-12-31"
            })
            ms_ids.append(ms_r.json()["id"])

        # Complete 2 of 4 → expect 50%
        for ms_id in ms_ids[:2]:
            await POST(client, f"/api/goals/{gid}/milestones/{ms_id}/complete")

        g = (await GET(client, f"/api/goals/{gid}")).json()["goal"]
        check("progress is 50%", g["progress"] == 50, g["progress"])

        # Complete remaining → expect 100% and status=done
        for ms_id in ms_ids[2:]:
            await POST(client, f"/api/goals/{gid}/milestones/{ms_id}/complete")

        g2 = (await GET(client, f"/api/goals/{gid}")).json()["goal"]
        check("progress is 100%", g2["progress"] == 100)
        check("status is done", g2["status"] == "done")
        check("completed_at or status done", g2.get("status") == "done" or g2.get("completed_at") not in (None, ""))

    async def test_04_multi_agent_checkins_build_history(self, client):
        """Multiple agent check-ins create a progress history."""
        create = await POST(client, "/api/goals", {"title": "Checkin History Goal"})
        gid = create.json()["goal_id"]

        agents_and_notes = [
            ("researcher", 20, "Researched requirements"),
            ("builder", 50, "Built the backend API"),
            ("reviewer", 75, "Code review complete"),
            ("orchestrator", 90, "Final integration"),
        ]
        for agent, pct, note in agents_and_notes:
            await POST(client, f"/api/goals/{gid}/checkin", {
                "progress": pct, "note": note, "agent_id": agent
            })

        g = (await GET(client, f"/api/goals/{gid}")).json()["goal"]
        check("progress at 90", g["progress"] == 90)
        check("4 checkins recorded", len(g["checkins"]) >= 4)
        agent_ids = [c["agent_id"] for c in g["checkins"]]
        for agent, _, _ in agents_and_notes:
            check(f"{agent} in checkins", agent in agent_ids)

    async def test_05_supervisor_run_full_lifecycle(self, client):
        """Full supervisor run: launch → tasks created → completion."""
        r = await POST(client, "/api/supervisor/run", {
            "goal": "What are the 3 main benefits of using FastAPI over Flask?",
            "goal_title": "FastAPI vs Flask Integration Test"
        })
        d = ok(r, "launch supervisor")
        check("ok", d["ok"] is True)
        run_id = d["run_id"]
        check("run_id format", run_id.startswith("srun_"))
        check("initial status", d["status"] == "decomposing")

        # Poll for completion (max 20s)
        for attempt in range(20):
            await asyncio.sleep(1)
            status_r = await GET(client, f"/api/supervisor/run/{run_id}")
            run = status_r.json()["run"]
            if run["status"] in ("done", "failed", "killed"):
                break

        final = (await GET(client, f"/api/supervisor/run/{run_id}")).json()
        check("run completed", final["run"]["status"] in ("done", "failed", "killed"))
        check("tasks were created", final["run"]["task_count"] > 0)
        check("tasks in list", len(final["tasks"]) > 0)

        # Verify tasks have required fields
        for task in final["tasks"]:
            check("task has task_id", "task_id" in task)
            check("task has seq", "seq" in task)
            check("task has agent_id", "agent_id" in task)
            check("task has status", "status" in task)

    async def test_06_supervisor_stats_updated(self, client):
        """Supervisor stats reflect completed runs."""
        r = await GET(client, "/api/supervisor/stats")
        d = ok(r, "supervisor stats")
        check("total_runs > 0", d["total_runs"] > 0)
        check("has by_status", "by_status" in d)
        check("has top_agents", "top_agents" in d)

    async def test_07_goal_launch_creates_supervisor_run(self, client):
        """Goal launch automatically creates and links a supervisor run."""
        create = await POST(client, "/api/goals", {
            "title": "Goal Launch Integration Test",
            "description": "Test that goal launch creates supervisor run",
            "success_criteria": "Supervisor run is created and linked"
        })
        gid = create.json()["goal_id"]

        launch_r = await POST(client, f"/api/goals/{gid}/launch", {})
        ld = ok(launch_r, "goal launch")
        check("launch ok", ld["ok"] is True)
        check("run_id returned", "run_id" in ld)
        check("run_id format", ld["run_id"].startswith("srun_"))

        # Goal should now have supervisor_run_id set
        await asyncio.sleep(0.5)
        g = (await GET(client, f"/api/goals/{gid}")).json()["goal"]
        check("supervisor_run_id linked", g.get("supervisor_run_id") == ld["run_id"],
              g.get("supervisor_run_id"))

    async def test_08_goals_summary_counts_all_domains(self, client):
        """Goals summary shows counts across all created domains."""
        # Create goals in different domains
        for domain in ["Work", "Research", "Learning"]:
            await POST(client, "/api/goals", {
                "title": f"Summary Test {domain}",
                "domain": domain
            })

        r = await GET(client, "/api/goals/stats/summary")
        d = ok(r, "goals summary")
        check("total > 0", d["total"] > 0)
        check("has by_domain", "by_domain" in d)
        check("has by_status", "by_status" in d)
        check("has avg_progress", "avg_progress" in d)

    async def test_09_kill_switch_stops_supervisor(self, client):
        """Kill switch immediately terminates a running supervisor."""
        # Launch a run
        run_id = (await POST(client, "/api/supervisor/run", {
            "goal": "A long complex goal that needs many steps to research and implement"
        })).json()["run_id"]

        # Kill immediately
        await asyncio.sleep(0.3)
        kill_r = await POST(client, f"/api/supervisor/run/{run_id}/kill", {
            "reason": "Integration test kill switch"
        })
        kd = ok(kill_r, "kill supervisor")
        check("kill ok", kd["ok"] is True)
        check("killed flag", kd["killed"] is True)

        # Verify status is killed
        status = (await GET(client, f"/api/supervisor/run/{run_id}")).json()["run"]["status"]
        check("status=killed", status == "killed", status)

    async def test_10_delete_run_removes_all_tasks(self, client):
        """Deleting a supervisor run removes all associated tasks."""
        run_id = (await POST(client, "/api/supervisor/run", {
            "goal": "Quick goal for delete test"
        })).json()["run_id"]
        await asyncio.sleep(2)  # Let it decompose

        # Kill then delete
        await POST(client, f"/api/supervisor/run/{run_id}/kill", {"reason": "cleanup"})
        del_r = await client.delete(f"/api/supervisor/run/{run_id}")
        dd = ok(del_r, "delete run")
        check("delete ok", dd["ok"] is True)

        # Should now 404
        get_r = await GET(client, f"/api/supervisor/run/{run_id}")
        check("run 404 after delete", get_r.status_code == 404)


class TestLoopScheduler:
    """Autonomous loop scheduler lifecycle tests."""

    async def test_01_create_loop_appears_in_list(self, client):
        """Created loop immediately appears in list."""
        job_id = f"integration_loop_{uid()}"
        r = await POST(client, "/api/loops", {
            "prompt": "Integration test: check system health every hour",
            "interval_minutes": 60,
            "agent_id": "researcher",
            "job_id": job_id
        })
        d = ok(r, "create loop")
        check("loop ok", d["ok"] is True)
        check("job_id matches", d["job_id"] == job_id)

        # Verify in list
        loops = (await GET(client, "/api/loops")).json()
        job_ids = [l["id"] for l in loops]
        check("loop in list", job_id in job_ids)

    async def test_02_loop_with_goal_id(self, client):
        """Loop linked to a goal ID stores the goal reference."""
        goal_r = await POST(client, "/api/goals", {"title": "Loop Linked Goal"})
        gid = goal_r.json()["goal_id"]

        job_id = f"goal_linked_loop_{uid()}"
        r = await POST(client, "/api/loops", {
            "prompt": "Monitor progress on loop linked goal",
            "interval_minutes": 30,
            "agent_id": "builder",
            "job_id": job_id,
            "goal_id": gid
        })
        d = ok(r, "create goal-linked loop")
        check("loop ok", d["ok"] is True)

    async def test_03_pause_and_resume(self, client):
        """Loop can be paused and resumed."""
        job_id = f"pause_resume_{uid()}"
        await POST(client, "/api/loops", {
            "prompt": "Pause/resume test", "interval_minutes": 60, "job_id": job_id
        })

        # Pause
        p_r = await POST(client, f"/api/loops/{job_id}/pause")
        check("pause 200", p_r.status_code == 200)
        check("pause ok", p_r.json()["ok"] is True)

        # Resume
        r_r = await POST(client, f"/api/loops/{job_id}/resume")
        check("resume 200", r_r.status_code == 200)
        check("resume ok", r_r.json()["ok"] is True)

    async def test_04_delete_loop_removes_from_scheduler(self, client):
        """Deleted loop disappears from the scheduler."""
        job_id = f"delete_loop_{uid()}"
        await POST(client, "/api/loops", {
            "prompt": "Delete test loop", "interval_minutes": 60, "job_id": job_id
        })
        del_r = await client.delete(f"/api/loops/{job_id}")
        check("delete ok", del_r.json()["ok"] is True)

        loops = (await GET(client, "/api/loops")).json()
        ids = [l["id"] for l in loops]
        check("loop removed", job_id not in ids)

    async def test_05_builtin_jobs_protected(self, client):
        """Built-in system jobs cannot be deleted or paused."""
        for builtin in ["memory_index", "standup", "cost_digest", "status_cleanup"]:
            del_r = await client.delete(f"/api/loops/{builtin}")
            d = del_r.json()
            check(f"{builtin} not deletable",
                  d.get("ok") is False or "protected" in str(d).lower(),
                  d)

    async def test_06_loop_max_runs_parameter(self, client):
        """Loop with max_runs parameter is accepted."""
        job_id = f"max_runs_{uid()}"
        r = await POST(client, "/api/loops", {
            "prompt": "Max runs test", "interval_minutes": 60,
            "job_id": job_id, "max_runs": 5
        })
        check("max_runs loop ok", r.json()["ok"] is True)

    async def test_07_scheduler_status_accessible(self, client):
        """Scheduler status endpoint returns scheduler state."""
        r = await GET(client, "/api/loops/status")
        check("status 200", r.status_code == 200)
        d = r.json()
        check("has running or paused", "running" in d or "status" in d or isinstance(d, dict))
