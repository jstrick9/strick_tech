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

import ast
import contextlib
import json
import logging
import re
from pathlib import Path

from fastapi import APIRouter, Request

router = APIRouter(prefix='/api/codeindex', tags=['codeindex'])
log = logging.getLogger('agentic.codeindex')

from backend.config import get_data_dir

from ..services.request_body import json_body_or_error
from ..services.safe_paths import is_within

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
    decorators  TEXT DEFAULT '',
    is_entrypoint INTEGER DEFAULT 0,
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
        # Databases indexed before decorator-awareness lack these columns.
        # Dead-code detection reads them, so add them in place rather than
        # forcing a re-index (old rows simply report no decorators).
        cols = {r[1] for r in con.execute('PRAGMA table_info(code_symbols)').fetchall()}
        if 'decorators' not in cols:
            con.execute("ALTER TABLE code_symbols ADD COLUMN decorators TEXT DEFAULT ''")
        if 'is_entrypoint' not in cols:
            con.execute('ALTER TABLE code_symbols ADD COLUMN is_entrypoint INTEGER DEFAULT 0')
        con.commit()
    finally:
        con.close()


_ensure_schema()


# A symbol reached through a framework/registry rather than a direct call is
# NOT dead code. Deleting a FastAPI route handler because nothing calls it by
# name removes a live endpoint, so these decorators mark a symbol as an entry
# point and exempt it from dead-code reporting.
ENTRYPOINT_DECORATOR_HINTS = (
    'route', 'get', 'post', 'put', 'patch', 'delete', 'head', 'options',
    'websocket', 'middleware', 'exception_handler', 'on_event',
    'fixture', 'task', 'command', 'callback', 'listener', 'subscribe',
    'register', 'hook', 'validator', 'property', 'setter',
    'app', 'cli', 'main', 'schedule', 'cron', 'event', 'errorhandler',
    'before_request', 'after_request', 'receiver', 'step', 'tool',
)


def _decorator_name(node) -> str:
    """Flatten a decorator expression to a dotted name (best effort)."""
    if isinstance(node, ast.Call):
        node = node.func
    parts = []
    while isinstance(node, ast.Attribute):
        parts.append(node.attr)
        node = node.value
    if isinstance(node, ast.Name):
        parts.append(node.id)
    return '.'.join(reversed(parts))


def _is_entrypoint(decorators: list) -> bool:
    """True when any decorator implies the symbol is invoked by a framework."""
    for dec in decorators:
        # Match on the trailing segment so `router.get` and `app.route` both
        # resolve, while a user helper called `getter` does not.
        tail = dec.rsplit('.', 1)[-1].lower()
        if tail in ENTRYPOINT_DECORATOR_HINTS:
            return True
    return False


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
            decs = [_decorator_name(d) for d in node.decorator_list]
            # Annotations are references: a Pydantic model used only as
            # `def f(body: LoginRequest)` is constructed by the framework and
            # was previously reported as dead code.
            _anns = [a.annotation for a in node.args.args if a.annotation]
            if node.returns:
                _anns.append(node.returns)
            for ann in _anns:
                for sub_n in ast.walk(ann):
                    if isinstance(sub_n, ast.Name):
                        calls.append({'from_symbol': node.name, 'to_symbol': sub_n.id, 'line': node.lineno})
                    elif isinstance(sub_n, ast.Attribute):
                        calls.append({'from_symbol': node.name, 'to_symbol': sub_n.attr, 'line': node.lineno})
            for dec in node.decorator_list:
                for sub_n in ast.walk(dec):
                    if isinstance(sub_n, ast.Name):
                        calls.append({'from_symbol': node.name, 'to_symbol': sub_n.id, 'line': node.lineno})
            symbols.append(
                {
                    'name': node.name,
                    'type': 'async_function' if isinstance(node, ast.AsyncFunctionDef) else 'function',
                    'line': node.lineno,
                    'col': node.col_offset,
                    'docstring': doc[:300],
                    'signature': sig[:200],
                    'complexity': _complexity(node),
                    'decorators': [d for d in decs if d],
                    'is_entrypoint': _is_entrypoint(decs),
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
            decs = [_decorator_name(d) for d in node.decorator_list]
            for base in node.bases:
                bname = _decorator_name(base)
                if bname:
                    calls.append(
                        {'from_symbol': node.name, 'to_symbol': bname.rsplit('.', 1)[-1], 'line': node.lineno}
                    )
            symbols.append(
                {
                    'name': node.name,
                    'type': 'class',
                    'line': node.lineno,
                    'col': node.col_offset,
                    'docstring': doc[:300],
                    'signature': f'class {node.name}',
                    'complexity': 1,
                    'decorators': [d for d in decs if d],
                    'is_entrypoint': _is_entrypoint(decs),
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

    # Calls were only collected by walking function bodies, so module-level
    # code was invisible to the call graph. `config = load_config()` at import
    # time is a real reference; without it load_config() looked dead.
    _nested = set()
    for node in ast.walk(tree):
        if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef, ast.ClassDef)):
            for child in ast.walk(node):
                if child is not node:
                    _nested.add(id(child))
    for node in ast.walk(tree):
        if id(node) in _nested:
            continue
        if isinstance(node, ast.Call):
            fn = node.func
            if isinstance(fn, ast.Name):
                calls.append({'from_symbol': '<module>', 'to_symbol': fn.id, 'line': node.lineno})
            elif isinstance(fn, ast.Attribute):
                calls.append({'from_symbol': '<module>', 'to_symbol': fn.attr, 'line': node.lineno})

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
                """INSERT INTO code_symbols(filepath,symbol_name,symbol_type,line_no,col_no,docstring,signature,complexity,decorators,is_entrypoint)
                           VALUES (?,?,?,?,?,?,?,?,?,?)""",
                (
                    rel_path,
                    s['name'],
                    s['type'],
                    s['line'],
                    s.get('col', 0),
                    s.get('docstring', ''),
                    s.get('signature', ''),
                    s.get('complexity', 1),
                    ','.join(s.get('decorators', []))[:300],
                    1 if s.get('is_entrypoint') else 0,
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
    body, _body_err = await json_body_or_error(req)
    if _body_err:
        return _body_err
    base_dir = body.get('directory', '')
    if base_dir:
        # FIX 8: validate directory stays inside project root
        candidate = (ROOT / base_dir).resolve()
        # is_within(): component-wise. str.startswith() accepted sibling
        # directories such as <root>_ESCAPED, which are OUTSIDE the root.
        if is_within(candidate, ROOT):
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
        params.append(max(1, min(limit, 500)))
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


# Names Python or a test runner calls. Never referenced by name in source.
_DUNDER_OR_PROTOCOL = {
    'main', 'setUp', 'tearDown', 'setUpClass', 'tearDownClass',
}


@router.get('/dead-code')
def dead_code_detection(limit: int = 50):
    """Find symbols that are defined but never called or imported.

    Framework entry points are NOT dead code. A FastAPI route handler, a
    pytest fixture or a CLI command is reached through a decorator registry,
    so nothing calls it by name -- the previous implementation reported every
    one of them as deletable. On this repo that was 47 of the first 50 rows
    (route handlers such as `index`, `favicon`, `manifest`), and acting on the
    report would have removed live endpoints.

    Symbols carrying an entry-point decorator are now excluded and counted
    separately, and the response states which heuristics were applied so the
    UI can present a candidate list rather than a verdict.
    """
    from ..services.memory_db import get_conn

    con = get_conn()
    try:
        defined = con.execute(
            """SELECT symbol_name, filepath, symbol_type, is_entrypoint, decorators
                 FROM code_symbols WHERE symbol_type IN ('function','class')"""
        ).fetchall()
        called = set(r['to_symbol'] for r in con.execute('SELECT to_symbol FROM code_calls').fetchall())
        imported = set(r['import_name'] for r in con.execute('SELECT import_name FROM code_imports').fetchall())
    finally:
        con.close()

    referenced = called | imported
    dead = []
    excluded_entrypoints = 0
    for r in defined:
        name = r['symbol_name']
        if name in referenced or name.startswith('_') or len(name) <= 2:
            continue
        if name in _DUNDER_OR_PROTOCOL or r['is_entrypoint']:
            excluded_entrypoints += 1
            continue
        dead.append(
            {
                'symbol_name': name,
                'filepath': r['filepath'],
                'symbol_type': r['symbol_type'],
                'decorators': r['decorators'] or '',
            }
        )

    limit = max(1, min(limit, 500))
    return {
        'dead_symbols': dead[:limit],
        'count': len(dead),
        'returned': len(dead[:limit]),
        'truncated': len(dead) > limit,
        'excluded_entrypoints': excluded_entrypoints,
        'confidence': 'heuristic',
        'note': (
            'Call-graph heuristic: name-based, single-repo. Dynamic dispatch, '
            'getattr(), templates and external importers are not visible to it. '
            f'{excluded_entrypoints} framework entry point(s) were excluded. '
            'Verify before deleting.'
        ),
    }


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
