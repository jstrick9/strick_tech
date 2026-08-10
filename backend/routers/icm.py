"""ICM workspace API (`/api/icm`).

Folder-as-architecture workspaces: numbered stages, markdown stage contracts,
layered context assembly. See backend/services/icm.py for the methodology and
backend/services/icm.py's module docstring for the source paper.

This router is deliberately thin. Every rule lives in the service so that
chat.py can assemble context without an HTTP round trip, and so the rules are
testable without a client.
"""

from __future__ import annotations

from typing import Any

from fastapi import APIRouter, HTTPException, Request

from ..services import icm as svc
from ..services.request_body import as_text, json_body_or_error

router = APIRouter(prefix='/api/icm', tags=['icm'])


def _require_ws(workspace_id: str):
    """Resolve an existing workspace or raise the right error."""
    ws = svc.workspace_dir(workspace_id)
    if ws is None:
        raise HTTPException(status_code=400, detail=f'Invalid workspace id {workspace_id!r}')
    if not ws.is_dir():
        raise HTTPException(status_code=404, detail=f'Workspace {workspace_id!r} not found')
    return ws


@router.get('/workspaces')
def list_workspaces() -> dict[str, Any]:
    """List ICM workspaces with their stage progress."""
    out = []
    for d in sorted(svc.WORKSPACES_DIR.iterdir()) if svc.WORKSPACES_DIR.is_dir() else []:
        if not d.is_dir() or d.name.startswith('.'):
            continue
        stages = svc.list_stages(d)
        entry, reason = svc.resolve_entry(d)
        meta = svc.read_meta(d)
        out.append({
            'workspace_id': d.name,
            'name': meta.get('name', d.name),
            'description': meta.get('description', ''),
            'stage_count': len(stages),
            'stages_complete': sum(1 for s in stages if s['complete']),
            'entry_stage': entry,
            'entry_reason': reason,
        })
    return {'ok': True, 'count': len(out), 'workspaces': out}


@router.post('/workspaces')
async def create_workspace(req: Request) -> dict[str, Any]:
    """Scaffold a workspace from a name and a list of stage names."""
    body, err = await json_body_or_error(req)
    if err:
        return err

    wid = (as_text(body.get('workspace_id')) or '').strip().lower()
    name = (as_text(body.get('name')) or '').strip()
    if not wid:
        wid = svc._slug(name, '')
    if not wid or not svc.WORKSPACE_ID_RE.match(wid):
        raise HTTPException(
            status_code=400,
            detail='workspace_id must be lowercase alphanumeric with - or _ (max 64 chars).',
        )
    ws = svc.workspace_dir(wid)
    if ws is None:
        raise HTTPException(status_code=400, detail='Invalid workspace id')
    if ws.exists():
        raise HTTPException(status_code=409, detail=f'Workspace {wid!r} already exists')

    raw_stages = body.get('stages') or []
    if not isinstance(raw_stages, list):
        raise HTTPException(status_code=400, detail='stages must be a list of stage names')
    stages = [s for s in (as_text(x).strip() for x in raw_stages) if s]
    if not stages:
        # A workspace with no stages has no pipeline and no entry point, so it
        # would fail its own walk test the moment it was created.
        raise HTTPException(
            status_code=422,
            detail='At least one stage is required. The numbered stages are what encode the workflow.',
        )
    if len(stages) > 50:
        raise HTTPException(status_code=422, detail='At most 50 stages.')

    meta = svc.scaffold(ws, name or wid, (as_text(body.get('description')) or '').strip(), stages)
    return {'ok': True, 'workspace': meta}


@router.get('/workspaces/{workspace_id}')
def get_workspace(workspace_id: str) -> dict[str, Any]:
    """Workspace detail: stages, contracts, and where an agent should start."""
    ws = _require_ws(workspace_id)
    stages = svc.list_stages(ws)
    entry, reason = svc.resolve_entry(ws)
    detailed = []
    for s in stages:
        cpath = ws / 'stages' / s['dir'] / 'CONTEXT.md'
        contract = svc.parse_contract(svc._read(cpath)) if cpath.is_file() else None
        detailed.append({**s, 'contract': contract})
    return {
        'ok': True,
        'workspace_id': workspace_id,
        'meta': svc.read_meta(ws),
        'stages': detailed,
        'entry_stage': entry,
        'entry_reason': reason,
    }


@router.delete('/workspaces/{workspace_id}')
def delete_workspace(workspace_id: str) -> dict[str, Any]:
    """Delete a workspace and everything in it."""
    ws = _require_ws(workspace_id)
    import shutil

    shutil.rmtree(ws)
    return {'ok': True, 'deleted': workspace_id}


@router.get('/workspaces/{workspace_id}/entry')
def get_entry(workspace_id: str) -> dict[str, Any]:
    """Where should an agent start?

    Exists because the known ICM failure mode in practice is an agent starting
    in the wrong folder: the layered context never loads, guidelines are missed,
    and the run looks fine. Callers ask here instead of remembering a path.
    """
    ws = _require_ws(workspace_id)
    entry, reason = svc.resolve_entry(ws)
    return {'ok': True, 'workspace_id': workspace_id, 'entry_stage': entry, 'reason': reason}


@router.get('/workspaces/{workspace_id}/context')
def get_context(workspace_id: str, stage: str = '') -> dict[str, Any]:
    """Assemble the layered context for a stage.

    Omit `stage` and the entry point is resolved automatically.
    """
    ws = _require_ws(workspace_id)
    resolved, reason = svc.resolve_entry(ws, stage)
    if not resolved:
        raise HTTPException(status_code=404, detail=reason)
    out = svc.assemble_context(ws, resolved)
    out.update({'ok': True, 'workspace_id': workspace_id, 'entry_reason': reason})
    return out


@router.get('/workspaces/{workspace_id}/validate')
def validate_workspace(workspace_id: str) -> dict[str, Any]:
    """Run the walk test and the convention checks."""
    ws = _require_ws(workspace_id)
    return {'ok': True, 'workspace_id': workspace_id, **svc.validate(ws)}


@router.get('/workspaces/{workspace_id}/file')
def read_file(workspace_id: str, path: str) -> dict[str, Any]:
    """Read one file inside a workspace.

    Every artifact is an edit surface, so the UI needs to show them. The path
    is confined to the workspace: this content is shown to users and can be fed
    to a model, so traversal here would be an arbitrary-file-read.
    """
    ws = _require_ws(workspace_id)
    target = (ws / path).resolve()
    try:
        target.relative_to(ws.resolve())
    except ValueError:
        raise HTTPException(status_code=400, detail='Path escapes the workspace') from None
    if not target.is_file():
        raise HTTPException(status_code=404, detail=f'No such file: {path}')
    return {'ok': True, 'path': path, 'content': svc._read(target)}


@router.put('/workspaces/{workspace_id}/file')
async def write_file(workspace_id: str, req: Request) -> dict[str, Any]:
    """Write one file inside a workspace.

    "Every output is an edit surface": a human reviews and edits between
    stages, and the next stage picks up the edited version.
    """
    ws = _require_ws(workspace_id)
    body, err = await json_body_or_error(req)
    if err:
        return err
    path = (as_text(body.get('path')) or '').strip()
    if not path:
        raise HTTPException(status_code=400, detail='path is required')
    content = body.get('content')
    if content is None:
        # An absent field wrote nothing and used to be indistinguishable from a
        # real save in this codebase's other routers; refuse instead.
        raise HTTPException(status_code=422, detail='content is required (send "" to clear the file)')

    target = (ws / path).resolve()
    try:
        target.relative_to(ws.resolve())
    except ValueError:
        raise HTTPException(status_code=400, detail='Path escapes the workspace') from None
    target.parent.mkdir(parents=True, exist_ok=True)
    target.write_text(as_text(content), encoding='utf-8')
    return {'ok': True, 'path': path, 'bytes': len(as_text(content))}
