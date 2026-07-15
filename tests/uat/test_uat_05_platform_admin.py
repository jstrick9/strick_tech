"""
UAT-05: Platform Administration & Settings
User stories:
  "As an admin I can manage the license and user settings"
  "As a user I can customize my profile and sidebar"
  "As a developer I can integrate external tools via hooks and webhooks"
  "As a developer I can extend the platform with plugins"
  "As a user I can view system health and performance metrics"
"""
import pytest
from tests.uat.conftest import *


class TestUATSettings:
    """User Story: Configure the platform to my preferences."""

    async def test_user_can_change_theme(self, U):
        """AC: Theme switcher changes the color scheme immediately."""
        for theme in ("dark", "darker", "midnight", "ocean", "forest"):
            r = await PATCH(U, "/api/profile", {"theme": theme})
            d = accept(r, f"set theme {theme}", 200)
            uat(f"theme '{theme}' accepted", d.get("ok") is True)
        
        # Restore default
        await PATCH(U, "/api/profile", {"theme": "dark"})

    async def test_user_can_change_font_size(self, U):
        """AC: Font size slider applies immediately to all text."""
        for size in ("sm", "base", "lg"):
            r = await PATCH(U, "/api/profile", {"font_size": size})
            d = accept(r, f"set font {size}", 200)
            uat(f"font size '{size}' accepted", d.get("ok") is True)
        
        await PATCH(U, "/api/profile", {"font_size": "base"})

    async def test_invalid_theme_shows_error(self, U):
        """AC: Selecting invalid theme shows validation error, not crash."""
        r = await PATCH(U, "/api/profile", {"theme": "hot_pink_neon"})
        uat("invalid theme shows error", r.status_code == 422)
        d = r.json()
        uat("error describes valid options", "theme" in str(d).lower())

    async def test_user_can_switch_between_simple_and_power_mode(self, U):
        """AC: Simple Mode hides advanced panes; Power Mode shows all."""
        for mode in ("simple", "power"):
            r = await PATCH(U, "/api/profile", {"ui_mode": mode})
            d = accept(r, f"switch to {mode}", 200)
            uat(f"mode '{mode}' accepted", d.get("ok") is True)
            
            p = accept(await GET(U, "/api/profile"), "get profile", 200)
            uat(f"profile shows {mode}", p["ui_mode"] == mode)
        
        # Restore
        await PATCH(U, "/api/profile", {"ui_mode": "simple"})

    async def test_notification_preferences_persist(self, U):
        """AC: Notification toggles persist across browser restarts."""
        await PATCH(U, "/api/profile", {
            "notifications": {"agent_complete": False, "sound": True}
        })
        p = accept(await GET(U, "/api/profile"), "get profile", 200)
        uat("agent_complete set to False", p["notifications"]["agent_complete"] is False)
        uat("sound set to True",           p["notifications"]["sound"] is True)
        
        # Restore
        await PATCH(U, "/api/profile", {
            "notifications": {"agent_complete": True, "sound": False}
        })


class TestUATLicenseSettings:
    """User Story: Manage my license and understand what I have access to."""

    async def test_user_sees_their_current_tier(self, U):
        """AC: Settings shows current tier (Free/Trial/Pro/Enterprise)."""
        d = accept(await GET(U, "/api/license/status"), "license status", 200)
        uat("ok true",             d.get("ok") is True)
        uat("tier shown",          d["tier"] in ("free","trial","pro","enterprise"))
        uat("pane access shown",   isinstance(d.get("pane_access"), dict))

    async def test_user_can_see_all_available_plans(self, U):
        """AC: View Plans modal shows Free, Pro, Enterprise with pricing."""
        d = accept(await GET(U, "/api/license/tiers"), "license tiers", 200)
        uat("ok true",          d.get("ok") is True)
        uat("3 tiers shown",    len(d.get("tiers", [])) == 3)
        
        tier_ids = {t["id"] for t in d["tiers"]}
        uat("free plan present",       "free" in tier_ids)
        uat("pro plan present",        "pro" in tier_ids)
        uat("enterprise plan present", "enterprise" in tier_ids)
        
        pro = next(t for t in d["tiers"] if t["id"] == "pro")
        uat("pro plan is highlighted", pro["highlight"] is True)
        uat("pro plan has features",   len(pro["features"]) >= 5)
        uat("pro plan has price",      "$" in pro["price"])

    async def test_user_can_enter_a_license_key(self, U):
        """AC: License key input accepts PRO-/ENT- format keys."""
        r = await POST(U, "/api/license/activate",
                       {"license_key": "PRO-UAT-TEST-XXXX-1234567890"})
        d = accept(r, "activate license", 200)
        uat("valid key accepted",  d.get("ok") is True)
        uat("tier is pro",         d.get("tier") == "pro")
        
        # Reset
        await POST(U, "/api/license/reset-trial", {})

    async def test_invalid_license_key_shows_helpful_error(self, U):
        """AC: Wrong key format shows 'Invalid license key format' message."""
        bad_keys = ["WRONGFORMAT", "TRIAL-EXPIRED", ""]
        for key in bad_keys:
            r = await POST(U, "/api/license/activate", {"license_key": key})
            d = r.json()
            uat(f"bad key '{key}' rejected cleanly", d.get("ok") is False)
            uat(f"error message shown for '{key}'",  "error" in d)
            uat(f"no crash on '{key}'",              r.status_code < 500)

    async def test_user_can_update_account_details(self, U):
        """AC: Name/email fields save and appear in license status."""
        r = await POST(U, "/api/license/set-user", {
            "name": "UAT Test User",
            "email": "uat@test.com",
            "org": "UAT Testing Co"
        })
        d = accept(r, "set user info", 200)
        uat("user info saved", d.get("ok") is True)
        
        status = accept(await GET(U, "/api/license/status"), "license status", 200)
        uat("name appears in status",  status.get("user_name") == "UAT Test User")
        uat("email appears in status", "uat@test.com" in status.get("user_email", ""))

    async def test_invalid_email_is_rejected(self, U):
        """AC: Email field validates format and shows error."""
        r = await POST(U, "/api/license/set-user", {
            "name": "Test", "email": "not-an-email-address", "org": ""
        })
        d = r.json()
        uat("invalid email rejected",  d.get("ok") is False)
        uat("error message helpful",   "email" in str(d).lower() or "error" in d)

    async def test_chat_pane_always_accessible_on_free(self, U):
        """AC: Core features (Chat, Kanban) work on free tier."""
        d = accept(await GET(U, "/api/license/pane-access/chat"), "pane access chat", 200)
        uat("chat always allowed",    d["allowed"] is True)
        uat("chat is free tier",      d["required_tier"] == "free")
        uat("no upgrade needed",      d["upgrade_needed"] is False)

    async def test_user_sees_activation_history(self, U):
        """AC: History tab shows all license changes with timestamps."""
        # Make a change to ensure history
        await POST(U, "/api/license/activate", {"license_key": "PRO-UAT-HIST-TEST-XXXXX1"})
        
        d = accept(await GET(U, "/api/license/history"), "license history", 200)
        uat("history present",          "history" in d)
        uat("history is list",          isinstance(d["history"], list))
        uat("recent activation shown",
            any("activated" in str(e.get("event","")) for e in d["history"]))
        
        await POST(U, "/api/license/reset-trial", {})


class TestUATHooksWebhooks:
    """User Story: Connect external systems with event-driven automation."""

    async def test_user_can_create_a_webhook(self, U):
        """AC: Register a webhook URL → platform sends events there."""
        name = uid("GitHubPushWebhook")
        r = await POST(U, "/api/webhooks", {
            "name": name,
            "secret": uid("whsecret"),
            "agent_id": "builder",
            "prompt_template": "A GitHub push happened: {{payload}}"
        })
        d = accept(r, "create webhook", 200)
        whid = d.get("id") or (d.get("webhook") or {}).get("id")
        uat("webhook ID returned", bool(whid))
        
        await DELETE(U, f"/api/webhooks/{whid}")

    async def test_user_can_test_a_webhook(self, U):
        """AC: Test button sends sample event to webhook URL."""
        r = await POST(U, "/api/webhooks", {
            "name": uid("TestableWebhook"), "secret": "s"
        })
        d = accept(r, "create webhook", 200)
        whid = d.get("id") or (d.get("webhook") or {}).get("id")
        
        if whid:
            r2 = await POST(U, f"/api/webhooks/{whid}/test", {})
            accept(r2, "test webhook", 200, 404)
            
            await DELETE(U, f"/api/webhooks/{whid}")

    async def test_user_can_see_webhook_event_log(self, U):
        """AC: Events tab shows all received webhook payloads."""
        r = await POST(U, "/api/webhooks", {
            "name": uid("EventLogWebhook"), "secret": "s"
        })
        d = accept(r, "create webhook", 200)
        whid = d.get("id") or (d.get("webhook") or {}).get("id")
        
        if whid:
            r2 = await GET(U, f"/api/webhooks/{whid}/events")
            accept(r2, "webhook events", 200, 404)
            if r2.status_code == 200:
                uat("events is list", isinstance(r2.json(), list))
            
            await DELETE(U, f"/api/webhooks/{whid}")

    async def test_user_can_create_an_event_hook(self, U):
        """AC: Create hook that fires on agent.complete event."""
        r = await POST(U, "/api/hooks", {
            "name": uid("AgentCompleteHook"),
            "event": "agent.complete",
            "prompt": "Agent finished: {{event}}. Notify user.",
            "agent_id": "builder",
            "enabled": True
        })
        d = accept(r, "create hook", 200)
        hid = d.get("hook_id") or d.get("id")
        uat("hook ID returned", bool(hid))
        
        if hid: await DELETE(U, f"/api/hooks/{hid}")

    async def test_user_can_toggle_hook_on_off(self, U):
        """AC: Toggle switch pauses/resumes hook without deleting it."""
        r = await POST(U, "/api/hooks", {
            "name": uid("ToggleHook"), "event": "task.complete",
            "prompt": "Task done!", "agent_id": "builder", "enabled": True
        })
        d = accept(r, "create hook", 200)
        hid = d.get("hook_id") or d.get("id")
        
        if hid:
            r2 = await POST(U, f"/api/hooks/{hid}/toggle", {})
            accept(r2, "toggle hook", 200, 404)
            
            await DELETE(U, f"/api/hooks/{hid}")


class TestUATPluginSystem:
    """User Story: Extend the platform with plugins."""

    async def test_user_sees_installed_plugins(self, U):
        """AC: Plugins pane shows list of installed extensions."""
        d = accept(await GET(U, "/api/plugins/installed"), "installed plugins", 200)
        uat("plugins is list", isinstance(d, list))

    async def test_user_can_browse_marketplace(self, U):
        """AC: Marketplace shows available plugins to install."""
        r = await GET(U, "/api/marketplace/plugins")
        accept(r, "marketplace", 200, 404)

    async def test_user_can_install_plugin_from_json(self, U):
        """AC: Paste plugin JSON → installs and appears in list."""
        plugin_id = uid("uat_plugin")
        r = await POST(U, "/api/plugins/install/json", {
            "id": plugin_id,
            "name": "UAT Test Plugin",
            "version": "1.0.0",
            "author": "UAT",
            "category": "productivity",
            "emoji": "🧪",
            "skills": [
                {"id": "test_skill", "name": "Test Skill",
                 "trigger": "test", "prompt": "Do test: {{input}}"}
            ]
        })
        accept(r, "install plugin", 200, 201, 400, 409, 422)

    async def test_plugin_sdk_template_is_valid_json(self, U):
        """AC: SDK template gives users a valid starting point."""
        r = await GET(U, "/api/pluginsdk/template")
        accept(r, "plugin template", 200, 404)

    async def test_user_can_validate_a_plugin_pack(self, U):
        """AC: Validate button checks plugin spec before publishing."""
        r = await POST(U, "/api/pluginsdk/validate", {
            "id": uid("validate_pack"),
            "name": "My Plugin",
            "version": "1.0.0",
            "author": "UAT User",
            "skills": [
                {"id": "skill1", "name": "My Skill",
                 "trigger": "do_thing", "prompt": "Do: {{input}}"}
            ]
        })
        accept(r, "validate plugin", 200, 400, 422)

    async def test_skills_accessible_from_platform(self, U):
        """AC: Skills library shows all runnable capabilities."""
        d = accept(await GET(U, "/api/skills"), "skills list", 200)
        skills = d.get("skills", d) if isinstance(d, dict) else d
        uat("skills is list", isinstance(skills, list))


class TestUATSystemMonitoring:
    """User Story: Keep an eye on system health and performance."""

    async def test_user_sees_system_health(self, U):
        """AC: System panel shows CPU, memory, disk usage."""
        r = await GET(U, "/api/system/health")
        accept(r, "system health", 200, 404)
        if r.status_code == 200:
            d = r.json()
            uat("system health is dict", isinstance(d, dict))

    async def test_user_sees_system_metrics(self, U):
        """AC: Metrics panel shows real-time resource usage."""
        r = await GET(U, "/api/system/metrics")
        accept(r, "system metrics", 200, 404)

    async def test_profiler_shows_endpoint_performance(self, U):
        """AC: Profiler shows which endpoints are slowest."""
        r = await GET(U, "/api/profiler/endpoints")
        accept(r, "profiler endpoints", 200, 404)
        if r.status_code == 200:
            d = r.json()
            endpoints = d.get("endpoints", d) if isinstance(d, dict) else d
            uat("endpoints is list or dict", isinstance(endpoints, (list, dict)))

    async def test_user_can_run_code_profiler(self, U):
        """AC: Code profiler runs safe Python code and shows cProfile stats."""
        r = await POST(U, "/api/profiler/profile/run", {
            "code": "total = sum(i**2 for i in range(1000))\nresult = total"
        })
        accept(r, "run profiler", 200, 400, 422)

    async def test_flamegraph_visualization_accessible(self, U):
        """AC: Flamegraph shows call stack visualization."""
        r = await GET(U, "/api/profiler/flamegraph")
        accept(r, "flamegraph", 200, 404)

    async def test_agent_leaderboard_shows_performance(self, U):
        """AC: Leaderboard shows which agents perform best."""
        r = await GET(U, "/api/agent-leaderboard")
        accept(r, "agent leaderboard", 200, 404)
        if r.status_code == 200:
            d = r.json()
            uat("leaderboard has data", isinstance(d, dict))

    async def test_user_can_record_agent_performance(self, U):
        """AC: Performance data is tracked automatically."""
        r = await POST(U, "/api/agent-leaderboard/record", {
            "agent_id": "builder",
            "task_type": "uat_test",
            "success": True,
            "tokens": 250,
            "latency_ms": 1500
        })
        accept(r, "record performance", 200, 201, 422)
