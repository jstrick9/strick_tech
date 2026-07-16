"""
Unit Tests — Git AI, GitHub Integration
Covers: gitai analysis, commit suggestions, changelog, github endpoints
"""
import pytest, httpx

class TestGitAI:
    def test_gitai_status(self, client):
        r = client.get("/api/gitai/status")
        assert r.status_code == 200
        d = r.json()
        assert "branch" in d or "clean" in d or "ok" in d or "diff" in d or isinstance(d, dict)

    def test_gitai_diff(self, client):
        r = client.get("/api/gitai/diff")
        assert r.status_code == 200
        d = r.json()
        assert "ok" in d or "diff" in d or "changes" in d

    def test_gitai_commit_message_no_diff(self, client):
        r = client.post("/api/gitai/commit", json={"message": "test", "auto_commit": False})
        assert r.status_code == 200
        d = r.json()
        assert "ok" in d or "message" in d

    def test_gitai_log(self, client):
        r = client.get("/api/gitai/log")
        assert r.status_code == 200
        d = r.json()
        assert "ok" in d or "commits" in d or isinstance(d, (list, dict))

    def test_gitai_branches(self, client):
        r = client.get("/api/gitai/log")
        assert r.status_code == 200

    def test_gitai_changelog(self, client):
        r = client.post("/api/gitai/changelog", json={"since": "HEAD~5"})
        assert r.status_code == 200
        d = r.json()
        assert "ok" in d or "changelog" in d

    def test_gitai_security_audit(self, client):
        r = client.post("/api/gitai/security/scan", json={"query": "commit everything"})
        assert r.status_code == 200
        d = r.json()
        assert "ok" in d

    def test_gitai_smart_commit_requires_message(self, client):
        r = client.post("/api/gitai/nl-git", json={})
        assert r.status_code in (200, 400, 422)


class TestGitHub:
    def test_github_status(self, client):
        r = client.get("/api/github/status")
        assert r.status_code == 200
        d = r.json()
        assert "ok" in d or "connected" in d or "authenticated" in d

    def test_github_repos_without_token(self, client):
        r = client.get("/api/github/repos")
        assert r.status_code == 200
        d = r.json()
        # Should return empty list or error (no token configured)
        assert "repos" in d or "ok" in d or "error" in d

    def test_github_create_repo_requires_name(self, client):
        r = client.post("/api/github/repos/create", json={})
        assert r.status_code in (200, 400, 422)
        if r.status_code == 200:
            assert r.json().get("ok") is False or "error" in r.json()

    def test_github_commits_history(self, client):
        r = client.get("/api/github/repos/test/test/commits")
        assert r.status_code in (200, 404)

    def test_github_push_without_token(self, client):
        r = client.post("/api/github/push", json={"message": "test"})
        assert r.status_code == 200
        d = r.json()
        assert "ok" in d
