"""
Agentic OS — Database Studio Router
Dual backend:
  1. Built-in SQLite studio (local, zero setup) — visual table browser, SQL editor, schema designer
  2. Supabase connect (PostgreSQL + Auth + Storage) — optional cloud DB like Lovable

Both accessible from the same UI.
"""

from __future__ import annotations

import contextlib

import json
import logging
import os
import re
import sqlite3
from pathlib import Path

import httpx
from fastapi import APIRouter, Request

router = APIRouter(prefix='/api/db', tags=['database'])
log = logging.getLogger('agentic.db')
from backend.config import get_data_dir
ROOT = get_data_dir()
DB = ROOT / 'memory' / 'agentic.db'


# ── SQLite Studio ──────────────────────────────────────────────────────────────
@router.get('/sqlite/tables')
def sqlite_tables():
    """List all user-created tables (excluding system tables)."""
    con = sqlite3.connect(DB)
    con.row_factory = sqlite3.Row
    try:
        tables = con.execute(
            "SELECT name, type FROM sqlite_master WHERE type IN ('table','view') ORDER BY name"
        ).fetchall()
        result = []
        for t in tables:
            name = t['name']
            if name.startswith('memory_fts'):
                continue
            try:
                count = con.execute(f'SELECT COUNT(*) FROM "{name}"').fetchone()[0]
                cols = [
                    {'name': c[1], 'type': c[2], 'notnull': bool(c[3]), 'pk': bool(c[5])}
                    for c in con.execute(f'PRAGMA table_info("{name}")').fetchall()
                ]
            except (KeyError, TypeError, ValueError, json.JSONDecodeError, OSError, AttributeError, RuntimeError):
                count, cols = 0, []
            result.append({'name': name, 'type': t['type'], 'row_count': count, 'columns': cols})
        return result
    except Exception as e:
        log.error('sqlite_tables error: %s', e)
        return []
    finally:
        con.close()


@router.get('/sqlite/table/{table}')
def sqlite_table_data(table: str, limit: int = 100, offset: int = 0, q: str = ''):
    """Read rows from a table with optional search."""
    # Validate table name
    if not re.match(r'^[a-zA-Z_][a-zA-Z0-9_]*$', table):
        return {'ok': False, 'error': 'Invalid table name'}
    con = sqlite3.connect(DB)
    con.row_factory = sqlite3.Row
    try:
        cols = [c[1] for c in con.execute(f'PRAGMA table_info("{table}")').fetchall()]
        total = con.execute(f'SELECT COUNT(*) FROM "{table}"').fetchone()[0]
        sql = f'SELECT * FROM "{table}"'
        params = []
        if q and cols:
            conditions = ' OR '.join(f'CAST("{c}" AS TEXT) LIKE ?' for c in cols[:5])
            sql += f' WHERE {conditions}'
            params = [f'%{q}%'] * min(5, len(cols))
        limit = min(max(int(limit), 1), 500)
        offset = max(int(offset), 0)
        sql += f' LIMIT {limit} OFFSET {offset}'
        rows = con.execute(sql, params).fetchall()
        con.close()
        return {
            'ok': True,
            'table': table,
            'columns': cols,
            'rows': [dict(r) for r in rows],
            'total': total,
            'limit': limit,
            'offset': offset,
        }
    except Exception as e:
        con.close()
        return {'ok': False, 'error': str(e)}


@router.post('/sqlite/query')
async def sqlite_query(req: Request):
    """Execute a raw SQL query (SELECT only for safety, or allow writes with flag)."""
    try:
        body = await req.json()
    except (json.JSONDecodeError, TypeError, ValueError):
        body = {}
    sql = (body.get('sql') or '').strip()
    allow_write = bool(body.get('allow_write', False))

    if not sql:
        return {'ok': False, 'error': 'SQL required'}

    # Safety: only allow SELECT unless explicitly enabled
    sql_upper = sql.upper().lstrip()
    is_write = any(
        sql_upper.startswith(kw) for kw in ['INSERT', 'UPDATE', 'DELETE', 'DROP', 'CREATE', 'ALTER', 'REPLACE']
    )
    if is_write and not allow_write:
        return {'ok': False, 'error': 'Write queries disabled. Set allow_write=true to enable.', 'is_write': True}

    con = sqlite3.connect(DB)
    con.row_factory = sqlite3.Row
    try:
        cur = con.execute(sql)
        if is_write:
            con.commit()
            con.close()
            return {'ok': True, 'rows_affected': cur.rowcount, 'type': 'write'}
        rows = cur.fetchall()[:1000]
        cols = [d[0] for d in (cur.description or [])]
        con.close()
        return {
            'ok': True,
            'columns': cols,
            'rows': [dict(r) for r in rows],
            'count': len(rows),
            'type': 'select',
        }
    except Exception as e:
        con.close()
        return {'ok': False, 'error': str(e)}


@router.post('/sqlite/table/{table}/insert')
async def sqlite_insert(table: str, req: Request):
    """Insert a row into a table."""
    if not re.match(r'^[a-zA-Z_][a-zA-Z0-9_]*$', table):
        return {'ok': False, 'error': 'Invalid table name'}
    try:
        body = await req.json()
    except (json.JSONDecodeError, TypeError, ValueError):
        body = {}
    row = body.get('row', {})
    if not row:
        return {'ok': False, 'error': 'row data required'}
    con = sqlite3.connect(DB)
    try:
        cols = list(row.keys())
        vals = list(row.values())
        placeholders = ', '.join('?' * len(cols))
        col_names = ', '.join(f'"{c}"' for c in cols)
        cur = con.execute(f'INSERT INTO "{table}" ({col_names}) VALUES ({placeholders})', vals)
        con.commit()
        rowid = cur.lastrowid
        con.close()
        return {'ok': True, 'rowid': rowid}
    except Exception as e:
        con.close()
        return {'ok': False, 'error': str(e)}


@router.delete('/sqlite/table/{table}/row')
async def sqlite_delete_row(table: str, req: Request):
    """Delete rows matching a condition."""
    if not re.match(r'^[a-zA-Z_][a-zA-Z0-9_]*$', table):
        return {'ok': False, 'error': 'Invalid table name'}
    try:
        body = await req.json()
    except (json.JSONDecodeError, TypeError, ValueError):
        body = {}
    pk = body.get('pk_column', 'id')
    value = body.get('pk_value')
    if value is None:
        return {'ok': False, 'error': 'pk_value required'}
    con = sqlite3.connect(DB)
    try:
        cur = con.execute(f'DELETE FROM "{table}" WHERE "{pk}"=?', (value,))
        con.commit()
        con.close()
        return {'ok': True, 'deleted': cur.rowcount}
    except Exception as e:
        con.close()
        return {'ok': False, 'error': str(e)}


@router.get('/sqlite/schema')
def sqlite_schema():
    """Return the full database schema (CREATE statements)."""
    con = sqlite3.connect(DB)
    try:
        rows = con.execute('SELECT name, sql FROM sqlite_master WHERE sql IS NOT NULL ORDER BY type, name').fetchall()
        return [{'name': r[0], 'sql': r[1]} for r in rows if not r[0].startswith('memory_fts')]
    except Exception as e:
        log.error('sqlite_schema error: %s', e)
        return []
    finally:
        con.close()


@router.post('/sqlite/table/create')
async def create_table(req: Request):
    """Create a new table from a natural language description or raw SQL."""
    try:
        body = await req.json()
    except (json.JSONDecodeError, TypeError, ValueError):
        body = {}
    sql = body.get('sql', '')
    name = body.get('name', '')
    cols = body.get('columns', [])  # [{name, type, pk, nullable}]

    if not sql and name and cols:
        # Build SQL from column definitions
        col_defs = []
        for c in cols:
            t = c.get('type', 'TEXT').upper()
            pk = ' PRIMARY KEY' if c.get('pk') else ''
            notnull = ' NOT NULL' if not c.get('nullable', True) else ''
            col_defs.append(f'  "{c["name"]}" {t}{pk}{notnull}')
        sql = f'CREATE TABLE IF NOT EXISTS "{name}" (\n' + ',\n'.join(col_defs) + '\n)'

    if not sql:
        return {'ok': False, 'error': 'Provide sql or name+columns'}

    con = sqlite3.connect(DB)
    try:
        con.execute(sql)
        con.commit()
        return {'ok': True, 'sql': sql}
    except Exception as e:
        return {'ok': False, 'error': str(e), 'sql': sql}
    finally:
        con.close()


def _strip_markdown_sql(text: str) -> str:
    """Robustly strip markdown code fences from LLM-generated SQL."""
    text = text.strip()
    if text.startswith('```'):
        lines = text.split('\n')
        lines = lines[1:]  # Remove first line (```sql or ```)
        if lines and lines[-1].strip() == '```':
            lines = lines[:-1]
        text = '\n'.join(lines).strip()
    return text


@router.post('/sqlite/ai-schema')
async def ai_schema_designer(req: Request):
    """Generate a SQL schema from natural language description."""
    try:
        body = await req.json()
    except (json.JSONDecodeError, TypeError, ValueError):
        body = {}
    desc = (body.get('description') or '').strip()
    if not desc:
        return {'ok': False, 'error': 'description required'}

    from ..services.llm import complete

    messages = [
        {
            'role': 'system',
            'content': 'You are a SQLite database schema expert. '
            'Generate a CREATE TABLE SQL statement from the description. '
            'Use SQLite-compatible types: INTEGER, TEXT, REAL, BLOB, NUMERIC. '
            "Always include 'id INTEGER PRIMARY KEY AUTOINCREMENT' and "
            "'created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP'. "
            'Return ONLY the SQL, no explanation, no markdown.',
        },
        {'role': 'user', 'content': f'Create a SQLite table for: {desc}'},
    ]
    result = await complete(messages, agent_id='builder', max_tokens=512, temperature=0.2, inject_steering=False)
    sql = result.get('text', '').strip()
    # Strip markdown code fences robustly
    sql = _strip_markdown_sql(sql)
    return {'ok': result.get('ok'), 'sql': sql, 'description': desc}


# ── Supabase Integration ───────────────────────────────────────────────────────
def _supabase_url() -> str:
    return os.getenv('SUPABASE_URL', '')


def _supabase_key() -> str:
    return os.getenv('SUPABASE_ANON_KEY', '') or os.getenv('SUPABASE_SERVICE_KEY', '')


def _supabase_headers() -> dict:
    key = _supabase_key()
    return {
        'apikey': key,
        'Authorization': f'Bearer {key}',
        'Content-Type': 'application/json',
    }


@router.get('/supabase/status')
async def supabase_status():
    """Check Supabase connection."""
    url = _supabase_url()
    key = _supabase_key()
    if not url or not key:
        return {
            'connected': False,
            'setup': {
                'steps': [
                    '1. Go to https://supabase.com and create a project',
                    '2. In Project Settings > API, copy your URL and anon key',
                    '3. Add to .env:',
                    '   SUPABASE_URL=https://xxxx.supabase.co',
                    '   SUPABASE_ANON_KEY=eyJhbGci...',
                    '4. Or save via 🔐 Vault tab in Agentic OS',
                ],
                'url': 'https://supabase.com',
            },
        }
    try:
        async with httpx.AsyncClient(timeout=8.0) as client:
            r = await client.get(f'{url}/rest/v1/', headers=_supabase_headers())
            if r.status_code in (200, 400):  # 400 = connected but no table queried
                return {
                    'connected': True,
                    'url': url,
                    'region': url.split('.supabase.co')[0].split('//')[-1] if '.supabase.co' in url else 'custom',
                }
            return {'connected': False, 'error': f'HTTP {r.status_code}'}
    except Exception as e:
        return {'connected': False, 'error': str(e)}


@router.get('/supabase/tables')
async def supabase_tables():
    """List tables in Supabase."""
    url, key = _supabase_url(), _supabase_key()
    if not url or not key:
        return {'ok': False, 'error': 'Supabase not configured'}
    try:
        async with httpx.AsyncClient(timeout=10.0) as client:
            # Query information_schema
            r = await client.post(
                f'{url}/rest/v1/rpc/get_tables',
                headers={**_supabase_headers(), 'Prefer': 'return=representation'},
                json={},
            )
            if r.status_code == 404:
                # Fallback: try direct query
                r2 = await client.get(f'{url}/rest/v1/', headers=_supabase_headers())
                return {'ok': True, 'tables': [], 'note': 'List tables via Supabase Studio'}
            return {'ok': True, 'tables': r.json()}
    except Exception as e:
        return {'ok': False, 'error': str(e)}


@router.post('/supabase/query')
async def supabase_query(req: Request):
    """Run a query against Supabase using PostgREST."""
    try:
        body = await req.json()
    except (json.JSONDecodeError, TypeError, ValueError):
        body = {}
    table = body.get('table', '')
    select = body.get('select', '*')
    filters = body.get('filters', {})
    limit = min(int(body.get('limit', 100)), 1000)
    order = body.get('order', '')

    url, key = _supabase_url(), _supabase_key()
    if not url or not key:
        return {'ok': False, 'error': 'Supabase not configured'}
    if not table:
        return {'ok': False, 'error': 'table required'}

    # Validate table name (prevent path injection)
    if not re.match(r'^[a-zA-Z_][a-zA-Z0-9_]*$', table):
        return {'ok': False, 'error': 'Invalid table name'}

    try:
        params = {'select': select, 'limit': limit}
        for col, val in filters.items():
            # PostgREST filter format: eq.value (httpx will URL-encode the value)
            params[col] = f'eq.{val}'
        if order:
            params['order'] = order

        async with httpx.AsyncClient(timeout=10.0) as client:
            r = await client.get(
                f'{url}/rest/v1/{table}', headers={**_supabase_headers(), 'Prefer': 'count=exact'}, params=params
            )
            if r.status_code == 200:
                return {'ok': True, 'table': table, 'rows': r.json(), 'count': len(r.json())}
            return {'ok': False, 'error': f'HTTP {r.status_code}: {r.text[:200]}'}
    except Exception as e:
        return {'ok': False, 'error': str(e)}


@router.post('/supabase/insert')
async def supabase_insert(req: Request):
    """Execute or process supabase insert operation."""
    try:
        body = await req.json()
    except (json.JSONDecodeError, TypeError, ValueError):
        body = {}
    table = body.get('table', '')
    row = body.get('row', {})
    url, key = _supabase_url(), _supabase_key()
    if not url or not key or not table or not row:
        return {'ok': False, 'error': 'table and row required'}
    try:
        async with httpx.AsyncClient(timeout=10.0) as client:
            r = await client.post(
                f'{url}/rest/v1/{table}', headers={**_supabase_headers(), 'Prefer': 'return=representation'}, json=row
            )
            return {
                'ok': r.status_code in (200, 201),
                'data': r.json() if r.status_code in (200, 201) else r.text[:200],
            }
    except Exception as e:
        return {'ok': False, 'error': str(e)}


@router.post('/supabase/ai-setup')
async def supabase_ai_setup(req: Request):
    """AI-powered Supabase schema generation from app description."""
    try:
        body = await req.json()
    except (json.JSONDecodeError, TypeError, ValueError):
        body = {}
    desc = (body.get('description') or '').strip()
    if not desc:
        return {'ok': False, 'error': 'description required'}

    from ..services.llm import complete

    messages = [
        {
            'role': 'system',
            'content': 'You are a Supabase/PostgreSQL expert. '
            'Generate SQL to create tables with Row Level Security policies. '
            'Include: CREATE TABLE statements, RLS policies, indexes, and seed data. '
            'Make it production-ready. Return only SQL.',
        },
        {'role': 'user', 'content': f'Create Supabase schema for: {desc}'},
    ]
    result = await complete(messages, agent_id='builder', max_tokens=2048, temperature=0.2, inject_steering=False)
    sql = result.get('text', '').strip()
    sql = _strip_markdown_sql(sql)
    return {
        'ok': result.get('ok'),
        'sql': sql,
        'description': desc,
        'note': 'Run this SQL in Supabase SQL Editor to create your schema.',
    }
