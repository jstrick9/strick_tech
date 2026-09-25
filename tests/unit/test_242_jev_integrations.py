"""Unit tests — Jev wired into chat re-ranking, arena judging, HITL gating (r92, #256)

The three reference integrations for the Jev decision service (#255), each
pinned with its fail-open contract:

  1. CHAT RAG RE-RANK — the heuristic junk filter still runs first; what it
     keeps is re-ranked by ONE batched Jev call (a Score question per
     passage, parallel and isolated). Unconfigured/unendorsed/failed returns
     the pre-Jev order. End-to-end through POST /api/chat with a captured
     stream: the reranker's output (not FTS order) is what reaches the
     system prompt, trimmed to the 4-passage budget.

  2. ARENA AUTO-JUDGE — a typed Choice question replaces the
     LLM-plus-regex-JSON judge when Jev is configured. Winner mark, tie
     tallies and ELO commit in ONE transaction (the #254 crash-window
     rule). Confident answers apply; the LLM path is the fallback.

  3. HITL CONFIDENCE GATE — a Jev answer below JEV_JUDGE_MIN_CONFIDENCE
     applies NOTHING and queues a human review via hitl.enqueue_review()
     (the extracted queue-write half of create_interrupt); the row is
     decidable through the normal /interrupt/{id}/decide flow.
"""
import asyncio
import json

import pytest

from backend.routers import arena as arena_mod
from backend.routers import chat as chat_mod
from backend.routers.hitl import enqueue_review
from backend.services import jev
from backend.services.memory_db import get_conn, memory_add


def _run(coro):
    return asyncio.run(coro)


def _seed_battle(bid='jp1', a='jpA', b='jpB', resp_a='answer a', resp_b='answer b'):
    con = get_conn()
    try:
        con.execute('DELETE FROM arena_battles WHERE id=?', (bid,))
        con.execute('DELETE FROM arena_leaderboard WHERE model IN (?,?)', (a, b))
        con.execute('INSERT INTO arena_battles(id,prompt,model_a,model_b,category,response_a,response_b) VALUES (?,?,?,?,?,?,?)',
                    (bid, 'a prompt', a, b, 'test', resp_a, resp_b))
        con.execute("INSERT INTO arena_leaderboard(model,elo,wins,losses,ties,battles) VALUES (?,1000.0,0,0,0,0)", (a,))
        con.execute("INSERT INTO arena_leaderboard(model,elo,wins,losses,ties,battles) VALUES (?,1000.0,0,0,0,0)", (b,))
        con.commit()
    finally:
        con.close()


@pytest.fixture(autouse=True)
def _clean(monkeypatch):
    monkeypatch.delenv('TYPESAFE_API_KEY', raising=False)
    yield
    con = get_conn()
    try:
        con.execute('DELETE FROM arena_battles WHERE id LIKE \'jp%\'')
        con.execute('DELETE FROM arena_leaderboard WHERE model LIKE \'jp%\'')
        con.execute("DELETE FROM hitl_queue WHERE requester='jev' OR action_type='arena.auto_judge'")
        con.execute("DELETE FROM memory WHERE source='test:r92'")
        con.execute("DELETE FROM cost_ledger WHERE source_type='jev'")
        con.execute("DELETE FROM obs_traces WHERE name LIKE 'jev:%'")
        con.commit()
    finally:
        con.close()


# ── 1. chat re-rank ───────────────────────────────────────────────────────────

class TestChatRerankHelper:
    def test_unconfigured_returns_input_order(self):
        rows = [{'source': 's', 'content': f'c{i}'} for i in range(6)]
        out = _run(chat_mod._jev_rerank_memories('a message', rows))
        assert out == rows

    def test_configured_reranks_by_expected_relevance(self, monkeypatch):
        rows = [{'source': 's', 'content': f'c{i}'} for i in range(4)]

        async def fake_ask_or_none(state, questions, **kw):
            assert set(questions.keys()) == {'p0', 'p1', 'p2', 'p3'}, 'one question per passage'
            return {
                'ok': True, 'model': 'jev-test', 'usage': {}, 'latency_ms': 5,
                'answers': {
                    # p0 directly relevant (2), p1 steady somewhat (1), p2
                    # mixed 2/0 -> 1.2, p3 not relevant (0) -> dropped
                    'p0': {'type': 'score', 'score': 2.0, 'confidence': 0.9,
                           'probabilities': {'0': 0.0, '1': 0.0, '2': 1.0}},
                    'p1': {'type': 'score', 'score': 1.0, 'confidence': 0.9,
                           'probabilities': {'0': 0.0, '1': 1.0, '2': 0.0}},
                    'p2': {'type': 'score', 'score': 2.0, 'confidence': 0.6,
                           'probabilities': {'0': 0.4, '1': 0.0, '2': 0.6}},
                    'p3': {'type': 'score', 'score': 0.0, 'confidence': 0.9,
                           'probabilities': {'0': 1.0, '1': 0.0, '2': 0.0}},
                },
            }

        monkeypatch.setenv('TYPESAFE_API_KEY', 'k')
        monkeypatch.setattr(jev, 'is_configured', lambda: True)
        monkeypatch.setattr(jev, 'ask_or_none', fake_ask_or_none)
        out = _run(chat_mod._jev_rerank_memories('a message', rows))
        # p0 (2.0) > p2 (1.2) > p1 (1.0); p3 (0.0) dropped
        assert [r['content'] for r in out] == ['c0', 'c2', 'c1']

    def test_nothing_endorsed_falls_back_to_input_order(self, monkeypatch):
        rows = [{'source': 's', 'content': 'c0'}]

        async def none_ask(state, questions, **kw):
            return None

        async def reject_all(state, questions, **kw):
            return {'ok': True, 'model': 'm', 'usage': {}, 'latency_ms': 1,
                    'answers': {'p0': {'type': 'score', 'score': 0.0, 'confidence': 0.9,
                                       'probabilities': {'0': 1.0, '1': 0.0, '2': 0.0}}}}

        monkeypatch.setenv('TYPESAFE_API_KEY', 'k')
        monkeypatch.setattr(jev, 'is_configured', lambda: True)
        monkeypatch.setattr(jev, 'ask_or_none', none_ask)
        assert _run(chat_mod._jev_rerank_memories('m', rows)) == rows
        monkeypatch.setattr(jev, 'ask_or_none', reject_all)
        assert _run(chat_mod._jev_rerank_memories('m', rows)) == rows

    def test_internal_bugs_never_propagate(self, monkeypatch):
        async def bad_ask(state, questions, **kw):
            raise RuntimeError('bug in our ranking code')

        monkeypatch.setenv('TYPESAFE_API_KEY', 'k')
        monkeypatch.setattr(jev, 'is_configured', lambda: True)
        monkeypatch.setattr(jev, 'ask_or_none', bad_ask)
        rows = [{'source': 's', 'content': 'c0'}]
        assert _run(chat_mod._jev_rerank_memories('m', rows)) == rows


class TestChatWiring:
    def test_reranker_output_reaches_the_system_prompt(self, client, monkeypatch):
        # 6 heuristic-eligible memories; the reranker decides order and the
        # prompt keeps only 4.
        for i in range(6):
            memory_add('test:r92', f'r92topic passage number {i} with distinct text {i}')

        captured = {}

        async def fake_rerank(message, rows):
            captured['n_eligible'] = len(rows)
            captured['rows'] = rows
            return list(reversed(rows))  # a deliberately different order

        async def fake_stream(messages, **kw):
            captured['system_prompt'] = messages[0]['content']
            yield 'data: {"delta": "ok", "done": true, "tokens": 1}\n\n'

        monkeypatch.setattr(chat_mod, '_jev_rerank_memories', fake_rerank)
        monkeypatch.setattr(chat_mod.llm, 'stream', fake_stream)

        r = client.post('/api/chat', json={'message': 'r92topic please', 'agent_id': 'default'})
        assert r.status_code == 200, r.text

        # The early `break at 4` is gone: the reranker sees every eligible row.
        assert captured['n_eligible'] == 6, 'eligible pool must not be pre-trimmed to the budget'
        # And the prompt carries the RERANKED order, trimmed to 4.
        prompt = captured['system_prompt']
        assert 'Relevant memories' in prompt
        reversed_contents = [row['content'] for row in list(reversed(captured['rows']))][:4]
        pos = [prompt.find(c[:40]) for c in reversed_contents]
        assert all(p != -1 for p in pos), 'the reranker\'s top-4 must all reach the prompt'
        assert pos == sorted(pos), 'order must follow the reranker, not FTS'
        dropped = [row['content'] for row in list(reversed(captured['rows']))][4:]
        assert all(prompt.find(c[:40]) == -1 for c in dropped), 'beyond-budget passages must not appear'


# ── 2. arena Jev judge ────────────────────────────────────────────────────────

def _jev_answer(confidence, choice='a'):
    return {
        'ok': True, 'model': 'jev-test', 'usage': {'input_tokens': 10, 'output_tokens': 5},
        'latency_ms': 30,
        'answers': {'winner': {'type': 'choice', 'choice': choice, 'confidence': confidence,
                               'probabilities': {choice: confidence, 'tie': round(1 - confidence, 2)}}},
    }


class TestArenaJevJudge:
    def test_confident_choice_applies_atomically(self, monkeypatch):
        _seed_battle()
        monkeypatch.setenv('TYPESAFE_API_KEY', 'k')
        monkeypatch.setattr(jev, 'is_configured', lambda: True)

        async def fake_ask(state, questions, **kw):
            assert 'winner' in questions and questions['winner']['type'] == 'choice'
            return _jev_answer(0.91, 'a')

        monkeypatch.setattr(jev, 'ask_or_none', fake_ask)

        class _Req:
            async def json(self):
                return {'battle_id': 'jp1'}

        out = _run(arena_mod.auto_judge_battle(_Req()))
        assert out['ok'] is True and out['winner'] == 'a' and out['judge'] == 'jev'
        assert out['confidence'] == 0.91
        con = get_conn()
        try:
            w, reason = con.execute('SELECT winner,vote_reason FROM arena_battles WHERE id=?', ('jp1',)).fetchone()
            wa = con.execute('SELECT elo,wins FROM arena_leaderboard WHERE model=?', ('jpA',)).fetchone()
            wb = con.execute('SELECT elo,losses FROM arena_leaderboard WHERE model=?', ('jpB',)).fetchone()
        finally:
            con.close()
        assert w == 'a'
        assert reason.startswith('[JEV]') and '91%' in reason
        assert wa['wins'] == 1 and wa['elo'] > 1000
        assert wb['losses'] == 1 and wb['elo'] < 1000

    def test_low_confidence_defers_to_human_review(self, client, monkeypatch):
        _seed_battle()
        monkeypatch.setenv('TYPESAFE_API_KEY', 'k')
        monkeypatch.setenv('JEV_JUDGE_MIN_CONFIDENCE', '0.7')
        monkeypatch.setattr(jev, 'is_configured', lambda: True)

        async def fake_ask(state, questions, **kw):
            return _jev_answer(0.55, 'b')

        monkeypatch.setattr(jev, 'ask_or_none', fake_ask)

        class _Req:
            async def json(self):
                return {'battle_id': 'jp1'}

        out = _run(arena_mod.auto_judge_battle(_Req()))
        assert out['ok'] is True
        assert out['winner'] is None and out['queued_for_review'] is True
        iid = out['interrupt_id']
        con = get_conn()
        try:
            # NOTHING applied to the battle or the leaderboard
            w = con.execute('SELECT winner FROM arena_battles WHERE id=?', ('jp1',)).fetchone()[0]
            wa = con.execute('SELECT wins,elo FROM arena_leaderboard WHERE model=?', ('jpA',)).fetchone()
            assert w == '' and wa['wins'] == 0
            # The review row carries everything a human needs
            row = con.execute('SELECT * FROM hitl_queue WHERE id=?', (iid,)).fetchone()
        finally:
            con.close()
        assert row is not None
        assert row['requester'] == 'jev'
        assert row['status'] == 'pending'
        data = json.loads(row['action_data'])
        assert data['battle_id'] == 'jp1' and data['proposed_winner'] == 'b'
        assert data['confidence'] == 0.55 and data['judge'] == 'jev'

        # ...and it is decidable through the normal flow
        r = client.post(f'/api/hitl/interrupt/{iid}/decide', json={'decision': 'approve'})
        assert r.status_code == 200, r.text
        con = get_conn()
        try:
            st = con.execute('SELECT status FROM hitl_queue WHERE id=?', (iid,)).fetchone()[0]
        finally:
            con.close()
        assert st == 'approve'  # the decide endpoint stores the decision verbatim

    def test_tie_updates_tallies(self, monkeypatch):
        _seed_battle()
        monkeypatch.setenv('TYPESAFE_API_KEY', 'k')
        monkeypatch.setattr(jev, 'is_configured', lambda: True)

        async def fake_ask(state, questions, **kw):
            return _jev_answer(0.9, 'tie')

        monkeypatch.setattr(jev, 'ask_or_none', fake_ask)

        class _Req:
            async def json(self):
                return {'battle_id': 'jp1'}

        out = _run(arena_mod.auto_judge_battle(_Req()))
        assert out['winner'] == 'tie'
        con = get_conn()
        try:
            w = con.execute('SELECT winner FROM arena_battles WHERE id=?', ('jp1',)).fetchone()[0]
            ta = con.execute('SELECT ties FROM arena_leaderboard WHERE model=?', ('jpA',)).fetchone()[0]
            tb = con.execute('SELECT ties FROM arena_leaderboard WHERE model=?', ('jpB',)).fetchone()[0]
        finally:
            con.close()
        assert w == 'tie' and ta == 1 and tb == 1

    def test_unusable_jev_answer_falls_back_to_llm_judge(self, monkeypatch):
        _seed_battle()
        monkeypatch.setenv('TYPESAFE_API_KEY', 'k')
        monkeypatch.setattr(jev, 'is_configured', lambda: True)

        async def garbage(state, questions, **kw):
            return None  # transport failure

        monkeypatch.setattr(jev, 'ask_or_none', garbage)

        async def fake_complete(messages, **kw):
            return {'ok': True, 'text': '{"winner": "b", "reason": "llm fallback", "scores": {"a": 5, "b": 8}}',
                    'model': 'm', 'tokens': 1, 'cost': 0.0}

        monkeypatch.setattr(arena_mod, '_update_elo', lambda *a, **kw: None)  # ELO pinned elsewhere
        import backend.services.llm as llm_mod

        monkeypatch.setattr(llm_mod, 'complete', fake_complete)

        class _Req:
            async def json(self):
                return {'battle_id': 'jp1'}

        out = _run(arena_mod.auto_judge_battle(_Req()))
        assert out['ok'] is True and out['winner'] == 'b' and 'scores' in out

    def test_unconfigured_keeps_llm_path(self, monkeypatch):
        _seed_battle()
        monkeypatch.delenv('TYPESAFE_API_KEY', raising=False)
        called = {'llm': False}

        async def fake_complete(messages, **kw):
            called['llm'] = True
            return {'ok': True, 'text': '{"winner": "tie", "reason": "r"}', 'model': 'm',
                    'tokens': 1, 'cost': 0.0}

        import backend.services.llm as llm_mod

        monkeypatch.setattr(llm_mod, 'complete', fake_complete)

        class _Req:
            async def json(self):
                return {'battle_id': 'jp1'}

        out = _run(arena_mod.auto_judge_battle(_Req()))
        assert called['llm'] is True and out['winner'] == 'tie'


# ── 3. the reusable HITL enqueue ──────────────────────────────────────────────

class TestEnqueueReview:
    def test_creates_a_decidable_pending_row(self, client):
        iid = enqueue_review(
            'test.r92',
            'a summary for review',
            {'k': 'v', 'n': 3},
            agent_id='tester',
            risk_level='low',
            confidence=0.42,
            requester='jev',
        )
        assert iid.startswith('hitl_')
        con = get_conn()
        try:
            row = con.execute('SELECT * FROM hitl_queue WHERE id=?', (iid,)).fetchone()
        finally:
            con.close()
        assert row['status'] == 'pending'
        assert row['requester'] == 'jev'
        assert row['confidence'] == 0.42
        assert json.loads(row['action_data']) == {'k': 'v', 'n': 3}

        r = client.post(f'/api/hitl/interrupt/{iid}/decide', json={'decision': 'reject'})
        assert r.status_code == 200, r.text
        con = get_conn()
        try:
            assert con.execute('SELECT status FROM hitl_queue WHERE id=?', (iid,)).fetchone()[0] == 'reject'
        finally:
            con.close()
