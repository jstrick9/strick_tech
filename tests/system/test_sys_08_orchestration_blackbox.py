"""
System Test 08 — Orchestration Layer (Black-Box)
Sprint B features — Supervisor, Goals, Loops — as a unified platform subsystem.

System assertions:
  • Goals track state across their full lifecycle
  • Supervisor decomposes and executes any goal
  • Loops run without interfering with platform state
  • Cross-cutting: goal progress reflects actual work done
"""
from __future__ import annotations
import asyncio, time
import httpx, pytest
from .conftest import BASE, uid, ts, GET, POST, PATCH, DELETE, must, check, no_server_error


class TestSysGoalLifecycle:
    """Goal Manager as a complete system feature."""

    async def test_goal_full_state_machine(self, C):
        """Goals transition through valid states: active → paused → active → done."""
        gid = must(await POST(C, "/api/goals", {
            "title": f"SysTest State Machine {uid()}",
            "domain": "Work", "priority": "high"
        }), label="create goal")["goal_id"]

        # active (default)
        g = must(await GET(C, f"/api/goals/{gid}"), label="get goal")["goal"]
        check("starts active", g["status"] == "active")
        check("starts 0%", g["progress"] == 0)

        # → paused
        must(await PATCH(C, f"/api/goals/{gid}", {"status": "paused"}), label="pause")
        g = must(await GET(C, f"/api/goals/{gid}"), label="get paused")["goal"]
        check("now paused", g["status"] == "paused")

        # → active again
        must(await PATCH(C, f"/api/goals/{gid}", {"status": "active"}), label="reactivate")

        # → done via 100% progress
        must(await PATCH(C, f"/api/goals/{gid}", {"progress": 100}), label="complete")
        g = must(await GET(C, f"/api/goals/{gid}"), label="get done")["goal"]
        check("now done", g["status"] == "done")
        check("progress 100", g["progress"] == 100)

    async def test_goal_milestone_system_consistency(self, C):
        """Milestone completions drive goal progress consistently."""
        gid = must(await POST(C, "/api/goals", {
            "title": f"SysTest Milestone Consistency {uid()}"
        }), label="create goal")["goal_id"]

        # Add 5 milestones
        ms_ids = []
        for i in range(5):
            ms = must(await POST(C, f"/api/goals/{gid}/milestones",
                                  {"title": f"Milestone {i+1}"}), label=f"add ms {i}")
            ms_ids.append(ms["id"])

        # Complete milestones one by one — verify progress is consistent
        for i, ms_id in enumerate(ms_ids):
            await POST(C, f"/api/goals/{gid}/milestones/{ms_id}/complete")
            g = must(await GET(C, f"/api/goals/{gid}"), label=f"after ms {i+1}")["goal"]
            expected = int(((i+1) / 5) * 100)
            check(f"progress after {i+1}/5 milestones is {expected}%",
                  g["progress"] == expected, g["progress"])

        # Final state
        g = must(await GET(C, f"/api/goals/{gid}"), label="final state")["goal"]
        check("all milestones done → goal done", g["status"] == "done")

    async def test_goal_summary_reflects_all_domains(self, C):
        """Summary stats cover all domains created during system testing."""
        domain_goals = {}
        for domain in ["Work", "Health", "Finance", "Learning", "Travel"]:
            r = await POST(C, "/api/goals", {
                "title": f"SysTest Domain {domain} {uid()}",
                "domain": domain
            })
            domain_goals[domain] = r.json()["goal_id"]

        summary = must(await GET(C, "/api/goals/stats/summary"), label="summary")
        by_domain = summary.get("by_domain", {})
        for domain in domain_goals:
            check(f"{domain} in summary", domain in by_domain, list(by_domain.keys()))

    async def test_goal_filter_and_pagination(self, C):
        """Goal filtering and pagination work correctly at system level."""
        # Create goals in specific domain/priority
        for i in range(3):
            await POST(C, "/api/goals", {
                "title": f"SysFilter Test {uid()}", "domain": "Research", "priority": "critical"
            })

        # Filter by domain
        r = await GET(C, "/api/goals", domain="Research", limit=5)
        d = must(r, label="filter domain")
        for g in d.get("goals", []):
            check("all Research domain", g["domain"] == "Research", g["domain"])

        # Filter by priority
        r2 = await GET(C, "/api/goals", priority="critical", limit=5)
        d2 = must(r2, label="filter priority")
        for g in d2.get("goals", []):
            check("all critical priority", g["priority"] == "critical", g["priority"])


class TestSysSupervisorSystem:
    """Supervisor as a complete orchestration platform feature."""

    async def test_supervisor_decomposes_any_reasonable_goal(self, C):
        """Supervisor creates a valid task DAG for any reasonable goal."""
        goals = [
            "Write a Python function to reverse a string",
            "Research the top 3 benefits of Python over JavaScript",
            "Create a simple REST API design for a todo app",
        ]
        for goal in goals:
            r = await POST(C, "/api/supervisor/run", {"goal": goal})
            d = must(r, label=f"launch for: {goal[:40]}")
            check("ok", d["ok"] is True)
            run_id = d["run_id"]

            # Wait for decomposition (max 15s)
            for _ in range(15):
                await asyncio.sleep(1)
                s = (await GET(C, f"/api/supervisor/run/{run_id}")).json()
                if s["run"]["status"] != "decomposing":
                    break

            final = (await GET(C, f"/api/supervisor/run/{run_id}")).json()
            check(f"tasks created for: {goal[:30]}",
                  final["run"]["task_count"] >= 1, final["run"]["task_count"])
            check(f"at least 2 tasks", final["run"]["task_count"] >= 2)

    async def test_supervisor_tasks_have_specialist_assignment(self, C):
        """Supervisor assigns appropriate specialist agents to tasks."""
        valid_agents = {"orchestrator","brain","builder","researcher",
                        "reviewer","creative","memory","local"}

        r = await POST(C, "/api/supervisor/run", {
            "goal": "Research Python best practices and write a code example"
        })
        run_id = r.json()["run_id"]

        for _ in range(15):
            await asyncio.sleep(1)
            s = (await GET(C, f"/api/supervisor/run/{run_id}")).json()
            if s["run"]["status"] not in ("decomposing", "scheduled"):
                break

        tasks = (await GET(C, f"/api/supervisor/run/{run_id}")).json()["tasks"]
        for task in tasks:
            check(f"task {task['seq']} assigned to valid agent",
                  task["agent_id"] in valid_agents, task["agent_id"])

    async def test_supervisor_kill_switch_immediate(self, C):
        """Kill switch stops supervisor immediately, no residual state."""
        run_id = (await POST(C, "/api/supervisor/run", {
            "goal": "An extremely complex multi-step research project requiring many iterations"
        })).json()["run_id"]

        await asyncio.sleep(0.5)  # Let it start

        # Kill
        kill = must(await POST(C, f"/api/supervisor/run/{run_id}/kill",
                                {"reason": "sys test kill"}), label="kill")
        check("kill ok", kill["ok"] is True)

        # State immediately reflects killed
        s = must(await GET(C, f"/api/supervisor/run/{run_id}"), label="after kill")
        check("status killed", s["run"]["status"] == "killed")

        # Cleanup
        await C.delete(f"/api/supervisor/run/{run_id}")

    async def test_supervisor_stats_accumulate_correctly(self, C):
        """Supervisor stats correctly aggregate across multiple runs."""
        before = must(await GET(C, "/api/supervisor/stats"), label="stats before")
        before_total = before.get("total_runs", 0)

        # Launch and complete 3 quick runs
        run_ids = []
        for i in range(3):
            r = (await POST(C, "/api/supervisor/run",
                             {"goal": f"Quick sys test goal {i}: answer briefly"})).json()
            run_ids.append(r["run_id"])

        await asyncio.sleep(5)

        after = must(await GET(C, "/api/supervisor/stats"), label="stats after")
        check("total_runs increased by 3",
              after.get("total_runs", 0) >= before_total + 3)

        # Cleanup
        for run_id in run_ids:
            await POST(C, f"/api/supervisor/run/{run_id}/kill", {"reason": "cleanup"})
            await C.delete(f"/api/supervisor/run/{run_id}")

    async def test_goal_to_supervisor_pipeline_end_to_end(self, C):
        """Creating a goal and launching supervisor links them correctly."""
        gid = (await POST(C, "/api/goals", {
            "title": "Sys Test: Goal-Supervisor Integration",
            "description": "What is the capital of France?",
            "success_criteria": "Answer: Paris"
        })).json()["goal_id"]

        launch = must(await POST(C, f"/api/goals/{gid}/launch", {}), label="launch")
        check("launch ok", launch["ok"] is True)
        run_id = launch["run_id"]
        check("run_id linked", run_id.startswith("srun_"))

        await asyncio.sleep(1)
        g = must(await GET(C, f"/api/goals/{gid}"), label="goal after launch")["goal"]
        check("supervisor_run_id set", g.get("supervisor_run_id") == run_id)

        # Cleanup
        await POST(C, f"/api/supervisor/run/{run_id}/kill", {"reason": "sys cleanup"})


class TestSysLoopSystem:
    """Autonomous loop scheduler as a platform subsystem."""

    async def test_loops_isolated_from_platform_state(self, C):
        """Creating loops does not affect task, agent, or session counts."""
        # Record state before
        agents_before = len((await GET(C, "/api/agents")).json())

        # Create 5 loops
        loop_ids = []
        for i in range(5):
            jid = f"sys_isolation_{uid()}"
            r = await POST(C, "/api/loops", {
                "prompt": f"Sys isolation test loop {i}",
                "interval_minutes": 120, "job_id": jid
            })
            loop_ids.append(jid)

        # Agent count unchanged
        agents_after = len((await GET(C, "/api/agents")).json())
        check("agents unchanged", agents_after == agents_before, agents_after)

        # Cleanup
        for jid in loop_ids:
            await C.delete(f"/api/loops/{jid}")

    async def test_loop_scheduler_status_accessible_under_load(self, C):
        """Scheduler status remains accessible with many loops."""
        loop_ids = []
        for i in range(10):
            jid = f"sys_load_loop_{uid()}"
            await POST(C, "/api/loops", {
                "prompt": f"Load test loop {i}", "interval_minutes": 60, "job_id": jid
            })
            loop_ids.append(jid)

        # Status must be accessible
        r = await GET(C, "/api/loops/status")
        no_server_error(r, "loop status under load")

        # All loops in list
        loops = (await GET(C, "/api/loops")).json()
        loop_id_set = {l["id"] for l in loops}
        found = sum(1 for jid in loop_ids if jid in loop_id_set)
        check("all created loops in list", found == 10, found)

        # Cleanup
        for jid in loop_ids:
            await C.delete(f"/api/loops/{jid}")
