"""Module 29 — ICM restructure mode and the system map form.

Restructure mode reorganises somebody's real folder, so the tests that matter
most here are the refusals. The canon is explicit that migration is human-gated
("Propose before moving... This is a human gate in a method built on human
gates -- honor it") and that nothing is deleted ("-> propose `_archive/`, never
silently delete").

A classifier is a heuristic, not an oracle. Every property below exists to stop
a heuristic being handed destructive power:

  * inventory() and plan() never write into the audited tree
  * apply_plan() refuses without an explicit approval flag
  * apply_plan() refuses a plan id it did not issue
  * applying twice is refused
  * files are copied, never moved or deleted
  * a crafted path in a stored plan cannot write outside the destination
"""

from __future__ import annotations

import importlib

import pytest


@pytest.fixture()
def svc(tmp_path, monkeypatch):
    monkeypatch.setenv('AGENTIC_OS_DATA_DIR', str(tmp_path / 'data'))
    from backend.services import icm_restructure as mod

    importlib.reload(mod)
    return mod


@pytest.fixture()
def tree(tmp_path):
    """A messy folder with one of everything the classifier must recognise."""
    r = tmp_path / 'subject'
    (r / 'docs').mkdir(parents=True)
    (r / 'output').mkdir()
    (r / 'src').mkdir()
    (r / 'archive').mkdir()
    (r / 'node_modules' / 'junk').mkdir(parents=True)

    (r / 'README.md').write_text('# Subject\nUses helper.py and voice.md\n', encoding='utf-8')
    (r / 'CONTEXT.md').write_text('# Routing\n', encoding='utf-8')
    (r / 'docs' / 'voice.md').write_text('Tone rules.\n', encoding='utf-8')
    (r / 'src' / 'helper.py').write_text('def go():\n    return 1\n', encoding='utf-8')
    (r / 'output' / 'run-1.md').write_text('result\n', encoding='utf-8')
    (r / 'archive' / 'ancient.md').write_text('old\n', encoding='utf-8')
    (r / 'notes_old.md').write_text('superseded\n', encoding='utf-8')
    (r / 'empty.md').write_text('', encoding='utf-8')
    (r / 'node_modules' / 'junk' / 'huge.js').write_text('x\n', encoding='utf-8')
    return r


# ── inventory reads, and only reads ───────────────────────────────────────────
def test_inventory_finds_the_real_files(svc, tree):
    inv = svc.inventory(tree)
    paths = {f['path'] for f in inv['files']}
    assert 'README.md' in paths
    assert 'src/helper.py' in paths
    assert 'output/run-1.md' in paths


def test_inventory_skips_generated_and_vendored_directories(svc, tree):
    """Walking node_modules would blow the file cap before reaching source."""
    paths = {f['path'] for f in svc.inventory(tree)['files']}
    assert not any(p.startswith('node_modules/') for p in paths)


def test_inventory_does_not_modify_the_tree(svc, tree):
    before = sorted(p.relative_to(tree).as_posix() for p in tree.rglob('*'))
    svc.inventory(tree)
    after = sorted(p.relative_to(tree).as_posix() for p in tree.rglob('*'))
    assert before == after


def test_inventory_records_reference_relationships(svc, tree):
    inv = svc.inventory(tree)
    by = {f['path']: f for f in inv['files']}
    # README.md mentions helper.py and voice.md by name.
    assert by['src/helper.py']['referenced'] is True
    assert by['docs/voice.md']['referenced'] is True
    assert by['output/run-1.md']['referenced'] is False


def test_inventory_is_bounded(svc, tmp_path, monkeypatch):
    r = tmp_path / 'big'
    r.mkdir()
    monkeypatch.setattr(svc, 'MAX_FILES', 10)
    for i in range(40):
        (r / f'f{i}.md').write_text('x', encoding='utf-8')
    inv = svc.inventory(r)
    assert inv['truncated'] is True
    assert inv['file_count'] <= 10


# ── the five roles ────────────────────────────────────────────────────────────
@pytest.mark.parametrize(('path', 'role'), [
    ('README.md', 'catalog'),
    ('CONTEXT.md', 'contract'),
    ('docs/voice.md', 'factory'),
    ('src/helper.py', 'factory'),
    ('output/run-1.md', 'product'),
    ('archive/ancient.md', 'dead'),
    ('notes_old.md', 'dead'),
])
def test_files_are_sorted_into_the_canonical_roles(svc, tree, path, role):
    items = {c['path']: c for c in (svc.classify(f) for f in svc.inventory(tree)['files'])}
    assert items[path]['role'] == role, items[path]['why']


def test_every_classification_states_why(svc, tree):
    """A migration map is only reviewable if each line explains itself."""
    for f in svc.inventory(tree)['files']:
        assert svc.classify(f)['why'].strip()


# ── the three universes ───────────────────────────────────────────────────────
def test_intentionally_empty_structural_files_are_not_ghosts(svc, tmp_path):
    """False positive found live: .gitkeep was reported as a ghost.

    A ghost is something "named or filed, not wired". .gitkeep is empty on
    purpose -- that IS its job -- so calling it a ghost trains the reader to
    ignore ghost warnings, which is worse than not emitting them.
    """
    r = tmp_path / 'structural'
    (r / 'output').mkdir(parents=True)
    (r / 'output' / '.gitkeep').write_text('', encoding='utf-8')
    (r / 'output' / '__init__.py').write_text('', encoding='utf-8')
    (r / 'output' / 'actually-hollow.md').write_text('', encoding='utf-8')

    items = {c['path']: c for c in (svc.classify(f) for f in svc.inventory(r)['files'])}
    assert items['output/.gitkeep']['universe'] != 'ghost'
    assert items['output/__init__.py']['universe'] != 'ghost'
    # A genuinely empty content file is still a ghost.
    assert items['output/actually-hollow.md']['universe'] == 'ghost'


def test_the_scan_ignores_its_own_migration_output(svc, tree):
    """Found live: a second plan proposed moving the first plan's copies."""
    pid = svc.plan(tree)['plan_id']
    svc.apply_plan(pid, approved=True)
    assert (tree / '_icm-restructured').is_dir()

    paths = {f['path'] for f in svc.inventory(tree)['files']}
    assert not any(p.startswith('_icm-restructured/') for p in paths)


def test_an_empty_file_is_a_ghost(svc, tree):
    items = {c['path']: c for c in (svc.classify(f) for f in svc.inventory(tree)['files'])}
    assert items['empty.md']['universe'] == 'ghost'


def test_archived_material_is_leftover_not_live(svc, tree):
    items = {c['path']: c for c in (svc.classify(f) for f in svc.inventory(tree)['files'])}
    assert items['archive/ancient.md']['universe'] == 'leftover'


def test_referenced_recent_files_are_live(svc, tree):
    items = {c['path']: c for c in (svc.classify(f) for f in svc.inventory(tree)['files'])}
    assert items['src/helper.py']['universe'] == 'live'


def test_unreferenced_and_ancient_is_leftover(svc, tree):
    import os
    import time

    old = time.time() - (400 * 86400)
    target = tree / 'output' / 'run-1.md'
    os.utime(target, (old, old))
    items = {c['path']: c for c in (svc.classify(f) for f in svc.inventory(tree)['files'])}
    assert items['output/run-1.md']['universe'] == 'leftover'


# ── the plan is a proposal ────────────────────────────────────────────────────
def test_plan_summarises_roles_and_universes(svc, tree):
    p = svc.plan(tree, 'subject')
    assert p['plan_id']
    assert sum(p['by_role'].values()) == p['file_count']
    assert sum(p['by_universe'].values()) == p['file_count']


def test_plan_does_not_touch_the_audited_tree(svc, tree):
    before = sorted(x.relative_to(tree).as_posix() for x in tree.rglob('*'))
    svc.plan(tree)
    after = sorted(x.relative_to(tree).as_posix() for x in tree.rglob('*'))
    assert before == after


def test_plan_proposes_dead_files_into_archive_never_deletion(svc, tree):
    moves = {m['from']: m['to'] for m in svc.plan(tree)['moves']}
    assert moves['notes_old.md'].startswith('_archive/')


def test_plan_is_persisted_and_reloadable(svc, tree):
    pid = svc.plan(tree)['plan_id']
    assert svc.load_plan(pid)['plan_id'] == pid


def test_plans_are_listed_newest_first(svc, tree):
    svc.plan(tree, 'one')
    svc.plan(tree, 'two')
    labels = [p['label'] for p in svc.list_plans()]
    assert labels[0] == 'two'


def test_loading_a_bogus_plan_id_returns_none_not_a_path_error(svc):
    for bad in ('', 'nope', '../../etc/passwd', 'a' * 200):
        assert svc.load_plan(bad) is None


def test_apply_validates_the_plan_id_before_building_any_write_path(svc, tree):
    """apply_plan WRITES the plan back, so its id must be validated too.

    Found by the revert proof: removing the plan-id validator broke no test,
    because load_plan's check was the only one exercised while plan() and
    apply_plan() built their write paths with a raw f-string. A traversal id
    therefore reached a file write. This pins the write path, not just the read.
    """
    from pathlib import Path as _P

    hostile = '../../../../../../tmp/icm_pwned'
    r = svc.apply_plan(hostile, approved=True)
    assert r['ok'] is False
    assert 'invalid plan id' in r['error']
    assert not _P('/tmp/icm_pwned.json').exists()

    # And a well-formed but unissued id is still a clean "not found".
    assert svc.apply_plan('0' * 16, approved=True)['error'].startswith('plan')


def test_every_plan_file_written_lands_inside_the_plans_dir(svc, tree):
    svc.plan(tree)
    for f in svc.PLANS_DIR.glob('*.json'):
        assert f.parent == svc.PLANS_DIR
        assert len(f.stem) == 16


# ── the human gate ────────────────────────────────────────────────────────────
def test_apply_refuses_without_explicit_approval(svc, tree):
    """The canon's gate: propose before moving, and honour the gate."""
    pid = svc.plan(tree)['plan_id']
    r = svc.apply_plan(pid, approved=False)
    assert r['ok'] is False
    assert 'approval' in r['error']
    assert not (tree / '_icm-restructured').exists()


def test_apply_refuses_a_plan_id_it_never_issued(svc, tree):
    r = svc.apply_plan('0123456789abcdef', approved=True)
    assert r['ok'] is False
    assert 'not found' in r['error']


def test_apply_refuses_to_run_twice(svc, tree):
    pid = svc.plan(tree)['plan_id']
    assert svc.apply_plan(pid, approved=True)['ok'] is True
    second = svc.apply_plan(pid, approved=True)
    assert second['ok'] is False
    assert 'already applied' in second['error']


def test_apply_copies_and_never_removes_the_original(svc, tree):
    before = {p.relative_to(tree).as_posix() for p in tree.rglob('*') if p.is_file()}
    pid = svc.plan(tree)['plan_id']
    svc.apply_plan(pid, approved=True)
    after = {p.relative_to(tree).as_posix() for p in tree.rglob('*') if p.is_file()}
    # Every original file survives; only new copies appear.
    assert before <= after


def test_apply_writes_into_a_dedicated_destination(svc, tree):
    pid = svc.plan(tree)['plan_id']
    r = svc.apply_plan(pid, approved=True)
    assert r['ok'] is True
    assert r['copied'] > 0
    assert (tree / '_icm-restructured').is_dir()


def test_apply_refuses_a_move_that_escapes_the_destination(svc, tree, tmp_path):
    """A tampered plan file must not become an arbitrary filesystem write.

    The escape target is a unique path under tmp_path, not a fixed /tmp name:
    an earlier version of this test asserted on /tmp/pwned.md and then failed
    spuriously because a PREVIOUS revert-proof run -- one that had deliberately
    removed containment -- had genuinely written that file and left it behind.
    The probe was reading another run's evidence.
    """
    import json

    escape_target = tmp_path / 'escaped' / 'pwned.md'
    escape_target.parent.mkdir(parents=True, exist_ok=True)
    rel = '../' * 12 + escape_target.relative_to(escape_target.anchor).as_posix()

    pid = svc.plan(tree)['plan_id']
    path = svc.PLANS_DIR / f'{pid}.json'
    data = json.loads(path.read_text(encoding='utf-8'))
    data['moves'] = [{'from': 'README.md', 'to': rel,
                      'role': 'catalog', 'universe': 'live', 'why': 'crafted'}]
    path.write_text(json.dumps(data), encoding='utf-8')

    r = svc.apply_plan(pid, approved=True)
    # safe_path clamps a traversal back inside the destination rather than
    # letting it out; either way nothing may be written outside.
    assert not escape_target.exists()
    dest = tree / '_icm-restructured'
    for written in dest.rglob('*'):
        if written.is_file():
            assert dest in written.parents
    assert r['ok'] is True


def test_apply_reports_a_missing_source_tree(svc, tree):
    import shutil

    pid = svc.plan(tree)['plan_id']
    shutil.rmtree(tree)
    r = svc.apply_plan(pid, approved=True)
    assert r['ok'] is False
    assert 'no longer exists' in r['error']


# ── the system map ────────────────────────────────────────────────────────────
def test_system_map_returns_index_cards_not_a_report(svc, tree):
    m = svc.system_map(tree)
    assert m['cards']
    for c in m['cards']:
        assert c['noun']
        assert c['universe'] in ('live', 'leftover', 'ghost')
        assert 'hits' in c
        assert len(c['examples']) <= 5


def test_system_map_clusters_by_top_level_directory(svc, tree):
    nouns = {c['noun'] for c in svc.system_map(tree)['cards']}
    assert 'src' in nouns
    assert 'docs' in nouns
    assert '(root)' in nouns


def test_system_map_counts_universes_per_cluster(svc, tree):
    cards = {c['noun']: c for c in svc.system_map(tree)['cards']}
    assert cards['src']['live'] >= 1
    assert cards['archive']['leftover'] >= 1


def test_system_map_hits_are_first_order_only(svc, tmp_path):
    """Naming everything downstream is how change-impact indexes go wrong.

    The cap is only meaningful against a tree that would otherwise exceed it,
    so this builds a hub file mentioning twelve sibling clusters rather than
    reusing the small shared fixture (which never reached six and so could not
    tell a working cap from a missing one).
    """
    r = tmp_path / 'wide'
    r.mkdir()
    clusters = [f'mod{i}' for i in range(12)]
    for c in clusters:
        (r / c).mkdir()
        (r / c / 'thing.py').write_text('x = 1\n', encoding='utf-8')
    hub = r / 'hub'
    hub.mkdir()
    (hub / 'main.py').write_text(
        '\n'.join(f'import {c}' for c in clusters) + '\n', encoding='utf-8')

    cards = {c['noun']: c for c in svc.system_map(r)['cards']}
    assert len(cards['hub']['hits']) == 6, 'first-order hits must be capped'
    for c in cards.values():
        assert len(c['hits']) <= 6
        assert c['noun'] not in c['hits']


def test_system_map_does_not_modify_the_tree(svc, tree):
    before = sorted(p.relative_to(tree).as_posix() for p in tree.rglob('*'))
    svc.system_map(tree)
    after = sorted(p.relative_to(tree).as_posix() for p in tree.rglob('*'))
    assert before == after


def test_system_map_on_an_empty_folder_is_empty_not_an_error(svc, tmp_path):
    empty = tmp_path / 'nothing'
    empty.mkdir()
    m = svc.system_map(empty)
    assert m['cards'] == []
    assert m['file_count'] == 0


# ── HTTP surface ──────────────────────────────────────────────────────────────
class TestRestructureEndpoints:
    def test_inventory_endpoint_classifies(self, client):
        r = client.get('/api/icm/restructure/inventory?path=.')
        assert r.status_code == 200
        body = r.json()
        assert body['ok'] is True
        assert isinstance(body['items'], list)
        for it in body['items'][:20]:
            assert it['role'] in ('catalog', 'contract', 'factory', 'product', 'dead')
            assert it['universe'] in ('live', 'leftover', 'ghost')

    def test_audit_path_cannot_escape_the_data_dir(self, client):
        """This reads file CONTENTS back to the caller."""
        for bad in ('../../../../etc', '/etc', '../../..'):
            r = client.get(f'/api/icm/restructure/inventory?path={bad}')
            assert r.status_code in (400, 404), bad
            if r.status_code == 200:  # pragma: no cover
                assert '/etc' not in r.json()['root']

    def test_system_map_endpoint_returns_cards(self, client):
        r = client.get('/api/icm/restructure/system-map?path=.')
        assert r.status_code == 200
        assert isinstance(r.json()['cards'], list)

    def test_system_map_limit_is_clamped(self, client):
        r = client.get('/api/icm/restructure/system-map?path=.&limit=99999')
        assert r.status_code == 200
        assert len(r.json()['cards']) <= 200

    def test_plan_then_apply_requires_approval(self, client):
        made = client.post('/api/icm/restructure/plan', json={'path': '.', 'label': 'uat'})
        assert made.status_code == 200
        pid = made.json()['plan']['plan_id']

        refused = client.post('/api/icm/restructure/apply', json={'plan_id': pid})
        assert refused.status_code == 400
        assert 'approval' in str(refused.json())

    def test_a_truthy_string_does_not_count_as_approval(self, client):
        """`approved: "no"` is truthy in Python. It must not approve anything."""
        pid = client.post('/api/icm/restructure/plan',
                          json={'path': '.'}).json()['plan']['plan_id']
        r = client.post('/api/icm/restructure/apply',
                        json={'plan_id': pid, 'approved': 'no'})
        assert r.status_code == 400
        assert 'approval' in str(r.json())

    def test_apply_without_a_plan_id_is_rejected(self, client):
        r = client.post('/api/icm/restructure/apply', json={'approved': True})
        assert r.status_code == 422

    def test_unknown_plan_is_a_404(self, client):
        assert client.get('/api/icm/restructure/plans/0123456789abcdef').status_code == 404

    def test_plans_list_endpoint(self, client):
        r = client.get('/api/icm/restructure/plans')
        assert r.status_code == 200
        assert isinstance(r.json()['plans'], list)
