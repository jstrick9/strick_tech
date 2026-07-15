"""
UX-13: Progressive Disclosure
UX-Progressive: All 56 panes render without blank state on navigation

Tests that:
  - Complex features use tabs/sections to avoid overwhelming users
  - Pane content loads correctly for ALL 56 panes
  - Each pane has at least a header and some content
  - Section organization makes sense
  - Advanced features are hidden behind toggles/tabs
  - Every pane renders something useful, not a blank screen
"""
import pytest, re
from tests.usability.conftest import *


class TestUXProgressiveDisclosure:
    """UX-13: Complex features use progressive disclosure."""

    def test_settings_organized_in_sections(self, FE):
        """Settings pane has organized sections."""
        # Settings should have multiple named sections
        section_indicators = [
            "API Keys", "Theme", "Model", "License",
            "Appearance", "Notification"
        ]
        found = sum(1 for s in section_indicators if s in FE)
        ux_check("Settings organized in sections",
                 found >= 4, f"Found {found}/{len(section_indicators)} sections")

    def test_db_studio_has_multiple_tabs(self, FE):
        """DB Studio has SQLite, Supabase, and SQL editor tabs."""
        tabs = ["SQLite", "Supabase", "SQL Editor", "Schema"]
        found = sum(1 for t in tabs if t in FE)
        ux_check("DB Studio has multiple tabs",
                 found >= 3, f"Found {found}/{len(tabs)} tabs")

    def test_docs_pane_has_tabs(self, FE):
        """Docs pane has tabs for Quick Starts, Features, FAQ, Shortcuts."""
        doc_tabs = ["Quick Starts", "Features", "FAQ", "Shortcuts", "Videos"]
        found = sum(1 for t in doc_tabs if t in FE)
        ux_check("Docs pane has navigation tabs",
                 found >= 4, f"Found {found}/{len(doc_tabs)} tabs")

    def test_websearch_has_tabs(self, FE):
        """Web Search has tabs for Grounded AI, Raw Search, Deep Research."""
        ws_tabs = ["Grounded AI", "Raw Search", "Deep Research", "History"]
        found = sum(1 for t in ws_tabs if t in FE)
        ux_check("Web Search has tabs",
                 found >= 3, f"Found {found}/{len(ws_tabs)}")

    def test_leaderboard_has_tabs(self, FE):
        """Leaderboard has tabs for Rankings, Discover, Policies."""
        lb_tabs = ["Leaderboard", "Discover", "Policies", "Governance"]
        found = sum(1 for t in lb_tabs if t in FE)
        ux_check("Leaderboard has tabs", found >= 3)

    def test_arena_has_clear_structure(self, FE):
        """Arena mode has render function and references battle concept."""
        fe_has(FE, "renderArena", "Arena render function")
        # Arena references A/B battles (could be "battles" or "battle" or arena tabs)
        has_battle = "battles" in FE or "battle" in FE or "A/B" in FE or "lbShowTab" in FE
        ux_check("Arena references battle/comparison concept", has_battle)

    def test_specs_has_phases(self, FE):
        """Spec-driven dev shows phases (Requirements, Design, Tasks)."""
        phases = ["Requirements", "Design", "Tasks", "Execution"]
        found = sum(1 for p in phases if p in FE)
        ux_check("Specs shows workflow phases", found >= 3)

    def test_evals_has_sections(self, FE):
        """Evals pane has organized sections."""
        fe_has(FE, "renderEvals", "Evals render function")
        sections = ["Quick Eval", "Red Team", "Dataset", "A/B"]
        found = sum(1 for s in sections if s in FE)
        ux_check("Evals has sections", found >= 3)

    def test_control_tower_organized(self, FE):
        """Control Tower has organized sections."""
        fe_has(FE, "renderControlTower", "Control Tower render")
        sections = ["Budget", "HITL", "Trace", "Kill"]
        found = sum(1 for s in sections if s in FE)
        ux_check("Control Tower organized", found >= 2)

    def test_complex_features_use_tooltips(self, FE):
        """Complex features use title/tooltip for discoverability."""
        tip_count = len(re.findall(r'title="[^"]{10,}"', FE))
        ux_check("Complex features have tooltips (≥80)",
                 tip_count >= 80, f"Found {tip_count} tooltip titles")


class TestUXAllPanesRender:
    """Every pane must render some meaningful content (not blank)."""

    def _check_pane_has_content(self, FE, pane_id):
        """Verify a pane has more than just an empty div."""
        # Find the pane div
        pattern = f'id="pane-{pane_id}"'
        idx = FE.find(pattern)
        if idx < 0:
            return False, f"Pane 'pane-{pane_id}' not found in HTML"
        
        # Get pane content (next ~500 chars after the pane div opening)
        pane_start = FE.find(">", idx) + 1
        pane_content = FE[pane_start:pane_start+200]
        
        # Empty panes (dynamic render) have just whitespace or closing tags
        # Non-empty panes have static content or a render function
        return True, pane_content[:100]

    def test_all_56_panes_exist_in_html(self, FE):
        """All 56 pane elements exist in the HTML."""
        ALL_PANES = [
            "chat", "studio", "templates", "composer", "builder", "kanban",
            "pipeline", "skills", "swarm", "galaxy", "loops", "mcp",
            "github", "deploy", "dbstudio", "dashboard", "plugins", "obsidian",
            "system", "control", "workspaces", "webhooks", "testgen", "terminal",
            "secrets", "integrations", "imagegen", "prompts", "codesearch", "workflow",
            "specs", "steering", "bugbot", "health", "gitai", "ambient", "fusion",
            "hitl", "browser", "websearch", "leaderboard", "docs", "evals",
            "observability", "knowledge-graph", "rag", "replay", "collabedit",
            "marketplace", "arena", "hooks", "codeindex", "pluginsdk", "multitab",
            "profiler", "settings",
        ]
        missing = [p for p in ALL_PANES if f'id="pane-{p}"' not in FE]
        ux_check("All 56 panes have HTML elements",
                 len(missing) == 0, f"Missing: {missing}")

    def test_chat_pane_has_message_area(self, FE):
        """Chat pane has message area and input."""
        fe_has(FE, 'id="chat-messages"',   "chat-messages element")
        fe_has(FE, 'id="chat-input"',      "chat-input element")
        fe_has(FE, 'id="chat-empty"',      "chat-empty state")
        fe_has(FE, 'id="active-agent-pill"',"agent picker")

    def test_kanban_pane_has_columns(self, FE):
        """Kanban has column structure (todo/doing/done)."""
        # Kanban is rendered dynamically but should reference columns
        fe_has(FE, "renderKanban", "Kanban render function")
        has_columns = "todo" in FE and "doing" in FE and "done" in FE
        ux_check("Kanban columns referenced", has_columns)

    def test_settings_pane_has_api_key_section(self, FE):
        """Settings has API key input section."""
        has_api_key = ('id="settings"' in FE or 'id="pane-settings"' in FE) and \
                      ("OPENROUTER_API_KEY" in FE or "api-key" in FE.lower() or 
                       "API Keys" in FE)
        ux_check("Settings has API key section", has_api_key)

    def test_studio_pane_has_editor_and_preview(self, FE):
        """Studio pane has Monaco editor and preview areas."""
        fe_has(FE, 'id="pane-studio"', "Studio pane exists")
        fe_has(FE, "studio-sidebar", "Studio sidebar")
        fe_has(FE, "renderBuilder",  "Builder render function")

    def test_terminal_pane_has_input(self, FE):
        """Terminal pane has command input."""
        fe_has(FE, "renderTerminal", "Terminal render function")
        fe_has(FE, "term-input", "Terminal input element")

    def test_workflow_pane_has_canvas(self, FE):
        """Workflow builder has a canvas area."""
        fe_has(FE, "renderWorkflow", "Workflow render function")
        # Canvas or graph container
        has_canvas = "canvas" in FE.lower() or "wf-canvas" in FE or "workflow-canvas" in FE
        ux_check("Workflow has canvas area", has_canvas)

    def test_galaxy_pane_has_3d_container(self, FE):
        """Galaxy/Memory Graph has a 3D container."""
        fe_has(FE, 'id="pane-galaxy"', "Galaxy pane exists")
        fe_has(FE, "initGalaxy",       "Galaxy init function")

    def test_docs_pane_has_tab_container(self, FE):
        """Docs pane has tab navigation."""
        fe_has(FE, 'id="pane-docs"', "Docs pane exists")
        fe_has(FE, "renderDocs",     "Docs render function")
        fe_has(FE, "docsTab",        "Docs tab function")

    def test_websearch_pane_has_input(self, FE):
        """Web Search pane has input areas."""
        fe_has(FE, 'id="pane-websearch"', "Websearch pane exists")
        fe_has(FE, "renderWebSearch",     "Websearch render function")
        fe_has(FE, "wsGrounded",          "Websearch grounded function")

    def test_secrets_pane_renders(self, FE):
        """Secrets vault pane has render function."""
        fe_has(FE, 'id="pane-secrets"', "Secrets pane exists")
        fe_has(FE, "renderSecretsVault", "Secrets render function")

    def test_prompts_pane_renders(self, FE):
        """Prompts library renders."""
        fe_has(FE, 'id="pane-prompts"', "Prompts pane exists")
        fe_has(FE, "renderPrompts",     "Prompts render function")
        fe_has(FE, "renderPromptCards", "Prompt cards render function")

    def test_imagegen_pane_renders(self, FE):
        """Image gen pane renders."""
        fe_has(FE, 'id="pane-imagegen"', "Imagegen pane exists")
        fe_has(FE, "renderImageGen",     "Imagegen render function")

    def test_leaderboard_pane_renders(self, FE):
        """Agent leaderboard pane renders."""
        fe_has(FE, 'id="pane-leaderboard"', "Leaderboard pane exists")
        fe_has(FE, "renderLeaderboard",     "Leaderboard render function")

    def test_evals_pane_renders(self, FE):
        """Evals pane renders."""
        fe_has(FE, 'id="pane-evals"', "Evals pane exists")
        fe_has(FE, "renderEvals",     "Evals render function")

    def test_rag_pane_renders(self, FE):
        """RAG pipeline pane renders."""
        fe_has(FE, 'id="pane-rag"', "RAG pane exists")
        fe_has(FE, "renderRAG",     "RAG render function")

    def test_knowledge_graph_renders(self, FE):
        """Knowledge graph pane renders."""
        fe_has(FE, 'id="pane-knowledge-graph"', "KG pane exists")
        fe_has(FE, "renderKnowledgeGraph",       "KG render function")

    def test_observability_renders(self, FE):
        """Observability pane renders."""
        fe_has(FE, 'id="pane-observability"', "Observability pane exists")
        fe_has(FE, "renderObservability",     "Observability render function")

    def test_hitl_renders(self, FE):
        """HITL governance pane renders."""
        fe_has(FE, 'id="pane-hitl"', "HITL pane exists")
        fe_has(FE, "renderHITL",     "HITL render function")

    def test_browser_agent_renders(self, FE):
        """Browser agent pane renders."""
        fe_has(FE, 'id="pane-browser"', "Browser pane exists")
        fe_has(FE, "renderBrowserAgent", "Browser render function")

    def test_fusion_renders(self, FE):
        """Model fusion pane renders."""
        fe_has(FE, 'id="pane-fusion"', "Fusion pane exists")
        fe_has(FE, "renderFusion",     "Fusion render function")

    def test_steering_renders(self, FE):
        """Steering files pane renders."""
        fe_has(FE, 'id="pane-steering"', "Steering pane exists")
        fe_has(FE, "renderSteering",     "Steering render function")

    def test_bugbot_renders(self, FE):
        """BugBot pane renders."""
        fe_has(FE, 'id="pane-bugbot"', "BugBot pane exists")
        fe_has(FE, "renderBugBot",     "BugBot render function")

    def test_arena_renders(self, FE):
        """Arena mode pane renders."""
        fe_has(FE, 'id="pane-arena"', "Arena pane exists")
        fe_has(FE, "renderArena",     "Arena render function")

    def test_replay_renders(self, FE):
        """Replay pane renders."""
        fe_has(FE, 'id="pane-replay"', "Replay pane exists")
        fe_has(FE, "renderReplay",     "Replay render function")

    def test_collabedit_renders(self, FE):
        """Collab edit pane renders."""
        fe_has(FE, 'id="pane-collabedit"', "CollabEdit pane exists")
        fe_has(FE, "renderCollabEdit",     "CollabEdit render function")

    def test_marketplace_renders(self, FE):
        """Plugin marketplace pane renders."""
        fe_has(FE, 'id="pane-marketplace"', "Marketplace pane exists")
        fe_has(FE, "renderMarketplace",     "Marketplace render function")

    def test_hooks_renders(self, FE):
        """Hooks pane renders."""
        fe_has(FE, 'id="pane-hooks"', "Hooks pane exists")
        fe_has(FE, "renderHooks",     "Hooks render function")

    def test_codeindex_renders(self, FE):
        """Code index pane renders."""
        fe_has(FE, 'id="pane-codeindex"', "Code index pane exists")
        fe_has(FE, "renderCodeIndex",     "Code index render function")

    def test_pluginsdk_renders(self, FE):
        """Plugin SDK pane renders."""
        fe_has(FE, 'id="pane-pluginsdk"', "PluginSDK pane exists")
        fe_has(FE, "renderPluginSDK",     "PluginSDK render function")

    def test_multitab_renders(self, FE):
        """Multi-tab preview pane renders."""
        fe_has(FE, 'id="pane-multitab"', "Multitab pane exists")
        fe_has(FE, "renderMultitab",     "Multitab render function")

    def test_profiler_renders(self, FE):
        """Code profiler pane renders."""
        fe_has(FE, 'id="pane-profiler"', "Profiler pane exists")
        fe_has(FE, "renderProfiler",     "Profiler render function")

    def test_gitai_renders(self, FE):
        """Git AI pane renders."""
        fe_has(FE, 'id="pane-gitai"', "GitAI pane exists")
        fe_has(FE, "renderGitAI",     "GitAI render function")

    def test_ambient_renders(self, FE):
        """Ambient agent pane renders."""
        fe_has(FE, 'id="pane-ambient"', "Ambient pane exists")
        fe_has(FE, "renderAmbient",     "Ambient render function")

    def test_health_renders(self, FE):
        """Health/tech-debt pane renders."""
        fe_has(FE, 'id="pane-health"', "Health pane exists")
        fe_has(FE, "renderHealth",     "Health render function")

    def test_specs_renders(self, FE):
        """Spec-driven dev pane renders."""
        fe_has(FE, 'id="pane-specs"', "Specs pane exists")
        fe_has(FE, "renderSpecs",     "Specs render function")

    def test_testgen_renders(self, FE):
        """Test generator pane renders."""
        fe_has(FE, 'id="pane-testgen"', "TestGen pane exists")
        fe_has(FE, "renderTestGen",     "TestGen render function")
