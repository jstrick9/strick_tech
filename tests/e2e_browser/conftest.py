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


# ── Production-database guard ─────────────────────────────────────────────────
# These suites talk to a SEPARATE server process, so a pytest fixture setting
# AGENTIC_TEST_DB cannot redirect it — they have always written to whatever
# database that server opened, which in practice is memory/agentic.db. The
# accumulated residue has interfered with six module reviews.
#
# Set AGENTIC_REQUIRE_TEST_DB=1 to make that a hard failure instead of a silent
# one. Start the server with AGENTIC_TEST_DB pointing at a scratch file to
# satisfy it:
#
#   AGENTIC_TEST_DB=/tmp/agentic-test.db python run.py
#   AGENTIC_REQUIRE_TEST_DB=1 pytest tests/system
#
# Default is a warning, not an error, so the existing workflow keeps working.
def _assert_server_db_is_sandboxed() -> None:
    import os as _os
    import warnings

    import httpx as _httpx

    try:
        info = _httpx.get(f'{BASE}/api/health', timeout=5).json()
    except Exception:
        return  # the "is the server up" check elsewhere reports this properly

    if info.get('db_is_test_sandbox'):
        return

    message = (
        f"Live-server suite is running against a NON-SANDBOXED database: "
        f"{info.get('db_path') or 'unknown'}. Test data will be written to it. "
        f"Restart the server with AGENTIC_TEST_DB=/tmp/agentic-test.db to isolate it."
    )
    if _os.environ.get('AGENTIC_REQUIRE_TEST_DB'):
        raise RuntimeError(message)
    warnings.warn(message, stacklevel=2)


@pytest.fixture(scope='session', autouse=True)
def _db_sandbox_check():
    _assert_server_db_is_sandboxed()
