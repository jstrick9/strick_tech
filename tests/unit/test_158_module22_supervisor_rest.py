"""Module 22 — the Supervisor workstation: `agent-identity`, `swarm`, `fusion`, `a2a`.

Destination: `supervisor`. Doc 82 covered the host pane and `hitl`; this pass
closes the remaining behavioural review of the tabs that run and authorise
agents. (`goals` is served by `goal_manager.py` and shares the DAG surface
already covered by the host pane; `finetune` is doc 71.)

Five defects, all reproduced against a live server before the fix:

1. AN EMPTY TOKEN SCOPE GRANTED EVERY ACTION. validate_jit_token guarded with
   `if required_action and scope and required_action not in scope`, so a token
   issued with scope [] skipped the check entirely. Verified live:

     token scope []            + required_action 'delete_everything' -> 200 ok
     token scope ['read_file'] + required_action 'delete_everything' -> 403

   The UNSCOPED token was the more powerful one. In a zero-trust design an
   empty scope is the least privilege there is; it must mean nothing.

2. issue-token raised HTTP 500 on a non-numeric ttl_seconds, and clamped only
   the UPPER bound — so ttl_seconds=-500 minted an ALREADY EXPIRED token and
   returned it as {"ok": true, "expires_in": -500}.

3. THE SWARM JUDGE'S WINNER WAS TRUSTED VERBATIM. A judge naming an agent that
   never ran produced ok:true, an EMPTY winner_output, and a confident
   "score: 99%" — while two real agents' answers were discarded. Judges
   hallucinate identifiers routinely.

4. fusion /route hardcoded ok:True beside an `error` field read from the
   result, and with no provider configured returned the placeholder string
   "[Stub: <model> — set OPENROUTER_API_KEY]" as the model's answer with
   ok:true AND error:false. Root cause: _call_model hand-rolled a stub dict
   with error:False and none of the markers llm.is_stub() looks for.

5. THE A2A AGENT-CARD FETCH WAS AN SSRF PRIMITIVE. /verify fetched whatever URL
   had been registered, with no address check and redirects followed. Verified
   live: an agent registered at http://169.254.169.254/latest/meta-data caused
   the server to attempt all three link-local URLs. The plugin installer
   refuses the identical URL — this endpoint never got the same guard.
"""

from __future__ import annotations

import json

import pytest

from backend.routers import agent_identity as ident


# ── 1 & 2. JIT token scope and bounds ─────────────────────────────────────────
@pytest.fixture
def agent(client):
    client.post('/api/agent-identity/provision', json={'agent_id': 't158_a', 'name': 'Probe'})
    yield 't158_a'
    from backend.services.memory_db import get_conn

    con = get_conn()
    try:
        for t, col in (
            ('agent_jit_tokens', 'agent_id'),
            ('agent_identities', 'agent_id'),
            ('agent_identity_audit', 'agent_id'),
        ):
            try:
                con.execute(f"DELETE FROM {t} WHERE {col} LIKE 't158%'")
            except Exception:
                pass
        con.commit()
    finally:
        con.close()


def _issue(client, agent, **kw):
    return client.post(f'/api/agent-identity/{agent}/issue-token', json=kw)


def _validate(client, token_id, agent, action=None):
    body = {'token_id': token_id, 'agent_id': agent}
    if action is not None:
        body['required_action'] = action
    return client.post('/api/agent-identity/token/validate', json=body)


def test_an_empty_scope_grants_no_action(client, agent):
    tok = _issue(client, agent, task_id='t', scope=[]).json()['token_id']
    r = _validate(client, tok, agent, 'delete_everything')
    assert r.status_code == 403, 'a token with no scope validated for an arbitrary action'
    assert 'scope does not include' in r.json()['error']


def test_an_empty_scope_is_stricter_than_a_populated_one(client, agent):
    """The defect made the unscoped token the MORE powerful one."""
    empty = _issue(client, agent, scope=[]).json()['token_id']
    scoped = _issue(client, agent, scope=['read_file']).json()['token_id']
    assert _validate(client, empty, agent, 'read_file').status_code == 403
    assert _validate(client, scoped, agent, 'read_file').status_code == 200


def test_a_scoped_action_still_validates(client, agent):
    tok = _issue(client, agent, scope=['read_file', 'write_file']).json()['token_id']
    assert _validate(client, tok, agent, 'write_file').status_code == 200


def test_an_explicit_wildcard_still_grants_everything(client, agent):
    """Unrestricted tokens remain possible — they just have to be asked for."""
    tok = _issue(client, agent, scope=['*']).json()['token_id']
    assert _validate(client, tok, agent, 'anything_at_all').status_code == 200


def test_validation_without_a_required_action_still_authenticates(client, agent):
    """Plain "is this token valid" must keep working for any scope."""
    tok = _issue(client, agent, scope=[]).json()['token_id']
    assert _validate(client, tok, agent).status_code == 200


def test_a_corrupt_scope_column_denies_rather_than_grants(client, agent):
    from backend.services.memory_db import get_conn

    tok = _issue(client, agent, scope=['read_file']).json()['token_id']
    con = get_conn()
    try:
        con.execute('UPDATE agent_jit_tokens SET scope=? WHERE token_id=?', ('not json', tok))
        con.commit()
    finally:
        con.close()
    assert _validate(client, tok, agent, 'read_file').status_code == 403


def test_a_non_numeric_ttl_is_a_400_not_a_500(client, agent):
    r = _issue(client, agent, ttl_seconds='abc')
    assert r.status_code == 400, 'a bad ttl took the endpoint out with a 500'


def test_a_non_numeric_max_uses_is_a_400(client, agent):
    assert _issue(client, agent, max_uses='lots').status_code == 400


def test_a_negative_ttl_cannot_mint_an_already_expired_token(client, agent):
    body = _issue(client, agent, ttl_seconds=-500).json()
    assert body['expires_in'] >= 1, 'issued a credential that was expired before it was returned'


def test_a_negative_max_uses_cannot_mint_an_unusable_token(client, agent):
    tok = _issue(client, agent, max_uses=-3, scope=['*']).json()['token_id']
    assert _validate(client, tok, agent, 'x').status_code == 200


def test_a_non_list_scope_is_rejected(client, agent):
    assert _issue(client, agent, scope='read_file').status_code == 400


def test_a_token_for_an_unprovisioned_agent_is_a_404(client):
    assert _issue(client, 't158_ghost', scope=['x']).status_code == 404


def test_expiry_and_revocation_still_deny(client, agent):
    tok = _issue(client, agent, scope=['*']).json()['token_id']
    client.post(f'/api/agent-identity/token/{tok}/revoke', json={'reason': 'test'})
    assert _validate(client, tok, agent, 'x').status_code == 403


# ── 3. the swarm judge must not invent a winner ───────────────────────────────
def _swarm(monkeypatch, judge_payload, agent_texts=('answer one is long', 'two')):
    import asyncio

    from backend.routers import swarm as sw

    calls = {'n': 0}

    async def fake(messages, **kw):
        calls['n'] += 1
        if calls['n'] <= len(agent_texts):
            return {'ok': True, 'text': agent_texts[calls['n'] - 1], 'tokens': 10}
        return {'ok': True, 'text': judge_payload, 'tokens': 5}

    monkeypatch.setattr('backend.services.llm.complete', fake)

    class Req:
        async def json(self):
            return {'prompt': 'x', 'agents': ['brain', 'builder'], 'strategy': 'judge'}

    r = asyncio.get_event_loop().run_until_complete(sw.swarm_run(Req()))
    return json.loads(bytes(r.body).decode()) if hasattr(r, 'body') else r


def test_a_hallucinated_winner_is_rejected(monkeypatch):
    body = _swarm(monkeypatch, json.dumps({'winner': 'ghost_agent', 'scores': {'ghost_agent': 0.99}}))
    assert body['winner'] != 'ghost_agent', 'the judge named an agent that never ran and was believed'
    assert body['winner'] in ('brain', 'builder')


def test_a_hallucinated_winner_does_not_produce_an_empty_result(monkeypatch):
    body = _swarm(monkeypatch, json.dumps({'winner': 'ghost_agent', 'scores': {'ghost_agent': 0.99}}))
    assert body['winner_output'], 'two real answers were discarded for a name the judge invented'


def test_a_hallucinated_winner_does_not_carry_a_confident_score(monkeypatch):
    body = _swarm(monkeypatch, json.dumps({'winner': 'ghost_agent', 'scores': {'ghost_agent': 0.99}}))
    assert body['winner_score'] is None
    assert body['improvement_vs_single'] == ''


def test_the_fallback_explains_itself(monkeypatch):
    body = _swarm(monkeypatch, json.dumps({'winner': 'ghost_agent'}))
    assert 'ghost_agent' in body['judge_reason']
    assert 'fell back' in body['judge_reason']


def test_a_valid_judge_verdict_is_honoured(monkeypatch):
    """Over-correcting would throw away every real verdict."""
    body = _swarm(monkeypatch, json.dumps({'winner': 'builder', 'scores': {'builder': 0.8}, 'reason': 'best'}))
    assert body['winner'] == 'builder'
    assert body['winner_score'] == 0.8
    assert body['judge_reason'] == 'best'


def test_a_judge_naming_nobody_falls_back_to_a_real_agent(monkeypatch):
    body = _swarm(monkeypatch, json.dumps({'scores': {}}))
    assert body['winner'] in ('brain', 'builder')
    assert body['winner_output']


def test_unparseable_judge_output_still_falls_back(monkeypatch):
    body = _swarm(monkeypatch, 'not json at all')
    assert body['winner'] in ('brain', 'builder')
    assert body['winner_output']


def test_fanout_never_names_a_failed_run_as_the_winner(monkeypatch):
    """`runs[0]` was the fallback, so a failed run could win and its error
    string became winner_output. Only a successful run may win; if none exists
    the endpoint's 503 is the correct answer.

    Added after revert-proof showed this fix had no test: breaking it changed no
    outcome, which means it was unverified rather than safe.
    """
    import asyncio

    from backend.routers import swarm as sw

    calls = {'n': 0}

    async def fake(messages, **kw):
        calls['n'] += 1
        if calls['n'] == 1:
            raise RuntimeError('first agent exploded')
        return {'ok': True, 'text': 'the only real answer', 'tokens': 10}

    monkeypatch.setattr('backend.services.llm.complete', fake)

    class Req:
        async def json(self):
            return {'prompt': 'x', 'agents': ['brain', 'builder'], 'strategy': 'fanout'}

    r = asyncio.get_event_loop().run_until_complete(sw.swarm_run(Req()))
    body = json.loads(bytes(r.body).decode()) if hasattr(r, 'body') else r
    assert body['ok'] is True
    assert body['winner'] == 'builder', 'a failed run was selected as the swarm winner'
    assert body['winner_output'] == 'the only real answer'
    assert 'exploded' not in (body['winner_output'] or '')


def test_fanout_with_every_agent_failing_is_a_503(monkeypatch):
    import asyncio

    from backend.routers import swarm as sw

    async def fake(messages, **kw):
        raise RuntimeError('all down')

    monkeypatch.setattr('backend.services.llm.complete', fake)

    class Req:
        async def json(self):
            return {'prompt': 'x', 'agents': ['brain', 'builder'], 'strategy': 'fanout'}

    r = asyncio.get_event_loop().run_until_complete(sw.swarm_run(Req()))
    assert getattr(r, 'status_code', 200) == 503


# ── 4. fusion must not pass a stub off as a model answer ──────────────────────
def test_route_reports_failure_when_no_provider_is_configured(client, monkeypatch):
    monkeypatch.delenv('OPENROUTER_API_KEY', raising=False)
    body = client.post('/api/fusion/route', json={'prompt': 'write a function'}).json()
    assert body['ok'] is False, 'a stub placeholder was reported as a successful model call'
    assert body['error'] is True
    assert body['stub'] is True


def test_route_does_not_return_the_placeholder_as_model_output(client, monkeypatch):
    monkeypatch.delenv('OPENROUTER_API_KEY', raising=False)
    body = client.post('/api/fusion/route', json={'prompt': 'hello'}).json()
    assert '[Stub:' not in (body.get('text') or ''), 'setup instructions were returned as the answer'
    assert body['text'] == ''
    assert 'No AI provider' in body['error_message']


def test_the_stub_is_marked_so_every_consumer_can_see_it(monkeypatch):
    """Fixed at the source: _call_model now emits the markers is_stub() reads."""
    import asyncio

    from backend.routers import fusion as fu
    from backend.services.llm import is_stub

    monkeypatch.delenv('OPENROUTER_API_KEY', raising=False)
    result = asyncio.get_event_loop().run_until_complete(fu._call_model('m', [{'role': 'user', 'content': 'x'}]))
    assert is_stub(result) is True
    assert result['error'] is True


def test_route_still_classifies_the_task(client, monkeypatch):
    monkeypatch.delenv('OPENROUTER_API_KEY', raising=False)
    body = client.post('/api/fusion/route', json={'prompt': 'write a function to sort'}).json()
    assert body['task_type'] == 'code'
    assert body['model']


def test_route_requires_a_prompt(client):
    assert client.post('/api/fusion/route', json={'prompt': ''}).status_code == 400


# ── 5. the a2a card fetch must refuse internal addresses ──────────────────────
@pytest.fixture
def a2a_cleanup():
    yield
    from backend.services.memory_db import get_conn

    con = get_conn()
    try:
        con.execute("DELETE FROM a2a_agents WHERE agent_id LIKE 't158%'")
        con.commit()
    finally:
        con.close()


@pytest.mark.parametrize(
    'url',
    [
        'http://169.254.169.254/latest/meta-data',
        'http://10.0.0.5/agent',
        'http://192.168.1.1/agent',
        'http://metadata.google.internal/computeMetadata/v1/',
    ],
)
def test_verify_refuses_internal_addresses(client, a2a_cleanup, url):
    client.post('/api/a2a/agents', json={'agent_id': 't158_ssrf', 'name': 'p', 'a2a_url': url})
    body = client.post('/api/a2a/agents/t158_ssrf/verify').json()
    assert body['ok'] is False
    assert body['blocked_urls'], f'{url} was fetched rather than refused'
    from backend.services.memory_db import get_conn

    con = get_conn()
    try:
        con.execute("DELETE FROM a2a_agents WHERE agent_id='t158_ssrf'")
        con.commit()
    finally:
        con.close()


def test_a_blocked_fetch_is_distinguishable_from_a_dead_host(client, a2a_cleanup):
    """Without this an operator cannot tell the guard fired from 'nobody home'."""
    client.post(
        '/api/a2a/agents',
        json={'agent_id': 't158_ssrf2', 'name': 'p', 'a2a_url': 'http://169.254.169.254/x'},
    )
    body = client.post('/api/a2a/agents/t158_ssrf2/verify').json()
    assert 'internal' in body['error'].lower()


def test_loopback_is_still_allowed(client, a2a_cleanup):
    """The platform registers its own agents on localhost; refusing loopback
    outright would break self-registration."""
    assert ident and True  # keep the import meaningful for linters
    from backend.routers.a2a import _is_loopback

    assert _is_loopback('http://localhost:8787/a2a/orchestrator') is True
    assert _is_loopback('http://127.0.0.1:8787/a2a/x') is True
    assert _is_loopback('http://169.254.169.254/x') is False
    assert _is_loopback('http://example.com/x') is False


def test_a_public_url_is_not_blocked(client, a2a_cleanup):
    """Over-blocking would make the whole A2A feature unusable."""
    from backend.services.safe_fetch import url_is_safe

    ok, _ = url_is_safe('https://example.com/.well-known/agent.json')
    assert ok is True
