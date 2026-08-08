#!/usr/bin/env python3
"""What a user sees when their session dies underneath them.

THE SEAM
────────
Every other failure audit in this directory simulates the server being BROKEN
(500) or SLOW. Authentication loss is a different shape of failure and the app
treats it differently:

  * The server answers 401 promptly and correctly. Nothing is down.
  * The response is a refusal, not a fault, so the connection banner in
    00-connection-status.js deliberately ignores it (4xx is "you asked for
    something you may not have", not "the platform is broken").
  * 00-net-feedback.js raises a toast — which auto-dismisses after 6 seconds.

That combination is the seam: six seconds after the session expires there is
nothing on screen saying so, while every pane the user opens renders a calm,
plausible empty state. A dead session and an empty account look identical, and
the user has no offered way back in.

WHAT IS MEASURED
────────────────
Every /api/ call is answered 401 (the shape the app's own secure mode emits,
see _SECURE_MODE in backend/app.py). Then, per pane:

  SILENT     the pane renders substantial content and never mentions that the
             session is the problem — an outage indistinguishable from "you
             have no data".

And once, for the session as a whole:

  NO-SIGNAL  after the transient toasts have expired, nothing persistent on
             screen says the session ended.
  NO-ACTION  nothing on screen offers a way to sign back in / resume.

MEASUREMENT NOTES
─────────────────
  * The toasts are read as well as the pane text (an earlier audit in this
    repo reported findings that the toast layer had already solved).
  * NO-SIGNAL is checked AFTER waiting past the 6000ms toast lifetime, on
    purpose. Checking immediately measures the toast, not the resting state,
    and would have reported this seam as clean.
  * The 401 route is installed after boot so the app loads normally and only
    the session is lost, which is what actually happens to a user.
"""

from __future__ import annotations

import re
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
from _harness import AuditResult, all_panes, browser_page, emit, pane_text, preflight, visit  # noqa: E402

# How long the transient toast lives (00-net-feedback.js) plus its fade.
TOAST_LIFETIME_MS = 6000
TOAST_FADE_MS = 400

# Language that tells the user this is about who they are, not about the data.
SESSION_WORDS = re.compile(
    r"sign(ed)? ?in|sign ?out|signed out|log(ged)? ?in|session|authenticat"
    r"|not authorised|not authorized|permission|credentials",
    re.I)

# Any admission at all that something failed.
ACKNOWLEDGES = re.compile(
    r"could ?n.t|cannot|can.t|unable|failed|error|problem|unavailable"
    r"|try again|retry|went wrong|not reachable|expired",
    re.I)


def _unauthorised(route):
    route.fulfill(
        status=401,
        content_type='application/json',
        body='{"ok":false,"error":"Authentication required"}',
        headers={'WWW-Authenticate': 'Bearer'},
    )


def _resting_state(page) -> str:
    """Everything persistently and VISIBLY on screen.

    Three things are excluded, each because it made this probe lie once:

      * toasts — removed rather than merely waited out. They re-fire on every
        poll, so "wait past the 6s lifetime" does not guarantee the screen is
        at rest; the first version of this probe read a freshly-raised toast
        as persistent UI.
      * `#sr-announcer` and explicit screen-reader-only containers — the
        announcer holds a COPY of the toast text and is `position:absolute`
        off-screen. It made NO-SIGNAL pass while the user saw nothing at all.
      * anything of zero size or scrolled off the top/left, by the same
        argument.

    Note what is NOT dropped: `[aria-live]` in general. Dropping every live
    region was the probe's SECOND bug — it deleted the visible lost-session
    banner, which is an `aria-live="assertive"` alert, and reported NO-SIGNAL
    against a screen that plainly said so. Visibility is the test, not the
    presence of an ARIA attribute.
    """
    return page.evaluate("""(() => {
        const drop = new Set([...document.querySelectorAll(
            '#toast-container, .toast, #sr-announcer, .sr-only, .visually-hidden')]);
        const offscreen = (el) => {
            const r = el.getBoundingClientRect();
            if (r.width <= 1 || r.height <= 1) return true;
            return r.bottom < 0 || r.right < 0;
        };
        const walk = (node) => {
            if (drop.has(node)) return '';
            if (node.nodeType === 3) return node.textContent;
            if (node.nodeType !== 1) return '';
            const cs = getComputedStyle(node);
            if (cs.display === 'none' || cs.visibility === 'hidden') return '';
            if (parseFloat(cs.opacity) === 0) return '';
            if (offscreen(node)) return '';
            return [...node.childNodes].map(walk).join(' ');
        };
        return walk(document.body).replace(/\\s+/g, ' ').trim();
    })()""")


def run() -> AuditResult:
    preflight()
    findings = []

    with browser_page('desktop') as (page, ctx):
        panes = all_panes(page)
        ctx.route('**/api/**', _unauthorised)

        for pane in panes:
            visit(page, pane, settle=420)
            text = pane_text(page, pane)
            toasts = page.evaluate(
                "[...document.querySelectorAll('.toast')].map(t=>t.innerText)")
            combined = text + '\n' + '\n'.join(toasts)

            # A nearly-empty pane is a loading state, not a lie.
            if len(text) <= 60:
                continue
            if not ACKNOWLEDGES.search(combined):
                findings.append(
                    f'SILENT     {pane:16} renders {len(text)} chars, '
                    f'no sign the session ended')

        # ── Resting state, after every toast has expired ─────────────────
        page.wait_for_timeout(TOAST_LIFETIME_MS + TOAST_FADE_MS)
        resting = _resting_state(page)

        if not SESSION_WORDS.search(resting):
            findings.append(
                'NO-SIGNAL  nothing persistent on screen says the session '
                'ended once the toasts expire')

        # A way back in: a control (not prose) whose label offers to restore
        # the session. Prose alone is not an action.
        action = page.evaluate(r"""(() => {
            const re = /sign in|sign back in|log in|reconnect|resume session|reload/i;
            const sel = 'button, a[href], [role=button], input[type=submit]';
            return [...document.querySelectorAll(sel)]
                .filter(e => e.offsetParent !== null)
                .map(e => (e.innerText || e.value || e.getAttribute('aria-label') || '').trim())
                .filter(t => re.test(t));
        })()""")
        if not action:
            findings.append(
                'NO-ACTION  no visible control offers a way to sign back in')

    return AuditResult(
        'session-expiry',
        len(findings),
        findings,
        note='what the user sees, and can do, when every API answers 401',
    )


if __name__ == '__main__':
    raise SystemExit(emit(run()))
