"""The single-token design system, pinned at the user-visible level (r94, #258).

WHAT CHANGED
────────────
* Four stylesheets each defined a :root token block (20 of 56 tokens in
  conflict, last sheet silently winning); there is now ONE token sheet,
  styles-tokens.css, loaded first.
* The six theme palettes lived only in JS and were written inline on <html>
  — inert below <body>, where the sheets re-defined every token. All eight
  palettes (six + the two former phantoms) are now CSS blocks generated
  from THEME_VARS, and switching themes is an attribute change.
* Onboarding offered "Ember" and "Ocean" swatches that did not exist; picking
  either silently applied the LIGHT palette. Both palettes are real now.
* 304 first-load inline-style CSP refusals were removed (823 -> 519): the
  static pane skeletons (211 attrs) and the settings/chat/shell repeated
  templates became classes. The full-walk noise (~300/pane) is dominated by
  pane-render templates outside this change and is NOT claimed.

WHAT THIS FILE PINS
───────────────────
1. First-load refusals stay under the ratchet (they can only improve).
2. The skeletons render with their shapes intact (they were converted from
   inline attributes to classes; a lost declaration = a broken skeleton).
3. All eight palettes actually apply — including ember and ocean, whose
   swatches onboarding has offered since the wizard was written.
4. The settings active-tab highlight works (it had been suppressed by the
   inline overrides; restoring it was the ONE deliberate visual delta).
"""

from __future__ import annotations

import pytest

BASE = 'http://127.0.0.1:8787'

# 519 measured after #258; +headroom for render variance, far below the 823
# that motivated the work. A regression above this means inline styles crept
# back into boot-critical markup.
FIRST_LOAD_REFUSAL_BUDGET = 560


@pytest.fixture(scope='module')
def shared_page(browser):
    ctx = browser.new_context()
    pg = ctx.new_page()
    yield pg
    ctx.close()


def test_first_load_inline_style_refusals_under_budget(shared_page):
    page = shared_page
    count = {'n': 0}
    page.on('console', lambda m: count.__setitem__('n', count['n'] + 1)
            if m.type == 'error' and 'Refused to apply inline style' in m.text else None)
    page.goto(BASE)
    page.wait_for_load_state('domcontentloaded')
    page.wait_for_timeout(4000)
    assert count['n'] <= FIRST_LOAD_REFUSAL_BUDGET, (
        f'{count["n"]} first-load inline-style refusals (budget {FIRST_LOAD_REFUSAL_BUDGET}; '
        '823 before #258, 519 after). Inline styles are creeping back into '
        'boot-critical markup — convert them to classes (see styles-tokens.css).'
    )


def test_static_skeletons_render_their_shapes(shared_page):
    page = shared_page
    # A pane never visited keeps its static skeleton. Do not navigate.
    state = page.evaluate("""() => {
        const el = document.querySelector('.pane:not(.active) .pane-skeleton');
        if (!el) return {found: false};
        const bars = el.querySelectorAll('.skeleton');
        const card = el.querySelector('.skel-card, .skel-panel, .skel-block, .skel-block-sm');
        const cs = card ? getComputedStyle(card) : null;
        return {
            found: true,
            bars: bars.length,
            cardHeight: cs ? cs.height : null,
            cardRadius: cs ? cs.borderRadius : null,
        };
    }""")
    assert state['found'], 'an unvisited pane must still carry its skeleton wrapper'
    assert state['bars'] >= 2, 'the skeleton must have its bars'
    assert state['cardHeight'] not in (None, '0px'), 'a skeleton block lost its height'


PALETTES = {
    'dark':     {'--bg-0': '#0f0f0f', '--accent': '#6a6df2'},
    'light':    {'--bg-0': '#ffffff', '--accent': '#6a6df2'},
    'obsidian': {'--bg-0': '#040408', '--accent': '#38bdf8'},
    'midnight': {'--bg-0': '#050810', '--accent': '#a855f7'},
    'forest':   {'--bg-0': '#06100a', '--accent': '#10b981'},
    # The two former phantoms: onboarding offered these swatches since the
    # wizard was written; until #258 both silently applied the LIGHT palette.
    'ember':    {'--bg-0': '#100a08', '--accent': '#f08850'},
    'ocean':    {'--bg-0': '#080d10', '--accent': '#38c5d8'},
}


def test_every_palette_actually_applies(shared_page):
    page = shared_page
    results = page.evaluate("""(themes) => {
        const out = {};
        for (const t of themes) {
            window.applyTheme(t, undefined, {persist: false});
            const cs = getComputedStyle(document.body);
            out[t] = {
                bg0: cs.getPropertyValue('--bg-0').trim(),
                accent: cs.getPropertyValue('--accent').trim(),
            };
        }
        window.applyTheme('dark', undefined, {persist: false});
        return out;
    }""", list(PALETTES))
    for theme, expected in PALETTES.items():
        got = results[theme]
        assert got['bg0'] == expected['--bg-0'], (
            f'{theme}: --bg-0 is {got["bg0"]!r}, expected {expected["--bg-0"]!r} — '
            'the palette block is missing or the token sheet is being overridden'
        )
        assert got['accent'] == expected['--accent'], (
            f'{theme}: --accent is {got["accent"]!r}, expected {expected["--accent"]!r}'
        )


def test_phantom_theme_no_longer_falls_back_to_light(shared_page):
    """The r93 phantom-theme bug: applyTheme with an unknown id used to
    resolve to THEME_VARS.light (a light-mode repaint). It must now stay on
    the dark base and say so."""
    page = shared_page
    out = page.evaluate("""() => {
        const warns = [];
        const orig = console.warn;
        console.warn = (...a) => { warns.push(String(a.join(' '))); orig(...a); };
        try { window.applyTheme('not-a-palette', undefined, {persist: false}); }
        finally { console.warn = orig; }
        const cs = getComputedStyle(document.body);
        window.applyTheme('dark', undefined, {persist: false});
        return { bg0: cs.getPropertyValue('--bg-0').trim(), warned: warns.some(w => w.includes('not-a-palette')) };
    }""")
    assert out['bg0'] == '#0f0f0f', (
        f"an unknown palette id resolved to {out['bg0']!r} — it must fall back to "
        'the dark base, not repaint the app light (the phantom-theme bug)'
    )
    assert out['warned'], 'an unknown palette id should warn — silent fallbacks are how the bug survived'


def test_settings_active_tab_is_visibly_highlighted(shared_page):
    """The inline overrides suppressed .settings-nav-item.active since the
    pane was written: the active tab rendered identical to the rest.
    Restoring the highlight was #258's one deliberate visual change."""
    page = shared_page
    page.goto(BASE)
    page.wait_for_load_state('domcontentloaded')
    page.wait_for_timeout(3500)
    page.evaluate("""() => {
        for (const id of ['onboarding-overlay', 'onboarding-modal', 'welcome-banner']) {
            const el = document.getElementById(id); if (el) el.remove();
        }
    }""")
    page.evaluate("window.nav && window.nav('settings')")
    page.wait_for_timeout(800)
    state = page.evaluate("""() => {
        const active = document.querySelector('.settings-nav-item.active');
        const inactive = [...document.querySelectorAll('.settings-nav-item')]
            .find(el => !el.classList.contains('active'));
        if (!active || !inactive) return {found: false};
        return {
            found: true,
            activeBg: getComputedStyle(active).backgroundColor,
            inactiveBg: getComputedStyle(inactive).backgroundColor,
        };
    }""")
    assert state['found'], 'settings nav items must render'
    assert state['activeBg'] != 'rgba(0, 0, 0, 0)', (
        'the active settings tab is transparent again — its highlight is what '
        'the inline overrides used to suppress'
    )
    assert state['activeBg'] != state['inactiveBg'], (
        'active and inactive settings tabs are visually identical'
    )
