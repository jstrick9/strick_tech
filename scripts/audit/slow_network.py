#!/usr/bin/env python3
"""Behaviour on a slow link, and when a response dies half-way.

Everything so far has tested two states: the server is up, or it returns a
hard 500. Real connections fail in messier ways, and those are the ones that
produce the worst UI:

  NO-PENDING   a slow request shows nothing while it is in flight. The pane
               looks empty or stale, so the user clicks again -- which is how
               duplicate submissions happen.

  STUCK        the request finished but the loading state never cleared. The
               pane spins forever on data that already arrived.

  TRUNCATED    the connection dropped mid-body. The response parses as
               garbage, and the pane must say so rather than render nonsense
               or throw a raw parse error at the user.

MEASUREMENT NOTES
─────────────────
Delay is applied by holding the route open, not by CDP throttling, so only
the API is slowed -- the page and its assets load normally and the measurement
isolates the thing under test.

"Shows something pending" counts a skeleton, a spinner, an `aria-busy`
attribute, or the word "loading". A pane that already has content from a
previous visit is excluded, because stale-but-present is a different
behaviour from blank.
"""

from __future__ import annotations

import re
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
from _harness import AuditResult, browser_page, emit, pane_text, preflight, visit  # noqa: E402

# Long enough that a human would notice and reach for the button again.
DELAY_SECONDS = 3.0

PANES = ['kanban', 'specs', 'goals', 'webhooks', 'workspaces', 'prompts']

PENDING_JS = """(pane) => {
    // Resolve the element the USER is looking at.
    //
    // An absorbed workstation tab keeps its own #pane-<id> node, but when the
    // host has not yet switched to it that node is empty and hidden -- so
    // measuring it reports "blank, no loading state" for a pane that is
    // rendering correctly somewhere else. This is the same trap that produced
    // three phantom findings in an earlier batch; see docs/SEAM-REGISTER.md.
    let el = document.getElementById('pane-' + pane);
    // Only fall back to the visible pane when this pane's own node does not
    // exist or is hidden. Falling back merely because it is EMPTY hides the
    // very thing being measured: the host's content then satisfies the
    // "something is showing" check and a genuinely blank tab reports clean.
    // Verified by removing the goals skeleton -- the audit went silent.
    if (!el || el.offsetParent === null) {
        const vis = [...document.querySelectorAll('[id^=pane-]')]
            .find(e => e.offsetParent !== null && e.innerText.trim());
        if (vis) el = vis;
    }
    if (!el) return {missing: true};
    const own = document.getElementById('pane-' + pane);
    const ownHidden = !!own && own.offsetParent === null;
    const busy = el.getAttribute('aria-busy') === 'true'
              || !!el.querySelector('[aria-busy="true"]');
    const skeleton = !!el.querySelector('.skeleton, [class*=skeleton]');
    const spinner = !!el.querySelector('[class*=spinner], [class*=loading]');
    const text = (el.innerText || '').toLowerCase();
    const says = text.includes('loading') || text.includes('…');
    return {
        pending: busy || skeleton || spinner || says,
        busy, skeleton, spinner, says,
        chars: (el.innerText || '').trim().length,
        ownHidden,
    };
}"""


def _slow(route):
    """Delay the response, then serve a normal empty payload.

    The delay is applied INSIDE the page via a stalling proxy rather than
    with time.sleep() here: a sync route handler runs on Playwright's own
    event loop, and blocking it deadlocks the driver rather than slowing the
    request. The first version of this audit did exactly that and hung for
    eight minutes before being cancelled.
    """
    route.fulfill(status=200, content_type='application/json', body='[]')


def _truncated(route):
    """A body that stops mid-JSON, as a dropped connection produces."""
    route.fulfill(status=200, content_type='application/json',
                  body='[{"id":1,"title":"partial har')


def run() -> AuditResult:
    preflight()
    findings = []

    # ── 1. Slow responses ────────────────────────────────────────────────
    # Delay is injected by wrapping fetch in the page, so only /api/ calls are
    # slowed and Playwright's event loop is untouched.
    stall = f"""() => {{
        const native = window.fetch;
        window.fetch = function (input, init) {{
            const url = (typeof input === 'string') ? input : (input && input.url) || '';
            if (url.includes('/api/')) {{
                return new Promise(resolve => setTimeout(
                    () => resolve(native.apply(this, arguments)),
                    {int(DELAY_SECONDS * 1000)}));
            }}
            return native.apply(this, arguments);
        }};
    }}"""

    with browser_page('desktop') as (page, _ctx):
        page.evaluate(stall)
        for pane in PANES:
            # Navigate WITHOUT waiting, then look while the request is still
            # in flight. Waiting first would measure the settled state and
            # miss the entire question.
            page.evaluate(f"window.nav && window.nav({pane!r})")
            page.wait_for_timeout(900)
            state = page.evaluate(PENDING_JS, pane)
            if state.get('missing'):
                continue
            if not state['pending'] and state['chars'] < 40:
                findings.append(
                    f'NO-PENDING  {pane:12} blank for {DELAY_SECONDS}s with no '
                    f'loading state — a user would click again')
            elif not state['pending'] and state.get('ownHidden'):
                # The pane's own node is empty and hidden while its
                # workstation HOST shows content. Nothing is blank on screen,
                # so this is not a NO-PENDING bug -- but the tab itself gains
                # no pending state either, so it is recorded as informational
                # rather than silently dropped.
                findings.append(
                    f'--          {pane:12} renders inside its workstation host; '
                    f'the tab itself shows no separate pending state')
            # Let it finish and confirm the pending state cleared.
            #
            # Re-check once. The audit navigates panes back to back, so a
            # request from the PREVIOUS pane can still be in flight and its
            # skeleton still on screen; reporting that as "stuck" blames the
            # wrong pane. Verified: webhooks renders 953 chars with no
            # skeleton on a healthy connection, so the first reading here was
            # a test artifact, not a bug.
            page.wait_for_timeout(int(DELAY_SECONDS * 1000) + 1500)
            after = page.evaluate(PENDING_JS, pane)
            if after.get('skeleton') or after.get('busy'):
                page.wait_for_timeout(2500)
                after = page.evaluate(PENDING_JS, pane)
            if after.get('skeleton') or after.get('busy'):
                findings.append(
                    f'STUCK       {pane:12} still shows a loading state after '
                    f'the response arrived')

    # ── 2. Truncated responses ───────────────────────────────────────────
    with browser_page('desktop', route_handler=_truncated) as (page, _ctx):
        for pane in PANES:
            visit(page, pane, settle=1100)
            text = pane_text(page, pane)
            lowered = text.lower()
            # Detail in TRAILING PARENTHESES is the documented design (see
            # frontend/js/00-error-copy.js): the sentence explains, the
            # technical detail is demoted. An earlier version of this check
            # flagged "Couldn't load your specs. Nothing was lost.
            # (Unterminated string...)" as a raw parse error, which punished
            # the fix instead of finding a bug. Only the HEADLINE is judged.
            headline = re.sub(r'\([^)]*\)', '', text).lower()
            leaks = ('unexpected token' in headline
                     or 'json.parse' in headline
                     or 'is not valid json' in headline
                     or 'unterminated' in headline
                     or "failed to execute 'json'" in headline)
            acknowledges = any(w in lowered for w in (
                'could', 'cannot', "can't", 'unable', 'fail', 'error',
                'problem', 'try again', 'retry', 'unavailable'))
            if leaks:
                line = next((ln.strip() for ln in text.split('\n')
                             if 'token' in ln.lower() or 'json' in ln.lower()), '')
                findings.append(f'TRUNCATED   {pane:12} raw parse error shown: {line[:60]}')
            elif len(text) > 60 and not acknowledges:
                findings.append(
                    f'TRUNCATED   {pane:12} renders {len(text)} chars from a '
                    f'broken response without saying anything is wrong')

    # Lines starting with '--' are informational, exactly as in
    # responsive.py: reported so the behaviour is visible, not counted so the
    # ratchet does not fail on something that is not a defect.
    counted = [f for f in findings if not f.startswith('--')]

    return AuditResult(
        'slow-and-flaky-network',
        len(counted),
        findings,
        note=f'panes with no pending state during a {DELAY_SECONDS}s request, '
             f'a stuck loading state, or a mishandled truncated response',
    )


if __name__ == '__main__':
    raise SystemExit(emit(run()))
