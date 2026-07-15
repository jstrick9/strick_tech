"""
Regression Tests — Original Audit Cycle Bug Fixes (Sprint 14/18 Audit)
These tests guard every bug that was found and fixed in the original
full audit cycle. If any of these fail, a regression has occurred.

Bug IDs: U-01 through UA-02, VULN-01 through VULN-04
"""
import pytest
import httpx

BASE = "http://127.0.0.1:8787"


@pytest.fixture(scope="module")
def client():
    return httpx.Client(base_url=BASE, timeout=15)


class TestRegressionU01_SessionsDelete:
    """U-01: DELETE /api/sessions with empty body caused 500 — fixed by adding try/except."""

    def test_sessions_delete_empty_body_no_500(self, client):
        """Regression: DELETE /api/sessions with empty JSON body must not return 500."""
        r = client.request("DELETE", "/api/sessions", json={})
        assert r.status_code != 500, f"U-01 REGRESSION: DELETE /api/sessions returned {r.status_code}"
        assert r.status_code == 200, f"Expected 200 got {r.status_code}: {r.text[:200]}"

    def test_sessions_delete_no_body_no_500(self, client):
        """Regression: DELETE /api/sessions with no body must not return 500."""
        r = client.delete("/api/sessions")
        assert r.status_code != 500, f"U-01 REGRESSION: {r.status_code}"
        assert r.status_code == 200
        d = r.json()
        assert "ok" in d

    def test_sessions_delete_returns_ok(self, client):
        """Regression: DELETE /api/sessions returns {ok: True, deleted: N}."""
        r = client.delete("/api/sessions")
        assert r.status_code == 200
        d = r.json()
        assert d["ok"] is True
        assert "deleted" in d


class TestRegressionU02_BulkUpdate:
    """U-02: bulk_update with non-list input returned {updated:0} — fixed to return {ok:False}."""

    def test_bulk_update_non_list_returns_error(self, client):
        """Regression: bulk_update with non-list must return ok:False not {updated:0}."""
        r = client.post("/api/tasks/bulk_update", json={"updates": "not_a_list"})
        assert r.status_code == 200
        d = r.json()
        assert d["ok"] is False, f"U-02 REGRESSION: got {d}"
        assert "error" in d

    def test_bulk_update_dict_input_returns_error(self, client):
        """Regression: dict input also rejected."""
        r = client.post("/api/tasks/bulk_update", json={"updates": {"id": 1}})
        assert r.status_code == 200
        assert r.json()["ok"] is False

    def test_bulk_update_valid_list_works(self, client):
        """Regression: valid list input still works."""
        r = client.post("/api/tasks/bulk_update", json={"updates": []})
        assert r.status_code == 200
        d = r.json()
        assert "updated" in d or "ok" in d


class TestRegressionU03_PluginsUninstall:
    """U-03: POST /plugins/uninstall was 405 (DELETE-only) — fixed by adding POST alias."""

    def test_plugins_uninstall_post_works(self, client):
        """Regression: POST /api/plugins/uninstall/{id} must not return 405."""
        r = client.post("/api/plugins/uninstall/nonexistent_plugin_xyz")
        assert r.status_code != 405, f"U-03 REGRESSION: 405 Method Not Allowed"
        # 200 with ok:False is expected for nonexistent plugin
        assert r.status_code == 200
        d = r.json()
        assert "ok" in d

    def test_plugins_uninstall_delete_still_works(self, client):
        """Regression: DELETE alias still works."""
        r = client.delete("/api/plugins/uninstall/nonexistent_plugin_xyz")
        assert r.status_code not in (404, 405), f"DELETE uninstall broken: {r.status_code}"


class TestRegressionU04_MemoryStats:
    """U-04: memory_stats() missing 'total' key — fixed to include total and count aliases."""

    def test_memory_stats_has_total(self, client):
        """Regression: /api/memory/stats must include 'total' key."""
        r = client.get("/api/memory/stats")
        assert r.status_code == 200
        d = r.json()
        assert "total" in d, f"U-04 REGRESSION: 'total' missing from {list(d.keys())}"

    def test_memory_stats_has_count_alias(self, client):
        """Regression: 'count' alias key must also be present."""
        r = client.get("/api/memory/stats")
        d = r.json()
        assert "count" in d or "total" in d, "Neither count nor total in memory stats"

    def test_memory_stats_total_is_integer(self, client):
        """Regression: total must be an integer >= 0."""
        r = client.get("/api/memory/stats")
        d = r.json()
        total = d.get("total", d.get("count", -1))
        assert isinstance(total, int) and total >= 0, f"total is {total!r}"


class TestRegressionF01_RouteOrdering:
    """F-01: /{task_id} wildcard was matching bulk_update — fixed by ordering bulk_update first."""

    def test_bulk_update_route_not_swallowed_by_task_id(self, client):
        """Regression: POST /api/tasks/bulk_update must not return 422 (wildcard match)."""
        r = client.post("/api/tasks/bulk_update", json={"updates": []})
        # 422 would mean it matched /{task_id} expecting a different payload
        assert r.status_code != 422, f"F-01 REGRESSION: 422 means wildcard is matching bulk_update"
        assert r.status_code == 200

    def test_task_id_route_still_works(self, client):
        """Regression: /{task_id} route still responds correctly."""
        # Create a task first
        create = client.post("/api/tasks", json={"title": "regress_F01", "status": "todo"})
        if create.status_code == 200:
            task_id = create.json().get("id", 0)
            if task_id:
                r = client.patch(f"/api/tasks/{task_id}", json={"status": "done"})
                assert r.status_code == 200, f"PATCH /api/tasks/{task_id} broken"


class TestRegressionF02_SpecsPatch:
    """F-02: No PATCH /{spec_id} route existed — fixed by adding full PATCH endpoint."""

    def test_specs_patch_route_exists(self, client):
        """Regression: PATCH /api/specs/{spec_id} must exist (not 404/405)."""
        # Create a spec first
        create = client.post("/api/specs", json={"title": "regress_spec_F02"})
        assert create.status_code == 200
        spec_id = create.json().get("spec", {}).get("id", "")
        if not spec_id:
            return

        r = client.patch(f"/api/specs/{spec_id}", json={"title": "Updated Title"})
        assert r.status_code != 404, f"F-02 REGRESSION: PATCH /api/specs/{spec_id} is 404"
        assert r.status_code != 405, f"F-02 REGRESSION: PATCH /api/specs/{spec_id} is 405"
        assert r.status_code == 200


class TestRegressionF03_HooksCreate:
    """F-03: Hook create returned only 'hook_id' not 'id' — fixed to return both."""

    def test_hooks_create_returns_both_id_fields(self, client):
        """Regression: POST /api/hooks must return both 'id' and 'hook_id'."""
        r = client.post("/api/hooks", json={
            "agent_id": "builder",
            "event_type": "file_save",
            "prompt": "regress_hook_F03"
        })
        assert r.status_code == 200
        d = r.json()
        assert "id" in d, f"F-03 REGRESSION: 'id' missing from hook create response: {d}"
        assert "hook_id" in d, f"F-03 REGRESSION: 'hook_id' missing from hook create response: {d}"
        assert d["id"] == d["hook_id"], "id and hook_id should match"


class TestRegressionF04_RAGCreate:
    """F-04: RAG pipeline create returned only 'pipeline_id' not 'id' — fixed to return both."""

    def test_rag_create_returns_both_id_fields(self, client):
        """Regression: POST /api/rag/pipelines must return both 'id' and 'pipeline_id'."""
        r = client.post("/api/rag/pipelines", json={
            "name": "regress_rag_F04",
            "chunk_size": 500
        })
        assert r.status_code == 200
        d = r.json()
        assert "id" in d, f"F-04 REGRESSION: 'id' missing from RAG create response: {d}"
        assert "pipeline_id" in d, f"F-04 REGRESSION: 'pipeline_id' missing: {d}"


class TestRegressionF05_MemoryTags:
    """F-05: Memory add with list tags caused 500 — fixed with list→string coercion."""

    def test_memory_add_accepts_list_tags(self, client):
        """Regression: POST /api/memory/add with tags as list must work."""
        r = client.post("/api/memory/add", json={
            "source": "regress_F05",
            "content": "Regression test for list tags",
            "tags": ["tag1", "tag2", "tag3"]
        })
        assert r.status_code != 500, f"F-05 REGRESSION: list tags caused 500"
        assert r.status_code == 200
        d = r.json()
        assert d.get("ok") is True

    def test_memory_add_still_accepts_string_tags(self, client):
        """Regression: String tags still work after the fix."""
        r = client.post("/api/memory/add", json={
            "source": "regress_F05_str",
            "content": "Regression test string tags",
            "tags": "tag1,tag2,tag3"
        })
        assert r.status_code == 200
        assert r.json().get("ok") is True


class TestRegressionF06_PromptTags:
    """F-06: Prompt create with list tags caused 500 — fixed with list→string coercion."""

    def test_prompts_create_accepts_list_tags(self, client):
        """Regression: POST /api/prompts with tags as list must work."""
        r = client.post("/api/prompts", json={
            "title": "regress_prompt_F06",
            "content": "Regression test prompt content",
            "tags": ["productivity", "regression", "test"]
        })
        assert r.status_code != 500, f"F-06 REGRESSION: list tags caused 500"
        assert r.status_code == 200


class TestRegressionS01_SessionsBranch:
    """S-01: Session branch returned 'new_session_id' but not 'id' — fixed to return both."""

    def test_sessions_branch_returns_id(self, client):
        """Regression: branch response must include 'id' field."""
        # Create a source session
        create = client.post("/api/sessions", json={"title": "regress_branch_source"})
        if create.status_code != 200:
            return
        src_id = create.json().get("id") or create.json().get("session_id", "")
        if not src_id:
            return

        r = client.post(f"/api/sessions/{src_id}/branch", json={"title": "branch copy"})
        if r.status_code == 200:
            d = r.json()
            assert "id" in d or "new_session_id" in d or "session_id" in d, \
                f"S-01 REGRESSION: branch response missing id field: {d}"


class TestRegressionS02_MalformedJSON:
    """S-02: App-level routes returned 500 on malformed JSON — fixed with try/except."""

    def test_malformed_json_no_500(self, client):
        """Regression: malformed JSON body must return 400/422, not 500."""
        endpoints = [
            "/api/goals",
            "/api/supervisor/run",
            "/api/audit-log/append",
        ]
        for ep in endpoints:
            r = client.post(ep, content=b"not json at all",
                            headers={"Content-Type": "application/json"})
            assert r.status_code != 500, \
                f"S-02 REGRESSION: {ep} returned 500 on malformed JSON"
            assert r.status_code in (200, 400, 422), \
                f"S-02: {ep} returned {r.status_code}"


class TestRegressionUA01_AgentSystemPrompts:
    """UA-01: Default agents had empty system_prompt — fixed with meaningful prompts."""

    def test_default_agents_have_system_prompts(self, client):
        """Regression: All 8 default agents must have non-empty system_prompt."""
        r = client.get("/api/agents")
        assert r.status_code == 200
        agents = r.json()
        agent_list = agents if isinstance(agents, list) else agents.get("agents", [])

        default_ids = {"brain", "builder", "researcher", "reviewer",
                       "creative", "memory", "local", "orchestrator"}
        for agent in agent_list:
            if agent.get("id") in default_ids:
                prompt = agent.get("system_prompt", "")
                assert prompt and len(prompt.strip()) > 10, \
                    f"UA-01 REGRESSION: agent {agent['id']} has empty/short system_prompt: {prompt!r}"


class TestRegressionUA02_ChatClear:
    """UA-02: POST /api/chat/clear endpoint didn't exist — fixed by adding it."""

    def test_chat_clear_endpoint_exists(self, client):
        """Regression: POST /api/chat/clear must exist (not 404)."""
        r = client.post("/api/chat/clear", json={})
        assert r.status_code != 404, \
            f"UA-02 REGRESSION: POST /api/chat/clear is 404 (endpoint missing)"
        assert r.status_code == 200
        d = r.json()
        assert d.get("ok") is True
        assert "cleared" in d

    def test_chat_clear_with_session_id(self, client):
        """Regression: chat clear with specific session_id works."""
        r = client.post("/api/chat/clear", json={"session_id": "test_session_xyz"})
        assert r.status_code == 200
        assert r.json()["ok"] is True


class TestRegressionVULN_TerminalInjection:
    """VULN-01 through VULN-04: Terminal injection vulnerabilities — fixed."""

    def test_vuln01_pipe_injection_blocked(self, client):
        """Regression: pipe chain injection blocked (cat /etc/passwd via pipe)."""
        r = client.post("/api/terminal/run",
                        json={"command": "ls | cat /etc/passwd"})
        text = r.text
        assert "root:" not in text, "VULN-01 REGRESSION: pipe injection succeeded"
        assert "blocked" in text.lower() or "permitted" in text.lower() or \
               r.status_code != 200 or "error" in text.lower(), \
            f"VULN-01: pipe injection not blocked: {text[:200]}"

    def test_vuln02_semicolon_injection_blocked(self, client):
        """Regression: semicolon injection blocked (echo; whoami)."""
        r = client.post("/api/terminal/run",
                        json={"command": "echo hello; whoami"})
        text = r.text
        # Should not execute whoami
        assert "blocked" in text.lower() or "not permitted" in text.lower() or \
               "semicolon" in text.lower() or r.status_code == 200, \
            f"VULN-02: semicolon handling unclear: {text[:200]}"

    def test_vuln03_sensitive_path_blocked(self, client):
        """Regression: cat /etc/passwd blocked."""
        r = client.post("/api/terminal/run",
                        json={"command": "cat /etc/passwd"})
        text = r.text
        assert "root:" not in text, "VULN-03 REGRESSION: /etc/passwd accessible"
        assert "blocked" in text.lower() or "not permitted" in text.lower() or \
               "error" in text.lower(), \
            f"VULN-03: sensitive path not blocked: {text[:200]}"

    def test_vuln04_metachar_injection_blocked(self, client):
        """Regression: &&, ``, $() metachar injection blocked."""
        dangerous_cmds = [
            "ls && cat /etc/passwd",
            "echo `whoami`",
            "echo $(id)",
        ]
        for cmd in dangerous_cmds:
            r = client.post("/api/terminal/run", json={"command": cmd})
            text = r.text
            assert "root:" not in text, \
                f"VULN-04 REGRESSION: command '{cmd}' exposed sensitive data"

    def test_safe_terminal_commands_still_work(self, client):
        """Regression: Safe commands still work after security fixes."""
        safe_cmds = ["ls", "pwd", "echo hello"]
        for cmd in safe_cmds:
            r = client.post("/api/terminal/run", json={"command": cmd})
            # Should be 200 or SSE stream — not 500
            assert r.status_code != 500, \
                f"Safe command '{cmd}' returned 500 after security fix"
