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
# ── Sandbox: temp DB + temp data dir (shared) ─────────────────────────────────
# r60: extracted verbatim to tests/_data_sandbox.py so the perf and benchmarks
# suites get the same isolation this suite has had; the full rationale and
# damage record (1158 stray workspaces/, 3135 files in git, prompt_library
# growing during a single test file) live in that module's docstring.
# Import-time activation is REQUIRED: ~40 routers bind the DB and data dir at
# module scope, so a fixture — even a session-scoped autouse one — runs far
# too late. Idempotent: a no-op if another suite's conftest already activated.
from tests._data_sandbox import activate as _activate_sandbox
_activate_sandbox(prefix="agentic-unit")


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
    sandbox = Path(os.environ["AGENTIC_OS_DATA_DIR"])
    assert resolved == sandbox, (
        f"backend resolved data dir {resolved} but the sandbox is {sandbox} — "
        "filesystem isolation is not in effect"
    )
    assert resolved != ROOT, "refusing to run tests that write into the repo"

    from backend.routers import workspaces as ws_mod

    assert ws_mod.WS_DIR == sandbox / "workspaces", (
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
# ── Obsidian vault guard ────────────────────────────────────────────────────
_REPO_ROOT = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))


def _vault_dir():
    vault = os.getenv("OBSIDIAN_VAULT_PATH", "")
    if vault and os.path.isdir(vault):
        return vault
    return os.path.join(_REPO_ROOT, "brain")


def _snapshot_tree(root):
    snap = {}
    try:
        for dirpath, _dirnames, filenames in os.walk(root):
            for fn in filenames:
                p = os.path.join(dirpath, fn)
                try:
                    if os.path.getsize(p) <= 1_000_000:
                        with open(p, "rb") as fh:
                            snap[os.path.relpath(p, root)] = fh.read()
                except OSError:
                    pass
    except OSError:
        pass
    return snap


def _restore_tree(root, snap):
    if not os.path.isdir(root):
        return
    for dirpath, _dirnames, filenames in os.walk(root):
        for fn in filenames:
            rel = os.path.relpath(os.path.join(dirpath, fn), root)
            if rel not in snap:
                try:
                    os.unlink(os.path.join(dirpath, fn))
                except OSError:
                    pass
    for rel, blob in snap.items():
        p = os.path.join(root, rel)
        try:
            current = open(p, "rb").read() if os.path.isfile(p) else None
            if current != blob:
                os.makedirs(os.path.dirname(p), exist_ok=True)
                with open(p, "wb") as fh:
                    fh.write(blob)
        except OSError:
            pass


@pytest.fixture(autouse=True)
def _guard_obsidian_vault():
    """Restore the Obsidian vault after any test that writes to it.

    Two test-written files were found committed to the repo
    (brain/agentic-os/unit-test-note.md and a percent-encoded traversal
    payload), and the daily-note flow writes brain/agentic-os/Daily/. The
    vault is user data rendered in the Obsidian pane — tests must leave it
    exactly as they found it, byte for byte, including tracked files (or
    the working tree is dirty after every run).
    """
    root = _vault_dir()
    before = _snapshot_tree(root) if os.path.isdir(root) else None
    yield
    if before is not None:
        _restore_tree(root, before)


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


# ── ICM module isolation ──────────────────────────────────────────────────────
import contextlib
import importlib as _importlib


@contextlib.contextmanager
def isolated_icm_dir(scratch, *module_names):
    """Point the ICM service modules at a scratch data dir, reloading them,
    and reload them BACK under the original data dir on exit.

    importlib.reload() re-executes a module IN PLACE: the object in
    sys.modules keeps whatever WORKSPACES_DIR the scratch env produced,
    forever, unless something reloads it again under the original env.
    Every ICM suite used setenv+reload with no restore, so whichever tmp
    dir the LAST such test used is where every later ICM call in the
    session looked. Reproduced: a template-deletion test's empty tmp dir
    stayed mounted, and a client-based export of the seeded 'home-ops'
    template 404'd (KeyError: 'ok') depending on pytest-randomly's seed.

    Yields the list of reloaded modules, in the order given.
    """
    original = os.environ.get('AGENTIC_OS_DATA_DIR')
    os.environ['AGENTIC_OS_DATA_DIR'] = str(scratch)
    mods = [_importlib.import_module(n) for n in module_names]
    for m in mods:
        _importlib.reload(m)
    try:
        yield mods
    finally:
        if original is None:
            os.environ.pop('AGENTIC_OS_DATA_DIR', None)
        else:
            os.environ['AGENTIC_OS_DATA_DIR'] = original
        for m in mods:
            _importlib.reload(m)
