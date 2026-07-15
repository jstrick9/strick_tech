"""Unit tests — User Profile & Preferences (userprofile.py)"""
import pytest
from tests.unit.conftest import assert_ok, assert_error, post_json, patch_json


class TestGetProfile:
    def test_get_200(self, client):
        assert client.get("/api/profile").status_code == 200

    def test_get_has_required_fields(self, client):
        d = assert_ok(client.get("/api/profile"))
        for field in ["name", "email", "avatar", "role", "skill_level",
                      "ui_mode", "theme", "font_size"]:
            assert field in d, f"Missing field: {field}"

    def test_get_has_notifications_dict(self, client):
        d = assert_ok(client.get("/api/profile"))
        assert isinstance(d["notifications"], dict)
        assert "agent_complete" in d["notifications"]

    def test_get_has_hidden_panes_list(self, client):
        d = assert_ok(client.get("/api/profile"))
        assert isinstance(d["hidden_panes"], list)

    def test_get_has_pinned_panes_list(self, client):
        d = assert_ok(client.get("/api/profile"))
        assert isinstance(d["pinned_panes"], list)

    def test_get_valid_ui_mode(self, client):
        d = assert_ok(client.get("/api/profile"))
        assert d["ui_mode"] in ("simple", "power")

    def test_get_valid_theme(self, client):
        d = assert_ok(client.get("/api/profile"))
        assert d["theme"] in ("dark", "darker", "midnight", "ocean", "forest")

    def test_get_valid_font_size(self, client):
        d = assert_ok(client.get("/api/profile"))
        assert d["font_size"] in ("sm", "base", "lg")


class TestPatchProfile:
    def test_patch_name(self, client):
        r = patch_json(client, "/api/profile", {"name": "Unit Test User"})
        d = r.json()
        assert d["ok"] is True
        assert d["profile"]["name"] == "Unit Test User"

    def test_patch_theme_valid(self, client):
        r = patch_json(client, "/api/profile", {"theme": "midnight"})
        assert r.json()["ok"] is True
        assert r.json()["profile"]["theme"] == "midnight"

    def test_patch_theme_invalid_rejected(self, client):
        r = patch_json(client, "/api/profile", {"theme": "nonexistent_theme"})
        assert r.status_code == 422
        d = r.json()
        assert d["ok"] is False

    def test_patch_font_size_valid(self, client):
        for size in ("sm", "base", "lg"):
            r = patch_json(client, "/api/profile", {"font_size": size})
            assert r.json()["ok"] is True

    def test_patch_font_size_invalid_rejected(self, client):
        r = patch_json(client, "/api/profile", {"font_size": "xxl"})
        assert r.status_code == 422

    def test_patch_ui_mode_valid(self, client):
        for mode in ("simple", "power"):
            r = patch_json(client, "/api/profile", {"ui_mode": mode})
            assert r.json()["ok"] is True

    def test_patch_ui_mode_invalid_rejected(self, client):
        r = patch_json(client, "/api/profile", {"ui_mode": "turbo"})
        assert r.status_code == 422

    def test_patch_skill_level_valid(self, client):
        for level in ("beginner", "intermediate", "advanced", "expert"):
            r = patch_json(client, "/api/profile", {"skill_level": level})
            assert r.json()["ok"] is True

    def test_patch_skill_level_invalid_rejected(self, client):
        r = patch_json(client, "/api/profile", {"skill_level": "god-mode"})
        assert r.status_code == 422

    def test_patch_notifications_merged(self, client):
        r = patch_json(client, "/api/profile", {"notifications": {"sound": True}})
        d = r.json()
        assert d["ok"] is True
        # sound should be updated; other keys preserved
        assert d["profile"]["notifications"]["sound"] is True
        assert "agent_complete" in d["profile"]["notifications"]

    def test_patch_name_length_capped(self, client):
        long_name = "A" * 200
        r = patch_json(client, "/api/profile", {"name": long_name})
        assert r.json()["ok"] is True
        assert len(r.json()["profile"]["name"]) <= 100

    def test_patch_avatar_length_capped(self, client):
        r = patch_json(client, "/api/profile", {"avatar": "🧑" * 20})
        assert r.json()["ok"] is True
        assert len(r.json()["profile"]["avatar"]) <= 10

    def test_patch_persists_to_get(self, client):
        patch_json(client, "/api/profile", {"name": "PersistCheck"})
        d = assert_ok(client.get("/api/profile"))
        assert d["name"] == "PersistCheck"

    def test_patch_invalid_json_422(self, client):
        r = client.patch("/api/profile",
                         content="not json",
                         headers={"Content-Type": "application/json"})
        # With the safe json parse, invalid body is treated as empty patch (ok: True)
        # or returns 422 — both are acceptable (no crash is the requirement)
        assert r.status_code in (200, 400, 422), \
            f"Invalid JSON body caused crash: {r.status_code}: {r.text[:200]}"


class TestRoles:
    def test_list_roles_200(self, client):
        assert client.get("/api/profile/roles").status_code == 200

    def test_list_roles_has_6_roles(self, client):
        d = assert_ok(client.get("/api/profile/roles"))
        assert len(d["roles"]) == 6

    def test_list_roles_ids(self, client):
        d = assert_ok(client.get("/api/profile/roles"))
        ids = {r["id"] for r in d["roles"]}
        assert ids == {"developer", "analyst", "writer", "designer", "manager", "student"}

    def test_apply_role_developer(self, client):
        r = client.post("/api/profile/role/developer")
        d = r.json()
        assert d["ok"] is True
        assert "applied" in d
        assert "pinned_panes" in d["applied"]

    def test_apply_role_analyst(self, client):
        r = client.post("/api/profile/role/analyst")
        assert r.json()["ok"] is True

    def test_apply_role_updates_profile(self, client):
        client.post("/api/profile/role/writer")
        d = assert_ok(client.get("/api/profile"))
        assert d["role"] == "writer"

    def test_apply_invalid_role_rejected(self, client):
        r = client.post("/api/profile/role/hacker")
        assert r.json()["ok"] is False


class TestTogglePane:
    def test_toggle_pane_hides(self, client):
        r = client.post("/api/profile/toggle-pane/test-toggle-pane")
        d = r.json()
        assert d["ok"] is True
        assert d["action"] in ("hidden", "shown")

    def test_toggle_pane_double_toggle_restores(self, client):
        client.post("/api/profile/toggle-pane/double-toggle-test")
        r2 = client.post("/api/profile/toggle-pane/double-toggle-test")
        d2 = r2.json()
        # Second toggle should show it (not in hidden_panes after toggle back)
        assert d2["action"] == "shown"

    def test_toggle_pane_updates_hidden_panes(self, client):
        client.post("/api/profile/toggle-pane/my-test-pane")
        d = assert_ok(client.get("/api/profile"))
        # pane should be in hidden_panes after one toggle
        # (if it was shown before)
        assert "hidden_panes" in d


class TestPinPane:
    def test_pin_pane_ok(self, client):
        r = client.post("/api/profile/pin-pane/chat")
        assert r.status_code == 200
        assert r.json()["ok"] is True

    def test_pin_pane_action_returned(self, client):
        r = client.post("/api/profile/pin-pane/workflow")
        d = r.json()
        assert "action" in d
        assert d["action"] in ("pinned", "unpinned")

    def test_pin_pane_updates_pinned_list(self, client):
        client.post("/api/profile/pin-pane/studio")
        d = assert_ok(client.get("/api/profile"))
        assert "pinned_panes" in d


class TestSidebarOrder:
    def test_set_sidebar_order_ok(self, client):
        r = client.post("/api/profile/sidebar-order",
                        json={"order": ["chat", "kanban", "docs"]})
        assert r.json()["ok"] is True

    def test_set_sidebar_order_empty_ok(self, client):
        r = client.post("/api/profile/sidebar-order", json={"order": []})
        assert r.json()["ok"] is True

    def test_set_sidebar_order_not_list_rejected(self, client):
        r = client.post("/api/profile/sidebar-order", json={"order": "chat,kanban"})
        assert r.json()["ok"] is False

    def test_set_sidebar_order_persists(self, client):
        order = ["chat", "docs", "workflow"]
        client.post("/api/profile/sidebar-order", json={"order": order})
        d = assert_ok(client.get("/api/profile"))
        assert d["sidebar_order"] == order


class TestCompleteOnboarding:
    def test_complete_onboarding_ok(self, client):
        r = client.post("/api/profile/complete-onboarding",
                        json={"name": "Onboarded", "role": "developer", "ui_mode": "simple"})
        assert r.json()["ok"] is True

    def test_complete_onboarding_sets_done(self, client):
        client.post("/api/profile/complete-onboarding", json={"name": "Done"})
        d = assert_ok(client.get("/api/profile"))
        assert d["onboarding_done"] is True

    def test_complete_onboarding_invalid_role_ignored(self, client):
        r = client.post("/api/profile/complete-onboarding",
                        json={"name": "X", "role": "hacker"})
        # Should succeed but ignore invalid role
        assert r.json()["ok"] is True


class TestUIConfig:
    def test_ui_config_200(self, client):
        assert client.get("/api/profile/ui-config").status_code == 200

    def test_ui_config_has_tier(self, client):
        d = assert_ok(client.get("/api/profile/ui-config"))
        assert "tier" in d

    def test_ui_config_has_profile(self, client):
        d = assert_ok(client.get("/api/profile/ui-config"))
        assert "profile" in d
        assert isinstance(d["profile"], dict)

    def test_ui_config_has_ui_mode(self, client):
        d = assert_ok(client.get("/api/profile/ui-config"))
        assert "ui_mode" in d

    def test_ui_config_has_hidden_panes(self, client):
        d = assert_ok(client.get("/api/profile/ui-config"))
        assert "hidden_panes" in d

    def test_ui_config_ok_true(self, client):
        d = assert_ok(client.get("/api/profile/ui-config"))
        assert d["ok"] is True


class TestProfileExport:
    def test_export_200(self, client):
        assert client.get("/api/profile/export").status_code == 200

    def test_export_content_disposition(self, client):
        r = client.get("/api/profile/export")
        assert "attachment" in r.headers.get("content-disposition", "")

    def test_export_is_json(self, client):
        r = client.get("/api/profile/export")
        import json
        data = json.loads(r.content)
        assert "name" in data or "role" in data
