"""Browser E2E test configuration — uses real Playwright Chromium and auto-spins up FastAPI backend."""
import pytest
import multiprocessing
import time
import urllib.request
from playwright.sync_api import sync_playwright

BASE = "http://127.0.0.1:8787"

def _run_server():
    import uvicorn
    from backend.app import app
    uvicorn.run(app, host="127.0.0.1", port=8787, log_level="error")

@pytest.fixture(scope="session", autouse=True)
def live_server():
    proc = multiprocessing.Process(target=_run_server, daemon=True)
    proc.start()
    for _ in range(40):
        try:
            with urllib.request.urlopen(f"{BASE}/api/system/health", timeout=1) as r:
                if r.status == 200:
                    break
        except Exception:
            time.sleep(0.25)
    yield proc
    if proc.is_alive():
        proc.terminate()
        proc.join(timeout=2)

@pytest.fixture(scope="session")
def browser():
    with sync_playwright() as p:
        b = p.chromium.launch(args=["--no-sandbox", "--disable-dev-shm-usage", "--disable-gpu"])
        yield b
        b.close()

@pytest.fixture
def page(browser):
    ctx = browser.new_context()
    pg  = ctx.new_page()
    yield pg
    ctx.close()
