"""Real-browser WCAG 2.1 A/AA audit, run with axe-core against all 28 panes.

BASELINE BEFORE THIS WORK: 684 violation nodes across 24 panes.

    aria-allowed-attr            critical  243 nodes / 24 panes
    aria-required-parent         critical  243 nodes / 24 panes
    color-contrast               serious   169 nodes / 24 panes
    scrollable-region-focusable  serious    29 nodes / 24 panes

AFTER: 0.

The four causes were:

1. `role="menuitem"` on every sidebar row. A menuitem must be inside a
   menu/menubar/group — the real parents are role="none" divs — and it forbids
   the `aria-selected` the nav code set on every item on every navigation.
   Two critical rules from one wrong role. It is also semantically wrong:
   these are links to panes, not items in an application menu.

2. A control inside a control. Every row was itself interactive AND contained
   a real <button> for favouriting, so the button's text was absorbed into the
   row's accessible name and activation was ambiguous.

3. Foregrounds chosen independently of the fill they sit on, instead of the
   `--on-accent` token that exists for exactly that pairing — plus a default
   `--accent` (#6366f1) that could not carry ANY accessible foreground:
   black measured 4.23:1 and white 4.47:1, both failing.

4. Scrollable regions with no focusable content, which cannot be scrolled by
   keyboard at all.

This file asserts the outcome (zero violations) rather than the mechanism, so
it stays valid if the implementation changes, and it catches regressions in
panes nobody thought to check.
"""
import json
import os
import pytest

BASE = "http://127.0.0.1:8787"

_AXE_PATH = os.path.join(os.path.dirname(__file__), '..', '..', 'node_modules', 'axe-core', 'axe.min.js')

# The rules that were actually broken, plus the ones most likely to regress
# from the specific fixes applied. Scoped deliberately: a blanket "every axe
# rule" assertion would fail on unrelated pre-existing issues and get muted,
# which is how a11y suites die.
RULES = [
    'aria-allowed-attr',
    'aria-required-parent',
    'aria-required-children',
    'nested-interactive',
    'color-contrast',
    'scrollable-region-focusable',
    'button-name',
    'link-name',
    'aria-valid-attr-value',
]

_DISMISS = """
() => {
  for (const id of ['onboarding-overlay', 'onboarding-modal', 'welcome-banner']) {
    const el = document.getElementById(id);
    if (el) el.remove();
  }
  try { localStorage.setItem('agentic_os_onboarded', '1'); } catch (_) {}
}
"""

_RUN = """
async (rules) => {
  const r = await axe.run(document, {
    runOnly: { type: 'rule', values: rules },
    resultTypes: ['violations'],
  });
  return r.violations.map(v => ({
    id: v.id,
    impact: v.impact,
    count: v.nodes.length,
    sample: v.nodes.slice(0, 3).map(n => ({
      html: (n.html || '').slice(0, 160),
      why: n.any.concat(n.all).map(c => c.message).join(' | ').slice(0, 200),
    })),
  }));
}
"""


@pytest.fixture(scope='module')
def axe_source():
    path = os.path.abspath(_AXE_PATH)
    if not os.path.exists(path):
        pytest.skip('axe-core not installed (npm install axe-core)')
    with open(path) as fh:
        return fh.read()


@pytest.fixture
def audited_page(page, axe_source):
    page.set_viewport_size({'width': 1440, 'height': 900})
    page.goto(BASE)
    page.wait_for_load_state('domcontentloaded')
    page.wait_for_function('typeof window.__delegateDispatch === "function"', timeout=15000)
    page.wait_for_timeout(1500)
    page.evaluate(_DISMISS)
    page.wait_for_timeout(300)
    # The app's own CSP (correctly) forbids inline <script>, so add_script_tag
    # is refused. Evaluating the source is equivalent and does not need a
    # policy exception for the test harness.
    page.evaluate("src => { if (!window.axe) (0, eval)(src); }", axe_source)
    return page


def _audit(pg):
    pg.evaluate("src => { if (!window.axe) (0, eval)(src); }", '') if False else None
    return pg.evaluate(_RUN, RULES)


def _format(pane, violations):
    lines = [f'{pane}: {sum(v["count"] for v in violations)} accessibility violations']
    for v in violations:
        lines.append(f'  [{v["impact"]}] {v["id"]} x{v["count"]}')
        for s in v['sample']:
            lines.append(f'      {s["why"]}')
            lines.append(f'      {s["html"]}')
    return '\n'.join(lines)


def test_the_default_pane_has_no_accessibility_violations(audited_page):
    v = _audit(audited_page)
    assert not v, _format('chat (default)', v)


def test_every_pane_has_no_accessibility_violations(audited_page, axe_source):
    """The whole sidebar, one pane at a time.

    Parametrising over a list hardcoded here would go stale as panes are added;
    the destinations are read from the live sidebar instead, so a new pane is
    audited automatically.
    """
    pg = audited_page
    panes = [p for p in pg.evaluate(
        "() => [...document.querySelectorAll('#sidebar .nav-item')]"
        "        .map(e => e.getAttribute('data-nav'))") if p]
    assert len(panes) >= 20, f'only found {len(panes)} panes; the sidebar did not render'

    failures = []
    for pane in panes:
        pg.evaluate("p => window.nav(p)", pane)
        pg.wait_for_timeout(700)
        pg.evaluate("src => { if (!window.axe) (0, eval)(src); }", axe_source)

        # Sample twice, ~900ms apart.
        #
        # A single sample is not enough for animated elements: the "⚡ LIVE"
        # badge in Studio pulsed opacity to .4, so its contrast swung between
        # 6.76:1 and 2.44:1 across a 2s cycle. An earlier sweep happened to
        # sample a bright frame and reported the pane clean, and the real
        # failure only surfaced later in CI. Two samples at different phases
        # catch that class of bug instead of flaking on it.
        v = pg.evaluate(_RUN, RULES)
        if not v:
            pg.wait_for_timeout(900)
            v = pg.evaluate(_RUN, RULES)
        if v:
            failures.append(_format(pane, v))

    assert not failures, (
        f'{len(failures)} of {len(panes)} panes have accessibility violations:\n\n'
        + '\n\n'.join(failures)
    )


# ══ The specific mechanisms, so a regression names itself ════════════════════

def test_navigation_rows_are_not_menuitems(audited_page):
    """role="menuitem" broke two critical rules at once and was semantically wrong."""
    bad = audited_page.evaluate(
        "() => [...document.querySelectorAll('#sidebar [role=menuitem]')].length")
    assert bad == 0, (
        f'{bad} sidebar rows are still role="menuitem". A menuitem requires a '
        'menu/menubar/group parent (these have role="none" parents) and forbids '
        'aria-selected, which the navigation code sets on every item.'
    )


def test_no_control_contains_another_control(audited_page):
    """Each row was interactive AND held a favourite button."""
    nested = audited_page.evaluate("""() => {
        const out = [];
        for (const c of document.querySelectorAll('#sidebar [role=button], #sidebar button')) {
            const inner = c.querySelectorAll('a[href],button,input,select,textarea,[role=button],[tabindex]');
            if (inner.length) out.push((c.className || c.tagName) + ' contains ' + inner.length);
        }
        return out;
    }""")
    assert not nested, 'interactive controls are nested inside one another:\n' + '\n'.join(nested)


def test_the_active_destination_is_marked_with_aria_current(audited_page):
    """The "you are here" cue, and it must land on the CONTROL, not the container.

    This caught a real regression while the fix was being built: after the rows
    were split into a control plus a sibling button, aria-current was still
    being written to the row — which no longer has a role, so the cue was
    silently dropped for screen-reader users.
    """
    pg = audited_page
    pg.evaluate("() => window.nav('kanban')")
    pg.wait_for_timeout(800)

    marked = pg.evaluate("""() => [...document.querySelectorAll('#sidebar [aria-current="page"]')]
        .map(e => ({ label: e.getAttribute('aria-label'),
                     role: e.getAttribute('role'),
                     nav: (e.closest('[data-nav]') || {}).dataset?.nav }))""")
    assert marked, 'no sidebar entry is marked aria-current after navigating'
    for m in marked:
        assert m['nav'] == 'kanban', f'aria-current is on the wrong destination: {m}'
        assert m['role'] == 'button', (
            f'aria-current is on a container with no role, so it is ignored: {m}'
        )

    assert pg.evaluate(
        "() => document.querySelectorAll('#sidebar [aria-selected]').length") == 0, (
        'aria-selected is back on the navigation; it is not a valid attribute here'
    )


def test_icon_only_favourite_buttons_have_names(audited_page):
    """A ★ glyph alone announces as "star" or as nothing."""
    unnamed = audited_page.evaluate("""() => {
        const out = [];
        for (const b of document.querySelectorAll('.nav-fav-btn, .fav-remove-btn')) {
            const name = (b.getAttribute('aria-label') || '').trim();
            if (!name) out.push(b.outerHTML.slice(0, 100));
        }
        return out;
    }""")
    assert not unnamed, 'icon-only controls with no accessible name:\n' + '\n'.join(unnamed)


def test_the_favourite_button_is_visible_without_a_mouse(audited_page):
    """It was opacity:0 until :hover.

    A keyboard user could Tab to it but never see it, and a touch user — who
    has no hover at all — could not reveal it by any means.
    """
    opacity = audited_page.evaluate("""() => {
        const b = document.querySelector('.fav-remove-btn');
        return b ? parseFloat(getComputedStyle(b).opacity) : null;
    }""")
    if opacity is None:
        pytest.skip('no favourites configured in this state')
    assert opacity > 0.1, (
        f'the remove-favourite button renders at opacity {opacity} without hover, '
        'so it is invisible to keyboard and touch users'
    )


def test_scrollable_regions_are_keyboard_reachable(audited_page):
    """A scrollable div with no focusable child cannot be scrolled by keyboard."""
    stranded = audited_page.evaluate("""() => {
        const out = [];
        for (const el of document.querySelectorAll('div,section,ul')) {
            const cs = getComputedStyle(el);
            const scrolls = /(auto|scroll)/.test(cs.overflowY) && el.scrollHeight > el.clientHeight + 4;
            if (!scrolls || el.offsetParent === null) continue;
            const focusable = el.querySelector('a[href],button,input,select,textarea,[tabindex]:not([tabindex="-1"])');
            const selfFocusable = el.hasAttribute('tabindex');
            if (!focusable && !selfFocusable) out.push((el.id || el.className || el.tagName).toString().slice(0, 60));
        }
        return out;
    }""")
    assert not stranded, (
        'scrollable regions a keyboard user cannot scroll:\n' + '\n'.join(stranded)
    )
