"""Module 21 — OPERATE: cost recording and budget enforcement were 1-in-30.

THE FINDING
───────────
30 routers call `llm.complete()` and spend real money. Exactly ONE — chat.py —
recorded anything to the cost ledger, and the same one was the only caller of
`check_budget_before_spend()`.

Verified live before the fix: running a skill and an MCP tool left
`/api/finops/dashboard` at `total_events: 80`, unchanged.

So the FinOps dashboard, the per-goal spend breakdown, burn-rate projection and
every budget cap were reporting *chat traffic only* while presenting themselves
as platform-wide. A runaway supervisor, swarm, workflow or eval loop was both
invisible and unstoppable.

WHY THE FIX IS AT THE LLM LAYER
Recording at the call site is precisely the arrangement that produced a 1-in-30
hit rate, and it regresses the moment a 31st caller is added. `complete()`
already computed `cost` — it just discarded it.
"""

from __future__ import annotations

import asyncio
import sqlite3
import uuid
from unittest.mock import AsyncMock, patch

import pytest

import backend.services.llm as llm_svc
from backend.routers import finops


def _ledger_count() -> int:
    con = finops._get_conn()
    try:
        return con.execute('SELECT COUNT(*) FROM cost_ledger').fetchone()[0]
    finally:
        con.close()


def _last_row() -> sqlite3.Row:
    con = finops._get_conn()
    con.row_factory = sqlite3.Row
    try:
        return con.execute(
            'SELECT * FROM cost_ledger ORDER BY rowid DESC LIMIT 1'
        ).fetchone()
    finally:
        con.close()


PAID_RESULT = {
    'text': 'hello', 'tokens': 1500, 'prompt_tokens': 1000, 'completion_tokens': 500,
    'cost': 0.0234, 'model': 'anthropic/claude-3.5-sonnet', 'provider': 'openrouter',
    'latency_ms': 842, 'ok': True,
}


# The session-scoped `client` fixture in conftest.py patches
# `backend.services.llm.complete` with an AsyncMock for the whole run. Any test
# that has used `client` first therefore leaves the module attribute replaced,
# so calling llm_svc.complete() here would hit the mock and return conftest's
# canned dict (no 'ok' key) instead of exercising the wrapper. That is exactly
# what happened: these tests passed alone and failed in the full run with
# KeyError: 'ok'.
#
# Capturing the real function at import time -- the pattern test_59 already
# uses for the same reason -- makes them order-independent.
REAL_COMPLETE = llm_svc.complete


@pytest.fixture()
def paid_call():
    """Patch the real implementation so the wrapper's recording is exercised."""
    with patch.object(llm_svc, '_complete_impl', new=AsyncMock(return_value=dict(PAID_RESULT))):
        yield


# ══ Cost recording ════════════════════════════════════════════════════════════
def test_completion_is_recorded_in_the_cost_ledger(paid_call):
    before = _ledger_count()
    asyncio.run(REAL_COMPLETE([{'role': 'user', 'content': 'x'}], agent_id='cost_probe'))
    assert _ledger_count() == before + 1, 'an LLM call was not recorded'


def test_recorded_row_has_the_real_values(paid_call):
    agent = 'cost_' + uuid.uuid4().hex[:6]
    asyncio.run(REAL_COMPLETE([{'role': 'user', 'content': 'x'}], agent_id=agent))
    row = _last_row()
    assert row['agent_id'] == agent
    assert row['source_type'] == 'llm'
    assert abs(row['cost_usd'] - 0.0234) < 1e-9
    assert row['total_tokens'] == 1500
    assert row['tokens_in'] == 1000 and row['tokens_out'] == 500


def test_model_lands_in_the_model_column(paid_call):
    """I first passed the model as source_id, leaving the model column empty —
    per-model cost breakdowns would have been blank. Caught by reading back the
    row I had just written instead of trusting the insert."""
    asyncio.run(REAL_COMPLETE([{'role': 'user', 'content': 'x'}], agent_id='model_probe'))
    row = _last_row()
    assert row['model'] == 'anthropic/claude-3.5-sonnet'
    assert row['latency_ms'] == 842


def test_free_or_stubbed_calls_are_not_recorded():
    """A stub response costs nothing; recording zeroes would inflate event
    counts and make the dashboard lie in the other direction."""
    free = {'text': '', 'tokens': 0, 'cost': 0.0, 'model': '', 'ok': False}
    with patch.object(llm_svc, '_complete_impl', new=AsyncMock(return_value=free)):
        before = _ledger_count()
        asyncio.run(REAL_COMPLETE([{'role': 'user', 'content': 'x'}], agent_id='free_probe'))
        assert _ledger_count() == before


def test_ledger_failure_does_not_break_the_completion(paid_call, monkeypatch):
    """A ledger outage must be loud in the logs but must not fail the user's
    request — the same rule applied to the audit chain in Module 17."""
    def boom(**kwargs):
        raise RuntimeError('ledger down')

    monkeypatch.setattr(finops, 'record_cost', boom)
    r = asyncio.run(REAL_COMPLETE([{'role': 'user', 'content': 'x'}], agent_id='resilient'))
    assert r['ok'] is True and r['text'] == 'hello'


def test_recording_lives_at_the_llm_layer_not_the_call_sites():
    """The structural guarantee. 29 of 30 routers never recorded; requiring
    each one to remember is what caused that."""
    import inspect

    src = inspect.getsource(REAL_COMPLETE)  # not llm_svc.complete — see REAL_COMPLETE
    assert '_record_llm_cost' in src
    assert '_complete_impl' in src, 'complete() must delegate so every return path is covered'


def test_recording_is_not_duplicated_inside_the_implementation():
    """Wrapping is what makes ONE recording site cover every return path.

    My first version asserted `_complete_impl` contained >=5 `ok: True`
    returns. It contains one -- the Ollama fallbacks live in
    `_ollama_complete`, which `_complete_impl` returns through. That assertion
    described my mental model of the file rather than any behaviour, so it is
    replaced with the property that actually matters: the implementation must
    not record anything itself, or the wrapper would double-count.
    """
    import inspect

    impl = inspect.getsource(llm_svc._complete_impl)
    assert 'record_cost' not in impl, 'recording leaked back into the implementation'
    assert '_record_llm_cost' not in impl

    ollama = inspect.getsource(llm_svc._ollama_complete)
    assert 'record_cost' not in ollama, 'the Ollama path records separately - double counting'


def test_ollama_path_is_also_recorded():
    """Every provider goes through the wrapper, not just OpenRouter."""
    ollama_result = {
        'text': 'hi', 'tokens': 200, 'cost': 0.0, 'model': 'llama3.1:8b',
        'provider': 'ollama', 'ok': True,
    }
    with patch.object(llm_svc, '_complete_impl', new=AsyncMock(return_value=ollama_result)):
        before = _ledger_count()
        asyncio.run(REAL_COMPLETE([{'role': 'user', 'content': 'x'}], agent_id='ollama_probe'))
        # Local models are free, so cost is 0 -- but the TOKENS are real usage
        # and must still be attributed, or local-model activity looks like
        # nothing happened at all.
        assert _ledger_count() == before + 1, 'a local-model call was not recorded'
        assert _last_row()['total_tokens'] == 200


# ══ Budget enforcement ════════════════════════════════════════════════════════
@pytest.fixture()
def hard_cap():
    """A kill-scoped cap on a unique agent, cleaned up afterwards."""
    agent = 'budget_' + uuid.uuid4().hex[:6]
    cap_id = 'cap_' + uuid.uuid4().hex[:8]
    con = finops._get_conn()
    try:
        con.execute(
            'INSERT INTO budget_caps(cap_id,name,scope_type,scope_id,period,'
            'limit_usd,on_breach,enabled) VALUES (?,?,?,?,?,?,?,1)',
            (cap_id, 'Test hard cap', 'agent', agent, 'hour', 0.001, 'kill'),
        )
        con.commit()
    finally:
        con.close()
    yield agent
    con = finops._get_conn()
    try:
        con.execute('DELETE FROM budget_caps WHERE cap_id=?', (cap_id,))
        con.commit()
    finally:
        con.close()


def test_breached_hard_cap_blocks_the_call(paid_call, hard_cap):
    first = asyncio.run(REAL_COMPLETE([{'role': 'user', 'content': 'x'}], agent_id=hard_cap))
    assert first['ok'] is True, 'the first call, under the cap, should succeed'

    second = asyncio.run(REAL_COMPLETE([{'role': 'user', 'content': 'x'}], agent_id=hard_cap))
    assert second['ok'] is False, 'a breached kill cap did not stop the call'
    assert second['code'] == 'budget_exceeded'
    assert 'Test hard cap' in second['error']


def test_a_breached_cap_only_affects_its_own_agent(paid_call, hard_cap):
    """One agent hitting its cap must not take the platform down."""
    asyncio.run(REAL_COMPLETE([{'role': 'user', 'content': 'x'}], agent_id=hard_cap))
    asyncio.run(REAL_COMPLETE([{'role': 'user', 'content': 'x'}], agent_id=hard_cap))

    other = asyncio.run(REAL_COMPLETE([{'role': 'user', 'content': 'x'}], agent_id='bystander'))
    assert other['ok'] is True, 'one agent\'s cap blocked an unrelated agent'


def test_blocked_call_costs_nothing(paid_call, hard_cap):
    asyncio.run(REAL_COMPLETE([{'role': 'user', 'content': 'x'}], agent_id=hard_cap))
    before = _ledger_count()
    blocked = asyncio.run(REAL_COMPLETE([{'role': 'user', 'content': 'x'}], agent_id=hard_cap))
    assert blocked['ok'] is False
    assert _ledger_count() == before, 'a blocked call still wrote to the ledger'


def test_budget_check_fails_open(paid_call, monkeypatch):
    """A guardrail that hard-blocks every AI call when the database hiccups is
    worse than the overspend it prevents."""
    def boom(**kwargs):
        raise RuntimeError('db down')

    monkeypatch.setattr(finops, 'check_budget_before_spend', boom)
    r = asyncio.run(REAL_COMPLETE([{'role': 'user', 'content': 'x'}], agent_id='failopen'))
    assert r['ok'] is True, 'a budget-check failure blocked the call instead of failing open'


def test_alert_only_caps_do_not_block(paid_call):
    """Existing installs configured caps when they had no teeth; 'alert' must
    keep its notify-only behaviour."""
    agent = 'alertonly_' + uuid.uuid4().hex[:6]
    cap_id = 'cap_' + uuid.uuid4().hex[:8]
    con = finops._get_conn()
    try:
        con.execute(
            'INSERT INTO budget_caps(cap_id,name,scope_type,scope_id,period,'
            'limit_usd,on_breach,enabled) VALUES (?,?,?,?,?,?,?,1)',
            (cap_id, 'Alert only', 'agent', agent, 'hour', 0.0001, 'alert'),
        )
        con.commit()
    finally:
        con.close()
    try:
        for _ in range(3):
            r = asyncio.run(REAL_COMPLETE([{'role': 'user', 'content': 'x'}], agent_id=agent))
            assert r['ok'] is True, 'an alert-only cap blocked a call'
    finally:
        con = finops._get_conn()
        try:
            con.execute('DELETE FROM budget_caps WHERE cap_id=?', (cap_id,))
            con.commit()
        finally:
            con.close()


# ══ Test residue that became load-bearing ═════════════════════════════════════
def test_no_wildcard_enforcing_caps_leak_from_tests():
    """Wildcard 'pause'/'kill' caps left behind by a test now block every LLM
    call in the session.

    test_28 created three wildcard caps at $0.01 and never deleted them. That
    was harmless while nothing read on_breach; once enforcement was wired up it
    broke test_59's provider-contract tests, which had nothing to do with
    budgets. 58 copies of that residue were also sitting in the production
    database from past runs — a real latent hazard, not just a test problem.
    """
    con = finops._get_conn()
    try:
        rows = con.execute(
            "SELECT cap_id, name FROM budget_caps WHERE enabled=1 AND scope_id='*' "
            "AND on_breach IN ('pause','kill') AND name LIKE 'Unit %'"
        ).fetchall()
    finally:
        con.close()
    assert not rows, f'test-created wildcard enforcing caps were left behind: {rows}'


# ══ The dashboard now reflects reality ════════════════════════════════════════
def test_dashboard_sees_non_chat_spend(client):
    """The user-visible consequence: spend from a non-chat path shows up.

    NOTE: the session `client` fixture patches `backend.services.llm.complete`
    with an AsyncMock, so calling that patched name here would bypass the very
    wrapper under test -- my first version did exactly that and failed for the
    wrong reason. Recording directly is the honest equivalent: it asserts the
    DASHBOARD reflects ledger writes, which is the user-visible half. The
    wrapper itself is covered by the tests above, which patch `_complete_impl`
    and go through the real `complete()`.
    """
    before = client.get('/api/finops/dashboard').json()['total_events']
    finops.record_cost(
        agent_id='dash_probe', source_type='llm', cost_usd=0.01,
        tokens=100, model='test-model',
    )
    after = client.get('/api/finops/dashboard').json()
    assert after['total_events'] == before + 1
    assert any(r['source_type'] == 'llm' for r in after['by_source_type'])
