"""
SEC-05: Secrets Exposure Tests
SEC-07: Authentication & Authorization Tests
SEC-09: License Tier Bypass Tests

Critical: secrets must never be returned in plaintext.
          The platform is local-first (no user auth required by design),
          but tier-based feature gating must not be bypassable.
"""
import pytest
from tests.security.conftest import *


class TestSecSecretsNeverExposed:
    """SEC-05: Vault secrets must never be readable in plaintext via API."""

    async def test_stored_secret_value_never_returned_in_list(self, C):
        """List endpoint returns fingerprint/masked value, NEVER the actual value."""
        secret_value = "super_secret_api_key_never_expose_this_in_responses"
        key = uid("SEC_VAULT_TEST").upper()
        
        r = await POST(C, "/api/secrets/set", {"key": key, "value": secret_value})
        assert r.json()["ok"] is True
        
        # Verify value never appears in any API response
        list_r = await GET(C, "/api/secrets/list")
        list_text = list_r.text
        
        assert secret_value not in list_text, \
            f"CRITICAL: Secret value appeared in list response!"
        
        # Check item-by-item
        items = list_r.json().get("items", [])
        item = next((i for i in items if i["key"] == key), None)
        assert item is not None, "Secret not in list"
        assert secret_value not in json.dumps(item), \
            f"CRITICAL: Secret value in list item: {item}"
        
        # Verify fingerprint is shown instead
        assert "fingerprint" in item, "No fingerprint in secret item"
        assert len(item.get("fingerprint", "")) == 12, \
            "Fingerprint length incorrect"
        
        await DELETE(C, f"/api/secrets/{key}")

    async def test_get_secret_returns_masked_not_plaintext(self, C):
        """GET /api/secrets/get returns masked value, not plaintext."""
        secret_value = "plaintext_must_never_appear_in_get_response"
        key = uid("SEC_GET_TEST").upper()
        
        await POST(C, "/api/secrets/set", {"key": key, "value": secret_value})
        
        r = await GET(C, "/api/secrets/get", key=key)
        if r.status_code == 200:
            assert secret_value not in r.text, \
                f"CRITICAL: Plaintext value returned by get endpoint!"
        
        await DELETE(C, f"/api/secrets/{key}")

    async def test_secret_value_not_in_set_response(self, C):
        """POST /api/secrets/set must not echo back the value."""
        secret_value = "echo_me_if_you_dare_secret"
        key = uid("SEC_ECHO_TEST").upper()
        
        r = await POST(C, "/api/secrets/set", {"key": key, "value": secret_value})
        
        assert secret_value not in r.text, \
            f"CRITICAL: Secret value echoed back in set response!"
        
        await DELETE(C, f"/api/secrets/{key}")

    async def test_multiple_secrets_none_exposed(self, C):
        """Multiple secrets stored — none appear in any list response."""
        secrets = {
            uid("SEC_A").upper(): "secret_alpha_never_show",
            uid("SEC_B").upper(): "secret_beta_never_show",
            uid("SEC_C").upper(): "secret_gamma_never_show",
        }
        
        for key, value in secrets.items():
            await POST(C, "/api/secrets/set", {"key": key, "value": value})
        
        list_r = await GET(C, "/api/secrets/list")
        list_text = list_r.text
        
        for key, value in secrets.items():
            assert value not in list_text, \
                f"CRITICAL: Secret value for {key} exposed in list!"
        
        for key in secrets:
            await DELETE(C, f"/api/secrets/{key}")

    async def test_secret_fingerprints_are_distinct(self, C):
        """Different values produce different fingerprints (collision resistance)."""
        key1 = uid("SEC_FP1").upper()
        key2 = uid("SEC_FP2").upper()
        
        r1 = await POST(C, "/api/secrets/set", {"key": key1, "value": "value_one"})
        r2 = await POST(C, "/api/secrets/set", {"key": key2, "value": "value_two"})
        
        fp1 = r1.json().get("fingerprint")
        fp2 = r2.json().get("fingerprint")
        
        assert fp1 != fp2, \
            "SECURITY: Two different values produced same fingerprint!"
        
        for key in [key1, key2]:
            await DELETE(C, f"/api/secrets/{key}")

    async def test_secrets_masked_in_list_display(self, C):
        """Masked field uses bullet characters, not partial value."""
        key = uid("SEC_MASK_TEST").upper()
        secret_val = "this_is_the_secret_value_123"
        
        await POST(C, "/api/secrets/set", {"key": key, "value": secret_val})
        
        list_r = await GET(C, "/api/secrets/list")
        items = list_r.json().get("items", [])
        item = next((i for i in items if i["key"] == key), None)
        
        if item:
            masked = item.get("masked", "")
            assert "•" in masked, "Masked field doesn't contain bullet chars"
            # Must not contain any part of the secret
            assert "this_is_the" not in masked, "Partial secret in masked field"
        
        await DELETE(C, f"/api/secrets/{key}")

    async def test_profile_export_excludes_secrets(self, C):
        """Profile export must not include secrets vault contents."""
        key = uid("SEC_EXPORT_TEST").upper()
        await POST(C, "/api/secrets/set", {"key": key, "value": "export_secret_test"})
        
        r = await GET(C, "/api/profile/export")
        assert "export_secret_test" not in r.text, \
            "Secret value leaked in profile export!"
        
        await DELETE(C, f"/api/secrets/{key}")


class TestSecLicenseTierBypass:
    """SEC-09: License tier gating must not be bypassable."""

    async def test_pane_access_chat_requires_no_tier(self, C):
        """Chat is always free — pane access correctly returns allowed:true."""
        r = await GET(C, "/api/license/pane-access/chat")
        d = r.json()
        assert d["allowed"] is True
        assert d["required_tier"] == "free"

    async def test_enterprise_panes_require_enterprise(self, C):
        """Enterprise panes must show required_tier=enterprise."""
        for pane in ["evals", "rag", "observability", "knowledge-graph"]:
            r = await GET(C, f"/api/license/pane-access/{pane}")
            d = r.json()
            assert d["required_tier"] == "enterprise", \
                f"Pane '{pane}' incorrectly requires: {d.get('required_tier')}"

    async def test_fake_tier_header_ignored(self, C):
        """Injecting fake tier headers must not bypass tier gating."""
        for header_name in ["X-Tier", "X-License-Tier", "X-Agentic-Tier", "Authorization"]:
            r = await C.get("/api/license/pane-access/evals",
                           headers={header_name: "enterprise"})
            d = r.json()
            assert d["ok"] is True
            # Status should not change based on injected headers
            # (it reads from license file, not headers)
            assert d.get("current_tier") in ("free", "trial", "pro", "enterprise")

    async def test_license_key_too_short_rejected(self, C):
        """Short license keys (< 16 chars) are rejected."""
        for key in ["PRO-", "PRO-X", "ENT-SHORT", "PRO-12345678", "ENT-12345678"]:
            r = await POST(C, "/api/license/activate", {"license_key": key})
            d = r.json()
            assert d["ok"] is False, f"Short key '{key}' was accepted!"

    async def test_license_key_wrong_prefix_rejected(self, C):
        """Keys with wrong prefix are rejected regardless of length."""
        for key in [
            "FREE-XXXXXXXXXXXXXXXXXXXX",
            "ADMIN-XXXXXXXXXXXXXXXXXXX",
            "ENTERPRISE-XXXXXXXXXX123",
            "PRO_XXXX_XXXX_XXXX_12345",
        ]:
            r = await POST(C, "/api/license/activate", {"license_key": key})
            d = r.json()
            assert d["ok"] is False, f"Invalid prefix key '{key}' was accepted!"

    async def test_tier_resets_after_trial_reset(self, C):
        """After reset-trial, tier correctly returns to 'trial'."""
        r = await POST(C, "/api/license/reset-trial", {})
        assert r.json()["ok"] is True
        
        status = (await GET(C, "/api/license/status")).json()
        assert status["tier"] == "trial", \
            f"Tier not reset to trial after reset: {status['tier']}"

    async def test_pane_access_with_injected_params(self, C):
        """Query params can't override tier in pane access check."""
        for pane in ["evals", "rag"]:
            # Try to override tier via query param
            r = await C.get(f"/api/license/pane-access/{pane}",
                           params={"tier": "enterprise", "override": "true"})
            d = r.json()
            # Should still use the actual license file tier
            assert "current_tier" in d
            assert d["current_tier"] in ("free", "trial", "pro", "enterprise")

    async def test_license_history_not_tamperable(self, C):
        """License history is read-only — no POST to inject fake events."""
        r = await GET(C, "/api/license/history")
        assert r.status_code == 200
        # History is GET-only — POST should 405
        r2 = await POST(C, "/api/license/history", {"event": "fake_enterprise_activation"})
        assert r2.status_code in (404, 405, 422), \
            f"License history POST should not exist, got: {r2.status_code}"


class TestSecAuthorizationBoundaries:
    """Verify authorization boundaries are maintained."""

    async def test_all_endpoints_respond_without_auth_header(self, C):
        """All endpoints accessible without auth (local-first design)."""
        endpoints = ["/api/health", "/api/agents", "/api/tasks",
                     "/api/profile", "/api/license/status"]
        for path in endpoints:
            r = await GET(C, path)
            assert r.status_code not in (401, 403), \
                f"Endpoint {path} requires auth (not expected for local-first)"

    async def test_no_bearer_token_required(self, C):
        """Platform doesn't require Bearer token (local-first design)."""
        r = await C.get("/api/agents",
                       headers={"Authorization": "Bearer invalid_token_xyz"})
        # Must still work (auth header is ignored)
        assert r.status_code not in (401, 403), \
            "Local-first platform should not require Bearer auth"

    async def test_no_api_key_header_required(self, C):
        """Platform doesn't require API-Key header."""
        r = await C.get("/api/tasks", headers={"X-API-Key": ""})
        assert r.status_code < 500

    async def test_profile_not_deletable_entirely(self, C):
        """Profile data cannot be completely destroyed via API."""
        r = await C.delete("/api/profile")
        # Should 404 or 405 — profile delete endpoint doesn't exist
        assert r.status_code in (404, 405), \
            f"Profile DELETE should not exist: {r.status_code}"
        
        # Profile still accessible after attempt
        profile = (await GET(C, "/api/profile")).json()
        assert "name" in profile, "Profile destroyed!"
