"""
Agentic OS — Memory Router
All /api/memory/* endpoints: search, stats, galaxy graph, CRUD, reindex.

Route ordering: all static paths BEFORE /{memory_id} to avoid wildcard capture.
"""

from __future__ import annotations

import contextlib

from fastapi import APIRouter, Request

from ..services.memory_db import (
    audit_log,
    get_conn,
    memory_add,
    memory_galaxy_graph,
    memory_list,
    memory_search_fts,
    memory_stats,
)

router = APIRouter(prefix='/api/memory', tags=['memory'])


# ── Stats & meta ───────────────────────────────────────────────────────────────
@router.get('/stats')
def stats():
    """Execute or process stats operation."""
    return memory_stats()


@router.get('/galaxy')
def galaxy(limit: int = 200):
    """Execute or process galaxy operation."""
    return memory_galaxy_graph(min(limit, 500))


@router.get('/search')
def search(q: str = '', mode: str = 'hybrid', limit: int = 20, source: str = ''):
    """Execute or process search operation."""
    limit = min(int(limit), 100)
    if not q and not source:
        return memory_list(limit=limit)
    if mode == 'keyword' or not q:
        return memory_search_fts(q, limit=limit)
    # hybrid: FTS + recency blend
    fts_results = memory_search_fts(q, limit=limit)
    if source:
        fts_results = [r for r in fts_results if r.get('source') == source]
    # fallback: if no FTS hits, return recent
    if not fts_results:
        return memory_list(limit=limit, source=source)
    return fts_results


@router.get('/list')
def list_memories(limit: int = 100, offset: int = 0, source: str = ''):
    """Retrieve and return list memories."""
    return memory_list(limit=min(limit, 500), offset=offset, source=source)


@router.get('/export')
def export_memories(limit: int = 5000, source: str = ''):
    """Export all memories as JSON."""
    memories = memory_list(limit=min(limit, 10000), offset=0, source=source)
    return {
        'ok': True,
        'memories': memories,
        'count': len(memories),
        'source_filter': source or 'all',
    }


# ── Qdrant / Hybrid search (sub-path so no wildcard issue) ───────────────────
@router.get('/qdrant/status')
def qdrant_status():
    """Check Qdrant connection and sentence-transformers status."""
    from ..services.memory_db import qdrant_status as _qs

    return _qs()


@router.get('/hybrid-search')
async def hybrid_search_endpoint(q: str = '', limit: int = 20):
    """Hybrid search: Qdrant semantic + SQLite FTS5 combined."""
    if not q:
        return {'results': [], 'mode': 'none'}
    from ..services.memory_db import _QDRANT_AVAILABLE, hybrid_search

    results = hybrid_search(q, limit=min(limit, 50))
    return {
        'results': results,
        'count': len(results),
        'query': q,
        'mode': 'hybrid' if _QDRANT_AVAILABLE else 'fts5',
    }


# ── CRUD ───────────────────────────────────────────────────────────────────────
@router.post('/add')
async def add(req: Request):
    """Execute or process add operation."""
    try:
        try:
            body = await req.json()
        except (KeyError, TypeError, ValueError, json.JSONDecodeError, OSError, AttributeError, RuntimeError):
            body = {}
    except (KeyError, TypeError, ValueError, json.JSONDecodeError, OSError, AttributeError, RuntimeError):
        body = {}
    source = (body.get('source') or 'user').strip()[:64]
    content = (body.get('content') or '').strip()
    tags_raw = body.get('tags') or ''
    # Accept both list ["a","b"] and comma-string "a,b"
    if isinstance(tags_raw, list):
        tags = ','.join(str(t) for t in tags_raw)[:256]
    else:
        tags = str(tags_raw).strip()[:256]
    if not content:
        return {'ok': False, 'error': 'content required'}
    mid = memory_add(source, content[:4000], tags)
    return {'ok': True, 'id': mid}


@router.post('/add-with-embedding')
async def add_with_embedding(req: Request):
    """Add memory entry with automatic vector embedding."""
    try:
        try:
            body = await req.json()
        except (KeyError, TypeError, ValueError, json.JSONDecodeError, OSError, AttributeError, RuntimeError):
            body = {}
    except (KeyError, TypeError, ValueError, json.JSONDecodeError, OSError, AttributeError, RuntimeError):
        body = {}
    content = (body.get('content') or '').strip()
    if not content:
        return {'ok': False, 'error': 'content required'}
    source = (body.get('source') or 'api').strip()[:64]
    raw_tags = body.get('tags') or ''
    # Accept both list and string for tags
    if isinstance(raw_tags, list):
        tags = ','.join(str(t) for t in raw_tags)[:256]
    else:
        tags = str(raw_tags).strip()[:256]
    meta = body.get('metadata', {}) or {}

    from ..services.memory_db import _QDRANT_AVAILABLE, _ST_AVAILABLE, memory_add_with_vector

    mid = memory_add_with_vector(source, content[:4000], tags, meta)

    return {
        'ok': True,
        'id': mid,
        'embedded': _ST_AVAILABLE,
        'qdrant_stored': _QDRANT_AVAILABLE,
        'fallback': 'SQLite FTS5' if not _QDRANT_AVAILABLE else None,
    }


@router.post('/reindex')
async def reindex():
    """Rebuild FTS index from memory table."""
    con = get_conn()
    try:
        try:
            con.execute("INSERT INTO memory_fts(memory_fts) VALUES('rebuild')")
            con.commit()
        except (KeyError, TypeError, ValueError, json.JSONDecodeError, OSError, AttributeError, RuntimeError):
            # manual rebuild
            rows = con.execute('SELECT id, content, tags FROM memory').fetchall()
            try:
                con.execute('DELETE FROM memory_fts')
            except (KeyError, TypeError, ValueError, json.JSONDecodeError, OSError, AttributeError, RuntimeError):
                pass
            for r in rows:
                try:
                    con.execute(
                        'INSERT INTO memory_fts(rowid, content, tags) VALUES (?,?,?)', (r[0], r[1] or '', r[2] or '')
                    )
                except (KeyError, TypeError, ValueError, json.JSONDecodeError, OSError, AttributeError, RuntimeError):
                    pass
            con.commit()
        total = con.execute('SELECT COUNT(*) FROM memory').fetchone()[0]
    finally:
        con.close()
    return {'ok': True, 'total': total, 'vectorized': total, 'model': 'sqlite-fts5'}


@router.post('/bulk-delete')
async def bulk_delete(req: Request):
    """Delete multiple memory entries by ID list."""
    try:
        try:
            body = await req.json()
        except (KeyError, TypeError, ValueError, json.JSONDecodeError, OSError, AttributeError, RuntimeError):
            body = {}
    except (KeyError, TypeError, ValueError, json.JSONDecodeError, OSError, AttributeError, RuntimeError):
        body = {}
    ids = body.get('ids', [])
    if not ids or not isinstance(ids, list):
        return {'ok': False, 'error': 'ids list required'}
    ids = [int(i) for i in ids if str(i).lstrip('-').isdigit()]
    if not ids:
        return {'ok': False, 'error': 'no valid IDs'}
    con = get_conn()
    try:
        placeholders = ','.join('?' * len(ids))
        cur = con.execute(f'DELETE FROM memory WHERE id IN ({placeholders})', ids)
        try:
            for mid in ids:
                con.execute('DELETE FROM memory_fts WHERE rowid=?', (mid,))
        except (KeyError, TypeError, ValueError, json.JSONDecodeError, OSError, AttributeError, RuntimeError):
            pass
        con.commit()
        deleted = cur.rowcount
    finally:
        con.close()
    # Remove from Qdrant if available
    try:
        from ..services.memory_db import _QDRANT_AVAILABLE
        from ..services.memory_db import qdrant_delete as _qd

        if _QDRANT_AVAILABLE:
            for mid in ids:
                _qd(mid)
    except (KeyError, TypeError, ValueError, json.JSONDecodeError, OSError, AttributeError, RuntimeError):
        pass
    audit_log('memory_bulk_delete', f'{deleted} items')
    return {'ok': True, 'deleted': deleted, 'ids': ids}


@router.post('/import')
async def import_memories(req: Request):
    """Import memories from a JSON list."""
    try:
        try:
            body = await req.json()
        except (KeyError, TypeError, ValueError, json.JSONDecodeError, OSError, AttributeError, RuntimeError):
            body = {}
    except (KeyError, TypeError, ValueError, json.JSONDecodeError, OSError, AttributeError, RuntimeError):
        body = {}
    memories = body.get('memories', [])
    if not memories or not isinstance(memories, list):
        return {'ok': False, 'error': 'memories list required'}
    imported, skipped = 0, 0
    for m in memories:
        content = (m.get('content') or '').strip()
        if not content:
            skipped += 1
            continue
        source = (m.get('source') or 'import').strip()[:64]
        tags = (m.get('tags') or '').strip()[:256]
        try:
            memory_add(source, content[:4000], tags)
            imported += 1
        except (KeyError, TypeError, ValueError, json.JSONDecodeError, OSError, AttributeError, RuntimeError):
            skipped += 1
    audit_log('memory_import', f'{imported} imported, {skipped} skipped')
    return {'ok': True, 'imported': imported, 'skipped': skipped}


@router.post('/qdrant/sync-all')
async def sync_all_to_qdrant():
    """Sync all SQLite memories to Qdrant (one-time migration)."""
    from ..services.memory_db import _QDRANT_AVAILABLE, get_conn, qdrant_upsert

    if not _QDRANT_AVAILABLE:
        return {'ok': False, 'error': 'Qdrant not available — run: docker run -p 6333:6333 qdrant/qdrant'}

    con = get_conn()
    try:
        rows = con.execute('SELECT id, source, content, tags FROM memory LIMIT 1000').fetchall()
    finally:
        con.close()

    synced, failed = 0, 0
    for row in rows:
        ok = qdrant_upsert(row['id'], row['content'] or '', {'source': row['source'], 'tags': row['tags']})
        if ok:
            synced += 1
        else:
            failed += 1

    return {'ok': True, 'synced': synced, 'failed': failed, 'total': len(rows)}


# ── Single-memory CRUD — keep /{memory_id} routes LAST ────────────────────────


@router.get('/{memory_id}')
def get_memory(memory_id: int):
    """Get a single memory entry by ID."""
    con = get_conn()
    try:
        row = con.execute(
            'SELECT id, source, content, tags, created_at FROM memory WHERE id=?', (memory_id,)
        ).fetchone()
    finally:
        con.close()
    if not row:
        return {'ok': False, 'error': 'Memory not found'}
    return dict(row)


@router.put('/{memory_id}')
async def update_memory(memory_id: int, req: Request):
    """Update a memory entry's content and/or tags."""
    try:
        try:
            body = await req.json()
        except (KeyError, TypeError, ValueError, json.JSONDecodeError, OSError, AttributeError, RuntimeError):
            body = {}
    except (KeyError, TypeError, ValueError, json.JSONDecodeError, OSError, AttributeError, RuntimeError):
        body = {}
    content = (body.get('content') or '').strip()
    tags = (body.get('tags') or '').strip()[:256]
    if not content:
        return {'ok': False, 'error': 'content required'}
    con = get_conn()
    try:
        cur = con.execute('UPDATE memory SET content=?, tags=? WHERE id=?', (content[:4000], tags, memory_id))
        if cur.rowcount == 0:
            return {'ok': False, 'error': 'Memory not found'}
        # Update FTS
        try:
            con.execute('DELETE FROM memory_fts WHERE rowid=?', (memory_id,))
            con.execute('INSERT INTO memory_fts(rowid, content, tags) VALUES (?,?,?)', (memory_id, content, tags))
        except (KeyError, TypeError, ValueError, json.JSONDecodeError, OSError, AttributeError, RuntimeError):
            pass
        con.commit()
        audit_log('memory_update', str(memory_id))
    finally:
        con.close()
    return {'ok': True, 'id': memory_id}


@router.delete('/{memory_id}')
def delete(memory_id: int):
    """Execute or process delete operation."""
    con = get_conn()
    try:
        cur = con.execute('DELETE FROM memory WHERE id=?', (memory_id,))
        # update FTS
        with contextlib.suppress(Exception):
            con.execute('DELETE FROM memory_fts WHERE rowid=?', (memory_id,))
        con.commit()
    finally:
        con.close()
    # Also remove from Qdrant if available
    try:
        from ..services.memory_db import _QDRANT_AVAILABLE
        from ..services.memory_db import qdrant_delete as _qd

        if _QDRANT_AVAILABLE:
            _qd(memory_id)
    except (KeyError, TypeError, ValueError, json.JSONDecodeError, OSError, AttributeError, RuntimeError):
        pass
    audit_log('memory_delete', str(memory_id))
    return {'ok': cur.rowcount > 0, 'deleted': memory_id}
