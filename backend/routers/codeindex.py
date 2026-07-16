"""
Agentic OS — Codebase Semantic Indexer + Dependency Graph
(Augment Code / Windsurf Codemaps / Cursor codebase indexing)

Features:
- AST-based parsing for Python and JavaScript/TypeScript
- Call graph + import graph construction
- Symbol index (functions, classes, variables) with FTS
- D3 force-directed dependency graph data
- Cross-file reference finding
- Complexity metrics (cyclomatic complexity per function)
- Dead code detection (symbols defined but never referenced)
"""

from __future__ import annotations

import contextlib

import ast
import logging
import re
from pathlib import Path

from fastapi import APIRouter, Request

router = APIRouter(prefix='/api/codeindex', tags=['codeindex'])
log = logging.getLogger('agentic.codeindex')

from backend.config import get_data_dir
ROOT = get_data_dir()
PREVIEW_DIR = ROOT / 'preview'

# ── DB schema ──────────────────────────────────────────────────────────────────
_SCHEMA = """
CREATE TABLE IF NOT EXISTS code_symbols (
    id          INTEGER PRIMARY KEY AUTOINCREMENT,
    filepath    TEXT NOT NULL,
    symbol_name TEXT NOT NULL,
    symbol_type TEXT NOT NULL,
    line_no     INTEGER DEFAULT 0,
    col_no      INTEGER DEFAULT 0,
    docstring   TEXT DEFAULT '',
    signature   TEXT DEFAULT '',
    complexity  INTEGER DEFAULT 1,
    indexed_at  TIMESTAMP DEFAULT CURRENT_TIMESTAMP
);
CREATE TABLE IF NOT EXISTS code_imports (
    id          INTEGER PRIMARY KEY AUTOINCREMENT,
    from_file   TEXT NOT NULL,
    to_module   TEXT NOT NULL,
    import_name TEXT DEFAULT '',
    line_no     INTEGER DEFAULT 0
);
CREATE TABLE IF NOT EXISTS code_calls (
    id          INTEGER PRIMARY KEY AUTOINCREMENT,
    from_file   TEXT NOT NULL,
    from_symbol TEXT NOT NULL,
    to_symbol   TEXT NOT NULL,
    line_no     INTEGER DEFAULT 0
);
CREATE VIRTUAL TABLE IF NOT EXISTS code_symbols_fts
    USING fts5(symbol_name, docstring, filepath, content='code_symbols', content_rowid='id');
CREATE INDEX IF NOT EXISTS idx_cs_file    ON code_symbols(filepath);
CREATE INDEX IF NOT EXISTS idx_cs_symbol  ON code_symbols(symbol_name);
CREATE INDEX IF NOT EXISTS idx_ci_from    ON code_imports(from_file);
CREATE INDEX IF NOT EXISTS idx_cc_from    ON code_calls(from_file, from_symbol);
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


# ── Python AST parser ─────────────────────────────────────────────────────────
def _parse_python(filepath: str, content: str) -> dict:
    symbols = []
    imports = []
    calls = []

    try:
        tree = ast.parse(content, filename=filepath)
    except SyntaxError:
        return {'symbols': symbols, 'imports': imports, 'calls': calls}

    def _complexity(node) -> int:
        """Approximate cyclomatic complexity."""
        branches = sum(
            1
            for n in ast.walk(node)
            if isinstance(n, (ast.If, ast.While, ast.For, ast.ExceptHandler, ast.With, ast.Assert, ast.comprehension))
        )
        return 1 + branches

    for node in ast.walk(tree):
        if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef)):
            doc = ast.get_docstring(node) or ''
            args = [a.arg for a in node.args.args]
            sig = f'def {node.name}({", ".join(args)})'
            symbols.append(
                {
                    'name': node.name,
                    'type': 'async_function' if isinstance(node, ast.AsyncFunctionDef) else 'function',
                    'line': node.lineno,
                    'col': node.col_offset,
                    'docstring': doc[:300],
                    'signature': sig[:200],
                    'complexity': _complexity(node),
                }
            )
            # Find calls inside this function
            for child in ast.walk(node):
                if isinstance(child, ast.Call):
                    fn = child.func
                    if isinstance(fn, ast.Name):
                        calls.append({'from_symbol': node.name, 'to_symbol': fn.id, 'line': child.lineno})
                    elif isinstance(fn, ast.Attribute):
                        calls.append({'from_symbol': node.name, 'to_symbol': fn.attr, 'line': child.lineno})

        elif isinstance(node, ast.ClassDef):
            doc = ast.get_docstring(node) or ''
            symbols.append(
                {
                    'name': node.name,
                    'type': 'class',
                    'line': node.lineno,
                    'col': node.col_offset,
                    'docstring': doc[:300],
                    'signature': f'class {node.name}',
                    'complexity': 1,
                }
            )

        elif isinstance(node, (ast.Import, ast.ImportFrom)):
            if isinstance(node, ast.Import):
                for alias in node.names:
                    imports.append({'to_module': alias.name, 'import_name': alias.name, 'line': node.lineno})
            else:
                mod = node.module or ''
                for alias in node.names:
                    imports.append({'to_module': mod, 'import_name': alias.name or '*', 'line': node.lineno})

    return {'symbols': symbols, 'imports': imports, 'calls': calls}


# ── JS/TS parser (regex-based) ────────────────────────────────────────────────
def _parse_js(filepath: str, content: str) -> dict:
    symbols = []
    imports = []
    calls = []

    lines = content.split('\n')

    # Function declarations
    fn_patterns = [
        r'(?:export\s+)?(?:async\s+)?function\s+(\w+)\s*\(',
        r'(?:const|let|var)\s+(\w+)\s*=\s*(?:async\s+)?\(',
        r'(?:const|let|var)\s+(\w+)\s*=\s*(?:async\s+)?function',
        r'(\w+)\s*:\s*(?:async\s+)?\(',
    ]
    for i, line in enumerate(lines, 1):
        for pat in fn_patterns:
            m = re.search(pat, line)
            if m:
                symbols.append(
                    {
                        'name': m.group(1),
                        'type': 'function',
                        'line': i,
                        'col': 0,
                        'docstring': '',
                        'signature': line.strip()[:120],
                        'complexity': 1,
                    }
                )
                break
        # Classes
        m = re.search(r'class\s+(\w+)', line)
        if m:
            symbols.append(
                {
                    'name': m.group(1),
                    'type': 'class',
                    'line': i,
                    'col': 0,
                    'docstring': '',
                    'signature': line.strip()[:120],
                    'complexity': 1,
                }
            )

    # Imports
    for i, line in enumerate(lines, 1):
        m = re.search(r"import\s+.*?\s+from\s+['\"](.+?)['\"]", line)
        if m:
            imports.append({'to_module': m.group(1), 'import_name': '*', 'line': i})
        m2 = re.search(r"require\(['\"](.+?)['\"]\)", line)
        if m2:
            imports.append({'to_module': m2.group(1), 'import_name': 'require', 'line': i})

    return {'symbols': symbols, 'imports': imports, 'calls': calls}


def _parse_file(filepath: str, content: str) -> dict:
    ext = Path(filepath).suffix.lower()
    if ext == '.py':
        return _parse_python(filepath, content)
    elif ext in ('.js', '.ts', '.jsx', '.tsx', '.mjs', '.cjs'):
        return _parse_js(filepath, content)
    return {'symbols': [], 'imports': [], 'calls': []}


# ── Indexing ──────────────────────────────────────────────────────────────────
def _index_file(filepath: str, content: str):
    """Parse a file and store its symbols/imports in SQLite."""
    rel_path = filepath
    parsed = _parse_file(rel_path, content)

    from ..services.memory_db import get_conn

    con = get_conn()
    try:
        # Remove old entries
        con.execute('DELETE FROM code_symbols WHERE filepath=?', (rel_path,))
        con.execute('DELETE FROM code_imports  WHERE from_file=?', (rel_path,))
        con.execute('DELETE FROM code_calls    WHERE from_file=?', (rel_path,))
        for s in parsed['symbols']:
            con.execute(
                """INSERT INTO code_symbols(filepath,symbol_name,symbol_type,line_no,col_no,docstring,signature,complexity)
                           VALUES (?,?,?,?,?,?,?,?)""",
                (
                    rel_path,
                    s['name'],
                    s['type'],
                    s['line'],
                    s.get('col', 0),
                    s.get('docstring', ''),
                    s.get('signature', ''),
                    s.get('complexity', 1),
                ),
            )
        for imp in parsed['imports']:
            con.execute(
                'INSERT INTO code_imports(from_file,to_module,import_name,line_no) VALUES (?,?,?,?)',
                (rel_path, imp['to_module'], imp.get('import_name', ''), imp.get('line', 0)),
            )
        for call in parsed['calls']:
            con.execute(
                'INSERT INTO code_calls(from_file,from_symbol,to_symbol,line_no) VALUES (?,?,?,?)',
                (rel_path, call['from_symbol'], call['to_symbol'], call.get('line', 0)),
            )
        # Rebuild FTS5 content table
        with contextlib.suppress(Exception):
            con.execute("INSERT INTO code_symbols_fts(code_symbols_fts) VALUES ('rebuild')")
        con.commit()
    finally:
        con.close()
    return len(parsed['symbols'])


# ── Endpoints ─────────────────────────────────────────────────────────────────
@router.post('/index')
async def index_directory(req: Request):
    """Index all Python/JS/TS files in preview/ or a given directory."""
    try:
        body = await req.json()
    except (json.JSONDecodeError, TypeError, ValueError):
        body = {}
    base_dir = body.get('directory', '')
    if base_dir:
        # FIX 8: validate directory stays inside project root
        candidate = (ROOT / base_dir).resolve()
        if str(candidate).startswith(str(ROOT.resolve())):
            target = candidate
        else:
            return {'ok': False, 'error': 'Directory outside project root is not allowed'}
    else:
        target = PREVIEW_DIR
    if not target.exists():
        target = PREVIEW_DIR

    EXTS = {'.py', '.js', '.ts', '.jsx', '.tsx', '.mjs'}
    indexed = 0
    symbols = 0
    errors = 0

    for f in target.rglob('*'):
        if not f.is_file() or f.suffix.lower() not in EXTS:
            continue
        if any(p in str(f) for p in ['node_modules', '__pycache__', '.git', 'venv', '.venv']):
            continue
        try:
            content = f.read_text(encoding='utf-8', errors='ignore')
            rel = str(f.relative_to(ROOT))
            sym_cnt = _index_file(rel, content)
            symbols += sym_cnt
            indexed += 1
        except Exception as ex:
            errors += 1
            log.warning('Index error %s: %s', f, ex)

    # Also index backend if requested
    if body.get('include_backend', False):
        for f in (ROOT / 'backend').rglob('*.py'):
            if '__pycache__' in str(f):
                continue
            try:
                content = f.read_text(encoding='utf-8', errors='ignore')
                rel = str(f.relative_to(ROOT))
                symbols += _index_file(rel, content)
                indexed += 1
            except (KeyError, TypeError, ValueError, json.JSONDecodeError, OSError, AttributeError, RuntimeError):
                errors += 1

    return {'ok': True, 'indexed_files': indexed, 'symbols_found': symbols, 'errors': errors}


@router.get('/symbols')
def search_symbols(q: str = '', file: str = '', type: str = '', limit: int = 50):
    """Search symbols by name, file, or type."""
    from ..services.memory_db import get_conn

    con = get_conn()
    try:
        where, params = [], []
        if file:
            where.append('filepath LIKE ?')
            params.append(f'%{file}%')
        if type:
            where.append('symbol_type=?')
            params.append(type)
        if q:
            where.append('symbol_name LIKE ?')
            params.append(f'%{q}%')
        sql = 'SELECT * FROM code_symbols'
        if where:
            sql += ' WHERE ' + ' AND '.join(where)
        sql += ' ORDER BY symbol_name LIMIT ?'
        params.append(min(limit, 500))
        rows = con.execute(sql, params).fetchall()
        count_params = params[:-1]  # exclude LIMIT
        count_where = ' WHERE ' + ' AND '.join(where) if where else ''
        total = con.execute(f'SELECT COUNT(*) FROM code_symbols{count_where}', count_params).fetchone()[0]
    finally:
        con.close()
    return {'symbols': [dict(r) for r in rows], 'count': len(rows), 'total': total}


@router.get('/graph')
def dependency_graph(limit: int = 200):
    """Return D3 force-graph data: nodes (files) + edges (imports)."""
    from ..services.memory_db import get_conn

    con = get_conn()
    try:
        files = con.execute(
            'SELECT filepath, COUNT(*) as sym_count FROM code_symbols GROUP BY filepath ORDER BY sym_count DESC LIMIT ?',
            (limit,),
        ).fetchall()
        imports = con.execute('SELECT from_file, to_module FROM code_imports LIMIT ?', (limit * 5,)).fetchall()
    finally:
        con.close()

    # Build node set
    file_set = {r['filepath'] for r in files}
    nodes = [
        {'id': r['filepath'], 'name': Path(r['filepath']).name, 'size': r['sym_count'], 'type': 'file'} for r in files
    ]

    # Build edges
    edges = []
    seen_edges: set[tuple] = set()
    for imp in imports:
        src = imp['from_file']
        mod = imp['to_module']
        if src not in file_set:
            continue
        # Try to resolve module to a file
        target = None
        for fp in file_set:
            fp_name = Path(fp).stem
            if fp_name == mod or fp.endswith(mod.replace('.', '/') + '.py') or fp.endswith(mod + '.py'):
                target = fp
                break
        if target and (src, target) not in seen_edges:
            edges.append({'source': src, 'target': target, 'type': 'import'})
            seen_edges.add((src, target))

    return {'nodes': nodes, 'edges': edges, 'node_count': len(nodes), 'edge_count': len(edges)}


@router.get('/file/{filepath:path}')
def file_symbols(filepath: str):
    """Get all symbols for a specific file."""
    from ..services.memory_db import get_conn

    con = get_conn()
    try:
        symbols = con.execute(
            'SELECT * FROM code_symbols WHERE filepath LIKE ? ORDER BY line_no', (f'%{filepath}%',)
        ).fetchall()
        imports = con.execute(
            'SELECT * FROM code_imports WHERE from_file LIKE ? ORDER BY line_no', (f'%{filepath}%',)
        ).fetchall()
        calls = con.execute(
            'SELECT * FROM code_calls WHERE from_file LIKE ? ORDER BY line_no', (f'%{filepath}%',)
        ).fetchall()
    finally:
        con.close()
    return {
        'filepath': filepath,
        'symbols': [dict(r) for r in symbols],
        'imports': [dict(r) for r in imports],
        'calls': [dict(r) for r in calls],
    }


@router.get('/references/{symbol_name}')
def find_references(symbol_name: str):
    """Find all files that reference a symbol (where it's called or imported)."""
    from ..services.memory_db import get_conn

    con = get_conn()
    try:
        calls = con.execute(
            'SELECT * FROM code_calls WHERE to_symbol=? ORDER BY from_file,line_no', (symbol_name,)
        ).fetchall()
        defined = con.execute('SELECT * FROM code_symbols WHERE symbol_name=?', (symbol_name,)).fetchall()
    finally:
        con.close()
    return {
        'symbol': symbol_name,
        'defined_in': [dict(r) for r in defined],
        'called_in': [dict(r) for r in calls],
        'ref_count': len(calls),
    }


@router.get('/complexity')
def complexity_report(min_complexity: int = 5, limit: int = 30):
    """Find functions with high cyclomatic complexity."""
    from ..services.memory_db import get_conn

    con = get_conn()
    try:
        rows = con.execute(
            "SELECT * FROM code_symbols WHERE complexity>=? AND symbol_type IN ('function','async_function') ORDER BY complexity DESC LIMIT ?",
            (min_complexity, limit),
        ).fetchall()
    finally:
        con.close()
    return {
        'hotspots': [dict(r) for r in rows],
        'count': len(rows),
        'threshold': min_complexity,
    }


@router.get('/dead-code')
def dead_code_detection():
    """Find symbols that are defined but never called or imported."""
    from ..services.memory_db import get_conn

    con = get_conn()
    try:
        # Get all defined symbols
        defined = con.execute(
            "SELECT symbol_name, filepath FROM code_symbols WHERE symbol_type IN ('function','class')"
        ).fetchall()
        # Get all referenced symbols
        called = set(r['to_symbol'] for r in con.execute('SELECT to_symbol FROM code_calls').fetchall())
        imported = set(r['import_name'] for r in con.execute('SELECT import_name FROM code_imports').fetchall())
    finally:
        con.close()

    referenced = called | imported
    dead = [
        {'symbol_name': r['symbol_name'], 'filepath': r['filepath']}
        for r in defined
        if r['symbol_name'] not in referenced
        and not r['symbol_name'].startswith('_')  # ignore private
        and len(r['symbol_name']) > 2
    ]

    return {'dead_symbols': dead[:50], 'count': len(dead)}


@router.get('/stats')
def index_stats():
    """Overall index statistics."""
    from ..services.memory_db import get_conn

    con = get_conn()
    try:
        total_files = con.execute('SELECT COUNT(DISTINCT filepath) FROM code_symbols').fetchone()[0]
        total_symbols = con.execute('SELECT COUNT(*) FROM code_symbols').fetchone()[0]
        total_imports = con.execute('SELECT COUNT(*) FROM code_imports').fetchone()[0]
        total_calls = con.execute('SELECT COUNT(*) FROM code_calls').fetchone()[0]
        by_type = con.execute('SELECT symbol_type, COUNT(*) as cnt FROM code_symbols GROUP BY symbol_type').fetchall()
        avg_complexity = con.execute(
            "SELECT AVG(complexity) FROM code_symbols WHERE symbol_type='function'"
        ).fetchone()[0]
    finally:
        con.close()
    return {
        'total_files': total_files,
        'total_symbols': total_symbols,
        'total_imports': total_imports,
        'total_calls': total_calls,
        'by_type': {r['symbol_type']: r['cnt'] for r in by_type},
        'avg_complexity': round(avg_complexity or 0, 2),
    }


@router.delete('/clear')
def clear_index():
    """Clear the entire codebase index."""
    from ..services.memory_db import get_conn

    con = get_conn()
    try:
        con.execute('DELETE FROM code_symbols')
        con.execute('DELETE FROM code_imports')
        con.execute('DELETE FROM code_calls')
        con.commit()
    finally:
        con.close()
    return {'ok': True, 'cleared': True}
