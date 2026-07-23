"""Boundary tests for browser, MCP, and integration adapters."""

from backend.routers.browser_agent import _validate_url
from backend.routers.integrations import _safe_preview_path


def test_browser_blocks_internal_and_non_http_urls():
    assert _validate_url('http://127.0.0.1:8787/api/secrets') == ''
    assert _validate_url('http://169.254.169.254/latest/meta-data') == ''
    assert _validate_url('file:///etc/passwd') == ''
    assert _validate_url('https://example.com').startswith('https://example.com')


def test_integration_preview_path_blocks_sibling_escape():
    assert _safe_preview_path('../preview_evil/secret.txt') is None
    assert _safe_preview_path('safe/file.txt') is not None


def test_mcp_server_invalid_rate_limits_are_safe(client):
    response = client.post(
        '/api/mcp-gateway/servers',
        json={'name': 'Boundary MCP', 'rate_limit_rpm': 'not-a-number', 'rate_limit_day': -999},
    )
    assert response.status_code == 200
    assert response.json().get('ok') is True
