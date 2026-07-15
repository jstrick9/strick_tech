"""Unit tests — Health, System Info, Static Assets"""
import pytest
from tests.unit.conftest import assert_ok


class TestHealth:
    def test_health_returns_200(self, client):
        r = client.get("/api/health")
        assert r.status_code == 200

    def test_health_ok_true(self, client):
        d = assert_ok(client.get("/api/health"))
        assert d["ok"] is True

    def test_health_has_version(self, client):
        d = assert_ok(client.get("/api/health"))
        assert "version" in d
        assert d["version"] == "6.0"

    def test_health_has_service_name(self, client):
        d = assert_ok(client.get("/api/health"))
        assert d["service"] == "Agentic OS"

    def test_frontend_index_served(self, client):
        r = client.get("/")
        assert r.status_code == 200
        assert "text/html" in r.headers["content-type"]

    def test_frontend_contains_html(self, client):
        r = client.get("/")
        assert b"<!DOCTYPE html>" in r.content or b"<html" in r.content

    def test_unknown_api_route_404(self, client):
        r = client.get("/api/this_route_does_not_exist_xyz")
        assert r.status_code == 404

    def test_health_content_type_json(self, client):
        r = client.get("/api/health")
        assert "application/json" in r.headers["content-type"]

    def test_health_no_auth_required(self, client):
        """Health endpoint must be publicly accessible."""
        r = client.get("/api/health")
        assert r.status_code != 401 and r.status_code != 403
