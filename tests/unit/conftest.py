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
# This MUST happen at import time, before any `backend.*` module is imported.
# Roughly 40 routers call _ensure_schema() at module scope, so their tables are
# created against whichever database is resolved during import. A fixture — even
# a session-scoped autouse one — runs too late: the schema would already have
# been built in production agentic.db and the sandbox would be missing ~40
# tables, which surfaces as mass HTTP 500 "no such table" errors.
#
# The previous version of this file set AGENTIC_TEST_DB in a fixture, and
# nothing in the backend read that variable at all. The docstring promised
# "unit tests never touch production agentic.db" while every run wrote straight
# into it — proven by watching prompt_library go from 503 to 511 rows during a
# single test file. Residue from that has interfered with six module reviews.
_TEST_DB_DIR = Path(tempfile.mkdtemp(prefix="agentic-unit-db-"))
os.environ["AGENTIC_TEST_DB"] = str(_TEST_DB_DIR / "test.db")

# ── Isolated data DIRECTORY so unit tests never write into the real repo ─────
# AGENTIC_TEST_DB above sandboxes the DATABASE. It does nothing for the
# FILESYSTEM: backend/config.py's get_data_dir() returns the repo root unless
# AGENTIC_OS_DATA_DIR is set, and ~20 routers derive write paths from it
# (ROOT/'preview', ROOT/'workspaces', ROOT/'brain', ...).
#
# The damage was measured, not assumed: 1158 directories under workspaces/ and
# 3135 files COMMITTED TO GIT, with 25 workspaces named ActivateWS_*, SysWS_*
# and "Regress WS Activate" appearing in the user's real workspace list. The
# Module 18 review found the user's actual projects buried in test output.
#
# Redirecting ROOT wholesale would break the many legitimate READS of static
# repo content (frontend/js/*.js, backend/, requirements.txt, templates/...),
# which is presumably why this was never done. So the sandbox is a temp dir
# that SYMLINKS the read-only repo paths and provides real, empty directories
# for everything the app writes to. Reads still resolve to the real files;
# writes land in the temp tree and are discarded.
#
# Set at import time for the same reason as the DB above: ~40 routers resolve
# these paths at module scope, so a fixture runs far too late.
_TEST_DATA_DIR = Path(tempfile.mkdtemp(prefix="agentic-unit-data-"))

# Directories the application WRITES to — created empty in the sandbox.
_WRITABLE_DIRS = (
    "preview", "workspaces", "memory", "brain", "plugins", "skills",
    ".agentic", "logs", "uploads", "exports",
)
# Repo content the application READS — symlinked back to the real thing so
# reads see live files without the sandbox holding a stale copy.
_READONLY_LINKS = (
    "frontend", "backend", "scripts", "agents", "tools",
    "contracts", "requirements.txt", "package.json", "config.yaml",
    "VERSION", "README.md",
)

# Directories that must be REAL, not symlinks, because safe_path() resolves
# symlinks before its containment check — correctly, since that is exactly how
# a symlink is used to escape a sandbox. A symlinked templates/ therefore
# resolves to the repo, fails `target.relative_to(root)`, and safe_path()
# returns None: github.py's directory allowlist started rejecting "templates"
# and "docs" as invalid. That was the SANDBOX being wrong, not the security
# control. These are small (templates 205K, docs 332K) so they are copied.
_READONLY_COPIES = ("templates", "docs")

for _name in _WRITABLE_DIRS:
    (_TEST_DATA_DIR / _name).mkdir(parents=True, exist_ok=True)

for _name in _READONLY_LINKS:
    _src = ROOT / _name
    if _src.exists():
        try:
            (_TEST_DATA_DIR / _name).symlink_to(_src, target_is_directory=_src.is_dir())
        except (OSError, NotImplementedError):
            pass  # symlinks unavailable (e.g. Windows without privilege)

import shutil as _shutil

for _name in _READONLY_COPIES:
    _src = ROOT / _name
    if _src.is_dir():
        _shutil.copytree(_src, _TEST_DATA_DIR / _name, dirs_exist_ok=True)
    else:
        (_TEST_DATA_DIR / _name).mkdir(parents=True, exist_ok=True)

os.environ["AGENTIC_OS_DATA_DIR"] = str(_TEST_DATA_DIR)


@pytest.fixture(scope="session", autouse=True)
def isolated_db():
    """Expose the sandbox path and prove it is not the production database."""
    db_path = Path(os.environ["AGENTIC_TEST_DB"])
    from backend.services.memory_db import db_path as resolved

    assert resolved() == db_path, (
        f"backend resolved {resolved()} but the sandbox is {db_path} — "
        "test isolation is not in effect"
    )
    assert "memory/agentic.db" not in str(resolved()), "refusing to run against production data"
    yield db_path

@pytest.fixture(scope="session", autouse=True)
def isolated_data_dir():
    """Prove the filesystem sandbox is in effect, not merely configured.

    Guards the specific regression that motivated it: unit tests creating
    workspaces inside the real repo. Asserted rather than trusted, because the
    previous DB sandbox spent months being "configured" while nothing read the
    variable.
    """
    from backend.config import get_data_dir

    resolved = get_data_dir()
    assert resolved == _TEST_DATA_DIR, (
        f"backend resolved data dir {resolved} but the sandbox is {_TEST_DATA_DIR} — "
        "filesystem isolation is not in effect"
    )
    assert resolved != ROOT, "refusing to run tests that write into the repo"

    from backend.routers import workspaces as ws_mod

    assert ws_mod.WS_DIR == _TEST_DATA_DIR / "workspaces", (
        f"workspaces router writes to {ws_mod.WS_DIR}, outside the sandbox"
    )
    yield resolved


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
