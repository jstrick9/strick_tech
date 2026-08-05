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
