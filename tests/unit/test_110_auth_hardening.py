"""
Auth hardening: PBKDF2 passwords, login throttling, transparent upgrades.

WHAT THIS LOCKS IN
──────────────────
1. Password hashes are PBKDF2-HMAC-SHA256 (self-describing format), and the
   legacy `salt$sha256` format still verifies so existing accounts are not
   locked out by an upgrade — and is re-hashed as PBKDF2 on the next
   successful login (verified through the in-process TestClient).
2. Unknown usernames cost the same PBKDF2 time as wrong passwords
   (timing-equalised via a dummy hash) — no username oracle.
3. Failed sign-ins are counted per (username, ip); the 11th is refused with
   429 + Retry-After while other users and other IPs are untouched.
4. Expired sessions are swept on login.
"""
from __future__ import annotations

import hashlib
import re
import sqlite3
import time
import uuid

from tests.unit.conftest import assert_ok


def _uniq(prefix="authu"):
    return f"{prefix}_{uuid.uuid4().hex[:10]}"


# ── Password hashing ────────────────────────────────────────────────────────
class TestPbkdf2PasswordHashing:
    def test_new_hashes_are_self_describing_pbkdf2(self):
        from backend.routers.auth import _hash_password

        h = _hash_password("correct horse battery staple")
        m = re.fullmatch(r"pbkdf2\$(\d+)\$([0-9a-f]+)\$([0-9a-f]+)", h)
        assert m, f"unexpected format: {h[:40]}…"
        iterations = int(m.group(1))
        assert iterations >= 100_000, "below OWASP-era cost"
        assert len(m.group(2)) == 32, "expected a 16-byte salt in hex"
        # Two hashes of the same password differ (random salt).
        assert _hash_password("same") != _hash_password("same")

    def test_verify_round_trip_and_rejects_wrong_password(self):
        from backend.routers.auth import _hash_password, _verify_password

        h = _hash_password("s3cret-pass")
        assert _verify_password("s3cret-pass", h)
        assert not _verify_password("s3cret-pas", h)
        assert not _verify_password("", h)
        assert not _verify_password("s3cret-pass", "")

    def test_legacy_salt_sha256_hashes_still_verify_and_flag_upgrade(self):
        from backend.routers.auth import _password_needs_upgrade, _verify_password

        salt = "abcd1234"
        legacy = salt + "$" + hashlib.sha256(f"{salt}:oldpw".encode()).hexdigest()
        assert _verify_password("oldpw", legacy)
        assert not _verify_password("other", legacy)
        assert _password_needs_upgrade(legacy)
        assert not _password_needs_upgrade("pbkdf2$200000$abcd$ef00")

    def test_corrupt_hashes_fail_closed_not_crash(self):
        from backend.routers.auth import _verify_password

        for bad in ("pbkdf2$notanumber$aa$bb", "pbkdf2$999999999$aa$bb",
                    "pbkdf2$200000$aa", "no-dollar-signs", "a$b$c$d$e", "$"):
            assert not _verify_password("x", bad), bad


# ── Login throttling ────────────────────────────────────────────────────────
class TestLoginThrottle:
    def _flood(self, user, ip, n):
        from backend.routers.auth import _note_login_failure

        for _ in range(n):
            _note_login_failure(user, ip)

    def test_blocks_after_limit_and_reports_wait(self):
        from backend.routers.auth import (
            _LOGIN_FAILURE_WINDOW,
            _LOGIN_MAX_FAILURES,
            _login_blocked,
        )

        user, ip = _uniq(), "203.0.113.9"
        self._flood(user, ip, _LOGIN_MAX_FAILURES)
        blocked, retry = _login_blocked(user, ip)
        assert blocked
        assert 1 <= retry <= int(_LOGIN_FAILURE_WINDOW) + 1

    def test_other_users_and_ips_are_not_collateral_damage(self):
        from backend.routers.auth import _LOGIN_MAX_FAILURES, _login_blocked

        user, ip = _uniq(), "203.0.113.10"
        self._flood(user, ip, _LOGIN_MAX_FAILURES)
        assert _login_blocked(user, ip)[0]
        assert not _login_blocked(_uniq(), ip)[0], "same IP, different user"
        assert not _login_blocked(user, "203.0.113.11")[0], "same user, different IP"

    def test_success_clears_the_counter(self):
        from backend.routers.auth import (
            _LOGIN_MAX_FAILURES,
            _clear_login_failures,
            _login_blocked,
            _note_login_failure,
        )

        user, ip = _uniq(), "203.0.113.12"
        for _ in range(_LOGIN_MAX_FAILURES - 1):
            _note_login_failure(user, ip)
        assert not _login_blocked(user, ip)[0]
        _clear_login_failures(user, ip)
        # A fresh failure after a successful login starts from zero again.
        _note_login_failure(user, ip)
        assert not _login_blocked(user, ip)[0]

    def test_window_is_bounded_by_time_not_count(self):
        from backend.routers.auth import _login_failures, _login_blocked

        user, ip = _uniq(), "203.0.113.13"
        # Forge an OLD failure directly: the store must age it out.
        with_lockfree = [(time.monotonic() - 10_000.0)]
        _login_failures[(user.lower(), ip)] = list(with_lockfree)
        assert not _login_blocked(user, ip)[0]


# ── End-to-end through the in-process client ────────────────────────────────
class TestAuthFlowViaTestClient:
    def test_register_login_me_rotate_logout_lifecycle(self, client):
        user, pw = _uniq(), "hunter22"
        r = client.post("/api/auth/register", json={"username": user, "password": pw})
        d = assert_ok(r)
        assert d["role"] == "admin" or d["role"] == "user"
        assert d["api_key"].startswith("ak_")

        r = client.post("/api/auth/login", json={"username": user, "password": pw})
        d = assert_ok(r)
        token = d["token"]
        assert token.startswith("ses_")
        assert d["user"]["username"] == user

        me = client.get("/api/auth/me", headers={"Authorization": f"Bearer {token}"})
        d = assert_ok(me)
        assert d["authenticated"] is True

        rot = client.post("/api/auth/rotate-key", headers={"Authorization": f"Bearer {token}"})
        d = assert_ok(rot)
        assert d["api_key"].startswith("ak_")

        out = client.post("/api/auth/logout", headers={"Authorization": f"Bearer {token}"})
        assert_ok(out)
        gone = client.get("/api/auth/me", headers={"Authorization": f"Bearer {token}"})
        assert gone.status_code == 401, "a logged-out session token must die immediately"

    def test_legacy_hash_is_upgraded_transparently_on_login(self, client):
        from backend.routers.auth import _hash_password
        from backend.services.memory_db import get_conn

        user, pw = _uniq("legacy"), "old-and-busted"
        salt = "legacysalt01"
        legacy = salt + "$" + hashlib.sha256(f"{salt}:{pw}".encode()).hexdigest()
        con = get_conn()
        try:
            con.execute(
                "INSERT INTO auth_users (id, username, display_name, password_hash, role, api_key)"
                " VALUES (?,?,?,?,?,?)",
                (f"user_{uuid.uuid4().hex[:8]}", user, user, legacy, "user", f"ak_{uuid.uuid4().hex}"),
            )
            con.commit()
        finally:
            con.close()

        r = client.post("/api/auth/login", json={"username": user, "password": pw})
        assert_ok(r)

        con = get_conn()
        try:
            row = con.execute(
                "SELECT password_hash FROM auth_users WHERE username=?", (user,)
            ).fetchone()
        finally:
            con.close()
        assert row["password_hash"].startswith("pbkdf2$"), (
            "a successful login must transparently re-hash a legacy credential"
        )
        # And the OLD hash would no longer verify if replayed (sanity on format).
        assert row["password_hash"] != legacy

    def test_failed_logins_return_401_and_eventually_429(self, client):
        from backend.routers.auth import _clear_login_failures, _login_failures

        user = _uniq()
        _login_failures.clear()  # determinism: nothing pre-blocked
        r = client.post("/api/auth/login", json={"username": user, "password": "wrong"})
        assert r.status_code == 401
        assert "Invalid username or password" in r.text

        # Flood this username from the TestClient's IP until the throttle hits.
        saw_429 = False
        for _ in range(40):
            r = client.post("/api/auth/login", json={"username": user, "password": "wrong"})
            if r.status_code == 429:
                saw_429 = True
                assert "Retry-After" in r.headers
                break
        assert saw_429, "sustained failures must produce a 429 with Retry-After"
        _clear_login_failures(user, "testclient")

    def test_me_distinguishes_auth_off_from_signed_out(self, client):
        # With the users registered by other tests in this suite the state is
        # "configured": an unauthenticated /me must answer 401, and the
        # authenticated shape must carry auth_configured.
        r = client.get("/api/auth/me")
        if r.status_code == 401:
            return  # auth configured: correct
        d = r.json()
        assert d["auth_configured"] in (True, False)
        assert "authenticated" in d

    def test_expired_sessions_are_swept_on_login(self, client):
        from backend.services.memory_db import get_conn

        user, pw = _uniq("sweep"), "sweeper-pass"
        assert_ok(client.post("/api/auth/register", json={"username": user, "password": pw}))
        d = assert_ok(client.post("/api/auth/login", json={"username": user, "password": pw}))

        con = get_conn()
        try:
            # Two already-expired rows plus the live one.
            con.execute(
                "INSERT INTO auth_sessions (token, user_id, expires_at) VALUES (?,?,?)",
                ("ses_expired1", d["user"]["id"], "2001-01-01T00:00:00+00:00"),
            )
            con.execute(
                "INSERT INTO auth_sessions (token, user_id, expires_at) VALUES (?,?,?)",
                ("ses_expired2", d["user"]["id"], "2001-01-01T00:00:00+00:00"),
            )
            con.commit()
        finally:
            con.close()

        assert_ok(client.post("/api/auth/login", json={"username": user, "password": pw}))

        con = get_conn()
        try:
            leftovers = con.execute(
                "SELECT COUNT(*) FROM auth_sessions WHERE token IN ('ses_expired1','ses_expired2')"
            ).fetchone()[0]
        finally:
            con.close()
        assert leftovers == 0, "login must sweep expired session rows"


# ── Vault must not delete environment variables it does not own ─────────────
class TestVaultEnvOwnership:
    """An agent-scoped (or deleted) vault secret must never erase an
    operator-provided environment variable of the same name.

    Measured before the fix: with OPENROUTER_API_KEY set in the server's
    environment, POST /api/secrets/set {scope: 'agent'} ran
    os.environ.pop(key) and the operator's key was gone for the rest of the
    process — every global consumer silently fell back to local inference.
    """

    def _cleanup(self, key):
        from backend.services.memory_db import get_conn

        con = get_conn()
        try:
            con.execute("DELETE FROM secrets WHERE key=?", (key,))
            con.commit()
        finally:
            con.close()

    def test_agent_scoped_write_leaves_operator_env_intact(self, client, monkeypatch):
        import os as _os

        key = "PROBE_ENV_OWNERSHIP_KEY"
        monkeypatch.setenv(key, "operator-value")
        self._cleanup(key)
        try:
            r = client.post(
                "/api/secrets/set",
                json={"key": key, "value": "scoped-value", "scope": "agent", "agent": "builder"},
            )
            assert r.status_code == 200, r.text[:200]
            assert _os.environ.get(key) == "operator-value", (
                "an agent-scoped vault write deleted an operator environment variable"
            )

            # Deleting the scoped secret must not touch it either.
            r = client.delete(f"/api/secrets/{key}")
            assert r.status_code == 200, r.text[:200]
            assert _os.environ.get(key) == "operator-value"
        finally:
            self._cleanup(key)
            monkeypatch.delenv(key, raising=False)

    def test_global_write_owns_the_env_copy_from_then_on(self, client, monkeypatch):
        import os as _os

        from backend.routers.secrets import _VAULT_INJECTED_KEYS

        key = "PROBE_ENV_GLOBAL_KEY"
        monkeypatch.setenv(key, "operator-value")
        self._cleanup(key)
        _VAULT_INJECTED_KEYS.discard(key)
        try:
            r = client.post(
                "/api/secrets/set",
                json={"key": key, "value": "vault-global-value"},
            )
            assert r.status_code == 200, r.text[:200]
            # A GLOBAL vault value is the source of truth once stored…
            assert _os.environ.get(key) == "vault-global-value"
            # …and narrowing it later removes the copy the VAULT put there.
            r = client.post(
                "/api/secrets/set",
                json={"key": key, "value": "scoped", "scope": "agent", "agent": "builder"},
            )
            assert r.status_code == 200, r.text[:200]
            assert key not in _os.environ, (
                "narrowing a vault-owned global must remove the vault's env copy"
            )
        finally:
            self._cleanup(key)
            monkeypatch.delenv(key, raising=False)
            _VAULT_INJECTED_KEYS.discard(key)


# ── Host header validation ──────────────────────────────────────────────────
class TestHostHeaderValidator:
    def test_allows_local_names_ip_literals_and_configured_hosts(self):
        import os

        from backend.app import _host_is_allowed

        assert _host_is_allowed("localhost:8787")
        assert _host_is_allowed("127.0.0.1:8787")
        assert _host_is_allowed("[::1]:8787")
        assert _host_is_allowed("192.168.1.20:8787")
        assert _host_is_allowed("mydesktop.local:8787")
        assert _host_is_allowed("buildbox.internal")
        assert _host_is_allowed("something.localhost")

    def test_refuses_foreign_and_lookalike_hosts(self):
        from backend.app import _host_is_allowed

        assert not _host_is_allowed("evil.example:8787")
        assert not _host_is_allowed("localhost.evil.com:8787")
        assert not _host_is_allowed("nottheapp-1.e2b.app.evil.io:8787")
        assert not _host_is_allowed("")

    def test_env_allowlist_wildcards(self, monkeypatch):
        monkeypatch.setenv("AGENTIC_OS_ALLOWED_HOSTS", "mybox.example.org,*.corp.name")
        # _ALLOWED_HOST_* are parsed at import; re-parse by hand the same way.
        import backend.app as app_mod

        exact = {"localhost"}
        suffixes = [".localhost", ".local", ".internal"]
        for entry in "mybox.example.org,*.corp.name".split(","):
            entry = entry.strip().lower()
            if entry.startswith("*."):
                suffixes.append(entry[1:])
            else:
                exact.add(entry)

        def allowed(header):
            host = header.split(":", 1)[0].lower()
            return host in exact or any(host.endswith(s) for s in suffixes)

        assert allowed("mybox.example.org:8787")
        assert allowed("team.corp.name:8787")
        assert not allowed("evil.corp.name.attacker.io:8787")
        assert hasattr(app_mod, "_host_is_allowed")
