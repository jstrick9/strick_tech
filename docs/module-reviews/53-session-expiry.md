# 53 — Session expiry and authentication loss

**Seam:** *session expiry / auth loss* (highest expected value in
`docs/SEAM-REGISTER.md`).
**Audit:** `scripts/audit/session_expiry.py` · **key:** `session-expiry` ·
**baseline:** 2 → **0**
**Tests:** `tests/unit/test_124_session_expiry.py` (12) — 8 proven to fail on
revert, plus 1 proven by a targeted revert.

---

## Why this seam was different

Every earlier failure audit here simulates the server being **broken** (500) or
**slow**. Losing a session is a third shape: the server is healthy, understands
the request perfectly, and refuses it. Each layer of the app responded
correctly to that and the combination stranded the user.

| Layer | Behaviour on 401 | Correct in isolation? |
|---|---|---|
| `00-connection-status.js` | ignores all 4xx | **Yes** — a refusal is not an outage |
| `00-net-feedback.js` | toast, auto-dismiss at 6000ms | **Yes** — a permanent toast is worse |
| every pane | renders its normal empty state | **Yes** — never throw at the user |

Net effect six seconds in: a calm, plausible, **completely empty application**
with nothing on screen saying why and nothing offering a way back.

---

## Four defects, all verified live before the fix

### 1. Session tokens were write-only

`POST /api/auth/login` minted a `ses_…` token and inserted it into
`auth_sessions`. **Nothing in the codebase ever read that table.**
`require_api_key()` matched only `auth_users.api_key`. Against the running
server:

```
POST /api/auth/login             -> 200 {"token":"ses_d92ab226d00e892f…"}
GET  /api/auth/me   Bearer ses_… -> 401 {"detail":"Invalid API key"}
```

The one credential the login flow hands you was rejected by every endpoint. The
entire session mechanism was decorative — a table, a token generator and a
schema, wired to nothing.

This is recurring pattern **#3** in this review: *a module reporting success
while doing nothing.* Login returned `ok: true` and a real-looking token.

### 2. Every session was born expired

```python
expires = datetime.now(timezone.utc).isoformat()   # no duration added
```

Observed row: issued `12:25:13`, `expires_at` `12:25:13`. Because nothing read
the column the app never noticed — but the instant sessions began to be
honoured (fix 1) every login would have been dead on arrival. **Fixing bug 1
alone would have shipped a login that never works.**

### 3. No way to end a session

There was no logout route at all. A token on a shared machine stayed valid
until it expired — and per bug 2, "expired" meant nothing.

### 4. A dead session was invisible and inescapable

`NO-SIGNAL` and `NO-ACTION` from the audit, described above.

---

## Fixes

**Backend — `backend/routers/auth.py`**

- `_session_user_id(token)` resolves `ses_…` against `auth_sessions`,
  **honouring `expires_at`**, and deletes expired rows on the way past so the
  table cannot grow without bound.
- `require_api_key()` checks a session token first (it is what the UI holds),
  then falls back to `api_key` (the scripted-client path).
- `SESSION_TTL_HOURS = 12`; `expires_at` is now issue-time **plus** the TTL, and
  `expires_at` is returned to the client so the UI can warn ahead of time
  rather than discovering expiry as a failed save.
- `last_login` now records *now* rather than the expiry timestamp — the same
  variable was doing both jobs.
- New `POST /api/auth/logout`. Deleting the row is the whole mechanism, so
  revocation is immediate across every worker. Answers **200** for an unknown
  or already-deleted token on purpose: logging out twice is a normal thing to
  do and the end state the caller asked for is the state they get.
- Failure message unified to `Invalid or expired credentials`. Distinguishing
  "expired" from "wrong" tells an attacker which guesses are closer; the UI
  explains the likely cause, the server does not.

**Frontend — `frontend/js/00-session-status.js` (new)**

A persistent lost-session banner, top-centre, `role="alert"`:

> Your session has ended. Nothing was lost — sign in again to carry on.
> **[Sign in]**

- **Separate from the connection banner on purpose.** "Your work is safe, try
  again" and "retrying will not help, sign in" are opposite instructions;
  merging them makes one of the two wrong. Top-centre vs bottom-centre so that
  if both appear neither hides the other.
- **No timer.** The condition does not expire on its own, so neither does the
  message. It clears when — and only when — an authenticated request succeeds.
- **Threshold of 2 within 10s**, and `/api/auth/login` is excluded: a 401 there
  means "wrong password", and announcing an expired session on top of a failed
  sign-in is both wrong and demoralising.
- **No third `fetch` wrapper.** It chains onto
  `connectionStatus.observeResponse`, the single existing observation point, so
  `window.fetch` keeps one owner (`scripts/lint_globals.py`).
- Focus moves to the **Sign in** button, so a keyboard or screen-reader user
  reaches the only useful control without hunting.

---

## The probe's own two bugs, found before the app's

Both are now in the measurement-traps table.

1. **Off-screen live region counted as visible signal.** The first run reported
   `NO-SIGNAL` as *clean*. It was reading `#sr-announcer` — a
   `position:absolute` off-screen element holding a **copy** of the toast text.
   The user could see nothing; the probe could see everything.
2. **Then it over-corrected and dropped every `[aria-live]`.** That deleted the
   new banner — which is an `aria-live="assertive"` alert — and reported
   `NO-SIGNAL` against a screen that plainly said so. **Visibility is the test,
   not the presence of an ARIA attribute.**

Also: waiting past the 6000ms toast lifetime does **not** prove the screen is at
rest, because polling re-raises the toast. The probe now removes toasts rather
than waiting them out.

---

## Verification

| Check | Result |
|---|---|
| `scripts/audit/session_expiry.py` | 2 → **0** |
| Revert whole fix | **8 of 12** tests fail |
| Targeted revert of the expiry comparison only | `test_expired_session_token_is_refused` fails (200 ≠ 401) |
| `ruff`, `lint_globals`, `lint_inline_handlers`, `build_bundle --check` | clean |
| All 13 audits | at baseline |
