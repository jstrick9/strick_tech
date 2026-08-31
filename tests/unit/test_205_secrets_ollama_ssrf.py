"""
`/api/secrets/test-connection` — SSRF + Ollama config-injection regression (Gap #007).

`provider='ollama'` accepted a `url` straight from the request body and passed
it to `client.get()`, with no guard. The server would fetch any attacker-chosen
address (the cloud metadata service, an internal API, a LAN host) — an SSRF —
and on a 200 the attacker's URL was written to `os.environ['OLLAMA_BASE_URL']`
and `llm.OLLAMA_BASE`, redirecting all subsequent model traffic to that host.

Only a genuine local Ollama (this machine's loopback) should be accepted as a
base URL. The handler now validates via `_validate_ollama_base_url()` before
any fetch, so only localhost/loopback passes and the URL is never persisted
till it has passed.
"""
from __future__ import annotations

import pytest

from backend.routers.secrets import _validate_ollama_base_url


@pytest.mark.parametrize('url', [
    'http://localhost:11434',
    'http://127.0.0.1:8080',
    'http://127.9.9.9:11434',
    'http://[::1]:11434',
    'http://localhost',
    'http://localhost:11434/v1',
])
def test_localhost_ollama_urls_allowed(url):
    # Should not raise.
    _validate_ollama_base_url(url)


@pytest.mark.parametrize('url', [
    # Cloud metadata / link-local (SSRF targets).
    'http://169.254.169.254/latest/meta-data/',
    'http://metadata.google.internal/',
    'http://100.100.100.200/',
    # Private / LAN hosts.
    'http://192.168.1.5:11434',
    'http://10.0.0.1:11434',
    'http://localhost.evil.com:8080',   # hostname prefix trick
    'http://169.254.169.254.nip.io/',   # public name resolving private won't be allowed
    # Scheme / host abuses.
    'file:///etc/passwd',
    'ftp://localhost',
    'http://',
    '',
    'localhost:11434',                  # no scheme
])
def test_non_local_or_abusive_urls_rejected(url):
    with pytest.raises(ValueError):
        _validate_ollama_base_url(url)


def test_non_string_rejected():
    with pytest.raises(ValueError):
        _validate_ollama_base_url(None)
    with pytest.raises(ValueError):
        _validate_ollama_base_url(12345)
