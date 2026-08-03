"""
Unit Tests — Browser Agent module review
(`tests/unit/test_58_browser_agent_module_review.py`)

Regression guards for real defects found during the Browser Agent review:

1. With neither Chromium NOR an AI provider available, a task still reported
   success. Simulation mode splits the LLM's reply into one "step" per line, so
   the no-provider placeholder ("⚠️ No OPENROUTER_API_KEY set…") was rendered as
   a numbered sequence of COMPLETED browser actions, and the session was
   recorded status='done' with an empty error.
2. The caller wrote status='done' unconditionally after simulation, so even an
   outright failure was persisted as a successful session.
3. An unsafe or malformed start_url was silently swapped for duckduckgo.com —
   asking the agent to visit an internal address produced a normal-looking run
   against a completely different site, with nothing signalling the swap.
4. A single error message ("must be http:// or https://") covered two very
   different failures: a malformed URL and a well-formed one rejected by the
   SSRF policy.
5. Five error paths returned HTTP 200, including DELETE /sessions/{id} echoing
   back a session_id it had not deleted.
"""

from __future__ import annotations

from pathlib import Path

import pytest

from backend.routers.browser_agent import _validate_url

ROOT = Path(__file__).resolve().parents[2]
BROWSER_PY = (ROOT / 'backend' / 'routers' / 'browser_agent.py').read_text(encoding='utf-8')


def executable_source(src: str) -> str:
    """Strip comments AND docstrings so assertions about REMOVED code are not
    satisfied by fix notes that quote the old behaviour."""
    import ast
    import io
    import tokenize

    kept = [t for t in tokenize.generate_tokens(io.StringIO(src).readline) if t.type != tokenize.COMMENT]
    stripped = tokenize.untokenize(kept)
    doc_lines: set[int] = set()
    for node in ast.walk(ast.parse(stripped)):
        if isinstance(node, (ast.Module, ast.ClassDef, ast.FunctionDef, ast.AsyncFunctionDef)):
            body = getattr(node, 'body', [])
            if body and isinstance(body[0], ast.Expr) and isinstance(body[0].value, ast.Constant) \
                    and isinstance(body[0].value.value, str):
                doc_lines.update(range(body[0].lineno, (body[0].end_lineno or body[0].lineno) + 1))
    return '\n'.join(ln for i, ln in enumerate(stripped.splitlines(), 1) if i not in doc_lines)


class TestSimulationDoesNotFakeSuccess:
    """No browser AND no model must not look like a completed run."""

    def test_stub_replies_are_detected(self):
        # Detection is now the shared llm.is_stub() helper rather than a
        # per-caller copy of the provider=='stub' literal.
        assert 'llm_svc.is_stub(result)' in BROWSER_PY
        assert "result.get('ok') is False" in BROWSER_PY

    def test_failure_is_reported_with_actionable_guidance(self):
        assert 'Browser agent cannot run' in BROWSER_PY
        assert 'playwright install chromium' in BROWSER_PY
        assert 'Settings → Connect AI' in BROWSER_PY

    def test_failed_simulation_is_persisted_as_an_error(self):
        assert "_db_update_session(session_id, 'error', [], '', detail)" in BROWSER_PY

    def test_caller_no_longer_overwrites_a_failure_with_done(self):
        assert 'sim_failed' in BROWSER_PY
        assert 'if not sim_failed:' in BROWSER_PY

    def test_stub_path_returns_before_emitting_fake_steps(self):
        """The placeholder must never be split into numbered 'completed' steps."""
        idx = BROWSER_PY.index('async def _simulate_browser_task')
        body = BROWSER_PY[idx:idx + 3500]
        stub_at = body.index('llm_svc.is_stub(result)')
        steps_at = body.index("for i, line in enumerate(lines")
        assert stub_at < steps_at, 'the stub guard must precede step emission'


class TestStartUrlIsNotSilentlySwapped:
    def test_invalid_start_url_is_rejected_not_replaced(self):
        code = executable_source(BROWSER_PY)
        assert "_validate_url(raw_url) or 'https://duckduckgo.com'" not in code

    def test_blocked_start_url_returns_403(self):
        assert 'That start_url is blocked' in BROWSER_PY

    def test_malformed_start_url_returns_400(self):
        assert 'start_url must be a valid http:// or https:// address' in BROWSER_PY


class TestUrlValidation:
    @pytest.mark.parametrize(
        'url',
        [
            'http://169.254.169.254/latest/meta-data/',
            'http://localhost:8787/api/secrets/list',
            'http://127.0.0.1:8787/',
            'file:///etc/passwd',
            'javascript:alert(1)',
            'data:text/html,<script>alert(1)</script>',
            'ftp://example.com/x',
            '',
        ],
    )
    def test_unsafe_urls_are_rejected(self, url):
        assert _validate_url(url) == ''

    def test_public_https_urls_are_accepted(self):
        assert _validate_url('https://example.com/page') == 'https://example.com/page'

    def test_scheme_is_added_when_missing(self):
        assert _validate_url('example.com').startswith('https://')


class TestErrorMessagesDistinguishBlockedFromMalformed:
    def test_blocked_but_wellformed_url_gets_its_own_message(self):
        assert 'That address is blocked' in BROWSER_PY

    def test_malformed_url_keeps_the_scheme_message(self):
        assert 'Invalid URL — must be http:// or https://' in BROWSER_PY


class TestStatusCodes:
    def test_no_bare_ok_false_returns_remain(self):
        assert "return {'ok': False, 'error'" not in BROWSER_PY

    def test_validation_failures_are_400(self):
        assert 'status_code=400' in BROWSER_PY

    def test_blocked_targets_are_403(self):
        assert 'status_code=403' in BROWSER_PY

    def test_missing_session_is_404(self):
        assert 'status_code=404' in BROWSER_PY

    def test_delete_no_longer_echoes_an_undeleted_session_id(self):
        code = executable_source(BROWSER_PY)
        assert "return {'ok': deleted, 'session_id': session_id}" not in code
        assert "return {'ok': True, 'session_id': session_id}" in code
