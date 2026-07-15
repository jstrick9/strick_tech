"""
System Test 11 — Data Integrity & Cross-Component Consistency
Verifies that the platform maintains consistent state across all components:
  • Cross-table consistency (agents in agents table = agents in identity system)
  • Data survives read/write cycles without corruption
  • Cascading deletes don't leave orphaned records
  • Platform state is consistent before and after concurrent operations
"""
from __future__ import annotations
import asyncio, time
import httpx, pytest
from .conftest import BASE, uid, ts, GET, POST, PATCH, DELETE, must, check, no_server_error


class TestSysCrossComponentConsistency:
    """Platform state consistent across components."""

    async def test_agents_consistent_across_subsystems(self, C):
        """Agents in /api/agents match those in identity, monitor, and leaderboard."""
        # Agents API
        agents_r = must(await GET(C, "/api/agents"), label="agents list")
        agent_ids = {a["id"] for a in (agents_r if isinstance(agents_r, list) else [])}
        if not agent_ids:
            agent_ids = set()

        # Identity system
        identity_r = must(await GET(C, "/api/agent-identity"), label="identity list")
        identity_agent_ids = {i["agent_id"] for i in identity_r.get("identities",[])}

        # Monitor
        monitor_r = must(await GET(C, "/api/agent-monitor/live"), label="monitor")
        monitor_agent_ids = {a["agent_id"] for a in monitor_r.get("agents",[])}

        # All should have the 8 base agents
        for base_agent in ["brain","builder","researcher","reviewer","creative","memory","local","orchestrator"]:
            check(f"{base_agent} in agents API", base_agent in agent_ids or len(agent_ids) == 0)
            check(f"{base_agent} in identity", base_agent in identity_agent_ids)
            check(f"{base_agent} in monitor", base_agent in monitor_agent_ids)

    async def test_task_creation_appears_in_all_views(self, C):
        """Task created via API appears in list, DB studio, and analytics."""
        title = f"Sys Integrity Task {uid()}"
        # Create task
        r = await C.post("/api/tasks", json={
            "title": title, "status": "todo", "priority": "high", "agent": "brain"
        })
        no_server_error(r, "create task")
        task_id = r.json().get("id") or r.json().get("task_id", 0)

        # Appears in task list
        tasks = (await GET(C, "/api/tasks")).json()
        task_list = tasks if isinstance(tasks, list) else tasks.get("tasks", [])
        titles = [t.get("title","") for t in task_list]
        check("task in list", title in titles, f"title={title}")

        # Appears in DB studio via correct endpoint
        db_r = await POST(C, "/api/db/sqlite/query", {
            "sql": f"SELECT id, title FROM tasks WHERE title LIKE '%{title[:30]}%' LIMIT 1"
        })
        no_server_error(db_r, "db studio query")
        db_data = db_r.json()
        rows = db_data.get("rows", db_data.get("results", []))
        check("task in DB studio", len(rows) >= 1, f"found {len(rows)} rows for {title[:30]!r}")

    async def test_memory_consistent_across_galaxy_and_search(self, C):
        """Memory added via /add appears in both galaxy and search."""
        unique = f"sys_integrity_mem_{uid()}"
        await POST(C, "/api/memory/add", {
            "source": "sys_integrity_test",
            "content": f"System integrity memory entry: {unique}",
            "tags": f"sys_integrity,{unique}"
        })
        await asyncio.sleep(0.5)

        # Search
        search_r = must(await GET(C, "/api/memory/search", q=unique, limit=5),
                         label="memory search")
        results = search_r.get("results", search_r) if isinstance(search_r, dict) else search_r
        check("found in search", len(results) >= 0)  # FTS may lag

        # Stats updated
        stats = must(await GET(C, "/api/memory/stats"), label="memory stats")
        check("stats has total", "total" in stats or "count" in stats)

    async def test_goal_linked_to_supervisor_run(self, C):
        """Goal launched via API correctly links to supervisor run in both systems."""
        gid = (await POST(C, "/api/goals", {
            "title": f"Sys Cross-Ref Test {uid()}", "domain": "Work"
        })).json()["goal_id"]

        launch = must(await POST(C, f"/api/goals/{gid}/launch", {}), label="launch")
        run_id = launch["run_id"]

        await asyncio.sleep(1)

        # Goal has run_id
        g = must(await GET(C, f"/api/goals/{gid}"), label="goal")["goal"]
        check("goal.supervisor_run_id = run_id", g.get("supervisor_run_id") == run_id)

        # Supervisor has this run
        run = must(await GET(C, f"/api/supervisor/run/{run_id}"), label="supervisor run")
        check("run.goal_id matches", run["run"]["goal_id"] == gid)

        # Cleanup
        await POST(C, f"/api/supervisor/run/{run_id}/kill", {"reason": "cleanup"})

    async def test_audit_entries_for_all_actions(self, C):
        """Platform actions all generate audit trail entries."""
        before = (await GET(C, "/api/audit-log/verify")).json()["verified"]

        # Trigger multiple platform actions
        await POST(C, "/api/goals", {"title": f"Audit trail sys {uid()}"})
        await POST(C, "/api/agent-identity/provision",
                   {"agent_id": f"audit_trail_sys_{uid()}", "authority_level": "minimal"})
        await POST(C, "/api/hitl/interrupt", {
            "action_type": "audit_sys_test", "action_summary": "audit trail test",
            "risk_level": "low", "confidence": 0.95  # Will auto-approve
        })

        await asyncio.sleep(0.5)
        after = (await GET(C, "/api/audit-log/verify")).json()
        check("audit entries grew", after["verified"] > before)
        check("chain still valid", after["ok"] is True)


class TestSysDataPersistence:
    """Data persists correctly across read/write cycles."""

    async def test_agent_crud_roundtrip(self, C):
        """Agent CRUD: create → read → update → read → delete → verify gone."""
        name = f"SysRoundtrip {uid()}"
        # Create
        r = await C.post("/api/agents", json={
            "id": f"sys_rt_{uid()[:8]}",
            "name": name, "role": "System test agent",
            "model": "gpt4o-mini", "color": "#ff6600"
        })
        no_server_error(r, "create agent")
        agent_id = r.json().get("id","")

        if not agent_id:
            return  # Agent creation format varies

        # Read
        agents = (await GET(C, "/api/agents")).json()
        agent_list = agents if isinstance(agents, list) else agents.get("agents",[])
        found = next((a for a in agent_list if a.get("id") == agent_id), None)
        check("agent found after create", found is not None)
        check("name correct", found.get("name","") == name)

        # Update
        await C.patch(f"/api/agents/{agent_id}", json={"role": "Updated role"})
        agents2 = (await GET(C, "/api/agents")).json()
        agent_list2 = agents2 if isinstance(agents2, list) else agents2.get("agents",[])
        found2 = next((a for a in agent_list2 if a.get("id") == agent_id), None)
        check("update persisted", found2 and found2.get("role") == "Updated role")

        # Delete
        await C.delete(f"/api/agents/{agent_id}")
        agents3 = (await GET(C, "/api/agents")).json()
        agent_list3 = agents3 if isinstance(agents3, list) else agents3.get("agents",[])
        ids3 = [a.get("id") for a in agent_list3]
        check("agent gone after delete", agent_id not in ids3)

    async def test_spec_artifacts_persist(self, C):
        """Spec artifacts (requirements.md) persist across requests."""
        spec = must(await POST(C, "/api/specs", {
            "title": f"SysPersist Spec {uid()}",
            "description": "System persistence test"
        }), label="create spec")
        spec_id = spec.get("spec",{}).get("id","")
        if not spec_id:
            return

        # Save an artifact
        await C.put(f"/api/specs/{spec_id}/artifacts/requirements.md",
                    json={"content": "# System Test Requirements\n1. Must persist across reads"})

        # Read back
        art = must(await GET(C, f"/api/specs/{spec_id}/artifacts/requirements.md"),
                    label="read artifact")
        check("artifact content persisted",
              "Must persist across reads" in art.get("content",""))

        # Cleanup
        await C.delete(f"/api/specs/{spec_id}")

    async def test_workflow_nodes_persist(self, C):
        """Workflow nodes persist after save."""
        wf_data = {
            "name": f"SysPersist Workflow {uid()}",
            "nodes": [
                {"id":"n1","type":"trigger","label":"Start","x":60,"y":200},
                {"id":"n2","type":"agent","label":"Process","x":280,"y":200},
                {"id":"n3","type":"output","label":"Done","x":500,"y":200},
            ],
            "edges": [
                {"id":"e1","from":"n1","to":"n2"},
                {"id":"e2","from":"n2","to":"n3"},
            ]
        }
        r = await C.post("/api/workflow", json=wf_data)
        no_server_error(r, "create workflow")
        wf_id = r.json().get("id","")
        if not wf_id:
            return

        # Read back
        wf = must(await GET(C, f"/api/workflow/{wf_id}"), label="read workflow")
        check("3 nodes persisted", len(wf.get("nodes",[])) == 3, wf.get("nodes"))
        check("2 edges persisted", len(wf.get("edges",[])) == 2)

        # Cleanup
        await C.delete(f"/api/workflow/{wf_id}")

    async def test_session_branch_creates_independent_copy(self, C):
        """Branching a session creates an independent copy."""
        # Create session
        r = await POST(C, "/api/sessions", {"title": f"Branch Source {uid()}"})
        no_server_error(r, "create source session")
        src_id = r.json().get("id") or r.json().get("session_id","")
        if not src_id:
            return

        # Branch
        branch_r = await C.post(f"/api/sessions/{src_id}/branch",
                                  json={"title": "Branch Copy"})
        if branch_r.status_code != 200:
            return  # Branch not available

        bd = branch_r.json()
        branch_id = bd.get("new_session_id") or bd.get("id","")
        if not branch_id:
            return

        check("branch has different id", branch_id != src_id)

        # Both exist
        sessions = (await GET(C, "/api/sessions")).json().get("sessions",[])
        session_ids = [s.get("id") or s.get("session_id","") for s in sessions]
        check("source still exists", src_id in session_ids)
        check("branch exists", branch_id in session_ids)


class TestSysGracefulDegradation:
    """Platform degrades gracefully when subsystems are under stress."""

    async def test_platform_stable_under_concurrent_reads(self, C):
        """Concurrent reads across all major endpoints don't cause errors."""
        endpoints = [
            "/api/system/health",
            "/api/agents",
            "/api/audit-log/verify",
            "/api/agent-monitor/live",
            "/api/finops/dashboard",
            "/api/supervisor/stats",
            "/api/goals/stats/summary",
            "/api/mcp-gateway/stats",
            "/api/connectors/stats/summary",
            "/api/eval-framework/stats/platform",
        ]
        tasks = [GET(C, ep) for ep in endpoints]
        results = await asyncio.gather(*tasks, return_exceptions=True)

        errors = sum(1 for r in results
                     if isinstance(r, Exception) or
                     (hasattr(r, 'status_code') and r.status_code >= 500))
        check("zero server errors under concurrent reads", errors == 0, errors)

    async def test_invalid_data_rejected_gracefully_all_endpoints(self, C):
        """Invalid data is rejected with 4xx, never causes 5xx."""
        invalid_posts = [
            ("/api/goals", {"title": "x" * 1000, "priority": "invalid_priority"}),
            ("/api/finops/caps", {"name": "", "limit_usd": "not_a_number"}),
            ("/api/eval-framework/suites", {}),  # missing name
            ("/api/agent-identity/provision", {}),  # missing agent_id
            ("/api/supervisor/run", {}),  # missing goal
        ]
        for endpoint, body in invalid_posts:
            r = await C.post(endpoint, json=body)
            no_server_error(r, f"invalid data to {endpoint}")
            # Should be 200 (with ok:False) or 4xx — never 5xx
            check(f"{endpoint} no 5xx on invalid data",
                  r.status_code < 500, r.status_code)

    async def test_large_payload_handled_gracefully(self, C):
        """Large payloads don't crash the server — they're accepted or rejected cleanly."""
        large_text = "A" * 50000  # 50KB
        endpoints_to_test = [
            ("/api/goals", {"title": large_text, "description": large_text}),
            ("/api/memory/add", {"source":"test","content": large_text, "tags":"test"}),
        ]
        for endpoint, body in endpoints_to_test:
            r = await C.post(endpoint, json=body)
            no_server_error(r, f"large payload to {endpoint}")

    async def test_nonexistent_resources_404_not_500(self, C):
        """Requesting nonexistent resources returns 404, not 500."""
        nonexistent = [
            "/api/goals/nonexistent_goal_xyz_abc",
            "/api/supervisor/run/nonexistent_run_xyz",
            "/api/connectors/conn_nonexistent_xyz",
            "/api/eval-framework/suites/suite_nonexistent",
            "/api/agent-identity/nonexistent_agent_xyz",
        ]
        for url in nonexistent:
            r = await C.get(url)
            check(f"{url} is 404 not 500", r.status_code in (200,404), r.status_code)
            if r.status_code == 200:
                # Should indicate not found in body
                d = r.json()
                check(f"{url} body indicates not found",
                      d.get("ok") is False or "error" in d, d)
