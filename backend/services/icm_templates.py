"""Workspace template library — method and instance live apart.

Closes G12. Two canon rules drive every decision here:

    "Method and instance live apart. The blank, reusable template of a
     structure is a different artifact from any filled-in deployment of it.
     When a structure proves out, extract the template before it tangles with
     the data."

    "Instantiate by copying. New unit of work = copy a template folder, not a
     blank page."

WHAT SEPARATES METHOD FROM INSTANCE

Not a judgement call — the ICM layer model already answers it:

    L0 IDENTITY.md    method   (how to work here)
    L1 CONTEXT.md     method   (routing, the shape)
    L2 stage CONTEXT  method   (the contract: inputs, process, outputs)
    L3 references/    method   (the factory: voice, conventions, schema)
    ---------------------------------------------------------------
    L4 output/        INSTANCE (what this particular run produced)

So extraction is exactly "keep L0-L3, drop L4", which is the factory/product
split this codebase already implements and tests. A template is a workspace
with its products removed.

NOT A SEPARATE FORMAT

A template IS a workspace folder. It is stored under a different root and
carries a `.icm-template.json`, but the bytes are the same shape, so a template
can be opened, read, edited and diffed with the same tools — and instantiating
one is a directory copy, not a code path that renders a schema. A template
format that drifts from the thing it produces is a template format that
produces broken workspaces.

WHAT IS DELIBERATELY REFUSED

Extraction never mutates the source workspace. Instantiation refuses to
overwrite an existing workspace. Neither ever deletes. The reason is the same
one as everywhere else in this system: these operate on folders somebody is
actively working in.
"""

from __future__ import annotations

import json
import re
import shutil
import time
from pathlib import Path
from typing import Any

from backend.config import get_data_dir

from .safe_paths import safe_path

ROOT = get_data_dir()
TEMPLATES_DIR = ROOT / 'memory' / 'icm-templates'

TEMPLATE_ID_RE = re.compile(r'^[a-z0-9][a-z0-9_-]{0,63}$')
META_NAME = '.icm-template.json'

# L4 lives in these. Everything under them is instance data and is dropped when
# a template is extracted. `output` is the canonical ICM handoff folder; the
# others are the per-run shelves the six forms create.
PRODUCT_DIRS = frozenset({'output', 'outputs', '_inbox', 'records', 'corpus', 'drafts'})

# Never carried into a template: environment, VCS state, caches, and anything
# that would make a "blank" template leak the machine it was extracted from.
SKIP_NAMES = frozenset({
    '.git', '.env', '.DS_Store', '__pycache__', 'node_modules', '.venv',
    '.icm-template.json',
    # A workspace's own marker. Carrying it would leave every template holding
    # the id, name and creation time of the instance it was extracted from --
    # a template that identifies itself as a workspace, which is exactly the
    # method/instance tangle this module exists to prevent. Instantiation
    # writes a fresh one.
    '.icm.json',
})

MAX_TEMPLATE_FILES = 2000


def template_dir(template_id: str) -> Path | None:
    if not template_id or not TEMPLATE_ID_RE.match(str(template_id)):
        return None
    return safe_path(str(template_id), base=TEMPLATES_DIR)


def _slug(text: str, fallback: str = 'template') -> str:
    s = re.sub(r'[^a-z0-9]+', '-', str(text or '').lower()).strip('-')
    return s[:48] or fallback


def _is_product_path(rel: Path) -> bool:
    """True when this path lives inside an L4 product folder."""
    return any(part in PRODUCT_DIRS for part in rel.parts)


# ── extraction: workspace -> template ─────────────────────────────────────────
def extract(ws: Path, template_id: str, name: str = '',
            description: str = '', overwrite: bool = False) -> dict[str, Any]:
    """Extract the METHOD from a working workspace, leaving the instance behind.

    Copies L0-L3 and drops L4. The source workspace is never modified — this is
    "extract the template before it tangles with the data", not "convert my
    working folder into a template and hope".
    """
    dest = template_dir(template_id)
    if dest is None:
        return {'ok': False, 'error': f'invalid template id {template_id!r}'}
    if not ws.is_dir():
        return {'ok': False, 'error': 'source workspace does not exist'}
    if dest.exists() and not overwrite:
        return {'ok': False, 'error': f'template {template_id!r} already exists'}

    from . import icm

    meta_src = icm.read_meta(ws)
    copied: list[str] = []
    dropped: list[str] = []

    if dest.exists():
        shutil.rmtree(dest)
    dest.mkdir(parents=True, exist_ok=True)

    for src_file in sorted(ws.rglob('*')):
        if len(copied) >= MAX_TEMPLATE_FILES:
            break
        rel = src_file.relative_to(ws)
        if any(part in SKIP_NAMES for part in rel.parts):
            continue
        if src_file.is_dir():
            # Keep the SHAPE of a product folder (so the instantiated workspace
            # has somewhere to write) but never its contents. A template that
            # omits output/ produces a workspace whose first stage has nowhere
            # to put anything.
            (dest / rel).mkdir(parents=True, exist_ok=True)
            continue
        if not src_file.is_file() or src_file.is_symlink():
            continue
        if _is_product_path(rel) and src_file.name != '.gitkeep':
            dropped.append(rel.as_posix())
            continue
        target = dest / rel
        target.parent.mkdir(parents=True, exist_ok=True)
        try:
            shutil.copy2(src_file, target)
            copied.append(rel.as_posix())
        except OSError as exc:
            return {'ok': False, 'error': f'{rel}: {exc}'}

    # Every product folder that survived must be empty and must stay traversable.
    for d in dest.rglob('*'):
        if d.is_dir() and d.name in PRODUCT_DIRS and not any(d.iterdir()):
            (d / '.gitkeep').write_text('', encoding='utf-8')

    meta = {
        'template_id': template_id,
        'name': name or meta_src.get('name') or template_id,
        'description': description or meta_src.get('description') or '',
        'form': meta_src.get('form') or 'pipeline',
        'extracted_from': ws.name,
        'created_at': time.time(),
        'file_count': len(copied),
        'builtin': False,
    }
    (dest / META_NAME).write_text(json.dumps(meta, indent=2), encoding='utf-8')

    return {'ok': True, 'template': meta, 'copied': len(copied),
            'dropped_instance_files': dropped}


# ── instantiation: template -> workspace ──────────────────────────────────────
def instantiate(template_id: str, workspace_id: str, name: str = '') -> dict[str, Any]:
    """Create a workspace by COPYING a template. Never renders from a schema.

    "New unit of work = copy a template folder, not a blank page."
    """
    src = template_dir(template_id)
    if src is None or not src.is_dir():
        return {'ok': False, 'error': f'template {template_id!r} not found'}

    from . import icm

    ws_id = _slug(workspace_id, 'workspace')
    if not icm.WORKSPACE_ID_RE.match(ws_id):
        return {'ok': False, 'error': f'invalid workspace id {workspace_id!r}'}
    dest = icm.workspace_dir(ws_id)
    if dest is None:
        return {'ok': False, 'error': 'could not resolve a safe workspace path'}
    if dest.exists():
        # Refusing beats merging. A half-overwritten workspace is worse than
        # either outcome, and the caller can pick another name in a second.
        return {'ok': False, 'error': f'workspace {ws_id!r} already exists'}

    try:
        meta_t = json.loads((src / META_NAME).read_text(encoding='utf-8'))
    except (OSError, ValueError):
        meta_t = {'name': template_id, 'form': 'pipeline'}

    try:
        shutil.copytree(src, dest, ignore=shutil.ignore_patterns(META_NAME))
    except OSError as exc:
        return {'ok': False, 'error': str(exc)}

    # The instance gets its own identity. Carrying the template's name would
    # leave three workspaces all called "Client Reports Template".
    display = name or ws_id.replace('-', ' ')
    meta = {
        'workspace_id': ws_id,
        'name': display,
        'description': meta_t.get('description', ''),
        'form': meta_t.get('form', 'pipeline'),
        'created_at': time.time(),
        'from_template': template_id,
        'stages': [s['dir'] for s in icm.list_stages(dest)],
    }
    (dest / '.icm.json').write_text(json.dumps(meta, indent=2), encoding='utf-8')

    # L0 names the workspace, so a fresh instance should say its own name.
    ident = dest / 'IDENTITY.md'
    if ident.is_file():
        try:
            text = ident.read_text(encoding='utf-8')
            lines = text.split('\n')
            if lines and lines[0].startswith('# '):
                lines[0] = f'# {display}'
                ident.write_text('\n'.join(lines), encoding='utf-8')
        except OSError:
            pass

    return {'ok': True, 'workspace': meta, 'validation': icm.validate(dest)}


# ── listing ───────────────────────────────────────────────────────────────────
def list_templates() -> list[dict[str, Any]]:
    ensure_builtins()
    if not TEMPLATES_DIR.is_dir():
        return []
    out: list[dict[str, Any]] = []
    for d in sorted(TEMPLATES_DIR.iterdir()):
        if not d.is_dir() or d.name.startswith('.'):
            continue
        path = d / META_NAME
        if not path.is_file():
            continue
        try:
            meta = json.loads(path.read_text(encoding='utf-8'))
        except (OSError, ValueError):
            continue
        meta['stages'] = sorted(
            p.name for p in (d / 'stages').iterdir()
            if p.is_dir() and not p.name.startswith('.')
        ) if (d / 'stages').is_dir() else []
        out.append(meta)
    return out


def get_template(template_id: str) -> dict[str, Any] | None:
    d = template_dir(template_id)
    if d is None or not (d / META_NAME).is_file():
        return None
    try:
        meta = json.loads((d / META_NAME).read_text(encoding='utf-8'))
    except (OSError, ValueError):
        return None
    files = []
    for f in sorted(d.rglob('*')):
        if f.is_file() and f.name != META_NAME:
            files.append(f.relative_to(d).as_posix())
    meta['files'] = files[:400]
    return meta


def delete_template(template_id: str) -> dict[str, Any]:
    d = template_dir(template_id)
    if d is None or not d.is_dir():
        return {'ok': False, 'error': 'not found'}
    meta = get_template(template_id) or {}
    if meta.get('builtin'):
        # Built-ins are re-created on the next list() anyway, so deleting one
        # is a no-op that looks like it worked. Say so instead.
        return {'ok': False, 'error': 'built-in templates cannot be deleted'}
    shutil.rmtree(d)
    return {'ok': True, 'deleted': template_id}


# ── the starter set ───────────────────────────────────────────────────────────
# Blank, reusable methods for the cases the research named: software work,
# content production, client records, a personal second brain, and life/home
# ops. Each is the SMALLEST structure that carries its job -- "three real
# stages beat seven imagined ones".
BUILTINS: dict[str, dict[str, Any]] = {
    'software-feature': {
        'name': 'Software feature',
        'description': 'Spec, build, review, ship — one feature per run.',
        'form': 'pipeline',
        'stages': ['spec', 'build', 'review', 'ship'],
        'routes': ['feature', 'build', 'implement'],
        'shared': {
            'conventions.md': ('# Conventions\n\nHow code is written here. '
                               'One home per fact; the code wins over the comment.\n'),
        },
    },
    'content-pipeline': {
        'name': 'Content pipeline',
        'description': 'Research, draft, edit, publish — one piece per run.',
        'form': 'pipeline',
        'stages': ['research', 'draft', 'edit', 'publish'],
        'routes': ['post', 'article', 'newsletter', 'content'],
        'shared': {
            'voice.md': ('# Voice\n\nThe tone every piece is written in. '
                         'Concrete examples beat adjectives.\n'),
        },
    },
    'client-records': {
        'name': 'Client records',
        'description': 'One folder per client, all the same shape.',
        'form': 'record_library',
        'stages': [],
        'routes': ['client', 'account'],
        'shared': {},
    },
    'second-brain': {
        'name': 'Second brain',
        'description': 'Sources in, a navigable body of knowledge out.',
        'form': 'knowledge_bundle',
        'stages': [],
        'routes': ['note', 'research', 'remember'],
        'shared': {},
    },
    'home-ops': {
        'name': 'Home & life ops',
        'description': 'Capture, decide, do — the recurring admin of a life.',
        'form': 'pipeline',
        'stages': ['capture', 'decide', 'do'],
        'routes': ['home', 'errand', 'admin', 'bill'],
        'shared': {
            'rules.md': ('# Rules\n\nStanding decisions, so they are made once. '
                         'Anything under ten minutes gets done, not filed.\n'),
        },
    },
}


def ensure_builtins() -> int:
    """Create any missing starter template. Never overwrites a user's edits.

    Built-ins are seeded rather than shipped as read-only, because a template
    the user cannot adjust is a template they will abandon. If they have edited
    one, that edit survives.
    """
    from . import icm, icm_forms

    TEMPLATES_DIR.mkdir(parents=True, exist_ok=True)
    made = 0
    for tid, spec in BUILTINS.items():
        d = template_dir(tid)
        if d is None or (d / META_NAME).is_file():
            continue
        d.mkdir(parents=True, exist_ok=True)
        form = spec['form']
        if form == 'pipeline':
            icm.scaffold(d, spec['name'], spec['description'], spec['stages'])
        else:
            icm_forms.scaffold_form(d, form, spec['name'], spec['description'], [])
        # The scaffolders write .icm.json; a template is identified by its own
        # metadata file, and leaving a workspace marker behind would make the
        # template look like an instance.
        (d / '.icm.json').unlink(missing_ok=True)

        for fname, body in (spec.get('shared') or {}).items():
            shared = d / '_shared'
            shared.mkdir(parents=True, exist_ok=True)
            (shared / fname).write_text(body, encoding='utf-8')

        if spec.get('routes'):
            ctx = d / 'CONTEXT.md'
            if ctx.is_file():
                ctx.write_text(
                    ctx.read_text(encoding='utf-8')
                    + '\n## Routes\n'
                    + '\n'.join(f'- {r}' for r in spec['routes']) + '\n',
                    encoding='utf-8')

        (d / META_NAME).write_text(json.dumps({
            'template_id': tid,
            'name': spec['name'],
            'description': spec['description'],
            'form': form,
            'extracted_from': '',
            'created_at': time.time(),
            'file_count': sum(1 for f in d.rglob('*') if f.is_file()),
            'builtin': True,
        }, indent=2), encoding='utf-8')
        made += 1
    return made


# ── portability ───────────────────────────────────────────────────────────────
def export_template(template_id: str) -> dict[str, Any] | None:
    """Serialise a template to plain JSON so it can be shared as one file.

    "A workspace is a folder. It can be copied to another machine, committed to
    Git, emailed as a zip." Text-only on purpose: a template carrying binaries
    is a template nobody will read before running it.
    """
    d = template_dir(template_id)
    if d is None or not (d / META_NAME).is_file():
        return None
    meta = get_template(template_id) or {}
    files: dict[str, str] = {}
    for f in sorted(d.rglob('*')):
        if not f.is_file() or f.name == META_NAME:
            continue
        try:
            text = f.read_text(encoding='utf-8')
        except (OSError, UnicodeDecodeError):
            continue
        files[f.relative_to(d).as_posix()] = text
    return {'template': {k: v for k, v in meta.items() if k != 'files'}, 'files': files}


def import_template(payload: dict[str, Any], template_id: str = '',
                    overwrite: bool = False) -> dict[str, Any]:
    """Load an exported template. Every path is contained before it is written."""
    meta = payload.get('template') or {}
    files = payload.get('files') or {}
    if not isinstance(files, dict) or not files:
        return {'ok': False, 'error': 'no files in payload'}

    tid = _slug(template_id or meta.get('template_id') or meta.get('name') or '')
    d = template_dir(tid)
    if d is None:
        return {'ok': False, 'error': f'invalid template id {tid!r}'}
    if d.exists() and not overwrite:
        return {'ok': False, 'error': f'template {tid!r} already exists'}
    if d.exists():
        shutil.rmtree(d)
    d.mkdir(parents=True, exist_ok=True)

    written, refused = 0, []
    for rel, content in list(files.items())[:MAX_TEMPLATE_FILES]:
        target = safe_path(str(rel), base=d)
        # An imported template is untrusted input that becomes files on disk.
        if target is None or not isinstance(content, str):
            refused.append(str(rel))
            continue
        try:
            target.parent.mkdir(parents=True, exist_ok=True)
            target.write_text(content[:400_000], encoding='utf-8')
            written += 1
        except OSError:
            refused.append(str(rel))

    (d / META_NAME).write_text(json.dumps({
        'template_id': tid,
        'name': meta.get('name') or tid,
        'description': meta.get('description', ''),
        'form': meta.get('form', 'pipeline'),
        'extracted_from': meta.get('extracted_from', ''),
        'created_at': time.time(),
        'file_count': written,
        'builtin': False,
        'imported': True,
    }, indent=2), encoding='utf-8')

    return {'ok': True, 'template_id': tid, 'written': written, 'refused': refused}
