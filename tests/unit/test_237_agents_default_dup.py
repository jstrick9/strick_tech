"""Unit tests — DEFAULT_AGENTS duplicate id + the eternal re-seed it caused (r88, #251)

DEFAULT_AGENTS contained 'orchestrator' TWICE (the classic Orchestrator and
a later "Swarm Orchestrator" entry). INSERT OR IGNORE always kept the first,
so the Swarm Orchestrator never materialized in any database — but its
presence made len(DEFAULT_AGENTS) = 13 while at most 12 distinct default
rows can exist. agents_list()'s completeness check
(`len(agents) < len(DEFAULT_AGENTS)`) therefore NEVER converged on a fresh
install: every GET /api/agents re-ran agents_seed_defaults — a no-op
INSERT OR IGNORE x 13 plus COMMIT, i.e. a write transaction with write locks
taken on a hot READ endpoint — and burned three connections instead of one,
forever (measured: steady-state 3 conns / 9.3ms -> 1 conn / 4.9ms; the live
preview only escaped because it happens to hold 13 agent rows).

Two fixes:
  1. The duplicate entry is removed. Zero behavior change by construction:
     INSERT OR IGNORE meant it could never be inserted anywhere.
  2. agents_list()'s `if not agents: return agents_list()` recursion is now
     a bounded single retry — a seed that cannot write (read-only volume,
     locked DB) used to recurse until RecursionError.

Measured context that frames this file (r88 WAL/write-path round): each
fresh connection to this app's 314-object schema costs ~1.2ms of schema
parse before its first real statement (pragmas included; a bare `SELECT 1`
is free), so per-request connection count is the currency that matters —
this is the endpoint that spent three of them on nothing.
"""
import sqlite3
from unittest.mock import patch

import backend.services.memory_db as mdb
from backend.services.memory_db import DEFAULT_AGENTS, agents_list, get_conn


def _db():
    get_conn().close()
    from backend.services.memory_db import db_path

    return sqlite3.connect(db_path())


class TestDefaultsData:
    def test_default_agent_ids_are_distinct(self):
        ids = [a['id'] for a in DEFAULT_AGENTS]
        assert len(ids) == len(set(ids)), (
            f'duplicate default agent ids: '
            f'{sorted(i for i in ids if ids.count(i) > 1)} — agents_list() '
            'completeness can never converge'
        )
        assert len(DEFAULT_AGENTS) >= 10, 'the known default roster (12) shrunk unexpectedly'

    def test_seeding_creates_exactly_the_defaults(self):
        con = _db()
        try:
            con.execute('DELETE FROM agents')
            con.commit()
        finally:
            con.close()
        agents = agents_list()
        ids = {a['id'] for a in agents}
        assert ids == {a['id'] for a in DEFAULT_AGENTS}
        assert len(agents) == len(DEFAULT_AGENTS)


class TestNoEternalReseed:
    def test_complete_roster_uses_one_connection_and_no_seed(self):
        """With every default present, agents_list must be a single
        connection and must not run the seed (the old code re-seeded —
        a write transaction — on every call because the duplicate id made
        the count check unsatisfiable)."""
        agents_list()  # ensure seeded
        conns = {'n': 0}
        real_get_conn = mdb.get_conn

        def counting():
            conns['n'] += 1
            return real_get_conn()

        seeded = {'n': 0}

        def spy_seed():
            seeded['n'] += 1

        with patch.object(mdb, 'get_conn', side_effect=counting):
            with patch.object(mdb, 'agents_seed_defaults', side_effect=spy_seed):
                agents = agents_list()
        assert len(agents) >= len(DEFAULT_AGENTS)
        assert conns['n'] == 1, (
            f'{conns["n"]} connections for a complete roster — the eternal '
            're-seed path is back'
        )
        assert seeded['n'] == 0, 'agents_seed_defaults ran on a complete roster'

    def test_deleted_default_is_still_resurrected(self):
        """Existing semantics preserved: a missing default agent is re-seeded
        by the next list call (aggressive default presence — pre-existing
        behavior, deliberately unchanged by this fix)."""
        con = _db()
        try:
            con.execute("DELETE FROM agents WHERE id='creative'")
            con.commit()
        finally:
            con.close()
        agents = agents_list()
        assert any(a['id'] == 'creative' for a in agents)


class TestBoundedRetry:
    def test_unwritable_seed_returns_empty_without_recursion(self):
        """A seed that cannot write (locked/read-only DB) must return the
        (empty) result after ONE bounded retry — the old code recursed
        until RecursionError."""
        con = _db()
        try:
            con.execute('DELETE FROM agents')
            con.commit()
        finally:
            con.close()

        calls = {'seed': 0}

        def failing_seed():
            calls['seed'] += 1  # does not write anything

        with patch.object(mdb, 'agents_seed_defaults', side_effect=failing_seed):
            result = agents_list()  # must not raise RecursionError
        assert result == []
        assert calls['seed'] == 1, 'seed must run exactly once (single bounded retry)'
        # restore: this test leaves the agents table EMPTY; a later test file
        # that assumes the default roster exists would otherwise fail (the
        # r85 lesson — tests own their DB state).
        mdb.agents_seed_defaults()
        assert len(agents_list()) == len(DEFAULT_AGENTS)
