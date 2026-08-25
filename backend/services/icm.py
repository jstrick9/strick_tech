"""Interpretable Context Methodology (ICM) — workspace runtime.

Implements the Model Workspace Protocol described in:

    Interpretable Context Methodology: Folder Structure as Agentic Architecture
    Jake Van Clief & David McDermott, arXiv:2603.16021 (MIT licensed)

The thesis: if the prompts and context for each stage of a workflow already
exist as files in a well-organised folder hierarchy, you do not need multiple
agents or a coordination framework. You need one agent that reads the right
files at the right moment. The filesystem does what a framework would do in
code:

    stage sequencing   -> folder numbering
    context scoping    -> folder hierarchy
    state management   -> files on disk
    stage coordination -> one folder's output/ is the next stage's input
    observability      -> open the folder and read it

WHY A SERVICE AND NOT JUST A ROUTER
The context assembler is called from chat.py to build the system prompt, so it
has to be importable without the HTTP layer. Keeping the rules here also means
the router stays a thin transport shell that is easy to test.

THE FIVE CONTEXT LAYERS

    L0  IDENTITY.md    identity + broad goals            (always loads)
    L1  CONTEXT.md     task routing: which stage handles what
    L2  stages/NN-x/CONTEXT.md   the STAGE CONTRACT      (the control point)
    L3  references/, _config/, shared/   stable knowledge (persists across runs)
    L4  stages/NN-x/output/      working artifacts        (changes every run)

The measured payoff from the paper: a stage assembles 2,000-8,000 tokens where
a monolithic prompt carrying every stage's instructions, every reference and
every prior output reaches 30,000-50,000 -- most of it irrelevant to the task
at hand, in the range where Liu et al. show retrieval accuracy degrading.

THE FAILURE MODE THIS MODULE EXISTS TO PREVENT
From the author's own notes on ICM in practice:

    "When you add more and more folders agents begin to skip information.
     Guidelines are missed, rules are overlooked... the model scans
     economically and thinks it knows enough. The solution is again simple,
     the agent has to actually start in the right folder."

In a team, "just cd to the correct directory" is exactly the kind of invisible,
error-prone step that breaks repeatability. So this runtime never asks a caller
to remember where to start: `resolve_entry()` computes the correct stage from
workspace state, and `assemble_context()` refuses to run without one.
"""

from __future__ import annotations

import json
import re
import time
from pathlib import Path
from typing import Any

from backend.config import get_data_dir

from .safe_paths import safe_path

ROOT = get_data_dir()
WORKSPACES_DIR = ROOT / 'memory' / 'icm'
WORKSPACES_DIR.mkdir(parents=True, exist_ok=True)

# Same shape as hierarchy.py's project ids: no separators or dots can reach a
# filesystem call, with safe_path() as the second layer.
WORKSPACE_ID_RE = re.compile(r'^[a-z0-9][a-z0-9_-]{0,63}$')
# "01-research", "02_script". The number carries execution order.
STAGE_DIR_RE = re.compile(r'^(\d{1,3})[-_](.+)$')

# Convention limits from the paper's _core/CONVENTIONS.md. Exceeding them is a
# warning, not an error: they are guidance about what stays readable, and a
# workspace that breaks them still runs.
MAX_CONTEXT_LINES = 80
MAX_REFERENCE_LINES = 200

# Layer names, used in assembled output so a caller can see what it received.
LAYER_IDENTITY = 'L0-identity'
LAYER_ROUTING = 'L1-routing'
LAYER_CONTRACT = 'L2-contract'
LAYER_REFERENCE = 'L3-reference'
LAYER_WORKING = 'L4-working'


# ── paths ─────────────────────────────────────────────────────────────────────
def workspace_dir(workspace_id: str) -> Path | None:
    """Resolve a workspace directory, or None if the id escapes the base."""
    if not workspace_id or not WORKSPACE_ID_RE.match(str(workspace_id)):
        return None
    return safe_path(workspace_id, base=WORKSPACES_DIR)


def _read(path: Path, limit: int = 200_000) -> str:
    try:
        return path.read_text(encoding='utf-8', errors='ignore')[:limit]
    except OSError:
        return ''


def _section(text: str, section: str) -> str:
    """Extract one markdown section by heading.

    Selective section routing is the convention that keeps context small: a
    stage contract names the section it needs, not the whole file. Without it
    an agent loads an entire style guide to read three lines of tone guidance.
    Matching is case-insensitive and ignores heading depth.
    """
    if not section or section.strip().lower() in ('full file', 'full', '*', 'all'):
        return text
    want = section.strip().lower().lstrip('#').strip()
    out: list[str] = []
    depth = None
    for line in text.splitlines():
        m = re.match(r'^(#{1,6})\s+(.*)$', line)
        if m:
            level, title = len(m.group(1)), m.group(2).strip().lower()
            if depth is None and title == want:
                depth = level
                out.append(line)
                continue
            # A heading at the same or shallower depth ends the section.
            if depth is not None and level <= depth:
                break
        if depth is not None:
            out.append(line)
    return '\n'.join(out).strip()


# ── stage discovery ───────────────────────────────────────────────────────────
def list_stages(ws: Path) -> list[dict[str, Any]]:
    """Discover stages from folder names. The numbering IS the sequence."""
    stages_root = ws / 'stages'
    if not stages_root.is_dir():
        return []
    found: list[dict[str, Any]] = []
    for d in stages_root.iterdir():
        if not d.is_dir() or d.name.startswith('.'):
            continue
        m = STAGE_DIR_RE.match(d.name)
        if not m:
            # Unnumbered folders are not stages. Silently skipping them would
            # be the "agent skips information" failure in miniature, so they
            # are surfaced by validate() instead.
            continue
        outputs = []
        odir = d / 'output'
        if odir.is_dir():
            outputs = sorted(
                f.name for f in odir.iterdir()
                if f.is_file() and not f.name.startswith('.')
            )
        found.append({
            'dir': d.name,
            'order': int(m.group(1)),
            'slug': m.group(2),
            'has_contract': (d / 'CONTEXT.md').is_file(),
            'outputs': outputs,
            'complete': bool(outputs),
        })
    found.sort(key=lambda s: (s['order'], s['dir']))
    return found


def parse_contract(text: str) -> dict[str, Any]:
    """Parse a stage contract's Inputs / Process / Outputs.

    The Inputs table is the control point of the whole methodology: it names
    which files, and which SECTIONS of them, the agent should load. Anything
    the table does not name is not loaded.
    """
    inputs: list[dict[str, str]] = []
    for row in re.findall(r'^\|(.+)\|\s*$', _section(text, 'Inputs'), re.M):
        cells = [c.strip() for c in row.split('|')]
        # Skip the header row and the |---|---| separator.
        if len(cells) < 2 or not cells[0] or set(cells[0]) <= set('-: '):
            continue
        if cells[0].lower() in ('source', 'artifact'):
            continue
        inputs.append({
            'source': cells[0],
            'path': cells[1] if len(cells) > 1 else '',
            'section': cells[2] if len(cells) > 2 else '',
            'why': cells[3] if len(cells) > 3 else '',
        })
    outputs: list[dict[str, str]] = []
    for row in re.findall(r'^\|(.+)\|\s*$', _section(text, 'Outputs'), re.M):
        cells = [c.strip() for c in row.split('|')]
        if len(cells) < 2 or not cells[0] or set(cells[0]) <= set('-: '):
            continue
        if cells[0].lower() in ('artifact', 'source'):
            continue
        outputs.append({
            'artifact': cells[0],
            'location': cells[1] if len(cells) > 1 else '',
            'format': cells[2] if len(cells) > 2 else '',
        })
    return {
        'inputs': inputs,
        'process': _section(text, 'Process'),
        'outputs': outputs,
    }


# ── entry resolution: the fix for the known failure mode ──────────────────────
def resolve_entry(ws: Path, requested: str = '') -> tuple[str, str]:
    """Decide which stage the agent starts in. Returns (stage_dir, reason).

    The paper's practical failure: start in a central place and the layered
    context never loads; start in the right place and the agent is instantly
    grounded. Leaving that to "cd to the right directory" is the invisible
    manual step that breaks repeatability, so it is computed here.

    Rule: an explicit request wins; otherwise the first stage with no output.
    """
    stages = list_stages(ws)
    if not stages:
        return '', 'no stages defined'
    if requested:
        for s in stages:
            if s['dir'] == requested or s['slug'] == requested:
                return s['dir'], 'explicitly requested'
        return '', f'stage {requested!r} not found'
    for s in stages:
        if not s['complete']:
            return s['dir'], 'first stage with no output'
    last = stages[-1]['dir']
    return last, 'all stages complete; resuming at the last'


# ── context assembly ──────────────────────────────────────────────────────────
def assemble_context(ws: Path, stage_dir: str) -> dict[str, Any]:
    """Build the layered context for one stage.

    Loads L0 and L1 always, then the stage contract (L2), then exactly the
    L3/L4 material the contract's Inputs table names -- and nothing else. That
    restraint is the entire point: it is what keeps a stage at 2-8k tokens
    instead of the 30-50k a monolithic prompt reaches.
    """
    parts: list[dict[str, Any]] = []
    missing: list[str] = []

    def add(layer: str, label: str, text: str) -> None:
        if text and text.strip():
            parts.append({'layer': layer, 'label': label, 'text': text.strip()})

    # L0 — identity. IDENTITY.md is the ICM name; CLAUDE.md and AGENTS.md are
    # the conventions the surrounding tooling already uses, so accept all three.
    for name in ('IDENTITY.md', 'CLAUDE.md', 'AGENTS.md'):
        if (ws / name).is_file():
            add(LAYER_IDENTITY, name, _read(ws / name))
            break

    # L1 — routing
    if (ws / 'CONTEXT.md').is_file():
        add(LAYER_ROUTING, 'CONTEXT.md', _read(ws / 'CONTEXT.md'))

    sdir = ws / 'stages' / stage_dir
    contract: dict[str, Any] = {'inputs': [], 'process': '', 'outputs': []}

    if stage_dir and sdir.is_dir():
        cpath = sdir / 'CONTEXT.md'
        if cpath.is_file():
            ctext = _read(cpath)
            contract = parse_contract(ctext)
            add(LAYER_CONTRACT, f'stages/{stage_dir}/CONTEXT.md', ctext)
        else:
            missing.append(f'stages/{stage_dir}/CONTEXT.md')

        # L3/L4 — only what the Inputs table names.
        for inp in contract['inputs']:
            rel = inp.get('path', '').strip().strip('`')
            if not rel:
                continue
            target = (sdir / rel).resolve()
            # Never read outside the workspace: this text goes into a system
            # prompt, so traversal here is an arbitrary-file-read fed to a model.
            try:
                target.relative_to(ws.resolve())
            except ValueError:
                missing.append(f'{rel} (outside workspace, refused)')
                continue
            if target.is_dir():
                files = sorted(
                    f for f in target.iterdir()
                    if f.is_file() and not f.name.startswith('.')
                )
                if not files:
                    missing.append(f'{rel} (empty)')
                for f in files:
                    layer = LAYER_WORKING if 'output' in f.parts else LAYER_REFERENCE
                    add(layer, str(f.relative_to(ws)), _read(f))
            elif target.is_file():
                layer = LAYER_WORKING if 'output' in target.parts else LAYER_REFERENCE
                add(layer, str(target.relative_to(ws)), _section(_read(target), inp.get('section', '')))
            else:
                missing.append(rel)

    body = '\n\n'.join(
        f'=== {p["layer"].upper()}: {p["label"]} ===\n{p["text"]}' for p in parts
    )
    compiled = f'<icm-workspace stage="{stage_dir}">\n{body}\n</icm-workspace>' if body else ''

    return {
        'stage': stage_dir,
        'compiled_context': compiled,
        'parts': [{'layer': p['layer'], 'label': p['label'], 'chars': len(p['text'])} for p in parts],
        'contract': contract,
        # Report what the contract asked for and did not get, rather than
        # quietly assembling a short context and letting the agent proceed as
        # though it were complete.
        'missing_inputs': missing,
        'char_count': len(compiled),
        'estimated_tokens': len(compiled) // 4,
    }


# ── validation: the walk test ─────────────────────────────────────────────────
def validate(ws: Path) -> dict[str, Any]:
    """Check a workspace against the ICM conventions.

    The paper's acceptance criterion is the walk test: an agent with no memory
    opens the root, finds its way, acts, and reports status from the files
    alone. These checks are that test, mechanised.
    """
    errors: list[str] = []
    warnings: list[str] = []

    has_identity = any((ws / n).is_file() for n in ('IDENTITY.md', 'CLAUDE.md', 'AGENTS.md'))
    if not has_identity:
        errors.append('No L0 identity file (IDENTITY.md). An agent landing here cannot tell where it is.')
    if not (ws / 'CONTEXT.md').is_file():
        errors.append('No L1 CONTEXT.md at the root. Nothing routes the agent to a stage.')

    # Which form this is decides what the walk test should require. A record
    # library has records, a knowledge bundle has layers -- neither has stages,
    # and reporting that as an error would fail correctly-built workspaces.
    # A validator that fails correct work teaches people to ignore it.
    form = read_meta(ws).get('form') or 'pipeline'
    if form != 'pipeline':
        from .icm_forms import validate_form

        sub = validate_form(ws, form)
        errors.extend(sub['errors'])
        warnings.extend(sub['warnings'])

    stages = list_stages(ws)
    if not stages and form == 'pipeline':
        errors.append('No numbered stages under stages/. The numbering is what encodes execution order.')

    # Unnumbered folders under stages/ are invisible to the runtime; that is
    # exactly the "agent skips information" failure, so name them.
    sroot = ws / 'stages'
    if sroot.is_dir():
        for d in sroot.iterdir():
            if d.is_dir() and not d.name.startswith('.') and not STAGE_DIR_RE.match(d.name):
                warnings.append(f'stages/{d.name} is not numbered, so it is not a stage and will never load.')

    seen: dict[int, str] = {}
    for s in stages:
        if s['order'] in seen:
            errors.append(f'Duplicate stage number {s["order"]:02d}: {seen[s["order"]]} and {s["dir"]}.')
        seen[s['order']] = s['dir']

        sdir = ws / 'stages' / s['dir']
        cpath = sdir / 'CONTEXT.md'
        if not cpath.is_file():
            errors.append(f'stages/{s["dir"]} has no CONTEXT.md, so it has no contract.')
            continue

        text = _read(cpath)
        lines = text.count('\n') + 1
        if lines > MAX_CONTEXT_LINES:
            warnings.append(f'stages/{s["dir"]}/CONTEXT.md is {lines} lines (convention: under {MAX_CONTEXT_LINES}).')
        c = parse_contract(text)
        if not c['inputs']:
            warnings.append(f'stages/{s["dir"]} declares no Inputs, so nothing scopes what it loads.')
        if not c['process'].strip():
            warnings.append(f'stages/{s["dir"]} declares no Process.')
        if not c['outputs']:
            warnings.append(f'stages/{s["dir"]} declares no Outputs, so the next stage has no defined handoff.')
        if not (sdir / 'output').is_dir():
            warnings.append(f'stages/{s["dir"]}/output/ is missing; it is the L4 handoff point.')

        for ref in (sdir / 'references').glob('*.md') if (sdir / 'references').is_dir() else []:
            n = _read(ref).count('\n') + 1
            if n > MAX_REFERENCE_LINES:
                warnings.append(f'{ref.relative_to(ws)} is {n} lines (convention: under {MAX_REFERENCE_LINES}).')

        # One-way references: a stage must not read from a LATER stage. That is
        # a cycle, and it breaks the pipe-and-filter guarantee the ordering
        # exists to provide.
        for inp in c['inputs']:
            m = re.search(r'\.\./(\d{1,3})[-_]', inp.get('path', ''))
            if m and int(m.group(1)) > s['order']:
                errors.append(
                    f'stages/{s["dir"]} reads from stage {int(m.group(1)):02d}, which runs later. '
                    'References must point backwards only.'
                )

    entry, reason = resolve_entry(ws)
    if not entry and stages:
        warnings.append('Could not resolve an entry stage.')

    return {
        'ok': not errors,
        'errors': errors,
        'warnings': warnings,
        'stage_count': len(stages),
        'entry_stage': entry,
        'entry_reason': reason,
        'form': form,
        'walk_test': {
            'can_orient': has_identity and (ws / 'CONTEXT.md').is_file(),
            # Non-pipeline forms have no entry STAGE; being walkable for them
            # means the required shelves exist, which validate_form checked.
            'can_find_work': bool(entry) if form == 'pipeline' else not errors,
            'can_report_status': bool(stages) if form == 'pipeline' else not errors,
        },
    }


# ── scaffolding ───────────────────────────────────────────────────────────────
def _slug(text: str, fallback: str = 'stage') -> str:
    s = re.sub(r'[^a-z0-9]+', '-', str(text).lower()).strip('-')
    return s[:40] or fallback


def scaffold(ws: Path, name: str, description: str, stage_names: list[str]) -> dict[str, Any]:
    """Create a workspace: L0, L1, and a numbered stage per name.

    "Configure the factory, not the product" -- the workspace is set up once,
    then every run reuses it with new inputs.
    """
    ws.mkdir(parents=True, exist_ok=True)
    (ws / 'stages').mkdir(exist_ok=True)
    (ws / '_config').mkdir(exist_ok=True)
    (ws / 'shared').mkdir(exist_ok=True)

    stages: list[dict[str, str]] = []
    for i, raw in enumerate(stage_names, start=1):
        slug = _slug(raw, f'stage-{i}')
        dirname = f'{i:02d}-{slug}'
        sdir = ws / 'stages' / dirname
        (sdir / 'references').mkdir(parents=True, exist_ok=True)
        (sdir / 'output').mkdir(parents=True, exist_ok=True)
        (sdir / 'output' / '.gitkeep').write_text('', encoding='utf-8')

        prev = f'../{i - 1:02d}-{_slug(stage_names[i - 2], f"stage-{i-1}")}/output/' if i > 1 else ''
        inputs = (
            f'| Previous stage | {prev} | Full file | Source material |\n'
            if prev else
            '| Run input | (provided at run time) | Full | The task |\n'
        )
        (sdir / 'CONTEXT.md').write_text(
            f'# Stage {i:02d} — {raw}\n\n'
            f'## Inputs\n'
            f'| Source | File/Location | Section/Scope | Why |\n'
            f'|--------|---------------|---------------|-----|\n'
            f'{inputs}'
            f'| Conventions | ../../_config/conventions.md | Full file | House rules |\n\n'
            f'## Process\n'
            f'1. Read the inputs above.\n'
            f'2. Do the work of this stage: {raw}.\n'
            f'3. Save the result to output/.\n\n'
            f'## Outputs\n'
            f'| Artifact | Location | Format |\n'
            f'|----------|----------|--------|\n'
            f'| {raw} result | output/{slug}.md | Markdown |\n',
            encoding='utf-8',
        )
        stages.append({'dir': dirname, 'name': raw})

    (ws / 'IDENTITY.md').write_text(
        f'# {name}\n\n'
        f'{description or "An ICM workspace."}\n\n'
        f'## What this workspace is\n'
        # Name the form explicitly. Every other form's L0 states which form it
        # is, and a cold agent that cannot tell a Pipeline from a record
        # library from the entry file has already failed the walk test.
        f'A **Pipeline** — the production line. Each stage reads its contract, '
        f'does one job, and writes to its own output/ folder. The numbering is '
        f'the order.\n\n'
        f'## How to work here\n'
        f'Open the stage you are assigned, read its CONTEXT.md, load only what '
        f'its Inputs table names, and write only what its Outputs table names.\n',
        encoding='utf-8',
    )

    routing = '\n'.join(f'| {s["dir"]} | {s["name"]} |' for s in stages)
    (ws / 'CONTEXT.md').write_text(
        f'# Routing\n\n'
        f'Which stage handles what. Start at the first stage with no output.\n\n'
        f'| Stage | Handles |\n|-------|---------|\n{routing}\n\n'
        f'## Conventions\n'
        f'- One stage, one job.\n'
        f'- Plain markdown is the interface between stages.\n'
        f'- Every output/ file is an edit surface: review before the next stage.\n'
        f'- References point backwards only.\n',
        encoding='utf-8',
    )

    if not (ws / '_config' / 'ontology.md').is_file():
        from .ontology import STARTER_ONTOLOGY

        (ws / '_config' / 'ontology.md').write_text(STARTER_ONTOLOGY, encoding='utf-8')

    if not (ws / '_config' / 'conventions.md').is_file():
        (ws / '_config' / 'conventions.md').write_text(
            '# Conventions\n\n'
            '- Canonical sources: every fact has one home; other files point at it.\n'
            '- Selective loading: name the section, not the whole file.\n'
            '- Keep CONTEXT.md under 80 lines and reference files under 200.\n',
            encoding='utf-8',
        )

    meta = {
        'workspace_id': ws.name,
        'name': name,
        'description': description,
        'created_at': time.time(),
        'stages': [s['dir'] for s in stages],
    }
    (ws / '.icm.json').write_text(json.dumps(meta, indent=2), encoding='utf-8')
    return meta


def read_meta(ws: Path) -> dict[str, Any]:
    try:
        return json.loads((ws / '.icm.json').read_text(encoding='utf-8'))
    except (OSError, ValueError):
        return {'workspace_id': ws.name, 'name': ws.name, 'stages': []}
