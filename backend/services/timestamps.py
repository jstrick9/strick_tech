"""Make API timestamps unambiguous.

THE PROBLEM
───────────
SQLite's `CURRENT_TIMESTAMP` -- used as a column default **141 times** across
this codebase -- stores UTC in the format `YYYY-MM-DD HH:MM:SS`, with **no
timezone designator**. A handful of routers also call naive
`datetime.now().isoformat()`.

`2026-08-08 14:42:08` is not a moment in time. It is a moment in an unstated
place, and every consumer has to guess. The browser's guess is the damaging
one:

    new Date('2026-08-08 14:42:08')   // interpreted as LOCAL time

So a UTC timestamp written by the server is rendered unshifted in the user's
zone. Nothing throws. The clock is simply wrong by the size of the offset, and
it is wrong in the direction that produces the most confusing possible output:
measured live with the browser in Australia/Eucla (UTC+8:45), a task created
*that second* displayed as **"in 3 minutes"** -- an event in the future that
had already happened.

WHY THIS IS FIXED AT THE BOUNDARY
─────────────────────────────────
The alternatives are worse:

  * Rewriting 141 schema defaults changes stored data and every query that
    compares against it, with no way to stop the 142nd being written.
  * Editing each router's serialisation is ~60 files and misses new ones.

Normalising on the way out covers every existing endpoint, every endpoint
added later, and cannot corrupt anything at rest because it never writes. It
is the same reasoning as `_restatus_refused_write`, which is why it runs in the
same buffering pass rather than adding a second one.

SCOPE, DELIBERATELY NARROW
──────────────────────────
  * Only values that match `YYYY-MM-DD[ T]HH:MM:SS[.ffffff]` exactly, i.e.
    already an ISO-8601 timestamp with the designator missing. A date-only
    value like `2026-08-08` is left alone: it is usually a calendar date
    (a due date, a birthday), and pinning it to a UTC instant would shift it
    across midnight for half the world -- turning a correct date into a wrong
    one.
  * Only keys that name a moment in time. A free-text field that happens to
    contain a timestamp-shaped substring is not rewritten.
  * Values that already carry `Z` or an offset are untouched.
"""

from __future__ import annotations

import re

# An ISO-8601 timestamp with the timezone designator missing. Anchored at both
# ends: a substring match would rewrite prose that merely contains a date.
_NAIVE = re.compile(r'^(\d{4}-\d{2}-\d{2})[T ](\d{2}:\d{2}:\d{2}(?:\.\d+)?)$')

# Keys whose value is a moment in time. Word-boundary style matching so
# `updated_at` and `created` match but `date_format` or `timeout` do not.
_TIME_KEY = re.compile(
    r'(^|_)(at|ts|time|timestamp|created|updated|modified|expires|started'
    r'|finished|completed|last_seen|last_run|last_login)($|_)',
    re.I)

# A response bigger than this is not worth walking on every request.
MAX_BYTES = 262144


def is_time_key(key: str) -> bool:
    return bool(_TIME_KEY.search(key))


def normalise_value(value: str) -> str:
    """Add the UTC designator to a naive timestamp; leave anything else alone.

    UTC is the correct assumption specifically because the naive values come
    from SQLite `CURRENT_TIMESTAMP`, which is documented to be UTC. This is not
    a guess applied to arbitrary input -- it is applied only to the format that
    function emits.
    """
    match = _NAIVE.match(value)
    if not match:
        return value
    return f'{match.group(1)}T{match.group(2)}Z'


def normalise(node, depth: int = 0):
    """Walk a decoded JSON structure, stamping naive timestamps under time keys.

    Returns the same object when nothing changed, so a caller can cheaply skip
    re-serialising an untouched response.
    """
    if depth > 12:
        return node
    if isinstance(node, dict):
        changed = False
        out = {}
        for key, value in node.items():
            if isinstance(value, str) and is_time_key(key):
                fixed = normalise_value(value)
                changed = changed or fixed is not value and fixed != value
                out[key] = fixed
            else:
                fixed = normalise(value, depth + 1)
                changed = changed or fixed is not value
                out[key] = fixed
        return out if changed else node
    if isinstance(node, list):
        changed = False
        out = []
        for item in node:
            fixed = normalise(item, depth + 1)
            changed = changed or fixed is not item
            out.append(fixed)
        return out if changed else node
    return node
