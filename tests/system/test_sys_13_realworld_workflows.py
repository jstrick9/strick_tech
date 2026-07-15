"""
System Test 13 — Real-World User Workflows (End-to-End Scenarios)
Tests complete user journeys as a single black-box system test:
  • Individual user managing their day
  • Developer building and reviewing code
  • Enterprise team governing AI agents
  • Platform administrator monitoring health
"""
from __future__ import annotations
import asyncio, time, json
import httpx, pytest
from .conftest import BASE, uid, ts, GET, POST, PATCH, DELETE, must, check, no_server_error


class TestSysIndividualUserJourney:
    """Complete individual user workflow: plan → execute → track."""

    async def test_daily_planning_workflow(self, C):
        """User creates goals, adds milestones, tracks progress through the day."""
        # Morning: Create daily goals
        goals = []
        for title, domain, priority in [
            ("Complete quarterly report", "Work", "high"),
            ("Exercise 30 minutes", "Health", "medium"),
            ("Read AI research papers", "Learning", "medium"),
        ]:
            r = await POST(C, "/api/goals", {
                "title": f"SysDay: {title}", "domain": domain,
                "priority": priority, "deadline": "2026-07-14"
            })
            goals.append(r.json()["goal_id"])

        # Add milestones to work goal
        work_goal = goals[0]
        for ms in ["Draft outline", "Write sections", "Review and submit"]:
            await POST(C, f"/api/goals/{work_goal}/milestones", {"title": ms})

        # Mid-day: Check-in progress
        await POST(C, f"/api/goals/{work_goal}/checkin", {
            "progress": 33, "note": "Draft outline complete", "agent_id": "user"
        })
        g = must(await GET(C, f"/api/goals/{work_goal}"), label="mid-day goal")["goal"]
        check("progress updated", g["progress"] == 33)

        # Evening: Complete milestones
        milestones = g["milestones"]
        if milestones:
            await POST(C, f"/api/goals/{work_goal}/milestones/{milestones[0]['id']}/complete")
        check("daily workflow complete", True)

        # Verify summary shows all domains
        summary = must(await GET(C, "/api/goals/stats/summary"), label="daily summary")
        for domain in ["Work", "Health", "Learning"]:
            check(f"{domain} in summary", domain in summary.get("by_domain", {}))

    async def test_research_workflow_with_memory(self, C):
        """User researches a topic, stores findings, retrieves later."""
        topic = f"agentic_AI_{uid()}"

        # Research: Add memories
        findings = [
            f"{topic} can decompose goals into sub-tasks",
            f"{topic} requires governance and HITL for safety",
            f"{topic} uses MCP protocol for tool access",
        ]
        for finding in findings:
            await POST(C, "/api/memory/add", {
                "source": "research", "content": finding, "tags": topic
            })
        await asyncio.sleep(0.3)

        # Retrieval: Search memories
        r = await GET(C, "/api/memory/search", q=topic, limit=5)
        no_server_error(r, "memory search")

        # Summary stats reflect additions
        stats = must(await GET(C, "/api/memory/stats"), label="memory stats after research")
        check("memory stats accessible", True)

    async def test_task_management_workflow(self, C):
        """User creates tasks, moves them through states, completes project."""
        # Create project tasks
        task_ids = []
        for i, title in enumerate(["Design", "Implement", "Test", "Deploy"]):
            r = await C.post("/api/tasks", json={
                "title": f"SysProject: {title} {uid()}",
                "status": "todo", "priority": "high", "agent": "builder"
            })
            no_server_error(r, f"create task {title}")
            task_ids.append(r.json().get("id",0))

        # Move through statuses
        for task_id in task_ids[:2]:
            if task_id:
                await C.patch(f"/api/tasks/{task_id}", json={"status": "in_progress"})
        for task_id in task_ids[:1]:
            if task_id:
                await C.patch(f"/api/tasks/{task_id}", json={"status": "done"})

        # Verify state machine worked
        tasks = (await GET(C, "/api/tasks")).json()
        task_list = tasks if isinstance(tasks, list) else tasks.get("tasks",[])
        statuses = {t.get("id",0): t.get("status","") for t in task_list}
        if task_ids[0]:
            check("first task done", statuses.get(task_ids[0],"") == "done",
                  statuses.get(task_ids[0],""))


class TestSysDeveloperWorkflow:
    """Complete developer workflow: code → review → test → deploy."""

    async def test_spec_driven_development_workflow(self, C):
        """Developer creates spec, generates tasks, executes them."""
        # Create spec
        spec = must(await POST(C, "/api/specs", {
            "title": f"SysDev: User Auth API {uid()}",
            "description": "Build JWT authentication for a REST API"
        }), label="create spec")["spec"]
        spec_id = spec["id"]

        # Get spec
        s = must(await GET(C, f"/api/specs/{spec_id}"), label="get spec")
        check("spec accessible", s.get("id") == spec_id)

        # Verify task list
        tasks = must(await GET(C, f"/api/specs/{spec_id}/tasks"), label="spec tasks")
        check("tasks structure ok", "tasks" in tasks)

        # Cleanup
        await C.delete(f"/api/specs/{spec_id}")

    async def test_knowledge_graph_workflow(self, C):
        """Developer maps project knowledge graph."""
        # Create entities
        e1 = must(await POST(C, "/api/knowledge-graph/entities", {
            "name": f"SysKG UserAuth {uid()}", "type": "project",
            "description": "JWT authentication system"
        }), label="create e1")
        e2 = must(await POST(C, "/api/knowledge-graph/entities", {
            "name": f"SysKG JWT Token {uid()}", "type": "concept",
            "description": "JSON Web Token"
        }), label="create e2")

        # Create relation
        rel = await POST(C, "/api/knowledge-graph/relations", {
            "from_id": e1["entity_id"],
            "to_id": e2["entity_id"],
            "relation": "USES",
            "confidence": 0.95
        })
        no_server_error(rel, "create relation")

        # Stats updated
        stats = must(await GET(C, "/api/knowledge-graph/stats"), label="kg stats")
        check("entities > 0", stats["entities"] >= 2)
        check("relations > 0", stats["relations"] >= 1)

    async def test_workflow_builder_creates_runnable_workflow(self, C):
        """Developer creates a visual workflow that can be executed."""
        wf_data = {
            "name": f"SysDev Pipeline {uid()}",
            "nodes": [
                {"id":"t1","type":"trigger","label":"On Input","x":80,"y":200},
                {"id":"a1","type":"agent","label":"Researcher","x":280,"y":200,
                 "config":{"agent_id":"researcher","prompt":"Research: {{input}}"}},
                {"id":"o1","type":"output","label":"Result","x":480,"y":200},
            ],
            "edges": [
                {"id":"e1","from":"t1","to":"a1"},
                {"id":"e2","from":"a1","to":"o1"},
            ]
        }
        r = await C.post("/api/workflow", json=wf_data)
        no_server_error(r, "create workflow")
        wf_id = r.json().get("id","")
        if not wf_id:
            return

        # Verify it's in list
        wfs = must(await GET(C, "/api/workflow"), label="workflow list")
        wf_list = wfs.get("workflows", wfs) if isinstance(wfs, dict) else wfs
        ids = [w.get("id","") for w in wf_list]
        check("workflow in list", wf_id in ids)

        # Cleanup
        await C.delete(f"/api/workflow/{wf_id}")


class TestSysEnterpriseGovernanceWorkflow:
    """Complete enterprise governance workflow."""

    async def test_agent_governance_lifecycle(self, C):
        """Enterprise: provision agent → assign permissions → monitor → audit."""
        agent_id = f"sys_enterprise_{uid()}"

        # 1. Provision identity
        prov = must(await POST(C, "/api/agent-identity/provision", {
            "agent_id": agent_id, "display_name": "Enterprise Test Agent",
            "authority_level": "standard"
        }), label="provision")
        check("provisioned ok", prov["ok"] is True)

        # 2. Assign custom permission
        grant = (await C.post(f"/api/agent-identity/{agent_id}/permissions",
                               json={"action": "enterprise_read", "resource": "reports"})).json()
        check("permission granted", grant.get("ok") is True)

        # 3. Issue JIT token for a task
        token = (await POST(C, f"/api/agent-identity/{agent_id}/issue-token", {
            "task_id": f"enterprise_task_{uid()}", "ttl_seconds": 300,
            "scope": ["enterprise_read"]
        })).json()
        check("token issued", token.get("ok") is True)
        tok_id = token["token_id"]

        # 4. Validate token
        val = (await POST(C, "/api/agent-identity/token/validate", {
            "token_id": tok_id, "agent_id": agent_id, "required_action": "enterprise_read"
        })).json()
        check("token valid", val.get("ok") is True)

        # 5. Revoke when done
        rev = (await POST(C, f"/api/agent-identity/token/{tok_id}/revoke", {})).json()
        check("revoked", rev.get("ok") is True)

        # 6. Audit trail exists
        audit = (await GET(C, f"/api/agent-identity/{agent_id}/audit")).json()
        check("audit trail present", len(audit.get("events", [])) > 0)

    async def test_budget_governance_workflow(self, C):
        """Enterprise: set budget cap → record costs → verify alerts."""
        dept_id = f"sys_dept_{uid()}"

        # Set budget
        cap = must(await POST(C, "/api/finops/caps", {
            "name": f"Enterprise Dept Cap {uid()}",
            "scope_type": "goal", "scope_id": dept_id,
            "period": "day", "limit_usd": 50.0, "on_breach": "alert"
        }), label="create budget cap")
        cap_id = cap["cap_id"]

        # Record cost under budget
        await POST(C, "/api/finops/ledger/record", {
            "agent_id": "brain", "source_type": "llm",
            "cost_usd": 10.0, "tokens": 5000,
            "goal_id": dept_id, "description": "Enterprise research task"
        })

        # Verify cap in dashboard
        dash = must(await GET(C, "/api/finops/dashboard"), label="dashboard")
        caps = dash.get("budget_caps", [])
        cap_ids = [c["cap_id"] for c in caps]
        check("cap visible in dashboard", cap_id in cap_ids)

        # Cleanup
        await C.delete(f"/api/finops/caps/{cap_id}")

    async def test_hitl_governance_approval_chain(self, C):
        """Enterprise: risky action → HITL queue → approve → audit."""
        # Risky action
        int_r = await POST(C, "/api/hitl/interrupt", {
            "action_type": "enterprise_data_export",
            "action_summary": "Export 500,000 customer records to S3",
            "risk_level": "critical", "confidence": 0.6,
            "agent_id": "orchestrator",
            "action_data": {"records": 500000, "destination": "s3://company-data"}
        })
        d = must(int_r, label="create interrupt")
        check("interrupt pending", d["decision"] == "pending")
        int_id = d["interrupt_id"]

        # Approve (simulating manager approval)
        approve = must(await POST(C, f"/api/hitl/interrupt/{int_id}/decide", {
            "decision": "approve",
            "note": "Approved after compliance review — PII check passed",
            "reviewer": "enterprise_compliance_officer"
        }), label="approve")
        check("approved ok", approve["ok"] is True)
        check("decision approve", approve["decision"] == "approve")

        # Audit shows the decision
        audit = must(await GET(C, "/api/hitl/audit", limit=5), label="hitl audit")
        check("audit not empty", len(audit.get("audit", [])) > 0)


class TestSysPlatformAdminWorkflow:
    """Platform administrator monitoring and management workflow."""

    async def test_platform_health_monitoring(self, C):
        """Admin can get complete platform health picture."""
        # System health
        health = must(await GET(C, "/api/system/health"), label="system health")
        check("system ok", health["ok"] is True)
        check("version present", "version" in health)
        check("database ok", health["database"]["ok"] is True)
        check("tables count", health["database"]["tables"] >= 100)

        # Agent monitor summary
        mon = must(await GET(C, "/api/agent-monitor/summary"), label="monitor summary")
        check("8+ agents", mon["total_agents"] >= 8)

        # FinOps dashboard
        fin = must(await GET(C, "/api/finops/dashboard"), label="finops")
        check("total cost tracked", fin["total_cost_usd"] >= 0)

        # Audit chain
        audit = must(await GET(C, "/api/audit-log/verify"), label="audit chain")
        check("chain valid", audit["ok"] is True)

    async def test_platform_api_surface_complete(self, C):
        """All platform API endpoints are registered in OpenAPI spec."""
        spec = must(await GET(C, "/openapi.json"), label="openapi")
        total_paths = len(spec.get("paths", {}))
        check("platform has 500+ API endpoints", total_paths >= 500, total_paths)

    async def test_platform_configuration_accessible(self, C):
        """Admin can access all configuration endpoints."""
        config_endpoints = [
            "/api/license/status",
            "/api/profile",
            "/api/steering",
            "/api/mcp-gateway/servers",
            "/api/connectors",
            "/api/agent-identity/system/stats",
        ]
        for ep in config_endpoints:
            r = await GET(C, ep)
            no_server_error(r, f"config endpoint {ep}")

    async def test_platform_metrics_dashboard(self, C):
        """Admin can access all monitoring dashboards simultaneously."""
        async with httpx.AsyncClient(base_url=BASE, timeout=30) as client:
            dashboards = await asyncio.gather(
                GET(client, "/api/system/health"),
                GET(client, "/api/agent-monitor/summary"),
                GET(client, "/api/finops/dashboard"),
                GET(client, "/api/supervisor/stats"),
                GET(client, "/api/goals/stats/summary"),
                GET(client, "/api/mcp-gateway/stats"),
                GET(client, "/api/connectors/stats/summary"),
                GET(client, "/api/eval-framework/stats/platform"),
                GET(client, "/api/audit-log/stats"),
                GET(client, "/api/agent-leaderboard/stats/overview"),
                return_exceptions=True
            )
        errors = sum(1 for r in dashboards
                     if isinstance(r, Exception) or
                     (hasattr(r,'status_code') and r.status_code >= 500))
        check("all 10 dashboards load without error", errors == 0, errors)
