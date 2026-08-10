"""Module 10 regression tests — finetune, pluginsdk, pqc.

Defects found by probing the running module:

1. POST /finetune/datasets/create wrote three hardcoded marketing sentences
   about Agentic OS whenever no rows were supplied, and reported "created with
   3 training examples". The response and the dataset list were
   indistinguishable from a dataset built out of the user's own data.
2. source_type defaults to "chat_history" and the endpoint never read chat
   history at all.
3. POST /pluginsdk/publish/{id} never ran the validator that lives in the same
   file. A pack the validator scores 40 ("Missing required field: skills",
   "version must be semantic") published to the marketplace registry AND
   registered itself in plugins/installed.json.
4. POST /pqc/kem/decapsulate returned a plain success with no `simulated`
   flag, while /keypair/generate and /kem/encapsulate both declare the
   simulation. It is the call that actually hands back the shared secret.
"""

from __future__ import annotations

import json

import pytest
from fastapi import HTTPException

from backend.routers import finetune, pluginsdk


# ── 1/2. datasets must not be invented ────────────────────────────────────────
def test_dataset_creation_refuses_rather_than_inventing_rows(tmp_path, monkeypatch):
    """No rows and no history must be an error, not three canned sentences."""
    monkeypatch.setattr(finetune, 'DATASETS_DIR', tmp_path)
    monkeypatch.setattr(finetune, '_rows_from_chat_history', lambda *a, **k: [])
    req = finetune.DatasetCreateRequest(name='empty')
    with pytest.raises(HTTPException) as ex:
        finetune.create_finetune_dataset(req)
    assert ex.value.status_code == 422
    assert 'placeholder' in str(ex.value.detail).lower()


def test_no_marketing_copy_is_written_as_training_data(tmp_path, monkeypatch):
    """The exact invented rows must not appear on disk."""
    monkeypatch.setattr(finetune, 'DATASETS_DIR', tmp_path)
    monkeypatch.setattr(finetune, '_rows_from_chat_history', lambda *a, **k: [])
    with pytest.raises(HTTPException):
        finetune.create_finetune_dataset(finetune.DatasetCreateRequest(name='x'))
    written = list(tmp_path.glob('*.jsonl'))
    assert not written, 'a dataset file was created despite having no data'


def test_source_module_no_longer_contains_the_invented_rows():
    import inspect

    src = inspect.getsource(finetune.create_finetune_dataset)
    assert 'mission of Agentic OS' not in src
    assert 'compounding Information Hierarchy' not in src


def test_custom_rows_are_used_verbatim(tmp_path, monkeypatch):
    monkeypatch.setattr(finetune, 'DATASETS_DIR', tmp_path)
    rows = [{'instruction': 'a', 'input': '', 'output': 'b'}]
    out = finetune.create_finetune_dataset(
        finetune.DatasetCreateRequest(name='real', custom_rows=rows)
    )
    assert out['dataset']['row_count'] == 1
    assert out['dataset']['source_type'] == 'custom_rows'
    written = (tmp_path / f"{out['dataset']['dataset_id']}.jsonl").read_text().strip()
    assert json.loads(written) == rows[0]


def test_chat_history_source_is_actually_read(tmp_path, monkeypatch):
    """source_type='chat_history' must consult chat history, not placeholders."""
    monkeypatch.setattr(finetune, 'DATASETS_DIR', tmp_path)
    monkeypatch.setattr(
        finetune, '_rows_from_chat_history',
        lambda *a, **k: [{'instruction': 'q', 'input': '', 'output': 'a'}],
    )
    out = finetune.create_finetune_dataset(finetune.DatasetCreateRequest(name='h'))
    assert out['dataset']['row_count'] == 1
    assert out['dataset']['source_type'] == 'chat_history'


def test_chat_history_pairs_user_with_following_assistant():
    class _Row(dict):
        def __getitem__(self, k):
            return dict.__getitem__(self, k)

    rows = [
        _Row(role='user', message='How do I add a key?'),
        _Row(role='assistant', message='Open Settings.'),
        _Row(role='user', message='Thanks'),
        _Row(role='assistant', message='Any time.'),
    ]

    class _Con:
        def execute(self, *a, **k):
            return self

        def fetchall(self):
            return rows

        def close(self):
            pass

    import backend.services.memory_db as mdb

    orig = mdb.get_conn
    mdb.get_conn = lambda *a, **k: _Con()
    try:
        out = finetune._rows_from_chat_history()
    finally:
        mdb.get_conn = orig
    assert len(out) == 2
    assert out[0]['instruction'] == 'How do I add a key?'
    assert out[0]['output'] == 'Open Settings.'


def test_chat_history_ignores_unpaired_messages():
    class _Row(dict):
        pass

    rows = [_Row(role='user', message='hello'), _Row(role='user', message='anyone?')]

    class _Con:
        def execute(self, *a, **k):
            return self

        def fetchall(self):
            return rows

        def close(self):
            pass

    import backend.services.memory_db as mdb

    orig = mdb.get_conn
    mdb.get_conn = lambda *a, **k: _Con()
    try:
        assert finetune._rows_from_chat_history() == []
    finally:
        mdb.get_conn = orig


# ── 3. publish must enforce validation ────────────────────────────────────────
def _write_pack(dirpath, pack):
    dirpath.mkdir(parents=True, exist_ok=True)
    (dirpath / f"{pack['id']}.json").write_text(json.dumps(pack))


def test_publish_refuses_an_invalid_pack(tmp_path, monkeypatch):
    monkeypatch.setattr(pluginsdk, 'PACKS_DIR', tmp_path / 'packs')
    monkeypatch.setattr(pluginsdk, 'PUBLISHED', tmp_path / 'published')
    (tmp_path / 'published').mkdir(parents=True, exist_ok=True)
    bad = {'id': 'broken', 'name': 'Broken', 'version': 'not-a-version',
           'description': '', 'skills': []}
    _write_pack(tmp_path / 'packs', bad)

    out = pluginsdk.publish_pack('broken')
    assert out['ok'] is False
    assert out['code'] == 'validation_failed'
    assert any('semantic' in e for e in out['errors'])
    # And nothing reached the registry.
    assert not (tmp_path / 'published' / 'broken.json').exists()


def test_publish_accepts_a_valid_pack(tmp_path, monkeypatch):
    monkeypatch.setattr(pluginsdk, 'PACKS_DIR', tmp_path / 'packs')
    monkeypatch.setattr(pluginsdk, 'PUBLISHED', tmp_path / 'published')
    (tmp_path / 'published').mkdir(parents=True, exist_ok=True)
    monkeypatch.setattr(pluginsdk, 'ROOT', tmp_path)
    good = {
        'id': 'goodpack', 'name': 'Good', 'version': '1.0.0',
        'description': 'It works', 'permissions': ['chat'],
        'skills': [{'id': 's1', 'name': 'S1', 'prompt': 'do {{input}}'}],
    }
    _write_pack(tmp_path / 'packs', good)
    out = pluginsdk.publish_pack('goodpack')
    assert out['ok'] is True
    assert (tmp_path / 'published' / 'goodpack.json').exists()


def test_publish_and_validate_share_one_implementation():
    """The rules must not be able to drift apart again."""
    import inspect

    assert callable(pluginsdk._validate_manifest)
    src = inspect.getsource(pluginsdk.publish_pack)
    src = '\n'.join(ln for ln in src.split('\n') if not ln.strip().startswith('#'))
    assert '_validate_manifest' in src


def test_validator_still_rejects_unknown_permissions():
    out = pluginsdk._validate_manifest({
        'id': 'p', 'name': 'P', 'version': '1.0.0', 'description': 'd',
        'skills': [{'id': 's', 'name': 'S', 'prompt': 'x'}],
        'permissions': ['chat', 'root'],
    })
    assert out['ok'] is False
    assert any('root' in e for e in out['errors'])


def test_validator_accepts_a_well_formed_manifest():
    out = pluginsdk._validate_manifest({
        'id': 'p', 'name': 'P', 'version': '2.1.3', 'description': 'd',
        'skills': [{'id': 's', 'name': 'S', 'prompt': 'x'}],
        'permissions': ['chat', 'memory'],
    })
    assert out['ok'] is True and out['score'] == 100


# ── 4. every PQC door must admit it is simulated ──────────────────────────────
def test_decapsulate_declares_the_simulation(tmp_path, monkeypatch):
    import base64

    monkeypatch.setattr(pqc_mod := __import__(
        'backend.routers.pqc', fromlist=['x']), 'KEYS_DIR', tmp_path)
    meta = {
        'keypair_id': 'pqc_kp_test', 'algorithm': 'ML-KEM-1024',
        'public_key_b64': base64.b64encode(b'pk' * 32).decode(),
        'private_key_b64': base64.b64encode(b'sk' * 32).decode(),
    }
    (tmp_path / 'pqc_kp_test.json').write_text(json.dumps(meta))
    req = pqc_mod.KemDecapsulateRequest(
        keypair_id='pqc_kp_test',
        ciphertext_b64=base64.b64encode(b'ct' * 32).decode(),
    )
    out = pqc_mod.kem_decapsulate(req)
    assert out['simulated'] is True
    assert out['warning']
    assert 'SIMULATED' in out['message']


@pytest.mark.parametrize('route', ['generate_pqc_keypair', 'kem_encapsulate', 'kem_decapsulate'])
def test_every_pqc_route_reports_simulated(route):
    """All three doors, not just the two that were already fixed."""
    import inspect

    pqc_mod = __import__('backend.routers.pqc', fromlist=['x'])
    src = inspect.getsource(getattr(pqc_mod, route))
    src = '\n'.join(ln for ln in src.split('\n') if not ln.strip().startswith('#'))
    assert '"simulated": True' in src or "'simulated': True" in src, route


def test_pqc_vault_encrypt_still_refuses_without_optin():
    import inspect

    pqc_mod = __import__('backend.routers.pqc', fromlist=['x'])
    src = inspect.getsource(pqc_mod.encrypt_pqc_vault_item)
    assert '_demo_mode_enabled' in src
    assert '501' in src
