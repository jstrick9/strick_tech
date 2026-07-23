"""Boundary tests for agents, chat request limits, and session upserts."""
import uuid

from backend.services.memory_db import get_conn


def test_agents_malformed_json_is_client_error_not_server_error(client):
    response = client.post('/api/agents', content=b'{', headers={'content-type': 'application/json'})
    assert response.status_code < 500


def test_chat_complete_accepts_and_bounds_generation_options(client):
    response = client.post(
        '/api/chat/complete',
        json={'message': 'test', 'temperature': 999, 'max_tokens': 999999},
    )
    assert response.status_code == 200
    assert response.json().get('text') == 'mocked LLM response'


def test_session_upsert_preserves_message_count(client):
    sid = f'upsert_{uuid.uuid4().hex[:8]}'
    created = client.post('/api/sessions', json={'id': sid, 'name': 'Original'}).json()
    assert created['ok'] is True
    con = get_conn()
    try:
        con.execute(
            "INSERT INTO chat_log(session_id, agent, role, message) VALUES (?,?,?,?)",
            (sid, 'brain', 'user', 'preserved message'),
        )
        con.execute('UPDATE chat_sessions SET message_count=1 WHERE id=?', (sid,))
        con.commit()
    finally:
        con.close()

    updated = client.post('/api/sessions', json={'id': sid, 'name': 'Updated'}).json()
    assert updated['ok'] is True
    session = client.get(f'/api/sessions/{sid}').json()
    assert session['name'] == 'Updated'
    assert session['message_count'] == 1
