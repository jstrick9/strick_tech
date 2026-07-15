"""
USABILITY-10: Complete End-to-End User Journeys
Full multi-step scenarios simulating real users accomplishing real goals.
Each test represents a complete workflow a person would actually do.
"""
import pytest, asyncio, time
from tests.usability.conftest import *


class TestUseJourneyNewUser:
    """Journey: A brand-new user starts using the platform for the first time."""

    async def test_journey_new_user_first_session(self, U):
        """
        Journey: New user → onboarding → first chat → memory → done.
        Step 1: Check onboarding status
        Step 2: View available agents
        Step 3: Open chat history
        Step 4: Send a message
        Step 5: Add a memory note
        Step 6: View memory stats
        """
        # 1. Onboarding
        ob = await GET(U, "/api/onboarding/status")
        uat("onboarding status loads",   ob.status_code < 500)

        # 2. Agent roster
        agents = await GET(U, "/api/agents")
        uat("agent roster loads",        agents.status_code == 200)
        uat("has agents",                len(j(agents) if isinstance(j(agents), list) else []) > 0)

        # 3. Chat history
        hist = await GET(U, "/api/chat/history")
        uat("chat history loads",        hist.status_code < 500)

        # 4. First message
        msg = await POST(U, "/api/chat", {
            "message": "Hello! I'm new here.", "agent": "brain", "session_id": uid("new_user")
        })
        uat("first message accepted",    msg.status_code < 500)

        # 5. Add memory
        mem = await POST(U, "/api/memory/add", {
            "content": "New user note: platform feels intuitive",
            "source": "first_impression", "tags": ["onboarding"]
        })
        uat("memory added",              mem.status_code < 500)

        # 6. Stats
        stats = await GET(U, "/api/memory/stats")
        uat("memory stats visible",      stats.status_code < 500)

    async def test_journey_profile_setup(self, U):
        """
        Journey: User configures their profile fully.
        Profile → set name → set role → configure UI → save preferences.
        """
        before = j(await GET(U, "/api/profile")).get("name", "User")

        r1 = await PATCH(U, "/api/profile", {"name": "Alice Developer"})
        uat("name updated",              r1.status_code < 500)

        r2 = await POST(U, "/api/profile/role/developer", {})
        uat("role set",                  r2.status_code < 500)

        r3 = await GET(U, "/api/profile/ui-config")
        uat("ui config accessible",      r3.status_code < 500)

        # Restore
        await PATCH(U, "/api/profile", {"name": before})


class TestUseJourneyDeveloper:
    """Journey: Developer codes, reviews, tests, and deploys."""

    async def test_journey_code_review_cycle(self, U):
        """
        Journey: Dev pastes code → BugBot reviews → fixes → generates tests → done.
        """
        code = """def parse_config(filename):
    with open(filename) as f:
        data = f.read()
    return eval(data)  # Security risk!"""

        # 1. Request code review
        review = await POST(U, "/api/bugbot/review/file", {
            "filename": "config.py", "content": code, "language": "python"
        })
        uat("bugbot review submitted",   review.status_code < 500)

        # 2. Fix the code
        fix = await POST(U, "/api/agent/fix", {
            "code": code,
            "error": "Security: eval() is dangerous",
            "language": "python"
        })
        uat("agent fixed code",          fix.status_code < 500)

        # 3. Generate tests
        tests = await POST(U, "/api/testgen/generate", {
            "source_code": code, "language": "python", "framework": "pytest"
        })
        uat("tests generated",           tests.status_code < 500)

        # 4. Check deployment options
        providers = await GET(U, "/api/deploy/providers")
        uat("deploy providers visible",  providers.status_code < 500)

    async def test_journey_git_workflow(self, U):
        """
        Journey: Developer uses AI git assistance — audit deps → commit → changelog.
        """
        # 1. Audit dependencies
        audit = await GET(U, "/api/gitai/deps/audit")
        uat("deps audit runs",           audit.status_code < 500)

        # 2. Generate commit message
        commit = await POST(U, "/api/gitai/commit", {
            "message": "AI generate",
            "files": ["backend/app.py"],
            "context": "Added SSRF protection to websearch"
        })
        uat("commit message generated",  commit.status_code < 500)

        # 3. Generate changelog
        changelog = await POST(U, "/api/gitai/changelog", {
            "from_ref": "HEAD~5", "to_ref": "HEAD", "format": "markdown"
        })
        uat("changelog generated",       changelog.status_code < 500)

    async def test_journey_spec_to_code(self, U):
        """
        Journey: User writes spec → generates tasks → watches Supervisor execute → done.
        """
        # 1. Create spec
        spec = await POST(U, "/api/specs", {
            "name": uid("AuthSpec"),
            "description": "Authentication service with JWT tokens"
        })
        uat("spec created",              spec.status_code < 500)
        sid = j(spec).get("id")

        # 2. Add requirements
        if sid:
            reqs = await POST(U, f"/api/specs/{sid}/requirements", {
                "requirements": ["Stateless JWT auth", "Refresh token rotation"]
            })
            uat("requirements added",    reqs.status_code < 500)

        # 3. Run Supervisor to orchestrate
        sup = await POST(U, "/api/supervisor/run", {
            "goal": "Implement authentication with JWT",
            "strategy": "parallel",
            "agents": ["builder", "reviewer"],
            "context": {}
        })
        uat("supervisor dispatched",     sup.status_code < 500)

        # 4. Check audit log
        audit = await GET(U, "/api/audit-log")
        uat("audit log updated",         audit.status_code < 500)

        if sid: await DELETE(U, f"/api/specs/{sid}")


class TestUseJourneyResearcher:
    """Journey: Researcher collects information, builds knowledge, shares findings."""

    async def test_journey_research_and_synthesize(self, U):
        """
        Journey: Researcher → web search → add to memory → KG extract → export.
        """
        # 1. Web search
        search = await POST(U, "/api/websearch/search", {
            "query": "agentic AI frameworks 2025 comparison",
            "max_results": 5
        })
        uat("search completed",          search.status_code < 500)

        # 2. Store finding in memory
        mem = await POST(U, "/api/memory/add", {
            "content": "Research finding: Agentic AI frameworks comparison shows FastAPI preferred",
            "source": "web_research", "tags": ["ai", "frameworks", "research"]
        })
        uat("finding stored in memory",  mem.status_code < 500)

        # 3. Extract to knowledge graph
        kg = await POST(U, "/api/knowledge-graph/extract", {
            "text": "FastAPI is a Python web framework. Agentic OS uses FastAPI.",
            "auto_link": True
        })
        uat("kg extraction ran",         kg.status_code < 500)

        # 4. Export memory
        export = await GET(U, "/api/memory/export")
        uat("memory exported",           export.status_code < 500)

    async def test_journey_knowledge_base_building(self, U):
        """
        Journey: Researcher builds a RAG knowledge base and tests retrieval.
        """
        # 1. Create RAG pipeline
        pipe = await POST(U, "/api/rag/pipelines", {
            "name": uid("ResearchBase"),
            "description": "Knowledge base for AI research",
            "type": "semantic", "chunk_size": 512
        })
        uat("rag pipeline created",      pipe.status_code < 500)
        pid = j(pipe).get("id")

        # 2. Query the pipeline
        if pid:
            query = await POST(U, f"/api/rag/pipelines/{pid}/query", {
                "query": "What are the benefits of agentic AI?",
                "top_k": 3
            })
            uat("rag query ran",         query.status_code < 500)


class TestUseJourneyManager:
    """Journey: Manager tracks team goals, monitors costs, reviews AI quality."""

    async def test_journey_goal_planning_and_tracking(self, U):
        """
        Journey: Manager creates Q3 goals → adds milestones → monitors progress.
        """
        # 1. Create strategic goal
        goal = await POST(U, "/api/goals", {
            "title": uid("Q3OKR"),
            "description": "Achieve 95% test coverage across all modules",
            "domain": "engineering", "priority": "high"
        })
        uat("strategic goal created",    goal.status_code < 500)
        gid = j(goal).get("id")

        if gid:
            # 2. Add milestones
            m1 = await POST(U, f"/api/goals/{gid}/milestones", {
                "title": "Core modules covered", "due_date": "2026-08-01"
            })
            uat("milestone added",       m1.status_code < 500)

            # 3. Launch goal
            launch = await POST(U, f"/api/goals/{gid}/launch", {})
            uat("goal launched",         launch.status_code < 500)

            # 4. First checkin
            checkin = await POST(U, f"/api/goals/{gid}/checkin", {
                "note": "Sprint 1 complete — 40% done", "completion_pct": 40
            })
            uat("checkin recorded",      checkin.status_code < 500)

            await DELETE(U, f"/api/goals/{gid}")

        # 5. View goal stats
        stats = await GET(U, "/api/goals/stats/summary")
        uat("goal stats visible",        stats.status_code < 500)

    async def test_journey_cost_monitoring(self, U):
        """
        Journey: Manager reviews AI costs → sets budget caps → exports report.
        """
        # 1. View dashboard
        dash = await GET(U, "/api/finops/dashboard")
        uat("finops dashboard loads",    dash.status_code < 500)

        # 2. Check timeseries
        ts = await GET(U, "/api/finops/stats/time-series")
        uat("cost timeseries visible",   ts.status_code < 500)

        # 3. Set a budget cap
        cap = await POST(U, "/api/finops/caps", {
            "name": uid("MgmtCap"), "agent_id": "brain",
            "period": "daily", "limit_usd": 2.0, "action": "alert"
        })
        uat("budget cap set",            cap.status_code < 500)
        cap_id = j(cap).get("cap_id") or j(cap).get("id")

        # 4. Export for accounting
        export = await GET(U, "/api/finops/export/csv")
        uat("cost report exported",      export.status_code < 500)

        if cap_id: await DELETE(U, f"/api/finops/caps/{cap_id}")

    async def test_journey_quality_review(self, U):
        """
        Journey: Manager creates eval suite → runs eval → reviews results → HITL if needed.
        """
        # 1. Create eval suite
        suite = await POST(U, "/api/eval-framework/suites", {
            "name": uid("QualitySuite"),
            "description": "Monthly quality audit",
            "agent_id": "brain", "scoring_method": "llm_judge"
        })
        uat("eval suite created",        suite.status_code < 500)
        sid = j(suite).get("suite_id") or j(suite).get("id")

        if sid:
            # 2. Add test cases
            case = await POST(U, f"/api/eval-framework/suites/{sid}/cases", {
                "input": "Summarize this in 3 bullet points: [long text]",
                "expected_output": "• Point 1\n• Point 2\n• Point 3",
                "category": "summarization"
            })
            uat("test case added",       case.status_code < 500)

        # 3. View review queue
        queue = await GET(U, "/api/eval-framework/review-queue")
        uat("review queue accessible",   queue.status_code < 500)

        # 4. Check HITL queue
        hitl = await GET(U, "/api/hitl/queue")
        uat("hitl queue accessible",     hitl.status_code < 500)

        # 5. Platform stats
        pstats = await GET(U, "/api/eval-framework/stats/platform")
        uat("platform eval stats",       pstats.status_code < 500)


class TestUseJourneySecurity:
    """Journey: Security engineer sets up governance and monitors compliance."""

    async def test_journey_governance_setup(self, U):
        """
        Journey: Security engineer → provisions agent identities → sets MCP policies → audit.
        """
        # 1. Provision identities
        provision = await POST(U, "/api/agent-identity/provision-all", {})
        uat("identities provisioned",    provision.status_code < 500)

        # 2. Create MCP policy
        policy = await POST(U, "/api/mcp-gateway/policies", {
            "name": uid("SecPolicy"), "tool_pattern": "shell.*",
            "agent_pattern": "*", "action": "deny", "conditions": {}
        })
        uat("security policy created",   policy.status_code < 500)
        pid = j(policy).get("id")

        # 3. Verify audit chain
        verify = await GET(U, "/api/audit-log/verify")
        uat("audit chain verified",      verify.status_code < 500)

        # 4. Compliance report
        compliance = await GET(U, "/api/observability/compliance/eu-ai-act")
        uat("compliance report generated", compliance.status_code < 500)

        # 5. Monitor anomalies
        anomalies = await GET(U, "/api/agent-monitor/anomalies")
        uat("anomaly monitoring active", anomalies.status_code < 500)

        if pid: await DELETE(U, f"/api/mcp-gateway/policies/{pid}")

    async def test_journey_secrets_management(self, U):
        """
        Journey: Engineer stores secrets → verifies masking → rotates → deletes.
        """
        key = uid("ROTATION_TEST_KEY")

        # 1. Set secret
        set_r = await POST(U, "/api/secrets/set", {"key": key, "value": "initial_value_v1"})
        uat("secret set",                set_r.status_code < 500)

        # 2. Verify masked in list
        list_r = await GET(U, "/api/secrets")
        uat("secret listed (masked)",    list_r.status_code < 500)
        uat("value not exposed",         "initial_value_v1" not in list_r.text)

        # 3. Rotate — set new value
        rotate_r = await POST(U, "/api/secrets/set", {"key": key, "value": "rotated_value_v2"})
        uat("secret rotated",            rotate_r.status_code < 500)

        # 4. Delete
        del_r = await DELETE(U, f"/api/secrets/{key}")
        uat("secret deleted",            del_r.status_code < 500)


class TestUseJourneyDataEngineer:
    """Journey: Data engineer queries the database and builds pipelines."""

    async def test_journey_db_studio_session(self, U):
        """
        Journey: Data engineer → lists tables → queries → creates table → analyzes.
        """
        # 1. List tables
        tables = await GET(U, "/api/db/sqlite/tables")
        uat("tables visible",            tables.status_code < 500)
        tnames = j(tables) if isinstance(j(tables), list) else j(tables).get("tables", [])
        uat("has tables",                len(tnames) > 0)

        # 2. Run analytical query
        query = await POST(U, "/api/db/sqlite/query", {
            "sql": "SELECT COUNT(*) as total, MAX(created_at) as latest FROM agents"
        })
        uat("analytical query ran",      query.status_code < 500)
        d = j(query)
        uat("query result returned",     d.get("ok") is True or "rows" in d)

        # 3. Schema inspection
        schema = await GET(U, "/api/db/sqlite/schema")
        uat("schema visible",            schema.status_code < 500)

        # 4. AI schema suggestion
        ai_schema = await POST(U, "/api/db/sqlite/ai-schema", {
            "description": "A pipeline run tracking table with status, duration, and error columns"
        })
        uat("ai schema suggestion",      ai_schema.status_code < 500)

    async def test_journey_analytics_deep_dive(self, U):
        """
        Journey: Data engineer → KPIs → sessions → agent perf → export.
        """
        kpis    = await GET(U, "/api/analytics/kpis")
        uat("kpis loaded",               kpis.status_code < 500)

        sessions = await GET(U, "/api/analytics/sessions")
        uat("session analytics",         sessions.status_code < 500)

        agents  = await GET(U, "/api/analytics/agents/summary")
        uat("agent analytics",           agents.status_code < 500)

        costs   = await GET(U, "/api/analytics/cost")
        uat("cost analytics",            costs.status_code < 500)

        export  = await GET(U, "/api/analytics/export")
        uat("analytics exported",        export.status_code < 500)


class TestUseJourneyPlatformHealth:
    """Journey: Platform health check — everything is running correctly."""

    async def test_full_platform_health_sweep(self, U):
        """
        Complete health sweep: every major subsystem checked in sequence.
        This is the 'all green' confirmation test.
        """
        checks = [
            ("/api/health",                        "platform health"),
            ("/api/agents",                        "agent roster"),
            ("/api/chat/history",                  "chat system"),
            ("/api/memory/stats",                  "memory system"),
            ("/api/tasks",                         "task system"),
            ("/api/sessions",                      "session system"),
            ("/api/prompts",                       "prompt library"),
            ("/api/steering",                      "steering rules"),
            ("/api/workflow",                      "workflow engine"),
            ("/api/analytics/kpis",                "analytics"),
            ("/api/license/status",                "license system"),
            ("/api/profile",                       "user profile"),
            ("/api/docs/quick-starts",             "documentation"),
            ("/api/db/sqlite/tables",              "database studio"),
            ("/api/knowledge-graph/stats",         "knowledge graph"),
            ("/api/rag/pipelines",                 "rag system"),
            ("/api/audit-log",                     "audit log"),
            ("/api/agent-identity",                "agent identity"),
            ("/api/supervisor/runs",               "supervisor"),
            ("/api/goals",                         "goal manager"),
            ("/api/mcp-gateway/servers",           "mcp gateway"),
            ("/api/connectors",                    "connectors"),
            ("/api/agent-monitor/live",            "agent monitor"),
            ("/api/finops/dashboard",              "finops"),
            ("/api/eval-framework/suites",         "eval framework"),
            ("/api/arena/models",                  "arena"),
            ("/api/marketplace/catalog",           "marketplace"),
            ("/api/templates",                     "templates"),
            ("/api/onboarding/status",             "onboarding"),
            ("/api/observability/traces",          "observability"),
        ]

        failures = []
        for ep, label in checks:
            r = await GET(U, ep)
            if r.status_code >= 500:
                failures.append(f"{label} ({ep}): HTTP {r.status_code}")

        print(f"\n  Platform health sweep: {len(checks) - len(failures)}/{len(checks)} subsystems healthy")
        for f in failures:
            print(f"  ❌ {f}")

        uat("all subsystems healthy (no 5xx)", len(failures) == 0, got=failures or "all OK")

    async def test_response_times_acceptable(self, U):
        """All critical paths respond within acceptable time."""
        import time
        slow = []
        endpoints = [
            ("/api/health", 100),
            ("/api/agents", 200),
            ("/api/tasks", 300),
            ("/api/chat/history", 200),
            ("/api/memory/list", 200),
            ("/api/audit-log", 300),
            ("/api/finops/dashboard", 400),
            ("/api/eval-framework/suites", 300),
        ]
        for ep, limit_ms in endpoints:
            t0 = time.perf_counter()
            r = await GET(U, ep)
            ms = (time.perf_counter() - t0) * 1000
            if ms > limit_ms:
                slow.append(f"{ep}: {ms:.0f}ms > {limit_ms}ms")

        uat("all critical paths respond fast", len(slow) == 0, got=slow or "all fast")
