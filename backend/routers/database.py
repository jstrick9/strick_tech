"""
Agentic OS — Database Studio Router
Dual backend:
  1. Built-in SQLite studio (local, zero setup) — visual table browser, SQL editor, schema designer
  2. Supabase connect (PostgreSQL + Auth + Storage) — optional cloud DB like Lovable

Both accessible from the same UI.
"""

from __future__ import annotations

import json
import logging
import os
import re
import sqlite3

import httpx
from fastapi import APIRouter, Request
from fastapi.responses import JSONResponse

router = APIRouter(prefix='/api/db', tags=['database'])
log = logging.getLogger('agentic.db')
from backend.config import get_data_dir

ROOT = get_data_dir()
DB = ROOT / 'memory' / 'agentic.db'


def _connect() -> sqlite3.Connection:
    """
    Open a connection to the same agentic.db file used app-wide by
    backend/services/memory_db.py's get_conn(). Every call site in this
    router previously used a bare `sqlite3.connect(DB)` with Python's
    stdlib defaults — notably a 5-SECOND busy_timeout and no WAL/
    synchronous tuning — while every OTHER part of the app (chat, memory,
    agents, specs, workflows, etc.) opens the identical file via
    memory_db.get_conn()'s 10-SECOND busy_timeout + WAL journal mode.
    Database Studio is a power-user tool explicitly meant to run
    SELECT/INSERT/DELETE/DDL against live application data WHILE the rest
    of the app keeps writing to the same file — mismatched locking
    behavior here is exactly the kind of "works in isolation, flakes
    under real concurrent use" bug this session has repeatedly found and
    fixed elsewhere (see the Specs module's "database is locked" fix).
    Centralizing connection setup here matches get_conn()'s settings.

    The path now comes from memory_db.db_path() rather than the module-level
    DB constant, so AGENTIC_TEST_DB redirection applies here too — otherwise
    this router would keep writing to the production database during tests
    while every other module was correctly sandboxed.
    """
    from ..services.memory_db import db_path

    con = sqlite3.connect(db_path(), check_same_thread=False, timeout=10)
    con.execute('PRAGMA busy_timeout=10000')
    con.execute('PRAGMA journal_mode=WAL')
    con.execute('PRAGMA synchronous=NORMAL')
    return con


# Statements that modify data or schema. Detected by scanning the whole
# statement rather than matching a prefix — see classify_sql().
_WRITE_KEYWORDS = frozenset({
    'INSERT', 'UPDATE', 'DELETE', 'DROP', 'CREATE', 'ALTER', 'REPLACE',
    'TRUNCATE', 'VACUUM', 'REINDEX', 'ANALYZE',
})

# Never permitted, with or without allow_write. These reach outside the
# database file or corrupt its internals, so "the user opted in to writes" is
# not consent to them:
#   ATTACH   — opens or CREATES an arbitrary file on disk, and lets a query
#              copy rows out of agentic.db into it. Verified live: an ATTACH
#              with allow_write=false created /tmp/evil_attached.db.
#   PRAGMA writable_schema — allows direct edits to sqlite_master, i.e. silent
#              schema corruption that survives every other guard.
_FORBIDDEN_STATEMENTS = frozenset({'ATTACH', 'DETACH'})
_FORBIDDEN_PRAGMAS = ('WRITABLE_SCHEMA', 'JOURNAL_MODE', 'SYNCHRONOUS', 'TEMP_STORE')


def strip_sql_comments(sql: str) -> str:
    """Remove -- line comments and /* */ block comments from anywhere in `sql`.

    The previous implementation only stripped comments from the START of the
    statement, which was enough for the bypass it was written for but leaves
    `SELECT 1 /* */ ; DROP ...` and similar untouched. Strings are respected so
    a literal containing `--` is not mangled.
    """
    out = []
    i, n = 0, len(sql)
    quote = None
    while i < n:
        ch = sql[i]
        if quote:
            out.append(ch)
            if ch == quote:
                # Doubled quote inside a string is an escaped quote.
                if i + 1 < n and sql[i + 1] == quote:
                    out.append(sql[i + 1])
                    i += 2
                    continue
                quote = None
            i += 1
            continue
        if ch in ('\'', '"', '`'):
            quote = ch
            out.append(ch)
            i += 1
            continue
        if ch == '-' and i + 1 < n and sql[i + 1] == '-':
            nl = sql.find('\n', i)
            i = n if nl == -1 else nl + 1
            out.append(' ')
            continue
        if ch == '/' and i + 1 < n and sql[i + 1] == '*':
            end = sql.find('*/', i + 2)
            i = n if end == -1 else end + 2
            out.append(' ')
            continue
        out.append(ch)
        i += 1
    return ''.join(out)


def classify_sql(sql: str) -> tuple[bool, str]:
    """Classify a statement. Returns (is_write, refusal_reason_or_empty).

    SECURITY FIX: write detection matched a KEYWORD PREFIX on the statement.
    Any construct that puts something else first slipped through as a "read",
    executed anyway, and was reported back as {"type": "select"}. Verified live
    against a real table with allow_write=false:

        WITH t AS (SELECT 1) DELETE FROM dbstudio_victim
          -> {"ok": true, "type": "select", "count": 0}   and the row was GONE

        ATTACH DATABASE '/tmp/evil_attached.db' AS evil
          -> reported as a select; the file was created on disk

        PRAGMA writable_schema=1
          -> reported as a select; schema protection disabled

    A prefix check cannot express "does this statement modify anything" — SQL
    is not prefix-structured. Scanning for the keywords as whole WORDS anywhere
    in the comment-stripped statement is conservative in the right direction:
    it may over-report a read as a write (the user sets allow_write and
    proceeds), but it will not under-report a write as a read.
    """
    import re as _re

    cleaned = strip_sql_comments(sql).strip()
    if not cleaned:
        return False, 'statement is empty after removing comments'

    upper = cleaned.upper()

    # Leading token, ignoring wrapping parens/whitespace.
    lead_match = _re.match(r'^[\s(]*([A-Z_]+)', upper)
    lead = lead_match.group(1) if lead_match else ''

    if lead in _FORBIDDEN_STATEMENTS:
        return True, (
            f'{lead} is not permitted: it can create or read files outside the '
            f'application database.'
        )
    if lead == 'PRAGMA':
        for bad in _FORBIDDEN_PRAGMAS:
            if bad in upper:
                return True, (
                    f'PRAGMA {bad.lower()} is not permitted: it can corrupt the '
                    f'database or alter its durability guarantees.'
                )

    # Whole-word scan of the comment-stripped statement, outside string
    # literals (already normalised by strip_sql_comments keeping them intact,
    # so mask them here before matching).
    masked = _re.sub(r"'[^']*'", "''", upper)
    masked = _re.sub(r'"[^"]*"', '""', masked)
    for kw in _WRITE_KEYWORDS:
        if _re.search(rf'\b{kw}\b', masked):
            return True, ''
    return False, ''



# ── Sensitive data policy ──────────────────────────────────────────────────────
from ..services import db_policy


def _policy_refusal(sql: str) -> str:
    """Refusal reason if the statement touches credential material."""
    return db_policy.check_statement(strip_sql_comments(sql))


# ── Audit trail ────────────────────────────────────────────────────────────────
# Every mutating statement Database Studio executes is recorded in the immutable
# hash-chained ledger (backend/routers/audit_log.py) BEFORE it runs and again
# with its outcome AFTER it runs.
#
# Why: verified live before this fix — `DROP TABLE audit_victim` with
# allow_write=true returned {"ok": true, "type": "write"} and produced ZERO
# rows anywhere in audit_log_chain. The single most destructive operation the
# platform exposes was also its least observable one: no record of who ran it,
# what the statement was, or that it happened at all. Every other privileged
# subsystem in this codebase (MCP tool calls, connector execs, goal changes,
# agent messages) already appends receipts; Database Studio did not.
#
# Two entries, not one, for destructive statements. The ledger is append-only,
# so an "in flight" row cannot later be updated with its result. A pre-entry
# means a statement that crashes the process, corrupts the file, or hangs
# forever still leaves a trace of having been attempted — which is precisely
# the case where the post-entry never gets written.

# Statements that destroy data or schema. These get the pre-entry as well and
# are recorded at high risk.
_DESTRUCTIVE_KEYWORDS = frozenset({'DROP', 'DELETE', 'TRUNCATE', 'ALTER', 'REPLACE', 'VACUUM'})


def _sql_risk(sql: str) -> str:
    """Classify a mutating statement's blast radius for the audit ledger."""
    import re as _re

    upper = _re.sub(r"'[^']*'", "''", strip_sql_comments(sql).upper())
    has_where = bool(_re.search(r'\bWHERE\b', upper))

    # Ordered checks, not a set scan: iteration order over a frozenset is not
    # stable, so `DROP TABLE x; ALTER ...` could be graded 'high' on one run and
    # 'critical' on the next. Always test the worst case first.
    if _re.search(r'\b(DROP|TRUNCATE)\b', upper):
        return 'critical'
    # An unqualified DELETE/UPDATE empties the whole table.
    if _re.search(r'\b(DELETE|UPDATE)\b', upper) and not has_where:
        return 'critical'
    for kw in sorted(_DESTRUCTIVE_KEYWORDS):
        if _re.search(rf'\b{kw}\b', upper):
            return 'high'
    return 'medium'


def _sql_tables(sql: str) -> list[str]:
    """Best-effort list of table names referenced after FROM/INTO/TABLE/UPDATE."""
    import re as _re

    cleaned = strip_sql_comments(sql)
    names = _re.findall(
        r'\b(?:FROM|INTO|UPDATE|TABLE|JOIN)\s+["`\[]?([A-Za-z_][A-Za-z0-9_]*)',
        cleaned,
        _re.IGNORECASE,
    )
    seen: list[str] = []
    for n in names:
        if n.upper() in ('IF', 'EXISTS', 'SELECT') or n in seen:
            continue
        seen.append(n)
    return seen[:10]


def audit_sql(
    sql: str,
    *,
    action: str,
    outcome: str,
    risk: str = 'medium',
    detail: str = '',
    extra: dict | None = None,
) -> None:
    """Append a Database Studio statement to the immutable audit chain.

    Best-effort by design: a ledger failure must not silently swallow the user's
    query result, but it must be loud in the logs. It is never allowed to raise
    into the request path.
    """
    try:
        from ..routers.audit_log import append_entry

        meta = {'sql': sql[:2000], 'tables': _sql_tables(sql)}
        if extra:
            meta.update(extra)
        append_entry(
            agent_id='user',
            agent_name='Database Studio',
            action_type=action,
            action_detail=(detail or sql)[:2000],
            reasoning='Statement submitted through the Database Studio SQL editor',
            authority='user',
            risk_level=risk,
            outcome=outcome,
            metadata=meta,
        )
    except Exception as e:  # pragma: no cover - ledger must never break the request
        log.error('AUDIT FAILURE: could not record Database Studio statement: %s', e)


def _dry_run_statement(sql: str, risk: str) -> dict:
    """Run a mutating statement inside a transaction and roll it back.

    Returns the row count the statement WOULD affect. Nothing is committed --
    verified by re-counting the affected tables after the rollback.
    """
    con = _connect()
    con.row_factory = sqlite3.Row
    before = {}
    try:
        tables = _sql_tables(sql)
        for t in tables:
            try:
                before[t] = con.execute(f'SELECT COUNT(*) FROM "{t}"').fetchone()[0]
            except sqlite3.Error:
                pass  # not a real table (CTE alias, or being created)

        con.execute('BEGIN')
        cur = con.execute(sql)
        affected = cur.rowcount
        after = {}
        for t in tables:
            try:
                after[t] = con.execute(f'SELECT COUNT(*) FROM "{t}"').fetchone()[0]
            except sqlite3.Error:
                pass
        con.rollback()

        deltas = {t: after[t] - before[t] for t in after if t in before and after[t] != before[t]}
        audit_sql(
            sql, action='db_sql_dryrun', outcome='success', risk=risk,
            extra={'rows_affected': affected, 'deltas': deltas},
        )
        return {
            'ok': True,
            'dry_run': True,
            'type': 'write',
            'rows_affected': affected,
            'row_count_before': before,
            'row_count_after': after,
            'deltas': deltas,
            'risk': risk,
            'committed': False,
            'message': f'Dry run only -- rolled back. {affected} row(s) would be affected.',
        }
    except Exception as e:
        try:
            con.rollback()
        except sqlite3.Error:
            pass
        audit_sql(sql, action='db_sql_dryrun', outcome='failure', risk=risk, extra={'error': str(e)[:300]})
        return JSONResponse({'ok': False, 'error': str(e), 'dry_run': True}, status_code=400)
    finally:
        con.close()


# ── SQLite Studio ──────────────────────────────────────────────────────────────
@router.get('/sqlite/tables')
def sqlite_tables():
    """List all user-created tables (excluding system tables)."""
    con = _connect()
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
            restricted = db_policy.is_restricted_table(name)
            result.append({
                'name': name,
                'type': t['type'],
                'row_count': count,
                'columns': cols,
                'restricted': restricted,
                'sensitive_columns': [c['name'] for c in cols if db_policy.is_sensitive_column(name, c['name'])],
            })
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
        return JSONResponse({'ok': False, 'error': 'Invalid table name'}, status_code=400)
    if db_policy.is_restricted_table(table):
        reason = (
            f'Table "{table}" holds credential material and is not readable through '
            f'Database Studio. Set AGENTIC_DB_ALLOW_SENSITIVE=1 on the server to override.'
        )
        if not db_policy.sensitive_override_enabled():
            audit_sql(
                f'SELECT * FROM "{table}"', action='db_read_refused', outcome='blocked',
                risk='critical', detail=reason, extra={'table': table},
            )
            return JSONResponse(
                {'ok': False, 'error': reason, 'forbidden': True, 'sensitive': True}, status_code=403
            )

    con = _connect()
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
        out_rows, redacted = db_policy.redact_rows([dict(r) for r in rows], cols, table=table)
        return {
            'ok': True,
            'table': table,
            'columns': cols,
            'rows': out_rows,
            'total': total,
            'limit': limit,
            'offset': offset,
            'redacted_columns': redacted,
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
        return JSONResponse({'ok': False, 'error': 'SQL required'}, status_code=400)

    dry_run = bool(body.get('dry_run', False))

    is_write, refusal = classify_sql(sql)
    if refusal:
        # Refusals are recorded too: a rejected ATTACH or writable_schema attempt
        # is a security signal, and a ledger that only holds successes cannot
        # show that someone tried.
        audit_sql(sql, action='db_sql_refused', outcome='blocked', risk='high', detail=refusal)
        return JSONResponse({'ok': False, 'error': refusal, 'forbidden': True}, status_code=403)

    policy_refusal = _policy_refusal(sql)
    if policy_refusal:
        audit_sql(
            sql, action='db_sql_refused', outcome='blocked', risk='critical', detail=policy_refusal,
            extra={'reason': 'sensitive_data_policy'},
        )
        return JSONResponse(
            {'ok': False, 'error': policy_refusal, 'forbidden': True, 'sensitive': True},
            status_code=403,
        )
    if is_write and not allow_write:
        audit_sql(
            sql,
            action='db_sql_refused',
            outcome='blocked',
            risk='medium',
            detail='Write attempted without allow_write',
        )
        return JSONResponse(
            {
                'ok': False,
                'error': 'Write queries disabled. Set allow_write=true to enable.',
                'is_write': True,
            },
            status_code=403,
        )

    risk = _sql_risk(sql) if is_write else 'low'

    if is_write and dry_run:
        # Execute inside a transaction that is ALWAYS rolled back, so the user
        # can see how many rows a statement would touch before committing it.
        # Every statement here auto-commits, which made a mistyped DELETE
        # instantly permanent with no undo — this is the "show me the row count
        # before I commit" mode that gap called for.
        return _dry_run_statement(sql, risk)

    if is_write and risk == 'critical':
        # Pre-entry: the ledger is append-only, so a statement that never
        # returns would otherwise leave no trace whatsoever.
        audit_sql(sql, action='db_sql_attempt', outcome='pending', risk=risk)

    con = _connect()
    con.row_factory = sqlite3.Row
    try:
        cur = con.execute(sql)
        if is_write:
            con.commit()
            affected = cur.rowcount
            con.close()
            audit_sql(
                sql,
                action='db_sql_write',
                outcome='success',
                risk=risk,
                extra={'rows_affected': affected},
            )
            return {'ok': True, 'rows_affected': affected, 'type': 'write'}
        rows = cur.fetchall()[:1000]
        cols = [d[0] for d in (cur.description or [])]
        con.close()
        # `SELECT *` never names the column, so the statement scan above cannot
        # see it. Mask on the way out as well.
        out_rows, redacted = db_policy.redact_rows(
            [dict(r) for r in rows], cols, table=(_sql_tables(sql) or [''])[0]
        )
        return {
            'ok': True,
            'columns': cols,
            'rows': out_rows,
            'count': len(out_rows),
            'type': 'select',
            'redacted_columns': redacted,
        }
    except Exception as e:
        con.close()
        if is_write:
            audit_sql(sql, action='db_sql_write', outcome='failure', risk=risk, extra={'error': str(e)[:300]})
        return JSONResponse({'ok': False, 'error': str(e)}, status_code=400)


@router.post('/sqlite/table/{table}/insert')
async def sqlite_insert(table: str, req: Request):
    """Insert a row into a table."""
    if not re.match(r'^[a-zA-Z_][a-zA-Z0-9_]*$', table):
        return JSONResponse({'ok': False, 'error': 'Invalid table name'}, status_code=400)
    try:
        body = await req.json()
    except (json.JSONDecodeError, TypeError, ValueError):
        body = {}
    row = body.get('row', {})
    if not row:
        return {'ok': False, 'error': 'row data required'}
    con = _connect()
    try:
        cols = list(row.keys())
        vals = list(row.values())
        placeholders = ', '.join('?' * len(cols))
        col_names = ', '.join(f'"{c}"' for c in cols)
        cur = con.execute(f'INSERT INTO "{table}" ({col_names}) VALUES ({placeholders})', vals)
        con.commit()
        rowid = cur.lastrowid
        con.close()
        audit_sql(
            f'INSERT INTO "{table}" ({col_names}) VALUES (...)',
            action='db_row_insert',
            outcome='success',
            risk='medium',
            detail=f'Insert row into {table}',
            extra={'table': table, 'columns': cols, 'rowid': rowid},
        )
        return {'ok': True, 'rowid': rowid}
    except Exception as e:
        con.close()
        audit_sql(
            f'INSERT INTO "{table}"',
            action='db_row_insert',
            outcome='failure',
            risk='medium',
            detail=f'Insert row into {table}',
            extra={'table': table, 'error': str(e)[:300]},
        )
        return {'ok': False, 'error': str(e)}


@router.delete('/sqlite/table/{table}/row')
async def sqlite_delete_row(table: str, req: Request):
    """Delete rows matching a condition."""
    if not re.match(r'^[a-zA-Z_][a-zA-Z0-9_]*$', table):
        return JSONResponse({'ok': False, 'error': 'Invalid table name'}, status_code=400)
    try:
        body = await req.json()
    except (json.JSONDecodeError, TypeError, ValueError):
        body = {}
    pk = body.get('pk_column', 'id')
    value = body.get('pk_value')
    if value is None:
        return {'ok': False, 'error': 'pk_value required'}
    con = _connect()
    try:
        cur = con.execute(f'DELETE FROM "{table}" WHERE "{pk}"=?', (value,))
        con.commit()
        deleted = cur.rowcount
        con.close()
        audit_sql(
            f'DELETE FROM "{table}" WHERE "{pk}"=?',
            action='db_row_delete',
            outcome='success',
            risk='high',
            detail=f'Delete from {table} where {pk}={value}',
            extra={'table': table, 'pk_column': pk, 'pk_value': str(value)[:200], 'deleted': deleted},
        )
        return {'ok': True, 'deleted': deleted}
    except Exception as e:
        con.close()
        audit_sql(
            f'DELETE FROM "{table}"',
            action='db_row_delete',
            outcome='failure',
            risk='high',
            detail=f'Delete from {table}',
            extra={'table': table, 'error': str(e)[:300]},
        )
        return {'ok': False, 'error': str(e)}


@router.get('/sqlite/schema')
def sqlite_schema():
    """Return the full database schema (CREATE statements)."""
    con = _connect()
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

    # DDL arriving here is frequently LLM-authored (the AI Schema Designer posts
    # straight to this endpoint), so it is subject to the same statement guard
    # as the SQL editor rather than being executed on trust.
    _is_write, refusal = classify_sql(sql)
    if refusal:
        audit_sql(sql, action='db_schema_refused', outcome='blocked', risk='high', detail=refusal)
        return JSONResponse({'ok': False, 'error': refusal, 'forbidden': True}, status_code=403)

    policy_refusal = _policy_refusal(sql)
    if policy_refusal:
        audit_sql(
            sql, action='db_schema_refused', outcome='blocked', risk='critical', detail=policy_refusal,
            extra={'reason': 'sensitive_data_policy'},
        )
        return JSONResponse(
            {'ok': False, 'error': policy_refusal, 'forbidden': True, 'sensitive': True}, status_code=403
        )

    risk = _sql_risk(sql)
    con = _connect()
    try:
        con.execute(sql)
        con.commit()
        audit_sql(sql, action='db_schema_change', outcome='success', risk=risk)
        return {'ok': True, 'sql': sql}
    except Exception as e:
        audit_sql(sql, action='db_schema_change', outcome='failure', risk=risk, extra={'error': str(e)[:300]})
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

    # The model proposes; the server decides. LLM-authored DDL used to be handed
    # to the UI with nothing but a Create Table button next to it. It is now
    # analysed server-side and returned as a REVIEW PLAN so the operator sees
    # what it would do to the live database before anything runs. The same
    # lesson as the Module 16 gitai fix and the Module 14 composer paths.
    plan = _analyse_ddl(sql)
    return {
        'ok': result.get('ok'),
        'sql': sql,
        'description': desc,
        'plan': plan,
        'requires_confirmation': True,
        'safe': plan['safe'],
    }


def _analyse_ddl(sql: str) -> dict:
    """Describe what a DDL statement would do to the live database.

    Reports collisions with existing tables, destructive clauses, and whether
    the statement is refused outright by the guards -- computed from the real
    schema, never from anything the model asserted about its own output.
    """
    import re as _re

    warnings: list[str] = []

    # classify_sql() inspects the LEADING token for forbidden statements, which
    # is correct for the executor (sqlite3.execute() refuses multi-statement
    # input outright) but wrong for a PREVIEW: analysing the whole blob as one
    # string reported `safe: true` for
    #     CREATE TABLE t (k TEXT); ATTACH DATABASE '/tmp/z.db' AS z
    # because ATTACH was not the leading token. Not exploitable — the execution
    # path rejects it with "You can only execute one statement at a time" — but
    # a confirmation screen that says "safe" about SQL the server will refuse is
    # itself a defect. Each statement is classified separately here.
    statements = [s.strip() for s in (sql or '').split(';') if s.strip()]
    refusal = ''
    policy = ''
    if not sql:
        refusal = 'no SQL was generated'
    else:
        for stmt in statements:
            _is_write, r = classify_sql(stmt)
            if r and not refusal:
                refusal = r
            pr = _policy_refusal(stmt)
            if pr and not policy:
                policy = pr
        if len(statements) > 1:
            warnings.append(
                f'{len(statements)} statements were generated. Only one statement can be '
                f'executed at a time — run them individually.'
            )

    creates = [m.upper() for m in _re.findall(
        r'CREATE\s+TABLE\s+(?:IF\s+NOT\s+EXISTS\s+)?["`\[]?([A-Za-z_][A-Za-z0-9_]*)', sql or '', _re.I)]
    drops = _re.findall(
        r'DROP\s+TABLE\s+(?:IF\s+EXISTS\s+)?["`\[]?([A-Za-z_][A-Za-z0-9_]*)', sql or '', _re.I)

    existing: list[str] = []
    collisions: list[str] = []
    try:
        con = _connect()
        try:
            existing = [r[0] for r in con.execute(
                "SELECT name FROM sqlite_master WHERE type='table'").fetchall()]
        finally:
            con.close()
        upper_existing = {e.upper(): e for e in existing}
        collisions = [upper_existing[c] for c in creates if c in upper_existing]
    except Exception as e:  # pragma: no cover - schema read must not break the preview
        warnings.append(f'Could not read the current schema to check for collisions: {e}')

    if collisions:
        warnings.append(
            'These tables ALREADY EXIST and would be affected: ' + ', '.join(collisions)
        )
    if drops:
        warnings.append('This statement DROPS existing tables: ' + ', '.join(drops))
    if refusal:
        warnings.append(f'This statement will be refused: {refusal}')
    if policy:
        warnings.append(f'This statement will be refused: {policy}')
    if not sql:
        warnings.append('The model returned no SQL.')

    return {
        'creates': creates,
        'drops': list(drops),
        'collisions': collisions,
        'statements': len(statements),
        'risk': _sql_risk(sql) if sql else 'low',
        'warnings': warnings,
        'safe': not warnings,
    }


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
                await client.get(f'{url}/rest/v1/', headers=_supabase_headers())
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
        return JSONResponse({'ok': False, 'error': 'Invalid table name'}, status_code=400)

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
