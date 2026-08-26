"""Module 36 — the walk test as a gate, not a report.

    "Every result gets checked cold. An agent with no memory has to open the
     root, find its way, act, and report status from the files alone. If it
     can't, the structure gets fixed until it can."

validate() has always run those checks; nothing acted on the result. Measured
live before this module existed, deleting ONE stage contract produced:

    /validate       ok: False, "stages/01-gather has no CONTEXT.md"
    /api/icm/route  status: matched, stage: 01-gather
    POST /api/chat  200, route-log: matched, 214 tokens

The validator knew. The router routed anyway, the agent got a context with no
stage contract in it, and the log recorded a normal-looking run.

The two properties that matter, and they pull in opposite directions:

1. A workspace failing the walk test must NOT be silently assembled into a
   model's context, and a blocked run must not look like a successful one.
2. A write must NEVER be blocked. "Every output is an edit surface", and
   editing is how a broken workspace gets repaired — gating the repair path
   would be perverse.
"""

from __future__ import annotations

import importlib

import pytest


@pytest.fixture()
def env(tmp_path, monkeypatch):
    monkeypatch.setenv('AGENTIC_OS_DATA_DIR', str(tmp_path))
    from backend.services import icm as icm_mod

    importlib.reload(icm_mod)
    from backend.services import icm_gate as gate_mod

    importlib.reload(gate_mod)
    from backend.services import icm_router as router_mod

    importlib.reload(router_mod)
    gate_mod.clear_cache()
    return icm_mod, gate_mod, router_mod


@pytest.fixture()
def ws(env):
    icm, gate, _ = env
    w = icm.WORKSPACES_DIR / 'billing'
    icm.scaffold(w, 'billing', '', ['gather', 'send'])
    ctx = w / 'CONTEXT.md'
    ctx.write_text(ctx.read_text(encoding='utf-8') + '\n## Routes\n- invoice\n',
                   encoding='utf-8')
    gate.clear_cache()
    return w


def _break_contract(w, gate):
    (w / 'stages' / '01-gather' / 'CONTEXT.md').unlink()
    gate.clear_cache()


# ── the gate itself ───────────────────────────────────────────────────────────
def test_a_healthy_workspace_is_allowed(env, ws):
    _, gate, _ = env
    v = gate.gate(ws)
    assert v['allowed'] is True
    assert v['passes'] is True
    assert v['errors'] == []


def test_a_missing_stage_contract_is_refused(env, ws):
    """L2 is the control point. Without it a stage scopes nothing."""
    _, gate, _ = env
    _break_contract(ws, gate)
    v = gate.gate(ws)
    assert v['allowed'] is False
    assert any('CONTEXT.md' in e for e in v['errors'])


def test_every_refusal_carries_a_repair(env, ws):
    """A gate that blocks without saying how to unblock gets routed around."""
    _, gate, _ = env
    _break_contract(ws, gate)
    v = gate.gate(ws)
    assert v['remedies']
    for r in v['remedies']:
        assert r['error']
        assert r['fix'].strip()


def test_remedies_are_specific_to_the_failure(env, ws):
    """A single boilerplate fix for every error is not a repair instruction.

    The revert proof showed the per-error branches could all be deleted and
    every test still passed, because nothing compared two different failures.
    """
    _, gate, _ = env

    (ws / 'stages' / '01-gather' / 'CONTEXT.md').unlink()
    gate.clear_cache()
    contract_fix = gate.gate(ws)['remedies'][0]['fix']

    (ws / 'IDENTITY.md').unlink()
    gate.clear_cache()
    fixes = {r['fix'] for r in gate.gate(ws)['remedies']}

    identity_fix = next(f for f in fixes if 'IDENTITY' in f)
    assert contract_fix != identity_fix, 'different failures need different repairs'
    assert 'CONTEXT.md' in contract_fix
    assert 'Inputs' in contract_fix


def test_the_refusal_explains_the_consequence_not_just_the_rule(env, ws):
    _, gate, _ = env
    _break_contract(ws, gate)
    assert 'incomplete structure' in gate.gate(ws)['reason']


def test_warnings_alone_do_not_gate(env, ws):
    """A long CONTEXT.md is untidy, not misleading. Only errors block."""
    _, gate, _ = env
    ctx = ws / 'stages' / '01-gather' / 'CONTEXT.md'
    ctx.write_text(ctx.read_text(encoding='utf-8') + '\n' + '\n'.join(
        f'padding line {i}' for i in range(200)), encoding='utf-8')
    gate.clear_cache()
    v = gate.gate(ws)
    assert v['warnings'], 'expected this to produce a warning'
    assert v['allowed'] is True


def test_a_missing_identity_is_refused(env, ws):
    _, gate, _ = env
    (ws / 'IDENTITY.md').unlink()
    gate.clear_cache()
    v = gate.gate(ws)
    assert v['allowed'] is False
    assert any('IDENTITY' in r['fix'] for r in v['remedies'])


def test_a_nonexistent_workspace_is_refused_not_crashed(env):
    _, gate, _ = env
    v = gate.gate_workspace_id('no-such-workspace')
    assert v['allowed'] is False
    assert 'does not exist' in v['reason']


def test_a_hostile_workspace_id_is_refused(env):
    _, gate, _ = env
    assert gate.gate_workspace_id('../../etc')['allowed'] is False


# ── caching, because this runs on every chat turn ─────────────────────────────
def test_the_verdict_is_cached_briefly(env, ws):
    """Re-walking the tree per chat turn puts a filesystem crawl in the hot path."""
    _, gate, _ = env
    calls = []
    from backend.services import icm as icm_mod

    real = icm_mod.validate

    def counting(w):
        calls.append(1)
        return real(w)

    icm_mod.validate = counting
    try:
        gate.check(ws)
        gate.check(ws)
        gate.check(ws)
    finally:
        icm_mod.validate = real
    assert len(calls) == 1


def test_clearing_the_cache_forces_a_re_check(env, ws):
    """A repair must be picked up, not masked by a stale pass."""
    _, gate, _ = env
    assert gate.gate(ws)['allowed'] is True
    _break_contract(ws, gate)
    assert gate.gate(ws)['allowed'] is False


def test_the_cache_expires_on_its_own(env, ws, monkeypatch):
    """Without an expiry a repair stays invisible until the process restarts.

    The explicit clear_cache() in the test above hides this: it proves the
    cache CAN be invalidated, not that it ever invalidates itself. The revert
    proof caught that -- making the cache permanent broke nothing. This drives
    the clock instead of clearing the cache.
    """
    _, gate, _ = env
    assert gate.gate(ws)['allowed'] is True

    # Break it WITHOUT clearing: the cached pass must still be served.
    (ws / 'stages' / '01-gather' / 'CONTEXT.md').unlink()
    assert gate.gate(ws)['allowed'] is True, 'expected the cached verdict'

    # Move past the TTL. The next call must re-walk and see the truth.
    real_time = gate.time.time
    monkeypatch.setattr(gate.time, 'time',
                        lambda: real_time() + gate.CACHE_SECONDS + 1)
    assert gate.gate(ws)['allowed'] is False, 'the cache must expire on its own'


def test_an_audit_never_uses_the_cache(env, ws):
    """"What is broken right now" must not answer from a stale verdict."""
    _, gate, _ = env
    gate.check(ws)
    (ws / 'stages' / '01-gather' / 'CONTEXT.md').unlink()
    audit = gate.audit_all()
    row = next(r for r in audit['workspaces'] if r['workspace_id'] == 'billing')
    assert row['passes'] is False


# ── the router refuses to assemble a broken workspace ─────────────────────────
def test_a_healthy_workspace_still_assembles(env, ws):
    _, _, router = env
    d = router.resolve_and_assemble('send the invoice')
    assert d['matched'] is True
    assert d['compiled_context']
    assert d['gate']['allowed'] is True


def test_a_broken_workspace_is_not_assembled_into_context(env, ws):
    """THE defect. The context is what reaches the model."""
    _, gate, router = env
    _break_contract(ws, gate)
    d = router.resolve_and_assemble('send the invoice')
    assert d['compiled_context'] == ''
    assert d['estimated_tokens'] == 0
    assert d['blocked_by_walk_test'] is True


def test_the_decision_and_its_evidence_still_come_back(env, ws):
    """Withholding the context must not withhold the diagnosis."""
    _, gate, router = env
    _break_contract(ws, gate)
    d = router.resolve_and_assemble('send the invoice')
    assert d['matched'] is True
    assert d['workspace_id'] == 'billing'
    assert d['reason']
    assert d['gate']['remedies']


def test_a_blocked_run_does_not_look_like_a_normal_one_in_the_log(env, ws):
    """It logged "matched, 214 tokens" while the control point was missing."""
    _, gate, router = env
    _break_contract(ws, gate)
    d = router.resolve_and_assemble('send the invoice')
    router.log_decision('send the invoice', d)
    entry = router.recent_decisions()[0]
    assert entry['status'] == 'blocked-walk-test'
    assert entry['estimated_tokens'] == 0
    assert entry['blocked_errors']


def test_an_unmatched_request_is_unaffected_by_the_gate(env, ws):
    _, _, router = env
    d = router.resolve_and_assemble('what is the weather tomorrow')
    assert d['matched'] is False
    assert d['gate'] is None


def test_repairing_the_workspace_restores_assembly(env, ws):
    """The gate must be a door, not a wall."""
    _, gate, router = env
    _break_contract(ws, gate)
    assert router.resolve_and_assemble('send the invoice')['compiled_context'] == ''

    (ws / 'stages' / '01-gather' / 'CONTEXT.md').write_text(
        '# 01 gather\n\n## Inputs\n| Source | File/Location | Section/Scope | Why |\n'
        '|--------|---------------|---------------|-----|\n'
        '| Run input | (provided at run time) | Full | The task |\n\n'
        '## Process\n1. Gather.\n\n## Outputs\n'
        '| Artifact | Location | Format |\n|----------|----------|--------|\n'
        '| Result | output/gather.md | Markdown |\n', encoding='utf-8')
    gate.clear_cache()
    d = router.resolve_and_assemble('send the invoice')
    assert d['compiled_context']
    assert not d.get('blocked_by_walk_test')


# ── writes are never gated ────────────────────────────────────────────────────
def test_a_write_into_a_broken_workspace_is_allowed(env, ws):
    """Editing is how a broken workspace gets fixed."""
    _, gate, _ = env
    _break_contract(ws, gate)
    target = ws / 'stages' / '01-gather' / 'CONTEXT.md'
    target.write_text('# rebuilt by hand\n', encoding='utf-8')
    assert target.is_file()


class TestGateEndpoints:
    def _make(self, client, name, routes='invoice'):
        r = client.post('/api/icm/workspaces',
                        json={'name': name, 'stages': ['gather', 'send']})
        assert r.status_code == 200, r.text
        client.put(f'/api/icm/workspaces/{name}/file',
                   json={'path': 'CONTEXT.md',
                         'content': f'# Routing\n\n## Routes\n- {routes}\n'})
        return name

    def _break(self, client, name):
        """Put the workspace into a genuinely FAILING state over HTTP.

        Writing an empty IDENTITY.md does not do it -- validate() checks the
        file EXISTS, so an empty one still passes and the "break then write"
        tests were vacuous. The revert proof exposed that: gating writes broke
        no test because no test ever wrote into a failing workspace. Emptying a
        stage contract is a real failure: the stage then has no Inputs, Process
        or Outputs.
        """
        import shutil
        from backend.services import icm, icm_gate

        target = icm.WORKSPACES_DIR / name / 'stages' / '01-gather' / 'CONTEXT.md'
        target.unlink()
        icm_gate.clear_cache()
        assert not icm_gate.gate(icm.WORKSPACES_DIR / name)['allowed'], (
            'the fixture must actually break the walk test')
        return shutil  # keeps the import used; harmless

    def test_writing_into_a_failing_workspace_is_never_blocked(self, client):
        """Editing is how a broken workspace gets repaired."""
        import uuid

        name = 'g11-' + uuid.uuid4().hex[:8]
        self._make(client, name)
        self._break(client, name)

        r = client.put(f'/api/icm/workspaces/{name}/file',
                       json={'path': 'notes.md', 'content': 'working on it'})
        assert r.status_code == 200, r.text
        assert r.json()['ok'] is True, 'a write must never be refused'
        assert r.json()['walk_test']['passes'] is False
        assert r.json()['walk_test']['remedies']

    def test_a_repair_write_clears_the_failure_immediately(self, client):
        """A stale cached verdict would hide the repair from the next run."""
        import uuid

        name = 'g11-' + uuid.uuid4().hex[:8]
        self._make(client, name)
        self._break(client, name)

        contract = ('# 01 gather\n\n## Inputs\n'
                    '| Source | File/Location | Section/Scope | Why |\n'
                    '|--------|---------------|---------------|-----|\n'
                    '| Run input | (provided at run time) | Full | The task |\n\n'
                    '## Process\n1. Gather.\n\n## Outputs\n'
                    '| Artifact | Location | Format |\n|----------|----------|--------|\n'
                    '| Result | output/gather.md | Markdown |\n')
        fixed = client.put(f'/api/icm/workspaces/{name}/file',
                           json={'path': 'stages/01-gather/CONTEXT.md',
                                 'content': contract})
        assert fixed.status_code == 200
        assert fixed.json()['walk_test']['passes'] is True, (
            'the repair must be visible in the same response, not after a cache expiry')

    def test_the_audit_endpoint_lists_failures_with_repairs(self, client):
        r = client.get('/api/icm/walk-test')
        assert r.status_code == 200
        body = r.json()
        assert body['ok'] is True
        assert body['total'] == body['passing'] + body['failing']
        for w in body['workspaces']:
            if not w['passes']:
                assert w['remedies']

    def test_a_single_workspace_can_be_walk_tested(self, client):
        import uuid

        name = 'g11-' + uuid.uuid4().hex[:8]
        self._make(client, name)
        r = client.get(f'/api/icm/workspaces/{name}/walk-test')
        assert r.status_code == 200
        assert 'allowed' in r.json()

    def test_walk_testing_an_unknown_workspace_is_404(self, client):
        assert client.get('/api/icm/workspaces/not-real-at-all/walk-test').status_code == 404

    def test_the_route_preview_is_unaffected(self, client):
        """Previewing a route is diagnosis, not a run; it must keep working."""
        r = client.get('/api/icm/route?q=anything+at+all')
        assert r.status_code == 200
