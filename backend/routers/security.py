"""
Agentic OS — Security Router (/api/security)
Provides CSRF token generation/validation and request ID trace tracking.
"""

from __future__ import annotations

import hashlib
import hmac
import secrets
import time
import uuid
from typing import Any

from fastapi import APIRouter, Header, Request, Response
from pydantic import BaseModel

router = APIRouter(prefix='/api/security', tags=['security'])

_TOKEN_TTL = 86400  # 24 hours

# ── Stateless CSRF tokens ─────────────────────────────────────────────────────
# This used to be `_CSRF_TOKENS: dict[str, float]` — a PER-PROCESS dict. It was
# correct for one uvicorn process and broke under several: a token minted by
# worker A is unknown to worker B. Measured with `--workers 4` and enforcement
# on: of 60 POSTs carrying a VALID token, 27 succeeded and 33 returned 403.
#
# The previous mitigation detected the topology and refused to enable
# enforcement by default. That is a guard, not a fix — it left every
# multi-worker deployment permanently unable to run with CSRF protection on.
#
# A CSRF token does not need a server-side record. It needs to be unforgeable
# and to expire. An HMAC over the issue time gives both, and any worker can
# verify any token because they share a key (see services/csrf_secret.py):
#
#     <issued_at>.<nonce>.<hmac_sha256(key, "issued_at.nonce")>
#
# Constant-time comparison throughout: a token check that leaks timing is a
# token check an attacker can walk byte by byte.
_TOKEN_PARTS = 3


def _sign(payload: str) -> str:
    from ..services.csrf_secret import get_secret  # noqa: PLC0415

    return hmac.new(get_secret(), payload.encode(), hashlib.sha256).hexdigest()


def mint_csrf_token() -> str:
    """Issue a signed, self-describing CSRF token."""
    payload = f'{int(time.time())}.{secrets.token_urlsafe(16)}'
    return f'{payload}.{_sign(payload)}'


def csrf_token_is_valid(token: str | None) -> bool:
    """Whether a token is well formed, correctly signed and unexpired."""
    if not token or not isinstance(token, str):
        return False
    parts = token.split('.')
    if len(parts) != _TOKEN_PARTS:
        return False
    issued_raw, nonce, signature = parts
    if not issued_raw or not nonce or not signature:
        return False

    # Verify the signature BEFORE trusting anything in the payload, including
    # the timestamp — otherwise an attacker picks their own expiry.
    if not hmac.compare_digest(_sign(f'{issued_raw}.{nonce}'), signature):
        return False

    try:
        issued = int(issued_raw)
    except (TypeError, ValueError):
        return False

    age = time.time() - issued
    # A token from the future means a forged or clock-skewed payload. A small
    # negative tolerance absorbs ordinary skew between hosts.
    if age < -300:
        return False
    return age <= _TOKEN_TTL


class CSRFValidateRequest(BaseModel):
    """Payload for CSRF token validation requests."""

    csrf_token: str


def _clean_expired_tokens() -> None:
    """No-op, kept so existing callers and tests keep working.

    Tokens carry their own expiry in a signed payload, so there is nothing to
    sweep and no store to grow without bound.
    """
    return None


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


# Per-signature report ceiling.
#
# The buffer already de-duplicates by signature, but the REQUESTS still arrive:
# a directive matching hundreds of nodes produces hundreds of POSTs per load,
# each running the full middleware stack. Measured at 662 on one load before
# style-src was dropped from the Report-Only policy.
#
# Keeping the first N per signature preserves everything the measurement needs
# -- what was violated, where, and that it is frequent -- while bounding the
# cost. Beyond the ceiling the count keeps incrementing but the work stops.
_CSP_REPORT_CEILING = 25


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
        # Past the ceiling the count keeps rising but nothing else is touched.
        # The measurement needs "what, where, and how often" -- it does not need
        # the thousandth identical copy, and each one costs a full request
        # through the middleware stack.
        if entry['count'] > _CSP_REPORT_CEILING:
            entry['throttled'] = True
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
    token = mint_csrf_token()
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
    token_to_check = payload.csrf_token or x_csrf_token
    if not csrf_token_is_valid(token_to_check):
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
