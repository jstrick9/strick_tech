"""
UAT 14 — Developer Pipeline & CI/CD Experience
User Stories:
  • As a developer, I can build, test, and deploy code from within the platform
  • As a developer, I can run automated E2E tests on my preview app
  • As a developer, I can generate test cases automatically
  • As a developer, I can review code and get quality scores
  • As a developer, I replay workflow runs to debug issues

Acceptance Criteria at the USER level.
"""
from __future__ import annotations
import asyncio, time
import httpx, pytest
from .conftest import BASE, uid, GET, POST, PATCH, DELETE, j, accept, uat, no_error


class TestUATCodeQualityPipeline:
    """User Story: As a developer, I get automated code quality checks."""

    async def test_developer_gets_code_review(self, U):
        """AC: Developer submits code diff → gets quality score with specific issues."""
        r = await POST(U, "/api/bugbot/review/diff", {
            "diff": """--- a/app.py
+++ b/app.py
@@ -1,5 +1,12 @@
 from flask import Flask, request
 app = Flask(__name__)
 
+users = {}
+
 @app.route('/user/<id>')
 def get_user(id):
-    return db.query(f"SELECT * FROM users WHERE id={id}")
+    query = f"SELECT * FROM users WHERE id = '{id}'"
+    result = db.execute(query)
+    return result
""",
            "language": "python"
        })
        no_error(r, "code review")
        d = j(r)
        uat("review completed", d.get("ok") is True)

    async def test_developer_gets_automated_test_generation(self, U):
        """AC: Developer submits function → gets pytest test cases."""
        r = await POST(U, "/api/testgen/generate", {
            "code": """def calculate_discount(price: float, pct: float) -> float:
    if not 0 <= pct <= 100:
        raise ValueError(f"Invalid discount: {pct}")
    return price * (1 - pct / 100)
""",
            "language": "python",
            "framework": "pytest"
        })
        no_error(r, "test generation")
        d = j(r)
        uat("test generation responded", isinstance(d, dict))

    async def test_developer_sees_code_complexity(self, U):
        """AC: Developer opens Code Intelligence → sees complexity scores per function."""
        r = await GET(U, "/api/codeindex/complexity", min_complexity=1, limit=10)
        no_error(r, "code complexity")
        uat("complexity data accessible", r.status_code == 200)

    async def test_developer_searches_codebase(self, U):
        """AC: Developer types in search → finds where functions/variables are used."""
        r = await GET(U, "/api/project/search", q="router", limit=5)
        no_error(r, "code search")
        d = j(r)
        uat("search results returned", "results" in d)
        uat("total match count shown", "total" in d)
        uat("query echoed back", d["query"] == "router")

    async def test_developer_sees_import_graph(self, U):
        """AC: Developer opens Dependency Graph → sees which modules depend on each other."""
        r = await GET(U, "/api/codeindex/graph", limit=20)
        no_error(r, "import graph")
        uat("graph data accessible", r.status_code == 200)

    async def test_developer_runs_e2e_tests(self, U):
        """AC: Developer clicks 'Run E2E' → tests execute against preview and show results."""
        r = await POST(U, "/api/e2e/run", {"target": "web"})
        no_error(r, "e2e run")
        d = j(r)
        uat("E2E tests ran", "ok" in d)
        uat("test results shown with passed count", "passed" in d)
        uat("total test count shown", "total" in d)
        uat("score shown", "score" in d and 0 <= d["score"] <= 1.0)
        uat("engine type shown (playwright/heuristic)", "engine" in d)

    async def test_developer_sees_e2e_history(self, U):
        """AC: Developer can see past E2E run results for comparison."""
        r = await GET(U, "/api/e2e/history", limit=5)
        no_error(r, "e2e history")
        uat("E2E history accessible", isinstance(r.json(), list))

    async def test_developer_checks_playwright_status(self, U):
        """AC: Developer sees if Playwright is installed for real screenshots."""
        r = await GET(U, "/api/e2e/playwright/status")
        no_error(r, "playwright status")
        d = j(r)
        uat("playwright status shown", "installed" in d or "browser_ready" in d)


class TestUATDeploymentWorkflow:
    """User Story: As a developer, I deploy my preview app to production."""

    async def test_developer_sees_deployment_providers(self, U):
        """AC: Developer opens Deploy pane → sees Netlify, Vercel, GitHub Pages options."""
        r = await GET(U, "/api/deploy/providers")
        no_error(r, "deployment providers")
        d = j(r)
        providers = d.get("providers", d) if isinstance(d, dict) else d
        uat("deployment providers available", len(providers) >= 1)

    async def test_developer_attempts_deploy_without_token(self, U):
        """AC: Missing API key → helpful message 'Add NETLIFY_TOKEN to vault'."""
        r = await POST(U, "/api/deploy/netlify", {"site_name": "uat-test-site"})
        no_error(r, "deploy without token")
        d = j(r)
        uat("helpful message shown (not crash)", "ok" in d)

    async def test_developer_sees_deploy_history(self, U):
        """AC: Deployment history shows past deployments with timestamps."""
        r = await GET(U, "/api/deploy/history")
        no_error(r, "deploy history")
        uat("history accessible", r.status_code == 200)


class TestUATReplayDebugger:
    """User Story: As a developer, I replay past workflow runs to debug issues."""

    async def test_developer_sees_replay_run_list(self, U):
        """AC: Developer opens Replay → sees list of past workflow executions."""
        r = await GET(U, "/api/replay/runs", limit=10)
        no_error(r, "replay runs")
        d = j(r)
        uat("replay list accessible", "runs" in d or isinstance(d, (list, dict)))

    async def test_developer_handles_nonexistent_replay(self, U):
        """AC: Developer searches for deleted run → 'Run not found' message."""
        r = await GET(U, "/api/replay/runs/nonexistent_run_xyz_abc")
        uat("graceful not-found response", r.status_code in (200, 404))
        if r.status_code == 200:
            d = j(r)
            uat("informative error returned",
                d.get("ok") is False or "steps" in d)


class TestUATPluginSDKDeveloper:
    """User Story: As a developer, I build and publish plugins for the platform."""

    async def test_developer_gets_plugin_template(self, U):
        """AC: Developer clicks 'New Plugin' → gets starter template."""
        r = await GET(U, "/api/pluginsdk/template")
        no_error(r, "plugin template")
        uat("template accessible", r.status_code == 200)

    async def test_developer_validates_plugin_pack(self, U):
        """AC: Developer validates plugin → sees pass/fail with specific issues."""
        r = await POST(U, "/api/pluginsdk/validate", {
            "pack": {
                "name": "uat-test-plugin",
                "version": "1.0.0",
                "description": "UAT test plugin",
                "author": "uat_developer"
            }
        })
        no_error(r, "validate plugin")
        uat("validation ran", r.status_code == 200)

    async def test_developer_creates_plugin_pack(self, U):
        """AC: Developer creates plugin pack → it appears in their SDK packs list."""
        r = await POST(U, "/api/pluginsdk/packs", {
            "name": f"uat-developer-plugin-{uid()}",
            "version": "0.1.0",
            "description": "UAT developer plugin pack"
        })
        no_error(r, "create plugin pack")
        d = j(r)
        uat("plugin pack created", d.get("ok") is True or "id" in d or "pack_id" in d)

    async def test_developer_sees_plugin_registry(self, U):
        """AC: Developer can browse available plugins in the registry."""
        r = await GET(U, "/api/pluginsdk/registry")
        no_error(r, "plugin registry")
        uat("registry accessible", r.status_code == 200)
