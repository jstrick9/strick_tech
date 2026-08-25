"""ICM Restructure — audit an existing folder and propose an ICM migration.

Implements Restructure mode and the System map form from `icm-architect`
(Van Clief), the counterpart to Build mode: rather than scaffolding a new
workspace, this reads a tree that already exists, works out the shape hiding
inside it, and proposes how to make it walkable.

    "Point it at a folder, repo, or vault you already have. It reads every
     file, sorts each one by role, shows you a migration map, waits for your
     yes, then moves and checks the result."

THE FIVE ROLES (canon, Restructure mode step 3)

    catalog   identity/routing            -> feeds CLAUDE.md / index files
    contract  describes how a step works  -> becomes a CONTEXT.md
    factory   stable reference material   -> _shared/ / references/
    product   run-specific artifacts      -> stage output/ or record folders
    dead      stale/duplicated/superseded -> _archive/, NEVER silently deleted

THE THREE UNIVERSES (System map form)

    live      in force; implement and cite against these
    leftover  still present, no longer the main path
    ghost     named or filed but not wired (stubs, docs for absent code)

Ghost classification matters more than it looks. The named failure mode of the
form is "mapping aspiration as live" — a later agent reads a doc describing a
function that does not exist and implements against it. Marking it ghost is the
difference between a map and a fiction.

WHY MIGRATION IS A SEPARATE, GATED CALL

Step 4 of the canon is "Propose before moving... This is a human gate in a
method built on human gates — honor it." So `inventory()` and `plan()` are
pure reads that never touch the tree, and `apply_plan()` refuses to run without
a plan_id produced by a prior plan() call and an explicit approval flag. A
"restructure" that reorganises someone's repo on a guess is not a feature.

Nothing is ever deleted. Dead files are proposed into `_archive/`, which is the
canon's explicit instruction and also the only safe reading of "dead" when the
classifier is a heuristic rather than an oracle.
"""

from __future__ import annotations

import hashlib
import json
import re
import shutil
import time
from pathlib import Path
from typing import Any

from backend.config import get_data_dir

from .safe_paths import safe_path

ROOT = get_data_dir()
PLANS_DIR = ROOT / 'memory' / 'icm-plans'

# Caps. A restructure scan walks a whole repo, so it must be bounded or a large
# tree turns a read-only audit into an outage.
MAX_FILES = 4000
MAX_DEPTH = 12
SNIFF_BYTES = 4096

# Directories never worth auditing: generated, vendored, or the VCS itself.
# Walking node_modules would blow the file cap before reaching real source.
SKIP_DIRS = frozenset({
    '.git', '.hg', '.svn', 'node_modules', '__pycache__', '.venv', 'venv',
    'dist', 'build', 'out', 'target', 'coverage', '.next', '.nuxt', '.cache',
    '.pytest_cache', '.mypy_cache', '.ruff_cache', '.tox', 'site-packages',
    '.idea', '.vscode', '.terraform', 'vendor', '.gradle', 'Pods',
    # Our own migration output. Auditing it would classify a proposal as if it
    # were part of the subject tree, and the next plan would propose moving
    # the previous plan's copies.
    '_icm-restructured',
})

# Entry/routing files: the catalog. Matched on stem so CLAUDE.md, AGENTS.md,
# CONTEXT.md and friends are recognised whatever their case.
CATALOG_STEMS = frozenset({
    'claude', 'agents', 'readme', 'index', 'start-here', '00-start-here',
    'routing', 'file-map', 'identity', 'map', 'toc',
})
CONTRACT_STEMS = frozenset({'context', 'conventions', 'schema', 'skill', 'spec'})

# Stable reference material -- the factory. Configure once, reuse every run.
FACTORY_DIR_HINTS = frozenset({
    'references', 'reference', '_shared', 'shared', '_config', 'config',
    'docs', 'doc', 'documentation', '_templates', 'templates', '_meta',
    'meta', 'brand', 'guidelines', 'styleguide', 'rules', 'skills',
})
# Per-run artifacts -- the product.
PRODUCT_DIR_HINTS = frozenset({
    'output', 'outputs', 'drafts', 'draft', 'results', 'runs', 'exports',
    'artifacts', 'generated', 'tmp', 'temp', 'logs', 'records', 'inbox',
})
DEAD_DIR_HINTS = frozenset({'_archive', 'archive', 'old', 'deprecated', 'backup', 'bak'})

DEAD_NAME_RE = re.compile(
    r'(^|[-_. ])(old|copy|backup|bak|deprecated|obsolete|unused|tmp|temp|draft\d+|v\d+_old)([-_. ]|$)'
    r'|\.(bak|old|orig|swp|tmp)$'
    r'|( \(\d+\))\.',
    re.I,
)

# A file nothing links to and nothing imports, that has not changed in a long
# time, is the strongest signal available for "leftover" without executing it.
STALE_DAYS = 365

# Files whose whole job is to be empty. Calling these ghosts is a false
# positive: .gitkeep exists precisely so an otherwise-empty directory survives
# in git, so it is doing its job, not failing to.
STRUCTURAL_EMPTY = frozenset({
    '.gitkeep', '.gitignore', '.keep', '.placeholder', '__init__.py',
})


def _plan_path(plan_id: str) -> Path | None:
    if not re.fullmatch(r'[a-f0-9]{16}', str(plan_id or '')):
        return None
    return PLANS_DIR / f'{plan_id}.json'


def _rel(path: Path, root: Path) -> str:
    try:
        return path.relative_to(root).as_posix()
    except ValueError:
        return path.name


def _is_texty(path: Path) -> bool:
    """Cheap binary sniff: a NUL byte in the first block means not text."""
    try:
        with path.open('rb') as fh:
            return b'\x00' not in fh.read(SNIFF_BYTES)
    except OSError:
        return False


# ── inventory ─────────────────────────────────────────────────────────────────
def inventory(root: Path) -> dict[str, Any]:
    """Walk the tree and describe it. Reads only; never writes or moves.

    Canon step 1: "Inventory before touching. List the tree. For each area
    note: what it is, when last touched, what refers to it. Never delete or
    move in this pass."
    """
    files: list[dict[str, Any]] = []
    truncated = False
    now = time.time()

    def walk(d: Path, depth: int) -> None:
        nonlocal truncated
        if truncated or depth > MAX_DEPTH:
            return
        try:
            entries = sorted(d.iterdir(), key=lambda p: (p.is_file(), p.name.lower()))
        except OSError:
            return
        for p in entries:
            if len(files) >= MAX_FILES:
                truncated = True
                return
            if p.is_dir():
                if p.name in SKIP_DIRS or p.is_symlink():
                    continue
                walk(p, depth + 1)
            elif p.is_file() and not p.is_symlink():
                try:
                    st = p.stat()
                except OSError:
                    continue
                rel = _rel(p, root)
                files.append({
                    'path': rel,
                    'name': p.name,
                    'ext': p.suffix.lower(),
                    'size': st.st_size,
                    'age_days': max(0, int((now - st.st_mtime) / 86400)),
                    'depth': rel.count('/'),
                    'text': _is_texty(p),
                })

    walk(root, 0)

    # Reference graph: who mentions whom. A file nobody references anywhere is
    # a candidate for leftover/ghost -- this is the cheapest honest signal
    # short of executing the code.
    names = {f['path'].rsplit('/', 1)[-1] for f in files}
    referenced: set[str] = set()
    for f in files:
        if not f['text'] or f['size'] > 400_000:
            continue
        try:
            body = (root / f['path']).read_text(encoding='utf-8', errors='ignore')
        except OSError:
            continue
        for name in names:
            if name != f['name'] and name in body:
                referenced.add(name)

    for f in files:
        f['referenced'] = f['name'] in referenced

    return {
        'root': str(root),
        'file_count': len(files),
        'truncated': truncated,
        'files': files,
    }


# ── classification ────────────────────────────────────────────────────────────
def classify(entry: dict[str, Any]) -> dict[str, Any]:
    """Assign one of the five roles and one of the three universes, with a why.

    Every classification carries its reason. A migration map a human is asked
    to approve is only reviewable if each line says why it was decided that
    way -- an unexplained "dead" is not something anyone can sensibly approve.
    """
    path = entry['path']
    parts = path.lower().split('/')
    dirs = set(parts[:-1])
    stem = Path(entry['name']).stem.lower()
    reasons: list[str] = []

    # ── role ──
    role = 'product'
    if dirs & DEAD_DIR_HINTS:
        role, why = 'dead', f'lives under {sorted(dirs & DEAD_DIR_HINTS)[0]}/'
    elif DEAD_NAME_RE.search(entry['name']):
        role, why = 'dead', 'filename marks it as a copy/backup/old version'
    elif stem in CATALOG_STEMS:
        role, why = 'catalog', f'{entry["name"]} is an entry/routing file'
    elif stem in CONTRACT_STEMS:
        role, why = 'contract', f'{entry["name"]} declares how a step works'
    elif dirs & PRODUCT_DIR_HINTS:
        role, why = 'product', f'lives under {sorted(dirs & PRODUCT_DIR_HINTS)[0]}/'
    elif dirs & FACTORY_DIR_HINTS:
        role, why = 'factory', f'lives under {sorted(dirs & FACTORY_DIR_HINTS)[0]}/'
    elif entry['ext'] in ('.py', '.js', '.ts', '.tsx', '.jsx', '.go', '.rs', '.java', '.rb'):
        role, why = 'factory', 'source code: stable across runs'
    elif entry['ext'] in ('.md', '.rst', '.txt') and entry['depth'] == 0:
        role, why = 'catalog', 'top-level prose usually orients the reader'
    elif entry['ext'] in ('.yaml', '.yml', '.toml', '.ini', '.cfg'):
        role, why = 'factory', 'configuration is factory, not product'
    else:
        why = 'no catalog/contract/factory signal; treated as run output'
    reasons.append(why)

    # ── universe ──
    # Ghost is asserted narrowly and only with a stated basis. Over-calling
    # ghost is worse than under-calling it: the map is supposed to stop people
    # implementing against fiction, not invent new fiction of its own.
    if role == 'dead':
        universe = 'leftover'
        reasons.append('archived/superseded material is not the main path')
    elif entry['size'] == 0 and entry['name'].lower() not in STRUCTURAL_EMPTY:
        universe = 'ghost'
        reasons.append('empty file: named but carries nothing')
    elif not entry['referenced'] and entry['age_days'] > STALE_DAYS:
        universe = 'leftover'
        reasons.append(f'nothing references it and untouched for {entry["age_days"]}d')
    else:
        universe = 'live'
        reasons.append('referenced or recently touched')

    return {
        **entry,
        'role': role,
        'universe': universe,
        'why': '; '.join(reasons),
    }


def _target_for(item: dict[str, Any]) -> str:
    """Where this file would live in the restructured tree."""
    name = item['name']
    return {
        'catalog': name,
        'contract': f'stages/{Path(item["path"]).parent.name or "01-stage"}/CONTEXT.md',
        'factory': f'_shared/{name}',
        'product': f'output/{name}',
        'dead': f'_archive/{item["path"]}',
    }[item['role']]


# ── the plan ──────────────────────────────────────────────────────────────────
def plan(root: Path, label: str = '') -> dict[str, Any]:
    """Inventory, classify, and write a migration map awaiting approval.

    The plan is persisted so approval refers to something specific and
    immutable. Approving "the plan" that was recomputed after the tree changed
    underneath would be approving something the human never actually read.
    """
    inv = inventory(root)
    items = [classify(f) for f in inv['files']]

    by_role: dict[str, int] = {}
    by_universe: dict[str, int] = {}
    for it in items:
        by_role[it['role']] = by_role.get(it['role'], 0) + 1
        by_universe[it['universe']] = by_universe.get(it['universe'], 0) + 1

    moves = [
        {'from': it['path'], 'to': _target_for(it), 'role': it['role'],
         'universe': it['universe'], 'why': it['why']}
        for it in items
        if _target_for(it) != it['path']
    ]

    payload = {
        'root': str(root),
        'label': label or Path(root).name,
        'created_at': time.time(),
        'file_count': inv['file_count'],
        'truncated': inv['truncated'],
        'by_role': by_role,
        'by_universe': by_universe,
        'moves': moves,
        'items': items,
        'applied': False,
        'applied_at': 0.0,
    }
    plan_id = hashlib.sha256(
        f'{root}:{payload["created_at"]}:{inv["file_count"]}'.encode()
    ).hexdigest()[:16]
    payload['plan_id'] = plan_id

    PLANS_DIR.mkdir(parents=True, exist_ok=True)
    dest = _plan_path(plan_id)
    if dest is None:  # pragma: no cover - plan_id is a sha256 slice
        raise ValueError('generated plan id failed validation')
    dest.write_text(json.dumps(payload, indent=2), encoding='utf-8')
    return payload


def load_plan(plan_id: str) -> dict[str, Any] | None:
    p = _plan_path(plan_id)
    if p is None or not p.is_file():
        return None
    try:
        return json.loads(p.read_text(encoding='utf-8'))
    except (OSError, ValueError):
        return None


def list_plans(limit: int = 50) -> list[dict[str, Any]]:
    if not PLANS_DIR.is_dir():
        return []
    out: list[dict[str, Any]] = []
    for p in sorted(PLANS_DIR.glob('*.json'), key=lambda x: x.stat().st_mtime, reverse=True)[:limit]:
        try:
            d = json.loads(p.read_text(encoding='utf-8'))
        except (OSError, ValueError):
            continue
        out.append({k: d.get(k) for k in
                    ('plan_id', 'label', 'root', 'created_at', 'file_count',
                     'by_role', 'by_universe', 'applied', 'applied_at')})
    return out


def apply_plan(plan_id: str, approved: bool = False) -> dict[str, Any]:
    """Execute a previously proposed migration. Refuses without explicit approval.

    Copies rather than moves, into `<root>/_icm-restructured/`. The canon says
    propose-then-migrate, but it does not say destroy the original, and a
    heuristic classifier is exactly the wrong thing to hand destructive power
    to. The user can diff the proposal against the source and delete the
    original themselves once satisfied.
    """
    # Validate the caller-supplied id BEFORE building any write path. load_plan
    # validates for its own read, but apply_plan writes the updated plan back,
    # and an earlier draft built that write path with a raw f-string --
    # bypassing the check entirely. The revert proof caught this: removing the
    # validator broke nothing any test could see, because no test exercised the
    # write path with a hostile id.
    store = _plan_path(plan_id)
    if store is None:
        return {'ok': False, 'error': f'invalid plan id {plan_id!r}'}
    p = load_plan(plan_id)
    if p is None:
        return {'ok': False, 'error': f'plan {plan_id!r} not found'}
    if not approved:
        return {'ok': False, 'error': 'refused: apply requires explicit approval of this plan',
                'plan_id': plan_id, 'moves': len(p.get('moves', []))}
    if p.get('applied'):
        return {'ok': False, 'error': 'plan already applied', 'plan_id': plan_id}

    root = Path(p['root'])
    if not root.is_dir():
        return {'ok': False, 'error': 'source tree no longer exists'}

    dest_root = root / '_icm-restructured'
    dest_root.mkdir(parents=True, exist_ok=True)

    copied, skipped = 0, []
    for mv in p.get('moves', []):
        src = safe_path(mv['from'], base=root, must_exist=True)
        dst = safe_path(mv['to'], base=dest_root)
        if src is None or dst is None:
            # A path that will not resolve inside its base is refused rather
            # than clamped: this loop writes files, so an escape here is an
            # arbitrary filesystem write.
            skipped.append({'from': mv['from'], 'reason': 'path escaped its base'})
            continue
        try:
            dst.parent.mkdir(parents=True, exist_ok=True)
            shutil.copy2(src, dst)
            copied += 1
        except OSError as exc:
            skipped.append({'from': mv['from'], 'reason': str(exc)})

    p['applied'] = True
    p['applied_at'] = time.time()
    p['copied'] = copied
    p['skipped'] = skipped
    store.write_text(json.dumps(p, indent=2), encoding='utf-8')

    return {'ok': True, 'plan_id': plan_id, 'copied': copied,
            'skipped': skipped, 'destination': str(dest_root)}



MAX_HITS = 6
# Reading every file of a large cluster to build one card is not worth it; the
# first slice is representative enough for a first-order answer.
HITS_SAMPLE = 60


def _first_order_hits(root: Path, name: str, group: list[dict[str, Any]],
                      clusters: set[str]) -> list[str]:
    """Which other clusters this one actually references.

    Reads FILE CONTENTS. An earlier draft tested `other in g['path']`, i.e. it
    searched the filename of each file in the cluster for the name of another
    cluster -- which is almost never true, so every card reported an empty
    waterfall. "If you change this, what else moves" was structurally incapable
    of answering, and no test noticed because the fixture tree was too small
    for the cap to bite either way.
    """
    hits: set[str] = set()
    for g in group[:HITS_SAMPLE]:
        if not g['text'] or g['size'] > 400_000:
            continue
        try:
            body = (root / g['path']).read_text(encoding='utf-8', errors='ignore')
        except OSError:
            continue
        for other in clusters:
            if other != name and other != '(root)' and other in body:
                hits.add(other)
        if len(hits) >= MAX_HITS * 3:
            break
    return sorted(hits)[:MAX_HITS]

# ── the system map ────────────────────────────────────────────────────────────
def system_map(root: Path, limit: int = 40) -> dict[str, Any]:
    """Index cards for a tree a later agent must edit.

    "You do not get a 40-page audit report. You get index-card pages." Each
    card names the noun, its universe, what it is connected to, and -- the
    load-bearing part -- what changing it hits and what it deliberately does
    not.
    """
    inv = inventory(root)
    items = [classify(f) for f in inv['files']]

    # Cluster by top-level directory: how an editor actually asks ("what's in
    # backend?"), not by the classifier's roles.
    clusters: dict[str, list[dict[str, Any]]] = {}
    for it in items:
        top = it['path'].split('/')[0] if '/' in it['path'] else '(root)'
        clusters.setdefault(top, []).append(it)

    cards = []
    for name, group in sorted(clusters.items(), key=lambda kv: -len(kv[1]))[:limit]:
        live = [g for g in group if g['universe'] == 'live']
        ghosts = [g for g in group if g['universe'] == 'ghost']
        leftovers = [g for g in group if g['universe'] == 'leftover']
        roles: dict[str, int] = {}
        for g in group:
            roles[g['role']] = roles.get(g['role'], 0) + 1
        cards.append({
            'noun': name,
            'files': len(group),
            'universe': 'live' if live else ('leftover' if leftovers else 'ghost'),
            'roles': roles,
            'live': len(live),
            'ghost': len(ghosts),
            'leftover': len(leftovers),
            # First-order only, per the form: naming everything downstream is
            # how change-impact indexes become wrong and expensive.
            'hits': _first_order_hits(root, name, group, set(clusters)),
            'examples': [g['path'] for g in group[:5]],
        })

    return {
        'root': str(root),
        'file_count': inv['file_count'],
        'truncated': inv['truncated'],
        'cards': cards,
    }
