"""
Agentic OS — Project Workspaces Router
Switch between multiple projects (client A, client B, personal).
Export any project as ZIP. Import from GitHub. Full project isolation.
"""

from __future__ import annotations

import contextlib

import io
import json
import logging
import shutil
import time
import uuid
import zipfile
from pathlib import Path

from fastapi import APIRouter, Request
from fastapi.responses import StreamingResponse

from ..services.memory_db import audit_log, get_conn

router = APIRouter(prefix='/api/workspaces', tags=['workspaces'])
log = logging.getLogger('agentic.workspaces')

from backend.config import get_data_dir
ROOT = get_data_dir()
PREVIEW_DIR = ROOT / 'preview'
WS_DIR = ROOT / 'workspaces'
WS_DIR.mkdir(exist_ok=True)
CURRENT_FILE = WS_DIR / '.current'


def _ensure_table():
    con = get_conn()
    try:
        con.execute("""
        CREATE TABLE IF NOT EXISTS workspaces (
        id          TEXT PRIMARY KEY,
        name        TEXT NOT NULL,
        description TEXT DEFAULT '',
        color       TEXT DEFAULT '#5b8af8',
        emoji       TEXT DEFAULT '📁',
        framework   TEXT DEFAULT 'web',
        github_repo TEXT DEFAULT '',
        is_active   INTEGER DEFAULT 0,
        created_at  TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
        updated_at  TIMESTAMP DEFAULT CURRENT_TIMESTAMP
        )
        """)
        con.commit()
        # Seed default workspace
        count = con.execute('SELECT COUNT(*) FROM workspaces').fetchone()[0]
        if count == 0:
            wid = str(uuid.uuid4())[:8]
            con.execute(
                'INSERT INTO workspaces(id,name,description,is_active) VALUES(?,?,?,1)',
                (wid, 'My Project', 'Default workspace'),
            )
            con.commit()
            CURRENT_FILE.write_text(wid)
    finally:
        con.close()


try:
    _ensure_table()
except Exception as _e:
    log.error('workspaces: DB init failed — %s', _e)


def _current_ws_id() -> str:
    if CURRENT_FILE.exists():
        return CURRENT_FILE.read_text().strip()
    con = get_conn()
    try:
        row = con.execute('SELECT id FROM workspaces WHERE is_active=1 LIMIT 1').fetchone()
    finally:
        con.close()
    return row['id'] if row else ''


def _ensure_preview_index(directory: Path) -> None:
    """Every workspace needs a valid preview target, even before its first edit."""
    index = directory / 'index.html'
    if not index.exists():
        index.write_text(
            '<!DOCTYPE html><html><head><meta charset="utf-8"><title>New Project</title></head>'
            '<body style="font-family:system-ui,sans-serif;padding:32px;color:#334155">'
            '<h2>Your new project is ready</h2><p>Open Studio to start creating.</p></body></html>',
            encoding='utf-8',
        )


def _ws_preview_dir(ws_id: str) -> Path:
    d = WS_DIR / ws_id / 'preview'
    d.mkdir(parents=True, exist_ok=True)
    _ensure_preview_index(d)
    return d


# ── Endpoints ──────────────────────────────────────────────────────────────────


@router.get('')
def list_workspaces():
    """Retrieve and return list workspaces."""
    con = get_conn()
    try:
        rows = con.execute('SELECT * FROM workspaces ORDER BY is_active DESC, updated_at DESC').fetchall()
    finally:
        con.close()
    current = _current_ws_id()
    result = []
    for r in rows:
        ws = dict(r)
        ws_dir = WS_DIR / ws['id'] / 'preview'
        ws['file_count'] = sum(1 for f in ws_dir.rglob('*') if f.is_file()) if ws_dir.exists() else 0
        ws['is_current'] = ws['id'] == current
        result.append(ws)
    return result


@router.post('')
async def create_workspace(req: Request):
    """Create and initialize a new workspace."""
    try:
        body = await req.json()
    except (json.JSONDecodeError, TypeError, ValueError):
        body = {}
    name = (body.get('name') or 'New Project').strip()[:80]
    wid = str(uuid.uuid4())[:8]
    con = get_conn()
    try:
        con.execute(
            'INSERT INTO workspaces(id,name,description,color,emoji,framework,github_repo) VALUES(?,?,?,?,?,?,?)',
            (
                wid,
                name,
                body.get('description', '')[:200],
                body.get('color', '#5b8af8'),
                body.get('emoji', '📁'),
                body.get('framework', 'web'),
                body.get('github_repo', ''),
            ),
        )
        con.commit()
    finally:
        con.close()
    _ws_preview_dir(wid)  # create dir
    audit_log('workspace_create', f'{wid}: {name}')
    return {'ok': True, 'id': wid, 'name': name}


@router.get('/current')
def current_workspace():
    """Execute or process current workspace operation."""
    ws_id = _current_ws_id()
    if not ws_id:
        return {'ok': False, 'error': 'No workspace'}
    con = get_conn()
    try:
        row = con.execute('SELECT * FROM workspaces WHERE id=?', (ws_id,)).fetchone()
    finally:
        con.close()
    return dict(row) if row else {'ok': False, 'error': 'Not found'}


@router.post('/{ws_id}/activate')
def activate_workspace(ws_id: str):
    """Switch to a workspace — copies its files to preview/."""
    con = get_conn()
    try:
        ws = con.execute('SELECT * FROM workspaces WHERE id=?', (ws_id,)).fetchone()
        if not ws:
            return {'ok': False, 'error': 'Workspace not found'}
    finally:
        con.close()

    # Save current preview/ to current workspace
    current_id = _current_ws_id()
    if current_id and current_id != ws_id:
        _save_preview_to_workspace(current_id)

    # Load new workspace's files into preview/ atomically
    ws_preview = _ws_preview_dir(ws_id)
    if PREVIEW_DIR.exists() and ws_preview != PREVIEW_DIR:
        # Copy new workspace files to a temp dir first, then swap atomically
        tmp_dir = ROOT / f'.preview_tmp_{ws_id}'
        try:
            if ws_preview.exists():
                shutil.copytree(str(ws_preview), str(tmp_dir), dirs_exist_ok=False)
            else:
                tmp_dir.mkdir(parents=True, exist_ok=True)
            shutil.rmtree(PREVIEW_DIR, ignore_errors=True)
            PREVIEW_DIR.mkdir(exist_ok=True)
            if tmp_dir.exists():
                shutil.copytree(str(tmp_dir), str(PREVIEW_DIR), dirs_exist_ok=True)
        except Exception as _e:
            log.error('activate_workspace copy failed: %s', _e)
            # Restore from tmp if possible
            if tmp_dir.exists() and not PREVIEW_DIR.exists():
                PREVIEW_DIR.mkdir(exist_ok=True)
                shutil.copytree(str(tmp_dir), str(PREVIEW_DIR), dirs_exist_ok=True)
        finally:
            shutil.rmtree(str(tmp_dir), ignore_errors=True)

    # Update DB — need a fresh connection (previous was closed in try/finally above)
    con2 = get_conn()
    try:
        con2.execute('UPDATE workspaces SET is_active=0')
        con2.execute('UPDATE workspaces SET is_active=1, updated_at=CURRENT_TIMESTAMP WHERE id=?', (ws_id,))
        con2.commit()
    finally:
        con2.close()
    CURRENT_FILE.write_text(ws_id)
    audit_log('workspace_activate', ws_id)
    return {'ok': True, 'id': ws_id, 'name': dict(ws)['name']}


def _save_preview_to_workspace(ws_id: str) -> bool:
    """Sync current preview/ → workspace storage. Returns True on success."""
    if not PREVIEW_DIR.exists():
        return True
    ws_preview = _ws_preview_dir(ws_id)
    try:
        # Copy to temp first for safety
        tmp = ws_preview.parent / f'.preview_save_tmp_{ws_id}'
        shutil.copytree(str(PREVIEW_DIR), str(tmp), dirs_exist_ok=False)
        shutil.rmtree(str(ws_preview), ignore_errors=True)
        ws_preview.mkdir(parents=True, exist_ok=True)
        shutil.copytree(str(tmp), str(ws_preview), dirs_exist_ok=True)
        return True
    except Exception as e:
        log.error('_save_preview_to_workspace failed for %s: %s', ws_id, e)
        return False
    finally:
        tmp = ws_preview.parent / f'.preview_save_tmp_{ws_id}'
        shutil.rmtree(str(tmp), ignore_errors=True)


@router.post('/{ws_id}/save')
def save_workspace(ws_id: str):
    """Manually save current preview/ to workspace storage."""
    _save_preview_to_workspace(ws_id)
    con = get_conn()
    try:
        con.execute('UPDATE workspaces SET updated_at=CURRENT_TIMESTAMP WHERE id=?', (ws_id,))
        con.commit()
    finally:
        con.close()
    return {'ok': True}


@router.patch('/{ws_id}')
async def update_workspace(ws_id: str, req: Request):
    """Update existing workspace record or state."""
    try:
        body = await req.json()
    except (json.JSONDecodeError, TypeError, ValueError):
        body = {}
    allowed = {'name', 'description', 'color', 'emoji', 'framework', 'github_repo'}
    sets, vals = [], []
    _limits = {'name': 80, 'description': 500, 'color': 20, 'emoji': 8, 'framework': 50, 'github_repo': 200}
    for k in allowed:
        if k in body:
            limit = _limits.get(k, 200)
            sets.append(f'{k}=?')
            vals.append(str(body[k])[:limit])
    if not sets:
        return {'ok': False}
    sets.append('updated_at=CURRENT_TIMESTAMP')
    vals.append(ws_id)
    con = get_conn()
    try:
        con.execute(f'UPDATE workspaces SET {", ".join(sets)} WHERE id=?', vals)
        con.commit()
    finally:
        con.close()
    return {'ok': True}


@router.delete('/{ws_id}')
def delete_workspace(ws_id: str):
    """Delete or remove specified workspace."""
    current = _current_ws_id()
    if ws_id == current:
        return {'ok': False, 'error': 'Cannot delete active workspace'}
    con = get_conn()
    try:
        con.execute('DELETE FROM workspaces WHERE id=?', (ws_id,))
        con.commit()
    finally:
        con.close()
    ws_dir = WS_DIR / ws_id
    shutil.rmtree(str(ws_dir), ignore_errors=True)
    audit_log('workspace_delete', ws_id)
    return {'ok': True}


# ── Export as ZIP ──────────────────────────────────────────────────────────────
@router.get('/{ws_id}/export')
def export_workspace_zip(ws_id: str):
    """Download the workspace as a ZIP file."""
    # Only sync if this is the currently active workspace
    if ws_id == _current_ws_id():
        _save_preview_to_workspace(ws_id)
    ws_preview = _ws_preview_dir(ws_id)

    con = get_conn()
    try:
        ws = con.execute('SELECT name FROM workspaces WHERE id=?', (ws_id,)).fetchone()
    finally:
        con.close()
    name = dict(ws)['name'] if ws else ws_id
    safe_name = ''.join(c for c in name if c.isalnum() or c in ' -_').strip().replace(' ', '_')

    buf = io.BytesIO()
    with zipfile.ZipFile(buf, 'w', zipfile.ZIP_DEFLATED) as zf:
        # Add all preview files
        for f in sorted(ws_preview.rglob('*')):
            if f.is_file() and '.git' not in str(f):
                rel = f.relative_to(ws_preview).as_posix()
                zf.write(f, rel)
        # Add a README
        readme = f'# {name}\n\nExported from Agentic OS — {time.strftime("%Y-%m-%d")}\n\nBuilt with Agentic OS Platform (https://github.com/jstrick9/strick_tech)\n'
        zf.writestr('README.md', readme)

    buf.seek(0)
    audit_log('workspace_export', ws_id)
    return StreamingResponse(
        iter([buf.read()]),
        media_type='application/zip',
        headers={'Content-Disposition': f'attachment; filename="{safe_name}.zip"'},
    )


# ── Export current preview as ZIP ──────────────────────────────────────────────
@router.get('/export/current')
def export_current_zip():
    """Download current preview/ as a ZIP."""
    buf = io.BytesIO()
    with zipfile.ZipFile(buf, 'w', zipfile.ZIP_DEFLATED) as zf:
        for f in sorted(PREVIEW_DIR.rglob('*')):
            if f.is_file() and '.git' not in str(f) and 'branches' not in str(f):
                rel = f.relative_to(PREVIEW_DIR).as_posix()
                zf.write(f, rel)
        zf.writestr('README.md', f'# Agentic OS Export\n\nExported: {time.strftime("%Y-%m-%d %H:%M")}\n')
    buf.seek(0)
    audit_log('export_zip', 'current preview')
    return StreamingResponse(
        iter([buf.read()]),
        media_type='application/zip',
        headers={'Content-Disposition': 'attachment; filename="agentic-os-project.zip"'},
    )


# ── Import from GitHub ─────────────────────────────────────────────────────────
@router.post('/import/github')
async def import_from_github(req: Request):
    """Import files from a GitHub repository into a new workspace."""
    try:
        body = await req.json()
    except (json.JSONDecodeError, TypeError, ValueError):
        body = {}
    repo_name = body.get('repo', '').strip()
    branch = body.get('branch', 'main')
    ws_name = body.get('name', repo_name.split('/')[-1] if '/' in repo_name else repo_name)

    if not repo_name:
        return {'ok': False, 'error': 'repo required (e.g. username/my-repo)'}

    # Create workspace
    new_ws = await create_workspace(_make_internal_request({'name': ws_name, 'github_repo': repo_name}))
    ws_id = new_ws['id']
    ws_preview = _ws_preview_dir(ws_id)

    # Pull files using GitHub router
    from .github import pull_from_github

    result = await pull_from_github(
        _make_internal_request({'repo': repo_name, 'branch': branch, 'target': str(ws_preview)})
    )

    if result.get('ok'):
        return {'ok': True, 'workspace_id': ws_id, 'name': ws_name, 'files_imported': result.get('files_pulled', 0)}
    else:
        # Clean up the zombie workspace created before import failed
        with contextlib.suppress(Exception):
            delete_workspace(ws_id)
        return {'ok': False, 'error': result.get('error', 'Import failed')}


def _fake_recv(data: dict):
    """Create an ASGI receive callable with complete scope for internal use."""
    body_bytes = json.dumps(data).encode()

    async def receive():
        """Execute or process receive operation."""
        return {'type': 'http.request', 'body': body_bytes, 'more_body': False}

    return receive


def _make_internal_request(data: dict) -> Request:
    """Build a minimal FastAPI Request for internal delegation."""
    return Request(
        scope={
            'type': 'http',
            'method': 'POST',
            'path': '/internal',
            'query_string': b'',
            'headers': [(b'content-type', b'application/json')],
        },
        receive=_fake_recv(data),
    )
