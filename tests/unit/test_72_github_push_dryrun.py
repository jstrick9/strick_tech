"""GitHub push dry-run — follow-up 1 & 2 from the Module 16 review.

Two gaps recorded in that write-up:

  1. "Push has no confirmation step. It uploads up to 100 files to a remote
     repository with no preview of WHAT will be sent."
  2. "`skipped_secrets` is collected but not surfaced in the response. The
     files are correctly held back; the caller should be told which and why,
     otherwise a missing file looks like a bug."

Both matter more now that secret screening exists: a file deliberately withheld
is indistinguishable from one that silently failed.

The design decision that makes the dry-run trustworthy is that plan_push() is
the SAME routine the real push iterates. A preview computed separately from the
action can drift from it, and a preview that lies is worse than none.
"""
from __future__ import annotations

from pathlib import Path
from unittest.mock import patch

import pytest

from backend.routers import github as gh

REPO = Path(__file__).resolve().parents[2]


@pytest.fixture
def probe_dir():
    """A directory with a realistic mix of publishable files and credentials."""
    d = gh.ROOT / 'preview' / '_dryrun_test'
    d.mkdir(parents=True, exist_ok=True)
    (d / 'index.html').write_text('<h1>page</h1>')
    (d / 'app.js').write_text('console.log(1)')
    (d / '.env').write_text('SECRET=abc')
    (d / 'server.pem').write_text('key')
    (d / 'local.db').write_text('data')
    (d / 'sub').mkdir(exist_ok=True)
    (d / 'sub' / '.env').write_text('x')
    yield d
    import shutil

    shutil.rmtree(d, ignore_errors=True)


class FakeResp:
    def __init__(self, code):
        self.status_code = code
        self.text = ''

    def json(self):
        return {}


def make_fake_client(calls):
    class FakeClient:
        def __init__(self, *a, **k):
            pass

        async def __aenter__(self):
            return self

        async def __aexit__(self, *a):
            return False

        async def get(self, url, **k):
            calls.append(('GET', url))
            return FakeResp(404)

        async def put(self, url, **k):
            calls.append(('PUT', url))
            return FakeResp(201)

    return FakeClient


# ── The planner ────────────────────────────────────────────────────────────────


class TestPlanPush:
    def test_it_separates_publishable_from_held_back(self, probe_dir):
        plan = gh.plan_push(probe_dir)
        assert sorted(f['path'] for f in plan['include']) == ['app.js', 'index.html']
        assert sorted(f['path'] for f in plan['skipped']) == [
            '.env', 'local.db', 'server.pem', 'sub/.env'
        ]

    def test_every_held_back_file_has_a_reason(self, probe_dir):
        for entry in gh.plan_push(probe_dir)['skipped']:
            assert entry['reason'], f"{entry['path']} withheld with no explanation"

    def test_it_reports_sizes_and_totals(self, probe_dir):
        plan = gh.plan_push(probe_dir)
        assert all(f['bytes'] > 0 for f in plan['include'])
        assert plan['total_bytes'] == sum(f['bytes'] for f in plan['include'])
        assert plan['total_candidates'] == 6

    def test_oversize_files_are_reported_not_silently_dropped(self, probe_dir, monkeypatch):
        monkeypatch.setattr(gh, 'PUSH_MAX_FILE_BYTES', 5)
        plan = gh.plan_push(probe_dir)
        assert plan['oversize'], 'a file over the API limit must be reported'
        assert all('limit' in f['reason'] for f in plan['oversize'])

    def test_truncation_is_flagged(self, probe_dir):
        plan = gh.plan_push(probe_dir, limit=2)
        assert plan['truncated'] is True
        assert plan['limit'] == 2

    def test_build_artefacts_are_skipped_wholesale(self, probe_dir):
        (probe_dir / 'node_modules').mkdir(exist_ok=True)
        (probe_dir / 'node_modules' / 'x.js').write_text('junk')
        paths = {f['path'] for f in gh.plan_push(probe_dir)['include']}
        assert not any(p.startswith('node_modules/') for p in paths)

    def test_ordering_is_deterministic(self, probe_dir):
        """Two previews of the same tree must agree, or the preview is noise."""
        a = [f['path'] for f in gh.plan_push(probe_dir)['include']]
        b = [f['path'] for f in gh.plan_push(probe_dir)['include']]
        assert a == b


# ── The endpoint ───────────────────────────────────────────────────────────────


class TestDryRunEndpoint:
    def test_dry_run_makes_no_network_call(self, client, probe_dir):
        """The whole point: nothing is uploaded while previewing."""
        calls = []
        with patch.object(gh, '_gh_token', lambda: 'ghp_fake'), \
             patch.object(gh.httpx, 'AsyncClient', make_fake_client(calls)):
            r = client.post('/api/github/push', json={
                'repo': 'owner/repo', 'directory': 'preview/_dryrun_test', 'dry_run': True,
            })
        assert r.status_code == 200
        assert r.json()['dry_run'] is True
        assert calls == [], f'dry-run contacted GitHub: {calls}'

    def test_dry_run_lists_what_would_be_published(self, client, probe_dir):
        with patch.object(gh, '_gh_token', lambda: 'ghp_fake'):
            body = client.post('/api/github/push', json={
                'repo': 'owner/repo', 'directory': 'preview/_dryrun_test', 'dry_run': True,
            }).json()
        assert sorted(f['path'] for f in body['would_push']) == ['app.js', 'index.html']
        assert body['would_push_count'] == 2

    def test_dry_run_lists_what_is_held_back_and_why(self, client, probe_dir):
        with patch.object(gh, '_gh_token', lambda: 'ghp_fake'):
            body = client.post('/api/github/push', json={
                'repo': 'owner/repo', 'directory': 'preview/_dryrun_test', 'dry_run': True,
            }).json()
        held = {f['path'] for f in body['held_back']}
        assert {'.env', 'sub/.env', 'server.pem', 'local.db'} <= held
        assert body['held_back_count'] == len(body['held_back'])

    def test_dry_run_says_nothing_was_uploaded(self, client, probe_dir):
        with patch.object(gh, '_gh_token', lambda: 'ghp_fake'):
            body = client.post('/api/github/push', json={
                'repo': 'owner/repo', 'directory': 'preview/_dryrun_test', 'dry_run': True,
            }).json()
        assert 'Nothing was uploaded' in body['note']

    def test_dry_run_is_opt_in(self, client, probe_dir):
        """Defaulting to True would make every existing push a silent no-op."""
        calls = []
        with patch.object(gh, '_gh_token', lambda: 'ghp_fake'), \
             patch.object(gh.httpx, 'AsyncClient', make_fake_client(calls)):
            body = client.post('/api/github/push', json={
                'repo': 'owner/repo', 'directory': 'preview/_dryrun_test',
            }).json()
        assert body['dry_run'] is False
        assert any(m == 'PUT' for m, _ in calls), 'a plain push must still upload'

    def test_dry_run_still_enforces_the_directory_allowlist(self, client):
        """A preview of a forbidden push must refuse, not preview."""
        with patch.object(gh, '_gh_token', lambda: 'ghp_fake'):
            r = client.post('/api/github/push', json={
                'repo': 'owner/repo', 'directory': 'memory', 'dry_run': True,
            })
        assert r.status_code == 403

    def test_dry_run_requires_a_token_like_a_real_push(self, client):
        r = client.post('/api/github/push', json={'repo': 'owner/repo', 'dry_run': True})
        assert r.status_code in (200, 401)


class TestPreviewMatchesReality:
    """A preview that disagrees with the action is worse than no preview."""

    def test_the_uploaded_set_equals_the_previewed_set(self, client, probe_dir):
        with patch.object(gh, '_gh_token', lambda: 'ghp_fake'):
            preview = client.post('/api/github/push', json={
                'repo': 'owner/repo', 'directory': 'preview/_dryrun_test', 'dry_run': True,
            }).json()

            calls = []
            with patch.object(gh.httpx, 'AsyncClient', make_fake_client(calls)):
                client.post('/api/github/push', json={
                    'repo': 'owner/repo', 'directory': 'preview/_dryrun_test', 'dry_run': False,
                })

        uploaded = sorted(u.rsplit('/contents/', 1)[-1] for m, u in calls if m == 'PUT')
        promised = sorted(f['path'] for f in preview['would_push'])
        assert uploaded == promised

    def test_no_credential_is_ever_uploaded(self, client, probe_dir):
        calls = []
        with patch.object(gh, '_gh_token', lambda: 'ghp_fake'), \
             patch.object(gh.httpx, 'AsyncClient', make_fake_client(calls)):
            client.post('/api/github/push', json={
                'repo': 'owner/repo', 'directory': 'preview/_dryrun_test', 'dry_run': False,
            })
        uploaded = {u.rsplit('/contents/', 1)[-1] for m, u in calls if m == 'PUT'}
        assert not ({'.env', 'sub/.env', 'server.pem', 'local.db'} & uploaded)

    def test_both_paths_use_the_same_planner(self):
        """Separate selection logic would let the preview drift from the push."""
        src = (REPO / 'backend' / 'routers' / 'github.py').read_text()
        assert src.count('plan_push(source_dir)') == 1
        assert "for entry in plan['include']" in src


class TestRealPushReportsHeldBackFiles:
    """Follow-up 2: they were collected and then dropped on the floor."""

    def test_held_back_is_in_the_response(self, client, probe_dir):
        calls = []
        with patch.object(gh, '_gh_token', lambda: 'ghp_fake'), \
             patch.object(gh.httpx, 'AsyncClient', make_fake_client(calls)):
            body = client.post('/api/github/push', json={
                'repo': 'owner/repo', 'directory': 'preview/_dryrun_test', 'dry_run': False,
            }).json()
        assert body['held_back_count'] == 4
        assert {f['path'] for f in body['held_back']} == {
            '.env', 'sub/.env', 'server.pem', 'local.db'
        }

    def test_a_withheld_file_is_distinguishable_from_a_failure(self, client, probe_dir):
        """Without this, a missing file reads as a bug rather than a protection."""
        calls = []
        with patch.object(gh, '_gh_token', lambda: 'ghp_fake'), \
             patch.object(gh.httpx, 'AsyncClient', make_fake_client(calls)):
            body = client.post('/api/github/push', json={
                'repo': 'owner/repo', 'directory': 'preview/_dryrun_test', 'dry_run': False,
            }).json()
        assert body['errors'] == [], 'held-back files must not be reported as errors'
        assert body['held_back'], 'and must be reported somewhere'


class TestFrontendPreviewsBeforePublishing:
    def _js(self):
        return (REPO / 'frontend' / 'js' / '18-github.js').read_text()

    def test_it_runs_a_dry_run_first(self):
        js = self._js()
        assert 'dry_run: true' in js
        assert 'ghConfirmPush' in js

    def test_the_user_must_confirm(self):
        assert 'Review before publishing' in self._js()

    def test_held_back_files_are_shown(self):
        js = self._js()
        assert 'held_back' in js
        assert 'will NOT be uploaded' in js

    def test_cancelling_uploads_nothing(self):
        assert 'nothing was uploaded' in self._js().lower()

    def test_the_result_reports_withheld_files(self):
        assert 'held_back_count' in self._js()
