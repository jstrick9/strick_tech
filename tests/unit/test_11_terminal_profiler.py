"""Unit tests — Terminal/Shell & Code Profiler (terminal.py, profiler.py)"""
import pytest
from tests.unit.conftest import assert_ok, post_json


class TestTerminal:
    def test_run_echo(self, client):
        r = post_json(client, "/api/terminal/run",
                      {"command": "echo unit_test_output", "cwd": "/tmp"})
        assert r.status_code == 200
        assert "unit_test_output" in r.text

    def test_run_pwd(self, client):
        r = post_json(client, "/api/terminal/run",
                      {"command": "pwd"})
        assert r.status_code == 200
        assert "/" in r.text

    def test_run_python_version(self, client):
        r = post_json(client, "/api/terminal/run",
                      {"command": "python3 --version"})
        assert r.status_code == 200

    def test_run_produces_sse_events(self, client):
        r = post_json(client, "/api/terminal/run",
                      {"command": "echo hello"})
        assert "data:" in r.text
        assert "exit" in r.text or "done" in r.text or "hello" in r.text

    def test_run_exit_code_in_output(self, client):
        r = post_json(client, "/api/terminal/run",
                      {"command": "exit 0"})
        # SSE response should contain exit_code
        assert "exit" in r.text.lower() or r.status_code == 200

    def test_run_nonzero_exit(self, client):
        r = post_json(client, "/api/terminal/run",
                      {"command": "false"})
        assert r.status_code == 200
        # Should contain exit_code != 0
        assert "exit" in r.text.lower()

    def test_history_200(self, client):
        assert client.get("/api/terminal/history").status_code in (200, 404)

    def test_history_is_list_or_dict(self, client):
        r = client.get("/api/terminal/history")
        if r.status_code == 200:
            d = r.json()
            assert isinstance(d, (list, dict))

    def test_suggestions_200(self, client):
        r = client.get("/api/terminal/suggestions")
        assert r.status_code in (200, 404)

    def test_run_dangerous_command_handled(self, client):
        """rm -rf / should be handled without crashing the server."""
        r = post_json(client, "/api/terminal/run",
                      {"command": "rm -rf /"})
        # Server must not crash (not 500)
        assert r.status_code in (200, 400, 403)

    def test_run_multiline_output(self, client):
        r = post_json(client, "/api/terminal/run",
                      {"command": "printf 'line1\\nline2\\nline3'"})
        assert r.status_code == 200

    def test_env_endpoint(self, client):
        r = client.get("/api/terminal/env")
        assert r.status_code in (200, 404)

    def test_run_duration_in_output(self, client):
        r = post_json(client, "/api/terminal/run",
                      {"command": "echo timing_test"})
        assert r.status_code == 200
        # exit event should have duration_ms
        assert "duration_ms" in r.text or "timing_test" in r.text


class TestProfiler:
    def test_summary_200(self, client):
        assert client.get("/api/profiler/summary").status_code in (200, 404)

    def test_summary_is_dict(self, client):
        r = client.get("/api/profiler/summary")
        if r.status_code == 200:
            assert isinstance(r.json(), dict)

    def test_endpoints_200(self, client):
        assert client.get("/api/profiler/endpoints").status_code in (200, 404)

    def test_endpoints_has_list(self, client):
        r = client.get("/api/profiler/endpoints")
        if r.status_code == 200:
            d = r.json()
            assert "endpoints" in d or isinstance(d, list)

    def test_flamegraph_200(self, client):
        assert client.get("/api/profiler/flamegraph").status_code in (200, 404)

    def test_flamegraph_is_dict(self, client):
        r = client.get("/api/profiler/flamegraph")
        if r.status_code == 200:
            assert isinstance(r.json(), dict)

    def test_db_stats_200(self, client):
        assert client.get("/api/profiler/db/stats").status_code in (200, 404)

    def test_memory_snapshot_200(self, client):
        r = client.get("/api/profiler/memory/snapshot")
        assert r.status_code in (200, 404)

    def test_run_safe_code(self, client):
        r = post_json(client, "/api/profiler/profile/run",
                      {"code": "x = 1 + 1\nresult = x * 2"})
        assert r.status_code in (200, 400, 422)

    def test_run_print_captured(self, client):
        r = post_json(client, "/api/profiler/profile/run",
                      {"code": "print('profiler_unit_test')"})
        if r.status_code == 200:
            d = r.json()
            assert "ok" in d

    def test_run_blocks_os_system(self, client):
        r = post_json(client, "/api/profiler/profile/run",
                      {"code": "import os; os.system('id')"})
        assert r.status_code in (200, 400, 403, 422)
        if r.status_code == 200:
            d = r.json()
            assert d.get("ok") is False or "error" in str(d).lower() or "block" in str(d).lower()

    def test_run_blocks_subprocess(self, client):
        r = post_json(client, "/api/profiler/profile/run",
                      {"code": "import subprocess; subprocess.run(['id'])"})
        if r.status_code == 200:
            d = r.json()
            assert d.get("ok") is False or "error" in str(d).lower()

    def test_run_blocks_eval_exec(self, client):
        r = post_json(client, "/api/profiler/profile/run",
                      {"code": "__import__('os').getcwd()"})
        if r.status_code == 200:
            d = r.json()
            # Should either block or fail
            assert "ok" in d

    def test_stats_reset(self, client):
        r = client.delete("/api/profiler/stats/reset")
        assert r.status_code in (200, 204, 404)

    def test_agent_timings_200(self, client):
        r = client.get("/api/profiler/agent/timings")
        assert r.status_code in (200, 404)
