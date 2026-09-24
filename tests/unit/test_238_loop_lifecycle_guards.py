"""Unit tests — loop lifecycle: creation guards, restore guards, manual-run retirement (r91, #252)

Fresh-eyes deep-dive of the scheduler's persistence/restore path found
three lifecycle holes:

  1. BUILT-IN ID HIJACK. DELETE /api/loops/{id} guards the built-in job ids
     with a 403, but POST /api/loops never did — so {"job_id": "standup"}
     (or memory_index / cost_digest / status_cleanup) silently REPLACED the
     built-in job via add_loop's replace_existing=True. Verified live on the
     old code: HTTP 200, the standup job's FUNCTION was swapped for the
     user's goal-loop (daily standups simply stop happening), the impostor
     was invisible in GET /api/loops (built-in ids are filtered out of the
     listing), and it never persisted (_save_loops filters them too) — a
     restart deleted the "loop" and resurrected the built-in. Four symptoms,
     one unguarded door.

  2. RESURRECTION OF DEAD LOOPS. The scheduled path retires a loop the
     moment its budget is spent or kill_after_success fires, but that
     retirement is a second _save_loops() after the run's own save — a crash
     in between persists a loop whose life already ended. restore_loops
     evaluated no stopping conditions, so a spent loop came back listed as
     'running' until its next wake (up to a week at interval=10080), and a
     kill_after_success loop whose SUCCESS had been persisted ran one more
     REAL paid LLM iteration before removing itself.

  3. MANUAL-RUN RETIREMENT GAP. run_loop_now incremented run_count but never
     applied the retirement checks — a manual run that spent the max_runs
     budget left the loop listed as running until the next scheduled wake
     (possibly a week out).

Restores that must still work, pinned: a loop whose last iteration FAILED
(kill_after_success not yet satisfied), a never-run loop with
kill_after_success set, and paused loops (pre-existing behavior).
"""
import json

import pytest

from backend.services import scheduler as sched
from backend.services.scheduler import _BUILTIN_JOB_IDS, LOOPS_PATH


@pytest.fixture(autouse=True)
def _clean_loop_state():
    """These tests manipulate the process-wide scheduler registry and the
    persisted loops file; both are restored to empty so later test files see
    a clean loop state (the r85/r88 lesson: tests own their shared state)."""
    yield
    sched._jobs.clear()
    _seed_loops_file({})


def _seed_loops_file(payload: dict) -> None:
    LOOPS_PATH.parent.mkdir(parents=True, exist_ok=True)
    LOOPS_PATH.write_text(json.dumps(payload, indent=2))


def _meta(**over):
    m = {
        'prompt': 'p', 'interval_minutes': 15, 'agent_id': 'builder', 'target': 'web',
        'goal_id': '', 'max_runs': 0, 'kill_after_success': False, 'status': 'running',
        'created_at': '2026-01-01T00:00:00', 'run_count': 0, 'last_run_at': '',
        'last_error': '', 'history': [],
    }
    m.update(over)
    return m


class TestBuiltinIdHijack:
    def test_create_with_builtin_id_is_refused_and_builtins_survive(self, client):
        sched.start()
        s = sched.get_scheduler()
        funcs_before = {jid: s.get_job(jid).func for jid in _BUILTIN_JOB_IDS}

        r = client.post('/api/loops', json={
            'prompt': 'hijack', 'interval_minutes': 5, 'job_id': 'standup',
        })
        assert r.status_code == 403, r.text
        assert 'protected system job' in r.json()['error']

        for jid, fn in funcs_before.items():
            assert s.get_job(jid).func is fn, f'{jid} was replaced by the refused create'
        assert 'standup' not in sched._jobs, 'the refused loop must not enter the registry'

    def test_delete_guard_still_enforced(self, client):
        r = client.delete('/api/loops/standup')
        assert r.status_code == 403


class TestRestoreGuards:
    def test_dead_loops_are_not_resurrected(self, client):
        _seed_loops_file({
            'dead_spent': _meta(max_runs=3, run_count=3),
            'dead_kill': _meta(kill_after_success=True, run_count=2),
        })
        sched._jobs.clear()
        restored = sched.restore_loops()
        assert restored == 0
        assert 'dead_spent' not in sched._jobs
        assert 'dead_kill' not in sched._jobs

    def test_dead_loops_are_pruned_from_the_persisted_file(self, client):
        _seed_loops_file({
            'dead_spent': _meta(max_runs=1, run_count=1),
            'alive': _meta(run_count=5),
        })
        sched._jobs.clear()
        sched.restore_loops()
        persisted = json.loads(LOOPS_PATH.read_text())
        assert 'dead_spent' not in persisted, 'finished loops must not linger in the file'
        assert 'alive' in persisted

    def test_live_loops_still_restore(self, client):
        # last iteration FAILED -> kill_after_success not satisfied -> alive
        # never ran -> kill_after_success cannot be satisfied yet -> alive
        # ordinary loop -> alive
        _seed_loops_file({
            'alive_failed_kill': _meta(kill_after_success=True, run_count=2, last_error='provider failed'),
            'alive_never_ran': _meta(kill_after_success=True, run_count=0),
            'alive_plain': _meta(run_count=7),
        })
        sched._jobs.clear()
        restored = sched.restore_loops()
        assert restored == 3
        for jid in ('alive_failed_kill', 'alive_never_ran', 'alive_plain'):
            assert jid in sched._jobs
        # counters are carried forward, not reset
        assert sched._jobs['alive_plain']['run_count'] == 7

    def test_paused_loop_restores_paused(self, client):
        _seed_loops_file({'paused_one': _meta(status='paused', run_count=1)})
        sched._jobs.clear()
        sched.restore_loops()
        assert sched._jobs['paused_one']['status'] == 'paused'


class TestManualRunRetirement:
    def test_manual_run_spending_max_runs_retires_immediately(self, client, monkeypatch):
        import asyncio

        async def fake_goal_loop(job_id, prompt, agent_id, target):
            sched._jobs[job_id]['run_count'] = sched._jobs[job_id].get('run_count', 0) + 1
            sched._jobs[job_id]['last_run_at'] = 'now'
            sched._jobs[job_id].pop('last_error', None)

        monkeypatch.setattr(sched, '_run_goal_loop', fake_goal_loop)
        result = sched.add_loop('manual_max', 'p', 15, max_runs=2)
        assert result['ok'] is True
        sched._jobs['manual_max']['run_count'] = 1  # one prior scheduled run

        out = asyncio.run(sched.run_loop_now('manual_max'))
        assert out['ok'] is True
        assert out['retired'] is True, 'run_count reached max_runs — must retire now'
        assert 'manual_max' not in sched._jobs
        assert out['job']['run_count'] == 2, 'the retiring response still reports the run'

    def test_manual_run_satisfying_kill_after_success_retires(self, client, monkeypatch):
        import asyncio

        async def fake_goal_loop(job_id, prompt, agent_id, target):
            sched._jobs[job_id]['run_count'] = sched._jobs[job_id].get('run_count', 0) + 1
            sched._jobs[job_id].pop('last_error', None)  # success

        monkeypatch.setattr(sched, '_run_goal_loop', fake_goal_loop)
        sched.add_loop('manual_kill', 'p', 15, kill_after_success=True)
        out = asyncio.run(sched.run_loop_now('manual_kill'))
        assert out['retired'] is True
        assert 'manual_kill' not in sched._jobs

    def test_manual_run_of_unbounded_loop_does_not_retire(self, client, monkeypatch):
        import asyncio

        async def fake_goal_loop(job_id, prompt, agent_id, target):
            sched._jobs[job_id]['run_count'] = sched._jobs[job_id].get('run_count', 0) + 1

        monkeypatch.setattr(sched, '_run_goal_loop', fake_goal_loop)
        sched.add_loop('manual_plain', 'p', 15)
        out = asyncio.run(sched.run_loop_now('manual_plain'))
        assert out['retired'] is False
        assert 'manual_plain' in sched._jobs
        assert out['job']['run_count'] == 1
