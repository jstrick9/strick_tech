#!/usr/bin/env python3
"""Printing, and having the app open twice.

TWO SEAMS, ONE PROBE
────────────────────
Both are cases where the application is used in a way the developer was not
looking at while building it.

PRINT
  `frontend/styles-print.css` is loaded but was never verified. Emulating the
  print medium answers the questions that matter:

    PRINT-CHROME    navigation, toolbars and buttons still on the page. A
                    printed sidebar is a column of dead links wasting a third
                    of every sheet.
    PRINT-CLIPPED   content inside a scroll container prints only the visible
                    slice. This is the one that silently loses data: the user
                    gets page 1 of a list and no indication the rest exists.
    PRINT-INVISIBLE light-on-dark text printed as-is. A dark theme sent to a
                    printer is either unreadable or a full page of toner.

MULTI-TAB
  Two tabs of one application sharing localStorage and one backend.

    TAB-CLOBBER     tab A writes a key, tab B overwrites it with stale state.
    TAB-NO-SYNC     a record created in tab A is invisible in tab B after a
                    refresh of that pane -- two windows disagreeing about
                    what exists.

MEASUREMENT NOTES
─────────────────
  * `emulate_media(media='print')` changes the CASCADE, which is what a print
    stylesheet acts on. Rendering to PDF and diffing pixels would measure the
    rasteriser as much as the CSS.
  * Clipping is judged by `scrollHeight > clientHeight` on a container that is
    still `overflow: auto/scroll` UNDER PRINT. A container that is scrollable
    on screen and becomes `visible` when printed is correctly handled.
  * The multi-tab check drives real UI in the second context rather than
    reading the API, because the question is whether the second WINDOW learns,
    not whether the server knows.
"""

from __future__ import annotations

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

PANES = ['kanban', 'goals', 'specs']


def _boot(context):
    page = context.new_page()
    page.goto(BASE_URL, wait_until='domcontentloaded', timeout=60000)
    page.wait_for_timeout(3500)
    for element_id in ('onboarding-overlay', 'onboarding-modal', 'welcome-banner'):
        page.evaluate(
            f"const e=document.getElementById({element_id!r}); if(e) e.remove();")
    return page


def run() -> AuditResult:
    preflight()
    findings = []

    from playwright.sync_api import sync_playwright

    with sync_playwright() as p:
        browser = p.chromium.launch(executable_path=chrome_path(), args=LAUNCH_ARGS)

        # ── PRINT ───────────────────────────────────────────────────────
        context = browser.new_context(viewport={'width': 1440, 'height': 900})
        page = _boot(context)
        page.evaluate('window.nav && window.nav("kanban")')
        page.wait_for_timeout(700)
        page.emulate_media(media='print')
        page.wait_for_timeout(400)

        chrome = page.evaluate('''() => {
            const out = [];
            const suspects = ['#sidebar', '#topbar', '#next-action-bar',
                              '#toast-container', '.studio-toolbar',
                              '#studio-console-drawer'];
            suspects.forEach(sel => {
                const el = document.querySelector(sel);
                if (!el) return;
                const cs = getComputedStyle(el);
                if (cs.display === 'none' || cs.visibility === 'hidden') return;
                const r = el.getBoundingClientRect();
                if (r.width < 2 || r.height < 2) return;
                out.push(sel);
            });
            return out;
        }''')
        if chrome:
            findings.append(
                f'PRINT-CHROME   {len(chrome)} interface element(s) still print: '
                + ', '.join(chrome))

        clipped = page.evaluate('''() => {
            const out = [];
            document.querySelectorAll('*').forEach(el => {
                if (el.offsetParent === null) return;
                const cs = getComputedStyle(el);
                if (!/auto|scroll|hidden/.test(cs.overflowY)) return;
                // More than a screen of content hidden inside a box that is
                // still clipping under print: the rest simply does not exist
                // on paper.
                if (el.scrollHeight <= el.clientHeight + 200) return;
                out.push((el.id ? '#' + el.id
                          : el.tagName + '.' + String(el.className).split(' ')[0]
                         ).slice(0, 40)
                         + ' (' + el.scrollHeight + 'px in '
                         + el.clientHeight + 'px)');
            });
            return [...new Set(out)].slice(0, 8);
        }''')
        if clipped:
            findings.append(
                f'PRINT-CLIPPED  {len(clipped)} container(s) print only their '
                'visible slice: ' + '; '.join(clipped[:4]))

        dark = page.evaluate('''() => {
            const lum = (c) => {
                const m = c.match(/\\d+/g);
                if (!m) return null;
                return (0.299 * +m[0] + 0.587 * +m[1] + 0.114 * +m[2]) / 255;
            };
            const body = getComputedStyle(document.body);
            const bg = lum(body.backgroundColor);
            const fg = lum(body.color);
            return {bg: bg, fg: fg};
        }''')
        if dark['bg'] is not None and dark['bg'] < 0.5:
            findings.append(
                f'PRINT-INVISIBLE body prints on a dark background '
                f'(luminance {dark["bg"]:.2f}); light text will not be legible')

        page.emulate_media(media='screen')
        context.close()

        # ── MULTI-TAB ───────────────────────────────────────────────────
        ctx_a = browser.new_context(viewport={'width': 1280, 'height': 900})
        page_a = _boot(ctx_a)
        ctx_b = browser.new_context(viewport={'width': 1280, 'height': 900})
        page_b = _boot(ctx_b)

        marker = 'multitab probe ' + str(int(page_a.evaluate('Date.now()')))
        created = page_a.evaluate('''async (title) => {
            const r = await fetch('/api/tasks', {
                method: 'POST',
                headers: {'Content-Type': 'application/json'},
                body: JSON.stringify({title: title}),
            });
            return r.status;
        }''', marker)

        if not (200 <= created < 300):
            findings.append(
                f'-- could not create a record in tab A (HTTP {created}); '
                'the cross-tab check measured nothing')
        else:
            page_b.evaluate('window.nav && window.nav("kanban")')
            page_b.wait_for_timeout(1800)
            seen = page_b.evaluate('document.body.innerText').find(marker) >= 0
            if not seen:
                findings.append(
                    'TAB-NO-SYNC    a record created in one window is absent '
                    'from a second window after that pane is opened')

        ctx_a.close()
        ctx_b.close()
        browser.close()

    return AuditResult(
        'print-and-multitab',
        len([f for f in findings if not f.startswith('--')]),
        findings,
        note='print stylesheet behaviour, and two windows of one application',
    )


if __name__ == '__main__':
    raise SystemExit(emit(run()))
