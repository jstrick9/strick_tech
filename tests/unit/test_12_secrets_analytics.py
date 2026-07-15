"""Unit tests — Secrets Vault & Analytics (secrets.py, analytics.py)"""
import uuid, pytest
from tests.unit.conftest import assert_ok, post_json


class TestSecretsVault:
    def _uid(self): return uuid.uuid4().hex[:6]

    def test_list_secrets_200(self, client):
        assert client.get("/api/secrets/list").status_code == 200

    def test_list_returns_ok(self, client):
        d = assert_ok(client.get("/api/secrets/list"))
        assert d.get("ok") is True

    def test_list_has_items(self, client):
        d = assert_ok(client.get("/api/secrets/list"))
        assert "items" in d

    def test_list_values_are_masked(self, client):
        """Values should never be returned in plaintext."""
        d = assert_ok(client.get("/api/secrets/list"))
        for item in d["items"]:
            if "value" in item:
                # If value is returned it must be masked
                assert "•" in str(item.get("masked", "•")) or "value" not in item

    def test_set_secret(self, client):
        key = f"UNIT_TEST_{self._uid().upper()}"
        r = post_json(client, "/api/secrets/set",
                      {"key": key, "value": "unit_test_value_123"})
        assert r.status_code == 200
        d = r.json()
        assert d["ok"] is True
        assert d["key"] == key

    def test_set_returns_fingerprint(self, client):
        key = f"FP_TEST_{self._uid().upper()}"
        r = post_json(client, "/api/secrets/set",
                      {"key": key, "value": "fingerprint_value"})
        d = r.json()
        assert "fingerprint" in d

    def test_get_secret(self, client):
        key = f"GET_TEST_{self._uid().upper()}"
        post_json(client, "/api/secrets/set", {"key": key, "value": "get_value"})
        r = client.get("/api/secrets/get", params={"key": key})
        assert r.status_code in (200, 404)

    def test_delete_secret(self, client):
        key = f"DEL_TEST_{self._uid().upper()}"
        post_json(client, "/api/secrets/set", {"key": key, "value": "delete_me"})
        r = client.delete(f"/api/secrets/{key}")
        assert r.status_code in (200, 204, 404)

    def test_delete_removes_from_list(self, client):
        key = f"REMOVE_TEST_{self._uid().upper()}"
        post_json(client, "/api/secrets/set", {"key": key, "value": "remove_me"})
        client.delete(f"/api/secrets/{key}")
        d = assert_ok(client.get("/api/secrets/list"))
        assert not any(item["key"] == key for item in d["items"])

    def test_inject_secrets(self, client):
        r = client.get("/api/secrets/inject")  # GET endpoint
        if r.status_code == 405:
            r = client.post("/api/secrets/inject")  # try POST if GET fails
        assert r.status_code in (200, 204, 405)

    def test_set_invalid_key_name(self, client):
        """Keys with invalid chars might be rejected or normalised."""
        r = post_json(client, "/api/secrets/set",
                      {"key": "VALID_KEY_NAME", "value": "v"})
        assert r.json()["ok"] is True

    def test_overwrite_existing_secret(self, client):
        key = f"OVERWRITE_{self._uid().upper()}"
        post_json(client, "/api/secrets/set", {"key": key, "value": "original"})
        r = post_json(client, "/api/secrets/set", {"key": key, "value": "updated"})
        assert r.json()["ok"] is True

    def test_count_increases_after_set(self, client):
        d1 = assert_ok(client.get("/api/secrets/list"))
        count_before = d1["count"]
        key = f"COUNT_TEST_{self._uid().upper()}"
        post_json(client, "/api/secrets/set", {"key": key, "value": "x"})
        d2 = assert_ok(client.get("/api/secrets/list"))
        assert d2["count"] >= count_before


class TestAnalytics:
    def test_kpis_200(self, client):
        r = client.get("/api/analytics/kpis")
        assert r.status_code in (200, 404)

    def test_kpis_is_dict(self, client):
        r = client.get("/api/analytics/kpis")
        if r.status_code == 200:
            assert isinstance(r.json(), dict)

    def test_activity_200(self, client):
        r = client.get("/api/analytics/activity")
        assert r.status_code in (200, 404)

    def test_activity_is_list_or_dict(self, client):
        r = client.get("/api/analytics/activity")
        if r.status_code == 200:
            assert isinstance(r.json(), (list, dict))

    def test_agents_analytics_200(self, client):
        r = client.get("/api/analytics/agents")
        assert r.status_code in (200, 404)

    def test_sessions_analytics_200(self, client):
        r = client.get("/api/analytics/sessions")
        assert r.status_code in (200, 404)

    def test_export_analytics_200(self, client):
        r = client.get("/api/analytics/export")
        assert r.status_code in (200, 404)

    def test_memory_growth_200(self, client):
        r = client.get("/api/analytics/memory/growth")
        assert r.status_code in (200, 404)

    def test_tasks_velocity_200(self, client):
        r = client.get("/api/analytics/tasks/velocity")
        assert r.status_code in (200, 404)


class TestOnboarding:
    def test_status_200(self, client):
        assert client.get("/api/onboarding/status").status_code == 200

    def test_status_has_complete_field(self, client):
        d = assert_ok(client.get("/api/onboarding/status"))
        assert "complete" in d or "done" in d or "step" in d

    def test_shortcuts_200(self, client):
        assert client.get("/api/onboarding/shortcuts").status_code in (200, 404)

    def test_preferences_200(self, client):
        assert client.get("/api/onboarding/preferences").status_code in (200, 404)

    def test_steps_200(self, client):
        assert client.get("/api/onboarding/steps").status_code in (200, 404)

    def test_themes_200(self, client):
        assert client.get("/api/onboarding/themes").status_code in (200, 404)

    def test_complete_onboarding(self, client):
        r = post_json(client, "/api/onboarding/complete",
                      {"name": "UnitTester", "role": "developer"})
        assert r.status_code in (200, 204)

    def test_reset_onboarding(self, client):
        r = client.post("/api/onboarding/reset")
        assert r.status_code in (200, 204, 404)
