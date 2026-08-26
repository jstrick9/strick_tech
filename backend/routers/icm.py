"""ICM workspace API (`/api/icm`).

Folder-as-architecture workspaces: numbered stages, markdown stage contracts,
layered context assembly. See backend/services/icm.py for the methodology and
backend/services/icm.py's module docstring for the source paper.

This router is deliberately thin. Every rule lives in the service so that
chat.py can assemble context without an HTTP round trip, and so the rules are
testable without a client.
"""

from __future__ import annotations

from pathlib import Path
from typing import Any

from fastapi import APIRouter, HTTPException, Request

from ..services import icm as svc
from ..services.request_body import as_text, json_body_or_error
from ..services.safe_paths import safe_path

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

    # The walk test NEVER blocks a write. "Every output is an edit surface", and
    # editing is how a broken workspace gets repaired -- refusing the save would
    # gate the repair path itself. The verdict is returned alongside the save so
    # the editor can show it, which is warning-not-blocking on purpose.
    from ..services import icm_gate

    icm_gate.clear_cache()
    verdict = icm_gate.gate(ws, action='write')
    return {'ok': True, 'path': path, 'bytes': len(as_text(content)),
            'walk_test': {'passes': verdict['passes'], 'errors': verdict['errors'],
                          'warnings': verdict['warnings'],
                          'remedies': verdict.get('remedies', [])}}


# ── Ontology ──────────────────────────────────────────────────────────────────
# The controlled vocabulary lives in _config/ontology.md as markdown, following
# the same "plain text as the interface / canonical sources" conventions as the
# rest of ICM. See backend/services/ontology.py for why it is a document rather
# than a schema.
@router.get('/workspaces/{workspace_id}/ontology')
def get_ontology(workspace_id: str) -> dict[str, Any]:
    """The workspace's entity types and relations, parsed and validated."""
    from ..services import ontology as onto_svc

    ws = _require_ws(workspace_id)
    onto = onto_svc.load(ws)
    return {
        'ok': True,
        'workspace_id': workspace_id,
        'defined': onto.get('defined', False),
        'entities': list(onto['entities'].values()),
        'relations': list(onto['relations'].values()),
        'validation': onto_svc.validate(onto),
        'summary': onto_svc.summarise(onto),
    }


@router.post('/workspaces/{workspace_id}/ontology/resolve')
async def resolve_terms(workspace_id: str, req: Request) -> dict[str, Any]:
    """Resolve free-text types/relations onto the workspace vocabulary.

    Returns the canonical term and HOW it matched, so a caller can tell an
    exact hit from a fuzzy rescue and surface that to the user.
    """
    from ..services import ontology as onto_svc

    ws = _require_ws(workspace_id)
    body, err = await json_body_or_error(req)
    if err:
        return err
    onto = onto_svc.load(ws)

    out: dict[str, Any] = {'ok': True, 'workspace_id': workspace_id}
    if body.get('entity_type') is not None:
        out['entity_type'] = onto_svc.resolve_entity_type(onto, as_text(body.get('entity_type')))
    if body.get('relation') is not None:
        out['relation'] = onto_svc.resolve_relation(onto, as_text(body.get('relation')))
    if body.get('relation') is not None and (body.get('from_type') or body.get('to_type')):
        out['domain'] = onto_svc.check_relation_domain(
            onto,
            as_text(body.get('relation')),
            as_text(body.get('from_type')),
            as_text(body.get('to_type')),
        )
    if len(out) == 2:
        raise HTTPException(
            status_code=422,
            detail='Send entity_type and/or relation (optionally with from_type/to_type).',
        )
    return out


# ── entry routing ─────────────────────────────────────────────────────────────
# "The agent has to actually start in the right folder." These endpoints expose
# that decision so it is inspectable rather than implicit: the route table says
# what enters where, /route explains a decision before it is acted on, and
# /route/log is the record of decisions already made.


@router.get('/routes')
def get_route_table() -> dict[str, Any]:
    """The root context map: every workspace and what enters it.

    Generated from the filesystem on every call rather than hand-maintained,
    because a hand-curated index always drifts from the folders it describes.
    """
    from ..services import icm_router as rsvc

    return {'ok': True, 'routes': rsvc.route_table()}


@router.get('/route')
def preview_route(q: str = '', workspace_id: str = '', stage: str = '') -> dict[str, Any]:
    """Explain where a request would enter, without loading or running it.

    Read-only on purpose: this is the "why did it pick that folder" tool, and
    it must be safe to call repeatedly from the UI as the user types.
    """
    from ..services import icm_router as rsvc

    if not str(q).strip():
        raise HTTPException(status_code=422, detail='Send q=<the request text>.')
    return {'ok': True, 'decision': rsvc.resolve(str(q), str(workspace_id), str(stage))}


@router.get('/route/log')
def get_route_log(limit: int = 50) -> dict[str, Any]:
    """Recent routing decisions, newest first.

    `limit` is typed, so FastAPI rejects non-numeric input with a 422 before
    this body runs -- an earlier draft wrapped the int() in a try/except that
    could never fire. Out-of-range numbers are clamped rather than refused,
    because a caller asking for 99999 wants "as many as you have".
    """
    from ..services import icm_router as rsvc

    return {'ok': True, 'decisions': rsvc.recent_decisions(max(1, min(limit, 500)))}


# ── restructure mode ──────────────────────────────────────────────────────────
# Audit a folder that already exists and propose an ICM migration. The canon's
# step 4 is "Propose before moving... This is a human gate in a method built on
# human gates -- honor it", so scanning and planning are pure reads and applying
# is a separate call that refuses without explicit approval.


def _audit_root(path: str) -> Path:
    """Resolve a caller-supplied audit root, or refuse.

    Confined to the data dir: this walks a tree and reads file contents back to
    the caller, so an unconstrained path here is an arbitrary filesystem read.
    """
    from ..services import icm_restructure as rsvc

    target = safe_path(str(path or '.'), base=rsvc.ROOT, must_exist=True)
    if target is None or not target.is_dir():
        raise HTTPException(
            status_code=400,
            detail=f'Path {path!r} is not a readable directory inside the data dir.',
        )
    return target


@router.get('/restructure/inventory')
def restructure_inventory(path: str = '.') -> dict[str, Any]:
    """Classify every file in a tree. Reads only; changes nothing."""
    from ..services import icm_restructure as rsvc

    root = _audit_root(path)
    inv = rsvc.inventory(root)
    items = [rsvc.classify(f) for f in inv['files']]
    return {
        'ok': True,
        'root': str(root),
        'file_count': inv['file_count'],
        'truncated': inv['truncated'],
        'items': items,
    }


@router.get('/restructure/system-map')
def restructure_system_map(path: str = '.', limit: int = 40) -> dict[str, Any]:
    """Index cards for a tree a later agent must edit."""
    from ..services import icm_restructure as rsvc

    return {'ok': True, **rsvc.system_map(_audit_root(path), max(1, min(limit, 200)))}


@router.get('/restructure/plans')
def restructure_plans(limit: int = 50) -> dict[str, Any]:
    from ..services import icm_restructure as rsvc

    return {'ok': True, 'plans': rsvc.list_plans(max(1, min(limit, 200)))}


@router.get('/restructure/plans/{plan_id}')
def restructure_plan(plan_id: str) -> dict[str, Any]:
    from ..services import icm_restructure as rsvc

    p = rsvc.load_plan(plan_id)
    if p is None:
        raise HTTPException(status_code=404, detail=f'Plan {plan_id!r} not found')
    return {'ok': True, 'plan': p}


@router.post('/restructure/plan')
async def restructure_create_plan(req: Request) -> dict[str, Any]:
    """Produce a migration map awaiting approval. Does not move anything."""
    from ..services import icm_restructure as rsvc

    body, err = await json_body_or_error(req)
    if err:
        return err
    root = _audit_root(as_text(body.get('path')) or '.')
    return {'ok': True, 'plan': rsvc.plan(root, as_text(body.get('label')))}


@router.post('/restructure/apply')
async def restructure_apply(req: Request) -> dict[str, Any]:
    """Execute a proposed migration. Refuses unless `approved` is exactly true.

    Copies into `<root>/_icm-restructured/` rather than moving: the classifier
    is a heuristic, and a heuristic should not be handed the power to rearrange
    somebody's repo irreversibly. Nothing is ever deleted.
    """
    from ..services import icm_restructure as rsvc

    body, err = await json_body_or_error(req)
    if err:
        return err
    plan_id = as_text(body.get('plan_id'))
    if not plan_id:
        raise HTTPException(status_code=422, detail='Send plan_id.')
    # Only a real boolean true approves. A truthy string like "no" must not.
    approved = body.get('approved') is True
    return rsvc.apply_plan(plan_id, approved=approved)


# ── dialogue → workspace ──────────────────────────────────────────────────────
# Build mode step 1: surface the structure already present in how someone
# describes their work, rather than making them learn the methodology first.


@router.post('/describe')
async def describe_work(req: Request) -> dict[str, Any]:
    """Analyse a description of work. Proposes a structure; creates nothing.

    Read-only by design: the canon's posture is propose-then-confirm, and the
    user has to be able to see and correct the proposed stages before any
    folder exists.
    """
    from ..services import icm_dialogue as dsvc

    body, err = await json_body_or_error(req)
    if err:
        return err
    text = as_text(body.get('text'))
    if not text.strip():
        raise HTTPException(status_code=422, detail='Send text describing your work.')
    analysis = dsvc.analyse(text)
    analysis['suggested_routes'] = dsvc.routes_block(text).strip()
    return analysis


@router.post('/describe/create')
async def create_from_description(req: Request) -> dict[str, Any]:
    """Scaffold the workspace a description implies, after confirmation.

    Honours the over-structuring guardrail: if the analysis says this does not
    warrant a workspace, that refusal is returned unless the caller explicitly
    overrides it. "A workspace for a thing done twice is scaffolding, not
    architecture" is advice worth actually enforcing, but it is the user's
    call in the end -- so the override exists and is explicit.
    """
    from ..services import icm as isvc
    from ..services import icm_dialogue as dsvc

    body, err = await json_body_or_error(req)
    if err:
        return err

    text = as_text(body.get('text'))
    if not text.strip():
        raise HTTPException(status_code=422, detail='Send text describing your work.')

    analysis = dsvc.analyse(text)
    if not analysis['recommend_workspace'] and body.get('force') is not True:
        return {'ok': False, 'error': analysis['advice'] or 'not enough structure to build',
                'analysis': analysis}

    # Stages may be edited by the user before confirming; trust the edited list
    # when one is supplied, since the whole point is that they correct it.
    stages = [as_text(s) for s in (body.get('stages') or []) if as_text(s).strip()]
    if not stages:
        stages = [s['name'] for s in analysis['stages']]
    if not stages:
        raise HTTPException(status_code=422, detail='No stages could be determined.')

    name = as_text(body.get('name')) or 'workspace'
    ws_id = isvc._slug(name, 'workspace')
    ws = isvc.workspace_dir(ws_id)
    if ws is None:
        raise HTTPException(status_code=400, detail=f'Invalid workspace name {name!r}')
    if ws.exists():
        raise HTTPException(status_code=409, detail=f'Workspace {ws_id!r} already exists')

    # Build in the DETECTED form, not always a pipeline. The extractor can tell
    # a record library from a production line; scaffolding stages for a form
    # that has no stages would hand back the wrong shape under the right name.
    # The user may override the detected form -- it is a proposal, not a ruling.
    from ..services import icm_forms as fsvc

    form = as_text(body.get('form')) or analysis['form']['form']
    if form not in fsvc.BUILDERS:
        raise HTTPException(status_code=422, detail=f'Unknown form {form!r}')
    meta = fsvc.scaffold_form(ws, form, name, analysis['form']['why'], stages)

    # Declare routes immediately. A workspace nothing routes to can only be
    # reached by name, which is the wrong-folder problem the router exists to
    # solve -- creating one without routes reintroduces it at birth.
    routes = dsvc.routes_block(text)
    if routes:
        ctx = ws / 'CONTEXT.md'
        ctx.write_text(ctx.read_text(encoding='utf-8') + routes, encoding='utf-8')

    return {'ok': True, 'workspace': meta, 'analysis': analysis,
            'validation': isvc.validate(ws)}


@router.get('/forms')
def list_forms() -> dict[str, Any]:
    """The six forms and the repeating unit each one is for.

    Served from FORM_META so the UI and the builders cannot drift apart.
    """
    from ..services import icm_forms as fsvc

    return {
        'ok': True,
        'forms': [{'id': f, **fsvc.FORM_META[f]} for f in fsvc.ALL_FORMS],
    }


@router.post('/workspaces/{workspace_id}/file-map')
def rebuild_file_map(workspace_id: str) -> dict[str, Any]:
    """Regenerate FILE-MAP.md from the tree. Never hand-edited."""
    from ..services import icm_forms as fsvc

    ws = _require_ws(workspace_id)
    body = fsvc.generate_file_map(ws)
    return {'ok': True, 'lines': body.count('\n')}


# ── template library: method and instance live apart ──────────────────────────
# "The blank, reusable template of a structure is a different artifact from any
# filled-in deployment of it." Extraction keeps L0-L3 and drops L4, which is the
# factory/product split the rest of this runtime already enforces.


@router.get('/templates')
def list_workspace_templates() -> dict[str, Any]:
    """Every template, including the seeded starter set."""
    from ..services import icm_templates as tsvc

    return {'ok': True, 'templates': tsvc.list_templates()}


@router.get('/templates/{template_id}')
def get_workspace_template(template_id: str) -> dict[str, Any]:
    from ..services import icm_templates as tsvc

    tpl = tsvc.get_template(template_id)
    if tpl is None:
        raise HTTPException(status_code=404, detail=f'Template {template_id!r} not found')
    return {'ok': True, 'template': tpl}


@router.post('/templates/extract')
async def extract_workspace_template(req: Request) -> dict[str, Any]:
    """Extract the method from a working workspace. Never modifies the source."""
    from ..services import icm_templates as tsvc

    body, err = await json_body_or_error(req)
    if err:
        return err
    ws_id = as_text(body.get('workspace_id'))
    if not ws_id:
        raise HTTPException(status_code=422, detail='Send workspace_id.')
    ws = _require_ws(ws_id)
    tid = as_text(body.get('template_id')) or tsvc._slug(ws_id)
    return tsvc.extract(
        ws, tid,
        name=as_text(body.get('name')),
        description=as_text(body.get('description')),
        overwrite=body.get('overwrite') is True,
    )


@router.post('/templates/{template_id}/instantiate')
async def instantiate_workspace_template(template_id: str, req: Request) -> dict[str, Any]:
    """Create a workspace by copying a template. Refuses to overwrite."""
    from ..services import icm_templates as tsvc

    body, err = await json_body_or_error(req)
    if err:
        return err
    ws_id = as_text(body.get('workspace_id'))
    if not ws_id:
        raise HTTPException(status_code=422, detail='Send workspace_id.')
    return tsvc.instantiate(template_id, ws_id, name=as_text(body.get('name')))


@router.delete('/templates/{template_id}')
def delete_workspace_template(template_id: str) -> dict[str, Any]:
    from ..services import icm_templates as tsvc

    return tsvc.delete_template(template_id)


@router.get('/templates/{template_id}/export')
def export_workspace_template(template_id: str) -> dict[str, Any]:
    """Serialise a template to one JSON file so it can be shared."""
    from ..services import icm_templates as tsvc

    payload = tsvc.export_template(template_id)
    if payload is None:
        raise HTTPException(status_code=404, detail=f'Template {template_id!r} not found')
    return {'ok': True, **payload}


@router.post('/templates/import')
async def import_workspace_template(req: Request) -> dict[str, Any]:
    """Load an exported template. Every path is contained before it is written."""
    from ..services import icm_templates as tsvc

    body, err = await json_body_or_error(req)
    if err:
        return err
    return tsvc.import_template(
        body,
        template_id=as_text(body.get('template_id')),
        overwrite=body.get('overwrite') is True,
    )


@router.get('/walk-test')
def walk_test_audit() -> dict[str, Any]:
    """Walk-test every workspace: what is broken, and how to fix each one."""
    from ..services import icm_gate

    return {'ok': True, **icm_gate.audit_all()}


@router.get('/workspaces/{workspace_id}/walk-test')
def walk_test_one(workspace_id: str) -> dict[str, Any]:
    """The gate verdict for one workspace, with a repair for every failure."""
    from ..services import icm_gate

    _require_ws(workspace_id)
    return {'ok': True, **icm_gate.gate_workspace_id(workspace_id, action='inspect')}
