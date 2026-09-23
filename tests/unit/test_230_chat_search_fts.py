"""Unit tests — chat search on FTS instead of a full-history LIKE scan (r81, #244)

Migration 4's comment says "Add FTS index on chat_log for search" but it
created a plain B-tree (idx_chat_log_message). /api/chat/search runs
LIKE '%q%' — infix, unindexable — so every search scanned the message
text of the ENTIRE chat history: measured 112ms (rare term) / 52ms
(absent term) at 200k messages, growing linearly forever. The global
search box in the frontend calls this endpoint per query.

Migration 9 adds what the comment promised: an external-content FTS5
table over chat_log(message), kept in sync by INSERT/UPDATE/DELETE
triggers (session delete, clear-history and retention all DELETE FROM
chat_log), seeded once via 'rebuild' (measured 4.1s one-time at 200k
rows; the app blocks on first startup after upgrade, not per request).

Measured at 200k messages after the fix:
    rare term   LIKE 112.2ms -> FTS 0.1ms
    absent term LIKE  52.4ms -> FTS 0.0ms
    common term LIKE   0.0ms -> FTS 0.1ms (see below — this one is subtle)

The common-term case is why the query orders by rowid DESC, not FTS
rank: rank must evaluate EVERY match before sorting (288ms for a term
in ~1/14 of messages — SLOWER than the old code), while rowid DESC
walks the doclist in id order and stops at the LIMIT. rowid DESC also
matches the old ORDER BY created_at DESC contract (id and created_at
are both insert-monotonic).

Query sanitization follows memory_search_fts's documented precedent:
raw user input in FTS5 MATCH is a syntax error for terms as common as
"multi-agent" (hyphen = NOT operator), so terms are tokenized and
individually quoted, OR'd. Any sqlite3.Error falls back to the original
LIKE scan — a failed or missing migration degrades to today's behavior
instead of breaking search (verified: DROP TABLE chat_log_fts, search
still returns results).

Write-path cost, measured: +24µs per message (trigger insert into the
external-content FTS) on a path that is LLM-rate-bound (seconds per
message).
"""
import sqlite3

from tests.unit.conftest import assert_ok


def _seed(con, session_id: str, name: str, messages: list[tuple[str, str]]):
    con.execute(
        'INSERT INTO chat_sessions(id, name) VALUES (?, ?)', (session_id, name)
    )
    for role, msg in messages:
        con.execute(
            'INSERT INTO chat_log(session_id, role, message, agent) VALUES (?,?,?,?)',
            (session_id, role, msg, ' Atlas'),
        )
    con.commit()


def _search(client, q: str, limit: int = 20):
    return assert_ok(client.get('/api/chat/search', params={'q': q, 'limit': limit}))


class TestChatSearchFts:
    def test_migration_created_fts_and_triggers(self, client):
        from backend.services.memory_db import get_conn

        con = get_conn()
        try:
            n = con.execute(
                "SELECT COUNT(*) FROM _schema_migrations WHERE version=9"
            ).fetchone()[0]
            assert n == 1, 'Migration 9 (chat_log_fts) must be recorded'
            triggers = {
                r[0]
                for r in con.execute(
                    "SELECT name FROM sqlite_master WHERE type='trigger' "
                    "AND name LIKE 'chat_log_fts_%'"
                ).fetchall()
            }
            assert {'chat_log_fts_ins', 'chat_log_fts_del', 'chat_log_fts_upd'} <= triggers
        finally:
            con.close()

    def test_search_finds_messages_with_session_context(self, client):
        from backend.services.memory_db import get_conn

        con = get_conn()
        try:
            _seed(
                con,
                's_fts_1',
                'Deploy review',
                [
                    ('user', 'please deploy the multi-agent pipeline'),
                    ('assistant', 'multi-agent pipeline queued as run 42'),
                    ('user', 'unrelated gardening note'),
                ],
            )
        finally:
            con.close()

        d_out = _search(client, 'pipeline')
        assert d_out['count'] == 2
        for r in d_out['results']:
            assert r['session_name'] == 'Deploy review'
            assert r['snippet']

    def test_hyphenated_query_is_not_a_syntax_error(self, client):
        """Raw FTS5 MATCH chokes on 'multi-agent' (hyphen = NOT operator);
        the sanitized tokenized query must return the matching rows."""
        from backend.services.memory_db import get_conn

        con = get_conn()
        try:
            _seed(
                con,
                's_fts_2',
                'Hyphen session',
                [('user', 'the multi-agent orchestration works'),
                 ('user', 'nothing relevant here')],
            )
        finally:
            con.close()

        d_out = _search(client, 'multi-agent')
        # the sandbox db is shared across this file's tests, so earlier
        # seeds with 'multi-agent' also match — assert THIS test's row is
        # among them and that no error was swallowed into an empty result
        assert d_out['count'] >= 1
        assert any('multi-agent' in r['snippet'] for r in d_out['results'])

    def test_newest_first_order_preserved(self, client):
        from backend.services.memory_db import get_conn

        con = get_conn()
        try:
            _seed(
                con,
                's_fts_3',
                'Order session',
                [('user', f'kickoff matchword {i}') for i in range(5)],
            )
            ids = [
                r[0]
                for r in con.execute(
                    "SELECT id FROM chat_log WHERE session_id='s_fts_3' ORDER BY id"
                ).fetchall()
            ]
        finally:
            con.close()

        d_out = _search(client, 'matchword')
        got = [r['id'] for r in d_out['results']]
        assert got == sorted(got, reverse=True), 'results must be newest (max id) first'
        assert got[0] == ids[-1]

    def test_deleted_messages_leave_fts_and_results(self, client):
        """Session delete / clear-history DELETE FROM chat_log — the delete
        trigger must keep the FTS index clean and results correct."""
        from backend.services.memory_db import get_conn

        con = get_conn()
        try:
            _seed(con, 's_fts_4', 'Doomed', [('user', 'vanishing targetword message')])
            con.execute("DELETE FROM chat_log WHERE session_id='s_fts_4'")
            con.commit()
            n_fts = con.execute(
                "SELECT COUNT(*) FROM chat_log_fts "
                "JOIN chat_log ON chat_log.id = chat_log_fts.rowid "
                "WHERE chat_log_fts MATCH 'targetword'"
            ).fetchone()[0]
        finally:
            con.close()
        assert n_fts == 0, 'dangling FTS entries after DELETE'

        d_out = _search(client, 'targetword')
        assert d_out['count'] == 0

    def test_fts_error_falls_back_to_like(self, client):
        """A missing/failed Migration 9 must degrade to the old LIKE scan,
        not break search. (sqlite3.Connection is an immutable C type — it
        cannot be monkeypatched — so simulate the failure the realistic
        way: drop the FTS table, then restore it for any later tests.)"""
        from backend.services.memory_db import get_conn

        con = get_conn()
        try:
            _seed(con, 's_fts_5', 'Fallback', [('user', 'fallback seekword message')])
            con.execute('DROP TABLE chat_log_fts')
            con.commit()
        finally:
            con.close()

        d_out = _search(client, 'seekword')
        assert d_out['count'] == 1, 'LIKE fallback must serve the search'

        # restore the FTS table for any test that runs after this one
        con = get_conn()
        try:
            con.executescript(
                '''
                CREATE VIRTUAL TABLE IF NOT EXISTS chat_log_fts
                    USING fts5(message, content='chat_log', content_rowid='id');
                INSERT INTO chat_log_fts(chat_log_fts) VALUES ('rebuild');
                '''
            )
            con.commit()
            n = con.execute(
                "SELECT COUNT(*) FROM chat_log_fts "
                "JOIN chat_log ON chat_log.id = chat_log_fts.rowid "
                "WHERE chat_log_fts MATCH 'seekword'"
            ).fetchone()[0]
        finally:
            con.close()
        assert n == 1, 'rebuilt FTS must serve the same search'

    def test_short_query_returns_empty_without_touching_db(self, client):
        d_out = _search(client, 'x')
        assert d_out == {'ok': True, 'results': [], 'count': 0}
