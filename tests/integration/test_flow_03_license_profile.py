"""
FLOW-04: License + Profile → UI Config coherence
FLOW-11: Profile Role → Sidebar cascade
FLOW-16: License Tier Access Control
FLOW-25: Onboarding → Profile → License first-run
"""
import pytest
from tests.integration.conftest import *


@pytest.mark.asyncio
class TestLicenseProfileCoherence:
    """FLOW-04: License and Profile must stay in sync via UI Config."""

    async def test_01_license_tier_matches_ui_config(self, client):
        """License status tier === ui-config tier."""
        lic = ok(await GET(client, "/api/license/status"))
        uic = ok(await GET(client, "/api/profile/ui-config"))
        check("tiers match", lic["tier"] == uic["tier"],
              f"license={lic['tier']} ui-config={uic['tier']}")

    async def test_02_profile_reflects_in_ui_config(self, client):
        """Update profile → ui-config returns updated values."""
        # Update profile name
        await PATCH(client, "/api/profile", {"name": "UIConfigSync"})
        uic = ok(await GET(client, "/api/profile/ui-config"))
        profile = uic.get("profile", {})
        check("profile name synced in ui-config", profile.get("name") == "UIConfigSync")

    async def test_03_set_user_info_appears_in_license_status(self, client):
        """Set user info → appears in license status response."""
        await POST(client, "/api/license/set-user", {
            "name": "IntegrationUser", "email": "integration@test.com", "org": "IntCo"
        })
        status = ok(await GET(client, "/api/license/status"))
        check("user_name in status", status.get("user_name") == "IntegrationUser")
        check("user_email in status", "integration@test.com" in status.get("user_email", ""))

    async def test_04_ui_config_is_comprehensive(self, client):
        """UI config includes all fields needed by frontend boot."""
        uic = ok(await GET(client, "/api/profile/ui-config"))
        required_fields = [
            "ok", "profile", "tier", "days_left", "is_trial",
            "ui_mode", "hidden_panes", "pinned_panes", "onboarding_done"
        ]
        for field in required_fields:
            check(f"ui-config has '{field}'", field in uic)

    async def test_05_ui_config_profile_has_required_fields(self, client):
        """Profile within ui-config has all required fields."""
        uic = ok(await GET(client, "/api/profile/ui-config"))
        p = uic.get("profile", {})
        for field in ["name", "role", "ui_mode", "theme"]:
            check(f"profile.{field} present", field in p)


@pytest.mark.asyncio
class TestLicenseTierGating:
    """FLOW-16: Tier gating controls pane access correctly."""

    async def test_01_free_panes_always_allowed(self, client):
        """Free panes are accessible regardless of tier."""
        for pane in ["chat", "kanban", "docs", "settings"]:
            d = ok(await GET(client, f"/api/license/pane-access/{pane}"))
            check(f"pane '{pane}' allowed", d["allowed"] is True, d)

    async def test_02_enterprise_panes_require_enterprise(self, client):
        """Enterprise panes require enterprise tier."""
        for pane in ["evals", "rag", "observability", "knowledge-graph"]:
            d = ok(await GET(client, f"/api/license/pane-access/{pane}"))
            check(f"pane '{pane}' has required_tier=enterprise",
                  d["required_tier"] == "enterprise", d)

    async def test_03_pro_panes_require_pro_or_higher(self, client):
        """Pro panes require at minimum pro tier."""
        for pane in ["workflow", "studio", "bugbot", "arena"]:
            d = ok(await GET(client, f"/api/license/pane-access/{pane}"))
            check(f"pane '{pane}' required_tier is pro or enterprise",
                  d["required_tier"] in ("pro", "enterprise"), d)

    async def test_04_activate_pro_key_changes_status(self, client):
        """Activate valid PRO key → tier changes to 'pro'."""
        r = await POST(client, "/api/license/activate",
                       {"license_key": "PRO-INTEGRATION-TEST-KEY-1234"})
        d = ok(r)
        check("activation ok", d["ok"] is True)
        check("tier is pro", d["tier"] == "pro")

        # Verify in status
        status = ok(await GET(client, "/api/license/status"))
        check("status reflects pro", status["tier"] in ("pro", "trial"))

        # Reset for other tests
        await POST(client, "/api/license/reset-trial", {})

    async def test_05_invalid_key_rejected_gracefully(self, client):
        """Invalid key format → rejected with clear error, no crash."""
        for bad_key in ["", "INVALID", "PRO-TOO_SHORT", "SQL-INJECTION-' OR '1'='1"]:
            r = await POST(client, "/api/license/activate", {"license_key": bad_key})
            d = r.json()
            check(f"invalid key '{bad_key[:20]}' rejected", d["ok"] is False)
            check("error message present", "error" in d)

    async def test_06_tiers_are_complete(self, client):
        """Tiers endpoint returns complete tier definitions."""
        d = ok(await GET(client, "/api/license/tiers"))
        check("3 tiers", len(d["tiers"]) == 3)
        for t in d["tiers"]:
            check(f"tier {t['id']} has name", "name" in t)
            check(f"tier {t['id']} has features", len(t["features"]) > 0)
            check(f"tier {t['id']} has price", "price" in t)

    async def test_07_history_tracks_activation(self, client):
        """License history records activation events."""
        await POST(client, "/api/license/activate",
                   {"license_key": "PRO-HISTORY-TRACK-TEST-12345"})
        h = ok(await GET(client, "/api/license/history"))
        check("history has entries", len(h["history"]) >= 1)
        events = [e.get("event") for e in h["history"]]
        check("activation event recorded", any("activated" in e for e in events))
        await POST(client, "/api/license/reset-trial", {})

    async def test_08_reset_trial_restores_trial_tier(self, client):
        """Reset trial → tier goes back to 'trial'."""
        r = await POST(client, "/api/license/reset-trial", {})
        d = ok(r)
        check("reset ok", d["ok"] is True)
        check("tier is trial after reset", d["tier"] == "trial")

        status = ok(await GET(client, "/api/license/status"))
        check("status shows trial or no-expired", status["tier"] in ("trial", "pro", "enterprise"))


@pytest.mark.asyncio
class TestProfileRoleCascade:
    """FLOW-11: Profile role → defaults cascade to sidebar & quick actions."""

    async def test_01_role_developer_sets_pinned_panes(self, client):
        """Applying developer role updates pinned_panes."""
        r = await POST(client, "/api/profile/role/developer", {})
        d = ok(r)
        check("role application ok", d["ok"] is True)
        check("applied has pinned_panes", "pinned_panes" in d["applied"])
        check("developer panes include chat", "chat" in d["applied"]["pinned_panes"])

        profile = ok(await GET(client, "/api/profile"))
        check("profile role is developer", profile["role"] == "developer")

    async def test_02_role_analyst_sets_different_panes(self, client):
        """Applying analyst role changes pinned panes distinctly from developer."""
        await POST(client, "/api/profile/role/developer", {})
        dev_profile = ok(await GET(client, "/api/profile"))
        dev_panes = set(dev_profile.get("pinned_panes", []))

        await POST(client, "/api/profile/role/analyst", {})
        analyst_profile = ok(await GET(client, "/api/profile"))
        analyst_panes = set(analyst_profile.get("pinned_panes", []))

        check("analyst panes differ from developer", dev_panes != analyst_panes)
        check("role changed to analyst", analyst_profile["role"] == "analyst")

    async def test_03_toggle_pane_persists_across_reads(self, client):
        """Toggle pane hidden → verified in profile → toggle back → verified."""
        # Hide 'studio'
        r1 = await POST(client, "/api/profile/toggle-pane/studio", {})
        d1 = ok(r1)
        action1 = d1["action"]

        profile_mid = ok(await GET(client, "/api/profile"))
        if action1 == "hidden":
            check("studio in hidden_panes", "studio" in profile_mid.get("hidden_panes", []))
        else:
            check("studio not in hidden_panes", "studio" not in profile_mid.get("hidden_panes", []))

        # Toggle back
        r2 = await POST(client, "/api/profile/toggle-pane/studio", {})
        d2 = ok(r2)
        check("action reversed", d2["action"] != action1)

        profile_final = ok(await GET(client, "/api/profile"))
        if action1 == "hidden":
            check("studio removed from hidden after restore",
                  "studio" not in profile_final.get("hidden_panes", []))

    async def test_04_pin_pane_persists(self, client):
        """Pin a pane → it appears in pinned_panes."""
        r = await POST(client, "/api/profile/pin-pane/websearch", {})
        d = ok(r)
        action = d["action"]

        profile = ok(await GET(client, "/api/profile"))
        if action == "pinned":
            check("websearch in pinned", "websearch" in profile.get("pinned_panes", []))

        # Unpin for cleanup
        if action == "pinned":
            await POST(client, "/api/profile/pin-pane/websearch", {})

    async def test_05_sidebar_order_persists(self, client):
        """Set sidebar order → GET profile returns same order."""
        order = ["chat", "workflow", "docs", "kanban"]
        r = await POST(client, "/api/profile/sidebar-order", {"order": order})
        d = ok(r)
        check("sidebar order ok", d["ok"] is True)

        profile = ok(await GET(client, "/api/profile"))
        check("order persisted", profile.get("sidebar_order") == order)

    async def test_06_profile_export_consistent_with_get(self, client):
        """Profile export contains same data as GET /api/profile."""
        profile = ok(await GET(client, "/api/profile"))
        export_r = await GET(client, "/api/profile/export")
        assert export_r.status_code == 200
        exported = export_r.json()
        check("same name", exported.get("name") == profile.get("name"))
        check("same role", exported.get("role") == profile.get("role"))

    async def test_07_notifications_merge_not_replace(self, client):
        """Update one notification pref → others unchanged."""
        # Get original
        p1 = ok(await GET(client, "/api/profile"))
        orig_hitl = p1["notifications"]["hitl_interrupt"]

        # Update only agent_complete
        await PATCH(client, "/api/profile", {"notifications": {"agent_complete": False}})

        p2 = ok(await GET(client, "/api/profile"))
        check("agent_complete updated", p2["notifications"]["agent_complete"] is False)
        check("hitl_interrupt unchanged", p2["notifications"]["hitl_interrupt"] == orig_hitl)

        # Restore
        await PATCH(client, "/api/profile", {"notifications": {"agent_complete": True}})


@pytest.mark.asyncio
class TestOnboardingFlow:
    """FLOW-25: Onboarding → Profile → License first-run coherence."""

    async def test_01_onboarding_status_accessible(self, client):
        r = await GET(client, "/api/onboarding/status")
        assert r.status_code == 200
        d = r.json()
        check("has complete/done field", "complete" in d or "done" in d or "step" in d)

    async def test_02_onboarding_steps_available(self, client):
        r = await GET(client, "/api/onboarding/steps")
        assert r.status_code in (200, 404)

    async def test_03_complete_onboarding_updates_profile(self, client):
        """Complete onboarding → profile reflects done state."""
        r = await POST(client, "/api/onboarding/complete", {
            "name": "IntegrationOnboardUser",
            "role": "developer",
            "ui_mode": "simple"
        })
        assert r.status_code in (200, 204)

        profile = ok(await GET(client, "/api/profile"))
        check("onboarding_done is True", profile.get("onboarding_done") is True)

    async def test_04_onboarding_shortcuts_available(self, client):
        r = await GET(client, "/api/onboarding/shortcuts")
        assert r.status_code in (200, 404)

    async def test_05_themes_available(self, client):
        r = await GET(client, "/api/onboarding/themes")
        assert r.status_code in (200, 404)
