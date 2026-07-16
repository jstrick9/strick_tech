"""
Agentic OS — Plugin SDK Router
Let users publish, validate, install, and manage their own plugin packs.
Plugin pack format: JSON manifest + optional JS/Python code.
"""

from __future__ import annotations

import contextlib

import io
import json
import logging
import time
import uuid
import zipfile
from pathlib import Path

from fastapi import APIRouter, File, Request, UploadFile
from fastapi.responses import JSONResponse

router = APIRouter(prefix='/api/pluginsdk', tags=['pluginsdk'])
log = logging.getLogger('agentic.pluginsdk')

ROOT = Path(__file__).resolve().parents[2]
SDK_DIR = ROOT / 'workspaces' / 'plugin_sdk'
PACKS_DIR = SDK_DIR / 'packs'
PUBLISHED = SDK_DIR / 'published'

try:
    SDK_DIR.mkdir(parents=True, exist_ok=True)
    PACKS_DIR.mkdir(parents=True, exist_ok=True)
    PUBLISHED.mkdir(parents=True, exist_ok=True)
except Exception as _e:
    log.error('Plugin SDK: failed to create directories: %s', _e)

PACK_TEMPLATE = {
    'id': 'my-plugin-pack',
    'name': 'My Plugin Pack',
    'version': '1.0.0',
    'description': 'What your plugin does',
    'author': 'Your Name',
    'license': 'MIT',
    'tags': ['utility', 'ai'],
    'icon': '🔧',
    'homepage': '',
    'skills': [
        {
            'id': 'my_skill',
            'name': 'My Skill',
            'description': 'What this skill does',
            'prompt': 'You are a helpful assistant. {{input}}',
            'model': 'auto',
            'tags': ['utility'],
            'icon': '⚡',
            'inputs': [{'name': 'input', 'label': 'Input', 'type': 'text', 'required': True}],
            'outputs': [{'name': 'result', 'label': 'Result', 'type': 'text'}],
        }
    ],
    'hooks': {
        'on_chat_send': None,
        'on_file_save': None,
        'on_pane_open': None,
        'on_agent_run': None,
        'on_deploy': None,
    },
    'ui': {
        'sidebar_item': None,
        'settings_tab': None,
        'pane': None,
    },
    'permissions': ['chat', 'memory', 'files'],
    'min_version': '6.0.0',
}


# ── SDK REST endpoints ─────────────────────────────────────────────────────────
@router.get('/template')
def get_template():
    """Return the plugin pack template / starter."""
    return PACK_TEMPLATE


@router.get('/template/json')
def get_template_json():
    """Retrieve and return get template json."""
    return JSONResponse(content=PACK_TEMPLATE)


@router.get('/packs')
def list_user_packs():
    """List all user-created plugin packs."""
    packs = []
    for f in sorted(PACKS_DIR.iterdir()):
        if f.suffix == '.json':
            try:
                packs.append(json.loads(f.read_text()))
            except (KeyError, TypeError, ValueError, json.JSONDecodeError, OSError, AttributeError, RuntimeError):
                pass
    return {'packs': packs, 'count': len(packs)}


@router.post('/packs')
async def create_pack(req: Request):
    """Create a new plugin pack."""
    try:
        body = await req.json()
    except (json.JSONDecodeError, TypeError, ValueError):
        body = {}
    name = (body.get('name') or '').strip()
    if not name:
        return {'ok': False, 'error': 'name is required'}
    pack_id = (body.get('id') or f'pack_{uuid.uuid4().hex[:6]}').lower().replace(' ', '-')
    # Sanitize pack_id — only alphanumeric + hyphens + underscores
    import re as _re

    pack_id = _re.sub(r'[^a-z0-9_-]', '-', pack_id).strip('-') or f'pack_{uuid.uuid4().hex[:6]}'
    pack = {
        **PACK_TEMPLATE,
        **body,
        'id': pack_id,
        'created_at': time.strftime('%Y-%m-%dT%H:%M:%SZ', time.gmtime()),
        'updated_at': time.strftime('%Y-%m-%dT%H:%M:%SZ', time.gmtime()),
    }
    (PACKS_DIR / f'{pack_id}.json').write_text(json.dumps(pack, indent=2))
    return {'ok': True, 'pack': pack}


@router.get('/packs/{pack_id}')
def get_pack(pack_id: str):
    """Retrieve and return get pack."""
    p = PACKS_DIR / f'{pack_id}.json'
    if not p.exists():
        return {'ok': False, 'error': 'Pack not found'}
    return json.loads(p.read_text())


@router.put('/packs/{pack_id}')
async def update_pack(pack_id: str, req: Request):
    """Update existing pack record or state."""
    try:
        body = await req.json()
    except (json.JSONDecodeError, TypeError, ValueError):
        body = {}
    p = PACKS_DIR / f'{pack_id}.json'
    existing = json.loads(p.read_text()) if p.exists() else {}
    existing.update({**body, 'id': pack_id, 'updated_at': time.strftime('%Y-%m-%dT%H:%M:%SZ', time.gmtime())})
    p.write_text(json.dumps(existing, indent=2))
    return {'ok': True, 'pack': existing}


@router.delete('/packs/{pack_id}')
def delete_pack(pack_id: str):
    """Delete or remove specified pack."""
    p = PACKS_DIR / f'{pack_id}.json'
    if p.exists():
        p.unlink()
    return {'ok': True}


# ── Validation ────────────────────────────────────────────────────────────────
@router.post('/validate')
async def validate_pack(req: Request):
    """Validate a plugin pack manifest."""
    try:
        body = await req.json()
    except (json.JSONDecodeError, TypeError, ValueError):
        body = {}
    errors: list[str] = []
    warns: list[str] = []

    # Required fields
    for field in ['id', 'name', 'version', 'description', 'skills']:
        if not body.get(field):
            errors.append(f'Missing required field: {field}')

    # ID format
    if body.get('id'):
        if not body['id'].replace('-', '').replace('_', '').isalnum():
            errors.append('id must be alphanumeric with hyphens/underscores only')

    # Version format
    if body.get('version'):
        parts = str(body['version']).split('.')
        if len(parts) != 3 or not all(p.isdigit() for p in parts):
            errors.append('version must be semantic (e.g. 1.0.0)')

    # Skills validation
    skills = body.get('skills', [])
    if not isinstance(skills, list):
        errors.append('skills must be a list')
    else:
        for i, skill in enumerate(skills):
            if not skill.get('id'):
                errors.append(f'skills[{i}]: missing id')
            if not skill.get('name'):
                errors.append(f'skills[{i}]: missing name')
            if not skill.get('prompt'):
                warns.append(f'skills[{i}]: no prompt defined')

    # Permissions
    allowed_perms = {'chat', 'memory', 'files', 'terminal', 'deploy', 'github', 'webhooks', 'secrets'}
    for perm in body.get('permissions', []):
        if perm not in allowed_perms:
            warns.append(f'Unknown permission: {perm}')

    return {
        'ok': len(errors) == 0,
        'errors': errors,
        'warns': warns,
        'score': max(0, 100 - len(errors) * 20 - len(warns) * 5),
    }


# ── Publish ────────────────────────────────────────────────────────────────────
@router.post('/publish/{pack_id}')
def publish_pack(pack_id: str):
    """Publish a pack to the local registry (makes it available in Plugin Marketplace)."""
    src = PACKS_DIR / f'{pack_id}.json'
    if not src.exists():
        return {'ok': False, 'error': 'Pack not found'}

    pack = json.loads(src.read_text())
    pack['published'] = True
    pack['published_at'] = time.strftime('%Y-%m-%dT%H:%M:%SZ', time.gmtime())
    pack['downloads'] = pack.get('downloads', 0)

    # Write to published registry
    (PUBLISHED / f'{pack_id}.json').write_text(json.dumps(pack, indent=2))

    # Update source
    src.write_text(json.dumps(pack, indent=2))

    # Also add to plugins system
    # Also register in the plugins installed.json for cross-system availability
    try:
        plugins_installed_file = ROOT / 'plugins' / 'installed.json'
        installed_data = {}
        if plugins_installed_file.exists():
            try:
                installed_data = json.loads(plugins_installed_file.read_text())
            except (KeyError, TypeError, ValueError, json.JSONDecodeError, OSError, AttributeError, RuntimeError):
                pass
        installed_data[pack_id] = {
            'id': pack_id,
            'name': pack['name'],
            'version': pack['version'],
            'author': pack.get('author', 'Community'),
            'category': pack.get('category', 'custom'),
            'emoji': pack.get('icon', '🔧'),
            'skill_count': len(pack.get('skills', [])),
            'installed_at': time.strftime('%Y-%m-%d'),
            'source': 'user_sdk',
        }
        plugins_installed_file.parent.mkdir(parents=True, exist_ok=True)
        plugins_installed_file.write_text(json.dumps(installed_data, indent=2))
        # Also install the skills into the skills system
        from .skills import load_skills, save_skills

        existing_skill_ids = {s['id'] for s in load_skills()}
        all_skills = load_skills()
        for skill in pack.get('skills', []):
            if skill.get('id') and skill['id'] not in existing_skill_ids:
                # Convert SDK skill format to skills.py format
                all_skills.append(
                    {
                        'id': skill['id'],
                        'name': skill.get('name', skill['id']),
                        'emoji': skill.get('icon', '⚡'),
                        'category': 'custom',
                        'description': skill.get('description', ''),
                        'agent': 'brain',
                        'inputs': [{'id': 'input', 'label': 'Input', 'type': 'text', 'required': True}],
                        'prompt_template': skill.get('prompt', '{{input}}').replace('{{input}}', '{input}'),
                    }
                )
        save_skills(all_skills)
    except Exception as ex:
        log.warning('Could not register published pack in plugin store: %s', ex)

    return {'ok': True, 'pack': pack, 'registry_url': f'/api/pluginsdk/registry/{pack_id}'}


@router.get('/registry')
def registry():
    """Browse published plugin packs."""
    packs = []
    for f in sorted(PUBLISHED.iterdir()):
        if f.suffix == '.json':
            try:
                packs.append(json.loads(f.read_text()))
            except (KeyError, TypeError, ValueError, json.JSONDecodeError, OSError, AttributeError, RuntimeError):
                pass
    return {'packs': packs, 'count': len(packs)}


@router.get('/registry/{pack_id}')
def registry_pack(pack_id: str):
    """Execute or process registry pack operation."""
    p = PUBLISHED / f'{pack_id}.json'
    if not p.exists():
        return {'ok': False, 'error': 'Not in registry'}
    return json.loads(p.read_text())


# ── Export as ZIP ──────────────────────────────────────────────────────────────
@router.get('/export/{pack_id}')
def export_pack(pack_id: str):
    """Export a plugin pack as a downloadable ZIP."""
    from fastapi.responses import StreamingResponse

    p = PACKS_DIR / f'{pack_id}.json'
    if not p.exists():
        return {'ok': False, 'error': 'Pack not found'}

    pack = json.loads(p.read_text())
    buf = io.BytesIO()

    with zipfile.ZipFile(buf, 'w', zipfile.ZIP_DEFLATED) as zf:
        zf.writestr('manifest.json', json.dumps(pack, indent=2))
        zf.writestr(
            'README.md',
            f'# {pack["name"]}\n\n{pack.get("description", "")}\n\nVersion: {pack.get("version", "1.0.0")}\nAuthor: {pack.get("author", "")}\nLicense: {pack.get("license", "MIT")}\n',
        )
        zf.writestr(
            'skills/README.md',
            f'# Skills in {pack["name"]}\n\n'
            + '\n'.join(f'## {s.get("name", "")}\n{s.get("description", "")}\n' for s in pack.get('skills', [])),
        )

    buf.seek(0)
    return StreamingResponse(
        buf,
        media_type='application/zip',
        headers={'Content-Disposition': f'attachment; filename="{pack_id.replace(chr(34), "")}.zip"'},
    )


# ── Upload ZIP ────────────────────────────────────────────────────────────────
@router.post('/import')
async def import_pack(file: UploadFile = File(...)):
    """Import a plugin pack from a ZIP file."""
    data = await file.read()
    buf = io.BytesIO(data)

    try:
        with zipfile.ZipFile(buf) as zf:
            names = zf.namelist()
            if 'manifest.json' not in names:
                return {'ok': False, 'error': 'ZIP must contain manifest.json'}
            manifest = json.loads(zf.read('manifest.json'))
    except Exception as ex:
        return {'ok': False, 'error': f'Invalid ZIP: {ex}'}

    # Validate manifest has minimum required fields
    if not manifest.get('name'):
        return {'ok': False, 'error': "manifest.json must have a 'name' field"}
    pack_id = manifest.get('id') or f'imported_{uuid.uuid4().hex[:6]}'
    # Sanitize pack_id
    import re as _re

    pack_id = _re.sub(r'[^a-z0-9_-]', '-', pack_id.lower()).strip('-') or f'imported_{uuid.uuid4().hex[:6]}'
    manifest['id'] = pack_id
    if not manifest.get('version'):
        manifest['version'] = '1.0.0'
    if not isinstance(manifest.get('skills'), list):
        manifest['skills'] = []
    (PACKS_DIR / f'{pack_id}.json').write_text(json.dumps(manifest, indent=2))
    return {'ok': True, 'pack': manifest}


# ── Skill runner (test a skill in isolation) ──────────────────────────────────
@router.post('/packs/{pack_id}/skills/{skill_id}/run')
async def run_skill(pack_id: str, skill_id: str, req: Request):
    """Test-run a single skill from a pack."""
    try:
        body = await req.json()
    except (json.JSONDecodeError, TypeError, ValueError):
        body = {}
    p = PACKS_DIR / f'{pack_id}.json'
    if not p.exists():
        return {'ok': False, 'error': 'Pack not found'}

    pack = json.loads(p.read_text())
    skills = {s['id']: s for s in pack.get('skills', [])}
    skill = skills.get(skill_id)
    if not skill:
        return {'ok': False, 'error': 'Skill not found'}

    user_input = body.get('input', '')
    prompt = skill.get('prompt', '{{input}}').replace('{{input}}', user_input)

    from ..services import llm as llm_svc

    msgs = [{'role': 'user', 'content': prompt}]
    result = await llm_svc.complete(msgs, agent_id=skill_id, max_tokens=1024, inject_steering=False)

    return {
        'ok': True,
        'skill': skill_id,
        'input': user_input,
        'output': result.get('text', ''),
        'tokens': result.get('tokens', 0),
    }
