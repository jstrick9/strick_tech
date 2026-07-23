"""
Agentic OS — Voice Coding Router
Voice commands, speech-to-text, voice-controlled navigation.
Uses browser WebSpeech API on frontend; backend handles command routing.
"""

from __future__ import annotations

import contextlib

import json
import logging
import re
import time

from fastapi import APIRouter, Request

router = APIRouter(prefix='/api/voice', tags=['voice'])
log = logging.getLogger('agentic.voice')

# ── In-memory command history (last 100 commands) ─────────────────────────────
_HISTORY: list[dict] = []
_MAX_HISTORY = 100


# ── Voice command registry ────────────────────────────────────────────────────
# IMPORTANT: More specific patterns must come BEFORE more generic ones.
# e.g. open_file (matches file extensions) must come before navigate (matches any word).
VOICE_COMMANDS = [
    # Files — must be before navigate to avoid "open index.html" → navigate
    {
        'pattern': r'(?:create|new|make)\s+(?:a\s+)?(?:file\s+)?(?:called\s+)?(.+\.(?:py|js|ts|html|css|json|md|yaml|yml|sh|txt))',
        'action': 'create_file',
        'example': 'create a file called app.py',
    },
    {
        'pattern': r'(?:open|edit|show)\s+(.+\.(?:py|js|ts|html|css|json|md|yaml|yml|sh|txt))',
        'action': 'open_file',
        'example': 'open index.html',
    },
    # Agent control
    {
        'pattern': r'(?:run|start|execute)\s+(?:the\s+)?(.+?)\s+agent',
        'action': 'run_agent',
        'example': 'run the researcher agent',
    },
    {'pattern': r'(?:stop|kill|cancel)\s+(?:all\s+)?agents?', 'action': 'stop_agents', 'example': 'stop all agents'},
    # Workflow — before run tests to avoid conflict
    {
        'pattern': r'(?:run|start|execute)\s+(?:workflow|flow)\s+(.+)',
        'action': 'run_workflow',
        'example': 'run workflow code review',
    },
    # Code actions
    {'pattern': r'(?:run|execute)\s+(?:the\s+)?tests?', 'action': 'run_tests', 'example': 'run tests'},
    {
        'pattern': r'(?:deploy|ship|publish)\s+(?:the\s+)?(?:app|project)?',
        'action': 'deploy',
        'example': 'deploy the app',
    },
    {
        'pattern': r'(?:save|commit)\s+(?:the\s+)?(?:file|changes|everything)?',
        'action': 'save',
        'example': 'save the file',
    },
    {'pattern': r'(?:undo|revert)\s+(?:last\s+)?(?:change|edit)?', 'action': 'undo', 'example': 'undo last change'},
    # Chat — must be before navigate "tell" could match
    {
        'pattern': r'(?:send|say|tell the agent|tell ai|tell agentic)\s+(.+)',
        'action': 'chat_send',
        'example': 'tell the agent to build a login form',
    },
    # Search
    {
        'pattern': r'(?:search|find|look for)\s+(?:for\s+)?(.+)',
        'action': 'search',
        'example': 'search for authentication',
    },
    # Settings — before navigate "change" matches
    {
        'pattern': r'(?:change|switch|use)\s+(?:model\s+to\s+|to\s+model\s+|the\s+model\s+to\s+)?(.+?)\s+model',
        'action': 'change_model',
        'example': 'change to GPT-4 model',
    },
    # Shortcuts — must come BEFORE generic navigate to avoid "open command palette" → navigate
    {
        'pattern': r'(?:open|show)\s+(?:the\s+)?(?:command\s+)?palette',
        'action': 'command_palette',
        'example': 'open command palette',
    },
    {'pattern': r'(?:toggle|show|hide)\s+sidebar', 'action': 'toggle_sidebar', 'example': 'toggle sidebar'},
    {'pattern': r'(?:new|create)\s+(?:a\s+)?(?:chat|conversation)', 'action': 'new_chat', 'example': 'new chat'},
    {'pattern': r'(?:clear|reset)\s+(?:the\s+)?chat', 'action': 'clear_chat', 'example': 'clear chat'},
    # Navigation — multi-word pane names captured with .+? then resolved
    {
        'pattern': r'(?:go to|navigate to|show)\s+(?:the\s+)?(.+?)(?:\s+pane|\s+tab)?$',
        'action': 'navigate',
        'example': 'go to chat / navigate to knowledge graph',
    },
    {
        'pattern': r'(?:open|switch|change)\s+(?:to\s+)?(?:the\s+)?(.+?)(?:\s+pane|\s+tab)?$',
        'action': 'navigate',
        'example': 'open terminal / switch to kanban',
    },
    # Help
    {
        'pattern': r'(?:help|what can you do|show commands|voice commands|show help)',
        'action': 'help',
        'example': 'help / voice commands',
    },
]

PANE_ALIASES = {
    # Chat
    'chat': 'chat',
    'conversation': 'chat',
    # Studio / editor
    'code': 'studio',
    'studio': 'studio',
    'editor': 'studio',
    'monaco': 'studio',
    # Kanban
    'board': 'kanban',
    'kanban': 'kanban',
    'tasks': 'kanban',
    'task board': 'kanban',
    # Memory / galaxy
    'memory': 'galaxy',
    'galaxy': 'galaxy',
    'graph': 'galaxy',
    'memory galaxy': 'galaxy',
    # Deploy
    'deploy': 'deploy',
    'deployment': 'deploy',
    'deployments': 'deploy',
    # GitHub
    'github': 'github',
    'git': 'github',
    'version control': 'github',
    # Terminal
    'terminal': 'terminal',
    'console': 'terminal',
    'shell': 'terminal',
    # Database
    'database': 'dbstudio',
    'db': 'dbstudio',
    'db studio': 'dbstudio',
    'sql': 'dbstudio',
    # Settings
    'settings': 'settings',
    'config': 'settings',
    'configuration': 'settings',
    # Plugins
    'plugins': 'plugins',
    'plugin': 'plugins',
    'marketplace': 'marketplace',
    # Workflow
    'workflow': 'workflow',
    'workflows': 'workflow',
    'flow': 'workflow',
    # Specs
    'spec': 'specs',
    'specs': 'specs',
    'specifications': 'specs',
    # Arena
    'arena': 'arena',
    'model arena': 'arena',
    # Hooks
    'hooks': 'hooks',
    'hook': 'hooks',
    'events': 'hooks',
    # Profiler
    'profiler': 'profiler',
    'performance': 'profiler',
    # Replay
    'replay': 'replay',
    # Dashboard
    'dashboard': 'dashboard',
    'analytics': 'dashboard',
    'overview': 'dashboard',
    # Image gen
    'images': 'imagegen',
    'imagegen': 'imagegen',
    'image generation': 'imagegen',
    # Swarm
    'swarm': 'swarm',
    'multi agent': 'swarm',
    # Loops
    'loops': 'loops',
    'loop': 'loops',
    'autonomous': 'loops',
    # Prompts
    'prompts': 'prompts',
    'prompt library': 'prompts',
    # MCP
    'mcp': 'mcp',
    # Control tower
    'control': 'control',
    'tower': 'control',
    'control tower': 'control',
    # Knowledge graph
    'knowledge': 'knowledge-graph',
    'knowledge graph': 'knowledge-graph',
    # Code search
    'codesearch': 'codesearch',
    'code search': 'codesearch',
    'search code': 'codesearch',
    'find code': 'codesearch',
    # Fusion
    'fusion': 'fusion',
    'model fusion': 'fusion',
    # HITL
    'hitl': 'hitl',
    'approval': 'hitl',
    'human in the loop': 'hitl',
    # Browser
    'browser': 'browser',
    'browser agent': 'browser',
    # Web search
    'websearch': 'websearch',
    'web search': 'websearch',
    'search web': 'websearch',
    # Leaderboard
    'leaderboard': 'leaderboard',
    'agent leaderboard': 'leaderboard',
    # Obsidian
    'obsidian': 'obsidian',
    'vault': 'obsidian',
    # Secrets
    'secrets': 'secrets',
    'vault secrets': 'secrets',
    # Webhooks
    'webhooks': 'webhooks',
    'webhook': 'webhooks',
    # TTS
    'tts': 'settings',
    'voice settings': 'settings',
}


@router.post('/parse')
async def parse_voice_command(req: Request):
    """Parse a voice transcript into an actionable command."""
    try:
        body = await req.json()
    except (json.JSONDecodeError, TypeError, ValueError):
        body = {}
    transcript = (body.get('transcript') or '').strip()

    if not transcript:
        return {'ok': False, 'error': 'transcript required'}

    transcript_lower = transcript.lower().strip()

    # Try each command pattern
    matched_action = None
    matched_payload = ''
    matched_pattern = 'fallback_chat'

    for cmd in VOICE_COMMANDS:
        m = re.search(cmd['pattern'], transcript_lower, re.IGNORECASE)
        if m:
            action = cmd['action']
            payload = m.group(1).strip() if m.lastindex and m.lastindex >= 1 else ''

            # Resolve pane aliases for navigation
            if action == 'navigate':
                # Try full payload first, then first word
                resolved = PANE_ALIASES.get(payload.lower())
                if not resolved:
                    first_word = payload.split()[0] if payload else ''
                    resolved = PANE_ALIASES.get(first_word.lower(), payload.lower())
                payload = resolved

            matched_action = action
            matched_payload = payload
            matched_pattern = cmd['pattern']
            break

    # Fallback: treat as chat message
    if not matched_action:
        matched_action = 'chat_send'
        matched_payload = transcript_lower
        matched_pattern = 'fallback_chat'

    result = {
        'ok': True,
        'action': matched_action,
        'payload': matched_payload,
        'transcript': transcript_lower,
        'matched': matched_pattern,
    }

    # Persist to history
    _HISTORY.insert(0, {**result, 'ts': int(time.time())})
    if len(_HISTORY) > _MAX_HISTORY:
        _HISTORY.pop()

    return result


@router.post('/parse/batch')
async def parse_batch(req: Request):
    """Parse multiple transcripts in one call."""
    try:
        body = await req.json()
    except (json.JSONDecodeError, TypeError, ValueError):
        body = {}
    transcripts = body.get('transcripts', [])
    if not transcripts or not isinstance(transcripts, list):
        return {'ok': False, 'error': 'transcripts list required'}

    results = []
    for t in transcripts[:20]:
        t = (t or '').strip()
        if not t:
            continue
        # Inline parse (reuse logic)
        t_lower = t.lower()
        matched = None
        for cmd in VOICE_COMMANDS:
            m = re.search(cmd['pattern'], t_lower, re.IGNORECASE)
            if m:
                action = cmd['action']
                payload = m.group(1).strip() if m.lastindex and m.lastindex >= 1 else ''
                if action == 'navigate':
                    resolved = PANE_ALIASES.get(payload.lower())
                    if not resolved:
                        first_word = payload.split()[0] if payload else ''
                        resolved = PANE_ALIASES.get(first_word.lower(), payload.lower())
                    payload = resolved
                matched = {'ok': True, 'action': action, 'payload': payload, 'transcript': t_lower}
                break
        if not matched:
            matched = {'ok': True, 'action': 'chat_send', 'payload': t_lower, 'transcript': t_lower}
        results.append(matched)

    return {'ok': True, 'results': results, 'count': len(results)}


@router.get('/commands')
def list_commands():
    """List all available voice commands."""
    return {
        'commands': [
            {
                'action': c['action'],
                'example': c['example'],
                'pattern': c['pattern'],
            }
            for c in VOICE_COMMANDS
        ],
        'pane_aliases': PANE_ALIASES,
        'count': len(VOICE_COMMANDS),
        'pane_count': len(set(PANE_ALIASES.values())),
    }


@router.get('/history')
def get_history(limit: int = 50):
    """Return recent voice command history."""
    limit = min(max(1, limit), 100)
    return {
        'history': _HISTORY[:limit],
        'count': len(_HISTORY),
    }


@router.delete('/history')
def clear_history():
    """Clear voice command history."""
    _HISTORY.clear()
    return {'ok': True}


@router.get('/session')
def get_session():
    """Return current voice session state."""
    return {
        'ok': True,
        'history_count': len(_HISTORY),
        'last_command': _HISTORY[0] if _HISTORY else None,
        'panes_available': sorted(set(PANE_ALIASES.values())),
        'actions_available': sorted({c['action'] for c in VOICE_COMMANDS}),
    }


@router.post('/synthesize')
async def synthesize_speech(req: Request):
    """Synthesize text to speech for voice feedback (delegates to TTS router)."""
    try:
        body = await req.json()
    except (json.JSONDecodeError, TypeError, ValueError):
        body = {}
    text = (body.get('text') or '').strip()[:500]
    voice = (body.get('voice') or 'aria').strip()
    rate = (body.get('rate') or '+0%').strip()

    if not text:
        return {'ok': False, 'error': 'text required'}

    try:
        from ..routers.tts import DEFAULT_VOICE, EDGE_VOICES, _edge_tts, _strip_markdown

        edge_voice = EDGE_VOICES.get(voice, EDGE_VOICES.get(DEFAULT_VOICE, 'en-US-AriaNeural'))
        clean_text = _strip_markdown(text)
        if not clean_text.strip():
            return {'ok': False, 'error': 'no speakable text'}
        audio_bytes = await _edge_tts(clean_text, edge_voice, rate)
        from fastapi.responses import StreamingResponse

        return StreamingResponse(iter([audio_bytes]), media_type='audio/mpeg')
    except ImportError:
        return {'ok': False, 'error': 'edge-tts not installed. Run: pip install edge-tts'}
    except Exception as ex:
        return {'ok': False, 'error': str(ex), 'text': text}


@router.get('/config')
def voice_config():
    """Return voice configuration for the frontend."""
    return {
        'enabled': True,
        'recognition_lang': 'en-US',
        'synthesis_lang': 'en-US',
        'default_voice': 'en-US-AriaNeural',
        'commands_count': len(VOICE_COMMANDS),
        'pane_aliases_count': len(PANE_ALIASES),
        'push_to_talk_key': 'Ctrl+Shift+V',
        'continuous_mode': False,
        'feedback_tts': True,
        'wake_word': 'hey agentic',
        'shortcuts': {
            'start_listening': 'Ctrl+Shift+V',
            'stop_listening': 'Escape',
            'toggle_voice_mode': 'Ctrl+Shift+M',
        },
        'supported_browsers': ['Chrome', 'Edge', 'Safari'],
    }
