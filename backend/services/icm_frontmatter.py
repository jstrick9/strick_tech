"""Typed frontmatter: one reader, a generated file map, and real dashboards.

Closes G5 and G7 together, because they are the same mechanism seen twice —
both need to read the typed YAML the form builders already write, and building
them separately would mean writing that reader twice.

WHAT WAS ACTUALLY WRONG, MEASURED FIRST

    form              FILE-MAP   .md files   with frontmatter
    pipeline          NO           6            0
    umbrella          NO          16            0
    record_library    NO          11            3
    knowledge_bundle  NO           7            2
    context_map       yes          9            4
    system_map        NO           8            3

G5: five of six forms had no generated index at all, so an agent had to crawl
the tree — the thing the canon says the catalog exists to prevent.

G7: the frontmatter was being WRITTEN and never READ. The context map even
shipped a `dashboards/00-tracker.md` containing this:

    ## What to automate next
    Sort process nodes by `value` desc, then `pain` desc, where `ai-level`
    is L0 or L1.

A prose description of a query, with nothing that runs it. That is a dashboard
that cannot answer its own question, which is worse than no dashboard: it looks
like the feature exists.

THE CANON THIS IMPLEMENTS

    "Every note carries typed YAML frontmatter (type:, layer:, access_tier:,
     strength:) — labels make it queryable, links make it a graph."

    "Generated indexes are never hand-edited. A file map built from frontmatter
     by a script cannot drift; a hand-curated one always does. If an index
     matters, script it and schedule the rebuild."

    "FILE-MAP.md — GENERATED index — agents jump here, never crawl."

ACCESS TIER IS ENFORCED, NOT DECORATIVE

    "access_tier gates what may leave the machine: patterns abstracted from
     private sources are fine; raw quotes are not."

So `query()` takes a max tier and filters. A field that labels sensitivity and
is then ignored by every reader is a false assurance, which is worse than not
labelling at all.
"""

from __future__ import annotations

import re
from pathlib import Path
from typing import Any

# Frontmatter is a header, so a bounded read is always enough to classify a
# file. Reading whole bodies to build an index is the same "cheap on the wire,
# expensive on disk" defect already found in the skills catalogue.
MAX_HEAD_BYTES = 2048
MAX_INDEXED_FILES = 2000

# Ordered least to most sensitive. Anything unlabelled is treated as `public`
# only because the alternative -- refusing to show unlabelled notes -- would
# hide most of a workspace; the ordering is what makes the gate meaningful.
ACCESS_TIERS = ('public', 'internal', 'private', 'secret')

_FM_RE = re.compile(r'^\s*---\s*\n(.*?)\n\s*---', re.S)
# Numeric-looking scores are compared, so they are parsed rather than kept as
# strings: '10' < '9' is true for strings and wrong for scores.
_NUM_RE = re.compile(r'^-?\d+(\.\d+)?$')


def parse_head(text: str) -> dict[str, Any]:
    """Parse a flat YAML frontmatter block. Values are typed where obvious."""
    m = _FM_RE.match(text or '')
    if not m:
        return {}
    out: dict[str, Any] = {}
    for line in m.group(1).splitlines():
        line = line.strip()
        if not line or line.startswith('#') or ':' not in line:
            continue
        key, _, raw = line.partition(':')
        key = key.strip().lower()
        val: Any = raw.strip().strip('"\'')
        if not key:
            continue
        if val.startswith('[') and val.endswith(']'):
            val = [v.strip().strip('"\'') for v in val[1:-1].split(',') if v.strip()]
        elif _NUM_RE.match(val):
            val = float(val) if '.' in val else int(val)
        elif val.lower() in ('true', 'false'):
            val = val.lower() == 'true'
        out[key] = val
    return out


def read_node(path: Path, root: Path) -> dict[str, Any] | None:
    """One indexed node: its frontmatter plus where it lives. Bounded read."""
    try:
        with path.open('r', encoding='utf-8', errors='ignore') as fh:
            head = fh.read(MAX_HEAD_BYTES)
    except OSError:
        return None
    # A truncated head can cut the closing '---'; re-terminate so a large file
    # still yields its metadata instead of silently vanishing from the index.
    if head.count('---') < 2:
        head = head + '\n---\n'
    meta = parse_head(head)
    rel = path.relative_to(root).as_posix()
    node: dict[str, Any] = {
        'path': rel,
        'name': path.stem,
        'type': str(meta.get('type') or '').lower(),
        'layer': str(meta.get('layer') or ''),
        'access_tier': str(meta.get('access_tier') or 'public').lower(),
        'tags': meta.get('tags') or [],
        'fields': {k: v for k, v in meta.items()
                   if k not in ('type', 'layer', 'access_tier', 'tags')},
        'has_frontmatter': bool(meta),
    }
    if node['access_tier'] not in ACCESS_TIERS:
        node['access_tier'] = 'public'
    return node


def index_workspace(ws: Path) -> list[dict[str, Any]]:
    """Every markdown node in a workspace, with its frontmatter."""
    if not ws.is_dir():
        return []
    out: list[dict[str, Any]] = []
    for p in sorted(ws.rglob('*.md')):
        if len(out) >= MAX_INDEXED_FILES:
            break
        if p.name == 'FILE-MAP.md' or any(part.startswith('.') for part in p.parts):
            continue
        node = read_node(p, ws)
        if node:
            out.append(node)
    return out


# ── G5: the generated file map, for every form ────────────────────────────────
def generate_file_map(ws: Path) -> str:
    """Rebuild FILE-MAP.md from the tree and its frontmatter.

    Works for all six forms, not just the context map. The header states that
    it is generated, because the one thing that reliably breaks a scripted
    index is somebody hand-editing it and expecting the edit to survive.
    """
    nodes = index_workspace(ws)
    typed = [n for n in nodes if n['has_frontmatter']]

    lines = [
        '# File map',
        '',
        '**GENERATED — do not hand-edit.** Rebuilt from the tree and node frontmatter.',
        'Agents jump from here; they never crawl the tree.',
        '',
        f'{len(nodes)} markdown files, {len(typed)} carrying typed frontmatter.',
        '',
    ]

    by_type: dict[str, list[dict[str, Any]]] = {}
    for n in typed:
        by_type.setdefault(n['type'] or 'untyped', []).append(n)
    if by_type:
        lines += ['## By type', '', '| Type | Count |', '|------|-------|']
        lines += [f'| {t} | {len(v)} |' for t, v in sorted(by_type.items())]
        lines.append('')

    lines += ['## Files', '', '| Path | Type | Layer | Access |', '|------|------|-------|--------|']
    for n in nodes:
        lines.append(
            f'| `{n["path"]}` | {n["type"] or "—"} | {n["layer"] or "—"} | {n["access_tier"]} |')
    body = '\n'.join(lines) + '\n'
    (ws / 'FILE-MAP.md').write_text(body, encoding='utf-8')
    return body


def rebuild_all() -> dict[str, Any]:
    """Regenerate every workspace's file map. Safe to schedule."""
    from . import icm

    root = icm.WORKSPACES_DIR
    if not root.is_dir():
        return {'rebuilt': 0, 'workspaces': []}
    done: list[str] = []
    for d in sorted(root.iterdir()):
        if not d.is_dir() or d.name.startswith('.') or not icm.WORKSPACE_ID_RE.match(d.name):
            continue
        generate_file_map(d)
        done.append(d.name)
    return {'rebuilt': len(done), 'workspaces': done}


# ── G7: queries over the frontmatter ──────────────────────────────────────────
def _tier_rank(tier: str) -> int:
    try:
        return ACCESS_TIERS.index(tier)
    except ValueError:
        return 0


def query(ws: Path, node_type: str = '', tag: str = '',
          max_access_tier: str = 'secret', sort_by: str = '',
          descending: bool = True, limit: int = 100) -> dict[str, Any]:
    """Query the frontmatter. The thing the dashboards were only describing.

    `max_access_tier` is enforced, not advisory. A field that labels
    sensitivity and is ignored by every reader is a false assurance.
    """
    nodes = [n for n in index_workspace(ws) if n['has_frontmatter']]
    ceiling = _tier_rank(max_access_tier if max_access_tier in ACCESS_TIERS else 'secret')

    withheld = 0
    kept: list[dict[str, Any]] = []
    for n in nodes:
        if _tier_rank(n['access_tier']) > ceiling:
            withheld += 1
            continue
        if node_type and n['type'] != node_type.lower():
            continue
        if tag and tag not in (n['tags'] or []):
            continue
        kept.append(n)

    if sort_by:
        # ONE sort, not two. An earlier draft sorted by (has_field, value) with
        # reverse=True -- which also reverses the has_field flag and floats
        # unscored nodes to the top -- and then ran a SECOND sort to undo that.
        # The two overlapped, so the first tuple element was dead: the revert
        # proof showed it could be changed with no observable effect.
        #
        # Sorting the value alone and keeping "missing sorts last" as a
        # separate, non-reversed partition does the job once and stays
        # readable.
        def _score(n: dict[str, Any]) -> float | None:
            v = n['fields'].get(sort_by)
            if isinstance(v, (int, float)) and not isinstance(v, bool):
                return float(v)
            return None

        scored = [n for n in kept if _score(n) is not None]
        unscored = [n for n in kept if _score(n) is None]
        scored.sort(key=lambda n: _score(n) or 0.0, reverse=descending)
        # Nodes missing the field always sort last, whichever direction the
        # scored ones run: a missing score is not a low score, and treating it
        # as zero would rank it above a real 1.
        kept = scored + unscored

    return {
        'nodes': kept[:max(1, min(limit, 500))],
        'matched': len(kept),
        'total_typed': len(nodes),
        # Reported, not silent: a query that quietly drops private notes looks
        # identical to one that found nothing.
        'withheld_by_access_tier': withheld,
    }


# The canon's own example, made executable: "Sort process nodes by value desc,
# then pain desc, where ai-level is L0 or L1."
AUTOMATION_LEVELS = ('l0', 'l1')


def automation_candidates(ws: Path, limit: int = 20,
                          max_access_tier: str = 'internal') -> dict[str, Any]:
    """What to automate next — the dashboard question, actually answered.

    Access tier is enforced HERE too, not only in query(). Found while
    verifying live: a node marked `access_tier: secret` came top of the
    automation table, because the tier check lived in query() and this path
    read the index directly. A gate applied on one route and not the other is
    not a gate -- and a dashboard is exactly the surface someone screen-shares.
    """
    ceiling = _tier_rank(max_access_tier if max_access_tier in ACCESS_TIERS else 'internal')
    all_process = [n for n in index_workspace(ws)
                   if n['has_frontmatter'] and n['type'] == 'process']
    nodes = [n for n in all_process if _tier_rank(n['access_tier']) <= ceiling]
    withheld = len(all_process) - len(nodes)
    rows: list[dict[str, Any]] = []
    for n in nodes:
        level = str(n['fields'].get('ai-level') or n['fields'].get('ai_level') or '').lower()
        if level and level not in AUTOMATION_LEVELS:
            continue
        value = n['fields'].get('value')
        pain = n['fields'].get('pain')
        value = float(value) if isinstance(value, (int, float)) and not isinstance(value, bool) else 0.0
        pain = float(pain) if isinstance(pain, (int, float)) and not isinstance(pain, bool) else 0.0
        rows.append({
            'path': n['path'], 'name': n['name'],
            'owner': n['fields'].get('owner', ''),
            'ai_level': level or 'unset',
            'value': value, 'pain': pain,
            'score': round(value + pain, 2),
            # Say WHY it ranked, so a ranking can be argued with.
            'why': f'value {value:g} + pain {pain:g}'
                   + (f', currently {level.upper()}' if level else ', ai-level unset'),
        })
    rows.sort(key=lambda r: (-r['value'], -r['pain'], r['name']))
    return {'candidates': rows[:max(1, min(limit, 200))], 'considered': len(nodes),
            'withheld_by_access_tier': withheld}


def dashboard(ws: Path) -> dict[str, Any]:
    """Everything a live tracker needs, computed rather than described."""
    nodes = index_workspace(ws)
    typed = [n for n in nodes if n['has_frontmatter']]
    by_type: dict[str, int] = {}
    by_tier: dict[str, int] = {}
    for n in typed:
        by_type[n['type'] or 'untyped'] = by_type.get(n['type'] or 'untyped', 0) + 1
        by_tier[n['access_tier']] = by_tier.get(n['access_tier'], 0) + 1
    return {
        'files': len(nodes),
        'typed': len(typed),
        'untyped': len(nodes) - len(typed),
        'by_type': dict(sorted(by_type.items(), key=lambda kv: -kv[1])),
        'by_access_tier': by_tier,
        'automation': automation_candidates(ws, limit=10),
    }


def render_tracker(ws: Path) -> str:
    """Write dashboards/00-tracker.md with REAL results, not a query description.

    The shipped tracker said "Sort process nodes by value desc, then pain desc"
    and stopped there. A dashboard that describes its own query without running
    it looks like a working feature and is not one.
    """
    data = dashboard(ws)
    lines = [
        '# Tracker',
        '',
        '**GENERATED — do not hand-edit.** Live queries over node frontmatter.',
        '',
        f'{data["files"]} files, {data["typed"]} typed, {data["untyped"]} untyped.',
        '',
        '## What to automate next',
        '',
    ]
    cands = data['automation']['candidates']
    if cands:
        lines += ['| Process | Owner | Value | Pain | Why |',
                  '|---------|-------|-------|------|-----|']
        lines += [f'| `{c["path"]}` | {c["owner"] or "—"} | {c["value"]:g} | '
                  f'{c["pain"]:g} | {c["why"]} |' for c in cands]
    else:
        # Say which of the two reasons applies. "No results" that could mean
        # either "nothing qualifies" or "you have not labelled anything" is not
        # an answer.
        lines.append(
            'No process nodes carry `value`/`pain` scores yet. Add them to a node\'s '
            'frontmatter and rebuild this tracker.'
            if data['automation']['considered'] == 0
            else 'Every process node is already at ai-level L2 or above.')
    lines += ['', '## By type', '', '| Type | Count |', '|------|-------|']
    lines += [f'| {t} | {c} |' for t, c in data['by_type'].items()] or ['| — | 0 |']

    body = '\n'.join(lines) + '\n'
    (ws / 'dashboards').mkdir(parents=True, exist_ok=True)
    (ws / 'dashboards' / '00-tracker.md').write_text(body, encoding='utf-8')
    return body
