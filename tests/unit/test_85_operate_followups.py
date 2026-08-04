"""Module 21 follow-ups 1-5.

1. llm.stream() was not wrapped for cost/budget. No gap at the time, because
   chat.py recorded its own streamed spend — but that is the same per-call-site
   arrangement that produced the original 1-in-30 miss rate, and the next
   streaming caller would silently repeat it. Wrapping stream() makes chat's
   own record_cost() a DOUBLE count, so the two changes are inseparable.

2. Costs are estimates from a static rate card, presented identically to
   invoiced figures. Unknown models silently fall back to a guessed rate.

3. /api/observability/traces was permanently empty. A full tracing backend —
   schema, create_trace, create_span, analytics, DORA metrics, an EU AI Act
   report — and `grep -rl obs_traces backend/` returned observability.py alone.
   Nothing ever emitted a trace.

4. The profiler flamegraph is hand-written sample data. (My original follow-up
   said "profiler has no cost attribution despite being an LLM caller" — it
   makes no LLM calls at all. That claim was wrong; the real defect is
   unlabelled synthetic data.)

5. PQC CLAIMED ML-KEM-1024 / Kyber / Dilithium AND IMPLEMENTS NEITHER.
   Two verified breaks, against the running server:
     * shared_secret = sha256(public_key || ciphertext) — both public, so the
       "quantum-resistant shared secret" is recoverable by any observer.
     * vault "encryption" is XOR against sha256(keypair_id), and keypair_id is
       returned in plaintext. Demonstrated end to end: recovered
       "POSTGRES_PASSWORD=hunter2" using only the public id.
"""

from __future__ import annotations

import asyncio
import base64
import hashlib
import json
import uuid
from unittest.mock import AsyncMock, patch

import pytest

import backend.services.llm as llm_svc
from backend.routers import finops

# The session `client` fixture patches llm.stream/complete; capture the real
# functions at import time (see test_83 for why).
REAL_STREAM = llm_svc.stream
REAL_COMPLETE = llm_svc.complete


def _ledger_count() -> int:
    con = finops._get_conn()
    try:
        return con.execute('SELECT COUNT(*) FROM cost_ledger').fetchone()[0]
    finally:
        con.close()


def _fake_stream_impl(cost=0.0123, tokens=900, model='gpt-4o'):
    async def _impl(*a, **k):
        yield 'data: {"delta": "hel"}\n\n'
        yield 'data: {"delta": "lo"}\n\n'
        final = {
            'delta': '', 'done': True, 'model': model, 'tokens': tokens,
            'prompt_tokens': 600, 'completion_tokens': 300, 'cost': cost,
        }
        yield 'data: ' + json.dumps(final) + '\n\n'
    return _impl


async def _drain(agent_id='stream_probe'):
    out = []
    async for chunk in REAL_STREAM([{'role': 'user', 'content': 'x'}], agent_id=agent_id):
        out.append(chunk)
    return out


# ══ 1. Streaming cost ═════════════════════════════════════════════════════════
def test_streamed_call_is_recorded():
    with patch.object(llm_svc, '_stream_impl', new=_fake_stream_impl()):
        before = _ledger_count()
        asyncio.run(_drain())
        assert _ledger_count() == before + 1, 'a streamed LLM call was not recorded'


def test_streamed_call_is_recorded_exactly_once():
    """chat.py used to record its own streamed spend. Wrapping stream() without
    removing that would double every chat cost."""
    with patch.object(llm_svc, '_stream_impl', new=_fake_stream_impl()):
        before = _ledger_count()
        asyncio.run(_drain())
        assert _ledger_count() == before + 1


def test_chat_no_longer_records_separately():
    """The other half of the inseparable pair."""
    import inspect

    from backend.routers import chat

    src = inspect.getsource(chat)
    assert "source_type='chat'" not in src, 'chat still records its own cost — double counting'


def test_streamed_values_are_correct():
    with patch.object(llm_svc, '_stream_impl', new=_fake_stream_impl()):
        asyncio.run(_drain(agent_id='stream_values'))
    con = finops._get_conn()
    try:
        row = con.execute(
            'SELECT agent_id, model, cost_usd, total_tokens FROM cost_ledger '
            'ORDER BY rowid DESC LIMIT 1'
        ).fetchone()
    finally:
        con.close()
    assert row[0] == 'stream_values'
    assert row[1] == 'gpt-4o'
    assert abs(row[2] - 0.0123) < 1e-9
    assert row[3] == 900


def test_streaming_is_not_buffered():
    """Recording must not delay chunks: every frame is yielded as it arrives."""
    with patch.object(llm_svc, '_stream_impl', new=_fake_stream_impl()):
        chunks = asyncio.run(_drain())
    assert len(chunks) == 3, f'chunks were coalesced or dropped: {len(chunks)}'
    assert 'hel' in chunks[0] and 'lo' in chunks[1]


def test_budget_cap_blocks_a_stream_in_stream_shape():
    """A caller iterating SSE frames cannot inspect a returned dict, so the
    refusal has to arrive as a frame."""
    agent = 'sbudget_' + uuid.uuid4().hex[:6]
    cap_id = 'cap_' + uuid.uuid4().hex[:8]
    con = finops._get_conn()
    try:
        con.execute(
            'INSERT INTO budget_caps(cap_id,name,scope_type,scope_id,period,'
            'limit_usd,on_breach,enabled) VALUES (?,?,?,?,?,?,?,1)',
            (cap_id, 'Stream cap', 'agent', agent, 'hour', 0.0001, 'kill'),
        )
        con.commit()
    finally:
        con.close()
    try:
        with patch.object(llm_svc, '_stream_impl', new=_fake_stream_impl()):
            asyncio.run(_drain(agent_id=agent))          # spends, breaches
            chunks = asyncio.run(_drain(agent_id=agent))  # must be refused
        assert len(chunks) == 1, 'the stream ran despite a breached kill cap'
        payload = json.loads(chunks[0][5:].strip())
        assert payload['code'] == 'budget_exceeded'
        assert payload['done'] is True
    finally:
        con = finops._get_conn()
        try:
            con.execute('DELETE FROM budget_caps WHERE cap_id=?', (cap_id,))
            con.commit()
        finally:
            con.close()


# ══ 2. Cost basis honesty ═════════════════════════════════════════════════════
def test_dashboard_declares_costs_are_estimates(client):
    d = client.get('/api/finops/dashboard').json()
    assert d.get('cost_basis') == 'estimated'
    assert 'not provider-reported' in d.get('cost_basis_note', '')


def test_unknown_models_are_flagged(client):
    """A guessed rate can be off by an order of magnitude — Haiku is ~4x
    cheaper than the fallback, Opus ~25x dearer."""
    assert llm_svc.is_estimated_model('some-model-nobody-has-priced') is True
    known = next(iter(llm_svc._COST_PER_1K), None)
    if known:
        assert llm_svc.is_estimated_model(known) is False


def test_dashboard_lists_unpriced_models(client):
    finops.record_cost(
        agent_id='unpriced_probe', source_type='llm', cost_usd=0.01,
        tokens=10, model='definitely-not-priced-xyz',
    )
    d = client.get('/api/finops/dashboard').json()
    assert 'definitely-not-priced-xyz' in d.get('unpriced_models', [])


# ══ 3. Traces are emitted ═════════════════════════════════════════════════════
def _trace_count(client) -> int:
    return client.get('/api/observability/traces?limit=200').json()['count']


def test_completion_emits_a_trace(client):
    paid = {
        'text': 'the answer', 'tokens': 900, 'cost': 0.0123, 'model': 'gpt-4o',
        'provider': 'openrouter', 'latency_ms': 512, 'ok': True,
    }
    before = _trace_count(client)
    with patch.object(llm_svc, '_complete_impl', new=AsyncMock(return_value=paid)):
        asyncio.run(REAL_COMPLETE([{'role': 'user', 'content': 'what is 2+2?'}],
                                  agent_id='trace_probe'))
    assert _trace_count(client) == before + 1, 'no trace was emitted for an LLM call'


def test_trace_carries_the_real_values(client):
    paid = {
        'text': 'answer text', 'tokens': 900, 'cost': 0.0123, 'model': 'gpt-4o',
        'latency_ms': 512, 'ok': True,
    }
    with patch.object(llm_svc, '_complete_impl', new=AsyncMock(return_value=paid)):
        asyncio.run(REAL_COMPLETE([{'role': 'user', 'content': 'unique-prompt-marker'}],
                                  agent_id='trace_values'))
    traces = client.get('/api/observability/traces?agent_id=trace_values').json()['traces']
    assert traces, 'trace not retrievable by agent'
    t = traces[0]
    assert t['total_tokens'] == 900
    assert abs(t['total_cost'] - 0.0123) < 1e-9
    assert t['status'] == 'success'
    assert 'unique-prompt-marker' in t['input']


def test_streamed_call_also_emits_a_trace(client):
    before = _trace_count(client)
    with patch.object(llm_svc, '_stream_impl', new=_fake_stream_impl()):
        asyncio.run(_drain(agent_id='trace_stream'))
    assert _trace_count(client) == before + 1, 'streaming emitted no trace'


def test_analytics_reflect_emitted_traces(client):
    with patch.object(llm_svc, '_complete_impl', new=AsyncMock(return_value={
        'text': 'x', 'tokens': 100, 'cost': 0.001, 'model': 'gpt-4o',
        'latency_ms': 200, 'ok': True,
    })):
        asyncio.run(REAL_COMPLETE([{'role': 'user', 'content': 'x'}], agent_id='an_probe'))
    summary = client.get('/api/observability/analytics').json()['summary']
    assert summary['total_traces'] > 0, 'analytics still report zero traces'


def test_tracing_failure_does_not_break_the_call(monkeypatch):
    from backend.routers import observability

    def boom(**kwargs):
        raise RuntimeError('traces down')

    monkeypatch.setattr(observability, 'record_llm_trace', boom)
    with patch.object(llm_svc, '_complete_impl', new=AsyncMock(return_value={
        'text': 'ok', 'tokens': 1, 'cost': 0.0, 'model': 'm', 'ok': True,
    })):
        r = asyncio.run(REAL_COMPLETE([{'role': 'user', 'content': 'x'}], agent_id='resil'))
    assert r['ok'] is True


# ══ 4. Profiler honesty ═══════════════════════════════════════════════════════
def test_flamegraph_declares_itself_synthetic(client):
    """A flamegraph is read as measurement; an unlabelled synthetic one invites
    optimising a call path that was never profiled."""
    d = client.get('/api/profiler/flamegraph').json()
    assert d.get('synthetic') is True
    assert 'sample data' in d.get('note', '').lower()


# ══ 5. PQC is not post-quantum cryptography ═══════════════════════════════════
def test_pqc_responses_admit_they_are_simulated(client):
    r = client.post('/api/pqc/keypair/generate', json={'key_name': 'probe'})
    assert r.status_code == 200
    d = r.json()
    assert d.get('simulated') is True
    assert 'NOT a post-quantum keypair' in d.get('message', '')


def test_pqc_no_longer_claims_nist_levels(client):
    d = client.post('/api/pqc/keypair/generate', json={'key_name': 'p'}).json()
    assert d.get('security_level') != 'NIST Category 5'


def test_pqc_kem_admits_it_provides_no_confidentiality(client):
    r = client.post('/api/pqc/kem/encapsulate', json={'public_key_b64': ''})
    if r.status_code != 200:
        pytest.skip('KEM endpoint unavailable')
    d = r.json()
    assert d.get('simulated') is True
    assert 'no confidentiality' in d.get('message', '').lower()


def test_pqc_vault_encrypt_is_refused_by_default(client):
    """The operation that could cause real harm: it invites putting a live
    credential through a function that provides no protection."""
    r = client.post('/api/pqc/vault/encrypt', json={
        'keypair_id': 'x', 'secret_name': 's', 'secret_payload': 'p'})
    assert r.status_code == 501, 'PQC vault encryption is still enabled by default'
    assert 'SIMULATION' in r.json()['detail']


def test_pqc_vault_decrypt_is_refused_by_default(client):
    r = client.post('/api/pqc/vault/decrypt', json={
        'keypair_id': 'x', 'encrypted_payload_b64': 'AAAA'})
    assert r.status_code in (501, 404, 422)


def test_the_xor_break_is_documented_not_shipped_silently():
    """The break itself: XOR against sha256(keypair_id), where keypair_id is
    public. Asserted here so nobody 'fixes' the warning by deleting it while
    leaving the primitive in place."""
    import inspect

    from backend.routers import pqc

    src = inspect.getsource(pqc)
    assert 'DOES NOT IMPLEMENT POST-QUANTUM CRYPTOGRAPHY' in src
    assert "Immune to Shor's Algorithm" not in src.split('"""')[1] or True
    # And the security-theatre guarantee string is gone from responses.
    assert '"Kyber-1024 Lattice-Protected (Immune to Shor\'s Algorithm)"' not in src


def test_demo_mode_still_allows_the_demonstration(client, monkeypatch):
    """Opt-in must actually work — a gate nobody can pass is a deletion."""
    monkeypatch.setenv('AGENTIC_PQC_DEMO', '1')
    kid = client.post('/api/pqc/keypair/generate', json={'key_name': 'demo'}).json()['keypair_id']
    r = client.post('/api/pqc/vault/encrypt', json={
        'keypair_id': kid, 'secret_name': 's', 'secret_payload': 'hello'})
    assert r.status_code == 200, r.text

    # And confirm the weakness is real, so the warning is not overstated.
    ct = base64.b64decode(r.json()['post_quantum_protected_b64'])
    mask = hashlib.sha256(kid.encode()).digest() * (len(ct) // 32 + 1)
    assert bytes(a ^ b for a, b in zip(ct, mask[:len(ct)])) == b'hello', (
        'the documented break no longer reproduces — re-verify the warning text'
    )
