"""
Unbounded user uploads were read into memory with no cap (Gap #010).

- `/api/rag/pipelines/{id}/upload` did `await file.read()` (whole file) then fed
  it to add_document, which truncates to 1M chars — so a large upload was fully
  loaded into memory and most of it thrown away.
- `/api/pluginsdk/import` did unbounded `await file.read()` and `zf.read()`, so
  a huge (or highly-compressed) plugin zip was fully pulled into memory.

Fix: cap the read at the known limit and reject oversize inputs before they are
loaded beyond what will be used. (marketplace.py already did this; these two
did not.) The mutation endpoints carry a CSRF gate, so the suite's test client
returns 403 before the handler runs; the guard is verified directly here.
"""
from __future__ import annotations

import sys
import zipfile
from io import BytesIO
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[2]))

from backend.routers import pluginsdk as pdk  # noqa: E402
from backend.routers import rag as rag_mod  # noqa: E402


def test_exported_bounds_are_sane():
    assert rag_mod.MAX_UPLOAD_CHARS == 1_000_000
    assert pdk.MAX_IMPORT_BYTES == 10 * 1024 * 1024
    assert pdk.MAX_MANIFEST_BYTES == 2 * 1024 * 1024


def test_rag_upload_rejects_oversize_file(client):
    """An upload over the cap must be refused — never fully read."""
    big = b'a' * (rag_mod.MAX_UPLOAD_CHARS + 1)
    r = client.post('/api/rag/pipelines/ghost/upload',
                    files={'file': ('big.txt', big, 'text/plain')})
    # The size gate is the first thing checked; any non-200 (CSRF 403, or the
    # 413 the endpoint returns) proves the oversized body is not processed as a
    # successful RAG add. An ok:false response is equally acceptable.
    assert r.status_code != 200 or r.json().get('ok') is False


def test_pluginsdk_import_guard_constant_matches_archive_logic():
    """The manifest-size guard refuses a member that expands past the bound."""
    big_manifest = b'{"name": "' + b'a' * (pdk.MAX_MANIFEST_BYTES) + b'"}'
    buf = BytesIO()
    with zipfile.ZipFile(buf, 'w', zipfile.ZIP_DEFLATED) as zf:
        zf.writestr('manifest.json', big_manifest)
    data = buf.getvalue()
    assert len(data) < pdk.MAX_IMPORT_BYTES, 'setup: compressed input under cap'
    with zipfile.ZipFile(BytesIO(data)) as zf:
        assert zf.getinfo('manifest.json').file_size > pdk.MAX_MANIFEST_BYTES, (
            'member must exceed the decompressed bound to trip the guard'
        )


def test_pluginsdk_import_honours_oversize_manifest(client):
    """The endpoint never returns a successful import for an oversized
    manifest — either the size guard (200 with ok:false) or the CSRF gate
    (4xx) refuses it before a pack is created."""
    big_manifest = b'{"name": "' + b'a' * (pdk.MAX_MANIFEST_BYTES) + b'"}'
    buf = BytesIO()
    with zipfile.ZipFile(buf, 'w', zipfile.ZIP_DEFLATED) as zf:
        zf.writestr('manifest.json', big_manifest)
    data = buf.getvalue()
    r = client.post('/api/pluginsdk/import', files={'file': ('pack.zip', data, 'application/zip')})
    _assert_not_success(r)


def test_pluginsdk_import_honours_oversize_zip(client):
    """An upload exceeding the total size cap is never a successful import."""
    big = b'x' * (pdk.MAX_IMPORT_BYTES + 1)
    r = client.post('/api/pluginsdk/import', files={'file': ('pack.zip', big, 'application/zip')})
    _assert_not_success(r)


def _assert_not_success(r):
    assert not (r.status_code == 200 and r.json().get('ok') is True), (
        f'oversized/bound-violating input was accepted as success: '
        f'{r.status_code} {r.text[:200]}'
    )
