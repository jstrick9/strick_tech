"""
Agentic OS — Ambient Always-On Agent + Project Health Dashboard

Ambient Agent: Background watcher that proactively suggests improvements,
notices stale TODOs, catches drift, monitors for issues — without being asked.

Project Health: Tech debt score, complexity metrics, security score,
test coverage estimate, dependency health, documentation score.

Background Agent Triggers: Fire agents from webhooks/API calls,
results delivered via notifications when complete.
"""

from __future__ import annotations

import contextlib

import asyncio
import json
import logging
import re
from pathlib import Path

from fastapi import APIRouter, Request

router = APIRouter(prefix='/api/ambient', tags=['ambient'])
log = logging.getLogger('agentic.ambient')

from backend.config import get_data_dir
ROOT = get_data_dir()
PREVIEW_DIR = ROOT / 'preview'

_SCHEMA = """
CREATE TABLE IF NOT EXISTS ambient_suggestions (
    id          INTEGER PRIMARY KEY AUTOINCREMENT,
    category    TEXT DEFAULT 'general',
    title       TEXT NOT NULL,
    description TEXT DEFAULT '',
    file_path   TEXT DEFAULT '',
    line_no     INTEGER DEFAULT 0,
    severity    TEXT DEFAULT 'info',
    action_type TEXT DEFAULT 'suggestion',
    action_data TEXT DEFAULT '{}',
    dismissed   INTEGER DEFAULT 0,
    created_at  TIMESTAMP DEFAULT CURRENT_TIMESTAMP
);
CREATE TABLE IF NOT EXISTS health_snapshots (
    id              INTEGER PRIMARY KEY AUTOINCREMENT,
    overall_score   INTEGER DEFAULT 0,
    complexity_score INTEGER DEFAULT 0,
    security_score  INTEGER DEFAULT 0,
    debt_score      INTEGER DEFAULT 0,
    docs_score      INTEGER DEFAULT 0,
    deps_score      INTEGER DEFAULT 0,
    details_json    TEXT DEFAULT '{}',
    created_at      TIMESTAMP DEFAULT CURRENT_TIMESTAMP
);
CREATE TABLE IF NOT EXISTS background_tasks (
    id          TEXT PRIMARY KEY,
    name        TEXT NOT NULL,
    prompt      TEXT NOT NULL,
    agent_id    TEXT DEFAULT 'builder',
    status      TEXT DEFAULT 'pending',
    result      TEXT DEFAULT '',
    trigger_src TEXT DEFAULT 'api',
    created_at  TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    completed_at TIMESTAMP
);
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


# ══════════════════════════════════════════════════════════════════
#  AMBIENT AGENT
# ══════════════════════════════════════════════════════════════════


@router.post('/scan')
async def ambient_scan(req: Request):
    """
    Ambient scan: analyze recent file changes, chat history, and codebase
    to proactively surface suggestions — without being asked.
    """
    try:
        body = await req.json()
    except (json.JSONDecodeError, TypeError, ValueError):
        body = {}
    deep = body.get('deep', False)
    max_files = min(int(body.get('max_files', 20)), 200)  # cap at 200 files

    suggestions: list[dict] = []

    # 1. Scan preview files for TODOs/FIXMEs
    todo_pattern = re.compile(r'(TODO|FIXME|HACK|BUG|XXX|TEMP|DEPRECATED)\s*:?\s*(.{0,120})', re.IGNORECASE)
    _CODE_EXTS = {'.py', '.js', '.ts', '.html', '.jsx', '.tsx'}
    if PREVIEW_DIR.exists():
        _code_files = [f for f in PREVIEW_DIR.rglob('*') if f.is_file() and f.suffix in _CODE_EXTS]
        for f in _code_files[:max_files]:
            try:
                content = f.read_text(errors='ignore')
                for m in todo_pattern.finditer(content):
                    line_no = content[: m.start()].count('\n') + 1
                    tag = m.group(1).upper()
                    msg = m.group(2).strip()
                    sev = 'high' if tag in ('BUG', 'FIXME') else 'medium' if tag == 'HACK' else 'info'
                    suggestions.append(
                        {
                            'category': 'todo',
                            'title': f'{tag}: {msg[:60]}',
                            'description': f'Found {tag} comment at line {line_no}',
                            'file_path': str(f.relative_to(ROOT)),
                            'line_no': line_no,
                            'severity': sev,
                            'action_type': 'review',
                        }
                    )
            except (KeyError, TypeError, ValueError, json.JSONDecodeError, OSError, AttributeError, RuntimeError):
                pass

    # 2. Check for large files (>500 lines = tech debt risk)
    if PREVIEW_DIR.exists():
        _py_files = [f for f in PREVIEW_DIR.rglob('*.py') if f.is_file()]
        for f in _py_files[:max_files]:
            try:
                lines = f.read_text(errors='ignore').count('\n')
                if lines > 300:
                    suggestions.append(
                        {
                            'category': 'complexity',
                            'title': f'Large file: {f.name} ({lines} lines)',
                            'description': 'Files over 300 lines should be split into modules',
                            'file_path': str(f.relative_to(ROOT)),
                            'severity': 'medium',
                            'action_type': 'refactor',
                        }
                    )
            except (KeyError, TypeError, ValueError, json.JSONDecodeError, OSError, AttributeError, RuntimeError):
                pass

    # 3. Check for missing error handling patterns
    if deep and PREVIEW_DIR.exists():
        no_try_pattern = re.compile(r'await\s+\w+\(', re.MULTILINE)
        _py_files_deep = [f for f in PREVIEW_DIR.rglob('*.py') if f.is_file()]
        for f in _py_files_deep[:10]:
            try:
                content = f.read_text(errors='ignore')
                awaits = len(no_try_pattern.findall(content))
                tries = content.count('try:')
                if awaits > 5 and tries == 0:
                    suggestions.append(
                        {
                            'category': 'error_handling',
                            'title': f'No try/except in {f.name} ({awaits} await calls)',
                            'description': 'Async calls without error handling can cause silent failures',
                            'file_path': str(f.relative_to(ROOT)),
                            'severity': 'medium',
                            'action_type': 'add_error_handling',
                        }
                    )
            except (KeyError, TypeError, ValueError, json.JSONDecodeError, OSError, AttributeError, RuntimeError):
                pass

    # 4. Check for hardcoded secrets patterns
    secret_patterns = [
        (r'(?i)(api_key|apikey|secret|password|token)\s*=\s*["\'][^"\']{8,}["\']', 'Possible hardcoded secret'),
        (r'(?i)sk-[a-zA-Z0-9]{20,}', 'Possible OpenAI key'),
        (r'(?i)gh[pousr]_[A-Za-z0-9]{36}', 'Possible GitHub token'),
    ]
    if PREVIEW_DIR.exists():
        _BINARY_EXTS = {'.png', '.jpg', '.gif', '.ico', '.svg', '.woff', '.woff2', '.ttf', '.eot', '.mp4', '.webp'}
        _text_files = [f for f in PREVIEW_DIR.rglob('*') if f.is_file() and f.suffix not in _BINARY_EXTS]
        for f in _text_files[:max_files]:
            try:
                content = f.read_text(errors='ignore')
                for pat, label in secret_patterns:
                    m = re.search(pat, content)
                    if m:
                        line_no = content[: m.start()].count('\n') + 1
                        suggestions.append(
                            {
                                'category': 'security',
                                'title': f'🔒 {label} in {f.name}',
                                'description': 'Move secrets to environment variables or the secrets vault',
                                'file_path': str(f.relative_to(ROOT)),
                                'line_no': line_no,
                                'severity': 'high',
                                'action_type': 'security_fix',
                            }
                        )
                        break
            except (KeyError, TypeError, ValueError, json.JSONDecodeError, OSError, AttributeError, RuntimeError):
                pass

    # 5. Check for stale chat sessions (unused agents)
    from ..services.memory_db import get_conn

    con = get_conn()
    try:
        stale = con.execute(
            "SELECT name,status FROM agents WHERE status='idle' AND updated_at < datetime('now','-7 days') LIMIT 5"
        ).fetchall()
        for ag in stale:
            suggestions.append(
                {
                    'category': 'maintenance',
                    'title': f'Idle agent: {ag["name"]}',
                    'description': "This agent hasn't been used in 7+ days — consider archiving or reassigning",
                    'severity': 'info',
                    'action_type': 'archive_agent',
                    'action_data': json.dumps({'agent_name': ag['name']}),
                }
            )
    except (KeyError, TypeError, ValueError, json.JSONDecodeError, OSError, AttributeError, RuntimeError):
        pass
    finally:
        con.close()

    # Save suggestions to DB
    con = get_conn()
    saved = 0
    try:
        for s in suggestions[:50]:  # cap at 50 per scan
            try:
                con.execute(
                    """INSERT INTO ambient_suggestions
                               (category,title,description,file_path,line_no,severity,action_type,action_data)
                               VALUES (?,?,?,?,?,?,?,?)""",
                    (
                        s['category'],
                        s['title'][:200],
                        s.get('description', '')[:500],
                        s.get('file_path', ''),
                        s.get('line_no', 0),
                        s.get('severity', 'info'),
                        s.get('action_type', 'suggestion'),
                        s.get('action_data', '{}'),
                    ),
                )
                saved += 1
            except (KeyError, TypeError, ValueError, json.JSONDecodeError, OSError, AttributeError, RuntimeError):
                pass
        con.commit()
    finally:
        con.close()

    return {
        'ok': True,
        'suggestions': suggestions,
        'count': len(suggestions),
        'saved': saved,
        'categories': list({s['category'] for s in suggestions}),
    }


@router.get('/suggestions')
def get_suggestions(dismissed: bool = False, severity: str = '', limit: int = 50):
    """Retrieve and return get suggestions."""
    from ..services.memory_db import get_conn

    con = get_conn()
    try:
        where, params = ['dismissed=?'], [1 if dismissed else 0]
        if severity:
            where.append('severity=?')
            params.append(severity)
        sql = f"SELECT * FROM ambient_suggestions WHERE {' AND '.join(where)} ORDER BY CASE severity WHEN 'high' THEN 0 WHEN 'medium' THEN 1 ELSE 2 END, created_at DESC LIMIT ?"
        params.append(min(limit, 200))
        rows = con.execute(sql, params).fetchall()
    finally:
        con.close()
    return {'suggestions': [dict(r) for r in rows], 'count': len(rows)}


@router.post('/suggestions/{suggestion_id}/dismiss')
def dismiss_suggestion(suggestion_id: int):
    """Execute or process dismiss suggestion operation."""
    from ..services.memory_db import get_conn

    con = get_conn()
    try:
        con.execute('UPDATE ambient_suggestions SET dismissed=1 WHERE id=?', (suggestion_id,))
        con.commit()
    finally:
        con.close()
    return {'ok': True}


@router.delete('/suggestions/clear')
def clear_suggestions():
    """Delete or remove specified clear suggestions."""
    from ..services.memory_db import get_conn

    con = get_conn()
    try:
        con.execute('DELETE FROM ambient_suggestions')
        con.commit()
    finally:
        con.close()
    return {'ok': True}


# ══════════════════════════════════════════════════════════════════
#  PROJECT HEALTH DASHBOARD
# ══════════════════════════════════════════════════════════════════


@router.get('/health')
async def project_health():
    """
    Compute a comprehensive project health score.
    Returns scores across 5 dimensions: complexity, security, debt, docs, deps.
    """
    from ..services.memory_db import get_conn

    scores = {}
    details: dict[str, list] = {}

    # ── 1. Complexity Score (from code index) ─────────────────────────────────
    try:
        con = get_conn()
        try:
            total_syms = con.execute('SELECT COUNT(*) FROM code_symbols').fetchone()[0]
            high_complex = con.execute('SELECT COUNT(*) FROM code_symbols WHERE complexity>=8').fetchone()[0]
            avg_complex = (
                con.execute("SELECT AVG(complexity) FROM code_symbols WHERE symbol_type='function'").fetchone()[0] or 1
            )
        finally:
            con.close()
        if total_syms > 0:
            complexity_score = max(0, 100 - int(high_complex / total_syms * 200) - int((avg_complex - 1) * 5))
        else:
            complexity_score = 70
        scores['complexity'] = min(100, max(0, complexity_score))
        details['complexity'] = [
            f'{total_syms} total symbols',
            f'{high_complex} high-complexity functions (CC≥8)',
            f'Avg complexity: {round(avg_complex, 1)}',
        ]
    except (KeyError, TypeError, ValueError, json.JSONDecodeError, OSError, AttributeError, RuntimeError):
        scores['complexity'] = 70
        details['complexity'] = ['Index codebase for complexity analysis']

    # ── 2. Security Score ─────────────────────────────────────────────────────
    security_issues = 0
    sec_details = []
    if PREVIEW_DIR.exists():
        secret_pattern = re.compile(r'(?i)(api_key|apikey|secret|password|token)\s*=\s*["\'][^"\']{8,}["\']')
        sql_injection = re.compile(r'(?i)f["\'].*(SELECT|INSERT|UPDATE|DELETE).*{', re.DOTALL)
        xss_pattern = re.compile(r'innerHTML\s*=\s*[^;]+\+')

        for f in list(PREVIEW_DIR.rglob('*'))[:50]:
            if not f.is_file() or f.suffix in ('.png', '.jpg', '.gif', '.ico'):
                continue
            try:
                content = f.read_text(errors='ignore')
                if secret_pattern.search(content):
                    security_issues += 3
                    sec_details.append(f'⚠️ Possible secret in {f.name}')
                if sql_injection.search(content):
                    security_issues += 5
                    sec_details.append(f'🚨 Possible SQL injection in {f.name}')
                if xss_pattern.search(content):
                    security_issues += 2
                    sec_details.append(f'⚡ Possible XSS in {f.name}')
            except (KeyError, TypeError, ValueError, json.JSONDecodeError, OSError, AttributeError, RuntimeError):
                pass

    scores['security'] = max(0, 100 - security_issues * 5)
    details['security'] = sec_details or ['No obvious security issues found']

    # ── 3. Tech Debt Score (TODOs, large files, dead code) ────────────────────
    debt = 0
    debt_details = []
    if PREVIEW_DIR.exists():
        todo_count = 0
        large_count = 0
        for f in list(PREVIEW_DIR.rglob('*'))[:50]:
            if not f.is_file() or f.suffix not in ('.py', '.js', '.ts'):
                continue
            try:
                content = f.read_text(errors='ignore')
                tc = len(re.findall(r'(?i)\b(TODO|FIXME|HACK|BUG)\b', content))
                todo_count += tc
                if content.count('\n') > 300:
                    large_count += 1
            except (KeyError, TypeError, ValueError, json.JSONDecodeError, OSError, AttributeError, RuntimeError):
                pass
        debt = todo_count * 2 + large_count * 5
        debt_details = [
            f'{todo_count} TODO/FIXME/HACK/BUG comments',
            f'{large_count} files over 300 lines',
        ]

    # Dead code from index
    try:
        con = get_conn()
        try:
            dead_count = con.execute(
                "SELECT COUNT(*) FROM code_symbols s WHERE symbol_type='function' AND symbol_name NOT IN (SELECT to_symbol FROM code_calls)"
            ).fetchone()[0]
        finally:
            con.close()
        if dead_count > 0:
            debt += dead_count
            debt_details.append(f'{dead_count} potentially dead functions')
    except (KeyError, TypeError, ValueError, json.JSONDecodeError, OSError, AttributeError, RuntimeError):
        pass

    scores['debt'] = max(0, 100 - min(debt, 100))
    details['debt'] = debt_details or ['No tech debt issues found']

    # ── 4. Documentation Score ────────────────────────────────────────────────
    try:
        con = get_conn()
        try:
            total_fns = con.execute("SELECT COUNT(*) FROM code_symbols WHERE symbol_type='function'").fetchone()[0]
            with_docs = con.execute(
                "SELECT COUNT(*) FROM code_symbols WHERE symbol_type='function' AND length(docstring)>10"
            ).fetchone()[0]
        finally:
            con.close()
        if total_fns > 0:
            doc_pct = int(with_docs / total_fns * 100)
        else:
            doc_pct = 50
        scores['docs'] = doc_pct
        details['docs'] = [
            f'{with_docs}/{total_fns} functions have docstrings ({doc_pct}%)',
            f'{"✅ Good coverage" if doc_pct > 70 else "⚠️ Consider adding more docstrings" if doc_pct > 30 else "❌ Missing documentation"}',
        ]
    except (KeyError, TypeError, ValueError, json.JSONDecodeError, OSError, AttributeError, RuntimeError):
        scores['docs'] = 50
        details['docs'] = ['Index codebase for documentation analysis']

    # ── 5. Dependency Health ─────────────────────────────────────────────────
    dep_issues = []
    req_file = ROOT / 'requirements.txt'
    pkg_file = ROOT / 'package.json'

    if req_file.exists():
        content = req_file.read_text()
        pinned = len(re.findall(r'==', content))
        unpinned = len(re.findall(r'^[a-zA-Z]', content, re.MULTILINE)) - pinned - content.count('#')
        if unpinned > 0:
            dep_issues.append(f'⚠️ {unpinned} unpinned Python dependencies')
        dep_issues.append(f'✅ {pinned} pinned Python packages')

    if pkg_file.exists():
        try:
            pkg = json.loads(pkg_file.read_text())
            deps = len(pkg.get('dependencies', {})) + len(pkg.get('devDependencies', {}))
            dep_issues.append(f'📦 {deps} npm packages')
        except (KeyError, TypeError, ValueError, json.JSONDecodeError, OSError, AttributeError, RuntimeError):
            pass

    scores['deps'] = max(50, 100 - len([d for d in dep_issues if '⚠️' in d]) * 15)
    details['deps'] = dep_issues or ['No package files found']

    # ── Overall Score ─────────────────────────────────────────────────────────
    weights = {'complexity': 0.25, 'security': 0.30, 'debt': 0.20, 'docs': 0.10, 'deps': 0.15}
    overall = int(sum(scores[k] * weights[k] for k in weights))

    # Grade
    grade = 'A' if overall >= 90 else 'B' if overall >= 80 else 'C' if overall >= 70 else 'D' if overall >= 60 else 'F'

    snapshot = {
        'overall_score': overall,
        'complexity_score': scores['complexity'],
        'security_score': scores['security'],
        'debt_score': scores['debt'],
        'docs_score': scores['docs'],
        'deps_score': scores['deps'],
        'details_json': json.dumps(details),
    }

    # Save snapshot
    con = get_conn()
    try:
        con.execute(
            """INSERT INTO health_snapshots
                       (overall_score,complexity_score,security_score,debt_score,docs_score,deps_score,details_json)
                       VALUES (?,?,?,?,?,?,?)""",
            (
                overall,
                scores['complexity'],
                scores['security'],
                scores['debt'],
                scores['docs'],
                scores['deps'],
                json.dumps(details),
            ),
        )
        con.commit()
    finally:
        con.close()

    return {
        'overall': overall,
        'grade': grade,
        'scores': scores,
        'details': details,
        'weights': weights,
        'tip': _health_tip(scores),
    }


def _health_tip(scores: dict) -> str:
    lowest = min(scores, key=lambda k: scores[k])
    tips = {
        'security': 'Run a security scan and move any hardcoded secrets to the vault',
        'complexity': 'Refactor high-complexity functions (CC≥8) into smaller units',
        'debt': 'Clear TODO/FIXME comments and split files over 300 lines',
        'docs': 'Add docstrings to public functions — aim for 80%+ coverage',
        'deps': 'Pin all dependencies to specific versions',
    }
    return tips.get(lowest, 'Keep up the great work!')


@router.get('/health/history')
def health_history(limit: int = 10):
    """Execute or process health history operation."""
    from ..services.memory_db import get_conn

    con = get_conn()
    try:
        rows = con.execute(
            'SELECT * FROM health_snapshots ORDER BY created_at DESC LIMIT ?', (min(limit, 50),)
        ).fetchall()
    finally:
        con.close()
    return {'snapshots': [dict(r) for r in rows], 'count': len(rows)}


# ══════════════════════════════════════════════════════════════════
#  BACKGROUND AGENT TASKS (Cursor-style async agent runs)
# ══════════════════════════════════════════════════════════════════


@router.post('/tasks')
async def create_background_task(req: Request):
    """Create a background agent task — fire and forget, notified on completion."""
    import uuid

    try:
        body = await req.json()
    except (json.JSONDecodeError, TypeError, ValueError):
        body = {}
    name = (body.get('name') or 'Background Task')[:200]
    prompt = (body.get('prompt') or '').strip()
    agent_id = body.get('agent_id', 'builder')
    trigger = body.get('trigger_src', 'api')

    if not prompt:
        return {'ok': False, 'error': 'prompt required'}

    task_id = f'bg_{uuid.uuid4().hex[:8]}'

    from ..services.memory_db import get_conn

    con = get_conn()
    try:
        con.execute(
            'INSERT INTO background_tasks(id,name,prompt,agent_id,status,trigger_src) VALUES (?,?,?,?,?,?)',
            (task_id, name, prompt[:4000], agent_id, 'pending', trigger),
        )
        con.commit()
    finally:
        con.close()

    # Run async in background
    asyncio.create_task(_execute_background_task(task_id, name, prompt, agent_id))

    return {'ok': True, 'task_id': task_id, 'name': name, 'status': 'running'}


async def _execute_background_task(task_id: str, name: str, prompt: str, agent_id: str):
    """Execute a background task and save result."""
    from ..services import llm as llm_svc
    from ..services.memory_db import get_conn

    try:
        result = await llm_svc.complete(
            [{'role': 'user', 'content': prompt}], agent_id=agent_id, max_tokens=2000, inject_steering=False
        )
        output = result.get('text', '')
        status = 'done'
    except Exception as ex:
        output = f'Error: {ex}'
        status = 'failed'

    con = get_conn()
    try:
        con.execute(
            'UPDATE background_tasks SET status=?,result=?,completed_at=CURRENT_TIMESTAMP WHERE id=?',
            (status, output[:4000], task_id),
        )
        con.commit()
    finally:
        con.close()

    # Broadcast notification
    try:
        from ..routers.websocket import broadcast

        await broadcast(
            {
                'type': 'background_task_done',
                'task_id': task_id,
                'name': name,
                'status': status,
                'preview': output[:100],
            }
        )
    except (KeyError, TypeError, ValueError, json.JSONDecodeError, OSError, AttributeError, RuntimeError):
        pass

    log.info('Background task %s (%s) completed: %s', task_id, name, status)


@router.get('/tasks')
def list_background_tasks(status: str = '', limit: int = 20):
    """Retrieve and return list background tasks."""
    from ..services.memory_db import get_conn

    con = get_conn()
    try:
        where, params = [], []
        if status:
            where.append('status=?')
            params.append(status)
        sql = (
            'SELECT * FROM background_tasks'
            + (f' WHERE {" AND ".join(where)}' if where else '')
            + ' ORDER BY created_at DESC LIMIT ?'
        )
        params.append(min(limit, 100))
        rows = con.execute(sql, params).fetchall()
    finally:
        con.close()
    return {'tasks': [dict(r) for r in rows], 'count': len(rows)}


@router.get('/tasks/{task_id}')
def get_task(task_id: str):
    """Retrieve and return get task."""
    from ..services.memory_db import get_conn

    con = get_conn()
    try:
        row = con.execute('SELECT * FROM background_tasks WHERE id=?', (task_id,)).fetchone()
    finally:
        con.close()
    if not row:
        return {'ok': False, 'error': 'Not found'}
    return dict(row)


@router.delete('/tasks/{task_id}')
def delete_task(task_id: str):
    """Delete or remove specified task."""
    from ..services.memory_db import get_conn

    con = get_conn()
    try:
        con.execute('DELETE FROM background_tasks WHERE id=?', (task_id,))
        con.commit()
    finally:
        con.close()
    return {'ok': True}
