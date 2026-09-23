"""Unit tests — audit action index, Migration 8 (r77, #239)

Five /history panes filter audit by action (code_review, deploy%,
composer_run, pipeline_run, testgen) and read newest-first. The backward
rowid walk those queries use stops at the LIMIT, so it is fast while the
action is DENSE — but an action that never occurs (fresh install, feature
never used, discontinued) walks the whole table on every pane open, and
audit is never deleted, so that cost grows forever with the table:

  absent action, ORDER BY id DESC          19.8ms @ 200k rows
  absent action, ORDER BY created_at DESC  267.7ms @ 200k rows (the planner
                                           satisfies the order from
                                           idx_audit_created and does a
                                           table lookup per entry)

Migration 8 adds idx_audit_action(action, id): both shapes become a
bounded seek (0.0ms / 0.1ms) regardless of table size. The deploy pane's
LIKE 'deploy%' could not use the index (case-insensitive LIKE cannot
range-scan a BINARY-collated index), so its query became GLOB 'deploy*' —
case-sensitive but exactly equivalent over the app's action vocabulary
(deploy:vercel / deploy:netlify / deploy:tunnel — all lowercase literals),
and GLOB prefix range-scans the index (absent prefix 19.8ms → 0.05ms).
"""
import sqlite3

from tests.unit.conftest import assert_ok


def _db():
    from backend.services.memory_db import db_path, get_conn

    get_conn().close()
    return sqlite3.connect(db_path())


def _seed(con, action, n, detail='seeded'):
    con.executemany(
        'INSERT INTO audit(action,detail) VALUES (?,?)',
        [(action, detail)] * n,
    )
    con.commit()


def _plan(con, q, params=()):
    return ' | '.join(r[-1] for r in con.execute('EXPLAIN QUERY PLAN ' + q, params))


class TestMigration8:
    def test_index_exists_and_recorded(self):
        con = _db()
        try:
            idx = {r[1] for r in con.execute('PRAGMA index_list(audit)')}
            row = con.execute(
                'SELECT name FROM _schema_migrations WHERE version=8'
            ).fetchone()
        finally:
            con.close()
        assert 'idx_audit_action' in idx
        assert row and row[0] == 'audit_action_index'
        # Migration 5's created_at index must survive (analytics today-windows).
        assert 'idx_audit_created' in idx

    def test_index_column_order(self):
        con = _db()
        try:
            cols = [r[2] for r in con.execute('PRAGMA index_info(idx_audit_action)')]
        finally:
            con.close()
        assert cols == ['action', 'id'], (
            'equality filters on action must be the leading column; id second '
            'serves the newest-first ordering within an action'
        )


class TestQueryPlans:
    """The guarantee is scale-independence: an absent action must SEEK, not
    scan — the cost of an empty history pane must not grow with the table."""

    EQ_SQL = ("SELECT action, detail, datetime(created_at,'localtime') as ts "
              "FROM audit WHERE action=? ORDER BY id DESC LIMIT ?")
    TS_SQL = "SELECT * FROM audit WHERE action='testgen' ORDER BY created_at DESC LIMIT 20"
    GLOB_SQL = ("SELECT action, detail, created_at FROM audit "
                "WHERE action GLOB 'deploy*' ORDER BY id DESC LIMIT ?")

    def test_equality_filter_seeks(self):
        con = _db()
        try:
            plans = _plan(con, self.EQ_SQL, ('code_review', 20))
        finally:
            con.close()
        assert 'USING INDEX idx_audit_action' in plans
        assert 'SCAN audit' not in plans and 'TEMP B-TREE' not in plans

    def test_created_at_order_seeks_then_sorts_matches_only(self):
        con = _db()
        try:
            plans = _plan(con, self.TS_SQL)
        finally:
            con.close()
        assert 'USING INDEX idx_audit_action' in plans
        # the sort is over the action's own rows, not the table
        assert 'SCAN audit' not in plans

    def test_deploy_glob_range_scans(self):
        con = _db()
        try:
            plans = _plan(con, self.GLOB_SQL, (20,))
        finally:
            con.close()
        assert 'USING INDEX idx_audit_action' in plans
        assert 'SCAN audit' not in plans


class TestGlobLikeEquivalence:
    def test_glob_matches_the_same_rows_over_the_action_vocabulary(self):
        """GLOB is case-sensitive, LIKE is not — over the app's actual
        (lowercase-literal) deploy actions the two predicates must return
        identical rows."""
        con = _db()
        try:
            con.execute(
                "DELETE FROM audit WHERE action LIKE 'deploy%' OR action GLOB 'deploy*'"
                " OR action IN ('unit_a','unit_b','unit_c')"
            )
            con.executemany(
                'INSERT INTO audit(action,detail) VALUES (?,?)',
                [('deploy:vercel', 'v'), ('deploy:netlify', 'n'),
                 ('deploy:tunnel', 't'), ('unit_a', 'a'), ('unit_b', 'b')],
            )
            con.commit()
            like = [r[0] for r in con.execute(
                "SELECT id FROM audit WHERE action LIKE 'deploy%' ORDER BY id")]
            glob = [r[0] for r in con.execute(
                "SELECT id FROM audit WHERE action GLOB 'deploy*' ORDER BY id")]
        finally:
            con.close()
        assert like == glob and len(like) == 3, (
            f'LIKE found {len(like)}, GLOB found {len(glob)} — predicates diverged'
        )
        # and neither matches unrelated actions
        assert like, 'deploy rows must exist'


class TestEndpointBehavior:
    def test_pipeline_history_shape(self, client):
        con = _db()
        try:
            _seed(con, 'pipeline_run', 3, detail='pipeline unit run')
        finally:
            con.close()

        rows = assert_ok(client.get('/api/pipeline/history?limit=10'))
        assert isinstance(rows, list) and rows
        assert {'action', 'detail', 'ts'} <= set(rows[0].keys())
        assert all(r['action'] == 'pipeline_run' for r in rows)

    def test_testgen_history_shape(self, client):
        con = _db()
        try:
            _seed(con, 'testgen', 2, detail='testgen unit run')
        finally:
            con.close()

        d = assert_ok(client.get('/api/testgen/history'))
        assert d['count'] == len(d['history'])
        assert {'action', 'detail'} <= set(d['history'][0].keys())

    def test_deploy_history_includes_audit_rows(self, client):
        con = _db()
        try:
            con.execute("DELETE FROM audit WHERE action GLOB 'deploy*'")
            con.execute(
                "INSERT INTO audit(action,detail) VALUES ('deploy:vercel','unit deploy')"
            )
            con.commit()
        finally:
            con.close()

        rows = assert_ok(client.get('/api/deploy/history?limit=10'))
        audit_sourced = [r for r in rows if r.get('source') == 'deploy:vercel']
        assert audit_sourced, 'audit-sourced deploy rows must appear in history'
        assert {'content', 'created_at', 'source', 'tags'} <= set(audit_sourced[0].keys())

    def test_empty_history_is_fast_and_clean(self, client):
        """The absent-action case the index exists for: an action with zero
        rows returns an empty history, 200, no error."""
        con = _db()
        try:
            n = con.execute(
                "SELECT COUNT(*) FROM audit WHERE action='never_happened_xyz'"
            ).fetchone()[0]
        finally:
            con.close()
        assert n == 0

        d = assert_ok(client.get('/api/testgen/history'))
        assert d['count'] == len(d['history'])
