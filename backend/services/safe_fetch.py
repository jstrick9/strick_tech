"""One SSRF guard for every outbound HTTP call the platform makes on request.

WHY THIS EXISTS
───────────────
Module 19 fixed SSRF in the plugin installer by putting `_url_is_safe()` inside
backend/routers/plugins.py. Module 20 then found the same primitive, unguarded,
in two more places — because a guard that lives in a router cannot be reused:

  MCP tool `http.get` (AGENT-CALLABLE, the worst of the three)
      POST /api/mcp/call {"tool":"http.get",
                          "args":{"url":"http://localhost:8787/api/connectors"}}
      -> {"ok": true, ..., "body": "{\"connectors\":[..."}
      The full internal API response, handed back to whoever asked. Also
      reached http://169.254.169.254/ (HTTP 401 = the connection succeeded).

  Outbound Webhook connector
      POST /api/connectors/conn_webhook/execute
           {"action":"post","payload":{"url":"http://169.254.169.254/..."}}
      -> {"ok": false, "status_code": 501, "response": "..."}
      A 501 is a RESPONSE, not a refusal — it reached the metadata service.

`http.get` matters most: it is a tool an agent can invoke. Everything in this
review about prompt injection (Module 19) becomes materially worse when the
model has a primitive that reads arbitrary internal URLs and returns the body.

This is the third repetition of a pattern this review keeps finding — a control
implemented at one call site while identical call sites go unprotected
(Module 17's /table/create, Module 19's two install routes). The fix is not
another local copy: it is one shared function, in services/, that every
outbound path calls, with a repo-wide test that fails if a new one appears.
"""

from __future__ import annotations

import ipaddress
import socket
from urllib.parse import urlparse

# Hostname fragments that are never legitimate targets for a user- or
# model-supplied URL.
_BLOCKED_HOST_PATTERNS = (
    'localhost', '127.', '0.0.0.0', '::1', '169.254.', '10.',
    '192.168.', 'metadata', '.internal', '.local',
)

# Named cloud metadata endpoints (AWS/GCP/Azure and Alibaba's 100.100.100.200).
_BLOCKED_HOSTS = frozenset({
    '169.254.169.254', 'metadata.google.internal', '100.100.100.200',
    'metadata.internal', '0.0.0.0', '::1', '[::1]', 'localhost',
})

ALLOWED_SCHEMES = ('http', 'https')

# Cap on response size for guarded fetches. An unbounded read of an attacker-
# chosen URL is a memory-exhaustion primitive on its own.
MAX_RESPONSE_BYTES = 5_000_000


class UnsafeURLError(ValueError):
    """Raised when a URL is refused by the SSRF guard."""


def url_is_safe(url: str, *, allow_private: bool = False) -> tuple[bool, str]:
    """Return (ok, reason). Refuses non-HTTP schemes and private/link-local hosts.

    `allow_private` exists for genuinely local integrations (a self-hosted
    Ollama, an MCP server on the same box). It is a SERVER-side decision passed
    by the calling code — never something a request body can set, because a
    flag the caller controls is a flag the attacker controls.
    """
    if not url or not isinstance(url, str):
        return False, 'No URL supplied'

    try:
        parsed = urlparse(url.strip())
    except ValueError:
        return False, 'Malformed URL'

    if parsed.scheme not in ALLOWED_SCHEMES:
        return False, f'Only http and https URLs are allowed (got {parsed.scheme or "none"})'

    host = (parsed.hostname or '').lower()
    if not host:
        return False, 'URL has no host'

    if allow_private:
        return True, ''

    if host in _BLOCKED_HOSTS:
        return False, f'Refusing to contact internal address: {host}'

    for pat in _BLOCKED_HOST_PATTERNS:
        if host == pat.rstrip('.') or host.startswith(pat) or host.endswith(pat):
            return False, f'Refusing to contact internal address: {host}'

    # Resolve and check the ACTUAL address. A public hostname can resolve to a
    # private IP (DNS rebinding), so matching the host string alone is the same
    # "check the label, not the thing" mistake as the SQL-prefix and
    # path-prefix bugs found earlier in this review.
    # Alternate IP encodings. Python's ipaddress does not parse integer or hex
    # forms such as 2130706433 or 0x7f000001 -- both of which are 127.0.0.1 and
    # are standard SSRF bypasses. This check came from websearch.py, which the
    # repo-wide test in test_80 flagged as a fourth hand-rolled guard: reading
    # it showed it was MORE thorough than the version I had written, so it was
    # merged in rather than replaced. Consolidation should keep the best of
    # each implementation, not flatten them to the newest one.
    try:
        if host.isdigit() or host.lower().startswith('0x'):
            alt = ipaddress.ip_address(int(host, 0))
            if alt.is_private or alt.is_loopback or alt.is_link_local or alt.is_reserved:
                return False, f'Refusing to contact internal address: {host} ({alt})'
    except (ValueError, OverflowError):
        pass  # ordinary hostname

    try:
        infos = socket.getaddrinfo(host, None)
    except socket.gaierror:
        return False, f'Could not resolve host: {host}'

    for info in infos:
        addr = info[4][0]
        try:
            ip = ipaddress.ip_address(addr)
        except ValueError:
            continue
        if ip.is_private or ip.is_loopback or ip.is_link_local or ip.is_reserved:
            return False, f'Host {host} resolves to a non-public address ({addr})'

    return True, ''


def require_safe_url(url: str, *, allow_private: bool = False) -> str:
    """Return the URL, or raise UnsafeURLError with the reason."""
    ok, reason = url_is_safe(url, allow_private=allow_private)
    if not ok:
        raise UnsafeURLError(reason)
    return url


async def safe_request(
    method: str,
    url: str,
    *,
    allow_private: bool = False,
    timeout: float = 15.0,
    **kwargs,
):
    """httpx request with the SSRF guard and redirects disabled.

    Redirects are NOT followed: a public URL that 302s to 169.254.169.254 walks
    straight past a check performed only on the original address. Callers that
    genuinely need redirects must re-validate each hop themselves.
    """
    import httpx

    require_safe_url(url, allow_private=allow_private)
    async with httpx.AsyncClient(timeout=timeout, follow_redirects=False) as client:
        resp = await client.request(method, url, **kwargs)
        if resp.is_redirect:
            location = resp.headers.get('location', '')
            raise UnsafeURLError(
                f'Refusing to follow a redirect to {location or "an unspecified location"}'
            )
        return resp
