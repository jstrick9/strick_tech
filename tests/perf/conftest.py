"""Performance test configuration — automatically starts a live local server if not already running."""
import pytest
import multiprocessing
import time
import urllib.request
import os

BASE = "http://127.0.0.1:8787"

def _run_server():
    import uvicorn
    from backend.app import app
    uvicorn.run(app, host="127.0.0.1", port=8787, log_level="error")

@pytest.fixture(scope="session", autouse=True)
def live_server():
    # Check if already running
    try:
        with urllib.request.urlopen(f"{BASE}/api/system/health", timeout=0.5) as r:
            if r.status == 200:
                yield None
                return
    except Exception:
        pass

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
    if proc and proc.is_alive():
        proc.terminate()
        proc.join(timeout=2)
