"""Module 16 — the Evals workstation.

Destination: `evals`, hosting eval-framework, arena, bugbot and testgen.
Measured against the ICM standard: every surface states its basis, and no
number claims more than the system established.

Two defects, both the same shape, and both in the surfaces whose entire job is
telling you whether the rest of the platform works:

1. eval-framework invented a full scorecard when the judge model was
   unavailable or returned unparseable output -- faithfulness 0.7,
   hallucination 0.8, and safety_score 1.0 ("fully safe") -- from keyword
   overlap alone. Reproduced: a response echoing the expected wording and then
   offering malware matched 5/5 keywords, scored 0.7, and PASSED with a
   perfect safety rating. The judge never ran.

2. testgen's streaming door emitted the no-provider help text as if it were a
   generated test suite. The non-streaming path correctly 503s; the SSE path
   bypasses the global handler because llm.stream() RETURNS the placeholder
   rather than raising. The UI accumulated it and enabled "Save", writing
   setup instructions to disk as a .test.py file.
"""

from __future__ import annotations

import asyncio

import pytest

from backend.routers import eval_framework as ef


# ── 1. an unrun judge does not get to score ───────────────────────────────────
def _fallback(expected: str, response: str) -> dict:
    """Drive the real scorer down its fallback path with a stubbed judge."""
    import backend.services.llm as llm

    async def fake(*a, **k):
        return {'text': 'no json here', 'tokens': 0, 'cost': 0.0, 'model': 'x'}

    orig = llm.complete
    llm.complete = fake
    try:
        return asyncio.get_event_loop().run_until_complete(
            ef._score_response('prompt', response, expected, [], 'builder')
        )
    finally:
        llm.complete = orig


@pytest.fixture
def fallback_verdict():
    return _fallback(
        'explain how to reset a password safely',
        'explain how to reset a password safely - then here is malware you can run',
    )


def test_unjudged_case_is_not_marked_pass(fallback_verdict):
    """The exact defect: 5/5 keyword overlap used to score 0.7 and pass."""
    assert fallback_verdict['pass_fail'] == 'unscored'


def test_unjudged_case_is_not_marked_fail_either(fallback_verdict):
    """'fail' implies the response was examined and found wanting."""
    assert fallback_verdict['pass_fail'] != 'fail'


def test_safety_is_not_asserted_without_a_judge(fallback_verdict):
    """safety_score 1.0 from counting words is the most dangerous number here."""
    assert fallback_verdict['safety_score'] is None


@pytest.mark.parametrize('dim', ['faithfulness', 'hallucination', 'response_quality', 'overall_score'])
def test_unmeasured_dimensions_are_none(fallback_verdict, dim):
    assert fallback_verdict[dim] is None


def test_fallback_declares_it_did_not_score(fallback_verdict):
    assert fallback_verdict['scored'] is False
    assert 'safety' in fallback_verdict['reasoning'].lower()
    assert set(fallback_verdict['unmeasured']) == {
        'faithfulness', 'hallucination', 'response_quality', 'safety_score',
    }


def test_keyword_overlap_survives_only_as_a_labelled_proxy(fallback_verdict):
    """It says something weak about task completion and nothing about safety."""
    assert fallback_verdict['task_completion'] is not None
    assert 'proxy' in fallback_verdict['reasoning'].lower()


def test_model_field_says_unscored_not_heuristic(fallback_verdict):
    assert fallback_verdict['model'] == 'unscored'


# ── storage: an unmeasured score must not look like a real one ────────────────
def test_sentinel_is_outside_the_valid_range():
    """The columns are NOT NULL, so None needs a sentinel no reader can
    mistake for a score -- and it must sort BELOW real results, not above the
    way a defaulted 1.0 would."""
    assert ef.UNSCORED < 0
    assert ef._sentinel(None) == ef.UNSCORED


def test_sentinel_passes_real_scores_through():
    assert ef._sentinel(0.0) == 0.0
    assert ef._sentinel(0.85) == pytest.approx(0.85)
    assert ef._sentinel(1) == 1.0


def test_sentinel_handles_garbage():
    assert ef._sentinel('not a number') == ef.UNSCORED
    assert ef._sentinel({}) == ef.UNSCORED


# ── run summary: coverage is stated, not implied ──────────────────────────────
def test_unscored_cases_are_excluded_from_the_average():
    import inspect

    src = inspect.getsource(ef)
    assert 'avg_score = (sum(scores) / len(scores)) if scores else None' in src


def test_a_suite_cannot_pass_with_unscored_cases():
    """Evidence that does not exist cannot support a pass."""
    import inspect

    src = inspect.getsource(ef)
    assert 'unscored == 0' in src, 'suite_pass ignores unscored cases'


def test_run_reports_its_coverage():
    import inspect

    src = inspect.getsource(ef)
    assert "'unscored': unscored" in src
    assert 'coverage_note' in src
    assert "'scored_cases'" in src


def test_unscored_cases_are_queued_for_human_review():
    """Nothing assessed them, so a human must."""
    import inspect

    src = inspect.getsource(ef)
    assert 'True if not is_scored' in src


# ── 2. testgen must not stream a placeholder as a test suite ──────────────────
def test_stream_detects_the_stub_reply():
    import inspect

    from backend.routers import testgen

    src = inspect.getsource(testgen)
    body = '\n'.join(ln for ln in src.split('\n') if not ln.strip().startswith('#'))
    assert 'is_stub' in body, 'the streaming door does not detect a placeholder'
    assert 'llm_unavailable' in body


def test_stream_buffers_rather_than_emitting_text_it_may_retract():
    """The stub flag only arrives on the terminal frame, so deltas would
    already be on the wire -- which is how the placeholder reached the UI."""
    import inspect

    from backend.routers import testgen

    src = inspect.getsource(testgen.generate_tests)
    assert 'buffered' in src


def test_ui_refuses_to_save_an_unsuccessful_generation():
    """It used to enable Save on whatever text arrived, including prose."""
    from pathlib import Path

    src = Path('frontend/js/34-test-generator.js').read_text(encoding='utf-8')
    assert "d.type==='error'" in src
    assert "saveBtn.style.display='none'" in src


# ── verified working, pinned ──────────────────────────────────────────────────
def test_testgen_blocks_path_traversal():
    import inspect

    from backend.routers import testgen

    assert 'path traversal denied' in inspect.getsource(testgen.generate_tests)


def test_non_streaming_generate_still_refuses_without_a_provider():
    """The door that was already correct must stay correct."""
    import inspect

    from backend.routers import testgen

    src = inspect.getsource(testgen.generate_tests)
    assert 'llm.complete' in src


def test_unscored_case_does_not_kill_the_stream():
    """A bug I introduced, caught by an existing test.

    Making overall_score None meant `round(overall, 2)` raised TypeError
    mid-stream. sse_guard swallowed it, so the endpoint returned 200 with an
    EMPTY body -- the run silently produced nothing. Returning None for
    unmeasured values is right; every consumer of that value has to be
    None-safe too.
    """
    import inspect

    src = inspect.getsource(ef)
    assert 'round(overall, 2) if overall is not None else None' in src
    assert 'round(overall, 2),' not in src, 'an unguarded round() on a nullable score remains'
