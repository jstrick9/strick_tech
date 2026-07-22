"""Live browser product-experience smoke suite for Mission Control's primary path."""
import os
import signal
import socket
import subprocess
import sys
import time
from pathlib import Path

from playwright.sync_api import sync_playwright

ROOT = Path(__file__).resolve().parent.parent.parent


def _wait_for_port(port: int, timeout: int = 15) -> bool:
    start = time.time()
    while time.time() - start < timeout:
        with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as sock:
            if sock.connect_ex(('127.0.0.1', port)) == 0:
                return True
        time.sleep(0.2)
    return False


def _stop_old_engine() -> None:
    for entry in os.listdir('/proc'):
        if not entry.isdigit():
            continue
        try:
            cmdline = Path(f'/proc/{entry}/cmdline').read_bytes().decode(errors='ignore')
            if 'run.py' in cmdline and int(entry) != os.getpid():
                os.kill(int(entry), signal.SIGKILL)
        except Exception:
            pass


def run_product_experience_smoke() -> None:
    _stop_old_engine()
    server = subprocess.Popen(
        [sys.executable, 'run.py', '--no-browser'], cwd=ROOT,
        stdout=subprocess.PIPE, stderr=subprocess.PIPE, text=True,
    )
    if not _wait_for_port(8787):
        server.kill()
        raise RuntimeError('Product smoke server did not start on port 8787')

    errors: list[str] = []
    try:
        with sync_playwright() as playwright:
            browser = playwright.chromium.launch(headless=True)
            context = browser.new_context(viewport={'width': 1280, 'height': 900})
            page = context.new_page()
            page.add_init_script("""
              localStorage.setItem('agentic_os_onboarded', 'true');
              localStorage.setItem('agentic_os_theme', 'light');
              localStorage.removeItem('agentic_os_launchpad_hidden');
            """)
            page.on('console', lambda message: errors.append(message.text) if message.type == 'error' else None)
            page.on('pageerror', lambda error: errors.append(f'UNHANDLED: {error}'))
            page.goto('http://localhost:8787/', wait_until='domcontentloaded')
            time.sleep(1.5)
            page.evaluate("window.nav('chat'); window.startNewChatSession()")
            time.sleep(0.3)

            assert not errors, f'Console errors during product boot: {errors}'
            assert page.locator('#topbar #chat-model-control').count() == 1
            assert page.locator('#topbar #restart-engine-btn').count() == 1
            assert page.locator('#topbar-quick-actions').is_hidden()
            assert page.locator('#mission-launchpad-deck').is_visible()
            for outcome in ('Ask a question', 'Research a topic', 'Make a plan', 'Create something'):
                assert page.get_by_text(outcome, exact=True).count() == 1

            # An ordinary user can choose an outcome and edit the suggested prompt.
            page.get_by_text('Research a topic', exact=True).click()
            assert page.locator('#chat-input').input_value().startswith('Help me research this topic:')

            # Text attachment intake must show a removable visible chip before send.
            page.locator('#chat-file-input').set_input_files({
                'name': 'product-notes.md', 'mimeType': 'text/markdown',
                'buffer': b'# Product notes\nMake setup effortless.',
            })
            page.wait_for_selector('.chat-attachment-chip')
            assert 'product-notes.md' in page.locator('.chat-attachment-chip').inner_text()

            # Auto appearance follows the OS and preserves the user's Auto preference.
            page.emulate_media(color_scheme='dark')
            page.evaluate("window.applyTheme('auto')")
            assert page.evaluate("document.documentElement.getAttribute('data-theme-preference')") == 'auto'
            assert page.evaluate("document.documentElement.getAttribute('data-theme')") == 'dark'

            # Studio is a primary creator workflow: its editor must initialize
            # without CSP worker failures or a blank editor.
            page.evaluate("window.nav('studio')")
            page.wait_for_selector('#pane-studio.active .monaco-editor', timeout=7000)
            assert page.locator('#pane-studio.active .monaco-editor').count() == 1

            # Sweep the primary workspaces. Navigation itself must not create
            # hidden runtime failures as scripts and data visualizations load.
            for pane in ('templates', 'swarm', 'galaxy', 'hierarchy', 'kanban', 'settings', 'builder'):
                page.evaluate(f"window.nav('{pane}')")
                page.wait_for_selector(f'#pane-{pane}.active', timeout=4000)
                time.sleep(0.35)

            # Kanban is a complete core lifecycle: create through the UI, move
            # through the persisted API, render its new state, then clean up.
            task_title = f'Functional browser task {int(time.time())}'
            page.evaluate("window.nav('kanban')")
            page.locator('#pane-kanban button').filter(has_text='＋ Task').click()
            page.locator('#gm-input').fill(task_title)
            page.locator('#gm-btns').get_by_text('OK', exact=True).click()
            page.wait_for_selector('#gm-input', state='visible')
            page.locator('#gm-input').fill('builder')
            page.locator('#gm-btns').get_by_text('OK', exact=True).click()
            task_card = page.get_by_text(task_title, exact=True)
            task_card.wait_for(state='visible', timeout=5000)
            task_id = task_card.locator('xpath=ancestor::div[contains(@class, "kb-card")]').get_attribute('data-id')
            assert task_id
            page.evaluate("""async (id) => {
                await fetch('/api/tasks/' + encodeURIComponent(id), {
                  method: 'PATCH', headers: {'Content-Type': 'application/json'},
                  body: JSON.stringify({status: 'doing'})
                });
                await window.renderKanban();
              }""", task_id)
            assert page.locator('#kbcol-doing').get_by_text(task_title, exact=True).is_visible()
            page.evaluate("id => fetch('/api/tasks/' + encodeURIComponent(id), {method: 'DELETE'})", task_id)

            # Projects are a core separation boundary: create and remove one
            # entirely through the visible UI without disturbing the active project.
            workspace_name = f'Functional project {int(time.time())}'
            page.evaluate("window.nav('workspaces')")
            page.get_by_text('＋ New Project', exact=True).click()
            page.locator('#gm-input').fill(workspace_name)
            page.locator('#gm-btns').get_by_text('OK', exact=True).click()
            project_label = page.get_by_text(workspace_name, exact=True)
            project_label.wait_for(state='visible', timeout=5000)
            project_card = page.locator('.card').filter(has_text=workspace_name).first
            project_card.locator('button[onclick^="deleteWorkspace"]').click()
            page.locator('#gm-btns').get_by_text('Delete', exact=True).click()
            page.wait_for_timeout(400)
            assert page.get_by_text(workspace_name, exact=True).count() == 0

            # Memory lifecycle: create from the simple inline form, search the
            # saved item, then delete it through the rendered result action.
            memory_text = f'Functional memory {int(time.time())}'
            page.evaluate("window.nav('galaxy')")
            page.locator('#gx-ingest-text').fill(memory_text)
            page.locator('#gx-ingest-tags').fill('functional,smoke')
            page.locator('#galaxy-panel button').filter(has_text='+ Add').click()
            page.locator('#gx-search').fill(memory_text)
            page.locator('.galaxy-search-row button').click()
            memory_result = page.get_by_text(memory_text, exact=True)
            memory_result.wait_for(state='visible', timeout=5000)
            memory_card = memory_result.locator('xpath=ancestor::div[contains(@class, "gx-hit")]')
            memory_card.locator('.gx-delete-memory').click()
            page.locator('#gm-btns').get_by_text('Delete', exact=True).click()
            page.wait_for_timeout(400)
            assert not errors, f'Console errors during product interactions: {errors}'
            browser.close()
            print('✅ Product experience smoke passed cleanly.')
    finally:
        server.kill()
        try:
            server.wait(timeout=5)
        except Exception:
            pass


if __name__ == '__main__':
    run_product_experience_smoke()
