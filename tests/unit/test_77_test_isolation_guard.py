"""Repo-wide guard: the unit suite must not write into the real repository.

THE FAILURE THIS PREVENTS
─────────────────────────
tests/unit/conftest.py sandboxed the DATABASE via AGENTIC_TEST_DB but never the
FILESYSTEM. backend/config.py's get_data_dir() returns the repo root unless
AGENTIC_OS_DATA_DIR is set, and ~20 routers derive write paths from it. Measured
before the fix:

    workspaces/ on disk           1158 directories
    tracked by git                3135 files
    rows in the workspaces table   618, of which ONE was a real user project

The user's actual project was buried under 617 workspaces named UnitWS_*,
ActivateWS_*, "Regress WS Activate", and injection payloads like
"' OR '1'='1'; DROP TABLE agents; --" left by the security tests.

This is the second half of the isolation fix begun in 50cc986 (the DB half).
These tests fail loudly if either half regresses.
"""

from __future__ import annotations

import os
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[2]


def test_data_dir_env_var_is_set():
    assert os.environ.get('AGENTIC_OS_DATA_DIR'), (
        'AGENTIC_OS_DATA_DIR is unset — routers will write into the repo'
    )


def test_backend_resolves_the_sandbox_not_the_repo():
    """Asserted, not trusted: the DB sandbox spent months merely 'configured'."""
    from backend.config import get_data_dir

    resolved = get_data_dir()
    assert resolved != REPO_ROOT, 'get_data_dir() returns the repo root during tests'
    assert str(resolved).startswith('/tmp') or 'pytest' in str(resolved), (
        f'data dir {resolved} does not look like a temp sandbox'
    )


def test_workspaces_router_writes_inside_the_sandbox():
    """The specific regression: workspace creation landing in the repo."""
    from backend.routers import workspaces as ws

    assert REPO_ROOT not in ws.WS_DIR.parents and ws.WS_DIR != REPO_ROOT / 'workspaces', (
        f'workspaces router writes to {ws.WS_DIR}, inside the repo'
    )


def test_preview_dir_is_inside_the_sandbox():
    """preview/ is shared by ~20 modules; it must be sandboxed too."""
    from backend.routers import workspaces as ws

    assert ws.PREVIEW_DIR != REPO_ROOT / 'preview', (
        'preview/ resolves to the repo — tests will mutate real project files'
    )


def test_database_is_sandboxed():
    from backend.services.memory_db import db_path

    resolved = str(db_path())
    assert 'memory/agentic.db' not in resolved, 'tests resolve the production database'


def test_creating_a_workspace_does_not_touch_the_repo(client):
    """End-to-end proof, not just a path assertion."""
    before = set(p.name for p in (REPO_ROOT / 'workspaces').iterdir()) if (
        REPO_ROOT / 'workspaces').exists() else set()

    r = client.post('/api/workspaces', json={'name': 'IsolationProbe'})
    assert r.status_code == 200
    wid = r.json()['id']
    try:
        after = set(p.name for p in (REPO_ROOT / 'workspaces').iterdir()) if (
            REPO_ROOT / 'workspaces').exists() else set()
        assert after == before, f'test created {after - before} inside the real repo'
    finally:
        client.delete(f'/api/workspaces/{wid}')


def test_static_repo_content_is_still_readable():
    """The sandbox must not break legitimate reads of repo content.

    Redirecting the data dir wholesale would hide frontend/js, backend/,
    requirements.txt etc. The sandbox symlinks those back, so reads still work.
    """
    from backend.config import get_data_dir

    root = get_data_dir()
    for name in ('frontend', 'backend', 'requirements.txt'):
        assert (root / name).exists(), f'{name} is not reachable from the sandbox'


def test_templates_and_docs_are_real_directories_not_symlinks():
    """safe_path() resolves symlinks before its containment check — correctly.

    A symlinked templates/ resolves to the repo, fails relative_to(root), and
    safe_path() returns None: github.py's allowlist began rejecting 'templates'
    and 'docs' as invalid paths. That was the sandbox being wrong, not the
    security control, so these two are copied rather than linked.
    """
    from backend.config import get_data_dir

    root = get_data_dir()
    for name in ('templates', 'docs'):
        p = root / name
        if p.exists():
            assert not p.is_symlink(), (
                f'{name} is a symlink; safe_path() will reject paths under it'
            )
