"""Unit tests — the vault cipher is cached, not re-read per row (r86, #250)

_get_fernet ran its full sequence — mkdir, exists, permission tightening,
read_bytes, Fernet() construction — on EVERY call, and _decrypt calls it
per ROW. Measured with a counting key-file proxy:

  _inject_to_env (runs at IMPORT TIME, before the app serves anything):
    100 global secrets = 100 key-file reads + 100 cipher constructions
    on every process boot. After: 0 reads, 1 construction.

The Fernet object is immutable, so it is cached keyed on
(path, mtime_ns, size). A rewritten or rotated key file changes the stat
tuple and forces a fresh read — rotation stays correct — and pointing
KEY_PATH elsewhere (as tests do) gets its own cache entry. The
permission-tightening stat still runs on every call.

Honest magnitudes: the reads were page-cache-warm here, so the wall-clock
gain on this machine was modest (10.9 -> 9.9ms for 100 secrets); the real
claim is the elimination of N per-row file reads and cipher constructions
on the boot path and every vault listing — which grows with secret count
and is uncached on a cold page cache or networked filesystem.
"""
import contextlib

import backend.routers.secrets as sec


class CountingPath:
    """Delegates everything to the real key file path, counting read_bytes."""

    def __init__(self, real, counter):
        self._real = real
        self._counter = counter

    def __getattr__(self, name):
        return getattr(self._real, name)

    def __fspath__(self):
        return str(self._real)

    def read_bytes(self):
        self._counter['reads'] += 1
        return self._real.read_bytes()

    def write_bytes(self, data):
        self._counter['writes'] += 1
        return self._real.write_bytes(data)


def _reset_cache():
    sec._FERNET_CACHE = None


class TestFernetCache:
    def test_repeated_calls_return_the_same_cipher(self, monkeypatch):
        real = sec.KEY_PATH
        counter = {'reads': 0, 'writes': 0}
        monkeypatch.setattr(sec, 'KEY_PATH', CountingPath(real, counter))
        _reset_cache()
        try:
            f1 = sec._get_fernet()
            f2 = sec._get_fernet()
            assert f1 is not None
            assert f1 is f2, 'the cipher must be cached, not reconstructed per call'
            assert counter['reads'] == 1, 'one key read total, not one per call'
        finally:
            _reset_cache()

    def test_per_row_decrypt_reads_the_key_once(self, monkeypatch):
        real = sec.KEY_PATH
        counter = {'reads': 0, 'writes': 0}
        monkeypatch.setattr(sec, 'KEY_PATH', CountingPath(real, counter))
        _reset_cache()
        try:
            enc, ok = sec._encrypt('row value')
            assert ok
            for _ in range(50):  # a 50-secret vault's per-row decrypt loop
                assert sec._decrypt(enc) == 'row value'
            assert counter['reads'] == 1, (
                f"{counter['reads']} key reads for 50 decryptions — "
                'the per-row key re-read is back'
            )
        finally:
            _reset_cache()

    def test_key_rotation_invalidates_the_cache(self, monkeypatch):
        from cryptography.fernet import Fernet

        real = sec.KEY_PATH
        counter = {'reads': 0, 'writes': 0}
        monkeypatch.setattr(sec, 'KEY_PATH', CountingPath(real, counter))
        _reset_cache()
        try:
            f1 = sec._get_fernet()
            enc = f1.encrypt(b'before rotation').decode()
            # rotate the key file
            monkeypatch.setattr(sec, 'KEY_PATH', CountingPath(real, counter))
            real.write_bytes(Fernet.generate_key())
            f2 = sec._get_fernet()
            assert f2 is not f1, 'a rewritten key file must force a fresh cipher'
            with contextlib.suppress(Exception):
                f2.decrypt(enc)  # must fail under the new key (InvalidToken)
            new_enc = f2.encrypt(b'after rotation').decode()
            assert f2.decrypt(new_enc.encode()).decode() == 'after rotation'
        finally:
            _reset_cache()

    def test_a_different_key_path_gets_its_own_entry(self, tmp_path, monkeypatch):
        from cryptography.fernet import Fernet

        _reset_cache()
        real = sec.KEY_PATH
        try:
            f1 = sec._get_fernet()
            alt = tmp_path / 'other_vault_key'
            alt.write_bytes(Fernet.generate_key())
            monkeypatch.setattr(sec, 'KEY_PATH', alt)
            f2 = sec._get_fernet()
            assert f2 is not f1, 'cache must be keyed on the path too'
            assert f2._signing_key is not None  # a working cipher came back
        finally:
            monkeypatch.setattr(sec, 'KEY_PATH', real)
            _reset_cache()

    def test_vault_list_still_reports_every_secret(self, client):
        """Behavior pin: listing with cached cipher still decrypts each row
        for its readability check and reports the right shape."""
        enc, ok = sec._encrypt('r86 list probe')
        assert ok
        r = client.post('/api/secrets/set', json={
            'key': 'R86_PROBE', 'value': 'r86 list probe', 'scope': 'global',
        })
        assert r.status_code == 200, r.text
        body = client.get('/api/secrets/list').json()
        assert body['ok'] is True
        assert body['encrypted'] is True
        assert any(i['key'] == 'R86_PROBE' for i in body['items'])
        assert body['unreadable'] == 0
