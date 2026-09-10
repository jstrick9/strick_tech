"""
SEC-11: Authentication flow, DNS-rebinding defense, and vault strictness.

Live-socket tests (the in-process unit suite bypasses the host check by
design, so these run against a real server):

  * Host header validation — a foreign Host must be refused (403) before any
    handler runs, while localhost/IP hosts continue to work. This is the
    DNS-rebinding defense for a localhost server; without it a public DNS
    name that flips to 127.0.0.1 makes the browser treat attacker pages as
    same-origin and CORS is never consulted.
  * Secrets vault — revealed values must carry Cache-Control: no-store, a
    tampered/plaintext value_enc must be reported unreadable (list) and
    refused (reveal 422), never "decrypted" into mojibake.
  * Auth lifecycle — register → login → me → logout, wrong-password 401, and
    the login failure throttle (429 + Retry-After).
"""
from __future__ import annotations

import sqlite3
import uuid

import pytest

from tests.security.conftest import BASE, DELETE, GET, POST, sec_ok, uid
from tests._csrf_client import async_client as _csrf_async_client


def _uniq(p="sec11"):
    return f"{p}_{uuid.uuid4().hex[:10]}"


@pytest.fixture
async def C2():
    """A second CSRF client used for Host-header tests (base URL overridden per call)."""
    async with _csrf_async_client(BASE, timeout=20) as c:
        yield c


# ── DNS-rebinding / Host header validation ─────────────────────────────────
class TestSecHostHeaderValidation:
    async def test_foreign_host_is_refused_before_any_handler(self, C2):
        r = await C2.get("/api/system/health", headers={"Host": "evil.example"})
        assert r.status_code == 403, (
            f"a rebound Host must be refused, got {r.status_code}: {r.text[:200]}"
        )
        assert "AGENTIC_OS_ALLOWED_HOSTS" in r.text, "the refusal must tell the operator the fix"

    async def test_localhost_and_ip_hosts_still_work(self, C2):
        r = await C2.get("/api/system/health")
        assert r.status_code == 200

    async def test_lookalike_suffix_hosts_are_refused(self, C2):
        r = await C2.get("/api/system/health", headers={"Host": "localhost.evil.example"})
        assert r.status_code == 403

    async def test_webhook_paths_remain_reachable_for_foreign_hosts(self, C2):
        # Webhooks are called by GitHub/Stripe/CI from outside; they must keep
        # working for whatever hostname the operator registered. A 403 from
        # the Host gate here would silently kill every webhook integration.
        r = await C2.post(
            "/api/webhooks/github",
            headers={"Host": "ci.corp.example"},
            json={"zen": "Keep it logically awesome."},
        )
        assert r.status_code != 403, "webhook endpoints must be exempt from the Host gate"
        sec_ok(r, "webhook with foreign host")


# ── Secrets vault strictness ────────────────────────────────────────────────
class TestSecVaultStrictness:
    async def test_reveal_and_metadata_responses_are_never_cacheable(self, C):
        key = uid("SEC_NOSTORE").upper()
        try:
            await POST(C, "/api/secrets/set", {"key": key, "value": "never-cache-me"})
            r = await GET(C, "/api/secrets/get", key=key)
            assert r.headers.get("cache-control") == "no-store", (
                f"metadata response cacheable: {dict(r.headers)}"
            )
            r = await GET(C, "/api/secrets/get", key=key, reveal="true")
            assert r.headers.get("cache-control") == "no-store", (
                f"revealed value cacheable: {dict(r.headers)}"
            )
            assert "never-cache-me" in r.text
        finally:
            await DELETE(C, f"/api/secrets/{key}")

    async def test_plaintext_tampered_row_is_reported_unreadable_and_reveal_refused(self, C):
        """A value_enc that is not Fernet must fail CLOSED everywhere.

        Before the fix, the list view flagged such rows "unreadable" while
        _decrypt() happily base64-decoded them into mojibake — which then went
        straight into os.environ as an API key.
        """
        from backend.config import get_data_dir

        key = uid("SEC_TAMPER").upper()
        try:
            await POST(C, "/api/secrets/set", {"key": key, "value": "real-value-1"})
            # Tamper: write a plaintext blob into value_enc directly.
            db = get_data_dir() / "memory" / "agentic.db"
            con = sqlite3.connect(db, timeout=10)
            try:
                con.execute(
                    "UPDATE secrets SET value_enc=? WHERE key=?",
                    ("ghp_this_is_not_fernet_at_all", key),
                )
                con.commit()
            finally:
                con.close()

            listing = await GET(C, "/api/secrets/list")
            item = next((i for i in listing.json().get("items", []) if i["key"] == key), None)
            assert item is not None
            assert item["readable"] is False, "tampered row must not claim the padlock"
            assert listing.json().get("unreadable", 0) >= 1

            r = await GET(C, "/api/secrets/get", key=key, reveal="true")
            assert r.status_code == 422, f"reveal must refuse, got {r.status_code}"
            assert "could not be decrypted" in r.text
            assert "ghp_this_is_not_fernet" not in r.text, "no mojibake may leak back"
        finally:
            await DELETE(C, f"/api/secrets/{key}")

    async def test_startup_injection_cannot_promote_tampered_rows(self, C):
        """_inject_to_env uses the same strict decrypt: garbage never reaches env."""
        from backend.routers.secrets import _decrypt

        # A base64-looking string that IS decodable — the old fallback would
        # have returned its bytes; the strict path must return ''.
        legacy_b64 = "c2hha2VuX25vdF9hX3ZhbGlkX3NlY3JldA=="
        assert _decrypt(legacy_b64) == "", "base64 fallback must be gone"
        assert _decrypt("") == ""


# ── Auth lifecycle against the live server ─────────────────────────────────
class TestSecLiveAuthLifecycle:
    async def test_register_login_me_logout_roundtrip(self, C):
        user, pw = _uniq("sec11user"), "live-round-trip-1"
        try:
            r = await POST(C, "/api/auth/register", {"username": user, "password": pw})
            assert r.status_code == 200 and r.json().get("ok"), r.text[:200]
            assert r.json()["api_key"].startswith("ak_")

            r = await POST(C, "/api/auth/login", {"username": user, "password": pw})
            assert r.status_code == 200, r.text[:200]
            d = r.json()
            token = d["token"]
            assert token.startswith("ses_")

            me = await C.get("/api/auth/me", headers={"Authorization": f"Bearer {token}"})
            assert me.status_code == 200
            assert me.json()["authenticated"] is True

            r = await C.post(
                "/api/auth/logout",
                headers={"Authorization": f"Bearer {token}"},
            )
            assert r.status_code == 200

            dead = await C.get("/api/auth/me", headers={"Authorization": f"Bearer {token}"})
            assert dead.status_code == 401, "revoked session must not authenticate"
        finally:
            # Remove the user so the live deployment returns to its prior
            # "auth not configured" state for other suites.
            from backend.config import get_data_dir

            db = get_data_dir() / "memory" / "agentic.db"
            con = sqlite3.connect(db, timeout=10)
            try:
                con.execute("DELETE FROM auth_sessions WHERE user_id IN (SELECT id FROM auth_users WHERE username=?)", (user,))
                con.execute("DELETE FROM auth_users WHERE username=?", (user,))
                con.commit()
            finally:
                con.close()

    async def test_wrong_password_is_401_without_leaking_which_part_failed(self, C):
        r = await POST(C, "/api/auth/login", {"username": _uniq("ghost"), "password": "x" * 8})
        assert r.status_code == 401
        assert "Invalid username or password" in r.text
        assert "user" in r.text  # one message for both cases; no enumeration hint

    async def test_login_throttle_locks_one_account_not_the_endpoint(self, C):
        user = _uniq("bruteforce")
        pw = "correct-password-9"
        await POST(C, "/api/auth/register", {"username": user, "password": pw})
        try:
            saw_429 = None
            for _ in range(40):
                r = await POST(C, "/api/auth/login", {"username": user, "password": "wrong"})
                if r.status_code == 429:
                    saw_429 = r
                    break
                assert r.status_code == 401
            assert saw_429 is not None, "sustained failures must trip the throttle"
            assert "Retry-After" in saw_429.headers
            # The throttle is per-account: a DIFFERENT user can still sign in
            # (probe with a bad password: must be 401, not 429).
            other = await POST(C, "/api/auth/login", {"username": _uniq("bystander"), "password": "nope"})
            assert other.status_code == 401, "bystander accounts must not be collaterally locked"
        finally:
            from backend.config import get_data_dir

            db = get_data_dir() / "memory" / "agentic.db"
            con = sqlite3.connect(db, timeout=10)
            try:
                con.execute("DELETE FROM auth_sessions WHERE user_id IN (SELECT id FROM auth_users WHERE username=?)", (user,))
                con.execute("DELETE FROM auth_users WHERE username=?", (user,))
                con.commit()
            finally:
                con.close()
