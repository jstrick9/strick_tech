"""Module 37 — typed frontmatter: generated indexes (G5) and live queries (G7).

Measured before this module existed:

    form              FILE-MAP   .md files   with frontmatter
    pipeline          NO           6            0
    umbrella          NO          16            0
    record_library    NO          11            3
    knowledge_bundle  NO           7            2
    context_map       yes          9            4
    system_map        NO           8            3

G5: five of six forms had no generated index, so an agent had to crawl.
G7: the frontmatter was WRITTEN and never READ. The context map even shipped a
dashboards/00-tracker.md containing a prose description of a query --

    "Sort process nodes by value desc, then pain desc, where ai-level is
     L0 or L1."

-- with nothing that ran it. A dashboard that describes its own query without
executing it looks like a working feature and is not one.

The load-bearing tests: every form gets a map; the map is generated (so it
cannot drift); the reads are bounded (an index must not cost the bodies it
indexes); and `access_tier` is ENFORCED on every path that returns nodes,
because a field labelling sensitivity that no reader honours is a false
assurance.
"""

from __future__ import annotations

import importlib

import pytest


@pytest.fixture()
def env(tmp_path, monkeypatch):
    monkeypatch.setenv('AGENTIC_OS_DATA_DIR', str(tmp_path))
    from backend.services import icm as icm_mod

    importlib.reload(icm_mod)
    from backend.services import icm_forms as forms_mod

    importlib.reload(forms_mod)
    from backend.services import icm_frontmatter as fm_mod

    importlib.reload(fm_mod)
    return icm_mod, forms_mod, fm_mod


@pytest.fixture()
def cmap(env):
    """A context map with real, scored process nodes."""
    icm, forms, fm = env
    ws = icm.WORKSPACES_DIR / 'cm'
    forms.scaffold_form(ws, forms.CONTEXT_MAP, 'cm', '', ['marketing'])
    p = ws / 'teams' / 'marketing' / 'processes'
    p.mkdir(parents=True, exist_ok=True)
    (p / 'lead-triage.md').write_text(
        '---\ntype: process\nowner: Sam\nai-level: L0\nvalue: 5\npain: 4\n---\n\n# Lead triage\n',
        encoding='utf-8')
    (p / 'invoicing.md').write_text(
        '---\ntype: process\nowner: Dana\nai-level: L1\nvalue: 3\npain: 5\n---\n\n# Invoicing\n',
        encoding='utf-8')
    (p / 'already-automated.md').write_text(
        '---\ntype: process\nowner: Kim\nai-level: L3\nvalue: 5\npain: 5\n---\n\n# Done\n',
        encoding='utf-8')
    return ws


# ── parsing ───────────────────────────────────────────────────────────────────
def test_frontmatter_values_are_typed_not_strings(env):
    """'10' < '9' is true for strings and wrong for scores."""
    _, _, fm = env
    meta = fm.parse_head('---\nvalue: 10\npain: 9\nflag: true\n---\nbody')
    assert meta['value'] == 10
    assert meta['value'] > meta['pain']
    assert meta['flag'] is True


def test_inline_lists_parse(env):
    _, _, fm = env
    assert fm.parse_head('---\ntags: [a, b]\n---\n')['tags'] == ['a', 'b']


def test_a_file_with_no_frontmatter_parses_to_empty(env):
    _, _, fm = env
    assert fm.parse_head('# Just a heading\n') == {}


def test_an_unterminated_block_is_not_treated_as_frontmatter(env):
    _, _, fm = env
    assert fm.parse_head('---\ntype: process\n# never closed\n') == {}


# ── G5: every form gets a generated map ───────────────────────────────────────
def test_every_form_generates_a_file_map(env):
    """Five of six forms shipped without one."""
    icm, forms, fm = env
    for form in forms.ALL_FORMS:
        ws = icm.WORKSPACES_DIR / form.replace('_', '-')
        forms.scaffold_form(ws, form, form, '', ['alpha', 'beta'])
        assert (ws / 'FILE-MAP.md').is_file(), form


def test_every_form_still_passes_its_walk_test(env):
    """Adding the map must not break any form's validation."""
    icm, forms, _ = env
    for form in forms.ALL_FORMS:
        ws = icm.WORKSPACES_DIR / (form.replace('_', '-') + '-v')
        forms.scaffold_form(ws, form, form, '', ['alpha'])
        assert icm.validate(ws)['ok'], (form, icm.validate(ws)['errors'])


def test_the_map_says_it_is_generated(env, cmap):
    """The one thing that breaks a scripted index is a hand edit."""
    _, _, fm = env
    body = fm.generate_file_map(cmap)
    assert 'GENERATED' in body
    assert 'do not hand-edit' in body.lower()


def test_the_map_never_indexes_itself(env, cmap):
    _, _, fm = env
    fm.generate_file_map(cmap)
    fm.generate_file_map(cmap)
    assert '`FILE-MAP.md`' not in (cmap / 'FILE-MAP.md').read_text(encoding='utf-8')


def test_the_map_reflects_new_files_on_rebuild(env, cmap):
    """A hand-curated index drifts; a scripted one cannot."""
    _, _, fm = env
    fm.generate_file_map(cmap)
    assert 'later-note.md' not in (cmap / 'FILE-MAP.md').read_text(encoding='utf-8')
    (cmap / 'teams' / 'later-note.md').write_text(
        '---\ntype: data\n---\n\n# Later\n', encoding='utf-8')
    fm.generate_file_map(cmap)
    body = (cmap / 'FILE-MAP.md').read_text(encoding='utf-8')
    assert 'teams/later-note.md' in body
    assert '| data |' in body


def test_the_map_records_type_and_access_tier(env, cmap):
    _, _, fm = env
    body = fm.generate_file_map(cmap)
    assert 'process' in body
    assert 'public' in body


def test_indexing_reads_a_bounded_head_not_whole_bodies(env, cmap):
    """An index must not cost the bodies it indexes.

    Counts bytes pulled off disk, not output shape: parsing a fully-read file
    and discarding the body produces identical output to a bounded read, so an
    output assertion cannot tell the two apart.
    """
    import pathlib

    _, _, fm = env
    (cmap / 'huge.md').write_text(
        '---\ntype: data\n---\n\n' + ('PAYLOAD ' * 20_000), encoding='utf-8')

    real_open = pathlib.Path.open
    unbounded: list[int] = []

    class _Counted:
        def __init__(self, fh, name):
            self._fh, self._name = fh, name

        def read(self, n=-1):
            data = self._fh.read(n)
            if self._name.endswith('.md') and (n is None or n < 0):
                unbounded.append(len(data))
            return data

        def __enter__(self):
            return self

        def __exit__(self, *a):
            return self._fh.__exit__(*a)

    monkey = pytest.MonkeyPatch()
    monkey.setattr(pathlib.Path, 'open', lambda self, *a, **k: _Counted(real_open(self, *a, **k), self.name))
    try:
        nodes = fm.index_workspace(cmap)
    finally:
        monkey.undo()

    assert any(n['path'] == 'huge.md' for n in nodes)
    assert unbounded == [], f'index read {sum(unbounded)} bytes of bodies'


def test_frontmatter_spanning_the_head_bound_still_parses(env, cmap):
    """A truncated head can cut the closing '---'.

    Without re-terminating the block the parser sees unclosed frontmatter,
    returns nothing, and the file silently drops out of the typed index -- a
    large node vanishing from the catalogue with no error anywhere. Nothing
    exercised that path, so the revert proof found the guard untested.
    """
    _, _, fm = env
    padded = ('---\ntype: data\nlayer: A\n'
              + ('# padding comment line\n' * 400)
              + '---\n\nbody\n')
    (cmap / 'wide-head.md').write_text(padded, encoding='utf-8')
    assert len(padded.encode()) > fm.MAX_HEAD_BYTES

    node = next((n for n in fm.index_workspace(cmap) if n['path'] == 'wide-head.md'), None)
    assert node is not None, 'the file must still appear in the index'
    assert node['has_frontmatter'] is True, 'its frontmatter must still parse'
    assert node['type'] == 'data'


def test_a_body_larger_than_the_head_bound_still_indexes(env, cmap):
    """The bound must not hide files whose frontmatter it can still reach."""
    _, _, fm = env
    (cmap / 'big.md').write_text(
        '---\ntype: data\n---\n\n' + 'X' * (fm.MAX_HEAD_BYTES * 10), encoding='utf-8')
    node = next(n for n in fm.index_workspace(cmap) if n['path'] == 'big.md')
    assert node['type'] == 'data'


def test_rebuild_all_covers_every_workspace(env):
    icm, forms, fm = env
    for name in ('one', 'two'):
        forms.scaffold_form(icm.WORKSPACES_DIR / name, forms.PIPELINE, name, '', ['a'])
    result = fm.rebuild_all()
    assert result['rebuilt'] >= 2
    for name in ('one', 'two'):
        assert (icm.WORKSPACES_DIR / name / 'FILE-MAP.md').is_file()


# ── G7: the query actually runs ───────────────────────────────────────────────
def test_nodes_can_be_queried_by_type(env, cmap):
    _, _, fm = env
    got = fm.query(cmap, node_type='process')
    assert got['matched'] == 3
    assert all(n['type'] == 'process' for n in got['nodes'])


def test_nodes_can_be_sorted_by_a_numeric_field(env, cmap):
    _, _, fm = env
    got = fm.query(cmap, node_type='process', sort_by='value')
    values = [n['fields']['value'] for n in got['nodes']]
    assert values == sorted(values, reverse=True)


def test_nodes_missing_the_sort_field_sort_last(env, cmap):
    """Treating a missing score as zero ranks it ABOVE a real low score.

    An earlier version of this test used a node named 'unscored', which sorts
    last alphabetically anyway -- so it passed whether the missing-field rule
    worked or not, and the revert proof caught that. This uses a node whose
    name sorts FIRST with no score, beside one carrying the lowest possible
    real score: only the rule can order them correctly.
    """
    _, _, fm = env
    procs = cmap / 'teams' / 'marketing' / 'processes'
    (procs / 'aaa-no-score.md').write_text(
        '---\ntype: process\nowner: Nobody\n---\n\n# No score\n', encoding='utf-8')
    (procs / 'zzz-low-score.md').write_text(
        '---\ntype: process\nowner: Someone\nvalue: 1\n---\n\n# Low\n', encoding='utf-8')

    names = [n['name'] for n in fm.query(cmap, node_type='process', sort_by='value')['nodes']]
    assert names[-1] == 'aaa-no-score', names
    assert names.index('zzz-low-score') < names.index('aaa-no-score'), (
        'a real score of 1 must outrank no score at all')


def test_the_automation_query_from_the_canon_is_executed(env, cmap):
    """"Sort process nodes by value desc, then pain desc, where ai-level is
    L0 or L1" -- previously prose in a markdown file, now a result.
    """
    _, _, fm = env
    got = fm.automation_candidates(cmap)
    names = [c['name'] for c in got['candidates']]
    assert names == ['lead-triage', 'invoicing'], names
    assert 'already-automated' not in names, 'L3 is already automated'


def test_every_candidate_explains_its_ranking(env, cmap):
    """A ranking you cannot argue with is a ranking nobody trusts."""
    _, _, fm = env
    for c in fm.automation_candidates(cmap)['candidates']:
        assert c['why'].strip()
        assert str(int(c['value'])) in c['why']


# ── access tier is enforced everywhere, not just in query() ───────────────────
def test_query_withholds_nodes_above_the_access_ceiling(env, cmap):
    _, _, fm = env
    (cmap / 'teams' / 'marketing' / 'processes' / 'secret.md').write_text(
        '---\ntype: process\naccess_tier: secret\nvalue: 9\npain: 9\n---\n\n# Secret\n',
        encoding='utf-8')
    got = fm.query(cmap, node_type='process', max_access_tier='internal')
    assert got['withheld_by_access_tier'] == 1
    assert all('secret' not in n['name'] for n in got['nodes'])


def test_withheld_nodes_are_reported_not_silently_dropped(env, cmap):
    """A query that silently drops private notes looks like one that found none."""
    _, _, fm = env
    (cmap / 'private.md').write_text(
        '---\ntype: data\naccess_tier: private\n---\n\n# P\n', encoding='utf-8')
    got = fm.query(cmap, node_type='data', max_access_tier='public')
    assert got['withheld_by_access_tier'] >= 1


def test_the_automation_dashboard_also_enforces_the_access_tier(env, cmap):
    """Found live: a `secret` node came TOP of the automation table.

    The tier check lived only in query() while this path read the index
    directly. A gate applied on one route and not the other is not a gate --
    and a dashboard is exactly the surface someone screen-shares.
    """
    _, _, fm = env
    (cmap / 'teams' / 'marketing' / 'processes' / 'secret.md').write_text(
        '---\ntype: process\naccess_tier: secret\nvalue: 9\npain: 9\n---\n\n# Secret\n',
        encoding='utf-8')
    got = fm.automation_candidates(cmap)
    assert all('secret' not in c['name'] for c in got['candidates']), got['candidates']
    assert got['withheld_by_access_tier'] == 1


def test_an_unknown_access_tier_is_treated_as_public_not_trusted(env, cmap):
    _, _, fm = env
    (cmap / 'odd.md').write_text(
        '---\ntype: data\naccess_tier: whatever\n---\n\n# Odd\n', encoding='utf-8')
    node = next(n for n in fm.index_workspace(cmap) if n['path'] == 'odd.md')
    assert node['access_tier'] == 'public'


# ── the rendered tracker carries results, not a description ───────────────────
def test_the_tracker_contains_real_rows(env, cmap):
    _, _, fm = env
    body = fm.render_tracker(cmap)
    assert 'lead-triage' in body
    assert 'GENERATED' in body


def test_the_tracker_distinguishes_no_data_from_nothing_qualifying(env):
    """"No results" that could mean either is not an answer."""
    icm, forms, fm = env
    ws = icm.WORKSPACES_DIR / 'empty-cm'
    forms.scaffold_form(ws, forms.CONTEXT_MAP, 'empty', '', ['team'])
    assert 'No process nodes carry' in fm.render_tracker(ws)

    p = ws / 'teams' / 'team' / 'processes'
    p.mkdir(parents=True, exist_ok=True)
    (p / 'done.md').write_text(
        '---\ntype: process\nai-level: L3\nvalue: 5\npain: 5\n---\n\n# Done\n', encoding='utf-8')
    assert 'already at ai-level L2' in fm.render_tracker(ws)


def test_the_dashboard_counts_typed_and_untyped(env, cmap):
    _, _, fm = env
    d = fm.dashboard(cmap)
    assert d['files'] == d['typed'] + d['untyped']
    assert d['by_type']['process'] == 3


# ── HTTP surface ──────────────────────────────────────────────────────────────
class TestFrontmatterEndpoints:
    def _make(self, client):
        import uuid

        name = 'fm-' + uuid.uuid4().hex[:8]
        r = client.post('/api/icm/workspaces', json={'name': name, 'stages': ['a', 'b']})
        assert r.status_code == 200, r.text
        return name

    def test_nodes_endpoint_returns_typed_nodes(self, client):
        name = self._make(client)
        client.put(f'/api/icm/workspaces/{name}/file',
                   json={'path': 'notes/thing.md',
                         'content': '---\ntype: data\nvalue: 4\n---\n\n# Thing\n'})
        r = client.get(f'/api/icm/workspaces/{name}/nodes?type=data')
        assert r.status_code == 200, r.text
        assert r.json()['matched'] == 1

    def test_nodes_endpoint_enforces_the_access_tier(self, client):
        name = self._make(client)
        client.put(f'/api/icm/workspaces/{name}/file',
                   json={'path': 'notes/secret.md',
                         'content': '---\ntype: data\naccess_tier: secret\n---\n\n# S\n'})
        r = client.get(f'/api/icm/workspaces/{name}/nodes?type=data&max_access_tier=public')
        assert r.json()['matched'] == 0
        assert r.json()['withheld_by_access_tier'] == 1

    def test_dashboard_endpoint(self, client):
        name = self._make(client)
        r = client.get(f'/api/icm/workspaces/{name}/dashboard')
        assert r.status_code == 200
        assert 'automation' in r.json()

    def test_rebuild_writes_both_generated_files(self, client):
        name = self._make(client)
        r = client.post(f'/api/icm/workspaces/{name}/index/rebuild')
        assert r.status_code == 200, r.text
        assert r.json()['file_map_lines'] > 0
        assert r.json()['tracker_lines'] > 0

    def test_rebuild_all_endpoint(self, client):
        self._make(client)
        r = client.post('/api/icm/index/rebuild-all')
        assert r.status_code == 200
        assert r.json()['rebuilt'] >= 1

    def test_an_unknown_workspace_is_404(self, client):
        assert client.get('/api/icm/workspaces/not-real-xyz/nodes').status_code == 404
        assert client.get('/api/icm/workspaces/not-real-xyz/dashboard').status_code == 404
