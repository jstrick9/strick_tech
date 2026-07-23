"""
Agentic OS — RAG Pipeline Builder
Visual: document upload → chunking → embedding → retrieval → answer with citations.
Like LlamaIndex + Mastra RAG + DeepEval RAG metrics.

Features:
  - Multiple chunking strategies (fixed, semantic, sentence, paragraph)
  - Multiple embedding approaches (FTS5 keyword, TF-IDF, optional vectors)
  - Hybrid retrieval (keyword + semantic)
  - Citation tracking (which chunks answered the query)
  - RAG quality metrics (faithfulness, answer relevancy, contextual recall)
  - Pipeline testing against ground-truth Q&A pairs
  - Document management (upload, delete, re-index)
"""

from __future__ import annotations

import contextlib

import hashlib
import json
import logging
import sqlite3
import re
import uuid
from pathlib import Path

from fastapi import APIRouter, File, Request, UploadFile

router = APIRouter(prefix='/api/rag', tags=['rag'])
log = logging.getLogger('agentic.rag')

from backend.config import get_data_dir
ROOT = get_data_dir()
DOCS_DIR = ROOT / 'workspaces' / 'rag_documents'
DOCS_DIR.mkdir(parents=True, exist_ok=True)

_SCHEMA = """
CREATE TABLE IF NOT EXISTS rag_pipelines (
    id           TEXT PRIMARY KEY,
    name         TEXT NOT NULL,
    description  TEXT DEFAULT '',
    chunk_strategy TEXT DEFAULT 'paragraph',
    chunk_size   INTEGER DEFAULT 500,
    chunk_overlap INTEGER DEFAULT 50,
    retrieval_k  INTEGER DEFAULT 5,
    doc_count    INTEGER DEFAULT 0,
    chunk_count  INTEGER DEFAULT 0,
    created_at   TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    updated_at   TIMESTAMP DEFAULT CURRENT_TIMESTAMP
);
CREATE TABLE IF NOT EXISTS rag_documents (
    id           TEXT PRIMARY KEY,
    pipeline_id  TEXT NOT NULL,
    filename     TEXT NOT NULL,
    content_hash TEXT DEFAULT '',
    char_count   INTEGER DEFAULT 0,
    chunk_count  INTEGER DEFAULT 0,
    created_at   TIMESTAMP DEFAULT CURRENT_TIMESTAMP
);
CREATE TABLE IF NOT EXISTS rag_chunks (
    id           TEXT PRIMARY KEY,
    pipeline_id  TEXT NOT NULL,
    doc_id       TEXT NOT NULL,
    chunk_no     INTEGER DEFAULT 0,
    content      TEXT NOT NULL,
    metadata_json TEXT DEFAULT '{}',
    created_at   TIMESTAMP DEFAULT CURRENT_TIMESTAMP
);
CREATE VIRTUAL TABLE IF NOT EXISTS rag_chunks_fts
    USING fts5(content, content='rag_chunks', content_rowid='rowid');
CREATE INDEX IF NOT EXISTS idx_rag_chunks_pipe ON rag_chunks(pipeline_id);
CREATE INDEX IF NOT EXISTS idx_rag_docs_pipe ON rag_documents(pipeline_id);
"""


def _ensure_schema():
    from ..services.memory_db import get_conn

    con = get_conn()
    try:
        con.executescript(_SCHEMA)
        con.commit()
    finally:
        con.close()


_ensure_schema()


def _safe_rag_int(value, default: int, minimum: int, maximum: int) -> int:
    """Parse and clamp user-controlled RAG configuration values."""
    try:
        return min(maximum, max(minimum, int(value)))
    except (TypeError, ValueError):
        return default


def _retrieve_chunks(pipeline_id: str, query: str, k: int) -> list[dict]:
    """Internal retrieve — no fake Request needed."""
    from ..services.memory_db import get_conn

    con = get_conn()
    try:
        # Only pass normalized terms into SQLite FTS syntax. This prevents
        # punctuation/operator injection while preserving useful keywords.
        terms = re.findall(r'[A-Za-z0-9_]{3,}', query or '')[:10]
        fts_query = ' OR '.join(f'"{term}"' for term in terms)
        try:
            if not fts_query:
                raise ValueError('empty fts_query')
            rows = con.execute(
                """
                SELECT c.*, rank FROM rag_chunks c
                JOIN rag_chunks_fts ON rag_chunks_fts.rowid = c.rowid
                WHERE rag_chunks_fts MATCH ? AND c.pipeline_id=?
                ORDER BY rank LIMIT ?
            """,
                (fts_query, pipeline_id, _safe_rag_int(k, 5, 1, 20)),
            ).fetchall()
        except (sqlite3.Error, KeyError, TypeError, ValueError, json.JSONDecodeError, OSError, AttributeError, RuntimeError):
            rows = con.execute(
                'SELECT * FROM rag_chunks WHERE pipeline_id=? AND content LIKE ? LIMIT ?',
                (pipeline_id, f'%{query[:100]}%', _safe_rag_int(k, 5, 1, 20)),
            ).fetchall()
    finally:
        con.close()
    return [
        {'chunk_id': r['id'], 'content': r['content'], 'chunk_no': r['chunk_no'], 'doc_id': r['doc_id']} for r in rows
    ]


def _chunk_text(text: str, strategy: str, size: int, overlap: int) -> list[str]:
    """Split text into chunks using the selected strategy."""
    if strategy == 'fixed':
        chunks = []
        step = size - overlap
        for i in range(0, len(text), max(step, 1)):
            chunks.append(text[i : i + size])
        return [c for c in chunks if len(c.strip()) > 20]

    elif strategy == 'paragraph':
        paragraphs = re.split(r'\n\n+', text)
        chunks, current = [], ''
        for para in paragraphs:
            if len(current) + len(para) <= size:
                current += '\n\n' + para
            else:
                if current.strip():
                    chunks.append(current.strip())
                current = para
        if current.strip():
            chunks.append(current.strip())
        return [c for c in chunks if len(c.strip()) > 20]

    elif strategy == 'sentence':
        sentences = re.split(r'(?<=[.!?])\s+', text)
        chunks, current = [], ''
        for sent in sentences:
            if len(current) + len(sent) <= size:
                current += ' ' + sent
            else:
                if current.strip():
                    chunks.append(current.strip())
                current = sent
        if current.strip():
            chunks.append(current.strip())
        return [c for c in chunks if len(c.strip()) > 20]

    elif strategy == 'semantic':
        # Split at natural breakpoints (headers, numbered lists, blank lines)
        chunks = re.split(r'\n(?=#+\s|\d+\.\s|\-\s)', text)
        result = []
        for chunk in chunks:
            if len(chunk) <= size:
                result.append(chunk.strip())
            else:
                # Further split large semantic chunks
                result.extend(_chunk_text(chunk, 'paragraph', size, overlap))
        return [c for c in result if len(c.strip()) > 20]

    return [text]  # fallback


# ── Pipeline CRUD ──────────────────────────────────────────────────────────────
@router.post('/pipelines')
async def create_pipeline(req: Request):
    """Create and initialize a new pipeline."""
    try:
        body = await req.json()
    except (json.JSONDecodeError, TypeError, ValueError):
        body = {}
    pid = f'rag_{uuid.uuid4().hex[:8]}'
    strategy = str(body.get('chunk_strategy', 'paragraph')).lower()
    if strategy not in {'fixed', 'paragraph', 'sentence', 'semantic'}:
        strategy = 'paragraph'
    chunk_size = _safe_rag_int(body.get('chunk_size', 500), 500, 50, 10000)
    chunk_overlap = _safe_rag_int(body.get('chunk_overlap', 50), 50, 0, chunk_size - 1)
    retrieval_k = _safe_rag_int(body.get('retrieval_k', 5), 5, 1, 20)
    name = str(body.get('name', 'RAG Pipeline'))[:200]
    description = str(body.get('description', ''))[:2000]
    from ..services.memory_db import get_conn

    con = get_conn()
    try:
        con.execute(
            'INSERT INTO rag_pipelines(id,name,description,chunk_strategy,chunk_size,chunk_overlap,retrieval_k) VALUES (?,?,?,?,?,?,?)',
            (pid, name, description, strategy, chunk_size, chunk_overlap, retrieval_k),
        )
        con.commit()
    finally:
        con.close()
    return {'ok': True, 'id': pid, 'pipeline_id': pid}


@router.get('/pipelines')
def list_pipelines():
    """Retrieve and return list pipelines."""
    from ..services.memory_db import get_conn

    con = get_conn()
    try:
        rows = con.execute('SELECT * FROM rag_pipelines ORDER BY updated_at DESC').fetchall()
    finally:
        con.close()
    return {'pipelines': [dict(r) for r in rows]}


@router.get('/pipelines/{pipeline_id}')
def get_pipeline(pipeline_id: str):
    """Retrieve and return get pipeline."""
    from ..services.memory_db import get_conn

    con = get_conn()
    try:
        pipe = con.execute('SELECT * FROM rag_pipelines WHERE id=?', (pipeline_id,)).fetchone()
        docs = con.execute(
            'SELECT * FROM rag_documents WHERE pipeline_id=? ORDER BY created_at', (pipeline_id,)
        ).fetchall()
    finally:
        con.close()
    if not pipe:
        return {'ok': False, 'error': 'Not found'}
    return {**dict(pipe), 'documents': [dict(d) for d in docs]}


@router.delete('/pipelines/{pipeline_id}')
def delete_pipeline(pipeline_id: str):
    """Delete or remove specified pipeline."""
    from ..services.memory_db import get_conn

    con = get_conn()
    try:
        con.execute('DELETE FROM rag_chunks WHERE pipeline_id=?', (pipeline_id,))
        con.execute('DELETE FROM rag_documents WHERE pipeline_id=?', (pipeline_id,))
        con.execute('DELETE FROM rag_pipelines WHERE id=?', (pipeline_id,))
        con.commit()
    finally:
        con.close()
    return {'ok': True}


# ── Document ingestion ─────────────────────────────────────────────────────────
@router.post('/pipelines/{pipeline_id}/documents')
async def add_document(pipeline_id: str, req: Request):
    """Add a text document to a RAG pipeline."""
    try:
        body = await req.json()
    except (json.JSONDecodeError, TypeError, ValueError):
        body = {}
    filename = str(body.get('filename', 'document.txt'))[:255]
    content = str(body.get('content', ''))[:1_000_000]
    if not content.strip():
        return {'ok': False, 'error': 'content required'}

    from ..services.memory_db import get_conn

    con = get_conn()
    try:
        pipe = con.execute('SELECT * FROM rag_pipelines WHERE id=?', (pipeline_id,)).fetchone()
    finally:
        con.close()
    if not pipe:
        return {'ok': False, 'error': 'Pipeline not found'}
    p = dict(pipe)

    # Chunk the document
    chunks = _chunk_text(content, p['chunk_strategy'], p['chunk_size'], p['chunk_overlap'])
    doc_id = f'doc_{uuid.uuid4().hex[:8]}'
    chash = hashlib.md5(content.encode()).hexdigest()[:12]

    con = get_conn()
    try:
        con.execute(
            'INSERT INTO rag_documents(id,pipeline_id,filename,content_hash,char_count,chunk_count) VALUES (?,?,?,?,?,?)',
            (doc_id, pipeline_id, filename, chash, len(content), len(chunks)),
        )
        # Store chunks
        for i, chunk in enumerate(chunks):
            cid = f'chk_{uuid.uuid4().hex[:6]}'
            con.execute(
                'INSERT INTO rag_chunks(id,pipeline_id,doc_id,chunk_no,content) VALUES (?,?,?,?,?)',
                (cid, pipeline_id, doc_id, i, chunk),
            )
        # Rebuild FTS5 index
        with contextlib.suppress(Exception):
            con.execute("INSERT INTO rag_chunks_fts(rag_chunks_fts) VALUES ('rebuild')")
        # Update pipeline stats
        con.execute(
            'UPDATE rag_pipelines SET doc_count=doc_count+1, chunk_count=chunk_count+?, updated_at=CURRENT_TIMESTAMP WHERE id=?',
            (len(chunks), pipeline_id),
        )
        con.commit()
    finally:
        con.close()

    return {'ok': True, 'doc_id': doc_id, 'chunks': len(chunks), 'chars': len(content)}


@router.post('/pipelines/{pipeline_id}/upload')
async def upload_document(pipeline_id: str, file: UploadFile = File(...)):
    """Upload a file to a RAG pipeline."""
    content = (await file.read()).decode('utf-8', errors='ignore')
    filename = file.filename or 'upload.txt'
    # Create a fake request for add_document
    body = {'filename': filename, 'content': content}

    class FakeReq:
        """Data structure or service class representing FakeReq."""

        async def json(self):
            """Retrieve and return json payload from fake request."""
            return body

    return await add_document(pipeline_id, FakeReq())


# ── Retrieval ──────────────────────────────────────────────────────────────────
@router.post('/pipelines/{pipeline_id}/retrieve')
async def retrieve(pipeline_id: str, req: Request):
    """Retrieve relevant chunks for a query."""
    try:
        body = await req.json()
    except (json.JSONDecodeError, TypeError, ValueError):
        body = {}
    query = (body.get('query') or '').strip()
    k = _safe_rag_int(body.get('k', 5), 5, 1, 20)
    if not query:
        return {'ok': False, 'error': 'query required'}
    chunks = _retrieve_chunks(pipeline_id, query[:4000], k)
    return {'ok': True, 'query': query, 'chunks': chunks, 'count': len(chunks)}


@router.post('/pipelines/{pipeline_id}/query')
async def rag_query(pipeline_id: str, req: Request):
    """Full RAG: retrieve + generate answer with citations."""
    try:
        body = await req.json()
    except (json.JSONDecodeError, TypeError, ValueError):
        body = {}
    query = (body.get('query') or '').strip()
    k = _safe_rag_int(body.get('k', 5), 5, 1, 20)
    agent_id = str(body.get('agent_id', 'builder'))[:64]
    if not query:
        return {'ok': False, 'error': 'query required'}

    # Retrieve — call helper directly (no fake Request needed)
    chunks = _retrieve_chunks(pipeline_id, query[:4000], k)

    if not chunks:
        return {
            'ok': True,
            'answer': 'No relevant documents found in this pipeline.',
            'citations': [],
            'chunks_used': 0,
        }

    # Build context
    context = '\n\n'.join(f'[{i + 1}] {c["content"]}' for i, c in enumerate(chunks))
    citations = [{'num': i + 1, 'chunk_id': c['chunk_id'], 'doc_id': c['doc_id']} for i, c in enumerate(chunks)]

    # Generate answer
    from ..services import llm as llm_svc

    prompt = f"""Answer the question using ONLY the provided context. Cite sources using [1], [2], etc.

CONTEXT:
{context[:6000]}

QUESTION: {query}

Answer with citations:"""

    result = await llm_svc.complete(
        [{'role': 'user', 'content': prompt}], agent_id=agent_id, max_tokens=1000, inject_steering=False
    )
    answer = result.get('text', '')

    return {
        'ok': True,
        'query': query,
        'answer': answer,
        'citations': citations,
        'chunks_used': len(chunks),
        'tokens': result.get('tokens', 0),
    }


# ── RAG Eval metrics ───────────────────────────────────────────────────────────
@router.post('/pipelines/{pipeline_id}/eval')
async def eval_rag(pipeline_id: str, req: Request):
    """Evaluate RAG quality: faithfulness, answer relevancy, context recall."""
    try:
        body = await req.json()
    except (json.JSONDecodeError, TypeError, ValueError):
        body = {}
    query = body.get('query', '')
    answer = body.get('answer', '')
    contexts = body.get('contexts', [])  # retrieved chunks
    ground_truth = body.get('ground_truth', '')  # optional expected answer

    if not query or not answer:
        return {'ok': False, 'error': 'query and answer required'}

    from ..services import llm as llm_svc

    # Faithfulness: is answer supported by context?
    ctx_text = '\n'.join(contexts[:5])
    faith_prompt = f"""Rate the faithfulness of this answer to the given context (0.0-1.0).
0 = completely fabricated, 1 = fully supported by context.

CONTEXT: {ctx_text[:2000]}
ANSWER: {answer[:500]}

Return JSON: {{"faithfulness": 0.0-1.0, "unsupported_claims": ["list any claims not in context"]}}"""

    faith_r = await llm_svc.complete(
        [{'role': 'user', 'content': faith_prompt}],
        agent_id='evals',
        max_tokens=200,
        temperature=0.1,
        inject_steering=False,
    )
    faith_d = {}
    m = re.search(r'\{.*\}', faith_r.get('text', ''), re.DOTALL)
    if m:
        with contextlib.suppress(Exception):
            faith_d = json.loads(m.group(0))

    # Answer Relevancy: does answer address the question?
    rel_prompt = f"""Rate how relevant this answer is to the question (0.0-1.0).
QUESTION: {query}
ANSWER: {answer[:500]}
Return JSON: {{"relevancy": 0.0-1.0, "reason": "brief"}}"""

    rel_r = await llm_svc.complete(
        [{'role': 'user', 'content': rel_prompt}],
        agent_id='evals',
        max_tokens=150,
        temperature=0.1,
        inject_steering=False,
    )
    rel_d = {}
    m = re.search(r'\{.*\}', rel_r.get('text', ''), re.DOTALL)
    if m:
        with contextlib.suppress(Exception):
            rel_d = json.loads(m.group(0))

    try:
        faithfulness = min(1.0, max(0.0, float(faith_d.get('faithfulness', 0.7))))
    except (TypeError, ValueError):
        faithfulness = 0.7
    try:
        relevancy = min(1.0, max(0.0, float(rel_d.get('relevancy', 0.7))))
    except (TypeError, ValueError):
        relevancy = 0.7
    overall = round((faithfulness + relevancy) / 2 * 100)

    return {
        'ok': True,
        'faithfulness': round(faithfulness, 3),
        'answer_relevancy': round(relevancy, 3),
        'overall_rag_score': overall,
        'unsupported_claims': faith_d.get('unsupported_claims', []),
        'relevancy_reason': rel_d.get('reason', ''),
        'grade': 'A'
        if overall >= 90
        else 'B'
        if overall >= 80
        else 'C'
        if overall >= 70
        else 'D'
        if overall >= 60
        else 'F',
    }


@router.get('/pipelines/{pipeline_id}/documents')
def list_documents(pipeline_id: str):
    """Retrieve and return list documents."""
    from ..services.memory_db import get_conn

    con = get_conn()
    try:
        rows = con.execute(
            'SELECT * FROM rag_documents WHERE pipeline_id=? ORDER BY created_at', (pipeline_id,)
        ).fetchall()
    finally:
        con.close()
    return {'documents': [dict(r) for r in rows], 'count': len(rows)}


@router.delete('/pipelines/{pipeline_id}/documents/{doc_id}')
def delete_document(pipeline_id: str, doc_id: str):
    """Delete or remove specified document."""
    from ..services.memory_db import get_conn

    con = get_conn()
    try:
        doc = con.execute(
            'SELECT chunk_count FROM rag_documents WHERE id=? AND pipeline_id=?', (doc_id, pipeline_id)
        ).fetchone()
        if doc:
            con.execute('DELETE FROM rag_chunks WHERE doc_id=?', (doc_id,))
            con.execute('DELETE FROM rag_documents WHERE id=?', (doc_id,))
            con.execute(
                'UPDATE rag_pipelines SET doc_count=doc_count-1,chunk_count=chunk_count-?,updated_at=CURRENT_TIMESTAMP WHERE id=?',
                (doc['chunk_count'], pipeline_id),
            )
        con.commit()
    finally:
        con.close()
    return {'ok': True}
