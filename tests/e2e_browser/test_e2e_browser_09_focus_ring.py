"""Every keyboard tab stop shows a focus ring, and there is a way to skip the chrome.

TWO GAPS THAT axe COULD NOT SEE
───────────────────────────────
The static a11y suite is clean and stays clean. Neither of these was findable
with it:

1. FOCUS RING SUPPRESSED ON 10 CONTROLS.
   Measured in Chromium by pressing real Tab and reading the computed style
   while the element was still focused: 10 of 29 tab stops matched
   `:focus-visible` and rendered NO ring -- outline width 0, no box-shadow.
   Among them the three most-used controls in the product: #chat-input,
   #chat-send and #chat-model-select.

   Cause: all three stylesheets declare `*:focus-visible { outline: 2px ... }`,
   which is specificity 0-0-1-0. Seventeen rules set `outline: none` to hide
   the default ring on inputs, and several are ID selectors (1-0-0-0):

       #chat-input { border:none; outline:none; }

   An ID beats the universal focus rule, so the suppression won and the control
   had no visible focus state at any time. WCAG 2.4.7.

   axe-core does not evaluate :focus-visible styling -- it cannot, without
   synthesising keyboard focus on every node. The existing test (test_93)
   asserts such a rule EXISTS and matches. Nothing checked whether it WINS.

2. NO SKIP LINK.
   A keyboard user tabbed through 12+ chrome controls -- logo, palette,
   Simple/Power, shortcuts, share, notifications, settings, profile, then the
   whole sidebar -- before reaching content, on EVERY navigation, because this
   is a single page and the chrome never unmounts. WCAG 2.4.1.

These tests press real keys. A `.focus()` call does not satisfy
`:focus-visible`, so nothing short of real Tab presses can verify either.
"""
import pytest

BASE = "http://127.0.0.1:8787"

_DISMISS = """
() => {
  for (const id of ['onboarding-overlay', 'onboarding-modal', 'welcome-banner']) {
    const el = document.getElementById(id);
    if (el) el.remove();
  }
  try { localStorage.setItem('agentic_os_onboarded', '1'); } catch (_) {}
}
"""


@pytest.fixture
def app(page):
    page.set_viewport_size({'width': 1440, 'height': 900})
    page.goto(BASE)
    page.wait_for_load_state('domcontentloaded')
    page.wait_for_function('typeof window.__delegateDispatch === "function"', timeout=15000)
    page.wait_for_timeout(1500)
    page.evaluate(_DISMISS)
    page.wait_for_timeout(300)
    return page


# Read the ring on the focused element in ONE evaluate, while it is still
# focused. Measuring after moving on reports the post-blur state and produced
# inconsistent counts (40 stops one run, 29 the next) until this was fixed.
_PROBE = """
() => {
  const a = document.activeElement;
  if (!a || a === document.body) return null;
  const cs = window.getComputedStyle(a);
  return {
    key: a.tagName + '#' + (a.id || '-') + '.' + String(a.className).slice(0, 24),
    focusVisible: a.matches(':focus-visible'),
    outlineWidth: parseFloat(cs.outlineWidth) || 0,
    outlineStyle: cs.outlineStyle,
    hasShadow: (cs.boxShadow || 'none') !== 'none',
  };
}
"""


def _walk(pg, presses=70):
    """Tab through the page, returning one record per distinct stop."""
    pg.evaluate("() => { if (document.activeElement) document.activeElement.blur(); }")
    seen, stops = set(), []
    for _ in range(presses):
        pg.keyboard.press('Tab')
        pg.wait_for_timeout(30)   # let style recalc settle before reading
        d = pg.evaluate(_PROBE)
        if not d or d['key'] in seen:
            continue
        seen.add(d['key'])
        stops.append(d)
    return stops


def test_every_keyboard_tab_stop_has_a_visible_focus_ring(app):
    """A tab stop with no ring is worse than no tab stop: focus is somewhere
    the user cannot see."""
    stops = _walk(app)
    assert len(stops) >= 15, f'only reached {len(stops)} tab stops; did the page render?'

    invisible = [
        d for d in stops
        if d['focusVisible']
        and not ((d['outlineWidth'] >= 1 and d['outlineStyle'] != 'none') or d['hasShadow'])
    ]
    assert not invisible, (
        f'{len(invisible)} of {len(stops)} keyboard tab stops render no focus ring:\n'
        + '\n'.join(f"  {d['key']}  outline={d['outlineWidth']}px {d['outlineStyle']}"
                    for d in invisible[:12])
    )


# NOTE: two tests were written here and DELETED before commit.
#
#   test_the_most_used_controls_specifically_show_a_ring
#   test_the_focus_rule_can_beat_an_id_selector
#
# Both passed against the BROKEN build as well as the fixed one, so they
# asserted nothing. The first used el.focus(), which does not satisfy
# :focus-visible, so it only ever proved the element exists. The second built
# a synthetic probe whose result it then did not assert on.
#
# A test that cannot fail is worse than no test: it makes the suite look like
# it covers something it does not. The real coverage is
# test_every_keyboard_tab_stop_has_a_visible_focus_ring above, which was
# verified to fail against the reverted stylesheet.


# ══ Skip links ════════════════════════════════════════════════════════════════

def test_the_first_tab_stop_is_a_skip_link(app):
    """WCAG 2.4.1. Otherwise a keyboard user pays a 12-control toll to reach
    the content, on every navigation."""
    app.evaluate("() => { document.body.setAttribute('tabindex','-1'); document.body.focus(); }")
    app.keyboard.press('Tab')
    app.wait_for_timeout(200)
    d = app.evaluate("""() => {
        const a = document.activeElement;
        const r = a.getBoundingClientRect();
        return { cls: String(a.className), text: (a.innerText || '').trim(),
                 top: Math.round(r.top), height: Math.round(r.height) };
    }""")
    assert 'skip-link' in d['cls'], f'first tab stop is not a skip link: {d}'
    assert 'skip' in d['text'].lower()


def test_the_skip_link_becomes_visible_when_focused(app):
    """Off-screen until focused is the point; off-screen WHILE focused is the
    bug. `display:none` would also make it unfocusable entirely."""
    app.evaluate("() => { document.body.setAttribute('tabindex','-1'); document.body.focus(); }")
    app.keyboard.press('Tab')
    app.wait_for_timeout(250)
    d = app.evaluate("""() => {
        const a = document.activeElement;
        const r = a.getBoundingClientRect();
        const cs = getComputedStyle(a);
        return { top: Math.round(r.top), h: Math.round(r.height),
                 display: cs.display, visibility: cs.visibility };
    }""")
    assert d['display'] != 'none' and d['visibility'] != 'hidden'
    assert 0 <= d['top'] < 200, f'skip link is still off-screen while focused: {d}'
    assert d['h'] > 10


def test_activating_the_skip_link_moves_focus_into_the_content(app):
    """The half-implemented version scrolls but leaves focus in the chrome, so
    the next Tab continues from the link -- back through everything the user
    just asked to skip."""
    app.evaluate("() => { document.body.setAttribute('tabindex','-1'); document.body.focus(); }")
    app.keyboard.press('Tab')
    app.wait_for_timeout(200)
    app.keyboard.press('Enter')
    app.wait_for_timeout(500)

    focused = app.evaluate("() => document.activeElement && document.activeElement.id")
    assert focused == 'content', f'focus did not move to the content region (got {focused!r})'

    app.keyboard.press('Tab')
    app.wait_for_timeout(200)
    inside = app.evaluate("""() => {
        const c = document.getElementById('content');
        return !!(c && c.contains(document.activeElement));
    }""")
    assert inside, 'the tab after skipping went back into the chrome'


def test_the_content_region_is_programmatically_focusable(app):
    """`tabindex="-1"` is what makes the skip target focusable without adding a
    tab stop of its own."""
    ti = app.evaluate("() => { const c = document.getElementById('content'); return c && c.tabIndex; }")
    assert ti == -1, f'#content tabIndex is {ti}, so a skip link cannot focus it'
