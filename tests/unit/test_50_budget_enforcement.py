"""
Unit Tests — Budget guardrail enforcement (`tests/unit/test_50_budget_enforcement.py`)

FEATURE GAP this covers: budget caps were purely retrospective. record_cost()
ran _check_budget_caps() AFTER the money was spent, which wrote an alert row and
set breached=1 — but nothing anywhere read the `on_breach` column, so the
'pause' and 'kill' actions the FinOps API accepts and persists were completely
inert. A cap could be exceeded without limit; the only consequence was a log
line. Separately, Chat — by far the largest source of spend — never wrote to
cost_ledger at all, so caps had nothing to measure.

check_budget_before_spend() is the enforcement half, and Chat now both consults
it before calling a paid model and records real usage afterwards.
"""

from __future__ import annotations

import uuid
from pathlib import Path

import pytest

from backend.routers.finops import _get_conn, check_budget_before_spend, record_cost

ROOT = Path(__file__).resolve().parents[2]
CHAT_PY = (ROOT / 'backend' / 'routers' / 'chat.py').read_text(encoding='utf-8')


@pytest.fixture
def scoped_agent():
    """A uniquely-named agent plus cleanup, so tests never collide.

    Other suites create wildcard caps (scope_id='*') that match every agent and
    are left behind in the shared database. Those would make these assertions
    depend on test execution order, so enforcing wildcard caps are disabled for
    the duration of each test and restored afterwards. Only enforcing
    ('pause'/'kill') wildcard caps are touched — nothing else is modified.
    """
    agent = f'test_agent_{uuid.uuid4().hex[:8]}'
    cap_id = f'test_cap_{uuid.uuid4().hex[:8]}'

    con = _get_conn()
    try:
        parked = [
            r[0]
            for r in con.execute(
                "SELECT cap_id FROM budget_caps "
                "WHERE enabled=1 AND scope_id='*' AND on_breach IN ('pause','kill')"
            ).fetchall()
        ]
        for pid in parked:
            con.execute('UPDATE budget_caps SET enabled=0 WHERE cap_id=?', (pid,))
        con.commit()
    finally:
        con.close()

    yield agent, cap_id

    con = _get_conn()
    try:
        con.execute('DELETE FROM budget_caps WHERE cap_id=?', (cap_id,))
        con.execute('DELETE FROM cost_ledger WHERE agent_id=?', (agent,))
        for pid in parked:
            con.execute('UPDATE budget_caps SET enabled=1 WHERE cap_id=?', (pid,))
        con.commit()
    finally:
        con.close()


def _make_cap(cap_id: str, agent: str, limit_usd: float, on_breach: str, limit_tokens: int = 0):
    con = _get_conn()
    try:
        con.execute(
            """INSERT INTO budget_caps
               (cap_id,name,scope_type,scope_id,period,limit_usd,limit_tokens,on_breach,enabled,created_at,updated_at)
               VALUES (?,?,'agent',?,'hour',?,?,?,1,'','')""",
            (cap_id, f'Cap {cap_id}', agent, limit_usd, limit_tokens, on_breach),
        )
        con.commit()
    finally:
        con.close()


class TestPreSpendEnforcement:
    def test_allows_when_under_budget(self, scoped_agent):
        agent, cap_id = scoped_agent
        _make_cap(cap_id, agent, 1.00, 'pause')
        record_cost(agent_id=agent, source_type='chat', cost_usd=0.25)
        assert check_budget_before_spend(agent_id=agent)['allowed'] is True

    def test_blocks_once_the_limit_is_reached(self, scoped_agent):
        agent, cap_id = scoped_agent
        _make_cap(cap_id, agent, 1.00, 'pause')
        record_cost(agent_id=agent, source_type='chat', cost_usd=1.10)
        result = check_budget_before_spend(agent_id=agent)
        assert result['allowed'] is False
        assert result['action'] == 'pause'
        assert result['cap_id'] == cap_id

    def test_kill_action_also_blocks(self, scoped_agent):
        agent, cap_id = scoped_agent
        _make_cap(cap_id, agent, 0.50, 'kill')
        record_cost(agent_id=agent, source_type='chat', cost_usd=0.75)
        assert check_budget_before_spend(agent_id=agent)['allowed'] is False

    def test_alert_only_caps_never_block(self, scoped_agent):
        """The default on_breach='alert' must stay notify-only.

        Existing installs configured caps when they had no enforcement; turning
        those into hard blocks retroactively would be a nasty surprise.
        """
        agent, cap_id = scoped_agent
        _make_cap(cap_id, agent, 0.01, 'alert')
        record_cost(agent_id=agent, source_type='chat', cost_usd=5.00)
        assert check_budget_before_spend(agent_id=agent)['allowed'] is True

    def test_cap_is_scoped_to_its_agent(self, scoped_agent):
        agent, cap_id = scoped_agent
        _make_cap(cap_id, agent, 0.10, 'pause')
        record_cost(agent_id=agent, source_type='chat', cost_usd=5.00)
        assert check_budget_before_spend(agent_id=agent)['allowed'] is False
        assert check_budget_before_spend(agent_id='some_other_agent')['allowed'] is True

    def test_token_limits_are_enforced(self, scoped_agent):
        agent, cap_id = scoped_agent
        _make_cap(cap_id, agent, 0, 'pause', limit_tokens=1000)
        record_cost(agent_id=agent, source_type='chat', cost_usd=0.0, tokens_in=800, tokens_out=400)
        result = check_budget_before_spend(agent_id=agent)
        assert result['allowed'] is False
        assert 'tokens' in result['reason']

    def test_zero_limit_means_unset_not_instantly_breached(self, scoped_agent):
        """A 0 limit must not block everything.

        0 means "no limit for this dimension" everywhere else in the module; if
        the guardrail treated it as an instantly-breached cap, one malformed row
        would silently halt all spend platform-wide.
        """
        agent, cap_id = scoped_agent
        _make_cap(cap_id, agent, 0, 'pause', limit_tokens=0)
        record_cost(agent_id=agent, source_type='chat', cost_usd=99.0, tokens_in=9999, tokens_out=9999)
        assert check_budget_before_spend(agent_id=agent)['allowed'] is True

    def test_disabled_caps_are_ignored(self, scoped_agent):
        agent, cap_id = scoped_agent
        _make_cap(cap_id, agent, 0.01, 'pause')
        con = _get_conn()
        try:
            con.execute('UPDATE budget_caps SET enabled=0 WHERE cap_id=?', (cap_id,))
            con.commit()
        finally:
            con.close()
        record_cost(agent_id=agent, source_type='chat', cost_usd=5.00)
        assert check_budget_before_spend(agent_id=agent)['allowed'] is True

    def test_guardrail_fails_open(self, monkeypatch):
        """A broken guardrail must not take the platform down with it."""
        import backend.routers.finops as finops

        def boom():
            raise RuntimeError('db exploded')

        monkeypatch.setattr(finops, '_get_conn', boom)
        assert finops.check_budget_before_spend(agent_id='anyone')['allowed'] is True


class TestChatIsWiredToTheGuardrail:
    def test_chat_consults_the_guardrail_before_spending(self):
        assert 'check_budget_before_spend' in CHAT_PY
        assert "if not gate.get('allowed'):" in CHAT_PY

    def test_blocked_response_explains_which_cap_and_what_to_do(self):
        assert 'Request blocked by a budget cap' in CHAT_PY
        assert 'local model' in CHAT_PY  # offers the free alternative

    def test_chat_records_real_spend_to_the_ledger(self):
        assert 'record_cost(' in CHAT_PY
        assert 'tokens_in=prompt_tokens' in CHAT_PY
        assert 'tokens_out=completion_tokens' in CHAT_PY

    def test_accounting_failure_cannot_break_chat(self):
        assert 'Cost ledger write failed' in CHAT_PY
