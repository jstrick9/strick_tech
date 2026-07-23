"""
SYS-01: Platform Bootstrap & Health
SYS-30: Full Platform API Surface Coverage

Black-box: the platform must be reachable, all routes registered,
DB healthy, frontend served, every known endpoint answers without 500.
"""
import pytest, asyncio
from tests.system.conftest import *


class TestSysBootstrap:
    """SYS-01 — Platform starts and every surface is alive."""

    async def test_health_endpoint_ok(self, C):
        r = await GET(C, "/api/health")
        d = must(r, 200, label="health")
        check("ok is True",      d["ok"] is True)
        check("version is 6.0",  d["version"] == "6.0")
        check("service name",    d["service"] == "Agentic OS")

    async def test_frontend_html_served(self, C):
        r = await GET(C, "/")
        check("frontend 200",    r.status_code == 200)
        check("is HTML",         "text/html" in r.headers.get("content-type",""))
        check("has DOCTYPE",     b"<!DOCTYPE" in r.content or b"<html" in r.content)

    async def test_db_tables_exist(self, C):
        """Database Studio proves all core tables are initialized."""
        r = await GET(C, "/api/db/sqlite/tables")
        must(r, 200)
        tables = {t["name"] for t in r.json()}
        for expected in ["tasks","agents","chat_log","memory","webhooks",
                         "steering_files","prompt_library","chat_sessions",
                         "workspaces","specs"]:
            check(f"table '{expected}' exists", expected in tables, tables)

    async def test_seeded_agents_present(self, C):
        """Default agents are seeded on boot."""
        agents = must(await GET(C, "/api/agents"), 200)
        agents = agents if isinstance(agents, list) else agents.get("agents",[])
        names = [a.get("name","").lower() for a in agents]
        check("at least 4 agents seeded", len(agents) >= 4)
        check("builder agent exists", any("builder" in n for n in names))
        check("brain agent exists",   any("brain" in n for n in names))

    async def test_all_agent_fields_present(self, C):
        """Every seeded agent has required fields."""
        agents = must(await GET(C, "/api/agents"), 200)
        agents = agents if isinstance(agents, list) else agents.get("agents",[])
        for a in agents[:5]:
            for field in ["id","name","model","system_prompt"]:
                check(f"agent.{field} present", field in a)

    async def test_license_initialized(self, C):
        """License system initializes with a valid tier on first boot."""
        d = must(await GET(C, "/api/license/status"), 200)
        check("ok true",          d["ok"] is True)
        check("tier is valid",    d["tier"] in ("free","trial","pro","enterprise"))
        check("pane_access dict", isinstance(d.get("pane_access"),dict))

    async def test_profile_initialized_with_defaults(self, C):
        """User profile initializes with all required defaults."""
        d = must(await GET(C, "/api/profile"), 200)
        for f in ["name","role","ui_mode","theme","font_size",
                  "hidden_panes","pinned_panes","notifications"]:
            check(f"profile.{f} present", f in d)
        check("ui_mode valid",  d["ui_mode"] in ("simple","power"))
        check("theme valid",    d["theme"] in ("dark","darker","midnight","ocean","forest"))
        check("font_size valid",d["font_size"] in ("sm","base","lg"))

    async def test_ui_config_boots_coherently(self, C):
        """UI config (used by frontend boot) is coherent."""
        d = must(await GET(C, "/api/profile/ui-config"), 200)
        for f in ["ok","profile","tier","is_trial","ui_mode",
                  "hidden_panes","pinned_panes","onboarding_done"]:
            check(f"ui-config.{f}", f in d)
        check("profile is dict", isinstance(d["profile"], dict))
        check("tier matches license",
              d["tier"] in ("free","trial","pro","enterprise"))

    async def test_openapi_spec_valid(self, C):
        """OpenAPI spec is reachable and lists ≥ 600 routes."""
        r = await GET(C, "/api/openapi.json")
        must(r, 200)
        spec = r.json()
        total = sum(len(v) for v in spec["paths"].values())
        check("≥ 600 routes registered", total >= 600, total)
        check("paths is dict", isinstance(spec["paths"], dict))


class TestSysFullAPISurface:
    """SYS-30 — Every route group responds without 500."""

    async def _check_group(self, C, paths: list[tuple[str,str]]):
        for method, path in paths:
            if method == "GET":
                r = await C.get(path)
            else:
                r = await C.post(path, json={})
            no_server_error(r, f"{method} {path}")

    async def test_core_routes_no_500(self, C):
        await self._check_group(C, [
            ("GET",  "/api/health"),
            ("GET",  "/api/agents"),
            ("GET",  "/api/tasks"),
            ("GET",  "/api/memory/list"),
            ("GET",  "/api/memory/stats"),
            ("GET",  "/api/sessions"),
            ("GET",  "/api/prompts"),
            ("GET",  "/api/templates"),
        ])

    async def test_ai_routes_no_500(self, C):
        await self._check_group(C, [
            ("GET",  "/api/steering"),
            ("GET",  "/api/steering/compiled"),
            ("GET",  "/api/workflow"),
            ("GET",  "/api/specs"),
            ("GET",  "/api/bugbot/reviews"),
            ("GET",  "/api/evals/runs"),
            ("GET",  "/api/evals/summary"),
            ("GET",  "/api/arena/battles"),
            ("GET",  "/api/fusion/presets"),
        ])

    async def test_infrastructure_routes_no_500(self, C):
        await self._check_group(C, [
            ("GET",  "/api/secrets/list"),
            ("GET",  "/api/license/status"),
            ("GET",  "/api/license/tiers"),
            ("GET",  "/api/profile"),
            ("GET",  "/api/profile/roles"),
            ("GET",  "/api/profile/ui-config"),
            ("GET",  "/api/onboarding/status"),
            ("GET",  "/api/workspaces"),
        ])

    async def test_knowledge_routes_no_500(self, C):
        await self._check_group(C, [
            ("GET",  "/api/knowledge-graph/entities"),
            ("GET",  "/api/knowledge-graph/stats"),
            ("GET",  "/api/rag/pipelines"),
            ("GET",  "/api/memory/galaxy"),
            ("GET",  "/api/memory/export"),
            ("GET",  "/api/codeindex/stats"),
            ("GET",  "/api/codeindex/symbols"),
        ])

    async def test_platform_routes_no_500(self, C):
        await self._check_group(C, [
            ("GET",  "/api/plugins/installed"),
            ("GET",  "/api/marketplace/plugins"),
            ("GET",  "/api/pluginsdk/packs"),
            ("GET",  "/api/hooks"),
            ("GET",  "/api/webhooks"),
            ("GET",  "/api/mcp/tools"),
            ("GET",  "/api/skills"),
        ])

    async def test_monitoring_routes_no_500(self, C):
        await self._check_group(C, [
            ("GET",  "/api/profiler/summary"),
            ("GET",  "/api/profiler/flamegraph"),
            ("GET",  "/api/system/health"),
            ("GET",  "/api/system/metrics"),
            ("GET",  "/api/analytics/kpis"),
            ("GET",  "/api/analytics/activity"),
            ("GET",  "/api/agent-leaderboard"),
        ])

    async def test_docs_routes_no_500(self, C):
        await self._check_group(C, [
            ("GET",  "/api/docs/quick-starts"),
            ("GET",  "/api/docs/features"),
            ("GET",  "/api/docs/faq"),
            ("GET",  "/api/docs/shortcuts"),
            ("GET",  "/api/docs/feedback/summary"),
        ])

    async def test_collaboration_routes_no_500(self, C):
        await self._check_group(C, [
            ("GET",  "/api/crdt/docs"),
            ("GET",  "/api/collab/sessions"),
            ("GET",  "/api/replay/runs"),
            ("GET",  "/api/websearch/history"),
        ])

    async def test_parallel_requests_stable(self, C):
        """10 concurrent GETs to different endpoints — all succeed."""
        paths = [
            "/api/health", "/api/agents", "/api/tasks", "/api/memory/list",
            "/api/steering", "/api/workflow", "/api/sessions", "/api/prompts",
            "/api/license/status", "/api/profile",
        ]
        results = await asyncio.gather(*[C.get(p) for p in paths])
        for r, p in zip(results, paths):
            check(f"parallel {p} no 500", r.status_code < 500)
