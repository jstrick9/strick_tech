"""Boundary tests for Studio, workspaces, preview isolation, and deploy setup."""


def test_preview_sibling_path_is_rejected(client):
    response = client.post(
        '/api/preview/save',
        json={'path': '../preview_evil/escaped.html', 'content': 'must not write'},
    )
    # A rejected path traversal answering 400 is strictly better than 200.
    # Asserting 200 here was pinning the 200-on-failure bug in place.
    assert response.status_code == 400
    assert response.json().get('ok') is False


def test_preview_malformed_json_is_not_a_server_error(client):
    response = client.post('/api/preview/save', content=b'{', headers={'content-type': 'application/json'})
    assert response.status_code < 500


def test_preview_versions_are_workspace_scoped(client):
    response = client.post('/api/preview/save', json={'path': 'component-scope-test.txt', 'content': 'v1'})
    assert response.status_code == 200
    history = client.get('/api/preview/history', params={'path': 'component-scope-test.txt'})
    assert history.status_code == 200
    assert history.json()
    version = client.get('/api/preview/version', params={'id': history.json()[0]['id']})
    assert version.status_code == 200
    assert version.json().get('workspace_id') is not None


def test_workspace_create_normalizes_non_string_fields(client):
    response = client.post(
        '/api/workspaces',
        json={'name': 123, 'description': 456, 'color': None, 'emoji': 789, 'framework': True},
    )
    assert response.status_code == 200
    assert response.json().get('ok') is True


def test_workspace_save_missing_workspace_is_rejected(client):
    # Updated in Module 18. This test's NAME said "is_rejected" while its
    # assertion pinned HTTP 200 — codifying the platform-wide "200 on failure"
    # pattern this review has been removing. Saving to a workspace that does
    # not exist is a 404; the body still carries ok:False for older clients.
    response = client.post('/api/workspaces/not-a-real-workspace/save')
    assert response.status_code == 404
    assert response.json().get('ok') is False


def test_deploy_malformed_json_is_not_a_server_error(client, monkeypatch):
    monkeypatch.delenv('VERCEL_TOKEN', raising=False)
    response = client.post('/api/deploy/vercel', content=b'{', headers={'content-type': 'application/json'})
    assert response.status_code < 500
