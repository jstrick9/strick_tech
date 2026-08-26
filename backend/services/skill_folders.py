"""Skills as folders — SKILL.md with three-level progressive disclosure.

The Agent Skills convention (Anthropic, ~40 platforms) and Van Clief's reading
of it: a skill is a FOLDER whose entry file is plain markdown with YAML
frontmatter, and it is loaded in three levels so a model never pays for
capability it is not using.

    Level 1  frontmatter        ~30-100 tokens   ALWAYS loaded (discovery)
    Level 2  the body           <5k tokens       loaded when the skill is chosen
    Level 3  bundled files      ~0 tokens        read on demand, by path

    "Skills are ICM in miniature -- plain-text processes an agent navigates,
     markdown that can embed Python for determinism."

WHAT WAS ACTUALLY WRONG HERE

Measured on this repo before writing any of this:

    skills/skills.json          83 skills, one file, no folders
    GET /api/skills             returns ALL 83 IN FULL, every field
    whole registry              24,641 chars  ~6,160 tokens
    name + description only      4,374 chars  ~1,093 tokens

So discovery -- "what can you do?" -- cost 6.2k tokens when it needed 1.1k, and
there was no level structure at all: no way to load a skill's instructions
without loading all 83, and no way for an author to edit one as a file. A
registry blob is also the thing you cannot review in a diff, cannot version
per-skill, and cannot hand to someone as a folder.

WHY BOTH REPRESENTATIONS EXIST

skills.json still works and still runs. This module adds the folder form
alongside it and merges the two on read, because 83 existing skills and the
Skills pane both depend on the registry. Deleting it to make a point would
break working software; the canon's own advice is to extract structure from
what is there, not replace it.

THE SAFETY POSTURE

A SKILL.md is untrusted input: it arrives by import, from a marketplace, or
from a folder someone was handed. >99% of published SKILL.md files carry a
"skill smell" and 36% of community skills carry a security flaw, so:

  * paths are resolved with safe_path and cannot escape the skills root
  * frontmatter is parsed with a strict minimal parser, never eval/yaml.load
  * bundled files are listed but NEVER auto-read into a prompt
  * the existing plugin safety scanner is applied on import
"""

from __future__ import annotations

import re
from pathlib import Path
from typing import Any

from backend.config import get_data_dir

from .safe_paths import safe_path

ROOT = get_data_dir()
SKILLS_DIR = ROOT / 'skills'

# Level budgets from the convention. Exceeding them is a warning, not an error:
# they describe what stays cheap, and an over-budget skill still runs.
L1_MAX_TOKENS = 100
L2_MAX_TOKENS = 5000
# "Body under 500 lines, references one level deep" -- the published guidance.
L2_MAX_LINES = 500

SKILL_ID_RE = re.compile(r'^[a-z0-9][a-z0-9_-]{0,63}$')

# Fields a frontmatter block may declare. Anything else is preserved but not
# trusted for behaviour, so a crafted skill cannot introduce new semantics by
# inventing a key.
KNOWN_FIELDS = frozenset({
    'name', 'description', 'id', 'category', 'emoji', 'agent', 'version',
    'author', 'license', 'tags', 'inputs', 'allowed_tools',
})


def _tokens(text: str) -> int:
    return len(str(text or '')) // 4


def parse_frontmatter(text: str) -> tuple[dict[str, Any], str]:
    """Split a SKILL.md into (frontmatter, body).

    Deliberately a strict minimal parser, NOT yaml.safe_load. A SKILL.md is
    untrusted input from imports and marketplaces; a full YAML parser accepts
    anchors, aliases, tags and multi-document streams, which are attack surface
    for something whose entire job is to hold five scalar fields and a list.
    Anything this parser does not understand is ignored rather than executed.
    """
    raw = str(text or '')
    if not raw.startswith('---'):
        return {}, raw.strip()

    end = raw.find('\n---', 3)
    if end == -1:
        # An unterminated block is malformed. Treating the whole file as
        # frontmatter would hide the body; treating it as body is safer.
        return {}, raw.strip()

    block = raw[3:end]
    body = raw[end + 4:].strip()

    meta: dict[str, Any] = {}
    current_list: str | None = None
    for line in block.splitlines():
        if not line.strip() or line.lstrip().startswith('#'):
            continue
        item = re.match(r'^\s*-\s+(.*)$', line)
        if item and current_list:
            meta[current_list].append(item.group(1).strip().strip('\'"'))
            continue
        m = re.match(r'^([A-Za-z_][A-Za-z0-9_-]*)\s*:\s*(.*)$', line)
        if not m:
            continue
        key, value = m.group(1).strip(), m.group(2).strip()
        if not value:
            meta[key] = []
            current_list = key
            continue
        current_list = None
        if value.startswith('[') and value.endswith(']'):
            meta[key] = [v.strip().strip('\'"') for v in value[1:-1].split(',') if v.strip()]
        else:
            meta[key] = value.strip('\'"')
    return meta, body


def skill_dir(skill_id: str) -> Path | None:
    if not skill_id or not SKILL_ID_RE.match(str(skill_id)):
        return None
    return safe_path(str(skill_id), base=SKILLS_DIR)


def _bundled(d: Path) -> list[dict[str, Any]]:
    """List level-3 files WITHOUT reading them.

    Level 3 is "~0 tokens" precisely because the model is told what exists and
    reads only what it needs. Auto-reading bundled files here would collapse
    three levels back into one and defeat the whole structure.
    """
    out: list[dict[str, Any]] = []
    for p in sorted(d.rglob('*')):
        if not p.is_file() or p.name == 'SKILL.md' or p.name.startswith('.'):
            continue
        try:
            size = p.stat().st_size
        except OSError:
            continue
        out.append({'path': p.relative_to(d).as_posix(), 'bytes': size})
    return out


def read_skill(skill_id: str) -> dict[str, Any] | None:
    """Read one folder skill at full depth (levels 1 and 2, plus a level-3 list)."""
    d = skill_dir(skill_id)
    if d is None or not (d / 'SKILL.md').is_file():
        return None
    try:
        text = (d / 'SKILL.md').read_text(encoding='utf-8', errors='ignore')
    except OSError:
        return None

    meta, body = parse_frontmatter(text)
    files = _bundled(d)
    return {
        'id': meta.get('id') or skill_id,
        'name': meta.get('name') or skill_id,
        'description': meta.get('description') or '',
        'category': meta.get('category') or 'other',
        'emoji': meta.get('emoji') or '🧩',
        'agent': meta.get('agent') or '',
        'tags': meta.get('tags') or [],
        'inputs': meta.get('inputs') or [],
        'allowed_tools': meta.get('allowed_tools') or [],
        'source': 'folder',
        'body': body,
        'files': files,
        'unknown_fields': sorted(set(meta) - KNOWN_FIELDS),
        'tokens': {
            'level1': _tokens(f'{meta.get("name", "")} {meta.get("description", "")}'),
            'level2': _tokens(body),
            'level3_files': len(files),
        },
    }


def level1(skill: dict[str, Any]) -> dict[str, Any]:
    """The discovery card. This is what "what can you do?" should cost."""
    return {
        'id': skill['id'],
        'name': skill['name'],
        'description': skill['description'],
        'category': skill.get('category', 'other'),
        'emoji': skill.get('emoji', '🧩'),
        'source': skill.get('source', 'registry'),
    }


def _registry_skills() -> list[dict[str, Any]]:
    """The pre-existing skills.json entries, normalised to the same shape.

    Kept because 83 skills and the Skills pane depend on it. The folder form is
    additive; breaking working software to make an architectural point is not
    an improvement.
    """
    try:
        from ..routers.skills import load_skills
    except (ImportError, AttributeError):
        return []
    try:
        raw = load_skills()
    except Exception:
        return []

    out: list[dict[str, Any]] = []
    for s in raw:
        if not isinstance(s, dict) or not s.get('id'):
            continue
        body = str(s.get('prompt_template') or '')
        out.append({
            'id': str(s['id']),
            'name': str(s.get('name') or s['id']),
            'description': str(s.get('description') or ''),
            'category': str(s.get('category') or 'other'),
            'emoji': str(s.get('emoji') or '🧩'),
            'agent': str(s.get('agent') or ''),
            'tags': [],
            'inputs': s.get('inputs') or [],
            'allowed_tools': [],
            'source': 'registry',
            'body': body,
            'files': [],
            'unknown_fields': [],
            'tokens': {'level1': _tokens(f'{s.get("name", "")} {s.get("description", "")}'),
                       'level2': _tokens(body), 'level3_files': 0},
        })
    return out


def _folder_skills() -> list[dict[str, Any]]:
    if not SKILLS_DIR.is_dir():
        return []
    out: list[dict[str, Any]] = []
    for d in sorted(SKILLS_DIR.iterdir()):
        if not d.is_dir() or d.name.startswith('.') or not SKILL_ID_RE.match(d.name):
            continue
        skill = read_skill(d.name)
        if skill:
            out.append(skill)
    return out


def index() -> list[dict[str, Any]]:
    """Every skill from both representations. Folder form wins an id clash."""
    folders = _folder_skills()
    seen = {s['id'] for s in folders}
    return folders + [s for s in _registry_skills() if s['id'] not in seen]


def catalog() -> dict[str, Any]:
    """Level 1 only: the cheap listing that answers "what can you do?".

    This is the measurable payoff. Before, discovery returned all 83 skills in
    full at ~6,160 tokens; the same question answered from level 1 costs ~1,100.
    """
    all_skills = index()
    cards = [level1(s) for s in all_skills]
    return {
        'skills': cards,
        'count': len(cards),
        'level1_tokens': sum(_tokens(f'{c["name"]} {c["description"]}') for c in cards),
        'full_tokens': sum(s['tokens']['level1'] + s['tokens']['level2'] for s in all_skills),
    }


def load_level(skill_id: str, level: int = 2) -> dict[str, Any] | None:
    """Load a single skill to the requested depth.

    Level 3 returns the file LIST, not the file contents. A caller that wants a
    bundled file asks for it by path, which is the entire point of the level
    existing.
    """
    skill = next((s for s in index() if s['id'] == skill_id), None)
    if skill is None:
        return None
    card = level1(skill)
    if level <= 1:
        return {**card, 'level': 1}
    out = {**card, 'level': min(level, 3), 'body': skill['body'],
           'inputs': skill.get('inputs') or [], 'agent': skill.get('agent', '')}
    if level >= 3:
        out['files'] = skill.get('files') or []
    return out


def read_bundled(skill_id: str, rel_path: str) -> dict[str, Any] | None:
    """Read one level-3 file, by explicit request only."""
    d = skill_dir(skill_id)
    if d is None or not d.is_dir():
        return None
    target = safe_path(rel_path, base=d, must_exist=True)
    # Containment matters more than usual: this content is destined for a model
    # prompt, so an escape here is an arbitrary file read fed to an LLM.
    if target is None or not target.is_file() or target.name == 'SKILL.md':
        return None
    try:
        content = target.read_text(encoding='utf-8', errors='ignore')[:200_000]
    except OSError:
        return None
    return {'path': rel_path, 'content': content, 'tokens': _tokens(content)}


def validate(skill: dict[str, Any]) -> dict[str, Any]:
    """Check a skill against the convention's budgets and smells."""
    errors: list[str] = []
    warnings: list[str] = []

    if not skill.get('name'):
        errors.append('No name: nothing to show in the catalog.')
    if not skill.get('description'):
        errors.append('No description: a model cannot tell when to choose this skill.')

    t = skill.get('tokens', {})
    if t.get('level1', 0) > L1_MAX_TOKENS:
        warnings.append(
            f'Level 1 is {t["level1"]} tokens (convention: under {L1_MAX_TOKENS}). '
            'Level 1 loads for EVERY skill on every turn, so this cost is paid '
            'whether or not the skill is used.')
    if t.get('level2', 0) > L2_MAX_TOKENS:
        warnings.append(f'Level 2 is {t["level2"]} tokens (convention: under {L2_MAX_TOKENS}).')

    lines = str(skill.get('body', '')).count('\n') + 1
    if lines > L2_MAX_LINES:
        warnings.append(f'Body is {lines} lines (convention: under {L2_MAX_LINES}). '
                        'Push detail into bundled files and point at them.')

    if skill.get('unknown_fields'):
        warnings.append(f'Unrecognised frontmatter fields {skill["unknown_fields"]} '
                        'are preserved but do not affect behaviour.')

    return {'ok': not errors, 'errors': errors, 'warnings': warnings}


def write_skill(skill_id: str, frontmatter: dict[str, Any], body: str) -> dict[str, Any] | None:
    """Create or overwrite a folder skill's SKILL.md."""
    d = skill_dir(skill_id)
    if d is None:
        return None
    d.mkdir(parents=True, exist_ok=True)
    lines = ['---']
    for key in ('name', 'description', 'category', 'emoji', 'agent'):
        if frontmatter.get(key):
            lines.append(f'{key}: {frontmatter[key]}')
    if frontmatter.get('tags'):
        lines.append('tags: [' + ', '.join(str(t) for t in frontmatter['tags']) + ']')
    lines += ['---', '', str(body or '').strip(), '']
    (d / 'SKILL.md').write_text('\n'.join(lines), encoding='utf-8')
    return read_skill(skill_id)


def migrate_registry_entry(entry: dict[str, Any]) -> dict[str, Any] | None:
    """Turn one skills.json entry into a folder skill.

    Method and instance live apart: the registry keeps working, and this
    produces the editable folder form of the same skill for anyone who wants
    to version, diff or hand it over as a folder.
    """
    sid = str(entry.get('id') or '').strip()
    # Redundant with write_skill's own skill_dir() check, and knowingly kept:
    # the revert proof confirms removing THIS line changes no observable
    # behaviour, because the inner guard already refuses and nothing escapes.
    # It stays as defence in depth at the trust boundary -- registry entries
    # arrive from marketplaces -- and is documented as belt-and-braces rather
    # than left looking like the only thing standing between a hostile id and
    # the filesystem.
    if not SKILL_ID_RE.match(sid):
        return None
    return write_skill(
        sid,
        {'name': entry.get('name'), 'description': entry.get('description'),
         'category': entry.get('category'), 'emoji': entry.get('emoji'),
         'agent': entry.get('agent')},
        str(entry.get('prompt_template') or ''),
    )
