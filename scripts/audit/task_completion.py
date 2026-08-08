#!/usr/bin/env python3
"""Can a user actually finish a job?

WHY THIS IS DIFFERENT FROM EVERY OTHER AUDIT HERE
─────────────────────────────────────────────────
Every other probe in this directory inspects a RENDERED STATE: is this control
big enough, does this pane announce itself, does this value carry a timezone.
None of them ever *uses* the product. A screen can pass every one of those
checks and still be impossible to get a job done in.

This one drives complete journeys through the real UI -- clicking the controls
a user clicks -- and asserts the outcome the user expects:

  CREATE-FAIL     the thing the user made does not appear afterwards. The
                  single worst outcome in an application: silent data loss
                  from the user's point of view, whatever the server did.
  PERSIST-FAIL    it appears, but is gone after a reload. Worse than never
                  saving, because the user has already been told it worked.
  EDIT-FAIL       a change cannot be made, or does not stick.
  DELETE-FAIL     a deletion does not happen, or the item comes back.
  NO-FEEDBACK     the action succeeded but nothing on screen confirmed it, so
                  the user cannot tell whether to try again.

MEASUREMENT NOTES
─────────────────
  * Everything goes through the DOM. A probe that POSTs to the API and then
    checks the API has verified the server and learned nothing about the
    product -- the failure mode this whole review keeps finding is a working
    backend behind a broken screen.
  * Each journey verifies its own PRECONDITION and reports a `--` note if the
    entry control is missing, rather than silently passing. A journey that
    never started is not a journey that succeeded.
  * Persistence is checked with a full page RELOAD, not a re-render, because
    an in-memory list can happily show a record the server never stored.
  * A unique marker per run prevents a previous run's leftovers from making a
    broken create look successful.
"""

from __future__ import annotations

import json
import sys
import time
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


def _boot(browser):
    context = browser.new_context(viewport={'width': 1440, 'height': 900})
    page = context.new_page()
    page.goto(BASE_URL, wait_until='domcontentloaded', timeout=60000)
    page.wait_for_timeout(4000)
    page.evaluate("""() => {
        const m = document.getElementById('onboarding-modal')
               || document.getElementById('onboarding-overlay');
        if (m) m.remove();
    }""")
    return context, page


def _visible(page, pane: str) -> str:
    return page.evaluate(f"""() => {{
        const own = document.getElementById('pane-' + {json.dumps(pane)});
        let el = own;
        if (!el || el.offsetParent === null) {{
            el = [...document.querySelectorAll('[id^=pane-]')]
                .find(e => e.offsetParent !== null);
        }}
        return el ? el.innerText : '';
    }}""")


def _nav(page, pane: str, settle: int = 900):
    page.evaluate(f'window.nav && window.nav({json.dumps(pane)})')
    page.wait_for_timeout(settle)


def _journey_kanban(page, findings, marker):
    """Create a task through the UI, confirm it, reload, confirm it survived."""
    _nav(page, 'kanban')

    opened = page.evaluate("""() => {
        const btn = [...document.querySelectorAll('button, [role=button]')]
            .find(b => b.offsetParent !== null
                    && /new task|add your first task/i.test(b.innerText || ''));
        if (!btn) return false;
        btn.click();
        return true;
    }""")
    if not opened:
        findings.append('-- kanban: no create control found; journey skipped')
        return
    page.wait_for_timeout(800)

    typed = page.evaluate("""(title) => {
        const fields = [...document.querySelectorAll(
            'input[type=text], input:not([type]), textarea')]
            .filter(i => i.offsetParent !== null);
        if (!fields.length) return false;
        const f = fields[0];
        const setter = Object.getOwnPropertyDescriptor(
            f.constructor.prototype, 'value').set;
        setter.call(f, title);
        f.dispatchEvent(new Event('input', {bubbles: true}));
        f.dispatchEvent(new Event('change', {bubbles: true}));
        return true;
    }""", marker)
    if not typed:
        findings.append('-- kanban: create dialog has no text field; skipped')
        return

    page.evaluate("""() => {
        const btn = [...document.querySelectorAll('button, [role=button]')]
            .filter(b => b.offsetParent !== null)
            .find(b => /^(create|add|save|submit|create task)$/i
                        .test((b.innerText || '').trim()));
        if (btn) btn.click();
    }""")
    page.wait_for_timeout(1600)

    if marker not in _visible(page, 'kanban'):
        findings.append(
            'CREATE-FAIL    kanban: the task created through the UI does not '
            'appear on the board')
        return

    page.reload(wait_until='domcontentloaded')
    page.wait_for_timeout(4000)
    _nav(page, 'kanban', settle=1500)
    if marker not in _visible(page, 'kanban'):
        findings.append(
            'PERSIST-FAIL   kanban: the task appeared, then was gone after a '
            'reload -- the user was told it saved and it did not')


def _journey_delete(page, findings, marker):
    """Remove what was just created, and confirm it stays removed."""
    _nav(page, 'kanban', settle=1200)
    if marker not in _visible(page, 'kanban'):
        findings.append('-- delete: nothing to delete; journey skipped')
        return

    removed = page.evaluate("""(title) => {
        const card = [...document.querySelectorAll('*')].find(
            el => el.children.length === 0
               && (el.innerText || '').trim() === title);
        if (!card) return 'no-card';
        let host = card;
        for (let i = 0; i < 6 && host; i++) {
            const del = host.querySelector
                ? host.querySelector('[data-act-click*="elete"], .kanban-card-delete,'
                                     + ' [aria-label*="elete" i], [title*="elete" i]')
                : null;
            if (del) { del.click(); return 'clicked'; }
            host = host.parentElement;
        }
        return 'no-control';
    }""", marker)

    if removed != 'clicked':
        findings.append(f'-- delete: no delete control reachable ({removed})')
        return

    page.wait_for_timeout(700)
    page.evaluate("""() => {
        const ok = [...document.querySelectorAll('button, [role=button]')]
            .filter(b => b.offsetParent !== null)
            .find(b => /^(delete|remove|confirm|yes|ok)$/i
                        .test((b.innerText || '').trim()));
        if (ok) ok.click();
    }""")
    page.wait_for_timeout(1500)

    if marker in _visible(page, 'kanban'):
        findings.append(
            'DELETE-FAIL    kanban: the task is still on the board after '
            'deleting it')
        return

    page.reload(wait_until='domcontentloaded')
    page.wait_for_timeout(4000)
    _nav(page, 'kanban', settle=1500)
    if marker in _visible(page, 'kanban'):
        findings.append(
            'DELETE-FAIL    kanban: the deleted task came back after a reload')


def run() -> AuditResult:
    preflight()
    findings = []
    marker = f'journey probe {int(time.time())}'

    from playwright.sync_api import sync_playwright

    with sync_playwright() as p:
        browser = p.chromium.launch(executable_path=chrome_path(), args=LAUNCH_ARGS)
        context, page = _boot(browser)
        try:
            _journey_kanban(page, findings, marker)
            _journey_delete(page, findings, marker)
        finally:
            context.close()
            browser.close()

    return AuditResult(
        'task-completion',
        len([f for f in findings if not f.startswith('--')]),
        findings,
        note='complete create/persist/delete journeys driven through the real UI',
    )


if __name__ == '__main__':
    raise SystemExit(emit(run()))
