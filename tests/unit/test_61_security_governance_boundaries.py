"""Boundary tests for secrets, HITL, and RBAC governance."""


def test_hitl_malformed_confidence_is_safe(client):
    response = client.post(
        '/api/hitl/interrupt',
        json={'action_type': 'test_action', 'action_summary': 'test', 'confidence': 'not-a-number'},
    )
    assert response.status_code == 200
    assert response.json().get('ok') is True


def test_hitl_invalid_timeout_does_not_500(client):
    response = client.get('/api/hitl/interrupt/not-real/wait', params={'timeout_seconds': 'invalid'})
    assert response.status_code == 200


def test_secret_vault_never_reports_base64_as_secure(client):
    result = client.post('/api/secrets/set', json={'key': 'BOUNDARY_SECRET', 'value': 'secret-value'})
    assert result.status_code == 200
    data = result.json()
    assert data.get('encrypted') is True or data.get('ok') is False


def test_rbac_token_expiry_is_validated(client):
    response = client.post('/api/rbac/tokens/create', json={'name': 'bad', 'expires_in_days': 0})
    assert response.status_code in (400, 422)
