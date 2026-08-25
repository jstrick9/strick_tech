"""Module 31 — the six ICM forms.

"One skeleton, six jobs. Every form obeys the ten invariants; what changes is
what the repeating unit is and what the structure optimizes for."

Before this module, icm.scaffold() built a Pipeline and only a Pipeline, while
the dialogue extractor could already detect all six. Asking for a record
library produced pipeline-shaped folders -- numbered stages for something with
no stages, an output/ handoff for something that never hands off -- and the
user was told they got the shape they asked for. So the load-bearing tests here
are the ones asserting each form builds ITS OWN shape and NOT a pipeline.

The second half is validation. validate() treated "no numbered stages" as an
error, which is right for a Pipeline and wrong for the other five. A validator
that fails correct work teaches people to ignore it.
"""

from __future__ import annotations

import importlib

import pytest

from backend.services import icm_forms as forms


@pytest.fixture()
def icm(tmp_path, monkeypatch):
    monkeypatch.setenv('AGENTIC_OS_DATA_DIR', str(tmp_path))
    from backend.services import icm as mod

    importlib.reload(mod)
    return mod


def _build(icm, form, units, name='w'):
    ws = icm.WORKSPACES_DIR / name
    meta = forms.scaffold_form(ws, form, name, '', units)
    return ws, meta


# ── every form is offered and described ───────────────────────────────────────
def test_all_six_forms_are_buildable():
    assert set(forms.BUILDERS) == set(forms.ALL_FORMS)
    assert len(forms.ALL_FORMS) == 6


def test_every_form_declares_its_repeating_unit():
    """Selection asks one question: what is the repeating unit of work?"""
    for f in forms.ALL_FORMS:
        meta = forms.FORM_META[f]
        assert meta['unit'].strip()
        assert meta['label'].strip()
        assert meta['optimises'].strip()


def test_an_unknown_form_is_refused(icm):
    with pytest.raises(ValueError):
        forms.scaffold_form(icm.WORKSPACES_DIR / 'x', 'not_a_form', 'x', '', [])


# ── each form builds its OWN shape, not a pipeline ────────────────────────────
@pytest.mark.parametrize('form', [
    forms.UMBRELLA, forms.RECORD_LIBRARY, forms.KNOWLEDGE_BUNDLE,
    forms.CONTEXT_MAP, forms.SYSTEM_MAP,
])
def test_non_pipeline_forms_do_not_create_numbered_stages(icm, form):
    """The original defect: every form got pipeline-shaped folders."""
    ws, _ = _build(icm, form, ['alpha', 'beta'])
    assert not (ws / 'stages').exists(), f'{form} must not have stages/'


@pytest.mark.parametrize('form', forms.ALL_FORMS)
def test_every_form_is_orientable(icm, form):
    """Invariant 2: a small stable entry file answering 'where am I'."""
    ws, _ = _build(icm, form, ['alpha', 'beta'])
    assert (ws / 'IDENTITY.md').is_file()
    assert (ws / 'CONTEXT.md').is_file()
    assert forms.FORM_META[form]['label'] in (ws / 'IDENTITY.md').read_text(encoding='utf-8')


@pytest.mark.parametrize('form', forms.ALL_FORMS)
def test_every_form_records_which_form_it_is(icm, form):
    """Validation depends on this: no form marker, no form-aware checks."""
    ws, meta = _build(icm, form, ['alpha'])
    assert meta['form'] == form
    assert icm.read_meta(ws)['form'] == form


def test_pipeline_still_builds_numbered_stages(icm):
    ws, meta = _build(icm, forms.PIPELINE, ['research', 'draft'])
    assert meta['stages'] == ['01-research', '02-draft']
    assert (ws / 'stages' / '01-research' / 'CONTEXT.md').is_file()
    assert (ws / 'stages' / '01-research' / 'output').is_dir()


# ── umbrella ──────────────────────────────────────────────────────────────────
def test_umbrella_children_are_self_contained_pipelines(icm):
    """"Each sub-pipeline is self-contained with its own entry file.\""""
    ws, meta = _build(icm, forms.UMBRELLA, ['video production', 'newsletter'])
    assert meta['pipelines'] == ['video-production', 'newsletter']
    for child in meta['pipelines']:
        assert (ws / child / 'IDENTITY.md').is_file()
        assert (ws / child / 'stages').is_dir()


def test_umbrella_has_a_shared_factory_layer(icm):
    ws, _ = _build(icm, forms.UMBRELLA, ['a'])
    assert (ws / '_shared' / 'voice.md').is_file()


def test_umbrella_root_routes_to_each_pipeline(icm):
    ws, _ = _build(icm, forms.UMBRELLA, ['video production'])
    assert 'video-production' in (ws / 'CONTEXT.md').read_text(encoding='utf-8')


# ── record library ────────────────────────────────────────────────────────────
def test_a_record_is_a_copy_of_the_template(icm):
    """"A new record is a copy, not a blank page. The template IS the schema.\""""
    ws, meta = _build(icm, forms.RECORD_LIBRARY, ['Acme Corp', 'Jane Doe'])
    assert meta['records'] == ['acme-corp', 'jane-doe']
    stamp = {f.name for f in (ws / '_templates' / 'record-template').iterdir() if f.is_file()}
    for rec in meta['records']:
        got = {f.name for f in (ws / 'records' / rec).iterdir() if f.is_file()}
        assert (stamp - {'README.md'}) <= got


def test_record_library_index_lists_every_record(icm):
    ws, meta = _build(icm, forms.RECORD_LIBRARY, ['Acme Corp'])
    log = (ws / '_index' / 'log.md').read_text(encoding='utf-8')
    for rec in meta['records']:
        assert rec in log


def test_record_names_are_slugged_safely(icm):
    ws, meta = _build(icm, forms.RECORD_LIBRARY, ['../escape', 'Ok Name'])
    assert meta['records'] == ['escape', 'ok-name']
    assert (ws / 'records' / 'escape').is_dir()
    assert not (ws.parent / 'escape').exists()


# ── knowledge bundle ──────────────────────────────────────────────────────────
def test_knowledge_bundle_separates_factory_from_product(icm):
    """corpus (raw) -> extraction (factory) -> bundle (product)."""
    ws, _ = _build(icm, forms.KNOWLEDGE_BUNDLE, ['essentials', 'topics'])
    assert (ws / 'corpus' / '_index.md').is_file()
    assert (ws / 'extraction' / 'CONTEXT.md').is_file()
    assert (ws / 'bundle' / 'index.md').is_file()


def test_knowledge_bundle_layers_carry_typed_frontmatter(icm):
    """"Labels make it queryable, links make it a graph.\""""
    ws, meta = _build(icm, forms.KNOWLEDGE_BUNDLE, ['essentials', 'topics', 'evidence'])
    first = (ws / 'bundle' / meta['layers'][0] / '_index.md').read_text(encoding='utf-8')
    assert first.startswith('---')
    assert 'type: layer' in first
    assert 'layer: A' in first


def test_knowledge_bundle_defaults_to_three_layers_when_none_given(icm):
    ws, meta = _build(icm, forms.KNOWLEDGE_BUNDLE, [])
    assert len(meta['layers']) == 3


# ── context map ───────────────────────────────────────────────────────────────
def test_context_map_defines_a_closed_set_of_node_types(icm):
    ws, _ = _build(icm, forms.CONTEXT_MAP, ['marketing'])
    schema = (ws / '_meta' / 'schema.md').read_text(encoding='utf-8')
    for t in ('team', 'job', 'process', 'data', 'governance'):
        assert t in schema


def test_context_map_nodes_declare_their_type(icm):
    ws, meta = _build(icm, forms.CONTEXT_MAP, ['marketing'])
    card = (ws / 'teams' / 'marketing' / 'marketing.md').read_text(encoding='utf-8')
    assert 'type: team' in card
    assert '## Movement' in card


def test_context_map_file_map_is_generated_and_says_so(icm):
    """"Generated indexes are never hand-edited.\""""
    ws, _ = _build(icm, forms.CONTEXT_MAP, ['marketing'])
    fm = (ws / 'FILE-MAP.md').read_text(encoding='utf-8')
    assert 'GENERATED' in fm
    assert 'teams/marketing/marketing.md' in fm


def test_regenerating_the_file_map_picks_up_new_nodes(icm):
    """A hand-curated index drifts; a scripted one cannot."""
    ws, _ = _build(icm, forms.CONTEXT_MAP, ['marketing'])
    assert 'sales' not in (ws / 'FILE-MAP.md').read_text(encoding='utf-8')
    (ws / 'teams' / 'sales').mkdir(parents=True)
    (ws / 'teams' / 'sales' / 'sales.md').write_text(
        '---\ntype: team\n---\n\n# Sales\n', encoding='utf-8')
    forms.generate_file_map(ws)
    fm = (ws / 'FILE-MAP.md').read_text(encoding='utf-8')
    assert 'teams/sales/sales.md' in fm
    assert '| team |' in fm


def test_file_map_never_indexes_itself(icm):
    """Must hold on REGENERATION, which is when the file already exists.

    Testing only the first build proves nothing: FILE-MAP.md does not exist
    yet during that pass, so the self-exclusion never runs. The revert proof
    caught this -- deleting the guard broke no test. Regenerating twice is the
    case that matters, since a scripted index is rebuilt on every change.
    """
    ws, _ = _build(icm, forms.CONTEXT_MAP, ['marketing'])
    assert (ws / 'FILE-MAP.md').is_file()
    forms.generate_file_map(ws)
    forms.generate_file_map(ws)
    body = (ws / 'FILE-MAP.md').read_text(encoding='utf-8')
    assert '`FILE-MAP.md`' not in body


# ── system map ────────────────────────────────────────────────────────────────
def test_system_map_object_cards_carry_change_impact(icm):
    ws, meta = _build(icm, forms.SYSTEM_MAP, ['session'])
    card = (ws / 'objects' / 'session.md').read_text(encoding='utf-8')
    assert '## If you change this' in card
    assert 'Does not hit' in card, 'naming the WRONG next noun is the point'


def test_system_map_declares_the_three_universes(icm):
    ws, _ = _build(icm, forms.SYSTEM_MAP, ['session'])
    schema = (ws / '_meta' / 'schema.md').read_text(encoding='utf-8')
    for u in ('live', 'leftover', 'ghost'):
        assert u in schema


def test_system_map_does_not_create_an_empty_processes_folder(icm):
    """"Do not create processes/ or effects/ empty. Three verified noun
    clusters beat seven imagined shelves." Processes come after nouns exist.
    """
    ws, _ = _build(icm, forms.SYSTEM_MAP, ['session'])
    assert not (ws / 'processes').exists()


def test_system_map_objects_start_as_stubs(icm):
    """"status: verified only with a date and citations. stale is allowed.
    A confident wrong date is not.\""""
    ws, _ = _build(icm, forms.SYSTEM_MAP, ['session'])
    assert 'status: stub' in (ws / 'objects' / 'session.md').read_text(encoding='utf-8')
    assert 'stub' in (ws / 'objects' / '_index.md').read_text(encoding='utf-8')


# ── form-aware validation ─────────────────────────────────────────────────────
@pytest.mark.parametrize('form', forms.ALL_FORMS)
def test_a_freshly_built_workspace_passes_its_own_walk_test(icm, form):
    """THE regression this module exists for.

    Before form-aware validation, five of six forms failed with "No numbered
    stages under stages/" the moment they were built correctly.
    """
    ws, _ = _build(icm, form, ['alpha', 'beta'])
    result = icm.validate(ws)
    assert result['ok'], (form, result['errors'])
    assert result['errors'] == []
    assert result['walk_test']['can_orient']
    assert result['walk_test']['can_find_work']


def test_validation_reports_the_form(icm):
    ws, _ = _build(icm, forms.RECORD_LIBRARY, ['acme'])
    assert icm.validate(ws)['form'] == 'record_library'


def test_a_pipeline_with_no_stages_still_errors(icm):
    """The stage check must survive for the form it was written for."""
    ws = icm.WORKSPACES_DIR / 'empty-pipe'
    forms.scaffold_form(ws, forms.PIPELINE, 'empty-pipe', '', ['only'])
    import shutil

    shutil.rmtree(ws / 'stages')
    result = icm.validate(ws)
    assert not result['ok']
    assert any('numbered stages' in e for e in result['errors'])


def test_a_record_library_missing_its_index_fails(icm):
    ws, _ = _build(icm, forms.RECORD_LIBRARY, ['acme'])
    (ws / '_index' / 'log.md').unlink()
    result = icm.validate(ws)
    assert not result['ok']
    assert any('_index/log.md' in e for e in result['errors'])


def test_a_record_drifting_from_the_template_is_warned_about(icm):
    """"Records drifting from the template shape (re-stamp them).\""""
    ws, _ = _build(icm, forms.RECORD_LIBRARY, ['acme'])
    (ws / 'records' / 'acme' / 'notes.md').unlink()
    result = icm.validate(ws)
    assert any('template shape' in w for w in result['warnings'])


def test_a_knowledge_bundle_missing_its_index_fails(icm):
    ws, _ = _build(icm, forms.KNOWLEDGE_BUNDLE, ['essentials'])
    (ws / 'bundle' / 'index.md').unlink()
    assert not icm.validate(ws)['ok']


def test_a_context_map_missing_its_schema_fails(icm):
    ws, _ = _build(icm, forms.CONTEXT_MAP, ['marketing'])
    (ws / '_meta' / 'schema.md').unlink()
    assert not icm.validate(ws)['ok']


def test_an_empty_unit_directory_is_warned_not_errored(icm):
    """Empty is a work-in-progress state, not a broken workspace."""
    ws, _ = _build(icm, forms.RECORD_LIBRARY, ['acme'])
    import shutil

    shutil.rmtree(ws / 'records' / 'acme')
    result = icm.validate(ws)
    assert result['ok'], result['errors']
    assert any('nothing to walk to' in w for w in result['warnings'])


def test_expectations_are_defined_for_every_form():
    for f in forms.ALL_FORMS:
        exp = forms.expectations(f)
        assert 'requires_stages' in exp
        assert exp['required']


# ── the router reaches every form ─────────────────────────────────────────────
def test_any_form_can_be_routed_to(icm):
    """Forms are useless if the entry router cannot find them."""
    from backend.services import icm_router as router_mod

    importlib.reload(router_mod)
    ws, _ = _build(icm, forms.RECORD_LIBRARY, ['acme'], name='clients')
    ctx = ws / 'CONTEXT.md'
    ctx.write_text(ctx.read_text(encoding='utf-8') + '\n## Routes\n- client file\n',
                   encoding='utf-8')
    d = router_mod.resolve('pull up the client file')
    assert d['matched']
    assert d['workspace_id'] == 'clients'


# ── HTTP surface ──────────────────────────────────────────────────────────────
CLIENT_WORK = (
    'I run a small consultancy. Each client gets their own folder with their '
    'brief, their contract and my notes from every call. When a new one signs '
    'I copy the same set of files and fill them in. I need to look up what we '
    'agreed with any client quickly.'
)


class TestFormEndpoints:
    def test_forms_catalogue_lists_all_six(self, client):
        r = client.get('/api/icm/forms')
        assert r.status_code == 200
        got = r.json()['forms']
        assert len(got) == 6
        for f in got:
            assert f['id'] in forms.ALL_FORMS
            assert f['unit']

    def test_describe_create_builds_the_detected_form(self, client):
        """THE integration this module closes.

        The extractor detected record_library already; the builder always made
        a pipeline. A record library must come back with records/, not stages/.
        """
        import uuid

        name = 'form-' + uuid.uuid4().hex[:8]
        r = client.post('/api/icm/describe/create',
                        json={'text': CLIENT_WORK, 'name': name,
                              'stages': ['acme corp', 'jane doe']})
        assert r.status_code == 200, r.text
        d = r.json()
        assert d['workspace']['form'] == 'record_library'
        assert d['workspace'].get('records') == ['acme-corp', 'jane-doe']
        assert not d['validation']['errors']

    def test_the_user_can_override_the_detected_form(self, client):
        """It is a proposal, not a ruling."""
        import uuid

        name = 'form-' + uuid.uuid4().hex[:8]
        r = client.post('/api/icm/describe/create',
                        json={'text': CLIENT_WORK, 'name': name,
                              'form': 'pipeline', 'stages': ['intake', 'deliver']})
        assert r.status_code == 200
        assert r.json()['workspace']['form'] == 'pipeline'
        assert r.json()['workspace']['stages'] == ['01-intake', '02-deliver']

    def test_an_unknown_form_is_rejected(self, client):
        import uuid

        r = client.post('/api/icm/describe/create',
                        json={'text': CLIENT_WORK, 'form': 'nonsense',
                              'name': 'form-' + uuid.uuid4().hex[:8]})
        assert r.status_code == 422

    def test_file_map_can_be_rebuilt_over_http(self, client):
        import uuid

        name = 'form-' + uuid.uuid4().hex[:8]
        client.post('/api/icm/describe/create',
                    json={'text': 'I want to map my team, who does what and '
                                  'the handoffs between them across teams.',
                          'name': name, 'stages': ['marketing', 'sales']})
        r = client.post(f'/api/icm/workspaces/{name}/file-map')
        assert r.status_code == 200
        assert r.json()['lines'] > 0

    def test_rebuilding_the_file_map_of_an_unknown_workspace_is_404(self, client):
        assert client.post('/api/icm/workspaces/nope-not-real/file-map').status_code == 404
