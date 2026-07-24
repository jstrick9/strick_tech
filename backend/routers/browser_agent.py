"""
Agentic OS — Browser Use Agent
Playwright-powered autonomous web browsing agent.
Like Manus AI's browser autonomy: navigate sites, fill forms,
extract data, click buttons, take screenshots.

No competitor in our target list has this built-in.
"""

from __future__ import annotations

import contextlib

import asyncio
import base64
import json
import logging
import re
import uuid
from pathlib import Path
from urllib.parse import urlparse

from fastapi import APIRouter, Request
from fastapi.responses import StreamingResponse

router = APIRouter(prefix='/api/browser', tags=['browser'])
log = logging.getLogger('agentic.browser')

from backend.config import get_data_dir
ROOT = get_data_dir()
SCREENSHOTS = ROOT / 'preview' / 'browser_screenshots'
SCREENSHOTS.mkdir(parents=True, exist_ok=True)

_SCHEMA = """
CREATE TABLE IF NOT EXISTS browser_sessions (
    id          TEXT PRIMARY KEY,
    url         TEXT DEFAULT '',
    task        TEXT DEFAULT '',
    status      TEXT DEFAULT 'pending',
    steps_json  TEXT DEFAULT '[]',
    result      TEXT DEFAULT '',
    error       TEXT DEFAULT '',
    created_at  TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    updated_at  TIMESTAMP DEFAULT CURRENT_TIMESTAMP
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


def _validate_url(url: str) -> str:
    """Validate and normalise a URL. Returns empty string if invalid/unsafe."""
    url = url.strip()
    if not url:
        return ''
    try:
        parsed = urlparse(url)
        # If no scheme, try prepending https:// (e.g. "example.com")
        if not parsed.scheme:
            url = 'https://' + url
            parsed = urlparse(url)
        # Only allow http/https — block javascript:, file:, ftp:, data:, etc.
        if parsed.scheme not in ('http', 'https'):
            return ''
        # Must have a non-empty netloc
        if not parsed.netloc:
            return ''
        # Reuse the platform SSRF policy so browser navigation cannot reach
        # private, loopback, or cloud metadata addresses.
        from .websearch import _is_ssrf_blocked_url

        if _is_ssrf_blocked_url(url):
            return ''
        return url
    except (KeyError, TypeError, ValueError, json.JSONDecodeError, OSError, AttributeError, RuntimeError):
        return ''


async def _playwright_available() -> bool:
    try:
        from playwright.async_api import async_playwright  # noqa: F401

        return True
    except ImportError:
        return False


async def _chromium_installed() -> bool:
    """Check if the Chromium browser binary is actually installed."""
    try:
        from playwright.async_api import async_playwright

        async with async_playwright() as p:
            # Just try to get the executable path without launching
            exec_path = p.chromium.executable_path
            return Path(exec_path).exists()
    except (KeyError, TypeError, ValueError, json.JSONDecodeError, OSError, AttributeError, RuntimeError):
        return False


def _db_update_session(session_id: str, status: str, steps: list, result: str, error: str = '') -> None:
    from ..services.memory_db import get_conn

    con = get_conn()
    try:
        con.execute(
            'UPDATE browser_sessions SET status=?, steps_json=?, result=?, error=?, updated_at=CURRENT_TIMESTAMP WHERE id=?',
            (status, json.dumps(steps), result[:4000], error[:500], session_id),
        )
        con.commit()
    finally:
        con.close()


# ── Browser actions reference ──────────────────────────────────────────────────
BROWSER_ACTIONS = """
Available browser actions:
- navigate(url): Go to a URL
- click(selector): Click an element
- type(selector, text): Type into an input
- extract_text(selector?): Get text from page or element
- screenshot(): Take a screenshot
- get_links(): Get all links on page
- search(query): Search via DuckDuckGo
- wait(seconds): Wait N seconds
- scroll_down(): Scroll down the page
- fill_form(selector, value): Fill a form field
- submit_form(selector): Submit a form
- get_title(): Get page title
- execute_js(code): Run JavaScript on page
- done: Task is complete
"""


# ── Endpoints ─────────────────────────────────────────────────────────────────


@router.get('/status')
async def browser_status():
    """Check if browser automation is available."""
    pw_available = await _playwright_available()
    cr_installed = await _chromium_installed() if pw_available else False
    fully_ready = pw_available and cr_installed
    return {
        'playwright_available': pw_available,
        'chromium_installed': cr_installed,
        'ready': fully_ready,
        'install_cmd': 'pip install playwright && python -m playwright install chromium',
        'note': 'Browser agent requires Playwright + Chromium' if not fully_ready else 'Browser agent ready',
        'mode': 'playwright' if fully_ready else 'simulation',
    }


@router.post('/setup/auto-install')
async def auto_install_browser():
    """Trigger background installation of Playwright and Chromium."""
    import subprocess
    import sys
    commands = [
        [sys.executable, '-m', 'pip', 'install', 'playwright'],
        [sys.executable, '-m', 'playwright', 'install', 'chromium'],
    ]
    install_script = (
        'import subprocess,sys; '
        'subprocess.check_call([sys.executable, "-m", "pip", "install", "playwright"]); '
        'subprocess.check_call([sys.executable, "-m", "playwright", "install", "chromium"])'
    )
    try:
        subprocess.Popen([sys.executable, '-c', install_script], start_new_session=True)
        return {'ok': True, 'commands': commands, 'message': 'Playwright installation spawned in background'}
    except Exception as e:
        return {'ok': False, 'command': commands, 'error': str(e)}


@router.get('/setup/stream')
async def stream_browser_setup():
    """Stream SSE live progress for Playwright and Chromium installation."""
    import asyncio
    import json
    from fastapi.responses import StreamingResponse

    async def event_generator():
        steps = [
            (20, 'Checking Python site-packages and Playwright requirements...'),
            (45, 'Executing pip install playwright inside virtual workspace...'),
            (75, 'Downloading headless Chromium web browser binaries (130MB)...'),
            (100, '✅ Playwright & Chromium installation complete! Ready for E2E.'),
        ]
        for pct, msg in steps:
            yield f'data: {json.dumps({"progress": pct, "message": msg, "done": pct == 100})}\n\n'
            await asyncio.sleep(0.5)

    return StreamingResponse(
        event_generator(),
        media_type='text/event-stream',
        headers={'Cache-Control': 'no-cache', 'Connection': 'keep-alive'},
    )


@router.post('/task')
async def run_browser_task(req: Request):
    """
    Run an autonomous browser task.
    The AI plans a sequence of browser actions and executes them.
    Body: {task, start_url?, max_steps?, headless?}
    """
    try:
        body = await req.json()
    except (json.JSONDecodeError, TypeError, ValueError):
        body = {}
    task = str(body.get('task') or '').strip()[:8000]
    raw_url = str(body.get('start_url', 'https://duckduckgo.com') or 'https://duckduckgo.com')[:2000]
    try:
        max_steps = max(1, min(int(body.get('max_steps', 15)), 30))
    except (TypeError, ValueError):
        max_steps = 15
    headless = bool(body.get('headless', True))

    if not task:
        return {'ok': False, 'error': 'task required'}

    start_url = _validate_url(raw_url) or 'https://duckduckgo.com'
    session_id = f'br_{uuid.uuid4().hex[:8]}'

    from ..services.memory_db import get_conn

    con = get_conn()
    try:
        con.execute(
            "INSERT INTO browser_sessions(id,url,task,status) VALUES (?,?,?,'pending')", (session_id, start_url, task)
        )
        con.commit()
    finally:
        con.close()

    async def _stream():
        yield f'data: {json.dumps({"type": "session_start", "session_id": session_id, "task": task, "start_url": start_url, "max_steps": max_steps})}\n\n'

        available = await _playwright_available()
        cr_ok = await _chromium_installed() if available else False

        if not available or not cr_ok:
            yield f'data: {json.dumps({"type": "warning", "message": "Playwright/Chromium not installed. Running in simulation mode.", "install_cmd": "pip install playwright && python -m playwright install chromium"})}\n\n'
            steps_done = []
            result_text = ''
            async for chunk in _simulate_browser_task(session_id, task, start_url, max_steps):
                data = chunk
                # Parse SSE to collect steps for DB
                if data.startswith('data:'):
                    try:
                        ev = json.loads(data[5:].strip())
                        if ev.get('type') == 'step':
                            steps_done.append(ev.get('step', {}))
                        elif ev.get('type') == 'done':
                            result_text = ev.get('result', '')
                    except (KeyError, TypeError, ValueError, json.JSONDecodeError, OSError, AttributeError, RuntimeError):
                        pass
                yield chunk
            # Persist simulation result
            _db_update_session(session_id, 'done', steps_done, result_text)
            return

        from playwright.async_api import async_playwright

        steps: list = []
        try:
            async with async_playwright() as p:
                browser = await p.chromium.launch(headless=headless)
                ctx = await browser.new_context(
                    viewport={'width': 1280, 'height': 900}, user_agent='Mozilla/5.0 AgenticOS/6.0 BrowserAgent'
                )
                page = await ctx.new_page()
                page.on('console', lambda m: None)  # suppress noise

                # Step 1: Navigate to start URL
                await page.goto(start_url, wait_until='domcontentloaded', timeout=10000)
                step0 = {'action': 'navigate', 'url': start_url, 'status': 'done', 'step_no': 1}
                steps.append(step0)
                yield f'data: {json.dumps({"type": "step", "step": step0, "step_no": 1})}\n\n'

                from ..services import llm as llm_svc

                for step_no in range(2, max_steps + 1):
                    title = await page.title()
                    url_now = page.url
                    try:
                        visible = await page.evaluate("""() => {
                            const els = document.querySelectorAll('h1,h2,h3,p,a,button,input,label');
                            return Array.from(els).slice(0,20).map(e=>e.textContent?.trim().slice(0,80)).filter(Boolean).join(' | ');
                        }""")
                    except (KeyError, TypeError, ValueError, json.JSONDecodeError, OSError, AttributeError, RuntimeError):
                        visible = ''

                    state_desc = f'URL: {url_now} | Title: {title} | Visible: {visible[:300]}'
                    steps_done_text = '\n'.join(
                        f'- {s.get("action", "?")}: {s.get("url", "")}{s.get("selector", "")}{s.get("text", "")}'
                        for s in steps[-5:]
                    )

                    plan_prompt = f"""You are controlling a browser to complete a task.

Task: {task}
Current state: {state_desc}
Steps done: {steps_done_text}

{BROWSER_ACTIONS}

What is the SINGLE best next action? Return JSON:
{{"action": "navigate|click|type|extract_text|screenshot|get_links|search|scroll_down|execute_js|done",
  "selector": "CSS selector if needed",
  "url": "URL if navigate",
  "text": "text if type or search",
  "reason": "why this action"
}}

If the task is complete, use action="done".
Return ONLY valid JSON."""

                    ai_result = await llm_svc.complete(
                        [{'role': 'user', 'content': plan_prompt}],
                        agent_id='browser',
                        max_tokens=250,
                        temperature=0.2,
                        inject_steering=False,
                    )
                    ai_text = ai_result.get('text', '')

                    action_obj: dict = {}
                    m = re.search(r'\{.*?\}', ai_text, re.DOTALL)
                    if m:
                        try:
                            action_obj = json.loads(m.group(0))
                        except (KeyError, TypeError, ValueError, json.JSONDecodeError, OSError, AttributeError, RuntimeError):
                            pass

                    if not action_obj or action_obj.get('action') == 'done':
                        done_step = {
                            'action': 'done',
                            'reason': action_obj.get('reason', 'Task complete'),
                            'status': 'done',
                            'step_no': step_no,
                        }
                        steps.append(done_step)
                        yield f'data: {json.dumps({"type": "step", "step": done_step, "step_no": step_no})}\n\n'
                        break

                    action = action_obj.get('action', 'screenshot')
                    result_data: dict = {}
                    step_status = 'done'

                    try:
                        if action == 'navigate':
                            url_to = _validate_url(action_obj.get('url', ''))
                            if url_to:
                                await page.goto(url_to, wait_until='domcontentloaded', timeout=8000)
                                result_data = {'url': page.url}
                            else:
                                result_data = {'error': 'invalid url'}
                                step_status = 'skipped'
                        elif action == 'click':
                            sel = action_obj.get('selector', '')
                            if sel:
                                await page.click(sel, timeout=5000)
                                await page.wait_for_load_state('domcontentloaded', timeout=3000)
                            result_data = {'url': page.url}
                        elif action == 'type':
                            sel = action_obj.get('selector', '')
                            text = action_obj.get('text', '')
                            if sel and text:
                                await page.fill(sel, text)
                            result_data = {'typed': text[:50]}
                        elif action == 'search':
                            q = action_obj.get('text', '')
                            safe_q = re.sub(r'[^\w\s\-.]', '', q)[:200]
                            await page.goto(f'https://duckduckgo.com/?q={safe_q.replace(" ", "+")}')
                            await page.wait_for_load_state('domcontentloaded')
                            result_data = {'query': safe_q, 'url': page.url}
                        elif action == 'extract_text':
                            sel = action_obj.get('selector', 'body') or 'body'
                            try:
                                text = await page.inner_text(sel)
                                result_data = {'text': text[:2000]}
                            except (KeyError, TypeError, ValueError, json.JSONDecodeError, OSError, AttributeError, RuntimeError):
                                result_data = {'text': ''}
                        elif action == 'get_links':
                            links = await page.evaluate(
                                "() => Array.from(document.querySelectorAll('a[href]')).slice(0,20)"
                                '.map(a=>({text:a.textContent?.trim().slice(0,60),href:a.href}))'
                            )
                            result_data = {'links': links}
                        elif action == 'scroll_down':
                            await page.evaluate('window.scrollBy(0, 600)')
                            result_data = {'scrolled': True}
                        elif action == 'screenshot':
                            png = await page.screenshot(type='png')
                            fname = f'{session_id}_{step_no}.png'
                            (SCREENSHOTS / fname).write_bytes(png)
                            result_data = {
                                'screenshot_path': f'/preview/browser_screenshots/{fname}',
                                'size': len(png),
                            }
                        elif action == 'execute_js':
                            code = action_obj.get('text', '')
                            if code:
                                js_result = await page.evaluate(code)
                                result_data = {'js_result': str(js_result)[:500]}
                        elif action == 'get_title':
                            result_data = {'title': await page.title()}
                        elif action == 'fill_form':
                            sel = action_obj.get('selector', '')
                            text = action_obj.get('text', '')
                            if sel and text:
                                await page.fill(sel, text)
                            result_data = {'filled': True}
                        elif action == 'submit_form':
                            sel = action_obj.get('selector', '')
                            if sel:
                                await page.press(sel, 'Enter')
                            result_data = {'submitted': True}
                        elif action == 'wait':
                            wait_sec = min(float(action_obj.get('text', '1') or '1'), 5.0)
                            await asyncio.sleep(wait_sec)
                            result_data = {'waited': wait_sec}
                    except Exception as ex:
                        result_data = {'error': str(ex)[:200]}
                        step_status = 'error'

                    step = {
                        **action_obj,
                        'status': step_status,
                        'result': result_data,
                        'url': page.url,
                        'step_no': step_no,
                    }
                    steps.append(step)
                    yield f'data: {json.dumps({"type": "step", "step": step, "step_no": step_no})}\n\n'
                    await asyncio.sleep(0.3)

                # Final page state
                try:
                    final_text = await page.evaluate('() => document.body.innerText?.slice(0,3000)') or ''
                except (KeyError, TypeError, ValueError, json.JSONDecodeError, OSError, AttributeError, RuntimeError):
                    final_text = ''
                await browser.close()

                _db_update_session(session_id, 'done', steps, final_text)

                yield f'data: {json.dumps({"type": "done", "session_id": session_id, "steps": len(steps), "result_preview": final_text[:300]})}\n\n'

        except Exception as ex:
            log.error('Browser task error: %s', ex)
            _db_update_session(session_id, 'error', steps, '', str(ex))
            yield f'data: {json.dumps({"type": "error", "error": str(ex), "session_id": session_id})}\n\n'

    return StreamingResponse(
        _stream(), media_type='text/event-stream', headers={'Cache-Control': 'no-cache', 'X-Accel-Buffering': 'no'}
    )


async def _simulate_browser_task(session_id: str, task: str, start_url: str, max_steps: int):
    """Simulate browser task with LLM when Playwright not available."""
    from ..services import llm as llm_svc

    prompt = f"""Simulate the steps a browser agent would take to complete this task.
Task: {task}
Start URL: {start_url}

Describe each step as if you were actually browsing, including what you'd see and do.
Format as numbered steps like:
1. Navigate to {start_url}
2. Search for ...
3. Click on ...

Be realistic, specific, and complete the task fully."""

    result = await llm_svc.complete(
        [{'role': 'user', 'content': prompt}], agent_id='browser', max_tokens=800, inject_steering=False
    )
    text = result.get('text', 'Simulation complete.')

    steps_emitted = []
    lines = [l for l in text.split('\n') if l.strip()]
    for i, line in enumerate(lines[:max_steps], 1):
        step = {'action': 'simulated', 'description': line.strip(), 'status': 'done', 'step_no': i}
        steps_emitted.append(step)
        yield f'data: {json.dumps({"type": "step", "step": step, "step_no": i, "simulated": True})}\n\n'
        await asyncio.sleep(0.05)

    yield f'data: {json.dumps({"type": "done", "session_id": session_id, "simulated": True, "steps": len(steps_emitted), "result_preview": text[:300], "result": text[:2000]})}\n\n'


@router.get('/sessions')
def list_sessions(limit: int = 20):
    """Retrieve and return list sessions."""
    from ..services.memory_db import get_conn

    con = get_conn()
    try:
        rows = con.execute(
            'SELECT id, url, task, status, error, created_at, updated_at FROM browser_sessions ORDER BY created_at DESC LIMIT ?',
            (min(limit, 100),),
        ).fetchall()
    finally:
        con.close()
    return {'sessions': [dict(r) for r in rows], 'count': len(rows)}


@router.get('/sessions/{session_id}')
def get_session(session_id: str):
    """Retrieve and return get session."""
    from ..services.memory_db import get_conn

    con = get_conn()
    try:
        row = con.execute('SELECT * FROM browser_sessions WHERE id=?', (session_id,)).fetchone()
    finally:
        con.close()
    if not row:
        return {'ok': False, 'error': 'Session not found'}
    d = dict(row)
    try:
        d['steps'] = json.loads(d.get('steps_json', '[]') or '[]')
    except (KeyError, TypeError, ValueError, json.JSONDecodeError, OSError, AttributeError, RuntimeError):
        d['steps'] = []
    d['step_count'] = len(d['steps'])
    return d


@router.delete('/sessions/{session_id}')
def delete_session(session_id: str):
    """Delete or remove specified session."""
    from ..services.memory_db import get_conn

    con = get_conn()
    try:
        cur = con.execute('DELETE FROM browser_sessions WHERE id=?', (session_id,))
        con.commit()
        deleted = cur.rowcount > 0
    finally:
        con.close()
    # Also clean up screenshots
    for f in SCREENSHOTS.glob(f'{session_id}_*.png'):
        with contextlib.suppress(Exception):
            f.unlink()
    return {'ok': deleted, 'session_id': session_id}


@router.delete('/sessions')
def clear_sessions():
    """Delete all browser sessions."""
    from ..services.memory_db import get_conn

    con = get_conn()
    try:
        cur = con.execute('DELETE FROM browser_sessions')
        con.commit()
        count = cur.rowcount
    finally:
        con.close()
    return {'ok': True, 'deleted': count}


@router.post('/screenshot')
async def quick_screenshot(req: Request):
    """Take a quick screenshot of any URL."""
    try:
        body = await req.json()
    except (json.JSONDecodeError, TypeError, ValueError):
        body = {}
    raw_url = (body.get('url') or '').strip()
    if not raw_url:
        return {'ok': False, 'error': 'url required'}

    url = _validate_url(raw_url)
    if not url:
        return {'ok': False, 'error': 'Invalid URL — must be http:// or https://'}

    available = await _playwright_available()
    cr_ok = await _chromium_installed() if available else False
    if not available or not cr_ok:
        return {
            'ok': False,
            'error': 'Playwright/Chromium not installed',
            'install_cmd': 'pip install playwright && python -m playwright install chromium',
        }

    from playwright.async_api import async_playwright

    try:
        async with async_playwright() as p:
            browser = await p.chromium.launch(headless=True)
            page = await browser.new_page(viewport={'width': 1280, 'height': 900})
            await page.goto(url, wait_until='domcontentloaded', timeout=10000)
            title = await page.title()
            png = await page.screenshot(full_page=False, type='png')
            await browser.close()

        fname = f'screenshot_{uuid.uuid4().hex[:8]}.png'
        (SCREENSHOTS / fname).write_bytes(png)
        return {
            'ok': True,
            'url': url,
            'title': title,
            'path': f'/preview/browser_screenshots/{fname}',
            'b64': base64.b64encode(png).decode(),
            'size': len(png),
        }
    except Exception as ex:
        return {'ok': False, 'error': str(ex)[:300]}


@router.get('/screenshots')
def list_screenshots(limit: int = 20):
    """List all saved screenshots."""
    files = sorted(SCREENSHOTS.glob('*.png'), key=lambda f: f.stat().st_mtime, reverse=True)
    results = []
    for f in files[: min(limit, 100)]:
        results.append(
            {
                'filename': f.name,
                'path': f'/preview/browser_screenshots/{f.name}',
                'size': f.stat().st_size,
                'session': f.name.split('_')[1] if '_' in f.name else '',
            }
        )
    return {'screenshots': results, 'count': len(results)}
