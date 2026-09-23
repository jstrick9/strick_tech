"""Unit tests — retention windows for file_versions + webhook_events (r75, #237)

Both tables had NO deletes at all: every changed save stored a full
file-content copy in file_versions and every webhook event a ≤5KB payload
in webhook_events, forever, while their read paths only ever show the
newest 150 per file (preview_history) / 100 per webhook (webhook_events).
Nothing beyond the window is reachable from the UI, so keeping it is pure
storage growth. The routers now prune to the read window on every insert
(the same house pattern terminal_history's 500-per-session cap uses), and
Migration 7 indexes the windowed reads and prune subqueries.

Measured at 50k rows: preview_history's read 23.3ms SCAN → 1.4ms index
search; first prune after upgrade is a one-time catch-up (8-15ms at 50k
rows), then each write prunes the 1-2 rows it just aged out of the window.
"""
import json
import sqlite3

from tests.unit.conftest import assert_ok, post_json


def _db():
    from backend.services.memory_db import db_path, get_conn

    get_conn().close()
    return sqlite3.connect(db_path())


def _seed_versions(con, path, n, workspace_id='', content='seed'):
    con.executemany(
        'INSERT INTO file_versions(path,content,author,message,workspace_id) VALUES (?,?,?,?,?)',
        [(path, content, 'seeder', 'seed', workspace_id)] * n,
    )
    con.commit()


class TestMigration7:
    def test_indexes_exist_and_recorded(self):
        con = _db()
        try:
            fv = {r[1] for r in con.execute('PRAGMA index_list(file_versions)')}
            we = {r[1] for r in con.execute('PRAGMA index_list(webhook_events)')}
            row = con.execute(
                'SELECT name FROM _schema_migrations WHERE version=7'
            ).fetchone()
        finally:
            con.close()
        assert 'idx_file_versions_path' in fv
        assert 'idx_webhook_events_hook' in we
        assert row and row[0] == 'retention_window_indexes'

    def test_history_read_uses_path_index(self):
        con = _db()
        try:
            plans = ' | '.join(r[-1] for r in con.execute(
                'EXPLAIN QUERY PLAN SELECT id, author, message, '
                "datetime(created_at,'localtime') as ts, length(content) as bytes "
                "FROM file_versions WHERE path=? AND (workspace_id=? OR workspace_id='') "
                'ORDER BY id DESC LIMIT 150', ('x', "''")))
        finally:
            con.close()
        assert 'USING INDEX idx_file_versions_path' in plans
        assert 'SCAN file_versions' not in plans

    def test_events_read_uses_webhook_index(self):
        con = _db()
        try:
            plans = ' | '.join(r[-1] for r in con.execute(
                'EXPLAIN QUERY PLAN SELECT * FROM webhook_events '
                'WHERE webhook_id=? ORDER BY id DESC LIMIT ?', ('x', 100)))
        finally:
            con.close()
        assert 'USING INDEX idx_webhook_events_hook' in plans
        assert 'SCAN webhook_events' not in plans


class TestFileVersionWindow:
    PATH = 'window_test.html'

    def test_save_prunes_to_visible_window(self, client):
        con = _db()
        try:
            con.execute("DELETE FROM file_versions WHERE path=?", (self.PATH,))
            _seed_versions(con, self.PATH, 160)
            seeded_ids = [r[0] for r in con.execute(
                'SELECT id FROM file_versions WHERE path=?', (self.PATH,))]
        finally:
            con.close()

        d = assert_ok(post_json(client, '/api/preview/save',
                                {'path': self.PATH, 'content': 'fresh content'}))
        assert d['ok'] is True

        con = _db()
        try:
            from backend.routers.builder import _current_workspace_id
            ws = _current_workspace_id()
            rows = con.execute(
                "SELECT id FROM file_versions WHERE path=? AND (workspace_id=? OR workspace_id='')",
                (self.PATH, ws),
            ).fetchall()
            ids = {r[0] for r in rows}
        finally:
            con.close()
        assert len(ids) == 150, f'window must hold exactly 150, got {len(ids)}'
        assert max(seeded_ids) in ids, 'newest seeded rows must survive'
        assert min(seeded_ids) not in ids, 'oldest rows must be pruned'

    def test_save_reports_windowed_count(self, client):
        con = _db()
        try:
            con.execute("DELETE FROM file_versions WHERE path=?", (self.PATH,))
            _seed_versions(con, self.PATH, 149)
        finally:
            con.close()

        d = assert_ok(post_json(client, '/api/preview/save',
                                {'path': self.PATH, 'content': 'exact window'}))
        # 149 seeded + 1 new = 150: exactly at the window, nothing pruned
        assert d['versions'] == 150

    def test_other_workspaces_never_pruned_by_this_workspace_save(self, client):
        con = _db()
        try:
            con.execute("DELETE FROM file_versions WHERE path=?", (self.PATH,))
            _seed_versions(con, self.PATH, 200, workspace_id='other-ws')
        finally:
            con.close()

        assert_ok(post_json(client, '/api/preview/save',
                            {'path': self.PATH, 'content': 'current ws save'}))

        con = _db()
        try:
            n = con.execute(
                "SELECT COUNT(*) FROM file_versions WHERE path=? AND workspace_id='other-ws'",
                (self.PATH,),
            ).fetchone()[0]
        finally:
            con.close()
        assert n == 200, 'another workspace’s versions must be invisible to this prune'


class TestWebhookEventWindow:
    def test_filtered_trigger_prunes_to_window(self, client):
        # webhook whose filters expect source 'github'; trigger sends source 'webhook'
        wh = assert_ok(post_json(client, '/api/webhooks', {
            'name': 'window hook', 'secret': 'supersecret123',
            'filters': {'source': 'github'},
        }))
        wid, secret = wh['id'], wh['secret']

        con = _db()
        try:
            con.execute('DELETE FROM webhook_events WHERE webhook_id=?', (wid,))
            con.executemany(
                'INSERT INTO webhook_events(webhook_id,source,payload,run_id,status) VALUES (?,?,?,?,?)',
                [(wid, 'github', '{"i":1}', '', 'pass')] * 110,
            )
            con.commit()
        finally:
            con.close()

        r = client.post(f'/api/webhooks/{wid}/trigger',
                        json={'hello': 'world'},
                        headers={'X-Webhook-Secret': secret})
        assert r.status_code == 200
        assert r.json().get('filtered') is True

        con = _db()
        try:
            ids = [r[0] for r in con.execute(
                'SELECT id FROM webhook_events WHERE webhook_id=? ORDER BY id DESC', (wid,))]
        finally:
            con.close()
        assert len(ids) == 100, f'window must hold exactly 100, got {len(ids)}'
        # the just-inserted filtered event is the newest and survived
        assert ids[0] == max(ids)
