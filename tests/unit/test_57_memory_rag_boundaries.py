"""Boundary tests for memory and RAG input handling."""
from backend.services.memory_db import hybrid_search


def test_memory_malformed_json_is_not_a_server_error(client):
    response = client.post('/api/memory/add', content=b'{', headers={'content-type': 'application/json'})
    assert response.status_code < 500


def test_memory_limits_are_clamped(client):
    response = client.get('/api/memory/list', params={'limit': '-100', 'offset': '-20'})
    assert response.status_code == 200
    assert isinstance(response.json(), list)


def test_empty_hybrid_query_is_safe():
    assert hybrid_search('', limit=9999) == []


def test_rag_fts_injection_is_not_a_server_error(client):
    pipeline = client.post('/api/rag/pipelines', json={'name': 'Boundary RAG'}).json()['pipeline_id']
    response = client.post(
        f'/api/rag/pipelines/{pipeline}/retrieve',
        json={'query': "' OR 1=1 -- MATCH (n) DELETE n", 'k': 9999},
    )
    assert response.status_code < 500
    client.delete(f'/api/rag/pipelines/{pipeline}')
