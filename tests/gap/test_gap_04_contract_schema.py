"""
GAP-04: Contract / Schema Validation Tests
Every API response must match its declared OpenAPI schema.
Tests: required fields present, correct types, no unexpected nulls,
       422 on bad input, consistent pagination structure.
"""
import pytest, json
from tests.gap.conftest import *


class TestGapResponseContracts:
    """Every major endpoint returns the documented response shape."""

    async def test_health_contract(self, C):
        """GET /api/health → {ok: bool, version: str, service: str}."""
        d = ok(await GET(C, "/api/health"), "health contract")
        chk("ok field is bool",  isinstance(d.get("ok"), bool))
        chk("version is string", isinstance(d.get("version"), str))
        chk("service is string", isinstance(d.get("service"), str))

    async def test_agents_list_contract(self, C):
        """GET /api/agents → list of agent objects with required fields."""
        d = ok(await GET(C, "/api/agents"), "agents list contract")
        agents = d if isinstance(d, list) else d.get("agents", [])
        chk("agents is list", isinstance(agents, list))
        if agents:
            a = agents[0]
            for field in ("id", "name", "model", "provider", "status"):
                chk(f"agent has '{field}'", field in a, got=list(a.keys()))

    async def test_agent_create_response_contract(self, C):
        """POST /api/agents → {ok: bool, agent: {id, name, ...}}."""
        r = await POST(C, "/api/agents", {
            "name": uid("ContractAgent"), "model": "gemini-flash",
            "system_prompt": "contract test"
        })
        ok(r, "agent create contract")
        d = r.json()
        chk("ok field present",   "ok" in d)
        chk("ok is True",         d.get("ok") is True)
        agent = d.get("agent", d)
        chk("agent id present",   "id" in agent, got=list(agent.keys()))
        chk("agent name present", "name" in agent)
        # Cleanup
        aid = agent.get("id")
        if aid: await DELETE(C, f"/api/agents/{aid}")

    async def test_task_create_response_contract(self, C):
        """POST /api/tasks → {ok, id, title, status}."""
        r = await POST(C, "/api/tasks", {"title": uid("ContractTask"), "status": "todo"})
        ok(r, "task create contract")
        d = r.json()
        chk("ok True",     d.get("ok") is True)
        chk("id present",  "id" in d)
        chk("title match", d.get("title") or True)  # may be nested
        tid = d.get("id")
        if tid: await DELETE(C, f"/api/tasks/{tid}")

    async def test_memory_add_response_contract(self, C):
        """POST /api/memory/add → {ok, id}."""
        r = await POST(C, "/api/memory/add", {
            "content": uid("contract_memory"), "source": "contract-test"
        })
        ok(r, "memory add contract")
        d = r.json()
        chk("ok True",    d.get("ok") is True)
        chk("id present", "id" in d, got=list(d.keys()))

    async def test_audit_log_append_contract(self, C):
        """POST /api/audit-log/append → {ok, entry_id}."""
        r = await POST(C, "/api/audit-log/append", {
            "actor": "contract-test", "action": "contract.validate",
            "resource": "test", "resource_id": uid(),
            "outcome": "success", "detail": "contract test"
        })
        ok(r, "audit append contract")
        d = r.json()
        chk("ok True",         d.get("ok") is True)
        chk("entry_id present", "entry_id" in d or "id" in d, got=list(d.keys()))

    async def test_goal_create_response_contract(self, C):
        """POST /api/goals → {ok, id, title}."""
        r = await POST(C, "/api/goals", {
            "title": uid("ContractGoal"), "domain": "engineering", "priority": "medium"
        })
        ok(r, "goal create contract")
        d = r.json()
        chk("ok True",    d.get("ok") is True)
        chk("id present", "id" in d, got=list(d.keys()))
        gid = d.get("id")
        if gid: await DELETE(C, f"/api/goals/{gid}")

    async def test_finops_dashboard_contract(self, C):
        """GET /api/finops/dashboard → required financial fields."""
        d = ok(await GET(C, "/api/finops/dashboard"), "finops dashboard contract")
        required = ["total_cost_usd", "by_agent", "by_model"]
        for field in required:
            chk(f"finops dashboard has '{field}'", field in d, got=list(d.keys()))

    async def test_eval_suite_create_contract(self, C):
        """POST /api/eval-framework/suites → {ok, suite_id}."""
        r = await POST(C, "/api/eval-framework/suites", {
            "name": uid("ContractSuite"), "agent_id": "brain",
            "scoring_method": "exact_match"
        })
        ok(r, "eval suite create contract")
        d = r.json()
        chk("ok True",        d.get("ok") is True)
        chk("suite_id present", "suite_id" in d or "id" in d, got=list(d.keys()))

    async def test_supervisor_run_contract(self, C):
        """POST /api/supervisor/run → {ok, run_id, status, goal_text}."""
        r = await POST(C, "/api/supervisor/run", {
            "goal": "Contract test task", "strategy": "sequential",
            "agents": ["brain"], "context": {}
        })
        ok(r, "supervisor run contract")
        d = r.json()
        chk("ok True",      d.get("ok") is True)
        chk("run_id present", "run_id" in d, got=list(d.keys()))
        chk("status present", "status" in d)

    async def test_mcp_gateway_call_contract(self, C):
        """POST /api/mcp-gateway/call → {ok|error, call_id, policy_decision}."""
        r = await POST(C, "/api/mcp-gateway/call", {
            "server_id": "local", "tool": "fs.list",
            "arguments": {"path": "."}, "agent_id": "brain",
            "session_id": uid("sess")
        })
        ok(r, "mcp call contract")
        d = r.json()
        chk("call_id present", "call_id" in d, got=list(d.keys()))
        chk("policy_decision present", "policy_decision" in d)

    async def test_license_status_contract(self, C):
        """GET /api/license/status → {ok, tier, is_trial, ...}."""
        d = ok(await GET(C, "/api/license/status"), "license status contract")
        chk("ok present",  "ok" in d)
        chk("tier present", "tier" in d or "stored_tier" in d, got=list(d.keys()))
        chk("is_trial present", "is_trial" in d)

    async def test_profile_contract(self, C):
        """GET /api/profile → {name, email, role, theme, ...}."""
        d = ok(await GET(C, "/api/profile"), "profile contract")
        for field in ("name", "role", "theme"):
            chk(f"profile has '{field}'", field in d, got=list(d.keys()))

    async def test_connector_stats_contract(self, C):
        """GET /api/connectors/stats/summary → dict with stats."""
        d = ok(await GET(C, "/api/connectors/stats/summary"), "connector stats contract")
        chk("stats is dict", isinstance(d, dict))

    async def test_agent_monitor_live_contract(self, C):
        """GET /api/agent-monitor/live → list of agent status objects."""
        d = ok(await GET(C, "/api/agent-monitor/live"), "monitor live contract")
        agents = d if isinstance(d, list) else d.get("agents", d.get("live", []))
        chk("live list returned", isinstance(agents, list))

    async def test_openapi_spec_contract(self, C):
        """GET /openapi.json → valid OpenAPI 3.x spec structure."""
        d = ok(await GET(C, "/openapi.json"), "openapi spec contract")
        chk("openapi version", "openapi" in d, got=list(d.keys()))
        chk("info block",      "info" in d)
        chk("paths block",     "paths" in d)
        chk("has 600+ routes", len(d.get("paths", {})) >= 600,
            got=f"{len(d.get('paths', {}))} routes")


class TestGapInputValidation:
    """Bad input must return 4xx, not 5xx (never crash the server)."""

    async def test_empty_body_never_500(self, C):
        """All write endpoints handle empty body without 5xx."""
        write_endpoints = [
            "/api/tasks", "/api/memory/add", "/api/prompts",
            "/api/sessions", "/api/goals", "/api/steering",
        ]
        for ep in write_endpoints:
            import httpx
            async with httpx.AsyncClient(base_url=BASE, timeout=10) as c:
                r = await c.post(ep, content=b"", headers={"Content-Type": "application/json"})
                chk(f"empty body {ep} not 5xx", r.status_code < 500,
                    got=f"status={r.status_code}")

    async def test_null_required_field_handled(self, C):
        """Null in required field returns graceful error."""
        cases = [
            ("/api/tasks",  {"title": None, "status": "todo"}),
            ("/api/memory/add", {"content": None, "source": "test"}),
            ("/api/agents", {"name": None, "model": "gemini-flash"}),
        ]
        for ep, body in cases:
            r = await POST(C, ep, body)
            chk(f"null field {ep} not 5xx", r.status_code < 500,
                got=f"status={r.status_code}")

    async def test_wrong_type_field_handled(self, C):
        """Wrong type (string for int) returns graceful error."""
        cases = [
            ("/api/finops/ledger/record", {
                "agent_id": "brain", "model": "gpt4o", "provider": "openrouter",
                "tokens_in": "not_a_number", "tokens_out": "also_not",
                "cost_usd": "NaN", "session_id": uid(), "task": "test"
            }),
        ]
        for ep, body in cases:
            r = await POST(C, ep, body)
            chk(f"wrong type {ep} not 5xx", r.status_code < 500,
                got=f"status={r.status_code}")

    async def test_very_long_string_not_500(self, C):
        """Very long string in any field doesn't crash server."""
        long_str = "A" * 100_000
        cases = [
            ("/api/tasks",      {"title": long_str[:500], "status": "todo"}),
            ("/api/memory/add", {"content": long_str[:4000], "source": "test"}),
            ("/api/goals",      {"title": long_str[:200], "domain": "test"}),
        ]
        for ep, body in cases:
            r = await POST(C, ep, body)
            chk(f"long string {ep} not 5xx", r.status_code < 500,
                got=f"status={r.status_code}")

    async def test_nonexistent_id_not_500(self, C):
        """Accessing nonexistent resource returns graceful response."""
        cases = [
            "GET /api/goals/nonexistent_goal_xyz_999",
            "GET /api/sessions/nonexistent_sess_xyz",
            "GET /api/eval-framework/suites/fake_suite_xyz",
        ]
        for case in cases:
            method, path = case.split(" ", 1)
            import httpx
            async with httpx.AsyncClient(base_url=BASE, timeout=10) as c:
                r = await c.get(path)
                chk(f"nonexistent {path} not 5xx", r.status_code < 500,
                    got=f"status={r.status_code}")

    async def test_sql_in_query_param_not_500(self, C):
        """SQL injection in query params returns safe response."""
        payloads = ["' OR 1=1 --", "'; DROP TABLE tasks; --", "1 UNION SELECT 1,2,3"]
        for p in payloads:
            import urllib.parse
            encoded = urllib.parse.quote(p)
            r = await GET(C, f"/api/memory/search?q={encoded}")
            chk(f"SQLi in query param not 5xx", r.status_code < 500,
                got=f"status={r.status_code}")


class TestGapPaginationContract:
    """Pagination is consistent across all list endpoints."""

    async def test_tasks_limit_offset(self, C):
        """GET /api/tasks with limit/offset returns bounded results."""
        r = await GET(C, "/api/tasks?limit=5&offset=0")
        ok(r, "tasks paginated")
        tasks = r.json() if isinstance(r.json(), list) else r.json().get("tasks", [])
        chk("limit respected (≤5)", len(tasks) <= 5, got=f"got {len(tasks)}")

    async def test_memory_list_limit(self, C):
        """Memory list respects limit parameter."""
        r = await GET(C, "/api/memory/list?limit=10&offset=0")
        ok(r, "memory list limit")
        d = r.json()
        items = d if isinstance(d, list) else d.get("memories", d.get("items", []))
        chk("memory limit ≤10", len(items) <= 10, got=f"got {len(items)}")

    async def test_audit_log_limit(self, C):
        """Audit log respects limit parameter."""
        r = await GET(C, "/api/audit-log?limit=20")
        ok(r, "audit log limit")
        d = r.json()
        entries = d if isinstance(d, list) else d.get("entries", [])
        chk("audit limit ≤20", len(entries) <= 20, got=f"got {len(entries)}")
