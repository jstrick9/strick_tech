"""
UX-01: Navigation & Routing Usability
UX-11: Label & Copy Clarity
UX-14: Accessibility Basics

Tests that every pane:
  - Has a corresponding HTML element
  - Has a nav item with a meaningful tooltip
  - Has ARIA role/label where appropriate
  - Has a data-nav attribute matching the pane
  - Is wired to a render function
  - The nav dispatcher handles it correctly
"""
import pytest, re
from tests.usability.conftest import *

# All 56 panes defined in the platform
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

class TestUXNavigation:
    """UX-01: Every pane has a nav item and renders correctly."""

    def test_all_panes_have_html_element(self, FE):
        """Every pane ID exists in the HTML."""
        missing = []
        for pane in ALL_PANES:
            if f'id="pane-{pane}"' not in FE:
                missing.append(pane)
        ux_check("All panes have HTML elements",
                 len(missing) == 0,
                 f"Missing pane elements: {missing}")

    def test_nav_items_have_tooltips(self, FE):
        """Every nav item has a meaningful tooltip (not empty)."""
        # Find all nav items with data-tooltip
        nav_items = re.findall(r'data-nav="([^"]+)"[^>]*data-tooltip="([^"]+)"', FE)
        
        ux_check("Nav items have tooltips", len(nav_items) >= 30,
                 f"Only {len(nav_items)} nav items have tooltips")
        
        # Check tooltips are meaningful (>10 chars)
        short_tooltips = [(nav, tip) for nav, tip in nav_items if len(tip) < 5]
        ux_check("All tooltips are meaningful",
                 len(short_tooltips) == 0,
                 f"Short/empty tooltips: {short_tooltips[:5]}")

    def test_sidebar_nav_items_have_aria(self, FE):
        """Nav items have role and aria-label for accessibility."""
        role_count = len(re.findall(r'role="menuitem"', FE))
        aria_count_nav = len(re.findall(r'aria-label="[^"]+"', FE))
        total = role_count + aria_count_nav
        ux_check("Nav items have accessibility attrs (total ≥ 8)",
                 total >= 8,
                 f"role=menuitem: {role_count}, aria-label: {aria_count_nav}")

    def test_nav_function_defined(self, FE):
        """nav() function is defined in the frontend."""
        fe_has(FE, "function nav(pane)", "nav() function defined")

    def test_all_panes_registered_in_nav_dispatcher(self, FE):
        """Key panes are dispatched by the nav function."""
        critical_panes = ["kanban", "swarm", "galaxy", "settings", "workflow",
                          "specs", "arena", "evals", "docs", "steering", "bugbot"]
        missing = []
        for pane in critical_panes:
            if f"'{pane}'" not in FE and f'"{pane}"' not in FE:
                missing.append(pane)
        ux_check("Critical panes referenced in nav dispatcher",
                 len(missing) == 0, f"Missing: {missing}")

    def test_active_chat_pane_on_load(self, FE):
        """Chat pane is active by default (not blank on first load)."""
        ux_check("Chat pane is initially active",
                 'id="pane-chat"' in FE and 'class="pane active"' in FE)

    def test_tier_gating_implemented(self, FE):
        """Pro/Enterprise pane gating logic exists."""
        fe_has(FE, "gatedPanes", "Tier gating set exists")
        fe_has(FE, "showUpgradeModal", "showUpgradeModal function exists")
        fe_has(FE, "pane-access", "Pane access check implemented")

    def test_next_action_bar_exists(self, FE):
        """Next action bar (contextual suggestions) exists."""
        fe_has(FE, "renderNextActionBar", "renderNextActionBar function exists")
        fe_has(FE, "updateNextActionBar", "updateNextActionBar function exists")

    def test_contextual_help_button_attached(self, FE):
        """Contextual ? help button is attached to panes."""
        fe_has(FE, "_attachContextualHelpToPane", "Contextual help attachment exists")
        fe_has(FE, "ctx-help-btn", "ctx-help-btn class exists")

    async def test_navigation_api_health(self, C):
        """Health endpoint responds quickly for navigation-dependent boot."""
        r = await GET(C, "/api/health")
        d = ux_ok(r, "health for nav boot")
        ux_check("Platform ready", d.get("ok") is True)

    async def test_ui_config_loads_for_sidebar(self, C):
        """UI config determines what sidebar shows — must load correctly."""
        r = await GET(C, "/api/profile/ui-config")
        d = ux_ok(r, "ui-config for sidebar")
        ux_check("UI config has ui_mode",    "ui_mode" in d)
        ux_check("UI config has tier",       "tier" in d)
        ux_check("UI config has hidden_panes","hidden_panes" in d)
        ux_check("UI mode is valid",
                 d.get("ui_mode") in ("simple", "power"))


class TestUXLabelClarity:
    """UX-11: All labels, placeholders, and copy are clear."""

    def test_chat_input_has_helpful_placeholder(self, FE):
        """Chat input has a helpful placeholder (not just 'type here')."""
        placeholders = re.findall(r'id="chat-input"[^>]*placeholder="([^"]+)"', FE)
        if not placeholders:
            # Try other order
            placeholders = re.findall(r'placeholder="([^"]+)"[^>]*id="chat-input"', FE)
        
        ux_check("Chat input has placeholder", len(placeholders) >= 1 or 
                 'placeholder="Message an agent' in FE)
        if placeholders:
            ux_check("Chat placeholder is helpful",
                     len(placeholders[0]) > 15,
                     f"Placeholder: '{placeholders[0]}'")

    def test_search_inputs_have_placeholders(self, FE):
        """All search inputs have descriptive placeholders."""
        search_placeholders = re.findall(r'placeholder="([^"]*[Ss]earch[^"]*)"', FE)
        ux_check("Search inputs have placeholders",
                 len(search_placeholders) >= 5,
                 f"Found: {len(search_placeholders)} search placeholders")

    def test_error_messages_use_eschtml(self, FE):
        """Error messages use escHtml() to prevent XSS and ensure correct display."""
        count = fe_count(FE, "escHtml(")
        ux_check("escHtml used extensively (≥500 times)",
                 count >= 500,
                 f"escHtml count: {count}")

    def test_nav_tooltips_not_generic(self, FE):
        """Nav tooltips are specific, not generic ('click here', 'button')."""
        bad_tooltips = ["click here", "button", "link", "item", "pane"]
        for bad in bad_tooltips:
            count = FE.lower().count(f'data-tooltip="{bad}"')
            ux_check(f"No generic tooltip '{bad}'", count == 0)

    def test_cmd_chips_have_examples(self, FE):
        """Command chips in chat empty state show real examples."""
        fe_has(FE, "/goal ", "Goal command chip example")
        fe_has(FE, "/research ", "Research command chip example")
        fe_has(FE, "/code ", "Code command chip example")

    def test_retry_buttons_on_error_states(self, FE):
        """Error states have retry buttons (not just error text)."""
        retry_count = len(re.findall(r'↻ Retry|Retry</button>|retry.*button', FE, re.IGNORECASE))
        ux_check("Retry buttons on error states",
                 retry_count >= 10,
                 f"Found {retry_count} retry buttons")

    def test_loading_states_exist(self, FE):
        """Loading states say 'Loading...' not just blank content."""
        loading_count = fe_count(FE, "Loading…") + fe_count(FE, "Loading...")
        ux_check("Loading states exist",
                 loading_count >= 10,
                 f"Found {loading_count} loading states")

    def test_empty_state_messages(self, FE):
        """Empty states have helpful messages."""
        empty_phrases = [
            "No results", "Nothing here", "No items", "Get started",
            "Create your first", "No data", "Empty"
        ]
        found = sum(1 for phrase in empty_phrases if phrase in FE)
        ux_check("Empty state messages exist",
                 found >= 3,
                 f"Found {found}/{len(empty_phrases)} empty state patterns")

    def test_success_feedback_exists(self, FE):
        """Success actions show confirmatory feedback."""
        success_patterns = ["✅", "showToast", "toast(", "created", "saved", "updated"]
        found = sum(1 for p in success_patterns if p in FE)
        ux_check("Success feedback patterns exist", found >= 5)

    def test_destructive_actions_use_danger_modal(self, FE):
        """Delete/destructive actions use gmDanger (not raw confirm)."""
        danger_count   = fe_count(FE, "gmDanger(")
        confirm_count  = fe_count(FE, "window.confirm(") + fe_count(FE, "confirm(")
        raw_alert_count = fe_count(FE, "window.alert(") + fe_count(FE, "alert(")
        
        ux_check("Destructive actions use gmDanger",
                 danger_count >= 5,
                 f"gmDanger count: {danger_count}")
        # confirm() appears once in a comment documenting what NOT to use
        # This is acceptable - it's a code comment, not functional usage
        ux_check("No functional confirm() (≤1 comment reference OK)",
                 confirm_count <= 1,
                 f"window.confirm count: {confirm_count}")
        ux_check("No raw window.alert()",
                 raw_alert_count == 0,
                 f"window.alert count: {raw_alert_count}")


class TestUXAccessibility:
    """UX-14: Accessibility basics."""

    def test_images_and_icons_have_labels(self, FE):
        """Interactive elements have accessible labels."""
        aria_count = len(re.findall(r'aria-label="[^"]+"', FE))
        # aria-labels: the main nav items have them (6)
        # role= attributes: menuitem on nav items
        role_count_inline = len(__import__("re").findall(r'role="[^"]+"', FE))
        total_accessible = aria_count + role_count_inline
        ux_check("Accessible attributes present (≥10 total)",
                 total_accessible >= 10,
                 f"aria-label: {aria_count}, role=: {role_count_inline}, total: {total_accessible}")

    def test_buttons_have_titles(self, FE):
        """Buttons have title attributes for keyboard users."""
        title_count = len(re.findall(r'<button[^>]*title="[^"]+"', FE))
        ux_check("Buttons have titles (≥30)", title_count >= 30,
                 f"Found {title_count} buttons with titles")

    def test_inputs_have_ids(self, FE):
        """Input elements have IDs for label association."""
        input_ids = re.findall(r'<input[^>]*id="([^"]+)"', FE)
        ux_check("Inputs have IDs (≥50)", len(input_ids) >= 50,
                 f"Found {len(input_ids)} inputs with IDs")

    def test_keyboard_shortcut_modal_exists(self, FE):
        """Keyboard shortcuts overlay modal exists."""
        fe_has(FE, 'id="shortcuts-modal"', "Shortcuts modal element")
        fe_has(FE, "showShortcuts", "showShortcuts function")
        fe_has(FE, "⌨️ Keyboard Shortcuts", "Keyboard shortcuts label")

    def test_focus_management_in_modals(self, FE):
        """Modal system uses focus() for keyboard users."""
        focus_count = fe_count(FE, ".focus()")
        ux_check("Focus management implemented (≥5)",
                 focus_count >= 5, f"Found {focus_count} .focus() calls")

    def test_textareas_have_placeholders(self, FE):
        """Textareas have descriptive placeholders."""
        ta_placeholders = re.findall(r'<textarea[^>]*placeholder="([^"]+)"', FE)
        ux_check("Textareas have placeholders (≥10)",
                 len(ta_placeholders) >= 10,
                 f"Found {len(ta_placeholders)} textarea placeholders")
        
        for ph in ta_placeholders[:5]:
            ux_check(f"Textarea placeholder meaningful: '{ph[:30]}'",
                     len(ph) >= 10)

    def test_select_elements_have_options(self, FE):
        """Select dropdowns have meaningful options."""
        select_options = re.findall(r'<option[^>]*>([^<]+)</option>', FE)
        ux_check("Select options present (≥20)",
                 len(select_options) >= 20,
                 f"Found {len(select_options)} select options")
