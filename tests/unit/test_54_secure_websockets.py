"""Secure deployment WebSocket authentication regression tests."""
import asyncio

from backend.security_auth import require_websocket_auth


class FakeWebSocket:
    def __init__(self, headers=None, query=None):
        self.headers = headers or {}
        self.query_params = query or {}
        self.closed = None

    async def close(self, code, reason):
        self.closed = (code, reason)


def test_secure_websocket_rejects_missing_token(monkeypatch):
    monkeypatch.setenv('AGENTIC_OS_SECURE_MODE', 'true')
    monkeypatch.setenv('AGENTIC_OS_AUTH_TOKEN', 'test-token')
    ws = FakeWebSocket()
    assert asyncio.run(require_websocket_auth(ws)) is False
    assert ws.closed == (1008, 'Authentication required')


def test_secure_websocket_accepts_query_token(monkeypatch):
    monkeypatch.setenv('AGENTIC_OS_SECURE_MODE', 'true')
    monkeypatch.setenv('AGENTIC_OS_AUTH_TOKEN', 'test-token')
    ws = FakeWebSocket(query={'token': 'test-token'})
    assert asyncio.run(require_websocket_auth(ws)) is True
    assert ws.closed is None


def test_local_websocket_mode_remains_open(monkeypatch):
    monkeypatch.setenv('AGENTIC_OS_SECURE_MODE', 'false')
    monkeypatch.delenv('AGENTIC_OS_AUTH_TOKEN', raising=False)
    ws = FakeWebSocket()
    assert asyncio.run(require_websocket_auth(ws)) is True
