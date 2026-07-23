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
