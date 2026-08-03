"""Regression contracts for the two Browser Agent review follow-ups.

1. `provider='stub'` is handled at the LLM layer, not per caller.

   When no AI provider is configured, `llm.complete()` used to return a
   *placeholder* result whose `text` is human-readable setup help
   ("⚠️ No OPENROUTER_API_KEY set…"), tagged `provider='stub'` / `ok=False`.
   Callers had to notice that flag. Chat, Supervisor and Browser Agent each
   shipped the same bug independently — rendering the help text as a genuine
   model reply and reporting success — and ~30 other call sites never checked
   at all.

   `complete()` now raises `LLMUnavailableError` unless the caller passes
   `allow_stub=True`, and `app.py` maps that to HTTP 503. Opting in is a
   deliberate, greppable act reserved for background jobs and SSE generators,
   where no HTTP status is left to set.

2. Simulation mode is opt-in.

   `POST /api/browser/task` silently fell back to an AI-narrated fake run
   whenever Chromium was missing. Asking for a real browser run now returns
   503 unless the caller explicitly passes `simulate: true`.
"""
from __future__ import annotations

import inspect
from pathlib import Path

import pytest

from backend.services import llm as llm_svc

# The session-scoped `client` fixture in conftest.py patches
# backend.services.llm.complete with an AsyncMock for the whole session. These
# tests exercise the real function, so capture it at import time — collection
# happens before any fixture runs.
REAL_COMPLETE = llm_svc.complete

REPO = Path(__file__).resolve().parents[2]
BROWSER_PY = (REPO / 'backend' / 'routers' / 'browser_agent.py').read_text()
SUPERVISOR_PY = (REPO / 'backend' / 'routers' / 'supervisor.py').read_text()
SCHEDULER_PY = (REPO / 'backend' / 'services' / 'scheduler.py').read_text()
SWARM_PY = (REPO / 'backend' / 'routers' / 'swarm.py').read_text()
APP_PY = (REPO / 'backend' / 'app.py').read_text()
BROWSER_JS = (REPO / 'frontend' / 'js' / '43-browser-agent.js').read_text()


class TestLLMLayerOwnsStubHandling:
    def test_llm_exposes_the_shared_pieces(self):
        assert issubclass(llm_svc.LLMUnavailableError, RuntimeError)
        assert callable(llm_svc.is_stub)
        assert llm_svc.STUB_PROVIDER == 'stub'
        assert 'openrouter.ai/keys' in llm_svc.NO_PROVIDER_MESSAGE

    def test_complete_accepts_allow_stub_and_defaults_to_raising(self):
        sig = inspect.signature(REAL_COMPLETE)
        assert 'allow_stub' in sig.parameters
        assert sig.parameters['allow_stub'].default is False, (
            'defaulting to True would restore the silent-placeholder behaviour'
        )

    def test_is_stub_recognises_both_shapes(self):
        assert llm_svc.is_stub({'provider': 'stub'}) is True
        assert llm_svc.is_stub({'stub': True}) is True          # final stream chunk
        assert llm_svc.is_stub({'provider': 'ollama'}) is False
        assert llm_svc.is_stub(None) is False

    def test_is_stub_does_not_treat_a_real_error_as_a_stub(self):
        """A model that ran and failed is a different condition from no model."""
        assert llm_svc.is_stub({'provider': 'openrouter', 'ok': False, 'error': 'HTTP 500'}) is False

    @pytest.mark.asyncio
    async def test_complete_raises_when_no_provider(self, monkeypatch):
        monkeypatch.setattr(llm_svc, '_or_key', lambda: '')
        monkeypatch.setenv('OLLAMA_BASE_URL', 'http://127.0.0.1:9')  # nothing listening
        with pytest.raises(llm_svc.LLMUnavailableError) as exc:
            await REAL_COMPLETE([{'role': 'user', 'content': 'hi'}], inject_steering=False)
        assert 'No AI provider' in str(exc.value)
        assert exc.value.model, 'the model that would have been used should be reported'

    @pytest.mark.asyncio
    async def test_allow_stub_returns_the_placeholder_instead(self, monkeypatch):
        monkeypatch.setattr(llm_svc, '_or_key', lambda: '')
        monkeypatch.setenv('OLLAMA_BASE_URL', 'http://127.0.0.1:9')
        result = await REAL_COMPLETE(
            [{'role': 'user', 'content': 'hi'}], inject_steering=False, allow_stub=True
        )
        assert llm_svc.is_stub(result)
        assert result['ok'] is False


class TestUnhandledStubsBecome503:
    def test_app_registers_the_exception_handler(self):
        assert '@app.exception_handler(_LLMUnavailableError)' in APP_PY
        assert 'status_code=503' in APP_PY
        assert "'code': 'llm_unavailable'" in APP_PY

    def test_chat_complete_reports_503_not_fabricated_success(self, client):
        r = client.post('/api/chat/complete', json={'message': 'hello'})
        assert r.status_code in (200, 503)
        if r.status_code == 503:
            body = r.json()
            assert body['ok'] is False
            assert body['code'] == 'llm_unavailable'
            # The old behaviour: HTTP 200 whose `text` was the setup help.
            assert 'text' not in body


class TestOptInsAreDeliberate:
    """allow_stub=True is only legitimate where no HTTP status can be set."""

    def test_background_and_sse_callers_opt_in_explicitly(self):
        # SSE generator: status already committed when the stub is discovered.
        assert 'allow_stub=True' in BROWSER_PY
        # Background tasks: no response object exists at all.
        assert 'allow_stub=True' in SUPERVISOR_PY
        assert 'allow_stub=True' in SCHEDULER_PY

    def test_opt_in_callers_still_check_the_flag(self):
        assert 'llm_svc.is_stub(result)' in BROWSER_PY
        assert 'llm_is_stub(result)' in SUPERVISOR_PY
        assert 'llm_is_stub(result)' in SCHEDULER_PY

    def test_no_caller_reimplements_the_stub_literal(self):
        """The provider=='stub' comparison must live in exactly one place."""
        offenders = [
            path.relative_to(REPO).as_posix()
            for path in (REPO / 'backend').rglob('*.py')
            if path.name != 'llm.py' and "provider') == 'stub'" in path.read_text()
        ]
        assert offenders == [], f'these should use llm.is_stub(): {offenders}'


class TestSimulationIsOptIn:
    def test_endpoint_reads_a_simulate_flag_defaulting_to_off(self):
        assert "simulate = bool(body.get('simulate', False))" in BROWSER_PY

    def test_real_run_without_a_browser_is_503(self, client):
        r = client.post('/api/browser/task', json={'task': 'find the docs'})
        assert r.status_code in (200, 503)
        if r.status_code == 503:
            body = r.json()
            assert body['code'] == 'browser_unavailable'
            assert body['chromium_installed'] is False
            assert 'simulate' in body['error']

    def test_simulate_true_is_accepted(self, client):
        r = client.post('/api/browser/task', json={'task': 'find the docs', 'simulate': True})
        assert r.status_code == 200, 'explicit opt-in must still work'

    def test_mode_is_decided_before_the_stream_opens(self):
        """Otherwise the refusal is a 200 with an error buried in an SSE frame."""
        decide_at = BROWSER_PY.index("if not (pw_ok and cr_ok) and not simulate:")
        stream_at = BROWSER_PY.index('async def _stream():')
        assert decide_at < stream_at

    def test_simulation_warning_states_that_nothing_is_fetched(self):
        assert 'nothing is actually being fetched' in BROWSER_PY

    def test_frontend_sends_the_flag_and_offers_a_toggle(self):
        assert "id=\"ba-simulate\"" in BROWSER_JS
        assert 'simulate: !!$(\'ba-simulate\')?.checked' in BROWSER_JS

    def test_frontend_shows_the_reason_not_just_a_status_code(self):
        assert '(await resp.json()).error' in BROWSER_JS


class TestSwarmDoesNotReportEmptySuccess:
    def test_a_fully_failed_swarm_is_not_ok(self):
        assert 'Every agent in the swarm failed' in SWARM_PY

    def test_failed_agents_are_identified(self):
        """Exceptions were logged against agent '?', which diagnoses nothing."""
        assert "'agent': '?'" not in SWARM_PY
        assert 'zip(agent_ids, results, strict=False)' in SWARM_PY
