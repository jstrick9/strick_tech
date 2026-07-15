"""Unit tests — License / Tier System (license.py)"""
import json, time, pytest
from pathlib import Path
from unittest.mock import patch, mock_open
from tests.unit.conftest import assert_ok, assert_error, post_json


class TestLicenseStatus:
    def test_status_200(self, client):
        assert client.get("/api/license/status").status_code == 200

    def test_status_ok_true(self, client):
        d = assert_ok(client.get("/api/license/status"))
        assert d["ok"] is True

    def test_status_has_tier(self, client):
        d = assert_ok(client.get("/api/license/status"))
        assert "tier" in d
        assert d["tier"] in ("free", "trial", "pro", "enterprise")

    def test_status_has_pane_access_map(self, client):
        d = assert_ok(client.get("/api/license/status"))
        assert "pane_access" in d
        assert isinstance(d["pane_access"], dict)
        assert "chat" in d["pane_access"]

    def test_status_has_is_trial(self, client):
        d = assert_ok(client.get("/api/license/status"))
        assert "is_trial" in d

    def test_status_trial_has_days_left(self, client):
        d = assert_ok(client.get("/api/license/status"))
        if d["is_trial"]:
            assert "trial_days_left" in d
            assert isinstance(d["trial_days_left"], int)

    def test_status_has_features_list(self, client):
        d = assert_ok(client.get("/api/license/status"))
        assert "features" in d

    def test_status_chat_always_allowed(self, client):
        d = assert_ok(client.get("/api/license/status"))
        # chat is free tier so always allowed during trial/pro/enterprise
        assert d["pane_access"].get("chat") is True


class TestLicenseTiers:
    def test_tiers_200(self, client):
        assert client.get("/api/license/tiers").status_code == 200

    def test_tiers_ok_true(self, client):
        d = assert_ok(client.get("/api/license/tiers"))
        assert d["ok"] is True

    def test_tiers_has_3_tiers(self, client):
        d = assert_ok(client.get("/api/license/tiers"))
        assert len(d["tiers"]) == 3

    def test_tiers_ids_correct(self, client):
        d = assert_ok(client.get("/api/license/tiers"))
        ids = {t["id"] for t in d["tiers"]}
        assert ids == {"free", "pro", "enterprise"}

    def test_tiers_pro_is_highlighted(self, client):
        d = assert_ok(client.get("/api/license/tiers"))
        pro = next(t for t in d["tiers"] if t["id"] == "pro")
        assert pro["highlight"] is True

    def test_tiers_each_has_features(self, client):
        d = assert_ok(client.get("/api/license/tiers"))
        for tier in d["tiers"]:
            assert "features" in tier
            assert isinstance(tier["features"], list)
            assert len(tier["features"]) > 0

    def test_tiers_each_has_price(self, client):
        d = assert_ok(client.get("/api/license/tiers"))
        for tier in d["tiers"]:
            assert "price" in tier


class TestPaneAccess:
    def test_pane_access_200(self, client):
        assert client.get("/api/license/pane-access/chat").status_code == 200

    def test_pane_access_chat_allowed(self, client):
        d = assert_ok(client.get("/api/license/pane-access/chat"))
        assert d["allowed"] is True
        assert d["required_tier"] == "free"

    def test_pane_access_has_upgrade_needed(self, client):
        d = assert_ok(client.get("/api/license/pane-access/chat"))
        assert "upgrade_needed" in d

    def test_pane_access_evals_enterprise(self, client):
        d = assert_ok(client.get("/api/license/pane-access/evals"))
        assert d["required_tier"] == "enterprise"

    def test_pane_access_unknown_pane_defaults_pro(self, client):
        d = assert_ok(client.get("/api/license/pane-access/totally_unknown_pane"))
        assert d["required_tier"] == "pro"

    def test_pane_access_ok_field_present(self, client):
        d = assert_ok(client.get("/api/license/pane-access/workflow"))
        assert "ok" in d


class TestLicenseActivate:
    def test_activate_invalid_key_rejected(self, client):
        r = post_json(client, "/api/license/activate", {"license_key": "INVALID"})
        d = r.json()
        assert d["ok"] is False

    def test_activate_empty_key_rejected(self, client):
        r = post_json(client, "/api/license/activate", {"license_key": ""})
        d = r.json()
        assert d["ok"] is False

    def test_activate_short_pro_key_rejected(self, client):
        r = post_json(client, "/api/license/activate", {"license_key": "PRO-SHORT"})
        d = r.json()
        assert d["ok"] is False

    def test_activate_valid_pro_key(self, client):
        r = post_json(client, "/api/license/activate", {"license_key": "PRO-UNIT-TEST-KEY-12345"})
        d = r.json()
        assert d["ok"] is True
        assert d["tier"] == "pro"

    def test_activate_valid_ent_key(self, client):
        r = post_json(client, "/api/license/activate", {"license_key": "ENT-UNIT-TEST-KEY-12345"})
        d = r.json()
        assert d["ok"] is True
        assert d["tier"] == "enterprise"

    def test_activate_missing_body_field(self, client):
        r = post_json(client, "/api/license/activate", {})
        assert r.json()["ok"] is False

    def test_activate_no_body_graceful(self, client):
        r = client.post("/api/license/activate",
                        content="not json",
                        headers={"Content-Type": "application/json"})
        # Should return ok:false not 500
        assert r.status_code in (200, 422)
        if r.status_code == 200:
            assert r.json()["ok"] is False


class TestSetUser:
    def test_set_user_ok(self, client):
        r = post_json(client, "/api/license/set-user",
                      {"name": "Unit Tester", "email": "unit@test.com", "org": "TestCo"})
        assert r.json()["ok"] is True

    def test_set_user_persists_name(self, client):
        post_json(client, "/api/license/set-user",
                  {"name": "PersistTest", "email": "p@test.com", "org": ""})
        d = assert_ok(client.get("/api/license/status"))
        assert d["user_name"] == "PersistTest"

    def test_set_user_invalid_email_rejected(self, client):
        r = post_json(client, "/api/license/set-user",
                      {"name": "X", "email": "not-an-email", "org": ""})
        assert r.json()["ok"] is False

    def test_set_user_empty_email_ok(self, client):
        r = post_json(client, "/api/license/set-user",
                      {"name": "NoEmail", "email": "", "org": ""})
        assert r.json()["ok"] is True

    def test_set_user_name_length_capped(self, client):
        long_name = "X" * 200
        r = post_json(client, "/api/license/set-user",
                      {"name": long_name, "email": "", "org": ""})
        assert r.json()["ok"] is True
        # Status should show truncated name
        d = assert_ok(client.get("/api/license/status"))
        assert len(d["user_name"]) <= 100


class TestLicenseHistory:
    def test_history_200(self, client):
        assert client.get("/api/license/history").status_code == 200

    def test_history_has_list(self, client):
        d = assert_ok(client.get("/api/license/history"))
        assert "history" in d
        assert isinstance(d["history"], list)

    def test_history_records_activation(self, client):
        post_json(client, "/api/license/activate", {"license_key": "PRO-HIST-TEST-KEY-12345"})
        d = assert_ok(client.get("/api/license/history"))
        assert any("activated" in str(e.get("event", "")) for e in d["history"])


class TestResetTrial:
    def test_reset_trial_ok_in_dev_mode(self, client):
        import os
        os.environ["AGENTIC_DEV_MODE"] = "1"
        r = post_json(client, "/api/license/reset-trial", {})
        assert r.json()["ok"] is True
        assert r.json()["tier"] == "trial"
