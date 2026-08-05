"""Real-browser regression tests for the mobile navigation drawer.

THE BUG THESE PIN
─────────────────
Both stylesheets that index.html actually links carried the same rule:

    @media (max-width: 768px) { #sidebar { display: none !important; } }

(styles-unified.css:1258 and styles-redesign.css:595)

and nothing was ever built to replace the sidebar at that width. Measured in
Chromium at 390x844 before the fix: `#sidebar` computed to `display:none`,
0x0, and all 28 `.nav-item` destinations measured 0x0 and were unclickable.
`#sidebar-toggle-btn` is a child of the sidebar, so it disappeared too — no
control anywhere on the page could bring the navigation back.

On a phone, and on a tablet in portrait, the product collapsed to one pane:
Chat, Code Studio, Memory, Tasks, Settings and 23 other destinations had no
reachable entry point. `display:none` also strips the subtree from the
accessibility tree, so this hit screen-reader and keyboard users identically.

These tests are written against observable browser state — computed geometry,
`inert`, focus, the active pane — not against the presence of markup, because
the pre-fix DOM contained all 28 nav items and a DOM-presence test would have
passed against the broken build.

WHY THESE TESTS DRIVE CLICKS VIA element.click()
────────────────────────────────────────────────
Playwright's actionability checks refuse to click a nav row here: the
first-run overlay covers it before dismissal, and after navigation the newly
rendered pane covers the coordinates the drawer used to occupy. Both are
correct app behaviour. Dispatching the click on the element exercises the same
delegated handler without fighting the auto-retry, which otherwise turns a
pass into a multi-minute hang.
"""
import pytest

BASE = "http://127.0.0.1:8787"

PHONE = {'width': 390, 'height': 844}
TABLET_PORTRAIT = {'width': 768, 'height': 1024}
DESKTOP = {'width': 1440, 'height': 900}

# Reads the drawer's observable state in one round trip.
_PROBE = """
() => {
  const q = s => document.querySelector(s);
  const box = e => {
    if (!e) return null;
    const r = e.getBoundingClientRect();
    return { w: Math.round(r.width), h: Math.round(r.height), x: Math.round(r.left) };
  };
  const sb = q('#sidebar');
  const burger = q('#mobile-nav-btn');
  return {
    burger:   box(burger),
    sidebar:  box(sb),
    inert:    sb ? sb.hasAttribute('inert') : null,
    open:     document.body.classList.contains('mobile-nav-open'),
    expanded: burger ? burger.getAttribute('aria-expanded') : null,
    navCount: document.querySelectorAll('#sidebar .nav-item').length,
    scrim:    box(q('#mobile-nav-scrim')),
    activePane: [...document.querySelectorAll('[id^=pane-]')]
                  .filter(e => e.offsetParent !== null).map(e => e.id)[0] || null,
  };
}
"""

_DISMISS_OVERLAY = """
() => {
  for (const id of ['onboarding-overlay', 'onboarding-modal', 'welcome-banner']) {
    const el = document.getElementById(id);
    if (el) el.remove();
  }
  try { localStorage.setItem('agentic_os_onboarded', '1'); } catch (_) {}
}
"""


def _load(page, viewport):
    page.set_viewport_size(viewport)
    page.goto(BASE)
    page.wait_for_load_state('domcontentloaded')
    page.wait_for_function('typeof window.__delegateDispatch === "function"', timeout=15000)
    page.wait_for_timeout(800)
    page.evaluate(_DISMISS_OVERLAY)
    page.wait_for_timeout(200)
    return page


@pytest.mark.parametrize('viewport,label', [(PHONE, 'phone'), (TABLET_PORTRAIT, 'tablet-portrait')])
def test_navigation_is_reachable_below_the_mobile_breakpoint(page, viewport, label):
    """The core regression: some control must be able to reveal the nav.

    Pre-fix this failed at both widths — there was no such control at all.
    """
    _load(page, viewport)
    before = page.evaluate(_PROBE)

    assert before['burger'] is not None, (
        f'[{label}] no navigation control exists at {viewport["width"]}px — '
        'the sidebar is hidden and nothing can bring it back'
    )
    assert before['burger']['w'] > 0 and before['burger']['h'] > 0, (
        f'[{label}] the navigation button exists but is not rendered'
    )
    # WCAG 2.5.5 / iOS HIG minimum touch target.
    assert before['burger']['w'] >= 44 and before['burger']['h'] >= 44, (
        f'[{label}] navigation button is {before["burger"]["w"]}x{before["burger"]["h"]}, '
        'below the 44x44 minimum touch target'
    )

    # Closed: off-canvas and out of the a11y tree / tab order.
    assert before['open'] is False
    assert before['inert'] is True, f'[{label}] closed drawer is still focusable'
    assert before['sidebar']['x'] < 0, f'[{label}] closed drawer is not off-canvas'
    assert before['expanded'] == 'false'

    page.eval_on_selector('#mobile-nav-btn', 'e => e.click()')
    page.wait_for_timeout(500)
    after = page.evaluate(_PROBE)

    assert after['open'] is True, f'[{label}] the navigation button did not open the drawer'
    assert after['sidebar']['x'] == 0, f'[{label}] drawer did not slide on-canvas'
    assert after['sidebar']['w'] > 200, f'[{label}] drawer is too narrow to use'
    assert after['inert'] is False, f'[{label}] open drawer is still inert'
    assert after['expanded'] == 'true', f'[{label}] aria-expanded not updated'
    assert after['navCount'] >= 20, (
        f'[{label}] only {after["navCount"]} destinations in the drawer'
    )


def test_choosing_a_destination_navigates_and_closes_the_drawer(page):
    """A drawer that stays open covers the pane the user just asked for."""
    _load(page, PHONE)
    page.eval_on_selector('#mobile-nav-btn', 'e => e.click()')
    page.wait_for_timeout(400)
    assert page.evaluate(_PROBE)['open'] is True

    page.eval_on_selector('#sidebar .nav-item[data-nav="kanban"]', 'e => e.click()')
    page.wait_for_timeout(800)
    after = page.evaluate(_PROBE)

    assert after['activePane'] == 'pane-kanban', (
        f'navigation from the drawer did not switch panes (active: {after["activePane"]})'
    )
    assert after['open'] is False, 'the drawer stayed open on top of the pane it navigated to'
    assert after['inert'] is True, 'the closed drawer is still in the tab order'


def test_escape_closes_the_drawer_and_returns_focus(page):
    """A drawer with no keyboard exit is a focus trap.

    This one caught a real ordering bug during development: registered on the
    bubble phase, this handler never fired for Escape, because the app already
    installs capture-phase Escape handling that can stop the event first.
    """
    _load(page, PHONE)
    page.eval_on_selector('#mobile-nav-btn', 'e => e.click()')
    page.wait_for_timeout(400)
    assert page.evaluate(_PROBE)['open'] is True

    page.keyboard.press('Escape')
    page.wait_for_timeout(400)

    assert page.evaluate(_PROBE)['open'] is False, 'Escape did not close the drawer'
    assert page.evaluate('() => document.activeElement && document.activeElement.id') == 'mobile-nav-btn', (
        'focus was not returned to the control that opened the drawer — '
        'a keyboard user is left with no focus position'
    )


def test_the_scrim_closes_the_drawer(page):
    _load(page, PHONE)
    page.eval_on_selector('#mobile-nav-btn', 'e => e.click()')
    page.wait_for_timeout(400)
    assert page.evaluate(_PROBE)['open'] is True

    page.eval_on_selector('#mobile-nav-scrim', 'e => e.click()')
    page.wait_for_timeout(400)
    assert page.evaluate(_PROBE)['open'] is False, 'tapping outside the drawer did not close it'


def test_desktop_layout_is_untouched(page):
    """The drawer must not leak into the desktop layout.

    An inert sidebar or a stray hamburger on desktop would be a worse bug than
    the one being fixed, so it gets its own assertion.
    """
    _load(page, DESKTOP)
    s = page.evaluate(_PROBE)

    assert s['sidebar']['w'] > 200, 'the desktop sidebar is not at full width'
    assert s['sidebar']['x'] == 0, 'the desktop sidebar has been pushed off-canvas'
    assert s['inert'] is False, 'the desktop sidebar was made inert — navigation would be dead'
    assert s['burger'] is None or s['burger']['w'] == 0, 'the mobile hamburger is showing on desktop'
    assert s['scrim'] is None or s['scrim']['w'] == 0, 'the mobile scrim is showing on desktop'


def test_crossing_the_breakpoint_does_not_strand_the_drawer(page):
    """Rotating a phone to landscape crosses 768px with the drawer open."""
    _load(page, PHONE)
    page.eval_on_selector('#mobile-nav-btn', 'e => e.click()')
    page.wait_for_timeout(400)
    assert page.evaluate(_PROBE)['open'] is True

    page.set_viewport_size(DESKTOP)
    page.wait_for_timeout(500)
    s = page.evaluate(_PROBE)

    assert s['open'] is False, 'drawer state survived the move to a desktop viewport'
    assert s['inert'] is False, 'the sidebar is inert at desktop width — navigation is dead'
    assert s['sidebar']['x'] == 0 and s['sidebar']['w'] > 200


def test_csp_contains_no_invalid_sources(page):
    """Chromium logged an invalid connect-src source on every page load.

    `https://jira.*.atlassian.net` is not legal CSP: a wildcard may only be the
    entire leftmost label. Chromium discarded the source, so Jira connector
    calls from the browser were blocked no matter the host, and the recurring
    console error trained everyone to ignore CSP output.
    """
    problems = []
    page.on('console', lambda m: problems.append(m.text[:300])
            if ('invalid source' in m.text or 'Unrecognized' in m.text) else None)
    page.set_viewport_size(DESKTOP)
    page.goto(BASE)
    page.wait_for_load_state('domcontentloaded')
    page.wait_for_timeout(2500)

    assert not problems, 'browser rejected part of the CSP:\n' + '\n'.join(problems)
