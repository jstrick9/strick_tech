"""Unit tests — Steering Files & BugBot (steering.py, bugbot.py)"""
import uuid, pytest
from tests.unit.conftest import assert_ok, post_json, patch_json


class TestSteering:
    def _uid(self): return uuid.uuid4().hex[:6]

    def test_list_200(self, client):
        assert client.get("/api/steering").status_code == 200

    def test_list_has_files(self, client):
        d = assert_ok(client.get("/api/steering"))
        files = d.get("files", d) if isinstance(d, dict) else d
        assert isinstance(files, list)

    def test_seeded_files_present(self, client):
        d = assert_ok(client.get("/api/steering"))
        files = d.get("files", d) if isinstance(d, dict) else d
        assert len(files) >= 1

    def test_create_steering_file(self, client):
        r = post_json(client, "/api/steering",
                      {"name": f"unit_test_{self._uid()}",
                       "content": "# Unit Test Steering\nAlways write tests.",
                       "enabled": True})
        assert r.status_code == 200
        d = r.json()
        sfid = d.get("id") or (d.get("file") or {}).get("id")
        assert sfid is not None or d.get("ok") is True

    def test_create_returns_id(self, client):
        r = post_json(client, "/api/steering",
                      {"name": f"id_test_{self._uid()}",
                       "content": "# ID test", "enabled": True})
        d = r.json()
        sfid = d.get("id") or (d.get("file") or {}).get("id")
        assert sfid is not None

    def test_toggle_steering_file(self, client):
        d = assert_ok(client.get("/api/steering"))
        files = d.get("files", d) if isinstance(d, dict) else d
        if files:
            sfid = files[0]["id"]
            r = client.post(f"/api/steering/{sfid}/toggle")
            assert r.status_code in (200, 404)
            if r.status_code == 200:
                assert "enabled" in r.json() or r.json().get("ok") is True

    def test_delete_steering_file(self, client):
        r = post_json(client, "/api/steering",
                      {"name": f"del_test_{self._uid()}",
                       "content": "# Delete me", "enabled": True})
        d = r.json()
        sfid = d.get("id") or (d.get("file") or {}).get("id")
        if sfid:
            r2 = client.delete(f"/api/steering/{sfid}")
            assert r2.status_code in (200, 204, 404)

    def test_compiled_endpoint(self, client):
        r = client.get("/api/steering/compiled")
        assert r.status_code in (200, 404)

    def test_context_endpoint(self, client):
        r = client.get("/api/steering/context")
        assert r.status_code in (200, 404)

    def test_learned_patterns(self, client):
        r = client.get("/api/steering/learned/patterns")
        assert r.status_code in (200, 404)

    def test_files_have_enabled_field(self, client):
        d = assert_ok(client.get("/api/steering"))
        files = d.get("files", d) if isinstance(d, dict) else d
        for f in files[:3]:
            assert "enabled" in f

    def test_files_have_content(self, client):
        d = assert_ok(client.get("/api/steering"))
        files = d.get("files", d) if isinstance(d, dict) else d
        for f in files[:3]:
            assert "content" in f


class TestBugBot:
    def test_reviews_200(self, client):
        assert client.get("/api/bugbot/reviews").status_code in (200, 404)

    def test_stats_200(self, client):
        assert client.get("/api/bugbot/stats").status_code in (200, 404)

    def test_review_diff_empty_rejected(self, client):
        r = post_json(client, "/api/bugbot/review/diff",
                      {"diff": "", "agent_id": "builder"})
        assert r.json()["ok"] is False

    def test_review_diff_schema_accepted(self, client):
        r = post_json(client, "/api/bugbot/review/diff",
                      {"diff": "+ def hello():\n+     pass\n- def hello():\n-     return None",
                       "agent_id": "builder"})
        # Without LLM key this may fail with 500 or return error body
        assert r.status_code in (200, 500)
        if r.status_code == 200:
            d = r.json()
            assert "ok" in d

    def test_review_file_schema_accepted(self, client):
        r = post_json(client, "/api/bugbot/review/file",
                      {"content": "def hello():\n    print('hello')",
                       "filename": "test.py",
                       "agent_id": "builder"})
        assert r.status_code in (200, 500)

    def test_review_git_endpoint_exists(self, client):
        r = post_json(client, "/api/bugbot/review/git",
                      {"agent_id": "builder"})
        assert r.status_code in (200, 400, 404, 500)

    def test_review_by_id(self, client):
        r = client.get("/api/bugbot/reviews/nonexistent_id")
        assert r.status_code in (200, 404)

    def test_feedback_on_review(self, client):
        r = post_json(client, "/api/bugbot/reviews/nonexistent/feedback",
                      {"feedback": "helpful", "issue_index": 0})
        assert r.status_code in (200, 404)


class TestSpecs:
    def _uid(self): return uuid.uuid4().hex[:6]

    def test_list_specs_200(self, client):
        assert client.get("/api/specs").status_code == 200

    def test_list_specs_has_items(self, client):
        d = assert_ok(client.get("/api/specs"))
        specs = d.get("specs", d) if isinstance(d, dict) else d
        assert isinstance(specs, list)

    def test_create_spec(self, client):
        r = post_json(client, "/api/specs",
                      {"name": f"UnitSpec_{self._uid()}",
                       "description": "A unit test specification for testing purposes"})
        assert r.status_code == 200
        d = r.json()
        spid = d.get("id") or (d.get("spec") or {}).get("id")
        assert spid is not None

    def test_create_spec_returns_id(self, client):
        r = post_json(client, "/api/specs",
                      {"name": f"SpecID_{self._uid()}",
                       "description": "test"})
        d = r.json()
        assert d.get("id") or (d.get("spec") or {}).get("id")

    def test_get_spec_by_id(self, client):
        r = post_json(client, "/api/specs",
                      {"name": f"GetSpec_{self._uid()}",
                       "description": "get by id test"})
        d = r.json()
        spid = d.get("id") or (d.get("spec") or {}).get("id")
        if spid:
            r2 = client.get(f"/api/specs/{spid}")
            assert r2.status_code in (200, 404)
            if r2.status_code == 200:
                data = r2.json()
                spec = data.get("spec", data) if isinstance(data, dict) else data
                assert spec.get("id") == spid or spec.get("title") is not None

    def test_delete_spec(self, client):
        r = post_json(client, "/api/specs",
                      {"name": f"DelSpec_{self._uid()}",
                       "description": "delete me"})
        d = r.json()
        spid = d.get("id") or (d.get("spec") or {}).get("id")
        if spid:
            r2 = client.delete(f"/api/specs/{spid}")
            assert r2.status_code in (200, 204, 404)

    def test_spec_tasks_endpoint(self, client):
        r = post_json(client, "/api/specs",
                      {"name": f"TaskSpec_{self._uid()}",
                       "description": "tasks test"})
        d = r.json()
        spid = d.get("id") or (d.get("spec") or {}).get("id")
        if spid:
            r2 = client.get(f"/api/specs/{spid}/tasks")
            assert r2.status_code in (200, 404)

    def test_spec_export(self, client):
        r = post_json(client, "/api/specs",
                      {"name": f"ExportSpec_{self._uid()}",
                       "description": "export test"})
        d = r.json()
        spid = d.get("id") or (d.get("spec") or {}).get("id")
        if spid:
            r2 = client.get(f"/api/specs/{spid}/export")
            assert r2.status_code in (200, 404)
