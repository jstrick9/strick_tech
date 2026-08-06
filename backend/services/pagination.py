"""Consistent, honest pagination for list endpoints.

THE PROBLEM
───────────
28 GET endpoints returned every row they had, with no `limit` parameter and no
paging in the UI. Measured: seeding 331 specs made `GET /api/specs` return
81 KB, and `specLoadList()` rendered all 331 into `innerHTML` in one pass with
no cap, no search and no paging. It does not freeze at 331; it grows
unboundedly with use and there is no point at which the product tells the user
anything is being left out.

The opposite failure is already documented in `26-autonomous-hunt.md`: goals
were capped at 100 of 724 and the UI said nothing, so 624 were simply
unreachable. Both bugs are the same mistake — the response does not describe
its own completeness.

THE CONTRACT
────────────
Every paginated list returns the same envelope:

    {
      "<key>":  [...],        # the page
      "count":  len(page),    # how many are in THIS response
      "total":  1234,         # how many exist in total
      "limit":  100,
      "offset": 0,
      "has_more": true        # is there anything after this page
    }

`total` and `has_more` are the part that matters. A client can always tell
whether it is looking at everything, which is exactly what both previous bugs
got wrong. `count` is kept because existing callers already read it, and it
keeps the same meaning it had when the list was complete.

DEFAULTS
────────
`limit` defaults to 100 and is clamped to [1, 500]. A NEGATIVE limit is clamped
too — `LIMIT -1` in SQLite means UNLIMITED, which is how `/api/audit?limit=-1`
previously returned 1398 rows against a cap of 2 (see `26-autonomous-hunt.md`).
`clamp_limit` exists so no call site has to remember that.
"""
from __future__ import annotations

from typing import Any

DEFAULT_LIMIT = 100
MAX_LIMIT = 500


def clamp_limit(limit: Any, *, default: int = DEFAULT_LIMIT, maximum: int = MAX_LIMIT) -> int:
    """A usable page size, whatever was asked for.

    Clamps on BOTH sides. A one-sided `min(limit, MAX)` still lets a negative
    through, and a negative LIMIT is unlimited in SQLite — that exact bug let
    `/api/audit?limit=-1` dump 1398 rows past a cap of 2.
    """
    try:
        value = int(limit)
    except (TypeError, ValueError):
        return default
    if value <= 0:
        return default
    return min(value, maximum)


def clamp_offset(offset: Any) -> int:
    """Never negative: a negative OFFSET is a SQL error on some backends and
    silently ignored on others, and neither is a useful answer."""
    try:
        value = int(offset)
    except (TypeError, ValueError):
        return 0
    return max(0, value)


def page(
    rows: list[Any],
    *,
    key: str,
    total: int,
    limit: int,
    offset: int,
    **extra: Any,
) -> dict[str, Any]:
    """Build the standard envelope around an already-sliced page of rows."""
    body: dict[str, Any] = {
        'ok': True,
        key: rows,
        'count': len(rows),
        'total': total,
        'limit': limit,
        'offset': offset,
        'has_more': (offset + len(rows)) < total,
    }
    body.update(extra)
    return body


def count_rows(con: Any, table: str, where: str = '', params: tuple = ()) -> int:
    """Total matching rows, for the `total` field.

    A second query rather than a window function: SQLite's COUNT(*) on an
    indexed table is cheap, and it keeps the page query unchanged and readable.
    """
    sql = f'SELECT COUNT(*) FROM {table}'  # noqa: S608 - table names are literals at call sites
    if where:
        sql += f' WHERE {where}'
    row = con.execute(sql, params).fetchone()
    return int(row[0]) if row else 0
