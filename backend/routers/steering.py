"""
Agentic OS — Steering Files System
Persistent project context injected into every AI prompt.
Equivalent to Kiro's .kiro/steering/ + Cursor's .cursorrules + Windsurf Memories.

Steering files encode:
  - Tech stack decisions (which framework, DB, patterns)
  - Coding standards (naming conventions, error handling style)
  - Architectural constraints ("never use class components", "always use async/await")
  - Team conventions ("all API endpoints return {ok, data, error}")
  - Project context (what the app does, who the users are)
  - Auto-learned patterns from chat history (Windsurf-style 48hr auto-learning)

Files live in .agentic/steering/ as markdown files.
All are concatenated and prepended to every LLM call.
"""

from __future__ import annotations

import contextlib

import json
import logging
import time
from pathlib import Path

from fastapi import APIRouter, Request

router = APIRouter(prefix='/api/steering', tags=['steering'])
log = logging.getLogger('agentic.steering')

from backend.config import get_data_dir
ROOT = get_data_dir()
STEERING_DIR = ROOT / '.agentic' / 'steering'
STEERING_DIR.mkdir(parents=True, exist_ok=True)

# ── DB schema ──────────────────────────────────────────────────────────────────
_SCHEMA = """
CREATE TABLE IF NOT EXISTS steering_files (
    id          TEXT PRIMARY KEY,
    filename    TEXT NOT NULL UNIQUE,
    title       TEXT NOT NULL,
    content     TEXT DEFAULT '',
    category    TEXT DEFAULT 'general',
    auto_learned INTEGER DEFAULT 0,
    confidence  REAL DEFAULT 1.0,
    enabled     INTEGER DEFAULT 1,
    created_at  TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    updated_at  TIMESTAMP DEFAULT CURRENT_TIMESTAMP
);
CREATE TABLE IF NOT EXISTS steering_learned (
    id          INTEGER PRIMARY KEY AUTOINCREMENT,
    pattern_key TEXT NOT NULL UNIQUE,
    pattern_val TEXT NOT NULL,
    source      TEXT DEFAULT 'chat',
    occurrences INTEGER DEFAULT 1,
    confidence  REAL DEFAULT 0.5,
    promoted    INTEGER DEFAULT 0,
    created_at  TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    updated_at  TIMESTAMP DEFAULT CURRENT_TIMESTAMP
);
"""

# ── Starter steering file templates ───────────────────────────────────────────
STARTER_FILES = [
    {
        'id': 'stack',
        'filename': 'stack.md',
        'title': 'Tech Stack',
        'category': 'stack',
        'content': """# Tech Stack

## Backend
- Language: Python 3.11+
- Framework: FastAPI
- Database: SQLite (via memory_db.py)
- Server: uvicorn

## Frontend
- Single-file HTML/CSS/JS (frontend/index.html)
- No build step required
- Vanilla JS with inline styles

## Key Conventions
- All API routes prefixed /api/
- Responses follow {ok: bool, data?: any, error?: str} pattern
- Use async/await throughout
- SQLite WAL mode enabled
""",
    },
    {
        'id': 'coding-style',
        'filename': 'coding-style.md',
        'title': 'Coding Style',
        'category': 'style',
        'content': """# Coding Style & Conventions

## Python
- Type hints on all functions
- Docstrings for public functions
- f-strings over .format()
- `from __future__ import annotations

import contextlib` at top of every file
- Error handling: always catch specific exceptions, log with log.warning/log.error

## JavaScript
- ES2022+ syntax
- Async/await over callbacks
- `escHtml()` for all user-rendered strings (XSS prevention)
- Modal dialogs via gmAlert/gmConfirm/gmPrompt (no raw alert/confirm/prompt)

## File Structure
- Backend routers in backend/routers/
- Services in backend/services/
- All frontend in frontend/index.html
""",
    },
    {
        'id': 'architecture',
        'filename': 'architecture.md',
        'title': 'Architecture Decisions',
        'category': 'architecture',
        'content': """# Architecture Decisions

## API Design
- REST endpoints with FastAPI routers
- SSE (Server-Sent Events) for long-running operations like agent runs
- WebSocket for real-time features (chat, collab, hooks)
- No GraphQL

## Data Layer
- Primary: SQLite at memory/agentic.db
- Optional: Qdrant for vector embeddings (graceful fallback to FTS5)
- File system for large artifacts (workflows, specs, plugin packs)

## Security
- Secrets encrypted with Fernet in secrets table
- Path traversal protection on all file endpoints
- No raw SQL string interpolation — always use parameterized queries

## Frontend Patterns
- Single-pane SPA with pane switching via nav()
- Master Nav Dispatcher handles all 37+ panes
- All modals use gmAlert/gmConfirm/gmPrompt (not browser alert/confirm)
""",
    },
    {
        'id': 'project-context',
        'filename': 'project-context.md',
        'title': 'Project Context',
        'category': 'context',
        'content': """# Project Context

## What is Agentic OS?
A local-first, MIT-licensed agentic AI operating system that runs on localhost:8787.
Comparable to Cursor, Windsurf, Lovable, Bolt.new — but self-hosted and free.

## Target Users
- Developers who want full control over their AI tooling
- Teams who need local-first privacy (no cloud, no subscriptions)
- Power users who want to combine multiple AI agents in workflows

## Key Principles
1. Local-first: Everything runs on your machine
2. Open: MIT licensed, no vendor lock-in
3. Composable: Agents, workflows, and tools can be combined freely
4. Transparent: Full audit logs, cost tracking, execution replay
""",
    },
]


def _ensure_schema():
    from ..services.memory_db import get_conn

    con = get_conn()
    try:
        con.executescript(_SCHEMA)
        # Seed starter files
        for sf in STARTER_FILES:
            row = con.execute('SELECT id FROM steering_files WHERE id=?', (sf['id'],)).fetchone()
            if not row:
                con.execute(
                    # FIX 1: seed with enabled=1 so steering is active on fresh install
                    'INSERT INTO steering_files(id,filename,title,content,category,auto_learned,enabled) VALUES (?,?,?,?,?,0,1)',
                    (sf['id'], sf['filename'], sf['title'], sf['content'], sf['category']),
                )
        # Write to disk too
        (STEERING_DIR / sf['filename']).write_text(sf['content'], encoding='utf-8')
        # FIX 1b: if starter files were seeded with enabled=0, correct them
        for sf in STARTER_FILES:
            con.execute('UPDATE steering_files SET enabled=1 WHERE id=? AND enabled=0 AND auto_learned=0', (sf['id'],))
        con.commit()
    finally:
        con.close()


_ensure_schema()


# ── Compile steering context (called by LLM service) ─────────────────────────
def compile_steering_context(max_chars: int = 8000) -> str:
    """
    Compile all enabled steering files into a single context string.
    Injected as a system prompt prefix in every LLM call.
    """
    from ..services.memory_db import get_conn

    con = get_conn()
    try:
        rows = con.execute(
            'SELECT title, content FROM steering_files WHERE enabled=1 ORDER BY category, title'
        ).fetchall()
    finally:
        con.close()

    if not rows:
        return ''

    parts = ['# Project Steering Context\n']
    try:
        rules_path = ROOT / '.agenticrules'
        if rules_path.exists() and rules_path.stat().st_size > 0:
            rules_text = rules_path.read_text(encoding='utf-8')[:3000]
            parts.append(f'\n## Runtime Behavioral Enforcement (.agenticrules)\n{rules_text}\n')
    except Exception:
        pass
    total = len(parts[0]) + (len(parts[1]) if len(parts) > 1 else 0)
    skipped = []
    for row in rows:
        section = f'\n## {row["title"]}\n{row["content"]}\n'
        if total + len(section) > max_chars:
            # FIX 12: track which files were truncated
            skipped.append(row['title'])
            continue  # skip but continue trying smaller files (greedy = False)
        parts.append(section)
        total += len(section)

    if skipped:
        parts.append(
            f'\n---\n*⚠️ Truncated: {len(skipped)} file(s) excluded (context limit {max_chars} chars): {", ".join(skipped[:3])}*\n'
        )

    return ''.join(parts)


# ── REST endpoints ─────────────────────────────────────────────────────────────
@router.get('')
def list_steering():
    """Retrieve and return list steering."""
    from ..services.memory_db import get_conn

    con = get_conn()
    try:
        rows = con.execute('SELECT * FROM steering_files ORDER BY category, title').fetchall()
    finally:
        con.close()
    return {'files': [dict(r) for r in rows], 'count': len(rows)}


@router.post('')
async def create_steering(req: Request):
    """Create and initialize a new steering."""
    try:
        try:
            body = await req.json()
        except (KeyError, TypeError, ValueError, json.JSONDecodeError, OSError, AttributeError):
            body = {}
    except (KeyError, TypeError, ValueError, json.JSONDecodeError, OSError, AttributeError):
        body = {}
    filename = (body.get('filename') or f'custom_{int(time.time())}.md').replace('/', '')
    title = (body.get('title') or filename.replace('.md', '').replace('-', ' ').title())[:120]
    content = body.get('content', '')
    category = body.get('category', 'custom')
    file_id = body.get('id') or filename.replace('.md', '').replace('-', '_')

    from ..services.memory_db import get_conn

    con = get_conn()
    try:
        con.execute(
            'INSERT OR REPLACE INTO steering_files(id,filename,title,content,category,enabled) VALUES (?,?,?,?,?,1)',
            (file_id, filename, title, content, category),
        )
        con.commit()
    finally:
        con.close()

    # Write to disk
    (STEERING_DIR / filename).write_text(content, encoding='utf-8')
    return {'ok': True, 'id': file_id, 'filename': filename}


@router.get('/compiled')
def get_compiled():
    """Return the full compiled steering context (what gets injected into prompts)."""
    # FIX 12b: expose both display limit (8000) and LLM injection limit (4000)
    context_full = compile_steering_context(max_chars=8000)
    context_llm = compile_steering_context(max_chars=4000)
    truncated_for_llm = len(context_full) > len(context_llm)
    return {
        'context': context_full,
        'length': len(context_full),
        'chars': len(context_full),
        'llm_chars': len(context_llm),
        'truncated_for_llm': truncated_for_llm,
    }


@router.get('/{file_id}')
def get_steering_file(file_id: str):
    """Retrieve and return get steering file."""
    from ..services.memory_db import get_conn

    con = get_conn()
    try:
        row = con.execute('SELECT * FROM steering_files WHERE id=?', (file_id,)).fetchone()
    finally:
        con.close()
    if not row:
        return {'ok': False, 'error': 'Not found'}
    return dict(row)


@router.put('/{file_id}')
async def update_steering(file_id: str, req: Request):
    """Update existing steering record or state."""
    try:
        try:
            body = await req.json()
        except (KeyError, TypeError, ValueError, json.JSONDecodeError, OSError, AttributeError):
            body = {}
    except (KeyError, TypeError, ValueError, json.JSONDecodeError, OSError, AttributeError):
        body = {}
    # FIX 4: use None default so we can tell if caller actually sent content
    # body.get("content","") always returns "" if key absent → silently wipes file on title-only updates
    content = body.get('content')  # None if not sent
    title = body.get('title', '')
    enabled = body.get('enabled')

    from ..services.memory_db import get_conn

    con = get_conn()
    try:
        sets, vals = ['updated_at=CURRENT_TIMESTAMP'], []
        if content is not None:
            sets.append('content=?')
            vals.append(content)
        if title:
            sets.append('title=?')
            vals.append(title[:120])
        if enabled is not None:
            sets.append('enabled=?')
            vals.append(1 if enabled else 0)
        vals.append(file_id)
        con.execute(f'UPDATE steering_files SET {",".join(sets)} WHERE id=?', vals)
        row = con.execute('SELECT * FROM steering_files WHERE id=?', (file_id,)).fetchone()
        con.commit()
    finally:
        con.close()

    if row and content is not None:
        (STEERING_DIR / row['filename']).write_text(content, encoding='utf-8')
    return {'ok': True}


@router.delete('/{file_id}')
def delete_steering(file_id: str):
    """Delete or remove specified steering."""
    from ..services.memory_db import get_conn

    con = get_conn()
    try:
        row = con.execute('SELECT filename,auto_learned FROM steering_files WHERE id=?', (file_id,)).fetchone()
        if row:
            con.execute('DELETE FROM steering_files WHERE id=?', (file_id,))
            con.commit()
            fp = STEERING_DIR / row['filename']
            if fp.exists():
                fp.unlink()
    finally:
        con.close()
    # FIX 7: return deleted:bool so callers can detect nonexistent file_id
    return {'ok': True, 'deleted': row is not None}


@router.post('/{file_id}/toggle')
def toggle_steering(file_id: str):
    """Execute or process toggle steering operation."""
    from ..services.memory_db import get_conn

    con = get_conn()
    try:
        row = con.execute('SELECT enabled FROM steering_files WHERE id=?', (file_id,)).fetchone()
        if not row:
            return {'ok': False, 'error': 'Not found'}
        new_val = 0 if row['enabled'] else 1
        con.execute('UPDATE steering_files SET enabled=? WHERE id=?', (new_val, file_id))
        con.commit()
    finally:
        con.close()
    return {'ok': True, 'enabled': bool(new_val)}


# ── Auto-learning (Windsurf Memories style) ────────────────────────────────────
@router.post('/learn/from-chat')
async def learn_from_chat(req: Request):
    """
    Analyze recent chat history to extract coding patterns and preferences.
    Windsurf does this automatically after 48hrs; we expose it as an API.
    """
    try:
        body = await req.json()
    except (json.JSONDecodeError, TypeError, ValueError):
        body = {}
    limit = body.get('limit', 50)  # number of recent messages to analyze

    from ..services.memory_db import get_conn

    con = get_conn()
    try:
        msgs = con.execute(
            "SELECT role, message FROM chat_log WHERE role='user' ORDER BY created_at DESC LIMIT ?", (min(limit, 200),)
        ).fetchall()
    finally:
        con.close()

    if not msgs:
        return {'ok': False, 'error': 'No chat history to learn from'}

    chat_text = '\n'.join(f'{r["role"]}: {r["message"][:200]}' for r in msgs)

    from ..services import llm as llm_svc

    prompt = f"""Analyze this developer's chat history and extract specific coding preferences and patterns.

CHAT HISTORY (recent {len(msgs)} messages):
{chat_text[:4000]}

Extract and return a JSON object with these categories:
{{
  "preferred_language": "Python/JS/TS/etc or null",
  "preferred_framework": "FastAPI/React/Vue/etc or null",
  "coding_style": ["list of observed style preferences"],
  "naming_conventions": ["camelCase/snake_case/etc patterns observed"],
  "error_handling": "preferred error handling pattern or null",
  "testing_preferences": "preferred testing approach or null",
  "architecture_patterns": ["patterns they repeatedly use"],
  "avoid_patterns": ["things they explicitly avoid or dislike"],
  "custom_rules": ["any specific rules they've mentioned"]
}}

Return ONLY valid JSON. Use null for unknown fields."""

    result = await llm_svc.complete(
        [{'role': 'user', 'content': prompt}],
        agent_id='steering',
        max_tokens=1000,
        temperature=0.1,
        inject_steering=False,
    )
    text = result.get('text', '')

    import re as _re

    m = _re.search(r'\{.*\}', text, _re.DOTALL)  # FIX 3: was re.DOTALL (wrong alias)
    learned = {}
    if m:
        with contextlib.suppress(Exception):
            learned = json.loads(m.group(0))

    if not learned:
        return {'ok': False, 'error': 'Could not extract patterns from chat history'}

    # Validate learned dict — reject if it looks like an API error (no expected keys)
    EXPECTED_KEYS = {
        'preferred_language',
        'preferred_framework',
        'coding_style',
        'naming_conventions',
        'error_handling',
        'testing_preferences',
        'architecture_patterns',
        'avoid_patterns',
        'custom_rules',
    }
    if not any(k in EXPECTED_KEYS for k in learned):
        return {'ok': False, 'error': 'Could not extract patterns from chat history'}

    # Store learned patterns
    from ..services.memory_db import get_conn

    con = get_conn()
    try:
        stored = 0
        for key, val in learned.items():
            # Only store keys we recognise — skip API errors, code fields, etc.
            if key not in EXPECTED_KEYS or not val:
                continue
            val_str = json.dumps(val) if isinstance(val, (list, dict)) else str(val)
            try:
                existing = con.execute(
                    'SELECT occurrences FROM steering_learned WHERE pattern_key=?', (key,)
                ).fetchone()
                if existing:
                    con.execute(
                        'UPDATE steering_learned SET pattern_val=?,occurrences=occurrences+1,confidence=MIN(1.0,confidence+0.1),updated_at=CURRENT_TIMESTAMP WHERE pattern_key=?',
                        (val_str, key),
                    )
                else:
                    con.execute(
                        'INSERT INTO steering_learned(pattern_key,pattern_val,source,confidence) VALUES (?,?,?,?)',
                        (key, val_str, 'chat_analysis', 0.6),
                    )
                stored += 1
            except (KeyError, TypeError, ValueError, json.JSONDecodeError, OSError):
                pass
        con.commit()
    finally:
        con.close()

    return {'ok': True, 'learned': learned, 'stored_patterns': stored}


@router.post('/learn/promote')
async def promote_learned_to_steering(req: Request):
    """
    Promote high-confidence learned patterns into a real steering file.
    This is what Windsurf Memories does automatically after 48 hours.
    """
    try:
        body = await req.json()
    except (json.JSONDecodeError, TypeError, ValueError):
        body = {}
    min_conf = body.get('min_confidence', 0.6)
    file_title = body.get('title', 'Auto-Learned Preferences')

    from ..services.memory_db import get_conn

    con = get_conn()
    try:
        patterns = con.execute(
            'SELECT * FROM steering_learned WHERE confidence>=? AND promoted=0 ORDER BY confidence DESC', (min_conf,)
        ).fetchall()
    finally:
        con.close()

    if not patterns:
        return {'ok': False, 'error': 'No patterns ready to promote'}

    # Build markdown content
    lines = [f'# {file_title}\n', '*Auto-generated from your coding patterns*\n\n']
    category_map: dict[str, list] = {}
    for p in patterns:
        cat = p['pattern_key'].replace('_', ' ').title()
        val = p['pattern_val']
        try:
            val = json.loads(val)
            if isinstance(val, list):
                val = '\n'.join(f'- {v}' for v in val)
        except (KeyError, TypeError, ValueError, json.JSONDecodeError, OSError):
            pass
        category_map.setdefault(cat, []).append(str(val))

    for cat, vals in category_map.items():
        lines.append(f'## {cat}\n')
        for v in vals:
            lines.append(f'{v}\n')
        lines.append('\n')

    content = ''.join(lines)
    file_id = f'auto_learned_{int(time.time())}'

    con = get_conn()
    try:
        con.execute(
            'INSERT OR REPLACE INTO steering_files(id,filename,title,content,category,auto_learned,enabled) VALUES (?,?,?,?,?,1,1)',
            (file_id, f'{file_id}.md', file_title, content, 'auto-learned'),
        )
        (STEERING_DIR / f'{file_id}.md').write_text(content, encoding='utf-8')
        # Mark patterns as promoted
        con.execute('UPDATE steering_learned SET promoted=1 WHERE confidence>=?', (min_conf,))
        con.commit()
    finally:
        con.close()

    return {'ok': True, 'file_id': file_id, 'patterns_promoted': len(patterns), 'content': content}


@router.get('/learned/patterns')
def get_learned_patterns():
    """Retrieve and return get learned patterns."""
    from ..services.memory_db import get_conn

    con = get_conn()
    try:
        rows = con.execute('SELECT * FROM steering_learned ORDER BY confidence DESC, occurrences DESC').fetchall()
    finally:
        con.close()
    return {'patterns': [dict(r) for r in rows], 'count': len(rows)}


@router.delete('/learned/clear')
def clear_learned():
    """Delete or remove specified clear learned."""
    from ..services.memory_db import get_conn

    con = get_conn()
    try:
        con.execute('DELETE FROM steering_learned')
        con.commit()
    finally:
        con.close()
    return {'ok': True}
