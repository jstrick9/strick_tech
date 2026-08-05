"""Browser E2E test configuration — uses real Playwright Chromium and auto-spins up FastAPI backend."""
import pytest
import multiprocessing
import time
import urllib.request

# Import at module scope with no guard meant ALL 31 tests ERRORED rather than
# skipped wherever no browser was installed — which is every fresh machine, and
# was this sandbox for the whole review. An error says "the suite is broken";
# a skip says "this needs a browser". The distinction matters because phase 2
# of the CSP work is gated on someone being able to run these.
#
# scripts/ensure_browser.py now installs Chromium on first launch (see run.py
# and start.sh), so on a normal desktop install these run for real.
pytest.importorskip('playwright', reason='playwright not installed')
from playwright.sync_api import sync_playwright  # noqa: E402

BASE = "http://127.0.0.1:8787"

def _run_server():
    # BUG: this server inherited PYTEST_CURRENT_TEST from the parent pytest
    # process, and backend/app.py disables BOTH rate limiting and CSRF
    # validation whenever that variable is set:
    #
    #     if request.method in ('POST',...) and not os.environ.get('PYTEST_CURRENT_TEST'):
    #
    # So every security assertion this suite made about a live browser was
    # made against a server with those controls switched off.
    # `test_a_post_without_a_csrf_token_is_refused` could therefore never
    # pass -- a token-less POST returned 200, and the test reported "CSRF is
    # not enforced" against a build where it is. Confirmed against the
    # committed tree before any of this session's changes, so it is a
    # harness bug, not a regression.
    #
    # A test that cannot pass is as bad as one that cannot fail: this one
    # was the only guard on CSRF from a real browser, and it was dead.
    #
    # Clearing the variable in the CHILD only. The parent keeps it, so the
    # rest of pytest is unaffected; multiprocessing on Linux forks, so this
    # assignment does not leak back.
    import os
    os.environ.pop('PYTEST_CURRENT_TEST', None)
    # Rate limiting keys off the same flag. The browser suite issues far more
    # than the 300-request default, so raise the ceiling rather than
    # reintroducing the blanket bypass this is removing.
    os.environ.setdefault('RATE_LIMIT_MAX', '1000000')

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
    # A downloaded-but-unlaunchable Chromium is a real state: the 425MB binary
    # installs fine while the host lacks libnss3 etc. Skipping with the actual
    # reason is more useful than a stack trace repeated 31 times.
    try:
        with sync_playwright() as p:
            b = p.chromium.launch(args=["--no-sandbox", "--disable-dev-shm-usage", "--disable-gpu"])
            yield b
            b.close()
    except Exception as exc:
        msg = str(exc)
        if "missing dependencies" in msg or "libnss3" in msg or "Executable doesn" in msg:
            pytest.skip(
                "Chromium is not launchable on this host. Run: "
                "python -m playwright install --with-deps chromium"
            )
        raise

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

    problems = []
    if not info.get('db_is_test_sandbox'):
        problems.append(f"database {info.get('db_path') or 'unknown'}")
    # The filesystem half. Checking only the DB let every workspace, preview
    # file and export land in the real repo: 1158 stray directories and 3135
    # files committed to git before anyone noticed.
    if not info.get('data_dir_is_test_sandbox'):
        problems.append(f"data directory {info.get('data_dir') or 'unknown'}")
    if not problems:
        return

    message = (
        f"Live-server suite is running against NON-SANDBOXED storage: "
        f"{'; '.join(problems)}. Test data will be written to it. Restart the "
        f"server with AGENTIC_TEST_DB=/tmp/agentic-test.db and "
        f"AGENTIC_OS_DATA_DIR=/tmp/agentic-test-data to isolate it."
    )
    if _os.environ.get('AGENTIC_REQUIRE_TEST_DB'):
        raise RuntimeError(message)
    warnings.warn(message, stacklevel=2)


@pytest.fixture(scope='session', autouse=True)
def _db_sandbox_check():
    _assert_server_db_is_sandboxed()
