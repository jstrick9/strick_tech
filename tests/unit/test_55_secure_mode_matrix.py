"""
Secure-deployment HTTP surface matrix.

The secure-mode bearer gate used to be `path.startswith('/api/')` — but the
A2A protocol router mounts at the ROOT, so POST /a2a/{agent_id} (task
submission = agent invocation), the SSE task stream, the agent cards, and
the interactive docs all answered WITHOUT the token while every /api/ route
401'd. Verified live against a secure-mode server: unauthenticated
tasks/send created a task, ran the agent, and returned its artifacts.

The decision now lives in security_auth.secure_path_is_public — an explicit
allowlist (app shell, static, preview, health probes) so any path outside
it, including routers added later, is locked by default. These tests pin
the matrix; the live end-to-end proof ran against a real secure-mode
server (see the commit message for #215).
"""
import pytest

from backend.security_auth import (
    SECURE_PUBLIC_EXACT,
    secure_path_is_public,
)

API_PUBLIC = frozenset({'/api/system/health', '/api/system/stats'})


def _public(path):
    return secure_path_is_public(path, API_PUBLIC)


class TestSecureModePublicSurface:
    """Exactly what the shell needs to load, plus health probes. Nothing else."""

    @pytest.mark.parametrize('path', sorted(SECURE_PUBLIC_EXACT))
    def test_shell_roots_public(self, path):
        assert _public(path) is True

    @pytest.mark.parametrize('path', [
        '/static/dist/app.js',
        '/static/dist/00-csrf.js',
        '/preview/my-app/index.html',
        '/preview/deep/nested/path/style.css',
        '/api/system/health',
        '/api/system/stats',
    ])
    def test_static_preview_health_public(self, path):
        assert _public(path) is True

    @pytest.mark.parametrize('path', [
        # the API surface
        '/api/agents', '/api/agents/orchestrator', '/api/openapi.json',
        '/api/webhooks/github', '/api/auth/login',
        # the A2A machine surface — the original hole
        '/a2a/orchestrator', '/a2a/researcher',
        '/a2a/orchestrator/stream/task_abc123',
        '/a2a/orchestrator/card',
        '/a2a/orchestrator/.well-known/agent.json',
        '/.well-known/agent.json',
        # interactive docs (schema behind them was already gated)
        '/docs', '/redoc',
        # a router mounted at a brand-new root path must fail closed
        '/future-router/action', '/experimental',
    ])
    def test_everything_else_gated(self, path):
        assert _public(path) is False

    def test_allowlist_is_exact_not_prefix(self):
        # /static-evil or /preview-admin must not inherit the prefix pass
        assert _public('/static-other/thing') is False
        assert _public('/previewX') is False
        assert _public('/manifest.json.bak') is False


class TestAgentCardAdvertisesRealAuth:
    """The A2A card's authentication.schemes must match what the middleware
    enforces — advertising 'none' while the server 401s breaks interop."""

    def _card(self, agent_id='gap_card_agent'):
        from backend.routers.a2a import _build_agent_card
        from backend.services.memory_db import get_conn

        con = get_conn()
        try:
            con.execute(
                "INSERT OR IGNORE INTO agents (id, name, role, status) "
                "VALUES (?, 'Card Test', 'general-purpose', 'active')",
                (agent_id,),
            )
            con.commit()
        finally:
            con.close()
        card = _build_agent_card(agent_id)
        assert card, f"card builder returned empty for {agent_id}"
        return card

    def test_local_mode_advertises_none_and_bearer(self, monkeypatch):
        monkeypatch.setenv('AGENTIC_OS_SECURE_MODE', 'false')
        assert self._card()['authentication']['schemes'] == ['none', 'bearer']

    def test_secure_mode_advertises_bearer_only(self, monkeypatch):
        monkeypatch.setenv('AGENTIC_OS_SECURE_MODE', 'true')
        monkeypatch.setenv('AGENTIC_OS_AUTH_TOKEN', 'test-token')
        assert self._card()['authentication']['schemes'] == ['bearer']
