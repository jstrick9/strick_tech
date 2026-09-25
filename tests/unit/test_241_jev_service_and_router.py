"""Unit tests — Jev decision service + /api/jev management router (r92, #255)

Jev (TypeSafe System One, https://docs.typesafe.ai) is a structured-decision
model: one state + typed questions (Choice / Score / Noul) -> typed answers
with probabilities and confidence. It does NOT generate text, which is why it
lives beside llm.py as its own service layer rather than as another provider
entry in complete().

Pinned here:
  * question builders + validation (order matters: malformed input is the
    caller's bug -> ValueError even on an unconfigured deployment)
  * ask() contract: unconfigured raises JevUnavailableError (-> honest 503
    via the app handler), success returns answers/usage/latency and writes
    a cost-ledger row (source_type='jev') + obs trace
  * ask_or_none(): the fail-open wrapper feature integrations rely on —
    every failure mode returns None so callers keep their pre-existing
    behaviour
  * the deterministic mock (scripts/mock_llm.py POST /v1/systemone) over
    REAL httpx against an in-process server: shape, probability sums,
    determinism — the thing the no-network topology will exercise
  * the router: /status never leaks key material, /ask 400s on malformed
    bodies, 503s unconfigured, 200s against the mock
"""
import asyncio
import importlib.util
import json
import threading
from http.server import ThreadingHTTPServer
from pathlib import Path

import pytest

from backend.services import jev


def _run(coro):
    return asyncio.run(coro)


def _fake_post(body=None, status=200, calls=None):
    """Build a replacement for jev._post_json returning a canned body."""

    async def _post(url, headers, payload, timeout):
        if calls is not None:
            calls.append({'url': url, 'headers': headers, 'payload': payload})
        if status != 200:
            raise jev.JevUnavailableError(f'Jev API returned HTTP {status}', detail='boom')
        return body

    return _post


_GOOD_QUESTIONS = {
    'department': {
        'type': 'choice',
        'instructions': 'Which team handles this',
        'criteria': {'billing': 'payments', 'technical': 'bugs'},
    },
    'frustration': {
        'type': 'score',
        'instructions': 'How frustrated',
        'criteria': ['calm', 'annoyed', 'furious'],
    },
    'urgent': {'type': 'noul', 'instructions': 'The message conveys urgency'},
}

_GOOD_RESPONSE = {
    'model': 'jev-test-1.0',
    'answers': {
        'department': {
            'type': 'choice', 'choice': 'technical', 'confidence': 0.78,
            'probabilities': {'technical': 0.85, 'billing': 0.15},
        },
        'frustration': {
            'type': 'score', 'score': 1.0, 'confidence': 1.0,
            'legend': {'0': 'calm', '1': 'annoyed', '2': 'furious'},
            'probabilities': {'0': 0.0, '1': 1.0, '2': 0.0},
        },
        'urgent': {'type': 'noul', 'noul': 1.0},
    },
    'usage': {'input_tokens': 392, 'output_tokens': 65},
}


@pytest.fixture(autouse=True)
def _clean_ledger_and_env(monkeypatch):
    """No key by default (unconfigured is the default deployment), and no
    jev rows survive the test (tests own their shared state)."""
    monkeypatch.delenv('TYPESAFE_API_KEY', raising=False)
    yield
    from backend.services.memory_db import get_conn

    con = get_conn()
    try:
        con.execute("DELETE FROM cost_ledger WHERE source_type='jev'")
        con.execute("DELETE FROM obs_traces WHERE name LIKE 'jev:%'")
        con.commit()
    finally:
        con.close()


class TestQuestionBuilders:
    def test_builders_produce_documented_shapes(self):
        c = jev.choice('pick', {'a': 'A option', 'b': 'B option'})
        assert c == {'type': 'choice', 'instructions': 'pick',
                     'criteria': {'a': 'A option', 'b': 'B option'}}
        s = jev.score('rate', ['low', 'high'])
        assert s == {'type': 'score', 'instructions': 'rate', 'criteria': ['low', 'high']}
        n = jev.noul('is it true')
        assert n == {'type': 'noul', 'instructions': 'is it true'}

    def test_builders_reject_degenerate_criteria(self):
        with pytest.raises(ValueError):
            jev.choice('pick', {'only': 'one option'})
        with pytest.raises(ValueError):
            jev.score('rate', ['single level'])


class TestAskContract:
    def test_unconfigured_raises(self, monkeypatch):
        monkeypatch.delenv('TYPESAFE_API_KEY', raising=False)
        with pytest.raises(jev.JevUnavailableError) as ei:
            _run(jev.ask('state', _GOOD_QUESTIONS))
        assert 'TYPESAFE_API_KEY' in ei.value.message

    def test_validation_precedes_key_check(self):
        # Malformed questions are the caller's bug: 400-worthy even when no
        # key is configured (the environment fact must not mask the bug).
        bad = dict(_GOOD_QUESTIONS)
        bad['warp'] = {'type': 'warp', 'instructions': 'x'}
        with pytest.raises(ValueError):
            _run(jev.ask('state', bad))
        with pytest.raises(ValueError):
            _run(jev.ask('   ', _GOOD_QUESTIONS))  # blank state

    def test_success_shape_and_auth_header(self, monkeypatch):
        monkeypatch.setenv('TYPESAFE_API_KEY', 'test-key-123')
        calls = []
        monkeypatch.setattr(jev, '_post_json', _fake_post(_GOOD_RESPONSE, calls=calls))
        result = _run(jev.ask('a ticket', _GOOD_QUESTIONS, agent_id='tester'))
        assert result['ok'] is True
        assert result['model'] == 'jev-test-1.0'
        assert result['answers']['department']['choice'] == 'technical'
        assert result['answers']['frustration']['score'] == 1.0
        assert result['answers']['urgent']['noul'] == 1.0
        assert result['usage'] == {'input_tokens': 392, 'output_tokens': 65}
        assert isinstance(result['latency_ms'], int)

        # The request carried the bearer key, the configured model, and the
        # questions verbatim.
        assert len(calls) == 1
        assert calls[0]['headers']['Authorization'] == 'Bearer test-key-123'
        assert calls[0]['payload']['model'] == jev.JEV_MODEL
        assert calls[0]['payload']['questions'] == _GOOD_QUESTIONS
        assert calls[0]['payload']['state'] == 'a ticket'

    def test_cost_ledger_row_written(self, monkeypatch):
        from backend.services.memory_db import get_conn

        monkeypatch.setenv('TYPESAFE_API_KEY', 'test-key-123')
        monkeypatch.setattr(jev, '_post_json', _fake_post(_GOOD_RESPONSE))
        _run(jev.ask('a ticket', _GOOD_QUESTIONS, agent_id='cost_check'))
        con = get_conn()
        try:
            rows = con.execute(
                "SELECT agent_id, source_type, model, total_tokens, tokens_in, tokens_out"
                " FROM cost_ledger WHERE source_type='jev' AND agent_id='cost_check'"
            ).fetchall()
        finally:
            con.close()
        assert len(rows) == 1, 'one Jev call must produce exactly one ledger row'
        r = rows[0]
        assert r['source_type'] == 'jev'
        assert r['model'] == 'jev-test-1.0'
        assert r['total_tokens'] == 457 and r['tokens_in'] == 392 and r['tokens_out'] == 65

    def test_missing_answers_raises(self, monkeypatch):
        monkeypatch.setenv('TYPESAFE_API_KEY', 'k')
        monkeypatch.setattr(jev, '_post_json', _fake_post({'model': 'm', 'usage': {}}))
        with pytest.raises(jev.JevUnavailableError):
            _run(jev.ask('state', _GOOD_QUESTIONS))

    def test_ask_or_none_fail_open(self, monkeypatch):
        # Unconfigured -> None (never an exception into the feature caller)
        assert _run(jev.ask_or_none('state', _GOOD_QUESTIONS)) is None
        # Transport failure -> None
        monkeypatch.setenv('TYPESAFE_API_KEY', 'k')
        monkeypatch.setattr(jev, '_post_json', _fake_post(None, status=500))
        assert _run(jev.ask_or_none('state', _GOOD_QUESTIONS)) is None
        # Malformed questions -> None (fail-open covers caller bugs too)
        assert _run(jev.ask_or_none('state', {'bad': {'type': 'warp'}})) is None
        # Success passes through
        monkeypatch.setattr(jev, '_post_json', _fake_post(_GOOD_RESPONSE))
        res = _run(jev.ask_or_none('state', _GOOD_QUESTIONS))
        assert res is not None and res['ok'] is True


def _load_mock_llm():
    path = Path(__file__).resolve().parents[2] / 'scripts' / 'mock_llm.py'
    spec = importlib.util.spec_from_file_location('mock_llm_for_jev_test', path)
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


class TestMockProviderContract:
    """The deterministic Jev mock, over real httpx against an in-process
    server — the same handler the no-network topology serves on 8790."""

    @pytest.fixture()
    def mock_server(self, monkeypatch):
        mod = _load_mock_llm()
        srv = ThreadingHTTPServer(('127.0.0.1', 0), mod.make_handler('openai'))
        port = srv.server_address[1]
        threading.Thread(target=srv.serve_forever, daemon=True).start()
        monkeypatch.setenv('TYPESAFE_API_KEY', 'mock-key')
        monkeypatch.setattr(jev, 'JEV_BASE_URL', f'http://127.0.0.1:{port}')
        yield mod
        srv.shutdown()
        srv.server_close()

    def test_all_three_primitives_over_http(self, mock_server):
        result = _run(jev.ask('a customer ticket about a failing integration', _GOOD_QUESTIONS))
        assert result['ok'] is True
        assert result['model'] == 'jev-mock-1.0'
        a = result['answers']
        assert a['department']['choice'] in ('billing', 'technical')
        assert sum(a['department']['probabilities'].values()) == pytest.approx(1.0, abs=1e-3)
        assert 0.0 <= a['department']['confidence'] <= 1.0
        assert a['frustration']['score'] in (0.0, 1.0, 2.0)
        assert sum(a['frustration']['probabilities'].values()) == pytest.approx(1.0, abs=1e-3)
        assert 0.0 <= a['urgent']['noul'] <= 1.0
        assert result['usage']['input_tokens'] >= 1 and result['usage']['output_tokens'] >= 1

    def test_deterministic_answers(self, mock_server):
        r1 = _run(jev.ask('same state', _GOOD_QUESTIONS))
        r2 = _run(jev.ask('same state', _GOOD_QUESTIONS))
        assert r1['answers'] == r2['answers'], 'mock must be stable for identical requests'

    def test_unknown_question_type_flagged(self, mock_server):
        r = mock_server.jev_systemone_answer(
            {'state': 's', 'questions': {'x': {'type': 'warp', 'instructions': 'x'}}}
        )
        assert 'error' in r['answers']['x']


class TestRouter:
    def test_status_reports_configuration_without_leaking_the_key(self, client, monkeypatch):
        r = client.get('/api/jev/status')
        assert r.status_code == 200
        body = r.json()
        assert body['ok'] is True
        assert body['configured'] is False
        assert body['model'] == jev.JEV_MODEL
        assert body['question_types'] == ['choice', 'score', 'noul']

        monkeypatch.setenv('TYPESAFE_API_KEY', 'super-secret-jev-key')
        r = client.get('/api/jev/status')
        assert r.status_code == 200
        assert r.json()['configured'] is True
        assert 'super-secret-jev-key' not in r.text

    def test_ask_unconfigured_is_honest_503(self, client):
        r = client.post('/api/jev/ask', json={'state': 's', 'questions': _GOOD_QUESTIONS})
        assert r.status_code == 503
        body = r.json()
        assert body['code'] == 'jev_unavailable'
        assert 'TYPESAFE_API_KEY' in body['error']

    def test_ask_validates_bodies(self, client):
        for bad in (
            {'questions': _GOOD_QUESTIONS},                                   # no state
            {'state': 's'},                                                   # no questions
            {'state': 's', 'questions': {}},                                  # empty questions
            {'state': 's', 'questions': {'x': {'type': 'warp', 'instructions': 'x'}}},
            {'state': 'x' * 60_000, 'questions': _GOOD_QUESTIONS},            # oversize
        ):
            r = client.post('/api/jev/ask', json=bad)
            assert r.status_code == 400, f'{bad} should 400, got {r.status_code}'

    def test_ask_against_the_mock(self, client, monkeypatch):
        mod = _load_mock_llm()
        srv = ThreadingHTTPServer(('127.0.0.1', 0), mod.make_handler('openai'))
        port = srv.server_address[1]
        threading.Thread(target=srv.serve_forever, daemon=True).start()
        monkeypatch.setenv('TYPESAFE_API_KEY', 'mock-key')
        monkeypatch.setattr(jev, 'JEV_BASE_URL', f'http://127.0.0.1:{port}')
        try:
            r = client.post('/api/jev/ask', json={'state': 'a ticket', 'questions': _GOOD_QUESTIONS})
        finally:
            srv.shutdown()
            srv.server_close()
        assert r.status_code == 200, r.text
        body = r.json()
        assert body['ok'] is True
        assert body['model'] == 'jev-mock-1.0'
        assert set(body['answers'].keys()) == set(_GOOD_QUESTIONS.keys())
        assert 'latency_ms' in body and 'usage' in body
