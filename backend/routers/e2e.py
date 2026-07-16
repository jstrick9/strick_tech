"""
Agentic OS — E2E Testing Router
Playwright-based end-to-end testing with:
- Real screenshot capture
- DOM snapshot
- Console log capture
- Auto-fix loop (Hermes patches failing tests)
- Trace viewer data
"""

from __future__ import annotations

import asyncio
import base64
import datetime
import json
import logging
import time
import uuid
from pathlib import Path

from fastapi import APIRouter, Request


def _get_port() -> int:
    import os

    return int(os.getenv('AGENTIC_OS_PORT', '8787'))


router = APIRouter(prefix='/api/e2e', tags=['e2e'])
log = logging.getLogger('agentic.e2e')

ROOT = Path(__file__).resolve().parents[2]  # FIX 1: parents[2]=agentic-os root
PREVIEW_DIR = ROOT / 'preview'


# ── Run E2E ────────────────────────────────────────────────────────────────────
@router.post('/run')
async def e2e_run(req: Request):
    """
    POST /api/e2e/run
    Body: {target: "web"|"mobile", url?, steps?}
    Returns full trace with screenshots if Playwright is installed,
    or a smart heuristic trace if not.
    """
    try:
        body = await req.json()
    except Exception:
        body = {}
    target = body.get('target', 'web')
    url = body.get('url') or (
        f'http://localhost:{_get_port()}/preview/mobile/index.html'
        if target == 'mobile'
        else f'http://localhost:{_get_port()}/preview/index.html'
    )
    run_id = f'e2e_{uuid.uuid4().hex[:10]}'

    # Try Playwright first
    playwright_available = await _check_playwright()
    if playwright_available:
        trace_steps = await _playwright_trace(url, target, run_id)
    else:
        trace_steps = await _heuristic_trace(url, target)

    # Persist to DB
    _persist_trace(run_id, target, trace_steps)

    passed = sum(1 for s in trace_steps if s.get('status') == 'pass')
    total = len(trace_steps)
    score = round(passed / total, 2) if total else 0

    return {
        'ok': passed == total,
        'run_id': run_id,
        'target': target,
        'engine': 'playwright' if playwright_available else 'heuristic',
        'passed': passed,
        'total': total,
        'score': score,
        'url': url,
        'trace_steps': trace_steps,
        'timestamp': datetime.datetime.now().isoformat(),
    }


@router.post('/autofix')
async def e2e_autofix(req: Request):
    """
    Run E2E, detect failures, use LLM to patch the file, re-run.
    Up to max_iters times until score >= 0.8.
    """
    try:
        body = await req.json()
    except Exception:
        body = {}
    target = body.get('target', 'web')
    max_iters = min(int(body.get('max_iters', 3)), 5)
    iterations = []

    for i in range(1, max_iters + 1):
        run_result = await e2e_run(Request(scope={'type': 'http'}, receive=_make_receive({'target': target})))
        score = run_result['score']
        passed = run_result['passed']
        total = run_result['total']
        run_id = run_result['run_id']
        failures = [s for s in run_result['trace_steps'] if s.get('status') != 'pass']

        iterations.append(
            {
                'iter': i,
                'score': score,
                'passed': passed,
                'total': total,
                'run_id': run_id,
                'patches': [],
            }
        )

        if score >= 0.8 or not failures:
            break

        # Attempt LLM auto-fix
        patches = await _llm_fix(target, failures)
        iterations[-1]['patches'] = patches

        await asyncio.sleep(0.3)

    final = iterations[-1]['score'] if iterations else 0
    return {
        'ok': final >= 0.8,
        'target': target,
        'iterations': iterations,
        'final_score': final,
        'status': 'green' if final >= 0.8 else 'needs_review',
    }


@router.get('/history')
def e2e_history(limit: int = 20):
    """Return recent E2E run summaries from DB."""
    from ..services.memory_db import get_conn

    con = get_conn()
    try:
        rows = con.execute(
            """SELECT DISTINCT run_id, target,
                      SUM(CASE WHEN status='pass' THEN 1 ELSE 0 END) as passed,
                      COUNT(*) as total,
                      datetime(MAX(created_at),'localtime') as ts
               FROM e2e_traces
               GROUP BY run_id, target
               ORDER BY MAX(created_at) DESC
               LIMIT ?""",
            (limit,),
        ).fetchall()
    finally:
        con.close()
    return [dict(r) | {'score': round(r['passed'] / r['total'], 2) if r['total'] else 0} for r in rows]


@router.get('/trace/{run_id}')
def e2e_trace(run_id: str):
    """Return full trace steps for a run."""
    from ..services.memory_db import get_conn

    con = get_conn()
    try:
        rows = con.execute(
            """SELECT step_no, step_name, status, screenshot_b64,
                      substr(dom_snapshot,1,8000) as dom,
                      console, network_json, duration_ms, created_at
               FROM e2e_traces WHERE run_id=? ORDER BY step_no""",
            (run_id,),
        ).fetchall()
    finally:
        con.close()
    out = []
    for r in rows:
        d = dict(r)
        try:
            d['meta'] = json.loads(d.pop('network_json') or '{}')
        except Exception:
            d['meta'] = {}
        out.append(d)
    return {'run_id': run_id, 'steps': out}


@router.get('/status')
def e2e_status():
    """Quick status: playwright installed? last run score?"""
    from ..services.memory_db import get_conn

    pw = False
    try:
        import playwright

        pw = True
    except ImportError:
        pass
    con = get_conn()
    try:
        last = con.execute(
            "SELECT run_id, target, datetime(MAX(created_at),'localtime') as ts FROM e2e_traces ORDER BY created_at DESC LIMIT 1"
        ).fetchone()
    finally:
        con.close()
    return {
        'playwright_installed': pw,
        'playwright_setup': 'pip install playwright && playwright install chromium' if not pw else 'ready',
        'last_run': dict(last) if last else None,
    }


# ── Playwright trace ───────────────────────────────────────────────────────────
async def _check_playwright() -> bool:
    try:
        from playwright.async_api import async_playwright

        return True
    except ImportError:
        return False


async def _playwright_trace(url: str, target: str, run_id: str) -> list[dict]:
    try:
        from playwright.async_api import async_playwright

        steps = []

        async with async_playwright() as p:
            is_mobile = target == 'mobile'
            browser = await p.chromium.launch(headless=True)
            ctx = await browser.new_context(
                viewport={'width': 390 if is_mobile else 1280, 'height': 844 if is_mobile else 800},
                is_mobile=is_mobile,
                has_touch=is_mobile,
                user_agent='AgenticOS/6.0 Playwright',
            )
            console_lines = []
            page = await ctx.new_page()
            page.on('console', lambda m: console_lines.append(f'[{m.type}] {m.text}'))
            page.on('pageerror', lambda e: console_lines.append(f'[error] {e}'))

            async def snap(name: str, status: str = 'pass') -> dict:
                """Execute or process snap operation."""
                try:
                    png = await page.screenshot(full_page=False, type='png')
                    html = await page.content()
                    return {
                        'step': name,
                        'status': status,
                        'screenshot_b64': base64.b64encode(png).decode(),
                        'dom': html[:10000],
                        'url': page.url,
                        'console': list(console_lines[-6:]),
                    }
                except Exception as ex:
                    return {'step': name, 'status': 'error', 'error': str(ex)}

            # Step 1: Navigate
            t0 = time.time()
            try:
                await page.goto(url, wait_until='domcontentloaded', timeout=8000)
                s = await snap('navigate', 'pass')
                s['duration_ms'] = round((time.time() - t0) * 1000)
                steps.append(s)
            except Exception as e:
                steps.append({'step': 'navigate', 'status': 'fail', 'error': str(e), 'duration_ms': 0})
                await browser.close()
                return steps

            # Step 2: Check title
            try:
                title = await page.title()
                ok = bool(title and len(title) > 0)
                s = await snap('check_title', 'pass' if ok else 'fail')
                s['title'] = title
                s['duration_ms'] = 80
                steps.append(s)
            except Exception as e:
                steps.append({'step': 'check_title', 'status': 'fail', 'error': str(e)})

            # Step 3: Find & check CTA button
            try:
                cta = page.locator('button, [role=button], a[href], [class*=btn], [id*=cta]').first
                exists = await cta.count() > 0
                s = await snap('find_cta', 'pass' if exists else 'warn')
                s['cta_found'] = exists
                s['duration_ms'] = 60
                steps.append(s)
                if exists:
                    await cta.hover(timeout=2000)
            except Exception as e:
                steps.append({'step': 'find_cta', 'status': 'warn', 'error': str(e)})

            # Step 4: Check for JS errors
            js_errors = [l for l in console_lines if '[error]' in l]
            s = await snap('check_errors', 'fail' if js_errors else 'pass')
            s['js_errors'] = js_errors
            s['duration_ms'] = 40
            steps.append(s)

            # Step 5: Check content rendered
            try:
                body_text = await page.locator('body').inner_text()
                ok = len(body_text.strip()) > 20
                s = await snap('content_rendered', 'pass' if ok else 'fail')
                s['body_length'] = len(body_text)
                s['duration_ms'] = 50
                steps.append(s)
            except Exception as e:
                steps.append({'step': 'content_rendered', 'status': 'fail', 'error': str(e)})

            await browser.close()

        # Add step numbers
        for i, s in enumerate(steps):
            s['step_no'] = i + 1
            s.setdefault('duration_ms', 100 + i * 50)
        return steps

    except Exception as e:
        log.error('Playwright trace failed: %s', e)
        return [{'step_no': 1, 'step': 'playwright_error', 'status': 'error', 'error': str(e)}]


# ── Heuristic trace (no Playwright) ───────────────────────────────────────────
async def _heuristic_trace(url: str, target: str) -> list[dict]:
    """Smart static analysis of preview files."""
    path = PREVIEW_DIR / ('mobile/index.html' if target == 'mobile' else 'index.html')
    html = path.read_text(encoding='utf-8', errors='ignore') if path.exists() else ''
    steps = []

    def chk(name: str, cond: bool, detail: str = '', hint: str = '') -> dict:
        """Execute or process chk operation."""
        return {
            'step': name,
            'status': 'pass' if cond else 'fail',
            'detail': detail,
            'hint': hint,
            'screenshot_b64': None,
            'dom': '',
            'console': [],
        }

    steps.append(
        chk(
            'file_exists',
            path.exists(),
            f'{path.name} found' if path.exists() else 'No index.html found',
            'Run Scaffold in Builder tab',
        )
    )
    if html:
        steps.append(chk('has_doctype', '<!doctype' in html.lower(), 'DOCTYPE present', 'Add <!DOCTYPE html>'))
        steps.append(chk('has_title', '<title' in html.lower(), 'Title tag present', 'Add <title>My App</title>'))
        steps.append(chk('has_body', '<body' in html.lower(), 'Body tag present', 'Add <body> tag'))
        steps.append(
            chk(
                'has_cta',
                any(t in html.lower() for t in ['button', 'btn', 'cta', 'get-started', 'onclick']),
                'CTA element detected',
                'Add a <button> or link',
            )
        )
        steps.append(chk('no_syntax_err', 'SyntaxError' not in html, 'No syntax errors in source', 'Check JS console'))
        steps.append(chk('has_content', len(html.strip()) > 200, f'{len(html)} bytes', 'Add content to your page'))
    else:
        steps += [chk('has_content', False, 'Empty file', 'Scaffold or write content')]

    for i, s in enumerate(steps):
        s['step_no'] = i + 1
        s['duration_ms'] = 20 + i * 15
    return steps


# ── LLM auto-fix ──────────────────────────────────────────────────────────────
async def _llm_fix(target: str, failures: list[dict]) -> list[str]:
    """Use LLM to patch the file for failing checks."""
    from ..services import llm

    fpath = PREVIEW_DIR / ('mobile/index.html' if target == 'mobile' else 'index.html')
    if not fpath.exists():
        return ['File not found — cannot patch']

    content = fpath.read_text(encoding='utf-8', errors='ignore')
    fail_names = [f.get('step', '?') + (': ' + f.get('error', '') if f.get('error') else '') for f in failures[:3]]

    messages = [
        {
            'role': 'system',
            'content': 'You are an expert web developer auto-fixing a failing page. '
            'Return ONLY the complete fixed HTML file, no explanation, no markdown fences.',
        },
        {'role': 'user', 'content': f'Failing checks: {fail_names}\n\nFix the following file:\n\n{content[:6000]}'},
    ]
    result = await llm.complete(messages, agent_id='builder', max_tokens=4096, inject_steering=False)  # FIX 10
    fixed = result.get('text', '').strip()

    patches = []
    if fixed and len(fixed) > 100 and fixed != content:
        # Strip any accidental code fences
        if fixed.startswith('```'):
            fixed = '\n'.join(fixed.split('\n')[1:])
        if fixed.endswith('```'):
            fixed = '\n'.join(fixed.split('\n')[:-1])
        fpath.write_text(fixed, encoding='utf-8')
        # version it
        from ..services.memory_db import get_conn

        con = get_conn()
        try:
            con.execute(
                'INSERT INTO file_versions(path,content,author,message) VALUES (?,?,?,?)',
                (fpath.name, content, 'e2e-autofix', f'autofix: {", ".join(fail_names)[:120]}'),
            )
            con.commit()
        finally:
            con.close()
        patches = [f'Patched {fpath.name} for: {", ".join(fail_names)[:80]}']
    else:
        patches = ['No patch applied (LLM returned unchanged or empty output)']

    return patches


def _persist_trace(run_id: str, target: str, steps: list[dict]):
    from ..services.memory_db import get_conn

    con = get_conn()
    try:
        for s in steps:
            con.execute(
                """INSERT INTO e2e_traces
                   (run_id, target, step_no, step_name, status,
                    screenshot_b64, dom_snapshot, console, network_json, duration_ms)
                   VALUES (?,?,?,?,?,?,?,?,?,?)""",
                (
                    run_id,
                    target,
                    s.get('step_no', 0),
                    s.get('step', ''),
                    s.get('status', ''),
                    s.get('screenshot_b64'),
                    (s.get('dom') or '')[:20000],
                    json.dumps(s.get('console', [])),
                    json.dumps({k: v for k, v in s.items() if k not in ('screenshot_b64', 'dom', 'console')})[:2000],
                    s.get('duration_ms', 0),
                ),
            )
        con.commit()
    finally:
        con.close()


def _make_receive(body_dict: dict):
    """Create a fake ASGI receive for internal POST calls."""
    import json as _json

    body = _json.dumps(body_dict).encode()

    async def receive():
        """Execute or process receive operation."""
        return {'type': 'http.request', 'body': body, 'more_body': False}

    return receive


# ════════════════════════════════════════════════════════════════
#  SPRINT 14 — Playwright install helper + extended tests
# ════════════════════════════════════════════════════════════════


@router.get('/playwright/status')
async def playwright_status():
    """Check if Playwright is installed and browser is available."""
    try:
        from playwright.async_api import async_playwright

        installed = True
    except ImportError:
        installed = False
        return {
            'installed': False,
            'browser_ready': False,
            'install_cmd': 'pip install playwright && python -m playwright install chromium',
            'note': 'Without Playwright, E2E uses smart heuristic fallback',
        }

    # Check if browser binary is available
    browser_ready = False
    try:
        from playwright.async_api import async_playwright

        async with async_playwright() as p:
            browser = await p.chromium.launch(headless=True)
            await browser.close()
            browser_ready = True
    except Exception as ex:
        return {
            'installed': True,
            'browser_ready': False,
            'error': str(ex),
            'install_cmd': 'python -m playwright install chromium',
        }

    return {
        'installed': True,
        'browser_ready': True,
        'note': 'Playwright is ready for real screenshot E2E tests',
    }


@router.post('/playwright/install')
async def install_playwright():
    """Trigger playwright browser install (background subprocess)."""
    import asyncio

    proc = await asyncio.create_subprocess_exec(
        'python',
        '-m',
        'playwright',
        'install',
        'chromium',
        stdout=asyncio.subprocess.PIPE,
        stderr=asyncio.subprocess.PIPE,
    )
    stdout, stderr = await asyncio.wait_for(proc.communicate(), timeout=120)
    ok = proc.returncode == 0
    return {
        'ok': ok,
        'stdout': stdout.decode()[:500],
        'stderr': stderr.decode()[:300] if not ok else '',
        'note': "Run 'pip install playwright && python -m playwright install chromium' manually if this fails",
    }


@router.post('/accessibility')
async def accessibility_audit(req: Request):
    """Run an accessibility audit on a URL using axe-core via Playwright."""
    try:
        body = await req.json()
    except Exception:
        body = {}
    url = body.get('url', 'http://localhost:8787/preview/index.html')

    try:
        from playwright.async_api import async_playwright
    except ImportError:
        return {
            'ok': False,
            'error': 'Playwright not installed',
            'mock_issues': [
                {
                    'id': 'color-contrast',
                    'description': 'Text must have sufficient color contrast',
                    'impact': 'serious',
                    'count': 3,
                },
                {
                    'id': 'aria-labels',
                    'description': 'Form elements must have labels',
                    'impact': 'moderate',
                    'count': 1,
                },
                {'id': 'alt-text', 'description': 'Images must have alt text', 'impact': 'critical', 'count': 2},
            ],
        }

    violations = []
    try:
        async with async_playwright() as p:
            browser = await p.chromium.launch(headless=True)
            page = await browser.new_page()
            await page.goto(url, timeout=8000)

            # Inject axe-core from CDN and run audit
            await page.add_script_tag(url='https://cdnjs.cloudflare.com/ajax/libs/axe-core/4.9.1/axe.min.js')
            await page.wait_for_timeout(500)

            results = await page.evaluate('() => axe.run()')
            violations = results.get('violations', [])

            await browser.close()
    except Exception as ex:
        return {'ok': False, 'error': str(ex)}

    return {
        'ok': True,
        'url': url,
        'violations': violations,
        'count': len(violations),
        'passed': len(violations) == 0,
    }


@router.post('/performance')
async def performance_audit(req: Request):
    """Run a Lighthouse-style performance audit using Playwright."""
    try:
        body = await req.json()
    except Exception:
        body = {}
    url = body.get('url', 'http://localhost:8787/preview/index.html')

    try:
        from playwright.async_api import async_playwright
    except ImportError:
        # Return simulated metrics
        # FIX 16: deterministic representative mock (not random)
        return {
            'ok': True,
            'mock': True,
            'metrics': {
                'FCP_ms': 1200,
                'LCP_ms': 2100,
                'TBT_ms': 150,
                'CLS': 0.05,
                'TTI_ms': 2500,
                'score': 72,
            },
            'note': 'Install Playwright for real metrics: pip install playwright && playwright install chromium',
        }

    metrics = {}
    try:
        async with async_playwright() as p:
            browser = await p.chromium.launch(headless=True)
            page = await browser.new_page()

            t0 = time.time()
            await page.goto(url, wait_until='networkidle', timeout=15000)
            load_time = (time.time() - t0) * 1000

            # Get Performance API data
            perf = await page.evaluate("""() => {
                const e = performance.getEntriesByType('navigation')[0];
                const p = performance.getEntriesByType('paint');
                const fcp = p.find(x=>x.name==='first-contentful-paint');
                return {
                    dom_complete: e ? e.domComplete : 0,
                    dom_interactive: e ? e.domInteractive : 0,
                    fcp: fcp ? fcp.startTime : 0,
                    resources: performance.getEntriesByType('resource').length,
                };
            }""")

            await browser.close()

            metrics = {
                'FCP_ms': round(perf.get('fcp', 0)),
                'DOM_ms': round(perf.get('dom_complete', 0)),
                'load_ms': round(load_time),
                'resources': perf.get('resources', 0),
                'score': max(0, 100 - int(load_time / 50)),
            }
    except Exception as ex:
        return {'ok': False, 'error': str(ex)}

    return {'ok': True, 'url': url, 'metrics': metrics}
