"""
Agentic OS — Obsidian Vault Sync Router
Bi-directional sync with a local Obsidian vault:
  - Index markdown notes → Memory Galaxy
  - Watch vault folder for changes (watchdog)
  - Export memories → vault as markdown
  - Daily note generation
  - Backlink graph
"""

from __future__ import annotations

import contextlib

import logging
import os
import re
from datetime import date, datetime
from pathlib import Path

from fastapi import APIRouter, Request

router = APIRouter(prefix='/api/obsidian', tags=['obsidian'])
log = logging.getLogger('agentic.obsidian')

from backend.config import get_data_dir
ROOT = get_data_dir()


# ── Config ─────────────────────────────────────────────────────────────────────
def _vault_path() -> Path | None:
    """Get configured vault path from config or env."""
    vault = os.getenv('OBSIDIAN_VAULT_PATH', '')
    if vault and Path(vault).exists():
        return Path(vault)
    # Use brain/ folder inside agentic-os as built-in vault
    brain = ROOT / 'brain'
    if brain.exists():
        return brain
    return None


def _note_dir() -> Path:
    """Get or create the agentic-os notes directory inside vault."""
    vp = _vault_path()
    if vp:
        d = vp / 'agentic-os'
        d.mkdir(exist_ok=True)
        return d
    # Fallback: create and use brain/agentic-os
    d = ROOT / 'brain' / 'agentic-os'
    d.mkdir(parents=True, exist_ok=True)
    return d


def _ensure_brain():
    """Create the brain/ directory if it doesn't exist."""
    brain = ROOT / 'brain'
    brain.mkdir(exist_ok=True)
    return brain


# ── Status ─────────────────────────────────────────────────────────────────────
@router.get('/status')
def status():
    """Execute or process status operation."""
    _ensure_brain()
    vp = _vault_path()
    brain_path = str(ROOT / 'brain')

    if not vp:
        return {
            'connected': False,
            'vault_path': None,
            'note_dir': str(ROOT / 'brain' / 'agentic-os'),
            'brain_path': brain_path,
            'note_count': len(list((ROOT / 'brain').rglob('*.md'))) if (ROOT / 'brain').exists() else 0,
            'setup': [
                'Set OBSIDIAN_VAULT_PATH=/path/to/your/vault in .env',
                'Or use brain/ folder as the built-in self-layer (always available)',
                'Install Obsidian: https://obsidian.md',
            ],
        }

    notes = list(vp.rglob('*.md'))
    return {
        'connected': True,
        'vault_path': str(vp),
        'note_count': len(notes),
        'size_mb': round(sum(n.stat().st_size for n in notes) / 1024 / 1024, 2),
        'last_modified': max((n.stat().st_mtime for n in notes), default=0),
        'note_dir': str(_note_dir()),
        'brain_path': brain_path,
    }


# ── Index status (GET) ─────────────────────────────────────────────────────────
@router.get('/index')
def index_status():
    """GET the current index status without re-indexing."""
    _ensure_brain()
    vp = _vault_path()
    notes = list(vp.rglob('*.md')) if vp else []

    from ..services.memory_db import get_conn

    con = get_conn()
    try:
        indexed_count = con.execute("SELECT COUNT(*) FROM memory WHERE source LIKE 'obsidian:%'").fetchone()[0]
    except (KeyError, TypeError, ValueError, json.JSONDecodeError, OSError, AttributeError, RuntimeError):
        indexed_count = 0
    finally:
        con.close()

    return {
        'ok': True,
        'vault_path': str(vp) if vp else None,
        'vault_exists': vp is not None and vp.exists(),
        'note_count': len(notes),
        'indexed_count': indexed_count,
        'note_dir': str(_note_dir()),
        'note': 'Use POST /api/obsidian/index to rebuild the index',
    }


# ── Index vault → Memory Galaxy ────────────────────────────────────────────────
@router.post('/index')
async def index_vault(req: Request):
    """
    Scan vault for .md files and ingest them into Memory Galaxy.
    Respects frontmatter tags. Skips already-indexed notes (unless re_index=true).
    """
    try:
        body = await req.json()
    except (json.JSONDecodeError, TypeError, ValueError):
        body = {}
    try:
        max_notes = min(int(body.get('max_notes', 500)), 2000)
    except (TypeError, ValueError):
        max_notes = 500
    re_index = bool(body.get('re_index', False))
    _ensure_brain()
    vp = _vault_path()

    if not vp:
        # Auto-create brain/ and use it
        brain = ROOT / 'brain'
        brain.mkdir(exist_ok=True)
        vp = brain

    from ..services.memory_db import audit_log, memory_add, memory_search_fts

    notes = list(vp.rglob('*.md'))[:max_notes]
    indexed = 0
    skipped = 0
    errors = 0

    for note in notes:
        try:
            content = note.read_text(encoding='utf-8', errors='ignore')
            if not content.strip():
                skipped += 1
                continue

            tags = _extract_tags(content, note)
            clean = _strip_frontmatter(content)
            title = note.stem
            source = f'obsidian:{note.relative_to(vp).as_posix()}'

            # Skip if already indexed (unless re_index)
            if not re_index:
                existing = memory_search_fts(title[:60], limit=2)
                if any(r.get('source', '').startswith('obsidian:') and title in r.get('content', '') for r in existing):
                    skipped += 1
                    continue

            chunks = _chunk_text(f'# {title}\n\n{clean}', max_chars=1200)
            for i, chunk in enumerate(chunks):
                mem_source = source if i == 0 else f'{source}#{i}'
                memory_add(mem_source, chunk, tags)
            indexed += 1

        except Exception as e:
            log.warning('Failed to index %s: %s', note.name, e)
            errors += 1

    audit_log('obsidian_index', f'{indexed} indexed, {skipped} skipped, {errors} errors from {vp}')
    return {
        'ok': True,
        'vault': str(vp),
        'total': len(notes),
        'indexed': indexed,
        'skipped': skipped,
        'errors': errors,
    }


# ── Export memory → vault note ─────────────────────────────────────────────────
@router.post('/export')
async def export_to_vault(req: Request):
    """Export recent memories to a markdown note in the vault."""
    try:
        body = await req.json()
    except (json.JSONDecodeError, TypeError, ValueError):
        body = {}
    source = (body.get('source') or '').strip()
    try:
        limit = min(int(body.get('limit', 50)), 200)
    except (TypeError, ValueError):
        limit = 50
    title = (body.get('title') or f'Agentic OS Export {date.today()}').strip()[:200]

    from ..services.memory_db import memory_list, memory_search_fts

    if source:
        mems = memory_search_fts(source, limit=limit)
    else:
        mems = memory_list(limit=limit)

    if not mems:
        return {'ok': False, 'error': 'No memories to export'}

    lines = [
        f'# {title}',
        f'*Generated by Agentic OS v6.0 — {datetime.now().strftime("%Y-%m-%d %H:%M")}*',
        '',
        '---',
        '',
    ]
    for m in mems:
        lines.append(f'## [{m.get("source", "?")}] {m.get("created_at", "")[:10]}')
        lines.append(m.get('content', ''))
        if m.get('tags'):
            lines.append(f'\n*Tags: {m["tags"]}*')
        lines.append('\n---\n')

    content = '\n'.join(lines)
    note_dir = _note_dir()
    filename = re.sub(r'[^\w\s-]', '', title).strip().replace(' ', '_') + '.md'
    outfile = note_dir / filename
    outfile.write_text(content, encoding='utf-8')

    return {
        'ok': True,
        'path': str(outfile),
        'filename': filename,
        'memories': len(mems),
        'chars': len(content),
    }


# ── Daily note ─────────────────────────────────────────────────────────────────
@router.post('/daily_note')
async def create_daily_note(req: Request):
    """Create or update today's daily note with Agentic OS activity."""
    from ..services.memory_db import get_conn

    con = get_conn()
    try:
        tasks_done = con.execute(
            "SELECT title, agent FROM tasks WHERE status='done' AND date(updated_at)=date('now') LIMIT 10"
        ).fetchall()
        tasks_doing = con.execute("SELECT title, agent FROM tasks WHERE status='doing' LIMIT 5").fetchall()
        chat_count = con.execute("SELECT COUNT(*) FROM chat_log WHERE date(created_at)=date('now')").fetchone()[0]
        cost_today = (
            con.execute("SELECT SUM(cost) FROM chat_log WHERE date(created_at)=date('now')").fetchone()[0] or 0.0
        )
        mem_today = con.execute("SELECT COUNT(*) FROM memory WHERE date(created_at)=date('now')").fetchone()[0]
    finally:
        con.close()

    today = date.today()
    note_dir = _note_dir()
    daily_dir = note_dir / 'Daily'
    daily_dir.mkdir(exist_ok=True)
    outfile = daily_dir / f'{today}.md'

    done_lines = ''.join(f'- [{t["agent"]}] {t["title"]}\n' for t in tasks_done) or '- Nothing completed yet'
    doing_lines = ''.join(f'- [{t["agent"]}] {t["title"]}\n' for t in tasks_doing) or '- No active tasks'

    content = f"""# Daily Note — {today}
*Agentic OS v6.0 — Auto-generated*

---

## 🤖 Agent Activity
- Chat messages today: **{chat_count}**
- LLM cost today: **${cost_today:.4f}**
- Memories added: **{mem_today}**

## ✅ Done Today
{done_lines}
## ⚡ In Progress
{doing_lines}
## 📝 Notes

_Add your notes here..._

---
*[[agentic-os/index|Back to Agentic OS Index]]*
"""
    outfile.write_text(content, encoding='utf-8')

    from ..services.memory_db import audit_log

    audit_log('obsidian_daily_note', str(today))

    return {
        'ok': True,
        'path': str(outfile),
        'date': str(today),
        'filename': f'Daily/{today}.md',
    }


# ── List vault notes ───────────────────────────────────────────────────────────
@router.get('/notes')
def list_notes(limit: int = 100, q: str = ''):
    """Retrieve and return list notes."""
    _ensure_brain()
    vp = _vault_path()
    if not vp:
        return {'notes': [], 'vault': None, 'count': 0}

    try:
        limit = min(max(1, int(limit)), 1000)
    except (TypeError, ValueError):
        limit = 100

    notes = []
    ql = q.lower().strip()
    for p in sorted(vp.rglob('*.md'), key=lambda x: -x.stat().st_mtime):
        if ql and ql not in p.name.lower() and ql not in p.stem.lower():
            continue
        try:
            rel_path = p.relative_to(vp).as_posix()
            notes.append(
                {
                    'name': p.stem,
                    'path': rel_path,
                    'size': p.stat().st_size,
                    'modified': datetime.fromtimestamp(p.stat().st_mtime).isoformat()[:16],
                    'folder': p.parent.name if p.parent != vp else '',
                }
            )
        except (KeyError, TypeError, ValueError, json.JSONDecodeError, OSError, AttributeError, RuntimeError):
            pass
        if len(notes) >= limit:
            break

    return {'notes': notes, 'vault': str(vp), 'count': len(notes)}


@router.get('/note')
def read_note(path: str):
    """Read a note from the vault. Path is relative to vault root."""
    _ensure_brain()
    vp = _vault_path()
    if not vp:
        return {'ok': False, 'error': 'No vault configured'}

    # Sanitise path: remove leading slashes and resolve
    clean_path = path.lstrip('/').lstrip('\\')
    f = (vp / clean_path).resolve()

    # Strict bounds check
    if not str(f).startswith(str(vp.resolve())):
        return {'ok': False, 'error': 'Path traversal denied'}
    if not f.exists():
        return {'ok': False, 'error': 'Note not found'}
    if not f.is_file():
        return {'ok': False, 'error': 'Not a file'}

    try:
        content = f.read_text(encoding='utf-8', errors='ignore')
        return {
            'ok': True,
            'content': content,
            'path': clean_path,
            'size': f.stat().st_size,
            'modified': datetime.fromtimestamp(f.stat().st_mtime).isoformat()[:16],
        }
    except Exception as ex:
        return {'ok': False, 'error': str(ex)}


@router.post('/note')
async def write_note(req: Request):
    """Write a note to the vault (inside agentic-os subfolder)."""
    try:
        body = await req.json()
    except (json.JSONDecodeError, TypeError, ValueError):
        body = {}
    path = (body.get('path') or '').strip().lstrip('/').lstrip('\\')
    content = body.get('content', '')

    if not path:
        return {'ok': False, 'error': 'path required'}
    if not path.endswith('.md'):
        path += '.md'

    note_dir = _note_dir()
    f = (note_dir / path).resolve()

    # Strict bounds check
    if not str(f).startswith(str(note_dir.resolve())):
        return {'ok': False, 'error': 'Path traversal denied'}

    try:
        f.parent.mkdir(parents=True, exist_ok=True)
        f.write_text(content, encoding='utf-8')
        from ..services.memory_db import audit_log

        audit_log('obsidian_write_note', path)
        # Return path relative to vault root for easy reading back
        vp = _vault_path()
        rel = str(f.relative_to(vp)) if vp and str(f).startswith(str(vp)) else str(f.relative_to(ROOT))
        return {'ok': True, 'path': rel, 'abs_path': str(f), 'size': len(content)}
    except Exception as ex:
        return {'ok': False, 'error': str(ex)}


@router.delete('/note')
async def delete_note(req: Request):
    """Delete a note from the vault (restricted to agentic-os subfolder)."""
    try:
        body = await req.json()
    except (json.JSONDecodeError, TypeError, ValueError):
        body = {}
    path = (body.get('path') or '').strip().lstrip('/')
    if not path:
        return {'ok': False, 'error': 'path required'}

    note_dir = _note_dir()
    f = (note_dir / path).resolve()

    if not str(f).startswith(str(note_dir.resolve())):
        return {'ok': False, 'error': 'Path traversal denied — can only delete from agentic-os folder'}
    if not f.exists():
        return {'ok': False, 'error': 'Note not found'}

    try:
        f.unlink()
        from ..services.memory_db import audit_log

        audit_log('obsidian_delete_note', path)
        return {'ok': True, 'deleted': path}
    except Exception as ex:
        return {'ok': False, 'error': str(ex)}


# ── File watcher (start/stop) ──────────────────────────────────────────────────
_watcher_thread = None


@router.post('/watch/start')
def start_watcher():
    """Start watchdog to auto-index vault changes."""
    global _watcher_thread
    _ensure_brain()
    vp = _vault_path()
    if not vp:
        return {'ok': False, 'error': 'No vault configured. Set OBSIDIAN_VAULT_PATH or create brain/ folder.'}

    if _watcher_thread and getattr(_watcher_thread, 'is_alive', lambda: False)():
        return {'ok': True, 'status': 'already running', 'vault': str(vp)}

    try:
        from watchdog.events import FileSystemEventHandler
        from watchdog.observers import Observer

        class VaultHandler(FileSystemEventHandler):
            """Data structure or service class representing VaultHandler."""

            def on_modified(self, event):
                """Execute or process on modified operation."""
                if event.src_path.endswith('.md'):
                    _auto_index_file(Path(event.src_path), vp)

            def on_created(self, event):
                """Execute or process on created operation."""
                if event.src_path.endswith('.md'):
                    _auto_index_file(Path(event.src_path), vp)

        observer = Observer()
        observer.schedule(VaultHandler(), str(vp), recursive=True)
        observer.start()
        _watcher_thread = observer
        log.info('Vault watcher started: %s', vp)
        return {'ok': True, 'status': 'started', 'vault': str(vp)}

    except ImportError:
        return {
            'ok': False,
            'error': 'watchdog not installed',
            'install_cmd': 'pip install watchdog',
        }
    except Exception as e:
        return {'ok': False, 'error': str(e)}


@router.post('/watch/stop')
def stop_watcher():
    """Execute or process stop watcher operation."""
    global _watcher_thread
    if _watcher_thread:
        try:
            _watcher_thread.stop()
            _watcher_thread.join(timeout=2)
            _watcher_thread = None
            return {'ok': True, 'status': 'stopped'}
        except Exception as e:
            return {'ok': False, 'error': str(e)}
    return {'ok': True, 'status': 'not running'}


@router.get('/watch/status')
def watcher_status():
    """Execute or process watcher status operation."""
    running = _watcher_thread is not None and getattr(_watcher_thread, 'is_alive', lambda: False)()
    vp = _vault_path()
    return {
        'running': running,
        'vault': str(vp) if vp else None,
        'install_cmd': 'pip install watchdog' if not running else None,
    }


# ── Backlink graph ─────────────────────────────────────────────────────────────
@router.get('/backlinks')
def get_backlinks(note: str = ''):
    """Return backlink graph for a note or all notes."""
    _ensure_brain()
    vp = _vault_path()
    if not vp:
        return {'ok': False, 'error': 'No vault configured'}

    notes = list(vp.rglob('*.md'))
    graph: dict = {}

    for n in notes:
        try:
            content = n.read_text(encoding='utf-8', errors='ignore')
            links = re.findall(r'\[\[([^\]|]+?)(?:\|[^\]]+)?\]\]', content)
            src = n.stem
            if src not in graph:
                graph[src] = {'links': [], 'backlinks': []}
            for lnk in links:
                lnk = lnk.strip()
                graph[src]['links'].append(lnk)
                if lnk not in graph:
                    graph[lnk] = {'links': [], 'backlinks': []}
                graph[lnk]['backlinks'].append(src)
        except (KeyError, TypeError, ValueError, json.JSONDecodeError, OSError, AttributeError, RuntimeError):
            pass

    if note:
        return {'ok': True, 'note': note, 'data': graph.get(note, {'links': [], 'backlinks': []})}
    return {'ok': True, 'graph': graph, 'node_count': len(graph)}


# ── Helpers ────────────────────────────────────────────────────────────────────
def _extract_tags(content: str, path: Path) -> str:
    tags = {'obsidian'}
    folder = path.parent.name.lower().replace(' ', '_')
    if folder:
        tags.add(folder)
    # frontmatter tags
    fm_match = re.match(r'^---\s*\n(.*?)\n---', content, re.DOTALL)
    if fm_match:
        fm = fm_match.group(1)
        # tags: [a, b, c]
        t = re.search(r'tags:\s*\[([^\]]+)\]', fm)
        if t:
            tags.update(x.strip().strip('"\'') for x in t.group(1).split(','))
        # tags:\n  - a\n  - b
        t2 = re.findall(r'tags:\s*\n((?:\s+-\s+\S+\n?)+)', fm)
        if t2:
            tags.update(re.findall(r'-\s+(\S+)', t2[0]))
    # inline #tags (first 500 chars)
    inline = re.findall(r'#([a-zA-Z][\w/]*)', content[:500])
    tags.update(t.lower() for t in inline[:10])
    return ','.join(sorted(tags))[:256]


def _strip_frontmatter(content: str) -> str:
    return re.sub(r'^---\s*\n.*?\n---\s*\n', '', content, flags=re.DOTALL).strip()


def _chunk_text(text: str, max_chars: int = 1200) -> list[str]:
    if len(text) <= max_chars:
        return [text]
    chunks: list = []
    current: list = []
    current_len = 0
    for line in text.split('\n'):
        line_len = len(line) + 1
        if current_len + line_len >= max_chars and current:
            chunks.append('\n'.join(current))
            current = []
            current_len = 0
        current.append(line)
        current_len += line_len
    if current:
        chunks.append('\n'.join(current))
    return chunks or [text]


def _auto_index_file(path: Path, vault_root: Path):
    """Auto-index a single changed file into Memory Galaxy."""
    try:
        from ..services.memory_db import memory_add

        content = path.read_text(encoding='utf-8', errors='ignore')
        if content.strip():
            tags = _extract_tags(content, path)
            clean = _strip_frontmatter(content)
            source = f'obsidian:{path.relative_to(vault_root).as_posix()}'
            memory_add(source, f'# {path.stem}\n\n{clean}'[:1200], tags)
            log.debug('Auto-indexed: %s', path.name)
    except Exception as e:
        log.warning('Auto-index failed %s: %s', path.name, e)
