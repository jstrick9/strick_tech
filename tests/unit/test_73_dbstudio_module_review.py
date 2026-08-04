"""Module 17 — Database Studio review contracts.

DB Studio runs SQL directly against the platform's own database — the one
holding secrets, auth_users, chat history and every module's state. Its
`allow_write` flag is therefore a security control, not a convenience.

Reproduced live before the fix, all with allow_write=FALSE:

    WITH t AS (SELECT 1) DELETE FROM dbstudio_victim
      -> {"ok": true, "type": "select", "count": 0}   and the row was GONE

    ATTACH DATABASE '/tmp/evil_attached.db' AS evil
      -> reported as a select; the file was created on disk

    PRAGMA writable_schema=1
      -> reported as a select; sqlite_master protection disabled

Write detection matched a KEYWORD PREFIX. Anything that puts another token
first — a CTE, a paren, a PRAGMA — slipped through as a "read", executed, and
was reported back as `{"type": "select"}`. A prefix check cannot express "does
this statement modify anything"; SQL is not prefix-structured.

An earlier fix had already patched the comment-prefix case
(`/* x */ DROP TABLE`). Patching one instance of a wrong approach leaves the
approach wrong — this replaces it.
"""
from __future__ import annotations

from pathlib import Path

import pytest

from backend.routers import database as db

REPO = Path(__file__).resolve().parents[2]


@pytest.fixture
def victim(client):
    """A real table with a real row, so destruction is observable."""
    def q(sql, write=False):
        return client.post('/api/db/sqlite/query', json={'sql': sql, 'allow_write': write})

    q('CREATE TABLE IF NOT EXISTS _dbs_probe(id INTEGER, note TEXT)', True)
    q("DELETE FROM _dbs_probe", True)
    q("INSERT INTO _dbs_probe VALUES (1, 'important data')", True)
    yield q
    q('DROP TABLE IF EXISTS _dbs_probe', True)


def row_count(q) -> int:
    body = q('SELECT COUNT(*) AS c FROM _dbs_probe').json()
    return body['rows'][0]['c'] if body.get('rows') else -1


# ── The classifier ─────────────────────────────────────────────────────────────


class TestWriteDetection:
    @pytest.mark.parametrize(
        'sql,label',
        [
            ('WITH t AS (SELECT 1) DELETE FROM x', 'CTE-prefixed DELETE'),
            ('(DELETE FROM x)', 'paren wrapped'),
            ('/* c */ DROP TABLE x', 'comment prefix'),
            ('-- note\nDROP TABLE x', 'line-comment prefix'),
            ('SELECT 1 /* */ ; DROP TABLE x', 'mid-statement comment'),
            ('BEGIN; DELETE FROM secrets; COMMIT', 'transaction wrapper'),
            ('   \n\t DROP TABLE x', 'leading whitespace'),
            ('VACUUM', 'VACUUM'),
            ('INSERT INTO t VALUES (1)', 'plain insert'),
            ('UPDATE t SET x=1', 'plain update'),
            ('ALTER TABLE t ADD COLUMN y', 'alter'),
            ('REPLACE INTO t VALUES (1)', 'replace'),
        ],
    )
    def test_writes_are_detected(self, sql, label):
        is_write, _ = db.classify_sql(sql)
        assert is_write is True, f'{label} was classified as a read: {sql!r}'

    @pytest.mark.parametrize(
        'sql',
        [
            'SELECT * FROM secrets',
            'SELECT COUNT(*) FROM t',
            'PRAGMA table_info(secrets)',
            'EXPLAIN QUERY PLAN SELECT 1',
            'SELECT name FROM sqlite_master',
        ],
    )
    def test_reads_are_not_blocked(self, sql):
        """Over-blocking would make the tool useless."""
        is_write, refusal = db.classify_sql(sql)
        assert is_write is False, f'{sql!r} misclassified as a write'
        assert refusal == ''

    def test_a_keyword_inside_a_string_literal_is_not_a_write(self):
        """Otherwise searching for the word "delete" is refused."""
        is_write, _ = db.classify_sql("SELECT * FROM t WHERE note LIKE '%delete me%'")
        assert is_write is False

    def test_a_keyword_inside_a_quoted_identifier_is_not_a_write(self):
        is_write, _ = db.classify_sql('SELECT "drop_count" FROM t')
        assert is_write is False

    def test_detection_errs_toward_calling_things_writes(self):
        """Conservative in the right direction.

        A false "write" costs the user an allow_write flag; a false "read"
        costs them their data. A subquery containing a write keyword as a whole
        word is treated as a write even though this particular statement only
        reads — deliberately.

        (My first version of this test used a TABLE named `deleted_rows` and
        expected it to trip the check. It does not, and should not: word-
        boundary matching sees `DELETED`, not `DELETE`. Asserting the wrong
        behaviour would have been worse than not asserting at all.)
        """
        is_write, _ = db.classify_sql(
            'SELECT * FROM t WHERE id IN (SELECT id FROM x) UNION SELECT 1 WHERE 1=0 -- DELETE'
        )
        # The DELETE here is inside a comment, so it is stripped: still a read.
        assert is_write is False

        # But a genuine write nested in a subquery IS caught.
        nested, _ = db.classify_sql('SELECT * FROM (DELETE FROM t RETURNING *)')
        assert nested is True

    def test_an_empty_statement_is_reported(self):
        is_write, refusal = db.classify_sql('/* only a comment */')
        assert refusal


class TestCommentStripping:
    def test_comments_are_removed_anywhere_not_just_the_prefix(self):
        out = db.strip_sql_comments('SELECT 1 /* mid */ FROM t -- trailing')
        assert '/*' not in out and '--' not in out
        assert 'SELECT' in out and 'FROM' in out

    def test_string_literals_survive_intact(self):
        """A literal containing -- must not be mangled into a comment."""
        out = db.strip_sql_comments("SELECT '-- not a comment' AS x")
        assert '-- not a comment' in out

    def test_escaped_quotes_do_not_break_parsing(self):
        out = db.strip_sql_comments("SELECT 'it''s fine' /* c */")
        assert "it''s fine" in out
        assert '/*' not in out

    def test_an_unterminated_block_comment_consumes_the_rest(self):
        """Failing open here would resurrect the original bypass."""
        out = db.strip_sql_comments('/* never closed DROP TABLE x')
        assert 'DROP' not in out.upper()


# ── Statements refused outright ────────────────────────────────────────────────


class TestForbiddenStatements:
    @pytest.mark.parametrize(
        'sql',
        [
            "ATTACH DATABASE '/tmp/evil.db' AS evil",
            'ATTACH DATABASE "/tmp/x.db" AS e',
            'DETACH DATABASE e',
        ],
    )
    def test_attach_is_refused(self, sql):
        """It creates or reads arbitrary files, and can copy rows out."""
        is_write, refusal = db.classify_sql(sql)
        assert refusal, f'{sql!r} must be refused outright'

    @pytest.mark.parametrize(
        'sql', ['PRAGMA writable_schema=1', 'PRAGMA journal_mode=DELETE']
    )
    def test_dangerous_pragmas_are_refused(self, sql):
        _is_write, refusal = db.classify_sql(sql)
        assert refusal

    def test_forbidden_beats_allow_write(self, client):
        """allow_write is consent to modify DATA, not to touch the filesystem.

        Clears the target first: a run against the pre-fix code leaves the file
        behind, and a test whose result depends on what ran before it is not
        evidence of anything.
        """
        target = Path('/tmp/_dbs_never.db')
        target.unlink(missing_ok=True)
        r = client.post('/api/db/sqlite/query', json={
            'sql': f"ATTACH DATABASE '{target}' AS e", 'allow_write': True,
        })
        assert r.status_code == 403
        assert r.json()['forbidden'] is True
        assert not target.exists()

    def test_read_pragmas_still_work(self, client):
        assert client.post(
            '/api/db/sqlite/query', json={'sql': 'PRAGMA table_info(memory)'}
        ).status_code == 200


# ── End to end: the data must survive ──────────────────────────────────────────


class TestDataIsActuallyProtected:
    def test_a_cte_prefixed_delete_cannot_destroy_rows(self, client, victim):
        """The exact live repro. Before: row gone, response said 'select'."""
        assert row_count(victim) == 1
        r = victim('WITH t AS (SELECT 1) DELETE FROM _dbs_probe', write=False)
        assert r.status_code == 403
        assert row_count(victim) == 1, 'the row was destroyed with allow_write=false'

    def test_a_paren_wrapped_delete_cannot_destroy_rows(self, client, victim):
        victim('(DELETE FROM _dbs_probe)', write=False)
        assert row_count(victim) == 1

    def test_a_comment_prefixed_drop_cannot_destroy_the_table(self, client, victim):
        victim('/* harmless */ DROP TABLE _dbs_probe', write=False)
        assert row_count(victim) == 1, 'the table was dropped'

    def test_attach_does_not_create_a_file(self, client, victim):
        target = Path('/tmp/_dbs_attach_probe.db')
        target.unlink(missing_ok=True)
        victim(f"ATTACH DATABASE '{target}' AS e", write=False)
        assert not target.exists()

    def test_legitimate_writes_still_work(self, client, victim):
        """A guard that blocks intended use is not a fix."""
        r = victim("INSERT INTO _dbs_probe VALUES (2, 'added')", write=True)
        assert r.status_code == 200
        assert row_count(victim) == 2

    def test_a_blocked_write_is_never_reported_as_a_select(self, client, victim):
        """The original bug reported {"type": "select"} while deleting rows."""
        body = victim('WITH t AS (SELECT 1) DELETE FROM _dbs_probe', write=False).json()
        assert body.get('type') != 'select'
        assert body['ok'] is False


# ── Status codes ───────────────────────────────────────────────────────────────


class TestStatusCodes:
    def test_empty_sql_is_400(self, client):
        assert client.post('/api/db/sqlite/query', json={}).status_code == 400

    def test_a_blocked_write_is_403(self, client):
        r = client.post('/api/db/sqlite/query', json={'sql': 'DROP TABLE nope'})
        assert r.status_code == 403
        assert r.json()['is_write'] is True

    def test_a_forbidden_statement_is_403(self, client):
        r = client.post('/api/db/sqlite/query', json={'sql': "ATTACH DATABASE '/tmp/x' AS e"})
        assert r.status_code == 403

    def test_a_syntax_error_is_400(self, client):
        assert client.post('/api/db/sqlite/query', json={'sql': 'SELECT FROM'}).status_code == 400

    @pytest.mark.parametrize('bad', ['bad-name!', '../etc', 'x" OR 1=1--'])
    def test_an_invalid_table_name_is_400(self, client, bad):
        assert client.get(f'/api/db/sqlite/table/{bad}').status_code in (400, 404)


# ── Regressions that must keep working ─────────────────────────────────────────


class TestExistingProtectionsHold:
    @pytest.mark.parametrize(
        'payload',
        ['x" UNION SELECT name,sql FROM sqlite_master--', 'x"; DROP TABLE y;--', '../../etc'],
    )
    def test_table_names_are_still_validated(self, client, payload):
        r = client.get(f'/api/db/sqlite/table/{payload}')
        assert r.status_code in (400, 404)
        if r.status_code == 400:
            assert 'Invalid table name' in r.text

    def test_the_search_parameter_is_still_parameterised(self):
        src = (REPO / 'backend' / 'routers' / 'database.py').read_text()
        assert 'LIKE ?' in src
        assert "params = [f'%{q}%']" in src

    def test_the_connection_still_matches_memory_db_settings(self):
        """Concurrent access to the same file needs the same locking config."""
        src = (REPO / 'backend' / 'routers' / 'database.py').read_text()
        assert 'busy_timeout=10000' in src
        assert 'journal_mode=WAL' in src

    def test_it_still_honours_the_test_database_sandbox(self):
        src = (REPO / 'backend' / 'routers' / 'database.py').read_text()
        assert 'from ..services.memory_db import db_path' in src
        assert 'sqlite3.connect(db_path()' in src
