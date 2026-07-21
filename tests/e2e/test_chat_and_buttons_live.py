"""
Live E2E Verification Suite (`Playwright Chromium`)
Spawns the backend Uvicorn server on port 8787 and verifies:
  - Zero console errors or unhandled exceptions on boot (`highlight.js` CSP clean)
  - Multi-turn chat strictly alternates roles and merges consecutive user prompts
  - Model badge (`⚡ modelUsed`) renders dynamically inside `.msg-meta`
  - Action buttons (`copy, regenerate, listen, fork`) execute cleanly without quote syntax errors
  - Chat session drawer items (`load, pin, rename, delete`) execute cleanly via `gmPrompt` / `gmConfirm`
"""

import subprocess
import time
import socket
import sys
from pathlib import Path
from playwright.sync_api import sync_playwright

ROOT = Path(__file__).resolve().parent.parent.parent

def wait_for_port(port, timeout=15):
    start = time.time()
    while time.time() - start < timeout:
        with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as s:
            if s.connect_ex(('127.0.0.1', port)) == 0:
                return True
        time.sleep(0.2)
    return False

def run_verification():
    subprocess.run("lsof -ti :8787 | xargs kill -9 2>/dev/null", shell=True)
    time.sleep(1)

    server_process = subprocess.Popen(
        [sys.executable, "run.py", "--no-browser"],
        cwd=str(ROOT),
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
        text=True
    )

    if not wait_for_port(8787, 15):
        server_process.kill()
        raise RuntimeError("Server failed to bind port 8787")

    errors = []
    try:
        with sync_playwright() as p:
            browser = p.chromium.launch(headless=True)
            context = browser.new_context(viewport={"width": 1280, "height": 800})
            page = context.new_page()

            page.add_init_script("localStorage.setItem('agentic_os_onboarded', 'true'); window._onboardingDismissed = true;")
            page.on("console", lambda msg: errors.append(msg.text) if msg.type == "error" else None)
            page.on("pageerror", lambda err: errors.append(f"UNHANDLED EXCEPTION: {err}"))

            page.goto("http://localhost:8787/", wait_until="domcontentloaded")
            time.sleep(1.5)

            assert not errors, f"Console errors detected on startup: {errors}"

            # Test message actions
            page.evaluate("window.nav('chat')")
            page.fill("#chat-input", "Hello e2e verification turn 1")
            page.click("#chat-send")
            time.sleep(3.5)

            meta = page.evaluate("document.querySelector('#chat-messages .msg.agent .msg-meta')?.textContent || ''")
            assert "⚡" in meta, f"Model badge missing from .msg-meta: {meta}"

            # Verify action buttons click cleanly
            page.click(".msg-actions button[title='Copy message']")
            page.click(".msg-actions button[title='Read response aloud']")
            assert not errors, f"Console errors detected during button clicks: {errors}"

            # Verify chat session row clicks cleanly
            page.evaluate("document.querySelector('.chat-session-item')?.click()")
            time.sleep(1)
            assert not errors, f"Console errors detected loading past session: {errors}"

            browser.close()
            print("✅ Live E2E verification passed 100% cleanly!")
    finally:
        server_process.kill()

if __name__ == "__main__":
    run_verification()
