"""
`/api/documents/extract` — .docx decompression-bomb regression (Gap #009).

A .docx stores word/document.xml DEFLATED, so the 4MB upload cap says nothing
about the expanded text. `_extract_docx` read and `ET.fromstring`-parsed the
WHOLE expanded member — building an in-memory DOM — before MAX_EXTRACTED_CHARS
trimmed it. A zip-bomb (small compressed upload, huge document.xml) could drive
unbounded memory/CPU. Reproduced: a ~172KB zip decompressed a 39MB member, and
the 215KB zip decompressed 118MB, both fully loaded before any cap.

Fix: refuse the archive up front if the `word/document.xml` member exceeds a
decompressed-size bound (MAX_DOCX_XML_BYTES), before it is pulled into memory.
A normal Word document is far below the cap, so legitimate extraction is
unaffected.
"""
from __future__ import annotations

import sys
import zipfile
from io import BytesIO
from pathlib import Path
from zipfile import ZipFile

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[2]))

from backend.routers.documents import MAX_DOCX_XML_BYTES, _extract_docx  # noqa: E402

# Real, readable document.xml (matches how test_49 builds a valid docx).
_DOC_XML = (
    b'<w:document xmlns:w="http://schemas.openxmlformats.org/wordprocessingml/2006/main">'
    b'<w:body><w:p><w:r><w:t>Hello Word doc</w:t></w:r></w:p></w:body></w:document>'
)


def _make_docx(xml_bytes: bytes, compressed: bool = False) -> bytes:
    buf = BytesIO()
    comp = zipfile.ZIP_DEFLATED if compressed else zipfile.ZIP_STORED
    with ZipFile(buf, 'w', compression=comp) as archive:
        archive.writestr('word/document.xml', xml_bytes)
    return buf.getvalue()


def test_valid_docx_still_extracts():
    raw = _make_docx(_DOC_XML)
    text = _extract_docx(raw)
    assert 'Hello Word doc' in text


def test_oversized_decompressed_member_is_rejected_before_parse():
    big_xml = b'<x>' + b'a' * (MAX_DOCX_XML_BYTES + 1) + b'</x>'
    raw = _make_docx(big_xml)
    with pytest.raises(ValueError, match='too large'):
        _extract_docx(raw)


def test_decompression_bomb_with_large_ratio_is_rejected():
    """A tiny compressed upload that expands hugely (the actual zip-bomb shape)
    must not be fully parsed into a DOM — it is refused by the decompressed-size
    bound before being pulled into memory."""
    big_xml = b'<x>' + b'a' * (MAX_DOCX_XML_BYTES + 1) + b'</x>'
    raw = _make_docx(big_xml, compressed=True)
    with pytest.raises(ValueError, match='too large'):
        _extract_docx(raw)


def test_bound_catches_practical_bomb_ratio():
    """A member just over the bound is refused even though the compressed input
    is tiny (high compression ratio)."""
    big = b'<x>' + b'a' * (MAX_DOCX_XML_BYTES + 1) + b'</x>'
    raw = _make_docx(big, compressed=True)
    assert len(raw) < len(big), 'setup: compressed input is much smaller'
    with pytest.raises(ValueError, match='too large'):
        _extract_docx(raw)
