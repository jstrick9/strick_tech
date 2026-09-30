"""One help list, one palette truth (r95, #259).

WHAT THIS FILE PINS
───────────────────
Phase 3 of the design-system work made three things single-source:

  1. SHORTCUTS. Four hand-maintained lists existed (the ? overlay, the dead
     #shortcuts-modal feed in onboarding.py, docs_center.py's list, and the
     overlay's own twin in 01-app-core.js) and they disagreed — the docs
     list claimed ⌘/ opened the documentation center (it focuses the chat
     input) and ⌘⇧P opened the Profiler; the overlay documented F7/F8 and
     Ctrl+Shift+M, none of which are bound anywhere. Now
     93-shortcuts-overlay.js is the single hand-curated source;
     docs_center.KEYBOARD_SHORTCUTS is its flattened mirror, onboarding.py
     imports that mirror, and this test fails if any of the three diverge
     in either direction.
  2. PALETTES. THEME_VARS already owned the palettes (#258); now ALL THREE
     derived artifacts are generated and drift-checked by
     scripts/gen_theme_css.py --check: the styles-tokens.css palette blocks
     (+ the new .theme-tile--* swatch faces), frontend/palettes.json (the
     docs Themes tab feed), and docs/palettes.md.
  3. THE PICKER. Settings offers all nine choices (eight palettes + auto)
     as class-based tiles with GENERATED faces, so a swatch previews the
     real palette; ember and ocean are selectable from Settings for the
     first time; applyTheme marks the current tile. The skeletons a pane
     shows while unrendered carry role="status" + aria-label so 153 bars
     of shimmer are announced as loading, not silence.
"""

from __future__ import annotations

import json
import re
import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
FRONTEND = ROOT / 'frontend'
OVERLAY_JS = FRONTEND / 'js' / '93-shortcuts-overlay.js'
INDEX_HTML = FRONTEND / 'index.html'
TOKENS_CSS = FRONTEND / 'styles-tokens.css'
PALETTES_JSON = FRONTEND / 'palettes.json'
PALETTES_MD = ROOT / 'docs' / 'palettes.md'

PALETTE_IDS = ['light', 'dark', 'obsidian', 'jet', 'midnight', 'forest', 'ember', 'ocean']


def flatten_overlay() -> list[tuple[str, str]]:
    """(key, desc) pairs parsed out of the overlay's data, source of truth.

    Mirrors the flattening the backend mirror uses: glyph modifiers (⌘ ⇧)
    attach directly to what follows; a '+' separates everything else.
    """
    src = OVERLAY_JS.read_text(encoding='utf-8')
    flat: list[tuple[str, str]] = []
    for gm in re.finditer(r"\{keys:\s*\[(.*?)\],\s*desc:\s*'([^']*)'\}", src):
        keys = [k.replace('\\\\', '\\')
                for k in re.findall(r"'((?:[^'\\]|\\.)*)'", gm.group(1))]
        key = ''
        for i, k in enumerate(keys):
            if i == 0:
                key = k
            elif keys[i - 1] in ('⌘', '⇧'):
                key += k
            else:
                key += '+' + k
        flat.append((key, gm.group(2)))
    assert flat, 'overlay shortcut data not found — 93-shortcuts-overlay.js changed shape?'
    return flat


# ── 1. Shortcuts: one list, three surfaces, no divergence ────────────────────

def test_backend_mirror_matches_the_overlay_exactly():
    from backend.routers.docs_center import KEYBOARD_SHORTCUTS as docs_list
    from backend.routers.onboarding import KEYBOARD_SHORTCUTS as onboarding_list

    overlay = [(k, d) for k, d in flatten_overlay()]
    docs = [(e['key'], e['desc']) for e in docs_list]
    onboarding = [(e['key'], e['desc']) for e in onboarding_list]

    assert docs == overlay, (
        'docs_center.KEYBOARD_SHORTCUTS diverged from the help overlay '
        '(93-shortcuts-overlay.js is the source of truth — regenerate the '
        'mirror from it and update both, or the docs pane documents an app '
        'that does not exist)')
    assert onboarding == overlay, (
        'onboarding.py must import the docs_center mirror, not carry its own list')


def test_the_fictional_shortcuts_stay_gone():
    """F7/F8 were never bound; Ctrl+Shift+M was removed as a duplicate long ago.

    They lived in two of the four old lists anyway. If one of these comes
    back, it must come back as a REAL binding first — then the overlay, and
    then this assertion.
    """
    banned = ('F7', 'F8', 'Ctrl+Shift+M')
    overlay_src = OVERLAY_JS.read_text(encoding='utf-8')
    # check the DATA (a keys entry or served row), not explanatory comments
    # that reference the history — the comment is the memory, the data is the lie.
    flat = dict(flatten_overlay())
    for key in banned:
        assert key not in flat, f'{key} documented but not bound — a lie'
        assert not re.search(r"keys:\s*\[[^\]]*'%s'" % re.escape(key), overlay_src)
    for name, path in (('docs_center', ROOT / 'backend/routers/docs_center.py'),
                       ('onboarding', ROOT / 'backend/routers/onboarding.py')):
        src = path.read_text(encoding='utf-8')
        if 'KEYBOARD_SHORTCUTS = [' in src:  # docs_center only; onboarding imports
            for key in banned:
                assert f"'{key}'" not in src, f'{name} documents unbound {key}'
    assert '(planned)' not in overlay_src, 'document real behaviour or nothing'


def test_no_second_help_implementation_survived():
    html = INDEX_HTML.read_text(encoding='utf-8')
    core = (FRONTEND / 'js' / '01-app-core.js').read_text(encoding='utf-8')
    assert 'shortcuts-modal' not in html, 'the dead #shortcuts-modal is back'
    assert 'shortcuts-modal' not in core, 'core still references the dead modal'
    assert 'function showShortcuts' not in core, 'the dead feeder is back'
    # window.showKeyboardShortcuts is defined exactly once across the frontend
    definers = [p.name for p in (FRONTEND / 'js').glob('*.js')
                if 'window.showKeyboardShortcuts =' in p.read_text(encoding='utf-8')]
    assert definers == ['93-shortcuts-overlay.js'], definers


def test_overlay_is_class_based_not_inline_styled():
    """The enforced `style-src 'self'` refuses parser-level style attributes;
    the old overlay emitted ~25 per open and relied on the hydrator to rescue
    them. Classes parse clean."""
    src = OVERLAY_JS.read_text(encoding='utf-8')
    assert "className = 'kbs-overlay'" in src
    assert 'style="' not in src
    assert 'style.cssText' not in src
    assert '.kbs-card' in TOKENS_CSS.read_text(encoding='utf-8')


# ── 2. Palettes: three generated artifacts, zero drift ───────────────────────

def test_generated_artifacts_in_sync_with_theme_vars():
    result = subprocess.run(
        [sys.executable, str(ROOT / 'scripts' / 'gen_theme_css.py'), '--check'],
        capture_output=True, text=True, timeout=60)
    assert result.returncode == 0, (
        f'THEME_VARS artifacts drifted. Run scripts/gen_theme_css.py. '
        f'Output: {result.stdout} {result.stderr}')


def test_palettes_json_shape_and_honesty():
    data = json.loads(PALETTES_JSON.read_text(encoding='utf-8'))
    ids = [p['id'] for p in data['palettes']]
    assert ids == PALETTE_IDS, ids
    for p in data['palettes']:
        assert p['tokens'], f'{p["id"]} has no tokens'
        assert p['contrast'], f'{p["id"]} has no contrast pairs'
        assert p['weakest_ratio'] > 0, f'{p["id"]} weakest ratio missing'
        # the weakest ratio must actually BE the weakest of the reported pairs
        assert abs(min(p['contrast'].values()) - p['weakest_ratio']) < 0.01
    # ember and ocean — the two onboarding offers that were phantoms until #258
    ember = next(p for p in data['palettes'] if p['id'] == 'ember')
    assert ember['tokens']['accent'] == '#f08850'


def test_palettes_md_documents_all_eight():
    src = PALETTES_MD.read_text(encoding='utf-8')
    for pid in PALETTE_IDS:
        assert f'`{pid}`' in src, f'{pid} missing from docs/palettes.md'
    assert 'gen_theme_css.py' in src, 'the regeneration command must be in the doc'
    # After the r95 AA fixes (light onAccent 4.13->4.58, ember text3
    # 4.47->4.96 on bg-3) every palette's weakest pair clears AA body text.
    # If one regresses, the generator marks it 'AA large-text only' — and
    # this assertion fails, forcing a real fix instead of a shrug.
    weak = [m for m in re.finditer(r'Weakest pair: \*\*(.+?) at ([\d.]+):1\*\* \(([^)]+)\)', src)]
    assert len(weak) == len(PALETTE_IDS), f'expected a weakest-pair line per palette, got {len(weak)}'
    for m in weak:
        assert m.group(3) == 'AA ✓', (
            f'{m.group(1)} at {m.group(2)}:1 is below AA body text — fix the palette, '
            'not the doc' if float(m.group(2)) < 4.5 else
            f'{m.group(1)}: ratio {m.group(2)} passes but the label says {m.group(3)!r}')


def test_every_palette_is_aa_for_body_text():
    """The r95 fixes: light's button labels were 4.13:1 (white on the frozen
    accent) and ember's text-3 was 4.47:1 on bg-3 — #258 verified ember on
    bg-2 only. All pairs must now clear 4.5:1."""
    data = json.loads(PALETTES_JSON.read_text(encoding='utf-8'))
    for p in data['palettes']:
        assert p['weakest_ratio'] >= 4.5, (
            f'{p["id"]}: weakest pair {p["weakest_pair"]} at {p["weakest_ratio"]}:1 — '
            'below WCAG AA for body text'
        )


def test_theme_tile_faces_are_generated_not_hand_typed():
    css = TOKENS_CSS.read_text(encoding='utf-8')
    for pid in PALETTE_IDS:
        # faces are DOUBLED (0-2-0): .btn-3d in styles-system.css (loaded
        # last) sets background/color/border-color at 0-1-0 and an undoubled
        # face loses all three to sheet order — measured live, the undoubled
        # faces rendered --bg-2 instead of the palette.
        assert f'.theme-tile--{pid}.theme-tile--{pid} ' in css, f'{pid} tile face missing or not doubled'
    # the hand-written auto face (two-tone device preview, not a palette) is
    # doubled for the same reason — an undoubled one loses its gradient to
    # .btn-3d's background shorthand
    assert '.theme-tile--auto.theme-tile--auto { background: linear-gradient(' in css
    # spot-pin two faces against THEME_VARS values (dark: honest neutral, not
    # the old navy approximation #0f172a; ember: the palette #258 added)
    assert '.theme-tile--dark.theme-tile--dark { background: #0f0f0f; color: #f5f5f5; border-color: #363636; }' in css
    assert '.theme-tile--ember.theme-tile--ember { background: #100a08; color: #fef3ec; border-color: #38221a; }' in css


# ── 3. The picker, the skeletons, and the API ────────────────────────────────

def test_settings_picker_nine_tiles_no_inline_styles():
    html = INDEX_HTML.read_text(encoding='utf-8')
    tiles = re.findall(r'<button[^>]*class="card-3d-tilt btn-3d theme-tile[^"]*"[^>]*>', html)
    assert len(tiles) == 9, f'expected 9 theme tiles, found {len(tiles)}'
    for tid in PALETTE_IDS + ['auto']:
        assert f'data-theme-id="{tid}"' in html, f'{tid} tile missing'
    for tile in tiles:
        assert 'style=' not in tile, 'a theme tile regressed to inline styles'
        assert 'aria-pressed' in tile


def test_all_static_skeletons_are_labelled_loading_states():
    html = INDEX_HTML.read_text(encoding='utf-8')
    total = len(re.findall(r'class="pane-skeleton"', html))
    labelled = len(re.findall(r'class="pane-skeleton" role="status" aria-label="Loading ', html))
    assert total == labelled == 22, (total, labelled)
    # the nav() fallback skeleton (01-app-core.js) is labelled too
    core = (FRONTEND / 'js' / '01-app-core.js').read_text(encoding='utf-8')
    assert 'role="status" aria-label="Loading ${escHtml(pane)}…"' in core


def test_skeleton_stagger_rules_exist():
    css = TOKENS_CSS.read_text(encoding='utf-8')
    for sel in ('.pane-skeleton-grid .skeleton:nth-child(3)',
                '.pane-skeleton-head .skeleton:nth-child(2)'):
        assert sel in css, f'stagger rule missing: {sel}'
    # negative delays only — a positive delay would show a static bar first
    for m in re.finditer(r'pane-skeleton[a-z-]* \.skeleton:nth-child\(\d+\)\s*\{[^}]*\}', css):
        assert 'animation-delay: -' in m.group(0), m.group(0)


def test_palettes_endpoint_serves_the_generated_artifact(client):
    r = client.get('/api/docs/palettes')
    assert r.status_code == 200, r.text
    body = r.json()
    assert body['count'] == 8
    assert [p['id'] for p in body['palettes']] == PALETTE_IDS

    # the shortcuts mirror is what the docs pane serves
    r = client.get('/api/docs/shortcuts')
    assert r.status_code == 200
    served = [(e['key'], e['desc']) for e in r.json()['shortcuts']]
    assert served == flatten_overlay()

    # and the onboarding feed no longer carries its own copy (it serves the
    # bare list — its original shape, kept for the integration/system suites)
    r = client.get('/api/onboarding/shortcuts')
    assert r.status_code == 200
    served = r.json()
    if isinstance(served, dict):
        served = served.get('shortcuts', [])
    assert [(e['key'], e['desc']) for e in served] == flatten_overlay()


def test_docs_pane_has_a_themes_tab():
    src = (FRONTEND / 'js' / '04-workflow-specs.js').read_text(encoding='utf-8')
    assert "docsTab('themes',$this)" in src, 'Themes tab button missing'
    assert "/api/docs/palettes" in src
    # swatch colours go through the CSSOM, never style attributes
    assert 'el.style.background' in src
    assert 'data-swatch' in src
