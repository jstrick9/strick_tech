"""Module 24 — the Workspaces workstation: `control` (Control Tower) and the host.

Destination: `workspaces`, hosting collabedit and control.

The headline defect here is the most consequential kind this review can find: a
guardrail that the UI presents as configured and that nothing enforces.

Five defects, all reproduced against a live server before the fix:

1. THE CONTROL TOWER'S BUDGET CAPS WERE NEVER ENFORCED. The platform had two
   unrelated budget stores:
     * `budget_rules` — written by /api/control/budget-rules, rendered in the
       Control Tower pane, and read by NOTHING (confirmed by grep: zero readers
       outside its own router).
     * `budget_caps`  — what finops.check_budget_before_spend() actually
       consults before every LLM call.
   Verified live: created {"max_cost": 0.01, "action": "stop"}, saw it listed,
   then asked the enforcer directly -> {'allowed': True}. The pane whose entire
   purpose is stopping runaway spend was decorative.

2. `float(body.get('max_cost', 1.0))` raised ValueError on a non-numeric value
   and returned HTTP 500.

3. Negative limits were accepted — a cap of -5 dollars can never be satisfied
   and was stored as though it were a sensible restriction.

4. PATCH bypassed every check the create path performs. Verified live: a rule
   ended up holding max_cost='not-a-number' and action='ignore_everything',
   both listed as valid. A cap holding a string cannot be compared to a number.

5. github pull's `target` escaped the data directory: `ROOT / target` with
   target='../../../tmp/x' resolves to /tmp/x and mkdir(parents=True) creates
   it. The per-file `is_within` check guarded paths inside the repo; nothing
   guarded the destination root.
"""

from __future__ import annotations

import json
from unittest.mock import patch

import pytest


@pytest.fixture(autouse=True)
def _clean():
    from backend.services.memory_db import get_conn

    def purge():
        con = get_conn()
        try:
            con.execute("DELETE FROM budget_rules WHERE name LIKE 't160%'")
            con.execute("DELETE FROM budget_caps WHERE cap_id LIKE 'ctrl_rule_%'")
            con.execute("DELETE FROM cost_ledger WHERE ledger_id LIKE 't160%'")
            con.commit()
        finally:
            con.close()

    purge()
    yield
    purge()


def _rule(client, **kw):
    body = {'name': 't160 rule', 'max_cost': 1.0}
    body.update(kw)
    return client.post('/api/control/budget-rules', json=body)


def _caps():
    from backend.services.memory_db import get_conn

    con = get_conn()
    try:
        return [dict(r) for r in con.execute("SELECT * FROM budget_caps WHERE cap_id LIKE 'ctrl_rule_%'").fetchall()]
    finally:
        con.close()


# ── 1. a configured cap must actually gate spending ───────────────────────────
def test_a_stop_rule_reaches_the_table_the_enforcer_reads(client):
    rid = _rule(client, name='t160 hardstop', max_cost=0.01, action='stop').json()['id']
    caps = _caps()
    assert caps, 'the Control Tower rule never reached budget_caps — nothing enforces it'
    cap = next(c for c in caps if c['cap_id'] == f'ctrl_rule_{rid}')
    assert cap['on_breach'] == 'pause', "a 'stop' rule must deny spending, not merely alert"
    assert cap['enabled'] == 1
    assert cap['limit_usd'] == 0.01


def test_a_stop_rule_actually_denies_a_spend(client):
    """End to end: configure in the Control Tower, ask the real enforcer.

    `created_at` on cost_ledger defaults to '' rather than a timestamp in this
    schema, and the enforcer's window filter is
    `created_at > datetime('now','-1 day')` -- so a row inserted without an
    explicit timestamp is NOT counted. Set it explicitly rather than relying on
    whatever spend happens to be in the shared database, or this test would
    pass on ambient data and prove nothing.
    """
    from backend.routers.finops import check_budget_before_spend
    from backend.services.memory_db import get_conn

    _rule(client, name='t160 hardstop', max_cost=0.01, max_tokens=10, action='stop')
    con = get_conn()
    try:
        con.execute(
            "INSERT INTO cost_ledger(ledger_id,agent_id,goal_id,model,tokens_in,tokens_out,"
            "total_tokens,cost_usd,created_at) "
            "VALUES('t160_led','brain','','m',10,10,20,5.0,datetime('now'))"
        )
        con.commit()
        spent = con.execute(
            "SELECT SUM(cost_usd) FROM cost_ledger WHERE created_at > datetime('now','-1 day')"
        ).fetchone()[0]
    finally:
        con.close()
    assert spent and spent >= 5.0, 'the probe spend was not visible to the enforcer window'

    verdict = check_budget_before_spend(agent_id='brain')
    assert verdict['allowed'] is False, 'a configured hard stop did not stop anything'
    assert verdict['action'] == 'pause'


def test_a_stop_rule_allows_spending_below_its_limit(client):
    """The mirror: enforcement must not block everything unconditionally."""
    from backend.routers.finops import check_budget_before_spend
    from backend.services.memory_db import get_conn

    # Deliberately NOT clearing cost_ledger: it is shared with the live app and
    # a destructive probe here has caused false failures elsewhere in this
    # review. Instead the limit is set far above any plausible accumulated
    # spend, which tests the same property without touching other rows.
    con = get_conn()
    try:
        spent = con.execute(
            "SELECT COALESCE(SUM(cost_usd),0) FROM cost_ledger WHERE created_at > datetime('now','-1 day')"
        ).fetchone()[0]
    finally:
        con.close()
    _rule(
        client,
        name='t160 roomy',
        max_cost=float(spent) + 1_000_000.0,
        max_tokens=10_000_000_000,
        action='stop',
    )
    verdict = check_budget_before_spend(agent_id='brain')
    assert verdict['allowed'] is True, f'a cap far above current spend ({spent}) still blocked'


def test_a_warn_rule_does_not_block(client):
    """'warn' promises an alert, not a block — over-enforcing would be its own bug."""
    rid = _rule(client, name='t160 warnonly', max_cost=0.01, action='warn').json()['id']
    cap = next(c for c in _caps() if c['cap_id'] == f'ctrl_rule_{rid}')
    assert cap['on_breach'] == 'alert'


def test_the_response_says_whether_the_rule_enforces(client):
    assert _rule(client, action='stop').json()['enforced'] is True
    body = _rule(client, name='t160 w', action='warn').json()
    assert body['enforced'] is False
    assert 'does not block' in body['note']


def test_the_listing_reports_real_enforcement_not_the_stored_action(client):
    """`enforced` is measured against budget_caps, so a rule whose mirror is
    missing is reported as inert rather than assumed live."""
    from backend.services.memory_db import get_conn

    rid = _rule(client, action='stop').json()['id']
    con = get_conn()
    try:
        con.execute('DELETE FROM budget_caps WHERE cap_id=?', (f'ctrl_rule_{rid}',))
        con.commit()
    finally:
        con.close()
    row = next(r for r in client.get('/api/control/budget-rules').json() if r['id'] == rid)
    assert row['action'] == 'stop'
    assert row['enforced'] is False, 'an unenforced rule was reported as active'


def test_updating_a_rule_updates_the_enforcing_cap(client):
    rid = _rule(client, max_cost=5.0, action='stop').json()['id']
    client.patch(f'/api/control/budget-rules/{rid}', json={'max_cost': 0.25})
    cap = next(c for c in _caps() if c['cap_id'] == f'ctrl_rule_{rid}')
    assert cap['limit_usd'] == 0.25


def test_deleting_a_rule_removes_the_enforcing_cap(client):
    rid = _rule(client, action='stop').json()['id']
    assert _caps()
    assert client.request('DELETE', f'/api/control/budget-rules/{rid}').status_code == 200
    assert not [c for c in _caps() if c['cap_id'] == f'ctrl_rule_{rid}'], (
        'a deleted rule kept blocking spend'
    )


def test_disabling_a_rule_disables_the_cap(client):
    rid = _rule(client, action='stop').json()['id']
    client.patch(f'/api/control/budget-rules/{rid}', json={'enabled': 0})
    cap = next(c for c in _caps() if c['cap_id'] == f'ctrl_rule_{rid}')
    assert cap['enabled'] == 0


# ── 2/3/4. validation ─────────────────────────────────────────────────────────
def test_a_non_numeric_max_cost_is_a_400_not_a_500(client):
    r = _rule(client, max_cost='abc')
    assert r.status_code == 400, 'a bad limit took the endpoint out with a 500'


def test_a_non_numeric_max_tokens_is_a_400(client):
    assert _rule(client, max_tokens='lots').status_code == 400


def test_a_negative_cost_cap_is_rejected(client):
    r = _rule(client, max_cost=-5)
    assert r.status_code == 400
    assert 'non-negative' in r.json()['error']


def test_a_negative_token_cap_is_rejected(client):
    assert _rule(client, max_tokens=-100).status_code == 400


def test_an_unknown_action_is_rejected_rather_than_silently_rewritten(client):
    """It used to become 'stop', so the stored rule disagreed with the request."""
    r = _rule(client, action='ignore_everything')
    assert r.status_code == 400
    assert 'stop, warn, notify' in r.json()['error']


def test_a_zero_cap_is_allowed(client):
    """Zero is a legitimate "block everything" cap; only negatives are absurd."""
    assert _rule(client, max_cost=0).status_code == 200


def test_patch_validates_max_cost(client):
    rid = _rule(client).json()['id']
    r = client.patch(f'/api/control/budget-rules/{rid}', json={'max_cost': 'not-a-number'})
    assert r.status_code == 400, 'PATCH bypassed every check the create path performs'


def test_patch_validates_the_action(client):
    rid = _rule(client).json()['id']
    assert client.patch(f'/api/control/budget-rules/{rid}', json={'action': 'nonsense'}).status_code == 400


def test_patch_rejects_a_negative_limit(client):
    rid = _rule(client).json()['id']
    assert client.patch(f'/api/control/budget-rules/{rid}', json={'max_cost': -1}).status_code == 400


def test_patching_a_missing_rule_is_a_404(client):
    assert client.patch('/api/control/budget-rules/999999', json={'max_cost': 1}).status_code == 404


def test_deleting_a_missing_rule_is_a_404(client):
    r = client.request('DELETE', '/api/control/budget-rules/999999')
    assert r.status_code == 404, 'reporting deleted:false with HTTP 200 reads as success'


def test_a_valid_patch_still_works(client):
    rid = _rule(client).json()['id']
    assert client.patch(f'/api/control/budget-rules/{rid}', json={'name': 't160 renamed'}).status_code == 200


# ── 5. the github pull target must stay inside the data dir ───────────────────
def _pull(target):
    import asyncio

    from backend.routers import github as gh

    class Req:
        async def json(self):
            return {'repo': 'o/r', 'branch': 'main', 'target': target}

    with patch.object(gh, '_gh_token', lambda: 'ghp_fake_for_test'):
        r = asyncio.get_event_loop().run_until_complete(gh.pull_from_github(Req()))
    if hasattr(r, 'body'):
        return getattr(r, 'status_code', 200), json.loads(bytes(r.body).decode())
    return 200, r


@pytest.mark.parametrize(
    'target',
    ['../../../tmp/t160_escape', '/etc/t160_escape', 'preview/../../../tmp/t160_escape', '..'],
)
def test_a_pull_target_cannot_escape_the_data_directory(target):
    status, body = _pull(target)
    assert body['ok'] is False, f'{target!r} was accepted as a pull destination'
    assert 'Invalid target' in body['error']


def test_an_escaping_target_creates_no_directory():
    """Self-cleaning: with the guard removed this test genuinely creates
    /tmp/t160_escape, which then makes the NEXT run fail on its precondition.
    Found during revert-proof. Removing it up front and again afterwards keeps
    the test honest whether or not the guard is in place -- and the fact that
    the directory appears at all when the guard is removed is the proof that
    the traversal was real."""
    import pathlib
    import shutil

    probe = pathlib.Path('/tmp/t160_escape')
    shutil.rmtree(probe, ignore_errors=True)
    try:
        _pull('../../../tmp/t160_escape')
        assert not probe.exists(), 'mkdir ran before the destination was validated'
    finally:
        shutil.rmtree(probe, ignore_errors=True)


def test_a_normal_target_is_still_accepted():
    """Over-blocking would break workspace import, which passes a real path."""
    from backend.routers import github as gh

    status, body = _pull('preview')
    # It fails later (no real GitHub), but NOT on the target check.
    assert 'Invalid target' not in str(body.get('error', ''))


def test_a_workspace_subdirectory_target_is_accepted():
    from backend.routers import github as gh

    status, body = _pull(str((gh.ROOT / 'workspaces' / 'ws_probe' / 'preview').relative_to(gh.ROOT)))
    assert 'Invalid target' not in str(body.get('error', ''))
