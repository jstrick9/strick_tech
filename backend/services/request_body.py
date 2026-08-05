"""Parse a JSON request body, telling "empty" apart from "malformed".

THE BUG
───────
179 handlers across 44 routers do this:

    try:
        body = await req.json()
    except (json.JSONDecodeError, TypeError, ValueError):
        body = {}

The intent is sound — many POSTs in this platform legitimately carry no body
at all (`/api/control/runs/kill-all`, `/api/agent-identity/provision-all`), so
an empty request must not be an error.

But the same `except` also swallows genuinely broken input. Verified against
the running server:

    POST /api/specs     Content-Type: application/json     body: not json
    -> 200 {"ok": true, "spec": {"title": "Untitled Feature", ...}}

    POST /api/webhooks  Content-Type: application/json     body: not json
    -> 200 {"ok": true, "name": "Webhook", "secret": "...", ...}

A client with a serialisation bug gets a cheerful 200 and a junk record in the
database. Nobody finds out until someone wonders why their spec list is full
of "Untitled Feature". Worse, the client never learns it is broken.

THE DISTINCTION
  no body at all        -> {}    (legitimate, keep working)
  whitespace only       -> {}    (same thing over the wire)
  valid JSON object     -> parsed
  valid JSON non-object -> 400   ("[1,2,3]" is not a set of fields)
  malformed JSON        -> 400   (the client is broken; say so)

Returning 400 here is also what makes the failure visible in the UI:
`frontend/js/00-net-feedback.js` reports on status, so a 200 produces silence.
"""

from __future__ import annotations

import json
from typing import Any

from fastapi import Request
from fastapi.responses import JSONResponse


class MalformedBodyError(Exception):
    """Raised when a body was sent but could not be parsed as a JSON object."""

    def __init__(self, detail: str) -> None:
        super().__init__(detail)
        self.detail = detail

    def response(self) -> JSONResponse:
        return JSONResponse(
            {
                'ok': False,
                'error': f'Malformed request body: {self.detail}',
                'hint': 'Send a JSON object, or no body at all.',
            },
            status_code=400,
        )


async def json_body(req: Request) -> dict[str, Any]:
    """Return the parsed body, or {} when none was sent.

    Raises MalformedBodyError when bytes were sent that are not a JSON object.
    """
    # Reading the raw bytes is what lets "no body" be told apart from
    # "malformed body" — req.json() collapses both into one exception.
    #
    # Some callers pass a lightweight stand-in that only implements .json()
    # (test doubles, and internal code that constructs a request-like object).
    # Fall back for those rather than requiring every caller to grow a .body().
    if not hasattr(req, 'body'):
        try:
            parsed = await req.json()
        except Exception as exc:  # noqa: BLE001 — any parse failure is malformed
            raise MalformedBodyError(str(exc)) from exc
        return parsed if isinstance(parsed, dict) else {}

    raw = await req.body()
    if not raw or not raw.strip():
        return {}

    try:
        parsed = json.loads(raw)
    except (json.JSONDecodeError, UnicodeDecodeError) as exc:
        raise MalformedBodyError(str(exc)) from exc

    if parsed is None:
        return {}
    if not isinstance(parsed, dict):
        raise MalformedBodyError(
            f'expected a JSON object, got {type(parsed).__name__}'
        )
    return parsed


async def json_body_or_error(req: Request) -> tuple[dict[str, Any] | None, JSONResponse | None]:
    """Non-raising variant for handlers that return responses directly.

    Usage:
        body, err = await json_body_or_error(req)
        if err:
            return err
    """
    try:
        return await json_body(req), None
    except MalformedBodyError as exc:
        return None, exc.response()


# ── Field coercion ────────────────────────────────────────────────────────────
# 22 POST endpoints returned HTTP 500 when a field arrived with the wrong type.
# The cause is uniform: `(body.get('title') or '').strip()` assumes a string,
# and an int, list or dict has no .strip(), so the handler raises AttributeError
# and FastAPI turns it into a 500.
#
#     POST /api/goals   {"title": 12345}   ->  500 Internal Server Error
#     POST /api/chat    {"message": 12345} ->  500 Internal Server Error
#
# A 500 is the wrong answer twice over: it says "the server is broken" when the
# request was, it is the status most likely to page someone, and it can expose
# a stack trace. The adjacent lines in the same handlers already do this
# correctly with `str(body.get('model') or '')`, so this is an oversight rather
# than a decision.
#
# A null byte is stripped as well. SQLite stores it happily, but it truncates
# C-style strings in downstream tooling and displays as a control character in
# the UI, so it is never something a user meant to send.

# 1 MiB. Generous for any single text field this platform accepts (chat
# messages already cap at 16k) while stopping a 10MB title from being written
# to the database -- verified accepted before this guard.
MAX_FIELD_CHARS = 1_048_576


def as_text(value: Any, *, limit: int = MAX_FIELD_CHARS) -> str:
    """Coerce a JSON field to a clean string. Never raises.

    None becomes '', which preserves the `or ''` semantics the call sites rely
    on. Non-strings are stringified rather than rejected: a client sending
    {"title": 123} plainly means "123", and refusing it would be a behaviour
    change on top of a crash fix.
    """
    if value is None:
        return ''
    if not isinstance(value, str):
        # dict/list stringify to their repr, which is not useful as a title but
        # is honest, bounded, and does not crash.
        value = str(value)
    if '\x00' in value:
        value = value.replace('\x00', '')
    if len(value) > limit:
        value = value[:limit]
    return value.strip()


def text_field(body: dict[str, Any], key: str, *, default: str = '',
               limit: int = MAX_FIELD_CHARS) -> str:
    """`as_text(body.get(key))` with a default for the missing/empty case."""
    out = as_text(body.get(key), limit=limit)
    return out if out else default
