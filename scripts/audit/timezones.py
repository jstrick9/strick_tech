#!/usr/bin/env python3
"""Timestamps across timezone boundaries.

THE SEAM
────────
Every timestamp in the product crosses a boundary: the server writes it, the
browser renders it, and the two are not in the same place. Three failures are
measured, in increasing order of how badly they mislead:

  AMBIGUOUS-API   the server emits a timestamp with NO timezone designator.
                  `2026-08-08T12:25:13` is not a moment in time -- it is a
                  moment in an unstated place. `new Date()` in a browser reads
                  a bare string as LOCAL time, so a UTC value written by a
                  server in London is displayed unshifted in Charlotte and is
                  silently four hours wrong. Nothing errors; the number is
                  just incorrect.

  FUTURE-TIME     a "just now" event rendered in the future ("in 4 hours"), or
                  a relative label that disagrees with the absolute one. This
                  is what AMBIGUOUS-API looks like from the user's side, and
                  it is measured separately because it can also be caused by
                  the frontend alone.

  INVALID-DATE    the literal string "Invalid Date" or "NaN" on screen.

MEASUREMENT NOTES
─────────────────
  * The browser is run in a timezone deliberately far from the server's, with
    a non-hour offset, so a bug cannot hide behind a zero difference. Chose
    Australia/Eucla (UTC+8:45): a whole-hour zone would make an off-by-one-hour
    bug and a correct result look identical when the server is on the hour.
  * API timestamps are inspected as STRINGS from the JSON, not parsed. Parsing
    with a library that assumes UTC for naive values would paper over exactly
    the defect being looked for.
  * Only fields that are actually rendered are counted as findings; a naive
    timestamp in an internal field is recorded informationally. A bug the user
    cannot see is a different priority from one they can.
"""

from __future__ import annotations

import json
import re
import sys
import urllib.error
import urllib.request
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
from _harness import BASE_URL, AuditResult, chrome_path, emit, preflight  # noqa: E402

# UTC+8:45. A 45-minute offset means an off-by-one-hour error cannot be
# mistaken for a correct rendering, which a whole-hour zone would allow.
PROBE_TZ = 'Australia/Eucla'

# Endpoints that return timestamped records and are rendered in the UI.
ENDPOINTS = ['/api/tasks', '/api/goals', '/api/agents', '/api/specs']

# Keys whose value is a moment in time.
TIME_KEY = re.compile(r'(^|_)(at|time|timestamp|date|created|updated|modified)($|_)', re.I)

# An ISO-8601 timestamp WITHOUT a timezone designator: no trailing Z and no
# ±HH:MM offset. This is the ambiguous case.
NAIVE_ISO = re.compile(r'^\d{4}-\d{2}-\d{2}[T ]\d{2}:\d{2}:\d{2}(\.\d+)?$')
AWARE_ISO = re.compile(r'^\d{4}-\d{2}-\d{2}[T ]\d{2}:\d{2}:\d{2}(\.\d+)?(Z|[+-]\d{2}:?\d{2})$')


def _get(path: str):
    url = f'{BASE_URL}{path}'
    if not url.startswith(('http://', 'https://')):
        return None
    try:
        with urllib.request.urlopen(url, timeout=15) as r:  # noqa: S310
            return json.loads(r.read())
    except (urllib.error.URLError, OSError, ValueError):
        return None


def _walk_timestamps(node, prefix=''):
    """Yield (key_path, value) for every string that looks like a timestamp."""
    if isinstance(node, dict):
        for key, value in node.items():
            path = f'{prefix}.{key}' if prefix else key
            if isinstance(value, str) and TIME_KEY.search(key):
                yield path, value
            else:
                yield from _walk_timestamps(value, path)
    elif isinstance(node, list):
        for item in node[:5]:
            yield from _walk_timestamps(item, prefix + '[]')


def run() -> AuditResult:
    preflight()
    findings = []

    # ── 1. Are the server's timestamps unambiguous? ─────────────────────
    naive = {}
    aware = 0
    for endpoint in ENDPOINTS:
        body = _get(endpoint)
        if body is None:
            continue
        for path, value in _walk_timestamps(body):
            if NAIVE_ISO.match(value):
                naive.setdefault(f'{endpoint} {path}', value)
            elif AWARE_ISO.match(value):
                aware += 1

    if naive:
        sample = list(naive.items())[:6]
        findings.append(
            f'AMBIGUOUS-API  {len(naive)} timestamp field(s) carry no timezone; '
            'a browser reads these as LOCAL time: '
            + ', '.join(f'{k}={v}' for k, v in sample))

    # ── 2. What does a distant browser show? ────────────────────────────
    from playwright.sync_api import sync_playwright

    with sync_playwright() as p:
        browser = p.chromium.launch(executable_path=chrome_path(),
                                    args=['--no-sandbox', '--disable-dev-shm-usage'])
        context = browser.new_context(timezone_id=PROBE_TZ,
                                      viewport={'width': 1440, 'height': 900})
        page = context.new_page()
        try:
            page.goto(BASE_URL, wait_until='domcontentloaded', timeout=60000)
            page.wait_for_timeout(3500)

            for pane in ('kanban', 'goals', 'agents'):
                page.evaluate(f'window.nav && window.nav({json.dumps(pane)})')
                page.wait_for_timeout(600)

            text = page.evaluate('document.body.innerText')

            if re.search(r'Invalid Date|\bNaN\b(?!\w)', text):
                line = next((ln.strip() for ln in text.split('\n')
                             if re.search(r'Invalid Date|\bNaN\b', ln)), '')
                findings.append(f'INVALID-DATE   {line[:90]}')

            # A relative label pointing into the future for a record that was
            # just created is the user-visible face of a naive timestamp.
            #
            # Scoped to elements that CARRY a timestamp (a datetime attribute,
            # a title/aria-label holding one, or a time-ish class) rather than
            # searching all body text. The unscoped version matched the
            # onboarding modal's prose -- "...set up in 3 minutes" -- which is
            # marketing copy, not a rendered date. That is the same trap the
            # offline audit hit with "Private • Ollama • Offline": a probe that
            # can be satisfied by prose is not measuring the product, and it
            # fails in BOTH directions.
            future = page.evaluate(r'''() => {
                const re = /\bin \d+ (?:second|minute|hour|day)s?\b/;
                const out = [];
                const sel = 'time, [datetime], [data-time], [data-timestamp], '
                          + '[class*="time"], [class*="date"], [class*="ago"]';
                document.querySelectorAll(sel).forEach(el => {
                    const t = (el.innerText || '').trim();
                    if (re.test(t)) out.push(t.slice(0, 60));
                });
                return out;
            }''')
            if future:
                findings.append(
                    f'FUTURE-TIME    relative labels point into the future '
                    f'in {PROBE_TZ}: ' + ', '.join(sorted(set(future))[:5]))
        finally:
            browser.close()

    if aware and not naive:
        findings.append(
            f'-- {aware} timestamp field(s) checked, all carry a timezone')

    return AuditResult(
        'timezone-correctness',
        len([f for f in findings if not f.startswith('--')]),
        findings,
        note=f'timestamp ambiguity at the API and rendering in {PROBE_TZ}',
    )


if __name__ == '__main__':
    raise SystemExit(emit(run()))
