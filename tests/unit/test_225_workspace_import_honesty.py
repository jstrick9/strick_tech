"""Workspace GitHub import: failure honesty + zombie cleanup.

A default install (no GITHUB_TOKEN) clicking "Import GitHub" got a 500 and a
permanent ghost workspace card:

  pull_from_github() is also a public route, and its no-token refusal comes
  back as a JSONResponse(401). import_from_github() then called
  result.get('ok') on that response object — AttributeError, 500 — and the
  crash happened BEFORE the zombie-cleanup line, so the workspace row created
  moments earlier stayed forever. Verified live: one failed import left
  ('b6b6c70f', 'nonexistent-repo-zz') in the table with no way to know it
  was dead weight beyond noticing it never loads.

  Second layer: the frontend discarded the body on non-200 ("Import failed:
  server error 400"), hiding the server's 'GITHUB_TOKEN not set' reason —
  the #142 deploy-error-honesty class. That half is guarded in
  frontend/tests/workspace-error-honesty.test.js.
"""

import pytest


def _names(client):
    return sorted(w['name'] for w in client.get('/api/workspaces').json())


class TestGithubImportHonesty:
    def test_no_token_is_an_explanation_not_a_500(self, client, monkeypatch):
        monkeypatch.delenv('GITHUB_TOKEN', raising=False)
        before = _names(client)

        r = client.post('/api/workspaces/import/github',
                        json={'repo': 'zz-user/nonexistent-zz', 'name': 'ZZ Import Probe'})

        assert r.status_code != 500, 'no-token import must not crash the endpoint'
        body = r.json()
        assert body.get('ok') is False
        assert 'GITHUB_TOKEN' in (body.get('error') or ''), body
        # the just-created workspace row must not survive the failure
        assert _names(client) == before, 'failed import left a zombie workspace'

    def test_plain_dict_refusal_also_cleans_up(self, client, monkeypatch):
        """pull_from_github's other failure shape: a plain {'ok': False} dict
        (network error, missing repo with a token set). Same contract."""
        before = _names(client)

        async def fake_pull(req):
            return {'ok': False, 'error': 'repository not found'}

        import backend.routers.github as gh
        monkeypatch.setattr(gh, 'pull_from_github', fake_pull)
        # workspaces.py imports the function lazily inside the handler
        # (`from .github import pull_from_github`), so patching the module
        # attribute is what the handler will see at call time.
        r = client.post('/api/workspaces/import/github',
                        json={'repo': 'zz-user/nonexistent-zz', 'name': 'ZZ Pull Probe'})

        assert r.status_code != 500
        assert r.json().get('ok') is False
        assert _names(client) == before

    def test_jsonresponse_refusal_shape_is_normalised(self, client, monkeypatch):
        """The regression itself: a JSONResponse from pull_from_github must be
        read as its body, not .get()'d into an AttributeError."""
        from fastapi.responses import JSONResponse

        async def fake_pull(req):
            return JSONResponse({'ok': False, 'error': 'GITHUB_TOKEN not set'},
                                status_code=401)

        import backend.routers.github as gh
        monkeypatch.setattr(gh, 'pull_from_github', fake_pull)
        r = client.post('/api/workspaces/import/github',
                        json={'repo': 'zz-user/any', 'name': 'ZZ Shape Probe'})

        assert r.status_code != 500
        body = r.json()
        assert body.get('ok') is False
        assert 'GITHUB_TOKEN' in (body.get('error') or '')
        assert 'ZZ Shape Probe' not in _names(client)
