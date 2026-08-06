"""Refused writes answer 4xx, and setup progress reports reality.

Two findings, both of the same family: the server told the user something had
worked when it had not.
"""
import os
import re
import sys
import time

import pytest

REPO = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))


def _read(path: str) -> str:
    with open(path, encoding='utf-8') as fh:
        return fh.read()


# ══ 1. 200-on-failure for mutating requests ═══════════════════════════════════

MUTATING_REFUSALS = [
    ('/api/agents', {}),                    # "name is required"
    ('/api/hooks', {}),                     # "prompt is required"
    ('/api/evals/run', {}),                 # "prompt and response required"
    ('/api/skills', {}),                    # "name required"
    ('/api/pipeline/run', {}),              # "goal required"
    ('/api/project/memory', {}),            # "key and value required"
    ('/api/sessions/auto-title', {}),       # "prompt or session_id required"
    ('/api/testgen/generate', {}),          # "filepath required"
    ('/api/templates/scaffold-custom', {}), # "name required"
    ('/api/memory/import', {}),             # "memories list required"
]


@pytest.mark.parametrize('path,body', MUTATING_REFUSALS)
def test_a_refused_write_does_not_answer_200(client, path, body):
    """62 mutating endpoints answered `200 {"ok": false, ...}`.

    This matters more than it looks. frontend/js/00-net-feedback.js reports
    failures by STATUS CODE — 5xx, 429, 401, 403. A 200 sails straight through
    it, so the user is told nothing at all: the dialog closes, the list does
    not change, and the action silently did not happen.
    """
    resp = client.post(path, json=body)
    if resp.status_code == 404:
        pytest.skip(f'{path} not mounted in this build')
    payload = resp.json() if resp.headers.get('content-type', '').startswith('application/json') else {}
    if payload.get('ok') is not False:
        pytest.skip(f'{path} accepted an empty body; not a refusal case')
    assert resp.status_code >= 400, (
        f'{path} refused the write ({payload.get("error")!r}) but answered '
        f'HTTP {resp.status_code}, so the global error handler stays silent'
    )


def test_the_body_of_a_refused_write_is_preserved(client):
    """Only the status changes. A client reading `ok`/`error` sees what it did
    before, so this cannot break an existing caller."""
    resp = client.post('/api/agents', json={})
    if resp.status_code == 404:
        pytest.skip('/api/agents not mounted')
    body = resp.json()
    assert body.get('ok') is False
    assert 'name' in str(body.get('error', '')).lower()


def test_reads_are_untouched(client):
    """A GET reporting ok:false is describing state, not refusing work.

    Verified when this was built: 0 of 287 GET endpoints returned 200 with
    ok:false, so the middleware could not have changed a read even if it
    applied to them — but the scope guard is asserted so it stays that way.
    """
    src = _read(os.path.join(REPO, 'backend', 'app.py'))
    call = src.index('response = await _restatus_refused_write(')
    guard = src[call - 500:call]
    assert "request.method in ('POST', 'PUT', 'PATCH', 'DELETE')" in guard, (
        f'the re-status rule is no longer scoped to mutating methods:\n{guard[-300:]}'
    )
    assert "path.startswith('/api/')" in guard, 'the rule is no longer scoped to /api/'


def test_report_style_endpoints_stay_200(client):
    """`ok: false` that is a RESULT, not a refusal.

    A connection test that runs and finds the service down has succeeded at
    testing. Turning that into a 4xx would make a working feature look broken.
    """
    resp = client.post('/api/secrets/test-connection', json={})
    if resp.status_code == 404:
        pytest.skip('endpoint not mounted')
    assert resp.status_code == 200, (
        'a diagnostic endpoint reporting a negative result was turned into an error'
    )


def test_the_exemption_list_is_explicit_and_small(client):
    """Exemption lists grow quietly. Pinning it makes each addition a visible
    decision rather than a line nobody reviews."""
    from backend.app import _OK_FALSE_EXEMPT

    allowed = {
        # diagnostics: the negative answer IS the successful result
        '/api/secrets/test-connection',
        '/api/pluginsdk/validate',
        '/api/security/validate-csrf',
        '/api/rbac/tokens/verify',
        # policy verdicts: the engine ran and returned "deny"
        '/api/mcp-gateway/call',
        '/api/connectors/execute',
        # "nothing to do" is a normal outcome
        '/api/system/git/commit',
        '/api/tauri/build/cancel',
        '/api/gitai/changelog',
        '/api/memory/qdrant/sync-all',
        # unconfigured integration: the response carries setup instructions
        '/api/deploy/vercel',
        '/api/deploy/netlify',
    }
    extra = set(_OK_FALSE_EXEMPT) - allowed
    assert not extra, f'undocumented exemptions crept in: {sorted(extra)}'


# ══ 2. Install jobs: real progress, real outcomes ═════════════════════════════

def test_a_failed_install_is_reported_as_failed():
    """The old code reported success for a process that exited non-zero.

    `subprocess.Popen(...)` with the handle discarded returns ok:true whenever
    the spawn itself does not raise — which is essentially always. Paired with
    a fake progress stream, a failed install and a successful one produced the
    same green toast.
    """
    from backend.services import install_jobs

    install_jobs.reset('unit-fail')
    install_jobs.start('unit-fail', [
        sys.executable, '-u', '-c',
        'import sys; print("Collecting thing"); print("ERROR: nope"); sys.exit(1)'])
    for _ in range(60):
        snap = install_jobs.snapshot('unit-fail')
        if snap['status'] != 'running':
            break
        time.sleep(0.1)
    assert snap['status'] == 'failed', f'a non-zero exit was reported as {snap["status"]}'
    assert snap['returncode'] == 1
    assert 'nope' in str(snap['error']), 'the failure text was not captured'
    install_jobs.reset('unit-fail')


def test_a_successful_install_is_reported_as_done_with_its_output():
    from backend.services import install_jobs

    install_jobs.reset('unit-ok')
    install_jobs.start('unit-ok', [
        sys.executable, '-u', '-c', 'print("Compiling x"); print("Installing tauri-cli")'])
    for _ in range(60):
        snap = install_jobs.snapshot('unit-ok')
        if snap['status'] != 'running':
            break
        time.sleep(0.1)
    assert snap['status'] == 'done'
    assert snap['returncode'] == 0
    assert any('Compiling' in ln for ln in snap['lines']), 'real output was not captured'
    install_jobs.reset('unit-ok')


def test_a_spawn_failure_is_not_reported_as_success():
    """The specific case the old `try/except Popen` got wrong."""
    from backend.services import install_jobs

    install_jobs.reset('unit-spawn')
    job = install_jobs.start('unit-spawn', ['/definitely/not/a/binary/xyz'])
    assert job['status'] == 'failed'
    assert job['error']
    install_jobs.reset('unit-spawn')


def test_a_second_start_does_not_spawn_a_duplicate():
    """Two concurrent `cargo install` runs fight over the same lock file and
    both fail confusingly."""
    from backend.services import install_jobs

    install_jobs.reset('unit-dup')
    a = install_jobs.start('unit-dup', [sys.executable, '-u', '-c', 'import time; time.sleep(2)'])
    b = install_jobs.start('unit-dup', [sys.executable, '-u', '-c', 'import time; time.sleep(2)'])
    assert a is b or a['pid'] == b['pid'], 'a second installer was spawned over a running one'
    install_jobs.reset('unit-dup')


def test_the_log_buffer_is_bounded():
    """A compile log must not be able to exhaust memory."""
    from backend.services import install_jobs

    install_jobs.reset('unit-big')
    install_jobs.start('unit-big', [
        sys.executable, '-u', '-c', 'for i in range(3000): print("line", i)'])
    for _ in range(100):
        snap = install_jobs.snapshot('unit-big')
        if snap['status'] != 'running':
            break
        time.sleep(0.1)
    assert len(snap['lines']) <= 401, f'log buffer grew to {len(snap["lines"])} lines'
    install_jobs.reset('unit-big')


# ══ 3. The fake progress streams are gone ═════════════════════════════════════

@pytest.mark.parametrize('router,label', [
    ('tauri_build.py', 'Rust & Tauri CLI'),
    ('browser_agent.py', 'Playwright & Chromium'),
])
def test_setup_streams_no_longer_emit_invented_progress(router, label):
    """Both streams slept on a timer and then declared success.

    tauri_build.py emitted "✅ Setup complete! Rust & Tauri CLI are ready."
    after five hardcoded steps 0.6s apart — about three seconds, against a
    `cargo install` that takes on the order of ten minutes. browser_agent.py
    did the same over four steps for a 130MB Chromium download.
    """
    src = _read(os.path.join(REPO, 'backend', 'routers', router))
    # Strip BOTH # comments and triple-quoted docstrings so this cannot match
    # the text of its own fix. 11th instance of that trap in this review: the
    # first version failed against the FIXED build, because the docstring
    # explaining what the fake stream used to emit quotes the very string it
    # asserts is gone.
    code = re.sub(r'"""[\s\S]*?"""', '', src)
    code = re.sub(r"'''[\s\S]*?'''", '', code)
    code = '\n'.join(ln for ln in code.split('\n') if not ln.strip().startswith('#'))
    assert 'install_jobs' in code, f'{router} no longer tracks the real job'
    assert not re.search(r'steps\s*=\s*\[\s*\(\d+,', code), (
        f'{router} has a hardcoded progress step list again'
    )
    assert 'Setup complete!' not in code, (
        f'{router} still claims completion without checking'
    )


def test_the_idle_stream_says_nothing_is_running(client):
    """Asking for progress when no install exists must not fabricate one."""
    with client.stream('GET', '/api/tauri/setup/stream') as resp:
        if resp.status_code == 404:
            pytest.skip('endpoint not mounted')
        first = next(resp.iter_lines())
        text = first if isinstance(first, str) else first.decode()
    assert 'No installation is running' in text, f'idle stream said: {text[:160]}'
    assert '"ok": false' in text or '"ok":false' in text


def test_the_ui_branches_on_the_real_outcome():
    """`if (d.done)` alone always toasted success. It must honour `ok`."""
    for path in ('frontend/js/43-browser-agent.js', 'frontend/js/03-features-a.js'):
        src = _read(os.path.join(REPO, path))
        code = '\n'.join(ln for ln in src.split('\n') if not ln.strip().startswith('//'))
        idx = code.find('if (d.done)')
        assert idx != -1, f'{path}: the stream handler is gone'
        block = code[idx:idx + 1400]
        assert 'd.ok' in block, f'{path} still declares success on `done` alone'
        assert 'err' in block or 'danger' in block, f'{path} has no failure branch'
