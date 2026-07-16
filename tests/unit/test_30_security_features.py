"""
Unit Tests — Security Features (CSRF Token & Request ID Tracing)
Covers: /api/security/csrf-token, /api/security/validate-csrf, /api/security/trace-context, X-Request-ID headers
"""
from __future__ import annotations
import pytest


class TestSecurityFeatures:
    """Suite testing CSRF tokens and request ID tracing middleware/endpoints."""

    def test_get_csrf_token_returns_200_and_cookie(self, client):
        r = client.get("/api/security/csrf-token")
        assert r.status_code == 200
        data = r.json()
        assert data["ok"] is True
        assert "csrf_token" in data
        assert len(data["csrf_token"]) > 16
        assert "agentic_os_csrf" in r.cookies

    def test_validate_csrf_token_valid(self, client):
        r = client.get("/api/security/csrf-token")
        token = r.json()["csrf_token"]

        r2 = client.post("/api/security/validate-csrf", json={"csrf_token": token})
        assert r2.status_code == 200
        data = r2.json()
        assert data["ok"] is True
        assert data["valid"] is True

    def test_validate_csrf_token_invalid(self, client):
        r = client.post("/api/security/validate-csrf", json={"csrf_token": "fake-token-1234"})
        assert r.status_code == 200
        data = r.json()
        assert data["ok"] is False
        assert data["valid"] is False

    def test_validate_csrf_token_via_header(self, client):
        r = client.get("/api/security/csrf-token")
        token = r.json()["csrf_token"]

        r2 = client.post(
            "/api/security/validate-csrf",
            json={"csrf_token": ""},
            headers={"X-CSRF-Token": token},
        )
        assert r2.status_code == 200
        assert r2.json()["valid"] is True

    def test_request_id_tracing_header_attached(self, client):
        r = client.get("/api/system/health")
        assert "X-Request-ID" in r.headers
        assert len(r.headers["X-Request-ID"]) > 0

    def test_request_id_tracing_custom_header_preserved(self, client):
        custom_id = "test-trace-id-999"
        r = client.get("/api/system/health", headers={"X-Request-ID": custom_id})
        assert r.headers.get("X-Request-ID") == custom_id

    def test_trace_context_endpoint(self, client):
        custom_id = "trace-ctx-123"
        r = client.get("/api/security/trace-context", headers={"X-Request-ID": custom_id})
        assert r.status_code == 200
        data = r.json()
        assert data["ok"] is True
        assert data["request_id"] == custom_id
        assert "timestamp" in data
        assert "client_ip" in data
