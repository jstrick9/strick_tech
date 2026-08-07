"""Replay the result of a repeated write instead of performing it twice.

THE PROBLEM
───────────
Measured against the running server: **5 concurrent identical POSTs create 5
records** on `/api/specs`, `/api/goals` and `/api/webhooks`, and an
`Idempotency-Key` header was ignored entirely.

Every one of these is an ordinary thing that happens to real users:

  * a double-click on "Create"
  * a browser or fetch-layer retry after a flaky connection
  * a request replayed when a mobile tab wakes
  * the same action fired from two open tabs

The user asked for one thing and got five, then has to clean up by hand.

WHY MIDDLEWARE AND NOT PER-ENDPOINT
───────────────────────────────────
There are ~390 write endpoints. A rule applied at one call site is a rule the
next call site forgets -- the "second door" pattern this review has hit six
times. Recording the response once, in the middleware every request already
passes through, covers every endpoint that exists today and every one added
later, by construction.

THE CONTRACT (matches the Stripe / IETF `Idempotency-Key` convention)
─────────────────────────────────────────────────────────────────────
  * A client sends `Idempotency-Key: <unique per user-intent>` on a write.
  * The FIRST request with that key executes normally; its status, body and
    content type are recorded.
  * Any LATER request with the same key returns the recorded response without
    re-executing the handler, with `Idempotency-Replayed: true` so a client
    can tell.
  * A request already in flight for that key gets 409 rather than being
    allowed to race it. This is what makes concurrent double-submits safe,
    not just sequential ones.
  * Keys expire, so this is a double-submit guard, not permanent storage.

DELIBERATE LIMITS
─────────────────
  * Only 2xx responses are recorded. Replaying a failure would prevent a
    legitimate retry after a transient error -- the opposite of the point.
  * No key means no change in behaviour. Nothing is dedeuplicated implicitly,
    because two genuinely-intended identical records must remain possible.
  * In-process storage. This platform runs as a local-first single instance;
    a multi-node deployment would need shared storage, and the code says so
    rather than pretending otherwise.
"""

from __future__ import annotations

import threading
import time
from dataclasses import dataclass, field

# How long a key is remembered. Long enough to cover a retry storm or a user
# double-clicking, short enough that the same key is reusable later and memory
# stays bounded.
TTL_SECONDS = 300

# Guard against a client sending an unbounded header.
MAX_KEY_LENGTH = 200

# Only these methods are protected. GET/HEAD are already idempotent by
# definition, and applying this to them would cache reads -- a different
# feature with different correctness rules.
PROTECTED_METHODS = ('POST', 'PUT', 'PATCH', 'DELETE')

# Ceiling on stored entries so a client generating unique keys in a loop
# cannot grow this without bound.
MAX_ENTRIES = 2000


@dataclass
class _Record:
    """A completed response, or a marker that one is in flight."""
    created_at: float
    in_flight: bool = True
    status: int = 0
    body: bytes = b''
    media_type: str = 'application/json'
    headers: dict = field(default_factory=dict)


_store: dict[str, _Record] = {}
_lock = threading.Lock()


def _prune(now: float) -> None:
    """Drop expired entries. Called under the lock."""
    expired = [k for k, v in _store.items() if now - v.created_at > TTL_SECONDS]
    for key in expired:
        _store.pop(key, None)
    if len(_store) > MAX_ENTRIES:
        # Oldest first; this is a double-submit guard, not a durable cache.
        for key, _ in sorted(_store.items(), key=lambda kv: kv[1].created_at)[
                :len(_store) - MAX_ENTRIES]:
            _store.pop(key, None)


def normalise_key(raw: str | None, method: str, path: str) -> str | None:
    """Scope a client key to its method and path.

    Two different endpoints must never collide just because a client reused a
    key, and a key sent on a GET is ignored.
    """
    if not raw:
        return None
    raw = raw.strip()
    if not raw or len(raw) > MAX_KEY_LENGTH:
        return None
    if method.upper() not in PROTECTED_METHODS:
        return None
    return f'{method.upper()} {path} {raw}'


def begin(key: str) -> tuple[str, _Record | None]:
    """Claim a key.

    Returns one of:
      ('proceed', None)    first caller; run the handler and call finish()
      ('replay',  record)  a completed response exists; return it verbatim
      ('conflict', None)   another request with this key is still running
    """
    now = time.time()
    with _lock:
        _prune(now)
        existing = _store.get(key)
        if existing is None:
            _store[key] = _Record(created_at=now, in_flight=True)
            # Prune AFTER inserting. Pruning first left the store one entry
            # over the ceiling, because the new record had not been counted
            # yet -- caught by test_store_is_bounded.
            _prune(now)
            return 'proceed', None
        if existing.in_flight:
            return 'conflict', None
        return 'replay', existing


def finish(key: str, status: int, body: bytes, media_type: str) -> None:
    """Record a completed response, or release the key if it should not be
    replayed."""
    with _lock:
        record = _store.get(key)
        if record is None:
            return
        # Only successful writes are replayable. A failure must stay
        # retryable, so the key is released rather than remembered.
        if not (200 <= status < 300):
            _store.pop(key, None)
            return
        record.in_flight = False
        record.status = status
        record.body = body
        record.media_type = media_type


def release(key: str) -> None:
    """Drop an in-flight claim, e.g. when the handler raised."""
    with _lock:
        record = _store.get(key)
        if record is not None and record.in_flight:
            _store.pop(key, None)


def reset() -> None:
    """Clear all state. For tests."""
    with _lock:
        _store.clear()


def stats() -> dict:
    with _lock:
        return {
            'entries': len(_store),
            'in_flight': sum(1 for r in _store.values() if r.in_flight),
        }
