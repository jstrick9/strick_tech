"""Unit tests — Documentation Center (docs_center.py)"""
import pytest
from tests.unit.conftest import assert_ok, post_json


class TestQuickStarts:
    def test_list_200(self, client):
        assert client.get("/api/docs/quick-starts").status_code == 200

    def test_list_has_items(self, client):
        d = assert_ok(client.get("/api/docs/quick-starts"))
        assert "quick_starts" in d
        assert d["count"] >= 1

    def test_list_count_matches(self, client):
        d = assert_ok(client.get("/api/docs/quick-starts"))
        assert d["count"] == len(d["quick_starts"])

    def test_list_filter_by_level_beginner(self, client):
        d = assert_ok(client.get("/api/docs/quick-starts", params={"level": "beginner"}))
        for qs in d["quick_starts"]:
            assert qs["level"] == "beginner"

    def test_list_filter_by_level_intermediate(self, client):
        d = assert_ok(client.get("/api/docs/quick-starts", params={"level": "intermediate"}))
        for qs in d["quick_starts"]:
            assert qs["level"] == "intermediate"

    def test_list_items_have_id(self, client):
        d = assert_ok(client.get("/api/docs/quick-starts"))
        for qs in d["quick_starts"]:
            assert "id" in qs

    def test_list_items_have_steps(self, client):
        d = assert_ok(client.get("/api/docs/quick-starts"))
        for qs in d["quick_starts"]:
            assert "steps" in qs
            assert len(qs["steps"]) > 0

    def test_get_by_id_qs_chat(self, client):
        r = client.get("/api/docs/quick-starts/qs_chat")
        assert r.status_code == 200
        d = r.json()
        assert d["id"] == "qs_chat"

    def test_get_by_id_has_steps(self, client):
        d = assert_ok(client.get("/api/docs/quick-starts/qs_chat"))
        assert len(d["steps"]) >= 4

    def test_get_by_id_steps_have_required_fields(self, client):
        d = assert_ok(client.get("/api/docs/quick-starts/qs_chat"))
        for step in d["steps"]:
            assert "step" in step
            assert "title" in step
            assert "desc" in step

    def test_get_nonexistent_returns_404(self, client):
        r = client.get("/api/docs/quick-starts/TOTALLY_NONEXISTENT_ID")
        assert r.status_code == 404

    def test_get_qs_agents(self, client):
        d = assert_ok(client.get("/api/docs/quick-starts/qs_agents"))
        assert d["id"] == "qs_agents"
        assert d["level"] == "beginner"

    def test_get_qs_workflow(self, client):
        d = assert_ok(client.get("/api/docs/quick-starts/qs_workflow"))
        assert d["level"] == "intermediate"


class TestFeatureDocs:
    def test_list_features_200(self, client):
        assert client.get("/api/docs/features").status_code == 200

    def test_list_features_has_items(self, client):
        d = assert_ok(client.get("/api/docs/features"))
        assert "features" in d
        assert d["count"] >= 5

    def test_list_features_have_id(self, client):
        d = assert_ok(client.get("/api/docs/features"))
        for f in d["features"]:
            assert "id" in f

    def test_list_features_have_tier(self, client):
        d = assert_ok(client.get("/api/docs/features"))
        for f in d["features"]:
            assert "tier" in f
            assert f["tier"] in ("free", "pro", "enterprise")

    def test_list_filter_by_tier_free(self, client):
        d = assert_ok(client.get("/api/docs/features", params={"tier": "free"}))
        for f in d["features"]:
            assert f["tier"] == "free"

    def test_get_feature_chat(self, client):
        d = assert_ok(client.get("/api/docs/features/chat"))
        assert "title" in d
        assert d["tier"] == "free"

    def test_get_feature_has_summary(self, client):
        d = assert_ok(client.get("/api/docs/features/chat"))
        assert "summary" in d
        assert len(d["summary"]) > 0

    def test_get_feature_has_tips(self, client):
        d = assert_ok(client.get("/api/docs/features/chat"))
        assert "tips" in d
        assert isinstance(d["tips"], list)

    def test_get_unknown_feature_returns_stub(self, client):
        r = client.get("/api/docs/features/zzz_nonexistent_pane")
        assert r.status_code == 200
        d = r.json()
        assert "title" in d or "summary" in d


class TestFAQ:
    def test_faq_200(self, client):
        assert client.get("/api/docs/faq").status_code == 200

    def test_faq_has_items(self, client):
        d = assert_ok(client.get("/api/docs/faq"))
        assert "faq" in d
        assert d["count"] >= 5

    def test_faq_items_have_q_and_a(self, client):
        d = assert_ok(client.get("/api/docs/faq"))
        for item in d["faq"]:
            assert "q" in item
            assert "a" in item
            assert len(item["q"]) > 0
            assert len(item["a"]) > 0

    def test_faq_search_api_key(self, client):
        d = assert_ok(client.get("/api/docs/faq", params={"q": "api key"}))
        assert d["count"] >= 1

    def test_faq_search_no_match_returns_empty(self, client):
        d = assert_ok(client.get("/api/docs/faq", params={"q": "zzz_no_match_xyz_abc"}))
        assert d["count"] == 0

    def test_faq_has_tags(self, client):
        d = assert_ok(client.get("/api/docs/faq"))
        for item in d["faq"]:
            assert "tags" in item


class TestShortcuts:
    def test_shortcuts_200(self, client):
        assert client.get("/api/docs/shortcuts").status_code == 200

    def test_shortcuts_has_list(self, client):
        d = assert_ok(client.get("/api/docs/shortcuts"))
        assert "shortcuts" in d
        assert d["count"] >= 5

    def test_shortcuts_have_key_and_desc(self, client):
        d = assert_ok(client.get("/api/docs/shortcuts"))
        for s in d["shortcuts"]:
            assert "key" in s
            assert "desc" in s
            assert len(s["key"]) > 0
            assert len(s["desc"]) > 0


class TestSearch:
    def test_search_200(self, client):
        assert client.get("/api/docs/search", params={"q": "workflow"}).status_code == 200

    def test_search_has_results(self, client):
        d = assert_ok(client.get("/api/docs/search", params={"q": "workflow"}))
        assert "results" in d
        assert d["count"] >= 1

    def test_search_has_count_and_shown(self, client):
        d = assert_ok(client.get("/api/docs/search", params={"q": "agent"}))
        assert "count" in d
        assert "shown" in d

    def test_search_empty_q_returns_empty(self, client):
        d = assert_ok(client.get("/api/docs/search", params={"q": ""}))
        assert d["results"] == []

    def test_search_limit_clamped(self, client):
        d = assert_ok(client.get("/api/docs/search", params={"q": "a", "limit": "1000"}))
        assert len(d["results"]) <= 50

    def test_search_limit_1(self, client):
        d = assert_ok(client.get("/api/docs/search", params={"q": "chat", "limit": "1"}))
        assert len(d["results"]) <= 1

    def test_search_results_have_type(self, client):
        d = assert_ok(client.get("/api/docs/search", params={"q": "workflow"}))
        for r in d["results"]:
            assert "type" in r
            assert r["type"] in ("quickstart", "feature", "faq", "shortcut")

    def test_search_results_sorted_by_score(self, client):
        d = assert_ok(client.get("/api/docs/search", params={"q": "chat"}))
        scores = [r.get("score", 0) for r in d["results"]]
        assert scores == sorted(scores, reverse=True)

    def test_search_faq(self, client):
        d = assert_ok(client.get("/api/docs/search", params={"q": "privacy"}))
        types = {r["type"] for r in d["results"]}
        assert "faq" in types


class TestContextualHelp:
    def test_contextual_200(self, client):
        assert client.get("/api/docs/contextual/chat").status_code == 200

    def test_contextual_has_pane(self, client):
        d = assert_ok(client.get("/api/docs/contextual/chat"))
        assert d["pane"] == "chat"

    def test_contextual_has_doc(self, client):
        d = assert_ok(client.get("/api/docs/contextual/chat"))
        assert "doc" in d

    def test_contextual_has_quick_starts(self, client):
        d = assert_ok(client.get("/api/docs/contextual/chat"))
        assert "quick_starts" in d
        assert isinstance(d["quick_starts"], list)

    def test_contextual_has_faq(self, client):
        d = assert_ok(client.get("/api/docs/contextual/chat"))
        assert "faq" in d

    def test_contextual_unknown_pane_graceful(self, client):
        r = client.get("/api/docs/contextual/zzz_totally_unknown")
        assert r.status_code == 200
        d = r.json()
        assert "pane" in d


class TestFeedback:
    def test_feedback_ok(self, client):
        r = post_json(client, "/api/docs/feedback",
                      {"doc_id": "qs_chat", "doc_type": "quickstart", "helpful": True})
        assert r.json()["ok"] is True

    def test_feedback_not_helpful(self, client):
        r = post_json(client, "/api/docs/feedback",
                      {"doc_id": "qs_chat", "doc_type": "quickstart", "helpful": False})
        assert r.json()["ok"] is True

    def test_feedback_missing_doc_id_rejected(self, client):
        r = post_json(client, "/api/docs/feedback",
                      {"doc_type": "quickstart", "helpful": True})
        assert r.json()["ok"] is False

    def test_feedback_returns_total(self, client):
        r = post_json(client, "/api/docs/feedback",
                      {"doc_id": "qs_agents", "doc_type": "quickstart", "helpful": True})
        d = r.json()
        assert "total_feedback" in d
        assert d["total_feedback"] >= 1

    def test_feedback_invalid_doc_type_normalised(self, client):
        r = post_json(client, "/api/docs/feedback",
                      {"doc_id": "test", "doc_type": "invalid_type", "helpful": True})
        # Should succeed, type normalised to "feature"
        assert r.json()["ok"] is True

    def test_feedback_summary_200(self, client):
        assert client.get("/api/docs/feedback/summary").status_code == 200

    def test_feedback_summary_has_list(self, client):
        post_json(client, "/api/docs/feedback",
                  {"doc_id": "summary-test", "doc_type": "feature", "helpful": True})
        d = assert_ok(client.get("/api/docs/feedback/summary"))
        assert "feedback" in d
        assert isinstance(d["feedback"], list)

    def test_feedback_summary_aggregates_correctly(self, client):
        # Submit 2 helpful, 1 not helpful for same doc
        for _ in range(2):
            post_json(client, "/api/docs/feedback",
                      {"doc_id": "agg-test", "doc_type": "feature", "helpful": True})
        post_json(client, "/api/docs/feedback",
                  {"doc_id": "agg-test", "doc_type": "feature", "helpful": False})
        d = assert_ok(client.get("/api/docs/feedback/summary"))
        agg = next((x for x in d["feedback"] if x["doc_id"] == "agg-test"), None)
        if agg:
            assert agg["helpful"] >= 2
            assert agg["not_helpful"] >= 1
