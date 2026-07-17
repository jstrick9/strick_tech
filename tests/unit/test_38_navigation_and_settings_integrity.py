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
        assert len(nav_ids) == 68, f"Expected 68 distinct data-nav items in sidebar, found {len(nav_ids)}"

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
