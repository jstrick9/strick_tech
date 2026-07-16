"""
Unit Tests — Code Search & Project Memory (/api/project)
Covers: search, file listing, project memory CRUD, suggestions, code review
"""
import pytest


class TestCodeSearch:
    def test_search_empty_query(self, client):
        r = client.get("/api/project/search?q=")
        assert r.status_code == 200
        d = r.json()
        assert d["total"] == 0
        assert d["results"] == []

    def test_search_returns_results_structure(self, client):
        r = client.get("/api/project/search?q=html&limit=5")
        assert r.status_code == 200
        d = r.json()
        assert "results" in d
        assert "total" in d
        assert "query" in d
        assert isinstance(d["results"], list)

    def test_search_limit_respected(self, client):
        r = client.get("/api/project/search?q=a&limit=3")
        assert r.status_code == 200
        d = r.json()
        assert len(d["results"]) <= 3

    def test_search_result_fields(self, client):
        r = client.get("/api/project/search?q=body&limit=5")
        d = r.json()
        for result in d["results"]:
            assert "file" in result
            assert "line" in result
            assert "match" in result

    def test_search_max_limit(self, client):
        r = client.get("/api/project/search?q=e&limit=999")
        assert r.status_code == 200
        assert len(r.json()["results"]) <= 200


class TestProjectFiles:
    def test_list_files(self, client):
        r = client.get("/api/project/files")
        assert r.status_code == 200
        d = r.json()
        assert "files" in d
        assert "stats" in d
        assert isinstance(d["files"], list)

    def test_files_stats_fields(self, client):
        d = client.get("/api/project/files").json()
        stats = d["stats"]
        assert "total_files" in stats
        assert "total_size" in stats
        assert "by_ext" in stats

    def test_list_files_exclude_hidden(self, client):
        r = client.get("/api/project/files?include_hidden=false")
        assert r.status_code == 200


class TestProjectMemory:
    def test_get_memory_empty(self, client):
        r = client.get("/api/project/memory")
        assert r.status_code == 200
        assert isinstance(r.json(), list)

    def test_set_memory(self, client):
        r = client.post("/api/project/memory", json={
            "key": "test_pref_unit",
            "value": "Use TypeScript always",
            "category": "style",
            "confidence": 0.9
        })
        assert r.status_code == 200
        assert r.json()["ok"] is True

    def test_get_memory_after_set(self, client):
        client.post("/api/project/memory", json={
            "key": "tech_stack_test", "value": "React + FastAPI"
        })
        items = client.get("/api/project/memory").json()
        keys = [i["key"] for i in items]
        assert "tech_stack_test" in keys

    def test_filter_by_category(self, client):
        client.post("/api/project/memory", json={
            "key": "cat_test", "value": "val", "category": "architecture"
        })
        items = client.get("/api/project/memory?category=architecture").json()
        for item in items:
            assert item["category"] == "architecture"

    def test_memory_upsert(self, client):
        client.post("/api/project/memory", json={"key": "upsert_key", "value": "v1"})
        client.post("/api/project/memory", json={"key": "upsert_key", "value": "v2"})
        items = client.get("/api/project/memory").json()
        matches = [i for i in items if i["key"] == "upsert_key"]
        assert len(matches) == 1
        assert matches[0]["value"] == "v2"

    def test_memory_requires_key_and_value(self, client):
        r = client.post("/api/project/memory", json={"key": "only_key"})
        assert r.json()["ok"] is False

    def test_delete_memory(self, client):
        client.post("/api/project/memory", json={"key": "to_delete", "value": "x"})
        r = client.delete("/api/project/memory/to_delete")
        assert r.status_code == 200
        assert r.json()["ok"] is True
        items = client.get("/api/project/memory").json()
        assert "to_delete" not in [i["key"] for i in items]


class TestProjectSuggestions:
    def test_get_suggestions_basic(self, client):
        r = client.post("/api/project/suggestions", json={
            "action": "opened studio", "pane": "studio"
        })
        assert r.status_code == 200
        d = r.json()
        assert "suggestions" in d
        assert isinstance(d["suggestions"], list)

    def test_suggestions_have_required_fields(self, client):
        d = client.post("/api/project/suggestions", json={
            "action": "built component"
        }).json()
        for s in d.get("suggestions", []):
            assert "label" in s
            assert "action" in s
            assert "icon" in s

    def test_suggestions_no_action(self, client):
        r = client.post("/api/project/suggestions", json={})
        assert r.status_code == 200  # Returns default suggestions


class TestCodeReview:
    def test_review_requires_filepath(self, client):
        r = client.post("/api/project/review", json={})
        assert r.json()["ok"] is False

    def test_review_nonexistent_file(self, client):
        r = client.post("/api/project/review", json={"filepath": "nonexistent.py"})
        assert r.json()["ok"] is False

    def test_review_history(self, client):
        r = client.get("/api/project/review/history")
        assert r.status_code == 200
        assert isinstance(r.json(), list)

    def test_learn_requires_action(self, client):
        r = client.post("/api/project/memory/learn", json={"context": "some context"})
        assert r.json()["ok"] is False

    def test_share_returns_url(self, client):
        r = client.post("/api/project/share", json={"target": "web"})
        assert r.status_code == 200
        d = r.json()
        assert "ok" in d
        assert "lan_url" in d
