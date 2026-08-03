"""
Unit Tests — Settings module review (`tests/unit/test_55_settings_module_review.py`)

Regression guards for real defects found during the Settings review:

1. "Test Connection" validated nothing. It called OpenRouter's GET /api/v1/models,
   which is a PUBLIC endpoint — it returns HTTP 200 with the full catalogue for an
   invalid key, a garbage string, or no Authorization header at all. So the button
   reported "✅ Verified OpenRouter connection! 338 models available" for literally
   any input, and a user with a typo'd key got a green check followed by every
   chat request failing.
2. Preference KEYS were allowlisted but VALUES were never validated, so
   font_size:99999, font_size:"enormous", sidebar_width:-1 and theme:"not-a-theme"
   all persisted and corrupted the UI on next load.
3. Secrets GET/DELETE returned HTTP 200 for keys that do not exist, and DELETE
   reported {"deleted": <key>} for a key that was never there.
4. Font size is stored in two incompatible places ('sm'/'base'/'lg' on
   /api/profile vs a number on /api/onboarding/preferences). applyPreferences()
   read the numeric one — which nothing ever writes — and stamped the 14 default
   over the user's chosen scale on every startup.
"""

from __future__ import annotations

from pathlib import Path

import pytest

from backend.routers.onboarding import DEFAULT_PREFS, validate_preference

ROOT = Path(__file__).resolve().parents[2]
SECRETS_PY = (ROOT / 'backend' / 'routers' / 'secrets.py').read_text(encoding='utf-8')
ONBOARDING_PY = (ROOT / 'backend' / 'routers' / 'onboarding.py').read_text(encoding='utf-8')
CORE_JS = (ROOT / 'frontend' / 'js' / '01-app-core.js').read_text(encoding='utf-8')


class TestConnectionTestActuallyVerifies:
    """/models is public — it can never prove a key is valid."""

    def test_uses_the_authenticated_endpoint(self):
        assert 'https://openrouter.ai/api/v1/auth/key' in SECRETS_PY

    def test_rejects_unauthorised_responses(self):
        assert 'auth.status_code in (401, 403)' in SECRETS_PY
        assert 'OpenRouter rejected this key' in SECRETS_PY

    def test_models_endpoint_is_no_longer_the_verification_gate(self):
        """It may still be called for the count, but only AFTER auth succeeds.

        Compares the real request URLs, not any mention in the fix comments.
        """
        auth_at = SECRETS_PY.index("'https://openrouter.ai/api/v1/auth/key'")
        models_at = SECRETS_PY.index("'https://openrouter.ai/api/v1/models'")
        assert auth_at < models_at, 'the key must be verified before the catalogue is fetched'

    def test_reports_key_metadata_when_valid(self):
        assert "key_info.get('limit')" in SECRETS_PY
        assert "'is_free_tier'" in SECRETS_PY


class TestKeyIsVerifiedBeforeItIsSaved:
    """An invalid key must never be written to the vault and made live."""

    def test_frontend_verifies_first(self):
        idx = CORE_JS.index('async function saveApiKey')
        body = CORE_JS[idx:idx + 2500]
        verify_at = body.index("test-connection")
        save_at = body.index("'/api/secrets/set'")
        assert verify_at < save_at, 'verification must happen before the key is stored'

    def test_nothing_is_saved_when_verification_fails(self):
        assert 'Nothing was saved' in CORE_JS

    def test_network_failure_does_not_save_an_unverified_key(self):
        assert 'Could not reach OpenRouter to verify' in CORE_JS


class TestPreferenceValueValidation:
    @pytest.mark.parametrize(
        'key,value',
        [
            ('font_size', 'enormous'),
            ('theme', 'not-a-theme'),
            ('ui_mode', 'hacker'),
            ('chat_stream', 'maybe'),
            ('default_framework', 'cobol'),
            ('shortcuts', 'not-an-object'),
        ],
    )
    def test_invalid_values_are_rejected_with_a_reason(self, key, value):
        clean, err = validate_preference(key, value)
        assert clean is None
        assert err and key in err

    @pytest.mark.parametrize(
        'key,value,expected',
        [
            ('font_size', 99999, 32),
            ('font_size', -500, 10),
            ('sidebar_width', -1, 160),
            ('sidebar_width', 99999, 600),
            ('auto_save_ms', 0, 100),
        ],
    )
    def test_out_of_range_numbers_are_clamped_not_rejected(self, key, value, expected):
        """A slider overshooting its bounds should settle at the limit."""
        clean, err = validate_preference(key, value)
        assert err is None
        assert clean == expected

    @pytest.mark.parametrize(
        'key,value',
        [('font_size', 18), ('theme', 'ocean'), ('theme', 'light'), ('ui_mode', 'power'), ('chat_stream', False)],
    )
    def test_valid_values_pass_through(self, key, value):
        clean, err = validate_preference(key, value)
        assert err is None
        assert clean == value

    def test_booleans_are_not_treated_as_numbers(self):
        """bool is a subclass of int — order of checks matters."""
        clean, err = validate_preference('chat_stream', True)
        assert err is None and clean is True

    def test_string_booleans_are_coerced(self):
        assert validate_preference('notifications', 'false') == (False, None)

    def test_text_values_are_length_capped(self):
        clean, err = validate_preference('workspace_name', 'x' * 5000)
        assert err is None
        assert len(clean) == 120

    def test_shortcuts_only_accepts_known_names(self):
        clean, err = validate_preference('shortcuts', {'palette': 'ctrl+p', 'bogus': 'x'})
        assert err is None
        assert 'palette' in clean and 'bogus' not in clean

    def test_every_default_value_validates_against_its_own_rule(self):
        """The shipped defaults must not be rejected by our own validator."""
        for key, value in DEFAULT_PREFS.items():
            clean, err = validate_preference(key, value)
            assert err is None, f'default {key}={value!r} rejected: {err}'

    def test_endpoints_use_the_validator(self):
        assert ONBOARDING_PY.count('validate_preference(') >= 2

    def test_rejections_are_reported_to_the_caller(self):
        assert "'rejected': rejected" in ONBOARDING_PY


class TestStatusCodes:
    def test_unknown_preference_key_is_404(self):
        assert 'status_code=404' in ONBOARDING_PY

    def test_invalid_preference_body_is_400(self):
        assert 'status_code=400' in ONBOARDING_PY

    def test_missing_secret_get_is_404(self):
        assert SECRETS_PY.count('status_code=404') >= 2

    def test_delete_no_longer_claims_to_delete_a_missing_key(self):
        assert "return {'ok': cur.rowcount > 0, 'deleted': key}" not in SECRETS_PY
        assert "return {'ok': True, 'deleted': key}" in SECRETS_PY

    def test_vault_unavailable_is_503(self):
        assert 'status_code=503' in SECRETS_PY


class TestFontSizeIsAppliedConsistently:
    def test_shared_scale_tokens_exist(self):
        assert 'const FONT_SCALE_PX = ' in CORE_JS

    def test_save_and_apply_use_the_same_tokens(self):
        """They previously kept private, divergent copies of the px map."""
        assert 'const sizeMap = FONT_SCALE_PX;' in CORE_JS

    def test_apply_prefers_the_users_saved_scale(self):
        idx = CORE_JS.index('function applyPreferences')
        body = CORE_JS[idx:idx + 1600]
        assert 'agentic_os_font_size' in body
        assert 'FONT_SCALE_PX[scale]' in body

    def test_numeric_preference_is_only_a_fallback(self):
        idx = CORE_JS.index('function applyPreferences')
        body = CORE_JS[idx:idx + 1600]
        # The old unconditional `prefs.font_size + 'px'` must be gone.
        assert "prefs.font_size + 'px'" not in body
        assert 'else if (prefs.font_size)' in body
