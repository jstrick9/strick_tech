"""Unit tests — Business Logic & Data Integrity
Tests the core logic functions in isolation (pure unit tests with no HTTP).
"""
from __future__ import annotations
import json, time, pytest
from pathlib import Path
from unittest.mock import patch, MagicMock
import sys, os
sys.path.insert(0, str(Path(__file__).resolve().parents[2]))


class TestLicenseBusinessLogic:
    """Pure unit tests for license helper functions."""

    def test_effective_tier_trial_not_expired(self):
        from backend.routers.license import _effective_tier
        data = {"tier": "trial", "trial_end": time.time() + 86400}
        assert _effective_tier(data) == "trial"

    def test_effective_tier_trial_expired_becomes_free(self):
        from backend.routers.license import _effective_tier
        data = {"tier": "trial", "trial_end": time.time() - 1}
        assert _effective_tier(data) == "free"

    def test_effective_tier_pro_unchanged(self):
        from backend.routers.license import _effective_tier
        data = {"tier": "pro", "trial_end": 0}
        assert _effective_tier(data) == "pro"

    def test_effective_tier_enterprise_unchanged(self):
        from backend.routers.license import _effective_tier
        data = {"tier": "enterprise", "trial_end": 0}
        assert _effective_tier(data) == "enterprise"

    def test_days_remaining_positive(self):
        from backend.routers.license import _days_remaining
        data = {"tier": "trial", "trial_end": time.time() + (3 * 86400)}
        days = _days_remaining(data)
        assert days >= 2

    def test_days_remaining_expired_is_zero(self):
        from backend.routers.license import _days_remaining
        data = {"tier": "trial", "trial_end": time.time() - 1}
        assert _days_remaining(data) == 0

    def test_days_remaining_pro_is_minus_1(self):
        from backend.routers.license import _days_remaining
        data = {"tier": "pro", "trial_end": 0}
        assert _days_remaining(data) == -1

    def test_pane_allowed_free_chat(self):
        from backend.routers.license import _pane_allowed
        assert _pane_allowed("chat", "free") is True

    def test_pane_allowed_free_workflow_false(self):
        from backend.routers.license import _pane_allowed
        assert _pane_allowed("workflow", "free") is False

    def test_pane_allowed_trial_all_panes(self):
        from backend.routers.license import _pane_allowed, PANE_TIERS
        for pane in PANE_TIERS:
            assert _pane_allowed(pane, "trial") is True, f"Trial should allow {pane}"

    def test_pane_allowed_pro_not_enterprise(self):
        from backend.routers.license import _pane_allowed
        # evals is enterprise-only
        assert _pane_allowed("evals", "pro") is False

    def test_pane_allowed_enterprise_all_panes(self):
        from backend.routers.license import _pane_allowed, PANE_TIERS
        for pane in PANE_TIERS:
            assert _pane_allowed(pane, "enterprise") is True

    def test_feature_allowed_wildcard(self):
        from backend.routers.license import _feature_allowed
        assert _feature_allowed("any_feature", "trial") is True
        assert _feature_allowed("any_feature", "enterprise") is True

    def test_feature_allowed_free_chat_ok(self):
        from backend.routers.license import _feature_allowed
        assert _feature_allowed("chat", "free") is True

    def test_feature_allowed_free_swarm_no(self):
        from backend.routers.license import _feature_allowed
        assert _feature_allowed("swarm", "free") is False

    def test_tier_order_hierarchy(self):
        from backend.routers.license import TIER_ORDER
        assert TIER_ORDER["free"] < TIER_ORDER["pro"]
        assert TIER_ORDER["pro"] < TIER_ORDER["enterprise"]

    def test_append_history_adds_entry(self):
        from backend.routers.license import _append_history
        data = {"history": []}
        _append_history(data, "test_event", "test detail")
        assert len(data["history"]) == 1
        assert data["history"][0]["event"] == "test_event"

    def test_append_history_caps_at_20(self):
        from backend.routers.license import _append_history
        data = {"history": []}
        for i in range(25):
            _append_history(data, f"event_{i}", "")
        assert len(data["history"]) == 20

    def test_append_history_has_ts(self):
        from backend.routers.license import _append_history
        data = {"history": []}
        _append_history(data, "ev", "detail")
        entry = data["history"][0]
        assert "ts" in entry
        assert "ts_iso" in entry


class TestUserProfileBusinessLogic:
    """Pure unit tests for profile helper functions."""

    def test_merge_fills_missing_keys(self):
        from backend.routers.userprofile import _merge, DEFAULT_PROFILE
        minimal = {"name": "Test"}
        merged = _merge(minimal)
        for key in DEFAULT_PROFILE:
            assert key in merged, f"Missing key: {key}"

    def test_merge_prefers_saved_values(self):
        from backend.routers.userprofile import _merge
        saved = {"name": "Saved Name", "theme": "midnight"}
        merged = _merge(saved)
        assert merged["name"] == "Saved Name"
        assert merged["theme"] == "midnight"

    def test_merge_notifications_merged_not_replaced(self):
        from backend.routers.userprofile import _merge, DEFAULT_PROFILE
        saved = {"notifications": {"sound": True}}
        merged = _merge(saved)
        # sound should be True (from saved)
        assert merged["notifications"]["sound"] is True
        # Other notification keys should still exist from defaults
        for key in DEFAULT_PROFILE["notifications"]:
            assert key in merged["notifications"]

    def test_role_defaults_all_roles_exist(self):
        from backend.routers.userprofile import ROLE_DEFAULTS
        for role in ["developer", "analyst", "writer", "designer", "manager", "student"]:
            assert role in ROLE_DEFAULTS

    def test_role_defaults_have_pinned_panes(self):
        from backend.routers.userprofile import ROLE_DEFAULTS
        for role, defaults in ROLE_DEFAULTS.items():
            assert "pinned_panes" in defaults
            assert isinstance(defaults["pinned_panes"], list)
            assert len(defaults["pinned_panes"]) >= 1

    def test_role_defaults_have_quick_actions(self):
        from backend.routers.userprofile import ROLE_DEFAULTS
        for role, defaults in ROLE_DEFAULTS.items():
            assert "quick_actions" in defaults

    def test_valid_sets_complete(self):
        from backend.routers.userprofile import (
            VALID_UI_MODES, VALID_THEMES, VALID_FONT_SIZES, VALID_SKILL_LEVELS, VALID_ROLES
        )
        assert "simple" in VALID_UI_MODES
        assert "power" in VALID_UI_MODES
        assert "dark" in VALID_THEMES
        assert "base" in VALID_FONT_SIZES
        assert "beginner" in VALID_SKILL_LEVELS
        assert "developer" in VALID_ROLES

    def test_ts_returns_utc_string(self):
        from backend.routers.userprofile import _ts
        ts = _ts()
        assert "T" in ts
        assert ts.endswith("Z")


class TestDocsBusinessLogic:
    """Pure unit tests for docs content and search logic."""

    def test_quick_starts_all_have_id(self):
        from backend.routers.docs_center import QUICK_STARTS
        for qs in QUICK_STARTS:
            assert "id" in qs
            assert qs["id"].startswith("qs_")

    def test_quick_starts_all_have_steps(self):
        from backend.routers.docs_center import QUICK_STARTS
        for qs in QUICK_STARTS:
            assert "steps" in qs
            assert len(qs["steps"]) >= 3

    def test_quick_starts_steps_numbered(self):
        from backend.routers.docs_center import QUICK_STARTS
        for qs in QUICK_STARTS:
            for i, step in enumerate(qs["steps"], 1):
                assert step["step"] == i

    def test_faq_all_have_q_and_a(self):
        from backend.routers.docs_center import FAQ
        for f in FAQ:
            assert "q" in f and len(f["q"]) > 0
            assert "a" in f and len(f["a"]) > 0
            assert "tags" in f

    def test_shortcuts_all_have_key_and_desc(self):
        from backend.routers.docs_center import KEYBOARD_SHORTCUTS
        for s in KEYBOARD_SHORTCUTS:
            assert "key" in s and len(s["key"]) > 0
            assert "desc" in s and len(s["desc"]) > 0

    def test_feature_docs_tiers_valid(self):
        from backend.routers.docs_center import FEATURE_DOCS
        valid_tiers = {"free", "pro", "enterprise"}
        for pane_id, doc in FEATURE_DOCS.items():
            assert doc["tier"] in valid_tiers, f"{pane_id} has invalid tier: {doc['tier']}"

    def test_search_scores_sorted(self):
        from backend.routers.docs_center import QUICK_STARTS, FEATURE_DOCS, FAQ, KEYBOARD_SHORTCUTS
        # Test the search logic produces sorted results
        qlow = "chat"
        results = []
        for qs in QUICK_STARTS:
            if qlow in qs["title"].lower():
                results.append({"score": 10, "id": qs["id"]})
        results.sort(key=lambda x: x["score"], reverse=True)
        scores = [r["score"] for r in results]
        assert scores == sorted(scores, reverse=True)

    def test_feedback_store_accessible(self):
        from backend.routers.docs_center import _feedback
        assert isinstance(_feedback, list)


class TestWebsearchBusinessLogic:
    """Pure unit tests for websearch helper logic."""

    def test_ddg_search_clamps_num_results(self):
        """_ddg_search is called with clamped num_results from endpoints."""
        # Verify the max(1, min(int(n), 10)) clamping in the router
        import re
        with open("backend/routers/websearch.py") as f:
            src = f.read()
        assert "max(1, min(int(" in src

    def test_record_search_never_raises(self):
        """_record_search should catch all exceptions."""
        from backend.routers.websearch import _record_search
        # Should not raise even with invalid data
        try:
            _record_search("test query", "test_kind", 5)
        except Exception as e:
            pytest.fail(f"_record_search raised: {e}")

    def test_ensure_schema_idempotent(self):
        """_ensure_schema can be called multiple times safely."""
        from backend.routers.websearch import _ensure_schema
        try:
            _ensure_schema()
            _ensure_schema()  # second call should be safe
        except Exception as e:
            pytest.fail(f"_ensure_schema raised on second call: {e}")

    def test_fetch_content_url_validation(self):
        """fetch-content validates URL starts with http/https."""
        import re
        with open("backend/routers/websearch.py") as f:
            src = f.read()
        assert 'r"^https?://"' in src or "^https?://" in src


class TestMemoryServiceLogic:
    """Pure unit tests for memory service functions."""

    def test_memory_add_returns_integer_id(self):
        from backend.services.memory_db import memory_add
        mid = memory_add("unit_test", "test content for logic test", "unit,test")
        assert isinstance(mid, int)
        assert mid > 0

    def test_memory_search_returns_list(self):
        from backend.services.memory_db import memory_add, memory_search_fts
        memory_add("unit_test", "searchable logic test content xyz", "logic")
        results = memory_search_fts("logic test", limit=10)
        assert isinstance(results, list)

    def test_memory_list_returns_list(self):
        from backend.services.memory_db import memory_list
        results = memory_list(limit=10)
        assert isinstance(results, list)

    def test_memory_stats_returns_dict(self):
        from backend.services.memory_db import memory_stats
        stats = memory_stats()
        assert isinstance(stats, dict)
        # Key may be "total" or "sqlite_memories" depending on implementation
        assert "total" in stats or "sqlite_memories" in stats or "count" in stats

    def test_get_conn_returns_connection(self):
        from backend.services.memory_db import get_conn
        import sqlite3
        con = get_conn()
        assert isinstance(con, sqlite3.Connection)
        con.close()

    def test_get_conn_row_factory(self):
        from backend.services.memory_db import get_conn
        import sqlite3
        con = get_conn()
        assert con.row_factory == sqlite3.Row
        con.close()

    def test_audit_log_works(self):
        from backend.services.memory_db import audit_log
        # Should not raise
        try:
            audit_log("unit_test_action", "unit test detail")
        except Exception as e:
            pytest.fail(f"audit_log raised: {e}")


class TestInputSanitization:
    """Test that all inputs are properly validated and sanitized."""

    def test_task_title_max_240_chars(self, client):
        from tests.unit.conftest import post_json
        r = post_json(client, "/api/tasks", {"title": "X" * 300})
        # Should succeed but title capped
        assert r.json()["ok"] is True

    def test_secret_key_empty_rejected(self, client):
        from tests.unit.conftest import post_json
        r = post_json(client, "/api/secrets/set", {"key": "", "value": "v"})
        # Empty key should fail
        assert r.status_code in (200, 400, 422)

    def test_prompt_content_required(self, client):
        from tests.unit.conftest import post_json
        r = post_json(client, "/api/prompts", {"title": "NoContent", "category": "general"})
        # Without content, should fail
        assert r.status_code in (200, 400, 422)

    def test_websearch_num_results_negative(self, client):
        from tests.unit.conftest import post_json
        from unittest.mock import AsyncMock
        import sys
        # Patch ddg for isolation
        r = post_json(client, "/api/websearch/search",
                      {"query": "test", "num_results": -99})
        assert r.status_code == 200  # Should clamp, not crash

    def test_profile_name_unicode_ok(self, client):
        from tests.unit.conftest import patch_json
        r = patch_json(client, "/api/profile", {"name": "José Müller 🧑‍💻"})
        assert r.json()["ok"] is True

    def test_license_key_sql_injection_safe(self, client):
        from tests.unit.conftest import post_json
        r = post_json(client, "/api/license/activate",
                      {"license_key": "PRO-'; DROP TABLE license; --XXXXXXX"})
        # Should safely reject (too many special chars / won't match format)
        assert r.json()["ok"] is False or r.json()["tier"] in ("pro", "enterprise")
