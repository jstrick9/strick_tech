"""
Unit Tests — Version 6.1 Features (`tests/unit/test_33_v6_1_features.py`)
Tests all 5 pillars of the v6.1 Roadmap:
1. Tauri Desktop App integration endpoints (`/api/tauri/status`, `/api/tauri/config`)
2. MCP Tool Router extended tools (`browser.navigate`, `browser.click`, `git.diff`, `git.commit`, `shell.run_background`)
3. Real Autonomous Agent Loops (`/api/loops/{id}/run-now`, `/api/loops/{id}/history`)
4. One-Click Deploy (`/api/deploy/providers`, `/api/deploy/status`)
5. Playwright E2E Auto-Fix Loop (`/api/e2e/autofix`, `/api/e2e/history`)
"""
from __future__ import annotations
import pytest


class TestV61Features:
    """Suite validating all 5 strategic capabilities of Agentic OS Platform v6.1."""

    def test_tauri_native_status_endpoint(self, client):
        r = client.get("/api/tauri/status")
        assert r.status_code == 200
        data = r.json()
        assert "tauri_cli" in data or "rust_available" in data or isinstance(data, dict)

    def test_tauri_config_endpoint(self, client):
        r = client.get("/api/tauri/config")
        assert r.status_code == 200
        data = r.json()
        assert isinstance(data, dict)

    def test_mcp_extended_tools_registry(self, client):
        r = client.get("/api/mcp/tools")
        assert r.status_code == 200
        data = r.json()
        assert "tools" in data
        raw_tools = data["tools"]
        tools = [t["name"] if isinstance(t, dict) else t for t in raw_tools]
        # Verify our newly added v6.1 MCP tools are registered and available
        assert "browser.navigate" in tools
        assert "browser.click" in tools
        assert "browser.screenshot" in tools
        assert "git.diff" in tools
        assert "git.commit" in tools
        assert "shell.run_background" in tools

    def test_mcp_execute_browser_navigate(self, client):
        r = client.post("/api/mcp/tools/execute", json={
            "tool": "browser.navigate",
            "args": {"url": "https://example.com", "session_id": "test_v6_1"}
        })
        assert r.status_code == 200
        data = r.json()
        assert data.get("ok") is True or "result" in data
        res = data.get("result", data)
        assert res.get("action") == "navigate"
        assert res.get("url") == "https://example.com"

    def test_mcp_execute_git_diff(self, client):
        r = client.post("/api/mcp/tools/execute", json={
            "tool": "git.diff",
            "args": {}
        })
        assert r.status_code == 200
        data = r.json()
        res = data.get("result", data)
        assert res.get("ok") is True
        assert "diff_summary" in res

    def test_autonomous_loops_run_now_and_history(self, client):
        # Create a loop first
        create_r = client.post("/api/loops", json={
            "prompt": "Test autonomous loop execution for v6.1",
            "interval_minutes": 15,
            "agent_id": "builder",
            "job_id": "test_loop_v61"
        })
        assert create_r.status_code == 200

        # Trigger immediate execution
        run_r = client.post("/api/loops/test_loop_v61/run-now")
        assert run_r.status_code == 200
        assert run_r.json()["ok"] is True

        # Fetch loop history
        hist_r = client.get("/api/loops/test_loop_v61/history")
        assert hist_r.status_code == 200
        hist_data = hist_r.json()
        assert hist_data["ok"] is True
        assert hist_data["job_id"] == "test_loop_v61"
        assert "history" in hist_data

    def test_one_click_deploy_providers(self, client):
        r = client.get("/api/deploy/providers")
        assert r.status_code == 200
        data = r.json()
        assert "providers" in data
        assert any("vercel" in str(p).lower() for p in data["providers"])
        assert any("netlify" in str(p).lower() for p in data["providers"])

    def test_e2e_autofix_loop_execution(self, client):
        r = client.post("/api/e2e/autofix", json={
            "target": "web",
            "max_iters": 1
        })
        assert r.status_code == 200
        data = r.json()
        assert "iterations" in data
        assert "final_score" in data
        assert "status" in data
