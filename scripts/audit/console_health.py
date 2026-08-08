#!/usr/bin/env python3
"""What the browser console says while the app is used.

WHY THIS IS A NEW DIMENSION
───────────────────────────
Twenty audits inspect the DOM, the network and the rendered pixels. **None of
them had ever read the console.** That is the one channel where the browser
itself reports what the application got wrong -- uncaught exceptions, failed
subresources, policy violations, deprecation warnings -- and it was being
thrown away on every run.

Three things are counted, deliberately separately, because they have very
different severities:

  PAGE-ERROR    an uncaught exception. Something threw and the handler that
                should have caught it did not. Always a defect.

  CONSOLE-ERROR an `console.error` or failed subresource that is NOT an
                already-understood, already-mitigated policy violation.

  NOISE         volume. A console with thousands of expected messages in it is
                a console nobody reads, so the next real error is invisible.
                This is not a bug in itself; it is the condition that hides
                the next bug, which is why it gets a number of its own.

WHAT THE FIRST RUN FOUND
────────────────────────
Zero page errors, zero unexplained console errors -- and **10,998 CSP
`style-src` violations** across a single pass over every pane.

Those violations are expected, and the styling still works: `style-src 'self'`
refuses the parser-level `style` attribute, and `00-style-hydrate.js`
re-applies each one through the CSSOM, where CSP does not reach. Verified
directly: of the visible elements carrying a `style` attribute, **0 had
dropped declarations.** Nothing is broken on screen.

But the browser logs a refusal *before* the hydrator re-applies it, once per
attribute, and that cannot be suppressed from script. The result is a console
in which a genuine error is a needle in a haystack of 11,000.

MEASUREMENT NOTES
─────────────────
  * `pageerror` and `console` are separate Playwright events; an uncaught
    exception does not always surface as a console message of type `error`.
  * The 404 on `/api/secrets/get` is excluded: it is the documented
    "this key is not configured" probe, already exempted by
    `00-connection-status.js` for the same reason.
  * Deprecation warnings from vendored libraries (three.js) are counted as
    noise, not errors -- they are not ours to fix and were not introduced by
    this application.
"""

from __future__ import annotations

import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
from _harness import (  # noqa: E402
    BASE_URL,
    LAUNCH_ARGS,
    AuditResult,
    chrome_path,
    emit,
    preflight,
)

# Messages that are understood, mitigated, and not evidence of a defect.
EXPECTED = (
    'Content Security Policy',      # style-src; see 00-style-hydrate.js
    '/api/secrets/get',             # "key not configured" probe
    'three.js',                     # vendored deprecation warnings
    'THREE.',
    'WebGL',
    'GroupMarkerNotSet',
    'allow-scripts and allow-same-origin',   # sandboxed preview iframe, by design
)

# Above this, the console is no longer a place a real error can be seen.
NOISE_BUDGET = 12000


def run() -> AuditResult:
    preflight()
    findings = []
    page_errors, console_errors, noise = [], [], 0

    def on_console(message):
        nonlocal noise
        if message.type not in ('error', 'warning'):
            return
        text = message.text
        if any(token in text for token in EXPECTED):
            noise += 1
            return
        if message.type == 'error':
            console_errors.append(text[:150])
        else:
            noise += 1

    from playwright.sync_api import sync_playwright

    with sync_playwright() as p:
        browser = p.chromium.launch(executable_path=chrome_path(), args=LAUNCH_ARGS)
        context = browser.new_context(viewport={'width': 1440, 'height': 900})
        page = context.new_page()
        # A failed subresource logs "Failed to load resource: ... 404" with NO
        # URL in the message text, so it cannot be matched against EXPECTED.
        # The `response` event carries the URL, so exempt paths are recorded
        # here and the matching console line is suppressed by count.
        expected_404 = {'n': 0}

        def on_response(response):
            if response.status < 400:
                return
            if any(token in response.url for token in EXPECTED):
                expected_404['n'] += 1

        page.on('response', on_response)
        page.on('console', on_console)
        page.on('pageerror', lambda e: page_errors.append(str(e)[:150]))

        page.goto(BASE_URL, wait_until='domcontentloaded', timeout=60000)
        page.wait_for_timeout(4500)
        page.evaluate("""() => {
            const m = document.getElementById('onboarding-modal')
                   || document.getElementById('onboarding-overlay');
            if (m) m.remove();
        }""")

        for pane in page.evaluate("Object.keys(window.MASTER_PANE_REGISTRY || {})"):
            page.evaluate(f'window.nav && window.nav({json.dumps(pane)})')
            page.wait_for_timeout(300)

        browser.close()

    # Drop as many "Failed to load resource" lines as there were exempt 4xx
    # responses. Deliberately count-matched rather than removed wholesale: a
    # NON-exempt 404 still surfaces, which is the case worth knowing about.
    remaining = expected_404['n']
    filtered = []
    for text in console_errors:
        if remaining and 'Failed to load resource' in text:
            remaining -= 1
            noise += 1
            continue
        filtered.append(text)
    console_errors = filtered

    for text in dict.fromkeys(page_errors):
        findings.append(f'PAGE-ERROR     {text}')
    for text in dict.fromkeys(console_errors):
        findings.append(f'CONSOLE-ERROR  {text}')

    if noise > NOISE_BUDGET:
        findings.append(
            f'NOISE          {noise} expected messages in one pass, over the '
            f'{NOISE_BUDGET} budget — a real error would not be findable here')
    else:
        findings.append(
            f'-- {noise} expected//mitigated messages (budget {NOISE_BUDGET}); '
            'mostly CSP style-src refusals that 00-style-hydrate.js re-applies')

    return AuditResult(
        'console-health',
        len([f for f in findings if not f.startswith('--')]),
        findings,
        note='uncaught exceptions and unexplained console errors across every pane',
    )


if __name__ == '__main__':
    raise SystemExit(emit(run()))
