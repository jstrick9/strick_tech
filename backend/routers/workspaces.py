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
import re
import shutil
import threading
import time
import uuid
import zipfile
from pathlib import Path

from fastapi import APIRouter, Request
from fastapi.responses import JSONResponse, StreamingResponse

from ..services.memory_db import audit_log, get_conn
from ..services.safe_paths import safe_path

router = APIRouter(prefix='/api/workspaces', tags=['workspaces'])
log = logging.getLogger('agentic.workspaces')

from backend.config import get_data_dir

from ..services.request_body import as_text, json_body_or_error

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


# Workspace ids are generated as uuid4[:8] and are the ONLY thing standing
# between a request and a filesystem path: delete_workspace() previously did
#     shutil.rmtree(WS_DIR / ws_id)
# with no validation whatsoever. Proven by direct call with the data dir
# redirected to /tmp: `delete_workspace('../precious')` removed
# /tmp/wsdata/precious entirely. Reaching it over HTTP is currently blocked by
# ASGI path normalisation, which is a property of the server in front of the
# code rather than of the code -- an internal caller, a future CLI, or a
# different ASGI server is not protected by it. The guard belongs here.
_WS_ID_RE = re.compile(r'^[A-Za-z0-9_-]{1,64}$')


def _valid_ws_id(ws_id: str) -> bool:
    """True if `ws_id` can be safely used as a single directory name."""
    return bool(_WS_ID_RE.match(ws_id or ''))


def _ws_root(ws_id: str) -> Path:
    """Resolve a workspace directory, refusing anything that escapes WS_DIR.

    Belt and braces: the character class already forbids '/' and '.', and
    safe_path() re-checks containment after resolution so a symlinked
    workspace directory cannot redirect a delete either.
    """
    if not _valid_ws_id(ws_id):
        raise ValueError(f'invalid workspace id: {ws_id!r}')
    resolved = safe_path(ws_id, base=WS_DIR)
    if resolved is None:
        raise ValueError(f'workspace id escapes WS_DIR: {ws_id!r}')
    return resolved


# Directories under preview/ that belong to OTHER modules, not to the user's
# project files. activate_workspace() wipes preview/ wholesale, which destroyed
# every one of these on a workspace switch -- the cross-module bug first seen in
# Module 10, where the image gallery broke permanently after switching
# workspaces. They are preserved across the swap instead of being copied into
# (and duplicated across) every workspace.
SHARED_PREVIEW_DIRS = ('browser_screenshots', 'assets/images', 'branches')


def _stash_shared(preview: Path, stash: Path) -> list[str]:
    """Move shared, non-project artefacts out of preview/ before it is wiped."""
    moved = []
    for rel in SHARED_PREVIEW_DIRS:
        src = preview / rel
        if src.is_dir():
            dst = stash / rel
            dst.parent.mkdir(parents=True, exist_ok=True)
            shutil.move(str(src), str(dst))
            moved.append(rel)
    return moved


def _restore_shared(stash: Path, preview: Path, moved: list[str]) -> None:
    """Put the shared artefacts back after the new workspace has been laid down."""
    for rel in moved:
        src = stash / rel
        if not src.exists():
            continue
        dst = preview / rel
        dst.parent.mkdir(parents=True, exist_ok=True)
        if dst.exists():
            # The incoming workspace shipped its own copy; merge rather than
            # discard either side.
            shutil.copytree(str(src), str(dst), dirs_exist_ok=True)
            shutil.rmtree(str(src), ignore_errors=True)
        else:
            shutil.move(str(src), str(dst))


# DATA-LOSS FIX 2 -- concurrency. activate_workspace() is a read-modify-write
# over a directory tree: save preview/ -> wipe preview/ -> repopulate. Two
# overlapping calls interleave those phases and unsaved work is destroyed.
#
# Reproduced 3 times out of 3 against the live server: with an unsaved file in
# preview/, two simultaneous activations of the same target workspace lost it
# permanently, while the identical sequence run SEQUENTIALLY preserved it.
# That isolates the cause as concurrency rather than the same-workspace path
# fixed above. The trigger is mundane -- the UI's "Switch" button is not
# disabled while its await is in flight, so an impatient double-click issues
# exactly this pair of requests.
#
# A threading.Lock is the right tool here: these are sync (def, not async def)
# endpoints, so FastAPI runs them in a threadpool where a real lock applies,
# and the critical section is filesystem I/O rather than anything awaitable.
_activate_lock = threading.Lock()


def _ws_exists(ws_id: str) -> bool:
    """Is this workspace real -- on disk or in the database?"""
    if not ws_id:
        return False
    if (WS_DIR / ws_id).exists():
        return True
    con = get_conn()
    try:
        return con.execute(
            'SELECT 1 FROM workspaces WHERE id=? LIMIT 1', (ws_id,)
        ).fetchone() is not None
    except Exception:
        return False
    finally:
        con.close()


def _current_ws_id() -> str:
    """The active workspace id, validated before it is trusted.

    THE BUG THIS FIXES. This returned the contents of `.current` whenever the
    FILE existed, without checking the workspace it names still does. Measured
    on a real machine:

        workspaces/.current        -> '6b27c178'  (no such directory)
        workspaces DB is_active=1  -> '71951640'  ('My Project')

    The file won, so the whole application believed the active workspace was a
    phantom. `builder.py` alone uses this id in 8+ places to scope
    `file_versions` queries, so version history and restore silently returned
    nothing for files the user had definitely edited -- an empty list, no
    error.

    A pointer to a deleted workspace is exactly what deleting the workspace
    you are in leaves behind, so this is reachable by ordinary use.

    The file is HEALED rather than merely ignored: leaving it stale means the
    next reader disagrees with this one, and intermittent disagreement is
    harder to diagnose than a consistently wrong answer.
    """
    if CURRENT_FILE.exists():
        pointed = CURRENT_FILE.read_text().strip()
        if pointed and _ws_exists(pointed):
            return pointed

    con = get_conn()
    try:
        row = con.execute(
            'SELECT id FROM workspaces WHERE is_active=1 LIMIT 1').fetchone()
    finally:
        con.close()

    resolved = row['id'] if row else ''
    if resolved:
        try:
            CURRENT_FILE.write_text(resolved)
        except OSError:
            # A read-only data dir must not break resolution.
            pass
    return resolved


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
    body, _body_err = await json_body_or_error(req)
    if _body_err:
        return _body_err
    name = str(as_text(body.get('name')) or 'New Project')[:80]
    description = str(body.get('description') or '')[:200]
    color = str(body.get('color') or '#5b8af8')[:20]
    emoji = str(body.get('emoji') or '📁')[:8]
    framework = str(body.get('framework') or 'web')[:50]
    github_repo = str(body.get('github_repo') or '')[:200]
    wid = str(uuid.uuid4())[:8]
    con = get_conn()
    try:
        con.execute(
            'INSERT INTO workspaces(id,name,description,color,emoji,framework,github_repo) VALUES(?,?,?,?,?,?,?)',
            (
                wid,
                name,
                description,
                color,
                emoji,
                framework,
                github_repo,
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
    # Serialised: see _activate_lock.
    with _activate_lock:
        return _activate_workspace_locked(ws_id)


def _activate_workspace_locked(ws_id: str):
    """Body of activate_workspace(). Callers must hold _activate_lock."""
    if not _valid_ws_id(ws_id):
        return JSONResponse({'ok': False, 'error': 'Invalid workspace id'}, status_code=400)

    con = get_conn()
    try:
        ws = con.execute('SELECT * FROM workspaces WHERE id=?', (ws_id,)).fetchone()
        if not ws:
            return JSONResponse({'ok': False, 'error': 'Workspace not found'}, status_code=404)
    finally:
        con.close()

    current_id = _current_ws_id()

    # DATA-LOSS FIX 1. The save was guarded by `current_id != ws_id`, but the
    # rmtree below was NOT. Activating the workspace you are ALREADY on
    # skipped the save and then wiped preview/ anyway, restoring the
    # last-saved copy over the top.
    #
    # CORRECTION to an earlier draft of this comment: the Workspaces pane does
    # NOT render a "Switch" button on the active card, so this is not reachable
    # by a single click there. It is reachable through the API directly, and
    # through any second caller that activates by id without first checking
    # which workspace is current. The guard belongs in the endpoint either way
    # -- an endpoint that destroys unsaved work for one class of caller is a
    # bug regardless of what today's UI happens to render.
    #
    # Reproduced live:
    #   echo "UNSAVED WORK" > preview/unsaved_edit.html
    #   POST /api/workspaces/537b5b7d/activate   (537b5b7d was already current)
    #   -> {"ok": true}   and unsaved_edit.html was GONE, unrecoverably.
    #
    # Switching to a DIFFERENT workspace was survivable because the outgoing
    # one got saved first and switching back restored it. This case had no
    # such recovery: the only copy of the work was the one that was deleted.
    #
    # The save now happens whenever there is a current workspace, full stop.
    if current_id:
        _save_preview_to_workspace(current_id)

    # Re-activating the current workspace is now a no-op for the filesystem.
    # Its files were just saved and are already in preview/; tearing the
    # directory down and rebuilding it identically only creates a window in
    # which preview/ does not exist for the other 20 modules that read it.
    if current_id == ws_id:
        con2 = get_conn()
        try:
            con2.execute('UPDATE workspaces SET updated_at=CURRENT_TIMESTAMP WHERE id=?', (ws_id,))
            con2.commit()
        finally:
            con2.close()
        audit_log('workspace_activate', f'{ws_id} (already active — saved, no swap)')
        return {'ok': True, 'id': ws_id, 'name': dict(ws)['name'], 'already_active': True}

    # Load new workspace's files into preview/ atomically
    ws_preview = _ws_preview_dir(ws_id)
    if PREVIEW_DIR.exists() and ws_preview != PREVIEW_DIR:
        # Copy new workspace files to a temp dir first, then swap atomically
        tmp_dir = ROOT / f'.preview_tmp_{ws_id}'
        stash_dir = ROOT / f'.preview_shared_{ws_id}'
        shutil.rmtree(str(stash_dir), ignore_errors=True)
        stash_dir.mkdir(parents=True, exist_ok=True)
        moved: list[str] = []
        try:
            # Preserve artefacts that belong to other modules, not to this
            # project. See SHARED_PREVIEW_DIRS.
            moved = _stash_shared(PREVIEW_DIR, stash_dir)

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
            # Shared artefacts go back even if the swap failed -- they must
            # never be collateral damage of a copy error.
            try:
                PREVIEW_DIR.mkdir(exist_ok=True)
                _restore_shared(stash_dir, PREVIEW_DIR, moved)
            except Exception as _e2:
                log.error('activate_workspace: shared artefact restore failed: %s', _e2)
            shutil.rmtree(str(tmp_dir), ignore_errors=True)
            shutil.rmtree(str(stash_dir), ignore_errors=True)

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
    # Shares the preview/ tree with activate_workspace(); same lock, or a save
    # landing mid-swap writes a half-built directory into workspace storage.
    with _activate_lock:
        return _save_workspace_locked(ws_id)


def _save_workspace_locked(ws_id: str):
    """Body of save_workspace(). Callers must hold _activate_lock."""
    if not _valid_ws_id(ws_id):
        return JSONResponse({'ok': False, 'error': 'Invalid workspace id'}, status_code=400)
    con = get_conn()
    try:
        exists = con.execute('SELECT 1 FROM workspaces WHERE id=?', (ws_id,)).fetchone()
    finally:
        con.close()
    if not exists:
        return JSONResponse({'ok': False, 'error': 'Workspace not found'}, status_code=404)
    if not _save_preview_to_workspace(ws_id):
        return JSONResponse(
            {'ok': False, 'error': 'Could not save workspace files'}, status_code=500
        )
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
    body, _body_err = await json_body_or_error(req)
    if _body_err:
        return _body_err
    if not _valid_ws_id(ws_id):
        return JSONResponse({'ok': False, 'error': 'Invalid workspace id'}, status_code=400)
    allowed = {'name', 'description', 'color', 'emoji', 'framework', 'github_repo'}
    sets, vals = [], []
    _limits = {'name': 80, 'description': 500, 'color': 20, 'emoji': 8, 'framework': 50, 'github_repo': 200}
    for k in allowed:
        if k in body:
            limit = _limits.get(k, 200)
            sets.append(f'{k}=?')
            vals.append(str(body[k])[:limit])
    if not sets:
        return JSONResponse({'ok': False, 'error': 'No updatable fields supplied'}, status_code=400)
    sets.append('updated_at=CURRENT_TIMESTAMP')
    vals.append(ws_id)
    con = get_conn()
    try:
        # UPDATE ... WHERE id=? on a missing row affects 0 rows and raises
        # nothing, so this endpoint answered {"ok": true} for workspaces that
        # do not exist. Verified live: PATCH /api/workspaces/nope123 -> 200
        # {"ok": true}. A rename that silently succeeded against nothing is
        # indistinguishable from one that worked.
        cur = con.execute(f'UPDATE workspaces SET {", ".join(sets)} WHERE id=?', vals)
        con.commit()
        if cur.rowcount == 0:
            return JSONResponse({'ok': False, 'error': 'Workspace not found'}, status_code=404)
    finally:
        con.close()
    return {'ok': True}


@router.delete('/{ws_id}')
def delete_workspace(ws_id: str):
    """Delete or remove specified workspace."""
    # `ws_id` reaches shutil.rmtree(). Validate before anything else.
    if not _valid_ws_id(ws_id):
        return JSONResponse({'ok': False, 'error': 'Invalid workspace id'}, status_code=400)

    current = _current_ws_id()
    if ws_id == current:
        return JSONResponse(
            {'ok': False, 'error': 'Cannot delete active workspace'}, status_code=409
        )

    con = get_conn()
    try:
        row = con.execute('SELECT 1 FROM workspaces WHERE id=?', (ws_id,)).fetchone()
        if not row:
            return JSONResponse({'ok': False, 'error': 'Workspace not found'}, status_code=404)
        con.execute('DELETE FROM workspaces WHERE id=?', (ws_id,))
        con.commit()
    finally:
        con.close()

    try:
        shutil.rmtree(str(_ws_root(ws_id)), ignore_errors=True)
    except ValueError as e:
        log.error('delete_workspace refused unsafe path: %s', e)
    audit_log('workspace_delete', ws_id)
    return {'ok': True}


# ── Export as ZIP ──────────────────────────────────────────────────────────────
@router.get('/{ws_id}/export')
def export_workspace_zip(ws_id: str):
    """Download the workspace as a ZIP file."""
    if not _valid_ws_id(ws_id):
        return JSONResponse({'ok': False, 'error': 'Invalid workspace id'}, status_code=400)

    con = get_conn()
    try:
        ws = con.execute('SELECT name FROM workspaces WHERE id=?', (ws_id,)).fetchone()
    finally:
        con.close()
    # Previously an unknown id fell through to _ws_preview_dir(), which CREATES
    # the directory, so exporting a typo'd id both left a stray workspace
    # directory on disk and returned a valid-looking zip containing only the
    # placeholder index.html. A download that looks like a successful backup
    # but contains none of the user's work is worse than an error.
    if not ws:
        return JSONResponse({'ok': False, 'error': 'Workspace not found'}, status_code=404)

    # Only sync if this is the currently active workspace
    if ws_id == _current_ws_id():
        _save_preview_to_workspace(ws_id)
    ws_preview = _ws_preview_dir(ws_id)

    name = dict(ws)['name']
    # str.isalnum() is True for CJK and most non-Latin scripts, so the original
    # filter passed them straight through into a Content-Disposition header --
    # which Starlette encodes as latin-1. Exporting a workspace named "日本語"
    # therefore crashed with UnicodeEncodeError and returned HTTP 500. Verified
    # live before this fix; found by a test written for the adjacent
    # empty-filename case.
    #
    # Restricted to ASCII alphanumerics, with an id-based fallback so a name
    # that reduces to nothing still yields a real filename rather than ".zip"
    # (which browsers save as a hidden, extensionless file).
    safe_name = ''.join(
        c for c in name if (c.isalnum() and c.isascii()) or c in ' -_'
    ).strip().replace(' ', '_')
    safe_name = safe_name or f'workspace_{ws_id}'

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
    body, _body_err = await json_body_or_error(req)
    if _body_err:
        return _body_err
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
