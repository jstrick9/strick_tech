#!/usr/bin/env python3
"""Reduced motion, forced colours, and zoom to 200%.

THREE SEAMS, ONE PROBE
──────────────────────
All three are the same shape: the user has told the operating system how they
need to be treated, and the question is whether the application listens. They
share a browser launch because each needs the same page walk under a different
emulated preference.

  MOTION       `prefers-reduced-motion: reduce` is set. An animation that
               still runs is not a cosmetic complaint -- for a user with a
               vestibular disorder it is a physical symptom, and WCAG 2.3.3
               makes it a conformance failure.

  CONTRAST     `forced-colors: active` (Windows High Contrast). The system
               replaces the palette; anything that conveys meaning ONLY
               through a background colour disappears. A status pill that is
               "green = healthy" and nothing else becomes an unlabelled grey
               box.

  ZOOM-200     WCAG 1.4.4 (AA) requires no loss of content or functionality at
               200%. Emulated by halving the viewport, which is what the
               success criterion actually describes -- a 1280x1024 desktop at
               200% has a 640x512 CSS viewport.

MEASUREMENT NOTES
─────────────────
  * Motion is measured from `getComputedStyle`'s animation/transition
    durations, not from a screenshot diff: a diff catches only what happens to
    be moving during the capture window, which makes the result depend on
    timing luck.
  * Under forced colours the probe looks for elements whose ONLY distinguishing
    feature is background-colour. An element that also has text, a border, or
    an accessible name survives the palette swap and is not a finding.
  * Zoom checks horizontal overflow of the DOCUMENT, and separately whether
    any interactive control has been pushed outside the viewport. Content that
    merely reflows is correct behaviour; content that becomes unreachable is
    not.
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

PANES = ['chat', 'kanban', 'goals', 'agents', 'settings', 'studio']

# WCAG 2.3.3 allows motion under ~5s only if it is essential; anything that
# still animates for a meaningful duration under `reduce` is reported.
MOTION_THRESHOLD_MS = 100


def _walk(page, panes=PANES, settle=500):
    for pane in panes:
        page.evaluate(f'window.nav && window.nav({json.dumps(pane)})')
        page.wait_for_timeout(settle)


def run() -> AuditResult:
    preflight()
    findings = []

    from playwright.sync_api import sync_playwright

    with sync_playwright() as p:
        browser = p.chromium.launch(executable_path=chrome_path(), args=LAUNCH_ARGS)

        # ── 1. Reduced motion ───────────────────────────────────────────
        context = browser.new_context(viewport={'width': 1440, 'height': 900},
                                      reduced_motion='reduce')
        page = context.new_page()
        page.goto(BASE_URL, wait_until='domcontentloaded', timeout=60000)
        page.wait_for_timeout(3500)
        _walk(page)

        moving = page.evaluate(f'''() => {{
            const out = [];
            const ms = (v) => (v || '').split(',')
                .map(s => s.trim().endsWith('ms')
                    ? parseFloat(s)
                    : parseFloat(s) * 1000)
                .reduce((a, b) => Math.max(a, b || 0), 0);
            document.querySelectorAll('*').forEach(el => {{
                if (el.offsetParent === null) return;
                const cs = getComputedStyle(el);
                const dur = Math.max(ms(cs.animationDuration), ms(cs.transitionDuration));
                if (dur < {MOTION_THRESHOLD_MS}) return;
                // An animation that is not actually applied to anything is
                // inert; `animation-name: none` with a duration set is a very
                // common harmless pattern.
                const named = cs.animationName && cs.animationName !== 'none';
                const transitions = cs.transitionProperty
                    && cs.transitionProperty !== 'none'
                    && cs.transitionProperty !== 'all';
                if (!named && !transitions) return;
                out.push((el.tagName + '.' + String(el.className).split(' ')[0])
                         .slice(0, 40) + ' ' + Math.round(dur) + 'ms');
            }});
            return [...new Set(out)];
        }}''')
        if moving:
            findings.append(
                f'MOTION         {len(moving)} element type(s) still animate '
                f'under prefers-reduced-motion: ' + ', '.join(moving[:6]))
        context.close()

        # ── 2. Forced colours ───────────────────────────────────────────
        context = browser.new_context(viewport={'width': 1440, 'height': 900},
                                      forced_colors='active')
        page = context.new_page()
        page.goto(BASE_URL, wait_until='domcontentloaded', timeout=60000)
        page.wait_for_timeout(3500)
        _walk(page)

        colour_only = page.evaluate('''() => {
            const out = [];
            document.querySelectorAll(
                '[class*="status"], [class*="badge"], [class*="pill"], '
                + '[class*="dot"], [class*="indicator"], [class*="chip"]'
            ).forEach(el => {
                if (el.offsetParent === null) return;
                const text = (el.innerText || '').trim();
                if (text) return;                                   // labelled
                if (el.getAttribute('aria-label')) return;
                if (el.getAttribute('title')) return;
                if (el.querySelector('svg, img')) return;           // has a shape
                // Vendored third-party UI is not ours to patch, and this one
                // is a false positive besides: `.monaco-status` is Monaco's
                // own aria-live announcement region, deliberately empty and
                // deliberately invisible. It is not a colour indicator at all
                // -- it matched only because the selector list looks for
                // "status" in a class name.
                if (el.closest('.monaco-editor, .monaco-aria-container, [class^="monaco-"]')) return;
                if (el.getAttribute('aria-live')) return;

                const cs = getComputedStyle(el);
                // Under forced-colors the UA overrides backgrounds, so a
                // meaning carried only by background-color is now gone.
                if (cs.borderStyle !== 'none' && parseFloat(cs.borderWidth) > 0) return;
                out.push((el.tagName + '.' + String(el.className).split(' ')[0]).slice(0, 44));
            });
            return [...new Set(out)];
        }''')
        if colour_only:
            findings.append(
                f'CONTRAST       {len(colour_only)} indicator type(s) convey '
                f'meaning by colour alone: ' + ', '.join(colour_only[:6]))
        context.close()

        # ── 3. Zoom to 200% ─────────────────────────────────────────────
        # WCAG 1.4.4 at 200% on a 1280x1024 desktop = a 640x512 CSS viewport.
        context = browser.new_context(viewport={'width': 640, 'height': 512})
        page = context.new_page()
        page.goto(BASE_URL, wait_until='domcontentloaded', timeout=60000)
        page.wait_for_timeout(3500)

        for pane in PANES:
            page.evaluate(f'window.nav && window.nav({json.dumps(pane)})')
            page.wait_for_timeout(500)
            overflow = page.evaluate('''() => {
                const d = document.documentElement;
                return {scroll: d.scrollWidth, client: d.clientWidth};
            }''')
            if overflow['scroll'] > overflow['client'] + 4:
                findings.append(
                    f'ZOOM-200       {pane}: document is '
                    f'{overflow["scroll"]}px wide in a {overflow["client"]}px '
                    'viewport, forcing horizontal scrolling')

            # A closed off-canvas drawer is CORRECT responsive design, not a
            # WCAG failure: the sidebar sits at left:-300px behind a menu
            # button and slides in on demand. The first version of this check
            # counted its 24 links as unreachable controls, which buried the
            # real finding (an overflowing topbar) under noise.
            #
            # So: skip anything inside a container that is translated off
            # screen AND has a control that opens it.
            offscreen = page.evaluate('''() => {
                const w = document.documentElement.clientWidth;
                const out = [];
                // Detect the drawer by GEOMETRY, not by parsing its transform
                // matrix. The first version matched `matrix(1,0,0,1,-300,0)`
                // literally, which missed the same drawer whenever it was
                // moved by `left`, a percentage translate, or a matrix with
                // any scale -- so sidebar controls were still reported as
                // unreachable. What actually defines a closed drawer is that
                // the whole container is parked outside the viewport.
                const inClosedDrawer = (el) => {
                    for (let n = el; n && n !== document.body; n = n.parentElement) {
                        const cs = getComputedStyle(n);
                        if (cs.position !== 'fixed' && cs.position !== 'absolute') continue;
                        const r = n.getBoundingClientRect();
                        // Tolerance of 1px: the sidebar parks at exactly
                        // right: 0 (left -300, width 300), and a strict `<= 0`
                        // treated that as still on screen -- so every control
                        // inside the closed drawer was reported unreachable.
                        if (r.width > 0 && (r.right <= 1 || r.left >= w - 1)) return true;
                    }
                    return false;
                };
                document.querySelectorAll(
                    'button, a[href], input, select, textarea, [role=button]'
                ).forEach(el => {
                    if (el.offsetParent === null) return;
                    const r = el.getBoundingClientRect();
                    if (r.width === 0 || r.height === 0) return;
                    if (r.left >= w || r.right <= 0) {
                        if (inClosedDrawer(el)) return;
                        out.push((el.innerText || el.getAttribute('aria-label')
                                  || el.tagName).trim().replace(/\\s+/g, ' ').slice(0, 24));
                    }
                });
                return [...new Set(out)];
            }''')
            if offscreen:
                findings.append(
                    f'ZOOM-200       {pane}: {len(offscreen)} control(s) sit '
                    'outside the viewport: ' + ', '.join(offscreen[:5]))
        context.close()
        browser.close()

    return AuditResult(
        'user-preferences',
        len([f for f in findings if not f.startswith('--')]),
        findings,
        note='reduced motion, forced colours, and WCAG 1.4.4 zoom to 200%',
    )


if __name__ == '__main__':
    raise SystemExit(emit(run()))
