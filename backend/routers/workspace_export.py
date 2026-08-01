"""
Agentic OS — Workspace Export/Import API
Full workspace portability: export all data as a single JSON archive,
import it on another instance.
"""
from __future__ import annotations

import logging
from datetime import datetime, timezone

from fastapi import APIRouter, Request
from fastapi.responses import JSONResponse

router = APIRouter(prefix='/api/workspace', tags=['workspace'])
log = logging.getLogger('agentic.workspace')

from ..services.memory_db import get_conn

# BUG FIX: 3 of these 11 entries referenced table names that don't actually
# exist in the schema — 'prompts' (the real table is 'prompt_library',
# see backend/routers/prompts.py), 'steering_rules' (the real tables are
# 'steering_files' and 'steering_learned', see backend/routers/steering.py),
# and 'skills' (skills are stored in a JSON file — skills/skills.json, see
# backend/routers/skills.py — not a DB table at all). Every export silently
# produced an empty [] for these 3 "tables" (the existing `except Exception:
# archive['tables'][table] = []` fallback masked the mismatch completely —
# confirmed live: a real export's summary reported 0 rows for all 3), and
# a restore of such an archive correctly no-ops for them, but the omission
# meant this backup feature was silently missing prompts, steering rules,
# and skills entirely since the feature was first written — a real gap now
# that it's wired up to an actual "Export/Restore" UI in this pass.
EXPORT_TABLES = [
    'agents',
    'chat_sessions',
    'chat_log',
    'tasks',
    'memory',
    'goals',
    'secrets',
    'swarm_history',
    'prompt_library',
    'steering_files',
    'steering_learned',
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
            # SECURITY FIX: `table_name` and each row's column names (both
            # fully attacker-controlled — this endpoint accepts an
            # arbitrary uploaded/pasted JSON archive) were previously
            # interpolated directly into a raw SQL string with ZERO
            # validation: `f'INSERT OR REPLACE INTO {table_name}
            # ({col_names}) VALUES (...)'`. Parameterized `?` placeholders
            # only protect VALUES, never table/column identifiers — this
            # is a classic SQL-injection-via-identifier pattern. Since
            # this endpoint is being wired up to a real "Restore from
            # Backup" UI button in this pass (previously it had zero
            # frontend access at all), it needs to actually be hardened
            # rather than left as a latent landmine now that a user can
            # reach it by importing an untrusted/tampered .json file.
            # Fix: only allow table names from the same fixed allow-list
            # this router itself exports from (EXPORT_TABLES), and only
            # allow column names that actually exist on that table
            # (via PRAGMA table_info, the same safe pattern already used
            # in backend/routers/database.py) — any unrecognized table or
            # column is silently skipped rather than ever reaching SQL.
            if table_name not in EXPORT_TABLES:
                imported[table_name] = 0
                continue
            if not rows:
                imported[table_name] = 0
                continue

            try:
                real_columns = {c[1] for c in con.execute(f'PRAGMA table_info("{table_name}")').fetchall()}
            except Exception:
                imported[table_name] = 0
                continue
            if not real_columns:
                imported[table_name] = 0
                continue

            count = 0
            for row in rows:
                columns = [c for c in row.keys() if c in real_columns]
                if not columns:
                    continue
                placeholders = ','.join(['?' for _ in columns])
                col_names = ','.join(f'"{c}"' for c in columns)
                try:
                    values = [row.get(c) for c in columns]
                    con.execute(
                        f'INSERT OR REPLACE INTO "{table_name}" ({col_names}) VALUES ({placeholders})',
                        values,
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
