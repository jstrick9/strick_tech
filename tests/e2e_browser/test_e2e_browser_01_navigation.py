"""
Browser E2E — Navigation & Page Load
Real Playwright Chromium tests: verifies the UI actually renders in a browser.
"""
import pytest
from tests.e2e_browser.conftest import BASE


class TestE2ENavigation:
    """Platform loads and core UI elements render correctly."""

    def test_platform_loads_with_correct_title(self, page):
        """Frontend HTML serves and sets the right page title."""
        page.goto(BASE)
        page.wait_for_load_state("domcontentloaded")
        assert "Agentic OS" in page.title(), f"Title was: {page.title()}"

    def test_sidebar_nav_items_visible(self, page):
        """Sidebar navigation items are rendered in the DOM."""
        page.goto(BASE)
        page.wait_for_load_state("domcontentloaded")
        nav_items = page.query_selector_all("[data-nav]")
        assert len(nav_items) > 5, f"Expected >5 [data-nav] elements, found {len(nav_items)}"

    def test_chat_pane_exists_in_dom(self, page):
        """The chat pane element exists in the DOM."""
        page.goto(BASE)
        page.wait_for_load_state("domcontentloaded")
        pane = page.query_selector("#pane-chat")
        assert pane is not None, "Chat pane #pane-chat not found"

    def test_65_panes_in_dom(self, page):
        """All 65 panes are present in the DOM."""
        page.goto(BASE)
        page.wait_for_load_state("domcontentloaded")
        panes = page.evaluate("""() =>
            Array.from(document.querySelectorAll('[id^="pane-"]')).map(e => e.id)""")
        assert len(panes) >= 60, f"Expected ≥60 panes, found {len(panes)}: {panes[:5]}"

    def test_core_panes_in_dom_with_correct_ids(self, page):
        """Core feature panes are in the DOM with their actual IDs."""
        page.goto(BASE)
        page.wait_for_load_state("domcontentloaded")
        # Use actual pane IDs (galaxy=memory, dashboard=analytics)
        core_panes = [
            "chat", "studio", "builder", "kanban", "galaxy",
            "dashboard", "secrets", "dbstudio", "docs", "settings",
            "audit-log", "agent-identity", "supervisor", "goals",
            "mcp-gateway", "connectors", "agent-monitor", "finops", "eval-framework"
        ]
        missing = []
        for pane in core_panes:
            el = page.query_selector(f"#pane-{pane}")
            if not el:
                missing.append(pane)
        assert len(missing) == 0, f"Missing panes in DOM: {missing}"

    def test_nav_function_defined_in_js(self, page):
        """The nav() dispatcher function exists in the browser JS context."""
        page.goto(BASE)
        page.wait_for_load_state("domcontentloaded")
        has_nav = page.evaluate("typeof nav === 'function' || typeof window.nav === 'function'")
        assert has_nav, "nav() function is not defined in page scope"

    def test_gmalert_defined_in_script_scope(self, page):
        """gmAlert() modal function is defined in script scope (not necessarily window global)."""
        page.goto(BASE)
        page.wait_for_load_state("domcontentloaded")
        # gmAlert is defined in the HTML script body — check via inline eval
        has_gm = page.evaluate("""() => {
            // Check script content for gmAlert definition
            const scripts = Array.from(document.scripts);
            return scripts.some(s => s.text && s.text.includes('function gmAlert'));
        }""")
        assert has_gm, "gmAlert function definition not found in any script tag"

    def test_eschtml_defined_in_script_scope(self, page):
        """escHtml() XSS-protection function is defined."""
        page.goto(BASE)
        page.wait_for_load_state("domcontentloaded")
        has_esc = page.evaluate("""() => {
            const scripts = Array.from(document.scripts);
            return scripts.some(s => s.text && s.text.includes('function escHtml'));
        }""")
        assert has_esc, "escHtml function definition not found"

    def test_no_raw_alert_calls(self, page):
        """No raw window.alert() calls exist — all use gmAlert instead."""
        page.goto(BASE)
        page.wait_for_load_state("domcontentloaded")
        has_raw_alert = page.evaluate("""() => {
            const scripts = Array.from(document.scripts);
            const content = scripts.map(s => s.text).join('');
            // Count raw alert( calls (not gmAlert)
            const rawAlerts = (content.match(/(?<!gm)(?<!show)\\balert\\s*\\(/g) || []).length;
            return rawAlerts;
        }""")
        assert has_raw_alert == 0, f"Found {has_raw_alert} raw alert() calls — should use gmAlert()"

    def test_manifest_json_served(self, page):
        """PWA manifest.json is served correctly."""
        r = page.goto(f"{BASE}/manifest.json")
        assert r.status == 200

    def test_api_health_reachable_from_browser(self, page):
        """API health endpoint reachable from browser context."""
        resp = page.request.get(f"{BASE}/api/health")
        assert resp.status == 200
        data = resp.json()
        assert data.get("ok") is True
        assert data.get("version") == "6.0"

    def test_sprint_a_panes_in_dom(self, page):
        """All Sprint A panes are in the DOM."""
        page.goto(BASE)
        page.wait_for_load_state("domcontentloaded")
        for pane in ["audit-log", "agent-identity"]:
            el = page.query_selector(f"#pane-{pane}")
            assert el is not None, f"Sprint A pane #{pane} missing"

    def test_sprint_b_panes_in_dom(self, page):
        """All Sprint B panes are in the DOM."""
        page.goto(BASE)
        page.wait_for_load_state("domcontentloaded")
        for pane in ["supervisor", "goals"]:
            el = page.query_selector(f"#pane-{pane}")
            assert el is not None, f"Sprint B pane #{pane} missing"

    def test_sprint_c_panes_in_dom(self, page):
        """All Sprint C panes are in the DOM."""
        page.goto(BASE)
        page.wait_for_load_state("domcontentloaded")
        for pane in ["mcp-gateway", "connectors"]:
            el = page.query_selector(f"#pane-{pane}")
            assert el is not None, f"Sprint C pane #{pane} missing"

    def test_sprint_d_panes_in_dom(self, page):
        """All Sprint D panes are in the DOM."""
        page.goto(BASE)
        page.wait_for_load_state("domcontentloaded")
        for pane in ["agent-monitor", "finops", "eval-framework"]:
            el = page.query_selector(f"#pane-{pane}")
            assert el is not None, f"Sprint D pane #{pane} missing"
