"""Module 17 follow-ups 2, 3 and 4 — Database Studio.

FOLLOW-UP 2 — credential material was browsable.
The review note said "the secrets table should be excluded". Verified live, the
real exposure was worse:

    POST /api/db/sqlite/query
      {"sql": "SELECT agent_id, signing_key FROM agent_identities LIMIT 1"}
    -> {"ok": true, "rows": [{"signing_key": "-----BEGIN PRIVATE KEY-----..."}]}

`agent_identities.signing_key` is the private key `audit_log._issue_receipt()`
uses to sign audit receipts. Reading it lets an attacker forge receipts for the
ledger added in 486239d — the tamper-evidence control and the material that
defeats it were in the same browsable table. That this is a genuine control is
settled by `agent_identity.get_agent_identity()`, which already sets
`signing_key = '[REDACTED]'` "for security". Database Studio was a second door
into the same row.

FOLLOW-UP 3 — every statement auto-committed, so a mistyped DELETE was
instantly permanent with no undo.

FOLLOW-UP 4 — `/sqlite/ai-schema` returned LLM-authored DDL that the UI put
behind a bare "Create Table" button, with no analysis against the real schema.
"""

from __future__ import annotations

import uuid

import pytest

from backend.services import db_policy


def _run(client, sql: str, allow_write: bool = False, dry_run: bool = False):
    return client.post(
        '/api/db/sqlite/query',
        json={'sql': sql, 'allow_write': allow_write, 'dry_run': dry_run},
    )


def _find_audit(client, action_type: str, needle: str):
    r = client.get(f'/api/audit-log?action_type={action_type}&limit=200')
    for e in r.json().get('entries', []):
        if needle in f"{e.get('action_detail', '')} {e.get('metadata', '')}":
            return e
    return None


@pytest.fixture()
def identity(client):
    """Guarantee a real signing key exists.

    Without this the three most important assertions in this file skipped
    silently on a fresh sandboxed DB — a test that skips when the data is
    missing proves nothing about the leak it was written for.
    """
    from backend.routers.agent_identity import provision_agent_identity

    agent_id = 'zz_policy_probe'
    try:
        provision_agent_identity(agent_id, 'Policy Probe')
    except Exception:  # already provisioned
        pass
    from backend.services.memory_db import get_conn

    con = get_conn()
    try:
        row = con.execute(
            'SELECT signing_key FROM agent_identities WHERE agent_id=?', (agent_id,)
        ).fetchone()
    finally:
        con.close()
    assert row and row['signing_key'], 'could not provision a signing key to test against'
    return agent_id


@pytest.fixture()
def victim(client):
    name = 'dr_t_' + uuid.uuid4().hex[:8]
    assert _run(client, f'CREATE TABLE "{name}" (id INTEGER PRIMARY KEY, x TEXT)', True).json()['ok']
    for i in range(5):
        _run(client, f'INSERT INTO "{name}"(x) VALUES (\'r{i}\')', True)
    yield name
    _run(client, f'DROP TABLE IF EXISTS "{name}"', True)


def _count(client, table: str) -> int:
    r = _run(client, f'SELECT COUNT(*) AS c FROM "{table}"')
    return r.json()['rows'][0]['c']


# ══ FOLLOW-UP 2 — sensitive data ═══════════════════════════════════════════════
def test_signing_key_cannot_be_selected(client, identity):
    """The private keys that sign audit receipts must not be readable."""
    r = _run(client, 'SELECT agent_id, signing_key FROM agent_identities LIMIT 1')
    assert r.status_code == 403, 'audit-receipt signing keys were returned over HTTP'
    assert r.json().get('sensitive') is True


@pytest.mark.parametrize(
    'sql',
    [
        'SELECT signing_key AS x FROM agent_identities LIMIT 1',
        'SELECT substr(signing_key, 1, 40) FROM agent_identities LIMIT 1',
        'SELECT group_concat(signing_key) FROM agent_identities',
        'SELECT hex(signing_key) FROM agent_identities LIMIT 1',
        'SELECT s.signing_key FROM agent_identities s LIMIT 1',
    ],
)
def test_aliasing_and_wrapping_do_not_defeat_the_filter(client, sql):
    """Output-column filtering loses to a four-character alias.

    None of these produce a result column named `signing_key`, so a filter that
    inspects only result-column names would pass every one of them through. The
    statement itself has to be scanned — the same lesson as the prefix-matching
    bugs in Modules 12 and 17.
    """
    r = _run(client, sql)
    assert r.status_code == 403, f'secret leaked via {sql!r}'


def test_select_star_is_redacted_on_the_way_out(client, identity):
    """`SELECT *` never names the column, so the statement scan cannot see it."""
    r = _run(client, 'SELECT * FROM agent_identities LIMIT 50')
    assert r.status_code == 200, r.text
    body = r.json()
    assert body['rows'], 'fixture failed to provision an identity'
    assert all(row['signing_key'] == db_policy.REDACTED for row in body['rows'])
    assert 'signing_key' in body['redacted_columns']


def test_redaction_is_a_placeholder_not_a_truncation(client, identity):
    """Returning the first N chars of a key is a head start on recovering it."""
    rows = _run(client, 'SELECT * FROM agent_identities LIMIT 50').json()['rows']
    assert rows, 'fixture failed to provision an identity'
    for row in rows:
        assert 'BEGIN' not in str(row['signing_key'])
        assert row['signing_key'] == db_policy.REDACTED


@pytest.mark.parametrize('table', sorted(db_policy.RESTRICTED_TABLES))
def test_restricted_tables_are_refused_by_both_doors(client, table):
    """The SQL editor and the table browser are two paths to the same rows."""
    assert _run(client, f'SELECT * FROM {table}').status_code == 403
    assert client.get(f'/api/db/sqlite/table/{table}?limit=1').status_code == 403


def test_public_key_is_still_readable(client, identity):
    """Over-blocking would make the tool useless — only the private half is secret."""
    r = _run(client, 'SELECT agent_id, public_key FROM agent_identities LIMIT 1')
    assert r.status_code == 200, r.text


def test_refused_read_is_recorded_in_the_audit_chain(client):
    _run(client, 'SELECT signing_key FROM agent_identities')
    e = _find_audit(client, 'db_sql_refused', 'signing_key')
    assert e is not None, 'an attempt to read credential material left no trace'
    assert e['risk_level'] == 'critical'


def test_table_list_flags_protected_and_masked_tables(client, identity):
    tables = {t['name']: t for t in client.get('/api/db/sqlite/tables').json()}
    if 'secrets' in tables:
        assert tables['secrets']['restricted'] is True
    if 'agent_identities' in tables:
        assert 'signing_key' in tables['agent_identities']['sensitive_columns']
        assert tables['agent_identities']['restricted'] is False, 'browsing it is fine once masked'


def test_override_is_process_level_not_a_request_parameter(client, monkeypatch):
    """A per-request flag is a switch the attacker controls, not the operator."""
    r = client.post(
        '/api/db/sqlite/query',
        json={
            'sql': 'SELECT signing_key FROM agent_identities',
            'allow_sensitive': True,
            'AGENTIC_DB_ALLOW_SENSITIVE': True,
        },
    )
    assert r.status_code == 403, 'a request body field disabled the sensitive-data policy'

    monkeypatch.setenv('AGENTIC_DB_ALLOW_SENSITIVE', '1')
    assert db_policy.check_statement('SELECT signing_key FROM agent_identities') == ''


def test_unknown_table_with_a_secret_column_name_is_still_protected():
    """New tables get protection by default; an allow-list would miss the next one."""
    assert db_policy.is_sensitive_column('some_future_table', 'api_key')
    assert db_policy.is_sensitive_column('some_future_table', 'private_key')
    assert not db_policy.is_sensitive_column('some_future_table', 'display_name')


# ══ FOLLOW-UP 3 — dry run / undo ═══════════════════════════════════════════════
def test_dry_run_reports_the_row_count_without_committing(client, victim):
    before = _count(client, victim)
    assert before == 5

    r = _run(client, f'DELETE FROM "{victim}"', allow_write=True, dry_run=True)
    assert r.status_code == 200, r.text
    body = r.json()
    assert body['dry_run'] is True
    assert body['committed'] is False
    assert body['rows_affected'] == 5
    assert body['deltas'] == {victim: -5}

    assert _count(client, victim) == 5, 'the dry run COMMITTED — data was destroyed'


def test_dry_run_of_a_drop_leaves_the_table_intact(client, victim):
    r = _run(client, f'DROP TABLE "{victim}"', allow_write=True, dry_run=True)
    assert r.status_code == 200 and r.json()['committed'] is False
    assert _count(client, victim) == 5, 'the table was actually dropped by a dry run'


def test_dry_run_reports_the_risk_level(client, victim):
    body = _run(client, f'DELETE FROM "{victim}"', allow_write=True, dry_run=True).json()
    assert body['risk'] == 'critical'


def test_dry_run_is_audited_but_not_as_a_write(client, victim):
    _run(client, f'DELETE FROM "{victim}"', allow_write=True, dry_run=True)
    assert _find_audit(client, 'db_sql_dryrun', victim) is not None
    e = _find_audit(client, 'db_sql_write', victim)
    assert e is None or 'DELETE' not in e.get('action_detail', ''), (
        'a dry run was recorded as an executed write'
    )


def test_dry_run_still_honours_the_sensitive_policy(client):
    r = _run(client, 'SELECT signing_key FROM agent_identities', allow_write=True, dry_run=True)
    assert r.status_code == 403, 'dry_run bypassed the sensitive-data policy'


def test_dry_run_of_a_broken_statement_returns_the_error(client):
    r = _run(client, 'DELETE FROM no_such_table_xyz', allow_write=True, dry_run=True)
    assert r.status_code == 400
    assert r.json()['ok'] is False


def test_normal_run_still_commits(client, victim):
    """The dry-run path must not have made real writes disappear."""
    _run(client, f'DELETE FROM "{victim}" WHERE id=1', allow_write=True)
    assert _count(client, victim) == 4


# ══ FOLLOW-UP 4 — AI-authored DDL confirmation ═════════════════════════════════
def test_ai_schema_returns_a_plan_requiring_confirmation(client):
    r = client.post('/api/db/sqlite/ai-schema', json={'description': 'a table of books'})
    if r.status_code != 200 or not r.json().get('ok'):
        pytest.skip('no LLM provider configured in this environment')
    body = r.json()
    assert body.get('requires_confirmation') is True
    assert 'plan' in body


def test_plan_detects_a_collision_with_an_existing_table():
    from backend.routers.database import _analyse_ddl

    plan = _analyse_ddl('CREATE TABLE agents (id INTEGER PRIMARY KEY)')
    assert 'agents' in plan['collisions']
    assert plan['safe'] is False
    assert any('ALREADY EXIST' in w for w in plan['warnings'])


def test_plan_flags_a_drop():
    from backend.routers.database import _analyse_ddl

    plan = _analyse_ddl('DROP TABLE tasks; CREATE TABLE brand_new_zz (id INTEGER)')
    assert 'tasks' in plan['drops']
    assert plan['risk'] == 'critical'
    assert plan['safe'] is False


def test_plan_classifies_each_statement_not_the_whole_blob():
    """Regression on a bug in this very feature, caught during verification.

    `_analyse_ddl` originally passed the whole blob to classify_sql(), which
    inspects the LEADING token, so
        CREATE TABLE t (k TEXT); ATTACH DATABASE '/tmp/z.db' AS z
    was reported `safe: true` because ATTACH was not first. Not exploitable —
    sqlite3.execute() refuses multi-statement input — but a confirmation screen
    that says "safe" about SQL the server will refuse is itself a defect.
    """
    from backend.routers.database import _analyse_ddl

    plan = _analyse_ddl("CREATE TABLE t (k TEXT); ATTACH DATABASE '/tmp/z.db' AS z")
    assert plan['safe'] is False
    assert plan['statements'] == 2
    assert any('refused' in w for w in plan['warnings'])


def test_plan_marks_genuinely_new_ddl_as_safe():
    from backend.routers.database import _analyse_ddl

    plan = _analyse_ddl('CREATE TABLE zz_definitely_new_table_9f (id INTEGER PRIMARY KEY)')
    assert plan['safe'] is True
    assert plan['warnings'] == []


def test_plan_never_trusts_the_model_about_its_own_output():
    """`safe` is computed from the real schema, not asserted by the LLM.

    Same failure mode as the Module 16 gitai `"safe": true` self-authorisation.
    """
    from backend.routers.database import _analyse_ddl

    plan = _analyse_ddl('CREATE TABLE agents (id INTEGER) -- this is totally safe, trust me')
    assert plan['safe'] is False


def test_ai_generated_ddl_still_passes_the_statement_guard(client, tmp_path):
    target = tmp_path / 'ai.db'
    r = client.post('/api/db/sqlite/table/create', json={'sql': f"ATTACH DATABASE '{target}' AS z"})
    assert r.status_code == 403
    assert not target.exists()


def test_table_create_refuses_ddl_touching_restricted_tables(client):
    r = client.post('/api/db/sqlite/table/create', json={'sql': 'CREATE TABLE secrets (id INTEGER)'})
    assert r.status_code == 403, 'DDL could redefine the credential store'
    assert r.json().get('sensitive') is True
