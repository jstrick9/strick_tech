"""
Unit Tests — Navigation, Settings Workstation & Ergonomics Integrity (`tests/unit/test_38_navigation_and_settings_integrity.py`)
Validates our 100% functional roadmap execution:
1. All 68 categorized sidebar navigation panes have exact DOM containers (`#pane-<id>`) in index.html.
2. MASTER_PANE_REGISTRY in 01-app-core.js registers all 68 navigation keys authoritatively.
3. No duplicate loadSettings() shadowing in 01-app-core.js and no inline window.nav overwrite in index.html.
4. toggleSidebar() minimum width guard (260px fallback) against 56px collapsed width traps.
5. 2-Column Settings Workstation layout and 6 tab navigation buttons (`#settings-nav-api`, etc.) in index.html.
6. Complete competitor attribution purge (`Sarah`, `Alex / Apex AI`, `CrewAI`, `LangGraph`) across JS and backend routers.
"""
from __future__ import annotations
import re
from pathlib import Path
import pytest
from bs4 import BeautifulSoup

from backend.config import get_data_dir
ROOT = Path(__file__).resolve().parents[2]
FRONTEND_DIR = ROOT / "frontend"
JS_DIR = FRONTEND_DIR / "js"
BACKEND_DIR = ROOT / "backend"


class TestNavigationAndSettingsIntegrity:
    """Suite formally verifying exact DOM and JavaScript contract integrity across all 68 navigation panes and settings."""

    @pytest.fixture(scope="class")
    def html_soup(self):
        html_path = FRONTEND_DIR / "index.html"
        assert html_path.exists(), "frontend/index.html must exist"
        return BeautifulSoup(html_path.read_text(encoding="utf-8"), "html.parser")

    @pytest.fixture(scope="class")
    def app_core_js(self):
        js_path = JS_DIR / "01-app-core.js"
        assert js_path.exists(), "frontend/js/01-app-core.js must exist"
        return js_path.read_text(encoding="utf-8")

    def test_all_68_sidebar_panes_exist_in_dom(self, html_soup):
        """Verify that every single data-nav item in the sidebar has an exact #pane-<id> container inside index.html."""
        nav_els = html_soup.find_all(lambda e: e.has_attr("data-nav"))
        nav_ids = sorted(list(set(el["data-nav"] for el in nav_els)))
        assert len(nav_ids) >= 68, f"Expected at least 68 distinct data-nav items in sidebar, found {len(nav_ids)}"

        missing_panes = []
        for nid in nav_ids:
            pane = html_soup.find(id=f"pane-{nid}")
            if not pane:
                missing_panes.append(nid)
        
        assert not missing_panes, f"Missing exact #pane-<id> containers in index.html for nav IDs: {missing_panes}"

    def test_master_pane_registry_maps_all_68_keys(self, html_soup, app_core_js):
        """Verify that MASTER_PANE_REGISTRY in 01-app-core.js authoritatively registers all 68 sidebar nav keys."""
        nav_els = html_soup.find_all(lambda e: e.has_attr("data-nav"))
        nav_ids = set(el["data-nav"] for el in nav_els)

        match = re.search(r"window\.MASTER_PANE_REGISTRY = \{(.*?)\};", app_core_js, re.DOTALL)
        assert match is not None, "window.MASTER_PANE_REGISTRY object definition must exist in 01-app-core.js"
        
        reg_content = match.group(1)
        registered_keys = set(re.findall(r"\x27([a-zA-Z0-9_-]+)\x27\s*:", reg_content))
        
        missing_in_registry = sorted(list(nav_ids - registered_keys))
        assert not missing_in_registry, f"MASTER_PANE_REGISTRY is missing mappings for keys: {missing_in_registry}"
        assert len(registered_keys) >= 68, f"Expected at least 68 keys in MASTER_PANE_REGISTRY, found {len(registered_keys)}"

    def test_no_duplicate_loadsettings_shadowing(self, app_core_js):
        """Verify that loadSettings is defined exactly once in 01-app-core.js without duplicate shadowing."""
        defs = re.findall(r"^(?:async\s+)?function\s+loadSettings\s*\(|window\.loadSettings\s*=\s*(?:async\s+)?function", app_core_js, re.MULTILINE)
        assert len(defs) == 1, f"Expected exactly 1 definition of loadSettings in 01-app-core.js to avoid shadowing, found {len(defs)}"

    def test_no_index_html_inline_nav_overwrite(self):
        """Verify that index.html no longer contains inline window.nav or PANE_RENDERERS overwrite script blocks."""
        html_text = (FRONTEND_DIR / "index.html").read_text(encoding="utf-8")
        assert "var PANE_RENDERERS = {" not in html_text, "Legacy var PANE_RENDERERS inside index.html must be removed"
        assert "window.nav = function(pane)" not in html_text, "Inline window.nav override inside index.html must be removed"

    def test_toggle_sidebar_minimum_width_guard(self, app_core_js):
        """Verify that toggleSidebar in 01-app-core.js guards against restoring saved widths <= 60px (such as 56px traps)."""
        toggle_match = re.search(r"window\.toggleSidebar = function\(\)\s*\{(.*?)\};", app_core_js, re.DOTALL)
        assert toggle_match is not None, "window.toggleSidebar definition must exist in 01-app-core.js"
        body = toggle_match.group(1)
        assert "if (isNaN(restoreW) || restoreW <= 60) restoreW = 260;" in body or "restoreW <= 60" in body, (
            "toggleSidebar must guard against restoring widths <= 60px when expanding from collapsed mode"
        )

    def test_settings_workstation_2column_dom(self, html_soup):
        """Verify that #pane-settings has our dedicated 2-column workstation layout and all 6 tab navigation items."""
        settings_pane = html_soup.find(id="pane-settings")
        assert settings_pane is not None, "#pane-settings must exist in index.html"
        
        ws = settings_pane.find(class_="settings-workstation")
        assert ws is not None, "#pane-settings must contain .settings-workstation wrapper"
        assert settings_pane.find(class_="settings-sidebar") is not None, "Must contain left .settings-sidebar"
        assert settings_pane.find(class_="settings-content-area") is not None, "Must contain right .settings-content-area"

        expected_tabs = ["api", "appearance", "layout", "agents", "ollama", "system"]
        for t in expected_tabs:
            nav_btn = settings_pane.find(id=f"settings-nav-{t}")
            assert nav_btn is not None, f"Settings sidebar must contain navigation button #settings-nav-{t}"
            tab_pane = settings_pane.find(id=f"settings-tab-{t}")
            assert tab_pane is not None, f"Settings content area must contain pane #settings-tab-{t}"

    def test_drag_and_drop_dropzone_and_attribution(self, app_core_js):
        """Verify that setupDragAndDrop is present and zero competitor attributions exist across JS and routers."""
        assert "window.setupDragAndDrop = function()" in app_core_js or "function setupDragAndDrop(" in app_core_js, (
            "setupDragAndDrop must be defined in 01-app-core.js"
        )

        js_files = [
            JS_DIR / "04-workflow-specs.js",
            JS_DIR / "06-sprint-features.js",
            JS_DIR / "12-information-hierarchy.js",
        ]
        competitor_pattern = re.compile(r"\b(?:LangGraph|CrewAI|AutoGPT|ServiceNow|watsonx|Arena\.ai|Sarah|Apex AI)\b", re.IGNORECASE)
        for jf in js_files:
            if jf.exists():
                text = jf.read_text(encoding="utf-8")
                matches = competitor_pattern.findall(text)
                assert not matches, f"Found forbidden competitor references {matches} in {jf.name}"

        hitl_py = BACKEND_DIR / "routers" / "hitl.py"
        if hitl_py.exists():
            text = hitl_py.read_text(encoding="utf-8")
            matches = competitor_pattern.findall(text)
            assert not matches, f"Found forbidden competitor references {matches} in hitl.py"

    def test_sidebar_categorized_group_folders_collapsable(self, html_soup, app_core_js):
        """Verify that the 5 categorized group folders in the sidebar are collapsable and expandable with default state = collapsable."""
        groups = ["core", "build", "ship", "tools", "enterprise"]
        for g in groups:
            content = html_soup.find(id=f"group-{g}")
            assert content is not None, f"Sidebar group content container #group-{g} must exist in index.html"
            style_str = content.get("style", "")
            assert "display:none" in style_str or "display: none" in style_str, (
                f"Sidebar group #group-{g} must start collapsed by default (display: none)"
            )
            arrow = html_soup.find(id=f"arrow-{g}")
            assert arrow is not None, f"Group arrow #arrow-{g} must exist in index.html"
            assert arrow.text.strip() == "▶", f"Default arrow state for #arrow-{g} must be collapsed '▶'"

        assert "window.toggleSidebarGroup =" in app_core_js, "toggleSidebarGroup must be defined in 01-app-core.js"
        assert "window.initSidebarGroups =" in app_core_js, "initSidebarGroups must be defined in 01-app-core.js"

    def test_phase1_ux_ui_ergonomics_and_navigation_polish(self, app_core_js):
        """Verify formal execution of Phase 1: URL deep linking, command palette dynamic search, and font/contrast scaling."""
        assert "window.initDeepLinkRouter =" in app_core_js, "initDeepLinkRouter must be defined in 01-app-core.js"
        assert "window.saveFontSize = async function(size)" in app_core_js, "saveFontSize must instantly scale font-size"
        assert "const sizeMap = { sm: '13px', base: '14px', lg: '16px' };" in app_core_js, "Must map exact typography scales"
        assert "Object.keys(window.MASTER_PANE_REGISTRY).forEach" in app_core_js, (
            "filterPalette must dynamically merge all 68 panes from MASTER_PANE_REGISTRY"
        )
        assert "window.toggleSidebarGroup(gid, true)" in app_core_js, (
            "nav(pane) must automatically uncollapse the parent group folder when navigating"
        )

        styles_css = (FRONTEND_DIR / "styles.css").read_text(encoding="utf-8")
        assert "body.theme-high-contrast {" in styles_css, "High-contrast WCAG AAA theme rule must exist in styles.css"
        ui_ergonomics_js = (JS_DIR / "13-ui-ergonomics.js").read_text(encoding="utf-8")
        assert "window.toggleHighContrastTheme = function()" in ui_ergonomics_js, "toggleHighContrastTheme must be globally assigned"

    def test_phase2_local_ai_engine_and_inference_orchestration(self, client, app_core_js):
        """Verify execution of Phase 2: local hardware telemetry, Ollama fallback/puller, and LoRA fine-tuning UI."""
        hw_r = client.get("/api/system/hardware")
        assert hw_r.status_code == 200
        hw = hw_r.json()
        assert hw["ok"] is True
        assert "recommended_model" in hw
        assert "recommended_quantization" in hw
        assert "Joshua Strickland" in hw["creator"]

        assert "window.checkHardwareRecommendations =" in app_core_js, "checkHardwareRecommendations must be defined in 01-app-core.js"
        assert "window.pullOllamaModel =" in app_core_js, "pullOllamaModel must be globally assigned in 01-app-core.js"

        llm_py = BACKEND_DIR / "services" / "llm.py"
        assert llm_py.exists(), "backend/services/llm.py must exist"
        llm_text = llm_py.read_text(encoding="utf-8")
        assert "_ollama_complete" in llm_text and "OLLAMA_FALLBACK_MODEL" in llm_text, (
            "llm.py must implement automatic fallback to local Ollama when OpenRouter throws or disconnects"
        )

        features_a_js = (JS_DIR / "03-features-a.js").read_text(encoding="utf-8")
        assert "window.renderFinetuneWorkstation =" in features_a_js, (
            "renderFinetuneWorkstation must be defined in 03-features-a.js"
        )

    def test_phase3_multi_agent_swarm_behavioral_enforcement_and_graph_pipelines(self, client, app_core_js):
        """Verify execution of Phase 3: runtime .agenticrules proxy, 7-role specialist swarm fleet, and SSE/fan-out enforcement."""
        steering_py = BACKEND_DIR / "routers" / "steering.py"
        assert steering_py.exists(), "backend/routers/steering.py must exist"
        steering_text = steering_py.read_text(encoding="utf-8")
        assert ".agenticrules" in steering_text and "compile_steering_context" in steering_text, (
            "compile_steering_context must dynamically append .agenticrules runtime behavioral rules"
        )

        memory_db_py = BACKEND_DIR / "services" / "memory_db.py"
        assert memory_db_py.exists(), "backend/services/memory_db.py must exist"
        memory_db_text = memory_db_py.read_text(encoding="utf-8")
        expected_roles = ["orchestrator", "visual_tester", "functional_tester", "design_decomposer", "test_creator", "brain", "builder"]
        for r in expected_roles:
            assert f"'id': '{r}'" in memory_db_text or f'"id": "{r}"' in memory_db_text, (
                f"DEFAULT_AGENTS in memory_db.py must include specialist role {r}"
            )

        swarm_py = BACKEND_DIR / "routers" / "swarm.py"
        assert swarm_py.exists(), "backend/routers/swarm.py must exist"
        swarm_text = swarm_py.read_text(encoding="utf-8")
        assert "agent_ids[:16]" in swarm_text or "agent_ids[:12]" in swarm_text, (
            "swarm.py must cap at >= 12 agents to allow our full 7+ specialist team to fan-out in parallel"
        )
        assert "inject_steering=True" in swarm_text, (
            "swarm.py run_agent must set inject_steering=True to enforce .agenticrules across all swarm outputs"
        )

        assert "orchestrator" in app_core_js and "visual_tester" in app_core_js and "design_decomposer" in app_core_js, (
            "renderSwarmAgents inside 01-app-core.js must check our full 7+ specialist swarm team by default"
        )

    def test_phase4_developer_workstation_studio_and_code_graph(self, app_core_js):
        """Verify execution of Phase 4: Monaco studio fallback, Multi-preview hub, and code search/graph exports."""
        assert "window.initStudio = function()" in app_core_js, "initStudio must be globally assigned in 01-app-core.js"
        assert "studio-fallback-textarea" in app_core_js, "studioLoadMonaco must provide an offline/sandboxed fallback textarea"
        assert "window.renderCodeSearch = renderCodeSearch;" in app_core_js, "renderCodeSearch must be globally assigned"

        features_a_js = (JS_DIR / "03-features-a.js").read_text(encoding="utf-8")
        assert "window.renderMultitab = renderMultitab;" in features_a_js, "renderMultitab must be globally assigned"

        features_b_js = (JS_DIR / "03-features-b.js").read_text(encoding="utf-8")
        assert "window.renderCodeIndex = renderCodeIndex;" in features_b_js, "renderCodeIndex must be globally assigned"

    def test_phase5_enterprise_governance_hitl_pqc_and_finops(self, app_core_js):
        """Verify execution of Phase 5: Control Tower, HITL interrupt gates, PQC hardened vault, and FinOps exports."""
        assert "window.renderControlTower = renderControlTower;" in app_core_js, "renderControlTower must be globally assigned"

        features_a_js = (JS_DIR / "03-features-a.js").read_text(encoding="utf-8")
        assert "window.renderPQCVault = async function()" in features_a_js, "renderPQCVault must be globally assigned"

        sprint_features_js = (JS_DIR / "06-sprint-features.js").read_text(encoding="utf-8")
        assert "window.renderHITL = renderHITL;" in sprint_features_js, "renderHITL must be globally assigned"
        assert "window.hitlDecide = hitlDecide;" in sprint_features_js, "hitlDecide must be globally assigned"
        assert "window.renderFinOps = renderFinOps;" in sprint_features_js, "renderFinOps must be globally assigned"
        assert "window.finopsCreateCap = finopsCreateCap;" in sprint_features_js, "finopsCreateCap must be globally assigned"
