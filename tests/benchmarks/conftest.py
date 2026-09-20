"""Benchmarks conftest — provides TestClient fixture (sandboxed).

r60: this suite imported backend.app in-process with NO isolation, so every
run read and wrote the production memory/agentic.db and repo data dir.
It now activates the shared sandbox (tests/_data_sandbox.py) at import time
— before backend.* is imported — so both the DB and all file writes land in
a temp dir. (The suite's own baseline_metrics.json output is a tracked file
the test refreshes by design — expect it to show as modified after a run.)
"""
import pytest

from tests._data_sandbox import activate as _activate_sandbox
_activate_sandbox(prefix="agentic-benchmarks")


@pytest.fixture(scope="module")
def client():
    from backend.app import app
    from fastapi.testclient import TestClient
    with TestClient(app, raise_server_exceptions=False) as c:
        yield c
