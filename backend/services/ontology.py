"""Ontology layer — typed entities and relations, defined in markdown.

WHY THIS EXISTS
`kg_entities.type` and `kg_relations.relation` are free text. Nothing checks
them, so the graph silently accumulates synonyms and typos for the same
concept. Demonstrated against the running server before this module existed:

    POST /entities {"name":"Acme",    "type":"Company"}      -> ok
    POST /entities {"name":"Globex",  "type":"compnay"}      -> ok
    POST /entities {"name":"Initech", "type":"organisation"} -> ok

    distinct types: ['Company', 'compnay', 'organisation']

Three companies that can never be retrieved as companies. Graph traversal is
only as good as the consistency of its type vocabulary, so an unconstrained
vocabulary quietly destroys the retrieval quality the graph exists to provide.

DESIGN: MARKDOWN IS THE SOURCE OF TRUTH
The ontology lives in an ICM workspace as `_config/ontology.md`, not in a
database table or a JSON schema. That follows the ICM conventions this platform
now implements:

  - plain text as the interface: any tool that reads a file can participate,
    any human who can open an editor can inspect or change it
  - canonical sources: the vocabulary has ONE home; the moment the same rule
    exists in two files they drift
  - it is diffable, reviewable, and travels with the workspace folder

An ontology is therefore a document a domain expert can write, not a schema
migration a developer has to ship.

FORMAT

    # Ontology

    ## Entities
    | Type    | Aliases              | Description        |
    |---------|----------------------|--------------------|
    | company | Company, org, firm   | A legal business   |
    | person  | Person, human        | An individual      |

    ## Relations
    | Relation   | From    | To      | Inverse     | Description       |
    |------------|---------|---------|-------------|-------------------|
    | employs    | company | person  | employed_by | Employment        |
    | founded_by | company | person  | founded     | Who founded it    |

RESOLUTION, NOT REJECTION
`resolve_entity_type("compnay")` returns `company` rather than an error. The
point is to converge the vocabulary, and refusing a near-miss just pushes the
user to invent another synonym. Exact match wins, then case-insensitive, then
an explicit alias, then a conservative fuzzy match. Anything further away is
reported as unknown so the caller can decide.

DOMAIN CONSTRAINTS
A relation declares which types it may connect. `employs` from a `person` to a
`company` is backwards, and catching that at write time is the difference
between a graph you can reason over and one you cannot.
"""

from __future__ import annotations

import difflib
import re
from pathlib import Path
from typing import Any

# A near-miss is a typo worth folding in; anything looser is a different word.
# 0.82 accepts "compnay"->"company" and rejects "companion"->"company".
FUZZY_THRESHOLD = 0.82

ONTOLOGY_FILENAME = 'ontology.md'

# Shipped as the starting point for a new workspace. Deliberately small: a
# vocabulary nobody curates is the same problem as no vocabulary at all.
STARTER_ONTOLOGY = """# Ontology

The controlled vocabulary for this workspace. Entity types and relations used
by the knowledge graph are resolved against these tables, so synonyms and
typos converge instead of fragmenting the graph.

Edit freely: this file is the canonical source.

## Entities

| Type     | Aliases                          | Description                    |
|----------|----------------------------------|--------------------------------|
| person   | Person, people, human, individual| A named individual             |
| company  | Company, org, organisation, firm | A business or institution      |
| project  | Project, initiative, programme   | A body of work                 |
| document | Document, doc, file, artifact    | A written artifact             |
| concept  | Concept, idea, topic, theme      | An abstract idea               |
| event    | Event, meeting, milestone        | Something that happened        |

## Relations

| Relation    | From     | To       | Inverse      | Description              |
|-------------|----------|----------|--------------|--------------------------|
| employs     | company  | person   | employed_by  | Employment               |
| founded_by  | company  | person   | founded      | Who founded the company  |
| works_on    | person   | project  | worked_on_by | Assignment to a project  |
| owns        | company  | project  | owned_by     | Ownership of a project   |
| mentions    | document | concept  | mentioned_in | A document cites an idea |
| relates_to  | concept  | concept  | relates_to   | Generic association      |
| part_of     | project  | project  | has_part     | Composition              |
| attended    | person   | event    | attended_by  | Participation            |
"""


def _rows(text: str, heading: str) -> list[list[str]]:
    """Return the data rows of the markdown table under `heading`."""
    want = heading.strip().lower()
    depth: int | None = None
    body: list[str] = []
    for line in (text or '').splitlines():
        m = re.match(r'^(#{1,6})\s+(.*)$', line)
        if m:
            level, title = len(m.group(1)), m.group(2).strip().lower()
            if depth is None and title == want:
                depth = level
                continue
            if depth is not None and level <= depth:
                break
        if depth is not None:
            body.append(line)

    out: list[list[str]] = []
    for line in body:
        if not line.strip().startswith('|'):
            continue
        cells = [c.strip() for c in line.strip().strip('|').split('|')]
        if not cells or not cells[0]:
            continue
        # Skip the |---|---| separator.
        if set(''.join(cells)) <= set('-: '):
            continue
        out.append(cells)
    return out


def parse(text: str) -> dict[str, Any]:
    """Parse an ontology markdown document.

    Unparseable rows are skipped rather than raising: a half-finished ontology
    should still constrain what it does define. Header rows are detected by
    their first cell so a table written without a separator still works.
    """
    entities: dict[str, dict[str, Any]] = {}
    alias_map: dict[str, str] = {}

    for cells in _rows(text, 'Entities'):
        name = cells[0].strip()
        if not name or name.lower() in ('type', 'entity', 'name'):
            continue
        canonical = name.lower()
        aliases = []
        if len(cells) > 1 and cells[1]:
            aliases = [a.strip() for a in cells[1].split(',') if a.strip()]
        entities[canonical] = {
            'type': canonical,
            'label': name,
            'aliases': aliases,
            'description': cells[2].strip() if len(cells) > 2 else '',
        }
        alias_map[canonical] = canonical
        for a in aliases:
            alias_map[a.strip().lower()] = canonical

    relations: dict[str, dict[str, Any]] = {}
    for cells in _rows(text, 'Relations'):
        name = cells[0].strip()
        if not name or name.lower() in ('relation', 'predicate', 'name'):
            continue
        canonical = name.lower()
        relations[canonical] = {
            'relation': canonical,
            'label': name,
            'from': (cells[1].strip().lower() if len(cells) > 1 else '') or '',
            'to': (cells[2].strip().lower() if len(cells) > 2 else '') or '',
            'inverse': (cells[3].strip().lower() if len(cells) > 3 else '') or '',
            'description': cells[4].strip() if len(cells) > 4 else '',
        }

    return {'entities': entities, 'relations': relations, 'alias_map': alias_map}


def load(ws: Path) -> dict[str, Any]:
    """Load a workspace's ontology from `_config/ontology.md`.

    An absent file means an empty ontology, which permits everything. Absence
    must not be an error: a workspace that has not defined a vocabulary yet
    still has to work.
    """
    path = ws / '_config' / ONTOLOGY_FILENAME
    if not path.is_file():
        return {'entities': {}, 'relations': {}, 'alias_map': {}, 'defined': False}
    try:
        data = parse(path.read_text(encoding='utf-8', errors='ignore'))
    except OSError:
        return {'entities': {}, 'relations': {}, 'alias_map': {}, 'defined': False}
    data['defined'] = bool(data['entities'] or data['relations'])
    return data


def _resolve(value: str, canonical_keys: dict[str, str], candidates: list[str]) -> dict[str, Any]:
    """Shared resolution ladder: exact -> case -> alias -> near-miss."""
    raw = (value or '').strip()
    if not raw:
        return {'resolved': '', 'input': raw, 'match': 'empty', 'known': False}
    low = raw.lower()

    if low in canonical_keys:
        how = 'exact' if raw == canonical_keys[low] else ('alias' if canonical_keys[low] != low else 'case')
        return {'resolved': canonical_keys[low], 'input': raw, 'match': how, 'known': True}

    # Underscores and hyphens are the same word to a human writing a type.
    normalised = re.sub(r'[\s_-]+', '', low)
    for key, canonical in canonical_keys.items():
        if re.sub(r'[\s_-]+', '', key) == normalised:
            return {'resolved': canonical, 'input': raw, 'match': 'normalised', 'known': True}

    close = difflib.get_close_matches(low, candidates, n=1, cutoff=FUZZY_THRESHOLD)
    if close:
        return {
            'resolved': canonical_keys[close[0]], 'input': raw,
            'match': 'fuzzy', 'known': True,
        }

    return {'resolved': low, 'input': raw, 'match': 'unknown', 'known': False}


def resolve_entity_type(onto: dict[str, Any], value: str) -> dict[str, Any]:
    """Map a user-supplied entity type onto the ontology's vocabulary."""
    if not onto.get('entities'):
        return {'resolved': (value or '').strip().lower(), 'input': value,
                'match': 'no-ontology', 'known': True}
    amap = onto['alias_map']
    return _resolve(value, amap, list(amap.keys()))


def resolve_relation(onto: dict[str, Any], value: str) -> dict[str, Any]:
    """Map a user-supplied relation onto the ontology's vocabulary."""
    rels = onto.get('relations') or {}
    if not rels:
        return {'resolved': (value or '').strip().lower(), 'input': value,
                'match': 'no-ontology', 'known': True}
    keys = {r: r for r in rels}
    # An inverse name is a legitimate way to refer to the relation.
    for name, spec in rels.items():
        if spec.get('inverse'):
            keys.setdefault(spec['inverse'], name)
    return _resolve(value, keys, list(keys.keys()))


def check_relation_domain(
    onto: dict[str, Any], relation: str, from_type: str, to_type: str
) -> dict[str, Any]:
    """Does `relation` permit these endpoint types?

    A relation declares what it may connect. `employs` from a person to a
    company is backwards, and catching it at write time is the difference
    between a graph you can reason over and one you cannot.
    """
    rels = onto.get('relations') or {}
    if not rels:
        return {'ok': True, 'reason': 'no ontology defined'}

    r = resolve_relation(onto, relation)
    spec = rels.get(r['resolved'])
    if spec is None:
        return {'ok': True, 'reason': f'relation {relation!r} is not in the ontology', 'unknown': True}

    ft = resolve_entity_type(onto, from_type)['resolved']
    tt = resolve_entity_type(onto, to_type)['resolved']
    problems = []
    # An empty domain in the table means "unconstrained", not "nothing allowed".
    if spec['from'] and ft and spec['from'] != ft:
        problems.append(f"expects a '{spec['from']}' on the left, got '{ft}'")
    if spec['to'] and tt and spec['to'] != tt:
        problems.append(f"expects a '{spec['to']}' on the right, got '{tt}'")

    if problems:
        hint = ''
        # The commonest mistake is stating the relation the wrong way round.
        if spec['from'] == tt and spec['to'] == ft:
            inv = spec.get('inverse')
            hint = (f" Did you mean '{inv}'?" if inv
                    else f" These look reversed: {spec['from']} {r['resolved']} {spec['to']}.")
        return {
            'ok': False,
            'reason': f"'{r['resolved']}' " + ' and '.join(problems) + '.' + hint,
            'expected': {'from': spec['from'], 'to': spec['to']},
            'inverse': spec.get('inverse', ''),
        }
    return {'ok': True, 'reason': ''}


def validate(onto: dict[str, Any]) -> dict[str, Any]:
    """Check an ontology for internal contradictions."""
    errors: list[str] = []
    warnings: list[str] = []
    ents = onto.get('entities') or {}
    rels = onto.get('relations') or {}

    # An alias pointing at two types makes resolution arbitrary.
    owner: dict[str, str] = {}
    for etype, spec in ents.items():
        for a in spec['aliases']:
            key = a.strip().lower()
            if key in owner and owner[key] != etype:
                errors.append(
                    f"Alias '{a}' is claimed by both '{owner[key]}' and '{etype}'."
                )
            owner[key] = etype
            if key in ents and key != etype:
                errors.append(
                    f"Alias '{a}' on '{etype}' is also a type in its own right."
                )

    for name, spec in rels.items():
        for side in ('from', 'to'):
            t = spec[side]
            if t and t not in ents:
                errors.append(
                    f"Relation '{name}' names an undefined {side} type '{t}'."
                )
        inv = spec.get('inverse')
        if inv and inv in rels:
            back = rels[inv]
            if back.get('inverse') and back['inverse'] != name:
                warnings.append(
                    f"'{name}' says its inverse is '{inv}', but '{inv}' says '{back['inverse']}'."
                )
            if back['from'] and back['from'] != spec['to']:
                warnings.append(
                    f"'{name}' and its inverse '{inv}' do not have mirrored domains."
                )

    if not ents:
        warnings.append('No entity types defined, so nothing constrains the graph.')

    return {
        'ok': not errors,
        'errors': errors,
        'warnings': warnings,
        'entity_count': len(ents),
        'relation_count': len(rels),
    }


def summarise(onto: dict[str, Any], max_chars: int = 1200) -> str:
    """A compact ontology block for a prompt.

    Selective loading applies to ontologies too: an agent needs the vocabulary,
    not the prose describing it.
    """
    ents = onto.get('entities') or {}
    rels = onto.get('relations') or {}
    if not ents and not rels:
        return ''
    lines = ['## Vocabulary']
    if ents:
        lines.append('Entity types: ' + ', '.join(sorted(ents)))
    for name, spec in sorted(rels.items()):
        arrow = f"{spec['from'] or '*'} -> {spec['to'] or '*'}"
        lines.append(f'- {name} ({arrow})')
    return '\n'.join(lines)[:max_chars]
