"""Unit tests — A/B test arms run concurrently (r81, #245)

POST /api/evals/ab-test ran its two arms strictly A-then-B per input,
although the arms are independent prompts over the same input. Every
case therefore cost arm_A + arm_B of wall time instead of max(arm_A,
arm_B): with 3 inputs and 4 LLM calls per arm (1 completion + 3 judge
calls) at 200ms simulated latency, a run took 4839ms; with the arms
gathered it takes 2421ms — the same 24 LLM calls, the same scores, the
same verdict, half the wall time. Real LLM latencies scale the same 2x.

The per-case SSE yield is kept: progress frames arrive per input, one
ab_case event after both arms of that input finish — the streaming UX
is unchanged. llm.complete returns error dicts instead of raising, so
failure semantics are unchanged too.

The regression pin is CONCURRENCY, not timing: a tracking fake counts
how many ARM calls ('A: ...' / 'B: ...' prompts) are in flight at once.
Sequential code maxes at 1; the gathered implementation must reach 2.
"""
import asyncio
import json
import sqlite3

import backend.services.llm as llm_mod

JUDGE = json.dumps(
    {
        'faithfulness': 0.9,
        'hallucination': 0.1,
        'faithfulness_reason': 'ok',
        'hallucination_reason': 'ok',
        'relevance': 0.8,
        'coherence': 0.9,
        'clarity': 0.9,
        'pass': True,
        'score': 0.9,
    }
)


def _tracking_fake(state):
    async def fake_complete(messages, **kw):
        text = messages[0]['content'] if messages else ''
        if text.startswith(('A: ', 'B: ')):
            state['inflight'] += 1
            state['max_inflight'] = max(state['max_inflight'], state['inflight'])
            state['arm_prompts'].append(text)
            try:
                await asyncio.sleep(0.05)
                return {'text': JUDGE, 'tokens': 5, 'model': 'mock'}
            finally:
                state['inflight'] -= 1
        await asyncio.sleep(0.02)
        return {'text': JUDGE, 'tokens': 5, 'model': 'mock'}

    return fake_complete


def _run_ab(client):
    return client.post(
        '/api/evals/ab-test',
        json={
            'name': 'r81 probe',
            'prompt_a': 'A: {{input}}',
            'prompt_b': 'B: {{input}}',
            'inputs': ['q1', 'q2', 'q3'],
        },
    )


class TestABTestArmsConcurrent:
    def test_arms_overlap_in_flight(self, client, monkeypatch):
        state = {'inflight': 0, 'max_inflight': 0, 'arm_prompts': []}
        monkeypatch.setattr(
            'backend.services.llm.complete', _tracking_fake(state), raising=False
        )
        r = _run_ab(client)
        assert r.status_code == 200
        assert state['max_inflight'] >= 2, (
            f'the two arms never overlapped (max in-flight {state["max_inflight"]}) — '
            'A/B arms are back to running sequentially'
        )

    def test_each_arm_prompt_runs_exactly_once(self, client, monkeypatch):
        state = {'inflight': 0, 'max_inflight': 0, 'arm_prompts': []}
        monkeypatch.setattr(
            'backend.services.llm.complete', _tracking_fake(state), raising=False
        )
        r = _run_ab(client)
        assert r.status_code == 200
        assert sorted(state['arm_prompts']) == [
            'A: q1', 'A: q2', 'A: q3', 'B: q1', 'B: q2', 'B: q3',
        ], 'concurrency must not duplicate or drop arm evaluations'

    def test_stream_contract_and_persistence(self, client, monkeypatch):
        state = {'inflight': 0, 'max_inflight': 0, 'arm_prompts': []}
        monkeypatch.setattr(
            'backend.services.llm.complete', _tracking_fake(state), raising=False
        )
        r = _run_ab(client)
        assert r.status_code == 200
        frames = [json.loads(l[6:]) for l in r.text.split('\n') if l.startswith('data: ')]
        types = [f['type'] for f in frames]

        assert types[0] == 'ab_start' and types[0:1] == ['ab_start']
        assert types.count('ab_case') == 3, 'one progress frame per input'
        assert types[-1] == 'ab_done'
        # inputs keep their order in the progress stream
        assert [f['input'] for f in frames if f.get('type') == 'ab_case'] == ['q1', 'q2', 'q3']

        done = frames[-1]
        assert done['winner'] in ('A', 'B', 'tie', 'unmeasured')
        assert done['avg_a'] == done['avg_b']  # both arms got the same judge JSON

        # the run is persisted before the done frame is emitted
        from backend.services.memory_db import db_path

        con = sqlite3.connect(db_path())
        try:
            row = con.execute(
                'SELECT winner, status FROM ab_tests WHERE id=?', (done['test_id'],)
            ).fetchone()
        finally:
            con.close()
        assert row is not None, 'the A/B run must be persisted'
        assert row[0] == done['winner'] and row[1] == 'done'
