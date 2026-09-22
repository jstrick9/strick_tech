"""Shared authentication helpers for HTTP and WebSocket boundaries."""
from __future__ import annotations

import hmac
import os


def secure_mode_enabled() -> bool:
    return os.getenv('AGENTIC_OS_SECURE_MODE', 'false').lower() in ('1', 'true', 'yes', 'on')


# What stays reachable without the bearer token in secure mode: the app shell
# (so it can load and then authenticate its API calls), static assets, the
# user-authored /preview/ documents (CSP'd, no APIs), and the health probes.
# Everything else — /api/*, the /a2a/ JSON-RPC surface, agent cards, and the
# interactive docs — requires the token. Allowlist, not denylist: a router
# mounted at a new root path is locked by default.
SECURE_PUBLIC_EXACT = frozenset(
    {'/', '/favicon.ico', '/manifest.json', '/sw.js'}
)
SECURE_PUBLIC_PREFIXES = ('/static/', '/preview/')


def secure_path_is_public(path: str, api_public_paths: frozenset) -> bool:
    """True when `path` may be served without the bearer token in secure mode."""
    if path in api_public_paths or path in SECURE_PUBLIC_EXACT:
        return True
    return path.startswith(SECURE_PUBLIC_PREFIXES)


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
