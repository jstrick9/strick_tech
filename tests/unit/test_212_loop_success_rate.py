"""Gap #017: loop health success_rate was miscalculated.

run_count counts only SUCCESSFUL iterations and error_count is a separate
counter, but the old formula was
    (run_count - error_count) / run_count * 100  if run_count else 100
so the denominator excluded failures entirely: 5 successes + 5 failures
reported 0%, any error_count > run_count reported a NEGATIVE rate, and an
all-failing loop (run_count=0) fell into `if total else 100` and reported 100%
forever. The rate was also only recomputed in the success branch. It is now
successes / total_attempts, recomputed in both branches.
"""
import sys
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[2]))

from backend.services.agent_engine import LoopConfig, LoopEngine


class TestLoopSuccessRate:
    @pytest.mark.asyncio
    async def test_mixed_5_and_5_is_50_percent(self):
        engine = LoopEngine()
        state = {'mode': 'ok'}

        async def fn():
            if state['mode'] == 'ok':
                state['mode'] = 'bad'
                return {'ok': True}
            state['mode'] = 'ok'
            raise ValueError('boom')

        engine.create_loop('mix', 'Mix', fn,
                           LoopConfig(max_consecutive_errors=100, backoff_on_error=False))
        for _ in range(10):
            await engine.run_loop_iteration('mix')
        st = engine.get_loop_status('mix')
        assert st['run_count'] == 5 and st['error_count'] == 5
        assert engine.loop_health['mix']['success_rate'] == 50.0

    @pytest.mark.asyncio
    async def test_all_fail_is_zero_not_one_hundred(self):
        engine = LoopEngine()

        async def bad():
            raise ValueError('x')

        engine.create_loop('all', 'All', bad,
                           LoopConfig(max_consecutive_errors=100, backoff_on_error=False))
        for _ in range(3):
            await engine.run_loop_iteration('all')
        st = engine.get_loop_status('all')
        assert st['run_count'] == 0 and st['error_count'] == 3
        assert engine.loop_health['all']['success_rate'] == 0.0

    @pytest.mark.asyncio
    async def test_all_succeed_is_100(self):
        engine = LoopEngine()

        async def good():
            return {'ok': True}

        engine.create_loop('ok', 'Ok', good)
        for _ in range(4):
            await engine.run_loop_iteration('ok')
        assert engine.loop_health['ok']['success_rate'] == 100.0

    @pytest.mark.asyncio
    async def test_more_errors_than_successes_is_not_negative(self):
        engine = LoopEngine()
        state = {'mode': 'ok'}

        async def fn():
            if state['mode'] == 'ok':
                state['mode'] = 'bad'
                return {'ok': True}
            # 1 success then many failures
            state['mode'] = 'bad'
            raise ValueError('boom')

        engine.create_loop('mix', 'Mix', fn,
                           LoopConfig(max_consecutive_errors=100, backoff_on_error=False))
        # 1 success, then 5 failures
        await engine.run_loop_iteration('mix')
        for _ in range(5):
            await engine.run_loop_iteration('mix')
        st = engine.get_loop_status('mix')
        assert st['run_count'] == 1 and st['error_count'] >= 1
        rate = engine.loop_health['mix']['success_rate']
        assert 0.0 <= rate <= 100.0 and rate < 50.0
