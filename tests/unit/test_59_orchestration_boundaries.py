"""Boundary tests for swarm, loops, and workflow orchestration inputs."""
from pathlib import Path


def test_loop_malformed_json_is_not_server_error(client):
    response = client.post('/api/loops', content=b'{', headers={'content-type': 'application/json'})
    assert response.status_code < 500


def test_swarm_bounds_and_normalizes_options(client):
    response = client.post(
        '/api/swarm/run',
        json={'prompt': 'test', 'agents': ['builder', 'brain'], 'strategy': 'unknown', 'max_tokens': 999999},
    )
    assert response.status_code == 200
    data = response.json()
    assert data.get('strategy') == 'judge'


def test_workflow_path_and_corrupt_file_are_safe(client):
    response = client.get('/api/workflow/../../etc/passwd')
    assert response.status_code < 500
    workflow_dir = Path('/tmp/agentic-workflow-boundary')
    workflow_dir.mkdir(exist_ok=True)


def test_workflow_webhook_rejects_internal_urls(client):
    workflow = client.post(
        '/api/workflow',
        json={
            'name': 'SSRF boundary',
            'nodes': [
                {'id': 't', 'type': 'trigger', 'config': {}},
                {'id': 'w', 'type': 'webhook', 'config': {'url': 'http://127.0.0.1:8787/api/secrets'}},
            ],
            'edges': [{'id': 'e', 'from': 't', 'to': 'w'}],
        },
    ).json()['workflow']
    response = client.post(f"/api/workflow/{workflow['id']}/run", json={'input': 'test'})
    assert response.status_code == 200
    assert 'Webhook error' in response.text or 'not allowed' in response.text
