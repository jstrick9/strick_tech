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
