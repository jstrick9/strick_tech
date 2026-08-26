"""Module 35 — the workspace template library.

    "Method and instance live apart. The blank, reusable template of a
     structure is a different artifact from any filled-in deployment of it.
     When a structure proves out, extract the template before it tangles with
     the data."

    "Instantiate by copying. New unit of work = copy a template folder, not a
     blank page."

The load-bearing property is the separation itself, and the ICM layer model
already defines it precisely: L0–L3 are method, L4 is instance. So extraction
is "keep the contracts and the factory, drop the outputs", and the tests that
matter most are the ones proving a template carries no run data — including a
test that a secret sitting in a working folder does not travel into a template
somebody then shares.
"""

from __future__ import annotations

import importlib
import json

import pytest


@pytest.fixture()
def tpl(tmp_path, monkeypatch):
    monkeypatch.setenv('AGENTIC_OS_DATA_DIR', str(tmp_path))
    from backend.services import icm as icm_mod

    importlib.reload(icm_mod)
    from backend.services import icm_templates as mod

    importlib.reload(mod)
    return mod


@pytest.fixture()
def worked(tpl):
    """A workspace that has actually been used: contracts, references, outputs."""
    from backend.services import icm

    ws = icm.WORKSPACES_DIR / 'live-work'
    icm.scaffold(ws, 'Live Work', 'a real project', ['research', 'draft'])
    (ws / 'stages' / '01-research' / 'references').mkdir(exist_ok=True)
    (ws / 'stages' / '01-research' / 'references' / 'method.md').write_text(
        'HOW WE RESEARCH', encoding='utf-8')
    (ws / 'stages' / '01-research' / 'output' / 'findings.md').write_text(
        'CLIENT SECRET DATA', encoding='utf-8')
    (ws / 'stages' / '02-draft' / 'output' / 'draft-v3.md').write_text(
        'THE ACTUAL DRAFT', encoding='utf-8')
    return ws


def _files(d):
    return {p.relative_to(d).as_posix() for p in d.rglob('*') if p.is_file()}


# ── extraction keeps the method ───────────────────────────────────────────────
def test_extraction_keeps_the_contracts_and_the_factory(tpl, worked):
    """L0, L1, L2 and L3 are the method and must all survive."""
    assert tpl.extract(worked, 'my-method')['ok'] is True
    got = _files(tpl.template_dir('my-method'))
    assert 'IDENTITY.md' in got
    assert 'CONTEXT.md' in got
    assert 'stages/01-research/CONTEXT.md' in got
    assert 'stages/02-draft/CONTEXT.md' in got
    assert 'stages/01-research/references/method.md' in got


def test_extraction_drops_every_output_file(tpl, worked):
    """L4 is the instance. A template carrying it is not blank."""
    result = tpl.extract(worked, 'my-method')
    got = _files(tpl.template_dir('my-method'))
    assert 'stages/01-research/output/findings.md' not in got
    assert 'stages/02-draft/output/draft-v3.md' not in got
    assert len(result['dropped_instance_files']) == 2


def test_a_secret_in_a_working_folder_does_not_travel_into_the_template(tpl, worked):
    """Templates get shared. Anything that leaks here leaks to everyone."""
    (worked / '.env').write_text('API_KEY=sk-live-not-a-real-key', encoding='utf-8')
    tpl.extract(worked, 'my-method')
    d = tpl.template_dir('my-method')
    assert '.env' not in _files(d)
    for f in d.rglob('*'):
        if f.is_file():
            assert 'sk-live-not-a-real-key' not in f.read_text(encoding='utf-8', errors='ignore')
            assert 'CLIENT SECRET DATA' not in f.read_text(encoding='utf-8', errors='ignore')


def test_the_template_does_not_carry_the_source_workspace_marker(tpl, worked):
    """A template holding .icm.json identifies itself as an instance.

    That is the method/instance tangle this module exists to prevent: the
    template would carry the id, name and creation time of the workspace it
    came from.
    """
    tpl.extract(worked, 'my-method')
    assert '.icm.json' not in _files(tpl.template_dir('my-method'))


def test_extraction_keeps_the_shape_of_output_folders(tpl, worked):
    """A template without output/ builds a workspace with nowhere to write.

    Uses a stage whose output/ holds ONLY instance data and no .gitkeep, so the
    folder cannot survive as a side effect of copying a file into it. That was
    the flaw in an earlier version of this test: copy2 recreates parent
    directories, so the assertion passed even with directory creation removed.
    """
    out = worked / 'stages' / '02-draft' / 'output'
    (out / '.gitkeep').unlink(missing_ok=True)
    assert [p.name for p in out.iterdir()] == ['draft-v3.md']

    tpl.extract(worked, 'my-method')
    d = tpl.template_dir('my-method')
    tpl_out = d / 'stages' / '02-draft' / 'output'
    assert tpl_out.is_dir(), 'the handoff folder must exist in the template'
    assert not (tpl_out / 'draft-v3.md').exists()
    # And an instance built from it must have somewhere to write immediately.
    tpl.instantiate('my-method', 'fresh-one')
    from backend.services import icm

    assert (icm.WORKSPACES_DIR / 'fresh-one' / 'stages' / '02-draft' / 'output').is_dir()


def test_extraction_never_modifies_the_source(tpl, worked):
    before = _files(worked)
    tpl.extract(worked, 'my-method')
    assert _files(worked) == before
    assert (worked / 'stages' / '01-research' / 'output' / 'findings.md').is_file()


def test_extraction_refuses_to_clobber_an_existing_template(tpl, worked):
    assert tpl.extract(worked, 'my-method')['ok'] is True
    second = tpl.extract(worked, 'my-method')
    assert second['ok'] is False
    assert 'already exists' in second['error']


def test_extraction_can_be_forced(tpl, worked):
    tpl.extract(worked, 'my-method')
    assert tpl.extract(worked, 'my-method', overwrite=True)['ok'] is True


def test_extraction_refuses_a_hostile_template_id(tpl, worked):
    for bad in ('../escape', '', 'a/b', 'UPPER'):
        assert tpl.extract(worked, bad)['ok'] is False


def test_extraction_records_the_form(tpl):
    """A record library template must instantiate as a record library."""
    from backend.services import icm, icm_forms

    ws = icm.WORKSPACES_DIR / 'clients'
    icm_forms.scaffold_form(ws, icm_forms.RECORD_LIBRARY, 'Clients', '', ['acme'])
    tpl.extract(ws, 'client-method')
    assert tpl.get_template('client-method')['form'] == 'record_library'


def test_records_are_instance_data_and_are_dropped(tpl):
    """A record library's records are its L4."""
    from backend.services import icm, icm_forms

    ws = icm.WORKSPACES_DIR / 'clients'
    icm_forms.scaffold_form(ws, icm_forms.RECORD_LIBRARY, 'Clients', '', ['acme-corp'])
    tpl.extract(ws, 'client-method')
    got = _files(tpl.template_dir('client-method'))
    assert not any(f.startswith('records/acme-corp/') for f in got), got
    # But the stamp -- the method -- survives.
    assert any(f.startswith('_templates/record-template/') for f in got), got


# ── instantiation copies ──────────────────────────────────────────────────────
def test_instantiating_produces_a_valid_workspace(tpl, worked):
    from backend.services import icm

    tpl.extract(worked, 'my-method')
    result = tpl.instantiate('my-method', 'client-a', name='Client A')
    assert result['ok'] is True
    assert result['validation']['errors'] == []
    assert (icm.WORKSPACES_DIR / 'client-a' / 'stages' / '01-research' / 'CONTEXT.md').is_file()


def test_a_new_instance_starts_with_no_output(tpl, worked):
    from backend.services import icm

    tpl.extract(worked, 'my-method')
    tpl.instantiate('my-method', 'client-a')
    out = icm.WORKSPACES_DIR / 'client-a' / 'stages' / '01-research' / 'output'
    assert out.is_dir()
    assert [p.name for p in out.iterdir()] == ['.gitkeep']


def test_the_instance_gets_its_own_identity(tpl, worked):
    """Otherwise three workspaces are all called "Live Work"."""
    from backend.services import icm

    tpl.extract(worked, 'my-method')
    tpl.instantiate('my-method', 'client-a', name='Client A')
    ident = (icm.WORKSPACES_DIR / 'client-a' / 'IDENTITY.md').read_text(encoding='utf-8')
    assert ident.split('\n')[0] == '# Client A'


def test_the_template_marker_does_not_leak_into_the_instance(tpl, worked):
    """A workspace carrying .icm-template.json looks like a template.

    That is the method/instance tangle in the other direction: the instance
    would advertise itself as a reusable method and could be extracted from
    as though it were one.
    """
    from backend.services import icm

    tpl.extract(worked, 'my-method')
    tpl.instantiate('my-method', 'client-a')
    assert not (icm.WORKSPACES_DIR / 'client-a' / tpl.META_NAME).exists()
    assert tpl.META_NAME not in _files(icm.WORKSPACES_DIR / 'client-a')


def test_the_instance_records_which_template_made_it(tpl, worked):
    from backend.services import icm

    tpl.extract(worked, 'my-method')
    tpl.instantiate('my-method', 'client-a')
    meta = json.loads((icm.WORKSPACES_DIR / 'client-a' / '.icm.json').read_text(encoding='utf-8'))
    assert meta['from_template'] == 'my-method'
    assert meta['workspace_id'] == 'client-a'


def test_instantiating_refuses_to_overwrite_a_workspace(tpl, worked):
    """A half-overwritten workspace is worse than either outcome."""
    tpl.extract(worked, 'my-method')
    assert tpl.instantiate('my-method', 'client-a')['ok'] is True
    second = tpl.instantiate('my-method', 'client-a')
    assert second['ok'] is False
    assert 'already exists' in second['error']


def test_instantiating_an_unknown_template_is_refused(tpl):
    assert tpl.instantiate('no-such-template', 'x')['ok'] is False


def test_instantiating_with_a_hostile_workspace_id_is_refused(tpl, worked):
    tpl.extract(worked, 'my-method')
    from backend.services import icm

    result = tpl.instantiate('my-method', '../../escape')
    assert result['ok'] is False or not (icm.WORKSPACES_DIR.parent / 'escape').exists()


def test_two_instances_of_one_template_are_independent(tpl, worked):
    from backend.services import icm

    tpl.extract(worked, 'my-method')
    tpl.instantiate('my-method', 'client-a')
    tpl.instantiate('my-method', 'client-b')
    (icm.WORKSPACES_DIR / 'client-a' / 'stages' / '01-research' / 'output'
     / 'a.md').write_text('A only', encoding='utf-8')
    b_out = icm.WORKSPACES_DIR / 'client-b' / 'stages' / '01-research' / 'output'
    assert [p.name for p in b_out.iterdir()] == ['.gitkeep']


def test_a_template_survives_a_round_trip(tpl, worked):
    """extract -> instantiate -> extract again must be stable."""
    tpl.extract(worked, 'v1')
    tpl.instantiate('v1', 'fresh')
    from backend.services import icm

    tpl.extract(icm.WORKSPACES_DIR / 'fresh', 'v2')
    assert _files(tpl.template_dir('v1')) == _files(tpl.template_dir('v2'))


# ── the starter set ───────────────────────────────────────────────────────────
def test_the_starter_templates_are_seeded(tpl):
    ids = {t['template_id'] for t in tpl.list_templates()}
    assert {'software-feature', 'content-pipeline', 'client-records',
            'second-brain', 'home-ops'} <= ids


def test_every_starter_instantiates_into_a_valid_workspace(tpl):
    """A starter that does not build is worse than no starter."""
    tpl.ensure_builtins()
    for t in tpl.list_templates():
        tid = t['template_id']
        result = tpl.instantiate(tid, f'ws-{tid}')
        assert result['ok'] is True, (tid, result)
        assert result['validation']['errors'] == [], (tid, result['validation'])


def test_starters_declare_routes_so_they_are_reachable(tpl):
    """A workspace nothing routes to reintroduces the wrong-folder problem."""
    from backend.services import icm_router

    tpl.ensure_builtins()
    tpl.instantiate('content-pipeline', 'my-content')
    importlib.reload(icm_router)
    d = icm_router.resolve('time to write the newsletter')
    assert d['matched']
    assert d['workspace_id'] == 'my-content'


def test_seeding_is_idempotent(tpl):
    tpl.ensure_builtins()
    before = len(tpl.list_templates())
    assert tpl.ensure_builtins() == 0
    assert len(tpl.list_templates()) == before


def test_seeding_does_not_overwrite_a_user_edit(tpl):
    """A template the user cannot adjust is one they abandon."""
    tpl.ensure_builtins()
    ctx = tpl.template_dir('home-ops') / 'CONTEXT.md'
    ctx.write_text('MY OWN VERSION', encoding='utf-8')
    tpl.ensure_builtins()
    assert ctx.read_text(encoding='utf-8') == 'MY OWN VERSION'


def test_a_builtin_cannot_be_deleted(tpl):
    """It would be recreated on the next list, so 'deleted' would be a lie."""
    tpl.ensure_builtins()
    result = tpl.delete_template('home-ops')
    assert result['ok'] is False
    assert tpl.get_template('home-ops') is not None


def test_a_user_template_can_be_deleted(tpl, worked):
    tpl.extract(worked, 'mine')
    assert tpl.delete_template('mine')['ok'] is True
    assert tpl.get_template('mine') is None


# ── portability ───────────────────────────────────────────────────────────────
def test_a_template_exports_to_one_json_payload(tpl, worked):
    tpl.extract(worked, 'my-method')
    payload = tpl.export_template('my-method')
    assert payload['template']['template_id'] == 'my-method'
    assert 'IDENTITY.md' in payload['files']
    assert 'stages/01-research/CONTEXT.md' in payload['files']


def test_an_exported_template_reimports_identically(tpl, worked):
    tpl.extract(worked, 'my-method')
    payload = tpl.export_template('my-method')
    assert tpl.import_template(payload, template_id='copied')['ok'] is True
    original = _files(tpl.template_dir('my-method')) - {'.icm-template.json'}
    copied = _files(tpl.template_dir('copied')) - {'.icm-template.json'}
    assert original == copied


def test_import_refuses_a_path_that_escapes_the_template_folder(tpl, tmp_path):
    """An imported template is untrusted input that becomes files on disk.

    An earlier version of this test asserted on one hardcoded escape path and
    passed with containment REMOVED, because the traversal actually landed
    somewhere else entirely (/tmp/tmp/...) -- it checked the wrong address.
    This walks the real filesystem instead: after the import, no file
    containing the payload may exist anywhere outside the template folder.
    """
    marker = 'ICM_TPL_ESCAPE_MARKER_9f2a'
    payload = {
        'template': {'name': 'evil'},
        'files': {
            '../../../../../../' + tmp_path.name + '/escaped.md': marker,
            '../escaped-sibling.md': marker,
            'IDENTITY.md': '# fine',
        },
    }
    tpl.import_template(payload, template_id='evil')

    d = tpl.template_dir('evil')
    # Nothing anywhere under the data root may carry the marker except inside
    # the template folder itself.
    for f in tpl.ROOT.rglob('*'):
        if f.is_file():
            try:
                body = f.read_text(encoding='utf-8', errors='ignore')
            except OSError:
                continue
            if marker in body:
                assert d in f.parents, f'escaped to {f}'
    # And the sibling directory of the template root must not have gained one.
    assert not (tpl.TEMPLATES_DIR / 'escaped-sibling.md').exists()


def test_import_refuses_non_string_content(tpl):
    result = tpl.import_template(
        {'template': {'name': 'x'}, 'files': {'a.md': {'nested': 'object'}}},
        template_id='badtypes')
    assert 'a.md' in result['refused']


def test_importing_an_empty_payload_is_refused(tpl):
    assert tpl.import_template({'template': {}, 'files': {}})['ok'] is False


def test_import_refuses_to_clobber_without_overwrite(tpl, worked):
    tpl.extract(worked, 'my-method')
    payload = tpl.export_template('my-method')
    assert tpl.import_template(payload, template_id='my-method')['ok'] is False
    assert tpl.import_template(payload, template_id='my-method', overwrite=True)['ok'] is True


# ── HTTP surface ──────────────────────────────────────────────────────────────
class TestTemplateEndpoints:
    def test_templates_list_is_not_swallowed_by_the_id_route(self, client):
        r = client.get('/api/icm/templates')
        assert r.status_code == 200
        assert isinstance(r.json()['templates'], list)

    def test_the_starter_set_is_served(self, client):
        ids = {t['template_id'] for t in client.get('/api/icm/templates').json()['templates']}
        assert 'software-feature' in ids

    def test_extract_requires_a_workspace_id(self, client):
        assert client.post('/api/icm/templates/extract', json={}).status_code == 422

    def test_extract_of_an_unknown_workspace_is_404(self, client):
        r = client.post('/api/icm/templates/extract',
                        json={'workspace_id': 'definitely-not-real'})
        assert r.status_code == 404

    def test_instantiate_requires_a_workspace_id(self, client):
        assert client.post('/api/icm/templates/home-ops/instantiate',
                           json={}).status_code == 422

    def test_extract_then_instantiate_over_http(self, client):
        import uuid

        ws = 'tw-' + uuid.uuid4().hex[:8]
        tid = 'tt-' + uuid.uuid4().hex[:8]
        made = client.post('/api/icm/workspaces',
                           json={'name': ws, 'stages': ['plan', 'do']})
        assert made.status_code == 200, made.text

        ex = client.post('/api/icm/templates/extract',
                         json={'workspace_id': ws, 'template_id': tid})
        assert ex.status_code == 200, ex.text
        assert ex.json()['ok'] is True

        inst = client.post(f'/api/icm/templates/{tid}/instantiate',
                           json={'workspace_id': ws + '-copy'})
        assert inst.status_code == 200, inst.text
        assert inst.json()['validation']['errors'] == []

    def test_unknown_template_is_404(self, client):
        assert client.get('/api/icm/templates/no-such-thing-here').status_code == 404

    def test_export_of_an_unknown_template_is_404(self, client):
        assert client.get('/api/icm/templates/no-such-thing/export').status_code == 404

    def test_two_templates_from_one_workspace_do_not_collide(self, client):
        """Found in the browser: the id fell back to the workspace id.

        The UI sends a name, so a user who hits "already exists" renames and
        retries — and gets the identical refusal, because the name was never
        what identified the template.
        """
        import uuid

        ws = 'tw-' + uuid.uuid4().hex[:8]
        assert client.post('/api/icm/workspaces',
                           json={'name': ws, 'stages': ['a']}).status_code == 200
        first = client.post('/api/icm/templates/extract',
                            json={'workspace_id': ws, 'template_id': ws + '-one',
                                  'name': 'One'})
        second = client.post('/api/icm/templates/extract',
                             json={'workspace_id': ws, 'template_id': ws + '-two',
                                   'name': 'Two'})
        assert first.json()['ok'] is True, first.text
        assert second.json()['ok'] is True, second.text

    def test_export_and_import_round_trip_over_http(self, client):
        import uuid

        payload = client.get('/api/icm/templates/home-ops/export').json()
        assert payload['ok'] is True
        tid = 'imp-' + uuid.uuid4().hex[:8]
        r = client.post('/api/icm/templates/import',
                        json={**payload, 'template_id': tid})
        assert r.status_code == 200, r.text
        assert r.json()['written'] > 0
