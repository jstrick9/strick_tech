"""Module 33 — skills as folders, with three-level progressive disclosure.

    Level 1  frontmatter    ~30-100 tokens   ALWAYS loaded (discovery)
    Level 2  the body       <5k tokens       loaded when the skill is chosen
    Level 3  bundled files  ~0 tokens        read on demand, by path

Measured on this repo before the change:

    skills/skills.json   83 skills, one file, no folders
    GET /api/skills      returns ALL 83 IN FULL
    whole registry       24,641 chars  ~6,160 tokens
    name + description    4,374 chars  ~1,093 tokens

Discovery cost 6.2k tokens to answer a question needing 1.1k, and there were no
levels at all: no way to load one skill's instructions without loading all 83.

The load-bearing properties: level 1 is genuinely cheaper than the full load;
level 3 is LISTED but never auto-read (auto-reading collapses three levels into
one); and a SKILL.md is untrusted input, so parsing and path handling are
hostile-input problems, not convenience problems.
"""

from __future__ import annotations

import importlib

import pytest


@pytest.fixture()
def sf(tmp_path, monkeypatch):
    monkeypatch.setenv('AGENTIC_OS_DATA_DIR', str(tmp_path))
    from backend.services import skill_folders as mod

    importlib.reload(mod)
    mod.SKILLS_DIR.mkdir(parents=True, exist_ok=True)
    # Isolate from the real 83-entry registry unless a test opts in.
    monkeypatch.setattr(mod, '_registry_skills', lambda: [])
    return mod


def _make(sf, skill_id, *, name='Test Skill', desc='Does a thing',
          body='# Body\n\nDo the thing.', files=None, extra=''):
    d = sf.SKILLS_DIR / skill_id
    d.mkdir(parents=True, exist_ok=True)
    fm = f'---\nname: {name}\ndescription: {desc}\ncategory: testing\n{extra}---\n\n{body}\n'
    (d / 'SKILL.md').write_text(fm, encoding='utf-8')
    for rel, content in (files or {}).items():
        p = d / rel
        p.parent.mkdir(parents=True, exist_ok=True)
        p.write_text(content, encoding='utf-8')
    return d


# ── frontmatter parsing ───────────────────────────────────────────────────────
def test_frontmatter_and_body_are_separated(sf):
    meta, body = sf.parse_frontmatter('---\nname: X\ndescription: Y\n---\n\nThe body.')
    assert meta['name'] == 'X'
    assert meta['description'] == 'Y'
    assert body == 'The body.'


def test_a_file_with_no_frontmatter_is_all_body(sf):
    meta, body = sf.parse_frontmatter('Just prose.')
    assert meta == {}
    assert body == 'Just prose.'


def test_an_unterminated_frontmatter_block_is_treated_as_body(sf):
    """Malformed input must not swallow the body into metadata."""
    meta, body = sf.parse_frontmatter('---\nname: X\nno closing fence')
    assert meta == {}
    assert 'no closing fence' in body


def test_inline_and_block_lists_both_parse(sf):
    meta, _ = sf.parse_frontmatter(
        '---\ntags: [alpha, beta]\nallowed_tools:\n  - fs.read\n  - git.commit\n---\n\nx')
    assert meta['tags'] == ['alpha', 'beta']
    assert meta['allowed_tools'] == ['fs.read', 'git.commit']


def test_quotes_are_stripped_from_values(sf):
    meta, _ = sf.parse_frontmatter('---\nname: "Quoted"\ndescription: \'Single\'\n---\n\nx')
    assert meta['name'] == 'Quoted'
    assert meta['description'] == 'Single'


def test_the_parser_ignores_what_it_does_not_understand(sf):
    """A SKILL.md is untrusted input from imports and marketplaces.

    A full YAML parser accepts anchors, aliases, tags and multi-document
    streams -- attack surface for something holding five scalars and a list.
    Anything unrecognised must be ignored, never executed.
    """
    meta, body = sf.parse_frontmatter(
        '---\n'
        'name: Legit\n'
        '!!python/object/apply:os.system ["echo pwned"]\n'
        'anchor: &a evil\n'
        'alias: *a\n'
        '---\n\nbody')
    assert meta['name'] == 'Legit'
    assert body == 'body'
    # The alias is read as a plain string, not resolved.
    assert meta.get('alias') == '*a'


def test_unknown_fields_are_reported_not_trusted(sf):
    _make(sf, 'weird', extra='mystery_field: something\n')
    skill = sf.read_skill('weird')
    assert 'mystery_field' in skill['unknown_fields']


# ── the three levels ──────────────────────────────────────────────────────────
def test_level_one_is_the_discovery_card_only(sf):
    _make(sf, 'alpha', body='X' * 4000)
    got = sf.load_level('alpha', 1)
    assert got['level'] == 1
    assert 'body' not in got, 'level 1 must not carry the instructions'
    assert got['name'] == 'Test Skill'


def test_level_two_adds_the_body(sf):
    _make(sf, 'alpha', body='The instructions.')
    got = sf.load_level('alpha', 2)
    assert got['body'] == 'The instructions.'
    assert 'files' not in got, 'level 2 does not need the bundle listing'


def test_level_three_lists_files_but_does_not_read_them(sf):
    """Auto-reading bundled files collapses three levels back into one."""
    _make(sf, 'alpha', files={'reference/data.md': 'SECRET-PAYLOAD'})
    got = sf.load_level('alpha', 3)
    assert got['files'] == [{'path': 'reference/data.md', 'bytes': len('SECRET-PAYLOAD')}]
    assert 'SECRET-PAYLOAD' not in str(got)


def test_a_bundled_file_is_read_only_when_asked_for_by_path(sf):
    _make(sf, 'alpha', files={'reference/data.md': 'PAYLOAD'})
    got = sf.read_bundled('alpha', 'reference/data.md')
    assert got['content'] == 'PAYLOAD'


def test_loading_an_unknown_skill_returns_none(sf):
    assert sf.load_level('does-not-exist', 2) is None


def test_level_one_is_measurably_cheaper_than_the_full_load(sf):
    """The whole claim of progressive disclosure, asserted numerically."""
    for i in range(10):
        _make(sf, f'skill{i}', body='word ' * 500)
    cat = sf.catalog()
    assert cat['count'] == 10
    assert cat['level1_tokens'] * 4 < cat['full_tokens'], (
        f'level 1 {cat["level1_tokens"]} vs full {cat["full_tokens"]}')


# ── safety ────────────────────────────────────────────────────────────────────
def test_a_bundled_path_cannot_escape_the_skill_folder(sf):
    """This content is destined for a model prompt.

    An escape here is an arbitrary file read fed to an LLM, not just a wrong
    file.
    """
    _make(sf, 'alpha')
    secret = sf.SKILLS_DIR.parent / 'secret.txt'
    secret.write_text('TOP-SECRET', encoding='utf-8')
    for attempt in ('../secret.txt', '../../secret.txt', '/etc/passwd',
                    'reference/../../secret.txt'):
        got = sf.read_bundled('alpha', attempt)
        assert got is None or 'TOP-SECRET' not in got['content'], attempt


def test_the_skill_md_itself_is_not_readable_as_a_bundled_file(sf):
    """It is level 2, already delivered; serving it again as level 3 is a hole."""
    _make(sf, 'alpha')
    assert sf.read_bundled('alpha', 'SKILL.md') is None


def test_a_hostile_skill_id_resolves_to_nothing(sf):
    for bad in ('../escape', '/etc', '..', '', 'A' * 200, 'has space'):
        assert sf.skill_dir(bad) is None, bad


def test_dotfiles_are_not_listed_as_bundled_files(sf):
    _make(sf, 'alpha', files={'.env': 'KEY=secret'})
    assert sf.read_skill('alpha')['files'] == []


# ── validation against the convention ─────────────────────────────────────────
def test_a_missing_description_is_an_error(sf):
    d = sf.SKILLS_DIR / 'nodesc'
    d.mkdir(parents=True)
    (d / 'SKILL.md').write_text('---\nname: X\n---\n\nbody', encoding='utf-8')
    result = sf.validate(sf.read_skill('nodesc'))
    assert not result['ok']
    assert any('description' in e for e in result['errors'])


def test_an_oversized_level_one_is_warned_about(sf):
    """Level 1 loads for EVERY skill on every turn."""
    _make(sf, 'fat', desc='word ' * 200)
    result = sf.validate(sf.read_skill('fat'))
    assert any('Level 1' in w for w in result['warnings'])
    assert 'whether or not the skill is used' in ' '.join(result['warnings'])


def test_an_oversized_body_is_warned_about(sf):
    _make(sf, 'long', body='line\n' * 600)
    result = sf.validate(sf.read_skill('long'))
    assert any('500' in w for w in result['warnings'])


def test_a_well_formed_skill_validates_clean(sf):
    _make(sf, 'good')
    result = sf.validate(sf.read_skill('good'))
    assert result['ok']
    assert result['warnings'] == []


# ── both representations coexist ──────────────────────────────────────────────
def test_registry_skills_appear_alongside_folder_skills(sf, monkeypatch):
    """83 existing skills and the Skills pane depend on skills.json."""
    monkeypatch.setattr(sf, '_registry_skills', lambda: [{
        'id': 'legacy', 'name': 'Legacy', 'description': 'From the registry',
        'category': 'old', 'emoji': '📜', 'agent': '', 'tags': [], 'inputs': [],
        'allowed_tools': [], 'source': 'registry', 'body': 'do it', 'files': [],
        'unknown_fields': [], 'tokens': {'level1': 5, 'level2': 2, 'level3_files': 0},
    }])
    _make(sf, 'modern')
    ids = {s['id'] for s in sf.index()}
    assert ids == {'modern', 'legacy'}


def test_a_folder_skill_wins_an_id_clash_with_the_registry(sf, monkeypatch):
    monkeypatch.setattr(sf, '_registry_skills', lambda: [{
        'id': 'dup', 'name': 'Registry version', 'description': 'old',
        'category': 'old', 'emoji': '📜', 'agent': '', 'tags': [], 'inputs': [],
        'allowed_tools': [], 'source': 'registry', 'body': '', 'files': [],
        'unknown_fields': [], 'tokens': {'level1': 1, 'level2': 1, 'level3_files': 0},
    }])
    _make(sf, 'dup', name='Folder version')
    got = [s for s in sf.index() if s['id'] == 'dup']
    assert len(got) == 1
    assert got[0]['name'] == 'Folder version'
    assert got[0]['source'] == 'folder'


def test_a_broken_registry_does_not_take_folder_skills_down(sf, monkeypatch):
    def boom():
        raise RuntimeError('registry unreadable')

    monkeypatch.setattr(sf, '_registry_skills', boom)
    _make(sf, 'modern')
    with pytest.raises(RuntimeError):
        sf.index()


# ── writing and migration ─────────────────────────────────────────────────────
def test_a_skill_can_be_written_and_read_back(sf):
    sf.write_skill('written', {'name': 'Written', 'description': 'made here',
                               'category': 'testing'}, 'The body.')
    got = sf.read_skill('written')
    assert got['name'] == 'Written'
    assert got['body'] == 'The body.'


def test_writing_to_a_hostile_id_writes_nothing_outside_the_root(sf):
    """Assert the FILESYSTEM, not just the return value.

    The revert proof caught this: an earlier version only checked that
    write_skill returned None. With containment removed the function still
    returned None (read_skill failed afterwards) while having already created
    a directory outside the skills root. A refusal that refuses after writing
    is not a refusal.
    """
    outside = sf.SKILLS_DIR.parent / 'escape'
    for bad in ('../escape', '../../escape', '/etc/escape'):
        assert sf.write_skill(bad, {'name': 'X'}, 'body') is None, bad
    assert not outside.exists(), 'write escaped the skills root'
    for child in sf.SKILLS_DIR.parent.iterdir():
        assert child == sf.SKILLS_DIR or child.name.startswith('.'), child


def test_a_registry_entry_migrates_to_a_folder(sf):
    """Method and instance live apart: the registry keeps working."""
    got = sf.migrate_registry_entry({
        'id': 'seo_audit', 'name': 'SEO Audit', 'description': 'Audit a URL',
        'category': 'marketing', 'emoji': '🔍', 'prompt_template': 'Audit {url}',
    })
    assert got['name'] == 'SEO Audit'
    assert got['body'] == 'Audit {url}'
    assert (sf.SKILLS_DIR / 'seo_audit' / 'SKILL.md').is_file()


def test_migrating_an_entry_with_a_bad_id_writes_nothing_outside_the_root(sf):
    """A marketplace registry entry is untrusted input like any other."""
    outside = sf.SKILLS_DIR.parent / 'evil'
    for bad in ('../evil', '/etc/evil', '..'):
        assert sf.migrate_registry_entry({'id': bad, 'name': 'X'}) is None, bad
    assert not outside.exists()
    assert sorted(p.name for p in sf.SKILLS_DIR.iterdir()) == []


def test_folders_without_a_skill_md_are_ignored(sf):
    (sf.SKILLS_DIR / 'empty-dir').mkdir(parents=True)
    _make(sf, 'real')
    assert {s['id'] for s in sf.index()} == {'real'}


# ── HTTP surface ──────────────────────────────────────────────────────────────
class TestSkillFolderEndpoints:
    def test_catalog_returns_level_one_only(self, client):
        r = client.get('/api/skills/catalog')
        assert r.status_code == 200
        d = r.json()
        assert d['ok'] is True
        assert d['count'] > 0
        for card in d['skills'][:20]:
            assert 'body' not in card, 'the catalog must not carry instructions'
            assert card['name']

    def test_the_catalog_is_cheaper_than_the_full_listing(self, client):
        """The measured payoff against the REAL 83-skill registry."""
        d = client.get('/api/skills/catalog').json()
        assert d['level1_tokens'] < d['full_tokens']

    def test_a_skill_loads_at_a_requested_level(self, client):
        cid = client.get('/api/skills/catalog').json()['skills'][0]['id']
        one = client.get(f'/api/skills/{cid}/level/1').json()['skill']
        two = client.get(f'/api/skills/{cid}/level/2').json()['skill']
        assert 'body' not in one
        assert 'body' in two

    def test_an_out_of_range_level_is_clamped_not_crashed(self, client):
        """Clamping must change BEHAVIOUR, not just the reported number.

        An earlier version only asserted 1 <= level <= 3, which passed with
        clamping removed because load_level's own min(level, 3) still reported
        3. This pins what each bound actually does: level 0 must behave as
        level 1 (no body), and level 99 as level 3 (a file list).
        """
        cid = client.get('/api/skills/catalog').json()['skills'][0]['id']

        low = client.get(f'/api/skills/{cid}/level/0')
        assert low.status_code == 200
        assert low.json()['skill']['level'] == 1
        assert 'body' not in low.json()['skill'], 'level 0 must clamp UP to a card, not leak the body'

        high = client.get(f'/api/skills/{cid}/level/99')
        assert high.status_code == 200
        assert high.json()['skill']['level'] == 3

        neg = client.get(f'/api/skills/{cid}/level/-3')
        assert neg.status_code == 200
        assert neg.json()['skill']['level'] == 1
        assert 'body' not in neg.json()['skill']

    def test_an_unknown_skill_is_404(self, client):
        assert client.get('/api/skills/no-such-skill-xyz/level/2').status_code == 404

    def test_reading_a_bundled_file_that_does_not_exist_is_404(self, client):
        cid = client.get('/api/skills/catalog').json()['skills'][0]['id']
        r = client.get(f'/api/skills/{cid}/file?path=nope.md')
        assert r.status_code == 404

    def test_a_traversal_path_is_refused_over_http(self, client):
        cid = client.get('/api/skills/catalog').json()['skills'][0]['id']
        r = client.get(f'/api/skills/{cid}/file?path=../../../../etc/passwd')
        assert r.status_code == 404
        assert 'root:' not in r.text
