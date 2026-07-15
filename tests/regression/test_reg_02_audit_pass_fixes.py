"""
Regression Tests — Audit Pass 1, 2, 3 Bug Fixes
Guards all fixes applied during the three-pass audit of all 74 routers.

Pass 1 (Critical): ROOT paths, DB connections, inject_steering
Pass 2 (High): More DB connections, frontend XSS/r.ok/encodeURIComponent
Pass 3 (Medium): Remaining gaps, services
"""
import pytest
import httpx

BASE = "http://127.0.0.1:8787"


@pytest.fixture(scope="module")
def client():
    return httpx.Client(base_url=BASE, timeout=15)


class TestRegressionPass1_ROOT:
    """Pass 1 A-1: control_tower.py had ROOT=parents[3] instead of parents[2]."""

    def test_control_tower_runs_accessible(self, client):
        """Regression: /api/control/runs must be accessible (wrong ROOT broke file ops)."""
        r = client.get("/api/control/runs?limit=5")
        assert r.status_code == 200, \
            f"PASS1 REGRESSION: control/runs broken: {r.status_code}"
        assert isinstance(r.json(), list)

    def test_control_tower_stats_accessible(self, client):
        """Regression: /api/control/stats must work with correct ROOT."""
        r = client.get("/api/control/stats")
        assert r.status_code == 200
        d = r.json()
        assert "total_runs" in d

    def test_control_tower_budget_rules_work(self, client):
        """Regression: Budget rules CRUD must work with correct path resolution."""
        r = client.get("/api/control/budget-rules")
        assert r.status_code == 200
        assert isinstance(r.json(), list)


class TestRegressionPass1_DBConnections:
    """Pass 1 B: DB connections were missing try/finally — caused connection leaks."""

    def test_codesearch_project_memory(self, client):
        """Regression: project/memory endpoint works (was missing try/finally)."""
        r = client.get("/api/project/memory")
        assert r.status_code == 200, \
            f"PASS1 REGRESSION: project/memory broken: {r.status_code}"

    def test_secrets_list_works(self, client):
        """Regression: secrets/list works without connection leak."""
        r = client.get("/api/secrets/list")
        assert r.status_code == 200
        d = r.json()
        assert d.get("ok") is True

    def test_knowledge_graph_stats(self, client):
        """Regression: kg/stats works (had 9 missing finally blocks)."""
        r = client.get("/api/knowledge-graph/stats")
        assert r.status_code == 200
        d = r.json()
        assert "entities" in d and "relations" in d

    def test_e2e_status_works(self, client):
        """Regression: e2e/status works (had 5 missing finally blocks)."""
        r = client.get("/api/e2e/status")
        assert r.status_code == 200
        d = r.json()
        assert "playwright_installed" in d


class TestRegressionPass1_InjectSteering:
    """Pass 1 C: specs.py had 0 inject_steering=False — fixed."""

    def test_specs_endpoints_work(self, client):
        """Regression: specs endpoints work after inject_steering fix."""
        r = client.get("/api/specs")
        assert r.status_code == 200
        d = r.json()
        assert "specs" in d

    def test_specs_create_works(self, client):
        """Regression: Creating a spec still works after the fix."""
        r = client.post("/api/specs", json={"title": "Regress Pass1 Spec"})
        assert r.status_code == 200
        d = r.json()
        assert "spec" in d
        spec_id = d["spec"]["id"]
        # Cleanup
        client.delete(f"/api/specs/{spec_id}")


class TestRegressionPass2_DBConnections:
    """Pass 2 B: Additional DB connection fixes across 13 more routers."""

    def test_workspaces_list(self, client):
        """Regression: workspaces list works (had 8 missing finally)."""
        r = client.get("/api/workspaces")
        assert r.status_code == 200
        assert isinstance(r.json(), (list, dict))

    def test_workspaces_activate_no_500(self, client):
        """Regression: workspace activate doesn't return 500 (DB reuse bug fixed)."""
        # Create a workspace
        create = client.post("/api/workspaces", json={"name": "Regress WS Activate"})
        if create.status_code == 200:
            ws_id = create.json().get("id", "")
            if ws_id:
                r = client.post(f"/api/workspaces/{ws_id}/activate")
                assert r.status_code == 200, \
                    f"PASS2 REGRESSION: workspace activate returned {r.status_code}: {r.text[:200]}"
                assert r.json().get("ok") is True

    def test_steering_list_works(self, client):
        """Regression: steering files list works (had 8 missing finally)."""
        r = client.get("/api/steering")
        assert r.status_code == 200

    def test_evals_summary_works(self, client):
        """Regression: evals summary works (had 5 missing finally)."""
        r = client.get("/api/evals/summary")
        assert r.status_code == 200

    def test_rag_list_works(self, client):
        """Regression: rag pipeline list works (had 5 missing finally)."""
        r = client.get("/api/rag/pipelines")
        assert r.status_code == 200

    def test_hitl_queue_works(self, client):
        """Regression: HITL queue works (had 5 missing finally)."""
        r = client.get("/api/hitl/queue")
        assert r.status_code == 200
        d = r.json()
        assert "interrupts" in d

    def test_chat_history_works(self, client):
        """Regression: chat history works (had 2 missing finally)."""
        r = client.get("/api/chat/history?limit=5")
        assert r.status_code == 200

    def test_bugbot_reviews_works(self, client):
        """Regression: bugbot reviews works (had 6 missing finally)."""
        r = client.get("/api/bugbot/reviews?limit=5")
        assert r.status_code == 200

    def test_terminal_history_works(self, client):
        """Regression: terminal history works (had 3 missing finally)."""
        r = client.get("/api/terminal/history?limit=5")
        assert r.status_code == 200

    def test_webhooks_list_works(self, client):
        """Regression: webhooks list works (had 2 missing finally)."""
        r = client.get("/api/webhooks")
        assert r.status_code == 200


class TestRegressionPass2_InjectSteering:
    """Pass 2 C: agents.py and workflow.py missing inject_steering=False."""

    def test_agents_endpoint_works(self, client):
        """Regression: agents endpoint works after inject_steering fix."""
        r = client.get("/api/agents")
        assert r.status_code == 200

    def test_workflow_list_works(self, client):
        """Regression: workflow list works after inject_steering fix."""
        r = client.get("/api/workflow")
        assert r.status_code == 200


class TestRegressionPass3_ServicesFixes:
    """Pass 3 H: Services (scheduler.py, memory_db.py) DB connection fixes."""

    def test_scheduler_status_accessible(self, client):
        """Regression: Loop scheduler status accessible (scheduler.py fixed)."""
        r = client.get("/api/loops/status")
        assert r.status_code == 200

    def test_memory_stats_complete(self, client):
        """Regression: memory_db.py audit_log and seed functions work."""
        r = client.get("/api/memory/stats")
        assert r.status_code == 200
        d = r.json()
        assert "total" in d


class TestRegressionPass3_RemainingRouters:
    """Pass 3 B: Remaining routers with DB connection gaps."""

    def test_crdt_docs_list(self, client):
        """Regression: CRDT docs list works (had 4 missing finally)."""
        r = client.get("/api/crdt/docs")
        assert r.status_code == 200

    def test_hooks_list_works(self, client):
        """Regression: hooks list works (had 4 missing finally)."""
        r = client.get("/api/hooks?limit=5")
        assert r.status_code == 200

    def test_observability_traces_works(self, client):
        """Regression: observability traces works (had 4 missing finally)."""
        r = client.get("/api/observability/traces?limit=5")
        assert r.status_code == 200

    def test_codeindex_stats_works(self, client):
        """Regression: codeindex stats works (had 3 missing finally)."""
        r = client.get("/api/codeindex/stats")
        assert r.status_code == 200

    def test_arena_leaderboard_works(self, client):
        """Regression: arena leaderboard works (had 2 missing finally)."""
        r = client.get("/api/arena/leaderboard")
        assert r.status_code == 200

    def test_swarm_history_works(self, client):
        """Regression: swarm history works (had 1 missing finally)."""
        r = client.get("/api/swarm/history")
        assert r.status_code == 200


class TestRegressionBugFix_WorkspaceActivate:
    """BUG: workspaces activate_workspace returned 500 — DB connection reuse after close."""

    def test_workspace_activate_returns_200(self, client):
        """Regression: workspace activate returns 200, not 500."""
        # Create workspace
        create = client.post("/api/workspaces",
                             json={"name": f"Regress Activate Test"})
        if create.status_code != 200:
            return
        ws_id = create.json().get("id", "")
        if not ws_id:
            return

        # Activate it — this was 500 before the fix
        r = client.post(f"/api/workspaces/{ws_id}/activate")
        assert r.status_code == 200, \
            f"REGRESSION: workspace activate is {r.status_code}: {r.text[:200]}"
        d = r.json()
        assert d.get("ok") is True, \
            f"REGRESSION: workspace activate ok=False: {d}"
        assert "id" in d or "name" in d
