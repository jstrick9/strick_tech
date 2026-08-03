"""
Agentic OS — Regression Test Configuration

Several regression tests exercise the agent-identity/token system for
existing default agents (e.g. issuing a token for "researcher", "brain",
or "creative"). Agent-identity provisioning is an intentional, explicit
Zero-Trust action (POST /api/agent-identity/provision-all) rather than
something the app does automatically at startup, so those tests would
otherwise only pass when another suite (tests/integration, tests/uat, or
tests/system) happened to provision identities earlier in the same test
run. This fixture makes tests/regression correctly runnable on its own,
matching the suite's own stated purpose of catching regressions
independently, regardless of what ran before it.
"""
from __future__ import annotations

import httpx
import pytest

BASE = "http://127.0.0.1:8787"


@pytest.fixture(autouse=True, scope="session")
def _ensure_agent_identities_provisioned():
    with httpx.Client(base_url=BASE, timeout=10) as c:
        try:
            c.post("/api/agent-identity/provision-all")
        except Exception:
            pass
    yield


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
