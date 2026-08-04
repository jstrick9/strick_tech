"""Module 17 follow-up — Database Studio destructive-SQL audit trail.

THE BUG (verified live against a running server before the fix):

    POST /api/db/sqlite/query  {"sql": "DROP TABLE audit_victim",
                                "allow_write": true}
      -> {"ok": true, "rows_affected": -1, "type": "write"}

    GET /api/audit-log?limit=... -> not one row referencing the statement,
    the table, or Database Studio at all.

The single most destructive operation the platform exposes was also its least
observable. Every other privileged subsystem (MCP tool calls, connector execs,
goal changes, agent messages) already appended hash-chained receipts; the SQL
editor, the row insert/delete endpoints and the table-create endpoint appended
nothing. There was no record of who dropped the table, what the statement was,
or that anything had happened.

These tests assert on the CONTENTS OF THE LEDGER after each operation, not on
the presence of a call in the source, so they fail against the pre-fix code and
cannot be satisfied by a comment.
"""

from __future__ import annotations

import json
import re
import uuid
from pathlib import Path

import pytest

DB_ACTIONS = (
    'db_sql_write',
    'db_sql_attempt',
    'db_sql_refused',
    'db_schema_change',
    'db_schema_refused',
    'db_row_insert',
    'db_row_delete',
)


def _entries(client, action_type: str, limit: int = 200) -> list[dict]:
    r = client.get(f'/api/audit-log?action_type={action_type}&limit={limit}')
    assert r.status_code == 200, r.text
    return r.json().get('entries', [])


def _find(client, action_type: str, needle: str) -> dict | None:
    """Newest ledger entry of `action_type` whose detail or metadata mentions `needle`."""
    for e in _entries(client, action_type):
        blob = f"{e.get('action_detail', '')} {e.get('metadata', '')}"
        if needle in blob:
            return e
    return None


def _run(client, sql: str, allow_write: bool = True):
    return client.post('/api/db/sqlite/query', json={'sql': sql, 'allow_write': allow_write})


@pytest.fixture()
def victim(client):
    """A throwaway table with a unique name so entries can't be confused."""
    name = 'audit_t_' + uuid.uuid4().hex[:8]
    r = _run(client, f'CREATE TABLE "{name}" (id INTEGER PRIMARY KEY, x TEXT)')
    assert r.status_code == 200 and r.json().get('ok'), r.text
    yield name
    _run(client, f'DROP TABLE IF EXISTS "{name}"')


# ── The headline bug ───────────────────────────────────────────────────────────
def test_drop_table_is_recorded_in_the_audit_chain(client, victim):
    """DROP TABLE with allow_write=true must leave a ledger entry. It left none."""
    r = _run(client, f'DROP TABLE "{victim}"')
    assert r.status_code == 200 and r.json().get('ok') is True

    entry = _find(client, 'db_sql_write', victim)
    assert entry is not None, 'DROP TABLE executed but produced no audit_log_chain entry'
    assert entry['outcome'] == 'success'
    assert entry['risk_level'] == 'critical', 'a DROP is not a medium-risk event'
    meta = json.loads(entry['metadata'])
    assert victim in meta['sql'], 'the ledger must record the actual statement text'
    assert victim in meta.get('tables', []), 'the affected table must be identifiable'


def test_destructive_statement_records_a_pre_entry_before_running(client, victim):
    """The chain is append-only, so an in-flight row cannot be updated later.

    A statement that hangs or kills the process must still leave a trace of the
    attempt — that is exactly the case where the completion entry never lands.
    """
    _run(client, f'DROP TABLE "{victim}"')
    pre = _find(client, 'db_sql_attempt', victim)
    assert pre is not None, 'no pre-execution entry for a critical statement'
    assert pre['outcome'] == 'pending'
    assert pre['risk_level'] == 'critical'


def test_pre_entry_precedes_the_completion_entry(client, victim):
    _run(client, f'DROP TABLE "{victim}"')
    pre = _find(client, 'db_sql_attempt', victim)
    post = _find(client, 'db_sql_write', victim)
    assert pre and post
    assert pre['seq'] < post['seq'], 'the attempt must be recorded before the outcome'


# ── Risk grading ───────────────────────────────────────────────────────────────
@pytest.mark.parametrize(
    'template,expected',
    [
        ('DROP TABLE "{t}"', 'critical'),
        ('DELETE FROM "{t}"', 'critical'),          # unqualified: empties the table
        ('UPDATE "{t}" SET x=\'z\'', 'critical'),   # unqualified
        ('DELETE FROM "{t}" WHERE id=1', 'high'),
        ('INSERT INTO "{t}"(x) VALUES (\'a\')', 'medium'),
    ],
)
def test_risk_level_reflects_blast_radius(client, victim, template, expected):
    sql = template.format(t=victim)
    _run(client, sql)
    entry = _find(client, 'db_sql_write', victim)
    assert entry is not None, f'no ledger entry for {sql!r}'
    assert entry['risk_level'] == expected, f'{sql!r} graded {entry["risk_level"]}, expected {expected}'


def test_risk_grading_is_deterministic():
    """Iteration order over a frozenset is not stable; grading must not depend on it."""
    from backend.routers.database import _sql_risk

    sql = 'DROP TABLE a; ALTER TABLE b ADD COLUMN c TEXT'
    assert {_sql_risk(sql) for _ in range(50)} == {'critical'}


# ── Failures and refusals are recorded too ─────────────────────────────────────
def test_failed_write_is_recorded_as_a_failure(client):
    name = 'no_such_table_' + uuid.uuid4().hex[:8]
    r = _run(client, f'DROP TABLE "{name}"')
    assert r.status_code == 400
    entry = _find(client, 'db_sql_write', name)
    assert entry is not None, 'a failed destructive statement left no trace'
    assert entry['outcome'] == 'failure'


def test_refused_write_without_allow_write_is_recorded(client, victim):
    """A ledger that only holds successes cannot show that someone tried."""
    r = _run(client, f'DROP TABLE "{victim}"', allow_write=False)
    assert r.status_code == 403
    entry = _find(client, 'db_sql_refused', victim)
    assert entry is not None, 'a blocked write attempt left no trace'
    assert entry['outcome'] == 'blocked'


def test_refused_attach_is_recorded_as_high_risk(client, tmp_path):
    target = tmp_path / 'evil.db'
    r = _run(client, f"ATTACH DATABASE '{target}' AS e")
    assert r.status_code == 403
    entry = _find(client, 'db_sql_refused', 'ATTACH')
    assert entry is not None, 'a refused ATTACH is a security signal and must be logged'
    assert entry['risk_level'] == 'high'
    assert not target.exists()


# ── The other mutating endpoints ───────────────────────────────────────────────
def test_row_insert_endpoint_is_audited(client, victim):
    r = client.post(f'/api/db/sqlite/table/{victim}/insert', json={'row': {'x': 'hello'}})
    assert r.status_code == 200 and r.json().get('ok')
    entry = _find(client, 'db_row_insert', victim)
    assert entry is not None, 'the row-insert endpoint bypassed the ledger'
    assert entry['outcome'] == 'success'


def test_row_delete_endpoint_is_audited(client, victim):
    client.post(f'/api/db/sqlite/table/{victim}/insert', json={'row': {'x': 'hello'}})
    r = client.request(
        'DELETE',
        f'/api/db/sqlite/table/{victim}/row',
        json={'pk_column': 'id', 'pk_value': 1},
    )
    assert r.status_code == 200 and r.json().get('ok')
    entry = _find(client, 'db_row_delete', victim)
    assert entry is not None, 'the row-delete endpoint bypassed the ledger'
    assert entry['risk_level'] == 'high'


def test_table_create_endpoint_is_audited(client):
    name = 'audit_c_' + uuid.uuid4().hex[:8]
    r = client.post(
        '/api/db/sqlite/table/create',
        json={'name': name, 'columns': [{'name': 'id', 'type': 'INTEGER', 'pk': True}]},
    )
    assert r.status_code == 200 and r.json().get('ok'), r.text
    try:
        assert _find(client, 'db_schema_change', name) is not None, (
            'the table-create endpoint bypassed the ledger'
        )
    finally:
        _run(client, f'DROP TABLE IF EXISTS "{name}"')


def test_table_create_applies_the_same_statement_guard_as_the_sql_editor(client, tmp_path):
    """/table/create takes raw SQL, often LLM-authored by the AI Schema Designer.

    Before this fix it executed whatever it was handed with no classify_sql()
    call at all, so the ATTACH refusal that the SQL editor enforces was trivially
    sidestepped by posting to this endpoint instead.
    """
    target = tmp_path / 'via_create.db'
    r = client.post('/api/db/sqlite/table/create', json={'sql': f"ATTACH DATABASE '{target}' AS e"})
    assert r.status_code == 403, 'table/create executed a forbidden statement'
    assert not target.exists()
    assert _find(client, 'db_schema_refused', 'ATTACH') is not None


# ── Ledger integrity and read-path noise ───────────────────────────────────────
def test_reads_are_not_audited(client, victim):
    """Auditing every SELECT would bury the destructive events in noise."""
    before = len(_entries(client, 'db_sql_write'))
    r = _run(client, f'SELECT * FROM "{victim}"', allow_write=False)
    assert r.status_code == 200
    assert len(_entries(client, 'db_sql_write')) == before


def test_chain_still_verifies_after_database_studio_writes(client, victim):
    _run(client, f'INSERT INTO "{victim}"(x) VALUES (\'a\')')
    _run(client, f'DROP TABLE "{victim}"')
    r = client.get('/api/audit-log/verify')
    assert r.status_code == 200
    body = r.json()
    assert body.get('broken_at') is None, f'Database Studio entries broke the hash chain: {body}'


def test_audit_failure_never_breaks_the_query(client, victim, monkeypatch):
    """A ledger outage must be loud in the logs but must not swallow the result."""
    import backend.routers.audit_log as al

    def boom(*a, **k):
        raise RuntimeError('ledger down')

    monkeypatch.setattr(al, 'append_entry', boom)
    r = _run(client, f'INSERT INTO "{victim}"(x) VALUES (\'a\')')
    assert r.status_code == 200 and r.json().get('ok') is True


# ── Source-level guard against the pattern regressing ──────────────────────────
def _executable(path: Path) -> str:
    """Source with comments and docstrings stripped.

    Earlier modules in this review produced assertions that passed only because
    they matched the explanatory comment written alongside the fix.
    """
    import io
    import tokenize

    out = []
    prev_end = (1, 0)
    with open(path, 'rb') as fh:
        toks = list(tokenize.tokenize(fh.readline))
    for tok in toks:
        if tok.type == tokenize.COMMENT:
            continue
        if tok.type == tokenize.STRING and re.match(r'^[rbuf]*("""|\'\'\')', tok.string):
            continue
        if tok.start[0] > prev_end[0]:
            out.append('\n')
        out.append(tok.string + ' ')
        prev_end = tok.end
    return ''.join(out)


def test_every_mutating_db_endpoint_calls_audit_sql():
    src = _executable(Path('backend/routers/database.py'))
    for fn in ('sqlite_query', 'sqlite_insert', 'sqlite_delete_row', 'create_table'):
        assert f'def {fn}' in src, f'{fn} disappeared — update this guard'
    assert src.count('audit_sql (') + src.count('audit_sql(') >= 8, (
        'a mutating Database Studio path stopped recording to the audit ledger'
    )
