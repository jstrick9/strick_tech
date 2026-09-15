"""Module 14 — workflow editor deep pass (round 26).

Regressions for defects found by journeying the editor end-to-end (palette,
ports, properties, undo, run, import/export, delete):

1. MODEL ROUTING. Agent nodes passed only agent_id to llm.complete(), and
   resolve_model() maps ids through the STATIC OPENROUTER_MODELS table —
   whose keys are MODEL names ('gemini', 'claude'), not agent ids
   ('researcher', 'builder'). Every workflow agent node therefore ran on
   the DEFAULT model, silently ignoring the model each agent is configured
   with. Verified in the cost ledger before the fix:

       researcher -> anthropic/claude-3.5-sonnet   (configured: gemini)
       builder    -> anthropic/claude-3.5-sonnet   (configured: hermes)

   and after:

       researcher -> google/gemini-2.5-pro
       builder    -> nousresearch/hermes-3-llama-3.1-405b

   The user picks the free model for the agent; the workflow quietly spends
   the expensive default. The fix passes the agent's own model through, the
   same way chat.py does. The loop node had the identical hole.

2. VALIDATOR BLINDNESS TO AGENT CONFIG. An unknown agent_id does not fail a
   run — the LLM layer falls back to the default model — so a typo (or an
   agent deleted after the workflow was built) produces output from the
   wrong model while everything looks fine. validate now warns with
   UNKNOWN_AGENT / NO_AGENT.

3. UI HONESTY / RACES (frontend/js/03-features-a.js, source contracts in
   the same style as test_147):
   - wfDeleteWf toasted "Workflow deleted" without reading the response —
     a 404 (already deleted elsewhere) or a 500 was reported as success.
   - wfNewWorkflow never checked the response; a server refusal degraded
     to a TypeError caught as a generic failure, losing the reason.
   - wfRun executed the SAVED graph while its validation gate checked the
     IN-MEMORY one — autosave debounces 2s, so an edit made right before
     Run raced and silently executed the stale graph. wfRun now flushes
     state to disk first.
   - Double-click palette adds all landed at the exact same centre point:
     the 2nd node buried the 1st perfectly under it (three chips added,
     one node visible). Adds now cascade diagonally like wfPasteNode.
"""

from __future__ import annotations

import json
import re
from pathlib import Path

import pytest

REPO = Path(__file__).resolve().parents[2]
JS = (REPO / 'frontend' / 'js' / '03-features-a.js').read_text()


# ── helpers ───────────────────────────────────────────────────────────────────

@pytest.fixture
def make_wf(client):
    """Create workflows and clean them up (workflows are FILES, not DB rows)."""
    created = []

    def _make(nodes, edges, name='EditorDeepProbe'):
        r = client.post('/api/workflow', json={'name': name, 'nodes': nodes, 'edges': edges})
        assert r.status_code == 200, r.text
        wid = r.json()['workflow']['id']
        created.append(wid)
        return wid

    yield _make
    for wid in created:
        client.delete(f'/api/workflow/{wid}')


def _agent_graph(agent_id):
    return {
        'nodes': [
            {'id': 'n1', 'type': 'trigger', 'x': 0, 'y': 0, 'config': {'event': 'chat'}},
            {'id': 'n2', 'type': 'agent', 'x': 100, 'y': 0, 'label': 'The Agent',
             'config': {'agent_id': agent_id} if agent_id is not None else {}},
            {'id': 'n3', 'type': 'output', 'x': 200, 'y': 0, 'config': {'target': 'chat'}},
        ],
        'edges': [
            {'id': 'e1', 'from': 'n1', 'to': 'n2'},
            {'id': 'e2', 'from': 'n2', 'to': 'n3'},
        ],
    }


def _fn_body(name: str) -> str:
    """Source of one function in 03-features-a.js, comments excluded by the
    asserts themselves (none of the asserted tokens appear in comments)."""
    starts = [JS.index(k) for k in (f'async function {name}(', f'function {name}(') if k in JS]
    assert starts, f'{name} not found'
    start = min(starts)
    nxt = len(JS)
    for m in re.finditer(r'\n(?:async )?function ', JS[start + 10:]):
        nxt = start + 10 + m.start()
        break
    return JS[start:nxt]


# ── 1. model routing ──────────────────────────────────────────────────────────

class TestAgentModelRouting:
    @pytest.fixture
    def captured(self, monkeypatch):
        """Capture what the executor hands llm.complete(); no network."""
        calls = []

        async def fake_complete(messages, agent_id='default', model='', **kw):
            calls.append({'agent_id': agent_id, 'model': model})
            return {'text': 'ok', 'tokens': 1, 'cost': 0.0, 'model': model or 'default',
                    'latency_ms': 1}

        from backend.services import llm as llm_mod
        monkeypatch.setattr(llm_mod, 'complete', fake_complete)
        return calls

    def test_agent_node_passes_the_agents_configured_model(self, client, make_wf, captured):
        wid = make_wf(*_agent_graph('researcher').values())
        r = client.post(f'/api/workflow/{wid}/run', json={'input': 'hello'})
        assert r.status_code == 200, r.text
        agent_calls = [c for c in captured if c['agent_id'] == 'researcher']
        assert agent_calls, 'agent node never called the LLM'
        # researcher is seeded with model 'gemini' — before the fix this was
        # '' (→ the anthropic default), ignoring the agent's configuration.
        assert agent_calls[0]['model'] == 'gemini', (
            f"agent node ignored the agent's configured model: {agent_calls[0]}"
        )

    def test_loop_node_passes_the_agents_configured_model(self, client, make_wf, captured):
        graph = {
            'nodes': [
                {'id': 'n1', 'type': 'trigger', 'x': 0, 'y': 0, 'config': {'event': 'chat'}},
                {'id': 'n2', 'type': 'loop', 'x': 100, 'y': 0,
                 'config': {'agent_id': 'builder', 'iterations': 1, 'prompt': 'refine {{prev_output}}'}},
                {'id': 'n3', 'type': 'output', 'x': 200, 'y': 0, 'config': {'target': 'chat'}},
            ],
            'edges': [
                {'id': 'e1', 'from': 'n1', 'to': 'n2'},
                {'id': 'e2', 'from': 'n2', 'to': 'n3'},
            ],
        }
        wid = make_wf(graph['nodes'], graph['edges'])
        r = client.post(f'/api/workflow/{wid}/run', json={'input': 'hello'})
        assert r.status_code == 200, r.text
        loop_calls = [c for c in captured if c['agent_id'] == 'builder']
        assert loop_calls, 'loop node never called the LLM'
        assert loop_calls[0]['model'] == 'hermes', (
            f"loop node ignored the agent's configured model: {loop_calls[0]}"
        )

    def test_unknown_agent_still_falls_back_but_says_so_in_validation(self, client, make_wf):
        """The LLM fallback for unknown ids is deliberate platform behaviour —
        but the validator must surface it instead of staying silent."""
        wid = make_wf(*_agent_graph('definitely_not_an_agent_zz').values())
        r = client.post(f'/api/workflow/{wid}/validate', json=_agent_graph('definitely_not_an_agent_zz'))
        assert r.status_code == 200, r.text
        codes = {w['code'] for w in r.json().get('warnings', [])}
        assert 'UNKNOWN_AGENT' in codes


# ── 2. validator warnings ──────────────────────────────────────────────────────

class TestValidateAgentConfig:
    def _codes(self, client, wid, graph):
        r = client.post(f'/api/workflow/{wid}/validate', json=graph)
        assert r.status_code == 200, r.text
        return {w['code'] for w in r.json().get('warnings', [])}

    def test_missing_agent_id_warns(self, client, make_wf):
        wid = make_wf(*_agent_graph('researcher').values())
        graph = _agent_graph(None)  # agent node with no agent_id at all
        assert 'NO_AGENT' in self._codes(client, wid, graph)

    def test_known_agent_does_not_warn(self, client, make_wf):
        wid = make_wf(*_agent_graph('researcher').values())
        codes = self._codes(client, wid, _agent_graph('researcher'))
        assert 'NO_AGENT' not in codes and 'UNKNOWN_AGENT' not in codes

    def test_warning_names_the_node_and_the_agent(self, client, make_wf):
        wid = make_wf(*_agent_graph('researcher').values())
        graph = _agent_graph('ghost_agent_42')
        r = client.post(f'/api/workflow/{wid}/validate', json=graph)
        msgs = [w['msg'] for w in r.json().get('warnings', []) if w['code'] == 'UNKNOWN_AGENT']
        assert msgs and 'The Agent' in msgs[0] and 'ghost_agent_42' in msgs[0], (
            'the warning must say which node references which missing agent'
        )


# ── 3. frontend source contracts ──────────────────────────────────────────────

class TestFrontendContracts:
    def test_delete_requires_server_confirmation(self):
        body = _fn_body('wfDeleteWf')
        assert '!r.ok' in body and 'd.ok === false' in body, (
            'wfDeleteWf must read the DELETE response before claiming success'
        )
        assert body.index('Delete failed') < body.index('Workflow deleted'), (
            'the failure branch must exist and be reachable before any success toast'
        )

    def test_create_checks_the_response(self):
        body = _fn_body('wfNewWorkflow')
        assert ('!r.ok' in body or '!d.workflow' in body) and 'Create failed' in body, (
            'wfNewWorkflow must check the create response and surface the reason'
        )

    def test_run_flushes_unsaved_state_before_starting(self):
        body = _fn_body('wfRun')
        # the executor runs the SAVED graph; the editor must PUT current
        # state before POSTing the run or it races its own 2s autosave.
        assert "method:'PUT'" in body and '/run' in body, (
            'wfRun must save the workflow before running it'
        )
        assert body.index("method:'PUT'") < body.index('/run'), (
            'the save must happen before the run request is issued'
        )

    def test_double_click_adds_cascade(self):
        body = _fn_body('wfAddNodeCenter')
        assert '(k % 7)' in body, (
            'palette double-click adds must cascade or later nodes bury earlier ones'
        )

    def test_delete_failure_refreshes_the_list(self):
        body = _fn_body('wfDeleteWf')
        # a 404 usually means "deleted elsewhere" — reload so the sidebar
        # reflects reality instead of leaving the stale row behind.
        assert 'wfLoadWorkflows' in body


# ── 4. run honesty stays intact ───────────────────────────────────────────────

def test_a_failing_agent_node_still_fails_the_run(client, make_wf, monkeypatch):
    """Guard the neighbouring behaviour while touching the executor."""
    async def boom(messages, agent_id='default', model='', **kw):
        raise RuntimeError('provider down')

    from backend.services import llm as llm_mod
    monkeypatch.setattr(llm_mod, 'complete', boom)
    wid = make_wf(*_agent_graph('researcher').values())
    text = client.post(f'/api/workflow/{wid}/run', json={'input': 'x'}).text
    assert '"type": "node_error"' in text or '"type":"node_error"' in text
    assert '"status": "failed"' in text or '"status":"failed"' in text
    # and no output may be delivered downstream of the failure
    assert '"delivered": false' in text or "'delivered': False" in text or '"delivered":false' in text
