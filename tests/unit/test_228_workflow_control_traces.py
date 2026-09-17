"""r51 — workflow runs are traced in the Control Tower.

Found by the unused-endpoint audit (r49): start_run()/record_step()/
finish_run() had NO production caller — the Control Tower's run list, live
steps, cost totals and kill switch all operated on a store that real work
never wrote to (only tests did). Workflow runs now open a trace, record one
step per node (with the model usage the replay frames don't carry), honor
both stop conditions at every node boundary, and finish the trace — which is
what pushes the completion/failure notification (r49 toast, r50 bell).
"""

import json

import pytest

from backend.services.memory_db import get_conn


SRC = open('backend/routers/workflow.py').read()
CT_SRC = open('backend/routers/control_tower.py').read()


@pytest.fixture
def make_wf(client):
    created = []

    def _make(nodes, edges, name='TraceProbe'):
        r = client.post('/api/workflow', json={'name': name, 'nodes': nodes, 'edges': edges})
        assert r.status_code == 200, r.text
        wid = r.json()['workflow']['id']
        created.append(wid)
        return wid

    yield _make
    for wid in created:
        client.delete(f'/api/workflow/{wid}')


def sse_events(text: str) -> list[dict]:
    out = []
    for line in text.splitlines():
        if line.startswith('data:'):
            try:
                out.append(json.loads(line[5:]))
            except ValueError:
                pass
    return out


def _cleanup_trace(run_id: str):
    con = get_conn()
    try:
        con.execute('DELETE FROM agent_trace_steps WHERE run_id=?', (run_id,))
        con.execute('DELETE FROM agent_traces WHERE run_id=?', (run_id,))
        con.execute('DELETE FROM notifications WHERE run_id=?', (run_id,))
        con.commit()
    finally:
        con.close()


def _wf_run_rows(client):
    r = client.get('/api/control/runs?limit=50')
    assert r.status_code == 200
    return r.json()


# ── wiring ─────────────────────────────────────────────────────────────────────


def test_the_workflow_executor_wires_the_trace():
    assert "ct_start_run('workflow'" in SRC, 'runs must open a control-tower trace'
    assert 'ct_run_is_stopped(ct_run_id)' in SRC, (
        'the executor must check the stop conditions at node boundaries'
    )
    assert 'ct_record_step(' in SRC, 'each node must record a step'
    assert 'ct_finish_run(' in SRC, 'the stream must close the trace'


def test_control_tower_exposes_the_poller_friendly_stop_check():
    assert 'def run_is_stopped' in CT_SRC, (
        'kill_run() finishes the run and discards its own flag, so an '
        'executor polling between steps needs run_is_stopped() to read '
        '"no longer active" as stopped too'
    )


# ── behaviour ──────────────────────────────────────────────────────────────────


def test_a_run_is_traced_end_to_end(client, make_wf, monkeypatch):
    async def fake_complete(messages, **kw):
        return {
            'text': 'the answer',
            'tokens': 30,
            'prompt_tokens': 20,
            'completion_tokens': 10,
            'cost': 0.001,
            'model': 'test-model',
            'ok': True,
        }

    monkeypatch.setattr('backend.services.llm.complete', fake_complete)

    nodes = [
        {'id': 't1', 'type': 'trigger', 'label': 'Start', 'config': {}},
        {'id': 'a1', 'type': 'agent', 'label': 'Agent', 'config': {'prompt': '{{input}}', 'agent_id': 'builder'}},
        {'id': 'o1', 'type': 'output', 'label': 'Output', 'config': {'target': 'chat'}},
    ]
    edges = [{'from': 't1', 'to': 'a1'}, {'from': 'a1', 'to': 'o1'}]
    wid = make_wf(nodes, edges, name='trace-end-to-end')

    try:
        events = sse_events(client.post(f'/api/workflow/{wid}/run', json={'input': 'hello'}).text)
        done = [e for e in events if e.get('type') == 'done']
        assert done and done[0]['status'] == 'success'

        rows = _wf_run_rows(client)
        mine = next(r for r in rows if r.get('agent_name') == '🔄 trace-end-to-end')
        assert mine['status'] == 'done'
        assert mine['step_count'] == 3
        assert mine['total_cost'] == pytest.approx(0.001)
        assert mine['total_tokens'] == 30

        detail = client.get(f"/api/control/runs/{mine['run_id']}").json()
        agent_step = next(s for s in detail['steps'] if s['step_type'] == 'agent')
        assert agent_step['model'] == 'test-model'
        assert agent_step['tokens_in'] == 20
        assert agent_step['tokens_out'] == 10
        assert agent_step['status'] == 'done'
    finally:
        for r in _wf_run_rows(client):
            if r.get('agent_name') == '🔄 trace-end-to-end':
                _cleanup_trace(r['run_id'])


def test_a_killed_trace_stops_the_run_at_the_next_node(client, make_wf, monkeypatch):
    from backend.routers import control_tower as ct

    dead_id = ct.start_run('probe', 'probe', 'probe')
    client.post(f'/api/control/runs/{dead_id}/kill')  # finishes AND removes it
    monkeypatch.setattr('backend.routers.control_tower.start_run', lambda *a, **k: dead_id)

    nodes = [
        {'id': 't1', 'type': 'trigger', 'label': 'Start', 'config': {}},
        {'id': 'd1', 'type': 'delay', 'label': 'Wait', 'config': {'seconds': 1}},
        {'id': 'o1', 'type': 'output', 'label': 'Output', 'config': {'target': 'chat'}},
    ]
    edges = [{'from': 't1', 'to': 'd1'}, {'from': 'd1', 'to': 'o1'}]
    wid = make_wf(nodes, edges, name='trace-killed')

    try:
        events = sse_events(client.post(f'/api/workflow/{wid}/run', json={'input': 'x'}).text)
        killed = [e for e in events if e.get('type') == 'killed']
        done = [e for e in events if e.get('type') == 'done']
        assert killed and killed[0]['reason'] == 'user'
        assert done and done[0]['status'] == 'killed'
        assert done[0]['nodes_run'] == 1, 'the run must stop at the first node boundary, not run on'
    finally:
        _cleanup_trace(dead_id)


def test_a_budget_stop_finishes_the_trace_as_killed(client, make_wf, monkeypatch):
    from backend.routers import control_tower as ct

    rid = ct.start_run('probe', 'probe', 'probe')
    ct._kill_flags.add(rid)  # budget stop: flagged but still active
    monkeypatch.setattr('backend.routers.control_tower.start_run', lambda *a, **k: rid)

    nodes = [
        {'id': 't1', 'type': 'trigger', 'label': 'Start', 'config': {}},
        {'id': 'o1', 'type': 'output', 'label': 'Output', 'config': {'target': 'chat'}},
    ]
    edges = [{'from': 't1', 'to': 'o1'}]
    wid = make_wf(nodes, edges, name='trace-budget')

    try:
        events = sse_events(client.post(f'/api/workflow/{wid}/run', json={'input': 'x'}).text)
        killed = [e for e in events if e.get('type') == 'killed']
        done = [e for e in events if e.get('type') == 'done']
        assert killed and killed[0]['reason'] == 'budget'
        assert done and done[0]['status'] == 'killed'
        # the run was still active, so the executor's own finish_run is what
        # persisted the final state
        row = next(r for r in _wf_run_rows(client) if r['run_id'] == rid)
        assert row['status'] == 'killed'
    finally:
        _cleanup_trace(rid)
