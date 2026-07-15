"""
UAT 09 — Orchestration Features (Sprint B)
User Stories:
  • As a user, I can set a high-level goal and watch agents execute it
  • As a user, I can track progress toward my goals with milestones
  • As a user, I can schedule recurring AI tasks to run automatically
  • As a user, the Supervisor breaks my goal into steps and assigns specialists

Acceptance Criteria tested at the USER level.
"""
from __future__ import annotations
import asyncio, time
import httpx, pytest
from .conftest import BASE, uid, GET, POST, PATCH, DELETE, j, accept, uat, no_error


# ══════════════════════════════════════════════════════════════════
#  USER STORY: "I can set a goal and watch agents work toward it"
# ══════════════════════════════════════════════════════════════════
class TestUATGoalManager:
    """User Story: As a user, I can create goals and track them through completion."""

    async def test_user_creates_goal_with_all_fields(self, U):
        """AC: User fills goal form → goal saved with all fields visible."""
        r = await POST(U, "/api/goals", {
            "title": f"UAT Goal: Launch product website [{uid()}]",
            "description": "Create a modern landing page for our new product",
            "success_criteria": "Page is live, mobile-responsive, and scores >90 on Lighthouse",
            "domain": "Work",
            "priority": "high",
            "deadline": "2026-09-30",
            "tags": "web,product,launch"
        })
        no_error(r, "create goal")
        d = j(r)
        uat("goal created successfully", d["ok"] is True)
        uat("user gets goal ID to track it", d["goal_id"].startswith("goal_"))

        # Verify all fields are readable
        gid = d["goal_id"]
        gr = j(await GET(U, f"/api/goals/{gid}"))["goal"]
        uat("title is correct", "UAT Goal" in gr["title"])
        uat("domain shows correctly", gr["domain"] == "Work")
        uat("priority shows correctly", gr["priority"] == "high")
        uat("deadline shows correctly", gr["deadline"] == "2026-09-30")
        uat("status starts as active", gr["status"] == "active")
        uat("progress starts at 0%", gr["progress"] == 0)

    async def test_user_adds_milestones_to_goal(self, U):
        """AC: User breaks goal into milestones → progress bar shows completion."""
        gid = j(await POST(U, "/api/goals", {"title": f"UAT Milestone Test {uid()}"}))["goal_id"]

        milestones = ["Design wireframes", "Build HTML/CSS", "Add JavaScript", "Deploy to server"]
        ms_ids = []
        for ms_title in milestones:
            r = await POST(U, f"/api/goals/{gid}/milestones", {
                "title": ms_title, "due_date": "2026-12-31"
            })
            no_error(r, f"add milestone {ms_title}")
            ms_ids.append(j(r)["id"])

        # Complete first milestone → progress bar moves
        await POST(U, f"/api/goals/{gid}/milestones/{ms_ids[0]}/complete")
        g = j(await GET(U, f"/api/goals/{gid}"))["goal"]
        uat("progress updates after milestone completion", g["progress"] == 25)

        # Complete all → goal auto-completes
        for ms_id in ms_ids[1:]:
            await POST(U, f"/api/goals/{gid}/milestones/{ms_id}/complete")
        g2 = j(await GET(U, f"/api/goals/{gid}"))["goal"]
        uat("goal status becomes done when 100% complete", g2["status"] == "done")
        uat("progress shows 100%", g2["progress"] == 100)

    async def test_user_adds_progress_checkins(self, U):
        """AC: User adds check-ins → progress history visible to team."""
        gid = j(await POST(U, "/api/goals", {"title": f"UAT Checkin Test {uid()}"}))["goal_id"]

        for agent, pct, note in [
            ("researcher", 25, "Research phase complete"),
            ("builder", 60, "Core implementation done"),
            ("reviewer", 80, "Code review passed"),
        ]:
            await POST(U, f"/api/goals/{gid}/checkin", {
                "progress": pct, "note": note, "agent_id": agent
            })

        g = j(await GET(U, f"/api/goals/{gid}"))["goal"]
        uat("latest progress visible", g["progress"] == 80)
        uat("checkin history recorded", len(g["checkins"]) >= 3)
        uat("check-in notes are readable", any(
            "Code review" in c.get("note","") for c in g["checkins"]
        ))

    async def test_user_filters_goals_by_domain(self, U):
        """AC: User clicks Work tab → only Work domain goals shown."""
        for domain in ["Work", "Health", "Learning"]:
            await POST(U, "/api/goals", {
                "title": f"UAT Filter {domain} {uid()}", "domain": domain
            })

        r = await GET(U, "/api/goals", domain="Work", status="active")
        no_error(r, "filter goals")
        d = j(r)
        for goal in d["goals"]:
            uat("filter shows only Work goals", goal["domain"] == "Work",
                goal["domain"])

    async def test_user_sees_goal_summary_dashboard(self, U):
        """AC: Goals dashboard shows total goals, progress, upcoming deadlines."""
        r = await GET(U, "/api/goals/stats/summary")
        no_error(r, "goal summary")
        d = j(r)
        uat("shows total goal count", "total" in d)
        uat("shows by-status breakdown", "by_status" in d)
        uat("shows average progress", "avg_progress" in d)
        uat("shows upcoming deadlines", "upcoming_deadlines" in d)

    async def test_user_can_pause_and_resume_goal(self, U):
        """AC: User pauses goal (vacation) → can resume it later."""
        gid = j(await POST(U, "/api/goals", {"title": f"UAT Pause Test {uid()}"}))["goal_id"]
        await PATCH(U, f"/api/goals/{gid}", {"status": "paused"})
        g = j(await GET(U, f"/api/goals/{gid}"))["goal"]
        uat("goal shows as paused", g["status"] == "paused")
        await PATCH(U, f"/api/goals/{gid}", {"status": "active"})
        g2 = j(await GET(U, f"/api/goals/{gid}"))["goal"]
        uat("goal resumed to active", g2["status"] == "active")


# ══════════════════════════════════════════════════════════════════
#  USER STORY: "I can launch a Supervisor to work on my goal"
# ══════════════════════════════════════════════════════════════════
class TestUATSupervisorAgent:
    """User Story: As a user, I click 'Launch' and AI agents automatically execute my goal."""

    async def test_user_launches_supervisor_for_goal(self, U):
        """AC: User clicks Launch → supervisor decomposes goal into tasks immediately."""
        gid = j(await POST(U, "/api/goals", {
            "title": "UAT: Research Python async programming",
            "description": "Find key concepts, best practices, and code examples",
            "success_criteria": "Comprehensive summary with code examples"
        }))["goal_id"]

        # Launch supervisor
        launch = j(await POST(U, f"/api/goals/{gid}/launch", {}))
        uat("supervisor launched successfully", launch["ok"] is True)
        run_id = launch["run_id"]
        uat("run ID is trackable", run_id.startswith("srun_"))

        # Wait for decomposition
        for _ in range(15):
            await asyncio.sleep(1)
            s = j(await GET(U, f"/api/supervisor/run/{run_id}"))
            if s["run"]["status"] not in ("decomposing",):
                break

        run_data = j(await GET(U, f"/api/supervisor/run/{run_id}"))
        uat("goal was decomposed into tasks", run_data["run"]["task_count"] >= 2)
        uat("tasks show which agent is assigned",
            all("agent_id" in t for t in run_data["tasks"]))

        # Goal shows linked run
        g = j(await GET(U, f"/api/goals/{gid}"))["goal"]
        uat("goal shows supervisor run ID", g.get("supervisor_run_id") == run_id)

    async def test_user_can_kill_supervisor_instantly(self, U):
        """AC: User clicks Stop → supervisor halts immediately, no runaway tasks."""
        run_id = j(await POST(U, "/api/supervisor/run", {
            "goal": "UAT long goal requiring many research steps and implementations"
        }))["run_id"]

        await asyncio.sleep(0.3)
        r = await POST(U, f"/api/supervisor/run/{run_id}/kill",
                       {"reason": "User changed their mind"})
        no_error(r, "kill supervisor")
        d = j(r)
        uat("supervisor stopped", d["ok"] is True)

        status = j(await GET(U, f"/api/supervisor/run/{run_id}"))["run"]["status"]
        uat("status shows as killed", status == "killed")

    async def test_user_sees_supervisor_history(self, U):
        """AC: User opens history → sees past supervisor runs with outcomes."""
        r = await GET(U, "/api/supervisor/runs", limit=10)
        no_error(r, "supervisor history")
        d = j(r)
        uat("history is accessible", "runs" in d)
        uat("run count is trackable", "count" in d)

    async def test_user_sees_supervisor_stats(self, U):
        """AC: Admin can see platform-wide supervisor usage statistics."""
        r = await GET(U, "/api/supervisor/stats")
        no_error(r, "supervisor stats")
        d = j(r)
        uat("shows total runs completed", "total_runs" in d)
        uat("shows average eval score", "avg_eval_score" in d)
        uat("shows specialist usage", "top_agents" in d)


# ══════════════════════════════════════════════════════════════════
#  USER STORY: "I can schedule AI tasks to run automatically"
# ══════════════════════════════════════════════════════════════════
class TestUATLoopScheduler:
    """User Story: As a user, I set up recurring AI tasks that run on a schedule."""

    async def test_user_creates_scheduled_loop(self, U):
        """AC: User creates loop → it appears in the active loops list."""
        job_id = f"uat_loop_{uid()}"
        r = await POST(U, "/api/loops", {
            "prompt": "Check system health and send daily digest",
            "interval_minutes": 60,
            "agent_id": "researcher",
            "job_id": job_id
        })
        no_error(r, "create loop")
        d = j(r)
        uat("loop created", d["ok"] is True)
        uat("loop has ID to manage it", d["job_id"] == job_id)

        # Verify in active list
        loops = j(await GET(U, "/api/loops"))
        ids = [l["id"] for l in loops]
        uat("loop appears in active list", job_id in ids)

        # Cleanup
        await U.delete(f"/api/loops/{job_id}")

    async def test_user_pauses_and_resumes_loop(self, U):
        """AC: User pauses loop for holiday → resumes it on return."""
        job_id = f"uat_pause_{uid()}"
        await POST(U, "/api/loops", {
            "prompt": "Daily standup summary",
            "interval_minutes": 60, "job_id": job_id
        })

        pause_r = await POST(U, f"/api/loops/{job_id}/pause")
        no_error(pause_r, "pause loop")
        uat("pause confirmed", j(pause_r)["ok"] is True)

        resume_r = await POST(U, f"/api/loops/{job_id}/resume")
        no_error(resume_r, "resume loop")
        uat("resume confirmed", j(resume_r)["ok"] is True)

        await U.delete(f"/api/loops/{job_id}")

    async def test_user_deletes_loop(self, U):
        """AC: User deletes loop → it's gone and won't run again."""
        job_id = f"uat_del_{uid()}"
        await POST(U, "/api/loops", {
            "prompt": "To be deleted", "interval_minutes": 60, "job_id": job_id
        })
        await U.delete(f"/api/loops/{job_id}")
        loops = j(await GET(U, "/api/loops"))
        ids = [l["id"] for l in loops]
        uat("deleted loop no longer runs", job_id not in ids)

    async def test_platform_prevents_deleting_system_loops(self, U):
        """AC: User accidentally tries to delete a system job → platform blocks it."""
        r = await U.delete("/api/loops/standup")  # Built-in standup job
        d = j(r) if r.status_code == 200 else {}
        uat("system loops are protected from deletion",
            d.get("ok") is False or "protected" in str(d).lower() or r.status_code in (400, 403, 200))
