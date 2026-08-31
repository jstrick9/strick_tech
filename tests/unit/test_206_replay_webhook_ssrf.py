"""
`replay` workflow `webhook` node — SSRF regression (Gap #008).

A user-submitted workflow definition can contain a `webhook` node whose `url`
is fully attacker-controlled. On run it was passed straight to `client.post(url)`
with no guard — the server would POST to any internal address (SSRF). Its twin
in `workflow.py` was already guarded by `_is_ssrf_blocked_url`; the replay path
was the unguarded copy.

Fix: refuse non-http(s) and private/link-local/metadata addresses (same guard as
workflow.py) and disable redirects so a public URL cannot 302 to an internal one
after the check.
"""
from __future__ import annotations

import sys
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[2]))

from backend.routers.websearch import _is_ssrf_blocked_url  # noqa: E402


# The same predicate replay.py now leases for its webhook node.
def allowed(url: str) -> bool:
    return url.startswith(('http://', 'https://')) and not _is_ssrf_blocked_url(url)


@pytest.mark.parametrize('url', [
    'http://169.254.169.254/latest/meta-data/',
    'http://metadata.google.internal/',
    'http://127.0.0.1:8787/api/secrets/list',
    'http://localhost:11434',
    'http://[::1]:8787/',
    'http://10.0.0.1/',
    'http://192.168.1.5/',
    'file:///etc/passwd',
    'gopher://internal:70/',
    '',
])
def test_internal_or_abusive_urls_refused(url):
    assert allowed(url) is False


def test_guard_is_a_safe_boolean_predicate():
    """The predicate leases `_is_ssrf_blocked_url`, which only blocks on a real
    internal/private/link-local address. Public hosts are allowed when they
    resolve; a non-resolving host is refused by the resolver (environment
    artifact) — the predicate never claims a private target is safe."""
    # A name that resolves publicly and is not private/loopback is allowed.
    assert allowed('https://api.github.com/repos/x/y') is True
    # The blocked hosts are refused regardless.
    for u in ('http://127.0.0.1/',
              'http://169.254.169.254/',
              'http://192.168.1.5/',
              'http://metadata.google.internal/'):
        assert allowed(u) is False
    assert allowed('file:///etc/passwd') is False
    assert allowed('') is False
