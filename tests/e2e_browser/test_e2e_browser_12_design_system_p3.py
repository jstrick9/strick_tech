"""Design system, phase 3: honest skeletons, honest help, real palettes (r95, #259).

WHAT CHANGED
────────────
* Skeletons: all 22 static pane skeletons (and nav()'s fallback for unknown
  pane ids, which used to be an ad-hoc "⚡ Initializing…" string) carry
  role="status" + aria-label, so 153 shimmering bars are announced as a
  loading state instead of nothing; the bars' shimmer is staggered (negative
  animation-delay) so panes don't pulse in lockstep.
* Help: the ? overlay is the ONE help surface. Its list was verified against
  the real bindings — three documented shortcuts were fiction (F7/F8/Ctrl+
  Shift+M, never bound), and the real ⌘1–6, ⌘P, Alt+1–7, Alt+Shift+F, ⌘R,
  ⌘U were missing. The dead #shortcuts-modal + showShortcuts() pair and the
  two divergent backend lists are gone. The overlay renders from classes —
  the old one emitted ~25 parser-refused inline styles on every open.
* Palettes: ember and ocean are selectable from Settings for the first time;
  all nine tiles are class-based with GENERATED faces (a swatch previews the
  real palette — the old "Dark Cyber" tile was navy while dark is neutral);
  applyTheme marks the current tile; the Documentation Center has a Themes
  tab fed by the generated palettes.json; docs/palettes.md documents all
  eight with WCAG contrast.

WHAT THIS FILE PINS
───────────────────
1. Skeleton labelling + stagger + the nav() fallback (live).
2. The ? overlay: opens/closes, class-based, ZERO CSP refusals per open,
   contains the previously-missing real shortcuts and none of the fiction.
3. The ⌘⇧ pane jumps actually land on the panes the help documents —
   including the two double-bound keys, pinned by their final landing pane
   (E → Health, P → Profiler; see docs/module-reviews/92).
4. The settings picker: nine tiles, honest faces, ember applies, the
   current tile is marked.
5. The docs Themes tab renders the generated palette reference and can
   apply a palette.
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
    # first-run surfaces (the same guard test_11 uses)
    pg.evaluate("""() => {
        for (const id of ['onboarding-overlay', 'onboarding-modal', 'welcome-banner']) {
            const el = document.getElementById(id); if (el) el.remove();
        }
    }""")
    yield pg
    ctx.close()


# ── 1. Skeletons ─────────────────────────────────────────────────────────────

def test_all_static_skeletons_are_labelled(shared_page):
    state = shared_page.evaluate("""() => ({
        total: document.querySelectorAll('.pane-skeleton').length,
        labelled: document.querySelectorAll('.pane-skeleton[role="status"][aria-label^="Loading "').length,
    })""")
    # The panes rendered before this ran have already replaced their
    # skeletons, so this is a floor, not an exact census: every skeleton
    # STILL in the DOM must be labelled.
    assert state['total'] > 0, 'no unrendered panes left to inspect — expand this test'
    assert state['total'] == state['labelled'], (
        f"{state['total'] - state['labelled']} skeleton(s) are not labelled loading states — "
        'role="status" + aria-label is the difference between "loading" and 153 silent grey bars'
    )


def test_skeleton_shimmer_is_staggered(shared_page):
    """All bars started their 1.5s shimmer at t=0 before #259 — one flat
    pulse. Negative delays phase-shift the grid so the wave travels."""
    state = shared_page.evaluate("""() => {
        const grid = document.querySelector('.pane:not(.active) .pane-skeleton-grid');
        if (!grid) return {found: false};
        const bars = [...grid.querySelectorAll('.skeleton')];
        return {found: true, delays: bars.map(b => getComputedStyle(b).animationDelay)};
    }""")
    assert state['found'], 'no unvisited skeleton grid to inspect'
    delays = state['delays']
    assert len(delays) >= 3, 'expected a grid with several bars'
    assert delays[0] == '0s', f'first bar should be un-shifted, got {delays[0]!r}'
    assert delays[1] != delays[0] and delays[2] != delays[0], (
        f'grid bars shimmer in lockstep (delays: {delays}) — the stagger rules are not applying'
    )


def test_nav_fallback_is_a_skeleton_not_an_error_string(shared_page):
    """Panes with no static markup (unknown ids, stale deep links) used to
    render an ad-hoc '⚡ Initializing' div. Now they get the same design-
    system skeleton as everything else."""
    page = shared_page
    page.evaluate("() => { document.activeElement && document.activeElement.blur(); window.nav('zz-not-a-real-pane'); }")
    page.wait_for_timeout(200)
    state = page.evaluate("""() => {
        const pane = document.getElementById('pane-zz-not-a-real-pane');
        if (!pane) return {found: false};
        const skel = pane.querySelector('.pane-skeleton');
        return {
            found: true,
            hasSkeleton: !!skel,
            labelled: !!(skel && skel.getAttribute('role') === 'status'
                         && (skel.getAttribute('aria-label') || '').startsWith('Loading ')),
            bars: pane.querySelectorAll('.skeleton').length,
            hasInitString: pane.textContent.includes('Initializing'),
        };
    }""")
    page.evaluate("() => { const p = document.getElementById('pane-zz-not-a-real-pane'); if (p) p.remove(); }")
    assert state['found'], 'nav() did not create the fallback pane'
    assert state['hasSkeleton'] and state['labelled'], (
        'the nav() fallback must be a labelled skeleton — an unrendered pane looks like loading, '
        'not an error state'
    )
    assert state['bars'] >= 4, 'the fallback skeleton must have its bars'
    assert not state['hasInitString'], 'the ad-hoc "⚡ Initializing" string is back'


# ── 2. The ? overlay ─────────────────────────────────────────────────────────

def test_help_overlay_opens_class_based_and_honest(browser):
    """Dedicated fresh page: the refusal count must be attributable to the
    overlay alone, not to boot-time render noise still settling."""
    ctx = browser.new_context()
    page = ctx.new_page()
    page.goto(BASE)
    page.wait_for_load_state('domcontentloaded')
    page.wait_for_timeout(6000)
    page.evaluate("() => { document.activeElement && document.activeElement.blur(); }")
    refusals = {'n': 0}
    handler = lambda m: refusals.__setitem__('n', refusals['n'] + 1) \
        if m.type == 'error' and 'Refused to apply inline style' in m.text else None
    page.on('console', handler)
    try:
        page.keyboard.press('?')
        page.wait_for_timeout(400)
    finally:
        page.remove_listener('console', handler)

    state = page.evaluate("""() => {
        const ov = document.getElementById('kb-shortcuts-overlay');
        if (!ov) return {open: false};
        return {
            open: true,
            inlineStyles: ov.querySelectorAll('[style]').length,
            groups: ov.querySelectorAll('.kbs-group-label').length,
            rows: ov.querySelectorAll('.kbs-row').length,
            text: ov.textContent,
        };
    }""")
    ctx.close()
    assert state['open'], 'pressing ? did not open the help overlay'
    assert state['inlineStyles'] == 0, (
        f"{state['inlineStyles']} inline style attribute(s) in the overlay — the enforced "
        "style-src 'self' refuses each one at parse time"
    )
    assert state['groups'] >= 7, f"expected the grouped list, got {state['groups']} groups"
    assert state['rows'] >= 40, f"expected the full verified list (44 rows), got {state['rows']}"
    # the previously-missing REAL shortcuts
    for needle in ('1–6', 'Profiler', 'Open Arena', 'Toggle voice coding', 'Format current file'):
        assert needle in state['text'], f'the verified list must document {needle!r}'
    # the fiction stays gone
    for banned in ('Next diff', 'Previous diff', 'voice mode (TTS)'):
        assert banned not in state['text'], f'{banned!r} is documented but not bound — a lie'
    assert refusals['n'] == 0, (
        f"opening the help overlay emitted {refusals['n']} inline-style CSP refusals — "
        'the whole point of the class-based rewrite was zero'
    )


def test_help_overlay_esc_closes_and_inputs_are_exempt(shared_page):
    page = shared_page
    page.evaluate("() => { document.activeElement && document.activeElement.blur(); }")
    page.keyboard.press('?')
    page.wait_for_timeout(250)
    assert page.evaluate("() => !!document.getElementById('kb-shortcuts-overlay')"), 'overlay did not open'
    page.keyboard.press('Escape')
    page.wait_for_timeout(150)
    assert not page.evaluate("() => !!document.getElementById('kb-shortcuts-overlay')"), 'Esc did not close the overlay'

    # '?' while typing must NOT open it — with the chat pane active so the
    # textarea can actually take focus (focus() on a hidden pane no-ops)
    page.evaluate("() => window.nav('chat')")
    page.wait_for_timeout(400)
    focused = page.evaluate("""() => {
        const i = document.getElementById('chat-input');
        i.focus();
        return document.activeElement === i;
    }""")
    assert focused, 'chat input did not take focus — the pane may not be active'
    page.keyboard.press('?')
    page.wait_for_timeout(150)
    assert not page.evaluate("() => !!document.getElementById('kb-shortcuts-overlay')"), (
        "'?' inside an input opened the help overlay — typing a question mark must not"
    )
    page.evaluate("() => { const i = document.getElementById('chat-input'); if (i) i.blur(); }")


def test_header_button_and_old_modal(shared_page):
    page = shared_page
    assert not page.evaluate("() => !!document.getElementById('shortcuts-modal')"), (
        'the dead #shortcuts-modal is back in the DOM'
    )
    page.evaluate("() => { const b = document.getElementById('shortcuts-btn'); if (b) b.click(); }")
    page.wait_for_timeout(200)
    assert page.evaluate("() => !!document.getElementById('kb-shortcuts-overlay')"), (
        'the header ⌨️ button must open the unified overlay'
    )
    page.keyboard.press('Escape')
    page.wait_for_timeout(150)


# ── 3. The ⌘⇧ pane jumps land where the help says ────────────────────────────

# Verified against the actual document-level keydown handlers. Two keys have
# two handlers each (registration order decides the landing pane) and are
# pinned by their FINAL effect — the honest thing to document. Note the
# workstation consolidation: an absorbed pane opens its HOST workstation with
# the absorbed pane's tab selected, so the assertion checks both.
PANE_JUMPS = {
    'A': 'arena',    'B': 'bugbot',  'E': 'health',  'F': 'fusion',
    'G': 'codeindex','H': 'hooks',   'K': 'knowledge-graph', 'L': 'leaderboard',
    'M': 'marketplace', 'N': 'hierarchy', 'O': 'observability', 'P': 'profiler',
    'R': 'replay',   'S': 'specs',   'W': 'workflow', 'X': 'websearch',
}


def test_pane_jump_shortcuts_land_where_documented(shared_page):
    page = shared_page
    misses = []
    for letter, pane in PANE_JUMPS.items():
        page.evaluate("() => { document.activeElement && document.activeElement.blur(); }")
        # ⌘ is Ctrl off macOS; the handlers accept e.ctrlKey || e.metaKey
        page.keyboard.press(f'Control+Shift+{letter}')
        page.wait_for_timeout(300)
        state = page.evaluate("""(pane) => {
            const host = (window.PANE_TO_WORKSTATION && window.PANE_TO_WORKSTATION[pane]) || pane;
            return {
                active: (document.querySelector('.pane.active') || {}).id,
                host: 'pane-' + host,
                tabOk: !window.PANE_TO_WORKSTATION || !window.PANE_TO_WORKSTATION[pane]
                       || (window._activeWorkstationTab || {})[host] === pane,
            };
        }""", pane)
        if state['active'] != state['host'] or not state['tabOk']:
            misses.append(
                f'⌘⇧{letter}: documented {pane!r}, landed on {state["active"]!r} '
                f'(expected host {state["host"]!r}, tab selected: {state["tabOk"]})')
    assert not misses, (
        'the help overlay documents pane jumps that do not land where they say:\n  '
        + '\n  '.join(misses)
    )


def test_cmd_p_opens_the_palette(shared_page):
    page = shared_page
    page.evaluate("() => { document.activeElement && document.activeElement.blur(); }")
    page.keyboard.press('Control+p')
    page.wait_for_timeout(400)
    state = page.evaluate("""() => ({
        paletteOpen: document.getElementById('palette-modal')?.classList.contains('open'),
        activePane: (document.querySelector('.pane.active') || {}).id,
    })""")
    page.keyboard.press('Escape')
    page.wait_for_timeout(150)
    assert state['paletteOpen'], '⌘P must open the command palette'
    # The honest footnote: ⌘P is double-bound — the palette opens AND the
    # legacy code-search navigation fires behind it (code search is a tab of
    # the Studio workstation). Pinned as-is; fixing it changes behaviour and
    # is deliberately not smuggled into #259.
    assert state['activePane'] == 'pane-studio', (
        f"⌘P's legacy second binding (Code Search inside Studio) did not fire — if this "
        'was fixed, update the help overlay and this pin together'
    )


# ── 4. The settings picker ───────────────────────────────────────────────────

def test_settings_theme_picker_nine_honest_tiles(shared_page):
    page = shared_page
    page.evaluate("() => window.nav('settings')")
    page.wait_for_timeout(900)
    state = page.evaluate("""() => {
        const tiles = [...document.querySelectorAll('.theme-tile[data-theme-id]')];
        return {
            count: tiles.length,
            inline: tiles.filter(t => t.hasAttribute('style')).length,
            ids: tiles.map(t => t.dataset.themeId),
            darkFace: (() => { const t = tiles.find(x => x.dataset.themeId === 'dark');
                               return t ? getComputedStyle(t).backgroundColor : null; })(),
        };
    }""")
    assert state['count'] == 9, f"expected 9 theme tiles, found {state['count']}"
    assert state['inline'] == 0, 'a theme tile regressed to inline styles'
    for tid in ('light', 'dark', 'auto', 'obsidian', 'jet', 'midnight', 'forest', 'ember', 'ocean'):
        assert tid in state['ids'], f'{tid} tile missing from Settings'
    # the honest face: dark previews #0f0f0f (rgb(15,15,15)), NOT the old
    # navy approximation #0f172a
    assert state['darkFace'] == 'rgb(15, 15, 15)', (
        f"the dark tile previews {state['darkFace']!r} — a swatch must preview the real palette"
    )


def test_settings_tile_applies_ember_and_marks_current(shared_page):
    page = shared_page
    page.evaluate("""() => {
        const t = [...document.querySelectorAll('.theme-tile')]
            .find(x => x.dataset.themeId === 'ember');
        t.click();
    }""")
    page.wait_for_timeout(500)
    state = page.evaluate("""() => ({
        theme: document.documentElement.getAttribute('data-theme'),
        emberActive: (() => { const t = [...document.querySelectorAll('.theme-tile')]
            .find(x => x.dataset.themeId === 'ember'); return t.classList.contains('active'); })(),
        emberPressed: (() => { const t = [...document.querySelectorAll('.theme-tile')]
            .find(x => x.dataset.themeId === 'ember'); return t.getAttribute('aria-pressed'); })(),
        darkPressed: (() => { const t = [...document.querySelectorAll('.theme-tile')]
            .find(x => x.dataset.themeId === 'dark'); return t.getAttribute('aria-pressed'); })(),
    })""")
    # reset before asserting so a failure doesn't leave the suite in ember
    page.evaluate("() => window.applyTheme('dark', undefined, {persist: false})")
    page.evaluate("() => { try { localStorage.setItem('agentic_os_theme', 'dark'); } catch (e) {} }")
    assert state['theme'] == 'ember', (
        f"clicking the ember tile set data-theme={state['theme']!r} — Settings could not apply "
        'the palette onboarding has offered since the wizard was written'
    )
    assert state['emberActive'] and state['emberPressed'] == 'true', 'the applied tile must be marked current'
    assert state['darkPressed'] == 'false', 'the unapplied tile must read aria-pressed=false'


# ── 5. The docs Themes tab ───────────────────────────────────────────────────

def test_docs_themes_tab_renders_the_reference(shared_page):
    page = shared_page
    page.evaluate("() => window.nav('docs')")
    page.wait_for_timeout(900)
    page.evaluate("""() => {
        const b = [...document.querySelectorAll('#pane-docs .docs-tab')]
            .find(t => t.dataset.tab === 'themes');
        if (b) b.click();
    }""")
    page.wait_for_timeout(600)
    state = page.evaluate("""() => ({
        cards: document.querySelectorAll('#pane-docs .pal-card').length,
        swatchColors: [...document.querySelectorAll('#pane-docs .pal-swatch')]
            .filter(el => getComputedStyle(el).backgroundColor !== 'rgba(0, 0, 0, 0)').length,
        currentChip: !!document.querySelector('#pane-docs .pal-current-chip'),
        names: [...document.querySelectorAll('#pane-docs .pal-name')].map(e => e.textContent),
    })""")
    assert state['cards'] == 8, f"expected 8 palette cards, found {state['cards']}"
    assert state['swatchColors'] >= 40, (
        f"only {state['swatchColors']} swatches carry a colour — the CSSOM colour pass is broken"
    )
    assert state['currentChip'], 'the current palette must be marked'
    for name in ('Ember', 'Ocean', 'Dark', 'Obsidian'):
        assert name in state['names'], f'{name} missing from the Themes tab'


def test_docs_themes_tab_applies_a_palette(shared_page):
    page = shared_page
    page.evaluate("""() => {
        const b = [...document.querySelectorAll('#pane-docs .pal-apply')]
            .find(x => x.textContent.includes('Ocean'));
        if (b) b.click();
    }""")
    page.wait_for_timeout(500)
    theme = page.evaluate("() => document.documentElement.getAttribute('data-theme')")
    chip = page.evaluate("""() => {
        const card = [...document.querySelectorAll('#pane-docs .pal-card')]
            .find(c => c.textContent.includes('Ocean'));
        return card ? card.classList.contains('current') : false;
    }""")
    # reset
    page.evaluate("() => window.applyTheme('dark', undefined, {persist: false})")
    page.evaluate("() => { try { localStorage.setItem('agentic_os_theme', 'dark'); } catch (e) {} }")
    assert theme == 'ocean', f'docs Themes "Apply Ocean" set data-theme={theme!r}'
    assert chip, 'the applied card must show as current after the re-render'
