"""The six ICM forms — one skeleton, six jobs.

From Van Clief's icm-architect `references/forms.md`:

    "One skeleton, six jobs. Every form obeys the ten invariants; what changes
     is what the repeating unit is and what the structure optimizes for."

    Ask one question first: WHAT IS THE REPEATING UNIT OF WORK?

        a run (same stages, new deliverable)      -> Pipeline
        several kinds of run, one identity         -> Umbrella
        a record that accumulates                  -> Record library
        the knowledge itself                       -> Knowledge bundle
        an organization                            -> Context map
        a folder later agents must edit            -> System map

WHY THIS MODULE EXISTS

`icm.scaffold()` builds a Pipeline and only a Pipeline. The dialogue extractor
can already *detect* all six, so until now choosing "record library" produced
pipeline-shaped folders: numbered stages for something that has no stages, an
output/ handoff for something that never hands off. That is worse than not
offering the form, because the user is told they got the shape they asked for.

Each builder below emits the SMALLEST structure that carries its form. The
canon is explicit: "Do not create processes/ or effects/ empty. Three verified
noun clusters beat seven imagined shelves." So no builder creates speculative
depth, and none of them invents stages a Pipeline would have.

THE VALIDATION CONSEQUENCE

`validate()` treats "no numbered stages" as an ERROR, which is right for a
Pipeline and wrong for every other form. A record library has records, not
stages; a knowledge bundle has layers. Validation has to know the form, or
correctly-built workspaces fail the walk test -- see `expectations()`.
"""

from __future__ import annotations

import json
import re
import time
from pathlib import Path
from typing import Any

PIPELINE = 'pipeline'
UMBRELLA = 'umbrella'
RECORD_LIBRARY = 'record_library'
KNOWLEDGE_BUNDLE = 'knowledge_bundle'
CONTEXT_MAP = 'context_map'
SYSTEM_MAP = 'system_map'

ALL_FORMS = (PIPELINE, UMBRELLA, RECORD_LIBRARY, KNOWLEDGE_BUNDLE,
             CONTEXT_MAP, SYSTEM_MAP)

# What the repeating unit is, per form. This is the selection question, kept
# as data so the UI and the docs cannot drift from the builders.
FORM_META: dict[str, dict[str, str]] = {
    PIPELINE: {
        'label': 'Pipeline',
        'tagline': 'the production line',
        'unit': 'a run (same stages, new deliverable each time)',
        'unit_noun': 'stage',
        'optimises': 'sequencing and human review between steps',
    },
    UMBRELLA: {
        'label': 'Umbrella',
        'tagline': 'a portfolio of pipelines',
        'unit': 'several kinds of run sharing one identity',
        'unit_noun': 'pipeline',
        'optimises': 'shared reference material across distinct lines',
    },
    RECORD_LIBRARY: {
        'label': 'Record library',
        'tagline': 'the unit is a record',
        'unit': 'a record that accumulates (person, client, session)',
        'unit_noun': 'record',
        'optimises': 'retrieval and uniform shape',
    },
    KNOWLEDGE_BUNDLE: {
        'label': 'Knowledge bundle',
        'tagline': 'the product is the knowledge',
        'unit': 'the knowledge itself (claims, notes, evidence)',
        'unit_noun': 'layer',
        'optimises': 'layered loading and linkability',
    },
    CONTEXT_MAP: {
        'label': 'Context map',
        'tagline': 'an organisation as a graph',
        'unit': 'an organisation (teams, processes, data, handoffs)',
        'unit_noun': 'node',
        'optimises': 'queryable frontmatter and generated indexes',
    },
    SYSTEM_MAP: {
        'label': 'System map',
        'tagline': 'a folder later agents will edit',
        'unit': 'a tree someone will change',
        'unit_noun': 'object',
        'optimises': 'change-impact: what a change hits and what it does not',
    },
}


def _slug(text: str, fallback: str = 'item') -> str:
    s = re.sub(r'[^a-z0-9]+', '-', str(text).lower()).strip('-')
    return s[:40] or fallback


def _write(path: Path, text: str) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(text, encoding='utf-8')


def _identity(name: str, description: str, form: str, how: str) -> str:
    """L0. 'Where am I' and nothing else -- the catalog holds no books."""
    meta = FORM_META[form]
    fallback = 'A ' + meta['label'].lower() + ' workspace.'
    return (
        f'# {name}\n\n'
        f'{description or fallback}\n\n'
        f'## What this workspace is\n'
        f'A **{meta["label"]}** — {meta["tagline"]}. The repeating unit here is '
        f'{meta["unit"]}.\n\n'
        f'## How to work here\n{how}\n'
    )


# ── the six builders ──────────────────────────────────────────────────────────
def build_pipeline(ws: Path, name: str, description: str, units: list[str]) -> dict[str, Any]:
    """Numbered stages; one stage's output/ is the next stage's input."""
    from .icm import scaffold as pipeline_scaffold

    # The Pipeline builder already exists and is well tested. Reimplementing it
    # here would be a second home for one fact.
    meta = pipeline_scaffold(ws, name, description, units)
    meta['form'] = PIPELINE
    return meta


def build_umbrella(ws: Path, name: str, description: str, units: list[str]) -> dict[str, Any]:
    """A root map plus N self-contained pipelines over a shared factory layer.

    "Each sub-pipeline is self-contained with its own entry file -- they don't
    share state except through the root reference layers."
    """
    from .icm import scaffold as pipeline_scaffold

    ws.mkdir(parents=True, exist_ok=True)
    _write(ws / '_shared' / 'voice.md',
           '# Voice\n\nThe tone every pipeline under this umbrella writes in.\n')
    _write(ws / '_shared' / 'conventions.md',
           '# Conventions\n\nRules shared by every pipeline here. One home per fact.\n')

    children: list[str] = []
    for raw in units:
        slug = _slug(raw, 'pipeline')
        sub = ws / slug
        # Each child is a full Pipeline with its own entry file, per the canon.
        pipeline_scaffold(sub, raw, f'A pipeline under {name}.', ['research', 'produce'])
        children.append(slug)

    rows = '\n'.join(f'| {c} | {c.replace("-", " ")} |' for c in children)
    _write(ws / 'IDENTITY.md', _identity(
        name, description, UMBRELLA,
        'Pick the pipeline that matches the job, then work inside it. The '
        'pipelines do not share state — only the material in `_shared/`.'))
    _write(ws / 'CONTEXT.md',
           '# Routing\n\nWhich pipeline handles what. The root is a map, not a sequence.\n\n'
           f'| Pipeline | Handles |\n|----------|---------|\n{rows}\n\n'
           '## Shared factory\n'
           '- `_shared/voice.md` — the tone every pipeline writes in\n'
           '- `_shared/conventions.md` — rules shared across pipelines\n')
    return {'pipelines': children}


def build_record_library(ws: Path, name: str, description: str, units: list[str]) -> dict[str, Any]:
    """A stamp, an index, and records that are copies of the stamp.

    "A new record is a copy, not a blank page. The template IS the schema."
    The index log is the declared source of truth for what exists.
    """
    ws.mkdir(parents=True, exist_ok=True)

    # The stamp. Every record starts as a copy of this.
    _write(ws / '_templates' / 'record-template' / 'README.md',
           '# <record name>\n\n'
           'Copy this whole folder to create a record. Do not start from blank.\n\n'
           '- `brief.md` — what this record is for\n'
           '- `notes.md` — accumulating notes\n')
    _write(ws / '_templates' / 'record-template' / 'brief.md',
           '---\nstatus: briefed\n---\n\n# Brief\n\nWhat this record is for.\n')
    _write(ws / '_templates' / 'record-template' / 'notes.md',
           '# Notes\n\nAppend-only. Newest at the top.\n')

    records: list[str] = []
    for raw in units:
        slug = _slug(raw, 'record')
        for fn in ('brief.md', 'notes.md'):
            src = (ws / '_templates' / 'record-template' / fn).read_text(encoding='utf-8')
            _write(ws / 'records' / slug / fn, src.replace('<record name>', raw))
        records.append(slug)

    log = '\n'.join(f'| {r} | briefed | |' for r in records)
    _write(ws / '_index' / 'log.md',
           '# Index\n\nOne line per record. This is the source of truth for what exists.\n'
           'Statuses: briefed → active → archived.\n\n'
           f'| Record | Status | Note |\n|--------|--------|------|\n{log}\n')
    _write(ws / '_reference' / 'method.md',
           '# Method\n\nHow records here are worked. Stable across every record.\n')
    _write(ws / 'IDENTITY.md', _identity(
        name, description, RECORD_LIBRARY,
        'Look the record up in `_index/log.md`, then open `records/<slug>/`. '
        'To add one, COPY `_templates/record-template/` — never start blank.'))
    _write(ws / 'CONTEXT.md',
           '# Routing\n\nNothing runs to completion here; records accumulate and are looked up.\n\n'
           '| Where | What |\n|-------|------|\n'
           '| `_index/log.md` | the catalog: what exists, its id and status |\n'
           '| `records/<slug>/` | one record, all the same internal shape |\n'
           '| `_templates/record-template/` | the stamp a new record is copied from |\n'
           '| `_reference/method.md` | how records are worked |\n')
    return {'records': records}


def build_knowledge_bundle(ws: Path, name: str, description: str, units: list[str]) -> dict[str, Any]:
    """corpus (raw) → extraction (factory) → bundle (product), layered A/B/C.

    "Layered loading is the reading protocol: always-load layer first,
    task-relevant nodes second, evidence only when needed. Never slurp."
    """
    ws.mkdir(parents=True, exist_ok=True)

    _write(ws / 'corpus' / '_index.md',
           '# Corpus\n\nRaw sources. Tick one off when it has been extracted.\n\n- [ ] (add sources)\n')
    _write(ws / 'extraction' / 'CONTEXT.md',
           '# Extraction — the factory\n\nOne job: turn corpus sources into bundle notes.\n\n'
           '## Inputs\n'
           '| Source | File/Location | Section/Scope | Why |\n'
           '|--------|---------------|---------------|-----|\n'
           '| Corpus | ../corpus/ | Full file | the raw material |\n\n'
           '## Process\n1. Take the next unticked source in `../corpus/_index.md`.\n'
           '2. Write notes into the right bundle layer.\n3. Tick the source off.\n\n'
           '## Outputs\n'
           '| Artifact | Location | Format |\n|----------|----------|--------|\n'
           '| Notes | ../bundle/ | Markdown with frontmatter |\n')

    layers = [(_slug(u, f'layer-{i}'), u) for i, u in enumerate(units or
              ['essentials', 'topics', 'evidence'], start=1)]
    # Layer A always loads; B loads by task; C is evidence, loaded last.
    tiers = ['A', 'B', 'C']
    rows = []
    for i, (slug, raw) in enumerate(layers):
        tier = tiers[min(i, len(tiers) - 1)]
        _write(ws / 'bundle' / slug / '_index.md',
               f'---\ntype: layer\nlayer: {tier}\n---\n\n'
               f'# {raw}\n\nNotes in this layer. Every note carries typed frontmatter.\n')
        rows.append(f'| {tier} | `bundle/{slug}/` | {raw} |')

    _write(ws / 'bundle' / 'index.md',
           '# Bundle\n\nWhat is in here, layer by layer.\n\n'
           '| Layer | Where | What |\n|-------|-------|------|\n' + '\n'.join(rows) + '\n')
    _write(ws / 'IDENTITY.md', _identity(
        name, description, KNOWLEDGE_BUNDLE,
        'Read `bundle/index.md` first. Load layer A always, layer B by task, '
        'and evidence only when you actually need it. Never slurp the bundle.'))
    _write(ws / 'CONTEXT.md',
           '# Routing\n\nThe deliverable is the knowledge itself.\n\n'
           '| Where | What |\n|-------|------|\n'
           '| `corpus/` | raw sources + the checkbox manifest |\n'
           '| `extraction/` | the factory that turns sources into notes |\n'
           '| `bundle/` | the product: layered, linked, queryable |\n\n'
           '## Reading protocol\n'
           'Layer A always. Layer B by task. Evidence last. A link beats a copy.\n')
    return {'layers': [s for s, _ in layers]}


def build_context_map(ws: Path, name: str, description: str, units: list[str]) -> dict[str, Any]:
    """Node cards with typed frontmatter, a generated file map, a schema.

    "A closed set of node types defined once in _meta/schema.md; every node
    declares its type in frontmatter." FILE-MAP.md is GENERATED -- a
    hand-curated index always drifts.
    """
    ws.mkdir(parents=True, exist_ok=True)

    _write(ws / '_meta' / 'schema.md',
           '# Schema\n\nThe closed set of node types. Every node declares one in frontmatter.\n\n'
           '| type | What it is |\n|------|------------|\n'
           '| team | a group of people |\n'
           '| job | an outcome someone owns |\n'
           '| process | a workflow that repeats |\n'
           '| data | a data asset |\n'
           '| governance | a rule or policy |\n\n'
           '## Process frontmatter\n'
           '`owner`, `ai-level` (L0 manual → L3 integrated), `frequency`, '
           '`value` 1–5, `pain` 1–5, `consumes:`, `produces:`\n')

    teams: list[str] = []
    for raw in (units or ['team']):
        slug = _slug(raw, 'team')
        _write(ws / 'teams' / slug / f'{slug}.md',
               f'---\ntype: team\nname: {raw}\n---\n\n'
               f'# {raw}\n\n## In\nWhat arrives here.\n\n## Movement\nWhat this team does to it.\n\n'
               f'## Out\nWhat leaves.\n\n## Edges\nWho this hands off to.\n')
        _write(ws / 'teams' / slug / 'processes' / '_index.md',
               f'---\ntype: index\n---\n\n# {raw} processes\n\nWorkflow nodes. The workhorses.\n')
        teams.append(slug)

    _write(ws / 'dashboards' / '00-tracker.md',
           '# Tracker\n\nLive queries over node frontmatter.\n\n'
           '## What to automate next\n'
           'Sort process nodes by `value` desc, then `pain` desc, where `ai-level` is L0 or L1.\n')
    _write(ws / 'IDENTITY.md', _identity(
        name, description, CONTEXT_MAP,
        'Jump via `FILE-MAP.md` — never crawl the tree. Node types are defined '
        'once in `_meta/schema.md`.'))
    _write(ws / 'CONTEXT.md',
           '# Routing\n\nThe subject is an organisation: who does what, what moves where.\n\n'
           '| Where | What |\n|-------|------|\n'
           '| `FILE-MAP.md` | GENERATED index — jump here |\n'
           '| `_meta/schema.md` | the closed set of node types |\n'
           '| `teams/<slug>/` | node cards: In / Movement / Out / Edges |\n'
           '| `dashboards/` | live queries over frontmatter |\n')
    generate_file_map(ws)
    return {'teams': teams}


def build_system_map(ws: Path, name: str, description: str, units: list[str]) -> dict[str, Any]:
    """Objects (nouns) and a change-impact index. Processes only once nouns exist.

    "Do not create processes/ or effects/ empty. Three verified noun clusters
    beat seven imagined shelves." So `processes/` is NOT created here.
    """
    ws.mkdir(parents=True, exist_ok=True)

    _write(ws / '_meta' / 'schema.md',
           '# Schema\n\nNode types: object (a noun), process (a movement).\n\n'
           '## Universes\n'
           '| universe | meaning |\n|----------|---------|\n'
           '| live | in force; implement and cite against these |\n'
           '| leftover | still present, no longer the main path |\n'
           '| ghost | named or filed, not wired — do NOT implement against these |\n')
    _write(ws / '_templates' / 'object.md',
           '---\ntype: object\nuniverse: live\nstatus: stub\n---\n\n'
           '# <noun>\n\nOne sentence — product name, and the code name if they differ.\n\n'
           '## Why this shape\nThe load-bearing why, not a field tour.\n\n'
           '## Shape\nKeys, constraints or owning files, with `path:line` citations.\n\n'
           '## Connected to\nowns / owned-by / joins / looks-like-but-is-not.\n\n'
           '## If you change this\n**Hits:** first-order only.\n\n'
           '**Does not hit:** the obvious next noun that is the WRONG one.\n\n'
           '## See\nThe source file.\n')

    objs: list[str] = []
    for raw in (units or ['object']):
        slug = _slug(raw, 'object')
        src = (ws / '_templates' / 'object.md').read_text(encoding='utf-8')
        _write(ws / 'objects' / f'{slug}.md', src.replace('<noun>', raw))
        objs.append(slug)

    _write(ws / 'objects' / '_index.md',
           '# Objects\n\nOne line per noun. `stub` until a body is written and cited.\n\n'
           '| Noun | Status | Universe |\n|------|--------|----------|\n'
           + '\n'.join(f'| {o} | stub | live |' for o in objs) + '\n')
    _write(ws / 'effects' / 'CONTEXT.md',
           '# Change impact\n\nIf you are changing X, open these cards.\n'
           'This is a catalog, not a copy of the waterfalls. '
           'If this and a card disagree, fix the card.\n')
    _write(ws / 'IDENTITY.md', _identity(
        name, description, SYSTEM_MAP,
        'Open `objects/_index.md`, then the one card you need. Never slurp '
        '`objects/`. Check the universe before implementing against anything.'))
    _write(ws / 'CONTEXT.md',
           '# Routing\n\nA walkable map of a tree someone will change.\n\n'
           '| Where | What |\n|-------|------|\n'
           '| `objects/_index.md` | one line per noun |\n'
           '| `objects/<noun>.md` | the card: shape, why, change impact |\n'
           '| `effects/CONTEXT.md` | if you change X, open these |\n'
           '| `_meta/schema.md` | node types and the three universes |\n\n'
           '## Name collisions\nProduct language and code names often disagree. '
           'State both once, here.\n')
    return {'objects': objs}


BUILDERS = {
    PIPELINE: build_pipeline,
    UMBRELLA: build_umbrella,
    RECORD_LIBRARY: build_record_library,
    KNOWLEDGE_BUNDLE: build_knowledge_bundle,
    CONTEXT_MAP: build_context_map,
    SYSTEM_MAP: build_system_map,
}


def scaffold_form(ws: Path, form: str, name: str, description: str,
                  units: list[str]) -> dict[str, Any]:
    """Build a workspace in the named form and record which form it is.

    The form is persisted in `.icm.json` because validation depends on it:
    a record library with no numbered stages is correct, and only the recorded
    form distinguishes that from a Pipeline someone forgot to finish.
    """
    if form not in BUILDERS:
        raise ValueError(f'unknown form {form!r}')

    units = [u for u in (units or []) if str(u).strip()]
    detail = BUILDERS[form](ws, name, description, units)

    meta = {
        'workspace_id': ws.name,
        'name': name,
        'description': description,
        'form': form,
        'created_at': time.time(),
        # Pipelines carry `stages`; the Pipeline builder writes its own meta,
        # so preserve it and layer the form information on top.
        **({} if form == PIPELINE else {'stages': []}),
        **{k: v for k, v in detail.items() if k != 'stages'},
    }
    if form == PIPELINE:
        meta['stages'] = detail.get('stages', [])

    (ws / '.icm.json').write_text(json.dumps(meta, indent=2), encoding='utf-8')
    return meta


# ── generated indexes ─────────────────────────────────────────────────────────
def generate_file_map(ws: Path, limit: int = 400) -> str:
    """Rebuild FILE-MAP.md from the tree and its frontmatter.

    "Generated indexes are never hand-edited. A file map built from frontmatter
    by a script cannot drift; a hand-curated one always does."
    """
    rows: list[str] = []
    for p in sorted(ws.rglob('*.md'))[:limit]:
        if p.name == 'FILE-MAP.md':
            continue
        rel = p.relative_to(ws).as_posix()
        node_type = ''
        try:
            head = p.read_text(encoding='utf-8', errors='ignore')[:400]
        except OSError:
            head = ''
        m = re.search(r'^type:\s*(\S+)', head, re.M)
        if m:
            node_type = m.group(1)
        rows.append(f'| `{rel}` | {node_type} |')

    body = ('# File map\n\n'
            '**GENERATED — do not hand-edit.** Rebuilt from the tree and node frontmatter.\n\n'
            '| Path | Type |\n|------|------|\n' + '\n'.join(rows) + '\n')
    (ws / 'FILE-MAP.md').write_text(body, encoding='utf-8')
    return body


# ── form-aware validation ─────────────────────────────────────────────────────
def expectations(form: str) -> dict[str, Any]:
    """What the walk test should require of THIS form.

    Without this, `validate()` reports "No numbered stages under stages/" as an
    ERROR for a record library — a form that correctly has no stages at all.
    A validator that fails correct work teaches people to ignore it.
    """
    common = ['IDENTITY.md', 'CONTEXT.md']
    return {
        PIPELINE: {'requires_stages': True, 'required': common,
                   'unit_dir': 'stages'},
        UMBRELLA: {'requires_stages': False, 'required': [*common, '_shared'],
                   'unit_dir': ''},
        RECORD_LIBRARY: {'requires_stages': False,
                         'required': [*common, '_index/log.md', '_templates'],
                         'unit_dir': 'records'},
        KNOWLEDGE_BUNDLE: {'requires_stages': False,
                           'required': [*common, 'bundle/index.md', 'corpus'],
                           'unit_dir': 'bundle'},
        CONTEXT_MAP: {'requires_stages': False,
                      'required': [*common, '_meta/schema.md', 'FILE-MAP.md'],
                      'unit_dir': 'teams'},
        SYSTEM_MAP: {'requires_stages': False,
                     'required': [*common, 'objects/_index.md', 'effects/CONTEXT.md'],
                     'unit_dir': 'objects'},
    }[form]


def validate_form(ws: Path, form: str) -> dict[str, Any]:
    """Walk-test checks specific to a non-pipeline form."""
    exp = expectations(form)
    errors: list[str] = []
    warnings: list[str] = []

    for rel in exp['required']:
        if not (ws / rel).exists():
            errors.append(f'{rel} is missing; a {FORM_META[form]["label"]} needs it to be walkable.')

    unit_dir = exp['unit_dir']
    if unit_dir and (ws / unit_dir).is_dir():
        units = [d for d in (ws / unit_dir).iterdir()
                 if not d.name.startswith('.') and not d.name.startswith('_')]
        if not units:
            warnings.append(f'{unit_dir}/ is empty, so there is nothing to walk to.')

    # Record library: records must match the stamp, or the library stops being
    # queryable -- "records drifting from the template shape (re-stamp them)".
    if form == RECORD_LIBRARY:
        tmpl = ws / '_templates' / 'record-template'
        if tmpl.is_dir():
            want = {f.name for f in tmpl.iterdir() if f.is_file()}
            for rec in (ws / 'records').iterdir() if (ws / 'records').is_dir() else []:
                if not rec.is_dir():
                    continue
                missing = want - {f.name for f in rec.iterdir() if f.is_file()}
                # README.md is the stamp's own instructions, not record content.
                missing.discard('README.md')
                if missing:
                    warnings.append(
                        f'records/{rec.name} is missing {sorted(missing)} from the template shape.')

    return {'ok': not errors, 'errors': errors, 'warnings': warnings}
