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
import threading
import time
from datetime import datetime, timedelta, timezone

from fastapi import APIRouter, Depends, HTTPException, Request
from fastapi.responses import JSONResponse
from pydantic import BaseModel

router = APIRouter(prefix='/api/auth', tags=['auth'])
log = logging.getLogger('agentic.auth')

from ..services.memory_db import audit_log, get_conn

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
# Password hashing: PBKDF2-HMAC-SHA256 (stdlib, no new dependency).
#
# The original scheme was a single unsalted-algorithm SHA-256 pass over
# "salt:password" — a few billion guesses per second on a modern GPU. A vault
# key and every stored credential deserve a KDF that is *slow on purpose*.
# OWASP's current guidance for PBKDF2-HMAC-SHA256 is 600,000 iterations; that
# costs ~300ms per login on this hardware, which is a poor trade for a
# local-first app whose login is rare. 200,000 keeps each login under ~100ms
# while still making offline attack ~5 orders of magnitude costlier than
# before. The iteration count is stored in the hash so it can be raised
# without invalidating existing credentials, and _verify_password accepts any
# sane count (old hashes stay verifiable at their original cost).
_PBKDF2_ITERATIONS = 200_000
_PBKDF2_MIN_ITERATIONS = 10_000        # sanity floor: refuse absurd stored counts
_PBKDF2_MAX_ITERATIONS = 5_000_000     # sanity ceiling: refuse DoS-by-iteration


def _hash_password(password: str) -> str:
    """Hash a password with PBKDF2-HMAC-SHA256 and a random salt.

    Format: pbkdf2$<iterations>$<salt-hex>$<dk-hex> — self-describing so the
    parameters can be raised later without a migration flag day.
    """
    salt = secrets.token_hex(16)
    dk = hashlib.pbkdf2_hmac('sha256', password.encode(), salt.encode(), _PBKDF2_ITERATIONS)
    return f'pbkdf2${_PBKDF2_ITERATIONS}${salt}${dk.hex()}'


def _verify_password(password: str, stored: str) -> bool:
    """Verify a password against a stored hash.

    Understands both the current `pbkdf2$…` format and the legacy
    `salt$sha256` format so existing accounts keep working; login upgrades
    them transparently (see `login_user`).
    """
    if not stored:
        return False
    parts = stored.split('$')
    if len(parts) == 4 and parts[0] == 'pbkdf2':
        try:
            iterations = int(parts[1])
        except ValueError:
            return False
        if not (_PBKDF2_MIN_ITERATIONS <= iterations <= _PBKDF2_MAX_ITERATIONS):
            return False
        salt, expected = parts[2], parts[3]
        try:
            dk = hashlib.pbkdf2_hmac('sha256', password.encode(), salt.encode(), iterations)
        except (ValueError, TypeError):
            return False
        return hmac.compare_digest(dk.hex(), expected)
    if len(parts) == 2:  # legacy: salt$sha256(password)
        salt, expected = parts
        return hmac.compare_digest(
            expected, hashlib.sha256(f'{salt}:{password}'.encode()).hexdigest()
        )
    return False


def _password_needs_upgrade(stored: str) -> bool:
    """True when a hash predates PBKDF2 and should be re-hashed on next login."""
    return not (stored or '').startswith('pbkdf2$')


# A real PBKDF2 hash of an unguessable throwaway value. When the username does
# not exist we still run a full verification against THIS, so "no such user"
# and "wrong password" take the same ~80ms. Without it the login endpoint
# answered unknown usernames in microseconds — a trivially measurable oracle
# for enumerating valid usernames. The one-time cost is paid at import.
_DUMMY_HASH = _hash_password(
    'timing-equalizer-' + secrets.token_hex(16)
)


# ── Login throttling ───────────────────────────────────────────────────────
# The global per-IP rate limit in app.py bounds REQUESTS; it does not track
# FAILURES, and it resets the moment an attacker slows below one request per
# window tick. Password guessing needs a counter that only successful logins
# clear. Keyed by (username, ip) so one attacker cannot lock out other users,
# and in-memory because the auth surface is already per-process (sessions are
# in SQLite, but a single-worker uvicorn is the documented deployment).
_LOGIN_MAX_FAILURES = 10
_LOGIN_FAILURE_WINDOW = 900.0  # 15 minutes
_LOGIN_FAILURES_CAP = 10_000   # distinct (username, ip) keys kept
_login_failures: dict[tuple[str, str], list[float]] = {}
_login_failures_lock = threading.Lock()


def _login_key(username: str, ip: str) -> tuple[str, str]:
    return (username.strip().lower(), ip or 'unknown')


def _login_blocked(username: str, ip: str) -> tuple[bool, int]:
    """(blocked?, seconds until the oldest counted failure ages out)."""
    key = _login_key(username, ip)
    now = time.monotonic()
    with _login_failures_lock:
        hits = [t for t in _login_failures.get(key, ()) if now - t < _LOGIN_FAILURE_WINDOW]
        if hits:
            _login_failures[key] = hits
        if len(hits) >= _LOGIN_MAX_FAILURES:
            return True, max(1, int(_LOGIN_FAILURE_WINDOW - (now - hits[0])) + 1)
        return False, 0


def _note_login_failure(username: str, ip: str) -> None:
    key = _login_key(username, ip)
    now = time.monotonic()
    with _login_failures_lock:
        hits = [t for t in _login_failures.get(key, ()) if now - t < _LOGIN_FAILURE_WINDOW]
        hits.append(now)
        _login_failures[key] = hits
        if len(_login_failures) > _LOGIN_FAILURES_CAP:
            # Evict the least recently failed keys rather than grow forever.
            for old_key, _ in sorted(_login_failures.items(), key=lambda kv: kv[1][-1] if kv[1] else 0):
                _login_failures.pop(old_key, None)
                if len(_login_failures) <= _LOGIN_FAILURES_CAP:
                    break


def _clear_login_failures(username: str, ip: str) -> None:
    with _login_failures_lock:
        _login_failures.pop(_login_key(username, ip), None)


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
async def login_user(req: LoginRequest, request: Request):
    """Login and get a session token."""
    ip = request.client.host if request.client else 'unknown'

    # Failure throttle BEFORE the user lookup: an attacker who is already
    # locked out must not learn anything further, including whether the
    # username exists (the timing profile of the lookup is itself a signal).
    blocked, retry_after = _login_blocked(req.username, ip)
    if blocked:
        try:
            audit_log('auth_login_lockout', f'user={req.username} ip={ip}')
        except Exception:
            pass
        return JSONResponse(
            {
                'ok': False,
                'error': (
                    f'Too many failed sign-in attempts for this account. '
                    f'Try again in {retry_after}s.'
                ),
            },
            status_code=429,
            headers={'Retry-After': str(retry_after)},
        )

    con = get_conn()
    try:
        user = con.execute(
            'SELECT id, username, display_name, role, password_hash FROM auth_users WHERE username=?',
            (req.username,)
        ).fetchone()

        if not user:
            # Burn the same PBKDF2 cost a real verification would have cost,
            # so a missing username and a wrong password are indistinguishable
            # by response time (see _DUMMY_HASH).
            _verify_password(req.password, _DUMMY_HASH)
            _note_login_failure(req.username, ip)
            return JSONResponse({'ok': False, 'error': 'Invalid username or password'}, status_code=401)

        if not _verify_password(req.password, user['password_hash']):
            _note_login_failure(req.username, ip)
            return JSONResponse({'ok': False, 'error': 'Invalid username or password'}, status_code=401)

        _clear_login_failures(req.username, ip)

        # Transparent KDF upgrade: the credential was just proven correct, so
        # this is the one moment a legacy salt$sha256 hash can be replaced
        # with PBKDF2 without ever asking the user to reset anything.
        if _password_needs_upgrade(user['password_hash']):
            con.execute(
                'UPDATE auth_users SET password_hash=? WHERE id=?',
                (_hash_password(req.password), user['id']),
            )

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
        # Expired sessions were deleted only when their OWN token was
        # presented again — which by definition never happens for an expired
        # token a client has already discarded. Every login now sweeps them,
        # so the table cannot grow without bound on a long-running server.
        con.execute(
            'DELETE FROM auth_sessions WHERE expires_at <= ?',
            (now,),
        )
        con.execute(
            'UPDATE auth_users SET last_login=? WHERE id=?',
            (now, user['id'])
        )
        con.commit()

        try:
            audit_log('auth_login', f'user={user["username"]} ip={ip}')
        except Exception:
            pass

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
async def get_current_user(user_id: str | None = Depends(require_api_key)):
    """Get current user info from API key.

    Also reports `auth_configured` (are there any registered users at all) so
    a UI can tell the three states apart WITHOUT probing register:
      * 200 + authenticated=False + auth_configured=False → auth is OFF
      * 401                                              → auth is ON, not signed in
      * 200 + authenticated=True                          → signed in
    """
    con = get_conn()
    try:
        count = con.execute('SELECT COUNT(*) FROM auth_users').fetchone()[0]
        if not user_id:
            return {
                'ok': True,
                'authenticated': False,
                'auth_configured': count > 0,
                'message': (
                    'No authentication configured — the first registered user becomes admin.'
                    if count == 0
                    else 'Authentication is configured. Sign in to continue.'
                ),
            }
        user = con.execute('SELECT id, username, display_name, role, last_login FROM auth_users WHERE id=?', (user_id,)).fetchone()
        if not user:
            return JSONResponse({'ok': False, 'error': 'User not found'}, status_code=404)
        return {
            'ok': True,
            'authenticated': True,
            'auth_configured': True,
            'user': dict(user),
        }
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
