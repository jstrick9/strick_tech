"""
Unit Tests — evals summary and A/B honesty (#141)

The eval runner reports overall_score NULL with pass_fail 'unmeasured'
when the judge model returns nothing usable, so that "not evaluated" can
never render like "evaluated, and it failed". Two consumers broke that
contract:

- /api/evals/summary coerced every AVG() NULL to 0 — so a run set made
  entirely of unmeasured runs displayed as a failing 0/100 average.
- /api/evals/ab-test summed the (None) per-case scores, raising
  TypeError and killing the SSE stream mid-test.

Both must report None/unmeasured instead of inventing a verdict.
"""
import json

import backend.routers.evals as evals_mod


async def _fake_complete_unparseable(messages, **kwargs):
    """A judge that never returns usable JSON — every score comes back None."""
    return {'text': 'MOCK-OK: some prose with no JSON anywhere in it'}


class TestEvalSummaryUnmeasured:
    def test_summary_reports_null_average_when_nothing_measured(self, client, monkeypatch):
        # One unmeasured run: the judge's reply cannot be parsed.
        monkeypatch.setattr('backend.services.llm.complete', _fake_complete_unparseable, raising=False)
        r = client.post('/api/evals/run', json={
            'prompt': 'What is 2+2?',
            'response': 'The answer is 4.',
            'expected': '4',
        })
        assert r.status_code == 200
        body = r.json()
        assert body['overall_score'] is None
        assert body['pass_fail'] == 'unmeasured'

        s = client.get('/api/evals/summary').json()['summary']
        # total counts the run; the average must NOT claim a measured 0.
        assert s['total'] >= 1
        assert s['avg_score'] is None, (
            'a run set of only unmeasured runs must not average to a failing 0/100'
        )

    def test_counters_stay_numeric_on_empty_table(self, client):
        s = client.get('/api/evals/summary').json()['summary']
        for k in ('total', 'passes', 'failures', 'total_cost'):
            assert isinstance(s[k], (int, float)), f'{k} must stay numeric'


class TestABTestUnmeasured:
    def test_ab_survives_unparseable_judge_and_reports_unmeasured(self, client, monkeypatch):
        monkeypatch.setattr('backend.services.llm.complete', _fake_complete_unparseable, raising=False)
        r = client.post('/api/evals/ab-test', json={
            'name': 'unmeasured probe',
            'prompt_a': 'Answer: {{input}}',
            'prompt_b': 'Reply to: {{input}}',
            'inputs': ['one question'],
        })
        assert r.status_code == 200
        frames = [json.loads(l[6:]) for l in r.text.split('\n') if l.startswith('data: ')]
        done = [f for f in frames if f.get('type') == 'ab_done']
        assert done, 'the stream crashed before ab_done — sum() over None scores'
        assert done[0]['avg_a'] is None
        assert done[0]['avg_b'] is None
        assert done[0]['winner'] == 'unmeasured'
