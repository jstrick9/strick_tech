"""Module 13 — AI Context & Guidelines (Information Hierarchy) review contracts.

This module compiles a context block that chat.py concatenates into the LLM
system prompt, so its inputs are a prompt-injection and file-read surface, not
just stored text. Everything below was reproduced live before the fix.

1. PATH TRAVERSAL. `project_id` was interpolated straight into a filesystem
   path with no validation:

     POST /projects/create {"project_id": "../../../tmp/hier_escape"}
       -> 200 OK, created /home/user/repo/tmp/hier_escape

     GET /compiled-context?project_id=../secretdir
       -> read files outside the projects tree AND injected their contents
          into the LLM system prompt

2. THE AUTHOR'S PERSONAL DETAILS WERE EVERY USER'S DEFAULT CONTEXT. The four
   Tier 1 templates shipped a real name, company, product tiers and pricing.
   Because compiled-context feeds the system prompt, every install silently
   told its AI it was working for someone else's business — phrased
   confidently enough that the model would cite it as fact.

3. `initialized` WAS ALWAYS TRUE. _ensure_tier1_init() creates all four files
   on first read, and status only checked existence, so nothing could
   distinguish a configured profile from an untouched one.

4. NO DELETE. The project lifecycle was create-and-save only; DELETE returned
   405 and a mistaken project stayed in every listing forever.

5. RE-CREATE SILENTLY OVERWROTE meta.json — name, audience and created_at
   replaced with no warning while the IVREN content stayed.
"""
from __future__ import annotations

from pathlib import Path

import pytest

from backend.routers import hierarchy as h

REPO = Path(__file__).resolve().parents[2]
SRC = (REPO / 'backend' / 'routers' / 'hierarchy.py').read_text()
JS = (REPO / 'frontend' / 'js' / '12-information-hierarchy.js').read_text()


@pytest.fixture
def project(client):
    """Create a project and clean it up afterwards."""
    created = []

    def _make(pid='revtest', **kw):
        body = {'project_id': pid, 'name': kw.get('name', 'Review Test')}
        body.update(kw)
        # Projects live on disk and survive between runs; creating is now a 409
        # if one already exists, so start from a known-clean state.
        client.delete(f'/api/hierarchy/projects/{pid}')
        r = client.post('/api/hierarchy/projects/create', json=body)
        if r.status_code == 200:
            created.append(r.json()['project']['project_id'])
        return r

    yield _make
    for pid in created:
        client.delete(f'/api/hierarchy/projects/{pid}')


# ── 1. Path traversal ──────────────────────────────────────────────────────────


class TestPathTraversal:
    @pytest.mark.parametrize(
        'pid',
        [
            '../../../tmp/hier_escape',
            '../secretdir',
            '..',
            '/etc/passwd',
            'a/../../b',
            'foo/bar',
            'foo\\bar',
            '.hidden',
            '',
        ],
    )
    def test_unsafe_ids_do_not_resolve(self, pid):
        assert h.project_dir(pid) is None, f'{pid!r} must be rejected'

    def test_a_normal_id_resolves_inside_the_tree(self):
        resolved = h.project_dir('newsletter')
        assert resolved is not None
        assert resolved.is_relative_to(h.PROJECTS_DIR.resolve())

    def test_normalisation_strips_path_characters(self):
        """Stripping happens BEFORE validation, so traversal fails the check
        rather than silently becoming a different valid id."""
        assert '/' not in h.normalize_project_id('../../etc')
        assert '.' not in h.normalize_project_id('../../etc')

    def test_create_cannot_escape(self, client, tmp_path):
        client.delete('/api/hierarchy/projects/tmpescape_probe')
        r = client.post(
            '/api/hierarchy/projects/create',
            json={'project_id': '../../../tmp/escape_probe', 'name': 'x'},
        )
        # Either rejected, or normalised into a safe id — never written outside.
        if r.status_code == 200:
            pid = r.json()['project']['project_id']
            assert '..' not in pid and '/' not in pid
            created = h.project_dir(pid)
            assert created is not None and created.is_relative_to(h.PROJECTS_DIR.resolve())
            client.delete(f'/api/hierarchy/projects/{pid}')
        assert not (REPO / 'tmp' / 'escape_probe').exists()

    def test_compiled_context_rejects_traversal(self, client):
        """The serious one: this output goes into the LLM system prompt."""
        r = client.get('/api/hierarchy/compiled-context', params={'project_id': '../secretdir'})
        assert r.status_code == 400

    def test_compiled_context_cannot_read_outside_the_tree(self, client):
        secret = h.HIERARCHY_DIR / 'leakprobe' / 'instructions'
        secret.mkdir(parents=True, exist_ok=True)
        (secret / 'instructions.md').write_text('CANARY_STRING_XYZ')
        try:
            for pid in ('../leakprobe', '..%2Fleakprobe', 'leakprobe/../leakprobe'):
                r = client.get('/api/hierarchy/compiled-context', params={'project_id': pid})
                assert 'CANARY_STRING_XYZ' not in r.text
        finally:
            import shutil

            shutil.rmtree(h.HIERARCHY_DIR / 'leakprobe', ignore_errors=True)

    @pytest.mark.parametrize('endpoint', ['', '/save', '/notes/append'])
    def test_project_endpoints_reject_bad_ids(self, client, endpoint):
        path = f'/api/hierarchy/projects/..{endpoint}'
        r = client.get(path) if endpoint == '' else client.post(path, json={})
        assert r.status_code in (400, 404, 405, 422)


# ── 2. Default templates ───────────────────────────────────────────────────────


class TestDefaultsAreNotSomeoneElsesData:
    @pytest.mark.parametrize(
        'leak', ['Joshua Strickland', 'Strick Tech', 'joshua', 'strick tech']
    )
    def test_no_personal_details_in_the_templates(self, leak):
        blob = ' '.join(h.DEFAULT_TIER1.values()).lower()
        assert leak.lower() not in blob, f'{leak!r} must not be a default for every user'

    def test_no_invented_pricing_in_the_templates(self):
        blob = ' '.join(h.DEFAULT_TIER1.values())
        for phrase in ('Free Version', 'Pro Version', 'Enterprise Version'):
            assert phrase not in blob, 'templates must not assert product tiers as fact'

    def test_templates_are_marked_as_unfilled(self):
        for key, text in h.DEFAULT_TIER1.items():
            assert h._is_placeholder(text), f'{key} is not detectable as a placeholder'

    def test_edited_content_is_not_flagged(self):
        assert h._is_placeholder('# About Me\n- Name: A real person') is False

    def test_detection_survives_partial_edits(self):
        """Marker-based, not equality-based: editing one line must clear it.

        UPDATED (Module 12). This used to simulate an edit by deleting the
        marker and asserting the file was no longer a placeholder. But
        stripping the marker leaves the template's `_(your name)_` prompts
        completely intact -- the file still contains no user content at all,
        and injecting it teaches a model nothing.

        Detection is now marker OR emptiness, because the guided interview
        writes files that never carry the marker: answering it with whitespace
        produced four files of empty headings that counted as a configured
        profile and silently removed the "do not invent details about the
        user" guard from every agent's context.

        The property this test exists to protect -- a real one-line edit must
        clear the flag -- is asserted below with content that is actually
        edited.
        """
        stripped = h.DEFAULT_TIER1['about_me'].replace(h.PLACEHOLDER_MARKER, '')
        # Marker gone, but still nothing but prompts: correctly still unfilled.
        assert h._is_placeholder(stripped) is True

        really_edited = stripped.replace('_(your name)_', 'Josh Strickland')
        assert h._is_placeholder(really_edited) is False


# ── 3. Unfilled context is not injected as fact ────────────────────────────────


class TestCompiledContextHonesty:
    def _reset(self, client):
        client.post('/api/hierarchy/tier1/reset')

    def test_unfilled_files_are_not_injected(self, client):
        self._reset(client)
        body = client.get('/api/hierarchy/compiled-context').json()
        assert body['tier1_filled'] == []
        assert '_(your name)_' not in body['compiled_context']

    def test_it_tells_the_model_not_to_invent(self, client):
        """A blank context block invites confabulation; say so explicitly."""
        self._reset(client)
        ctx = client.get('/api/hierarchy/compiled-context').json()['compiled_context']
        assert 'has not set up their profile' in ctx
        assert 'Do not invent' in ctx

    def test_filled_files_are_injected(self, client):
        self._reset(client)
        client.post('/api/hierarchy/tier1', json={'about_my_voice': '# Voice\n- Terse, no filler.'})
        body = client.get('/api/hierarchy/compiled-context').json()
        try:
            assert body['tier1_filled'] == ['about_my_voice']
            assert 'no filler' in body['compiled_context']
            assert '_(your name)_' not in body['compiled_context']
        finally:
            self._reset(client)

    def test_partial_configuration_reports_what_is_missing(self, client):
        self._reset(client)
        client.post('/api/hierarchy/tier1', json={'about_me': '# Me\n- Name: Test'})
        try:
            body = client.get('/api/hierarchy/compiled-context').json()
            assert 'about_me' in body['tier1_filled']
            assert 'about_my_offers' in body['tier1_unfilled']
        finally:
            self._reset(client)


# ── 4. status reflects real configuration ──────────────────────────────────────


class TestStatusReporting:
    def test_configured_is_false_for_untouched_templates(self, client):
        client.post('/api/hierarchy/tier1/reset')
        body = client.get('/api/hierarchy/status').json()
        assert body['initialized'] is True, 'the files do exist'
        assert body['configured'] is False, 'but the user has not filled them in'
        assert len(body['tier1_unfilled']) == 4

    def test_configured_becomes_true_once_filled(self, client):
        client.post('/api/hierarchy/tier1/reset')
        client.post(
            '/api/hierarchy/tier1',
            json={
                'about_me': '# Me\n- A',
                'about_my_business': '# Biz\n- B',
                'about_my_voice': '# Voice\n- C',
                'about_my_offers': '# Offers\n- D',
            },
        )
        try:
            body = client.get('/api/hierarchy/status').json()
            assert body['configured'] is True
            assert body['tier1_unfilled'] == []
        finally:
            client.post('/api/hierarchy/tier1/reset')

    def test_reset_restores_blank_templates(self, client):
        client.post('/api/hierarchy/tier1', json={'about_me': '# Custom'})
        r = client.post('/api/hierarchy/tier1/reset')
        assert r.status_code == 200
        assert client.get('/api/hierarchy/status').json()['configured'] is False


# ── 5. Project lifecycle ───────────────────────────────────────────────────────


class TestProjectLifecycle:
    def test_delete_removes_the_project(self, client, project):
        project('deleteme')
        assert client.delete('/api/hierarchy/projects/deleteme').status_code == 200
        assert client.get('/api/hierarchy/projects/deleteme').status_code == 404

    def test_delete_missing_is_404(self, client):
        assert client.delete('/api/hierarchy/projects/never_existed').status_code == 404

    def test_delete_rejects_traversal(self, client):
        assert client.delete('/api/hierarchy/projects/..').status_code in (400, 404, 405)

    def test_recreating_is_a_conflict_not_a_silent_overwrite(self, client, project):
        """It replaced meta.json while keeping IVREN content, leaving a project
        whose metadata described something else."""
        project('conflicttest', name='Original')
        r = client.post(
            '/api/hierarchy/projects/create',
            json={'project_id': 'conflicttest', 'name': 'Replacement'},
        )
        assert r.status_code == 409
        meta = client.get('/api/hierarchy/projects/conflicttest').json()['meta']
        assert meta['name'] == 'Original', 'the original metadata must survive'

    def test_create_still_works_normally(self, client, project):
        r = project('normalproj', name='Normal')
        assert r.status_code == 200
        body = client.get('/api/hierarchy/projects/normalproj').json()
        assert set(body['ivren']) == {
            'instructions', 'voice', 'references', 'examples', 'notes'
        }

    def test_empty_id_is_400(self, client):
        r = client.post('/api/hierarchy/projects/create', json={'project_id': '   ', 'name': 'x'})
        assert r.status_code == 400


# ── Frontend ───────────────────────────────────────────────────────────────────


class TestFrontend:
    def test_project_id_is_not_built_into_an_inline_handler(self):
        """Compares against a comment-stripped copy.

        The fix is documented in a comment that necessarily quotes the old
        pattern, so a raw substring search matches the explanation rather than
        the code — the same trap hit in Modules 10 and 12.
        """
        import re

        code = re.sub(r'^\s*//.*$', '', JS, flags=re.MULTILINE)
        assert "onclick=\"selectTier2Project(" not in code
        assert 'data-h-project=' in code

    def test_delete_is_reachable_from_the_ui(self):
        assert 'data-h-delete=' in JS
        assert "method:'DELETE'" in JS

    def test_delete_asks_for_confirmation(self):
        assert 'cannot be undone' in JS

    def test_server_error_detail_is_surfaced(self):
        assert '(await r.json()).detail' in JS
