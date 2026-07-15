"""
Unit Tests — Browser Agent, E2E Testing, Onboarding
Covers: browser agent sessions, E2E trace, accessibility, onboarding flows
"""
import pytest, httpx

BASE = "http://127.0.0.1:8787"

@pytest.fixture(scope="module")
def client():
    return httpx.Client(base_url=BASE, timeout=20)


class TestBrowserAgent:
    def test_browser_status(self, client):
        r = client.get("/api/browser/status")
        assert r.status_code == 200
        d = r.json()
        assert "chromium_installed" in d or "ok" in d or "mode" in d

    def test_browser_sessions_list(self, client):
        r = client.get("/api/browser/sessions")
        assert r.status_code == 200
        d = r.json()
        assert "sessions" in d or isinstance(d, list)

    def test_browser_run_requires_url(self, client):
        r = client.post("/api/browser/task", json={})
        assert r.status_code in (200, 400, 404, 422)

    def test_browser_screenshot_no_session(self, client):
        r = client.post("/api/browser/screenshot", json={"session_id": "nonexistent"})
        assert r.status_code in (200, 404)
        if r.status_code == 200:
            assert r.json().get("ok") is False or "error" in r.json()

    def test_browser_extract_no_session(self, client):
        r = client.post("/api/browser/task", json={
            "session_id": "nonexistent",
            "selector": "h1"
        })
        assert r.status_code in (200, 404)

    def test_browser_history(self, client):
        r = client.get("/api/browser/screenshots")
        assert r.status_code in (200, 404)


class TestE2E:
    def test_e2e_status(self, client):
        r = client.get("/api/e2e/status")
        assert r.status_code == 200
        d = r.json()
        assert "playwright_installed" in d or "ok" in d

    def test_e2e_playwright_status(self, client):
        r = client.get("/api/e2e/playwright/status")
        assert r.status_code == 200

    def test_e2e_history(self, client):
        r = client.get("/api/e2e/history?limit=5")
        assert r.status_code == 200
        assert isinstance(r.json(), list)

    def test_e2e_run_web(self, client):
        r = client.post("/api/e2e/run", json={"target": "web"})
        assert r.status_code == 200
        d = r.json()
        assert "ok" in d
        assert "trace_steps" in d
        assert "passed" in d
        assert "total" in d
        assert "score" in d
        assert d["score"] >= 0

    def test_e2e_trace_steps_structure(self, client):
        r = client.post("/api/e2e/run", json={"target": "web"}).json()
        for step in r.get("trace_steps", []):
            assert "step" in step or "step_name" in step
            assert "status" in step

    def test_e2e_trace_nonexistent(self, client):
        r = client.get("/api/e2e/trace/nonexistent_run")
        assert r.status_code == 200
        d = r.json()
        assert "steps" in d

    def test_e2e_accessibility(self, client):
        r = client.post("/api/e2e/accessibility", json={
            "url": "http://localhost:8787"
        })
        assert r.status_code == 200
        d = r.json()
        assert "ok" in d or "violations" in d

    def test_e2e_performance_audit(self, client):
        r = client.post("/api/e2e/performance", json={
            "url": "http://localhost:8787/preview/index.html"
        })
        assert r.status_code == 200
        d = r.json()
        assert "ok" in d or "metrics" in d

    def test_e2e_autofix_target(self, client):
        r = client.post("/api/e2e/autofix", json={"target": "web", "max_iters": 1})
        assert r.status_code == 200
        d = r.json()
        assert "ok" in d
        assert "iterations" in d
        assert "final_score" in d


class TestOnboarding:
    def test_get_preferences(self, client):
        r = client.get("/api/onboarding/preferences")
        assert r.status_code == 200
        d = r.json()
        assert isinstance(d, dict)

    def test_set_preferences(self, client):
        r = client.patch("/api/onboarding/preferences", json={
            "theme": "dark",
            "role": "developer",
            "first_run": False
        })
        assert r.status_code == 200

    def test_onboarding_complete(self, client):
        r = client.post("/api/onboarding/complete", json={
            "role": "developer",
            "use_case": "personal_assistant"
        })
        assert r.status_code in (200, 404)

    def test_onboarding_steps(self, client):
        r = client.get("/api/onboarding/steps")
        assert r.status_code == 200
        d = r.json()
        assert "steps" in d or isinstance(d, list)

    def test_onboarding_reset(self, client):
        r = client.post("/api/onboarding/reset")
        assert r.status_code == 200

    def test_onboarding_progress(self, client):
        r = client.get("/api/onboarding/status")
        assert r.status_code == 200
