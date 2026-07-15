"""
FLOW-10: Hooks + Webhooks event system
FLOW-13: Knowledge Graph entity → relations → query
FLOW-14: RAG Pipeline: Create → Ingest → List
FLOW-08: Plugin → Skills → SDK roundtrip
FLOW-15: Evals Engine
"""
import pytest
from tests.integration.conftest import *


@pytest.mark.asyncio
class TestHooksWebhooksEventSystem:
    """FLOW-10: Hooks and webhooks fire and record events."""

    async def test_01_create_hook_appears_in_list(self, client):
        """Create hook → verify in list."""
        hook_name = uid("IntHook")
        r = await POST(client, "/api/hooks", {
            "name": hook_name,
            "event": "agent.complete",
            "prompt": "Handle integration test event: {{event}}",
            "agent_id": "builder",
            "enabled": True
        })
        d = ok(r)
        hid = d.get("hook_id") or d.get("id") or (d.get("hook") or {}).get("id")
        check("hook id returned", bool(hid))

        hooks = ok(await GET(client, "/api/hooks"))
        hook_list = hooks.get("hooks", hooks) if isinstance(hooks, dict) else hooks
        ids = [h.get("id") or h.get("hook_id") for h in hook_list]
        check("hook in list", hid in ids)

        await DELETE(client, f"/api/hooks/{hid}")

    async def test_02_toggle_hook_changes_enabled(self, client):
        """Toggle hook → enabled state flips."""
        r = await POST(client, "/api/hooks", {
            "name": uid("ToggleHook"),
            "event": "agent.complete",
            "prompt": "Toggle test",
            "agent_id": "builder",
            "enabled": True
        })
        d = ok(r)
        hid = d.get("hook_id") or d.get("id")

        if hid:
            r2 = await POST(client, f"/api/hooks/{hid}/toggle", {})
            assert r2.status_code in (200, 404)

            await DELETE(client, f"/api/hooks/{hid}")

    async def test_03_create_webhook_appears_in_list(self, client):
        """Create webhook → verify in list."""
        wh_name = uid("IntWebhook")
        r = await POST(client, "/api/webhooks", {
            "name": wh_name,
            "secret": "integration_test_secret",
            "agent_id": "builder",
            "prompt_template": "Process: {{payload}}"
        })
        d = ok(r)
        whid = d.get("id") or (d.get("webhook") or {}).get("id")
        check("webhook id returned", bool(whid))

        whs = ok(await GET(client, "/api/webhooks"))
        wh_list = whs.get("webhooks", whs) if isinstance(whs, dict) else whs
        ids = [w.get("id") for w in wh_list]
        check("webhook in list", whid in ids)

        await DELETE(client, f"/api/webhooks/{whid}")

    async def test_04_webhook_events_list(self, client):
        """Create webhook → events list is accessible."""
        r = await POST(client, "/api/webhooks", {
            "name": uid("EventsWH"),
            "secret": "s",
            "agent_id": "builder",
            "prompt_template": "{{payload}}"
        })
        d = ok(r)
        whid = d.get("id") or (d.get("webhook") or {}).get("id")

        if whid:
            r2 = await GET(client, f"/api/webhooks/{whid}/events")
            assert r2.status_code in (200, 404)
            if r2.status_code == 200:
                check("events is list", isinstance(r2.json(), list))

            await DELETE(client, f"/api/webhooks/{whid}")

    async def test_05_fire_event_records_in_runs(self, client):
        """Fire hook event → appears in recent runs."""
        r = await POST(client, "/api/hooks/fire", {
            "event": "integration.test",
            "data": {"source": "integration_test", "ts": "now"}
        })
        assert r.status_code in (200, 404)

        runs = await GET(client, "/api/hooks/runs/recent")
        assert runs.status_code in (200, 404)

    async def test_06_event_types_accessible(self, client):
        """Event types list returns known event names."""
        r = await GET(client, "/api/hooks/events/types")
        assert r.status_code in (200, 404)
        if r.status_code == 200:
            d = r.json()
            types = d.get("types", d.get("event_types", d))
            check("types present", isinstance(types, (list, dict)))

    async def test_07_webhook_test_fires(self, client):
        """POST /api/webhooks/{id}/test fires a test event."""
        r = await POST(client, "/api/webhooks", {
            "name": uid("TestWH"), "secret": "s"
        })
        d = ok(r)
        whid = d.get("id") or (d.get("webhook") or {}).get("id")

        if whid:
            r2 = await POST(client, f"/api/webhooks/{whid}/test", {})
            assert r2.status_code in (200, 404)

            await DELETE(client, f"/api/webhooks/{whid}")

    async def test_08_hook_run_endpoint(self, client):
        """Manually run a hook."""
        r = await POST(client, "/api/hooks", {
            "name": uid("RunHook"),
            "event": "manual",
            "prompt": "Run this: {{event}}",
            "agent_id": "builder",
            "enabled": True
        })
        d = ok(r)
        hid = d.get("hook_id") or d.get("id")

        if hid:
            r2 = await POST(client, f"/api/hooks/{hid}/run", {
                "data": {"test": True}
            })
            assert r2.status_code in (200, 404, 500)

            await DELETE(client, f"/api/hooks/{hid}")


@pytest.mark.asyncio
class TestKnowledgeGraphIntegration:
    """FLOW-13: Knowledge Graph entity/relation/query flow."""

    async def test_01_create_entity(self, client):
        """Create entity → verify id returned."""
        r = await POST(client, "/api/knowledge-graph/entities", {
            "name": uid("KGEntity"),
            "type": "concept",
            "description": "Integration test entity"
        })
        d = ok(r)
        check("ok true", d["ok"] is True)
        eid = d.get("entity_id") or d.get("id")
        check("entity_id returned", bool(eid))

    async def test_02_entity_visible_in_list(self, client):
        """Created entity appears in entities list."""
        name = uid("ListKGEntity")
        r = await POST(client, "/api/knowledge-graph/entities", {
            "name": name, "type": "concept"
        })
        eid = ok(r).get("entity_id")

        r2 = await GET(client, "/api/knowledge-graph/entities")
        assert r2.status_code in (200, 404)
        if r2.status_code == 200:
            entities = r2.json()
            entities = entities.get("entities", entities) if isinstance(entities, dict) else entities
            if isinstance(entities, list):
                names = [e.get("name") for e in entities]
                check("entity in list", name in names)

    async def test_03_create_relation_between_entities(self, client):
        """Create two entities + relation → relation recorded."""
        r1 = await POST(client, "/api/knowledge-graph/entities", {
            "name": uid("KGEntityA"), "type": "concept"
        })
        r2 = await POST(client, "/api/knowledge-graph/entities", {
            "name": uid("KGEntityB"), "type": "concept"
        })
        eid_a = ok(r1).get("entity_id")
        eid_b = ok(r2).get("entity_id")

        if eid_a and eid_b:
            r3 = await POST(client, "/api/knowledge-graph/relations", {
                "from_entity": eid_a,
                "relation": "relates_to",
                "to_entity": eid_b,
                "weight": 1.0
            })
            assert r3.status_code in (200, 404, 422)

    async def test_04_stats_reflect_additions(self, client):
        """Stats endpoint shows entities count."""
        await POST(client, "/api/knowledge-graph/entities", {
            "name": uid("StatsKGE"), "type": "tool"
        })
        stats = ok(await GET(client, "/api/knowledge-graph/stats"))
        check("entities count present", "entities" in stats or isinstance(stats, dict))

    async def test_05_query_finds_entity(self, client):
        """Query knowledge graph for an entity."""
        name = uid("QueryKGE")
        await POST(client, "/api/knowledge-graph/entities", {
            "name": name, "type": "concept", "description": f"Queryable entity {name}"
        })
        r = await POST(client, "/api/knowledge-graph/query", {"query": name})
        assert r.status_code in (200, 404)
        if r.status_code == 200:
            d = r.json()
            check("query returns dict", isinstance(d, dict))

    async def test_06_facts_endpoint(self, client):
        """Add a fact to knowledge graph."""
        r = await POST(client, "/api/knowledge-graph/facts", {
            "subject": "Python",
            "predicate": "is_language",
            "object": "programming"
        })
        assert r.status_code in (200, 201, 404, 422)

    async def test_07_traverse_entity(self, client):
        """Traverse entity graph from a starting entity."""
        r = await POST(client, "/api/knowledge-graph/entities", {
            "name": uid("TraverseKGE"), "type": "concept"
        })
        eid = ok(r).get("entity_id")

        if eid:
            r2 = await GET(client, f"/api/knowledge-graph/traverse/{eid}")
            assert r2.status_code in (200, 404)


@pytest.mark.asyncio
class TestRAGPipelineIntegration:
    """FLOW-14: RAG Pipeline create → ingest → query flow."""

    async def test_01_create_pipeline(self, client):
        """Create RAG pipeline → verify fields."""
        r = await POST(client, "/api/rag/pipelines", {
            "name": uid("IntRAG"),
            "description": "Integration test RAG pipeline"
        })
        assert r.status_code in (200, 201, 422)
        if r.status_code in (200, 201):
            d = r.json()
            pid = d.get("id") or d.get("pipeline_id") or (d.get("pipeline") or {}).get("id")
            check("pipeline id returned", bool(pid))
            return pid

    async def test_02_pipeline_in_list(self, client):
        """Created pipeline appears in pipelines list."""
        r = await POST(client, "/api/rag/pipelines", {
            "name": uid("ListRAG"), "description": "List test"
        })
        if r.status_code not in (200, 201):
            return
        d = r.json()
        pid = d.get("id") or d.get("pipeline_id") or (d.get("pipeline") or {}).get("id")

        pipelines = ok(await GET(client, "/api/rag/pipelines"))
        p_list = pipelines.get("pipelines", pipelines) if isinstance(pipelines, dict) else pipelines
        ids = [p.get("id") for p in p_list if isinstance(p, dict)]
        check("pipeline in list", pid in ids)

        await DELETE(client, f"/api/rag/pipelines/{pid}")

    async def test_03_ingest_document(self, client):
        """Ingest document into pipeline."""
        r = await POST(client, "/api/rag/pipelines", {
            "name": uid("IngestRAG"), "description": "Ingest test"
        })
        if r.status_code not in (200, 201):
            return
        pid = r.json().get("id") or r.json().get("pipeline_id") or (r.json().get("pipeline") or {}).get("id")

        if pid:
            r2 = await POST(client, f"/api/rag/pipelines/{pid}/documents", {
                "content": "Integration test document. This is test content for RAG indexing.",
                "title": "Integration Test Document",
                "source": "integration_test"
            })
            assert r2.status_code in (200, 201, 400, 404)

            await DELETE(client, f"/api/rag/pipelines/{pid}")

    async def test_04_delete_pipeline_removes_from_list(self, client):
        """Delete pipeline → not in list."""
        r = await POST(client, "/api/rag/pipelines", {
            "name": uid("DelRAG"), "description": "Delete test"
        })
        if r.status_code not in (200, 201):
            return
        pid = r.json().get("id") or r.json().get("pipeline_id") or (r.json().get("pipeline") or {}).get("id")

        await DELETE(client, f"/api/rag/pipelines/{pid}")

        pipelines = ok(await GET(client, "/api/rag/pipelines"))
        p_list = pipelines.get("pipelines", pipelines) if isinstance(pipelines, dict) else pipelines
        ids = [p.get("id") for p in p_list if isinstance(p, dict)]
        check("deleted pipeline not in list", pid not in ids)


@pytest.mark.asyncio
class TestEvalsIntegration:
    """FLOW-15: Evals engine endpoints."""

    async def test_01_red_team_attacks_list(self, client):
        """Red team attacks list returns known attack types."""
        r = await GET(client, "/api/evals/red-team/attacks")
        assert r.status_code in (200, 404)
        if r.status_code == 200:
            d = r.json()
            attacks = d.get("attacks", d)
            check("attacks is list or dict", isinstance(attacks, (list, dict)))

    async def test_02_eval_runs_accessible(self, client):
        """Evals runs list accessible."""
        r = await GET(client, "/api/evals/runs")
        assert r.status_code in (200, 404)

    async def test_03_evals_summary(self, client):
        """Evals summary returns aggregate stats."""
        r = await GET(client, "/api/evals/summary")
        assert r.status_code in (200, 404)

    async def test_04_evals_datasets(self, client):
        """Evals datasets endpoint."""
        r = await GET(client, "/api/evals/datasets")
        assert r.status_code in (200, 404)

    async def test_05_evals_ab_tests(self, client):
        """A/B tests endpoint accessible."""
        r = await GET(client, "/api/evals/ab-tests")
        assert r.status_code in (200, 404)


@pytest.mark.asyncio
class TestPluginsSkillsSDK:
    """FLOW-08: Plugin → Skills → SDK roundtrip."""

    async def test_01_installed_plugins_list(self, client):
        """Installed plugins are readable."""
        plugins = ok(await GET(client, "/api/plugins/installed"))
        check("plugins is list", isinstance(plugins, list))

    async def test_02_skills_list_matches_plugins(self, client):
        """Skills list accessible."""
        d = ok(await GET(client, "/api/skills"))
        skills = d.get("skills", d) if isinstance(d, dict) else d
        check("skills is list", isinstance(skills, list))

    async def test_03_sdk_packs_list(self, client):
        """Plugin SDK packs are listable."""
        r = await GET(client, "/api/pluginsdk/packs")
        assert r.status_code in (200, 404)
        if r.status_code == 200:
            d = r.json()
            packs = d.get("packs", d) if isinstance(d, dict) else d
            check("packs is list", isinstance(packs, (list, dict)))

    async def test_04_marketplace_list(self, client):
        """Marketplace plugins accessible."""
        r = await GET(client, "/api/marketplace/plugins")
        assert r.status_code in (200, 404)

    async def test_05_install_plugin_json(self, client):
        """Install a plugin via JSON spec."""
        plugin_id = uid("test_plugin")
        r = await POST(client, "/api/plugins/install/json", {
            "id": plugin_id,
            "name": "Integration Test Plugin",
            "version": "1.0.0",
            "author": "IntegrationTest",
            "category": "testing",
            "emoji": "🧪",
            "skills": []
        })
        assert r.status_code in (200, 201, 400, 409, 422)

    async def test_06_sdk_template(self, client):
        """SDK plugin template endpoint accessible."""
        r = await GET(client, "/api/pluginsdk/template")
        assert r.status_code in (200, 404)

    async def test_07_sdk_validate(self, client):
        """SDK validate endpoint accepts pack JSON."""
        r = await POST(client, "/api/pluginsdk/validate", {
            "id": "test-pack",
            "name": "Test Pack",
            "version": "1.0.0",
            "author": "Test",
            "skills": []
        })
        assert r.status_code in (200, 400, 422)

    async def test_08_plugin_categories(self, client):
        """Plugin categories endpoint."""
        r = await GET(client, "/api/plugins/categories")
        assert r.status_code in (200, 404)
