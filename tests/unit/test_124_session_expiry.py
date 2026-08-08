"""Session expiry and authentication loss.

THE SEAM
────────
Every earlier failure audit in this repo simulated the server being BROKEN
(500) or SLOW. Losing your session is a different shape of failure and the app
handled it differently at every layer, in ways that were individually
defensible and collectively left the user stranded.

FOUR REAL DEFECTS, ALL VERIFIED LIVE BEFORE THE FIX
───────────────────────────────────────────────────

1. **Session tokens were write-only.** `POST /api/auth/login` minted a
   `ses_…` token and stored it in `auth_sessions`, but NOTHING ever read that
   table. `require_api_key()` only checked `auth_users.api_key`. Verified
   against the running server:

       POST /api/auth/login            -> 200 {"token": "ses_d92ab226…"}
       GET  /api/auth/me  Bearer ses_… -> 401 {"detail": "Invalid API key"}

   The one credential the login flow hands you is rejected by every endpoint.

2. **Every session was born expired.** `expires_at` was set to
   `datetime.now(timezone.utc).isoformat()` — the moment of issue, with no
   duration added. Because nothing read the column the app never noticed, but
   the moment sessions were honoured (fix 1) every login would have been dead
   on arrival. Stored value observed: issued 12:25:13, `expires_at`
   12:25:13.

3. **No way to end a session.** There was no logout route at all, so a token
   could not be revoked on a shared machine.

4. **A dead session was invisible.** `00-net-feedback.js` raises a toast on
   401 that auto-dismisses after 6000ms. `00-connection-status.js` explicitly
   ignores 4xx (correctly — "not found" is not an outage). Six seconds after
   the session ended there was nothing on screen saying so, while every pane
   rendered a calm, plausible empty state, and no control offered a way back
   in. `scripts/audit/session_expiry.py` measures exactly this and reported
   NO-SIGNAL + NO-ACTION.

MEASUREMENT NOTE (the audit's own bug, found first)
───────────────────────────────────────────────────
The first version of the probe reported NO-SIGNAL as clean. It was reading
`#sr-announcer` — a `position:absolute` off-screen live region holding a COPY
of the toast text — as persistent visible UI. The probe now drops live
regions and zero-size/off-screen nodes. This is the same trap already listed
in docs/SEAM-REGISTER.md as "instrumenting outside the layer under test".
"""

from __future__ import annotations

import re
import sqlite3
from datetime import datetime, timezone
from pathlib import Path

REPO = Path(__file__).resolve().parent.parent.parent
JS = REPO / 'frontend' / 'js'
AUDIT = REPO / 'scripts' / 'audit'
AUTH_PY = (REPO / 'backend' / 'routers' / 'auth.py').read_text(encoding='utf-8')


def _strip_comments_js(source: str) -> str:
    """So an assertion cannot be satisfied by the comment explaining the fix.

    This has caught a test asserting its own fix comment eleven times in this
    review.
    """
    source = re.sub(r'/\*.*?\*/', '', source, flags=re.S)
    return re.sub(r'(?m)^\s*//.*$', '', source)


def _strip_comments_py(source: str) -> str:
    source = re.sub(r'"""[\s\S]*?"""', '', source)
    return re.sub(r'(?m)^\s*#.*$', '', source)


SESSION_JS = _strip_comments_js((JS / '00-session-status.js').read_text(encoding='utf-8'))
AUTH_SRC = _strip_comments_py(AUTH_PY)


# ──────────────────────────────────────────────────────────────────────
#  1. Session tokens are actually accepted
# ──────────────────────────────────────────────────────────────────────
def test_login_token_is_accepted_by_authenticated_endpoints(client):
    """The credential login hands you must open the door it was minted for.

    Before the fix this returned 401 "Invalid API key" — the session table was
    written and never read.
    """
    client.post('/api/auth/register',
                json={'username': 'sess_probe_a', 'password': 'hunter22'})
    login = client.post('/api/auth/login',
                        json={'username': 'sess_probe_a', 'password': 'hunter22'})
    assert login.status_code == 200, login.text
    token = login.json()['token']
    assert token.startswith('ses_')

    me = client.get('/api/auth/me', headers={'Authorization': f'Bearer {token}'})
    assert me.status_code == 200, (
        f'a freshly issued session token was rejected: {me.text}')
    body = me.json()
    assert body.get('authenticated') is True
    assert body['user']['username'] == 'sess_probe_a'


def test_session_lookup_reads_the_sessions_table():
    """Structural guard: the credential check must consult auth_sessions.

    Without this, fix 1 could be satisfied by (say) also storing the session
    token in auth_users.api_key, which would make logout and expiry
    unimplementable.
    """
    assert 'auth_sessions' in AUTH_SRC
    # Slice to the NEXT top-level definition rather than to a blank-line gap:
    # stripping comments leaves runs of blank lines inside the body, so
    # `index('\n\n\n')` truncated the function halfway and the assertion was
    # reading a fragment.
    check = AUTH_SRC[AUTH_SRC.index('async def require_api_key'):]
    nxt = re.search(r'\n(?:@router|def |async def |class )', check[1:])
    if nxt:
        check = check[:nxt.start() + 1]
    assert 'auth_sessions' in check or '_session_user_id' in check, (
        'require_api_key must be able to authenticate a session token')


# ──────────────────────────────────────────────────────────────────────
#  2. Sessions have a real lifetime, and it is enforced
# ──────────────────────────────────────────────────────────────────────
def test_issued_session_expires_in_the_future(client):
    """`expires_at` was `now()` — every session was born expired."""
    client.post('/api/auth/register',
                json={'username': 'sess_probe_b', 'password': 'hunter22'})
    login = client.post('/api/auth/login',
                        json={'username': 'sess_probe_b', 'password': 'hunter22'})
    token = login.json()['token']

    from backend.services.memory_db import get_conn
    con = get_conn()
    try:
        row = con.execute(
            'SELECT expires_at FROM auth_sessions WHERE token=?', (token,)).fetchone()
    finally:
        con.close()
    assert row is not None, 'login did not persist the session'
    expires = datetime.fromisoformat(row['expires_at'])
    assert expires > datetime.now(timezone.utc), (
        f'session expires at {expires}, which is not in the future — '
        'every login would be dead on arrival')


def test_expired_session_token_is_refused(client):
    """An expired token must stop working. Otherwise the TTL is decorative."""
    client.post('/api/auth/register',
                json={'username': 'sess_probe_c', 'password': 'hunter22'})
    login = client.post('/api/auth/login',
                        json={'username': 'sess_probe_c', 'password': 'hunter22'})
    token = login.json()['token']

    from backend.services.memory_db import get_conn
    con = get_conn()
    try:
        con.execute('UPDATE auth_sessions SET expires_at=? WHERE token=?',
                    ('2000-01-01T00:00:00+00:00', token))
        con.commit()
    finally:
        con.close()

    me = client.get('/api/auth/me', headers={'Authorization': f'Bearer {token}'})
    assert me.status_code == 401, (
        f'an expired session token was still accepted: {me.status_code} {me.text}')


# ──────────────────────────────────────────────────────────────────────
#  3. A session can be ended
# ──────────────────────────────────────────────────────────────────────
def test_logout_revokes_the_token(client):
    """There was no logout route at all — a token on a shared machine was
    good until it expired."""
    client.post('/api/auth/register',
                json={'username': 'sess_probe_d', 'password': 'hunter22'})
    token = client.post('/api/auth/login',
                        json={'username': 'sess_probe_d', 'password': 'hunter22'}
                        ).json()['token']
    headers = {'Authorization': f'Bearer {token}'}

    assert client.get('/api/auth/me', headers=headers).status_code == 200

    out = client.post('/api/auth/logout', headers=headers)
    assert out.status_code == 200, f'no working logout route: {out.text}'

    after = client.get('/api/auth/me', headers=headers)
    assert after.status_code == 401, (
        'the token still worked after logout — the session was not revoked')


def test_logout_without_a_session_does_not_500(client):
    """Logging out twice, or with a stale token, is a normal thing to do."""
    r = client.post('/api/auth/logout',
                    headers={'Authorization': 'Bearer ses_does_not_exist'})
    assert r.status_code < 500, r.text


# ──────────────────────────────────────────────────────────────────────
#  4. The user is told, and offered a way back in
# ──────────────────────────────────────────────────────────────────────
def test_a_persistent_signal_exists_for_a_lost_session():
    """A 6-second toast is not a signal — it is gone before the user reads
    the empty screen it was explaining."""
    assert 'session-banner' in SESSION_JS
    assert '401' in SESSION_JS, 'the banner must be driven by the 401 status'
    # It must not be on a timer: the condition persists, so the message must.
    banner = SESSION_JS[SESSION_JS.index('function show'):]
    banner = banner[:2000]
    assert 'setTimeout' not in banner, (
        'the session banner must not auto-dismiss; the session is still gone')


def test_the_banner_offers_an_action():
    """NO-ACTION: nothing on screen offered a way to sign back in."""
    assert re.search(r'Sign in|Sign back in', SESSION_JS), (
        'the banner must offer a sign-in control, not just prose')


def test_session_status_observes_through_the_existing_fetch_wrapper():
    """Two intentional window.fetch wrappers already exist and adding a third
    was nearly done once in this review. This module must observe, not wrap.
    """
    assert 'window.fetch =' not in SESSION_JS, (
        'do not add a third fetch wrapper — observe via 00-csrf.js instead')
    assert 'observeResponse' in SESSION_JS or 'noteUnauthorised' in SESSION_JS


def test_a_success_clears_the_banner():
    """Signing back in must take the banner away, or it becomes furniture."""
    assert 'hide' in SESSION_JS
    assert re.search(r'response\.ok|status\s*<\s*400|status\s*===\s*200', SESSION_JS), (
        'a successful authenticated response must clear the lost-session state')


# ──────────────────────────────────────────────────────────────────────
#  The probe that found this keeps working
# ──────────────────────────────────────────────────────────────────────
def test_the_audit_excludes_offscreen_live_regions():
    """The probe's own bug: #sr-announcer holds a copy of the toast text and
    is positioned off-screen, so NO-SIGNAL passed while the user saw nothing.
    """
    src = (AUDIT / 'session_expiry.py').read_text(encoding='utf-8')
    assert 'sr-announcer' in src
    assert 'aria-live' in src
    assert 'getBoundingClientRect' in src, (
        'off-screen nodes must not count as visible signal')


def test_the_audit_is_registered():
    """An audit not in run_all.py and the ratchet is a probe that runs once."""
    assert 'session_expiry' in (AUDIT / 'run_all.py').read_text(encoding='utf-8')
    ratchet = (REPO / 'tests' / 'unit' / 'test_120_audit_ratchet.py').read_text(
        encoding='utf-8')
    assert 'session-expiry' in ratchet
    import json
    baseline = json.loads((AUDIT / 'baseline.json').read_text(encoding='utf-8'))
    assert baseline.get('session-expiry') == 0
