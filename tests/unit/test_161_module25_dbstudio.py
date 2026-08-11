"""Module 25 — the Database Studio destination (`dbstudio`).

`backend/services/db_policy.py` is a genuinely well-built control. Its docstring
explains why output-side redaction alone is not enough (an alias defeats it) and
it implements both directions: refuse statements that NAME a secret, and redact
by column on the way out. Probing it directly, it holds:

    SELECT signing_key FROM agent_identities            -> refused
    SELECT signing_key AS blob FROM agent_identities    -> refused
    SELECT * FROM agent_identities                      -> signing_key [REDACTED]
    CREATE TABLE copy AS SELECT * FROM agent_identities -> copy is redacted too

The defect is not the policy. It is that the policy was wired into the two READ
paths and into **neither write path**.

Four defects, all reproduced against a live server before the fix:

1. SQL INJECTION VIA `pk_column`. The delete endpoint validated the table name
   against an identifier pattern and then interpolated the CALLER'S column name
   into the same statement unchecked:

       DELETE FROM "<table>" WHERE "<pk_column>"=?

   A `"` closes the quoted identifier. Verified live against a 3-row table:
       {"pk_column": 'a" OR 1=1 OR "a', "pk_value": "nope"}
     -> {"ok": true, "deleted": 3}
   Three rows destroyed by a pk_value that matched nothing. The parameterised
   `?` beside it gave the appearance of safety.

2. DATABASE STUDIO COULD NOT READ THE SECRETS TABLE BUT COULD DELETE FROM IT.
   Verified live: a planted row in `secrets` was removed by
   DELETE /api/db/sqlite/table/secrets/row -> {"ok": true, "deleted": 1}.
   Destroying credential material is strictly worse than reading it — reading a
   vault entry leaks one secret; deleting it locks every agent out of that
   provider and the row is gone.

3. The insert endpoint had the same gap in both respects: no policy check, and
   caller-supplied column names interpolated into the INSERT.

4. Writing a sensitive COLUMN of an otherwise-browsable table was unguarded, so
   `signing_key` — the key that signs audit receipts — could be overwritten,
   forging the ledger just as effectively as reading it.
"""

from __future__ import annotations

import pytest

from backend.services import db_policy


@pytest.fixture
def victim(client):
    """A throwaway table with three rows, for destructive probes."""
    from backend.services.memory_db import get_conn

    con = get_conn()
    try:
        con.execute('DROP TABLE IF EXISTS t160_victim')
        con.execute('CREATE TABLE t160_victim(a TEXT)')
        for v in ('row1', 'row2', 'row3'):
            con.execute('INSERT INTO t160_victim VALUES(?)', (v,))
        con.commit()
    finally:
        con.close()
    yield 't160_victim'
    con = get_conn()
    try:
        con.execute('DROP TABLE IF EXISTS t160_victim')
        con.commit()
    finally:
        con.close()


def _count(table: str) -> int:
    from backend.services.memory_db import get_conn

    con = get_conn()
    try:
        return con.execute(f'SELECT COUNT(*) FROM "{table}"').fetchone()[0]
    finally:
        con.close()




@pytest.fixture
def seeded_identity():
    """Guarantee one agent_identities row with a real signing_key.

    The unit harness sandboxes the database (conftest sets AGENTIC_TEST_DB to
    its own file), so these tests cannot rely on rows that happen to exist in
    the dev database. Revert-proof exposed this: the redaction tests were
    guarded with `if body.get('rows')` and simply did nothing.
    """
    from backend.services.memory_db import get_conn

    con = get_conn()
    try:
        con.execute(
            """CREATE TABLE IF NOT EXISTS agent_identities (
                   agent_id TEXT PRIMARY KEY, signing_key TEXT, created_at TEXT)"""
        )
        con.execute(
            'INSERT OR REPLACE INTO agent_identities(agent_id,signing_key,created_at) VALUES(?,?,?)',
            ('t160_seed', '-----BEGIN PRIVATE KEY-----\nSECRETMATERIAL', '2026-01-01'),
        )
        con.commit()
    finally:
        con.close()
    yield 't160_seed'
    con = get_conn()
    try:
        con.execute("DELETE FROM agent_identities WHERE agent_id LIKE 't160%'")
        con.commit()
    finally:
        con.close()


def _csrf(client):
    """POST/DELETE on /api/db/** require a CSRF token.

    Added after revert-proof: `test_select_star_redacts_rather_than_leaking`
    did NOT fail when redaction was disabled, because the request was rejected
    for a missing CSRF token first and its `if body.get('rows')` guard then made
    the assertion vacuous. A test that cannot see any rows cannot prove they were
    masked.
    """
    r = client.get('/api/security/csrf-token')
    tok = r.json().get('csrf_token', '')
    return {'X-CSRF-Token': tok}


def _query(client, sql, **extra):
    body = {'sql': sql}
    body.update(extra)
    return client.post('/api/db/sqlite/query', json=body, headers=_csrf(client))


def _delete(client, table, **body):
    return client.request('DELETE', f'/api/db/sqlite/table/{table}/row', json=body, headers=_csrf(client))


# ── 1. pk_column injection ────────────────────────────────────────────────────
def test_a_quoted_pk_column_cannot_wipe_the_table(client, victim):
    r = _delete(client, victim, pk_column='a" OR 1=1 OR "a', pk_value='nope')
    assert r.status_code == 400, 'an injected identifier deleted every row'
    assert _count(victim) == 3


@pytest.mark.parametrize(
    'pk',
    [
        'a" OR 1=1 OR "a',
        'a"; DROP TABLE t160_victim; --',
        'a" --',
        "a' OR '1'='1",
        'a`',
        'a]',
        '1=1',
        '',
        'a b',
    ],
)
def test_malformed_column_names_are_refused(client, victim, pk):
    r = _delete(client, victim, pk_column=pk, pk_value='x')
    assert r.status_code == 400
    assert _count(victim) == 3


def test_a_legitimate_delete_still_works(client, victim):
    """Over-validating would break the feature."""
    r = _delete(client, victim, pk_column='a', pk_value='row2')
    assert r.status_code == 200 and r.json()['deleted'] == 1
    assert _count(victim) == 2


def test_a_delete_matching_nothing_deletes_nothing(client, victim):
    r = _delete(client, victim, pk_column='a', pk_value='no_such_row')
    assert r.json()['deleted'] == 0
    assert _count(victim) == 3


# ── 2 & 3. the policy must apply to writes, not only reads ────────────────────
@pytest.mark.parametrize('table', sorted(db_policy.RESTRICTED_TABLES))
def test_deleting_from_a_restricted_table_is_refused(client, table):
    r = _delete(client, table, pk_column='id', pk_value='anything')
    assert r.status_code == 403, f'{table} could be deleted from but not read'
    assert r.json()['forbidden'] is True


@pytest.mark.parametrize('table', sorted(db_policy.RESTRICTED_TABLES))
def test_inserting_into_a_restricted_table_is_refused(client, table):
    r = client.post(f'/api/db/sqlite/table/{table}/insert', json={'row': {'id': 't160'}}, headers=_csrf(client))
    assert r.status_code == 403
    assert r.json()['forbidden'] is True


def test_a_planted_secret_survives_a_delete_attempt(client):
    """The concrete reproduction: the row was really being destroyed."""
    from backend.services.memory_db import get_conn

    con = get_conn()
    try:
        con.execute(
            "INSERT OR REPLACE INTO secrets(key,value_enc,scope,agent) VALUES('T160_PROBE','gAAAAAfake','global','')"
        )
        con.commit()
    finally:
        con.close()
    try:
        _delete(client, 'secrets', pk_column='key', pk_value='T160_PROBE')
        con = get_conn()
        try:
            assert con.execute("SELECT COUNT(*) FROM secrets WHERE key='T160_PROBE'").fetchone()[0] == 1
        finally:
            con.close()
    finally:
        con = get_conn()
        try:
            con.execute("DELETE FROM secrets WHERE key='T160_PROBE'")
            con.commit()
        finally:
            con.close()


def test_writes_to_an_ordinary_table_are_unaffected(client, victim):
    r = client.post(f'/api/db/sqlite/table/{victim}/insert', json={'row': {'a': 'row4'}}, headers=_csrf(client))
    assert r.status_code == 200 and r.json()['ok'] is True
    assert _count(victim) == 4


# ── 4. sensitive columns of browsable tables ──────────────────────────────────
def test_writing_a_signing_key_is_refused(client, seeded_identity):
    """signing_key signs audit receipts — writing it forges the ledger."""
    r = client.post(
        '/api/db/sqlite/table/agent_identities/insert',
        json={'row': {'agent_id': 't160_x', 'signing_key': 'attacker-key'}},
        headers=_csrf(client),
    )
    assert r.status_code == 403
    assert 'signing_key' in r.json()['error']


def test_writing_a_non_sensitive_column_of_the_same_table_is_allowed(client, seeded_identity):
    """The column rule must not become a table rule."""
    from backend.services.memory_db import get_conn

    try:
        r = client.post(
            '/api/db/sqlite/table/agent_identities/insert',
            json={'row': {'agent_id': 't160_ok', 'created_at': '2026-01-01'}},
            headers=_csrf(client),
        )
        assert r.status_code != 403, 'a harmless column was blocked by the sensitive-column rule'
    finally:
        con = get_conn()
        try:
            con.execute("DELETE FROM agent_identities WHERE agent_id LIKE 't160%'")
            con.commit()
        finally:
            con.close()


def test_invalid_insert_column_names_are_refused(client, victim):
    """Defensive check — see the note in sqlite_insert().

    Unlike pk_column, an injected INSERT column is not exploitable today: the
    placeholder count always equals len(row), so the statement fails to execute
    rather than writing attacker-chosen values. This asserts the refusal is
    clean (400, nothing written) rather than an incidental SQL error.
    """
    before = _count(victim)
    r = client.post(
        f'/api/db/sqlite/table/{victim}/insert',
        json={'row': {'a" ,x) VALUES (1); --': 'v'}},
        headers=_csrf(client),
    )
    assert r.status_code == 400
    assert _count(victim) == before


def test_a_non_object_row_is_refused(client, victim):
    assert client.post(f'/api/db/sqlite/table/{victim}/insert', json={'row': ['a']}, headers=_csrf(client)).status_code == 400


# ── the read policy: pinned so a future edit cannot quietly weaken it ─────────
def test_naming_a_secret_column_is_refused(client, seeded_identity):
    assert _query(client, 'SELECT signing_key FROM agent_identities LIMIT 1').json()['ok'] is False


def test_aliasing_a_secret_column_is_still_refused(client, seeded_identity):
    """An alias defeats any filter that only inspects result-column names."""
    assert _query(client, 'SELECT signing_key AS blob FROM agent_identities LIMIT 1').json()['ok'] is False


def test_wrapping_a_secret_column_in_a_function_is_still_refused(client, seeded_identity):
    assert _query(client, 'SELECT substr(signing_key,1,8) FROM agent_identities LIMIT 1').json()['ok'] is False


def test_select_star_redacts_rather_than_leaking(client, seeded_identity):
    """`SELECT *` never names the column, so only output redaction catches it."""
    body = _query(client, 'SELECT * FROM agent_identities LIMIT 1').json()
    assert body['ok'] is True, f'the probe never reached the endpoint: {body.get("error")}'
    assert body['rows'], 'no rows returned — the assertion below would be vacuous'
    assert body['rows'][0]['signing_key'] == db_policy.REDACTED
    assert 'signing_key' in body['redacted_columns']


def test_a_copy_of_a_protected_table_is_redacted_too(client, seeded_identity):
    """Defence in depth: the global column-name rule covers derived tables."""
    from backend.services.memory_db import get_conn

    _query(client, 'CREATE TABLE t160_copy AS SELECT * FROM agent_identities', allow_write=True)
    try:
        body = _query(client, 'SELECT * FROM t160_copy LIMIT 1').json()
        assert body['ok'] is True and body['rows'], 'the copy was never created — assertion would be vacuous'
        assert body['rows'][0]['signing_key'] == db_policy.REDACTED
    finally:
        con = get_conn()
        try:
            con.execute('DROP TABLE IF EXISTS t160_copy')
            con.commit()
        finally:
            con.close()


def test_restricted_tables_are_refused_by_the_query_endpoint(client):
    assert _query(client, 'SELECT * FROM secrets LIMIT 1').json()['ok'] is False


def test_an_ordinary_query_still_works(client):
    body = _query(client, 'SELECT COUNT(*) AS n FROM agents').json()
    assert body['ok'] is True, f'a harmless query was refused: {body.get("error")}'
