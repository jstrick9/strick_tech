"""
Agentic OS — Workspace Export/Import API
Full workspace portability: export all data as a single JSON archive,
import it on another instance.
"""
from __future__ import annotations
import json
import logging
import time
from datetime import datetime, timezone
from typing import Any

from fastapi import APIRouter, Request
from fastapi.responses import JSONResponse

router = APIRouter(prefix='/api/workspace', tags=['workspace'])
log = logging.getLogger('agentic.workspace')

from ..services.memory_db import get_conn

EXPORT_TABLES = [
    'agents',
    'chat_sessions',
    'chat_log',
    'tasks',
    'memory',
    'goals',
    'secrets',
    'swarm_history',
    'prompts',
    'steering_rules',
    'skills',
]


@router.get('/export')
def export_workspace(
    include_chat: bool = True,
    include_memory: bool = True,
    include_secrets: bool = False,
    limit_per_table: int = 10000,
):
    """Export the entire workspace as a portable JSON archive.

    Args:
        include_chat: Include chat_log messages (can be large)
        include_memory: Include memory entries
        include_secrets: Include encrypted secrets (off by default)
        limit_per_table: Max rows per table
    """
    con = get_conn()
    try:
        archive = {
            'format': 'agentic-os-workspace',
            'version': 1,
            'exported_at': datetime.now(timezone.utc).isoformat(),
            'tables': {},
        }

        for table in EXPORT_TABLES:
            if table == 'chat_log' and not include_chat:
                continue
            if table == 'memory' and not include_memory:
                continue
            if table == 'secrets' and not include_secrets:
                continue

            try:
                rows = con.execute(
                    f'SELECT * FROM {table} ORDER BY rowid DESC LIMIT ?',
                    (limit_per_table,)
                ).fetchall()
                archive['tables'][table] = [dict(r) for r in rows]
            except Exception:
                # Table may not exist in this instance
                archive['tables'][table] = []

        # Count totals
        total_rows = sum(len(v) for v in archive['tables'].values())
        archive['summary'] = {
            'tables_exported': len(archive['tables']),
            'total_rows': total_rows,
        }

        return archive
    finally:
        con.close()


@router.post('/import')
async def import_workspace(req: Request):
    """Import a workspace archive. Merges data (upserts by primary key)."""
    try:
        body = await req.json()
    except Exception:
        return JSONResponse({'ok': False, 'error': 'Invalid JSON'}, status_code=400)

    if body.get('format') != 'agentic-os-workspace':
        return JSONResponse({'ok': False, 'error': 'Invalid archive format'}, status_code=400)

    tables = body.get('tables', {})
    if not tables:
        return JSONResponse({'ok': False, 'error': 'No tables in archive'}, status_code=400)

    con = get_conn()
    try:
        imported = {}
        for table_name, rows in tables.items():
            if not rows:
                imported[table_name] = 0
                continue

            # Get column names from first row
            columns = list(rows[0].keys())
            placeholders = ','.join(['?' for _ in columns])
            col_names = ','.join(columns)

            count = 0
            for row in rows:
                try:
                    values = [row.get(c) for c in columns]
                    con.execute(
                        f'INSERT OR REPLACE INTO {table_name} ({col_names}) VALUES ({placeholders})',
                        values
                    )
                    count += 1
                except Exception:
                    pass  # Skip rows with schema mismatches

            con.commit()
            imported[table_name] = count

        return {'ok': True, 'imported': imported, 'total': sum(imported.values())}
    finally:
        con.close()


@router.get('/stats')
def workspace_stats():
    """Get workspace statistics — counts of all major entities."""
    con = get_conn()
    try:
        stats = {}
        tables = ['agents', 'chat_sessions', 'chat_log', 'tasks', 'memory',
                  'goals', 'secrets', 'swarm_history']
        for table in tables:
            try:
                count = con.execute(f'SELECT COUNT(*) FROM {table}').fetchone()[0]
                stats[table] = count
            except Exception:
                stats[table] = 0

        # Get DB size
        import os
        from backend.config import get_data_dir
        db_path = get_data_dir() / 'memory' / 'agentic.db'
        stats['db_size_mb'] = round(os.path.getsize(db_path) / (1024 * 1024), 2) if db_path.exists() else 0
        stats['exported_at'] = datetime.now(timezone.utc).isoformat()

        return {'ok': True, 'stats': stats}
    finally:
        con.close()
