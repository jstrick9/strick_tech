"""
Agentic OS — Onboarding & Preferences Router
First-run wizard, user preferences, workspace settings, keyboard shortcuts.
"""

from __future__ import annotations

import contextlib

import json
import os
import time
from pathlib import Path

from fastapi import APIRouter, Request

from ..services.memory_db import audit_log, get_conn, memory_add

router = APIRouter(prefix='/api/onboarding', tags=['onboarding'])

from backend.config import get_data_dir
ROOT = get_data_dir()
PREFS_FILE = ROOT / 'memory' / 'preferences.json'

# ── Default preferences ────────────────────────────────────────────────────────
DEFAULT_PREFS: dict = {
    'onboarding_complete': False,
    'theme': 'dark',  # "dark" | "midnight" | "forest" | "ember" | "ocean"
    'accent_color': '#5b8af8',
    'font_size': 14,  # integer px
    'font_family': 'Inter',
    'editor_font': 'JetBrains Mono',
    'sidebar_width': 240,
    'chat_stream': True,
    'chat_rag': True,
    'voice_mode': False,
    'tts_voice': 'aria',
    'default_agent': 'brain',
    'hmr_enabled': True,
    'auto_save_ms': 600,
    'default_framework': 'web',
    'workspace_name': 'My Agentic OS',
    'show_cost_bar': True,
    'notifications': True,
    'ui_mode': 'simple',  # "simple" | "power"
    'shortcuts': {
        'palette': 'ctrl+k',
        'send_chat': 'enter',
        'save_file': 'ctrl+s',
        'new_agent': 'ctrl+shift+a',
        'run_swarm': 'ctrl+shift+s',
        'run_e2e': 'ctrl+shift+t',
    },
    'first_run_at': None,
    'version': '6.0',
}


def load_prefs() -> dict:
    """Load preferences from disk, merging with defaults for any missing keys."""
    # Try the correct path first, then fall back to legacy wrong path and migrate
    for prefs_path in [PREFS_FILE, ROOT.parent / 'memory' / 'preferences.json']:
        if prefs_path.exists():
            try:
                data = json.loads(prefs_path.read_text(encoding='utf-8'))
                if not isinstance(data, dict):
                    continue
                merged = {**DEFAULT_PREFS, **data}
                # If loaded from legacy path, migrate to correct path
                if prefs_path != PREFS_FILE:
                    save_prefs(merged)
                return merged
            except (KeyError, TypeError, ValueError, json.JSONDecodeError, OSError, AttributeError, RuntimeError):
                continue
    return dict(DEFAULT_PREFS)


def save_prefs(prefs: dict):
    """Persist preferences to disk."""
    PREFS_FILE.parent.mkdir(parents=True, exist_ok=True)
    PREFS_FILE.write_text(json.dumps(prefs, indent=2, ensure_ascii=False), encoding='utf-8')


# ── Onboarding steps ───────────────────────────────────────────────────────────
ONBOARDING_STEPS = [
    {
        'id': 'welcome',
        'title': 'Welcome to Agentic OS 🧠',
        'subtitle': 'Your local-first AI operating system',
        'body': "You have a full team of AI agents, a live code editor, memory galaxy, and more — all running on your machine. Let's get set up in 3 minutes.",
        'action': None,
        'skip': False,
    },
    {
        'id': 'api_key',
        'title': 'Connect your AI 🔑',
        'subtitle': 'One key unlocks Claude, GPT-4o, Gemini, Grok, Llama, and more',
        'body': "Agentic OS uses OpenRouter as a single gateway to all major AI models. It's free to start and you only pay for what you use.",
        'action': {'label': 'Get free API key', 'url': 'https://openrouter.ai/keys'},
        'input': {'id': 'api_key', 'label': 'OPENROUTER_API_KEY', 'type': 'password', 'placeholder': 'sk-or-v1-…'},
        'skip': True,
    },
    {
        'id': 'workspace',
        'title': 'Name your workspace 🏠',
        'subtitle': 'What are you building?',
        'body': 'This helps your agents understand your context and give better responses.',
        'input': {
            'id': 'workspace_name',
            'label': 'Workspace name',
            'type': 'text',
            'placeholder': 'e.g. My AI Agency, Solo Founder OS, Dev Studio',
        },
        'action': None,
        'skip': False,
    },
    {
        'id': 'agents',
        'title': 'Meet your team 🤖',
        'subtitle': '8 specialist agents ready to work',
        'body': 'Brain thinks deep, Builder codes, Researcher finds, Reviewer critiques, Creative writes, Orchestrator coordinates. You can create custom agents anytime.',
        'action': None,
        'skip': False,
    },
    {
        'id': 'first_task',
        'title': 'Create your first task 📋',
        'subtitle': 'Drop something into your Kanban board',
        'body': 'What do you want to build or accomplish? Add it as a task and assign it to an agent.',
        'action': {'label': 'Open Kanban', 'nav': 'kanban'},
        'skip': True,
    },
    {
        'id': 'theme',
        'title': 'Pick your vibe 🎨',
        'subtitle': 'Choose a theme for Mission Control',
        'body': 'All themes are fully dark to protect your eyes during long builds.',
        'action': None,
        'skip': False,
    },
    {
        'id': 'done',
        'title': "You're ready 🚀",
        'subtitle': 'Agentic OS is fully configured',
        'body': 'Start chatting with an agent, scaffold a project, run the swarm, or explore your Memory Galaxy. Press ⌘K anytime to search everything.',
        'action': {'label': 'Start building', 'nav': 'chat'},
        'skip': False,
    },
]

THEMES = [
    {'id': 'dark', 'name': 'Dark', 'bg': '#08090e', 'accent': '#5b8af8', 'preview': 'Deep space — default'},
    {
        'id': 'midnight',
        'name': 'Midnight',
        'bg': '#050810',
        'accent': '#9d74f5',
        'preview': 'Pure black — OLED friendly',
    },
    {'id': 'forest', 'name': 'Forest', 'bg': '#0a100d', 'accent': '#4cc98a', 'preview': 'Green-tinted dark'},
    {'id': 'ember', 'name': 'Ember', 'bg': '#100a08', 'accent': '#f08850', 'preview': 'Warm dark — easy on eyes'},
    {'id': 'ocean', 'name': 'Ocean', 'bg': '#080d10', 'accent': '#38c5d8', 'preview': 'Cool blue dark'},
]

KEYBOARD_SHORTCUTS = [
    {'keys': ['⌘', 'K'], 'label': 'Command Palette'},
    {'keys': ['Enter'], 'label': 'Send chat message'},
    {'keys': ['Shift', 'Enter'], 'label': 'New line in chat'},
    {'keys': ['⌘', 'S'], 'label': 'Save file in editor'},
    {'keys': ['⌘', 'Z'], 'label': 'Undo in editor'},
    {'keys': ['⌘', 'Shift', 'Z'], 'label': 'Redo in editor'},
    {'keys': ['F7'], 'label': 'Next diff'},
    {'keys': ['F8'], 'label': 'Previous diff'},
    {'keys': ['Esc'], 'label': 'Close modal / palette'},
    {'keys': ['Tab'], 'label': 'Accept autocomplete'},
    {'keys': ['⌘', 'Shift', 'A'], 'label': 'New agent (planned)'},
    {'keys': ['⌘', 'Shift', 'S'], 'label': 'Run swarm (planned)'},
    {'keys': ['⌘', '/'], 'label': 'Focus chat input'},
    {'keys': ['Ctrl', 'Shift', 'V'], 'label': 'Toggle voice coding'},
    {'keys': ['Ctrl', 'Shift', 'M'], 'label': 'Toggle voice mode (TTS)'},
]


# ── Endpoints ──────────────────────────────────────────────────────────────────


@router.get('/status')
def onboarding_status():
    """Return onboarding completion status and key preferences."""
    prefs = load_prefs()
    return {
        'complete': prefs.get('onboarding_complete', False),
        'workspace_name': prefs.get('workspace_name', ''),
        'api_key_set': bool(os.getenv('OPENROUTER_API_KEY')),
        'step_count': len(ONBOARDING_STEPS),
        'theme': prefs.get('theme', 'dark'),
        'accent_color': prefs.get('accent_color', '#5b8af8'),
        'ui_mode': prefs.get('ui_mode', 'simple'),
        'first_run_at': prefs.get('first_run_at'),
    }


@router.get('/steps')
def get_steps():
    """Return all onboarding wizard steps."""
    return ONBOARDING_STEPS


@router.get('/themes')
def get_themes():
    """Return available UI themes."""
    return THEMES


@router.get('/shortcuts')
def get_shortcuts():
    """Return keyboard shortcut reference."""
    return KEYBOARD_SHORTCUTS


@router.get('/preferences')
def get_preferences():
    """Return all user preferences."""
    return load_prefs()


@router.get('/preferences/{key}')
def get_preference_key(key: str):
    """Get a single preference value by key."""
    prefs = load_prefs()
    if key not in DEFAULT_PREFS:
        return {'ok': False, 'error': f"Unknown preference key '{key}'"}
    return {'ok': True, 'key': key, 'value': prefs.get(key, DEFAULT_PREFS.get(key))}


@router.patch('/preferences')
async def update_preferences(req: Request):
    """Update one or more preferences (partial update)."""
    try:
        body = await req.json()
    except (json.JSONDecodeError, TypeError, ValueError):
        body = {}
    if not isinstance(body, dict):
        return {'ok': False, 'error': 'body must be a JSON object'}
    prefs = load_prefs()
    allowed = set(DEFAULT_PREFS.keys())
    updated = {}
    for k, v in body.items():
        if k in allowed:
            prefs[k] = v
            updated[k] = v
    if not updated:
        return {'ok': False, 'error': 'No valid preference keys provided'}
    save_prefs(prefs)
    return {'ok': True, 'updated': updated, 'preferences': prefs}


@router.put('/preferences')
async def replace_preferences(req: Request):
    """Full replace of preferences (merges with defaults for missing keys)."""
    try:
        body = await req.json()
    except (json.JSONDecodeError, TypeError, ValueError):
        body = {}
    if not isinstance(body, dict):
        return {'ok': False, 'error': 'body must be a JSON object'}
    # Merge with defaults — only allow known keys
    allowed = set(DEFAULT_PREFS.keys())
    new_prefs = dict(DEFAULT_PREFS)
    for k, v in body.items():
        if k in allowed:
            new_prefs[k] = v
    save_prefs(new_prefs)
    audit_log('preferences_replace', f'{len(body)} keys')
    return {'ok': True, 'preferences': new_prefs}


@router.delete('/preferences')
def reset_preferences():
    """Reset all preferences to defaults."""
    save_prefs(dict(DEFAULT_PREFS))
    audit_log('preferences_reset', 'reset to defaults')
    return {'ok': True, 'preferences': dict(DEFAULT_PREFS)}


@router.post('/complete')
async def complete_onboarding(req: Request):
    """Mark onboarding as complete and apply final settings."""
    try:
        body = await req.json()
    except (json.JSONDecodeError, TypeError, ValueError):
        body = {}
    prefs = load_prefs()
    prefs['onboarding_complete'] = True
    prefs['first_run_at'] = time.strftime('%Y-%m-%dT%H:%M:%S')

    # Apply any settings from final step
    for k in [
        'workspace_name',
        'theme',
        'accent_color',
        'default_agent',
        'voice_mode',
        'tts_voice',
        'ui_mode',
        'font_size',
    ]:
        if k in body:
            prefs[k] = body[k]

    # Save API key to vault if provided
    api_key = (body.get('api_key') or '').strip()
    if api_key:
        os.environ['OPENROUTER_API_KEY'] = api_key
        try:
            from .secrets import _encrypt, _fingerprint

            enc, _ = _encrypt(api_key)
            fp = _fingerprint(api_key)
            con = get_conn()
            try:
                con.execute(
                    """INSERT INTO secrets(key,value_enc,scope,fingerprint,length,updated_at)
                       VALUES(?,?,?,?,?,CURRENT_TIMESTAMP)
                       ON CONFLICT(key) DO UPDATE SET value_enc=excluded.value_enc,
                       fingerprint=excluded.fingerprint,length=excluded.length,
                       updated_at=CURRENT_TIMESTAMP""",
                    ('OPENROUTER_API_KEY', enc, 'global', fp, len(api_key)),
                )
                con.commit()
            finally:
                con.close()
        except (KeyError, TypeError, ValueError, json.JSONDecodeError, OSError, AttributeError, RuntimeError):
            # Non-fatal: preferences still saved, just no vault entry
            pass

    save_prefs(prefs)
    audit_log('onboarding_complete', prefs.get('workspace_name', ''))
    memory_add(
        'system',
        f"Workspace '{prefs.get('workspace_name', 'Agentic OS')}' initialized via onboarding.",
        'system,onboarding',
    )
    return {'ok': True, 'preferences': prefs}


@router.post('/reset')
def reset_onboarding():
    """Re-trigger onboarding (for testing or fresh start)."""
    prefs = load_prefs()
    prefs['onboarding_complete'] = False
    prefs['first_run_at'] = None
    save_prefs(prefs)
    audit_log('onboarding_reset', '')
    return {'ok': True}
