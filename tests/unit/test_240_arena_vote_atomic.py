"""Unit tests — a vote and its ELO change commit atomically (r91, #254)

Class C crash/rollback audit (kill-mid-transaction semantics across
routers). An AST sweep flagged 41 multi-commit / multi-connection write
functions; hand-triage found most benign — get_conn() uses python's
default deferred isolation, so one connection + one trailing commit() is
already atomic (decompose_goal, bulk_delete, _update_elo itself...), and
sequential-phase writers (specs pipeline, a2a delegation) leave honest
resumable state.

The exception was arena voting: vote() committed the battle's winner on
connection 1, closed it, and THEN updated ELO on a second connection. A
crash in that window left the battle marked voted with the rating change
lost forever — the "Already voted" guard makes a half-applied vote
impossible to retry. The auto-judge path had the same split.

Proven end-to-end against a real server whose _update_elo os._exit(9)'d
at exactly that point (the kill lands between the winner mark and the ELO
write):

    OLD code after kill:  battle.winner='a'  committed,
                          modelA elo=1000.0 wins=0  — ELO lost forever
    NEW code after kill:  battle.winner=''   (rolled back),
                          modelA elo=1000.0          — vote fully retryable

Fix: _update_elo accepts an open connection and joins the caller's
transaction; both vote paths now do winner + ELO + commit on ONE
connection.
"""
import pytest

from backend.routers import arena
from backend.services.memory_db import get_conn


def _seed_battle(bid='kp1', a='kpA', b='kpB'):
    con = get_conn()
    try:
        con.execute('DELETE FROM arena_battles WHERE id=?', (bid,))
        con.execute('DELETE FROM arena_leaderboard WHERE model IN (?,?)', (a, b))
        con.execute('INSERT INTO arena_battles(id,prompt,model_a,model_b,category) VALUES (?,?,?,?,?)',
                    (bid, 'p', a, b, 'test'))
        con.execute("INSERT INTO arena_leaderboard(model,elo,wins,losses,ties,battles) VALUES (?,1000.0,0,0,0,0)", (a,))
        con.execute("INSERT INTO arena_leaderboard(model,elo,wins,losses,ties,battles) VALUES (?,1000.0,0,0,0,0)", (b,))
        con.commit()
    finally:
        con.close()


def _state(bid='kp1', a='kpA', b='kpB'):
    con = get_conn()
    try:
        w = con.execute('SELECT winner FROM arena_battles WHERE id=?', (bid,)).fetchone()[0]
        ra = con.execute('SELECT elo,wins,losses,ties,battles FROM arena_leaderboard WHERE model=?', (a,)).fetchone()
        rb = con.execute('SELECT elo,wins,losses,ties,battles FROM arena_leaderboard WHERE model=?', (b,)).fetchone()
    finally:
        con.close()
    return w, ra, rb


@pytest.fixture(autouse=True)
def _clean():
    yield
    con = get_conn()
    try:
        con.execute('DELETE FROM arena_battles WHERE id LIKE \'kp%\'')
        con.execute('DELETE FROM arena_leaderboard WHERE model LIKE \'kp%\'')
        con.commit()
    finally:
        con.close()


class TestVoteAtomicity:
    def test_failure_at_elo_rolls_back_the_winner_mark(self, client, monkeypatch):
        """A crash between winner-mark and ELO (the old two-transaction
        window) must leave NOTHING committed — the vote stays retryable."""
        import asyncio

        _seed_battle()

        def boom(*a, **kw):
            raise RuntimeError('simulated crash in the ELO window')

        monkeypatch.setattr(arena, '_update_elo', boom)
        import json as _json

        class _FakeReq:
            async def json(self):
                return {'winner': 'a'}

        with pytest.raises(RuntimeError):
            asyncio.run(arena.vote('kp1', _FakeReq()))

        w, ra, rb = _state()
        assert w == '', 'winner mark must roll back with the failed ELO update'
        assert ra['wins'] == 0 and rb['losses'] == 0

        # And the vote is retryable: same request now succeeds wholesale.
        monkeypatch.undo()
        r = client.post('/api/arena/battle/kp1/vote', json={'winner': 'a'})
        assert r.status_code == 200, r.text
        assert r.json()['ok'] is True
        w, ra, rb = _state()
        assert w == 'a'
        assert ra['wins'] == 1 and ra['elo'] > 1000
        assert rb['losses'] == 1 and rb['elo'] < 1000

    def test_vote_a_updates_battle_and_both_ratings_together(self, client):
        _seed_battle()
        r = client.post('/api/arena/battle/kp1/vote', json={'winner': 'a'})
        assert r.status_code == 200, r.text
        w, ra, rb = _state()
        assert w == 'a'
        assert ra['wins'] == 1 and rb['losses'] == 1
        assert ra['elo'] > 1000 > rb['elo']
        assert ra['battles'] == 1 and rb['battles'] == 1

    def test_vote_tie_counts_ties_for_both(self, client):
        _seed_battle()
        r = client.post('/api/arena/battle/kp1/vote', json={'winner': 'tie'})
        assert r.status_code == 200, r.text
        w, ra, rb = _state()
        assert w == 'tie'
        assert ra['ties'] == 1 and rb['ties'] == 1
        assert ra['elo'] == 1000.0 and rb['elo'] == 1000.0

    def test_already_voted_guard_still_blocks(self, client):
        _seed_battle()
        assert client.post('/api/arena/battle/kp1/vote', json={'winner': 'a'}).status_code == 200
        r = client.post('/api/arena/battle/kp1/vote', json={'winner': 'b'})
        # 400, not 200: the restatus middleware re-sends refused writes with
        # a real error status (a 200 "ok": false would sail past the frontend
        # failure reporting).
        assert r.status_code == 400
        assert 'Already voted' in r.json().get('error', '')

    def test_legacy_own_connection_mode_still_commits(self):
        """_update_elo() without a connection remains a self-contained
        transaction for any other caller (e.g. the unknown-model test)."""
        arena._update_elo('kpSoloW', 'kpSoloL')
        con = get_conn()
        try:
            w = con.execute('SELECT wins FROM arena_leaderboard WHERE model=?', ('kpSoloW',)).fetchone()
            l = con.execute('SELECT losses FROM arena_leaderboard WHERE model=?', ('kpSoloL',)).fetchone()
        finally:
            con.close()
        assert w[0] == 1 and l[0] == 1
