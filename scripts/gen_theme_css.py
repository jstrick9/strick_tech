#!/usr/bin/env python3
"""Render THEME_VARS into CSS palette blocks in styles-tokens.css.

WHY
───
The theme palettes lived only in JavaScript (THEME_VARS in 01-app-core.js):
`applyTheme()` wrote sixteen tokens inline on <html> at runtime, so CSS never
knew a palette existed. Four costs, all measured:

  * The four stylesheets' :root blocks each carried a *different* dark palette
    (20 of 56 tokens conflicted) and the last-loaded sheet silently won.
  * The four non-default palettes (obsidian, jet, midnight, forest — now six,
    with ember and ocean) had NO CSS representation at all, so a user with one
    of them saved got a generic-dark first paint until JavaScript ran.
  * Onboarding offered "Ember" and "Ocean" swatches that did not exist in
    THEME_VARS; `THEME_VARS[tid] || THEME_VARS.light` silently applied the
    LIGHT palette with an orange accent (fixed in r94/#258 by adding both).
  * Two sources of truth is how all of the above happened.

This script makes CSS the rendered artifact and THEME_VARS the single source.
It reads THEME_VARS out of 01-app-core.js (no import — the file is a classic
script, not a module), converts each palette to a `[data-theme="..."]` rule
containing exactly the tokens that differ from the :root base, and rewrites
the generated region of styles-tokens.css in place. Idempotent: an unchanged
THEME_VARS produces an empty diff.

WHAT THE GENERATED BLOCK CONTAINS
─────────────────────────────────
Per palette: the sixteen tokens applyTheme used to write inline
(--bg-0..5, --text-0..3, --border, --border-hi, --accent, --accent-hi,
--accent-text, --on-accent) plus --accent-glow. 'light' additionally carries
the tokens the old [data-theme="light"] sheet blocks provided that
applyTheme never wrote: --bg-base and the three shadows. dark and light are
emitted as full-set [data-theme] blocks (matching <body> too — that body
pin is load-bearing, see build_block); the six exotic palettes are emitted
as html[data-theme] blocks carrying only the tokens that differ from the
:root base.

SPECIFICITY
───────────
`:root` and `[data-theme="x"]` are both 0-1-0, so the palette blocks are
emitted AFTER the :root base in the same file and win by source order. No
other sheet may define these tokens — tests/unit/test_244 enforces that
styles-tokens.css is the only token definer in the frontend.

USAGE
─────
    python3 scripts/gen_theme_css.py            # write
    python3 scripts/gen_theme_css.py --check    # CI: fail if drifted
"""
from __future__ import annotations

import argparse
import json
import re
import sys
from pathlib import Path

REPO = Path(__file__).resolve().parent.parent
CORE_JS = REPO / 'frontend' / 'js' / '01-app-core.js'
TOKENS_CSS = REPO / 'frontend' / 'styles-tokens.css'

BEGIN = '/* ==== BEGIN generated theme palettes (scripts/gen_theme_css.py) ==== */'
END = '/* ==== END generated theme palettes ==== */'

# Fields of a THEME_VARS entry, in emission order, mapped to CSS token names.
FIELD_TO_TOKEN = [
    ('bg0', '--bg-0'), ('bg1', '--bg-1'), ('bg2', '--bg-2'),
    ('bg3', '--bg-3'), ('bg4', '--bg-4'), ('bg5', '--bg-5'),
    ('text0', '--text-0'), ('text1', '--text-1'),
    ('text2', '--text-2'), ('text3', '--text-3'),
    ('border', '--border'), ('borderHi', '--border-hi'),
    ('accent', '--accent'), ('accentHi', '--accent-hi'),
    ('accentText', '--accent-text'), ('onAccent', '--on-accent'),
]

# Tokens the runtime capture (r94, #258) showed flipping for light ONLY —
# they came from the old [data-theme="light"] sheet blocks, which applyTheme
# never wrote. Dark-base values for every other palette.
LIGHT_EXTRAS = {
    '--bg-base': '#f9fafb',
    '--shadow-sm': '0 1px 2px rgba(0,0,0,0.05)',
    '--shadow': '0 4px 12px rgba(0,0,0,0.1)',
    '--shadow-lg': '0 8px 32px rgba(0,0,0,0.15)',
}

# The :root base (dark) values these keys must be compared against, taken
# from the same runtime capture.
DARK_BASE = {
    '--bg-base': '#0a0a0a',
    '--shadow-sm': '0 1px 2px rgba(0,0,0,0.3)',
    '--shadow': '0 4px 12px rgba(0,0,0,0.4)',
    '--shadow-lg': '0 8px 32px rgba(0,0,0,0.5)',
}


def parse_theme_vars() -> dict[str, dict[str, str]]:
    """Read THEME_VARS out of 01-app-core.js.

    The file is a classic script, so it is parsed textually: the object
    literal is bounded by `const THEME_VARS = {` ... `\n};` and each palette
    is a single line of `key:'#value'` pairs. A structural change to that
    layout must fail loudly here rather than silently produce no palettes.
    """
    src = CORE_JS.read_text(encoding='utf-8')
    m = re.search(r'const THEME_VARS = \{(.*?)\n\};', src, re.S)
    if not m:
        raise SystemExit('gen_theme_css: THEME_VARS literal not found in 01-app-core.js')
    out: dict[str, dict[str, str]] = {}
    for line in m.group(1).splitlines():
        pm = re.match(r"\s*(\w+)\s*:\s*\{(.*)\}\s*,?\s*$", line)
        if not pm:
            continue  # comment lines between palettes
        name, body = pm.group(1), pm.group(2)
        palette: dict[str, str] = {}
        for fm in re.finditer(r"(\w+)\s*:\s*'([^']*)'", body):
            palette[fm.group(1)] = fm.group(2)
        if palette:
            out[name] = palette
    if 'dark' not in out or 'light' not in out:
        raise SystemExit(f'gen_theme_css: expected dark+light palettes, got {sorted(out)}')
    return out


def palette_tokens(palette: dict[str, str]) -> dict[str, str]:
    """The tokens one palette block contributes, with applyTheme's derivations."""
    tokens: dict[str, str] = {}
    for field, token in FIELD_TO_TOKEN:
        if palette.get(field):
            tokens[token] = palette[field]
    # --accent-glow was derived at runtime as accent + '22' (8-digit hex,
    # ~13% alpha) for the exotic palettes. dark and light carry an explicit
    # `glow` field instead: their visible glow came from the stylesheets
    # (rgba notation, a slightly different alpha), and value-neutrality
    # freezes what rendered, not what a derivation would produce.
    if palette.get('glow'):
        tokens['--accent-glow'] = palette['glow']
    elif palette.get('accent'):
        tokens['--accent-glow'] = palette['accent'] + '22'
    return tokens


def build_block(palette: dict[str, str], theme: str, root_values: dict[str, str]) -> str:
    """One palette rule. Two shapes, on purpose (r94, #258):

    dark / light  →  [data-theme="x"], FULL token set, no diffing. These must
        match <body> as well as <html>: the old stylesheets redefined every
        token on body via `:root, [data-theme="dark"]`, and that body-scope
        pin is what made a custom accent inert in the two default themes.
        Dropping the body match would silently make saved custom accents
        visible app-wide — a real behaviour change smuggled into a refactor.
        Full-set (no diffing against :root) because for these two the block
        IS the palette definition; a diffed subset would depend on :root
        staying still.

    exotic six    →  html[data-theme="x"], diff-only. These applied through
        applyTheme's inline writes on <html> and inherited down; body never
        had a scoped block for them, so a custom accent stayed visible.
        Scoping to html (and emitting only tokens that differ from the :root
        base) reproduces exactly that: no body pin, inheritance carries the
        palette, an inline accent on html still wins.
    """
    tokens = palette_tokens(palette)
    if theme == 'light':
        tokens.update(LIGHT_EXTRAS)
    if theme in ('dark', 'light'):
        decls = [f'  {token}: {value};' for token, value in tokens.items()]
        return f'[data-theme="{theme}"] {{\n' + '\n'.join(decls) + '\n}'
    decls = [
        f'  {token}: {value};'
        for token, value in tokens.items()
        if root_values.get(token) != value
    ]
    return f'html[data-theme="{theme}"] {{\n' + '\n'.join(decls) + '\n}'


def parse_root_base(tokens_css: str) -> dict[str, str]:
    """The :root block of styles-tokens.css — the diff baseline."""
    m = re.search(r':root\s*\{(.*?)\n\}', tokens_css, re.S)
    if not m:
        raise SystemExit('gen_theme_css: :root base block not found in styles-tokens.css')
    base: dict[str, str] = {}
    for dm in re.finditer(r'(--[\w-]+)\s*:\s*([^;]+);', m.group(1)):
        base[dm.group(1)] = dm.group(2).strip()
    return base


def generate() -> str:
    tokens_css = TOKENS_CSS.read_text(encoding='utf-8')
    if BEGIN not in tokens_css or END not in tokens_css:
        raise SystemExit(
            'gen_theme_css: generated region markers not found in styles-tokens.css.\n'
            'The region must exist (even empty) so this script only ever rewrites '
            'what it owns.')
    base = parse_root_base(tokens_css)
    palettes = parse_theme_vars()

    blocks = []
    # All eight palettes get a block. dark's is a full-set body-match (see
    # build_block): its values equal the :root base, but the block exists to
    # pin the palette on <body> — the old sheets' behaviour — not to differ
    # from :root.
    for theme in palettes:
        blocks.append(build_block(palettes[theme], theme, base))

    region = BEGIN + '\n' + '\n\n'.join(blocks) + '\n' + END
    out = tokens_css.split(BEGIN, 1)[0] + region + tokens_css.split(END, 1)[1]
    return out


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument('--check', action='store_true',
                    help='fail if styles-tokens.css has drifted from THEME_VARS')
    args = ap.parse_args()

    generated = generate()
    current = TOKENS_CSS.read_text(encoding='utf-8')
    if generated == current:
        print('gen_theme_css: in sync (%d palettes)' % len(parse_theme_vars()))
        return 0
    if args.check:
        print('gen_theme_css: DRIFTED — styles-tokens.css does not match THEME_VARS.')
        print('  Run: python3 scripts/gen_theme_css.py')
        return 1
    TOKENS_CSS.write_text(generated, encoding='utf-8')
    print('gen_theme_css: wrote %d palette blocks to %s'
          % (len(parse_theme_vars()), TOKENS_CSS.name))
    return 0


if __name__ == '__main__':
    sys.exit(main())
