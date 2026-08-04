"""Module 18 — Workspaces (with Collaborative Edit and Control Tower).

Four real bugs, all reproduced against a live server before being fixed.

1. UNRECOVERABLE DATA LOSS — activating the workspace you are already on.
   The save was guarded by `current_id != ws_id`; the rmtree was not. So the
   unsaved contents of preview/ were deleted and replaced with the last saved
   copy. Switching to a DIFFERENT workspace was survivable (the outgoing one
   was saved first, switching back restored it); this case had no recovery.

2. DATA LOSS UNDER CONCURRENCY — activate_workspace() is a read-modify-write
   over a directory tree (save -> wipe -> repopulate). Two overlapping calls
   interleave and unsaved work is destroyed. Reproduced 3/3 concurrently while
   the identical SEQUENTIAL sequence preserved the file, isolating concurrency
   as the cause. Trigger: the Switch button was not disabled during its await.

3. CROSS-MODULE DESTRUCTION — preview/ is shared by 20 modules. Wiping it
   wholesale destroyed browser_agent screenshots, generated images and branch
   data. This is the same cross-module bug first seen in Module 10.

4. CONTROL TOWER — killing an unknown run reported success AND leaked a
   permanent entry into the in-memory `_kill_flags` set, so a later run with
   that id was dead on arrival.

Plus phantom-success responses (PATCH/DELETE returning ok:true for records
that do not exist) across all three routers.
"""

from __future__ import annotations

import asyncio
import concurrent.futures
import uuid

import pytest

from backend.routers import workspaces as ws_mod


@pytest.fixture()
def workspace(client):
    r = client.post('/api/workspaces', json={'name': 'M18 ' + uuid.uuid4().hex[:6]})
    assert r.status_code == 200, r.text
    wid = r.json()['id']
    yield wid
    client.delete(f'/api/workspaces/{wid}')


def _current(client) -> str:
    return client.get('/api/workspaces/current').json().get('id', '')


# ══ BUG 1 — re-activating the current workspace destroyed unsaved work ════════
def test_reactivating_the_current_workspace_preserves_unsaved_work(client, workspace):
    """The single worst bug in this module: silent, unrecoverable data loss."""
    client.post(f'/api/workspaces/{workspace}/activate')
    assert _current(client) == workspace

    unsaved = ws_mod.PREVIEW_DIR / 'unsaved_work.html'
    unsaved.write_text('PRECIOUS UNSAVED WORK')

    r = client.post(f'/api/workspaces/{workspace}/activate')
    assert r.status_code == 200, r.text

    assert unsaved.exists(), 're-activating the current workspace DELETED unsaved work'
    assert unsaved.read_text() == 'PRECIOUS UNSAVED WORK'


def test_reactivating_the_current_workspace_reports_it(client, workspace):
    client.post(f'/api/workspaces/{workspace}/activate')
    body = client.post(f'/api/workspaces/{workspace}/activate').json()
    assert body.get('already_active') is True, 'a no-op swap should say so'


def test_reactivating_still_saves_to_workspace_storage(client, workspace):
    """The no-op path must still persist preview/, or it just moves the loss."""
    client.post(f'/api/workspaces/{workspace}/activate')
    marker = ws_mod.PREVIEW_DIR / 'to_be_saved.html'
    marker.write_text('SAVE ME')

    client.post(f'/api/workspaces/{workspace}/activate')

    stored = ws_mod.WS_DIR / workspace / 'preview' / 'to_be_saved.html'
    assert stored.exists(), 'the no-op path skipped the save entirely'


# ══ BUG 2 — concurrent activation ════════════════════════════════════════════
def test_concurrent_activation_does_not_destroy_unsaved_work(client, workspace):
    """Two overlapping switches interleaved save/wipe/repopulate and lost data."""
    other = client.post('/api/workspaces', json={'name': 'M18 other'}).json()['id']
    try:
        client.post(f'/api/workspaces/{workspace}/activate')
        marker = ws_mod.PREVIEW_DIR / 'race_marker.html'
        marker.write_text('RACE MARKER')

        with concurrent.futures.ThreadPoolExecutor(max_workers=3) as pool:
            futures = [
                pool.submit(client.post, f'/api/workspaces/{other}/activate')
                for _ in range(3)
            ]
            for f in futures:
                f.result()

        client.post(f'/api/workspaces/{workspace}/activate')
        assert marker.exists(), 'concurrent activation destroyed unsaved work'
    finally:
        client.post(f'/api/workspaces/{workspace}/activate')
        client.delete(f'/api/workspaces/{other}')


def test_activation_is_serialised():
    """A lock, not a comment, is what makes the above hold."""
    import threading

    assert isinstance(ws_mod._activate_lock, type(threading.Lock()))


# ══ BUG 3 — shared preview/ artefacts destroyed on switch ════════════════════
def test_switching_preserves_other_modules_artefacts(client, workspace):
    """preview/ is shared by 20 modules; a switch wiped all of it.

    Same cross-module failure as Module 10, where the image gallery broke
    permanently after a workspace switch.
    """
    other = client.post('/api/workspaces', json={'name': 'M18 shared'}).json()['id']
    try:
        client.post(f'/api/workspaces/{workspace}/activate')

        shots = ws_mod.PREVIEW_DIR / 'browser_screenshots'
        shots.mkdir(parents=True, exist_ok=True)
        (shots / 'evidence.png').write_text('SCREENSHOT BYTES')

        images = ws_mod.PREVIEW_DIR / 'assets' / 'images'
        images.mkdir(parents=True, exist_ok=True)
        (images / 'generated.png').write_text('IMAGE BYTES')

        client.post(f'/api/workspaces/{other}/activate')

        assert (shots / 'evidence.png').exists(), 'browser screenshots destroyed by a switch'
        assert (images / 'generated.png').exists(), 'generated images destroyed by a switch'
    finally:
        client.post(f'/api/workspaces/{workspace}/activate')
        client.delete(f'/api/workspaces/{other}')


def test_project_files_still_swap(client, workspace):
    """The artefact preservation must not accidentally pin project files."""
    other = client.post('/api/workspaces', json={'name': 'M18 swap'}).json()['id']
    try:
        client.post(f'/api/workspaces/{workspace}/activate')
        (ws_mod.PREVIEW_DIR / 'only_in_first.html').write_text('FIRST')

        client.post(f'/api/workspaces/{other}/activate')
        assert not (ws_mod.PREVIEW_DIR / 'only_in_first.html').exists(), (
            'project files leaked across workspaces — isolation is broken'
        )
    finally:
        client.post(f'/api/workspaces/{workspace}/activate')
        client.delete(f'/api/workspaces/{other}')


# ══ Path containment ═════════════════════════════════════════════════════════
@pytest.mark.parametrize('bad', ['..', '../precious', 'a/b', 'x/../..', '', '.', 'a b', 'a;b'])
def test_invalid_workspace_ids_are_refused(bad):
    """`ws_id` reaches shutil.rmtree(). Proven at function level pre-fix:
    delete_workspace('../precious') removed the directory outside WS_DIR.
    """
    assert not ws_mod._valid_ws_id(bad), f'{bad!r} accepted as a workspace id'


def test_ws_root_refuses_escapes():
    for bad in ('..', '../..', 'a/../..'):
        with pytest.raises(ValueError):
            ws_mod._ws_root(bad)


def test_ws_root_resolves_valid_ids():
    assert ws_mod._ws_root('abc123').parent == ws_mod.WS_DIR


def test_delete_does_not_escape_ws_dir(client, tmp_path):
    """The end-to-end version of the containment guard."""
    victim = ws_mod.ROOT / 'zz_m18_victim'
    victim.mkdir(exist_ok=True)
    (victim / 'keep.txt').write_text('IMPORTANT')
    try:
        ws_mod.delete_workspace('../zz_m18_victim')
        assert (victim / 'keep.txt').exists(), 'delete_workspace escaped WS_DIR'
    finally:
        import shutil

        shutil.rmtree(victim, ignore_errors=True)


# ══ Phantom success ══════════════════════════════════════════════════════════
def test_patch_unknown_workspace_is_404(client):
    """UPDATE ... WHERE id=? on a missing row affects 0 rows and raises nothing."""
    r = client.patch('/api/workspaces/nope_does_not_exist', json={'name': 'x'})
    assert r.status_code == 404, 'renaming a nonexistent workspace reported success'


def test_patch_known_workspace_still_works(client, workspace):
    r = client.patch(f'/api/workspaces/{workspace}', json={'name': 'Renamed'})
    assert r.status_code == 200 and r.json()['ok'] is True


def test_delete_unknown_workspace_is_404(client):
    assert client.delete('/api/workspaces/nope_does_not_exist').status_code == 404


def test_save_unknown_workspace_is_404(client):
    assert client.post('/api/workspaces/nope_does_not_exist/save').status_code == 404


def test_delete_active_workspace_is_409(client, workspace):
    client.post(f'/api/workspaces/{workspace}/activate')
    r = client.delete(f'/api/workspaces/{workspace}')
    assert r.status_code == 409, 'refusal must not be a 200'


def test_activate_unknown_workspace_is_404(client):
    assert client.post('/api/workspaces/nope_does_not_exist/activate').status_code == 404


# ══ Export ═══════════════════════════════════════════════════════════════════
def test_export_unknown_workspace_is_404_and_creates_no_directory(client):
    """Exporting a typo'd id returned a valid-looking zip AND made a stray dir.

    A download that looks like a successful backup but contains none of the
    user's work is worse than an error.
    """
    ghost = 'ghost_' + uuid.uuid4().hex[:6]
    r = client.get(f'/api/workspaces/{ghost}/export')
    assert r.status_code == 404
    assert not (ws_mod.WS_DIR / ghost).exists(), 'a failed export left a stray directory'


def test_export_known_workspace_returns_a_zip(client, workspace):
    r = client.get(f'/api/workspaces/{workspace}/export')
    assert r.status_code == 200
    assert r.content[:2] == b'PK', 'not a zip'


def test_export_of_a_non_ascii_named_workspace_does_not_500(client):
    """Found by this test, not by the review: exporting "日本語" returned HTTP 500.

    str.isalnum() is True for CJK, so those characters passed the filename
    filter and reached a Content-Disposition header, which Starlette encodes as
    latin-1 -> UnicodeEncodeError. Any user with a non-Latin workspace name
    simply could not export it.
    """
    wid = client.post('/api/workspaces', json={'name': '日本語'}).json()['id']
    try:
        r = client.get(f'/api/workspaces/{wid}/export')
        assert r.status_code == 200, 'non-ASCII workspace name crashed the export'
        disp = r.headers.get('content-disposition', '')
        assert 'filename=".zip"' not in disp, f'empty export filename: {disp}'
        assert f'workspace_{wid}' in disp, f'expected an id-based fallback name, got: {disp}'
        assert r.content[:2] == b'PK'
    finally:
        client.delete(f'/api/workspaces/{wid}')


def test_export_filename_keeps_ascii_names_readable(client):
    """The ASCII restriction must not mangle ordinary names."""
    wid = client.post('/api/workspaces', json={'name': 'Client A Site'}).json()['id']
    try:
        disp = client.get(f'/api/workspaces/{wid}/export').headers.get('content-disposition', '')
        assert 'Client_A_Site' in disp, disp
    finally:
        client.delete(f'/api/workspaces/{wid}')


# ══ BUG 4 — Control Tower kill ═══════════════════════════════════════════════
def test_killing_an_unknown_run_is_404_not_success(client):
    """The operator hitting a kill switch most needs the truth about it."""
    r = client.post('/api/control/runs/definitely_not_a_run/kill')
    assert r.status_code == 404, 'kill reported success for a run that never existed'


def test_killing_an_unknown_run_does_not_leak_a_permanent_flag(client):
    """`_kill_flags` was added to unconditionally, but only finish_run() clears
    it — and finish_run() returns early for unknown runs. The tombstone then
    killed any future run that happened to reuse the id.
    """
    from backend.routers import control_tower as ct

    ghost = 'run_ghost_' + uuid.uuid4().hex[:8]
    client.post(f'/api/control/runs/{ghost}/kill')
    assert ghost not in ct._kill_flags, 'kill flag leaked for a nonexistent run'

    ct._active_runs[ghost] = {
        'run_id': ghost, 'agent_id': 'a', 'agent_name': 'A', 'prompt': 'p',
        'status': 'running', 'total_cost': 0.0, 'total_tokens': 0,
        'step_count': 0, 'steps': [], 'budget': 0, 'start_time': 0, 'duration_ms': 0,
    }
    try:
        assert ct.record_step(ghost, 'step', 'thinking') is True, (
            'a brand-new run was dead on arrival because of a leaked kill flag'
        )
    finally:
        ct._active_runs.pop(ghost, None)
        ct._kill_flags.discard(ghost)


def test_killing_a_real_run_still_works(client):
    from backend.routers import control_tower as ct

    run_id = ct.start_run('tester', 'Tester', 'do a thing')
    try:
        r = client.post(f'/api/control/runs/{run_id}/kill')
        assert r.status_code == 200 and r.json()['status'] == 'killed'
        assert run_id not in ct._active_runs
    finally:
        ct._active_runs.pop(run_id, None)
        ct._kill_flags.discard(run_id)


# ══ Collab ═══════════════════════════════════════════════════════════════════
def test_closing_an_unknown_collab_session_is_404(client):
    """dict.pop(k, None) never fails, so this always claimed success."""
    assert client.delete('/api/collab/sessions/never_existed').status_code == 404


def test_collab_session_lifecycle(client):
    sid = client.post('/api/collab/sessions', json={'name': 'M18'}).json().get('session_id')
    assert sid, 'could not create a collab session'
    assert client.delete(f'/api/collab/sessions/{sid}').status_code == 200
    assert client.delete(f'/api/collab/sessions/{sid}').status_code == 404, (
        'a second close of the same session still reported success'
    )


def test_collab_state_roundtrip(client):
    sid = client.post('/api/collab/sessions', json={'name': 'M18 state'}).json()['session_id']
    try:
        asyncio.get_event_loop
        r = client.post(f'/api/collab/sessions/{sid}/state', json={'key': 'k', 'value': 42})
        assert r.status_code == 200 and r.json()['ok'] is True
        got = client.get(f'/api/collab/sessions/{sid}/state?key=k').json()
        assert got['value'] == 42
    finally:
        client.delete(f'/api/collab/sessions/{sid}')
