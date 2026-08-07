#!/usr/bin/env python3
"""What a user sees when the server is down.

Forces every /api/ call to return HTTP 500, walks all panes, and reports two
distinct failures of honesty:

  SILENT   the pane renders a normal-looking empty state with no indication
           anything went wrong. An outage is indistinguishable from an empty
           account -- the user concludes their data is gone.

  JARGON   the pane shows internal detail where an explanation belongs:
           "HTTP 500", "runs.filter is not a function", "undefined".

WHAT THIS AUDIT FOUND
─────────────────────
  * Kanban rendered "6 tasks" of FABRICATED work during an outage, because
    kanbanFetchTasks() fell back to sample data. A user could drag, edit or
    delete cards that did not exist.
  * `runs.filter is not a function` and `files.filter is not a function`
    shown as the user's explanation -- both were real crashes, not wording:
    the pane parsed an error object as if it were a list.
  * "DB size: undefined KB".

MEASUREMENT NOTE
────────────────
An earlier version of this probe read only pane TEXT and therefore missed the
toasts that 00-net-feedback.js already raises -- which led to a finding being
reported that was partly already solved. Toasts are counted here too.
"""

from __future__ import annotations

import re
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
from _harness import AuditResult, all_panes, browser_page, emit, fail_all_api, pane_text, preflight, visit  # noqa: E402

# Internal detail that should never be the sentence a user reads. Note this
# deliberately does NOT match text in trailing parentheses, which is the
# documented place for technical detail (see frontend/js/00-error-copy.js).
JARGON = re.compile(
    r'HTTP \d{3}|is not a function|Cannot read propert|Cannot set propert'
    r'|\bundefined\b|\bNaN\b|TypeError|SyntaxError|Unexpected token'
    r'|is not valid JSON|Failed to fetch|\[object Object\]',
    re.I)

# Evidence that the pane admitted something went wrong.
ACKNOWLEDGES = re.compile(
    r"could ?n.t|cannot|can.t|unable|failed|error|problem|unavailable"
    r"|try again|retry|went wrong|not reachable",
    re.I)


def _headline_only(text: str) -> str:
    """Strip trailing parenthesised detail before checking for jargon.

    `humanError()` deliberately keeps the technical detail, demoted to the end
    in parentheses. That is the intended design, so it must not be reported as
    a finding -- otherwise the audit punishes the fix.
    """
    return re.sub(r'\([^)]*\)', '', text)


def run() -> AuditResult:
    preflight()
    findings = []
    with browser_page('desktop', route_handler=fail_all_api()) as (page, _ctx):
        for pane in all_panes(page):
            visit(page, pane, settle=420)
            text = pane_text(page, pane)
            toasts = page.evaluate(
                "[...document.querySelectorAll('.toast')].map(t=>t.innerText)")
            combined = text + '\n' + '\n'.join(toasts)

            leaked = sorted(set(JARGON.findall(_headline_only(text))))
            if leaked:
                line = next(
                    (ln.strip() for ln in text.split('\n')
                     if JARGON.search(_headline_only(ln))), '')
                findings.append(f'JARGON  {pane:16} {line[:80]}')
                continue

            # A pane with almost no content is a loading state, not a lie.
            if len(text) > 60 and not ACKNOWLEDGES.search(combined):
                findings.append(
                    f'SILENT  {pane:16} renders {len(text)} chars, no failure shown')

    return AuditResult(
        'failure-honesty',
        len(findings),
        findings,
        note='panes that hide an outage (SILENT) or expose internals (JARGON) '
             'when every API returns 500',
    )


if __name__ == '__main__':
    raise SystemExit(emit(run()))
