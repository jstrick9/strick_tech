"""Unit tests — orphan adoption: bounded probes, no theft, specific-first (r85, #249)

_reconcile_orphan_sessions (runs on every GET /api/sessions — the chat
sidebar's most frequent call) had three residual defects after #240's
count-repair fix:

  1. ADOPTION THEFT: the name probe had no unclaimed filter, so a session
     whose message merely CONTAINED an orphan's title prefix could be
     adopted FROM — its messages re-linked into the orphan, leaving the
     victim empty with a stale count, itself becoming a new orphan on the
     next pass. Reproduced live: test_206's adoption scenario only passed
     because of a steal-back (a fresh empty session grabbed the row by
     timestamp, then the named orphan stole it back through the unfiltered
     name probe, leaving the fresh session with a stale count of 1).
  2. FULL-HISTORY SCANS PER PROBE: the name LIKE, timestamp, and any
     probes each scanned the ENTIRE chat_log per orphan session —
     78k-row LIKE walks during every healing call (measured: cold call
     with 5 orphans + 5 unclaimed at 78k messages: 231ms; bounded to the
     unclaimed sessions' rows: 83ms, 2.8x).
  3. GATE WALKED EVERY ROW: the unclaimed-existence gate probed chat_log
     PER ROW (78k PK probes steady-state, ~9ms of the ~24ms sidebar
     refresh); it now evaluates per DISTINCT session via the covering
     index (measured steady-state p50 24.3 -> 15.8ms).

Fixes: all probes are bounded to the unclaimed sessions' rows
(index seeks via idx_chat_log_session); matching is most-specific-first
(ALL name probes across orphans run before ANY timestamp probe, before
the any-fallback — a generic match can no longer claim a session that a
specific match wants); the gate walks distinct sessions.
"""
import contextlib
import sqlite3

from backend.routers import sessions as sessions_mod
from backend.routers.sessions import (
    _find_orphan_match,
    _probe_by_name,
    _reconcile_orphan_sessions,
    _unclaimed_session_ids,
)


def _db():
    from backend.services.memory_db import db_path, get_conn

    get_conn().close()
    return sqlite3.connect(db_path())


class TestAdoptionTheftPrevented:
    def test_claimed_session_cannot_be_adopted_from(self):
        con = _db()
        try:
            con.execute("DELETE FROM chat_log WHERE session_id IN ('victim','unclaimed_r85')")
            con.execute("DELETE FROM chat_sessions WHERE id IN ('orphan_r85','victim')")
            # a CLAIMED session whose message contains the orphan's title
            con.execute(
                "INSERT INTO chat_sessions(id,name,agent_id,message_count,description) "
                "VALUES ('victim','Innocent Live Session','default',2,'General')"
            )
            con.execute("INSERT INTO chat_log(session_id,agent,role,message) VALUES ('victim','default','user','Greek Mythology explained at length')")
            con.execute("INSERT INTO chat_log(session_id,agent,role,message) VALUES ('victim','default','assistant','Here is Greek Mythology...')")
            # an orphan whose title prefixes the victim's message
            con.execute(
                "INSERT INTO chat_sessions(id,name,agent_id,message_count,description) "
                "VALUES ('orphan_r85','Greek Mythology','default',0,'General')"
            )
            con.commit()

            _reconcile_orphan_sessions(con)

            victim_rows = con.execute(
                "SELECT COUNT(*) FROM chat_log WHERE session_id='victim'"
            ).fetchone()[0]  # noqa: E501
            assert victim_rows == 2, 'a claimed session must never lose its messages'
            orphan_rows = con.execute(
                "SELECT COUNT(*) FROM chat_log WHERE session_id='orphan_r85'"
            ).fetchone()[0]
            assert orphan_rows == 0, 'nothing unclaimed existed — the orphan must stay empty'
        finally:
            # cleanup: a leftover 0-message orphan in the shared DB would
            # name-match LATER tests' fixtures and steal their rows (the
            # old code masked this via steal-back theft; bounded adoption
            # cannot steal back).
            for t in (
                "DELETE FROM chat_log WHERE session_id IN ('victim','unclaimed_r85')",
                "DELETE FROM chat_sessions WHERE id IN ('orphan_r85','victim')",
            ):
                with contextlib.suppress(Exception):
                    con.execute(t)
                    con.commit()
            con.close()


class TestSpecificMatchWins:
    def test_named_orphan_beats_fresh_session_for_a_new_row(self):
        """The exact scenario the old code got right only by stealing back:
        a fresh empty session (timestamp-matchable) and a named orphan
        (name-matchable) compete for one unclaimed row. The named orphan
        wins; the fresh session stays empty — with an honest count."""
        con = _db()
        try:
            con.execute("DELETE FROM chat_log WHERE session_id='unclaimed_r85'")
            con.execute("DELETE FROM chat_sessions WHERE id IN ('fresh_r85','named_r85')")
            con.execute(
                "INSERT INTO chat_sessions(id,name,agent_id,message_count,description) "
                "VALUES ('fresh_r85','My Brand New Chat','default',0,'General')"
            )
            con.execute(
                "INSERT INTO chat_sessions(id,name,agent_id,message_count,description) "
                "VALUES ('named_r85','Orphan Title Here','default',0,'General')"
            )
            # created NOW: timestamp-matches the fresh session too
            con.execute(
                "INSERT INTO chat_log(session_id,agent,role,message) "
                "VALUES ('unclaimed_r85','default','user','Orphan Title Here full message')"
            )
            con.commit()

            _reconcile_orphan_sessions(con)

            named = con.execute(
                "SELECT message_count FROM chat_sessions WHERE id='named_r85'"
            ).fetchone()[0]
            fresh = con.execute(
                "SELECT message_count FROM chat_sessions WHERE id='fresh_r85'"
            ).fetchone()[0]
            assert named == 1, 'the specific (name) match must win the row'
            assert fresh == 0, 'the generic timestamp match must not claim it first'
        finally:
            for t in (
                "DELETE FROM chat_log WHERE session_id IN ('unclaimed_r85','named_r85','fresh_r85')",
                "DELETE FROM chat_sessions WHERE id IN ('fresh_r85','named_r85')",
            ):
                with contextlib.suppress(Exception):
                    con.execute(t)
                    con.commit()
            con.close()


class TestProbesBoundedToUnclaimed:
    def test_unclaimed_helper_lists_only_unowned_sessions(self):
        con = _db()
        try:
            con.execute("DELETE FROM chat_log WHERE session_id IN ('owned_r85','free_r85')")
            con.execute("DELETE FROM chat_sessions WHERE id='owned_r85'")
            con.execute(
                "INSERT INTO chat_sessions(id,name,agent_id,message_count,description) "
                "VALUES ('owned_r85','Owned','default',1,'General')"
            )
            con.execute("INSERT INTO chat_log(session_id,agent,role,message) VALUES ('owned_r85','default','user','claimed row')")
            con.execute("INSERT INTO chat_log(session_id,agent,role,message) VALUES ('free_r85','default','user','unclaimed row')")
            con.commit()
            assert _unclaimed_session_ids(con) == ['free_r85']
        finally:
            for t in (
                "DELETE FROM chat_log WHERE session_id IN ('owned_r85','free_r85')",
                "DELETE FROM chat_sessions WHERE id='owned_r85'",
            ):
                with contextlib.suppress(Exception):
                    con.execute(t)
                    con.commit()
            con.close()

    def test_name_probe_sql_is_restricted_to_unclaimed_sessions(self):
        con = _db()
        try:
            con.execute("DELETE FROM chat_log WHERE session_id='free_r85b'")
            con.execute(
                "INSERT INTO chat_log(session_id,agent,role,message) "
                "VALUES ('free_r85b','default','user','some unclaimed content')"
            )
            con.commit()

            captured = {}
            real_execute = sqlite3.Connection.execute

            class RecordingConn:
                def __init__(self, real):
                    self.real = real
                    self.last = None

                def execute(self, sql, params=()):
                    self.last = (sql, tuple(params))
                    return self.real.execute(sql, params)

            rec = RecordingConn(con)
            _probe_by_name(rec, 'some unclaimed', ['free_r85b'])
            sql, params = rec.last
            assert sql and 'session_id IN' in sql, f'name probe is unbounded again: {sql}'
            assert 'NOT IN (SELECT' not in sql
            plan = con.execute('EXPLAIN QUERY PLAN ' + sql, params).fetchall()
            plan_text = ' | '.join(r[-1] for r in plan)
            assert 'idx_chat_log_session' in plan_text, (
                f'probe must seek the covering index: {plan_text}'
            )
        finally:
            with contextlib.suppress(Exception):
                con.execute("DELETE FROM chat_log WHERE session_id='free_r85b'")
                con.commit()
            con.close()

    def test_gate_walks_distinct_sessions_not_every_row(self):
        from backend.services.memory_db import db_path

        con = sqlite3.connect(db_path())
        try:
            plan = con.execute(
                'EXPLAIN QUERY PLAN SELECT 1 FROM (SELECT DISTINCT session_id FROM chat_log) c '
                'WHERE NOT EXISTS (SELECT 1 FROM chat_sessions s WHERE s.id = c.session_id) LIMIT 1'
            ).fetchall()
            plan_text = ' | '.join(r[-1] for r in plan)
            assert 'COVERING INDEX' in plan_text, (
                f'the unclaimed gate must walk the covering index per DISTINCT '
                f'session, not probe per row: {plan_text}'
            )
        finally:
            con.close()


class TestMessagesFallbackStillAdopts:
    def test_session_messages_orphan_path_uses_the_same_bounded_probes(self):
        """GET /api/sessions/{id}/messages has its own adoption fallback;
        it must adopt through the same unclaimed-only helper."""
        con = _db()
        try:
            con.execute("DELETE FROM chat_log WHERE session_id='free_r85c'")
            con.execute("DELETE FROM chat_sessions WHERE id='orphan_r85c'")
            con.execute(
                "INSERT INTO chat_sessions(id,name,agent_id,message_count,description) "
                "VALUES ('orphan_r85c','Free Title','default',0,'General')"
            )
            con.execute(
                "INSERT INTO chat_log(session_id,agent,role,message) "
                "VALUES ('free_r85c','default','user','Free Title message body')"
            )
            con.commit()
            assert _find_orphan_match(con, 'Free Title', None, ['free_r85c']) == 'free_r85c'
            # and a claimed lookalike is never a candidate
            con.execute(
                "INSERT INTO chat_sessions(id,name,agent_id,message_count,description) "
                "VALUES ('claimed_r85c','Free Title','default',1,'General')"
            )
            con.execute(
                "INSERT INTO chat_log(session_id,agent,role,message) "
                "VALUES ('claimed_r85c','default','user','Free Title message body')"
            )
            con.commit()
            assert _find_orphan_match(con, 'Free Title', None, ['free_r85c']) == 'free_r85c'
        finally:
            for t in (
                "DELETE FROM chat_log WHERE session_id IN ('free_r85c','claimed_r85c')",
                "DELETE FROM chat_sessions WHERE id IN ('orphan_r85c','claimed_r85c')",
            ):
                with contextlib.suppress(Exception):
                    con.execute(t)
                    con.commit()
            con.close()
