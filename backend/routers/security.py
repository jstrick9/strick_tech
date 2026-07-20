"""
Agentic OS — Security Router (/api/security)
Provides CSRF token generation/validation and request ID trace tracking.
"""

from __future__ import annotations

import secrets
import time
import uuid
from typing import Optional, Union, Any, Dict, List, Tuple, Set, Callable, AsyncGenerator

from fastapi import APIRouter, Header, Request, Response
from pydantic import BaseModel

router = APIRouter(prefix='/api/security', tags=['security'])

# Global store for valid CSRF tokens with expiration (24 hours)
_CSRF_TOKENS: dict[str, float] = {}
_TOKEN_TTL = 86400  # 24 hours


class CSRFValidateRequest(BaseModel):
    """Payload for CSRF token validation requests."""

    csrf_token: str


def _clean_expired_tokens() -> None:
    """Purge expired CSRF tokens from the global store."""
    now = time.time()
    expired = [tok for tok, ts in _CSRF_TOKENS.items() if now - ts > _TOKEN_TTL]
    for tok in expired:
        _CSRF_TOKENS.pop(tok, None)


@router.get('/csrf-token')
async def get_csrf_token(response: Response) -> dict[str, Any]:
    """Generate and return a new secure CSRF token, also setting an HttpOnly cookie."""
    _clean_expired_tokens()
    token = secrets.token_urlsafe(32)
    _CSRF_TOKENS[token] = time.time()
    response.set_cookie(
        key='agentic_os_csrf',
        value=token,
        max_age=_TOKEN_TTL,
        httponly=False,  # Accessible to SPA JavaScript
        samesite='lax',
    )
    return {'ok': True, 'csrf_token': token, 'expires_in': _TOKEN_TTL}


@router.post('/validate-csrf')
async def validate_csrf_token(
    payload: CSRFValidateRequest,
    x_csrf_token:Optional[ str] = Header(None, alias='X-CSRF-Token'),
) -> dict[str, Any]:
    """Validate a provided CSRF token against active valid session tokens."""
    _clean_expired_tokens()
    token_to_check = payload.csrf_token or x_csrf_token
    if not token_to_check or token_to_check not in _CSRF_TOKENS:
        return {'ok': False, 'valid': False, 'error': 'Invalid or expired CSRF token'}
    return {'ok': True, 'valid': True}


@router.get('/trace-context')
async def get_trace_context(request: Request) -> dict[str, Any]:
    """Retrieve the current request ID and tracing context attributes."""
    request_id = getattr(request.state, 'request_id', None) or uuid.uuid4().hex
    return {
        'ok': True,
        'request_id': request_id,
        'client_ip': request.client.host if request.client else 'unknown',
        'path': request.url.path,
        'timestamp': time.time(),
    }
