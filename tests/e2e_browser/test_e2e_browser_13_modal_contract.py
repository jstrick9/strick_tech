"""The help overlay joins the platform modal contract (r96, #260).

Locked scope (e) of the design-system work: the shortcuts overlay's scrim
carries the platform's `kbd-modal-overlay` class, so the overlay answers to
the same machinery every other modal in the app does —
collectOpenModals()'s ad-hoc discovery, masterEscapeHandler's Esc teardown
(remove + focus restore + toast) and isTrapRoot's Tab focus trap — instead
of a private Esc branch and a Tab that escapes to the page behind it.

What that fixed, live:
* Esc teardown is owned by the master handler; the overlay's own Esc branch
  is belt-and-braces (it cannot fire first — the master is registered
  earlier on the same node and removes the element).
* Tab is trapped inside the dialog (WCAG 2.4.3) — before, focus walked out
  to the page behind the overlay.
* The element is REMOVED on Esc (the `-modal-overlay` teardown branch),
  never left as a display:none orphan that still catches clicks.
"""

from __future__ import annotations

import pytest

BASE = 'http://127.0.0.1:8787'


@pytest.fixture(scope='module')
def shared_page(browser):
    ctx = browser.new_context()
    pg = ctx.new_page()
    pg.goto(BASE)
    pg.wait_for_load_state('domcontentloaded')
    pg.wait_for_timeout(3500)
    # first-run surfaces (the same guard test_11/test_12 use)
    pg.evaluate("""() => {
        for (const id of ['onboarding-overlay', 'onboarding-modal', 'welcome-banner']) {
            const el = document.getElementById(id); if (el) el.remove();
        }
    }""")
    yield pg
    ctx.close()


def _overlay_state(page):
    return page.evaluate("""() => {
        const ov = document.getElementById('kb-shortcuts-overlay');
        const discovered = Array.from(
            document.querySelectorAll('[class*="-modal-overlay"]')
        ).map(el => el.id || el.className);
        return {
            open: !!ov,
            className: ov ? ov.className : null,
            visible: ov ? getComputedStyle(ov).display !== 'none'
                        && getComputedStyle(ov).visibility !== 'hidden' : false,
            discovered,
        };
    }""")


def test_overlay_is_discovered_as_a_platform_modal(shared_page):
    page = shared_page
    page.evaluate("() => { document.activeElement && document.activeElement.blur(); }")
    page.keyboard.press('?')
    page.wait_for_timeout(300)
    state = _overlay_state(page)
    assert state['open'], 'pressing ? did not open the help overlay'
    assert 'kbd-modal-overlay' in (state['className'] or ''), (
        f"the overlay must carry the platform modal class, got {state['className']!r}"
    )
    # the exact selector collectOpenModals() uses must find it, and it must
    # read as open (computed visibility — the same test the master applies)
    assert 'kb-shortcuts-overlay' in state['discovered'], (
        'the ad-hoc [class*="-modal-overlay"] discovery does not find the overlay — '
        'masterEscapeHandler cannot close it'
    )
    assert state['visible'], 'the overlay is not computably visible for collectOpenModals'
    page.keyboard.press('Escape')
    page.wait_for_timeout(150)


def test_escape_teardown_removes_the_element_and_leaves_no_orphan(shared_page):
    page = shared_page
    page.evaluate("() => { document.activeElement && document.activeElement.blur(); }")
    page.keyboard.press('?')
    page.wait_for_timeout(250)
    assert page.evaluate("() => !!document.getElementById('kb-shortcuts-overlay')")
    page.keyboard.press('Escape')
    page.wait_for_timeout(200)
    leftover = page.evaluate("""() => ({
        overlay: !!document.getElementById('kb-shortcuts-overlay'),
        anyModalOverlay: document.querySelectorAll('[class*="-modal-overlay"]').length,
    })""")
    assert not leftover['overlay'], (
        'Esc left the help overlay in the DOM — the master teardown must REMOVE it'
    )
    assert leftover['anyModalOverlay'] == 0, (
        f"{leftover['anyModalOverlay']} modal-overlay element(s) survived Esc — "
        'an orphaned scrim still catches clicks'
    )


def test_tab_is_trapped_inside_the_dialog(shared_page):
    page = shared_page
    page.evaluate("() => { document.activeElement && document.activeElement.blur(); }")
    page.keyboard.press('?')
    page.wait_for_timeout(250)
    inside = []
    for _ in range(4):
        page.keyboard.press('Tab')
        page.wait_for_timeout(60)
        inside.append(page.evaluate(
            "() => { const ov = document.getElementById('kb-shortcuts-overlay');"
            "        return !!ov && (ov === document.activeElement || ov.contains(document.activeElement)); }"
        ))
    for _ in range(2):
        page.keyboard.press('Shift+Tab')
        page.wait_for_timeout(60)
        inside.append(page.evaluate(
            "() => { const ov = document.getElementById('kb-shortcuts-overlay');"
            "        return !!ov && (ov === document.activeElement || ov.contains(document.activeElement)); }"
        ))
    page.keyboard.press('Escape')
    page.wait_for_timeout(150)
    assert all(inside), (
        f'Tab escaped the help overlay dialog ({sum(1 for x in inside if not x)}/6 presses '
        'landed outside) — isTrapRoot no longer traps it'
    )


def test_backdrop_click_and_question_mark_toggle(shared_page):
    page = shared_page
    page.evaluate("() => { document.activeElement && document.activeElement.blur(); }")

    # clicking the backdrop (target === overlay) closes
    page.keyboard.press('?')
    page.wait_for_timeout(250)
    box = page.evaluate("""() => {
        const ov = document.getElementById('kb-shortcuts-overlay');
        const r = ov.getBoundingClientRect();
        // a point on the overlay itself, outside the card
        return {x: Math.max(2, r.left + 4), y: Math.max(2, r.top + 4), w: r.width, h: r.height};
    }""")
    assert box['w'] > 0 and box['h'] > 0, 'the overlay has no backdrop to click'
    page.mouse.click(box['x'], box['y'])
    page.wait_for_timeout(200)
    assert not page.evaluate("() => !!document.getElementById('kb-shortcuts-overlay')"), (
        'clicking the backdrop did not close the overlay'
    )

    # ? toggles: open, then close
    page.keyboard.press('?')
    page.wait_for_timeout(250)
    assert page.evaluate("() => !!document.getElementById('kb-shortcuts-overlay')")
    page.keyboard.press('?')
    page.wait_for_timeout(200)
    assert not page.evaluate("() => !!document.getElementById('kb-shortcuts-overlay')"), (
        'pressing ? again must toggle the overlay closed'
    )
