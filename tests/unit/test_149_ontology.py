"""Ontology layer — typed entities and relations defined in markdown.

The defect this closes, reproduced against the running server before the
module existed:

    POST /entities {"name":"Acme",    "type":"Company"}      -> ok
    POST /entities {"name":"Globex",  "type":"compnay"}      -> ok
    POST /entities {"name":"Initech", "type":"organisation"} -> ok
    distinct types: ['Company', 'compnay', 'organisation']

Three companies that can never be retrieved as companies. Graph traversal is
only as good as its type vocabulary, so an unconstrained vocabulary quietly
destroys the retrieval quality the graph exists to provide.

These tests pin:
  1. Resolution converges synonyms/typos instead of rejecting them.
  2. Resolution reports HOW it matched, so a fuzzy rescue is visible.
  3. Relations declare their domain, and reversed edges are caught.
  4. An ontology with no file permits everything (absence is not an error).
  5. Contradictory ontologies are reported.
"""

from __future__ import annotations

import pytest

from backend.services import icm
from backend.services import ontology as onto_svc

SAMPLE = """# Ontology

## Entities

| Type    | Aliases                    | Description   |
|---------|----------------------------|---------------|
| person  | Person, human, individual  | An individual |
| company | Company, org, organisation | A business    |
| project | Project, initiative        | A body of work|

## Relations

| Relation   | From    | To      | Inverse      | Description |
|------------|---------|---------|--------------|-------------|
| employs    | company | person  | employed_by  | Employment  |
| works_on   | person  | project | worked_on_by | Assignment  |
| relates_to | project | project | relates_to   | Association |
"""


@pytest.fixture
def onto():
    return onto_svc.parse(SAMPLE)


# ── 1. parsing ────────────────────────────────────────────────────────────────
def test_parses_entities_and_relations(onto):
    assert set(onto['entities']) == {'person', 'company', 'project'}
    assert set(onto['relations']) == {'employs', 'works_on', 'relates_to'}


def test_table_header_is_not_parsed_as_a_type(onto):
    assert 'type' not in onto['entities']
    assert 'relation' not in onto['relations']


def test_relation_domains_are_captured(onto):
    r = onto['relations']['employs']
    assert (r['from'], r['to'], r['inverse']) == ('company', 'person', 'employed_by')


def test_aliases_are_indexed(onto):
    assert onto['alias_map']['organisation'] == 'company'
    assert onto['alias_map']['human'] == 'person'


def test_empty_document_parses_to_an_empty_ontology():
    e = onto_svc.parse('')
    assert e['entities'] == {} and e['relations'] == {}


def test_partial_ontology_still_constrains_what_it_defines():
    """A half-written ontology must not raise."""
    e = onto_svc.parse('# Ontology\n\n## Entities\n| Type |\n|------|\n| person |\n')
    assert 'person' in e['entities']
    assert e['relations'] == {}


# ── 2. resolution converges the vocabulary ────────────────────────────────────
@pytest.mark.parametrize('given,expected', [
    ('company', 'company'),         # exact
    ('Company', 'company'),         # case
    ('organisation', 'company'),    # alias
    ('ORGANISATION', 'company'),    # alias, case-insensitive
    ('compnay', 'company'),         # the typo from the live reproduction
    ('org', 'company'),
    ('human', 'person'),
    ('individual', 'person'),
])
def test_synonyms_and_typos_converge(onto, given, expected):
    assert onto_svc.resolve_entity_type(onto, given)['resolved'] == expected


def test_resolution_reports_how_it_matched(onto):
    """A fuzzy rescue must be distinguishable from an exact hit."""
    assert onto_svc.resolve_entity_type(onto, 'company')['match'] == 'exact'
    assert onto_svc.resolve_entity_type(onto, 'Company')['match'] == 'case'
    assert onto_svc.resolve_entity_type(onto, 'organisation')['match'] == 'alias'
    assert onto_svc.resolve_entity_type(onto, 'compnay')['match'] == 'fuzzy'


def test_hyphen_and_underscore_are_the_same_word():
    o = onto_svc.parse('## Entities\n| Type |\n|---|\n| line_item |\n')
    for v in ('line-item', 'line item', 'lineitem', 'LINE_ITEM'):
        assert onto_svc.resolve_entity_type(o, v)['resolved'] == 'line_item'


def test_a_genuinely_different_word_is_not_folded_in(onto):
    """Convergence must not become collapse."""
    r = onto_svc.resolve_entity_type(onto, 'spacecraft')
    assert r['known'] is False
    assert r['match'] == 'unknown'
    assert r['resolved'] == 'spacecraft'


def test_near_miss_threshold_rejects_a_real_word(onto):
    """'companion' is a word, not a typo for 'company'."""
    assert onto_svc.resolve_entity_type(onto, 'companion')['known'] is False


def test_unknown_terms_are_returned_lowercased_not_dropped(onto):
    assert onto_svc.resolve_entity_type(onto, 'Spacecraft')['resolved'] == 'spacecraft'


def test_empty_input_is_reported_as_empty(onto):
    assert onto_svc.resolve_entity_type(onto, '')['match'] == 'empty'


# ── 3. relations and domain constraints ───────────────────────────────────────
def test_relation_resolves_by_name_and_inverse(onto):
    assert onto_svc.resolve_relation(onto, 'employs')['resolved'] == 'employs'
    assert onto_svc.resolve_relation(onto, 'employed_by')['resolved'] == 'employs'


def test_correct_direction_passes(onto):
    assert onto_svc.check_relation_domain(onto, 'employs', 'company', 'person')['ok']


def test_reversed_relation_is_caught(onto):
    r = onto_svc.check_relation_domain(onto, 'employs', 'person', 'company')
    assert r['ok'] is False
    assert 'company' in r['reason'] and 'person' in r['reason']


def test_reversed_relation_suggests_the_inverse(onto):
    """The commonest mistake is stating it backwards; say so."""
    r = onto_svc.check_relation_domain(onto, 'employs', 'person', 'company')
    assert 'employed_by' in r['reason']


def test_wrong_type_on_one_side_is_caught(onto):
    r = onto_svc.check_relation_domain(onto, 'employs', 'company', 'project')
    assert r['ok'] is False


def test_aliased_endpoints_still_satisfy_the_domain(onto):
    """'org employs human' is the same statement as 'company employs person'."""
    assert onto_svc.check_relation_domain(onto, 'employs', 'org', 'human')['ok']


def test_unknown_relation_is_permitted_but_flagged(onto):
    r = onto_svc.check_relation_domain(onto, 'sponsors', 'company', 'project')
    assert r['ok'] is True
    assert r.get('unknown') is True


def test_unconstrained_domain_permits_anything():
    o = onto_svc.parse(
        '## Entities\n| Type |\n|---|\n| a |\n| b |\n'
        '## Relations\n| Relation | From | To |\n|---|---|---|\n| links | | |\n'
    )
    assert onto_svc.check_relation_domain(o, 'links', 'a', 'b')['ok']


# ── 4. absence is not an error ────────────────────────────────────────────────
def test_no_ontology_permits_everything():
    empty = {'entities': {}, 'relations': {}, 'alias_map': {}}
    r = onto_svc.resolve_entity_type(empty, 'anything')
    assert r['known'] is True and r['match'] == 'no-ontology'
    assert onto_svc.check_relation_domain(empty, 'whatever', 'x', 'y')['ok']


def test_missing_file_loads_as_undefined(tmp_path):
    o = onto_svc.load(tmp_path)
    assert o['defined'] is False
    assert o['entities'] == {}


# ── 5. self-consistency ───────────────────────────────────────────────────────
def test_valid_ontology_passes(onto):
    r = onto_svc.validate(onto)
    assert r['ok'], r['errors']
    assert r['entity_count'] == 3 and r['relation_count'] == 3


def test_alias_claimed_by_two_types_is_an_error():
    o = onto_svc.parse(
        '## Entities\n| Type | Aliases |\n|---|---|\n| person | agent |\n| company | agent |\n'
    )
    assert any('agent' in e for e in onto_svc.validate(o)['errors'])


def test_alias_shadowing_a_real_type_is_an_error():
    o = onto_svc.parse(
        '## Entities\n| Type | Aliases |\n|---|---|\n| person | company |\n| company | firm |\n'
    )
    assert not onto_svc.validate(o)['ok']


def test_relation_naming_an_undefined_type_is_an_error():
    o = onto_svc.parse(
        '## Entities\n| Type |\n|---|\n| person |\n'
        '## Relations\n| Relation | From | To |\n|---|---|---|\n| employs | company | person |\n'
    )
    assert any('company' in e for e in onto_svc.validate(o)['errors'])


def test_mismatched_inverse_is_a_warning_not_an_error():
    o = onto_svc.parse(
        '## Entities\n| Type |\n|---|\n| a |\n| b |\n'
        '## Relations\n| Relation | From | To | Inverse |\n|---|---|---|---|\n'
        '| x | a | b | y |\n| y | a | b | z |\n'
    )
    r = onto_svc.validate(o)
    assert r['ok']
    assert any('inverse' in w for w in r['warnings'])


# ── 6. prompt summary ─────────────────────────────────────────────────────────
def test_summary_lists_the_vocabulary(onto):
    s = onto_svc.summarise(onto)
    assert 'company' in s and 'employs' in s
    assert 'company -> person' in s


def test_summary_is_bounded(onto):
    assert len(onto_svc.summarise(onto, max_chars=40)) <= 40


def test_summary_of_an_empty_ontology_is_empty():
    assert onto_svc.summarise({'entities': {}, 'relations': {}}) == ''


# ── 7. integration with ICM scaffolding ───────────────────────────────────────
def test_scaffold_ships_a_starter_ontology(tmp_path, monkeypatch):
    """A vocabulary nobody starts with never gets written."""
    monkeypatch.setattr(icm, 'WORKSPACES_DIR', tmp_path)
    ws = tmp_path / 'demo'
    icm.scaffold(ws, 'Demo', '', ['Research'])
    assert (ws / '_config' / 'ontology.md').is_file()
    o = onto_svc.load(ws)
    assert o['defined'] is True
    assert 'company' in o['entities']


def test_starter_ontology_is_self_consistent():
    """The shipped default must not itself be contradictory."""
    r = onto_svc.validate(onto_svc.parse(onto_svc.STARTER_ONTOLOGY))
    assert r['ok'], r['errors']


def test_starter_ontology_resolves_the_reproduced_defect():
    o = onto_svc.parse(onto_svc.STARTER_ONTOLOGY)
    resolved = {
        onto_svc.resolve_entity_type(o, t)['resolved']
        for t in ('Company', 'compnay', 'organisation')
    }
    assert resolved == {'company'}, 'the three spellings must converge to one type'
