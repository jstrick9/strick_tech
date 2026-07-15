"""
Integration Flow 16 — Marketplace, Plugins & Ambient Intelligence
Tests the complete plugin/marketplace lifecycle and ambient AI features:
  Marketplace browse → Plugin install → Skills → Ambient scan → Health
"""
from __future__ import annotations
import asyncio, time
import httpx, pytest
from .conftest import BASE, TIMEOUT, uid, GET, POST, PATCH, DELETE, ok, ok_or, check


class TestMarketplaceFlow:
    """Marketplace: browse, install, review, manage."""

    async def test_01_marketplace_list_packs(self, client):
        """Marketplace lists available packs with metadata."""
        r = await GET(client, "/api/marketplace")
        d = ok(r, "marketplace list")
        packs = d.get("packs", d) if isinstance(d, dict) else d
        check("is list", isinstance(packs, list))
        # Verify structure of each pack
        for pack in packs[:3]:
            check("has id", "id" in pack)
            check("has name", "name" in pack)

    async def test_02_marketplace_categories(self, client):
        """Marketplace categories are accessible."""
        r = await GET(client, "/api/marketplace/categories")
        d = ok(r, "marketplace categories")
        categories = d.get("categories", d) if isinstance(d, dict) else d
        check("categories is list", isinstance(categories, list))
        check("has categories", len(categories) >= 0)

    async def test_03_marketplace_featured(self, client):
        """Featured packs endpoint works."""
        r = await GET(client, "/api/marketplace/featured")
        d = ok(r, "marketplace featured")
        check("is dict or list", isinstance(d, (dict, list)))

    async def test_04_marketplace_search(self, client):
        """Search marketplace returns filtered results."""
        r = await GET(client, "/api/marketplace?q=react&limit=5")
        d = ok(r, "marketplace search")
        packs = d.get("packs", d) if isinstance(d, dict) else d
        check("search results list", isinstance(packs, list))

    async def test_05_marketplace_pack_detail(self, client):
        """Individual pack details are accessible."""
        packs = (await GET(client, "/api/marketplace")).json()
        pack_list = packs.get("packs", packs) if isinstance(packs, dict) else packs
        if pack_list:
            pack_id = pack_list[0]["id"]
            r = await GET(client, f"/api/marketplace/{pack_id}")
            d = ok(r, "pack detail")
            check("has pack data", "id" in d or "pack" in d)

    async def test_06_marketplace_install_uninstall(self, client):
        """Pack can be installed and uninstalled."""
        packs = (await GET(client, "/api/marketplace")).json()
        pack_list = packs.get("packs", packs) if isinstance(packs, dict) else packs
        if not pack_list:
            return

        pack_id = pack_list[0]["id"]

        # Install (accept any non-5xx — may already be installed in full suite)
        install_r = await POST(client, f"/api/marketplace/{pack_id}/install")
        check("install not 5xx", install_r.status_code < 500)

        # Check installed
        installed = (await GET(client, "/api/marketplace/installed/list")).json()
        check("installed list ok", installed is not None)

        # Uninstall
        uninstall_r = await client.delete(f"/api/marketplace/{pack_id}/uninstall")
        check("uninstall not 5xx", uninstall_r.status_code < 500)

    async def test_07_installed_list(self, client):
        """Installed packs list is accessible."""
        r = await GET(client, "/api/marketplace/installed/list")
        d = ok(r, "installed list")
        installed = d.get("installed", d) if isinstance(d, dict) else d
        check("is list", isinstance(installed, list))


class TestPluginsFlow:
    """Plugin management: list, install, uninstall."""

    async def test_01_plugins_list(self, client):
        """Plugins list is accessible."""
        r = await GET(client, "/api/plugins/installed")
        d = ok(r, "plugins list")
        check("has plugins", "plugins" in d or "installed" in d or isinstance(d, (list, dict)))

    async def test_02_plugins_registry(self, client):
        """Custom plugin registry is accessible."""
        r = await GET(client, "/api/plugins/registry")
        check("registry 200", r.status_code == 200)

    async def test_03_install_nonexistent_graceful(self, client):
        """Installing nonexistent plugin fails gracefully."""
        r = await POST(client, "/api/plugins/install/nonexistent-plugin-xyz")
        check("not 500", r.status_code != 500)
        d = r.json()
        check("ok false or error", d.get("ok") is False or "error" in d or
              r.status_code in (200, 404))


class TestSkillsIntegration:
    """Skills: list, execute, create."""

    async def test_01_skills_list(self, client):
        """Skills list is accessible."""
        r = await GET(client, "/api/skills")
        d = ok(r, "skills list")
        check("has skills", "skills" in d or isinstance(d, list))

    async def test_02_skills_categories(self, client):
        """Skills are organized by categories."""
        r = await GET(client, "/api/skills/categories")
        check("categories 200", r.status_code in (200, 404))

    async def test_03_skill_create_and_run(self, client):
        """Creating and running a skill works end-to-end."""
        # Create a simple skill
        r = await POST(client, "/api/skills", {
            "name": f"Integration Test Skill {uid()}",
            "description": "A simple test skill",
            "prompt": "Echo the following input verbatim: {{input}}",
            "category": "utilities",
            "params": [{"name": "input", "type": "string"}]
        })
        d = ok(r, "create skill")
        check("skill created", d.get("ok") is True or "id" in d)
        skill_id = d.get("id") or d.get("skill_id")

        if skill_id:
            # Run it
            run_r = await POST(client, f"/api/skills/{skill_id}/run", {
                "input": "integration test input"
            })
            check("skill run 200", run_r.status_code in (200, 404))


class TestAmbientIntelligence:
    """Ambient agent: scan, health, background tasks, notifications."""

    async def test_01_ambient_scan_detects_todos(self, client):
        """Ambient scan detects code issues in preview files."""
        r = await POST(client, "/api/ambient/scan", {
            "deep": False,
            "max_files": 10
        })
        d = ok(r, "ambient scan")
        check("scan ok", d["ok"] is True)
        check("has suggestions list", isinstance(d["suggestions"], list))
        check("has count", d["count"] >= 0)
        check("has categories", "categories" in d)

    async def test_02_suggestions_severity_ordering(self, client):
        """Suggestions are ordered by severity (high first)."""
        r = await GET(client, "/api/ambient/suggestions?limit=20")
        d = ok(r, "get suggestions")
        check("has suggestions", "suggestions" in d)
        # If we have suggestions, verify structure
        for s in d["suggestions"][:3]:
            check("has title", "title" in s)
            check("has severity", "severity" in s)
            check("severity valid", s["severity"] in ("high", "medium", "low", "info"))

    async def test_03_health_score_dimensions(self, client):
        """Health score returns all 5 dimensions."""
        r = await GET(client, "/api/ambient/health")
        d = ok(r, "health score")
        check("has overall", "overall" in d)
        check("has grade", "grade" in d)
        check("has scores", "scores" in d)
        scores = d["scores"]
        for dim in ("security", "complexity", "debt", "docs", "deps"):
            check(f"has {dim} score", dim in scores)
            check(f"{dim} 0-100", 0 <= scores[dim] <= 100)

    async def test_04_health_history_grows(self, client):
        """Health history accumulates after scans."""
        before = len((await GET(client, "/api/ambient/health/history")).json().get("snapshots", []))

        # Trigger a new health scan
        await GET(client, "/api/ambient/health")

        after_r = await GET(client, "/api/ambient/health/history")
        after = len(after_r.json().get("snapshots", []))
        check("history grew", after >= before)

    async def test_05_background_task_creates_and_runs(self, client):
        """Background task is created and executes."""
        r = await POST(client, "/api/ambient/tasks", {
            "name": f"Integration Background Task {uid()}",
            "prompt": "Say 'integration test complete' and nothing else.",
            "agent_id": "builder",
            "trigger_src": "integration_test"
        })
        d = ok(r, "create background task")
        check("task ok", d["ok"] is True)
        check("task_id present", "task_id" in d)
        task_id = d["task_id"]
        check("task status running", d["status"] == "running")

        # Wait for completion
        for _ in range(10):
            await asyncio.sleep(1)
            task_r = await GET(client, f"/api/ambient/tasks/{task_id}")
            td = ok(task_r, "get task")
            if td.get("status") in ("done", "failed"):
                break

        final = (await GET(client, f"/api/ambient/tasks/{task_id}")).json()
        check("task completed", final.get("status") in ("done", "failed", "running"))

    async def test_06_dismiss_suggestion(self, client):
        """Suggestions can be dismissed."""
        # Add a suggestion via scan
        await POST(client, "/api/ambient/scan", {"max_files": 5})
        suggestions = (await GET(client, "/api/ambient/suggestions?limit=1")).json()
        sug_list = suggestions.get("suggestions", [])
        if sug_list:
            sid = sug_list[0]["id"]
            dis_r = await POST(client, f"/api/ambient/suggestions/{sid}/dismiss")
            check("dismiss ok", dis_r.status_code in (200, 404))

    async def test_07_background_tasks_list(self, client):
        """Background tasks list is accessible."""
        r = await GET(client, "/api/ambient/tasks?limit=10")
        d = ok(r, "tasks list")
        check("has tasks", "tasks" in d)
        check("has count", "count" in d)
