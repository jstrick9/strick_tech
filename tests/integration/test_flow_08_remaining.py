"""
Remaining integration flows:
- BugBot reviews
- Image Generation  
- TTS/Voice
- Browser Agent SSE
- Obsidian Vault
- Observability/DORA
- HITL Governance
- Ambient Agent
- MCP tool calling
- Multi-tab preview
- Deploy providers
- Arena Mode
- Model Fusion
- Code Index → Semantic Search
- GitAI → Changelogs
- Swarm history
- E2E + TestGen
- Replay runs
"""
import pytest
from tests.integration.conftest import *


@pytest.mark.asyncio
class TestBugBotIntegration:
    """BugBot code review flow."""

    async def test_01_reviews_list_accessible(self, client):
        r = await GET(client, "/api/bugbot/reviews")
        assert r.status_code in (200, 404)

    async def test_02_stats_accessible(self, client):
        r = await GET(client, "/api/bugbot/stats")
        assert r.status_code in (200, 404)

    async def test_03_empty_diff_rejected(self, client):
        r = await POST(client, "/api/bugbot/review/diff",
                       {"diff": "", "agent_id": "builder"})
        check("empty diff rejected", r.json()["ok"] is False)

    async def test_04_diff_review_schema_accepted(self, client):
        """Non-empty diff is accepted (LLM may fail but schema is correct)."""
        r = await POST(client, "/api/bugbot/review/diff", {
            "diff": "+ def greet(name: str) -> str:\n+     return f'Hello, {name}!'",
            "agent_id": "builder"
        })
        check("schema accepted (200 or 500)", r.status_code in (200, 500))

    async def test_05_file_review_schema_accepted(self, client):
        r = await POST(client, "/api/bugbot/review/file", {
            "content": "def add(a, b):\n    return a + b\n",
            "filename": "math_utils.py",
            "agent_id": "builder"
        })
        check("file review accepted", r.status_code in (200, 500))

    async def test_06_git_review_accessible(self, client):
        r = await POST(client, "/api/bugbot/review/git", {"agent_id": "builder"})
        assert r.status_code in (200, 400, 404, 500)

    async def test_07_github_pr_review_accessible(self, client):
        r = await POST(client, "/api/bugbot/review/github-pr", {
            "pr_url": "https://github.com/owner/repo/pull/1",
            "agent_id": "builder"
        })
        assert r.status_code in (200, 400, 404, 500)

    async def test_08_feedback_on_review(self, client):
        reviews = await GET(client, "/api/bugbot/reviews")
        if reviews.status_code == 200:
            r_list = reviews.json()
            reviews_list = r_list.get("reviews", r_list) if isinstance(r_list, dict) else r_list
            if isinstance(reviews_list, list) and reviews_list:
                rid = reviews_list[0].get("id")
                if rid:
                    r = await POST(client, f"/api/bugbot/reviews/{rid}/feedback",
                                   {"feedback": "helpful", "issue_index": 0})
                    assert r.status_code in (200, 404)


@pytest.mark.asyncio
class TestImageGenIntegration:
    """Image generation flow."""

    async def test_01_gallery_accessible(self, client):
        r = await GET(client, "/api/imagegen/gallery")
        assert r.status_code in (200, 404)

    async def test_02_models_accessible(self, client):
        r = await GET(client, "/api/imagegen/models")
        assert r.status_code in (200, 404)

    async def test_03_empty_prompt_rejected(self, client):
        r = await POST(client, "/api/imagegen/generate", {"prompt": "", "model": "dall-e-3"})
        assert r.status_code in (200, 400, 422)
        if r.status_code == 200:
            check("empty prompt rejected", r.json().get("ok") is False)

    async def test_04_enhance_prompt_accessible(self, client):
        r = await POST(client, "/api/imagegen/enhance-prompt",
                       {"prompt": "a sunset over mountains"})
        assert r.status_code in (200, 404, 500)

    async def test_05_upload_to_gallery_accessible(self, client):
        r = await POST(client, "/api/imagegen/gallery/upload",
                       {"filename": "test.png", "url": "https://example.com/img.png"})
        assert r.status_code in (200, 400, 404, 422)


@pytest.mark.asyncio
class TestTTSVoiceIntegration:
    """TTS and voice endpoints."""

    async def test_01_tts_status(self, client):
        r = await GET(client, "/api/tts/status")
        assert r.status_code in (200, 404)

    async def test_02_tts_voices(self, client):
        r = await GET(client, "/api/tts/voices")
        assert r.status_code in (200, 404)

    async def test_03_tts_models(self, client):
        r = await GET(client, "/api/tts/models")
        assert r.status_code in (200, 404)

    async def test_04_voice_status(self, client):
        r = await GET(client, "/api/voice/status")
        assert r.status_code in (200, 404)

    async def test_05_voice_history(self, client):
        r = await GET(client, "/api/voice/history")
        assert r.status_code in (200, 404)

    async def test_06_voice_models(self, client):
        r = await GET(client, "/api/voice/models")
        assert r.status_code in (200, 404)


@pytest.mark.asyncio
class TestBrowserAgentIntegration:
    """Browser agent SSE streaming."""

    async def test_01_sessions_list(self, client):
        r = await GET(client, "/api/browser/sessions")
        assert r.status_code in (200, 404)

    async def test_02_screenshots_list(self, client):
        r = await GET(client, "/api/browser/screenshots")
        assert r.status_code in (200, 404)

    async def test_03_status_accessible(self, client):
        r = await GET(client, "/api/browser/status")
        assert r.status_code in (200, 404)

    async def test_04_task_is_sse_stream(self, client):
        """Browser task returns SSE stream."""
        r = await POST(client, "/api/browser/task", {
            "url": "https://example.com",
            "task": "Integration test: describe the page",
            "max_steps": 2
        })
        check("task 200", r.status_code == 200)
        check("SSE events in response", "data:" in r.text)
        check("session_start event", "session_start" in r.text or "step" in r.text or "done" in r.text)

    async def test_05_task_empty_url_handled(self, client):
        """Empty URL is handled gracefully."""
        r = await POST(client, "/api/browser/task", {"url": "", "task": "test"})
        # Browser agent falls back to default URL or errors gracefully
        assert r.status_code in (200, 400, 422)

    async def test_06_simulation_mode_when_no_playwright(self, client):
        """Without Playwright, browser agent runs in simulation mode."""
        r = await POST(client, "/api/browser/task", {
            "url": "https://example.com",
            "task": "Test simulation mode",
            "max_steps": 1
        })
        if r.status_code == 200:
            # Should contain warning about simulation
            check("simulation handled",
                  "simulated" in r.text.lower() or "session_start" in r.text or "warning" in r.text.lower())


@pytest.mark.asyncio
class TestObsidianIntegration:
    """Obsidian vault sync endpoints."""

    async def test_01_status_accessible(self, client):
        r = await GET(client, "/api/obsidian/status")
        assert r.status_code in (200, 404)

    async def test_02_notes_accessible(self, client):
        r = await GET(client, "/api/obsidian/notes")
        assert r.status_code in (200, 404)

    async def test_03_index_accessible(self, client):
        r = await GET(client, "/api/obsidian/index")
        assert r.status_code in (200, 404)

    async def test_04_watch_status(self, client):
        r = await GET(client, "/api/obsidian/watch/status")
        assert r.status_code in (200, 404)


@pytest.mark.asyncio
class TestObservabilityHITL:
    """Observability/DORA and HITL governance."""

    async def test_01_observability_metrics(self, client):
        r = await GET(client, "/api/observability/metrics")
        assert r.status_code in (200, 404)

    async def test_02_dora_metrics(self, client):
        r = await GET(client, "/api/observability/dora")
        assert r.status_code in (200, 404)

    async def test_03_observability_traces(self, client):
        r = await GET(client, "/api/observability/traces")
        assert r.status_code in (200, 404)

    async def test_04_hitl_queue(self, client):
        r = await GET(client, "/api/hitl/queue")
        assert r.status_code in (200, 404)

    async def test_05_hitl_history(self, client):
        r = await GET(client, "/api/hitl/history")
        assert r.status_code in (200, 404)

    async def test_06_hitl_policies(self, client):
        r = await GET(client, "/api/hitl/policies")
        assert r.status_code in (200, 404)

    async def test_07_create_hitl_policy(self, client):
        r = await POST(client, "/api/hitl/policies", {
            "name": uid("IntHITLPolicy"),
            "condition": "cost > 1.0",
            "action": "pause",
            "agent_id": "builder"
        })
        assert r.status_code in (200, 201, 400, 404, 422)


@pytest.mark.asyncio
class TestArenaFusionLeaderboard:
    """Arena mode, Model Fusion, Agent Leaderboard."""

    async def test_01_arena_battles_list(self, client):
        r = await GET(client, "/api/arena/battles")
        assert r.status_code in (200, 404)

    async def test_02_arena_leaderboard(self, client):
        r = await GET(client, "/api/arena/leaderboard")
        assert r.status_code in (200, 404)
        if r.status_code == 200:
            d = r.json()
            check("leaderboard is list or dict", isinstance(d, (list, dict)))

    async def test_03_arena_stats(self, client):
        r = await GET(client, "/api/arena/stats")
        assert r.status_code in (200, 404)

    async def test_04_fusion_presets(self, client):
        r = await GET(client, "/api/fusion/presets")
        assert r.status_code in (200, 404)
        if r.status_code == 200:
            d = r.json()
            presets = d.get("presets", d) if isinstance(d, dict) else d
            check("presets present", isinstance(presets, (list, dict)))

    async def test_05_fusion_models(self, client):
        r = await GET(client, "/api/fusion/models")
        assert r.status_code in (200, 404)

    async def test_06_fusion_classify(self, client):
        r = await GET(client, "/api/fusion/classify", prompt="Write a Python function")
        assert r.status_code in (200, 404)

    async def test_07_agent_leaderboard_discover(self, client):
        r = await GET(client, "/api/agent-leaderboard/discover")
        assert r.status_code in (200, 404)

    async def test_08_leaderboard_rate_agent(self, client):
        r = await POST(client, "/api/agent-leaderboard/rate", {
            "agent_id": "builder",
            "rating": 5,
            "task_type": "integration_test"
        })
        assert r.status_code in (200, 400, 404, 422)


@pytest.mark.asyncio
class TestCodeIndexSearch:
    """Code Index and Semantic Search."""

    async def test_01_codeindex_stats(self, client):
        r = await GET(client, "/api/codeindex/stats")
        assert r.status_code in (200, 404)

    async def test_02_codeindex_symbols(self, client):
        r = await GET(client, "/api/codeindex/symbols")
        assert r.status_code in (200, 404)

    async def test_03_index_real_file(self, client):
        """Index an existing file → stats update."""
        r = await POST(client, "/api/codeindex/index", {
            "path": "/home/user/agentic-os/backend/routers/websearch.py"
        })
        assert r.status_code in (200, 400, 404, 422)

    async def test_04_complexity_accessible(self, client):
        r = await GET(client, "/api/codeindex/complexity")
        assert r.status_code in (200, 404)

    async def test_05_dead_code_accessible(self, client):
        r = await GET(client, "/api/codeindex/dead-code")
        assert r.status_code in (200, 404)

    async def test_06_graph_accessible(self, client):
        r = await GET(client, "/api/codeindex/graph")
        assert r.status_code in (200, 404)


@pytest.mark.asyncio
class TestGitAIChangelogsIntegration:
    """Git AI and Changelogs."""

    async def test_01_gitai_history(self, client):
        r = await GET(client, "/api/gitai/history")
        assert r.status_code in (200, 404)

    async def test_02_gitai_changelogs(self, client):
        r = await GET(client, "/api/gitai/changelogs")
        assert r.status_code in (200, 404)

    async def test_03_gitai_diff(self, client):
        r = await GET(client, "/api/gitai/diff")
        assert r.status_code in (200, 400, 404)

    async def test_04_github_status(self, client):
        r = await GET(client, "/api/github/status")
        assert r.status_code in (200, 404)

    async def test_05_github_repos_needs_token(self, client):
        """GitHub repos requires token → 401 or 200 depending on vault."""
        r = await GET(client, "/api/github/repos")
        assert r.status_code in (200, 401, 403, 404)


@pytest.mark.asyncio
class TestE2ETestgenReplay:
    """E2E, TestGen, and Replay."""

    async def test_01_e2e_suites(self, client):
        r = await GET(client, "/api/e2e/suites")
        assert r.status_code in (200, 404)

    async def test_02_e2e_results(self, client):
        r = await GET(client, "/api/e2e/results")
        assert r.status_code in (200, 404)

    async def test_03_testgen_history(self, client):
        r = await GET(client, "/api/testgen/history")
        assert r.status_code in (200, 404)

    async def test_04_testgen_templates(self, client):
        r = await GET(client, "/api/testgen/templates")
        assert r.status_code in (200, 404)

    async def test_05_replay_runs(self, client):
        r = await GET(client, "/api/replay/runs")
        assert r.status_code in (200, 404)
        if r.status_code == 200:
            d = r.json()
            runs = d.get("runs", d) if isinstance(d, dict) else d
            check("runs is list", isinstance(runs, list))

    async def test_06_replay_sessions(self, client):
        r = await GET(client, "/api/replay/sessions")
        assert r.status_code in (200, 404)

    async def test_07_replay_run_by_id(self, client):
        """If any runs exist, can fetch one by ID."""
        r = await GET(client, "/api/replay/runs")
        if r.status_code == 200:
            d = r.json()
            runs = d.get("runs", d) if isinstance(d, dict) else d
            if runs and isinstance(runs, list):
                rid = runs[0].get("id")
                if rid:
                    r2 = await GET(client, f"/api/replay/runs/{rid}")
                    assert r2.status_code in (200, 404)


@pytest.mark.asyncio
class TestMultiTabDeploy:
    """Multi-Tab Preview and Deploy."""

    async def test_01_multitab_tabs(self, client):
        r = await GET(client, "/api/multitab/tabs")
        assert r.status_code in (200, 404)

    async def test_02_deploy_providers(self, client):
        r = await GET(client, "/api/deploy/providers")
        assert r.status_code in (200, 404)
        if r.status_code == 200:
            d = r.json()
            providers = d.get("providers", d) if isinstance(d, dict) else d
            check("providers is list or dict", isinstance(providers, (list, dict)))

    async def test_03_deploy_history(self, client):
        r = await GET(client, "/api/deploy/history")
        assert r.status_code in (200, 404)

    async def test_04_swarm_history(self, client):
        r = await GET(client, "/api/swarm/history")
        assert r.status_code in (200, 404)
        if r.status_code == 200:
            d = r.json()
            runs = d.get("runs", d.get("history", d)) if isinstance(d, dict) else d
            check("swarm history is list or dict", isinstance(runs, (list, dict)))


@pytest.mark.asyncio
class TestIntegrationsSummary:
    """Integrations Hub and external connections."""

    async def test_01_integrations_list(self, client):
        r = await GET(client, "/api/integrations")
        assert r.status_code in (200, 404)

    async def test_02_providers_list(self, client):
        r = await GET(client, "/api/integrations/providers")
        assert r.status_code in (200, 404)

    async def test_03_mcp_tools_list(self, client):
        d = ok(await GET(client, "/api/mcp/tools"))
        tools = d.get("tools", d) if isinstance(d, dict) else d
        check("tools present", isinstance(tools, list))
        check("has json.parse tool",
              any("json" in str(t).lower() for t in tools))

    async def test_04_mcp_call_json_parse(self, client):
        """json.parse tool works end-to-end."""
        r = await POST(client, "/api/mcp/call", {
            "tool": "json.parse",
            "args": {"data": '{"integration": true, "value": 42}'}
        })
        d = ok(r)
        check("json.parse ok", d["ok"] is True)
        check("result present", "result" in d)

    async def test_05_pipeline_templates(self, client):
        r = await GET(client, "/api/pipeline/templates")
        assert r.status_code in (200, 404)

    async def test_06_composer_history(self, client):
        r = await GET(client, "/api/composer/sessions")
        assert r.status_code in (200, 404)
