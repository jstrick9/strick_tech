"""
Agentic OS — Unit Test Configuration & Shared Fixtures
Uses FastAPI TestClient so every test is in-process with no network I/O.
External calls (LLM, DuckDuckGo, file-system side-effects) are mocked.
"""
from __future__ import annotations
import json, os, sys, sqlite3, tempfile, time, uuid
from pathlib import Path
from unittest.mock import AsyncMock, MagicMock, patch
import pytest

# ── Make package importable ──────────────────────────────────────────────────
ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT))

# ── Isolated temp DB so unit tests never touch production agentic.db ─────────
@pytest.fixture(scope="session", autouse=True)
def isolated_db(tmp_path_factory):
    """Create a fresh in-memory-style SQLite DB for the test session."""
    db_dir = tmp_path_factory.mktemp("memory")
    db_path = db_dir / "test.db"
    os.environ["AGENTIC_TEST_DB"] = str(db_path)
    yield db_path

@pytest.fixture(scope="session", autouse=True)
def isolated_agentic_dir(tmp_path_factory):
    """Redirect .agentic/ writes (license.json, profile.json) to temp dir."""
    agentic_dir = tmp_path_factory.mktemp("agentic")
    os.environ["AGENTIC_TEST_DIR"] = str(agentic_dir)
    return agentic_dir

# ── TestClient (shared across all tests in one session) ────────────────────
@pytest.fixture(scope="session")
def client():
    """Create a single FastAPI TestClient for the entire session."""
    # Patch heavy services before importing app
    with patch("backend.services.llm.complete", new_callable=AsyncMock) as mock_llm, \
         patch("backend.services.llm.stream",   new_callable=AsyncMock) as mock_stream:

        mock_llm.return_value  = {"text": "mocked LLM response", "tokens": 10, "model": "test"}
        mock_stream.return_value = iter(["mocked ", "stream ", "chunk"])

        from backend.app import app
        from fastapi.testclient import TestClient
        with TestClient(app, raise_server_exceptions=False) as c:
            yield c

# ── Per-test fresh client (for tests needing isolation) ────────────────────
@pytest.fixture(autouse=True)
def reset_rate_limiter():
    """Reset the global rate limiter store before each test so tests don't get 429."""
    from backend.app import _rate_limit_store
    _rate_limit_store.clear()
    yield

@pytest.fixture
def fresh_client():
    from backend.app import app
    from fastapi.testclient import TestClient
    with TestClient(app, raise_server_exceptions=False) as c:
        yield c

# ── Shared helpers ──────────────────────────────────────────────────────────
def assert_ok(response, status=200):
    """Assert response is OK and return parsed JSON."""
    assert response.status_code == status, (
        f"Expected {status}, got {response.status_code}: {response.text[:200]}"
    )
    return response.json()

def assert_error(response, field="error"):
    """Assert response indicates an error."""
    d = response.json()
    assert d.get("ok") is False or field in d, f"Expected error, got: {d}"
    return d

def post_json(client, path, body):
    return client.post(path, json=body, headers={"Content-Type": "application/json"})

def patch_json(client, path, body):
    return client.patch(path, json=body, headers={"Content-Type": "application/json"})

def put_json(client, path, body):
    return client.put(path, json=body, headers={"Content-Type": "application/json"})
