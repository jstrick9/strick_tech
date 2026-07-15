"""
Unit Tests — Multifile Agent/Composer, Plugin SDK, Test Generator, Profiler
Covers: multi-file editing, plugin dev SDK, AI test gen, performance profiler
"""
import pytest, httpx

BASE = "http://127.0.0.1:8787"

@pytest.fixture(scope="module")
def client():
    return httpx.Client(base_url=BASE, timeout=20)


class TestMultifileComposer:
    def test_composer_preview_files(self, client):
        r = client.get("/api/composer/preview/branches")
        assert r.status_code == 200
        d = r.json()
        assert "branches" in d or isinstance(d, list)

    def test_composer_branches(self, client):
        r = client.get("/api/composer/preview/branches")
        assert r.status_code == 200

    def test_composer_create_branch(self, client):
        r = client.post("/api/composer/preview/branch", json={
            "name": "unit-test-branch"
        })
        assert r.status_code == 200
        d = r.json()
        assert "ok" in d

    def test_composer_generate_requires_prompt(self, client):
        r = client.post("/api/composer/run", json={})
        assert r.status_code in (200, 400, 422)

    def test_composer_read_file(self, client):
        r = client.get("/api/composer/context")
        assert r.status_code in (200, 404)

    def test_composer_history(self, client):
        r = client.get("/api/composer/history")
        assert r.status_code == 200


class TestPluginSDK:
    def test_pluginsdk_list_packs(self, client):
        r = client.get("/api/pluginsdk/packs")
        assert r.status_code == 200
        d = r.json()
        assert "packs" in d or isinstance(d, list)

    def test_pluginsdk_create_pack(self, client):
        r = client.post("/api/pluginsdk/packs", json={
            "name": "unit-test-pack",
            "version": "1.0.0",
            "description": "Unit test plugin pack",
            "author": "test_suite"
        })
        assert r.status_code == 200
        d = r.json()
        assert "ok" in d or "id" in d or "pack_id" in d

    def test_pluginsdk_get_pack(self, client):
        create = client.post("/api/pluginsdk/packs", json={
            "name": "sdk-get-test", "version": "0.1.0"
        }).json()
        pack_id = create.get("id") or create.get("pack_id", "")
        if pack_id:
            r = client.get(f"/api/pluginsdk/packs/{pack_id}")
            assert r.status_code in (200, 404)

    def test_pluginsdk_templates(self, client):
        r = client.get("/api/pluginsdk/template")
        assert r.status_code == 200

    def test_pluginsdk_validate(self, client):
        r = client.post("/api/pluginsdk/validate", json={
            "pack": {"name": "test", "version": "1.0.0"}
        })
        assert r.status_code == 200


class TestTestGen:
    def test_testgen_generate_requires_code(self, client):
        r = client.post("/api/testgen/generate", json={})
        assert r.status_code in (200, 400, 422)
        if r.status_code == 200:
            assert r.json().get("ok") is False or "error" in r.json()

    def test_testgen_with_code(self, client):
        r = client.post("/api/testgen/generate", json={
            "code": "def add(a, b): return a + b",
            "language": "python",
            "framework": "pytest"
        })
        assert r.status_code == 200
        d = r.json()
        assert "ok" in d or "tests" in d or "code" in d

    def test_testgen_history(self, client):
        r = client.get("/api/testgen/history")
        assert r.status_code == 200
        d = r.json()
        assert isinstance(d, (list, dict))

    def test_testgen_coverage(self, client):
        r = client.get("/api/testgen/frameworks")
        assert r.status_code == 200


class TestProfiler:
    def test_profiler_summary(self, client):
        r = client.get("/api/profiler/summary")
        assert r.status_code == 200
        d = r.json()
        assert "endpoints" in d or "total_calls" in d or "summary" in d

    def test_profiler_endpoints(self, client):
        r = client.get("/api/profiler/endpoints?limit=10")
        assert r.status_code == 200
        d = r.json()
        assert "endpoints" in d or isinstance(d, list)

    def test_profiler_db_stats(self, client):
        r = client.get("/api/profiler/db/stats")
        assert r.status_code == 200

    def test_profiler_agent_timings(self, client):
        r = client.get("/api/profiler/agent/timings")
        assert r.status_code == 200

    def test_profiler_flamegraph(self, client):
        r = client.get("/api/profiler/flamegraph")
        assert r.status_code == 200
        d = r.json()
        assert "flamegraph" in d or isinstance(d, (list, dict))

    def test_profiler_memory_snapshot(self, client):
        r = client.get("/api/profiler/memory/snapshot")
        assert r.status_code == 200

    def test_profiler_reset(self, client):
        r = client.delete("/api/profiler/stats/reset")
        assert r.status_code == 200
        d = r.json()
        assert "ok" in d
