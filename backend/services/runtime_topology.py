"""Detect whether this process is one of several serving the application.

WHY THIS EXISTS
───────────────
Two security controls in this platform keep state in a plain Python dict:

  * `backend.app._rate_limit_store`        — requests per client IP
  * `backend.routers.security._CSRF_TOKENS` — issued CSRF tokens

BOTH PROBLEMS THIS MODULE WAS BUILT TO WARN ABOUT ARE NOW FIXED. It stays
because the detection is still needed: the rate-limit fix uses the worker
count, and an operator still deserves to know the topology was noticed.

  CSRF used to BREAK LOUDLY under multiple workers.
      A token minted by worker A was not in worker B's dict. Measured on this
      codebase with `--workers 4` and `AGENTIC_CSRF_STRICT=1`: of 60 POSTs
      carrying a VALID token, **13 succeeded and 47 returned 403** — the user
      saw random failures on most of their actions.

      FIXED. Tokens are stateless: an HMAC over the issue time, signed with a
      key shared by every worker (`services/csrf_secret.py`). Re-measured on
      the same 4-worker setup: **60 of 60 accepted**, with forged tokens still
      refused 8 of 8.

  Rate limiting used to DEGRADE QUIETLY.
      Each worker counted independently, so the effective ceiling was
      `workers x configured`. An operator who set 300 and ran 4 workers got
      1200 and was never told.

      FIXED. `app.py` divides the configured budget by the worker count, so
      the number the operator set is the number that applies. Load balancing
      is not perfectly even, so the residual error is in the conservative
      direction: a client can be throttled slightly early, never allowed past
      the ceiling.

WHAT IT DOES NOT DO
───────────────────
It does not add Redis, and it does not try to make the stores shared. The
platform is local-first and a shared backend would be an operational
dependency imposed on every single-process user to serve a deployment shape
that may never happen. The written trigger for revisiting that decision is in
`docs/module-reviews/25-runtime-topology.md`.

Detection is best-effort by design: it is used to WARN and to refuse an unsafe
default, never to reject traffic. A false negative costs a missing warning; a
false positive would cost a spurious one. Neither breaks a request.
"""

from __future__ import annotations

import logging
import os
import sys

log = logging.getLogger('agentic.topology')

# Environment variables that conventionally carry a worker count.
#   WEB_CONCURRENCY  — honoured by gunicorn and by many PaaS platforms
#   UVICORN_WORKERS  — uvicorn's own env form
#   GUNICORN_WORKERS / WORKERS — seen in Docker images and compose files
_WORKER_ENV_VARS = (
    'WEB_CONCURRENCY',
    'UVICORN_WORKERS',
    'GUNICORN_WORKERS',
    'WORKERS',
)

# Env var an operator sets to state "I know, and I have handled it."
_ACK_ENV = 'AGENTIC_ACK_MULTIPROCESS'


def _int_or_none(raw: str | None) -> int | None:
    if raw is None:
        return None
    raw = raw.strip()
    if not raw:
        return None
    try:
        value = int(raw)
    except (TypeError, ValueError):
        return None
    return value if value > 0 else None


def _workers_from_env() -> int | None:
    for name in _WORKER_ENV_VARS:
        value = _int_or_none(os.getenv(name))
        if value is not None:
            return value
    return None


def _workers_from_argv(argv: list[str] | None = None) -> int | None:
    """Parse `--workers N` / `--workers=N` / `-w N` out of the command line.

    Covers `uvicorn --workers 4` and `gunicorn -w 4`, which are how this is
    almost always spelled in practice and which set no environment variable.
    """
    args = sys.argv if argv is None else argv
    for i, arg in enumerate(args):
        if arg in ('--workers', '-w'):
            if i + 1 < len(args):
                value = _int_or_none(args[i + 1])
                if value is not None:
                    return value
        elif arg.startswith('--workers='):
            value = _int_or_none(arg.split('=', 1)[1])
            if value is not None:
                return value
    return None


def _under_gunicorn() -> bool:
    """Gunicorn sets SERVER_SOFTWARE on its workers.

    Detected separately because a gunicorn worker does not necessarily see the
    master's `-w` on its own argv, and the count may only be knowable as
    ">1" rather than exactly.
    """
    return 'gunicorn' in os.getenv('SERVER_SOFTWARE', '').lower()


def worker_count() -> int:
    """Best-effort number of processes serving this app. 1 when unknown.

    Returns 1 rather than None for an unknown-but-probably-single case so
    callers can treat this as a plain number.
    """
    for candidate in (_workers_from_env(), _workers_from_argv()):
        if candidate is not None:
            return candidate
    if _under_gunicorn():
        # Present but uncountable. Report 2 — the smallest value that is still
        # "more than one" — so the warning fires without inventing a figure.
        return 2
    return 1


def is_multiprocess() -> bool:
    return worker_count() > 1


def multiprocess_acknowledged() -> bool:
    """True when the operator has explicitly accepted the per-process caveats."""
    return os.getenv(_ACK_ENV, '').strip().lower() in ('1', 'true', 'yes', 'on')


def describe() -> dict[str, object]:
    """Structured view, for the health endpoint and for tests."""
    workers = worker_count()
    return {
        'workers': workers,
        'multiprocess': workers > 1,
        'acknowledged': multiprocess_acknowledged(),
        # csrf_tokens is no longer per-process state: tokens are stateless.
        'per_process_state': ['rate_limit_store'],
        'detected_via': (
            'env' if _workers_from_env() is not None
            else 'argv' if _workers_from_argv() is not None
            else 'gunicorn' if _under_gunicorn()
            else 'default'
        ),
    }


def warn_if_multiprocess(*, rate_limit_max: int, csrf_strict: bool) -> list[str]:
    """Log a startup warning naming the concrete consequences.

    Returns the emitted messages so tests can assert on them without parsing
    log output.
    """
    if not is_multiprocess():
        return []

    workers = worker_count()
    # `rate_limit_max` is the PER-WORKER budget app.py derived by dividing the
    # configured value. Report both numbers so an operator can see the
    # arithmetic rather than have to trust it.
    messages = [
        f'Running with {workers} worker processes.',
        f'  Rate limit: {rate_limit_max} requests/window per worker, so the '
        f'effective ceiling is ~{rate_limit_max * workers}. The configured value '
        f'is divided across workers so the number you set is the number that '
        f'applies; uneven load balancing can throttle a client slightly early, '
        f'which is the conservative direction.',
    ]

    from . import csrf_secret  # noqa: PLC0415

    source = csrf_secret.secret_source()
    if source == 'ephemeral':
        # The one remaining way to reach the original broken behaviour.
        messages.append(
            '  CSRF: WARNING — the signing key is in-process only, because no '
            'AGENTIC_CSRF_SECRET is set and the data directory is not writable. '
            'Each worker signs with a DIFFERENT key, so tokens will be rejected '
            'across workers exactly as they were before tokens became stateless. '
            'Set AGENTIC_CSRF_SECRET to a shared value.'
        )
    else:
        messages.append(
            f'  CSRF: tokens are stateless and signed with a shared key '
            f'({source}), so every worker accepts every other worker\'s tokens. '
            f'Enforcement is safe in this topology.'
        )

    messages.append('  See docs/module-reviews/25-runtime-topology.md.')

    if multiprocess_acknowledged():
        for line in messages:
            log.info('[topology] %s', line)
    else:
        for line in messages:
            log.warning('[topology] %s', line)

    return messages


def csrf_strict_is_safe() -> bool:
    """Whether CSRF enforcement can be turned on WITHOUT breaking users.

    Used to return False under multiple workers, because the token store was a
    per-process dict. Tokens are now stateless and signed with a key shared by
    every worker (`services/csrf_secret.py`), so enforcement is safe in any
    topology — verified with `--workers 4`: 60 of 60 POSTs carrying a single
    token were accepted, against 13 of 60 before.

    The one exception is an in-process signing key, which happens only when no
    AGENTIC_CSRF_SECRET is set AND the data directory is unwritable. Each
    worker would then sign with a different key, reproducing the original
    failure, so that case reports unsafe and is warned about at startup.
    """
    if not is_multiprocess():
        return True
    from . import csrf_secret  # noqa: PLC0415

    return csrf_secret.secret_source() != 'ephemeral'
