"""Unit tests — the WS status tick computes once per window, not per client (r84, #248)

Every connected WebSocket client ran its own 8-second status task, and
each task independently ran agents_list() + memory_stats() — the SAME
work, N times per tick, with every client receiving the same numbers.
memory_stats alone runs four aggregations over the memory table
(COUNT(*), COUNT(DISTINCT source), GROUP BY source, a vector count),
so at N dashboard clients the platform ran N x ~5 queries every 8
seconds. Measured with 5 concurrent clients over two ticks:
15 memory_stats calls before, 7 after (5 connect-time inits + one per
tick) — the tick herd collapses to a single computation.

The snapshot is TTL-cached (TTL = the tick interval) and single-flown
across event loops: client tick tasks can live on different loops (one
per request in tests), so an asyncio.Lock would be loop-bound — a
plain threading mutex is used instead, and the compute body never
yields, so the lock is never held across an await.

Each client still receives its own agent_status + memory_stats frames;
data is at most ~2 ticks old instead of 1 (status counters, not a
ledger). Connect-time _send_init still computes fresh — the shared
path is only the recurring tick.
"""
import contextlib
import time

import backend.routers.websocket as wsr
import backend.services.memory_db as mdb


async def _fake_statuses():
    return [{'id': 'a1', 'name': 'A', 'status': 'idle', 'avatar': ''}]


async def _fake_stats():
    return {'sqlite_memories': 1, 'total': 1, 'count': 1, 'vectors_sqlite': 0,
            'source_count': 1, 'status': 'active', 'engine': 'test'}


def _install_fakes(monkeypatch, stats_calls):
    async def counting_statuses():
        stats_calls['agents'] = stats_calls.get('agents', 0) + 1
        return await _fake_statuses()

    async def counting_stats():
        stats_calls['memory'] = stats_calls.get('memory', 0) + 1
        return await _fake_stats()

    monkeypatch.setattr(wsr, '_get_agent_statuses', counting_statuses)
    monkeypatch.setattr(wsr, '_get_memory_stats', counting_stats)


def _reset_snapshot():
    wsr._ws_snapshot_cache = None


class TestSnapshotSingleFlight:
    def test_concurrent_tickers_compute_once(self, monkeypatch):
        import asyncio

        _reset_snapshot()
        calls = {}
        _install_fakes(monkeypatch, calls)

        async def scenario():
            # five tick tasks fire "simultaneously" on one loop
            return await asyncio.gather(*[wsr._status_snapshot() for _ in range(5)])

        results = asyncio.run(scenario())
        assert calls['memory'] == 1, (
            f"a tick herd of 5 caused {calls['memory']} computations — "
            "single-flight is broken"
        )
        assert calls['agents'] == 1
        for agents, stats in results:
            assert agents == [{'id': 'a1', 'name': 'A', 'status': 'idle', 'avatar': ''}]
            assert stats['total'] == 1

    def test_ttl_expiry_recomputes(self, monkeypatch):
        _reset_snapshot()
        calls = {}
        _install_fakes(monkeypatch, calls)

        async def call():
            return await wsr._status_snapshot()

        import asyncio

        asyncio.run(call())
        asyncio.run(call())  # within TTL: cached
        assert calls['memory'] == 1

        # age the cache past the TTL
        ts, agents, stats = wsr._ws_snapshot_cache
        wsr._ws_snapshot_cache = (ts - wsr._WS_SNAPSHOT_TTL - 1, agents, stats)
        asyncio.run(call())
        assert calls['memory'] == 2, 'an expired snapshot must be recomputed'


class TestWSClientsStillServed:
    def test_every_client_receives_status_frames(self, client, monkeypatch):
        """Each connected client must still get its own agent_status and
        memory_stats frames on the (fast) tick."""
        monkeypatch.setattr(wsr, '_WS_TICK_SECONDS', 0.05)
        monkeypatch.setattr(wsr, '_WS_SNAPSHOT_TTL', 0.05)
        _reset_snapshot()
        _install_fakes(monkeypatch, {})

        with contextlib.ExitStack() as stack:
            sessions = [stack.enter_context(client.websocket_connect('/ws')) for _ in range(3)]
            for s in sessions:
                seen = set()
                for _ in range(40):  # bounded drain: init frames then ticks
                    frame = s.receive_json()
                    seen.add(frame.get('type'))
                    if {'agent_status', 'memory_stats'} <= seen:
                        break
                assert 'agent_status' in seen, f'client missed status frames: {seen}'
                assert 'memory_stats' in seen, f'client missed stats frames: {seen}'

    def test_tick_herd_collapses_to_one_compute(self, client, monkeypatch):
        """3 clients x ~10 fast ticks: the per-client compute would be ~30
        memory_stats calls; the shared snapshot must keep it near the tick
        count itself."""
        monkeypatch.setattr(wsr, '_WS_TICK_SECONDS', 0.05)
        monkeypatch.setattr(wsr, '_WS_SNAPSHOT_TTL', 0.05)
        _reset_snapshot()

        calls = {'n': 0}
        real_stats = mdb.memory_stats

        def counting_stats(*a, **kw):
            calls['n'] += 1
            return real_stats(*a, **kw)

        monkeypatch.setattr(mdb, 'memory_stats', counting_stats)

        with contextlib.ExitStack() as stack:
            sessions = [stack.enter_context(client.websocket_connect('/ws')) for _ in range(3)]
            time.sleep(0.55)  # ~10 ticks at 0.05s
            for s in sessions:
                with contextlib.suppress(Exception):
                    for _ in range(6):
                        s.receive_json()

        # sequential per-client: ~30 computes; shared: ~10 (one per tick).
        # generous upper margin for scheduling jitter, still half of sequential.
        assert calls['n'] < 16, (
            f"{calls['n']} memory_stats computations for 3 clients x ~10 ticks — "
            'the tick herd is computing per client again'
        )
