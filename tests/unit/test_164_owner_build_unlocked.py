"""Owner build — every module and feature is accessible.

This is a self-hosted, single-owner deployment, so the tier system has no
customer to gate. Rather than delete the licensing code (which would touch ~14
frontend files and every PANE_TIERS consumer, and would be painful to reverse),
the one function every access decision flows through — `_effective_tier()` —
returns the top tier unless `AGENTIC_ENFORCE_LICENSE=1` is set.

Unlocking at that single point matters: `_feature_allowed`, `_pane_allowed`,
`/api/license/status`, `/api/license/pane-access/{id}` and the frontend's
`_UI.tier` all derive from it, so no surface can drift out of step with a
gate somebody forgot to update.

WHAT THE BROWSER CAUGHT. Unlocking the backend was not sufficient. The frontend
boots `_UI` from `/api/profile/ui-config`, NOT from `/api/license/status`, and
that payload carried no `unlocked` flag — so `_UI.unlocked` fell back to false
on every load and the paywall guards stayed live. Forcing `showUpgradeModal()`
and `renderTrialBanner()` directly in Chromium showed both still rendering.
Fixed by having ui-config report the same state; both now no-op.

The tier ENGINE is still real and still tested — `test_16_business_logic.py`
and `test_50_product_status_truthfulness.py` enable enforcement so the gating
maths stays verified rather than becoming dead untested code.
"""

from __future__ import annotations

import time

import pytest

from backend.routers import license as lic


@pytest.fixture(autouse=True)
def _default_unlocked(monkeypatch):
    """The owner build default: no enforcement env var set."""
    monkeypatch.delenv('AGENTIC_ENFORCE_LICENSE', raising=False)


# ── the unlock itself ─────────────────────────────────────────────────────────
def test_effective_tier_is_top_tier_by_default():
    assert lic._effective_tier({'tier': 'free'}) == 'enterprise'


def test_an_expired_trial_does_not_downgrade():
    """The countdown-to-lockout is what the owner asked to remove."""
    expired = {'tier': 'trial', 'trial_end': time.time() - 86400}
    assert lic._effective_tier(expired) == 'enterprise'


@pytest.mark.parametrize('stored', ['free', 'trial', 'pro', 'enterprise', '', 'nonsense'])
def test_every_stored_tier_resolves_unlocked(stored):
    assert lic._effective_tier({'tier': stored}) == 'enterprise'


def test_every_known_pane_is_allowed():
    tier = lic._effective_tier({'tier': 'free'})
    denied = [p for p in lic.PANE_TIERS if not lic._pane_allowed(p, tier)]
    assert denied == [], f'panes still gated: {denied}'


def test_an_unlisted_pane_is_allowed():
    """PANE_TIERS.get(pane, 'pro') defaults unknown panes to pro."""
    assert lic._pane_allowed('some-brand-new-pane', lic._effective_tier({})) is True


def test_every_feature_is_allowed():
    tier = lic._effective_tier({})
    for feature in ('chat', 'agents', 'swarm', 'evals', 'anything_at_all'):
        assert lic._feature_allowed(feature, tier) is True


# ── the endpoints the UI reads ────────────────────────────────────────────────
def test_status_reports_unlocked(client):
    d = client.get('/api/license/status').json()
    assert d['unlocked'] is True
    assert d['license_enforced'] is False
    assert d['all_features'] is True
    assert d['features'] == ['*']


def test_status_reports_no_trial_countdown(client):
    """No trial means no expiry banner and no "N days left" chip."""
    d = client.get('/api/license/status').json()
    assert d['is_trial'] is False
    assert d['trial_expired'] is False
    assert d['trial_days_left'] == -1


def test_status_pane_access_map_is_all_true(client):
    d = client.get('/api/license/status').json()
    assert d['pane_access'], 'the access map is empty'
    assert all(d['pane_access'].values())


@pytest.mark.parametrize(
    'pane', ['studio', 'swarm', 'galaxy', 'hierarchy', 'deploy', 'evals', 'observability', 'rag']
)
def test_pane_access_endpoint_allows_previously_gated_panes(client, pane):
    d = client.get(f'/api/license/pane-access/{pane}').json()
    assert d['allowed'] is True
    assert d['upgrade_needed'] is False


def test_ui_config_reports_unlocked(client):
    """The frontend boots _UI from THIS payload, not from /license/status.

    Omitting these fields is what left the paywall guards live in the browser
    after the backend was already unlocked.
    """
    d = client.get('/api/profile/ui-config').json()
    assert d['unlocked'] is True
    assert d['all_features'] is True
    assert d['is_trial'] is False


# ── the escape hatch still works ──────────────────────────────────────────────
def test_enforcement_can_be_re_enabled(monkeypatch):
    """Reversible on purpose: the licensing code is intact, not deleted."""
    monkeypatch.setenv('AGENTIC_ENFORCE_LICENSE', '1')
    assert lic._effective_tier({'tier': 'free'}) == 'free'
    expired = {'tier': 'trial', 'trial_end': time.time() - 86400}
    assert lic._effective_tier(expired) == 'free'


def test_enforcement_restores_pane_gating(monkeypatch):
    monkeypatch.setenv('AGENTIC_ENFORCE_LICENSE', '1')
    assert lic._pane_allowed('studio', lic._effective_tier({'tier': 'free'})) is False


def test_a_trial_still_unlocks_every_pane_when_enforced(monkeypatch):
    """Regression guard on TIER_ORDER.

    'trial' deliberately ranks level with 'enterprise' so a trial unlocks
    everything — four panes (evals, observability, knowledge-graph, rag)
    require 'enterprise'. I briefly "corrected" trial to rank below it, which
    broke exactly that, and the existing suite caught it. Pinned here too.
    """
    monkeypatch.setenv('AGENTIC_ENFORCE_LICENSE', '1')
    denied = [p for p in lic.PANE_TIERS if not lic._pane_allowed(p, 'trial')]
    assert denied == [], f'a trial should unlock everything, still gated: {denied}'


def test_free_tier_is_still_a_real_restriction_when_enforced(monkeypatch):
    """The mirror: unlocking must not have flattened the tier table itself."""
    monkeypatch.setenv('AGENTIC_ENFORCE_LICENSE', '1')
    denied = [p for p in lic.PANE_TIERS if not lic._pane_allowed(p, 'free')]
    assert denied, 'free tier allows everything — the tier table is no longer meaningful'
