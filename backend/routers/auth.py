"""
Agentic OS — Authentication & Authorization Scaffolding
Provides API key authentication middleware and user session management.
Designed for progressive hardening: starts simple, can grow to full OAuth2.
"""
from __future__ import annotations

import hashlib
import hmac
import logging
import secrets
from datetime import datetime, timedelta, timezone

from fastapi import APIRouter, Depends, HTTPException, Request
from fastapi.responses import JSONResponse
from pydantic import BaseModel

router = APIRouter(prefix='/api/auth', tags=['auth'])
log = logging.getLogger('agentic.auth')

from ..services.memory_db import get_conn

# ── Schema ─────────────────────────────────────────────────────────────────
_AUTH_SCHEMA = """
CREATE TABLE IF NOT EXISTS auth_users (
    id TEXT PRIMARY KEY,
    username TEXT UNIQUE NOT NULL,
    display_name TEXT DEFAULT '',
    password_hash TEXT NOT NULL,
    role TEXT DEFAULT 'user',
    api_key TEXT UNIQUE,
    last_login TEXT DEFAULT '',
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
);
CREATE TABLE IF NOT EXISTS auth_sessions (
    token TEXT PRIMARY KEY,
    user_id TEXT NOT NULL,
    expires_at TEXT NOT NULL,
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
);
"""


def _ensure_auth_schema():
    con = get_conn()
    try:
        con.executescript(_AUTH_SCHEMA)
        con.commit()
    except Exception:
        pass
    finally:
        con.close()


_ensure_auth_schema()


# ── Helpers ────────────────────────────────────────────────────────────────
def _hash_password(password: str) -> str:
    """Hash a password with a random salt using SHA-256."""
    salt = secrets.token_hex(16)
    h = hashlib.sha256(f'{salt}:{password}'.encode()).hexdigest()
    return f'{salt}${h}'


def _verify_password(password: str, stored: str) -> bool:
    """Verify a password against a salt$hash string."""
    if '$' not in stored:
        return False
    salt, h = stored.split('$', 1)
    return hmac.compare_digest(h, hashlib.sha256(f'{salt}:{password}'.encode()).hexdigest())


def _generate_api_key() -> str:
    return f'ak_{secrets.token_hex(24)}'


def _generate_session_token() -> str:
    return f'ses_{secrets.token_hex(32)}'


# How long a login lasts. Long enough that a working day does not require a
# second sign-in; short enough that a token left on a shared machine dies.
SESSION_TTL_HOURS = 12


def _session_expiry() -> str:
    return (datetime.now(timezone.utc) + timedelta(hours=SESSION_TTL_HOURS)).isoformat()


def _session_user_id(token: str) -> str | None:
    """Resolve a `ses_…` token to a user, honouring its expiry.

    WHY THIS EXISTS. `/api/auth/login` minted a session token and wrote it to
    `auth_sessions`, but nothing in the codebase ever READ that table --
    `require_api_key()` matched only `auth_users.api_key`. Verified against the
    running server before this fix:

        POST /api/auth/login             -> 200 {"token": "ses_d92ab226…"}
        GET  /api/auth/me   Bearer ses_… -> 401 {"detail": "Invalid API key"}

    The one credential the login flow hands the caller was rejected by every
    endpoint, so the entire session mechanism was decorative.

    Expired rows are deleted on the way past rather than merely refused, so the
    table does not grow without bound in a long-running deployment.
    """
    if not token or not token.startswith('ses_'):
        return None
    con = get_conn()
    try:
        row = con.execute(
            'SELECT user_id, expires_at FROM auth_sessions WHERE token=?',
            (token,),
        ).fetchone()
        if not row:
            return None
        try:
            expires = datetime.fromisoformat(row['expires_at'])
        except (TypeError, ValueError):
            # An unparseable expiry is treated as expired: failing closed is
            # the only safe reading of a credential we cannot date.
            expires = datetime.min.replace(tzinfo=timezone.utc)
        if expires.tzinfo is None:
            expires = expires.replace(tzinfo=timezone.utc)
        if expires <= datetime.now(timezone.utc):
            con.execute('DELETE FROM auth_sessions WHERE token=?', (token,))
            con.commit()
            return None
        return row['user_id']
    except Exception:
        return None
    finally:
        con.close()


# ── API Key authentication dependency ──────────────────────────────────────
async def require_api_key(request: Request) -> str | None:
    """FastAPI dependency: validates API key from header or query param.
    Returns user_id if valid, None if no auth configured.
    Raises 401 if auth is required but invalid.
    """
    # Check if any users exist (auth is optional until first user is created)
    con = get_conn()
    try:
        count = con.execute('SELECT COUNT(*) FROM auth_users').fetchone()[0]
    finally:
        con.close()

    if count == 0:
        return None  # No users configured — auth not required

    # Check header
    api_key = request.headers.get('X-API-Key', '') or request.headers.get('Authorization', '').replace('Bearer ', '')
    if not api_key:
        api_key = request.query_params.get('api_key', '')

    if not api_key:
        raise HTTPException(status_code=401, detail='API key required')

    # A session token from /api/auth/login is a first-class credential. It is
    # checked first because it is the one the UI actually holds; a long-lived
    # api_key is the scripted-client path.
    session_user = _session_user_id(api_key)
    if session_user:
        return session_user

    con = get_conn()
    try:
        user = con.execute('SELECT id FROM auth_users WHERE api_key=?', (api_key,)).fetchone()
    finally:
        con.close()

    if not user:
        # Deliberately one message for "expired session", "revoked session" and
        # "wrong key": distinguishing them tells an attacker which guesses are
        # closer. The UI explains the likely cause; the server does not.
        raise HTTPException(status_code=401, detail='Invalid or expired credentials')
    return user['id']


# ── Routes ─────────────────────────────────────────────────────────────────
class RegisterRequest(BaseModel):
    username: str
    password: str
    display_name: str = ''


@router.post('/register')
def register_user(req: RegisterRequest):
    """Register a new user. First user becomes admin."""
    if len(req.username) < 2:
        return JSONResponse({'ok': False, 'error': 'Username must be at least 2 characters'}, status_code=400)
    if len(req.password) < 6:
        return JSONResponse({'ok': False, 'error': 'Password must be at least 6 characters'}, status_code=400)

    con = get_conn()
    try:
        # First user is admin
        count = con.execute('SELECT COUNT(*) FROM auth_users').fetchone()[0]
        role = 'admin' if count == 0 else 'user'

        user_id = f'user_{secrets.token_hex(8)}'
        api_key = _generate_api_key()
        password_hash = _hash_password(req.password)

        con.execute(
            'INSERT INTO auth_users (id, username, display_name, password_hash, role, api_key) VALUES (?,?,?,?,?,?)',
            (user_id, req.username, req.display_name or req.username, password_hash, role, api_key)
        )
        con.commit()

        return {
            'ok': True,
            'user_id': user_id,
            'username': req.username,
            'role': role,
            'api_key': api_key,
            'message': f'User registered as {role}. Save your API key — it is shown only once.',
        }
    except Exception as e:
        if 'UNIQUE' in str(e):
            return JSONResponse({'ok': False, 'error': 'Username already exists'}, status_code=409)
        return JSONResponse({'ok': False, 'error': str(e)}, status_code=500)
    finally:
        con.close()


class LoginRequest(BaseModel):
    username: str
    password: str


@router.post('/login')
def login_user(req: LoginRequest):
    """Login and get a session token."""
    con = get_conn()
    try:
        user = con.execute(
            'SELECT id, username, display_name, role, password_hash FROM auth_users WHERE username=?',
            (req.username,)
        ).fetchone()

        if not user or not _verify_password(req.password, user['password_hash']):
            return JSONResponse({'ok': False, 'error': 'Invalid username or password'}, status_code=401)

        token = _generate_session_token()
        # `expires_at` was `datetime.now(...)` -- the instant of issue, with no
        # duration added, so every session was born already expired. Nothing
        # read the column, so the app never noticed; the moment sessions began
        # to be honoured, every login would have been dead on arrival.
        expires = _session_expiry()
        now = datetime.now(timezone.utc).isoformat()

        con.execute(
            'INSERT INTO auth_sessions (token, user_id, expires_at) VALUES (?,?,?)',
            (token, user['id'], expires)
        )
        con.execute(
            'UPDATE auth_users SET last_login=? WHERE id=?',
            (now, user['id'])
        )
        con.commit()

        return {
            'ok': True,
            'token': token,
            # Told to the client so the UI can warn before it happens rather
            # than discovering expiry as a failed save.
            'expires_at': expires,
            'user': {
                'id': user['id'],
                'username': user['username'],
                'display_name': user['display_name'],
                'role': user['role'],
            },
        }
    finally:
        con.close()


@router.post('/logout')
async def logout(request: Request):
    """End the current session.

    There was no logout route at all, so a session token could not be revoked:
    on a shared machine it stayed valid until it expired. Deleting the row is
    the whole mechanism -- `_session_user_id()` reads that table on every
    request, so removal takes effect immediately across all workers.

    Answers 200 for an unknown or already-deleted token on purpose. Logging out
    twice, or with a token the server has already forgotten, is a normal thing
    to do and must not produce an error the user has to think about; the
    end state they asked for is the state they get.
    """
    token = (request.headers.get('Authorization', '').replace('Bearer ', '')
             or request.headers.get('X-API-Key', ''))
    revoked = 0
    if token.startswith('ses_'):
        con = get_conn()
        try:
            cur = con.execute('DELETE FROM auth_sessions WHERE token=?', (token,))
            con.commit()
            revoked = cur.rowcount or 0
        except Exception:
            revoked = 0
        finally:
            con.close()
    return {'ok': True, 'revoked': revoked, 'message': 'Signed out.'}


@router.get('/me')
async def get_current_user(user_id: str = Depends(require_api_key)):
    """Get current user info from API key."""
    if not user_id:
        return {'ok': True, 'authenticated': False, 'message': 'No authentication configured'}
    con = get_conn()
    try:
        user = con.execute('SELECT id, username, display_name, role, last_login FROM auth_users WHERE id=?', (user_id,)).fetchone()
        if not user:
            return JSONResponse({'ok': False, 'error': 'User not found'}, status_code=404)
        return {'ok': True, 'authenticated': True, 'user': dict(user)}
    finally:
        con.close()


@router.get('/users')
async def list_users(user_id: str = Depends(require_api_key)):
    """List all users (admin only)."""
    con = get_conn()
    try:
        # Check if requester is admin
        if user_id:
            requester = con.execute('SELECT role FROM auth_users WHERE id=?', (user_id,)).fetchone()
            if not requester or requester['role'] != 'admin':
                return JSONResponse({'ok': False, 'error': 'Admin access required'}, status_code=403)

        users = con.execute('SELECT id, username, display_name, role, last_login, created_at FROM auth_users').fetchall()
        return {'ok': True, 'users': [dict(u) for u in users]}
    finally:
        con.close()


@router.post('/rotate-key')
async def rotate_api_key(user_id: str = Depends(require_api_key)):
    """Generate a new API key for the current user (invalidates old one)."""
    if not user_id:
        return JSONResponse({'ok': False, 'error': 'Authentication required'}, status_code=401)
    new_key = _generate_api_key()
    con = get_conn()
    try:
        con.execute('UPDATE auth_users SET api_key=? WHERE id=?', (new_key, user_id))
        con.commit()
        return {'ok': True, 'api_key': new_key, 'message': 'New API key generated. Old key is now invalid.'}
    finally:
        con.close()
