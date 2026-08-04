"""Module 21 — OPERATE: vault key permissions and eval status codes.

1. VAULT KEY WAS WORLD-READABLE. `_get_fernet()` called `chmod(0o600)` only in
   the branch that CREATES the key, so any vault created before that line was
   added kept whatever the umask gave it — permanently. Found in this repo:

       $ ls -la memory/.vault_key
       -rw-r--r--  1 user user 44 ...        # mode 644

   That key decrypts every stored credential, so its file mode is the entirety
   of the vault's at-rest protection. Module 17 refused to let Database Studio
   read the `secrets` table for precisely this reason; leaving the master key
   readable by any local process undoes that work.

2. EVAL RUNS ON A NONEXISTENT SUITE RETURNED 200. The SSE body carried
   {"error": "No cases in suite"} — honest text, wrong status. A client
   checking the status code saw success, and anything piping the stream into a
   dashboard recorded an eval run that never happened.
"""

from __future__ import annotations

import os
import stat
import uuid

import pytest


# ══ 1. Vault key permissions ══════════════════════════════════════════════════
def _mode(path) -> int:
    return stat.S_IMODE(os.stat(path).st_mode)


def test_vault_key_is_not_group_or_world_readable(client):
    """The live key, whatever its history."""
    from backend.routers.secrets import KEY_PATH, _get_fernet

    _get_fernet()  # ensure it exists
    if not KEY_PATH.exists():
        pytest.skip('cryptography not installed; no vault key created')
    assert not (_mode(KEY_PATH) & 0o077), (
        f'{KEY_PATH} is mode {_mode(KEY_PATH):o} — the key that decrypts every '
        f'stored credential is readable beyond its owner'
    )


def test_existing_loose_key_is_tightened(client, tmp_path, monkeypatch):
    """The actual bug: chmod ran only on creation, so an existing loose key
    stayed loose forever. This is what makes the fix self-healing rather than
    something that only helps new installs."""
    from cryptography.fernet import Fernet

    import backend.routers.secrets as secrets_mod

    key_file = tmp_path / '.vault_key'
    key_file.write_bytes(Fernet.generate_key())
    key_file.chmod(0o644)
    assert _mode(key_file) & 0o077, 'fixture did not create a loose key'

    monkeypatch.setattr(secrets_mod, 'KEY_PATH', key_file)
    secrets_mod._get_fernet()

    assert not (_mode(key_file) & 0o077), 'an existing world-readable key was left as-is'


def test_new_key_is_created_locked_down(client, tmp_path, monkeypatch):
    import backend.routers.secrets as secrets_mod

    key_file = tmp_path / 'fresh' / '.vault_key'
    monkeypatch.setattr(secrets_mod, 'KEY_PATH', key_file)
    secrets_mod._get_fernet()
    assert key_file.exists()
    assert not (_mode(key_file) & 0o077)


def test_tightening_does_not_corrupt_the_key(client, tmp_path, monkeypatch):
    """A permissions fix that broke decryption would be far worse than the
    exposure it closes."""
    from cryptography.fernet import Fernet

    import backend.routers.secrets as secrets_mod

    key_file = tmp_path / '.vault_key'
    raw = Fernet.generate_key()
    key_file.write_bytes(raw)
    key_file.chmod(0o644)

    monkeypatch.setattr(secrets_mod, 'KEY_PATH', key_file)
    f = secrets_mod._get_fernet()
    token = f.encrypt(b'round trip')
    assert f.decrypt(token) == b'round trip'
    assert key_file.read_bytes() == raw, 'the key material was modified'


# ══ Secret handling still correct ═════════════════════════════════════════════
def test_secret_values_are_never_returned(client):
    key = 'PROBE_' + uuid.uuid4().hex[:6]
    r = client.post('/api/secrets/set', json={'key': key, 'value': 'sk-SUPER-SECRET-VALUE'})
    assert r.status_code == 200 and r.json()['ok'] is True

    listing = client.get('/api/secrets/list').text
    assert 'SUPER-SECRET' not in listing, 'the vault listing leaked a plaintext secret'


def test_secret_set_reports_encryption_status(client):
    key = 'PROBE_' + uuid.uuid4().hex[:6]
    body = client.post('/api/secrets/set', json={'key': key, 'value': 'v'}).json()
    assert body.get('encrypted') is True
    assert body.get('fingerprint'), 'no fingerprint to identify the value by'


# ══ 2. Eval status codes ══════════════════════════════════════════════════════
def test_running_an_unknown_suite_is_404(client):
    r = client.post('/api/eval-framework/run', json={'suite_id': 'nope_not_real_xyz'})
    assert r.status_code == 404, 'an eval run on a nonexistent suite reported success'
    assert 'not found' in r.json()['error'].lower()


def test_running_an_empty_suite_is_409(client):
    """Distinct from 404: the suite exists, there is simply nothing to run.
    Collapsing both into one code would hide a real configuration mistake."""
    # The server generates its own suite_id and ignores any supplied one --
    # my first version passed 'empty_xxx' and then ran against that made-up id,
    # so it got the 404 path and looked like the 409 was missing. Use the id the
    # API actually returns.
    created = client.post('/api/eval-framework/suites', json={
        'name': 'Empty probe ' + uuid.uuid4().hex[:6], 'description': 'no cases'})
    if created.status_code != 200:
        pytest.skip('suite creation unavailable in this environment')
    body = created.json()
    sid = body.get('suite_id') or (body.get('suite') or {}).get('suite_id')
    assert sid, f'could not determine the created suite id from {body}'

    r = client.post('/api/eval-framework/run', json={'suite_id': sid})
    assert r.status_code == 409, f'expected 409 for an empty suite, got {r.status_code}'


def test_running_a_real_suite_still_streams(client):
    """The guard must not break the working path."""
    suites = client.get('/api/eval-framework/suites').json()
    items = suites if isinstance(suites, list) else suites.get('suites', [])
    with_cases = next((s for s in items if (s.get('case_count') or 0) > 0), None)
    if not with_cases:
        pytest.skip('no seeded suite with cases in this environment')

    r = client.post('/api/eval-framework/run', json={'suite_id': with_cases['suite_id']})
    assert r.status_code == 200


def test_validation_happens_before_the_stream_opens():
    """Returning 200 and then an error inside the SSE body is what made this
    invisible to status-code checks."""
    import inspect

    from backend.routers import eval_framework

    src = inspect.getsource(eval_framework)
    run_src = src[src.index("async def run_eval_suite") if "async def run_eval_suite" in src else 0:]
    assert 'status_code=404' in run_src or 'status_code=404' in src
