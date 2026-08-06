"""The signing key for stateless CSRF tokens.

WHY THIS EXISTS
───────────────
CSRF tokens used to be kept in a per-process dict (`_CSRF_TOKENS`). That is
correct for one uvicorn process and breaks under several: a token minted by
worker A is unknown to worker B. Measured on this codebase with `--workers 4`
and enforcement on: of 60 POSTs carrying a VALID token, 27 succeeded and 33
returned 403. The user sees random failures on about half their actions.

The previous mitigation was to detect the topology and refuse to enable
enforcement by default (`runtime_topology.csrf_strict_is_safe()`). That is a
guard, not a fix: it left multi-worker deployments permanently unable to run
with CSRF protection on.

The actual fix is to stop storing tokens at all. A CSRF token does not need a
server-side record — it needs to be unforgeable and expiring. An HMAC over
`issued_at` with a process-independent key gives both:

    token = <issued_at>.<nonce>.<hmac_sha256(key, "issued_at.nonce")>

Any worker can verify any token because they share the key, so the multi-worker
failure disappears. No Redis, no shared cache, no operational dependency added
to the single-process local-first deployment this platform is built around.

WHERE THE KEY COMES FROM, IN ORDER
──────────────────────────────────
1. `$AGENTIC_CSRF_SECRET`, then `$SECRET_KEY` — for operators who want to
   manage it themselves, and the only way to keep tokens valid across a rolling
   restart of a multi-host deployment.
2. A file under the data directory, created on first use with 0600.
   Generated once and reused, so tokens survive a restart and every worker on
   the host reads the same value.
3. A random in-process key, if the data directory is not writable. Tokens then
   do not survive a restart and are not shared between hosts, which is degraded
   but still correct for a single process. This is logged at WARNING because it
   silently reintroduces the multi-worker problem if workers are on separate
   filesystems.

WHY NOT JUST A RANDOM KEY PER PROCESS
─────────────────────────────────────
Because that is exactly the bug: every worker would sign with a different key
and reject each other's tokens. The file makes the key a property of the
deployment rather than the process.
"""
from __future__ import annotations

import logging
import os
import secrets
import threading

log = logging.getLogger('agentic.csrf')

_KEY_FILE_NAME = '.csrf_secret'  # noqa: S105 - a filename, not a credential
_lock = threading.Lock()
_cached: bytes | None = None
_source: str = 'unset'


def _data_dir() -> str | None:
    """The directory the app already uses for local state."""
    for var in ('AGENTIC_OS_DATA_DIR', 'AGENTIC_DATA_DIR'):
        value = os.environ.get(var)
        if value:
            return value
    # Fall back to the package's own data location if one is configured.
    try:
        from ..config import get_config  # noqa: PLC0415

        cfg = get_config()
        for attr in ('data_dir', 'data_directory'):
            value = getattr(cfg, attr, None)
            if value:
                return str(value)
    except Exception:  # pragma: no cover - config shape varies by deployment
        pass
    return None


def _from_env() -> bytes | None:
    for var in ('AGENTIC_CSRF_SECRET', 'SECRET_KEY'):
        raw = os.environ.get(var, '').strip()
        # A short key is worse than useless: it looks configured while being
        # brute-forceable, so it is refused rather than silently accepted.
        if raw and len(raw) >= 16:
            global _source
            _source = f'env:{var}'
            return raw.encode()
        if raw:
            log.warning(
                'CSRF: %s is set but shorter than 16 characters; ignoring it '
                'and falling back to the generated key file.', var,
            )
    return None


def _from_file() -> bytes | None:
    directory = _data_dir()
    if not directory:
        return None
    path = os.path.join(directory, _KEY_FILE_NAME)
    global _source
    try:
        if os.path.exists(path):
            with open(path, 'rb') as fh:
                data = fh.read().strip()
            if len(data) >= 32:
                _source = f'file:{path}'
                return data
            log.warning('CSRF: %s is too short to be a signing key; regenerating.', path)

        os.makedirs(directory, exist_ok=True)
        generated = secrets.token_hex(32).encode()
        # Write-then-rename so two workers racing on first start cannot leave a
        # truncated file that a third worker would read as the key.
        tmp = f'{path}.{os.getpid()}.tmp'
        with open(tmp, 'wb') as fh:
            fh.write(generated)
        os.chmod(tmp, 0o600)
        os.replace(tmp, path)
        _source = f'file:{path}'
        return generated
    except OSError as exc:
        log.warning('CSRF: could not use a key file at %s (%s).', path, exc)
        return None


def get_secret() -> bytes:
    """The HMAC key for signing and verifying CSRF tokens."""
    global _cached, _source
    if _cached is not None:
        return _cached
    with _lock:
        if _cached is not None:
            return _cached
        secret = _from_env() or _from_file()
        if secret is None:
            secret = secrets.token_hex(32).encode()
            _source = 'ephemeral'
            log.warning(
                'CSRF: using an in-process signing key. Tokens will not survive '
                'a restart and will NOT be accepted by other worker processes. '
                'Set AGENTIC_CSRF_SECRET, or make the data directory writable.'
            )
        _cached = secret
        return _cached


def secret_source() -> str:
    """Where the key came from — surfaced in diagnostics, never the key itself."""
    if _cached is None:
        get_secret()
    return _source


def reset_for_tests() -> None:
    """Drop the cached key so a test can exercise a different source."""
    global _cached, _source
    with _lock:
        _cached = None
        _source = 'unset'
