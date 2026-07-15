"""Unit tests — Web Search Grounding (websearch.py)"""
import pytest
from unittest.mock import AsyncMock, patch, MagicMock
from tests.unit.conftest import assert_ok, post_json


# ── Mock DuckDuckGo so tests run offline ────────────────────────────────────
MOCK_RESULTS = [
    {"rank": 1, "title": "FastAPI Tutorial", "url": "https://fastapi.tiangolo.com", "snippet": "Build APIs fast"},
    {"rank": 2, "title": "Python Docs",     "url": "https://docs.python.org",       "snippet": "Python reference"},
    {"rank": 3, "title": "Real Python",     "url": "https://realpython.com",        "snippet": "Python tutorials"},
]


@pytest.fixture(autouse=True)
def mock_ddg(monkeypatch):
    """Patch DuckDuckGo so no real HTTP calls are made."""
    async def _fake_ddg(query, num_results=5):
        if not query:
            return []
        return MOCK_RESULTS[:num_results]

    async def _fake_fetch(url, max_chars=2000):
        return f"Fetched content from {url}"[:max_chars]

    monkeypatch.setattr("backend.routers.websearch._ddg_search", _fake_ddg)
    monkeypatch.setattr("backend.routers.websearch._fetch_page_text", _fake_fetch)


class TestWebSearch:
    def test_search_empty_query_rejected(self, client):
        r = post_json(client, "/api/websearch/search", {"query": "", "num_results": 3})
        assert r.json()["ok"] is False

    def test_search_ok(self, client):
        r = post_json(client, "/api/websearch/search", {"query": "Python FastAPI", "num_results": 2})
        assert r.status_code == 200
        d = r.json()
        assert d["ok"] is True

    def test_search_returns_results(self, client):
        r = post_json(client, "/api/websearch/search", {"query": "FastAPI", "num_results": 2})
        d = r.json()
        assert "results" in d
        assert len(d["results"]) >= 1

    def test_search_results_have_rank_title_url_snippet(self, client):
        r = post_json(client, "/api/websearch/search", {"query": "FastAPI", "num_results": 2})
        for res in r.json()["results"]:
            assert "rank" in res
            assert "title" in res
            assert "url" in res
            assert "snippet" in res

    def test_search_num_results_clamped_max_10(self, client):
        r = post_json(client, "/api/websearch/search", {"query": "test", "num_results": 100})
        assert len(r.json()["results"]) <= 10

    def test_search_num_results_clamped_min_1(self, client):
        r = post_json(client, "/api/websearch/search", {"query": "test", "num_results": -5})
        assert r.status_code == 200

    def test_search_returns_query(self, client):
        r = post_json(client, "/api/websearch/search", {"query": "test query xyz"})
        assert r.json()["query"] == "test query xyz"

    def test_search_returns_count(self, client):
        r = post_json(client, "/api/websearch/search", {"query": "test", "num_results": 2})
        d = r.json()
        assert "count" in d
        assert d["count"] == len(d["results"])

    def test_search_with_fetch_content(self, client):
        r = post_json(client, "/api/websearch/search",
                      {"query": "FastAPI", "num_results": 2, "fetch_content": True})
        d = r.json()
        assert d["ok"] is True
        # First 3 results should have content
        for res in d["results"][:3]:
            assert "content" in res

    def test_search_records_history(self, client):
        post_json(client, "/api/websearch/search", {"query": "history_test_query_unique"})
        history = client.get("/api/websearch/history").json()
        queries = [item["query"] for item in history.get("items", [])]
        assert any("history_test_query_unique" in q for q in queries)


class TestFetchContent:
    def test_fetch_empty_url_rejected(self, client):
        r = post_json(client, "/api/websearch/fetch-content", {"url": ""})
        assert r.json()["ok"] is False

    def test_fetch_invalid_url_rejected(self, client):
        r = post_json(client, "/api/websearch/fetch-content", {"url": "not-a-url"})
        assert r.json()["ok"] is False

    def test_fetch_ftp_url_rejected(self, client):
        r = post_json(client, "/api/websearch/fetch-content", {"url": "ftp://example.com"})
        assert r.json()["ok"] is False

    def test_fetch_valid_url_ok(self, client):
        r = post_json(client, "/api/websearch/fetch-content",
                      {"url": "https://example.com", "max_chars": 500})
        d = r.json()
        assert d["ok"] is True
        assert "content" in d
        assert "url" in d

    def test_fetch_returns_length(self, client):
        r = post_json(client, "/api/websearch/fetch-content",
                      {"url": "https://example.com", "max_chars": 500})
        d = r.json()
        assert "length" in d
        assert d["length"] <= 500


class TestHistory:
    def test_history_200(self, client):
        assert client.get("/api/websearch/history").status_code == 200

    def test_history_has_items(self, client):
        d = assert_ok(client.get("/api/websearch/history"))
        assert "items" in d
        assert isinstance(d["items"], list)

    def test_history_ok_true(self, client):
        d = assert_ok(client.get("/api/websearch/history"))
        assert d["ok"] is True

    def test_history_limit_param(self, client):
        d = assert_ok(client.get("/api/websearch/history", params={"limit": "5"}))
        assert len(d["items"]) <= 5

    def test_delete_history_entry_not_found(self, client):
        r = client.delete("/api/websearch/history/9999999")
        assert r.json()["ok"] is False

    def test_delete_history_clears_all(self, client):
        # First add something
        post_json(client, "/api/websearch/search", {"query": "to_be_cleared_xyz"})
        # Clear
        r = client.delete("/api/websearch/history")
        assert r.json()["ok"] is True
        # Verify cleared
        d = assert_ok(client.get("/api/websearch/history"))
        assert len(d["items"]) == 0

    def test_delete_specific_entry(self, client):
        post_json(client, "/api/websearch/search", {"query": "delete_me_specific"})
        items = client.get("/api/websearch/history").json()["items"]
        if items:
            entry_id = items[0]["id"]
            r = client.delete(f"/api/websearch/history/{entry_id}")
            assert r.json()["ok"] is True


class TestSuggest:
    def test_suggest_200(self, client):
        assert client.get("/api/websearch/suggest", params={"q": "Py"}).status_code == 200

    def test_suggest_has_suggestions(self, client):
        # First add some history
        post_json(client, "/api/websearch/search", {"query": "Python FastAPI tutorial"})
        d = assert_ok(client.get("/api/websearch/suggest", params={"q": "Python"}))
        assert "suggestions" in d
        assert isinstance(d["suggestions"], list)

    def test_suggest_empty_q_returns_recent(self, client):
        d = assert_ok(client.get("/api/websearch/suggest", params={"q": ""}))
        assert "suggestions" in d

    def test_suggest_limit_param(self, client):
        d = assert_ok(client.get("/api/websearch/suggest", params={"q": "", "limit": "3"}))
        assert len(d["suggestions"]) <= 3

    def test_suggest_ok_true(self, client):
        d = assert_ok(client.get("/api/websearch/suggest"))
        assert d["ok"] is True


class TestGroundedCompletion:
    @pytest.fixture(autouse=True)
    def mock_llm(self, monkeypatch):
        async def _fake_complete(messages, **kwargs):
            return {"text": "Grounded answer with citations [1]", "tokens": 20}
        monkeypatch.setattr("backend.services.llm.complete", _fake_complete)

    def test_grounded_empty_prompt_rejected(self, client):
        r = post_json(client, "/api/websearch/grounded-completion", {"prompt": ""})
        assert r.json()["ok"] is False

    def test_grounded_ok(self, client):
        r = post_json(client, "/api/websearch/grounded-completion",
                      {"prompt": "What is FastAPI?", "num_results": 2})
        d = r.json()
        assert d["ok"] is True

    def test_grounded_has_answer(self, client):
        r = post_json(client, "/api/websearch/grounded-completion",
                      {"prompt": "What is FastAPI?", "num_results": 2})
        d = r.json()
        assert "answer" in d
        assert len(d["answer"]) > 0

    def test_grounded_has_citations(self, client):
        r = post_json(client, "/api/websearch/grounded-completion",
                      {"prompt": "What is Python?", "num_results": 2})
        d = r.json()
        assert "citations" in d
        assert isinstance(d["citations"], list)

    def test_grounded_has_query(self, client):
        r = post_json(client, "/api/websearch/grounded-completion",
                      {"prompt": "What is Python?", "num_results": 2})
        assert "query" in r.json()

    def test_grounded_has_sources_count(self, client):
        r = post_json(client, "/api/websearch/grounded-completion",
                      {"prompt": "test", "num_results": 2})
        d = r.json()
        assert "sources" in d
        assert isinstance(d["sources"], int)

    def test_grounded_inject_steering_false(self, client, monkeypatch):
        """Verify LLM is called with inject_steering=False."""
        called_with = {}
        async def _capture_complete(messages, **kwargs):
            called_with.update(kwargs)
            return {"text": "ok", "tokens": 5}
        monkeypatch.setattr("backend.services.llm.complete", _capture_complete)
        post_json(client, "/api/websearch/grounded-completion",
                  {"prompt": "test inject_steering", "num_results": 1})
        assert called_with.get("inject_steering") is False
