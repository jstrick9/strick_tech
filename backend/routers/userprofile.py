"""
Agentic OS — User Profile & Preferences System
Full profile: name, avatar, skill level, feature toggles, sidebar layout,
theme, shortcuts, notification prefs, and workspace personalization.

Stored in .agentic/profile.json (local-first, no server).
"""

from __future__ import annotations

import contextlib

import json
import logging
import time
from pathlib import Path

from fastapi import APIRouter, Request
from fastapi.responses import JSONResponse

router = APIRouter(prefix='/api/profile', tags=['profile'])
log = logging.getLogger('agentic.profile')

from backend.config import get_data_dir
ROOT = get_data_dir()
PROFILE_FILE = ROOT / '.agentic' / 'profile.json'
PROFILE_FILE.parent.mkdir(parents=True, exist_ok=True)

VALID_UI_MODES = {'simple', 'power'}
VALID_THEMES = {'dark', 'darker', 'midnight', 'ocean', 'forest'}
VALID_FONT_SIZES = {'sm', 'base', 'lg'}
VALID_SKILL_LEVELS = {'beginner', 'intermediate', 'advanced', 'expert'}
VALID_ROLES = {'developer', 'analyst', 'writer', 'designer', 'manager', 'student'}

DEFAULT_PROFILE: dict = {
    'name': '',
    'email': '',
    'avatar': '🧑‍💻',
    'role': 'developer',
    'skill_level': 'beginner',
    'ui_mode': 'simple',
    'theme': 'dark',
    'font_size': 'base',
    'sidebar_width': 'normal',
    'show_tips': True,
    'show_tour': True,
    'onboarding_done': False,
    'onboarding_step': 0,
    'notifications': {
        'agent_complete': True,
        'hitl_interrupt': True,
        'daily_summary': False,
        'sound': False,
    },
    'hidden_panes': [],
    'pinned_panes': ['chat', 'kanban', 'docs'],
    'sidebar_order': [],
    'enabled_features': {},
    'quick_actions': ['chat', 'workflow', 'arena', 'bugbot'],
    'default_agent': 'default',
    'default_model': 'free',
    'created_at': '',
    'updated_at': '',
}

ROLE_DEFAULTS: dict[str, dict] = {
    'developer': {
        'pinned_panes': ['chat', 'studio', 'github', 'terminal', 'bugbot', 'codeindex'],
        'quick_actions': ['chat', 'studio', 'bugbot', 'gitai'],
        'default_agent': 'default',
    },
    'analyst': {
        'pinned_panes': ['chat', 'dashboard', 'dbstudio', 'rag', 'evals'],
        'quick_actions': ['chat', 'rag', 'evals', 'dashboard'],
        'default_agent': 'default',
    },
    'writer': {
        'pinned_panes': ['chat', 'prompts', 'templates', 'docs'],
        'quick_actions': ['chat', 'prompts', 'templates', 'websearch'],
        'default_agent': 'default',
    },
    'designer': {
        'pinned_panes': ['chat', 'imagegen', 'studio', 'templates'],
        'quick_actions': ['chat', 'imagegen', 'studio', 'collabedit'],
        'default_agent': 'default',
    },
    'manager': {
        'pinned_panes': ['chat', 'kanban', 'dashboard', 'control', 'leaderboard'],
        'quick_actions': ['chat', 'kanban', 'dashboard', 'ambient'],
        'default_agent': 'default',
    },
    'student': {
        'pinned_panes': ['chat', 'docs', 'templates', 'kanban'],
        'quick_actions': ['chat', 'docs', 'templates', 'arena'],
        'default_agent': 'default',
    },
}


# ── File helpers ───────────────────────────────────────────────────────────────


def _ts() -> str:
    return time.strftime('%Y-%m-%dT%H:%M:%SZ', time.gmtime())


def _merge(saved: dict) -> dict:
    """Merge saved profile with defaults so new fields are always present."""
    merged = {**DEFAULT_PROFILE, **saved}
    merged['notifications'] = {
        **DEFAULT_PROFILE['notifications'],
        **saved.get('notifications', {}),
    }
    return merged


def _load() -> dict:
    if PROFILE_FILE.exists():
        try:
            text = PROFILE_FILE.read_text(encoding='utf-8')
            saved = json.loads(text)
            if isinstance(saved, dict):
                return _merge(saved)
        except Exception as exc:
            log.warning('Profile file corrupt (%s) — using defaults', exc)
    p = {**DEFAULT_PROFILE, 'created_at': _ts()}
    _save(p)
    return p


def _save(data: dict) -> bool:
    """Write profile to disk. Returns True on success."""
    try:
        data['updated_at'] = _ts()
        PROFILE_FILE.write_text(json.dumps(data, indent=2), encoding='utf-8')
        return True
    except Exception as exc:
        log.error('Could not save profile: %s', exc)
        return False


# ── REST endpoints ──────────────────────────────────────────────────────────────


@router.get('')
def get_profile():
    """Retrieve and return get profile."""
    return _load()


@router.patch('')
async def update_profile(req: Request):
    """Update existing profile record or state."""
    try:
        try:
            body = await req.json()
        except (KeyError, TypeError, ValueError, json.JSONDecodeError, OSError, AttributeError, RuntimeError):
            body = {}
    except (KeyError, TypeError, ValueError, json.JSONDecodeError, OSError, AttributeError, RuntimeError):
        return JSONResponse(status_code=422, content={'ok': False, 'error': 'Invalid JSON body'})

    profile = _load()

    # ── Field-level validation ────────────────────────────────────────────────
    if 'ui_mode' in body and body['ui_mode'] not in VALID_UI_MODES:
        return JSONResponse(
            status_code=422, content={'ok': False, 'error': f'ui_mode must be one of: {sorted(VALID_UI_MODES)}'}
        )
    if 'theme' in body and body['theme'] not in VALID_THEMES:
        return JSONResponse(
            status_code=422, content={'ok': False, 'error': f'theme must be one of: {sorted(VALID_THEMES)}'}
        )
    if 'font_size' in body and body['font_size'] not in VALID_FONT_SIZES:
        return JSONResponse(
            status_code=422, content={'ok': False, 'error': f'font_size must be one of: {sorted(VALID_FONT_SIZES)}'}
        )
    if 'skill_level' in body and body['skill_level'] not in VALID_SKILL_LEVELS:
        return JSONResponse(
            status_code=422, content={'ok': False, 'error': f'skill_level must be one of: {sorted(VALID_SKILL_LEVELS)}'}
        )

    updatable = {
        'name',
        'email',
        'avatar',
        'role',
        'skill_level',
        'ui_mode',
        'theme',
        'font_size',
        'sidebar_width',
        'show_tips',
        'show_tour',
        'onboarding_done',
        'onboarding_step',
        'default_agent',
        'default_model',
        'hidden_panes',
        'pinned_panes',
        'sidebar_order',
        'enabled_features',
        'quick_actions',
        'notifications',
    }
    for k in updatable:
        if k not in body:
            continue
        if k == 'name':
            profile[k] = str(body[k])[:100]
        elif k == 'email':
            profile[k] = str(body[k])[:200]
        elif k == 'avatar':
            profile[k] = str(body[k])[:10]
        elif k == 'notifications' and isinstance(body[k], dict):
            profile['notifications'] = {**profile['notifications'], **body[k]}
        elif k == 'enabled_features' and isinstance(body[k], dict):
            profile['enabled_features'] = {**profile['enabled_features'], **body[k]}
        else:
            profile[k] = body[k]

    saved = _save(profile)
    if not saved:
        return JSONResponse(
            status_code=500, content={'ok': False, 'error': 'Profile updated in memory but could not persist to disk'}
        )

    return {'ok': True, 'profile': profile}


@router.post('/role/{role_id}')
def apply_role_defaults(role_id: str):
    """Apply role-based defaults to the profile."""
    if role_id not in ROLE_DEFAULTS:
        return {'ok': False, 'error': f'Unknown role. Valid: {sorted(ROLE_DEFAULTS.keys())}'}
    profile = _load()
    profile['role'] = role_id
    for k, v in ROLE_DEFAULTS[role_id].items():
        profile[k] = v
    _save(profile)
    return {'ok': True, 'role': role_id, 'applied': ROLE_DEFAULTS[role_id]}


@router.post('/toggle-pane/{pane_id}')
def toggle_pane(pane_id: str):
    """Show or hide a pane in the sidebar."""
    pane_id = pane_id.strip()[:50]
    if not pane_id:
        return {'ok': False, 'error': 'pane_id required'}
    profile = _load()
    # Deduplicate before toggling
    hidden = list(dict.fromkeys(profile.get('hidden_panes', [])))
    if pane_id in hidden:
        hidden.remove(pane_id)
        action = 'shown'
    else:
        hidden.append(pane_id)
        action = 'hidden'
    profile['hidden_panes'] = hidden
    _save(profile)
    return {'ok': True, 'pane': pane_id, 'action': action, 'hidden_panes': hidden}


@router.post('/pin-pane/{pane_id}')
def pin_pane(pane_id: str):
    """Pin or unpin a pane."""
    pane_id = pane_id.strip()[:50]
    if not pane_id:
        return {'ok': False, 'error': 'pane_id required'}
    profile = _load()
    pinned = list(dict.fromkeys(profile.get('pinned_panes', [])))
    if pane_id in pinned:
        pinned.remove(pane_id)
        action = 'unpinned'
    else:
        pinned.append(pane_id)
        action = 'pinned'
    profile['pinned_panes'] = pinned
    _save(profile)
    return {'ok': True, 'pane': pane_id, 'action': action, 'pinned_panes': pinned}


@router.post('/sidebar-order')
async def set_sidebar_order(req: Request):
    """Execute or process set sidebar order operation."""
    try:
        try:
            body = await req.json()
        except (KeyError, TypeError, ValueError, json.JSONDecodeError, OSError, AttributeError, RuntimeError):
            body = {}
    except (KeyError, TypeError, ValueError, json.JSONDecodeError, OSError, AttributeError, RuntimeError):
        return {'ok': False, 'error': 'Invalid JSON body'}
    order = body.get('order', [])
    if not isinstance(order, list):
        return {'ok': False, 'error': 'order must be a list'}
    # Validate: only string items, max 100
    order = [str(x)[:50] for x in order if isinstance(x, (str, int))][:100]
    profile = _load()
    profile['sidebar_order'] = order
    _save(profile)
    return {'ok': True, 'sidebar_order': order}


@router.get('/roles')
def list_roles():
    """Retrieve and return list roles."""
    return {
        'roles': [
            {'id': 'developer', 'label': 'Developer', 'icon': '💻', 'desc': 'Code, debug, deploy'},
            {'id': 'analyst', 'label': 'Analyst', 'icon': '📊', 'desc': 'Data, research, reports'},
            {'id': 'writer', 'label': 'Writer', 'icon': '✍️', 'desc': 'Content, prompts, docs'},
            {'id': 'designer', 'label': 'Designer', 'icon': '🎨', 'desc': 'UI, images, prototypes'},
            {'id': 'manager', 'label': 'Manager', 'icon': '📋', 'desc': 'Projects, teams, oversight'},
            {'id': 'student', 'label': 'Student', 'icon': '🎓', 'desc': 'Learning, exploring'},
        ]
    }


@router.post('/complete-onboarding')
async def complete_onboarding(req: Request):
    """Execute or process complete onboarding operation."""
    try:
        try:
            body = await req.json()
        except (KeyError, TypeError, ValueError, json.JSONDecodeError, OSError, AttributeError, RuntimeError):
            body = {}
    except (KeyError, TypeError, ValueError, json.JSONDecodeError, OSError, AttributeError, RuntimeError):
        body = {}
    profile = _load()
    profile['onboarding_done'] = True
    profile['show_tour'] = bool(body.get('show_tour', False))
    if body.get('name'):
        profile['name'] = str(body['name'])[:100]
    if body.get('role') and body['role'] in ROLE_DEFAULTS:
        profile['role'] = body['role']
    elif body.get('role'):
        log.warning("complete-onboarding: unknown role '%s', ignoring", body['role'])
    if body.get('ui_mode') in VALID_UI_MODES:
        profile['ui_mode'] = body['ui_mode']
    # Apply role defaults
    role = profile.get('role', 'developer')
    if role in ROLE_DEFAULTS:
        for k, v in ROLE_DEFAULTS[role].items():
            profile[k] = v
    _save(profile)
    return {'ok': True, 'profile': profile}


@router.get('/ui-config')
def get_ui_config():
    """Get full UI configuration (profile + license) for the frontend boot."""
    profile = _load()
    try:
        from .license import _days_remaining, _effective_tier, _load_license

        lic = _load_license()
        eff_tier = _effective_tier(lic)
        days_left = _days_remaining(lic)
        is_trial = False
    except Exception as exc:
        log.warning('ui-config: license load failed (%s), defaulting to enterprise lifetime', exc)
        eff_tier = 'enterprise'
        days_left = 36500
        is_trial = False

    return {
        'ok': True,
        'profile': profile,
        'tier': eff_tier,
        'days_left': days_left,
        'is_trial': is_trial,
        'ui_mode': profile.get('ui_mode', 'simple'),
        'skill_level': profile.get('skill_level', 'beginner'),
        'hidden_panes': profile.get('hidden_panes', []),
        'pinned_panes': profile.get('pinned_panes', []),
        'onboarding_done': profile.get('onboarding_done', False),
        'show_tour': profile.get('show_tour', True),
    }


@router.get('/export')
def export_profile():
    """Export the full profile as a downloadable JSON snapshot."""
    from fastapi.responses import Response

    profile = _load()
    blob = json.dumps(profile, indent=2, ensure_ascii=False)
    return Response(
        content=blob,
        media_type='application/json',
        headers={'Content-Disposition': 'attachment; filename="agentic-profile.json"'},
    )
