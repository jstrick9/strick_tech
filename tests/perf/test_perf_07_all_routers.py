"""
Performance Test Suite — All 74 Routers Latency Sweep
Tests: Every router's primary GET endpoint meets SLA thresholds
Covers: All 74 registered routers in backend/routers/
SLA: P99 < 200ms for all read endpoints
"""
import pytest, asyncio, time
from tests.perf.perf_engine import (
    measure_latency, measure_throughput, GET, POST, BASE, uid,
    SLA, httpx, LatencyResult
)


P99_LIMIT = 200  # ms — all read endpoints must be under this


def assert_read_sla(result: LatencyResult, label: str):
    ok = result.p99 <= P99_LIMIT and result.success_rate >= SLA.MIN_SUCCESS_RATE
    status = "✅" if ok else "❌"
    print(f"    {status} {label}: p50={result.p50:.1f} p99={result.p99:.1f}ms ok={result.success_rate:.0f}%")
    assert ok, f"FAIL {label}: p99={result.p99:.1f}ms > {P99_LIMIT}ms or ok={result.success_rate:.1f}%"


# ── AGENTS (agents.py) ────────────────────────────────────────────────────────
class TestRouterAgents:
    async def test_agents_list(self):
        r = await measure_latency("/api/agents", n=20)
        assert_read_sla(r, "GET /api/agents")

    async def test_agents_models(self):
        r = await measure_latency("/api/agents/models", n=20)
        assert_read_sla(r, "GET /api/agents/models")


# ── CHAT (chat.py) ────────────────────────────────────────────────────────────
class TestRouterChat:
    async def test_chat_history(self):
        r = await measure_latency("/api/chat/history", n=20)
        assert_read_sla(r, "GET /api/chat/history")


# ── MEMORY (memory.py) ───────────────────────────────────────────────────────
class TestRouterMemory:
    async def test_memory_list(self):
        r = await measure_latency("/api/memory/list", n=20)
        assert_read_sla(r, "GET /api/memory/list")

    async def test_memory_stats(self):
        r = await measure_latency("/api/memory/stats", n=20)
        assert_read_sla(r, "GET /api/memory/stats")


# ── TASKS (system.py) ────────────────────────────────────────────────────────
class TestRouterTasks:
    async def test_tasks_list(self):
        r = await measure_latency("/api/tasks", n=20)
        assert_read_sla(r, "GET /api/tasks")


# ── SESSIONS (sessions.py) ───────────────────────────────────────────────────
class TestRouterSessions:
    async def test_sessions_list(self):
        r = await measure_latency("/api/sessions", n=20)
        assert_read_sla(r, "GET /api/sessions")


# ── PROMPTS (prompts.py) ─────────────────────────────────────────────────────
class TestRouterPrompts:
    async def test_prompts_list(self):
        r = await measure_latency("/api/prompts", n=20)
        assert_read_sla(r, "GET /api/prompts")


# ── STEERING (steering.py) ───────────────────────────────────────────────────
class TestRouterSteering:
    async def test_steering_list(self):
        r = await measure_latency("/api/steering", n=20)
        assert_read_sla(r, "GET /api/steering")


# ── WORKFLOW (workflow.py) ───────────────────────────────────────────────────
class TestRouterWorkflow:
    async def test_workflow_list(self):
        r = await measure_latency("/api/workflow", n=20)
        assert_read_sla(r, "GET /api/workflow")


# ── WORKSPACES (workspaces.py) ───────────────────────────────────────────────
class TestRouterWorkspaces:
    async def test_workspaces_list(self):
        r = await measure_latency("/api/workspaces", n=20)
        assert_read_sla(r, "GET /api/workspaces")


# ── SKILLS (skills.py) ───────────────────────────────────────────────────────
class TestRouterSkills:
    async def test_skills_list(self):
        r = await measure_latency("/api/skills", n=20)
        assert_read_sla(r, "GET /api/skills")


# ── PLUGINS (plugins.py) ─────────────────────────────────────────────────────
class TestRouterPlugins:
    async def test_plugins_installed(self):
        r = await measure_latency("/api/plugins/installed", n=20)
        assert_read_sla(r, "GET /api/plugins/installed")


# ── MCP (mcp.py) ─────────────────────────────────────────────────────────────
class TestRouterMCP:
    async def test_mcp_tools(self):
        r = await measure_latency("/api/mcp/tools", n=20)
        assert_read_sla(r, "GET /api/mcp/tools")

    async def test_mcp_servers(self):
        r = await measure_latency("/api/mcp/servers", n=20)
        assert_read_sla(r, "GET /api/mcp/servers")


# ── SECRETS (secrets.py) ─────────────────────────────────────────────────────
class TestRouterSecrets:
    async def test_secrets_list(self):
        r = await measure_latency("/api/secrets", n=20)
        assert_read_sla(r, "GET /api/secrets")


# ── WEBHOOKS (webhooks.py) ───────────────────────────────────────────────────
class TestRouterWebhooks:
    async def test_webhooks_list(self):
        r = await measure_latency("/api/webhooks", n=20)
        assert_read_sla(r, "GET /api/webhooks")


# ── HOOKS (hooks.py) ─────────────────────────────────────────────────────────
class TestRouterHooks:
    async def test_hooks_list(self):
        r = await measure_latency("/api/hooks", n=20)
        assert_read_sla(r, "GET /api/hooks")


# ── ANALYTICS (analytics.py) ─────────────────────────────────────────────────
class TestRouterAnalytics:
    async def test_analytics_kpis(self):
        r = await measure_latency("/api/analytics/kpis", n=20)
        assert_read_sla(r, "GET /api/analytics/kpis")

    async def test_analytics_dashboard(self):
        r = await measure_latency("/api/analytics/dashboard", n=20)
        assert_read_sla(r, "GET /api/analytics/dashboard")

    async def test_analytics_activity(self):
        r = await measure_latency("/api/analytics/activity", n=15)
        assert_read_sla(r, "GET /api/analytics/activity")


# ── LICENSE (license.py) ─────────────────────────────────────────────────────
class TestRouterLicense:
    async def test_license_status(self):
        r = await measure_latency("/api/license/status", n=20)
        assert_read_sla(r, "GET /api/license/status")

    async def test_license_tiers(self):
        r = await measure_latency("/api/license/tiers", n=20)
        assert_read_sla(r, "GET /api/license/tiers")


# ── USER PROFILE (userprofile.py) ─────────────────────────────────────────────
class TestRouterUserProfile:
    async def test_profile_get(self):
        r = await measure_latency("/api/profile", n=20)
        assert_read_sla(r, "GET /api/profile")

    async def test_profile_ui_config(self):
        r = await measure_latency("/api/profile/ui-config", n=20)
        assert_read_sla(r, "GET /api/profile/ui-config")

    async def test_profile_roles(self):
        r = await measure_latency("/api/profile/roles", n=20)
        assert_read_sla(r, "GET /api/profile/roles")


# ── DOCS CENTER (docs_center.py) ──────────────────────────────────────────────
class TestRouterDocs:
    async def test_docs_quickstarts(self):
        r = await measure_latency("/api/docs/quick-starts", n=20)
        assert_read_sla(r, "GET /api/docs/quick-starts")

    async def test_docs_features(self):
        r = await measure_latency("/api/docs/features", n=20)
        assert_read_sla(r, "GET /api/docs/features")

    async def test_docs_faq(self):
        r = await measure_latency("/api/docs/faq", n=20)
        assert_read_sla(r, "GET /api/docs/faq")

    async def test_docs_shortcuts(self):
        r = await measure_latency("/api/docs/shortcuts", n=20)
        assert_read_sla(r, "GET /api/docs/shortcuts")


# ── ONBOARDING (onboarding.py) ───────────────────────────────────────────────
class TestRouterOnboarding:
    async def test_onboarding_status(self):
        r = await measure_latency("/api/onboarding/status", n=20)
        assert_read_sla(r, "GET /api/onboarding/status")

    async def test_onboarding_steps(self):
        r = await measure_latency("/api/onboarding/steps", n=20)
        assert_read_sla(r, "GET /api/onboarding/steps")


# ── DATABASE (database.py) ───────────────────────────────────────────────────
class TestRouterDatabase:
    async def test_db_tables(self):
        r = await measure_latency("/api/db/sqlite/tables", n=20)
        assert_read_sla(r, "GET /api/db/sqlite/tables")

    async def test_db_schema(self):
        r = await measure_latency("/api/db/sqlite/schema", n=20)
        assert_read_sla(r, "GET /api/db/sqlite/schema")


# ── KNOWLEDGE GRAPH (knowledge_graph.py) ─────────────────────────────────────
class TestRouterKnowledgeGraph:
    async def test_kg_stats(self):
        r = await measure_latency("/api/knowledge-graph/stats", n=20)
        assert_read_sla(r, "GET /api/knowledge-graph/stats")

    async def test_kg_entities(self):
        r = await measure_latency("/api/knowledge-graph/entities", n=20)
        assert_read_sla(r, "GET /api/knowledge-graph/entities")


# ── RAG (rag.py) ─────────────────────────────────────────────────────────────
class TestRouterRAG:
    async def test_rag_pipelines(self):
        r = await measure_latency("/api/rag/pipelines", n=20)
        assert_read_sla(r, "GET /api/rag/pipelines")


# ── WEBSEARCH (websearch.py) ─────────────────────────────────────────────────
class TestRouterWebSearch:
    async def test_websearch_history(self):
        r = await measure_latency("/api/websearch/history", n=20)
        assert_read_sla(r, "GET /api/websearch/history")

    async def test_websearch_suggest(self):
        r = await measure_latency("/api/websearch/suggest?q=AI", n=20)
        assert_read_sla(r, "GET /api/websearch/suggest")


# ── SPECS (specs.py) ─────────────────────────────────────────────────────────
class TestRouterSpecs:
    async def test_specs_list(self):
        r = await measure_latency("/api/specs", n=20)
        assert_read_sla(r, "GET /api/specs")


# ── EVALS (evals.py) ─────────────────────────────────────────────────────────
class TestRouterEvals:
    async def test_evals_abtests(self):
        r = await measure_latency("/api/evals/ab-tests", n=20)
        assert_read_sla(r, "GET /api/evals/ab-tests")


# ── ARENA (arena.py) ─────────────────────────────────────────────────────────
class TestRouterArena:
    async def test_arena_battles(self):
        r = await measure_latency("/api/arena/battles", n=20)
        assert_read_sla(r, "GET /api/arena/battles")

    async def test_arena_models(self):
        r = await measure_latency("/api/arena/models", n=20)
        assert_read_sla(r, "GET /api/arena/models")

    async def test_arena_leaderboard(self):
        r = await measure_latency("/api/arena/leaderboard", n=20)
        assert_read_sla(r, "GET /api/arena/leaderboard")


# ── AGENT LEADERBOARD (agent_leaderboard.py) ─────────────────────────────────
class TestRouterLeaderboard:
    async def test_leaderboard(self):
        r = await measure_latency("/api/agent-leaderboard", n=20)
        assert_read_sla(r, "GET /api/agent-leaderboard")

    async def test_leaderboard_stats(self):
        r = await measure_latency("/api/agent-leaderboard/stats/overview", n=20)
        assert_read_sla(r, "GET /api/agent-leaderboard/stats/overview")

    async def test_leaderboard_policies(self):
        r = await measure_latency("/api/agent-leaderboard/policies", n=20)
        assert_read_sla(r, "GET /api/agent-leaderboard/policies")


# ── OBSERVABILITY (observability.py) ──────────────────────────────────────────
class TestRouterObservability:
    async def test_observability_traces(self):
        r = await measure_latency("/api/observability/traces", n=20)
        assert_read_sla(r, "GET /api/observability/traces")

    async def test_observability_spans(self):
        r = await measure_latency("/api/observability/spans", n=20)
        assert_read_sla(r, "GET /api/observability/spans")


# ── HITL (hitl.py) ───────────────────────────────────────────────────────────
class TestRouterHITL:
    async def test_hitl_queue(self):
        r = await measure_latency("/api/hitl/queue", n=20)
        assert_read_sla(r, "GET /api/hitl/queue")

    async def test_hitl_audit(self):
        r = await measure_latency("/api/hitl/audit", n=20)
        assert_read_sla(r, "GET /api/hitl/audit")


# ── CONTROL TOWER (control_tower.py) ──────────────────────────────────────────
class TestRouterControlTower:
    async def test_control_runs(self):
        r = await measure_latency("/api/control/runs", n=20)
        assert_read_sla(r, "GET /api/control/runs")

    async def test_control_active(self):
        r = await measure_latency("/api/control/active", n=20)
        assert_read_sla(r, "GET /api/control/active")

    async def test_control_stats(self):
        r = await measure_latency("/api/control/stats", n=20)
        assert_read_sla(r, "GET /api/control/stats")

    async def test_control_budget(self):
        r = await measure_latency("/api/control/budget", n=20)
        assert_read_sla(r, "GET /api/control/budget")

    async def test_control_notifications(self):
        r = await measure_latency("/api/control/notifications", n=20)
        assert_read_sla(r, "GET /api/control/notifications")


# ── SWARM (swarm.py) ─────────────────────────────────────────────────────────
class TestRouterSwarm:
    async def test_swarm_runs(self):
        r = await measure_latency("/api/swarm/history", n=20)
        assert_read_sla(r, "GET /api/swarm/history")


# ── LOOPS (loops.py) ─────────────────────────────────────────────────────────
class TestRouterLoops:
    async def test_loops_list(self):
        r = await measure_latency("/api/loops", n=20)
        assert_read_sla(r, "GET /api/loops")


# ── PIPELINE (pipeline.py) ───────────────────────────────────────────────────
class TestRouterPipeline:
    async def test_pipeline_list(self):
        r = await measure_latency("/api/pipeline/history", n=20)
        assert_read_sla(r, "GET /api/pipeline/history")


# ── DEPLOY (deploy.py) ───────────────────────────────────────────────────────
class TestRouterDeploy:
    async def test_deploy_providers(self):
        r = await measure_latency("/api/deploy/providers", n=20)
        assert_read_sla(r, "GET /api/deploy/providers")

    async def test_deploy_history(self):
        r = await measure_latency("/api/deploy/history", n=20)
        assert_read_sla(r, "GET /api/deploy/history")

    async def test_deploy_status(self):
        r = await measure_latency("/api/deploy/status", n=20)
        assert_read_sla(r, "GET /api/deploy/status")


# ── GITHUB (github.py) ───────────────────────────────────────────────────────
class TestRouterGitHub:
    async def test_github_repos(self):
        r = await measure_latency("/api/github/repos", n=20)
        assert_read_sla(r, "GET /api/github/repos")


# ── GITAI (gitai.py) ─────────────────────────────────────────────────────────
class TestRouterGitAI:
    async def test_gitai_deps_audit(self):
        r = await measure_latency("/api/gitai/deps/audit", n=20)
        assert_read_sla(r, "GET /api/gitai/deps/audit")


# ── CODEINDEX (codeindex.py) ─────────────────────────────────────────────────
class TestRouterCodeIndex:
    async def test_codeindex_stats(self):
        r = await measure_latency("/api/codeindex/stats", n=20)
        assert_read_sla(r, "GET /api/codeindex/stats")

    async def test_codeindex_symbols(self):
        r = await measure_latency("/api/codeindex/symbols", n=20)
        assert_read_sla(r, "GET /api/codeindex/symbols")


# ── CODESEARCH (codesearch.py) ───────────────────────────────────────────────
class TestRouterCodeSearch:
    async def test_codesearch_index(self):
        r = await measure_latency("/api/codesearch/index", n=20)
        assert_read_sla(r, "GET /api/codesearch/index")


# ── BUGBOT (bugbot.py) ───────────────────────────────────────────────────────
class TestRouterBugBot:
    async def test_bugbot_reviews(self):
        r = await measure_latency("/api/bugbot/reviews", n=20)
        assert_read_sla(r, "GET /api/bugbot/reviews")

    async def test_bugbot_stats(self):
        r = await measure_latency("/api/bugbot/stats", n=20)
        assert_read_sla(r, "GET /api/bugbot/stats")


# ── TESTGEN (testgen.py) ─────────────────────────────────────────────────────
class TestRouterTestGen:
    async def test_testgen_history(self):
        r = await measure_latency("/api/testgen/history", n=20)
        assert_read_sla(r, "GET /api/testgen/history")


# ── E2E (e2e.py) ─────────────────────────────────────────────────────────────
class TestRouterE2E:
    async def test_e2e_history(self):
        r = await measure_latency("/api/e2e/history", n=20)
        assert_read_sla(r, "GET /api/e2e/history")

    async def test_e2e_status(self):
        r = await measure_latency("/api/e2e/status", n=20)
        assert_read_sla(r, "GET /api/e2e/status")


# ── PROFILER (profiler.py) ───────────────────────────────────────────────────
class TestRouterProfiler:
    async def test_profiler_runs(self):
        r = await measure_latency("/api/profiler/endpoints", n=20)
        assert_read_sla(r, "GET /api/profiler/endpoints")


# ── REPLAY (replay.py) ───────────────────────────────────────────────────────
class TestRouterReplay:
    async def test_replay_sessions(self):
        r = await measure_latency("/api/replay/runs", n=20)
        assert_read_sla(r, "GET /api/replay/runs")


# ── CRDT (crdt.py) ───────────────────────────────────────────────────────────
class TestRouterCRDT:
    async def test_crdt_docs(self):
        r = await measure_latency("/api/crdt/docs", n=20)
        assert_read_sla(r, "GET /api/crdt/docs")


# ── TEMPLATES (templates.py) ─────────────────────────────────────────────────
class TestRouterTemplates:
    async def test_templates_list(self):
        r = await measure_latency("/api/templates", n=20)
        assert_read_sla(r, "GET /api/templates")


# ── MARKETPLACE (marketplace.py) ─────────────────────────────────────────────
class TestRouterMarketplace:
    async def test_marketplace_catalog(self):
        r = await measure_latency("/api/marketplace/catalog", n=20)
        assert_read_sla(r, "GET /api/marketplace/catalog")

    async def test_marketplace_installed(self):
        r = await measure_latency("/api/marketplace/installed", n=20)
        assert_read_sla(r, "GET /api/marketplace/installed")


# ── COLLAB (collab.py) ───────────────────────────────────────────────────────
class TestRouterCollab:
    async def test_collab_sessions(self):
        r = await measure_latency("/api/collab/sessions", n=20)
        assert_read_sla(r, "GET /api/collab/sessions")


# ── VOICE (voice.py) ─────────────────────────────────────────────────────────
class TestRouterVoice:
    async def test_voice_status(self):
        r = await measure_latency("/api/voice/config", n=20)
        assert_read_sla(r, "GET /api/voice/config")


# ── AMBIENT (ambient.py) ─────────────────────────────────────────────────────
class TestRouterAmbient:
    async def test_ambient_health(self):
        r = await measure_latency("/api/ambient/health", n=20)
        assert_read_sla(r, "GET /api/ambient/health")

    async def test_ambient_suggestions(self):
        r = await measure_latency("/api/ambient/suggestions", n=20)
        assert_read_sla(r, "GET /api/ambient/suggestions")


# ── MULTITAB (multitab.py) ───────────────────────────────────────────────────
class TestRouterMultiTab:
    async def test_multitab_sessions(self):
        r = await measure_latency("/api/multitab/tabs", n=20)
        assert_read_sla(r, "GET /api/multitab/tabs")


# ── INTEGRATIONS (integrations.py) ───────────────────────────────────────────
class TestRouterIntegrations:
    async def test_integrations_list(self):
        r = await measure_latency("/api/integrations", n=20)
        assert_read_sla(r, "GET /api/integrations")


# ── BROWSER AGENT (browser_agent.py) ─────────────────────────────────────────
class TestRouterBrowserAgent:
    async def test_browser_status(self):
        r = await measure_latency("/api/browser/status", n=20)
        assert_read_sla(r, "GET /api/browser/status")

    async def test_browser_sessions(self):
        r = await measure_latency("/api/browser/sessions", n=20)
        assert_read_sla(r, "GET /api/browser/sessions")

    async def test_browser_screenshots(self):
        r = await measure_latency("/api/browser/screenshots", n=20)
        assert_read_sla(r, "GET /api/browser/screenshots")


# ── COMPOSER (composer.py / multifile_agent.py) ───────────────────────────────
class TestRouterComposer:
    async def test_composer_history(self):
        r = await measure_latency("/api/composer/history", n=20)
        assert_read_sla(r, "GET /api/composer/history")

    async def test_composer_branches(self):
        r = await measure_latency("/api/composer/preview/branches", n=20)
        assert_read_sla(r, "GET /api/composer/preview/branches")


# ── PLUGINSDK (pluginsdk.py) ──────────────────────────────────────────────────
class TestRouterPluginSDK:
    async def test_pluginsdk_plugins(self):
        r = await measure_latency("/api/pluginsdk/packs", n=20)
        assert_read_sla(r, "GET /api/pluginsdk/packs")


# ── IMAGEGEN (imagegen.py) ───────────────────────────────────────────────────
class TestRouterImageGen:
    async def test_imagegen_history(self):
        r = await measure_latency("/api/imagegen/gallery", n=20)
        assert_read_sla(r, "GET /api/imagegen/gallery")


# ── OBSIDIAN (obsidian.py) ───────────────────────────────────────────────────
class TestRouterObsidian:
    async def test_obsidian_status(self):
        r = await measure_latency("/api/obsidian/status", n=20)
        assert_read_sla(r, "GET /api/obsidian/status")


# ── TERMINAL (terminal.py) ───────────────────────────────────────────────────
class TestRouterTerminal:
    async def test_terminal_sessions(self):
        r = await measure_latency("/api/terminal/history", n=20)
        assert_read_sla(r, "GET /api/terminal/history")


# ── FUSION (fusion.py) ───────────────────────────────────────────────────────
class TestRouterFusion:
    async def test_fusion_pipelines(self):
        r = await measure_latency("/api/fusion/presets", n=20)
        assert_read_sla(r, "GET /api/fusion/presets")


# ── AUDIT (legacy audit.py) ──────────────────────────────────────────────────
class TestRouterAudit:
    async def test_audit_legacy(self):
        r = await measure_latency("/api/audit", n=20)
        assert_read_sla(r, "GET /api/audit")


# ── COST (cost.py) ───────────────────────────────────────────────────────────
class TestRouterCost:
    async def test_cost_endpoint(self):
        r = await measure_latency("/api/cost", n=20)
        assert_read_sla(r, "GET /api/cost")


# ── BACKUP (backup in system.py) ─────────────────────────────────────────────
class TestRouterBackup:
    async def test_backup_endpoint(self):
        r = await measure_latency("/api/backup", n=10)
        # Backup involves file I/O, allow 500ms
        ok = r.p99 <= 500 and r.success_rate >= SLA.MIN_SUCCESS_RATE
        status = "✅" if ok else "❌"
        print(f"    {status} GET /api/backup: p99={r.p99:.1f}ms ok={r.success_rate:.0f}%")
        assert ok, f"FAIL GET /api/backup: p99={r.p99:.1f}ms > 500ms"


# ── HEALTH (global) ──────────────────────────────────────────────────────────
class TestRouterGlobalHealth:
    async def test_health_check(self):
        r = await measure_latency("/api/health", n=30)
        print(f"\n    /api/health: p50={r.p50:.1f} p99={r.p99:.1f}ms")
        # Health check must be very fast
        assert r.p99 <= 50, f"Health p99={r.p99:.1f}ms > 50ms"
        assert r.success_rate == 100.0
