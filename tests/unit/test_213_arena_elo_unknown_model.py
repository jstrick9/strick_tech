"""Gap #018: arena ELO update was silently dropped for unlisted models.

_update_elo read the current elo (defaulting to 1000 when absent) but the
leaderboard row was only ever created by _ensure_schema's seed over
AVAILABLE_MODELS. A battle using a custom/unlisted model name therefore
computed a rating against a 1000 default and then the UPDATE matched 0 rows —
the rating change was lost and the model never appeared in the leaderboard.
"""
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[2]))

from backend.routers import arena
from backend.services.memory_db import get_conn


class TestArenaEloUnknownModel:
    def test_custom_model_row_is_created_and_rated(self):
        # Custom (unlisted) model names that are NOT in AVAILABLE_MODELS.
        arena._update_elo('custom-winner', 'custom-loser')
        con = get_conn()
        try:
            w = con.execute(
                'SELECT elo, wins, losses, battles FROM arena_leaderboard WHERE model=?',
                ('custom-winner',),
            ).fetchone()
            l = con.execute(
                'SELECT elo, wins, losses, battles FROM arena_leaderboard WHERE model=?',
                ('custom-loser',),
            ).fetchone()
        finally:
            con.close()
        assert w is not None, 'winner row was not created'
        assert l is not None, 'loser row was not created'
        # Winner gained above 1000, loser below; exactly one battle each.
        assert w['elo'] > 1000 and l['elo'] < 1000
        assert w['wins'] == 1 and w['battles'] == 1
        assert l['losses'] == 1 and l['battles'] == 1

    def test_seeded_model_still_works(self):
        # Existing behavior for a seeded model must not regress.
        arena._update_elo('claude-sonnet', 'gpt-4o')
        con = get_conn()
        try:
            w = con.execute(
                'SELECT elo, wins, battles FROM arena_leaderboard WHERE model=?',
                ('claude-sonnet',),
            ).fetchone()
        finally:
            con.close()
        assert w is not None and w['wins'] >= 1
