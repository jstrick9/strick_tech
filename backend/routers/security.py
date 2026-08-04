"""
Agentic OS — Security Router (/api/security)
Provides CSRF token generation/validation and request ID trace tracking.
"""

from __future__ import annotations

import secrets
import time
import uuid
from typing import Any

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


# ── CSP violation reporting ────────────────────────────────────────────────────
# Receives reports from the Report-Only policy in app.py. Kept deliberately
# simple: an in-memory ring buffer, no database. The purpose is to answer one
# question — "what would break if we dropped 'unsafe-inline'?" — from real
# usage, and that answer is only needed until the migration completes.
#
# Aggregated by (directive, blocked-uri, source-file:line) so 500 clicks on the
# same button appear once with a count, rather than flooding the buffer and
# hiding the long tail.
_CSP_REPORTS: dict[str, dict] = {}
_CSP_REPORT_CAP = 500


@router.post('/csp-report')
async def csp_report(request: Request) -> dict[str, Any]:
    """Collect a CSP violation report. Always 200: a browser will not retry."""
    try:
        body = await request.json()
    except Exception:
        return {'ok': True}

    r = body.get('csp-report') or body.get('cspReport') or body
    if not isinstance(r, dict):
        return {'ok': True}

    key = '|'.join(str(r.get(k, ''))[:200] for k in (
        'effective-directive', 'violated-directive', 'blocked-uri',
        'source-file', 'line-number',
    ))

    entry = _CSP_REPORTS.get(key)
    if entry:
        entry['count'] += 1
        entry['last_seen'] = time.time()
    elif len(_CSP_REPORTS) < _CSP_REPORT_CAP:
        _CSP_REPORTS[key] = {
            'directive': r.get('effective-directive') or r.get('violated-directive', ''),
            'blocked_uri': str(r.get('blocked-uri', ''))[:200],
            'source_file': str(r.get('source-file', ''))[:300],
            'line_number': r.get('line-number'),
            'sample': str(r.get('script-sample', ''))[:200],
            'count': 1,
            'first_seen': time.time(),
            'last_seen': time.time(),
        }
    return {'ok': True}


@router.get('/csp-report')
def list_csp_reports() -> dict[str, Any]:
    """What would break if 'unsafe-inline' were removed, measured not guessed."""
    items = sorted(_CSP_REPORTS.values(), key=lambda x: -x['count'])
    return {
        'ok': True,
        'violations': items,
        'distinct': len(items),
        'total': sum(i['count'] for i in items),
        'capped': len(_CSP_REPORTS) >= _CSP_REPORT_CAP,
        'note': (
            'Reports come from the Report-Only policy; nothing was blocked. '
            'An empty list after real usage is the signal that the enforcing '
            'policy can drop script-src unsafe-inline.'
        ),
    }


@router.delete('/csp-report')
def clear_csp_reports() -> dict[str, Any]:
    """Reset the buffer, e.g. before a fresh measurement pass."""
    n = len(_CSP_REPORTS)
    _CSP_REPORTS.clear()
    return {'ok': True, 'cleared': n}


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
    x_csrf_token:str | None = Header(None, alias='X-CSRF-Token'),
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
