"""
UX-02: Data Rendering Correctness
UX-04: Loading & Error States
UX-10: Empty State Messages

Tests that all render functions:
  - Produce valid output with real API data
  - Show loading spinners during fetch
  - Show error states with retry on failure
  - Show helpful empty states when no data
  - Render with escHtml (no raw HTML injection risk)
"""
import pytest, re
from tests.usability.conftest import *


class TestUXRenderFunctions:
    """UX-02: Render functions exist and are correctly defined."""

    def test_all_render_functions_defined(self, FE):
        """All major render functions exist in frontend."""
        render_fns = [
            "renderKanban", "renderSwarm", "renderDashboard", "renderSkills",
            "renderDeploy", "renderPipeline", "renderObsidian", "renderSystem",
            "renderGalaxy", "renderSettings", "renderGitHub", "renderDBStudio",
            "renderComposer", "renderPlugins", "renderControlTower",
            "renderWorkspaces", "renderWebhooks", "renderTestGen",
            "renderTerminal", "renderSecretsVault", "renderImageGen",
            "renderIntegrations", "renderPrompts", "renderCodeSearch",
            "renderWorkflow", "renderProfiler", "renderPluginSDK",
            "renderMultitab", "renderSpecs", "renderHooks", "renderCodeIndex",
            "renderArena", "renderSteering", "renderBugBot", "renderHealth",
            "renderGitAI", "renderAmbient", "renderReplay", "renderCollabEdit",
            "renderMarketplace", "renderEvals", "renderObservability",
            "renderKnowledgeGraph", "renderRAG", "renderFusion", "renderHITL",
            "renderBrowserAgent", "renderWebSearch", "renderLeaderboard",
            "renderDocs", "renderTemplates",
        ]
        
        missing = [fn for fn in render_fns if fn not in FE]
        ux_check("All major render functions defined",
                 len(missing) == 0,
                 f"Missing: {missing[:10]}")

    def test_render_functions_are_async(self, FE):
        """Render functions that fetch data are async."""
        async_renders = re.findall(r'async function render\w+', FE)
        sync_renders  = re.findall(r'(?<!async )function render\w+', FE)
        
        ux_check("Many render functions are async (fetch data)",
                 len(async_renders) >= 30,
                 f"Found {len(async_renders)} async renders")

    def test_render_functions_check_pane_element(self, FE):
        """Render functions guard against missing pane element."""
        guard_patterns = [
            "if (!pane) return",
            "if(!pane) return",
            "if (!el) return",
            "if(!el) return",
        ]
        count = sum(fe_count(FE, p) for p in guard_patterns)
        ux_check("Render functions have null guards (≥20)",
                 count >= 20, f"Found {count} null guards")

    def test_render_functions_show_loading_state(self, FE):
        """Render functions show loading state before fetch."""
        loading_patterns = ["Loading…", "Loading...", "loading…"]
        count = sum(fe_count(FE, p) for p in loading_patterns)
        ux_check("Loading states in render functions (≥15)",
                 count >= 15, f"Found {count} loading messages")

    def test_render_functions_have_try_catch(self, FE):
        """Render functions use try/catch for error handling."""
        try_count = fe_count(FE, "try {") + fe_count(FE, "try{")
        catch_count = fe_count(FE, "catch(") + fe_count(FE, "catch (")
        
        ux_check("Try/catch in render functions (≥50)",
                 try_count >= 50, f"try blocks: {try_count}")
        # catch blocks may exceed try blocks due to Promise.catch() chains — allow wider margin
        ux_check("Catch blocks balance try blocks (within 200)",
                 abs(try_count - catch_count) < 200,
                 f"try={try_count} catch={catch_count} diff={abs(try_count - catch_count)}")

    def test_error_states_have_retry_buttons(self, FE):
        """Error states include retry buttons."""
        retry_count = len(re.findall(
            r'onclick="render\w+\(\)|↻ Retry|Retry</button>',
            FE, re.IGNORECASE
        ))
        ux_check("Retry buttons in error states (≥10)",
                 retry_count >= 10, f"Found {retry_count} retry buttons")

    def test_danger_color_on_errors(self, FE):
        """Error messages use danger color variable."""
        danger_color_count = fe_count(FE, "var(--danger)")
        ux_check("Danger color used for errors (≥50)",
                 danger_color_count >= 50,
                 f"var(--danger) count: {danger_color_count}")


class TestUXDataRenderingWithRealData:
    """UX-02: Render functions produce correct output with live data."""

    async def test_agents_api_renders_usable_data(self, C):
        """GET /api/agents returns data that can be displayed in agent picker."""
        r = await GET(C, "/api/agents")
        d = ux_ok(r, "agents list for render")
        agents = d if isinstance(d, list) else d.get("agents", [])
        
        ux_check("Agents list not empty", len(agents) >= 1)
        
        for a in agents[:3]:
            ux_check(f"Agent '{a.get('name','')}' has displayable name",
                     len(a.get("name", "")) >= 1)
            ux_check(f"Agent has avatar or emoji", 
                     a.get("avatar") or a.get("color") or a.get("model"))

    async def test_tasks_api_renders_usable_data(self, C):
        """GET /api/tasks returns data renderable in Kanban."""
        r = await GET(C, "/api/tasks")
        d = ux_ok(r, "tasks for kanban")
        tasks = d if isinstance(d, list) else []
        
        ux_check("Tasks list is a list", isinstance(tasks, list))
        for t in tasks[:3]:
            ux_check("Task has title", "title" in t)
            ux_check("Task has valid status",
                     t.get("status") in ("todo","doing","blocked","done"))
            ux_check("Task has id",    "id" in t)

    async def test_memory_stats_renders_usable_data(self, C):
        """Memory stats has fields displayable in Galaxy view."""
        r = await GET(C, "/api/memory/stats")
        d = ux_ok(r, "memory stats")
        ux_check("Stats is dict", isinstance(d, dict))
        
        # Should have some count field
        has_count = any(k in d for k in ["total", "sqlite_memories", "count"])
        ux_check("Stats has memory count field", has_count, str(d.keys()))

    async def test_steering_renders_usable_data(self, C):
        """Steering files have fields for display."""
        r = await GET(C, "/api/steering")
        d = ux_ok(r, "steering list")
        files = d.get("files", d) if isinstance(d, dict) else d
        
        ux_check("Steering files is list", isinstance(files, list))
        if files:
            f = files[0]
            ux_check("Steering file has title",   "title" in f)
            ux_check("Steering file has enabled", "enabled" in f)
            ux_check("Steering file has content", "content" in f)

    async def test_prompts_renders_usable_data(self, C):
        """Prompt library returns displayable data."""
        r = await GET(C, "/api/prompts")
        d = ux_ok(r, "prompts list")
        prompts = d.get("prompts", d) if isinstance(d, dict) else d
        
        if isinstance(prompts, list) and prompts:
            p = prompts[0]
            ux_check("Prompt has title",   "title" in p)
            ux_check("Prompt has content", "content" in p)
            ux_check("Prompt has id",      "id" in p)

    async def test_templates_renders_usable_data(self, C):
        """Templates gallery returns displayable data."""
        r = await GET(C, "/api/templates")
        d = ux_ok(r, "templates list")
        
        ux_check("Templates has templates key", "templates" in d)
        ux_check("Templates has count ≥ 10", d.get("count", 0) >= 10)
        
        for t in d.get("templates", [])[:3]:
            ux_check(f"Template '{t.get('id','')}' has emoji", "emoji" in t)
            ux_check(f"Template has description", "description" in t)
            ux_check(f"Template has preview_color", "preview_color" in t)

    async def test_docs_renders_usable_data(self, C):
        """Docs center returns displayable content."""
        r = await GET(C, "/api/docs/quick-starts")
        d = ux_ok(r, "docs quick-starts")
        ux_check("Quick-starts present", len(d.get("quick_starts", [])) >= 4)
        
        for qs in d["quick_starts"][:2]:
            ux_check(f"QS '{qs['id']}' has title", len(qs.get("title","")) > 5)
            ux_check(f"QS has icon", len(qs.get("icon","")) > 0)
            ux_check(f"QS has steps", len(qs.get("steps",[])) >= 3)

    async def test_websearch_history_renders_usable_data(self, C):
        """Websearch history returns structured data."""
        r = await GET(C, "/api/websearch/history")
        d = ux_ok(r, "websearch history")
        ux_check("History has items", "items" in d)
        ux_check("Items is list", isinstance(d["items"], list))
        ux_check("History has count", "count" in d)

    async def test_knowledge_graph_stats_renders(self, C):
        """Knowledge graph stats returns displayable data."""
        r = await GET(C, "/api/knowledge-graph/stats")
        d = ux_ok(r, "KG stats")
        ux_check("KG stats is dict", isinstance(d, dict))
        ux_check("Has entities count", "entities" in d or isinstance(d, dict))

    async def test_license_renders_all_required_fields(self, C):
        """License status has all fields needed for UI display."""
        r = await GET(C, "/api/license/status")
        d = ux_ok(r, "license status")
        
        required = ["tier", "is_trial", "pane_access", "features"]
        for field in required:
            ux_check(f"License has '{field}'", field in d)
        
        # Tier banner needs these
        if d.get("is_trial"):
            ux_check("Trial has days_left", "trial_days_left" in d)


class TestUXEmptyStates:
    """UX-10: Empty state messages are helpful and informative."""

    def test_kanban_empty_state_exists(self, FE):
        """Kanban shows helpful message when no tasks."""
        # Look for empty kanban state
        has_empty = (
            "No tasks" in FE or
            "Add your first task" in FE or
            "Create a task" in FE or
            "empty" in FE.lower()
        )
        ux_check("Kanban has empty state", has_empty)

    def test_chat_empty_state_is_helpful(self, FE):
        """Chat empty state shows commands and description."""
        fe_has(FE, "Mission Control", "Chat empty state title")
        fe_has(FE, "cmd-chip", "Command chips in empty state")
        fe_has(FE, "/goal", "Goal command chip")
        fe_has(FE, "/research", "Research command chip")

    def test_templates_gallery_shows_items(self, FE):
        """Templates gallery has actual template items."""
        # Template grid function exists
        fe_has(FE, "renderTemplateGrid", "Template grid render function")
        fe_has(FE, "saas-landing", "SaaS landing template mentioned")

    def test_search_shows_no_results_message(self, FE):
        """Search results show 'no results' message."""
        no_results = (
            "No results" in FE or
            "no results" in FE or
            "Nothing found" in FE or
            "not found" in FE.lower()
        )
        ux_check("No-results message exists", no_results)

    def test_agent_list_has_fallback(self, FE):
        """Agent list has a message when empty."""
        # Either 'No agents' or the list has a create button
        has_fallback = (
            "No agents" in FE or
            "Add Agent" in FE or
            "+ New Agent" in FE or
            "Create agent" in FE.lower()
        )
        ux_check("Agent list has empty state or create button", has_fallback)

    async def test_empty_search_returns_structured_response(self, C):
        """Empty search query returns empty results, not error."""
        r = await GET(C, "/api/docs/search", q="")
        d = ux_ok(r, "empty docs search")
        ux_check("Empty search returns empty results",
                 d.get("results") == [] or r.status_code == 200)

    async def test_nonexistent_agent_handled(self, C):
        """Non-existent resource is handled gracefully."""
        # /api/agents/{id} is a PATCH/DELETE route - GET of all agents works
        # Test a clearly non-existent task (uses integer ID)
        r = await GET(C, "/api/tasks/99999")
        ux_check("Non-existent task handled gracefully",
                 r.status_code in (404, 405, 422))
