"""
Agentic OS — AI Test Generator
Select any file → AI writes a complete test suite.
Supports Jest, pytest, Vitest, Mocha, and Playwright.
"""

from __future__ import annotations

import contextlib

import logging
from pathlib import Path

from fastapi import APIRouter, Request
from fastapi.responses import StreamingResponse

from ..services import llm, memory_db

router = APIRouter(prefix='/api/testgen', tags=['testgen'])
log = logging.getLogger('agentic.testgen')

ROOT = Path(__file__).resolve().parents[2]  # FIX 1: parents[2]=agentic-os root
PREVIEW_DIR = ROOT / 'preview'

FRAMEWORK_CONFIGS = {
    'jest': {'lang': 'javascript', 'ext': '.test.js', 'import': 'describe/test/expect'},
    'vitest': {'lang': 'javascript', 'ext': '.test.ts', 'import': "import {describe,it,expect} from 'vitest'"},
    'pytest': {'lang': 'python', 'ext': '_test.py', 'import': 'import pytest'},
    'mocha': {'lang': 'javascript', 'ext': '.test.js', 'import': "const {expect} = require('chai')"},
    'playwright': {'lang': 'javascript', 'ext': '.spec.ts', 'import': "import {test,expect} from '@playwright/test'"},
}


@router.post('/generate')
async def generate_tests(req: Request):
    """
    POST /api/testgen/generate
    Body: {filepath, framework, context?}
    Streams the generated test file.
    """
    try:
        body = await req.json()
    except (json.JSONDecodeError, TypeError, ValueError):
        body = {}
    filepath = (body.get('filepath') or '').strip().lstrip('/')
    framework = body.get('framework', 'jest').lower()
    context = body.get('context', '')
    stream = body.get('stream', True)

    if not filepath:
        return {'ok': False, 'error': 'filepath required'}

    # Read the source file
    source_path = (PREVIEW_DIR / filepath).resolve()
    if not str(source_path).startswith(str(PREVIEW_DIR.resolve())):
        return {'ok': False, 'error': 'path traversal denied'}
    if not source_path.exists():
        return {'ok': False, 'error': f'File not found: {filepath}'}

    source_code = source_path.read_text(encoding='utf-8', errors='ignore')
    ext = filepath.rsplit('.', 1)[-1] if '.' in filepath else 'js'
    cfg = FRAMEWORK_CONFIGS.get(framework, FRAMEWORK_CONFIGS['jest'])

    system = f"""You are an expert test engineer. Write a comprehensive {framework} test suite for the provided code.
Rules:
- Use {framework} syntax and conventions exactly
- Cover: happy path, edge cases, error cases, boundary values
- Write descriptive test names that explain WHAT is being tested
- Include setup/teardown where needed (beforeEach, afterEach)
- Mock external dependencies (APIs, databases, filesystem)
- Aim for >90% coverage
- Include at least 8-12 meaningful test cases
- Return ONLY the test file content, no explanation, no markdown fences
File: {filepath}
{f'Additional context: {context}' if context else ''}"""

    messages = [
        {'role': 'system', 'content': system},
        {
            'role': 'user',
            'content': f'Write {framework} tests for this {ext} code:\n\n```{ext}\n{source_code[:6000]}\n```',
        },
    ]

    if stream:
        # FIX 15: audit_log the streaming generation so it's tracked
        memory_db.audit_log('testgen_stream', f'{filepath} ({framework}) [streaming]')

        async def generate():
            """Execute or process generate operation."""
            async for chunk in llm.stream(
                messages, agent_id='reviewer', max_tokens=4096, temperature=0.2, inject_steering=False
            ):  # FIX 2a
                yield chunk
            # After streaming, save the test file
            # (client saves it via /api/preview/save)

        return StreamingResponse(generate(), media_type='text/event-stream', headers={'Cache-Control': 'no-cache'})

    # Non-streaming
    result = await llm.complete(
        messages, agent_id='reviewer', max_tokens=4096, temperature=0.2, inject_steering=False
    )  # FIX 2b
    test_code = result.get('text', '').strip()
    if test_code.startswith('```'):
        test_code = '\n'.join(test_code.split('\n')[1:]).rstrip('`').strip()

    # Auto-save the test file
    name = filepath.rsplit('.', 1)[0]
    test_name = name + cfg['ext']
    test_path = (PREVIEW_DIR / test_name).resolve()
    if str(test_path).startswith(str(PREVIEW_DIR.resolve())):
        test_path.parent.mkdir(parents=True, exist_ok=True)
        test_path.write_text(test_code, encoding='utf-8')

    memory_db.audit_log('testgen', f'{filepath} → {test_name} ({framework})')
    return {
        'ok': result.get('ok'),
        'framework': framework,
        'source': filepath,
        'test_file': test_name,
        'test_code': test_code,
        'tokens': result.get('tokens', 0),
    }


@router.post('/generate-for-project')
async def generate_project_tests(req: Request):
    """Generate tests for all files in the project."""
    try:
        body = await req.json()
    except (json.JSONDecodeError, TypeError, ValueError):
        body = {}
    framework = body.get('framework', 'jest')
    max_files = min(int(body.get('max_files', 5)), 10)

    # Find all JS/TS/Python files
    if not PREVIEW_DIR.exists():
        return {'ok': False, 'error': 'No preview files'}

    ext_map = {
        'jest': ['.js', '.jsx', '.ts', '.tsx'],
        'vitest': ['.ts', '.tsx'],
        'pytest': ['.py'],
        'mocha': ['.js'],
    }
    target_exts = ext_map.get(framework, ['.js', '.ts'])
    files = [
        f.relative_to(PREVIEW_DIR).as_posix()
        for f in PREVIEW_DIR.rglob('*')
        if f.is_file()
        and f.suffix in target_exts
        and 'test' not in f.name.lower()
        and 'spec' not in f.name.lower()
        and '.git' not in str(f)
    ][:max_files]

    results = []
    for filepath in files:
        try:

            class _Req:
                async def json(self_inner):
                    """Execute or process json operation."""
                    return {'filepath': filepath, 'framework': framework, 'stream': False}

            r = await generate_tests(_Req())
            results.append({'file': filepath, 'test': r.get('test_file', ''), 'ok': r.get('ok', False)})
        except Exception as e:
            results.append({'file': filepath, 'error': str(e), 'ok': False})

    return {'ok': True, 'framework': framework, 'files_processed': len(results), 'results': results}


@router.get('/frameworks')
def list_frameworks():
    """Retrieve and return list frameworks."""
    return [
        {'id': k, 'lang': v['lang'], 'ext': v['ext'], 'description': f'{k.capitalize()} test framework for {v["lang"]}'}
        for k, v in FRAMEWORK_CONFIGS.items()
    ]


@router.post('/run')
async def run_tests(req: Request):
    """Run tests using the MCP shell tool."""
    try:
        body = await req.json()
    except (json.JSONDecodeError, TypeError, ValueError):
        body = {}
    framework = body.get('framework', 'jest')
    test_file = body.get('test_file', '')

    cmd_map = {
        'jest': 'npx jest --no-coverage',
        'vitest': 'npx vitest run',
        'pytest': 'python -m pytest -v',
        'mocha': 'npx mocha',
    }
    cmd = cmd_map.get(framework, 'npx jest')
    if test_file:
        # FIX 7: sanitize test_file — only allow alphanumeric, /, ., _, - to prevent injection
        import re as _re

        safe_file = _re.sub(r'[^a-zA-Z0-9/_\-.]', '', test_file)[:200]
        if safe_file:
            cmd += f' {safe_file}'

    from .mcp import _shell_run

    try:
        result = await _shell_run(cmd, '')
        return {
            'ok': result.get('returncode', 1) == 0,
            'stdout': result.get('stdout', ''),
            'stderr': result.get('stderr', ''),
            'returncode': result.get('returncode'),
            'command': cmd,
        }
    except Exception as e:
        return {
            'ok': False,
            'error': str(e),
            'command': cmd,
            'hint': f'Make sure {framework} is installed: npm install --save-dev {framework}',
        }


# ── GET alias for generate-for-project ───────────────────────────────────────
@router.get('/generate-for-project')
def generate_project_tests_get(framework: str = 'pytest', max_files: int = 10):
    """GET version of generate-for-project — returns existing test files list."""
    from pathlib import Path

    preview = Path(__file__).resolve().parents[2] / 'preview'
    test_files = []
    if preview.exists():
        for f in preview.rglob('test_*.py'):
            test_files.append({'path': str(f.relative_to(preview)), 'size': f.stat().st_size})
    return {
        'ok': True,
        'framework': framework,
        'test_files': test_files,
        'count': len(test_files),
        'note': 'Use POST to generate new tests',
    }


@router.get('/history')
def test_history():
    """Recent test generation history."""
    from ..services.memory_db import get_conn

    con = get_conn()
    try:
        rows = con.execute("SELECT * FROM audit WHERE action='testgen' ORDER BY created_at DESC LIMIT 20").fetchall()
    except (KeyError, TypeError, ValueError, json.JSONDecodeError, OSError, AttributeError, RuntimeError):
        rows = []
    finally:
        con.close()
    return {'history': [dict(r) for r in rows], 'count': len(rows)}
