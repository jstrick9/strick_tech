"""Panes must render once per navigation, and workstations must survive it.

WHAT WAS BROKEN
───────────────
Four panes threw `TypeError: Cannot set properties of null (setting
'innerHTML')` on every visit -- renderSystem, renderControlTower,
renderWebhooks, renderTestGen. Their `#pane-<id>` elements did not exist.

Chasing that found a much larger fault. `window.nav` is wrapped 14 times
across 10 files, and the wrappers re-invoke renderers the registry already
ran:

    window.nav = function masterNav19(pane) {
      _base(pane);                                    // registry ran it
      if (pane === 'observability') renderObservability?.();   // again
    };

Measured live: **25 redundant API calls across 10 sampled panes**, and worse,
the duplicate render destroyed the workstation feature. A host renderer is
async -- it awaits fetches, then assigns `pane.innerHTML`. nav() builds the
workstation into the host after the first render settles; the duplicate then
resolves and wipes it. **7 of the 11 workstations were destroyed on first
open, removing 28 absorbed pane elements from the DOM.** That is why those
four renderers found nothing to render into.

THE FIXES, ALL VERIFIED IN A REAL BROWSER
─────────────────────────────────────────
1. `00-render-dedupe.js` -- each pane renderer runs at most once per
   navigation. Applied by wrapping the renderers named in the registry, not
   by editing 40 call sites across 14 wrappers, so wrappers added later are
   covered automatically.
2. `nav()` waits for an async host renderer to settle before building the
   workstation. The old code ran immediately after `renderer()` *returned*,
   which is only correct for synchronous renderers.
3. `initWorkstation()` decides "already built?" from the DOM instead of a
   `data-workstationReady` flag. The flag survived an innerHTML wipe that
   destroyed everything it claimed was ready, so a wiped workstation could
   never rebuild.
4. `showWorkstationTab()` keeps the `active` class in sync with visibility.
   Absorbed panes lost it, and renderers use it as "am I on screen?" --
   `refreshControlTower()` bailed out entirely, leaving a permanent skeleton.
5. nav()'s deactivation swept `.pane` only, never `.ws-body`, so a stale
   `active` left Control Tower polling every 5 s forever after navigating
   away.
6. The workstation redirect no longer calls `showWorkstationTab()` eagerly;
   it records the wanted tab and lets the host's navigation open it. The
   eager call's render was always discarded by the host rebuild.

RESULT: 16 console errors -> 0. 7 broken workstations -> 0. 25 redundant API
calls -> 7.
"""

from __future__ import annotations

import re
from pathlib import Path

REPO = Path(__file__).resolve().parent.parent.parent
JS = REPO / 'frontend' / 'js'

APP_CORE = (JS / '01-app-core.js').read_text(encoding='utf-8')
WORKSTATIONS = (JS / '00-workstations.js').read_text(encoding='utf-8')
DEDUPE = (JS / '00-render-dedupe.js').read_text(encoding='utf-8')
INDEX = (REPO / 'frontend' / 'index.html').read_text(encoding='utf-8')


def _strip_comments(source: str) -> str:
    """Remove comments so assertions cannot match their own explanation.

    This review has hit that trap 11 times: a test asserts on a substring
    that only appears in the comment describing the fix.
    """
    source = re.sub(r'/\*.*?\*/', '', source, flags=re.S)
    return re.sub(r'(?m)^\s*//.*$', '', source)


APP_CORE_CODE = _strip_comments(APP_CORE)
WORKSTATIONS_CODE = _strip_comments(WORKSTATIONS)
DEDUPE_CODE = _strip_comments(DEDUPE)


# ──────────────────────────────────────────────────────────────────────
#  1. Render deduplication exists and is wired in
# ──────────────────────────────────────────────────────────────────────
def test_dedupe_module_is_loaded_before_app_core():
    """It must wrap the renderers before anything can navigate."""
    assert INDEX.index('00-pane-registry.js') < INDEX.index('00-render-dedupe.js')
    assert INDEX.index('00-render-dedupe.js') < INDEX.index('01-app-core.js')


def test_nav_opens_the_dedupe_window():
    assert 'beginNavRender' in APP_CORE_CODE, (
        'nav() must open the render-deduplication window, or the 14 nav '
        'wrappers each re-run the pane renderer')


def test_dedupe_reads_renderer_names_from_the_registry():
    """Not a hand-maintained list -- a new pane must be covered for free."""
    assert 'MASTER_PANE_REGISTRY' in DEDUPE_CODE


def test_dedupe_window_closes_so_refreshes_still_work():
    """Renderers are legitimately re-invoked later as refreshes.

    `renderSecretsVault()` after adding a secret, `renderEvals()` after
    creating a dataset. Suppressing those would be a worse bug than the one
    being fixed.
    """
    assert 'setTimeout' in DEDUPE_CODE, 'the suppression window must expire'
    assert 'active = null' in DEDUPE_CODE


def test_dedupe_window_is_not_held_open_across_awaits():
    """Regression: extending the window past the tick blanked 13 panes.

    An attempt to also suppress showWorkstationTab()'s render suppressed the
    render that actually matters. When an absorbed pane is opened, the
    registry renders it, the HOST's async renderer then replaces the host's
    innerHTML (destroying that DOM), and only then is the pane rendered into
    the rebuilt workstation. The second render is required, not redundant.
    """
    assert 'extendNavRender' not in DEDUPE_CODE, (
        'holding the dedupe window open across nav\'s await suppresses the '
        'absorbed pane\'s real render and leaves the tab empty')
    assert 'extendNavRender' not in APP_CORE_CODE


def test_begin_nav_render_is_idempotent():
    """nav() is wrapped 14 times, so this runs many times per navigation.

    An earlier version reset state on every call, letting an inner wrapper
    tear down the window the outermost navigation still needed. Duplicates
    went from 8 panes to 32.
    """
    body = DEDUPE_CODE[DEDUPE_CODE.index('beginNavRender'):]
    body = body[:body.index('};')]
    assert 'if (active) return' in body, (
        'beginNavRender must no-op when a window is already open')


def test_lazy_chunks_get_deduplicated_too():
    """A lazily loaded pane must not escape deduplication."""
    loader = _strip_comments((JS / '00-chunk-loader.js').read_text(encoding='utf-8'))
    assert 'installRenderDedupe' in loader, (
        'chunk loader must re-wrap renderers defined by a freshly loaded chunk')


# ──────────────────────────────────────────────────────────────────────
#  2. Workstations survive an async host renderer
# ──────────────────────────────────────────────────────────────────────
def test_nav_waits_for_an_async_host_renderer_before_building():
    """The old code ran immediately after `renderer()` returned.

    That is only correct for synchronous renderers. Most host renderers are
    async: they return a pending promise, the workstation gets built into the
    host, and then their await resolves and `pane.innerHTML = ...` deletes it
    along with every absorbed pane.
    """
    assert re.search(r'rendered\s*&&\s*typeof\s+rendered\.then', APP_CORE_CODE), (
        'nav() must await the host renderer before calling initWorkstation')
    assert 'rendered.then(buildWorkstation, buildWorkstation)' in APP_CORE_CODE, (
        'the workstation must still be built if the host renderer rejects')


def test_init_workstation_checks_the_dom_not_a_flag():
    """Regression: `data-workstationReady` outlived what it described.

    The attribute survived an innerHTML wipe that removed the tab strip and
    every absorbed pane, so initWorkstation returned early forever and the
    workstation could never rebuild itself.
    """
    assert "dataset.workstationReady === '1'" not in WORKSTATIONS_CODE, (
        'idempotency must be decided by the DOM, so a wiped workstation '
        'rebuilds on the next navigation')
    assert ":scope > .ws-tabs" in WORKSTATIONS_CODE
    assert ":scope > .ws-bodies" in WORKSTATIONS_CODE


def test_absorbed_panes_keep_active_in_sync_with_visibility():
    """Regression: Control Tower was stuck on its skeleton forever.

    `refreshControlTower()` returns early unless `#pane-control` has the
    `active` class, but initWorkstation() strips it when absorbing a pane.
    """
    # Scope to the loop over pane BODIES. An earlier version searched the
    # whole function and passed against broken code, because the tab BUTTON
    # loop a few lines below contains an identical
    # `classList.toggle('active', on)`. A test that passes with the fix
    # removed proves nothing.
    show = WORKSTATIONS_CODE[WORKSTATIONS_CODE.index('showWorkstationTab'):]
    bodies_loop = show[show.index('.ws-bodies > .ws-body'):show.index('.ws-tabs > .ws-tab')]
    assert "classList.toggle('active', on)" in bodies_loop, (
        'a visible absorbed pane must carry the class the app uses to mean '
        '"on screen"; without it refreshControlTower() bails out and the '
        'pane is stuck on its skeleton')


def test_navigation_deactivates_absorbed_panes_too():
    """Regression: Control Tower polled every 5s forever after leaving it.

    Absorbed panes are `.ws-body`, not `.pane`. Renderers that poll while
    visible use `active` as their stop condition, so a stale class meant the
    timer never stopped.
    """
    assert "querySelectorAll('.pane, .ws-body')" in APP_CORE_CODE, (
        'nav() must clear `active` from absorbed panes as well as top-level '
        'ones, or polling renderers never stop')


def test_workstation_redirect_does_not_render_the_tab_twice():
    """Regression: the eager showWorkstationTab() render was always discarded.

    nav(host) waits for the host's async renderer, which rebuilds the
    workstation and opens the wanted tab itself. Rendering it first just
    refired that pane's API calls for nothing.
    """
    redirect = APP_CORE_CODE[APP_CORE_CODE.index('PANE_TO_WORKSTATION'):]
    redirect = redirect[:redirect.index('NavigationState')]
    assert 'showWorkstationTab' not in redirect, (
        'the redirect should record the wanted tab and let the host\'s own '
        'navigation open it')
    assert 'setWorkstationTab(wsHost, pane)' in redirect, (
        'the redirect must record which tab to open')


# ──────────────────────────────────────────────────────────────────────
#  3. The renderers that crashed now guard their pane lookup
# ──────────────────────────────────────────────────────────────────────
def test_crashing_renderers_no_longer_assume_their_pane_exists():
    """Defence in depth for the four that threw.

    The ordering fixes above mean the element should always be there now, but
    a renderer that assumes a DOM node exists will crash the whole navigation
    if anything ever removes it again. A missing pane should be a no-op.
    """
    cases = {
        '38-system-monitor.js': 'pane-system',
        '31-control-tower.js': 'pane-control',
        '33-webhooks.js': 'pane-webhooks',
        '34-test-generator.js': 'pane-testgen',
    }
    for filename, pane_id in cases.items():
        code = _strip_comments((JS / filename).read_text(encoding='utf-8'))
        idx = code.index(f"getElementById('{pane_id}')")
        following = code[idx:idx + 240]
        assert re.search(r'if\s*\(!\s*pane\s*\)\s*return', following), (
            f'{filename}: renderer must return early when {pane_id} is '
            f'missing instead of throwing on .innerHTML')
