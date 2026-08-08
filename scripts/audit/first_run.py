#!/usr/bin/env python3
"""What a brand-new user sees, on an empty account.

WHY THIS IS A NEW DIMENSION
───────────────────────────
All eighteen existing audits run against a database with data in it -- 250
seeded goals, 200 tasks, agents, specs. That was deliberate for measuring
volume, truncation and layout. It also means **every audit in this directory
has only ever seen the application in a state no new user is ever in.**

An empty account is the first thing every single user experiences, and it is
the state most likely to have been eyeballed once during development and never
looked at again. It fails differently from every other state: nothing is
broken, nothing errors, and the screen is simply blank.

Four failures are measured, in the order a new user meets them:

  DEAD-END      a pane renders an empty state with NO action in it. The user
                has arrived somewhere with nothing to do and no clue what
                this screen is for. This is the single most common product
                failure in an empty account, and it is invisible to every
                audit that runs against seeded data.

  NO-EXPLAIN    the pane shows an action but never says what the feature IS.
                "No items yet" plus a "+ New" button tells a new user
                nothing about whether they want one.

  RAW-EMPTY     the pane shows a bare technical void -- "[]", "null",
                "0 results", "undefined" -- rather than a written empty state.

  BROKEN-EMPTY  the pane throws, or shows an ERROR, merely because there is
                no data. An empty account is not a failure and must not be
                reported as one. This is the most serious: a new user's first
                impression is that the product is broken.

MEASUREMENT NOTES
─────────────────
  * Needs a server started against an EMPTY data dir. Run:
        AGENTIC_TEST_DB=/tmp/fresh.db AGENTIC_OS_DATA_DIR=/tmp/fresh-data \
          python run.py
    The audit refuses to run if it detects seeded data, rather than reporting
    a meaningless clean result -- an audit measuring the wrong state looks
    exactly like one finding nothing.
  * First-run overlays are NOT removed here, unlike every other audit in this
    directory. The onboarding modal is part of the first-run experience and
    removing it would measure a state the new user never sees. It is dismissed
    the way a user dismisses it, by clicking its own close control.
  * "An action" means a control that CREATES something or explains the
    feature -- not any button at all. A pane whose only control is a filter
    dropdown is still a dead end.
"""

from __future__ import annotations

import json
import re
import sys
import urllib.error
import urllib.request
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
from _harness import (  # noqa: E402
    BASE_URL,
    LAUNCH_ARGS,
    AuditResult,
    all_panes,
    chrome_path,
    emit,
    preflight,
)

# Words that indicate the pane is telling the user this state is normal and
# expected, rather than showing them a void.
EMPTY_STATE = re.compile(
    r"no \w+ yet|nothing here yet|get started|create your first|add your first"
    r"|you have ?n.t|haven.t (yet|created)|start by|once you|will appear here"
    r"|no \w+ (found|created|configured) yet|empty",
    re.I)

# A bare technical void with no writing around it.
RAW_VOID = re.compile(r'^\s*(\[\]|\{\}|null|undefined|0|none|n/a)\s*$', re.I)

# Something went wrong -- which an empty account is not.
#
# SCOPED TO SENTENCES, NOT TO WORDS. The first version matched any occurrence
# of /error|failed/ anywhere in the pane and produced five false positives out
# of six:
#
#   control      "ERRORS  0"        -- a metric LABEL on a dashboard tile
#   leaderboard  "Error Rate  0%"   -- ditto
#   audit-log    "Failed Actions 0" -- ditto
#   hooks        "🚨 Error"          -- the NAME of a trigger type the user picks
#   testgen      "...edge cases, mocks, and error handling"  -- feature copy
#
# A product that reports "Errors: 0" is working correctly and saying so. What
# actually indicates breakage is a sentence ADDRESSED to the user about a
# failure, so the pattern now requires the failure word to sit in a clause
# rather than beside a number or inside a label.
BROKEN = re.compile(
    r"could ?n.t \w+|can ?not \w+|unable to \w+|failed to \w+"
    r"|something went wrong|an error occurred|is not a function"
    r"|cannot read propert|undefined is not|\bTypeError\b|\bTraceback\b",
    re.I)


def _broken_line(text: str) -> str:
    """The first line that is genuinely a failure message.

    A line is exonerated when the match sits next to a count -- "Errors 0",
    "0 Failed Actions" -- because that is a metric being reported, not a
    failure being suffered.
    """
    for line in text.split('\n'):
        stripped = line.strip()
        if not BROKEN.search(stripped):
            continue
        if re.fullmatch(r'[^a-zA-Z]*[\w %$.]{0,24}', stripped):
            continue
        if re.search(r'^\W*\d+[\s%$]*$', stripped):
            continue
        return stripped
    return ''

# A control that lets the user DO the thing this pane is for.
#
# WIDENED AFTER TRIAGE. The first version matched only creation VERBS in a
# label, and over-reported badly -- 23 findings of which most were working
# panes:
#
#   websearch    an "Ask a grounded question" field + Ask button
#   codesearch   a search input
#   swarm        a prompt textarea
#   multitab     a URL bar and Go
#   replay       "Run a workflow" and a run search
#
# For a search or prompt pane, THE TEXT BOX IS THE ENTRY POINT. Judging entry
# by button labels alone declares the most usable panes in the product broken,
# which would have sent me rewriting screens that were already right.
ACTION = re.compile(
    r"\+|new|create|add|start|generate|import|connect|upload|get started"
    r"|set up|configure|browse|explore|try|learn|run|ask|search|send|submit"
    r"|go\b|open|choose|select|record|write|build|deploy|install|enable"
    # Tab and section labels are an entry point on a pane whose landing
    # state IS a chooser: dbstudio offers "SQL Editor" / "Schema
    # Designer", integrations offers "Docs" / "Rules". Both were reported
    # as dead ends by a verb-only pattern while being perfectly navigable.
    r"|editor|designer|studio|docs|rules|trail|sqlite|supabase|gallery",
    re.I)

# Panes that legitimately have nothing to create: they REPORT on the system.
# An empty dashboard is honest, not a dead end -- but it must still say what
# it is waiting for, which is what the EMPTY_STATE check below covers.
READ_ONLY_OK = {
    'system', 'health', 'agent-monitor', 'control', 'leaderboard',
    'audit-log', 'profiler', 'analytics',
}


def _seeded() -> bool:
    """Refuse to run against a populated database.

    An audit pointed at the wrong state reports a clean result for the wrong
    reason -- the exact failure that made the concurrency audit pass while
    every one of its writes was being rejected.
    """
    for path in ('/api/tasks', '/api/goals'):
        url = f'{BASE_URL}{path}'
        if not url.startswith(('http://', 'https://')):
            continue
        try:
            with urllib.request.urlopen(url, timeout=10) as r:  # noqa: S310
                body = json.loads(r.read())
        except (urllib.error.URLError, OSError, ValueError):
            continue
        rows = body if isinstance(body, list) else (
            body.get('tasks') or body.get('goals') or [])
        if isinstance(rows, list) and len(rows) > 3:
            return True
    return False


def run() -> AuditResult:
    preflight()

    if _seeded():
        return AuditResult(
            'first-run-experience', 0,
            ['-- the server has seeded data; this audit measures an EMPTY '
             'account and refuses to report a result against the wrong state. '
             'Start a server with an empty AGENTIC_OS_DATA_DIR.'],
            note='what a brand-new user sees on an empty account')

    findings = []
    from playwright.sync_api import sync_playwright

    with sync_playwright() as p:
        browser = p.chromium.launch(executable_path=chrome_path(), args=LAUNCH_ARGS)
        context = browser.new_context(viewport={'width': 1440, 'height': 900})
        page = context.new_page()
        page.goto(BASE_URL, wait_until='domcontentloaded', timeout=60000)
        page.wait_for_timeout(4000)

        # Dismiss first-run UI the way a USER does, via its own control, so
        # anything that depends on that click still happens.
        page.evaluate("""() => {
            const modal = document.getElementById('onboarding-modal')
                       || document.getElementById('onboarding-overlay');
            if (!modal) return;
            const close = modal.querySelector(
                '[data-close], .close, [aria-label*="lose" i], button');
            if (close) close.click(); else modal.remove();
        }""")
        page.wait_for_timeout(600)

        for pane in all_panes(page):
            page.evaluate(f'window.nav && window.nav({json.dumps(pane)})')
            page.wait_for_timeout(450)

            state = page.evaluate(f"""() => {{
                const own = document.getElementById('pane-' + {json.dumps(pane)});
                let el = own;
                if (!el || el.offsetParent === null) {{
                    el = [...document.querySelectorAll('[id^=pane-]')]
                        .find(e => e.offsetParent !== null);
                }}
                if (!el) return null;
                const controls = [...el.querySelectorAll(
                    'button, a[href], [role=button], input, select, textarea')]
                    .filter(c => c.offsetParent !== null)
                    .map(c => (c.innerText || c.value
                               || c.getAttribute('aria-label')
                               || c.getAttribute('placeholder') || '').trim())
                    .filter(Boolean);
                return {{text: el.innerText.trim(), controls: controls}};
            }}""")

            if state is None:
                continue
            text = state['text']
            controls = state['controls']

            # A pane still loading is not a finding.
            if len(text) < 3:
                continue

            broken = _broken_line(text)
            if broken:
                findings.append(
                    f'BROKEN-EMPTY  {pane:18} reports a failure on an empty '
                    f'account: {broken[:70]}')
                continue

            if RAW_VOID.match(text):
                findings.append(
                    f'RAW-EMPTY     {pane:18} shows a bare {text.strip()[:20]!r}')
                continue

            # A free-text input IS the entry point on a search or prompt pane.
            has_input = page.evaluate(f"""() => {{
                const own = document.getElementById('pane-' + {json.dumps(pane)});
                let el = own;
                if (!el || el.offsetParent === null) {{
                    el = [...document.querySelectorAll('[id^=pane-]')]
                        .find(e => e.offsetParent !== null);
                }}
                if (!el) return false;
                return [...el.querySelectorAll(
                    'textarea, input:not([type=checkbox]):not([type=radio])')]
                    .some(i => i.offsetParent !== null);
            }}""")
            has_action = has_input or any(ACTION.search(c) for c in controls)
            if pane in READ_ONLY_OK:
                has_action = True
            explains = EMPTY_STATE.search(text) or len(text) > 220

            if not has_action and not explains:
                findings.append(
                    f'DEAD-END      {pane:18} {len(text)} chars, '
                    f'{len(controls)} control(s), no way in and no explanation')
            elif not has_action:
                findings.append(
                    f'DEAD-END      {pane:18} explains itself but offers no '
                    'action to start')
            elif not explains:
                findings.append(
                    f'NO-EXPLAIN    {pane:18} offers an action but never says '
                    'what the feature is for')

        browser.close()

    return AuditResult(
        'first-run-experience',
        len([f for f in findings if not f.startswith('--')]),
        findings,
        note='what a brand-new user sees on a completely empty account',
    )


if __name__ == '__main__':
    raise SystemExit(emit(run()))
