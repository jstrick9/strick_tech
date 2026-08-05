"""Detect whether this process is one of several serving the application.

WHY THIS EXISTS
───────────────
Two security controls in this platform keep state in a plain Python dict:

  * `backend.app._rate_limit_store`        — requests per client IP
  * `backend.routers.security._CSRF_TOKENS` — issued CSRF tokens

Both are correct for the single-process, local-first deployment the platform
is built around (`run.py` starts one uvicorn process). Neither survives being
run under multiple workers, and they fail in *opposite* directions:

  Rate limiting DEGRADES QUIETLY.
      Each worker counts independently, so the effective limit becomes
      `workers x configured`. Nothing is bypassed; the ceiling is just higher
      than the operator asked for. Nobody notices.

  CSRF BREAKS LOUDLY — but only once enforcement is on.
      A token minted by worker A is not in worker B's dict. Measured on this
      codebase with `--workers 4` and `AGENTIC_CSRF_STRICT=1`: of 60 POSTs
      carrying a VALID token, **27 succeeded and 33 returned 403**. The user
      sees random failures on roughly half their actions.

That second one is why this module is a prerequisite for turning CSRF
enforcement on by default rather than a nice-to-have. An operator who scales
out must find out at startup, not from a support ticket.

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
        'per_process_state': ['rate_limit_store', 'csrf_tokens'],
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
    messages = [
        f'Running with {workers} worker processes, but rate limiting and CSRF '
        f'tokens are stored PER PROCESS.',
        f'  Rate limit: each worker allows {rate_limit_max} requests/window, so '
        f'the effective limit is ~{rate_limit_max * workers}, not {rate_limit_max}.',
    ]

    if csrf_strict:
        # This one is not a degradation, it is an outage for the user.
        messages.append(
            '  CSRF: AGENTIC_CSRF_STRICT is ON. A token minted by one worker is '
            'unknown to the others, so roughly (workers-1)/workers of all '
            'state-changing requests will be rejected with 403 despite '
            'carrying a valid token. Set AGENTIC_CSRF_STRICT=0 or run a single '
            'worker until a shared token store exists.'
        )
    else:
        messages.append(
            '  CSRF: enforcement is off, so nothing breaks today — but do NOT '
            'enable AGENTIC_CSRF_STRICT in this topology; tokens are not shared '
            'between workers.'
        )

    messages.append(
        '  Run a single worker for correct enforcement, or see '
        'docs/module-reviews/25-runtime-topology.md.'
    )

    if multiprocess_acknowledged():
        for line in messages:
            log.info('[topology] %s', line)
    else:
        for line in messages:
            log.warning('[topology] %s', line)

    return messages


def csrf_strict_is_safe() -> bool:
    """Whether CSRF enforcement can be turned on WITHOUT breaking users.

    False under multiple workers, because the token store is per process.
    Used to keep the secure-by-default behaviour from becoming a self-inflicted
    outage on a topology it was never designed for.
    """
    return not is_multiprocess()
