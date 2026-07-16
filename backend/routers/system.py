"""
Agentic OS — System Monitor Router
Real-time CPU, RAM, disk, process health, HMR file watcher.
"""

from __future__ import annotations

import contextlib

import asyncio
import json
import logging
import os
import time
from pathlib import Path

from fastapi import APIRouter, Request
from fastapi.responses import StreamingResponse

router = APIRouter(prefix='/api/system', tags=['system'])
log = logging.getLogger('agentic.system')

from backend.config import get_data_dir
ROOT = get_data_dir()


# ── Health & metrics ───────────────────────────────────────────────────────────
@router.get('/health')
def system_health():
    """Full system health snapshot."""
    info = _system_info()
    disk = _disk_info()
    db = _db_health()
    procs = _key_processes()
    return {
        'ok': True,
        'timestamp': time.time(),
        'system': info,
        'disk': disk,
        'database': db,
        'processes': procs,
        'version': '6.0.0',
    }


@router.get('/metrics')
def metrics():
    """Lightweight metrics for status bar polling (fast)."""
    try:
        import psutil

        cpu = psutil.cpu_percent(interval=0.1)
        ram = psutil.virtual_memory()
        return {
            'cpu_pct': cpu,
            'ram_pct': ram.percent,
            'ram_used_mb': round(ram.used / 1024 / 1024),
            'ram_total_mb': round(ram.total / 1024 / 1024),
        }
    except ImportError:
        return {'cpu_pct': 0, 'ram_pct': 0, 'ram_used_mb': 0, 'ram_total_mb': 0, 'psutil': False}


@router.get('/info')
def system_info():
    """Execute or process system info operation."""
    return _system_info()


# ── HMR — file-watch + auto-broadcast ─────────────────────────────────────────
import threading as _threading_hmr

_hmr_watchers: dict[str, float] = {}  # path → last_mtime
_hmr_clients: list = []  # SSE queues
_hmr_lock = _threading_hmr.Lock()  # protects _hmr_clients across threads


@router.get('/hmr')
async def hmr_stream(request: Request):
    """
    SSE stream: GET /api/system/hmr
    Client subscribes; when preview/ files change, events are pushed.
    Frontend uses this to auto-reload the preview iframe.
    """
    queue: asyncio.Queue = asyncio.Queue(maxsize=50)
    with _hmr_lock:
        _hmr_clients.append(queue)

    async def generate():
        """Execute or process generate operation."""
        try:
            yield 'data: {"type":"connected"}\n\n'
            while True:
                if await request.is_disconnected():
                    break
                try:
                    event = await asyncio.wait_for(queue.get(), timeout=15.0)
                    yield f'data: {json.dumps(event)}\n\n'
                except asyncio.TimeoutError:
                    yield 'data: {"type":"ping"}\n\n'
        finally:
            with _hmr_lock:
                try:
                    _hmr_clients.remove(queue)
                except ValueError:
                    pass

    return StreamingResponse(
        generate(), media_type='text/event-stream', headers={'Cache-Control': 'no-cache', 'X-Accel-Buffering': 'no'}
    )


async def _hmr_broadcast(event: dict):
    """Broadcast HMR event to all connected SSE clients (thread-safe)."""
    with _hmr_lock:
        clients_snapshot = list(_hmr_clients)
    dead = []
    for q in clients_snapshot:
        try:
            q.put_nowait(event)
        except asyncio.QueueFull:
            dead.append(q)
    if dead:
        with _hmr_lock:
            for q in dead:
                try:
                    _hmr_clients.remove(q)
                except ValueError:
                    pass


async def _watch_preview_dir():
    """Background task: watch preview/ for file changes → broadcast HMR."""
    preview = ROOT / 'preview'
    preview.mkdir(exist_ok=True)
    log.info('HMR watcher started on %s', preview)

    while True:
        try:
            changed = []
            for f in preview.rglob('*'):
                if not f.is_file() or '.git' in str(f):
                    continue
                mtime = f.stat().st_mtime
                key = str(f)
                if key in _hmr_watchers:
                    if mtime > _hmr_watchers[key] + 0.5:
                        changed.append(f.relative_to(preview).as_posix())
                _hmr_watchers[key] = mtime

            for path in changed:
                await _hmr_broadcast({'type': 'file_changed', 'path': path, 'ts': time.time()})
                log.debug('HMR: %s changed', path)

        except Exception as e:
            log.warning('HMR watch error: %s', e)

        await asyncio.sleep(0.8)  # poll every 800ms


# HMR watcher is started by the FastAPI app lifespan (see app.py _watch_preview_dir startup).
# The thread is kept as a fallback for environments where lifespan is not used.
import asyncio as _asyncio
import threading as _hmr_threading_mod

_hmr_thread_started = False


def _ensure_hmr_thread():
    """Start HMR watcher thread exactly once (guarded against re-import)."""
    global _hmr_thread_started
    if _hmr_thread_started:
        return
    _hmr_thread_started = True

    def _start():
        loop = _asyncio.new_event_loop()
        _asyncio.set_event_loop(loop)
        loop.run_until_complete(_watch_preview_dir())

    t = _hmr_threading_mod.Thread(target=_start, daemon=True, name='hmr-watcher')
    t.start()


_ensure_hmr_thread()


@router.post('/hmr/trigger')
async def hmr_trigger(req: Request):
    """Manually trigger HMR for a specific file (called after save)."""
    try:
        body = await req.json()
    except (json.JSONDecodeError, TypeError, ValueError):
        body = {}
    path = body.get('path', '')
    await _hmr_broadcast({'type': 'file_changed', 'path': path, 'ts': time.time(), 'source': 'manual'})
    return {'ok': True, 'clients': len(_hmr_clients)}


@router.get('/hmr/status')
def hmr_status():
    """Execute or process hmr status operation."""
    return {
        'clients': len(_hmr_clients),
        'watching': len(_hmr_watchers),
        'watch_dir': str(ROOT / 'preview'),
    }


# ── Git status ─────────────────────────────────────────────────────────────────
@router.get('/git')
def git_status():
    """Real git status of the project (requires gitpython)."""
    try:
        import git

        repo = git.Repo(ROOT, search_parent_directories=True)
        branch = repo.active_branch.name
        commits = list(repo.iter_commits(max_count=5))
        dirty = repo.is_dirty()
        untracked = repo.untracked_files[:10]
        staged = [item.a_path for item in repo.index.diff('HEAD')][:10]
        unstaged = [item.a_path for item in repo.index.diff(None)][:10]
        return {
            'ok': True,
            'branch': branch,
            'dirty': dirty,
            'untracked': untracked,
            'staged': staged,
            'unstaged': unstaged,
            'recent_commits': [
                {
                    'hash': c.hexsha[:8],
                    'message': c.message.strip()[:80],
                    'author': str(c.author),
                    'date': c.committed_datetime.isoformat()[:10],
                }
                for c in commits
            ],
        }
    except ImportError:
        return {'ok': False, 'error': 'gitpython not installed. pip install gitpython'}
    except Exception as e:
        return {'ok': False, 'error': str(e), 'tip': 'Not a git repo, or git not configured'}


@router.post('/git/commit')
async def git_commit(req: Request):
    """Commit all preview/ changes to git."""
    try:
        body = await req.json()
    except (json.JSONDecodeError, TypeError, ValueError):
        body = {}
    message = (body.get('message') or 'Agentic OS checkpoint').strip()[:500]
    if not message:
        message = 'Agentic OS checkpoint'
    try:
        import git

        repo = git.Repo(ROOT, search_parent_directories=True)
        repo.git.add(str(ROOT / 'preview'))
        if repo.is_dirty(index=True):
            commit = repo.index.commit(message)
            return {'ok': True, 'hash': commit.hexsha[:8], 'message': message}
        return {'ok': True, 'message': 'Nothing to commit', 'clean': True}
    except Exception as e:
        return {'ok': False, 'error': str(e)}


# ── Helpers ────────────────────────────────────────────────────────────────────
def _system_info() -> dict:
    try:
        import platform

        import psutil

        cpu = psutil.cpu_percent(interval=0.1)
        ram = psutil.virtual_memory()
        py_proc = psutil.Process(os.getpid())
        return {
            'platform': platform.system(),
            'python': platform.python_version(),
            'cpu_pct': cpu,
            'cpu_count': psutil.cpu_count(),
            'ram_pct': ram.percent,
            'ram_used_mb': round(ram.used / 1024 / 1024),
            'ram_total_mb': round(ram.total / 1024 / 1024),
            'process_ram_mb': round(py_proc.memory_info().rss / 1024 / 1024),
            'process_cpu': py_proc.cpu_percent(interval=0.1),
            'pid': os.getpid(),
        }
    except ImportError:
        return {'psutil': False, 'pid': os.getpid()}


def _disk_info() -> dict:
    try:
        import psutil

        disk = psutil.disk_usage(str(ROOT))
        db = ROOT / 'memory' / 'agentic.db'
        return {
            'total_gb': round(disk.total / 1e9, 1),
            'used_gb': round(disk.used / 1e9, 1),
            'free_gb': round(disk.free / 1e9, 1),
            'pct': disk.percent,
            'db_mb': round(db.stat().st_size / 1024 / 1024, 2) if db.exists() else 0,
        }
    except Exception as e:
        return {'error': str(e)}


def _db_health() -> dict:
    from ..services.memory_db import get_conn

    con = None
    try:
        con = get_conn()
        tables = [r[0] for r in con.execute("SELECT name FROM sqlite_master WHERE type='table'").fetchall()]
        counts = {}
        _SAFE_TABLES = {'memory', 'tasks', 'agents', 'chat_log', 'file_versions', 'audit'}
        for t in _SAFE_TABLES:
            if t in tables:
                # Use parameterized-style: table names from whitelist are safe
                counts[t] = con.execute(f'SELECT COUNT(*) FROM "{t}"').fetchone()[0]
        return {'ok': True, 'tables': len(tables), 'counts': counts}
    except Exception as e:
        log.warning('_db_health error: %s', e)
        return {'ok': False, 'error': str(e)}
    finally:
        if con:
            con.close()


def _key_processes() -> list:
    try:
        import psutil

        procs = []
        for proc in psutil.process_iter(['pid', 'name', 'status', 'memory_info']):
            name = proc.info.get('name', '')
            if any(k in name.lower() for k in ['python', 'uvicorn', 'node', 'ollama']):
                procs.append(
                    {
                        'pid': proc.info['pid'],
                        'name': name,
                        'status': proc.info.get('status'),
                        'ram_mb': round(
                            (proc.info.get('memory_info') or type('', (), {'rss': 0})()).rss / 1024 / 1024, 1
                        ),
                    }
                )
        return procs[:10]
    except (KeyError, TypeError, ValueError, json.JSONDecodeError, OSError, AttributeError, RuntimeError):
        return []
