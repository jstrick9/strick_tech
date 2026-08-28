"""
Agentic OS — Onboarding & Preferences Router
First-run wizard, user preferences, workspace settings, keyboard shortcuts.
"""

from __future__ import annotations

import json
import os
import sqlite3
import time

from fastapi import APIRouter, Request
from fastapi.responses import JSONResponse

from ..services.memory_db import audit_log, get_conn, memory_add

router = APIRouter(prefix='/api/onboarding', tags=['onboarding'])

from backend.config import get_data_dir

from ..services.request_body import as_text, json_body_or_error

ROOT = get_data_dir()
PREFS_FILE = ROOT / 'memory' / 'preferences.json'

# ── Default preferences ────────────────────────────────────────────────────────
DEFAULT_PREFS: dict = {
    'onboarding_complete': False,
    'theme': 'dark',  # 'dark' (default) | 'light' | 'auto' | optional visual palettes
    'accent_color': '#5b8af8',
    'font_size': 14,  # integer px
    'font_family': 'Inter',
    'editor_font': 'JetBrains Mono',
    'sidebar_width': 240,
    'chat_stream': True,
    'chat_rag': True,
    'voice_mode': False,
    'tts_voice': 'aria',
    'default_agent': 'default',
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


# ── Preference validation ──────────────────────────────────────────────────────
# BUG FIX: preference KEYS were allowlisted but VALUES were never checked, so
# any type or magnitude was accepted and persisted — font_size:"enormous",
# font_size:99999, sidebar_width:-1 and theme:"not-a-theme" all saved happily
# and then corrupted the UI on the next load (an unusable 99999px font, a
# negative sidebar, a theme with no stylesheet). Values are now coerced and
# bounded, and anything unusable is rejected with a reason.

#: Numeric preferences -> (minimum, maximum)
_NUMERIC_RANGES: dict[str, tuple[int, int]] = {
    'font_size': (10, 32),
    'sidebar_width': (160, 600),
    'auto_save_ms': (100, 60000),
}

#: Preferences restricted to a fixed set of values.
_ENUM_VALUES: dict[str, set[str]] = {
    # 'light'/'auto' are appearance modes; the rest are the visual palettes
    # advertised by GET /api/onboarding/themes.
    'theme': {'dark', 'light', 'auto', 'midnight', 'forest', 'ember', 'ocean'},
    'ui_mode': {'simple', 'power'},
    'default_framework': {'web', 'react', 'vue', 'svelte', 'static', 'node', 'python'},
}

#: Free-text preferences -> maximum length.
_TEXT_LIMITS: dict[str, int] = {
    'accent_color': 32,
    'font_family': 80,
    'editor_font': 80,
    'tts_voice': 40,
    'default_agent': 64,
    'workspace_name': 120,
}


def validate_preference(key: str, value):
    """Coerce and bound one preference value.

    Returns (clean_value, error). `error` is None when the value is usable.
    """
    default = DEFAULT_PREFS.get(key)

    # Booleans first — bool is a subclass of int, so check before the numerics.
    if isinstance(default, bool):
        if isinstance(value, bool):
            return value, None
        if isinstance(value, str) and value.lower() in ('true', 'false'):
            return value.lower() == 'true', None
        return None, f"'{key}' must be true or false"

    if key in _NUMERIC_RANGES:
        low, high = _NUMERIC_RANGES[key]
        try:
            num = int(value)
        except (TypeError, ValueError):
            return None, f"'{key}' must be a number between {low} and {high}"
        # Clamp rather than reject: a slider overshooting its bounds should
        # settle at the limit, not fail the whole save.
        return max(low, min(high, num)), None

    if key in _ENUM_VALUES:
        text = str(value)
        if text not in _ENUM_VALUES[key]:
            allowed = ', '.join(sorted(_ENUM_VALUES[key]))
            return None, f"'{key}' must be one of: {allowed}"
        return text, None

    if key in _TEXT_LIMITS:
        if not isinstance(value, (str, int, float)):
            return None, f"'{key}' must be text"
        return str(value)[: _TEXT_LIMITS[key]], None

    if key == 'shortcuts':
        if not isinstance(value, dict):
            return None, "'shortcuts' must be an object"
        known = set(DEFAULT_PREFS['shortcuts'].keys())
        cleaned = {k: str(v)[:40] for k, v in value.items() if k in known and isinstance(v, (str, int))}
        if not cleaned:
            return None, "'shortcuts' contained no recognised shortcut names"
        return cleaned, None

    # Anything else (first_run_at, version, onboarding_complete handled above)
    # passes through unchanged.
    return value, None


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
        'body': 'Start with a bright, clear workspace, choose a dark workspace, or let the app follow your device automatically.',
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


def _store_openrouter_key(api_key: str) -> bool:
    """Persist an OpenRouter key through the vault's own encryption path.

    Returns False when the key could not be stored ENCRYPTED. Callers must not
    report success in that case -- silently keeping a credential in a weaker
    form than the UI advertises is the failure this helper exists to prevent.
    """
    try:
        from .secrets import _encrypt, _fingerprint

        enc, is_fernet = _encrypt(api_key)
        if not is_fernet:
            return False
        fp = _fingerprint(api_key)
        con = get_conn()
        try:
            con.execute(
                """INSERT INTO secrets(key,value_enc,scope,agent,fingerprint,length,updated_at)
                   VALUES(?,?,?,?,?,?,CURRENT_TIMESTAMP)
                   ON CONFLICT(key) DO UPDATE SET value_enc=excluded.value_enc,
                   scope=excluded.scope, fingerprint=excluded.fingerprint,
                   length=excluded.length, updated_at=CURRENT_TIMESTAMP""",
                ('OPENROUTER_API_KEY', enc, 'global', '', fp, len(api_key)),
            )
            con.commit()
        finally:
            con.close()
    except (KeyError, TypeError, ValueError, json.JSONDecodeError, OSError, AttributeError, RuntimeError, sqlite3.Error):
        return False
    os.environ['OPENROUTER_API_KEY'] = api_key
    return True


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
        return JSONResponse({'ok': False, 'error': f"Unknown preference key '{key}'"}, status_code=404)
    return {'ok': True, 'key': key, 'value': prefs.get(key, DEFAULT_PREFS.get(key))}


@router.patch('/preferences')
async def update_preferences(req: Request):
    """Update one or more preferences (partial update)."""
    body, _body_err = await json_body_or_error(req)
    if _body_err:
        return _body_err
    if not isinstance(body, dict):
        return JSONResponse({'ok': False, 'error': 'body must be a JSON object'}, status_code=400)
    prefs = load_prefs()
    allowed = set(DEFAULT_PREFS.keys())
    updated: dict = {}
    rejected: dict = {}
    for k, v in body.items():
        if k not in allowed:
            continue
        clean, err = validate_preference(k, v)
        if err:
            rejected[k] = err
            continue
        prefs[k] = clean
        updated[k] = clean
    if not updated:
        detail = '; '.join(rejected.values()) if rejected else 'No valid preference keys provided'
        return JSONResponse({'ok': False, 'error': detail, 'rejected': rejected}, status_code=400)
    save_prefs(prefs)
    return {'ok': True, 'updated': updated, 'rejected': rejected, 'preferences': prefs}


@router.put('/preferences')
async def replace_preferences(req: Request):
    """Full replace of preferences (merges with defaults for missing keys)."""
    body, _body_err = await json_body_or_error(req)
    if _body_err:
        return _body_err
    if not isinstance(body, dict):
        return JSONResponse({'ok': False, 'error': 'body must be a JSON object'}, status_code=400)
    # Merge with defaults — only allow known keys, and validate their values.
    allowed = set(DEFAULT_PREFS.keys())
    new_prefs = dict(DEFAULT_PREFS)
    rejected: dict = {}
    for k, v in body.items():
        if k not in allowed:
            continue
        clean, err = validate_preference(k, v)
        if err:
            rejected[k] = err
            continue
        new_prefs[k] = clean
    save_prefs(new_prefs)
    audit_log('preferences_replace', f'{len(body)} keys')
    return {'ok': True, 'preferences': new_prefs, 'rejected': rejected}


@router.delete('/preferences')
def reset_preferences():
    """Reset all preferences to defaults."""
    save_prefs(dict(DEFAULT_PREFS))
    audit_log('preferences_reset', 'reset to defaults')
    return {'ok': True, 'preferences': dict(DEFAULT_PREFS)}


@router.post('/complete')
async def complete_onboarding(req: Request):
    """Mark onboarding as complete and apply final settings."""
    body, _body_err = await json_body_or_error(req)
    if _body_err:
        return _body_err
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
    api_key = as_text(body.get('api_key'))
    if api_key:
        os.environ['OPENROUTER_API_KEY'] = api_key
        # Shares one writer with quick-setup so the two entry points cannot
        # drift into different storage formats again.
        _store_openrouter_key(api_key)

    save_prefs(prefs)

    # Keep the first-run preferences store and the profile store coherent. The
    # frontend reads `/api/profile` for its boot state, while the onboarding
    # wizard persists to `preferences.json`; completing the wizard must update
    # both representations atomically from the user's perspective.
    try:
        from .userprofile import ROLE_DEFAULTS
        from .userprofile import _load as load_profile
        from .userprofile import _save as save_profile

        profile = load_profile()
        profile['onboarding_done'] = True
        if body.get('name'):
            profile['name'] = str(body['name'])[:100]
        if body.get('role') in ROLE_DEFAULTS:
            profile['role'] = body['role']
        if body.get('ui_mode') in {'simple', 'power'}:
            profile['ui_mode'] = body['ui_mode']
        save_profile(profile)
    except (OSError, TypeError, ValueError, KeyError, RuntimeError) as exc:
        # Do not fail a completed onboarding response because a secondary
        # profile write failed; leave a diagnostic trail for local recovery.
        import logging

        logging.getLogger('agentic.onboarding').warning('Profile sync failed: %s', exc)

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


# ═══════════════════════════════════════════════════════════════════════════
#  ONE-CLICK SETUP — Auto-detect and configure the best available AI
# ═══════════════════════════════════════════════════════════════════════════

@router.post('/quick-setup')
async def quick_setup(req: Request):
    """One-click setup: auto-detect available AI backends and configure the best one.

    Checks (in order):
    1. Ollama running locally — zero config needed
    2. OpenRouter API key in env — immediate access to 140+ models
    3. Custom endpoint configured — use whatever's available

    Returns the configured model and connection status.
    """
    import os
    body = {}
    try:
        body = await req.json()
    except Exception:
        pass

    api_key = body.get('api_key', '').strip()

    results = []

    # Check 1: Ollama local
    ollama_ok = False
    ollama_models = []
    try:
        import httpx as _httpx
        async with _httpx.AsyncClient(timeout=3) as c:
            r = await c.get('http://127.0.0.1:11434/api/tags')
            if r.status_code == 200:
                ollama_ok = True
                ollama_models = [m.get('name', '') for m in r.json().get('models', [])]
                results.append({'backend': 'ollama', 'status': 'available', 'models': len(ollama_models)})
    except Exception:
        results.append({'backend': 'ollama', 'status': 'not_running'})

    # Check 2: OpenRouter (from env or provided key)
    or_key = api_key or os.getenv('OPENROUTER_API_KEY', '')
    or_ok = False
    if or_key:
        try:
            import httpx as _httpx
            async with _httpx.AsyncClient(timeout=5) as c:
                # BUG FIX: this probed GET /api/v1/models, which is PUBLIC on
                # OpenRouter -- it answers 200 with the full catalogue for a
                # garbage key, a revoked key, or no Authorization header at all.
                # So the setup wizard reported "OpenRouter connected. 140+ models
                # available" for any string the user typed, then every chat
                # failed. Verified live: key 'sk-or-v1-total-garbage-not-a-real-
                # key' -> status 'available', models 401.
                # This is the same defect already fixed in
                # /api/secrets/test-connection; the wizard was its second door.
                # /api/v1/auth/key is the authenticated endpoint (401 on a bad key).
                auth = await c.get(
                    'https://openrouter.ai/api/v1/auth/key', headers={'Authorization': f'Bearer {or_key}'}
                )
                if auth.status_code == 200:
                    or_ok = True
                    models = 0
                    try:
                        rm = await c.get(
                            'https://openrouter.ai/api/v1/models',
                            headers={'Authorization': f'Bearer {or_key}'},
                        )
                        if rm.status_code == 200:
                            models = len(rm.json().get('data', []))
                    except Exception:
                        pass
                    results.append({'backend': 'openrouter', 'status': 'available', 'models': models})
                elif auth.status_code in (401, 403):
                    results.append({'backend': 'openrouter', 'status': 'invalid_key'})
                else:
                    results.append(
                        {'backend': 'openrouter', 'status': 'unreachable', 'http_status': auth.status_code}
                    )
        except Exception:
            results.append({'backend': 'openrouter', 'status': 'unreachable'})
    else:
        results.append({'backend': 'openrouter', 'status': 'no_key'})

    # Determine best config
    recommended = {}
    if ollama_ok and ollama_models:
        recommended = {
            'backend': 'ollama',
            'model': ollama_models[0],
            'message': f'Ollama detected with {len(ollama_models)} model(s). Ready to use — no API key needed.',
        }
    elif or_ok:
        recommended = {
            'backend': 'openrouter',
            'model': 'claude',
            'message': 'OpenRouter connected. 140+ models available including Claude, GPT-4o, Gemini, Llama.',
        }
    else:
        recommended = {
            'backend': 'none',
            'model': '',
            'message': 'No AI backend detected. Install Ollama (ollama.com) for free local AI, or add an OpenRouter API key in Settings.',
        }

    # Save API key if provided.
    #
    # BUG FIX: this wrote the raw API key straight into secrets.value_enc -- the
    # column every other writer fills with a Fernet token. Three things followed
    # from that, all verified live:
    #   1. The key sat in the SQLite file in PLAINTEXT while the Secrets Vault
    #      screen displayed it with a 🔒 badge and the banner "AES-256 Fernet
    #      Encryption Active".
    #   2. fingerprint and length were left NULL, so the vault listed it as
    #      "0 chars".
    #   3. _decrypt() could not read it back, so _inject_to_env() skipped it on
    #      every restart and "Reveal" returned an empty string. The key the user
    #      pasted into the setup wizard never actually reached the LLM client.
    # Routing through the vault's own _encrypt keeps one writer, one format.
    # Only persist a key the provider actually accepted. Storing a rejected key
    # overwrites a previously working one and injects it into os.environ.
    if api_key and not or_ok:
        return JSONResponse(
            {
                'ok': False,
                'backends': results,
                'error': 'OpenRouter rejected this API key. It was not saved. '
                'Check that it is correct and still active.',
            },
            status_code=400,
        )
    if api_key:
        _stored = _store_openrouter_key(api_key)
        if not _stored:
            return JSONResponse(
                {
                    'ok': False,
                    'error': 'Could not store the API key securely (encrypted vault unavailable). '
                    'Install the cryptography package and try again.',
                },
                status_code=503,
            )

    # Update preferences
    prefs = load_prefs()
    prefs['setup_complete'] = True
    if recommended.get('model'):
        prefs['default_model'] = recommended['model']
    save_prefs(prefs)

    return {
        'ok': True,
        'backends': results,
        'recommended': recommended,
        'ollama_models': ollama_models[:10] if ollama_models else [],
        'setup_time_ms': 0,
    }


@router.get('/quick-setup/status')
async def quick_setup_status():
    """Check current AI connection status without re-configuring."""
    import os
    status = {'ollama': False, 'openrouter': False, 'models': []}

    try:
        import httpx as _httpx
        async with _httpx.AsyncClient(timeout=2) as c:
            r = await c.get('http://127.0.0.1:11434/api/tags')
            if r.status_code == 200:
                status['ollama'] = True
                status['models'] = [m.get('name', '') for m in r.json().get('models', [])]
    except Exception:
        pass

    if os.getenv('OPENROUTER_API_KEY'):
        status['openrouter'] = True

    return {'ok': True, 'status': status}


# ── local model auto-detection ────────────────────────────────────────────────
# REPORTED: "The Ollama localhost did not auto connect."
#
# Detection code already existed, but ONLY inside POST /quick-setup, which the
# frontend calls from a button in Settings. Nothing ran at launch, so a local
# Ollama with models installed stayed invisible until the user went looking for
# it. This is the standalone probe the frontend can call on boot.


@router.get('/detect-local-models')
async def detect_local_models() -> dict:
    """Probe for a local Ollama and report what it has. Read-only, never raises.

    Honours OLLAMA_BASE_URL. The pre-existing probe inside quick-setup
    hardcoded 127.0.0.1:11434, so anyone running Ollama on another host or
    port was undetectable no matter how the app was configured.

    A missing Ollama is a normal state, not an error: this returns
    `available: false` and the caller stays quiet. Surfacing a scary message
    to someone who never wanted local models is worse than saying nothing.
    """
    base = os.getenv('OLLAMA_BASE_URL', 'http://127.0.0.1:11434').rstrip('/')
    # Accept an OpenAI-compatible base URL and normalise it back to the native
    # API root, since that is what people paste from other tools' docs.
    base = base.removesuffix('/v1').rstrip('/')

    out: dict = {
        'ok': True,
        'backend': 'ollama',
        'base_url': base,
        'available': False,
        'models': [],
        'suggested_model': '',
    }
    try:
        import httpx as _httpx

        async with _httpx.AsyncClient(timeout=3) as c:
            r = await c.get(f'{base}/api/tags')
        if r.status_code != 200:
            out['error'] = f'HTTP {r.status_code}'
            return out
        models = [str(m.get('name', '')) for m in (r.json().get('models') or [])]
        models = [m for m in models if m]
    except Exception as exc:
        # Not running is the common case and is not an error worth shouting
        # about; record the reason for the diagnostic and move on.
        out['error'] = type(exc).__name__
        return out

    out['available'] = bool(models)
    out['models'] = models
    out['suggested_model'] = _suggest_local_model(models)
    return out


# Preference order for an automatic default. Instruct/chat-tuned general models
# first; embedding-only and vision-only models are never a sensible default for
# a chat box, and a code model is a poor general assistant.
_LOCAL_MODEL_PREFERENCE = (
    'llama3.1', 'llama3.2', 'llama3', 'qwen2.5', 'qwen3', 'mistral',
    'gemma2', 'gemma3', 'phi4', 'phi3',
)
# Substrings that mark a model as unusable as a general chat default.
# 'minilm', 'gte' and 'e5' are here because they are common embedding families
# whose names contain none of the obvious markers -- 'all-minilm' slipped
# through an earlier version of this list and was suggested as a chat model,
# which fails on the first message with an opaque provider error.
_LOCAL_MODEL_EXCLUDE = (
    'embed', 'embedding', 'clip', 'vision', 'rerank', 'bge', 'nomic',
    'minilm', 'gte-', 'e5-', 'mxbai', 'snowflake-arctic-embed', 'paraphrase',
)


def _suggest_local_model(models: list[str]) -> str:
    """Pick a sane default from what is installed, or nothing.

    Returning '' when only embedding models are present is deliberate: an
    embedding model selected as the chat default fails on the first message
    with an opaque error, which is worse than leaving the field unset.
    """
    usable = [m for m in models
              if not any(bad in m.lower() for bad in _LOCAL_MODEL_EXCLUDE)]
    if not usable:
        return ''
    for family in _LOCAL_MODEL_PREFERENCE:
        for m in usable:
            if m.lower().startswith(family):
                return m
    return usable[0]
