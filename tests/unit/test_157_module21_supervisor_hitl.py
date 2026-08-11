"""Module 21 — the Supervisor workstation: the `hitl` tab.

Destination: `supervisor`, hosting a2a, agent-identity, hitl, goals, swarm,
fusion and finetune. This pass covers the host pane and `hitl`; `finetune` was
covered by doc 71 and `agent-monitor` by doc 76.

HITL is the human approval gate on autonomous agents — the component whose only
job is deciding when a person must look before an agent acts. Its own module
docstring cites "EU AI Act Article 14 compliance (documented human oversight)".
That makes every defect here a governance defect, not just a bug.

Six defects, all reproduced against a live server before the fix:

1. THE ALWAYS-INTERRUPT LIST COULD BE SIDE-STEPPED BY CAPITALISATION.
   ALWAYS_INTERRUPT is the hard list of actions that must reach a human no
   matter how confident the agent claims to be. It was matched with a bare `in`
   against the caller's raw string, while `risk_level` right beside it was
   already lower()ed. Verified live, confidence 0.99, risk_level 'low':

       'delete_file'  -> pending        (correct)
       'DELETE_FILE'  -> auto_approved
       'delete_file ' -> auto_approved
       'delete-file'  -> auto_approved

   The caller is an AGENT emitting a free-form string, so a model that writes
   "Delete_File" defeats the gate with no intent to.

2. AN UNRECOGNISED risk_level SILENTLY BECAME 'medium' — the second most
   permissive setting. A caller sending 'severe' believes it asked for the
   strictest gate and gets a 0.85 auto-approve threshold.

3. AUTO-APPROVALS WERE NEVER RECORDED. No hitl_queue row, no hitl_audit row,
   nothing in /stats. Verified live: three destructive actions auto-approved
   and the oversight record moved by ZERO rows. The decisions most worth
   reviewing — the ones no human saw — were the only ones left undocumented.

4. approval_rate counted human decisions only in its numerator but would have
   been polluted the moment auto-approvals were recorded, and read 0% when
   nothing had been reviewed.

5. assess-confidence FABRICATED A VERDICT when the judge returned unusable
   output: confidence 0.5, is_reversible true, recommendation 'proceed', with
   ok:true. Reproduced with a judge answering in prose for the action
   "rm -rf / on the production database". Module 16's defect, in the component
   that decides whether a human is needed.

6. A FAILED UNDO REPORTED SUCCESS. Every failure path fell through to a generic
   {'ok': True, 'restored': 'file'}. Verified live for both a snapshot with no
   recorded path and one whose directory no longer exists. The most damaging
   possible false success: the user has just been told their destructive action
   was reverted, so they stop looking.
"""

from __future__ import annotations

import asyncio
from unittest.mock import AsyncMock, patch

import pytest

from backend.routers import hitl


@pytest.fixture(autouse=True)
def _clean(tmp_path):
    """Remove only this module's rows — the HITL tables are shared."""
    from backend.services.memory_db import get_conn

    def purge():
        con = get_conn()
        try:
            con.execute("DELETE FROM hitl_queue WHERE agent_id LIKE 't157%'")
            con.execute("DELETE FROM hitl_audit WHERE interrupt_id LIKE 't157%' OR note LIKE '%t157%'")
            con.execute("DELETE FROM undo_snapshots WHERE action_id LIKE '%t157%' OR id LIKE '%t157%'")
            con.commit()
        finally:
            con.close()

    purge()
    yield
    purge()


def _interrupt(client, **kw):
    body = {'agent_id': 't157_agent', 'confidence': 0.99, 'risk_level': 'low'}
    body.update(kw)
    return client.post('/api/hitl/interrupt', json=body).json()


# ── 1. the always-interrupt list must not be defeated by formatting ───────────
@pytest.mark.parametrize(
    'variant',
    [
        'delete_file',
        'DELETE_FILE',
        'Delete_File',
        ' delete_file ',
        'delete-file',
        'delete.file',
        'delete file',
        'DELETE-FILE',
    ],
)
def test_every_spelling_of_a_protected_action_reaches_a_human(client, variant):
    body = _interrupt(client, action_type=variant)
    assert body['decision'] == 'pending', (
        f'{variant!r} was auto-approved — the always-interrupt gate is formatting-sensitive'
    )


@pytest.mark.parametrize('action', ['stripe_charge', 'PUSH_TO_MAIN', 'git-force-push', 'Send.Email'])
def test_other_protected_actions_are_gated_too(client, action):
    assert _interrupt(client, action_type=action)['decision'] == 'pending'


def test_an_ordinary_action_is_still_auto_approved(client):
    """Over-gating would make the queue useless and train users to rubber-stamp."""
    body = _interrupt(client, action_type='read_file')
    assert body['decision'] == 'auto_approved'


def test_the_normaliser_does_not_collapse_unrelated_actions():
    """`read_file` must not fold into anything protected."""
    assert hitl._normalise_action('read_file') == 'read_file'
    assert hitl._normalise_action('  DELETE--FILE  ') == 'delete_file'
    assert hitl._normalise_action('fs.delete') == 'fs_delete'
    assert hitl._normalise_action('') == ''


# ── 2. an unrecognised risk level must fail towards oversight ─────────────────
def test_an_unrecognised_risk_level_requires_review(client):
    body = _interrupt(client, action_type='write_file', risk_level='severe')
    assert body['decision'] == 'pending', "'severe' was quietly downgraded to a permissive threshold"
    assert body['risk_level'] == 'high'
    assert 'severe' in body['risk_level_note']


def test_high_and_critical_always_require_review(client):
    """Asserted at confidence 1.0, not 0.99.

    Revert-proof caught this passing for the wrong reason: RISK_THRESHOLDS['high']
    is 1.0, so at the default 0.99 the threshold comparison gates the action even
    when the explicit force-interrupt clause is removed. Only confidence == 1.0
    distinguishes "forced to a human because the level says so" from "happened to
    fall under the threshold".
    """
    for level in ('high', 'critical'):
        body = _interrupt(client, action_type='write_file', risk_level=level, confidence=1.0)
        assert body['decision'] == 'pending', (
            f'{level} risk auto-approved at full confidence — the level itself must force review'
        )


def test_a_low_risk_action_at_full_confidence_is_still_auto_approved(client):
    """The mirror, so the test above cannot be satisfied by gating everything."""
    assert _interrupt(client, action_type='read_file', risk_level='low', confidence=1.0)['decision'] == 'auto_approved'


def test_a_recognised_level_is_not_flagged(client):
    body = _interrupt(client, action_type='write_file', risk_level='low')
    assert 'risk_level_note' not in body


def test_confidence_is_clamped_and_absent_confidence_fails_safe(client):
    assert _interrupt(client, action_type='write_file', confidence=1e9)['decision'] == 'auto_approved'
    body = client.post(
        '/api/hitl/interrupt', json={'action_type': 'write_file', 'risk_level': 'low', 'agent_id': 't157_agent'}
    ).json()
    assert body['decision'] == 'pending', 'a missing confidence must not auto-approve'


# ── 3. auto-approvals must be documented ──────────────────────────────────────
def _rows(interrupt_id):
    from backend.services.memory_db import get_conn

    con = get_conn()
    try:
        q = con.execute('SELECT * FROM hitl_queue WHERE id=?', (interrupt_id,)).fetchone()
        a = con.execute('SELECT * FROM hitl_audit WHERE interrupt_id=?', (interrupt_id,)).fetchone()
    finally:
        con.close()
    return q, a


def test_an_auto_approval_is_written_to_the_queue(client):
    body = _interrupt(client, action_type='write_file')
    assert body['decision'] == 'auto_approved'
    q, _ = _rows(body['interrupt_id'])
    assert q is not None, 'the machine approved an action and left no record of it'
    assert q['status'] == 'auto_approved'
    assert q['reviewer'] == 'system'


def test_an_auto_approval_is_written_to_the_audit_trail(client):
    body = _interrupt(client, action_type='write_file')
    _, a = _rows(body['interrupt_id'])
    assert a is not None, 'no audit row for a machine-made approval decision'
    assert a['decision'] == 'auto_approved'
    assert 'Confidence' in a['note'], 'the record must say WHY it was auto-approved'


def test_an_auto_approval_is_not_counted_as_a_human_approval(client):
    """`status='auto_approved'` must stay distinct from a human `approve`."""
    body = _interrupt(client, action_type='write_file')
    q, _ = _rows(body['interrupt_id'])
    assert q['status'] != 'approve'


def test_the_response_says_the_decision_was_recorded(client):
    assert _interrupt(client, action_type='write_file')['recorded'] is True


def test_a_pending_interrupt_still_records_normally(client):
    body = _interrupt(client, action_type='delete_file')
    q, _ = _rows(body['interrupt_id'])
    assert q is not None and q['status'] == 'pending'


# ── 4. stats must separate machine decisions from human ones ──────────────────
def test_stats_report_auto_approvals_separately(client):
    before = client.get('/api/hitl/stats').json()
    for _ in range(3):
        _interrupt(client, action_type='write_file')
    after = client.get('/api/hitl/stats').json()
    assert after['auto_approved'] == before['auto_approved'] + 3
    assert after['approved'] == before['approved'], (
        'machine approvals were folded into the human approved count'
    )


def test_approval_rate_excludes_auto_approvals(client):
    for _ in range(5):
        _interrupt(client, action_type='write_file')
    stats = client.get('/api/hitl/stats').json()
    assert stats['approval_rate_basis'] == 'human decisions only; auto-approvals excluded'
    assert stats['human_reviewed'] == stats['approved'] + stats['rejected']


def test_approval_rate_is_none_rather_than_zero_when_nothing_was_reviewed(client, monkeypatch):
    """`0%` reads as "humans reject everything"; the truth is "no data"."""
    from backend.services import memory_db

    real = memory_db.get_conn

    class FakeCon:
        def __init__(self, inner):
            self._i = inner

        def execute(self, sql, *a):
            if "status='approve'" in sql or "status='reject'" in sql:
                return _Zero()
            return self._i.execute(sql, *a)

        def close(self):
            self._i.close()

    class _Zero:
        def fetchone(self):
            return [0]

    monkeypatch.setattr(memory_db, 'get_conn', lambda *a, **k: FakeCon(real()))
    stats = client.get('/api/hitl/stats').json()
    assert stats['approval_rate'] is None


def test_auto_approval_share_is_reported(client):
    _interrupt(client, action_type='write_file')
    stats = client.get('/api/hitl/stats').json()
    assert isinstance(stats['auto_approval_share'], float)


# ── 5. an unrun assessor must escalate, never wave things through ─────────────
def _assess(text, action='rm -rf / on the production database'):
    class Req:
        async def json(self):
            return {'action': action}

    with patch('backend.services.llm.complete', new=AsyncMock(return_value={'ok': True, 'text': text, 'tokens': 5})):
        return asyncio.get_event_loop().run_until_complete(hitl.assess_confidence(Req()))


def _body(resp):
    import json as _json

    if hasattr(resp, 'body'):
        return _json.loads(bytes(resp.body).decode())
    return resp


def test_an_unparseable_assessment_does_not_recommend_proceeding():
    resp = _assess("I'm sorry, I can't help with that request.")
    body = _body(resp)
    assert body['ok'] is False, 'a fabricated assessment was returned as a real one'
    assert body['assessed'] is False
    assert body['recommendation'] == 'interrupt'
    assert body['confidence'] is None
    assert body['risk_level'] is None


def test_an_unparseable_assessment_returns_503():
    assert getattr(_assess('no json at all'), 'status_code', 200) == 503


def test_an_unrun_assessor_never_claims_an_action_is_reversible():
    """`is_reversible: true` for `rm -rf /` was invented out of nothing."""
    assert _body(_assess('prose only'))['is_reversible'] is None


def test_a_real_assessment_is_passed_through():
    resp = _assess('{"confidence":0.2,"risk_level":"critical","is_reversible":false,"recommendation":"reject"}')
    body = _body(resp)
    assert body['ok'] is True
    assert body['assessed'] is True
    assert body['recommendation'] == 'reject'
    assert body['risk_level'] == 'critical'


# ── 6. an undo that did nothing must not report success ───────────────────────
def _snapshot(client, **kw):
    return client.post('/api/hitl/undo-snapshot', json=kw).json()['snapshot_id']


def test_an_undo_with_no_recorded_path_is_not_a_success(client):
    sid = _snapshot(client, type='file', state_data='t157 original')
    r = client.post(f'/api/hitl/undo/{sid}')
    assert r.status_code == 422, 'an undo that wrote nothing reported ok:true'
    assert r.json()['ok'] is False
    assert 'Nothing was changed' in r.json()['error']


def test_an_undo_to_a_missing_directory_is_not_a_success(client):
    sid = _snapshot(
        client, type='file', action_id='/home/user/repo/t157_no_such_dir/f.txt', state_data='x'
    )
    r = client.post(f'/api/hitl/undo/{sid}')
    assert r.status_code == 422
    assert r.json()['restored'] is None


def test_a_real_undo_restores_the_file_and_reports_the_path(client, tmp_path, monkeypatch):
    from pathlib import Path

    target = Path(hitl.__file__).resolve().parents[2] / 't157_undo_probe.txt'
    target.write_text('modified')
    try:
        sid = _snapshot(client, type='file', action_id=str(target), state_data='ORIGINAL t157')
        r = client.post(f'/api/hitl/undo/{sid}')
        assert r.status_code == 200 and r.json()['ok'] is True
        assert target.read_text() == 'ORIGINAL t157'
    finally:
        target.unlink(missing_ok=True)


def test_a_real_undo_is_written_to_the_audit_trail(client):
    from pathlib import Path

    from backend.services.memory_db import get_conn

    target = Path(hitl.__file__).resolve().parents[2] / 't157_undo_audit.txt'
    target.write_text('modified')
    try:
        sid = _snapshot(client, type='file', action_id=str(target), state_data='ORIGINAL')
        client.post(f'/api/hitl/undo/{sid}')
        con = get_conn()
        try:
            row = con.execute(
                "SELECT * FROM hitl_audit WHERE decision='undo' AND interrupt_id=?", (sid,)
            ).fetchone()
        finally:
            con.close()
        assert row is not None, 'an undo reverses an approved action and was never recorded'
    finally:
        target.unlink(missing_ok=True)
        con = get_conn()
        try:
            con.execute("DELETE FROM hitl_audit WHERE decision='undo'")
            con.commit()
        finally:
            con.close()


def test_a_custom_state_type_says_it_applied_nothing(client):
    sid = _snapshot(client, type='custom', action_id='t157', state_data='{}')
    body = client.post(f'/api/hitl/undo/{sid}').json()
    assert body['applied'] is False, "a custom type reported 'restored' without restoring anything"
    assert body['restored'] is None
    assert 'Nothing was changed' in body['note']


def test_path_traversal_is_still_denied(client):
    sid = _snapshot(client, type='file', action_id='/etc/t157_passwd', state_data='pwned')
    r = client.post(f'/api/hitl/undo/{sid}')
    assert r.status_code == 403


def test_an_unknown_snapshot_is_a_404(client):
    assert client.post('/api/hitl/undo/undo_t157nope').status_code == 404


# ── the decide path, which was already correct — pinned so it stays that way ──
def test_deciding_an_interrupt_twice_is_a_conflict(client):
    iid = _interrupt(client, action_type='delete_file')['interrupt_id']
    assert client.post(f'/api/hitl/interrupt/{iid}/decide', json={'decision': 'approve'}).status_code == 200
    assert client.post(f'/api/hitl/interrupt/{iid}/decide', json={'decision': 'reject'}).status_code == 409


def test_deciding_an_unknown_interrupt_is_a_404(client):
    r = client.post('/api/hitl/interrupt/hitl_t157nope/decide', json={'decision': 'approve'})
    assert r.status_code == 404
