"""Module 11 — Prompt Library review contracts.

Bugs these pin, all reproduced live against a running server before the fix:

1. {placeholder} variables were advertised but never implemented. The editor
   says "Use {placeholder} for variables"; nothing anywhere substituted them,
   so clicking Use sent the literal braces to the model.

2. An unknown ?category= was dropped from the WHERE clause, so a filtered
   request silently returned the ENTIRE library — the opposite of what was
   asked. Likewise an unknown category on create/update was rewritten to
   'general', filing the prompt somewhere the user never chose.

3. LIKE wildcards in search were unescaped: q='%' matched every row, q='_'
   matched any single character.

4. Import's docstring promised "skips duplicates by title" but the only guard
   was INSERT OR IGNORE against a fresh UUID primary key, which never
   collides. Re-importing an export doubled the library every time.

5. Import returned a bare HTTP 500 on a non-dict entry, and on tags supplied
   as a list — the shape create() explicitly accepts, so a library exported
   from this API could fail to import.

6. Seven endpoints returned HTTP 200 for a prompt that does not exist.

7. Duplicating twice produced two prompts both called "Copy of X", and for a
   long title the "Copy of " prefix pushed the distinguishing tail off the
   120-char limit.

8. No indexes on any filtered/sorted column.
"""
from __future__ import annotations

import uuid

import pytest

from backend.routers import prompts as pr


def _title() -> str:
    return f'ReviewTest_{uuid.uuid4().hex[:8]}'


@pytest.fixture
def made(client):
    """Create prompts and clean them up afterwards."""
    created: list[str] = []

    def _make(**kw):
        body = {'title': _title(), 'content': 'body text'}
        body.update(kw)
        r = client.post('/api/prompts', json=body)
        assert r.status_code == 201, r.text
        pid = r.json()['id']
        created.append(pid)
        return pid, body

    yield _make
    for pid in created:
        client.delete(f'/api/prompts/{pid}')


# ── 1. Variables ───────────────────────────────────────────────────────────────


class TestVariablesActuallyWork:
    def test_extraction_finds_names_in_first_use_order(self):
        assert pr.extract_variables('Review {language} in {repo} for {language} bugs') == [
            'language',
            'repo',
        ]

    def test_double_braces_are_not_variables(self):
        """Otherwise JSON or code samples inside a prompt become variables."""
        assert pr.extract_variables('Return {{"ok": true}} for {name}') == ['name']

    def test_no_variables_is_an_empty_list(self):
        assert pr.extract_variables('plain prompt with no tokens') == []

    def test_rendering_substitutes_every_occurrence(self):
        out, missing = pr.render_prompt('{x} then {x} and {y}', {'x': 'A', 'y': 'B'})
        assert out == 'A then A and B'
        assert missing == []

    def test_unsupplied_variables_are_reported_not_blanked(self):
        """Blanking silently changes what the prompt means."""
        out, missing = pr.render_prompt('Review {lang} in {repo}', {'lang': 'Go'})
        assert out == 'Review Go in {repo}'
        assert missing == ['repo']

    def test_render_endpoint_returns_finished_text(self, client, made):
        pid, _ = made(content='Review this {language} code in {repo}')
        r = client.post(
            f'/api/prompts/{pid}/render',
            json={'values': {'language': 'Python', 'repo': 'strick_tech'}},
        )
        assert r.status_code == 200
        body = r.json()
        assert body['rendered'] == 'Review this Python code in strick_tech'
        assert body['complete'] is True
        assert body['missing'] == []

    def test_render_reports_missing_values(self, client, made):
        pid, _ = made(content='Review {language} in {repo}')
        body = client.post(f'/api/prompts/{pid}/render', json={'values': {'language': 'Go'}}).json()
        assert body['missing'] == ['repo']
        assert body['complete'] is False

    def test_render_increments_use_count(self, client, made):
        pid, _ = made(content='Hello {name}')
        before = client.get(f'/api/prompts/{pid}').json()['use_count']
        client.post(f'/api/prompts/{pid}/render', json={'values': {'name': 'x'}})
        assert client.get(f'/api/prompts/{pid}').json()['use_count'] == before + 1

    def test_render_rejects_a_non_object_values(self, client, made):
        pid, _ = made(content='Hello {name}')
        assert client.post(f'/api/prompts/{pid}/render', json={'values': 'nope'}).status_code == 400

    def test_variables_are_exposed_on_list_and_get(self, client, made):
        pid, body = made(content='Fix {bug} in {file}')
        assert client.get(f'/api/prompts/{pid}').json()['variables'] == ['bug', 'file']
        listed = client.get('/api/prompts', params={'q': body['title']}).json()['prompts']
        assert listed[0]['variables'] == ['bug', 'file']

    def test_frontend_prompts_for_values_before_using(self):
        from pathlib import Path

        js = (Path(__file__).resolve().parents[2] / 'frontend' / 'js' / '14-prompt-library.js').read_text()
        assert 'function askForVariables' in js
        assert "/render" in js
        assert 'function promptVariables' in js


# ── 2. Category handling ───────────────────────────────────────────────────────


class TestUnknownCategoryIsRejected:
    def test_listing_with_a_bogus_category_does_not_return_everything(self, client):
        """It used to drop the filter and return the whole library."""
        r = client.get('/api/prompts', params={'category': 'NOT_A_CATEGORY'})
        assert r.status_code == 400
        assert 'valid_categories' in r.json()

    def test_creating_with_a_bogus_category_is_rejected_not_silently_moved(self, client):
        r = client.post(
            '/api/prompts', json={'title': _title(), 'content': 'x', 'category': 'nonsense'}
        )
        assert r.status_code == 400

    def test_updating_to_a_bogus_category_is_rejected(self, client, made):
        pid, _ = made()
        assert client.patch(f'/api/prompts/{pid}', json={'category': 'nonsense'}).status_code == 400

    def test_a_valid_category_still_filters(self, client, made):
        pid, body = made(category='review')
        titles = [
            p['title']
            for p in client.get('/api/prompts', params={'category': 'review', 'limit': 500}).json()['prompts']
        ]
        assert body['title'] in titles

    def test_bogus_sort_is_rejected(self, client):
        assert client.get('/api/prompts', params={'sort': 'haxx'}).status_code == 400


# ── 3. LIKE wildcards ──────────────────────────────────────────────────────────


class TestSearchWildcardsAreEscaped:
    def test_escaper_quotes_the_metacharacters(self):
        assert pr._like('%') == r'%\%%'
        assert pr._like('_') == r'%\_%'

    def test_percent_is_a_literal_search_not_match_everything(self, client, made):
        """q='%' used to match the whole library; it must now match only rows
        that genuinely contain a percent sign."""
        _pid, body = made(content='no percent sign here')
        total = client.get('/api/prompts').json()['total']
        hits = client.get('/api/prompts/search', params={'q': '%', 'limit': 50}).json()['results']
        assert len(hits) < total, 'a bare % must not behave as a wildcard'
        assert all('%' in (h['title'] + h['content'] + (h['tags'] or '')) for h in hits)
        assert body['title'] not in [h['title'] for h in hits]

    def test_percent_finds_a_prompt_that_contains_one(self, client, made):
        pid, body = made(content='discount is 50% off')
        hits = client.get('/api/prompts/search', params={'q': '%', 'limit': 50}).json()['results']
        assert any(h['id'] == pid for h in hits)

    def test_underscore_only_matches_a_real_underscore(self, client, made):
        pid, _body = made(content='snake_case identifier')
        hits = client.get('/api/prompts/search', params={'q': 'snake_case', 'limit': 50}).json()['results']
        assert any(h['id'] == pid for h in hits)

    def test_list_query_is_escaped_too(self, client, made):
        _pid, body = made(content='nothing special here')
        listed = client.get('/api/prompts', params={'q': '%', 'limit': 500}).json()
        assert listed['count'] < listed['total']
        assert body['title'] not in [p['title'] for p in listed['prompts']]


# ── 4 & 5. Import ──────────────────────────────────────────────────────────────


class TestImport:
    def test_same_title_is_skipped_not_duplicated(self, client):
        title = _title()
        payload = {'prompts': [{'title': title, 'content': c} for c in ('a', 'b', 'c')]}
        body = client.post('/api/prompts/import', json=payload).json()
        assert body['imported'] == 1
        assert body['skipped'] == 2
        found = client.get('/api/prompts', params={'q': title}).json()
        assert found['count'] == 1
        for p in found['prompts']:
            client.delete(f"/api/prompts/{p['id']}")

    def test_replace_existing_updates_in_place(self, client):
        title = _title()
        client.post('/api/prompts/import', json={'prompts': [{'title': title, 'content': 'old'}]})
        body = client.post(
            '/api/prompts/import',
            json={'replace_existing': True, 'prompts': [{'title': title, 'content': 'NEW'}]},
        ).json()
        assert body['replaced'] == 1
        found = client.get('/api/prompts', params={'q': title}).json()
        assert found['count'] == 1
        assert found['prompts'][0]['content'] == 'NEW'
        client.delete(f"/api/prompts/{found['prompts'][0]['id']}")

    def test_reimporting_an_export_is_idempotent(self, client):
        """This is the real-world consequence: export → import doubled everything."""
        title = _title()
        client.post('/api/prompts', json={'title': title, 'content': 'x'})
        export = client.get('/api/prompts/export').json()
        before = export['count']
        client.post('/api/prompts/import', json={'prompts': export['prompts']})
        assert client.get('/api/prompts/export').json()['count'] == before
        for p in client.get('/api/prompts', params={'q': title}).json()['prompts']:
            client.delete(f"/api/prompts/{p['id']}")

    def test_non_dict_entries_do_not_crash_the_import(self, client):
        """Used to raise AttributeError → bare HTTP 500, aborting everything."""
        r = client.post('/api/prompts/import', json={'prompts': ['a string', 42, None]})
        assert r.status_code == 200
        body = r.json()
        assert body['skipped'] == 3
        assert len(body['errors']) == 3

    def test_tags_as_a_list_is_accepted(self, client):
        """create() accepts a list, so an export from this API must import."""
        title = _title()
        r = client.post(
            '/api/prompts/import',
            json={'prompts': [{'title': title, 'content': 'x', 'tags': ['a', 'b']}]},
        )
        assert r.status_code == 200
        found = client.get('/api/prompts', params={'q': title}).json()['prompts']
        assert found[0]['tags'] == 'a,b'
        client.delete(f"/api/prompts/{found[0]['id']}")

    def test_a_bad_entry_does_not_discard_the_good_ones(self, client):
        good = _title()
        r = client.post(
            '/api/prompts/import',
            json={'prompts': [None, {'title': good, 'content': 'x'}, {'title': '', 'content': ''}]},
        ).json()
        assert r['imported'] == 1
        for p in client.get('/api/prompts', params={'q': good}).json()['prompts']:
            client.delete(f"/api/prompts/{p['id']}")

    def test_prompts_must_be_a_list(self, client):
        assert client.post('/api/prompts/import', json={'prompts': 'nope'}).status_code == 400


# ── 6. Status codes ────────────────────────────────────────────────────────────


class TestStatusCodes:
    MISSING = 'definitely-not-a-real-prompt-id'

    def test_get_missing_is_404(self, client):
        assert client.get(f'/api/prompts/{self.MISSING}').status_code == 404

    def test_delete_missing_is_404(self, client):
        assert client.delete(f'/api/prompts/{self.MISSING}').status_code == 404

    def test_patch_missing_is_404(self, client):
        assert client.patch(f'/api/prompts/{self.MISSING}', json={'title': 'x'}).status_code == 404

    def test_use_missing_is_404(self, client):
        assert client.post(f'/api/prompts/{self.MISSING}/use').status_code == 404

    def test_duplicate_missing_is_404(self, client):
        assert client.post(f'/api/prompts/{self.MISSING}/duplicate').status_code == 404

    def test_render_missing_is_404(self, client):
        assert client.post(f'/api/prompts/{self.MISSING}/render', json={}).status_code == 404

    def test_create_without_required_fields_is_400(self, client):
        assert client.post('/api/prompts', json={}).status_code == 400

    def test_create_returns_201(self, client, made):
        pid, _ = made()
        assert pid

    def test_update_with_no_fields_is_400(self, client, made):
        pid, _ = made()
        assert client.patch(f'/api/prompts/{pid}', json={}).status_code == 400

    def test_update_to_an_empty_title_is_rejected(self, client, made):
        pid, _ = made()
        assert client.patch(f'/api/prompts/{pid}', json={'title': '   '}).status_code == 400

    def test_update_to_empty_content_is_rejected(self, client, made):
        pid, _ = made()
        assert client.patch(f'/api/prompts/{pid}', json={'content': '  '}).status_code == 400


# ── 7. Duplicate naming ────────────────────────────────────────────────────────


class TestDuplicateNaming:
    def test_repeated_duplicates_are_distinguishable(self, client, made):
        pid, _ = made()
        titles = []
        ids = []
        for _ in range(3):
            r = client.post(f'/api/prompts/{pid}/duplicate')
            assert r.status_code == 201
            titles.append(r.json()['title'])
            ids.append(r.json()['id'])
        try:
            assert len(set(titles)) == 3, f'copies must not collide: {titles}'
        finally:
            for i in ids:
                client.delete(f'/api/prompts/{i}')

    def test_copy_of_copy_of_does_not_accumulate(self, client, made):
        pid, _ = made()
        first = client.post(f'/api/prompts/{pid}/duplicate').json()
        second = client.post(f"/api/prompts/{first['id']}/duplicate").json()
        try:
            assert not second['title'].startswith('Copy of Copy of')
        finally:
            client.delete(f"/api/prompts/{first['id']}")
            client.delete(f"/api/prompts/{second['id']}")

    def test_a_long_title_keeps_its_distinguishing_tail(self, client):
        """Truncating the tail made copies of similar long titles identical."""
        tail = 'UNIQUE_TAIL'
        title = 'A' * (pr.MAX_TITLE - len(tail)) + tail
        pid = client.post('/api/prompts', json={'title': title, 'content': 'x'}).json()['id']
        dup = client.post(f'/api/prompts/{pid}/duplicate').json()
        try:
            assert len(dup['title']) <= pr.MAX_TITLE
            assert dup['title'].endswith(tail)
        finally:
            client.delete(f'/api/prompts/{pid}')
            client.delete(f"/api/prompts/{dup['id']}")


# ── 8. Schema / hygiene ────────────────────────────────────────────────────────


class TestSchemaAndHygiene:
    def test_filtered_columns_are_indexed(self):
        from backend.services.memory_db import get_conn

        con = get_conn()
        try:
            names = {
                r[0]
                for r in con.execute(
                    "SELECT name FROM sqlite_master WHERE type='index' AND tbl_name='prompt_library'"
                ).fetchall()
            }
        finally:
            con.close()
        for expected in ('idx_prompt_category', 'idx_prompt_updated', 'idx_prompt_use_count'):
            assert expected in names, f'missing index {expected}'

    def test_tags_are_normalised(self):
        assert pr._clean_tags(['a', 'B', 'a', ' c ']) == 'a,B,c'
        assert pr._clean_tags(',,,   ,,,') == ''
        assert pr._clean_tags('x, y ,x') == 'x,y'

    def test_tag_junk_does_not_reach_storage(self, client, made):
        pid, _ = made(tags=',,,  ,,')
        assert client.get(f'/api/prompts/{pid}').json()['tags'] == ''

    def test_content_and_title_are_capped(self, client):
        r = client.post('/api/prompts', json={'title': 'T' * 500, 'content': 'c' * 20000})
        pid = r.json()['id']
        try:
            got = client.get(f'/api/prompts/{pid}').json()
            assert len(got['title']) <= pr.MAX_TITLE
            assert len(got['content']) <= pr.MAX_CONTENT
        finally:
            client.delete(f'/api/prompts/{pid}')


class TestFrontendContract:
    def test_it_surfaces_server_error_text(self):
        from pathlib import Path

        js = (Path(__file__).resolve().parents[2] / 'frontend' / 'js' / '14-prompt-library.js').read_text()
        assert 'async function promptError' in js
        assert "HTTP '+r.status" not in js, 'bare status numbers hide the reason'
