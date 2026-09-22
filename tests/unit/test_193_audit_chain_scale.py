"""Audit chain verification at scale: streaming + checkpoint suffix mode.

The chain appends one entry per audited action and only grows. The old
verify_chain() fetchall'd the ENTIRE chain and walked it — measured on a
synthetic 75k-entry chain: 668ms and 138MB peak RSS per call, growing
linearly forever. Three routes paid that cost repeatedly: GET
/api/audit-log/verify (Database Studio calls it on pane open), the
compliance report (up to 3 full walks per report including export/json),
and — worst — GET /api/compliance/summary, a dashboard headline that
re-hashed the whole history on every refresh only to read one boolean.

#226 changes:
  * the walk STREAMS rows from the cursor (O(1) memory; same result keys);
  * every successful walk-to-tip advances a persisted checkpoint
    (audit_chain_checkpoint: seq + tip_hash);
  * verify_chain(since_checkpoint=True) verifies only entries appended
    since the checkpoint, anchored at its tip hash — steady-state cost is
    bounded by traffic since the last verify (measured 1.1ms vs 534ms
    full on 75k entries). Suffix verification composes transitively with
    the checkpoint (checkpoint verified from genesis + suffix verified
    from checkpoint = full coverage to the tip);
  * the documented trade: a partial edit of an entry OLDER than the
    checkpoint is not re-hashed until the next full walk (the /verify
    default and the compliance export still do full walks).

Tamper-detection guarantees pinned here: payload and linkage tampering
INSIDE the suffix window are caught; broken walks never advance the
checkpoint; old-row tampering is caught by the full walk.
"""
import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient

from backend.routers import audit_log as al
from backend.routers.audit_log import router as audit_router


@pytest.fixture(scope="module")
def client():
    app = FastAPI()
    app.include_router(audit_router)
    with TestClient(app) as c:
        yield c


def _append(detail="scale test entry"):
    al.append_entry(agent_id="scale_test", agent_name="scale", action_type="test", action_detail=detail)


def _con():
    return al._get_conn()


def _max_seq():
    con = _con()
    try:
        return con.execute("SELECT MAX(seq) m FROM audit_log_chain").fetchone()["m"] or 0
    finally:
        con.close()


def _checkpoint():
    con = _con()
    try:
        row = con.execute("SELECT seq, tip_hash FROM audit_chain_checkpoint WHERE id=1").fetchone()
        return dict(row) if row else None
    finally:
        con.close()


def _sql(sql, params=()):
    con = _con()
    try:
        con.execute(sql, params)
        con.commit()
    finally:
        con.close()


class TestFullVerification:
    def test_full_verify_shape_and_keys(self):
        _append()  # robust to an empty chain (fresh sandbox)
        r = al.verify_chain()
        assert r["ok"] is True
        assert r["mode"] == "full"
        assert r["anchored_seq"] == 0
        assert isinstance(r["verified"], int) and r["verified"] > 0
        assert r["total_checked"] == r["total_entries"]
        assert len(r["chain_tip"]) == 64
        assert r["broken_at"] is None

    def test_full_walk_detects_payload_tamper(self):
        _append("tamper me")
        seq = _max_seq()
        con = _con()
        try:
            original = con.execute(
                "SELECT action_detail FROM audit_log_chain WHERE seq=?", (seq,)
            ).fetchone()["action_detail"]
        finally:
            con.close()
        try:
            _sql("UPDATE audit_log_chain SET action_detail='TAMPERED' WHERE seq=?", (seq,))
            r = al.verify_chain()
            assert r["ok"] is False
            assert r["broken_at"] == seq
        finally:
            _sql("UPDATE audit_log_chain SET action_detail=? WHERE seq=?", (original, seq))
        assert al.verify_chain()["ok"] is True, "repair must restore the chain"

    def test_successful_full_verify_advances_checkpoint(self):
        al.verify_chain()  # walk to tip
        cp = _checkpoint()
        assert cp is not None, "a successful walk must persist the checkpoint"
        assert cp["seq"] == _max_seq()
        assert len(cp["tip_hash"]) == 64

    def test_broken_walk_does_not_advance_checkpoint(self):
        al.verify_chain()
        before = _checkpoint()["seq"]
        _append("tamper me too")
        seq = _max_seq()
        con = _con()
        try:
            original = con.execute(
                "SELECT action_detail FROM audit_log_chain WHERE seq=?", (seq,)
            ).fetchone()["action_detail"]
        finally:
            con.close()
        try:
            _sql("UPDATE audit_log_chain SET action_detail='TAMPERED' WHERE seq=?", (seq,))
            assert al.verify_chain()["ok"] is False
            assert _checkpoint()["seq"] == before, "a broken walk must not advance the checkpoint"
        finally:
            _sql("UPDATE audit_log_chain SET action_detail=? WHERE seq=?", (original, seq))


class TestSuffixVerification:
    def test_suffix_verifies_only_new_entries(self):
        al.verify_chain()
        anchored = _checkpoint()["seq"]
        _append("suffix one")
        _append("suffix two")
        r = al.verify_chain(since_checkpoint=True)
        assert r["ok"] is True
        assert r["mode"] == "suffix"
        assert r["anchored_seq"] == anchored
        assert r["verified"] == 2, "only entries appended since the checkpoint are walked"
        assert r["total_entries"] > 2, "total_entries still reports the whole chain"
        assert _checkpoint()["seq"] == _max_seq(), "a successful suffix walk advances the checkpoint"

    def test_suffix_detects_payload_tamper_in_window(self):
        al.verify_chain()
        _append("window tamper payload")
        seq = _max_seq()
        con = _con()
        try:
            original = con.execute(
                "SELECT action_detail FROM audit_log_chain WHERE seq=?", (seq,)
            ).fetchone()["action_detail"]
        finally:
            con.close()
        try:
            _sql("UPDATE audit_log_chain SET action_detail='TAMPERED' WHERE seq=?", (seq,))
            r = al.verify_chain(since_checkpoint=True)
            assert r["ok"] is False
            assert r["broken_at"] == seq
        finally:
            _sql("UPDATE audit_log_chain SET action_detail=? WHERE seq=?", (original, seq))

    def test_suffix_detects_linkage_tamper_in_window(self):
        al.verify_chain()
        _append("link A")
        _append("link B")
        b_seq = _max_seq()
        con = _con()
        try:
            original = con.execute(
                "SELECT prev_hash FROM audit_log_chain WHERE seq=?", (b_seq,)
            ).fetchone()["prev_hash"]
        finally:
            con.close()
        try:
            _sql("UPDATE audit_log_chain SET prev_hash='deadbeef' WHERE seq=?", (b_seq,))
            r = al.verify_chain(since_checkpoint=True)
            assert r["ok"] is False
            assert r["broken_at"] == b_seq
        finally:
            _sql("UPDATE audit_log_chain SET prev_hash=? WHERE seq=?", (original, b_seq))

    def test_suffix_falls_back_to_full_without_checkpoint(self):
        al.verify_chain()
        _sql("DELETE FROM audit_chain_checkpoint WHERE id=1")
        r = al.verify_chain(since_checkpoint=True)
        assert r["mode"] == "full", "no checkpoint -> verify everything from genesis"
        assert r["ok"] is True
        assert r["anchored_seq"] == 0
        assert _checkpoint() is not None, "the fallback full walk re-establishes the checkpoint"


class TestVerifyRoute:
    def test_route_default_is_full(self, client):
        d = client.get("/api/audit-log/verify").json()
        assert d["ok"] is True
        assert d["mode"] == "full"

    def test_route_suffix_param(self, client):
        client.get("/api/audit-log/verify")  # ensure a checkpoint exists
        d = client.get("/api/audit-log/verify?since_checkpoint=true").json()
        assert d["ok"] is True
        assert d["mode"] == "suffix"
        assert d["anchored_seq"] > 0
