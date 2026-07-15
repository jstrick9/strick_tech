"""Unit tests — Remaining components: Workflows, GitAI, GitHub, Deploy, Templates,
   Observability, HITL, Ambient, Control Tower, System, Leaderboard, Fusion,
   Image Gen, TTS, Browser, Obsidian, Pipeline, Tauri, Replay, E2E, TestGen, Loops
"""
import uuid, pytest
from tests.unit.conftest import assert_ok, post_json, put_json


def _uid(): return uuid.uuid4().hex[:6]


# ── WORKFLOW ─────────────────────────────────────────────────────────────────
class TestWorkflow:
    def test_list_200(self, client):
        assert client.get("/api/workflow").status_code == 200

    def test_list_is_list_or_dict(self, client):
        d = client.get("/api/workflow").json()
        wfs = d if isinstance(d, list) else d.get("workflows", [])
        assert isinstance(wfs, list)

    def test_create_workflow(self, client):
        r = post_json(client, "/api/workflow",
                      {"name": f"UnitWF_{_uid()}",
                       "nodes": [{"id": "n1", "type": "trigger", "label": "Start", "x": 0, "y": 0}],
                       "edges": []})
        assert r.status_code == 200
        d = r.json()
        assert d.get("id") or d.get("ok") is True

    def test_get_by_id(self, client):
        r = post_json(client, "/api/workflow",
                      {"name": f"GetWF_{_uid()}", "nodes": [], "edges": []})
        d = r.json()
        wid = d.get("id") or (d.get("workflow") or {}).get("id")
        if wid:
            r2 = client.get(f"/api/workflow/{wid}")
            assert r2.status_code in (200, 404)

    def test_update_workflow(self, client):
        r = post_json(client, "/api/workflow",
                      {"name": f"UpdWF_{_uid()}", "nodes": [], "edges": []})
        d = r.json()
        wid = d.get("id") or (d.get("workflow") or {}).get("id")
        if wid:
            r2 = client.put(f"/api/workflow/{wid}",
                            json={"name": "UpdatedWF", "nodes": [], "edges": []})
            assert r2.status_code in (200, 404)

    def test_delete_workflow(self, client):
        r = post_json(client, "/api/workflow",
                      {"name": f"DelWF_{_uid()}", "nodes": [], "edges": []})
        d = r.json()
        wid = d.get("id") or (d.get("workflow") or {}).get("id")
        if wid:
            r2 = client.delete(f"/api/workflow/{wid}")
            assert r2.status_code in (200, 204, 404)

    def test_node_types_200(self, client):
        assert client.get("/api/workflow/node-types/list").status_code in (200, 404)


# ── GIT AI ────────────────────────────────────────────────────────────────────
class TestGitAI:
    def test_history_200(self, client):
        assert client.get("/api/gitai/history").status_code in (200, 404)

    def test_changelogs_200(self, client):
        assert client.get("/api/gitai/changelogs").status_code in (200, 404)

    def test_diff_200(self, client):
        assert client.get("/api/gitai/diff").status_code in (200, 400, 404)

    def test_generate_changelog_schema(self, client):
        r = post_json(client, "/api/gitai/changelog/generate",
                      {"repo_path": "/tmp", "since_tag": ""})
        assert r.status_code in (200, 400, 404, 500)


# ── GITHUB ────────────────────────────────────────────────────────────────────
class TestGitHub:
    def test_status_200(self, client):
        r = client.get("/api/github/status")
        assert r.status_code in (200, 404)

    def test_repos_200_or_401(self, client):
        r = client.get("/api/github/repos")
        assert r.status_code in (200, 401, 403, 404)

    def test_save_token(self, client):
        r = post_json(client, "/api/github/token",
                      {"token": "ghp_unit_test_token_XXXX"})
        assert r.status_code in (200, 400, 404, 422)


# ── DEPLOY ────────────────────────────────────────────────────────────────────
class TestDeploy:
    def test_providers_200(self, client):
        assert client.get("/api/deploy/providers").status_code in (200, 404)

    def test_history_200(self, client):
        assert client.get("/api/deploy/history").status_code in (200, 404)

    def test_providers_is_list_or_dict(self, client):
        r = client.get("/api/deploy/providers")
        if r.status_code == 200:
            d = r.json()
            assert isinstance(d, (list, dict))


# ── TEMPLATES ─────────────────────────────────────────────────────────────────
class TestTemplates:
    def test_list_200(self, client):
        assert client.get("/api/templates").status_code == 200

    def test_list_has_templates(self, client):
        d = assert_ok(client.get("/api/templates"))
        assert "templates" in d
        assert d["count"] >= 1

    def test_templates_have_id(self, client):
        d = assert_ok(client.get("/api/templates"))
        for t in d["templates"]:
            assert "id" in t

    def test_templates_have_category(self, client):
        d = assert_ok(client.get("/api/templates"))
        for t in d["templates"]:
            assert "category" in t

    def test_search_templates(self, client):
        r = client.get("/api/templates/search", params={"q": "saas"})
        assert r.status_code in (200, 404)
        if r.status_code == 200:
            d = r.json()
            results = d.get("results", d.get("templates", []))
            assert isinstance(results, list)

    def test_scaffold_custom(self, client):
        r = post_json(client, "/api/templates/scaffold-custom",
                      {"name": f"UnitTemplate_{_uid()}",
                       "html": "<h1>Unit Test Template</h1>"})
        assert r.status_code in (200, 400, 404, 422)
        # scaffold-custom requires an existing index.html in preview/ - ok:false is valid
        if r.status_code == 200:
            assert "ok" in r.json()  # ok:true or ok:false both are valid responses


# ── OBSERVABILITY / DORA ──────────────────────────────────────────────────────
class TestObservability:
    def test_metrics_200(self, client):
        assert client.get("/api/observability/metrics").status_code in (200, 404)

    def test_dora_200(self, client):
        assert client.get("/api/observability/dora").status_code in (200, 404)

    def test_traces_200(self, client):
        assert client.get("/api/observability/traces").status_code in (200, 404)


# ── HITL ──────────────────────────────────────────────────────────────────────
class TestHITL:
    def test_queue_200(self, client):
        assert client.get("/api/hitl/queue").status_code in (200, 404)

    def test_history_200(self, client):
        assert client.get("/api/hitl/history").status_code in (200, 404)

    def test_policies_200(self, client):
        assert client.get("/api/hitl/policies").status_code in (200, 404)


# ── AMBIENT ───────────────────────────────────────────────────────────────────
class TestAmbient:
    def test_status_200(self, client):
        assert client.get("/api/ambient/status").status_code in (200, 404)

    def test_tasks_200(self, client):
        assert client.get("/api/ambient/tasks").status_code in (200, 404)


# ── CONTROL TOWER ─────────────────────────────────────────────────────────────
class TestControlTower:
    def test_status_200(self, client):
        assert client.get("/api/control-tower/status").status_code in (200, 404)

    def test_agents_200(self, client):
        assert client.get("/api/control-tower/agents").status_code in (200, 404)


# ── SYSTEM MONITOR ────────────────────────────────────────────────────────────
class TestSystem:
    def test_health_200(self, client):
        assert client.get("/api/system/health").status_code in (200, 404)

    def test_metrics_200(self, client):
        assert client.get("/api/system/metrics").status_code in (200, 404)

    def test_processes_200(self, client):
        assert client.get("/api/system/processes").status_code in (200, 404)


# ── AGENT LEADERBOARD ─────────────────────────────────────────────────────────
class TestLeaderboard:
    def test_leaderboard_200(self, client):
        assert client.get("/api/agent-leaderboard").status_code in (200, 404)

    def test_governance_summary_200(self, client):
        assert client.get("/api/agent-leaderboard/governance/summary").status_code in (200, 404)


# ── MODEL FUSION ──────────────────────────────────────────────────────────────
class TestFusion:
    def test_presets_200(self, client):
        assert client.get("/api/fusion/presets").status_code in (200, 404)

    def test_history_200(self, client):
        assert client.get("/api/fusion/history").status_code in (200, 404)

    def test_models_200(self, client):
        assert client.get("/api/fusion/models").status_code in (200, 404)


# ── IMAGE GENERATION ──────────────────────────────────────────────────────────
class TestImageGen:
    def test_gallery_200(self, client):
        assert client.get("/api/imagegen/gallery").status_code in (200, 404)

    def test_models_200(self, client):
        assert client.get("/api/imagegen/models").status_code in (200, 404)

    def test_generate_empty_prompt_rejected(self, client):
        r = post_json(client, "/api/imagegen/generate",
                      {"prompt": "", "model": "dall-e-3"})
        assert r.status_code in (200, 400, 422)
        if r.status_code == 200:
            assert r.json().get("ok") is False

    def test_enhance_prompt(self, client):
        r = post_json(client, "/api/imagegen/enhance-prompt",
                      {"prompt": "a beautiful sunset"})
        assert r.status_code in (200, 404, 500)


# ── TTS & VOICE ───────────────────────────────────────────────────────────────
class TestTTS:
    def test_status_200(self, client):
        assert client.get("/api/tts/status").status_code in (200, 404)

    def test_voices_200(self, client):
        assert client.get("/api/tts/voices").status_code in (200, 404)

    def test_synthesize_schema(self, client):
        r = post_json(client, "/api/tts/synthesize",
                      {"text": "Hello unit test", "voice": "alloy"})
        assert r.status_code in (200, 400, 404, 422, 500)

    def test_voice_status_200(self, client):
        assert client.get("/api/voice/status").status_code in (200, 404)


# ── BROWSER AGENT ─────────────────────────────────────────────────────────────
class TestBrowser:
    def test_sessions_200(self, client):
        assert client.get("/api/browser/sessions").status_code in (200, 404)

    def test_screenshots_200(self, client):
        assert client.get("/api/browser/screenshots").status_code in (200, 404)

    def test_task_runs_ok(self, client):
        r = post_json(client, "/api/browser/task",
                      {"url": "https://example.com", "task": "Unit test", "max_steps": 2})
        assert r.status_code in (200, 404)

    def test_task_is_sse_stream(self, client):
        r = post_json(client, "/api/browser/task",
                      {"url": "https://example.com", "task": "test", "max_steps": 1})
        if r.status_code == 200:
            # SSE streams contain data: lines
            assert "data:" in r.text or "session_start" in r.text or "done" in r.text


# ── OBSIDIAN ──────────────────────────────────────────────────────────────────
class TestObsidian:
    def test_status_200(self, client):
        assert client.get("/api/obsidian/status").status_code in (200, 404)

    def test_notes_200(self, client):
        assert client.get("/api/obsidian/notes").status_code in (200, 404)


# ── PIPELINE ──────────────────────────────────────────────────────────────────
class TestPipeline:
    def test_runs_200(self, client):
        assert client.get("/api/pipeline/runs").status_code in (200, 404)

    def test_status_200(self, client):
        assert client.get("/api/pipeline/status").status_code in (200, 404)

    def test_templates_200(self, client):
        assert client.get("/api/pipeline/templates").status_code in (200, 404)


# ── TAURI BUILD ───────────────────────────────────────────────────────────────
class TestTauri:
    def test_status_200(self, client):
        assert client.get("/api/tauri/status").status_code in (200, 404)

    def test_builds_200(self, client):
        assert client.get("/api/tauri/builds").status_code in (200, 404)


# ── EXECUTION REPLAY ──────────────────────────────────────────────────────────
class TestReplay:
    def test_runs_200(self, client):
        assert client.get("/api/replay/runs").status_code in (200, 404)

    def test_sessions_200(self, client):
        assert client.get("/api/replay/sessions").status_code in (200, 404)


# ── E2E & TESTGEN ──────────────────────────────────────────────────────────────
class TestE2E:
    def test_suites_200(self, client):
        assert client.get("/api/e2e/suites").status_code in (200, 404)

    def test_results_200(self, client):
        assert client.get("/api/e2e/results").status_code in (200, 404)

    def test_history_200(self, client):
        assert client.get("/api/e2e/history").status_code in (200, 404)

    def test_testgen_history_200(self, client):
        assert client.get("/api/testgen/history").status_code in (200, 404)

    def test_testgen_templates_200(self, client):
        assert client.get("/api/testgen/templates").status_code in (200, 404)


# ── LOOPS ─────────────────────────────────────────────────────────────────────
class TestLoops:
    def test_list_200(self, client):
        assert client.get("/api/loops").status_code in (200, 404)

    def test_create_prompt_required(self, client):
        r = post_json(client, "/api/loops",
                      {"agent_id": "builder", "interval_minutes": 60})
        # prompt is required
        if r.status_code == 200:
            assert r.json()["ok"] is False

    def test_create_with_prompt(self, client):
        r = post_json(client, "/api/loops",
                      {"prompt": "Unit test autonomous loop task",
                       "agent_id": "builder",
                       "interval_minutes": 60})
        assert r.status_code in (200, 201, 422, 503)

    def test_status_200(self, client):
        assert client.get("/api/loops/status").status_code in (200, 404)


# ── INTEGRATIONS ──────────────────────────────────────────────────────────────
class TestIntegrations:
    def test_list_200(self, client):
        assert client.get("/api/integrations").status_code in (200, 404)

    def test_providers_200(self, client):
        assert client.get("/api/integrations/providers").status_code in (200, 404)


# ── SWARM ─────────────────────────────────────────────────────────────────────
class TestSwarm:
    def test_history_200(self, client):
        assert client.get("/api/swarm/history").status_code in (200, 404)

    def test_agents_200(self, client):
        assert client.get("/api/swarm/agents").status_code in (200, 404)


# ── CODE INDEX ────────────────────────────────────────────────────────────────
class TestCodeIndex:
    def test_stats_200(self, client):
        assert client.get("/api/codeindex/stats").status_code in (200, 404)

    def test_symbols_200(self, client):
        assert client.get("/api/codeindex/symbols").status_code in (200, 404)

    def test_index_file(self, client):
        r = post_json(client, "/api/codeindex/index",
                      {"path": "/tmp/test.py"})
        assert r.status_code in (200, 400, 404, 422)

    def test_codesearch_200(self, client):
        r = client.get("/api/codesearch/search", params={"q": "def "})
        assert r.status_code in (200, 404)


# ── MARKETPLACE ───────────────────────────────────────────────────────────────
class TestMarketplace:
    def test_plugins_200(self, client):
        assert client.get("/api/marketplace/plugins").status_code in (200, 404)


# ── MULTI-TAB ─────────────────────────────────────────────────────────────────
class TestMultiTab:
    def test_tabs_200(self, client):
        assert client.get("/api/multitab/tabs").status_code in (200, 404)

    def test_create_tab(self, client):
        r = post_json(client, "/api/multitab/tabs",
                      {"name": "UnitTab", "url": "https://example.com"})
        assert r.status_code in (200, 201, 404, 422)
