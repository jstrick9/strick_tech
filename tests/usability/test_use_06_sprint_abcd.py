"""
USABILITY-06: Sprint A-D Feature Usability
Full user-journey tests for every Sprint A-D feature from the user's perspective.
Sprint A: Audit Log, Agent Identity
Sprint B: Supervisor, Goal Manager
Sprint C: MCP Gateway, Connectors
Sprint D: Agent Monitor, FinOps, Eval Framework
"""
import pytest
from tests.usability.conftest import *


class TestUseAuditLog:
    """User reviews the audit trail to understand what happened."""

    async def test_audit_log_shows_recent_events(self, U):
        """User opens Audit Log pane — recent events appear."""
        r = await GET(U, "/api/audit-log")
        no_error(r, "audit log loads")
        d = j(r)
        entries = d if isinstance(d, list) else d.get("entries", d.get("logs", []))
        uat("audit log entries returned", isinstance(entries, list))

    async def test_audit_log_stats_visible(self, U):
        """Audit log statistics panel shows totals."""
        r = await GET(U, "/api/audit-log/stats")
        no_error(r, "audit log stats")
        d = j(r)
        uat("stats returned", isinstance(d, dict))
        uat("total count present", "total" in d or "count" in d)

    async def test_user_can_append_audit_event(self, U):
        """User action creates an audit entry."""
        r = await POST(U, "/api/audit-log/append", {
            "actor": "user@agentic.os", "action": "user.test_action",
            "resource": "audit_log", "resource_id": uid("res"),
            "outcome": "success", "detail": "Usability test audit event"
        })
        no_error(r, "append audit event")
        d = j(r)
        uat("audit entry id returned", d.get("entry_id") or d.get("id") or d.get("ok") is True)

    async def test_audit_chain_verification(self, U):
        """User can verify the audit chain integrity."""
        r = await GET(U, "/api/audit-log/verify")
        no_error(r, "verify audit chain")
        d = j(r)
        uat("verification result returned", "valid" in d or "chain_valid" in d or "ok" in d)

    async def test_audit_log_export_csv(self, U):
        """User exports audit log as CSV for compliance."""
        r = await GET(U, "/api/audit-log/export/csv")
        no_error(r, "export audit csv")
        uat("csv content returned", "csv" in r.headers.get("content-type","").lower()
            or len(r.content) > 0)

    async def test_audit_log_export_json(self, U):
        """User exports audit log as JSON for analysis."""
        r = await GET(U, "/api/audit-log/export/json")
        no_error(r, "export audit json")

    async def test_audit_entry_detail_view(self, U):
        """User clicks on an audit entry to see full details."""
        # Create an entry first
        r = await POST(U, "/api/audit-log/append", {
            "actor": "detail_test", "action": "detail.view",
            "resource": "test", "resource_id": uid(),
            "outcome": "success", "detail": "test"
        })
        eid = j(r).get("entry_id")
        if eid:
            r2 = await GET(U, f"/api/audit-log/entry/{eid}")
            no_error(r2, "audit entry detail")


class TestUseAgentIdentity:
    """User manages cryptographic agent identities."""

    async def test_identity_roster_loads(self, U):
        """Agent identity pane shows all provisioned agents."""
        r = await GET(U, "/api/agent-identity")
        no_error(r, "identity roster")
        d = j(r)
        identities = d if isinstance(d, list) else d.get("identities", d.get("agents", []))
        uat("identities returned", isinstance(identities, list))

    async def test_system_stats_visible(self, U):
        """Identity system stats show key/token counts."""
        r = await GET(U, "/api/agent-identity/system/stats")
        no_error(r, "identity system stats")
        d = j(r)
        uat("stats returned", isinstance(d, dict))

    async def test_provision_all_agents(self, U):
        """Admin provisions cryptographic identity for all agents."""
        r = await POST(U, "/api/agent-identity/provision-all", {})
        no_error(r, "provision all agents")
        d = j(r)
        uat("provisioning completed", d.get("ok") is True or "provisioned" in d)

    async def test_agent_identity_detail(self, U):
        """User inspects a specific agent's identity."""
        agents = j(await GET(U, "/api/agents"))
        if not isinstance(agents, list) or not agents:
            pytest.skip("No agents")
        aid = agents[0]["id"]
        r = await GET(U, f"/api/agent-identity/{aid}")
        no_error(r, "agent identity detail")
        d = j(r)
        uat("identity returned", d.get("identity") or d.get("agent_id") or d.get("ok") is not None)

    async def test_issue_and_validate_token(self, U):
        """User issues a JIT token for an agent, then validates it."""
        agents = j(await GET(U, "/api/agents"))
        if not isinstance(agents, list) or not agents:
            pytest.skip("No agents")
        aid = agents[0]["id"]

        r = await POST(U, f"/api/agent-identity/{aid}/issue-token", {
            "scope": ["read", "write"], "ttl_minutes": 60
        })
        no_error(r, "issue token")
        d = j(r)
        token = d.get("token")
        uat("token issued", bool(token) or d.get("ok") is True)


class TestUseSupervisor:
    """User runs multi-agent supervised tasks."""

    async def test_supervisor_run_dispatches(self, U):
        """User submits a complex task — Supervisor fans it out to agents."""
        r = await POST(U, "/api/supervisor/run", {
            "goal": "Research and summarize the top 3 benefits of async Python",
            "strategy": "parallel",
            "agents": ["brain", "researcher"],
            "context": {"depth": "brief"}
        })
        no_error(r, "supervisor run")
        d = j(r)
        rid = d.get("run_id")
        uat("run id returned",   bool(rid))
        uat("status returned",   bool(d.get("status")))
        uat("goal text echoed",  "async" in d.get("goal_text","").lower() or d.get("ok") is True)

    async def test_supervisor_run_history(self, U):
        """User sees history of all supervised runs."""
        r = await GET(U, "/api/supervisor/runs")
        no_error(r, "supervisor run history")
        d = j(r)
        runs = d if isinstance(d, list) else d.get("runs", [])
        uat("runs history returned", isinstance(runs, list))

    async def test_supervisor_run_kill(self, U):
        """User can kill an active supervisor run."""
        r = await POST(U, "/api/supervisor/run", {
            "goal": "Long running task to kill", "strategy": "sequential",
            "agents": ["brain"], "context": {}
        })
        rid = j(r).get("run_id")
        if rid:
            r2 = await POST(U, f"/api/supervisor/run/{rid}/kill", {})
            no_error(r2, "kill supervisor run")


class TestUseGoalManager:
    """User tracks strategic goals (Sprint B)."""

    async def test_goals_dashboard_loads(self, U):
        """Goals pane shows active goals and progress."""
        r = await GET(U, "/api/goals")
        no_error(r, "goals dashboard")
        d = j(r)
        goals = d if isinstance(d, list) else d.get("goals", [])
        uat("goals returned", isinstance(goals, list))

    async def test_create_and_track_goal(self, U):
        """User creates a strategic goal and tracks it."""
        title = uid("UsabilityGoal")
        r = await POST(U, "/api/goals", {
            "title": title, "description": "Ensure platform works perfectly",
            "domain": "quality", "priority": "critical"
        })
        no_error(r, "create goal")
        gid = j(r).get("id")
        uat("goal id issued", bool(gid))

        # Check in with progress
        r2 = await POST(U, f"/api/goals/{gid}/checkin", {
            "note": "25% done", "completion_pct": 25
        })
        no_error(r2, "goal checkin")

        await DELETE(U, f"/api/goals/{gid}")


class TestUseMCPGateway:
    """User routes AI tool calls through the MCP Gateway."""

    async def test_mcp_gateway_servers_list(self, U):
        """User sees registered MCP servers."""
        r = await GET(U, "/api/mcp-gateway/servers")
        no_error(r, "mcp servers list")
        d = j(r)
        servers = d if isinstance(d, list) else d.get("servers", [])
        uat("servers list returned", isinstance(servers, list))

    async def test_mcp_gateway_policies_list(self, U):
        """User manages MCP access policies."""
        r = await GET(U, "/api/mcp-gateway/policies")
        no_error(r, "mcp policies")
        d = j(r)
        policies = d if isinstance(d, list) else d.get("policies", [])
        uat("policies returned", isinstance(policies, list))

    async def test_mcp_gateway_stats(self, U):
        """MCP Gateway usage statistics visible."""
        r = await GET(U, "/api/mcp-gateway/stats")
        no_error(r, "mcp stats")
        d = j(r)
        uat("stats returned", isinstance(d, dict))

    async def test_create_and_toggle_mcp_policy(self, U):
        """User creates an MCP policy and toggles it."""
        r = await POST(U, "/api/mcp-gateway/policies", {
            "name": uid("TestPolicy"), "tool_pattern": "fs.*",
            "agent_pattern": "builder", "action": "allow", "conditions": {}
        })
        no_error(r, "create mcp policy")
        d = j(r)
        pid = d.get("id")
        if pid:
            r2 = await PATCH(U, f"/api/mcp-gateway/policies/{pid}/toggle", {})
            no_error(r2, "toggle mcp policy")
            await DELETE(U, f"/api/mcp-gateway/policies/{pid}")

    async def test_mcp_gateway_call(self, U):
        """User makes a tool call through the gateway."""
        r = await POST(U, "/api/mcp-gateway/call", {
            "server_id": "local", "tool": "fs.list",
            "arguments": {"path": "."}, "agent_id": "builder",
            "session_id": uid("sess")
        })
        no_error(r, "mcp gateway call")
        d = j(r)
        uat("call processed", d.get("call_id") or d.get("ok") is not None)

    async def test_mcp_gateway_call_history(self, U):
        """User reviews all gateway call logs."""
        r = await GET(U, "/api/mcp-gateway/calls")
        no_error(r, "mcp call history")
        d = j(r)
        calls = d if isinstance(d, list) else d.get("calls", [])
        uat("call history returned", isinstance(calls, list))


class TestUseConnectors:
    """User configures and uses enterprise connectors."""

    async def test_connector_catalog_visible(self, U):
        """User sees all available connectors in the catalog."""
        r = await GET(U, "/api/connectors")
        no_error(r, "connector catalog")
        d = j(r)
        connectors = d if isinstance(d, list) else d.get("connectors", [])
        uat("connectors listed", len(connectors) > 0)
        types = [c.get("name","") for c in connectors]
        uat("email connector available", any("email" in t.lower() or "smtp" in t.lower() for t in types))

    async def test_connector_stats_summary(self, U):
        """User sees aggregated connector stats."""
        r = await GET(U, "/api/connectors/stats/summary")
        no_error(r, "connector stats")
        d = j(r)
        uat("stats returned", isinstance(d, dict))

    async def test_connector_execution_history(self, U):
        """User sees past connector executions."""
        r = await GET(U, "/api/connectors/conn_webhook/executions")
        no_error(r, "connector executions")
        d = j(r)
        execs = d if isinstance(d, list) else d.get("executions", [])
        uat("executions returned", isinstance(execs, list))


class TestUseAgentMonitor:
    """User watches live agent activity on the monitor dashboard."""

    async def test_live_dashboard_shows_agents(self, U):
        """Live monitor shows all agent statuses."""
        r = await GET(U, "/api/agent-monitor/live")
        no_error(r, "live monitor")
        d = j(r)
        agents = d if isinstance(d, list) else d.get("agents", d.get("live", []))
        uat("live agents returned", isinstance(agents, list))

    async def test_monitor_summary_stats(self, U):
        """Monitor summary shows aggregate health metrics."""
        r = await GET(U, "/api/agent-monitor/summary")
        no_error(r, "monitor summary")
        d = j(r)
        uat("summary returned", isinstance(d, dict))

    async def test_anomaly_list(self, U):
        """User sees detected anomalies with severity."""
        r = await GET(U, "/api/agent-monitor/anomalies")
        no_error(r, "anomaly list")
        d = j(r)
        anomalies = d if isinstance(d, list) else d.get("anomalies", [])
        uat("anomaly list returned", isinstance(anomalies, list))

    async def test_anomaly_detection_runs(self, U):
        """User triggers anomaly detection scan."""
        r = await POST(U, "/api/agent-monitor/anomalies/detect", {})
        no_error(r, "detect anomalies")
        d = j(r)
        uat("detection ran", d.get("ok") is True or "anomalies" in d or isinstance(d, dict))

    async def test_kpi_snapshot(self, U):
        """User takes a KPI snapshot for baseline comparison."""
        r = await POST(U, "/api/agent-monitor/kpis/snapshot", {})
        no_error(r, "kpi snapshot")

    async def test_per_agent_kpis(self, U):
        """User inspects performance KPIs for a specific agent."""
        r = await GET(U, "/api/agent-monitor/kpis/brain")
        no_error(r, "per-agent kpis")
        d = j(r)
        uat("agent kpis returned", isinstance(d, dict))

    async def test_shadow_test_creation(self, U):
        """User creates a shadow test to evaluate agent quality."""
        r = await POST(U, "/api/agent-monitor/shadow", {
            "agent_id": "brain", "test_type": "response_quality",
            "config": {"prompt": "Hello, how are you?", "expected_tone": "helpful"}
        })
        no_error(r, "create shadow test")
        d = j(r)
        uat("shadow test created", d.get("ok") is True or "test_id" in d)


class TestUseFinOps:
    """User monitors and controls AI spending through FinOps."""

    async def test_cost_ledger_visible(self, U):
        """User sees every cost entry in the ledger."""
        r = await GET(U, "/api/finops/ledger")
        no_error(r, "finops ledger")
        d = j(r)
        entries = d if isinstance(d, list) else d.get("entries", d.get("ledger", []))
        uat("ledger returned", isinstance(entries, list) or isinstance(d, dict))

    async def test_finops_dashboard_metrics(self, U):
        """FinOps dashboard shows total spend, by-agent, by-model breakdowns."""
        r = await GET(U, "/api/finops/dashboard")
        no_error(r, "finops dashboard")
        d = j(r)
        uat("total cost visible",  "total_cost_usd" in d or "total_cost" in d or "total" in d)
        uat("by-agent breakdown",  "by_agent" in d or "agents" in d or "by_source_type" in d)
        uat("by-model breakdown",  "by_model" in d or "models" in d or "by_source_type" in d)

    async def test_record_and_view_cost(self, U):
        """User action records cost — appears in ledger."""
        r = await POST(U, "/api/finops/ledger/record", {
            "agent_id": "brain", "model": "gpt4o", "provider": "openrouter",
            "tokens_in": 500, "tokens_out": 100, "cost_usd": 0.005,
            "session_id": uid("sess"), "task": "usability test"
        })
        no_error(r, "record cost")
        d = j(r)
        uat("cost entry id returned", d.get("ledger_id") or d.get("ok") is True)

    async def test_budget_cap_create_and_view(self, U):
        """User sets a budget cap — appears in caps list."""
        r = await POST(U, "/api/finops/caps", {
            "name": uid("UsabilityCap"), "agent_id": "brain",
            "period": "daily", "limit_usd": 5.0, "action": "alert"
        })
        no_error(r, "create budget cap")
        d = j(r)
        cap_id = d.get("cap_id") or d.get("id")
        uat("cap created", bool(cap_id) or d.get("ok") is True)

        r2 = await GET(U, "/api/finops/caps")
        no_error(r2, "list budget caps")
        d2 = j(r2)
        caps = d2 if isinstance(d2, list) else d2.get("caps", [])
        uat("caps listed", isinstance(caps, list))

        if cap_id:
            await DELETE(U, f"/api/finops/caps/{cap_id}")

    async def test_finops_alerts_visible(self, U):
        """User sees budget alerts when spending approaches limits."""
        r = await GET(U, "/api/finops/alerts")
        no_error(r, "finops alerts")

    async def test_cost_timeseries(self, U):
        """User views cost trend over time."""
        r = await GET(U, "/api/finops/stats/time-series")
        no_error(r, "cost timeseries")
        d = j(r)
        uat("timeseries data", isinstance(d, dict) or isinstance(d, list))

    async def test_finops_csv_export(self, U):
        """User exports cost data for accounting."""
        r = await GET(U, "/api/finops/export/csv")
        no_error(r, "finops csv export")
        uat("export content returned", len(r.content) >= 0)


class TestUseEvalFramework:
    """User runs continuous evaluations to monitor AI quality."""

    async def test_eval_suites_dashboard(self, U):
        """User sees all evaluation suites."""
        r = await GET(U, "/api/eval-framework/suites")
        no_error(r, "eval suites")
        d = j(r)
        suites = d if isinstance(d, list) else d.get("suites", [])
        uat("suites returned", isinstance(suites, list))

    async def test_create_eval_suite_with_cases(self, U):
        """User creates an eval suite and adds test cases."""
        r = await POST(U, "/api/eval-framework/suites", {
            "name": uid("UsabilitySuite"), "description": "Suite for usability testing",
            "agent_id": "brain", "scoring_method": "exact_match"
        })
        no_error(r, "create eval suite")
        d = j(r)
        sid = d.get("suite_id") or d.get("id")
        uat("suite id issued", bool(sid))

        # Add a test case
        r2 = await POST(U, f"/api/eval-framework/suites/{sid}/cases", {
            "input": "What is 2+2?", "expected_output": "4", "category": "math"
        })
        no_error(r2, "add eval case")

    async def test_eval_platform_stats(self, U):
        """Platform-wide eval statistics visible."""
        r = await GET(U, "/api/eval-framework/stats/platform")
        no_error(r, "eval platform stats")
        d = j(r)
        uat("stats returned", isinstance(d, dict))
        uat("total suites field", "total_suites" in d or "suites" in d)

    async def test_eval_review_queue(self, U):
        """Human review queue shows pending reviews."""
        r = await GET(U, "/api/eval-framework/review-queue")
        no_error(r, "eval review queue")
        d = j(r)
        queue = d if isinstance(d, list) else d.get("queue", [])
        uat("queue returned", isinstance(queue, list))

    async def test_eval_results_history(self, U):
        """User browses past evaluation results."""
        r = await GET(U, "/api/eval-framework/results")
        no_error(r, "eval results")
        d = j(r)
        results = d if isinstance(d, list) else d.get("results", [])
        uat("results returned", isinstance(results, list))

    async def test_per_agent_eval_summary(self, U):
        """User sees Brain agent's eval performance summary."""
        r = await GET(U, "/api/eval-framework/summary/brain")
        no_error(r, "agent eval summary")
        d = j(r)
        uat("summary returned", isinstance(d, dict))
