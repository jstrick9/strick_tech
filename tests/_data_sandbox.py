"""Shared in-process test sandbox: temp DB + temp data dir.

Extracted verbatim from tests/unit/conftest.py (r60) so every suite that
imports the backend in-process gets the same isolation the unit suite has:

  * AGENTIC_TEST_DB   -> temp database (nothing touches memory/agentic.db)
  * AGENTIC_OS_DATA_DIR -> temp data dir (nothing writes into the repo:
    workspaces/, plugins/, preview/, brain/, memory/, ...)
      - app WRITABLE dirs are created empty in the sandbox
      - repo READ paths (frontend/, backend/, scripts/...) are symlinked
        back so reads still resolve to the real files
      - templates/ and docs/ are COPIED, not symlinked, because safe_path()
        resolves symlinks before its containment check and would correctly
        reject a symlinked root as a sandbox escape (see unit conftest)
  * AGENTIC_OS_HOST   -> 127.0.0.1 (terminal auth gate runs as loopback)

Why a module and not a fixture: ~40 routers call _ensure_schema() and bind
get_data_dir() at module scope, so the environment must be in place at
CONFTEST IMPORT time — before any backend.* module is imported. A fixture,
even session-scoped autouse, runs far too late.

Idempotent: the first conftest to import this wins; later imports (another
suite's conftest in the same pytest session) are a no-op, so suites can be
run individually or together without fighting over the environment.

Proven necessary the hard way (see the unit conftest's own record): before
isolation, test runs left 1158 directories under workspaces/, 3133 stray
files in git, and prompt_library grew rows during a single test file. The
2026-09 workspace cleanup (#201) removed 407 test-artifact pack manifests
and 419 junk installed.json entries of exactly this provenance.
"""
from __future__ import annotations

import os
import shutil as _shutil
import sys
import tempfile
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]  # tests/ -> repo root
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

_ACTIVATED = False

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


def activate(prefix: str = "agentic-test") -> bool:
    """Activate the sandbox if no conftest already has. True if activated."""
    global _ACTIVATED
    if _ACTIVATED or os.environ.get("AGENTIC_OS_DATA_DIR"):
        return False

    # ── Isolated temp DB ────────────────────────────────────────────────────
    _db_dir = Path(tempfile.mkdtemp(prefix=f"{prefix}-db-"))
    os.environ.setdefault("AGENTIC_TEST_DB", str(_db_dir / "test.db"))

    # ── Isolated data directory ─────────────────────────────────────────────
    _data_dir = Path(tempfile.mkdtemp(prefix=f"{prefix}-data-"))
    for _name in _WRITABLE_DIRS:
        (_data_dir / _name).mkdir(parents=True, exist_ok=True)
    for _name in _READONLY_LINKS:
        _src = ROOT / _name
        if _src.exists():
            try:
                (_data_dir / _name).symlink_to(_src, target_is_directory=_src.is_dir())
            except (OSError, NotImplementedError):
                pass  # symlinks unavailable (e.g. Windows without privilege)
    for _name in _READONLY_COPIES:
        _src = ROOT / _name
        if _src.is_dir():
            _shutil.copytree(_src, _data_dir / _name, dirs_exist_ok=True)
        else:
            (_data_dir / _name).mkdir(parents=True, exist_ok=True)
    os.environ["AGENTIC_OS_DATA_DIR"] = str(_data_dir)

    # ── Loopback host for the terminal auth gate ────────────────────────────
    os.environ.setdefault("AGENTIC_OS_HOST", "127.0.0.1")

    _ACTIVATED = True
    return True
