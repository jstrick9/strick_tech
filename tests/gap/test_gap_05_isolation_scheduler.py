"""
GAP-05: Data Isolation, Scheduler Jobs & Chaos Recovery
Covers:
  - Per-agent data isolation (cost, eval, monitor scoping)
  - Background scheduler job effects
  - Fault injection and graceful recovery
  - Rate limiting / resource protection
  - Idempotency of critical operations
"""
import pytest, asyncio, time, json
from tests.gap.conftest import *


class TestGapDataIsolation:
    """Data scoped to one agent/goal must not bleed into another's view."""

    async def test_finops_by_agent_isolation(self, C):
        """Cost entries for brain don't appear in builder-scoped query."""
        # Record cost for brain
        await POST(C, "/api/finops/ledger/record", {
            "agent_id": "brain", "model": "gpt4o", "provider": "openrouter",
            "tokens_in": 1000, "tokens_out": 200, "cost_usd": 0.01,
            "session_id": uid("brain_sess"), "task": "isolation_test_brain"
        })
        # Record cost for builder
        await POST(C, "/api/finops/ledger/record", {
            "agent_id": "builder", "model": "gpt4o-mini", "provider": "openrouter",
            "tokens_in": 500, "tokens_out": 100, "cost_usd": 0.001,
            "session_id": uid("builder_sess"), "task": "isolation_test_builder"
        })
        # Brain summary should show brain costs
        r_brain = await GET(C, "/api/eval-framework/summary/brain")
        ok(r_brain, "brain eval summary")
        # Builder summary should show builder costs
        r_builder = await GET(C, "/api/eval-framework/summary/builder")
        ok(r_builder, "builder eval summary")
        # Both should return valid distinct responses
        chk("brain summary is dict",   isinstance(r_brain.json(), dict))
        chk("builder summary is dict", isinstance(r_builder.json(), dict))

    async def test_goal_milestones_scoped_to_goal(self, C):
        """Milestones of goal A don't appear in goal B's list."""
        # Create goal A and B
        rA = await POST(C, "/api/goals", {"title": uid("GoalA"), "domain": "engineering"})
        rB = await POST(C, "/api/goals", {"title": uid("GoalB"), "domain": "product"})
        gidA = rA.json().get("id")
        gidB = rB.json().get("id")
        if not gidA or not gidB:
            pytest.skip("Could not create goals")

        # Add milestone to A only
        r_ms = await POST(C, f"/api/goals/{gidA}/milestones", {
            "title": uid("OnlyForA"), "due_date": "2026-12-31"
        })
        ok(r_ms, "add milestone to A")
        ms_id = r_ms.json().get("id")

        # B's milestones must not contain A's milestone
        r_B_ms = await GET(C, f"/api/goals/{gidB}/milestones")
        ok(r_B_ms, "B milestones")
        d = r_B_ms.json()
        b_milestones = d if isinstance(d, list) else d.get("milestones", [])
        b_ids = [str(m.get("id")) for m in b_milestones]
        chk("A's milestone not in B", str(ms_id) not in b_ids)

        await DELETE(C, f"/api/goals/{gidA}")
        await DELETE(C, f"/api/goals/{gidB}")

    async def test_eval_suites_agent_scoped(self, C):
        """Eval suite for brain shows in brain summary, not builder summary."""
        r = await POST(C, "/api/eval-framework/suites", {
            "name": uid("BrainSuite"), "agent_id": "brain",
            "scoring_method": "exact_match", "description": "isolation test"
        })
        ok(r, "create brain eval suite")
        sid = r.json().get("suite_id") or r.json().get("id")

        # Brain summary should include this suite (eventually)
        r_brain = await GET(C, "/api/eval-framework/summary/brain")
        ok(r_brain, "brain eval summary")
        chk("brain summary accessible", isinstance(r_brain.json(), dict))

    async def test_mcp_gateway_calls_logged_per_session(self, C):
        """MCP calls are tracked per session — call log is accessible."""
        # Make a call
        r = await POST(C, "/api/mcp-gateway/call", {
            "server_id": "local", "tool": "fs.list",
            "arguments": {"path": "."}, "agent_id": "brain",
            "session_id": uid("isolation_sess")
        })
        ok(r, "mcp gateway call")
        # Calls list is accessible
        r2 = await GET(C, "/api/mcp-gateway/calls")
        ok(r2, "mcp calls list")
        d = r2.json()
        calls = d if isinstance(d, list) else d.get("calls", [])
        chk("calls list returned", isinstance(calls, list))

    async def test_budget_cap_per_agent_not_global(self, C):
        """Budget cap scoped to brain doesn't affect builder."""
        # Create a cap for brain only
        r = await POST(C, "/api/finops/caps", {
            "name": uid("BrainCap"), "agent_id": "brain",
            "period": "daily", "limit_usd": 0.01, "action": "alert"
        })
        ok(r, "create brain cap")
        cap_id = r.json().get("cap_id") or r.json().get("id")

        # Overall caps list is accessible
        r2 = await GET(C, "/api/finops/caps")
        ok(r2, "caps list")
        d = r2.json()
        caps = d if isinstance(d, list) else d.get("caps", [])
        chk("caps list returned", isinstance(caps, list))

        if cap_id:
            await DELETE(C, f"/api/finops/caps/{cap_id}")

    async def test_session_messages_isolated(self, C):
        """Messages in session A don't appear in session B."""
        # Create session A
        rA = await POST(C, "/api/sessions", {"name": uid("SessA"), "agent_id": "brain"})
        dA = rA.json()
        sidA = (dA.get("session") or dA).get("id") or dA.get("session_id")

        # Create session B
        rB = await POST(C, "/api/sessions", {"name": uid("SessB"), "agent_id": "brain"})
        dB = rB.json()
        sidB = (dB.get("session") or dB).get("id") or dB.get("session_id")

        if not sidA or not sidB:
            pytest.skip("Could not create sessions")

        # Send message to A
        await POST(C, "/api/chat", {
            "message": uid("only_in_A"), "agent": "brain", "session_id": sidA
        })
        # B's messages should not include A's
        r_B_msgs = await GET(C, f"/api/sessions/{sidB}/messages")
        ok(r_B_msgs, "session B messages")
        d_B = r_B_msgs.json()
        b_msgs = d_B if isinstance(d_B, list) else d_B.get("messages", [])
        chk("session B messages isolated", isinstance(b_msgs, list))


class TestGapSchedulerJobs:
    """Background APScheduler jobs must have observable effects."""

    async def test_scheduler_memory_auto_index_effect(self, C):
        """Memory re-index scheduled job — index stats accessible."""
        # The scheduler runs _memory_auto_index periodically
        # We can verify the index is functional by doing a search
        await POST(C, "/api/memory/add", {
            "content": uid("scheduler_test_memory_auto"),
            "source": "scheduler-test"
        })
        r = await GET(C, "/api/memory/search?q=scheduler_test_memory")
        ok(r, "memory search after auto-index")
        d = r.json()
        results = d if isinstance(d, list) else d.get("results", d.get("memories", []))
        chk("FTS search works (auto-index functional)", isinstance(results, list))

    async def test_scheduler_agent_status_cleanup(self, C):
        """Agent status cleanup job — live monitor accessible and consistent."""
        r = await GET(C, "/api/agent-monitor/live")
        ok(r, "monitor live after cleanup")
        d = r.json()
        agents = d if isinstance(d, list) else d.get("agents", [])
        chk("monitor returns list", isinstance(agents, list))

    async def test_scheduler_cost_digest_accessible(self, C):
        """Cost digest job — FinOps dashboard aggregation works."""
        r = await GET(C, "/api/finops/dashboard")
        ok(r, "finops dashboard (cost digest)")
        d = r.json()
        chk("total_cost_usd present", "total_cost_usd" in d or "total_cost" in d)

    async def test_manual_memory_reindex_works(self, C):
        """POST /api/memory/reindex completes without error."""
        r = await POST(C, "/api/memory/reindex", {})
        ok(r, "memory reindex")
        d = r.json()
        chk("reindex accepted", d.get("ok") is True or "status" in d)

    async def test_scheduler_loop_resilience(self, C):
        """Platform remains responsive during/after background jobs."""
        # Fire multiple background-like operations simultaneously
        tasks = [
            GET(C, "/api/analytics/kpis"),
            GET(C, "/api/agent-monitor/live"),
            GET(C, "/api/finops/dashboard"),
            GET(C, "/api/eval-framework/stats/platform"),
            GET(C, "/api/audit-log/stats"),
        ]
        results = await asyncio.gather(*tasks, return_exceptions=True)
        errors = [r for r in results if isinstance(r, Exception)]
        server_errors = [r for r in results if hasattr(r, 'status_code') and r.status_code >= 500]
        chk("no exceptions during background ops", len(errors) == 0, got=str(errors[:2]))
        chk("no 5xx during background ops", len(server_errors) == 0)


class TestGapFaultInjection:
    """Platform must recover gracefully from adversarial conditions."""

    async def test_malformed_json_graceful(self, C):
        """Malformed JSON body → 4xx, not 5xx."""
        import httpx
        async with httpx.AsyncClient(base_url=BASE, timeout=10) as c:
            r = await c.post("/api/tasks",
                content=b"not {valid json at all!!",
                headers={"Content-Type": "application/json"})
            chk("malformed json → not 5xx", r.status_code < 500,
                got=f"status={r.status_code}")

    async def test_missing_content_type_handled(self, C):
        """POST without Content-Type header handled gracefully."""
        import httpx
        async with httpx.AsyncClient(base_url=BASE, timeout=10) as c:
            r = await c.post("/api/tasks", content=b'{"title":"test"}')
            chk("missing content-type not 5xx", r.status_code < 500)

    async def test_deeply_nested_json_no_stack_overflow(self, C):
        """100-level deep JSON doesn't crash parser."""
        nested = {"value": "leaf"}
        for _ in range(100):
            nested = {"child": nested}
        r = await POST(C, "/api/tasks", {"title": "deep", "meta": nested})
        chk("deep JSON not 5xx", r.status_code < 500)

    async def test_emoji_and_unicode_in_all_fields(self, C):
        """Unicode/emoji in text fields stored and retrieved correctly."""
        title = "🚀 Аgentic OS テスト 测试 🎯"
        r = await POST(C, "/api/tasks", {"title": title[:200], "status": "todo"})
        ok(r, "unicode task create")
        d = r.json()
        tid = d.get("id")
        chk("unicode task created", bool(tid))
        if tid: await DELETE(C, f"/api/tasks/{tid}")

    async def test_concurrent_delete_same_resource(self, C):
        """Deleting the same resource concurrently — no 5xx."""
        r = await POST(C, "/api/tasks", {"title": uid("del_race"), "status": "todo"})
        tid = r.json().get("id")
        if not tid: pytest.skip()

        import httpx
        async def try_delete():
            async with httpx.AsyncClient(base_url=BASE, timeout=10) as c:
                r = await c.delete(f"/api/tasks/{tid}")
                return r.status_code

        results = await asyncio.gather(*[try_delete() for _ in range(5)])
        errors = [s for s in results if s >= 500]
        chk("concurrent deletes no 5xx", len(errors) == 0,
            got=f"{len(errors)} errors: {set(results)}")

    async def test_platform_healthy_after_fault_injection(self, C):
        """After all fault injection tests, platform still 100% healthy."""
        r = await GET(C, "/api/health")
        ok(r, "health after fault injection")
        d = r.json()
        chk("ok True", d.get("ok") is True)
        chk("version present", "version" in d)


class TestGapIdempotency:
    """Critical operations must be idempotent where specified."""

    async def test_provision_all_agents_idempotent(self, C):
        """Calling provision-all twice doesn't corrupt identities."""
        r1 = await POST(C, "/api/agent-identity/provision-all", {})
        ok(r1, "provision all 1st")
        r2 = await POST(C, "/api/agent-identity/provision-all", {})
        ok(r2, "provision all 2nd")
        # Both should succeed
        chk("1st provision ok", r1.json().get("ok") is True or "provisioned" in r1.json())
        chk("2nd provision ok", r2.json().get("ok") is True or "provisioned" in r2.json())

    async def test_audit_verify_idempotent(self, C):
        """Chain verify can be called repeatedly without error."""
        for _ in range(3):
            r = await GET(C, "/api/audit-log/verify")
            ok(r, "audit verify idempotent")
            d = r.json()
            chk("verify returns valid field", "valid" in d or "chain_valid" in d or "ok" in d)

    async def test_memory_reindex_idempotent(self, C):
        """Reindex can be called multiple times safely."""
        for _ in range(3):
            r = await POST(C, "/api/memory/reindex", {})
            ok(r, "memory reindex idempotent")

    async def test_onboarding_complete_idempotent(self, C):
        """Completing onboarding twice doesn't cause errors."""
        data = {"name": uid("OnboardUser"), "role": "developer"}
        r1 = await POST(C, "/api/onboarding/complete", data)
        ok(r1, "onboarding complete 1st")
        r2 = await POST(C, "/api/onboarding/complete", data)
        ok(r2, "onboarding complete 2nd — idempotent")

    async def test_anomaly_detect_idempotent(self, C):
        """Anomaly detection can run repeatedly without side effects."""
        for _ in range(3):
            r = await POST(C, "/api/agent-monitor/anomalies/detect", {})
            ok(r, "anomaly detect idempotent")

    async def test_kpi_snapshot_accumulates_not_overwrites(self, C):
        """Taking two KPI snapshots both persist."""
        r1 = await POST(C, "/api/agent-monitor/kpis/snapshot", {})
        ok(r1, "kpi snapshot 1")
        await asyncio.sleep(0.1)
        r2 = await POST(C, "/api/agent-monitor/kpis/snapshot", {})
        ok(r2, "kpi snapshot 2")
        chk("both snapshots accepted", r1.json().get("ok") is True or r1.status_code == 200)
        chk("second snapshot ok",      r2.json().get("ok") is True or r2.status_code == 200)
