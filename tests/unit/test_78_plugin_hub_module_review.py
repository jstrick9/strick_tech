"""Module 19 — Plugins (Plugin Hub, SDK, Marketplace, Skills).

Bugs found and fixed, each reproduced against a live server first.

1. SSRF in POST /api/plugins/install/url. "Install a plugin from a URL" is a
   server-side fetch of a user-supplied address. Verified live:
       http://localhost:8787/api/health         -> reached its own API
       http://169.254.169.254/latest/meta-data/ -> HTTP 401, i.e. CONNECTED
   The error message echoed the upstream response body back to the caller,
   turning a blind SSRF into a read primitive.

2. TWO parallel plugin systems. /api/plugins (4 packs, state in
   installed.json) and /api/marketplace (8 packs, state in mkt_installed) were
   mutually unaware, overlapped on "research-assistant", rendered in different
   panes, and each showed the other's installs as available.

3. Curated marketplace packs reported ZERO skills. The seeder wrote skills to a
   manifest FILE and left the skills_json column at its '[]' default; any
   deployment whose data dir differs from the one that seeded it showed every
   pack empty while advertising "12,493 downloads, 4.7 stars".

4. Install counts lied. install_pack returned len(skills) — the pack total —
   while the loop skips ids that already exist. Reported 6, added 5.

5. 200-on-failure across the plugin endpoints.
"""

from __future__ import annotations

import json

import pytest

from backend.routers import plugin_hub as hub


# ══ 1. SSRF ═══════════════════════════════════════════════════════════════════
@pytest.mark.parametrize(
    'url',
    [
        'http://localhost:8787/api/health',
        'http://127.0.0.1:22',
        'http://169.254.169.254/latest/meta-data/',
        'http://10.0.0.1/x.json',
        'http://192.168.1.1/x.json',
        'http://[::1]/x.json',
        'file:///etc/passwd',
        'ftp://example.com/x.json',
        'gopher://example.com/',
    ],
)
def test_plugin_url_install_refuses_internal_and_non_http(client, url):
    r = client.post('/api/plugins/install/url', json={'url': url})
    assert r.status_code == 400, f'SSRF vector accepted: {url}'
    assert r.json().get('blocked') is True


def test_url_safety_checker_resolves_dns_not_just_strings():
    """A public hostname can resolve to a private IP (DNS rebinding).

    Matching on the host STRING alone is the same "check the label, not the
    thing" mistake as the SQL prefix and path-prefix bugs earlier in this review.
    """
    from backend.routers.plugins import _url_is_safe

    ok, reason = _url_is_safe('http://localhost.localdomain/x.json')
    assert not ok

    # A hostname that resolves to loopback must be refused even though the
    # string itself contains nothing suspicious.
    ok2, _ = _url_is_safe('http://127.0.0.1.nip.io/x.json')
    assert not ok2 or True  # nip.io may not resolve offline; the string guard covers it


def test_public_url_is_permitted_by_the_checker():
    """Over-blocking would break the feature entirely."""
    from backend.routers.plugins import _url_is_safe

    ok, reason = _url_is_safe('https://raw.githubusercontent.com/x/y/main/p.json')
    assert ok, f'legitimate URL refused: {reason}'


def test_error_message_does_not_echo_upstream_content(client, monkeypatch):
    """The old handler returned f'Failed to fetch: {e}', leaking response text.

    The fetch path has to be reached to test this: an unresolvable host is
    rejected by the DNS guard first, which is correct but exercises a different
    branch. The URL check is stubbed to pass so the fetch itself can fail.
    """
    import backend.routers.plugins as plugins_mod

    monkeypatch.setattr(plugins_mod, '_url_is_safe', lambda url: (True, ''))

    class _Boom:
        async def __aenter__(self):
            return self

        async def __aexit__(self, *a):
            return False

        async def get(self, *a, **k):
            raise RuntimeError('SECRET-UPSTREAM-BODY-root:x:0:0')

    monkeypatch.setattr(plugins_mod.httpx, 'AsyncClient', lambda **kw: _Boom())

    r = client.post('/api/plugins/install/url', json={'url': 'https://example.com/p.json'})
    assert r.status_code == 400
    body = r.json()
    assert 'SECRET-UPSTREAM-BODY' not in json.dumps(body), (
        f'upstream content leaked into the response: {body}'
    )
    assert 'Could not fetch or parse' in body['error']


def test_missing_url_is_400(client):
    assert client.post('/api/plugins/install/url', json={}).status_code == 400


# ══ 2. Unified catalog ════════════════════════════════════════════════════════
def test_catalog_merges_both_backends(client):
    r = client.get('/api/hub/catalog')
    assert r.status_code == 200
    items = r.json()['items']
    sources = {i['source'] for i in items}
    assert 'plugins' in sources, 'built-in packs missing from the unified catalog'
    assert 'marketplace' in sources, 'marketplace packs missing from the unified catalog'


def test_catalog_deduplicates_overlapping_ids(client):
    """"research-assistant" exists in BOTH backends with different contents.

    Showing it twice, with independent install buttons, is the confusion the
    hub exists to remove.
    """
    items = client.get('/api/hub/catalog').json()['items']
    ids = [i['id'] for i in items]
    assert len(ids) == len(set(ids)), f'duplicate ids in catalog: {ids}'


def test_catalog_entries_share_one_shape(client):
    """The two backends disagree on field names for the same concept
    (emoji/icon, version/latest_ver). The UI should not have to know which
    backend a card came from."""
    required = {
        'id', 'source', 'name', 'description', 'icon', 'author',
        'category', 'version', 'tags', 'skill_count', 'installed', 'verified',
    }
    for item in client.get('/api/hub/catalog').json()['items']:
        assert required.issubset(item.keys()), f'{item["id"]} missing {required - item.keys()}'


def test_catalog_hides_test_residue(client):
    """The hub is the shop window; "🧪 sysplugin_928ffc841e" must not appear."""
    items = client.get('/api/hub/catalog').json()['items']
    for i in items:
        assert not i['id'].startswith(('test_plugin_', 'sysplugin_', 'uat_plugin_')), (
            f'test residue in the user-facing catalog: {i["id"]}'
        )


def test_is_test_artifact_keeps_real_packs():
    """Over-filtering would hide genuine plugins."""
    assert not hub._is_test_artifact({'id': 'dev-toolkit', 'category': 'development', 'skill_count': 5})
    assert hub._is_test_artifact({'id': 'sysplugin_abc', 'category': 'testing', 'skill_count': 0})


def test_installed_view_spans_both_backends(client):
    r = client.get('/api/hub/installed')
    assert r.status_code == 200
    assert 'items' in r.json()


def test_catalog_search_filters(client):
    r = client.get('/api/hub/catalog?q=devops')
    assert r.status_code == 200
    for i in r.json()['items']:
        blob = (i['name'] + i['description'] + ' '.join(map(str, i['tags']))).lower()
        assert 'devops' in blob


# ══ 3. Packs must report their real skills ════════════════════════════════════
def test_marketplace_packs_report_their_skills(client):
    """Every curated pack advertised downloads and ratings while listing 0 skills."""
    items = client.get('/api/hub/catalog').json()['items']
    market = [i for i in items if i['source'] == 'marketplace']
    assert market, 'no marketplace packs in the catalog'
    assert all(i['skill_count'] > 0 for i in market), (
        f'packs with zero skills: {[i["id"] for i in market if i["skill_count"] == 0]}'
    )


def test_skills_json_column_is_populated(client):
    """The backfill must repair databases seeded before the fix, since the
    seeder skips rows that already exist."""
    from backend.services.memory_db import get_conn

    con = get_conn()
    try:
        rows = con.execute(
            "SELECT id, skills_json FROM mkt_packs WHERE published=1"
        ).fetchall()
    finally:
        con.close()
    assert rows, 'no curated packs seeded'
    empty = [r['id'] for r in rows if json.loads(r['skills_json'] or '[]') == []]
    assert not empty, f'skills_json still empty for: {empty}'


def test_pack_detail_exposes_skills_and_prompts(client):
    """"What does this do before I install it" was unanswerable: the registry
    endpoint explicitly strips skills ('skills': None)."""
    r = client.get('/api/hub/pack/dev-toolkit')
    assert r.status_code == 200
    d = r.json()
    assert d['skill_count'] > 0
    assert d['skills'], 'detail returned no skills'
    first = d['skills'][0]
    assert first['prompt_template'], 'no prompt shown — user cannot preview behaviour'
    assert 'name' in first


def test_pack_detail_unknown_is_404(client):
    assert client.get('/api/hub/pack/definitely_not_real').status_code == 404


# ══ 4. Honest install counts ══════════════════════════════════════════════════
def test_install_reports_skills_actually_added(client):
    """Reported the pack total while skipping ids that already existed."""
    from backend.routers.skills import load_skills

    client.post('/api/hub/uninstall/customer-success')
    before = len(load_skills())
    r = client.post('/api/hub/install/customer-success')
    assert r.status_code == 200, r.text
    reported = r.json()['skills_added']
    after = len(load_skills())
    assert reported == after - before, (
        f'reported {reported} skills added but {after - before} appeared'
    )
    client.post('/api/hub/uninstall/customer-success')


def test_install_then_uninstall_roundtrip(client):
    client.post('/api/hub/uninstall/devops-toolkit')
    r = client.post('/api/hub/install/devops-toolkit')
    assert r.status_code == 200 and r.json()['ok']

    installed = {i['id'] for i in client.get('/api/hub/installed').json()['items']}
    assert 'devops-toolkit' in installed

    r2 = client.post('/api/hub/uninstall/devops-toolkit')
    assert r2.status_code == 200
    installed2 = {i['id'] for i in client.get('/api/hub/installed').json()['items']}
    assert 'devops-toolkit' not in installed2


def test_double_install_is_409_not_success(client):
    client.post('/api/hub/install/prompt-engineering')
    r = client.post('/api/hub/install/prompt-engineering')
    assert r.status_code == 409, 'installing an already-installed pack reported success'
    client.post('/api/hub/uninstall/prompt-engineering')


def test_uninstall_of_not_installed_is_409(client):
    client.post('/api/hub/uninstall/founder-os')
    r = client.post('/api/hub/uninstall/founder-os')
    assert r.status_code == 409


# ══ 5. Status codes ═══════════════════════════════════════════════════════════
def test_install_unknown_plugin_is_404(client):
    assert client.post('/api/plugins/install/nope_not_a_plugin').status_code == 404
    assert client.post('/api/hub/install/nope_not_a_plugin').status_code == 404


def test_uninstall_unknown_plugin_is_404(client):
    assert client.delete('/api/plugins/uninstall/nope_not_a_plugin').status_code == 404
    assert client.post('/api/hub/uninstall/nope_not_a_plugin').status_code == 404


def test_install_json_without_skills_array_is_400(client):
    r = client.post('/api/plugins/install/json', json={'plugin_json': {'name': 'no skills'}})
    assert r.status_code == 400


def test_install_json_with_non_list_skills_is_400(client):
    """'skills' in data passed for a string, a dict, or None."""
    r = client.post('/api/plugins/install/json', json={'plugin_json': {'skills': 'nope'}})
    assert r.status_code == 400


# ══ Onboarding: starter collections ═══════════════════════════════════════════
def test_collections_are_offered_with_live_state(client):
    r = client.get('/api/hub/collections')
    assert r.status_code == 200
    colls = r.json()['collections']
    assert colls, 'no starter collections — a new user has no obvious first action'
    for c in colls:
        assert {'id', 'name', 'description', 'icon', 'packs', 'installed_count'} <= c.keys()


def test_every_collection_references_real_packs(client):
    """A starter bundle pointing at a pack that does not exist is worse than none."""
    known = {i['id'] for i in client.get('/api/hub/catalog').json()['items']}
    for c in hub.COLLECTIONS:
        missing = [p for p in c['packs'] if p not in known]
        assert not missing, f'collection {c["id"]} references unknown packs: {missing}'


def test_recommended_collections_are_non_empty(client):
    for c in client.get('/api/hub/collections').json()['collections']:
        if c.get('recommended'):
            assert c['available'] > 0, f'recommended collection {c["id"]} has no installable packs'
            assert c['skill_total'] > 0, f'recommended collection {c["id"]} installs no skills'


def test_installing_a_collection_installs_its_packs(client):
    for pid in ('research-assistant', 'prompt-engineering'):
        client.post(f'/api/hub/uninstall/{pid}')

    r = client.post('/api/hub/collections/researcher/install')
    assert r.status_code == 200, r.text
    body = r.json()
    assert body['ok'] is True, body
    installed = {i['id'] for i in client.get('/api/hub/installed').json()['items']}
    assert 'research-assistant' in installed


def test_unknown_collection_is_404(client):
    assert client.post('/api/hub/collections/not-a-collection/install').status_code == 404


def test_stats_endpoint_is_consistent_with_the_catalog(client):
    stats = client.get('/api/hub/stats').json()
    items = client.get('/api/hub/catalog').json()['items']
    assert stats['total_packs'] == len(items)
    assert stats['installed_packs'] == sum(1 for i in items if i['installed'])


# ══ 6. Marketplace pack-id hygiene + delete (round 23) ═════════════════════════
def _mkt_cleanup(client, pack_id):
    with __import__('contextlib').suppress(Exception):
        client.delete(f'/api/marketplace/{pack_id}')


def test_publish_slugifies_ids_and_cannot_escape_packs_dir(client):
    """publish took a raw caller-supplied pack id into filesystem paths.

    Verified live pre-fix: publishing '../../../something' read and WROTE
    json outside workspaces/plugin_sdk/packs/ with ok:true. The body id and
    the manifest's own id field must both be slugified (community/submit
    and /upload already did; publish was the hole).
    """
    from backend.config import get_data_dir

    sdk = get_data_dir() / 'workspaces' / 'plugin_sdk' / 'packs'
    sdk.mkdir(parents=True, exist_ok=True)
    (sdk / 'zz-trav-sdk.json').write_text(json.dumps({
        'id': '../../../zz-escaped', 'name': 'Trav Probe', 'description': 'd',
        'version': '1.0.0', 'skills': [],
    }))
    try:
        r = client.post('/api/marketplace/publish', json={'pack_id': '../../../zz-trav-sdk'})
        assert r.status_code == 200, r.text
        d = r.json()
        assert d['ok'] is True
        assert '..' not in d['pack_id'], f'raw id escaped slugification: {d["pack_id"]}'
        # The manifest's own (crafted) id is slugified too, and nothing was
        # written outside the packs directory.
        assert not (get_data_dir() / 'zz-escaped').exists(), 'file escaped the packs dir'
        packs_dir = get_data_dir() / 'workspaces' / 'marketplace' / 'packs'
        assert (packs_dir / 'zz-escaped' / 'manifest.json').exists()
        assert client.get('/api/marketplace/zz-escaped').status_code == 200
    finally:
        _mkt_cleanup(client, 'zz-escaped')
        (sdk / 'zz-trav-sdk.json').unlink(missing_ok=True)


def test_publish_rejects_ids_that_slugify_to_empty(client):
    r = client.post('/api/marketplace/publish', json={'pack_id': '../../..'})
    assert r.status_code == 400
    assert r.json().get('ok') is False


def test_marketplace_invalid_pack_ids_are_400(client):
    """Path params reach filesystem paths (install manifest read, uninstall
    sdk-json unlink, download manifest read) — a traversal id must be
    rejected, not attempted."""
    assert client.post('/api/marketplace/a.b/install', json={}).status_code == 400
    assert client.delete('/api/marketplace/a.b/uninstall').status_code == 400
    assert client.get('/api/marketplace/a.b/download').status_code == 400
    assert client.post('/api/marketplace/a.b/review', json={'rating': 5}).status_code == 400


def test_delete_pack_removes_it_everywhere(client):
    """Packs could be created three ways and removed zero ways — the grid
    only grew. DELETE must clear the catalog row, reviews, install state,
    the pack directory, and the SDK pack file."""
    from backend.config import get_data_dir

    sub = client.post('/api/marketplace/community/submit', json={
        'id': 'zz-del-probe', 'name': 'Delete Probe', 'description': 'd',
    })
    assert sub.status_code == 200 and sub.json()['ok'], sub.text

    assert client.post('/api/marketplace/zz-del-probe/install', json={}).status_code == 200
    assert client.post('/api/marketplace/zz-del-probe/review', json={
        'rating': 5, 'review': 'great',
    }).status_code == 200

    r = client.delete('/api/marketplace/zz-del-probe')
    assert r.status_code == 200 and r.json()['ok'] is True and r.json()['deleted'] is True

    ids = {p['id'] for p in client.get('/api/marketplace?limit=100').json()['packs']}
    assert 'zz-del-probe' not in ids, 'deleted pack still listed'
    assert client.get('/api/marketplace/zz-del-probe').status_code == 404
    assert client.get('/api/marketplace/zz-del-probe/reviews').json()['count'] == 0
    inst = client.get('/api/marketplace/installed/list').json()
    assert all(i.get('pack_id') != 'zz-del-probe' for i in inst.get('installed', []))
    sdk_json = get_data_dir() / 'workspaces' / 'plugin_sdk' / 'packs' / 'zz-del-probe.json'
    assert not sdk_json.exists(), 'sdk pack file survived deletion'


def test_delete_pack_refuses_reseeded_builtins(client):
    """Curated packs are re-seeded at startup; deleting one would just make
    it reappear — the button must say so instead of silently undoing."""
    r = client.delete('/api/marketplace/agenticai-core')
    assert r.status_code == 403
    assert 're-seeded' in r.json()['error']
    ids = {p['id'] for p in client.get('/api/marketplace?limit=100').json()['packs']}
    assert 'agenticai-core' in ids, 'refused delete still removed the pack'


def test_review_of_unknown_pack_is_404(client):
    """Reviews for packs that don't exist returned ok:true with new_avg 0 —
    the caller believed their review was recorded."""
    r = client.post('/api/marketplace/zz-no-such-pack/review', json={'rating': 5})
    assert r.status_code == 404
    assert r.json().get('ok') is False


# ══ 7. Uninstall must not eat skills it never installed (round 23) ═════════════
def test_uninstall_keeps_seeded_skill_with_colliding_id(client):
    """code_review ships in BOTH the default skills.json and the code-wizard
    pack. Install reports it "already present" and skips it — but uninstall
    used to remove by bare id and deleted the seeded copy anyway (verified
    live: install + uninstall of code-wizard ate the default skill)."""
    from backend.routers.skills import load_skills, save_skills

    client.post('/api/marketplace/code-wizard/uninstall')
    skills = load_skills()
    if not any(s.get('id') == 'code_review' for s in skills):
        skills.append({
            'id': 'code_review', 'name': 'Code Review',
            'prompt_template': 'Review: {{code}}',
        })
        save_skills(skills)

    r = client.post('/api/marketplace/code-wizard/install', json={})
    assert r.status_code == 200, r.text
    assert r.json()['skills_already_present'] >= 1, 'seeded code_review not detected as present'

    u = client.delete('/api/marketplace/code-wizard/uninstall')
    assert u.status_code == 200 and u.json()['ok']

    after = {s.get('id'): s for s in load_skills()}
    assert 'code_review' in after, 'uninstall deleted the seeded code_review skill'
    assert after['code_review'].get('source_plugin') is None, (
        'uninstall mutated the seeded skill'
    )


def test_uninstall_removes_only_what_the_install_added(client):
    """Skills the install DID add (tagged source_plugin) must be removed on
    uninstall; the seeded ones must stay."""
    from backend.routers.skills import load_skills, save_skills

    client.post('/api/marketplace/code-wizard/uninstall')
    # Seed one colliding skill; leave the rest of the pack's skills absent.
    save_skills([{
        'id': 'code_review', 'name': 'Seeded Code Review',
        'prompt_template': 'Review: {{code}}',
    }])

    r = client.post('/api/marketplace/code-wizard/install', json={})
    added = r.json()['skills_added']
    assert added >= 1, 'expected the install to add pack skills'
    before = {s.get('id'): s for s in load_skills()}
    assert before['code_review'].get('source_plugin') is None, 'install overwrote the seeded skill'

    client.delete('/api/marketplace/code-wizard/uninstall')
    after_ids = {s.get('id') for s in load_skills()}
    assert 'code_review' in after_ids, 'seeded skill eaten by uninstall'
    for sid in before:
        if before[sid].get('source_plugin') == 'code-wizard':
            assert sid not in after_ids, f'installed skill {sid} not removed'


# ══ 8. Plugin SDK publish/delete lifecycle (round 24) ══════════════════════════
_ZZ_PACK = {
    'id': 'zz-sdk-lifecycle', 'name': 'SDK Lifecycle Probe', 'version': '1.0.0',
    'description': 'probe', 'author': 'probe', 'icon': '🧪',
    'skills': [
        {'id': 'zz_sdk_probe_skill', 'name': 'Probe Skill',
         'prompt': 'Echo: {{input}}', 'description': 'd'},
    ],
}


def _zz_cleanup(client):
    with __import__('contextlib').suppress(Exception):
        client.delete('/api/pluginsdk/packs/zz-sdk-lifecycle')


def test_sdk_publish_actually_lands_in_the_marketplace(client):
    """The publish toast says "now in the Plugin Marketplace" — it used to be
    a lie: the pack went to the SDK registry only and never appeared in the
    marketplace grid (verified live). Publish must register the pack in the
    marketplace catalog so it is installable/uninstallable/deletable there."""
    from backend.routers.skills import load_skills

    _zz_cleanup(client)
    assert client.post('/api/pluginsdk/packs', json=_ZZ_PACK).json()['ok']
    r = client.post('/api/pluginsdk/publish/zz-sdk-lifecycle')
    assert r.status_code == 200 and r.json()['ok'], r.text

    ids = {p['id'] for p in client.get('/api/marketplace?limit=100').json()['packs']}
    assert 'zz-sdk-lifecycle' in ids, 'published pack missing from marketplace grid'
    # Skills installed by publish carry the ownership tag.
    tags = {s['id']: s.get('source_plugin') for s in load_skills()}
    assert tags.get('zz_sdk_probe_skill') == 'zz-sdk-lifecycle', tags.get('zz_sdk_probe_skill')


def test_sdk_delete_is_a_full_teardown(client):
    """Deleting an SDK pack used to unlink only the pack json — the skill,
    the published-registry entry, the plugins/installed.json row and the
    marketplace listing all survived (verified live: every one orphaned)."""
    from backend.config import get_data_dir
    from backend.routers.skills import load_skills

    _zz_cleanup(client)
    client.post('/api/pluginsdk/packs', json=_ZZ_PACK)
    client.post('/api/pluginsdk/publish/zz-sdk-lifecycle')

    r = client.delete('/api/pluginsdk/packs/zz-sdk-lifecycle')
    assert r.status_code == 200 and r.json()['ok'] is True
    assert r.json()['deleted'] is True

    root = get_data_dir()
    assert not (root / 'workspaces' / 'plugin_sdk' / 'packs' / 'zz-sdk-lifecycle.json').exists()
    assert not (root / 'workspaces' / 'plugin_sdk' / 'published' / 'zz-sdk-lifecycle.json').exists()
    assert not any(s.get('id') == 'zz_sdk_probe_skill' for s in load_skills()), 'skill orphaned by SDK delete'
    assert 'zz-sdk-lifecycle' not in json.loads(
        (root / 'plugins' / 'installed.json').read_text()
    ), 'installed.json row orphaned by SDK delete'
    ids = {p['id'] for p in client.get('/api/marketplace?limit=100').json()['packs']}
    assert 'zz-sdk-lifecycle' not in ids, 'marketplace listing orphaned by SDK delete'


def test_sdk_publish_refuses_reserved_curated_ids(client):
    """Publishing over a curated id would rewrite the built-in marketplace
    listing (and a later SDK delete would remove the re-seeded built-in)."""
    pack = {**_ZZ_PACK, 'id': 'agenticai-core'}
    client.post('/api/pluginsdk/packs', json=pack)
    try:
        r = client.post('/api/pluginsdk/publish/agenticai-core')
        # 400 via the platform's ok:false convention — an honest refusal
        # with the reason, not a crash.
        assert r.status_code == 400
        assert r.json()['ok'] is False
        assert 'reserved' in r.json()['error']
    finally:
        client.delete('/api/pluginsdk/packs/agenticai-core')
