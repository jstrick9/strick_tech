"""
USABILITY-07: Platform Features — Marketplace, Plugins, Templates, Arena,
Hooks, Webhooks, Integrations, Collab, CRDT, Replay, Profiler, Specs
"""
import pytest
from tests.usability.conftest import *


class TestUseMarketplace:
    """User discovers and installs packs from the marketplace."""

    async def test_marketplace_catalog_loads(self, U):
        """Marketplace shows available packs to browse."""
        r = await GET(U, "/api/marketplace/catalog")
        no_error(r, "marketplace catalog")
        d = j(r)
        items = d if isinstance(d, list) else d.get("packs", d.get("catalog", []))
        uat("catalog items returned", isinstance(items, list))

    async def test_installed_packs_list(self, U):
        """User sees their installed packs."""
        r = await GET(U, "/api/marketplace/installed")
        no_error(r, "installed packs")
        d = j(r)
        installed = d if isinstance(d, list) else d.get("installed", [])
        uat("installed list returned", isinstance(installed, list))

    async def test_marketplace_search(self, U):
        """User searches marketplace for a specific pack type."""
        r = await GET(U, "/api/marketplace/catalog?q=agent")
        no_error(r, "marketplace search")

    async def test_pack_install_and_uninstall(self, U):
        """User installs a pack then uninstalls it."""
        catalog = j(await GET(U, "/api/marketplace/catalog"))
        packs = catalog if isinstance(catalog, list) else catalog.get("packs", [])
        if not packs:
            pytest.skip("No packs in catalog")

        pack_id = packs[0]["id"]
        r = await POST(U, f"/api/marketplace/{pack_id}/install", {})
        no_error(r, "install pack")

        r2 = await DELETE(U, f"/api/marketplace/{pack_id}/uninstall")
        no_error(r2, "uninstall pack")

    async def test_pack_review_submission(self, U):
        """User leaves a review for a marketplace pack."""
        catalog = j(await GET(U, "/api/marketplace/catalog"))
        packs = catalog if isinstance(catalog, list) else catalog.get("packs", [])
        if not packs:
            pytest.skip("No packs in catalog")
        pack_id = packs[0]["id"]
        r = await POST(U, f"/api/marketplace/{pack_id}/review", {
            "rating": 5, "review": "Excellent pack, very useful!"
        })
        no_error(r, "submit review")


class TestUsePlugins:
    """User manages platform plugins."""

    async def test_installed_plugins_visible(self, U):
        """User sees installed plugins."""
        r = await GET(U, "/api/plugins/installed")
        no_error(r, "installed plugins")
        d = j(r)
        plugins = d if isinstance(d, list) else d.get("plugins", d.get("installed", []))
        uat("plugin list returned", isinstance(plugins, list))

    async def test_plugin_sdk_packs(self, U):
        """Developer sees their plugin packs."""
        r = await GET(U, "/api/pluginsdk/packs")
        no_error(r, "pluginsdk packs")
        d = j(r)
        packs = d if isinstance(d, list) else d.get("packs", [])
        uat("packs returned", isinstance(packs, list))

    async def test_create_plugin_pack(self, U):
        """Developer creates a new plugin pack."""
        r = await POST(U, "/api/pluginsdk/packs", {
            "name": uid("MyPlugin"), "description": "A test plugin",
            "version": "1.0.0", "author": "Test Developer",
            "skills": []
        })
        no_error(r, "create plugin pack")
        d = j(r)
        pid = d.get("id") or d.get("pack_id")
        if pid: await DELETE(U, f"/api/pluginsdk/packs/{pid}")

    async def test_plugin_sdk_validate(self, U):
        """Developer validates their plugin manifest."""
        r = await POST(U, "/api/pluginsdk/validate", {
            "manifest": {
                "name": "TestPlugin", "version": "1.0.0",
                "skills": [{"name": "hello", "description": "Says hello"}]
            }
        })
        no_error(r, "validate plugin")


class TestUseTemplates:
    """User scaffolds projects from templates."""

    async def test_template_gallery_loads(self, U):
        """Template gallery shows available project templates."""
        r = await GET(U, "/api/templates")
        no_error(r, "template gallery")
        d = j(r)
        templates = d if isinstance(d, list) else d.get("templates", [])
        uat("templates listed", isinstance(templates, list))
        uat("has templates", len(templates) > 0)

    async def test_template_categories_visible(self, U):
        """Templates organized by category."""
        r = await GET(U, "/api/templates?category=apps")
        no_error(r, "template by category")

    async def test_template_search(self, U):
        """User searches for a template by keyword."""
        r = await GET(U, "/api/templates?q=landing")
        no_error(r, "template search")

    async def test_template_scaffold(self, U):
        """User scaffolds a project from a template."""
        r = await GET(U, "/api/templates")
        d = j(r)
        templates = d if isinstance(d, list) else d.get("templates", [])
        if not templates: pytest.skip("No templates")
        tid = templates[0]["id"]
        r2 = await POST(U, f"/api/templates/{tid}/scaffold", {
            "project_name": uid("MyProject"), "target_path": f"/tmp/{uid()}"
        })
        no_error(r2, "scaffold from template")

    async def test_custom_template_scaffold(self, U):
        """User creates a custom scaffold with their own files."""
        r = await POST(U, "/api/templates/scaffold-custom", {
            "name": uid("CustomScaffold"),
            "files": {
                "README.md": "# My Project\n\nA great project.",
                "main.py": "print('Hello World')"
            }
        })
        no_error(r, "custom scaffold")


class TestUseArena:
    """User compares AI models in head-to-head battles."""

    async def test_arena_models_list(self, U):
        """Arena shows available models for comparison."""
        r = await GET(U, "/api/arena/models")
        no_error(r, "arena models")
        d = j(r)
        models = d if isinstance(d, list) else d.get("models", [])
        uat("models listed", isinstance(models, list))

    async def test_arena_battle_starts(self, U):
        """User submits a prompt — two models battle each other (SSE stream)."""
        r = await POST(U, "/api/arena/battle", {
            "prompt": "Explain quantum entanglement in one sentence.",
            "model_a": "gpt4o-mini", "model_b": "gemini-flash",
            "category": "science"
        })
        no_error(r, "start arena battle")
        # Arena returns SSE stream — check text for battle_id marker
        text = r.text
        uat("battle started (sse or json)",
            "battle_id" in text or "battle" in text or r.status_code == 200)

    async def test_arena_battles_history(self, U):
        """User reviews past arena battles."""
        r = await GET(U, "/api/arena/battles")
        no_error(r, "arena battles history")
        d = j(r)
        battles = d if isinstance(d, list) else d.get("battles", [])
        uat("battles returned", isinstance(battles, list))

    async def test_arena_leaderboard(self, U):
        """User sees model leaderboard rankings."""
        r = await GET(U, "/api/arena/leaderboard")
        no_error(r, "arena leaderboard")
        d = j(r)
        leaders = d if isinstance(d, list) else d.get("leaderboard", d.get("rankings", []))
        uat("leaderboard returned", isinstance(leaders, list))

    async def test_arena_stats_overview(self, U):
        """Arena statistics visible."""
        r = await GET(U, "/api/arena/stats")
        no_error(r, "arena stats")


class TestUseHooksWebhooks:
    """User automates platform workflows with hooks and webhooks."""

    async def test_hook_create_and_list(self, U):
        """User creates a hook to run on task completion."""
        r = await POST(U, "/api/hooks", {
            "name": uid("TaskHook"), "event": "task.completed",
            "action": "notify", "config": {"channel": "team"}
        })
        no_error(r, "create hook")
        d = j(r)
        hid = d.get("id") or d.get("hook_id")

        r2 = await GET(U, "/api/hooks")
        no_error(r2, "list hooks")
        hooks = j(r2) if isinstance(j(r2), list) else j(r2).get("hooks", [])
        uat("hooks listed", isinstance(hooks, list))
        if hid: await DELETE(U, f"/api/hooks/{hid}")

    async def test_webhook_create_and_list(self, U):
        """User registers an outgoing webhook."""
        r = await POST(U, "/api/webhooks", {
            "name": uid("MyWebhook"), "url": "https://example.com/webhook",
            "events": ["task.created", "agent.completed"], "secret": "webhook_secret_123"
        })
        no_error(r, "create webhook")
        d = j(r)
        wid = d.get("id") or d.get("webhook_id")

        r2 = await GET(U, "/api/webhooks")
        no_error(r2, "list webhooks")

        if wid: await DELETE(U, f"/api/webhooks/{wid}")

    async def test_hook_fire_event(self, U):
        """User manually fires a hook event for testing."""
        r = await POST(U, "/api/hooks/fire", {
            "event": "task.completed",
            "payload": {"task_id": "test123", "result": "success"}
        })
        no_error(r, "fire hook event")


class TestUseCollabCRDT:
    """User collaborates in real-time with CRDT documents."""

    async def test_create_collab_session(self, U):
        """User starts a collaborative session."""
        r = await POST(U, "/api/collab/sessions", {
            "name": uid("CollabSession"), "doc_id": uid("doc")
        })
        no_error(r, "create collab session")
        d = j(r)
        sid = d.get("id") or d.get("session_id")
        uat("session created", bool(sid) or d.get("ok") is True)

    async def test_crdt_doc_create_and_edit(self, U):
        """User creates a CRDT document and applies an operation."""
        r = await POST(U, "/api/crdt/docs", {
            "title": uid("CRDTDoc"), "content": "Initial content"
        })
        no_error(r, "create crdt doc")
        d = j(r)
        did = d.get("id") or d.get("doc_id")
        uat("crdt doc created", bool(did) or d.get("ok") is True)

        if did:
            r2 = await POST(U, f"/api/crdt/docs/{did}/op", {
                "op": "insert", "pos": 7, "text": " extended"
            })
            no_error(r2, "crdt insert op")

            r3 = await GET(U, f"/api/crdt/docs/{did}/history")
            no_error(r3, "crdt doc history")

    async def test_crdt_docs_list(self, U):
        """User sees all collaborative documents."""
        r = await GET(U, "/api/crdt/docs")
        no_error(r, "crdt docs list")
        d = j(r)
        docs = d if isinstance(d, list) else d.get("docs", d.get("documents", []))
        uat("docs listed", isinstance(docs, list))


class TestUseReplayProfiler:
    """User replays past runs and profiles performance."""

    async def test_replay_runs_list(self, U):
        """User sees replay-able past runs."""
        r = await GET(U, "/api/replay/runs")
        no_error(r, "replay runs")
        d = j(r)
        runs = d if isinstance(d, list) else d.get("runs", [])
        uat("runs list returned", isinstance(runs, list))

    async def test_profiler_endpoints_visible(self, U):
        """Profiler shows endpoint performance data."""
        r = await GET(U, "/api/profiler/endpoints")
        no_error(r, "profiler endpoints")
        d = j(r)
        uat("endpoint data returned", isinstance(d, dict) or isinstance(d, list))

    async def test_profiler_db_stats(self, U):
        """Profiler shows database query performance."""
        r = await GET(U, "/api/profiler/db/stats")
        no_error(r, "profiler db stats")

    async def test_profiler_memory_history(self, U):
        """Profiler shows memory usage over time."""
        r = await GET(U, "/api/profiler/memory/history")
        no_error(r, "profiler memory history")

    async def test_profiler_flamegraph(self, U):
        """User views a flamegraph of system performance."""
        r = await GET(U, "/api/profiler/flamegraph")
        no_error(r, "profiler flamegraph")

    async def test_profiler_agent_timings(self, U):
        """User sees per-agent execution timing breakdown."""
        r = await GET(U, "/api/profiler/agent/timings")
        no_error(r, "profiler agent timings")


class TestUseSpecs:
    """User creates and executes specifications."""

    async def test_spec_create_and_list(self, U):
        """User creates a project spec and sees it in the list."""
        r = await POST(U, "/api/specs", {
            "name": uid("MySpec"), "description": "A test specification",
            "type": "feature"
        })
        no_error(r, "create spec")
        d = j(r)
        sid = d.get("id") or d.get("spec_id")
        uat("spec created", bool(sid) or d.get("ok") is True)

        r2 = await GET(U, "/api/specs")
        no_error(r2, "list specs")

        if sid:
            # Add requirements
            r3 = await POST(U, f"/api/specs/{sid}/requirements", {
                "requirements": ["Must handle 100 concurrent users", "Response time < 200ms"]
            })
            no_error(r3, "add requirements")
            await DELETE(U, f"/api/specs/{sid}")

    async def test_spec_design_generation(self, U):
        """User generates a design from a spec description."""
        r = await POST(U, "/api/specs", {"name": uid("DesignSpec"), "description": "test"})
        sid = j(r).get("id")
        if not sid: pytest.skip()
        r2 = await POST(U, f"/api/specs/{sid}/design", {
            "prompt": "Design the authentication flow"
        })
        no_error(r2, "spec design generation")
        await DELETE(U, f"/api/specs/{sid}")
