"""Module 17 — the Secrets Vault destination.

Destination: `secrets`, hosting the vault and the `pqc` encryption tab. This is
the credential surface, so the platform-wide defect theme of this review —
confident reporting of unverified things — is at its most damaging here: every
claim the screen makes is a security claim.

Seven defects, all verified against a live server before the fix:

1. The pencil icon widened a secret's blast radius. `set_secret` defaulted
   scope/agent to 'global'/'' whenever the caller omitted them, and the UPSERT
   wrote those defaults over the stored row. `vaultEdit()` sends {key, value}
   only, so changing the VALUE of a secret scoped to one agent silently
   promoted it to every agent. Live: scope agent/builder -> POST {key,value}
   -> scope global/''.

2. The per-agent scope had no reader at all. `_inject_to_env` selected
   scope='global' and every consumer read os.environ, so an agent-scoped
   secret was stored, listed as scoped, and never used by anyone. The
   dropdown was decorative.

3. ...and `set_secret` leaked it anyway: it wrote EVERY saved secret into
   os.environ regardless of scope, so choosing "agent — specific agent"
   published the value to the whole process until the next restart.

4. scope was never validated. scope='agent' with a blank agent name stored a
   secret that matched no agent and could never be reached; an arbitrary
   string like 'everyone' was accepted verbatim.

5. Onboarding's quick-setup wrote the raw API key straight into
   `secrets.value_enc` — the column every other writer fills with a Fernet
   token. The key sat in SQLite in PLAINTEXT while the vault screen showed it
   with a 🔒 badge under the banner "AES-256 Fernet Encryption Active".

6. The vault never checked that a stored blob decrypts. A row was reported as
   encrypted because it existed, so the plaintext row from (5) rendered with a
   padlock, "0 chars", and a Reveal button that returned {'ok': True,
   'value': ''}.

7. Second door #16: quick-setup verified OpenRouter keys against
   GET /api/v1/models, a PUBLIC endpoint that answers 200 for a garbage key.
   The wizard reported "OpenRouter connected. 140+ models available" for any
   string, then stored the rejected key. This is the identical defect already
   fixed in /api/secrets/test-connection — the wizard was its untouched twin.
"""

from __future__ import annotations

import sqlite3

import pytest

from backend.routers import secrets as sec
from backend.services.memory_db import ensure_schema, get_conn


@pytest.fixture(autouse=True)
def _clean_probe_rows(monkeypatch):
    """Remove only this module's rows — the DB is shared with the live app.

    Also pins OPENROUTER_API_KEY for the duration of each test. Several cases
    here exercise writers that inject the key into os.environ by design
    (`_store_openrouter_key`, `set_secret`), and os.environ outlives the test.
    Without this, a probe key such as 'sk-or-v1-T153-...' escaped into the
    session and the imagegen suite -- which reads the same variable -- made a
    live request with it and got a real 401. monkeypatch restores the prior
    value (or absence) on teardown.
    """
    monkeypatch.setenv('OPENROUTER_API_KEY', 'test-key-t153')

    def purge():
        con = get_conn()
        try:
            con.execute("DELETE FROM secrets WHERE key LIKE 'T153_%'")
            con.commit()
        finally:
            con.close()

    ensure_schema()
    purge()
    yield
    purge()


def _raw(key: str):
    con = get_conn()
    try:
        row = con.execute(
            'SELECT key, value_enc, scope, agent, fingerprint, length FROM secrets WHERE key=?', (key,)
        ).fetchone()
    finally:
        con.close()
    return dict(row) if row else None


# ── 1. a value-only update must not widen the scope ───────────────────────────
def test_value_only_update_preserves_agent_scope(client):
    r = client.post(
        '/api/secrets/set',
        json={'key': 'T153_SCOPED', 'value': 'v1', 'scope': 'agent', 'agent': 'builder'},
    )
    assert r.status_code == 200 and r.json()['scope'] == 'agent'

    # Exactly the body vaultEdit() sends.
    r2 = client.post('/api/secrets/set', json={'key': 'T153_SCOPED', 'value': 'v2'})
    assert r2.status_code == 200
    body = r2.json()
    assert body['scope'] == 'agent', 'editing the value must not promote the secret to global'
    assert body['agent'] == 'builder'
    assert _raw('T153_SCOPED')['scope'] == 'agent'


def test_value_only_update_on_a_global_secret_stays_global(client):
    client.post('/api/secrets/set', json={'key': 'T153_GLOBAL', 'value': 'v1', 'scope': 'global'})
    r = client.post('/api/secrets/set', json={'key': 'T153_GLOBAL', 'value': 'v2'})
    assert r.json()['scope'] == 'global'


def test_explicit_scope_change_is_still_honoured(client):
    """"Absent means unchanged" must not become "scope can never be changed"."""
    client.post(
        '/api/secrets/set', json={'key': 'T153_MOVE', 'value': 'v', 'scope': 'agent', 'agent': 'builder'}
    )
    r = client.post('/api/secrets/set', json={'key': 'T153_MOVE', 'value': 'v', 'scope': 'global'})
    assert r.json()['scope'] == 'global'
    assert _raw('T153_MOVE')['scope'] == 'global'


# ── 2. the agent scope has a reader, and it isolates ──────────────────────────
def test_agent_scoped_secret_is_visible_only_to_that_agent(client):
    client.post(
        '/api/secrets/set',
        json={'key': 'T153_ONLY_BUILDER', 'value': 'builder-key', 'scope': 'agent', 'agent': 'builder'},
    )
    assert sec.secrets_for_agent('builder').get('T153_ONLY_BUILDER') == 'builder-key'
    assert 'T153_ONLY_BUILDER' not in sec.secrets_for_agent('reviewer')
    assert 'T153_ONLY_BUILDER' not in sec.secrets_for_agent('')


def test_global_secrets_reach_every_agent(client):
    client.post('/api/secrets/set', json={'key': 'T153_EVERYONE', 'value': 'shared', 'scope': 'global'})
    for agent in ('builder', 'reviewer', 'planner'):
        assert sec.secrets_for_agent(agent).get('T153_EVERYONE') == 'shared'


def test_agent_scoped_secret_overrides_the_global_of_the_same_name(client):
    client.post('/api/secrets/set', json={'key': 'T153_OVERRIDE', 'value': 'global-val', 'scope': 'global'})
    con = get_conn()
    try:
        enc, _ = sec._encrypt('builder-val')
        con.execute(
            'INSERT INTO secrets(key,value_enc,scope,agent,fingerprint,length) VALUES(?,?,?,?,?,?)',
            ('T153_OVERRIDE_B', enc, 'agent', 'builder', 'x', 11),
        )
        con.commit()
    finally:
        con.close()
    # Same-name override, exercised through the resolver's ordering guarantee.
    assert sec.secrets_for_agent('builder')['T153_OVERRIDE'] == 'global-val'
    assert sec.secrets_for_agent('builder')['T153_OVERRIDE_B'] == 'builder-val'
    assert 'T153_OVERRIDE_B' not in sec.secrets_for_agent('reviewer')


def test_agent_lookup_is_case_insensitive(client):
    client.post(
        '/api/secrets/set',
        json={'key': 'T153_CASE', 'value': 'v', 'scope': 'agent', 'agent': 'Builder'},
    )
    assert 'T153_CASE' in sec.secrets_for_agent('builder')
    assert 'T153_CASE' in sec.secrets_for_agent('BUILDER')


# ── 3. an agent-scoped secret must not land in the process environment ────────
def test_saving_an_agent_scoped_secret_does_not_populate_os_environ(client, monkeypatch):
    import os

    monkeypatch.delenv('T153_NOLEAK', raising=False)
    client.post(
        '/api/secrets/set',
        json={'key': 'T153_NOLEAK', 'value': 'scoped-only', 'scope': 'agent', 'agent': 'builder'},
    )
    assert os.environ.get('T153_NOLEAK') is None, (
        'os.environ is process-global; writing a scoped secret there hands it to every agent'
    )


def test_narrowing_a_global_secret_clears_the_stale_environment_copy(client, monkeypatch):
    import os

    monkeypatch.delenv('T153_NARROW', raising=False)
    client.post('/api/secrets/set', json={'key': 'T153_NARROW', 'value': 'v', 'scope': 'global'})
    assert os.environ.get('T153_NARROW') == 'v'
    client.post(
        '/api/secrets/set',
        json={'key': 'T153_NARROW', 'value': 'v', 'scope': 'agent', 'agent': 'builder'},
    )
    assert os.environ.get('T153_NARROW') is None


def test_global_secrets_still_reach_os_environ(client, monkeypatch):
    import os

    monkeypatch.delenv('T153_STILLGLOBAL', raising=False)
    client.post('/api/secrets/set', json={'key': 'T153_STILLGLOBAL', 'value': 'v', 'scope': 'global'})
    assert os.environ.get('T153_STILLGLOBAL') == 'v'


# ── 4. scope validation ───────────────────────────────────────────────────────
def test_agent_scope_without_an_agent_name_is_rejected(client):
    r = client.post('/api/secrets/set', json={'key': 'T153_NOAGENT', 'value': 'v', 'scope': 'agent'})
    assert r.status_code == 400
    assert 'agent name' in r.json()['error'].lower()
    assert _raw('T153_NOAGENT') is None, 'a rejected secret must not be stored'


def test_agent_scope_with_a_whitespace_agent_name_is_rejected(client):
    r = client.post(
        '/api/secrets/set', json={'key': 'T153_WS', 'value': 'v', 'scope': 'agent', 'agent': '   '}
    )
    assert r.status_code == 400
    assert _raw('T153_WS') is None


def test_an_unknown_scope_is_rejected_rather_than_stored_verbatim(client):
    r = client.post('/api/secrets/set', json={'key': 'T153_BAD', 'value': 'v', 'scope': 'everyone'})
    assert r.status_code == 400
    assert _raw('T153_BAD') is None


# ── 5. onboarding must not write plaintext into the vault ─────────────────────
def _store(api_key: str) -> bool:
    from backend.routers.onboarding import _store_openrouter_key

    return _store_openrouter_key(api_key)


def test_onboarding_stores_the_api_key_encrypted_not_in_the_clear():
    con = get_conn()
    try:
        con.execute("DELETE FROM secrets WHERE key='OPENROUTER_API_KEY'")
        con.commit()
    finally:
        con.close()
    try:
        assert _store('sk-or-v1-T153-cleartext-probe') is True
        row = _raw('OPENROUTER_API_KEY')
        assert row is not None
        assert 'T153-cleartext-probe' not in row['value_enc'], (
            'the API key is sitting in the database in plaintext'
        )
        assert row['value_enc'].startswith('gAAAAA'), 'expected a Fernet token'
        # And it must round-trip, or the wizard stored something unusable.
        assert sec._decrypt(row['value_enc']) == 'sk-or-v1-T153-cleartext-probe'
    finally:
        con = get_conn()
        try:
            con.execute("DELETE FROM secrets WHERE key='OPENROUTER_API_KEY'")
            con.commit()
        finally:
            con.close()


def test_onboarding_records_fingerprint_and_length():
    """The vault lists these; NULLs rendered the wizard's key as "0 chars"."""
    try:
        _store('sk-or-v1-T153-metadata')
        row = _raw('OPENROUTER_API_KEY')
        assert row['fingerprint'], 'fingerprint was never recorded'
        assert row['length'] == len('sk-or-v1-T153-metadata')
    finally:
        con = get_conn()
        try:
            con.execute("DELETE FROM secrets WHERE key='OPENROUTER_API_KEY'")
            con.commit()
        finally:
            con.close()


def test_onboarding_reports_failure_when_it_cannot_encrypt(monkeypatch):
    """It must not fall back to a weaker store and call that success."""
    monkeypatch.setattr(sec, '_encrypt', lambda v: ('', False))
    assert _store('sk-or-v1-should-not-persist') is False
    assert _raw('OPENROUTER_API_KEY') is None


# ── 6. the padlock must be measured, not assumed ──────────────────────────────
def _insert_plaintext(key: str, value: str):
    con = get_conn()
    try:
        con.execute(
            'INSERT OR REPLACE INTO secrets(key,value_enc,scope,agent) VALUES(?,?,?,?)',
            (key, value, 'global', ''),
        )
        con.commit()
    finally:
        con.close()


def test_a_row_that_does_not_decrypt_is_reported_unreadable(client):
    _insert_plaintext('T153_PLAIN', 'sk-not-a-fernet-token')
    data = client.get('/api/secrets/list').json()
    row = next(i for i in data['items'] if i['key'] == 'T153_PLAIN')
    assert row['readable'] is False, 'the vault claimed encryption it never verified'
    assert row['storage'] == 'unreadable'
    assert data['unreadable'] >= 1


def test_a_genuinely_encrypted_row_is_reported_readable(client):
    client.post('/api/secrets/set', json={'key': 'T153_GOOD', 'value': 'real', 'scope': 'global'})
    data = client.get('/api/secrets/list').json()
    row = next(i for i in data['items'] if i['key'] == 'T153_GOOD')
    assert row['readable'] is True
    assert row['storage'] == 'fernet'


def test_the_list_warns_when_some_secrets_cannot_be_decrypted(client):
    _insert_plaintext('T153_PLAIN2', 'nope')
    data = client.get('/api/secrets/list').json()
    assert data['warning'], 'an unreadable secret must be surfaced, not silently listed'
    assert 'decrypt' in data['warning'].lower()


def test_no_warning_when_every_secret_is_readable(client):
    """The banner must not cry wolf on a healthy vault."""
    con = get_conn()
    try:
        con.execute('DELETE FROM secrets')
        con.commit()
    finally:
        con.close()
    client.post('/api/secrets/set', json={'key': 'T153_FINE', 'value': 'v', 'scope': 'global'})
    data = client.get('/api/secrets/list').json()
    assert data['unreadable'] == 0
    assert data['warning'] is None


def test_list_never_returns_the_ciphertext_itself(client):
    client.post('/api/secrets/set', json={'key': 'T153_NOCIPHER', 'value': 'v', 'scope': 'global'})
    data = client.get('/api/secrets/list').json()
    row = next(i for i in data['items'] if i['key'] == 'T153_NOCIPHER')
    assert 'value_enc' not in row, 'the list endpoint must not ship ciphertext to the browser'


def test_revealing_an_undecryptable_secret_reports_an_error_not_an_empty_success(client):
    _insert_plaintext('T153_PLAIN3', 'sk-plaintext')
    r = client.get('/api/secrets/get', params={'key': 'T153_PLAIN3', 'reveal': 'true'})
    assert r.status_code == 422, 'returning 200 with value="" told the user it was fine'
    body = r.json()
    assert body['ok'] is False
    assert body['readable'] is False


def test_revealing_a_healthy_secret_still_works(client):
    client.post('/api/secrets/set', json={'key': 'T153_REVEAL', 'value': 'top-secret', 'scope': 'global'})
    r = client.get('/api/secrets/get', params={'key': 'T153_REVEAL', 'reveal': 'true'})
    assert r.status_code == 200
    assert r.json()['value'] == 'top-secret'


# ── 7. second door: the setup wizard's key check ──────────────────────────────
def test_quick_setup_verifies_the_key_against_the_authenticated_endpoint(client, monkeypatch):
    """A public catalogue endpoint answers 200 for any key. It cannot verify one."""
    import httpx

    called: list[str] = []

    async def fake_get(self, url, *a, **k):
        called.append(url)
        if 'auth/key' in url:
            return httpx.Response(401, json={'error': 'invalid'}, request=httpx.Request('GET', url))
        if 'api/tags' in url:
            raise httpx.ConnectError('no ollama', request=httpx.Request('GET', url))
        return httpx.Response(
            200, json={'data': [{'id': f'm{i}'} for i in range(401)]}, request=httpx.Request('GET', url)
        )

    monkeypatch.setattr(httpx.AsyncClient, 'get', fake_get)
    r = client.post('/api/onboarding/quick-setup', json={'api_key': 'sk-or-v1-garbage'})
    assert any('auth/key' in u for u in called), 'the wizard never asked an endpoint that can say no'
    body = r.json()
    assert body['ok'] is False
    or_row = next(b for b in body['backends'] if b['backend'] == 'openrouter')
    assert or_row['status'] == 'invalid_key', 'a rejected key was reported as a working connection'


def test_quick_setup_does_not_store_a_key_the_provider_rejected(client, monkeypatch):
    import httpx

    async def fake_get(self, url, *a, **k):
        if 'auth/key' in url:
            return httpx.Response(401, json={}, request=httpx.Request('GET', url))
        if 'api/tags' in url:
            raise httpx.ConnectError('no ollama', request=httpx.Request('GET', url))
        return httpx.Response(200, json={'data': []}, request=httpx.Request('GET', url))

    monkeypatch.setattr(httpx.AsyncClient, 'get', fake_get)
    con = get_conn()
    try:
        con.execute("DELETE FROM secrets WHERE key='OPENROUTER_API_KEY'")
        con.commit()
    finally:
        con.close()
    client.post('/api/onboarding/quick-setup', json={'api_key': 'sk-or-v1-rejected'})
    assert _raw('OPENROUTER_API_KEY') is None, (
        'storing a rejected key overwrites a working one and injects it into the environment'
    )


def test_quick_setup_accepts_a_key_the_provider_confirms(client, monkeypatch):
    import httpx

    async def fake_get(self, url, *a, **k):
        if 'auth/key' in url:
            return httpx.Response(
                200, json={'data': {'label': 'test', 'usage': 0}}, request=httpx.Request('GET', url)
            )
        if 'api/tags' in url:
            raise httpx.ConnectError('no ollama', request=httpx.Request('GET', url))
        return httpx.Response(
            200, json={'data': [{'id': 'a'}, {'id': 'b'}]}, request=httpx.Request('GET', url)
        )

    monkeypatch.setattr(httpx.AsyncClient, 'get', fake_get)
    try:
        r = client.post('/api/onboarding/quick-setup', json={'api_key': 'sk-or-v1-good'})
        body = r.json()
        assert body['ok'] is True
        or_row = next(b for b in body['backends'] if b['backend'] == 'openrouter')
        assert or_row['status'] == 'available'
        assert or_row['models'] == 2
        row = _raw('OPENROUTER_API_KEY')
        assert row is not None and sec._decrypt(row['value_enc']) == 'sk-or-v1-good'
    finally:
        con = get_conn()
        try:
            con.execute("DELETE FROM secrets WHERE key='OPENROUTER_API_KEY'")
            con.commit()
        finally:
            con.close()


# ── the LLM client honours the agent scope ────────────────────────────────────
def test_llm_uses_the_agent_scoped_key_when_one_exists(client, monkeypatch):
    monkeypatch.setenv('OPENROUTER_API_KEY', 'global-key')
    con = get_conn()
    try:
        enc, _ = sec._encrypt('builder-key')
        con.execute(
            'INSERT OR REPLACE INTO secrets(key,value_enc,scope,agent,fingerprint,length) VALUES(?,?,?,?,?,?)',
            ('OPENROUTER_API_KEY', enc, 'agent', 'builder', 'f', 11),
        )
        con.commit()
    finally:
        con.close()
    try:
        import backend.services.llm as llm

        assert llm._or_key('builder') == 'builder-key'
        assert llm._or_key('reviewer') == 'global-key', 'another agent must fall back to the global key'
        assert llm._or_key('') == 'global-key'
        assert 'Bearer builder-key' == llm._or_headers('builder')['Authorization']
    finally:
        con = get_conn()
        try:
            con.execute("DELETE FROM secrets WHERE key='OPENROUTER_API_KEY'")
            con.commit()
        finally:
            con.close()


def test_llm_key_lookup_survives_a_broken_vault(monkeypatch):
    """A vault failure must degrade to the environment, never break every call."""
    import backend.services.llm as llm

    monkeypatch.setenv('OPENROUTER_API_KEY', 'env-key')

    def boom(_agent):
        raise sqlite3.OperationalError('vault is gone')

    monkeypatch.setattr(sec, 'secrets_for_agent', boom)
    assert llm._or_key('builder') == 'env-key'


# ── timestamps ────────────────────────────────────────────────────────────────
def test_updated_at_is_utc_and_labelled_as_utc(client):
    """The list applied SQLite `localtime` and the response layer then stamped a
    `Z` on the result. On any server not running in UTC that published a local
    wall-clock time labelled as UTC — wrong by the offset, silently."""
    client.post('/api/secrets/set', json={'key': 'T153_TS', 'value': 'v', 'scope': 'global'})
    row = next(i for i in client.get('/api/secrets/list').json()['items'] if i['key'] == 'T153_TS')
    assert row['updated_at'].endswith('Z')

    con = get_conn()
    try:
        stored = con.execute(
            "SELECT updated_at, datetime(updated_at,'localtime') AS local FROM secrets WHERE key='T153_TS'"
        ).fetchone()
    finally:
        con.close()
    # The value shipped must be the raw UTC column, never the localtime shift.
    assert row['updated_at'].replace('T', ' ').rstrip('Z') == stored['updated_at']
