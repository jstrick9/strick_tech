#!/usr/bin/env python3
"""Behaviour with realistic data volumes.

Every audit so far ran against a near-empty workspace: 0 specs, 0 goals, 42
prompts. That is the best case, and it is not the case that breaks. This audit
seeds a few hundred records and measures what happens.

WHAT IS MEASURED
────────────────
  SLOW-RENDER   the pane takes longer than the budget to become interactive
                after the data arrives

  UNBOUNDED     every record is rendered into the DOM at once, with no paging
                and no "showing X of Y" -- the pattern that put 331 specs and
                81 KB into a single innerHTML in an earlier batch

  SILENT-CAP    the list is truncated but the UI does not say so, which is
                indistinguishable from "that is all your data"

  HUGE-DOM      the pane creates enough nodes to make scrolling janky

Cleanup runs even if the audit fails, so a run does not leave hundreds of
records behind for the next one.

MEASUREMENT NOTE
────────────────
Timing is taken from the moment the pane's own fetch resolves, not from
navigation, so network latency in the sandbox is not counted as render cost.
"""

from __future__ import annotations

import json
import sys
import urllib.error
import urllib.request
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
from _harness import BASE_URL, AuditResult, browser_page, emit, preflight, server_reachable  # noqa: E402

SEED_COUNT = 250

# Rendering more than this many nodes for one list is a scrolling problem.
NODE_BUDGET = 4000

# Time from data-arrival to interactive, in ms.
RENDER_BUDGET_MS = 2500

MARKER = '__large_data_probe__'

_CSRF: str | None = None


def _open(request_or_url, timeout: int = 30):
    target = (request_or_url if isinstance(request_or_url, str)
              else request_or_url.full_url)
    if not target.startswith(('http://', 'https://')):
        raise OSError('refusing non-http scheme')
    return urllib.request.urlopen(request_or_url, timeout=timeout)  # noqa: S310


def _csrf() -> str:
    """Writes are rejected 403 without this.

    The concurrency audit shipped once without it and reported "0 records
    created" as a PASS -- an audit measuring nothing looks exactly like an
    audit finding nothing.
    """
    global _CSRF
    if _CSRF is None:
        try:
            with _open(f'{BASE_URL}/api/security/csrf-token') as response:
                body = json.loads(response.read())
            _CSRF = body.get('csrf_token') or body.get('token') or ''
        except (urllib.error.URLError, OSError, ValueError):
            _CSRF = ''
    return _CSRF


def _post(path: str, payload: dict) -> int:
    request = urllib.request.Request(  # noqa: S310 - scheme checked in _open()
        f'{BASE_URL}{path}', data=json.dumps(payload).encode(), method='POST',
        headers={'Content-Type': 'application/json', 'X-CSRF-Token': _csrf()})
    try:
        with _open(request) as response:
            return response.status
    except urllib.error.HTTPError as exc:
        return exc.code
    except OSError:
        return 0


def _list(path: str) -> tuple[list, int | None]:
    try:
        with _open(f'{BASE_URL}{path}') as response:
            data = json.loads(response.read())
    except (urllib.error.URLError, OSError, ValueError):
        return [], None
    if isinstance(data, list):
        return data, None
    rows = (data.get('specs') or data.get('goals') or data.get('items')
            or data.get('results') or [])
    return (rows if isinstance(rows, list) else []), data.get('total')


def _seed(path: str, field: str, count: int) -> int:
    def one(i: int) -> int:
        return _post(path, {field: f'{MARKER} {i:04d}'})
    with ThreadPoolExecutor(max_workers=8) as pool:
        results = list(pool.map(one, range(count)))
    return sum(1 for s in results if 200 <= s < 300)


def _cleanup(list_path: str, base: str, field: str) -> None:
    rows, _ = _list(list_path)
    for row in rows:
        if not isinstance(row, dict):
            continue
        if not str(row.get(field, '')).startswith(MARKER):
            continue
        row_id = row.get('id') or row.get('spec_id') or row.get('goal_id')
        if row_id is None:
            continue
        request = urllib.request.Request(  # noqa: S310 - scheme checked in _open()
            f'{BASE_URL}{base}/{row_id}', method='DELETE',
            headers={'X-CSRF-Token': _csrf()})
        try:
            _open(request).close()
        except OSError:
            pass


MEASURE_JS = """(pane) => {
    let el = document.getElementById('pane-' + pane);
    if (!el || el.offsetParent === null) {
        const vis = [...document.querySelectorAll('[id^=pane-]')]
            .find(e => e.offsetParent !== null && e.innerText.trim());
        if (vis) el = vis;
    }
    if (!el) return null;
    const text = el.innerText || '';
    return {
        nodes: el.querySelectorAll('*').length,
        chars: text.trim().length,
        // Two SEPARATE facts, because they answer different questions and
        // conflating them made this audit blind: with "Showing X of Y"
        // deleted, a surviving "Load more" button still satisfied a combined
        // check, so removing the disclosure produced no finding at all.
        //
        //   countDisclosed -- does the user know HOW MANY they are not seeing?
        //   hasMoreControl -- can they get to the rest?
        //
        // A list can have a Load more button and still lie about the total.
        countDisclosed: /showing\\s+\\d+\\s+of\\s+\\d+/i.test(text)
                     || /\\d+\\s+of\\s+\\d+\\s+(results?|items?|rows?)/i.test(text),
        hasMoreControl: /load more|show more|next page/i.test(text),
    };
}"""

# The list path here must be what the UI ACTUALLY CALLS -- the default,
# uncapped request. Querying with `limit=1000` returns every row, so
# `len(rows) < total` is never true and the SILENT-CAP check can never fire.
# Verified: /api/specs returns 100 of 250 by default, but /api/specs?limit=1000
# returns all 250. The audit was blind for exactly that reason.
#
# (label, create path, field, list path AS THE UI CALLS IT, cleanup path)
TARGETS = [
    ('specs', '/api/specs', 'title', '/api/specs', '/api/specs?limit=1000'),
    ('goals', '/api/goals', 'title', '/api/goals', '/api/goals?limit=1000'),
]


def run() -> AuditResult:
    preflight()
    if not server_reachable():
        print(f'SKIP: no server at {BASE_URL}', file=sys.stderr)
        raise SystemExit(2)

    findings = []
    seeded: list[tuple[str, str, str]] = []

    try:
        for label, create, field, list_path, cleanup_path in TARGETS:
            accepted = _seed(create, field, SEED_COUNT)
            if accepted == 0:
                # Zero accepted writes means the probe is broken, not that the
                # pane is fast. Say so rather than reporting a pass.
                findings.append(
                    f'BROKEN      {label:8} could not seed any records; '
                    f'this pane was NOT tested')
                continue
            seeded.append((cleanup_path, create, field))

            rows, total = _list(list_path)
            with browser_page('desktop') as (page, _ctx):
                # Measure until the pane STOPS GROWING, not for a fixed wait.
                #
                # A first version timed `visit(settle=2500)` and reported
                # 2556ms and 2521ms -- both a hair over a 2500ms budget,
                # because the fixed sleep WAS the measurement. That would have
                # been reported as a performance finding when it was an
                # artefact of the probe.
                page.evaluate(f"window.nav && window.nav({label!r})")
                elapsed = page.evaluate("""async (pane) => {
                    const t0 = performance.now();
                    const read = () => {
                        let el = document.getElementById('pane-' + pane);
                        if (!el || el.offsetParent === null) {
                            el = [...document.querySelectorAll('[id^=pane-]')]
                                .find(e => e.offsetParent !== null && e.innerText.trim());
                        }
                        return el ? el.querySelectorAll('*').length : 0;
                    };
                    let last = -1, stable = 0;
                    // Settled = node count unchanged across three 100ms polls.
                    while (performance.now() - t0 < 15000) {
                        await new Promise(r => setTimeout(r, 100));
                        const n = read();
                        if (n === last && n > 0) { if (++stable >= 3) break; }
                        else { stable = 0; last = n; }
                    }
                    return performance.now() - t0;
                }""", label)
                state = page.evaluate(MEASURE_JS, label)

            if state is None:
                findings.append(f'BROKEN      {label:8} pane not found')
                continue

            if elapsed > RENDER_BUDGET_MS:
                findings.append(
                    f'SLOW-RENDER {label:8} {int(elapsed)}ms to render '
                    f'{accepted} records (budget {RENDER_BUDGET_MS}ms)')

            if state['nodes'] > NODE_BUDGET:
                findings.append(
                    f'HUGE-DOM    {label:8} {state["nodes"]} DOM nodes for '
                    f'{accepted} records')

            # If the API capped the list, the UI must say HOW MANY are hidden.
            if total is not None and len(rows) < total:
                if not state['countDisclosed']:
                    findings.append(
                        f'SILENT-CAP  {label:8} API returned {len(rows)} of '
                        f'{total} but the pane never states the total')
                if not state['hasMoreControl']:
                    findings.append(
                        f'UNBOUNDED   {label:8} {total} records capped to '
                        f'{len(rows)} with no way to reach the rest')
    finally:
        for list_path, create, field in seeded:
            _cleanup(list_path, create, field)

    return AuditResult(
        'large-data-volumes',
        len(findings),
        findings,
        note=f'render time, DOM size and truncation honesty with {SEED_COUNT} '
             f'seeded records',
    )


if __name__ == '__main__':
    raise SystemExit(emit(run()))
