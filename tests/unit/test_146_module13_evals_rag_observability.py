"""Module 13 regression tests — evals, RAG, knowledge-graph, observability.

1. Every eval judge dimension fell back to an invented mid-range number when
   the model's reply was not parseable JSON -- routine, since models wrap JSON
   in prose. With all four unparseable the eval reported task 0.7, faith 0.7,
   halluc 0.3, quality 70 -> overall 71 -> "pass". An evaluation that measured
   nothing graded the response a PASS.
2. RAG's /eval had the identical defect (second door): 0.7/0.7 -> overall 70
   -> grade "C". Verified live: an answer claiming cats communicate by radio
   waves scored 0.7 faithfulness and a C.
3. /observability/dora reported "12 in 30 days", "0.0% error rate" and grade
   "Elite" with total_traces = 0:
     - "12 deployments" counted the 12 BUILT-IN seeded agents
     - errors/max(total,1) is 0/1 with no data, so an unmeasured failure rate
       was reported as a perfect one
     - Elite is DORA's top tier, awarded for having measured nothing
     - mttr_ms was avg_latency * 2, an invented multiplier labelled "Estimated"
"""

from __future__ import annotations

from unittest.mock import AsyncMock, patch

import pytest

import backend.services.llm as llm
from backend.routers import evals, observability, rag


# ── 1. eval scoring must not invent ───────────────────────────────────────────
@pytest.mark.parametrize('raw,expected', [
    (None, None), ('', None), ('abc', None), (float('nan'), None),
    (0.9, 0.9), ('0.5', 0.5), (2.0, 1.0), (-1.0, 0.0),
])
def test_score_or_none_coercion(raw, expected):
    assert evals._score_or_none(raw) == expected


def test_score_or_none_on_a_100_scale():
    assert evals._score_or_none(88, scale=100) == 88
    assert evals._score_or_none('nope', scale=100) is None
    assert evals._score_or_none(150, scale=100) == 100


async def _judge(text):
    with patch.object(llm, 'complete', new=AsyncMock(
        return_value={'ok': True, 'text': text, 'provider': 'openrouter'})):
        return await evals._eval_response('do X', 'I did X')


@pytest.mark.asyncio
async def test_unparseable_judge_does_not_produce_a_pass():
    """The exact defect: 71/"pass" from an eval that measured nothing."""
    out = await _judge('Looks fine to me.')
    assert out['overall_score'] is None
    assert out['pass_fail'] == 'unmeasured'
    assert out['task_completion'] is None
    assert out['faithfulness'] is None
    assert out['response_quality'] is None


@pytest.mark.asyncio
async def test_unparseable_judge_reports_what_was_missing():
    out = await _judge('Looks fine to me.')
    assert set(out['unmeasured']) >= {'task_completion', 'faithfulness', 'response_quality'}
    assert any(i['type'] == 'unmeasured' for i in out['issues'])


@pytest.mark.asyncio
async def test_partial_coverage_is_below_the_floor():
    """One dimension out of five is not enough to state a verdict."""
    out = await _judge('{"task_completion":0.9}')
    assert out['overall_score'] is None
    assert out['pass_fail'] == 'unmeasured'
    assert out['task_completion'] == 0.9  # still reported, just not graded


@pytest.mark.asyncio
async def test_sufficient_coverage_grades_normally():
    out = await _judge('{"faithfulness":0.9,"hallucination":0.1,"task_completion":0.9}')
    assert out['overall_score'] is not None
    assert out['pass_fail'] == 'pass'
    assert out['measured_weight_pct'] >= 50


@pytest.mark.asyncio
async def test_a_full_judge_reply_scores_all_dimensions():
    out = await _judge('{"faithfulness":0.9,"hallucination":0.05,"task_completion":0.95,"quality":88}')
    assert out['unmeasured'] == []
    assert out['measured_weight_pct'] == 100
    assert out['overall_score'] >= 85


@pytest.mark.asyncio
async def test_a_bad_response_still_fails():
    """Honesty must not become leniency."""
    out = await _judge('{"faithfulness":0.1,"hallucination":0.9,"task_completion":0.1,"quality":10}')
    assert out['pass_fail'] == 'fail'
    assert out['overall_score'] < 50


# ── 2. RAG eval — the second door ─────────────────────────────────────────────
class _Req:
    def __init__(self, body):
        self._b = body

    async def json(self):
        return self._b


_RAG_BODY = {
    'query': 'what sound do cats make',
    'answer': 'Cats communicate exclusively via radio waves, invented in 1987 by Belgium.',
    'contexts': ['Cats purr when content.'],
}


@pytest.mark.asyncio
async def test_rag_eval_does_not_invent_a_c_grade():
    with patch.object(llm, 'complete', new=AsyncMock(
        return_value={'ok': True, 'text': "I'd rate this poorly.", 'provider': 'openrouter'})):
        out = await rag.eval_rag('p', _Req(_RAG_BODY))
    assert out['faithfulness'] is None
    assert out['answer_relevancy'] is None
    assert out['overall_rag_score'] is None
    assert out['grade'] is None
    assert set(out['unmeasured']) == {'faithfulness', 'answer_relevancy'}
    assert out['note']


@pytest.mark.asyncio
async def test_rag_eval_grades_a_real_judgement():
    good = '{"faithfulness":0.1,"relevancy":0.2,"unsupported_claims":["radio waves"]}'
    with patch.object(llm, 'complete', new=AsyncMock(
        return_value={'ok': True, 'text': good, 'provider': 'openrouter'})):
        out = await rag.eval_rag('p', _Req(_RAG_BODY))
    assert out['grade'] == 'F'
    assert out['overall_rag_score'] == 15
    assert out['unmeasured'] == []


@pytest.mark.asyncio
async def test_rag_eval_partial_judgement_uses_what_it_has():
    with patch.object(llm, 'complete', new=AsyncMock(
        return_value={'ok': True, 'text': '{"faithfulness":0.8}', 'provider': 'openrouter'})):
        out = await rag.eval_rag('p', _Req(_RAG_BODY))
    assert out['faithfulness'] == 0.8
    assert out['answer_relevancy'] is None
    assert out['unmeasured'] == ['answer_relevancy']
    assert out['overall_rag_score'] == 80


# ── 3. DORA must not award Elite for no data ──────────────────────────────────
def _dora(monkeypatch, traces, errors, custom_agents):
    """Run dora_metrics against a stubbed DB."""
    class _Con:
        def __init__(self):
            self.calls = 0

        def execute(self, sql, params=()):
            self._sql = sql
            return self

        def fetchone(self):
            s = self._sql
            if 'FROM agents' in s:
                return [custom_agents]
            if "status='error'" in s:
                return [errors]
            if 'COUNT(*) FROM obs_traces' in s:
                return [traces]
            if 'AVG(total_latency_ms)' in s:
                return [1200 if traces else None]
            return [0]

        def fetchall(self):
            return [[1400]] if traces else []

        def close(self):
            pass

    import backend.services.memory_db as mdb
    monkeypatch.setattr(mdb, 'get_conn', lambda *a, **k: _Con())
    return observability.dora_metrics(30)


def test_dora_does_not_grade_an_empty_install(monkeypatch):
    """The exact defect: Elite with zero traces."""
    out = _dora(monkeypatch, traces=0, errors=0, custom_agents=0)
    assert out['grade'] is None
    assert out['total_traces'] == 0
    assert 'Not enough data' in out['grade_basis']


def test_dora_failure_rate_is_null_not_zero(monkeypatch):
    """0 errors out of 0 runs is unknown, not perfect."""
    out = _dora(monkeypatch, traces=0, errors=0, custom_agents=0)
    assert out['change_failure_rate']['value'] is None
    assert out['change_failure_rate']['label'] == 'Not measured'


def test_dora_excludes_builtin_agents_from_deployments(monkeypatch):
    """'12 deployments' was the 12 seeded built-ins."""
    import inspect

    src = inspect.getsource(observability.dora_metrics)
    src = '\n'.join(ln for ln in src.split('\n') if not ln.strip().startswith('#'))
    assert 'DEFAULT_AGENTS' in src
    assert 'NOT IN' in src


def test_dora_will_not_grade_activity_without_deployments(monkeypatch):
    out = _dora(monkeypatch, traces=20, errors=1, custom_agents=0)
    assert out['grade'] is None
    assert 'no deployments' in out['grade_basis'].lower()


def test_dora_grades_real_data(monkeypatch):
    out = _dora(monkeypatch, traces=20, errors=1, custom_agents=1)
    assert out['grade'] == 'High'          # 5% CFR
    assert out['change_failure_rate']['value'] == 5.0
    assert '20 run(s)' in out['grade_basis']


def test_dora_elite_still_reachable(monkeypatch):
    out = _dora(monkeypatch, traces=100, errors=1, custom_agents=3)
    assert out['grade'] == 'Elite'


def test_dora_mttr_is_not_an_invented_multiple(monkeypatch):
    """mttr_ms was avg_latency * 2 labelled 'Estimated'."""
    out = _dora(monkeypatch, traces=20, errors=1, custom_agents=1)
    assert out['mttr_ms']['value'] is None
    assert out['mttr_ms']['label'] == 'Not tracked'


# ── the UI must not turn "unmeasured" into a verdict ──────────────────────────
def test_dora_ui_does_not_default_a_null_grade_to_low():
    from pathlib import Path

    src = Path('frontend/js/05-evals-observability.js').read_text(encoding='utf-8')
    assert "[dora.grade||'Low']" not in src, 'null grade must not colour as Low'
    assert "${m?.value||0}" not in src, 'a null metric must not render as 0'
    assert 'grade_basis' in src, 'the UI should explain why it is not graded'
