"""Shared authentication helpers for HTTP and WebSocket boundaries."""
from __future__ import annotations

import hmac
import os


def secure_mode_enabled() -> bool:
    return os.getenv('AGENTIC_OS_SECURE_MODE', 'false').lower() in ('1', 'true', 'yes', 'on')


def configured_token() -> str:
    return os.getenv('AGENTIC_OS_AUTH_TOKEN', '')


def websocket_token_valid(websocket) -> bool:
    """Validate bearer auth from a header or browser-safe query parameter."""
    if not secure_mode_enabled():
        return True
    header = websocket.headers.get('authorization', '')
    query_token = websocket.query_params.get('token', '')
    return hmac.compare_digest(header, f'Bearer {configured_token()}') or hmac.compare_digest(
        query_token, configured_token()
    )


async def require_websocket_auth(websocket) -> bool:
    """Accept only authorized WebSocket connections in secure mode."""
    if websocket_token_valid(websocket):
        return True
    await websocket.close(code=1008, reason='Authentication required')
    return False
