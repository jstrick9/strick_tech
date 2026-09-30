"""One token sheet, generated from one palette source (r94, #258).

WHAT THIS FILE PINS
───────────────────
styles-tokens.css is the single source of truth for design tokens. Before
#258, four stylesheets each carried a :root block — 56 distinct tokens, 20
with conflicting values, the last-loaded sheet silently winning — and the
theme palettes lived only in JavaScript (THEME_VARS), written inline on
<html> at runtime and largely INERT below <body>, where the sheets'
`:root, [data-theme="dark"]` rules redefined every token (the measured
visible palette was the sheets', not THEME_VARS'). Onboarding offered two
palettes ("Ember", "Ocean") that did not exist in THEME_VARS at all; picking
either silently applied the light palette.

The invariants, so none of that can quietly return:

  1. styles-tokens.css is the ONLY frontend stylesheet defining custom
     properties at :root or [data-theme] scope.
  2. The generated palette blocks in styles-tokens.css are exactly what
     scripts/gen_theme_css.py produces from THEME_VARS (no hand edits, no
     drift).
  3. THEME_VARS carries all eight palettes, including ember and ocean —
     the two onboarding offers that used to be phantoms.
  4. Every [data-theme] block the app can switch to has a palette: the
     picker lists and THEME_VARS agree.
  5. The two dead sheets (styles.css, styles-phase5.css — 237KB unloaded)
     stay deleted.
"""

from __future__ import annotations

import json
import re
import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
FRONTEND = ROOT / 'frontend'
TOKENS_CSS = FRONTEND / 'styles-tokens.css'
CORE_JS = FRONTEND / 'js' / '01-app-core.js'

LOADED_SHEETS = [
    'styles-tokens.css', 'styles-unified.css', 'styles-extracted.css',
    'styles-print.css', 'styles-redesign.css', 'styles-system.css',
]


def test_styles_tokens_is_the_only_token_definer():
    offenders = []
    for name in LOADED_SHEETS:
        if name == 'styles-tokens.css':
            continue
        src = (FRONTEND / name).read_text(encoding='utf-8')
        for m in re.finditer(r'([^{}]+)\{([^{}]*)\}', src):
            sel, body = m.group(1).strip(), m.group(2)
            if (':root' in sel or 'data-theme' in sel) and '--' in body:
                offenders.append(f'{name}: {sel[:50]}')
    assert offenders == [], (
        'Only styles-tokens.css may define tokens. Found token definitions in: '
        f'{offenders}. A second definer recreates the #257-era conflict regime '
        'where 20 of 56 tokens disagreed and the last sheet silently won.'
    )


def test_generated_palette_blocks_match_theme_vars():
    """Regenerate and compare — the CSS must be the machine's output, not a
    hand-edited approximation of it."""
    result = subprocess.run(
        [sys.executable, str(ROOT / 'scripts' / 'gen_theme_css.py'), '--check'],
        capture_output=True, text=True, timeout=60)
    assert result.returncode == 0, (
        'styles-tokens.css has drifted from THEME_VARS. '
        f'Run scripts/gen_theme_css.py. Output: {result.stdout} {result.stderr}'
    )


def test_theme_vars_has_all_eight_palettes_including_the_former_phantoms():
    src = CORE_JS.read_text(encoding='utf-8')
    m = re.search(r'const THEME_VARS = \{(.*?)\n\};', src, re.S)
    assert m, 'THEME_VARS literal not found'
    names = re.findall(r'^\s*(\w+)\s*:\s*\{', m.group(1), re.M)
    expected = {'light', 'dark', 'obsidian', 'jet', 'midnight', 'forest', 'ember', 'ocean'}
    assert expected <= set(names), (
        f'THEME_VARS palettes {sorted(names)} are missing {sorted(expected - set(names))}. '
        'Onboarding offers ember and ocean as swatches; a palette missing from '
        'THEME_VARS silently falls back to light (the r93 phantom-theme bug).'
    )


def test_dark_and_light_blocks_are_body_pinned_and_exotic_are_html_scoped():
    """The two selector shapes are load-bearing, not styling whims (r94):

    [data-theme="dark"/"light"] must match <body> — that body-scope pin is
    what kept a custom accent inert in the two default themes, and removing
    it would make every saved custom accent visible app-wide overnight.

    html[data-theme=...] for the exotic six — body never had a scoped block
    for those, so a custom accent stayed VISIBLE. Scoping them to body would
    silently break the accent in six themes.
    """
    src = TOKENS_CSS.read_text(encoding='utf-8')
    assert re.search(r'^\[data-theme="dark"\] \{', src, re.M), (
        'dark needs a full-set [data-theme] block (the body pin)')
    assert re.search(r'^\[data-theme="light"\] \{', src, re.M), (
        'light needs a full-set [data-theme] block (the body pin)')
    for theme in ('obsidian', 'jet', 'midnight', 'forest', 'ember', 'ocean'):
        assert re.search(rf'^html\[data-theme="{theme}"\] \{{', src, re.M), (
            f'{theme} must be html-scoped (custom accents stay visible in exotic themes)')
    # and the dark block must pin the accent (the inertness mechanism)
    dark = re.search(r'\[data-theme="dark"\] \{(.*?)\n\}', src, re.S).group(1)
    assert '--accent: #6a6df2;' in dark, (
        'the dark block must pin --accent on body — without it a saved custom '
        'accent becomes visible in the default theme (a silent app-wide repaint)')


def test_dead_stylesheets_stay_deleted():
    for name in ('styles.css', 'styles-phase5.css'):
        assert not (FRONTEND / name).exists(), (
            f'{name} was deleted in #258 (237KB of CSS no page ever loaded). '
            'If it is back, it is dead weight again — re-delete or load it '
            'deliberately and update this pin.')
    # and index.html must not have grown a link to them
    index = (FRONTEND / 'index.html').read_text(encoding='utf-8')
    assert 'styles-phase5' not in index
    assert not re.search(r'href="/static/styles\.css"', index)


def test_index_html_links_tokens_sheet_first():
    index = (FRONTEND / 'index.html').read_text(encoding='utf-8')
    tokens_at = index.find('styles-tokens.css')
    first_sheet_at = index.find('styles-unified.css')
    assert 0 < tokens_at < first_sheet_at, (
        'styles-tokens.css must load before the component sheets — the token '
        'base is established first, then components build on it.'
    )


def test_skeleton_classes_cover_the_static_pane_placeholders():
    """153 skeleton bars + 58 wrappers were inline-styled in index.html (211
    of the 823 first-load CSP refusals). They are classes now; a regression
    to inline styles would put the refusals straight back."""
    index = (FRONTEND / 'index.html').read_text(encoding='utf-8')
    leftovers = re.findall(r'class="skeleton[^"]*" style="', index)
    assert leftovers == [], (
        f'{len(leftovers)} skeleton bars carry inline styles again — use the '
        '.skel-* classes in styles-tokens.css'
    )
    assert 'class="pane-skeleton"' in index, 'the pane-skeleton wrapper class must exist'
    css = TOKENS_CSS.read_text(encoding='utf-8')
    for cls in ('skel-title', 'skel-sub', 'skel-card', 'skel-block',
                'skel-block-sm', 'skel-panel', 'skel-title-wide'):
        assert f'.{cls}.{cls}' in css, f'{cls} class definition missing'
