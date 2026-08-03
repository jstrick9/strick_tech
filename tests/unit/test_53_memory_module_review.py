"""
Unit Tests — Memory workstation module review
(`tests/unit/test_53_memory_module_review.py`)

Covers the Memory workstation: core Memory plus the RAG, Knowledge Graph and
Obsidian Sync tabs folded into it by the consolidation.

Regression guards for real defects found during the review:

1. PERF: memory_stats() returned EVERY distinct ingest source with no limit
   (~160 rows / 10 KB here) and that payload is broadcast over the WebSocket to
   every connected client every 8 seconds — despite neither consumer reading
   the source list at all.
2. Memory GET/PUT/DELETE returned HTTP 200 for a nonexistent id, and DELETE
   reported {"deleted": <id>} for a row that never existed.
3. 31 endpoints across rag/knowledge_graph/obsidian returned 200 with
   {"ok": false} for not-found, validation and traversal failures.
4. GET /rag/pipelines/{id}/documents never checked the pipeline existed, so a
   typo'd id returned an empty list — indistinguishable from "no documents".
5. Obsidian note paths were only bounds-checked AFTER accepting the filename,
   so percent-encoded traversal ("..%2f..") was written out as a literal file.
   The vault had accumulated junk like "..%2f..%2fetc%2fpasswd.md" and a stray
   "etc/" directory.
"""

from __future__ import annotations

from pathlib import Path

import pytest

from backend.routers.obsidian import validate_note_path
from backend.services.memory_db import MEMORY_STATS_SOURCE_LIMIT, memory_stats

ROOT = Path(__file__).resolve().parents[2]
MEMORY_PY = (ROOT / 'backend' / 'routers' / 'memory.py').read_text(encoding='utf-8')
RAG_PY = (ROOT / 'backend' / 'routers' / 'rag.py').read_text(encoding='utf-8')
KG_PY = (ROOT / 'backend' / 'routers' / 'knowledge_graph.py').read_text(encoding='utf-8')
OBSIDIAN_PY = (ROOT / 'backend' / 'routers' / 'obsidian.py').read_text(encoding='utf-8')
WS_PY = (ROOT / 'backend' / 'routers' / 'websocket.py').read_text(encoding='utf-8')


class TestMemoryStatsPayloadIsBounded:
    """This response is pushed to every client every 8 seconds."""

    def test_source_list_is_capped_by_default(self):
        stats = memory_stats()
        assert len(stats['sources']) <= MEMORY_STATS_SOURCE_LIMIT

    def test_true_source_total_is_still_reported(self):
        stats = memory_stats()
        assert 'source_count' in stats
        assert stats['source_count'] >= len(stats['sources'])

    def test_truncation_is_signalled_not_hidden(self):
        stats = memory_stats()
        assert stats['sources_truncated'] is (stats['source_count'] > len(stats['sources']))

    def test_full_list_is_still_reachable(self):
        capped = memory_stats(source_limit=5)
        full = memory_stats(source_limit=0)
        assert len(capped['sources']) <= 5
        assert len(full['sources']) == full['source_count']

    def test_counters_are_unaffected_by_the_cap(self):
        assert memory_stats(source_limit=1)['total'] == memory_stats(source_limit=0)['total']

    def test_websocket_broadcast_omits_the_source_list(self):
        """No WS consumer reads `sources`; sending it wasted ~10 KB per tick."""
        assert 'PERF FIX' in WS_PY
        idx = WS_PY.index('async def _get_memory_stats')
        body = WS_PY[idx:idx + 1200]
        assert "'sources'" not in body, 'the full source list must not be broadcast'
        assert "'sqlite_memories'" in body


class TestMemoryCrudStatusCodes:
    """A missing row is a 404, not a 200 with ok:false."""

    def test_get_returns_404(self):
        assert MEMORY_PY.count('status_code=404') >= 3

    def test_delete_no_longer_claims_to_delete_a_missing_row(self):
        assert "return {'ok': cur.rowcount > 0, 'deleted': memory_id}" not in MEMORY_PY
        assert "return {'ok': True, 'deleted': memory_id}" in MEMORY_PY

    def test_delete_checks_rowcount_before_reporting_success(self):
        assert 'deleted_rows = cur.rowcount' in MEMORY_PY
        assert 'if deleted_rows == 0:' in MEMORY_PY


class TestTabRoutersUseRealStatusCodes:
    @pytest.mark.parametrize(
        'src,name',
        [(RAG_PY, 'rag'), (KG_PY, 'knowledge_graph'), (OBSIDIAN_PY, 'obsidian')],
    )
    def test_no_bare_ok_false_returns_remain(self, src, name):
        """Every error path must carry a status code."""
        assert "return {'ok': False, 'error'" not in src, f'{name} still returns 200 on an error path'

    def test_rag_maps_validation_and_not_found_separately(self):
        assert 'status_code=400' in RAG_PY
        assert 'status_code=404' in RAG_PY

    def test_knowledge_graph_maps_validation_and_not_found(self):
        assert 'status_code=400' in KG_PY
        assert 'status_code=404' in KG_PY

    def test_obsidian_uses_403_for_traversal(self):
        assert 'status_code=403' in OBSIDIAN_PY

    def test_rag_documents_verifies_the_pipeline_exists(self):
        """An unknown pipeline returned an empty list, not a 404."""
        assert "SELECT 1 FROM rag_pipelines WHERE id=?" in RAG_PY


class TestObsidianPathValidation:
    """Traversal must be rejected before a filename is ever accepted."""

    @pytest.mark.parametrize(
        'bad',
        [
            '../../../etc/passwd',
            '..%2f..%2fetc%2fpasswd',
            '%2e%2e%2fsecret',
            'notes/../../escape.md',
            'a/..%5cb',
            '....//....//etc/passwd',
        ],
    )
    def test_traversal_payloads_are_rejected(self, bad):
        safe, err = validate_note_path(bad)
        assert safe is None
        assert err and 'traversal' in err.lower()

    def test_absolute_paths_are_rejected_not_silently_rebased(self):
        safe, err = validate_note_path('/etc/passwd')
        assert safe is None
        assert err

    def test_empty_paths_are_rejected(self):
        for value in ('', '   ', None, '/', './'):
            safe, err = validate_note_path(value)
            assert safe is None and err

    def test_legitimate_paths_are_accepted_and_normalised(self):
        assert validate_note_path('my note') == ('my note.md', None)
        assert validate_note_path('folder/my note.md') == ('folder/my note.md', None)
        assert validate_note_path('a//b/c') == ('a/b/c.md', None)

    def test_backslashes_are_normalised_to_forward_slashes(self):
        safe, err = validate_note_path('folder\\note.md')
        assert err is None
        assert safe == 'folder/note.md'

    def test_null_bytes_are_rejected(self):
        safe, err = validate_note_path('note\x00.md')
        assert safe is None and err

    def test_containment_uses_path_semantics_not_string_prefix(self):
        """brain_backup/ must not count as inside brain/."""
        assert 'f.relative_to(' in OBSIDIAN_PY
        assert 'str(f).startswith(str(note_dir.resolve()))' not in OBSIDIAN_PY
