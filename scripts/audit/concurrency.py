#!/usr/bin/env python3
"""Duplicate records created by concurrent or repeated identical writes.

THE SCENARIO
────────────
A user double-clicks "Create". A flaky connection retries. A mobile browser
replays a request after a tab wake. Each of these sends the same POST twice,
and without server-side protection each one creates a separate record.

This audit fires N identical POSTs concurrently at each creating endpoint and
counts how many rows appear. Anything above 1 is a duplicate the user did not
ask for and will have to clean up by hand.

It also checks whether the standard mitigation -- an `Idempotency-Key` header,
where the server remembers the result of a key and replays it rather than
acting twice -- has any effect.

WHY THIS SEAM MATTERS
─────────────────────
It was flagged as a known gap early in the review and deferred as "lower
priority (client-side double-submit guard covers the common case)". A
client-side guard does not cover a retry, a replayed request, or two tabs. The
server is the only place this can be settled.
"""

from __future__ import annotations

import json
import sys
import urllib.error
import urllib.request
import uuid
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
from _harness import BASE_URL, AuditResult, emit, server_reachable  # noqa: E402

BURST = 5

# (label, create path, payload, list path, key that identifies our records)
TARGETS = [
    ('specs', '/api/specs', {'title': '__audit_dupe_probe__'},
     '/api/specs?limit=200', 'title'),
    ('goals', '/api/goals', {'title': '__audit_dupe_probe__'},
     '/api/goals?limit=200', 'title'),
    ('webhooks', '/api/webhooks',
     {'name': '__audit_dupe_probe__', 'agent_id': 'default'},
     '/api/webhooks', 'name'),
]


def _open(request_or_url, timeout: int = 20):
    """urlopen restricted to http(s).

    BASE_URL is developer-supplied, but refusing other schemes keeps `file:`
    out of an audit that issues writes.
    """
    target = (request_or_url if isinstance(request_or_url, str)
              else request_or_url.full_url)
    if not target.startswith(('http://', 'https://')):
        raise OSError(f'refusing non-http scheme: {target[:40]}')
    return urllib.request.urlopen(request_or_url, timeout=timeout)  # noqa: S310


_CSRF_TOKEN: str | None = None


def _csrf_token() -> str:
    """Fetch a CSRF token once and reuse it.

    Without this every write returned 403 and the audit reported "0 records
    created" as a PASS -- an audit that measures nothing looks identical to an
    audit that finds nothing. The first run of this probe did exactly that.
    """
    global _CSRF_TOKEN
    if _CSRF_TOKEN is None:
        try:
            with _open(f'{BASE_URL}/api/security/csrf-token') as response:
                payload = json.loads(response.read())
            _CSRF_TOKEN = payload.get('csrf_token') or payload.get('token') or ''
        except (urllib.error.URLError, OSError, ValueError):
            _CSRF_TOKEN = ''
    return _CSRF_TOKEN


def _post(path: str, payload: dict, idempotency_key: str | None = None):
    body = json.dumps(payload).encode()
    request = urllib.request.Request(  # noqa: S310 - scheme checked in _open()
        f'{BASE_URL}{path}', data=body, method='POST',
        headers={'Content-Type': 'application/json',
                 'X-CSRF-Token': _csrf_token()})
    if idempotency_key:
        request.add_header('Idempotency-Key', idempotency_key)
    try:
        with _open(request) as response:
            return response.status
    except urllib.error.HTTPError as exc:
        return exc.code
    except OSError:
        return 0


def _count_matching(list_path: str, field: str, needle: str) -> int:
    try:
        with _open(f'{BASE_URL}{list_path}') as response:
            data = json.loads(response.read())
    except (urllib.error.URLError, OSError, ValueError):
        return -1
    rows = data if isinstance(data, list) else (
        data.get('items') or data.get('specs') or data.get('goals')
        or data.get('webhooks') or data.get('results') or [])
    if not isinstance(rows, list):
        return -1
    return sum(1 for r in rows if isinstance(r, dict) and r.get(field, '') == needle)


def _delete_matching(list_path: str, field: str, needle: str, base: str) -> None:
    """Best-effort cleanup so the audit does not pollute the workspace."""
    try:
        with _open(f'{BASE_URL}{list_path}') as response:
            data = json.loads(response.read())
    except (urllib.error.URLError, OSError, ValueError):
        return
    rows = data if isinstance(data, list) else (
        data.get('items') or data.get('specs') or data.get('goals')
        or data.get('webhooks') or [])
    for row in rows if isinstance(rows, list) else []:
        if not isinstance(row, dict) or row.get(field, '') != needle:
            continue
        row_id = row.get('id') or row.get('spec_id') or row.get('goal_id')
        if row_id is None:
            continue
        request = urllib.request.Request(  # noqa: S310 - scheme checked in _open()
            f'{BASE_URL}{base}/{row_id}', method='DELETE',
            headers={'X-CSRF-Token': _csrf_token()})
        try:
            _open(request).close()
        except (urllib.error.URLError, OSError):
            pass


def run() -> AuditResult:
    if not server_reachable():
        print(f'SKIP: no server at {BASE_URL}', file=sys.stderr)
        raise SystemExit(2)

    findings = []
    duplicating = 0

    for label, create, payload, list_path, field in TARGETS:
        needle = payload[field]
        _delete_matching(list_path, field, needle, create)

        # 1. Concurrent identical writes with no idempotency key.
        with ThreadPoolExecutor(max_workers=BURST) as pool:
            statuses = list(pool.map(
                lambda _, c=create, pl=payload: _post(c, pl), range(BURST)))
        created = _count_matching(list_path, field, needle)
        accepted = sum(1 for s in statuses if 200 <= s < 300)

        if created < 0:
            findings.append(f'--     {label:10} could not read back the list; skipped')
            _delete_matching(list_path, field, needle, create)
            continue

        # An unkeyed client CAN still create duplicates, and that is by
        # design: two genuinely-intended identical records must remain
        # possible. What is not acceptable is the header having no effect, so
        # both paths are measured and only the keyed one is counted.
        if accepted == 0:
            # Zero accepted writes means the probe is broken (auth, payload
            # shape), not that the endpoint is safe. Reporting this as a pass
            # is how an audit silently stops auditing.
            findings.append(
                f'BROKEN {label:10} no write was accepted (statuses={statuses}); '
                f'this endpoint was NOT tested')
        else:
            findings.append(
                f'--     {label:10} {BURST} unkeyed concurrent POSTs created '
                f'{created} record(s) (no key means no dedupe, by design)')

        _delete_matching(list_path, field, needle, create)

        # 2. Does an Idempotency-Key change anything?
        # A fresh key per run. A fixed key is remembered by the server for
        # its TTL, so the SECOND run of this audit would replay the first
        # run's response, create nothing, and report a pass for the wrong
        # reason -- an audit that stops measuring while still looking green.
        key = f'audit-probe-{uuid.uuid4().hex}'
        with ThreadPoolExecutor(max_workers=BURST) as pool:
            list(pool.map(
                lambda _, c=create, pl=payload, k=key: _post(c, pl, k), range(BURST)))
        with_key = _count_matching(list_path, field, needle)
        if with_key > 1:
            duplicating += 1
            findings.append(
                f'DUPE   {label:10} Idempotency-Key IGNORED: {BURST} concurrent '
                f'requests with ONE key created {with_key} records')
        elif with_key == 1:
            findings.append(
                f'ok     {label:10} {BURST} concurrent requests with one '
                f'Idempotency-Key created 1 record')
        _delete_matching(list_path, field, needle, create)

    return AuditResult(
        'concurrent-duplicate-writes',
        duplicating,
        findings,
        note=f'endpoints where {BURST} concurrent POSTs sharing one '
             f'Idempotency-Key still create more than one record',
    )


if __name__ == '__main__':
    raise SystemExit(emit(run()))
