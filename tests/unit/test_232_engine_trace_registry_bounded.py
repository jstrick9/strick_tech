"""Unit tests — engine trace / harness registries are bounded (r82, #246)

The process-wide ExecutionEngine singleton stored every completed
ExecutionTrace in self.active_traces and never removed one; six write
paths (single, fan-out, map-reduce, chain, test-harness, and the
router's own execute) each added an entry per execution for the
lifetime of the process. A workflow-heavy deployment accumulates
hundreds of thousands of traces while the only consumers are
GET /api/engine/traces?limit=50 and an by-id drill-down used right
after a run. Measured: 2000 executions retained 2000 traces / 2.6MB
and climbing; with the cap, 256 traces / 1.2MB steady — identical API
output.

HarnessEngine had the same shape worse: run_test_harness appends to
self.results[harness_id] and the router DEFAULTS harness_id to a
fresh uuid per run — a new dict key per run, forever. The only
consumer (get_regression_report) reads history[-1] and history[-2].

Caps: 256 traces (5x the default listing depth; evicted by started_at,
not insertion order — fan-out/map-reduce complete out of order), 50
runs of history per harness id (25x the reader's needs), and the 100
most recently run harness ids. All write sites now go through
engine.record_trace().
"""
import asyncio
import json

import backend.services.llm as llm_mod


async def _fake_complete(messages, **kw):
    return {'text': 'ok', 'tokens': 3, 'model': 'mock'}


def _execute(client, i):
    return client.post(
        '/api/engine/execute',
        json={'agent_id': 'r82', 'prompt': f'p{i}', 'max_tokens': 10},
    ).json()


class TestTraceRegistryBounded:
    def test_registry_caps_at_256_and_keeps_newest(self, client, monkeypatch):
        monkeypatch.setattr('backend.services.llm.complete', _fake_complete, raising=False)
        from backend.services.agent_engine import get_engine

        engine = get_engine()
        first = _execute(client, 0)['trace_id']
        for i in range(1, 300):  # 300 > cap 256
            _execute(client, i)

        assert len(engine.active_traces) == 256, 'registry must not grow past the cap'

        listing = client.get('/api/engine/traces').json()['traces']
        assert len(listing) == 50, 'default listing depth unchanged'
        started = [t['duration_ms'] for t in listing]  # all present and recent
        assert listing[0]['agent_id'] == 'r82'

        # the 300th execution's trace is still resolvable by id…
        last = _execute(client, 300)
        assert engine.get_trace(last['trace_id']) is not None
        # …and the very first run's trace has been evicted (oldest, by
        # started_at). This is the intended new behavior: bounded history.
        assert engine.get_trace(first) is None
        assert len(engine.active_traces) == 256

    def test_eviction_is_by_started_at_not_insertion(self, client, monkeypatch):
        monkeypatch.setattr('backend.services.llm.complete', _fake_complete, raising=False)
        from backend.services.agent_engine import get_engine

        engine = get_engine()
        ids = [_execute(client, i)['trace_id'] for i in range(260)]
        kept = set(engine.active_traces)
        # exactly the OLDEST traces are gone; everything newer survives
        evicted = [t for t in ids if t not in kept]
        assert len(evicted) == 4
        assert evicted == ids[:4], 'eviction must remove oldest-first'


class TestHarnessRegistriesBounded:
    def _run(self, harness_id):
        from backend.services.agent_engine import get_harness_engine

        async def agent_fn(tc):
            return {'text': 'ok'}

        return asyncio.run(
            get_harness_engine().run_test_harness(
                harness_id, agent_fn, [{'id': 'x', 'input': 'i', 'expected': 'ok'}]
            )
        )

    def test_history_capped_per_harness_id(self):
        from backend.services.agent_engine import get_harness_engine

        for _ in range(55):  # > cap 50
            self._run('r82_stable')
        history = get_harness_engine().results['r82_stable']
        assert len(history) == 50
        # the regression reader still works on the last two runs
        report = get_harness_engine().get_regression_report('r82_stable')
        assert report['ok'] is True
        assert 'latest_pass_rate' in report

    def test_harness_id_registry_capped(self):
        from backend.services.agent_engine import get_harness_engine

        for i in range(120):  # > cap 100
            self._run(f'r82_auto_{i}')
        assert len(get_harness_engine().results) == 100
