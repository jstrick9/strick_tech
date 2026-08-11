"""Module 19 — the GitHub workstation: the `github` host and its `deploy` tab.

Destination: `github`, hosting gitai and deploy. `gitai` was covered by module 9
(doc 70); this pass closes the host pane and `deploy`.

This is the publishing surface — the last step before something the user built
becomes public — so a false success here is expensive in a way a dashboard's is
not: the artefact is already live and wrong.

Eight defects, all reproduced against a live server before the fix:

1. EVERY IMAGE, FONT AND MEDIA FILE WAS SILENTLY DROPPED FROM THE DEPLOY.
   `_BINARY_EXTS` was an EXCLUSION list: .png/.jpg/.svg/.woff/... were skipped
   entirely, and the deploy then reported plain success. A static site published
   without its logo, favicon or webfonts is broken and nothing said so.
   Verified: preview/ with index.html, app.js and assets/logo.png collected
   exactly two files. Vercel's API takes {"encoding":"base64"} and Netlify takes
   a zip, so both could always have carried binaries.

2. Files over the (1 MB) size cap and archives were dropped just as silently.

3. `errors='replace'` meant any binary NOT caught by the extension list was
   uploaded as UTF-8 replacement characters — a corrupt file at the far end
   rather than an absent one.

4. Netlify's zip was built from `f['data']`, so with (1) fixed a base64 entry
   would have written the base64 TEXT into the archive.

5. THE PANE PROMISED MORE FILES THAN IT WOULD PUBLISH. /status counted every
   file on disk and the UI rendered "N files ready in preview/", while a deploy
   shipped a different, smaller set. Verified live: status said 4, the deploy
   carried 2.

6. Netlify was the only provider that never recorded its deploy — no
   memory_add, no audit_log — so a real Netlify deploy was missing from
   /api/deploy/history.

7. A PARTIAL GITHUB PUSH REPORTED SUCCESS. `ok` was `files_pushed > 0`, so 1 of
   200 files uploading with 199 failures rendered "✅ Pushed to GitHub!" while
   the repository sat half-written.

8. /status's `ready` flag is computed from token PRESENCE and had never been
   checked against the provider, and deploy history used SQLite `localtime`
   which the response layer then stamped `Z` — local time labelled as UTC.
"""

from __future__ import annotations

import io
import zipfile

import pytest

from backend.routers import deploy as dep


@pytest.fixture
def preview(tmp_path, monkeypatch):
    """A preview/ directory with a text file, a real binary and an asset."""
    d = tmp_path / 'preview'
    (d / 'assets').mkdir(parents=True)
    (d / 'index.html').write_text('<html><img src="assets/logo.png"></html>')
    (d / 'app.js').write_text('console.log(1)')
    # A real PNG header — the bytes must survive the round trip intact.
    (d / 'assets' / 'logo.png').write_bytes(b'\x89PNG\r\n\x1a\n' + bytes(range(256)) * 2)
    monkeypatch.setattr(dep, 'PREVIEW_DIR', d)
    return d


# ── 1. binaries are deployed, not silently dropped ────────────────────────────
def test_images_are_included_in_the_deploy(preview):
    files, _ = dep.collect_deploy_files(preview)
    names = {f['file'] for f in files}
    assert 'assets/logo.png' in names, (
        'the site logo was silently dropped and the deploy still reported success'
    )


def test_binaries_are_base64_encoded_not_mangled_as_text(preview):
    files, _ = dep.collect_deploy_files(preview)
    png = next(f for f in files if f['file'] == 'assets/logo.png')
    assert png['encoding'] == 'base64'
    assert dep._file_bytes(png) == (preview / 'assets' / 'logo.png').read_bytes()


def test_text_files_are_still_sent_as_utf8(preview):
    files, _ = dep.collect_deploy_files(preview)
    html = next(f for f in files if f['file'] == 'index.html')
    assert html['encoding'] == 'utf-8'
    assert html['data'].startswith('<html>')


def test_fonts_and_media_are_included(preview):
    (preview / 'font.woff2').write_bytes(b'wOF2' + b'\x00\x01\x02' * 10)
    (preview / 'clip.mp4').write_bytes(b'\x00\x00\x00\x18ftypmp42')
    names = {f['file'] for f in dep.collect_deploy_files(preview)[0]}
    assert {'font.woff2', 'clip.mp4'} <= names


def test_an_svg_survives_the_round_trip(preview):
    """SVG was on the exclusion list despite being plain text."""
    svg = '<svg xmlns="http://www.w3.org/2000/svg"><circle r="5"/></svg>'
    (preview / 'icon.svg').write_text(svg)
    files, _ = dep.collect_deploy_files(preview)
    entry = next(f for f in files if f['file'] == 'icon.svg')
    assert dep._file_bytes(entry).decode() == svg


# ── 2. exclusions are reported, never silent ──────────────────────────────────
def test_an_oversize_file_is_reported_not_just_skipped(preview):
    (preview / 'huge.css').write_text('a{}' * 4_000_000)  # ~12 MB
    files, excluded = dep.collect_deploy_files(preview)
    assert 'huge.css' not in {f['file'] for f in files}
    entry = next(e for e in excluded if e['file'] == 'huge.css')
    assert 'exceeds' in entry['reason']


def test_archives_are_excluded_with_a_reason(preview):
    (preview / 'bundle.zip').write_bytes(b'PK\x03\x04' + b'x' * 50)
    _, excluded = dep.collect_deploy_files(preview)
    assert any(e['file'] == 'bundle.zip' for e in excluded)


def test_a_clean_preview_reports_no_exclusions(preview):
    """The warning must not cry wolf on a site that deploys whole."""
    files, excluded = dep.collect_deploy_files(preview)
    assert excluded == []
    assert dep._deploy_warning(excluded) is None


def test_the_warning_names_the_missing_files(preview):
    (preview / 'bundle.zip').write_bytes(b'PK')
    _, excluded = dep.collect_deploy_files(preview)
    warning = dep._deploy_warning(excluded)
    assert 'bundle.zip' in warning
    assert 'NOT deployed' in warning


def test_node_modules_and_git_are_still_skipped(preview):
    (preview / 'node_modules').mkdir()
    (preview / 'node_modules' / 'x.js').write_text('x')
    names = {f['file'] for f in dep.collect_deploy_files(preview)[0]}
    assert not any('node_modules' in n for n in names)


# ── 3. a non-UTF8 file with a text extension must not be corrupted ────────────
def test_an_undeclared_binary_is_base64d_rather_than_corrupted(preview):
    """`errors='replace'` turned these into replacement characters — a corrupt
    file at the other end, which is worse than an absent one."""
    (preview / 'data.txt').write_bytes(b'\xff\xfe\x00\x01 not utf-8')
    files, _ = dep.collect_deploy_files(preview)
    entry = next(f for f in files if f['file'] == 'data.txt')
    assert entry['encoding'] == 'base64'
    assert dep._file_bytes(entry) == b'\xff\xfe\x00\x01 not utf-8'
    assert '\ufffd' not in entry['data']


# ── 4. the Netlify zip must carry real bytes ──────────────────────────────────
def test_the_netlify_zip_uploaded_contains_the_real_binary(client, preview, monkeypatch):
    """Inspects the archive the ENDPOINT actually posts to Netlify.

    An earlier version of this test built the zip itself from
    collect_deploy_files + _file_bytes, which is not the code path the router
    uses -- reverting the router's zip line changed nothing and the test still
    passed. Capture the real upload instead.
    """
    import httpx

    monkeypatch.setenv('NETLIFY_TOKEN', 'tok')
    captured: dict = {}

    async def fake_post(self, url, *a, **k):
        captured['content'] = k.get('content')
        return httpx.Response(201, json={'ssl_url': 'https://x.netlify.app'}, request=httpx.Request('POST', url))

    monkeypatch.setattr(httpx.AsyncClient, 'post', fake_post)
    assert client.post('/api/deploy/netlify', json={}).json()['ok'] is True

    z = zipfile.ZipFile(io.BytesIO(captured['content']))
    assert 'assets/logo.png' in z.namelist(), 'the image never reached the archive'
    assert z.read('assets/logo.png').startswith(b'\x89PNG'), (
        'the zip carried base64 text instead of the file bytes'
    )
    assert z.read('assets/logo.png') == (preview / 'assets' / 'logo.png').read_bytes()
    assert z.read('index.html') == (preview / 'index.html').read_bytes()


# ── 5. the pane must promise what it will actually publish ────────────────────
def test_status_counts_deployable_files_not_files_on_disk(client, preview):
    (preview / 'bundle.zip').write_bytes(b'PK')
    body = client.get('/api/deploy/status').json()
    deployable, excluded = dep.collect_deploy_files(preview)
    assert body['preview_files'] == len(deployable), (
        'the pane advertised more files than a deploy would publish'
    )
    assert body['excluded_count'] == len(excluded) == 1


def test_status_names_the_files_it_will_not_deploy(client, preview):
    (preview / 'bundle.zip').write_bytes(b'PK')
    body = client.get('/api/deploy/status').json()
    assert body['excluded_files'][0]['file'] == 'bundle.zip'
    assert body['excluded_files'][0]['reason']


def test_status_states_the_basis_of_its_ready_flags(client):
    """`ready` is token PRESENCE; it has never been checked against a provider.
    A green tick that means something weaker than the user assumes must say so."""
    body = client.get('/api/deploy/status').json()
    assert 'not verified' in body['readiness_basis']


def test_providers_list_matches_what_is_advertised(client):
    body = client.get('/api/deploy/providers').json()
    assert body['count'] == len(body['providers'])
    assert len(body['detail']) == body['count']
    assert {d['id'] for d in body['detail']} == set(body['providers'])


# ── 6. every provider records its deploy ──────────────────────────────────────
def test_netlify_records_its_deploy_like_every_other_provider(client, preview, monkeypatch):
    """netlify was the only provider with no memory_add/audit_log, so a real
    Netlify deploy left no trace in /api/deploy/history."""
    import httpx

    monkeypatch.setenv('NETLIFY_TOKEN', 'tok')
    calls: list[tuple[str, str]] = []
    from backend.services import memory_db

    real_add, real_audit = memory_db.memory_add, memory_db.audit_log
    monkeypatch.setattr(
        memory_db, 'memory_add', lambda s, c, t='': (calls.append(('mem', s)), real_add(s, c, t))[1]
    )
    monkeypatch.setattr(
        memory_db, 'audit_log', lambda a, d='': (calls.append(('audit', a)), real_audit(a, d))[1]
    )

    async def fake_post(self, url, *a, **k):
        return httpx.Response(
            201, json={'ssl_url': 'https://x.netlify.app', 'id': 's1'}, request=httpx.Request('POST', url)
        )

    monkeypatch.setattr(httpx.AsyncClient, 'post', fake_post)
    body = client.post('/api/deploy/netlify', json={}).json()
    assert body['ok'] is True
    assert any(c[1] == 'deploy:netlify' for c in calls), 'the deploy was never recorded'


def test_netlify_reports_what_it_left_out(client, preview, monkeypatch):
    import httpx

    monkeypatch.setenv('NETLIFY_TOKEN', 'tok')
    (preview / 'bundle.zip').write_bytes(b'PK')

    async def fake_post(self, url, *a, **k):
        return httpx.Response(201, json={'ssl_url': 'https://x.netlify.app'}, request=httpx.Request('POST', url))

    monkeypatch.setattr(httpx.AsyncClient, 'post', fake_post)
    body = client.post('/api/deploy/netlify', json={}).json()
    assert body['excluded_count'] == 1
    assert body['warning'] and 'bundle.zip' in body['warning']


def test_vercel_reports_what_it_left_out(client, preview, monkeypatch):
    """Both API providers share the collector; both must disclose."""
    import httpx

    monkeypatch.setenv('VERCEL_TOKEN', 'tok')
    (preview / 'bundle.zip').write_bytes(b'PK')

    async def fake_post(self, url, *a, **k):
        return httpx.Response(200, json={'url': 'x.vercel.app', 'id': 'd1'}, request=httpx.Request('POST', url))

    monkeypatch.setattr(httpx.AsyncClient, 'post', fake_post)
    body = client.post('/api/deploy/vercel', json={}).json()
    assert body['ok'] is True
    assert body['excluded_count'] == 1
    assert 'bundle.zip' in body['warning']


def test_deploy_history_timestamps_are_utc_not_local(client, monkeypatch):
    from backend.services import memory_db

    memory_db.audit_log('deploy:probe155', 'ts check')
    rows = client.get('/api/deploy/history').json()
    row = next((r for r in rows if r.get('source') == 'deploy:probe155'), None)
    assert row is not None
    con = memory_db.get_conn()
    try:
        raw = con.execute(
            "SELECT created_at FROM audit WHERE action='deploy:probe155' ORDER BY id DESC LIMIT 1"
        ).fetchone()[0]
    finally:
        con.close()
    assert row['created_at'].replace('T', ' ').rstrip('Z') == raw


# ── 7. a partial GitHub push is not a success ─────────────────────────────────
def _push(monkeypatch, results, preview_dir):
    """Drive /api/github/push with a scripted per-file PUT outcome."""
    import httpx

    from backend.routers import github as gh

    monkeypatch.setenv('GITHUB_TOKEN', 'ghp_test')
    monkeypatch.setattr(gh, 'resolve_push_dir', lambda d: (preview_dir, ''))
    monkeypatch.setattr(
        gh,
        'plan_push',
        lambda d: {
            'include': [{'path': p} for p in results],
            'skipped': [],
            'oversize': [],
            'total_bytes': 10,
            'total_candidates': len(results),
            'truncated': False,
            'limit': 500,
        },
    )

    async def fake_get(self, url, *a, **k):
        return httpx.Response(404, json={}, request=httpx.Request('GET', url))

    async def fake_put(self, url, *a, **k):
        for path, code in results.items():
            if path in url:
                return httpx.Response(code, json={}, request=httpx.Request('PUT', url))
        return httpx.Response(500, json={}, request=httpx.Request('PUT', url))

    monkeypatch.setattr(httpx.AsyncClient, 'get', fake_get)
    monkeypatch.setattr(httpx.AsyncClient, 'put', fake_put)


def test_a_push_where_most_files_failed_is_not_reported_as_success(client, preview, monkeypatch):
    for name in ('a.txt', 'b.txt', 'c.txt'):
        (preview / name).write_text('x')
    _push(monkeypatch, {'a.txt': 201, 'b.txt': 422, 'c.txt': 422}, preview)
    body = client.post('/api/github/push', json={'repo': 'o/r', 'dry_run': False}).json()
    assert body['ok'] is False, '1 of 3 files uploading rendered "✅ Pushed to GitHub!"'
    assert body['status'] == 'partial'
    assert body['files_pushed'] == 1 and body['files_failed'] == 2
    assert 'partial state' in body['error']


def test_a_fully_successful_push_is_still_ok(client, preview, monkeypatch):
    for name in ('a.txt', 'b.txt'):
        (preview / name).write_text('x')
    _push(monkeypatch, {'a.txt': 201, 'b.txt': 200}, preview)
    body = client.post('/api/github/push', json={'repo': 'o/r', 'dry_run': False}).json()
    assert body['ok'] is True
    assert body['status'] == 'complete'
    assert body['files_failed'] == 0
    assert body['error'] is None


def test_a_push_where_everything_failed_is_reported_failed(client, preview, monkeypatch):
    (preview / 'a.txt').write_text('x')
    _push(monkeypatch, {'a.txt': 500}, preview)
    body = client.post('/api/github/push', json={'repo': 'o/r', 'dry_run': False}).json()
    assert body['ok'] is False
    assert body['status'] == 'failed'
    assert body['files_pushed'] == 0


def test_the_push_audit_entry_records_the_real_ratio(client, preview, monkeypatch):
    for name in ('a.txt', 'b.txt'):
        (preview / name).write_text('x')
    _push(monkeypatch, {'a.txt': 201, 'b.txt': 422}, preview)
    client.post('/api/github/push', json={'repo': 'o/r', 'dry_run': False})
    from backend.services import memory_db

    con = memory_db.get_conn()
    try:
        detail = con.execute(
            "SELECT detail FROM audit WHERE action='github_push' ORDER BY id DESC LIMIT 1"
        ).fetchone()[0]
    finally:
        con.close()
    assert '1/2' in detail and 'partial' in detail, (
        'the audit log recorded only a count, so a partial push looked complete'
    )


# ── 8. tunnel state hygiene ───────────────────────────────────────────────────
def test_stopping_a_tunnel_clears_the_registry(client, monkeypatch):
    class FakeProc:
        returncode = None

        def terminate(self):
            FakeProc.returncode = 0

    monkeypatch.setitem(dep._active_tunnel, 'proc', FakeProc())
    monkeypatch.setitem(dep._active_tunnel, 'url', 'https://x.trycloudflare.com')
    body = client.post('/api/deploy/tunnel/stop').json()
    assert body['ok'] is True
    assert dep._active_tunnel['proc'] is None
    assert dep._active_tunnel['url'] is None


def test_a_dead_tunnel_left_in_the_registry_is_cleared(client, monkeypatch):
    """A stale non-None proc made the next start refuse as 'already running'."""

    class DeadProc:
        returncode = 1

    monkeypatch.setitem(dep._active_tunnel, 'proc', DeadProc())
    monkeypatch.setitem(dep._active_tunnel, 'url', 'https://old.trycloudflare.com')
    client.post('/api/deploy/tunnel/stop')
    assert dep._active_tunnel['proc'] is None, 'a dead tunnel blocked the next start'


def test_tunnel_status_reports_inactive_when_nothing_is_running(client, monkeypatch):
    monkeypatch.setitem(dep._active_tunnel, 'proc', None)
    monkeypatch.setitem(dep._active_tunnel, 'url', None)
    body = client.get('/api/deploy/tunnel').json()
    assert body['active'] is False
    assert body['url'] is None
