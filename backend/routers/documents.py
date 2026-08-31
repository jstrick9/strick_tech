"""Safe local document-to-text extraction for Chat attachments."""
from __future__ import annotations

import xml.etree.ElementTree as ET
from io import BytesIO
from pathlib import Path
from zipfile import BadZipFile, ZipFile

from fastapi import APIRouter, File, HTTPException, UploadFile

router = APIRouter(prefix='/api/documents', tags=['documents'])

MAX_UPLOAD_BYTES = 4 * 1024 * 1024
MAX_EXTRACTED_CHARS = 30_000
TEXT_EXTENSIONS = {
    '.txt', '.md', '.markdown', '.csv', '.tsv', '.json', '.js', '.jsx', '.ts',
    '.tsx', '.py', '.html', '.css', '.xml', '.yaml', '.yml', '.log', '.sql',
    '.sh', '.java', '.go', '.rs', '.rb', '.php', '.c', '.cpp', '.h',
}


def _trim(text: str) -> tuple[str, bool]:
    cleaned = text.replace('\x00', '').strip()
    return cleaned[:MAX_EXTRACTED_CHARS], len(cleaned) > MAX_EXTRACTED_CHARS


# A .docx is a ZIP; word/document.xml is stored DEFLATED, so the *compressed*
# upload size says nothing about the expanded text. An attacker can send a
# small .docx whose document.xml decompresses to hundreds of MB (a zip-bomb) —
# and ET.fromstring builds an in-memory DOM of the WHOLE expanded member before
# MAX_EXTRACTED_CHARS ever trims it. Bound the decompressed size up front and
# reject anything grossly larger than we'd ever return.
MAX_DOCX_XML_BYTES = 12 * 1024 * 1024


def _extract_docx(raw: bytes) -> str:
    try:
        with ZipFile(BytesIO(raw)) as archive:
            info = archive.getinfo('word/document.xml')
            # Refuse a decompression bomb before pulling it into memory.
            if info.file_size > MAX_DOCX_XML_BYTES:
                raise ValueError('Word document is too large to extract safely.')
            xml = archive.read('word/document.xml')
        root = ET.fromstring(xml)
        paragraphs = []
        for paragraph in root.iter('{http://schemas.openxmlformats.org/wordprocessingml/2006/main}p'):
            value = ''.join(paragraph.itertext()).strip()
            if value:
                paragraphs.append(value)
        return '\n\n'.join(paragraphs)
    except (BadZipFile, KeyError, ET.ParseError) as exc:
        raise ValueError('This file is not a readable Word document.') from exc


def _extract_pdf(raw: bytes) -> tuple[str, int]:
    try:
        from pypdf import PdfReader
        reader = PdfReader(BytesIO(raw))
        pages = [page.extract_text() or '' for page in reader.pages]
        return '\n\n'.join(pages), len(pages)
    except ImportError as exc:
        raise RuntimeError('PDF reading is not installed. Update the local app dependencies and try again.') from exc
    except Exception as exc:
        raise ValueError('This PDF could not be read. It may be protected, scanned, or corrupted.') from exc


@router.post('/extract')
async def extract_document(file: UploadFile = File(...)):
    """Extract local text from a supported attachment without persisting the file."""
    filename = Path(file.filename or 'document').name
    extension = Path(filename).suffix.lower()
    raw = await file.read(MAX_UPLOAD_BYTES + 1)
    if len(raw) > MAX_UPLOAD_BYTES:
        raise HTTPException(413, 'Files must be 4 MB or smaller for Chat extraction.')

    try:
        if extension == '.pdf':
            text, pages = _extract_pdf(raw)
            kind = 'PDF document'
        elif extension == '.docx':
            text, pages = _extract_docx(raw), None
            kind = 'Word document'
        elif extension in TEXT_EXTENSIONS or (file.content_type or '').startswith('text/'):
            text, pages = raw.decode('utf-8', errors='replace'), None
            kind = 'text document'
        elif extension in {'.png', '.jpg', '.jpeg', '.webp', '.gif', '.heic'}:
            raise HTTPException(415, 'Image understanding is not active for this Chat connection yet. Try a text document, PDF, or Word document.')
        else:
            raise HTTPException(415, 'Supported files are text, code, CSV, JSON, PDF, and Word documents.')
    except HTTPException:
        raise
    except (ValueError, RuntimeError) as exc:
        raise HTTPException(422, str(exc)) from exc

    extracted, truncated = _trim(text)
    if not extracted:
        raise HTTPException(422, 'No readable text was found in this document.')
    return {
        'ok': True, 'filename': filename, 'kind': kind, 'text': extracted,
        'pages': pages, 'truncated': truncated, 'characters': len(extracted),
    }
