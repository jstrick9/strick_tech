"""
Agentic OS — TTS (Text-to-Speech) Router
Uses edge-tts (Microsoft Neural TTS, FREE, no API key).
Also supports ElevenLabs if ELEVENLABS_API_KEY is set.
Streams audio directly to the browser or saves to file.
"""

from __future__ import annotations

import contextlib

import hashlib
import io
import json
import logging
import os
from pathlib import Path

from fastapi import APIRouter, Request
from fastapi.responses import JSONResponse, StreamingResponse

router = APIRouter(prefix='/api/tts', tags=['tts'])
log = logging.getLogger('agentic.tts')

from backend.config import get_data_dir
ROOT = get_data_dir()
CACHE_DIR = ROOT / 'memory' / 'tts_cache'
CACHE_DIR.mkdir(parents=True, exist_ok=True)

# ── Voice registry ─────────────────────────────────────────────────────────────
EDGE_VOICES: dict[str, str] = {
    'aria': 'en-US-AriaNeural',  # warm, conversational female
    'guy': 'en-US-GuyNeural',  # confident male
    'jenny': 'en-US-JennyNeural',  # friendly female
    'davis': 'en-US-DavisNeural',  # professional male
    'jane': 'en-US-JaneNeural',  # expressive female
    'jason': 'en-US-JasonNeural',  # calm male
    'sara': 'en-US-SaraNeural',  # cheerful female
    'tony': 'en-US-TonyNeural',  # energetic male
    'sonia': 'en-GB-SoniaNeural',  # British female
    'ryan': 'en-GB-RyanNeural',  # British male
    'natasha': 'en-AU-NatashaNeural',  # Australian female
    'william': 'en-AU-WilliamNeural',  # Australian male
}
DEFAULT_VOICE = 'aria'

# Agent → voice mapping (customisable, persisted to DB)
AGENT_VOICES: dict[str, str] = {
    'brain': 'aria',
    'builder': 'davis',
    'researcher': 'jenny',
    'reviewer': 'jason',
    'creative': 'sara',
    'orchestrator': 'guy',
    'local': 'tony',
    'default': 'aria',
}

# Persistence file for voice preferences
_VOICE_PREFS_FILE = ROOT / 'memory' / 'tts_voice_prefs.json'


def _load_voice_prefs():
    """Load persisted agent voice prefs from disk."""
    global AGENT_VOICES
    try:
        if _VOICE_PREFS_FILE.exists():
            saved = json.loads(_VOICE_PREFS_FILE.read_text())
            for agent, voice in saved.items():
                if voice in EDGE_VOICES:
                    AGENT_VOICES[agent] = voice
    except Exception as ex:
        log.warning('Failed to load voice prefs: %s', ex)


def _save_voice_prefs():
    """Persist agent voice prefs to disk."""
    try:
        _VOICE_PREFS_FILE.write_text(json.dumps(AGENT_VOICES, indent=2))
    except Exception as ex:
        log.warning('Failed to save voice prefs: %s', ex)


_load_voice_prefs()


def _voice_for_agent(agent_id: str) -> str:
    voice_key = AGENT_VOICES.get(agent_id.lower(), AGENT_VOICES.get('default', DEFAULT_VOICE))
    return EDGE_VOICES.get(voice_key, EDGE_VOICES[DEFAULT_VOICE])


def _cache_key(text: str, voice: str, rate: str) -> str:
    return hashlib.sha256(f'{text}|{voice}|{rate}'.encode()).hexdigest()[:20]


# ── Speak endpoint ─────────────────────────────────────────────────────────────
@router.post('/speak')
async def speak(req: Request):
    """
    POST /api/tts/speak
    Body: {text, agent_id?, voice?, rate?, cache?}
    Returns: audio/mpeg stream (MP3)
    """
    try:
        body = await req.json()
    except (json.JSONDecodeError, TypeError, ValueError):
        body = {}
    text = (body.get('text') or '').strip()
    agent_id = (body.get('agent_id') or 'default').strip()
    voice = (body.get('voice') or '').strip()
    rate = (body.get('rate') or '+0%').strip()
    use_cache = body.get('cache', True)

    if not text:
        return JSONResponse({'ok': False, 'error': 'text required'}, status_code=400)

    # Truncate very long text
    text = text[:3000]

    # Strip markdown for better TTS
    text = _strip_markdown(text)
    if not text.strip():
        return JSONResponse({'ok': False, 'error': 'no speakable text after markdown stripping'}, status_code=400)

    # Validate rate format
    if not rate or not (rate.startswith('+') or rate.startswith('-') or rate == '0%'):
        rate = '+0%'

    # Resolve voice
    if voice and voice in EDGE_VOICES:
        edge_voice = EDGE_VOICES[voice]
    elif voice and voice in EDGE_VOICES.values():
        edge_voice = voice  # raw voice name passed directly
    else:
        edge_voice = _voice_for_agent(agent_id)

    # Cache check
    ck = _cache_key(text, edge_voice, rate)
    cache_file = CACHE_DIR / f'{ck}.mp3'
    if use_cache and cache_file.exists():
        log.debug('TTS cache hit: %s', ck)
        return StreamingResponse(
            _file_iter(cache_file),
            media_type='audio/mpeg',
            headers={'X-Cache': 'HIT', 'X-Voice': edge_voice, 'Content-Disposition': 'inline'},
        )

    # Check edge-tts availability
    try:
        import edge_tts  # noqa: F401
    except ImportError:
        return JSONResponse(
            {'ok': False, 'error': 'edge-tts not installed. Run: pip install edge-tts'}, status_code=503
        )

    # Generate via edge-tts
    try:
        audio_bytes = await _edge_tts(text, edge_voice, rate)
        if use_cache:
            cache_file.write_bytes(audio_bytes)
        return StreamingResponse(
            iter([audio_bytes]),
            media_type='audio/mpeg',
            headers={
                'X-Cache': 'MISS',
                'X-Voice': edge_voice,
                'X-Chars': str(len(text)),
                'Content-Disposition': 'inline',
            },
        )
    except Exception as e:
        # edge-tts depends on Microsoft's remote service. Treat an unavailable or
        # failed provider as a service dependency failure rather than an internal
        # application error so clients can retry or fall back cleanly.
        log.error('TTS provider error: %s', e)
        return JSONResponse({'ok': False, 'error': 'TTS provider unavailable'}, status_code=503)


@router.get('/speak')
async def speak_get(
    text: str = '',
    agent_id: str = 'default',
    voice: str = '',
    rate: str = '+0%',
):
    """GET version for easy embedding in <audio src=...>"""
    if not text:
        return JSONResponse({'ok': False, 'error': 'text param required'}, status_code=400)

    text = _strip_markdown(text[:1000])
    if not text.strip():
        return JSONResponse({'ok': False, 'error': 'no speakable text'}, status_code=400)

    if voice and voice in EDGE_VOICES:
        edge_voice = EDGE_VOICES[voice]
    elif voice and voice in EDGE_VOICES.values():
        edge_voice = voice
    else:
        edge_voice = _voice_for_agent(agent_id)

    rate = rate if (rate.startswith('+') or rate.startswith('-')) else '+0%'

    ck = _cache_key(text, edge_voice, rate)
    cache_file = CACHE_DIR / f'{ck}.mp3'
    if cache_file.exists():
        return StreamingResponse(
            _file_iter(cache_file), media_type='audio/mpeg', headers={'X-Cache': 'HIT', 'X-Voice': edge_voice}
        )

    try:
        import edge_tts  # noqa: F401
    except ImportError:
        return JSONResponse(
            {'ok': False, 'error': 'edge-tts not installed. Run: pip install edge-tts'}, status_code=503
        )

    try:
        audio_bytes = await _edge_tts(text, edge_voice, rate)
        cache_file.write_bytes(audio_bytes)
        return StreamingResponse(
            iter([audio_bytes]), media_type='audio/mpeg', headers={'X-Cache': 'MISS', 'X-Voice': edge_voice}
        )
    except Exception as e:
        log.error('TTS provider error: %s', e)
        return JSONResponse({'ok': False, 'error': 'TTS provider unavailable'}, status_code=503)


@router.get('/voices')
def list_voices():
    """Return available voices and agent mappings."""
    return {
        'voices': [
            {'id': k, 'name': v, 'lang': v.split('-')[0] + '-' + v.split('-')[1]} for k, v in EDGE_VOICES.items()
        ],
        'agent_voices': AGENT_VOICES,
        'default': DEFAULT_VOICE,
        'provider': 'edge-tts (Microsoft Neural, free)',
        'elevenlabs_available': bool(os.getenv('ELEVENLABS_API_KEY')),
    }


@router.get('/voices/{agent_id}')
def get_agent_voice(agent_id: str):
    """Get the configured voice for a specific agent."""
    voice_key = AGENT_VOICES.get(agent_id.lower(), AGENT_VOICES.get('default', DEFAULT_VOICE))
    edge_voice = EDGE_VOICES.get(voice_key, EDGE_VOICES[DEFAULT_VOICE])
    return {
        'ok': True,
        'agent_id': agent_id,
        'voice': voice_key,
        'edge_voice': edge_voice,
    }


@router.patch('/voices/{agent_id}')
async def set_agent_voice(agent_id: str, req: Request):
    """Set preferred voice for an agent (persisted to disk)."""
    try:
        body = await req.json()
    except (json.JSONDecodeError, TypeError, ValueError):
        body = {}
    voice = (body.get('voice') or DEFAULT_VOICE).strip()
    if voice not in EDGE_VOICES:
        return {'ok': False, 'error': f"Unknown voice '{voice}'. Options: {list(EDGE_VOICES.keys())}"}
    AGENT_VOICES[agent_id.lower()] = voice
    _save_voice_prefs()
    from ..services.memory_db import audit_log

    audit_log('tts_voice_set', f'{agent_id} → {voice}')
    return {'ok': True, 'agent_id': agent_id, 'voice': voice, 'edge_voice': EDGE_VOICES[voice]}


@router.delete('/voices/{agent_id}')
def reset_agent_voice(agent_id: str):
    """Reset an agent's voice to default."""
    if agent_id in AGENT_VOICES and agent_id != 'default':
        del AGENT_VOICES[agent_id]
        _save_voice_prefs()
    return {'ok': True, 'agent_id': agent_id, 'voice': DEFAULT_VOICE}


@router.delete('/cache')
def clear_cache():
    """Clear TTS audio cache."""
    count = 0
    for f in CACHE_DIR.glob('*.mp3'):
        with contextlib.suppress(Exception):
            f.unlink()
            count += 1
    return {'ok': True, 'cleared': count}


@router.get('/cache/stats')
def cache_stats():
    """Return cache statistics."""
    files = list(CACHE_DIR.glob('*.mp3'))
    total_bytes = sum(f.stat().st_size for f in files)
    return {
        'files': len(files),
        'total_mb': round(total_bytes / 1024 / 1024, 2),
        'cache_dir': str(CACHE_DIR),
    }


@router.get('/status')
def tts_status():
    """Return TTS engine status and availability."""
    edge_available = False
    edge_version = None
    try:
        import edge_tts

        edge_available = True
        edge_version = getattr(edge_tts, '__version__', 'unknown')
    except ImportError:
        pass

    el_available = bool(os.getenv('ELEVENLABS_API_KEY'))

    return {
        'ok': True,
        'edge_tts_available': edge_available,
        'edge_tts_version': edge_version,
        'elevenlabs_available': el_available,
        'install_cmd': 'pip install edge-tts' if not edge_available else None,
        'cache_files': len(list(CACHE_DIR.glob('*.mp3'))),
        'voices_count': len(EDGE_VOICES),
    }


# ── ElevenLabs (optional, premium) ────────────────────────────────────────────
@router.post('/elevenlabs/speak')
async def elevenlabs_speak(req: Request):
    """Speak using ElevenLabs API (requires ELEVENLABS_API_KEY)."""
    try:
        body = await req.json()
    except (json.JSONDecodeError, TypeError, ValueError):
        body = {}
    text = (body.get('text') or '').strip()[:2000]
    voice_id = body.get('voice_id', '21m00Tcm4TlvDq8ikWAM')  # default Rachel voice
    model = body.get('model', 'eleven_monolingual_v1')

    if not text:
        return JSONResponse({'ok': False, 'error': 'text required'}, status_code=400)

    api_key = os.getenv('ELEVENLABS_API_KEY', '')
    if not api_key:
        return JSONResponse(
            {'ok': False, 'error': 'ELEVENLABS_API_KEY not set. Set it in Settings → API Keys.'}, status_code=503
        )

    text = _strip_markdown(text)

    try:
        import httpx

        async with httpx.AsyncClient(timeout=30) as client:
            r = await client.post(
                f'https://api.elevenlabs.io/v1/text-to-speech/{voice_id}',
                headers={'xi-api-key': api_key, 'Content-Type': 'application/json'},
                json={'text': text, 'model_id': model, 'voice_settings': {'stability': 0.5, 'similarity_boost': 0.8}},
            )
            if r.status_code == 200:
                audio_bytes = r.content
                return StreamingResponse(iter([audio_bytes]), media_type='audio/mpeg')
            else:
                return JSONResponse(
                    {'ok': False, 'error': f'ElevenLabs error {r.status_code}: {r.text[:200]}'},
                    status_code=r.status_code,
                )
    except Exception as ex:
        return JSONResponse({'ok': False, 'error': str(ex)}, status_code=500)


# ── Core edge-tts call ─────────────────────────────────────────────────────────
async def _edge_tts(text: str, voice: str, rate: str = '+0%') -> bytes:
    import edge_tts

    buf = io.BytesIO()
    communicate = edge_tts.Communicate(text, voice, rate=rate)
    async for chunk in communicate.stream():
        if chunk['type'] == 'audio':
            buf.write(chunk['data'])
    audio = buf.getvalue()
    if not audio:
        raise RuntimeError('edge-tts returned empty audio — check network connectivity')
    return audio


async def _file_iter(path: Path):
    """Async generator to stream a file in 8KB chunks."""
    with open(path, 'rb') as f:
        while True:
            chunk = f.read(8192)
            if not chunk:
                break
            yield chunk


def _strip_markdown(text: str) -> str:
    """Remove markdown formatting so TTS reads naturally."""
    import re

    text = re.sub(r'```[\s\S]*?```', ' ', text)  # fenced code blocks
    text = re.sub(r'`[^`]+`', ' ', text)  # inline code
    text = re.sub(r'\*\*(.+?)\*\*', r'\1', text)  # bold
    text = re.sub(r'\*(.+?)\*', r'\1', text)  # italic
    text = re.sub(r'__(.+?)__', r'\1', text)  # bold underscore
    text = re.sub(r'_(.+?)_', r'\1', text)  # italic underscore
    text = re.sub(r'~~(.+?)~~', r'\1', text)  # strikethrough
    text = re.sub(r'#+\s+', '', text)  # headers
    text = re.sub(r'\[(.+?)\]\(.+?\)', r'\1', text)  # links → label
    text = re.sub(r'^[-•*]\s+', '', text, flags=re.M)  # list bullets
    text = re.sub(r'^\d+\.\s+', '', text, flags=re.M)  # numbered lists
    text = re.sub(r'^>\s+', '', text, flags=re.M)  # blockquotes
    text = re.sub(r'\|[^\n]+\|', ' ', text)  # tables
    text = re.sub(r'^\s*[-|]+\s*$', '', text, flags=re.M)  # table separators
    text = re.sub(r'\n{3,}', '\n\n', text)  # excess newlines
    text = re.sub(r'!\[.*?\]\(.*?\)', '', text)  # images
    return text.strip()
