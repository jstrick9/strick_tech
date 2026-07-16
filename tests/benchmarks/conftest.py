"""Benchmarks conftest — provides TestClient fixture."""
import pytest
from fastapi.testclient import TestClient

@pytest.fixture(scope="module")
def client():
    from backend.app import app
    with TestClient(app, raise_server_exceptions=False) as c:
        yield c
