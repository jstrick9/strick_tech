"""
Agentic OS — Template Gallery Router
Production-ready starter templates across:
- SaaS & Business (dashboards, landing pages, pricing, auth, CRM)
- Apps & Tools (todo, notes, calculator, weather, chat, URL shortener)
- Portfolio & Marketing (personal site, agency, product launch, waitlist)
- E-Commerce (product page, cart, checkout, store)

Each template is a fully working HTML/CSS/JS app that scaffolds instantly.
"""

from __future__ import annotations

import html
import json
import logging
import re
from datetime import datetime, timezone
from pathlib import Path

from fastapi import APIRouter, Request
from fastapi.responses import JSONResponse

from ..services.memory_db import audit_log, get_conn

router = APIRouter(prefix='/api/templates', tags=['templates'])
log = logging.getLogger('agentic.templates')
from backend.config import get_data_dir

from ..services.request_body import as_text, json_body_or_error

ROOT = get_data_dir()
PREV = ROOT / 'preview'
PREV.mkdir(parents=True, exist_ok=True)


# ── Template catalogue ─────────────────────────────────────────────────────────
# ── Template catalogue ─────────────────────────────────────────────────────────
# ARCHITECTURE: the 14 built-in templates used to be ~660 lines of inline HTML
# string literals in this file, which meant editing a starter template required
# editing backend Python (and risked breaking the router with a stray quote).
# They now live on disk under templates/<id>/ as a template.json manifest plus
# the real files, so they can be edited, diffed and reviewed as ordinary source
# — and third parties can ship new ones by dropping in a directory.
TEMPLATES_DIR = Path(__file__).resolve().parent.parent.parent / 'templates'

# Manifest fields that are copied through to the API as-is.
_MANIFEST_FIELDS = ('id', 'name', 'category', 'emoji', 'description', 'prompt', 'tags', 'preview_color')


def _load_template_dir(d: Path) -> dict | None:
    """Load one templates/<id>/ directory into the in-memory catalogue shape."""
    manifest_path = d / 'template.json'
    if not manifest_path.is_file():
        return None
    try:
        meta = json.loads(manifest_path.read_text(encoding='utf-8'))
    except (OSError, json.JSONDecodeError) as exc:
        log.warning('Skipping template %s — unreadable manifest: %s', d.name, exc)
        return None

    tpl = {k: meta.get(k) for k in _MANIFEST_FIELDS if meta.get(k) is not None}
    tpl.setdefault('id', d.name)
    tpl.setdefault('category', 'custom')
    tpl.setdefault('name', d.name.replace('-', ' ').title())
    tpl.setdefault('emoji', '📄')
    tpl.setdefault('description', '')
    tpl.setdefault('tags', [])
    tpl.setdefault('preview_color', '#5b8af8')

    files: dict[str, str] = {}
    for rel in meta.get('files', []):
        # Manifest-declared paths must stay inside the template directory.
        candidate = (d / rel).resolve()
        try:
            candidate.relative_to(d.resolve())
        except ValueError:
            log.warning('Skipping %s in template %s — escapes template dir', rel, d.name)
            continue
        if candidate.is_file():
            files[rel] = candidate.read_text(encoding='utf-8')
        else:
            log.warning('Template %s declares missing file %s', d.name, rel)
    if not files:
        return None
    tpl['files'] = files
    return tpl


def load_templates() -> list[dict]:
    """Read every template directory from disk, sorted by id for stable output."""
    if not TEMPLATES_DIR.is_dir():
        log.warning('Templates directory not found: %s', TEMPLATES_DIR)
        return []
    out = []
    for d in sorted(TEMPLATES_DIR.iterdir()):
        if not d.is_dir() or d.name.startswith(('.', '_')):
            continue
        tpl = _load_template_dir(d)
        if tpl:
            out.append(tpl)
    return out


TEMPLATES: list[dict] = load_templates()


def reload_templates() -> int:
    """Re-read templates from disk in place. Returns the new count."""
    TEMPLATES[:] = load_templates()
    return len(TEMPLATES)



# ── Helpers ───────────────────────────────────────────────────────────────────

_CATEGORY_LABELS = {
    'saas': 'SaaS & Business',
    'apps': 'Apps & Tools',
    'portfolio': 'Portfolio',
    'marketing': 'Marketing',
    'ecommerce': 'E-Commerce',
}


def _safe_name(name: str) -> str:
    """Sanitize a project name for HTML substitution."""
    return re.sub(r'[^\w\s\-]', '', (name or '').strip())[:80]


def _within_preview(target: Path) -> bool:
    """True only if target is inside PREV.

    Uses path semantics rather than str.startswith(), which treats a sibling
    directory sharing a name prefix (e.g. `preview_backup/`) as being inside
    `preview/`.
    """
    try:
        target.resolve().relative_to(PREV.resolve())
        return True
    except (ValueError, OSError):
        return False


# Placeholders that the built-in templates use for the product/brand name.
_NAME_PLACEHOLDERS = ('YourSaaS', 'Your Name', 'Your Company', 'My App')


def _apply_project_name(content: str, project_name: str) -> str:
    """Substitute the user's project name into a template file.

    BUG FIX: substitution only replaced the four literal placeholders above, but
    just 3 of the 14 built-in templates actually contain one. For the other 11
    (todo-app, notes-app, weather-app, chat-app, ...) the UI collected a project
    name, sent it, and it silently did nothing — the scaffolded app still said
    "Todo App". Falling back to rewriting the document <title> and the first
    <h1> means naming a project has a visible effect for every template.
    """
    if not project_name:
        return content

    replaced_any = False
    for placeholder in _NAME_PLACEHOLDERS:
        if placeholder in content:
            content = content.replace(placeholder, project_name)
            replaced_any = True
    if replaced_any:
        return content

    safe = html.escape(project_name)
    content, n_title = re.subn(r'(<title>)(.*?)(</title>)', lambda m: m.group(1) + safe + m.group(3), content, count=1, flags=re.S)
    content, _ = re.subn(r'(<h1\b[^>]*>)(.*?)(</h1>)', lambda m: m.group(1) + safe + m.group(3), content, count=1, flags=re.S)
    return content


def _current_workspace_id() -> str:
    """Resolve the active workspace without making workspace imports mandatory.

    BUG FIX: template scaffolding previously inserted into `file_versions`
    without a `workspace_id` at all (it defaults to '' at the column level),
    unlike every other write path into this table (builder.py's save/commit/
    restore/scaffold all tag rows with the CURRENT workspace). Every
    version-history read query in the app matches `workspace_id=? OR
    workspace_id=''` specifically to remain backward-compatible with old
    untagged rows — which means an untagged template-scaffold row is visible
    from EVERY workspace's history, not just the one it was scaffolded into.
    Tagging these rows properly prevents template-scaffold history from
    leaking across workspace boundaries.
    """
    try:
        from .workspaces import _current_ws_id

        return _current_ws_id() or ''
    except Exception:
        return ''


def _template_summary(t: dict) -> dict:
    """Return safe public fields (no raw file content)."""
    return {
        'id': t['id'],
        'name': t['name'],
        'category': t['category'],
        'emoji': t['emoji'],
        'description': t['description'],
        'tags': t['tags'],
        'preview_color': t.get('preview_color', '#5b8af8'),
        'prompt': t.get('prompt', ''),
        'file_count': len(t.get('files', {})),
        'file_names': list(t.get('files', {}).keys()),
    }


# ── Endpoints ──────────────────────────────────────────────────────────────────


@router.get('')
def list_templates(category: str = '', q: str = ''):
    """List all templates, optionally filtered by category or search query."""
    results = [_template_summary(t) for t in TEMPLATES]
    if category:
        results = [t for t in results if t['category'] == category]
    if q:
        ql = q.lower()
        results = [
            t
            for t in results
            if ql in t['name'].lower() or ql in t['description'].lower() or any(ql in tag.lower() for tag in t['tags'])
        ]
    return {
        'templates': results,
        'count': len(results),
        'total': len(TEMPLATES),
    }


@router.get('/categories')
def list_categories():
    """Return all categories with counts and labels."""
    cats: dict = {}
    for t in TEMPLATES:
        c = t['category']
        cats[c] = cats.get(c, 0) + 1
    return [{'id': k, 'label': _CATEGORY_LABELS.get(k, k.title()), 'count': v} for k, v in sorted(cats.items())]


@router.get('/search')
def search_templates(q: str = '', limit: int = 10):
    """Search templates by name, description, or tags."""
    if not q.strip():
        return {'results': [], 'count': 0}
    ql = q.lower().strip()
    results = [
        _template_summary(t)
        for t in TEMPLATES
        if ql in t['name'].lower() or ql in t['description'].lower() or any(ql in tag.lower() for tag in t['tags'])
    ][: max(1, min(limit, 50))]
    return {'results': results, 'count': len(results), 'query': q}


# ── Saved snapshots ────────────────────────────────────────────────────────────
# MISSING FEATURE: /scaffold-custom wrote snapshots into preview/templates/ but
# nothing could list, restore or delete them — they were write-only, reachable
# only by guessing the slugged URL. These three endpoints make saved work a
# first-class part of the gallery.

_SAVED_INDEX = 'index.json'


def _saved_dir() -> Path:
    d = PREV / 'templates'
    d.mkdir(parents=True, exist_ok=True)
    return d


def _read_saved_index() -> dict:
    """filename -> original display name."""
    fp = _saved_dir() / _SAVED_INDEX
    if not fp.is_file():
        return {}
    try:
        data = json.loads(fp.read_text(encoding='utf-8'))
        return data if isinstance(data, dict) else {}
    except (OSError, json.JSONDecodeError):
        return {}


def _write_saved_index(mapping: dict) -> None:
    try:
        (_saved_dir() / _SAVED_INDEX).write_text(json.dumps(mapping, indent=2), encoding='utf-8')
    except OSError as exc:
        log.warning('Could not update saved-template index: %s', exc)


def _resolve_saved(filename: str) -> Path | None:
    """Resolve a saved snapshot filename, refusing anything outside the dir."""
    name = (filename or '').strip()
    if not name or '/' in name or '\\' in name or not name.endswith('.html'):
        return None
    target = (_saved_dir() / name).resolve()
    try:
        target.relative_to(_saved_dir().resolve())
    except ValueError:
        return None
    return target if target.is_file() else None


@router.get('/saved')
def list_saved():
    """List snapshots created by 'Save Current Work'."""
    names = _read_saved_index()
    out = []
    for fp in sorted(_saved_dir().glob('*.html')):
        try:
            stat = fp.stat()
        except OSError:
            continue
        out.append({
            'filename': fp.name,
            'name': names.get(fp.name, fp.stem.replace('_', ' ').title()),
            'bytes': stat.st_size,
            'saved_at': datetime.fromtimestamp(stat.st_mtime, tz=timezone.utc).isoformat(),
            'url': f'/preview/templates/{fp.name}',
        })
    out.sort(key=lambda x: x['saved_at'], reverse=True)
    return {'ok': True, 'saved': out, 'count': len(out)}


@router.post('/saved/{filename}/restore')
def restore_saved(filename: str):
    """Restore a snapshot back into preview/index.html.

    The file being replaced is snapshotted into file_versions first, for the
    same reason scaffolding does it — restoring must never be a one-way door.
    """
    src = _resolve_saved(filename)
    if src is None:
        return JSONResponse({'ok': False, 'error': 'Saved template not found'}, status_code=404)

    dest = PREV / 'index.html'
    con = get_conn()
    try:
        if dest.is_file():
            previous = dest.read_text(encoding='utf-8', errors='replace')
            if previous.strip():
                con.execute(
                    'INSERT INTO file_versions(path,content,author,message,workspace_id) VALUES (?,?,?,?,?)',
                    ('index.html', previous, 'template', f'Auto-backup before restoring: {filename}',
                     _current_workspace_id()),
                )
        content = src.read_text(encoding='utf-8')
        dest.write_text(content, encoding='utf-8')
        con.execute(
            'INSERT INTO file_versions(path,content,author,message,workspace_id) VALUES (?,?,?,?,?)',
            ('index.html', content, 'template', f'Restored saved template: {filename}', _current_workspace_id()),
        )
        con.commit()
    finally:
        con.close()

    audit_log('template_saved_restore', filename)
    return {'ok': True, 'filename': filename, 'preview_url': '/preview/index.html'}


@router.delete('/saved/{filename}')
def delete_saved(filename: str):
    """Delete a saved snapshot."""
    target = _resolve_saved(filename)
    if target is None:
        return JSONResponse({'ok': False, 'error': 'Saved template not found'}, status_code=404)
    try:
        target.unlink()
    except OSError as exc:
        return JSONResponse({'ok': False, 'error': f'Could not delete: {exc}'}, status_code=500)
    index = _read_saved_index()
    index.pop(target.name, None)
    _write_saved_index(index)
    audit_log('template_saved_delete', filename)
    return {'ok': True, 'deleted': filename}


@router.get('/{template_id}/preview')
def get_template_preview(template_id: str):
    """Return the first HTML file content for in-pane preview."""
    t = next((t for t in TEMPLATES if t['id'] == template_id), None)
    if not t:
        # Was a 200 with ok:false — a missing template is a 404, and returning
        # 200 meant callers doing `if (r.ok)` treated it as success.
        return JSONResponse({'ok': False, 'error': f"Template '{template_id}' not found"}, status_code=404)
    files = t.get('files', {})
    for fname, fcontent in files.items():
        if fname.endswith('.html'):
            return {
                'ok': True,
                'filename': fname,
                'content': fcontent,
                'template': t['name'],
                'renderable': True,
                'file_count': len(files),
            }

    # Not every template is a web page. Backend starters (e.g. fastapi-service)
    # ship no HTML at all, and previously got a flat "No HTML file in template"
    # error — so the 👁 preview button was simply broken for them. Fall back to
    # showing the primary source file, flagged as non-renderable so the UI
    # displays it as code rather than trying to run it in an iframe.
    preferred = ('README.md', 'app/main.py', 'main.py', 'index.js', 'package.json')
    for candidate in preferred:
        if candidate in files:
            return {
                'ok': True,
                'filename': candidate,
                'content': files[candidate],
                'template': t['name'],
                'renderable': False,
                'file_count': len(files),
            }
    first = next(iter(files.items()), None)
    if first:
        return {
            'ok': True,
            'filename': first[0],
            'content': first[1],
            'template': t['name'],
            'renderable': False,
            'file_count': len(files),
        }
    return JSONResponse({'ok': False, 'error': 'Template ships no files'}, status_code=404)


@router.get('/{template_id}')
def get_template(template_id: str):
    """Get full template details including file names (not content)."""
    t = next((t for t in TEMPLATES if t['id'] == template_id), None)
    if not t:
        return JSONResponse({'ok': False, 'error': f"Template '{template_id}' not found"}, status_code=404)
    return {**_template_summary(t), 'ok': True}


@router.post('/{template_id}/scaffold')
async def scaffold_template(template_id: str, req: Request):
    """Scaffold a template into preview/.

    Body: {project_name?, overwrite?}

    BUG FIX (data loss): this used to overwrite preview/ unconditionally. If you
    had unsaved work open in Studio, scaffolding any template destroyed it with
    no warning, no confirmation and no way back — the template's NEW content was
    written to file_versions, but the user's REPLACED content never was, so it
    was genuinely unrecoverable. Reproduced live: hand-written index.html gone
    after one scaffold call.

    Now: any file that would be clobbered is first snapshotted into
    file_versions (so Studio's version history can restore it), and if the
    caller hasn't explicitly opted in with overwrite=true the request is
    refused with the list of files at risk so the UI can ask first.
    """
    body, _body_err = await json_body_or_error(req)
    if _body_err:
        return _body_err
    t = next((t for t in TEMPLATES if t['id'] == template_id), None)
    if not t:
        return JSONResponse({'ok': False, 'error': f"Template '{template_id}' not found"}, status_code=404)

    # Sanitised project name for substitution
    raw_name = body.get('project_name', '')
    custom_name = _safe_name(raw_name) if raw_name else ''
    overwrite = bool(body.get('overwrite'))

    PREV.mkdir(parents=True, exist_ok=True)

    # Which existing files would this scaffold replace?
    at_risk = []
    for filename in t['files']:
        target = (PREV / filename).resolve()
        if not _within_preview(target):
            continue
        if target.is_file() and target.read_text(encoding='utf-8', errors='replace').strip():
            at_risk.append(filename)

    if at_risk and not overwrite:
        return {
            'ok': False,
            'needs_confirmation': True,
            'error': 'This would replace existing files in your preview workspace.',
            'conflicts': at_risk,
            'template': t['name'],
            'template_id': template_id,
        }

    created: list = []
    replaced: list = []

    con = get_conn()
    try:
        for filename, file_content in t['files'].items():
            # Substitute project name placeholders
            if custom_name:
                file_content = _apply_project_name(file_content, custom_name)

            # Path traversal guard
            target = (PREV / filename).resolve()
            if not _within_preview(target):
                log.warning('Blocked path traversal attempt in template: %s', filename)
                continue

            # Snapshot whatever is being replaced so it stays recoverable from
            # Studio's version history.
            if target.is_file():
                try:
                    previous = target.read_text(encoding='utf-8', errors='replace')
                    if previous.strip():
                        con.execute(
                            'INSERT INTO file_versions(path,content,author,message,workspace_id) VALUES (?,?,?,?,?)',
                            (
                                filename,
                                previous,
                                'template',
                                f'Auto-backup before scaffolding: {t["name"]}',
                                _current_workspace_id(),
                            ),
                        )
                        replaced.append(filename)
                except OSError as exc:
                    log.warning('Could not snapshot %s before scaffold: %s', filename, exc)

            target.parent.mkdir(parents=True, exist_ok=True)
            target.write_text(file_content, encoding='utf-8')
            created.append(filename)

            # Record in file_versions
            try:
                con.execute(
                    'INSERT INTO file_versions(path,content,author,message,workspace_id) VALUES (?,?,?,?,?)',
                    (filename, file_content, 'template', f'Template: {t["name"]}', _current_workspace_id()),
                )
            except (KeyError, TypeError, ValueError, json.JSONDecodeError, OSError, AttributeError, RuntimeError):
                pass

        con.commit()
        audit_log('template_scaffold', f'{template_id}: {", ".join(created)}')
    finally:
        con.close()

    # Determine primary preview URL
    preview_url = '/preview/index.html'
    for fn in created:
        if fn.endswith('.html'):
            preview_url = f'/preview/{fn}'
            break

    message = f'✅ {t["name"]} scaffolded — {len(created)} file(s)'
    if replaced:
        message += f' — {len(replaced)} replaced file(s) backed up to version history'

    return {
        'ok': True,
        'template': t['name'],
        'template_id': template_id,
        'files': created,
        'replaced': replaced,
        'preview_url': preview_url,
        'message': message,
    }


@router.post('/scaffold-custom')
async def scaffold_custom(req: Request):
    """Save current preview/index.html as a named template backup."""
    body, _body_err = await json_body_or_error(req)
    if _body_err:
        return _body_err
    name = as_text(body.get('name'))[:80]
    if not name:
        return {'ok': False, 'error': 'name required'}

    src = PREV / 'index.html'
    if not src.exists():
        return {'ok': False, 'error': 'No index.html in preview/ to save'}

    # Save as a named backup in preview/templates/
    backup_dir = PREV / 'templates'
    backup_dir.mkdir(exist_ok=True)
    safe_fname = re.sub(r'[^\w\-]', '_', name.lower())[:40] + '.html'
    dest = backup_dir / safe_fname
    dest.write_text(src.read_text(encoding='utf-8'), encoding='utf-8')
    # Keep the display name — the filename is slugged and lossy ("My App" ->
    # "my_app"), so without this the gallery could only ever show the slug.
    _write_saved_index({**_read_saved_index(), safe_fname: name})
    audit_log('template_custom_save', name)
    return {
        'ok': True,
        'name': name,
        'saved_to': str(dest.relative_to(ROOT)),
        'url': f'/preview/templates/{safe_fname}',
    }


