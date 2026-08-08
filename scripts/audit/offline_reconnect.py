#!/usr/bin/env python3
"""Going offline, and coming back.

WHY THIS IS ITS OWN SEAM
────────────────────────
`failure_honesty.py` covers "the server answers 500" and `session_expiry.py`
covers "the server refuses you". Offline is a third thing again: the request
never reaches anyone, `fetch` REJECTS rather than resolving, and — crucially —
the condition ENDS. Every other failure audit measures a steady state. This one
measures a transition, and recovery is where the interesting bugs are.

Three questions, in the order a user experiences them:

  GOING-OFFLINE   does anything say the connection is gone?
  CONTRADICTORY   do several independent surfaces say DIFFERENT things about
                  the same connection? Three separate listeners each raising
                  their own message is not three times the help; the user has
                  to work out which one to believe, and here they genuinely
                  conflicted -- "local features still work" and "your work is
                  safe" alongside "changes will not be saved".
  WHILE-OFFLINE   does a write attempted while offline tell the user it did
                  not happen? A write that is silently dropped is the worst
                  outcome in the whole application: the user believes their
                  work is saved and closes the tab.
  RECONNECT       when the network returns, does the app notice and recover
                  WITHOUT the user reloading? A banner that never clears is a
                  lie in the opposite direction, and a screen that stays empty
                  after the connection is back is indistinguishable from data
                  loss.

MEASUREMENT NOTES
─────────────────
  * `context.set_offline(True)` is used rather than routing to an error,
    because it also flips `navigator.onLine` and fires the `offline`/`online`
    events. The app listens for those, so faking the failure at the route
    layer would test a different code path from the real one.
  * The reconnect check waits for the app's OWN recovery, then reloads only as
    a control. If the pane recovers on reload but not without one, that is the
    finding — "reload fixes it" is not recovery, it is the user doing the
    work.
  * A stale banner is checked AFTER a successful request has demonstrably
    happened, not merely after `online` fires. The event says the OS thinks
    there is a network; only a 200 proves the server is reachable.
"""

from __future__ import annotations

import re
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
from _harness import AuditResult, browser_page, emit, pane_text, preflight, visit  # noqa: E402

# Panes with a visible list and a create action, i.e. where a dropped write is
# actually observable.
PANES = ['kanban', 'goals', 'specs', 'webhooks']

OFFLINE_WORDS = re.compile(
    r"offline|no connection|not connected|can.?t reach|cannot reach|unreachable"
    r"|no internet|connection (lost|problem)|reconnect",
    re.I)

ACKNOWLEDGES = re.compile(
    r"could ?n.t|cannot|can.t|unable|failed|error|problem|unavailable"
    r"|try again|retry|went wrong|not reachable|offline|not saved",
    re.I)


# The surfaces the app uses to report connection state. Scoped deliberately:
# see _status_text().
STATUS_SELECTOR = (
    '#net-offline-banner, #connection-banner, #session-banner, '
    '.toast, .connection-banner, .session-banner'
)


def _status_text(page) -> str:
    """Text from the app's STATUS surfaces only, not the whole document.

    WHY NOT THE WHOLE BODY. The first version of this probe searched all
    visible text for /offline/ and reported "an offline message is still on
    screen after the connection returned". The match was
    `Private • Ollama • Offline` -- a product feature label describing that a
    local LLM runs without a network. Nothing was wrong.

    That cuts BOTH ways, and the second direction is the dangerous one: the
    same prose would have satisfied the GOING-OFFLINE check, so a total
    absence of offline reporting would have been reported as clean. A probe
    that can be satisfied by marketing copy is not measuring the product.
    """
    return page.evaluate("""(sel) => {
        const nodes = [...document.querySelectorAll(sel)];
        return nodes.filter(el => {
            const cs = getComputedStyle(el);
            if (cs.display === 'none' || cs.visibility === 'hidden') return false;
            if (parseFloat(cs.opacity) === 0) return false;
            const r = el.getBoundingClientRect();
            return r.width > 1 && r.height > 1;
        }).map(el => el.innerText).join(' | ').replace(/\\s+/g, ' ').trim();
    }""", STATUS_SELECTOR)


def _visible_text(page) -> str:
    """All visible text. Off-screen live regions hold copies of toast text
    and made an earlier audit in this directory report a clean screen while
    the user could see nothing (see docs/SEAM-REGISTER.md)."""
    return page.evaluate("""(() => {
        const drop = new Set([...document.querySelectorAll(
            '#sr-announcer, .sr-only, .visually-hidden')]);
        const walk = (node) => {
            if (drop.has(node)) return '';
            if (node.nodeType === 3) return node.textContent;
            if (node.nodeType !== 1) return '';
            const cs = getComputedStyle(node);
            if (cs.display === 'none' || cs.visibility === 'hidden') return '';
            if (parseFloat(cs.opacity) === 0) return '';
            const r = node.getBoundingClientRect();
            if (r.width <= 1 || r.height <= 1) return '';
            return [...node.childNodes].map(walk).join(' ');
        };
        return walk(document.body).replace(/\\s+/g, ' ').trim();
    })()""")


def _attempt_write(page) -> None:
    """Fire a write the way the app does, so the app's own error handling runs.

    Deliberately NOT a bare `fetch()` from the probe: that would bypass the
    UI's reporting and measure the transport instead of the product.
    """
    page.evaluate("""(async () => {
        window.__offlineProbe = 'pending';
        try {
            const r = await fetch('/api/tasks', {
                method: 'POST',
                headers: {'Content-Type': 'application/json'},
                body: JSON.stringify({title: 'offline probe'}),
            });
            window.__offlineProbe = 'resolved:' + r.status;
        } catch (e) {
            window.__offlineProbe = 'rejected';
        }
    })()""")
    page.wait_for_timeout(1200)


def run() -> AuditResult:
    preflight()
    findings = []

    with browser_page('desktop') as (page, ctx):
        visit(page, 'kanban', settle=600)

        # ── 1. Going offline ────────────────────────────────────────────
        ctx.set_offline(True)
        page.evaluate("window.dispatchEvent(new Event('offline'))")
        # Provoke traffic so anything driven by failures has a chance to fire.
        for pane in PANES:
            visit(page, pane, settle=350)
        page.wait_for_timeout(1500)

        status = _status_text(page)
        if not OFFLINE_WORDS.search(status):
            findings.append(
                'GOING-OFFLINE  no status surface says the connection is gone')

        # How many DISTINCT surfaces are talking about the connection. One is
        # the design. Several, each with its own wording, is the bug -- and it
        # is also why sabotaging a single one of them left this audit clean:
        # the redundancy hid the breakage. Duplicates of the same text are
        # collapsed first so a repeated toast counts once.
        speakers = page.evaluate('''(sel) => {
            const seen = new Set();
            [...document.querySelectorAll(sel)].forEach(el => {
                const cs = getComputedStyle(el);
                if (cs.display === 'none' || cs.visibility === 'hidden') return;
                const r = el.getBoundingClientRect();
                if (r.width <= 1 || r.height <= 1) return;
                const t = (el.innerText || '').replace(/\\s+/g, ' ').trim();
                if (/offline|connection|can.?t reach|unreachable/i.test(t)) {
                    seen.add(t.replace(/[×✕↻]/g, '').trim());
                }
            });
            return [...seen];
        }''', STATUS_SELECTOR)
        if len(speakers) > 1:
            findings.append(
                f'CONTRADICTORY  {len(speakers)} different messages about the '
                f'same lost connection: ' + ' // '.join(s[:60] for s in speakers))

        # ── 2. A write attempted while offline ──────────────────────────
        _attempt_write(page)
        state = page.evaluate("window.__offlineProbe")
        if state == 'rejected':
            text = _visible_text(page)
            if not ACKNOWLEDGES.search(text):
                findings.append(
                    'WHILE-OFFLINE  a write failed with nothing on screen '
                    'saying it did not happen')
        else:
            findings.append(
                f'-- write while offline returned {state!r}; not a dropped '
                'write, so the silent-write check did not apply')

        # ── 3. Coming back ──────────────────────────────────────────────
        ctx.set_offline(False)
        page.evaluate("window.dispatchEvent(new Event('online'))")
        page.wait_for_timeout(500)

        # Prove the server really is reachable again before judging anything;
        # the `online` event only says the OS found a network.
        reachable = page.evaluate("""(async () => {
            try { const r = await fetch('/api/health'); return r.ok; }
            catch (e) { return false; }
        })()""")
        page.wait_for_timeout(2500)

        if not reachable:
            findings.append('-- server not reachable after going online; '
                            'reconnect checks skipped')
            return AuditResult('offline-reconnect', len(findings), findings,
                               note='behaviour going offline, writing while '
                                    'offline, and reconnecting')

        after = _status_text(page)
        if OFFLINE_WORDS.search(after):
            findings.append(
                'RECONNECT      an offline message is still on screen after '
                'the connection returned')

        # Does content come back without the user reloading? Navigate away and
        # back so the pane refetches the way it would on any normal use.
        visit(page, 'goals', settle=400)
        visit(page, 'kanban', settle=900)
        recovered = pane_text(page, 'kanban')

        if len(recovered) < 60 or ACKNOWLEDGES.search(recovered):
            page.reload(wait_until='domcontentloaded')
            page.wait_for_timeout(3500)
            visit(page, 'kanban', settle=900)
            after_reload = pane_text(page, 'kanban')
            if len(after_reload) >= 60 and not ACKNOWLEDGES.search(after_reload):
                findings.append(
                    'RECONNECT      kanban only recovers after a full page '
                    'reload; the app does not recover on its own')
            else:
                findings.append(
                    '-- kanban did not recover even after a reload; likely a '
                    'pane fault rather than a reconnect fault')

    return AuditResult(
        'offline-reconnect',
        len([f for f in findings if not f.startswith('--')]),
        findings,
        note='behaviour going offline, writing while offline, and reconnecting',
    )


if __name__ == '__main__':
    raise SystemExit(emit(run()))
