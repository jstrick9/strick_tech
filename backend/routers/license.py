"""
Agentic OS — License / Tier System
Free / Pro / Enterprise tiers with 14-day free trial.

Trial is tracked locally in .agentic/license.json (no server needed).
Feature flags control which panes and features are accessible per tier.

Tiers:
  free       — limited features, after 14-day trial expires
  trial      — all Pro features, 14 days from first launch
  pro        — full platform, individual
  enterprise — full platform + governance + admin + multi-user
"""

from __future__ import annotations

import contextlib

import json
import logging
import os
import time
from datetime import datetime, timezone
from pathlib import Path

from fastapi import APIRouter, Request

router = APIRouter(prefix='/api/license', tags=['license'])
log = logging.getLogger('agentic.license')

ROOT = Path(__file__).resolve().parents[2]
LICENSE_FILE = ROOT / '.agentic' / 'license.json'
LICENSE_FILE.parent.mkdir(parents=True, exist_ok=True)

# ── Feature flag matrix per tier ──────────────────────────────────────────────
TIER_FEATURES: dict[str, list[str]] = {
    'free': [
        'chat',
        'agents_basic',
        'kanban',
        'templates_basic',
        'docs',
        'settings',
        'tts_basic',
    ],
    'trial': ['*'],  # all features during trial
    'pro': [
        'chat',
        'agents',
        'kanban',
        'templates',
        'docs',
        'settings',
        'tts',
        'swarm',
        'memory',
        'galaxy',
        'loops',
        'mcp',
        'github',
        'deploy',
        'dbstudio',
        'dashboard',
        'plugins',
        'obsidian',
        'system',
        'control',
        'workspaces',
        'webhooks',
        'testgen',
        'terminal',
        'integrations',
        'imagegen',
        'prompts',
        'codesearch',
        'workflow',
        'profiler',
        'pluginsdk',
        'multitab',
        'replay',
        'collabedit',
        'marketplace',
        'specs',
        'hooks',
        'codeindex',
        'arena',
        'steering',
        'bugbot',
        'health',
        'gitai',
        'ambient',
        'fusion',
        'hitl',
        'browser',
        'websearch',
        'leaderboard',
        'evals',
        'observability',
        'knowledge-graph',
        'rag',
        'voice',
        'pipeline',
    ],
    'enterprise': ['*'],  # all features
}

# Pane → minimum tier required
PANE_TIERS: dict[str, str] = {
    # Always free
    'chat': 'free',
    'kanban': 'free',
    'settings': 'free',
    'docs': 'free',
    'dashboard': 'free',
    # Pro features
    'studio': 'pro',
    'builder': 'pro',
    'swarm': 'pro',
    'galaxy': 'pro',
    'loops': 'pro',
    'mcp': 'pro',
    'github': 'pro',
    'deploy': 'pro',
    'dbstudio': 'pro',
    'plugins': 'pro',
    'obsidian': 'pro',
    'system': 'pro',
    'control': 'pro',
    'workspaces': 'pro',
    'webhooks': 'pro',
    'testgen': 'pro',
    'terminal': 'pro',
    'integrations': 'pro',
    'imagegen': 'pro',
    'prompts': 'pro',
    'codesearch': 'pro',
    'workflow': 'pro',
    'profiler': 'pro',
    'pluginsdk': 'pro',
    'multitab': 'pro',
    'replay': 'pro',
    'collabedit': 'pro',
    'marketplace': 'pro',
    'specs': 'pro',
    'hooks': 'pro',
    'codeindex': 'pro',
    'arena': 'pro',
    'steering': 'pro',
    'bugbot': 'pro',
    'health': 'pro',
    'gitai': 'pro',
    'ambient': 'pro',
    'fusion': 'pro',
    'hitl': 'pro',
    'browser': 'pro',
    'websearch': 'pro',
    'leaderboard': 'pro',
    'voice': 'pro',
    'pipeline': 'pro',
    # Enterprise only
    'evals': 'enterprise',
    'observability': 'enterprise',
    'knowledge-graph': 'enterprise',
    'rag': 'enterprise',
}

# trial & enterprise get level-3 access — all features unlocked
TIER_ORDER = {'free': 0, 'trial': 3, 'pro': 2, 'enterprise': 3}


# ── License file helpers ───────────────────────────────────────────────────────


def _load_license() -> dict:
    """Load license JSON, creating a trial if missing or corrupt."""
    if LICENSE_FILE.exists():
        try:
            text = LICENSE_FILE.read_text(encoding='utf-8')
            data = json.loads(text)
            if isinstance(data, dict):
                return data
        except Exception as exc:
            log.warning('License file corrupt (%s) — resetting to trial', exc)
    return _create_trial()


def _save_license(data: dict) -> bool:
    """Write license JSON to disk. Returns True on success, False on failure."""
    try:
        LICENSE_FILE.write_text(json.dumps(data, indent=2), encoding='utf-8')
        return True
    except Exception as exc:
        log.error('Could not save license file: %s', exc)
        return False


def _create_trial() -> dict:
    now = time.time()
    data = {
        'tier': 'trial',
        'trial_start': now,
        'trial_end': now + (14 * 24 * 3600),
        'trial_days': 14,
        'activated_at': now,
        'license_key': '',
        'user_name': '',
        'user_email': '',
        'org': '',
        'history': [],
    }
    _save_license(data)
    log.info('14-day trial started')
    return data


def _effective_tier(data: dict) -> str:
    """Return effective tier, accounting for expired trial."""
    tier = data.get('tier', 'trial')
    if tier == 'trial':
        if time.time() > data.get('trial_end', 0):
            return 'free'  # trial expired → free
    return tier


def _days_remaining(data: dict) -> int:
    if data.get('tier') != 'trial':
        return -1
    remaining = data.get('trial_end', 0) - time.time()
    return max(0, int(remaining / 86400))


def _feature_allowed(feature: str, effective_tier: str) -> bool:
    allowed = TIER_FEATURES.get(effective_tier, [])
    return '*' in allowed or feature in allowed


def _pane_allowed(pane: str, effective_tier: str) -> bool:
    required = PANE_TIERS.get(pane, 'pro')
    return TIER_ORDER.get(effective_tier, 0) >= TIER_ORDER.get(required, 2)


def _append_history(data: dict, event: str, detail: str = '') -> None:
    """Append to the in-license activation history (keep last 20)."""
    history = data.get('history', [])
    history.append(
        {
            'event': event,
            'detail': detail[:200],
            'ts': int(time.time()),
            'ts_iso': datetime.fromtimestamp(time.time(), tz=timezone.utc).isoformat(),
        }
    )
    data['history'] = history[-20:]


# ── REST endpoints ──────────────────────────────────────────────────────────────


@router.get('/status')
def license_status():
    """Full license status + feature access map."""
    data = _load_license()
    eff_tier = _effective_tier(data)
    days_left = _days_remaining(data)
    is_trial = data.get('tier') == 'trial'
    trial_expired = is_trial and days_left == 0

    pane_access = {pane: _pane_allowed(pane, eff_tier) for pane in PANE_TIERS}

    return {
        'ok': True,
        'tier': eff_tier,
        'stored_tier': data.get('tier', 'trial'),
        'is_trial': is_trial,
        'trial_expired': trial_expired,
        'trial_days_left': days_left,
        'trial_end_date': datetime.fromtimestamp(data.get('trial_end', 0), tz=timezone.utc).isoformat()
        if is_trial
        else None,
        'user_name': data.get('user_name', ''),
        'user_email': data.get('user_email', ''),
        'org': data.get('org', ''),
        'pane_access': pane_access,
        'features': TIER_FEATURES.get(eff_tier, []),
        'all_features': eff_tier in ('trial', 'enterprise'),
    }


@router.post('/activate')
async def activate_license(req: Request):
    """Activate a Pro or Enterprise license key."""
    try:
        try:
            body = await req.json()
        except (KeyError, TypeError, ValueError, json.JSONDecodeError, OSError, AttributeError, RuntimeError):
            body = {}
    except (KeyError, TypeError, ValueError, json.JSONDecodeError, OSError, AttributeError, RuntimeError):
        return {'ok': False, 'error': 'Invalid JSON body'}

    key = (body.get('license_key') or '').strip()
    if not key:
        return {'ok': False, 'error': 'license_key required'}

    # Key format: PRO-XXXX… or ENT-XXXX… (min 16 chars total)
    key_upper = key.upper()
    if key_upper.startswith('ENT-') and len(key) >= 16:
        tier = 'enterprise'
    elif key_upper.startswith('PRO-') and len(key) >= 16:
        tier = 'pro'
    else:
        return {
            'ok': False,
            'error': 'Invalid license key. Pro keys must start with PRO- and Enterprise keys with ENT- (minimum 16 characters).',
        }

    data = _load_license()
    data['tier'] = tier
    data['license_key'] = key[:100]
    data['activated_at'] = time.time()
    _append_history(data, 'activated', f'tier={tier} key={key[:8]}…')
    saved = _save_license(data)

    if not saved:
        return {
            'ok': False,
            'error': 'License activated in memory but could not be saved to disk — check file permissions.',
        }

    return {'ok': True, 'tier': tier, 'message': f'✅ {tier.title()} license activated!'}


@router.post('/set-user')
async def set_user(req: Request):
    """Store user name, email, and org in the license file."""
    try:
        try:
            body = await req.json()
        except (KeyError, TypeError, ValueError, json.JSONDecodeError, OSError, AttributeError, RuntimeError):
            body = {}
    except (KeyError, TypeError, ValueError, json.JSONDecodeError, OSError, AttributeError, RuntimeError):
        return {'ok': False, 'error': 'Invalid JSON body'}

    name = (body.get('name', '') or '')[:100].strip()
    email = (body.get('email', '') or '')[:200].strip()
    org = (body.get('org', '') or '')[:100].strip()

    # Basic email format check if provided
    if email and not ('@' in email and '.' in email.split('@')[-1]):
        return {'ok': False, 'error': 'Invalid email format'}

    data = _load_license()
    data['user_name'] = name
    data['user_email'] = email
    data['org'] = org
    _append_history(data, 'user_set', f'name={name} email={email}')
    saved = _save_license(data)

    if not saved:
        return {'ok': False, 'error': 'User info saved in memory but could not persist to disk'}

    return {'ok': True, 'user_name': name, 'user_email': email, 'org': org}


@router.get('/pane-access/{pane_id}')
def check_pane(pane_id: str):
    """Verify and validate check pane functionality or health."""
    data = _load_license()
    eff_tier = _effective_tier(data)
    allowed = _pane_allowed(pane_id, eff_tier)
    required = PANE_TIERS.get(pane_id, 'pro')  # explicit default "pro" for unlisted panes
    return {
        'ok': True,
        'pane': pane_id,
        'allowed': allowed,
        'required_tier': required,
        'current_tier': eff_tier,
        'upgrade_needed': not allowed,
    }


@router.get('/tiers')
def list_tiers():
    """Retrieve and return list tiers."""
    return {
        'ok': True,
        'tiers': [
            {
                'id': 'free',
                'name': 'Free',
                'price': '$0/mo',
                'description': 'Get started with core AI chat and basic features',
                'features': [
                    'AI Chat with any model',
                    'Basic agent creation',
                    'Kanban board',
                    'Template gallery',
                    'Documentation center',
                    'Settings & API keys',
                ],
                'locked': ['Swarm agents', 'Workflow builder', 'GitHub integration', 'All 50+ advanced panes'],
                'cta': 'Start Free Trial',
                'highlight': False,
            },
            {
                'id': 'pro',
                'name': 'Pro',
                'price': '$29/mo',
                'description': 'Full platform access for power users and small teams',
                'features': [
                    'Everything in Free',
                    'All 50+ panes unlocked',
                    'Swarm agents',
                    'Workflow builder',
                    'BugBot PR review',
                    'Git AI & changelogs',
                    'Spec-driven development',
                    'Model Fusion',
                    'Web Search grounding',
                    'Voice coding',
                ],
                'locked': [
                    'Agent Evals engine',
                    'LLM Observability/DORA',
                    'Knowledge Graph',
                    'RAG pipeline builder',
                    'Multi-user admin',
                ],
                'cta': 'Upgrade to Pro',
                'highlight': True,
            },
            {
                'id': 'enterprise',
                'name': 'Enterprise',
                'price': 'Contact us',
                'description': 'Full governance, compliance, and team management',
                'features': [
                    'Everything in Pro',
                    'Agent Evals (DeepEval-level)',
                    'LLM Observability + DORA',
                    'EU AI Act compliance',
                    'Knowledge Graph memory',
                    'RAG pipeline builder',
                    'HITL governance',
                    'Multi-user admin panel',
                    'SOC 2 audit trails',
                    'Priority support',
                ],
                'locked': [],
                'cta': 'Contact Sales',
                'highlight': False,
            },
        ],
    }


@router.get('/history')
def get_history():
    """Return license activation/change history."""
    data = _load_license()
    history = data.get('history', [])
    return {'ok': True, 'history': list(reversed(history)), 'count': len(history)}


@router.post('/reset-trial')
async def reset_trial():
    """Dev/demo: reset trial to start fresh. Gated by AGENTIC_DEV_MODE env var."""
    dev_mode = os.getenv('AGENTIC_DEV_MODE', '1')  # default on for local dev
    if dev_mode not in ('1', 'true', 'yes', 'on'):
        return {'ok': False, 'error': 'reset-trial is only available in dev mode'}
    data = _create_trial()
    _append_history(data, 'trial_reset', 'dev reset')
    _save_license(data)
    return {'ok': True, 'message': 'Trial reset to 14 days', 'tier': 'trial'}
