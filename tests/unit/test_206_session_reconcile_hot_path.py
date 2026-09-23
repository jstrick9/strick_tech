"""Unit tests — session reconciler hot path (r78, #240)

GET /api/sessions is the chat sidebar's most frequent call (22 frontend
call sites: every pane-open, every send). It ran a "universal
reconciliation" whose first statement was a TRIM-correlated UPDATE over
every session on every call:

  UPDATE chat_sessions SET message_count =
    (SELECT COUNT(*) FROM chat_log c WHERE TRIM(c.session_id) = TRIM(chat_sessions.id))

TRIM() defeats index seeking, so each session paid a full walk of the
chat_log session index — 200 sessions x 78k messages ≈ 2.3 SECONDS per
sidebar refresh (measured), growing linearly with sessions x messages.

Worse, the repair was a silent no-op: the function's only commit() lived
inside the orphan-adoption branch, so without an adoption match the
UPDATE's transaction was rolled back by con.close() — verified live: a
session with a stale count still had it after the call.

The fix (all behavior preserved, verified against test_41's adoption
scenario):
  1. Fast count repair, every call: sargable equality against the
     covering index, writes only wrong counts, COMMITS when it writes.
  2. Orphan adoption gated on BOTH sides existing: a 0-message session
     AND chat_log rows no session claims. A brand-new empty session no
     longer runs the TRIM scan / prefix-LIKE / timestamp anti-join
     machinery on every list call.
  3. TRIM-tolerant repair kept, but restricted to the 0-count anomaly
     rows instead of every session.

Measured: 2315.1ms → 15.9ms p50 (146x) at 200 sessions / 78k messages.
"""
import sqlite3

from tests.unit.conftest import assert_ok


def _db():
    from backend.services.memory_db import db_path, get_conn

    get_conn().close()
    return sqlite3.connect(db_path())


def _reconcile(con):
    from backend.routers.sessions import _reconcile_orphan_sessions

    _reconcile_orphan_sessions(con)


class TestCountRepairPersists:
    """The rollback bug: repairs must survive con.close() with no adoption."""

    def test_stale_count_is_repaired_and_committed(self, client):
        con = _db()
        try:
            con.execute("DELETE FROM chat_log WHERE session_id='persistence_s1'")
            con.execute("DELETE FROM chat_sessions WHERE id='persistence_s1'")
            con.execute(
                "INSERT INTO chat_sessions(id,name,agent_id,message_count,description) "
                "VALUES ('persistence_s1','T','default',1,'General')"
            )
            for i in range(3):
                con.execute(
                    "INSERT INTO chat_log(session_id,agent,role,message) "
                    "VALUES ('persistence_s1','default','user',?)", (f'm{i}',)
                )
            con.commit()
        finally:
            con.close()

        assert_ok(client.get('/api/sessions'))

        con = _db()
        try:
            n = con.execute(
                "SELECT message_count FROM chat_sessions WHERE id='persistence_s1'"
            ).fetchone()[0]
        finally:
            con.close()
        assert n == 3, (
            f'count repair must persist without an adoption match (got {n}) — '
            'the transaction is being rolled back on close again'
        )


class TestAdoptionGates:
    def test_fresh_empty_session_skips_adoption_machinery(self):
        """A brand-new 0-message session with no unclaimed chat_log rows
        anywhere must not run the adoption scans — and must not be
        'adopted into' (its count stays 0, its name unchanged)."""
        con = _db()
        try:
            con.execute("DELETE FROM chat_log WHERE session_id LIKE 'fresh%'")
            con.execute("DELETE FROM chat_sessions WHERE id LIKE 'fresh%'")
            con.execute(
                "INSERT INTO chat_sessions(id,name,agent_id,message_count,description) "
                "VALUES ('fresh_s1','My New Chat','default',0,'General')"
            )
            con.commit()

            _reconcile(con)

            n = con.execute(
                "SELECT message_count FROM chat_sessions WHERE id='fresh_s1'"
            ).fetchone()[0]
            name = con.execute(
                "SELECT name FROM chat_sessions WHERE id='fresh_s1'"
            ).fetchone()[0]
            assert n == 0, 'a legitimately empty session must not adopt messages'
            assert name == 'My New Chat'
        finally:
            con.close()

    def test_orphan_adoption_still_runs_when_both_sides_exist(self):
        con = _db()
        try:
            con.execute("DELETE FROM chat_log WHERE session_id='unclaimed_r78'")
            con.execute("DELETE FROM chat_sessions WHERE id='adopt_r78'")
            con.execute(
                "INSERT INTO chat_sessions(id,name,agent_id,message_count,description) "
                "VALUES ('adopt_r78','Orphan Title Here','default',0,'General')"
            )
            con.execute(
                "INSERT INTO chat_log(session_id,agent,role,message) "
                "VALUES ('unclaimed_r78','default','user','Orphan Title Here full message')"
            )
            con.commit()

            _reconcile(con)

            sid = con.execute(
                "SELECT DISTINCT session_id FROM chat_log "
                "WHERE session_id='unclaimed_r78'"
            ).fetchone()
            assert sid is None, 'unclaimed row must have been re-pointed'
            n = con.execute(
                "SELECT message_count FROM chat_sessions WHERE id='adopt_r78'"
            ).fetchone()[0]
            assert n == 1, f'adoption must still work (count={n})'
        finally:
            con.close()

    def test_trim_repair_for_whitespace_corrupted_ids(self):
        """The TRIM-tolerant branch: chat_log rows whose session_id carries
        stray whitespace still count toward their session."""
        con = _db()
        try:
            con.execute("DELETE FROM chat_log WHERE TRIM(session_id)='trim_r78'")
            con.execute("DELETE FROM chat_sessions WHERE id='trim_r78'")
            con.execute(
                "INSERT INTO chat_sessions(id,name,agent_id,message_count,description) "
                "VALUES ('trim_r78','T','default',0,'General')"
            )
            con.execute(
                "INSERT INTO chat_log(session_id,agent,role,message) "
                "VALUES (' trim_r78','default','user','padded id message')"
            )
            con.commit()

            _reconcile(con)

            n = con.execute(
                "SELECT message_count FROM chat_sessions WHERE id='trim_r78'"
            ).fetchone()[0]
            assert n == 1, (
                f'TRIM-tolerant repair must count whitespace-padded ids (got {n})'
            )
        finally:
            con.close()


class TestQueryPlans:
    def test_fast_count_repair_seeks_the_covering_index(self):
        """The 2.3s form showed 'SCAN c USING COVERING INDEX' — a full walk
        per session. The repaired form must SEEK (session_id=?)."""
        con = _db()
        try:
            plans = ' | '.join(r[-1] for r in con.execute(
                'EXPLAIN QUERY PLAN UPDATE chat_sessions '
                'SET message_count = (SELECT COUNT(*) FROM chat_log c WHERE c.session_id = chat_sessions.id) '
                'WHERE message_count <> (SELECT COUNT(*) FROM chat_log c WHERE c.session_id = chat_sessions.id)'))
        finally:
            con.close()
        assert 'USING COVERING INDEX idx_chat_log_session (session_id=?)' in plans
        assert 'SCAN c USING' not in plans, (  # exact: 'SCAN c' would also match 'SCAN chat_sessions'
            f'count repair regressed to a scan: {plans}'
        )
