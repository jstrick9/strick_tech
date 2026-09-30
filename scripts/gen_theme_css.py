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

WHY (r95, #259)
──────────────
The same single-source rule now covers everything derived from THEME_VARS.
Three artifacts are rendered from the one table and cannot drift from it
(`--check` fails on any of the three):

  * frontend/styles-tokens.css — the palette blocks (as before) plus the
    `.theme-tile--<id>` swatch faces for the settings picker. The tiles used
    to carry hand-typed preview colours that did not match the palette they
    claimed to preview (the "Dark Cyber" tile was navy #0f172a while the dark
    palette is #0f0f0f); the faces are now generated from the table, so a
    swatch cannot lie about its own palette.
  * frontend/palettes.json — the same data as structured JSON, served by
    /api/docs/palettes and rendered by the Documentation Center's Themes
    tab (swatches + WCAG contrast ratios + Apply).
  * docs/palettes.md — the human-readable design-system reference: token
    tables per palette, contrast ratios (WCAG 2.x relative luminance,
    measured on --bg-2, the pane surface text actually sits on), and the
    two deliberate block shapes (body-pinned full set vs html-scoped
    diff-only).

SPECIFICITY
───────────
`:root` and `[data-theme="x"]` are both 0-1-0, so the palette blocks are
emitted AFTER the :root base in the same file and win by source order. No
other sheet may define these tokens — tests/unit/test_244 enforces that
styles-tokens.css is the only token definer in the frontend.

The `.theme-tile--<id>` face rules are 0-1-0 class selectors in the
generated region; the hand-written `.theme-tile.theme-tile` base (0-2-0,
earlier in this same file) carries the layout. The doubling is deliberate:
the picker buttons also carry `.btn-3d`, which sets padding/border in
styles-redesign.css and styles-system.css, and the face must not fight the
base for the border colour.

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
PALETTES_MD = REPO / 'docs' / 'palettes.md'
PALETTES_JSON = REPO / 'frontend' / 'palettes.json'

BEGIN = '/* ==== BEGIN generated theme palettes (scripts/gen_theme_css.py) ==== */'
END = '/* ==== END generated theme palettes ==== */'

# Display names and one-line descriptions for the reference artifacts. The
# colours all come from THEME_VARS; only these labels are curated here.
PALETTE_META = {
    'light':    ('Light', 'The default light palette. Body-pinned full-set block: a saved custom accent stays inert (pre-existing behaviour, deliberately preserved).'),
    'dark':     ('Dark', 'The default dark palette — what :root carries, measured as rendered. Body-pinned full-set block: a saved custom accent stays inert.'),
    'obsidian': ('Obsidian', 'Deep blue-black with a sky accent. html-scoped diff-only block: a custom accent stays visible.'),
    'jet':      ('Jet', 'Pure black with a crimson accent. html-scoped diff-only block: a custom accent stays visible.'),
    'midnight': ('Midnight Blue', 'Navy ramp with a violet accent. html-scoped diff-only block: a custom accent stays visible.'),
    'forest':   ('Forest Emerald', 'Green-on-green ramp. html-scoped diff-only block: a custom accent stays visible.'),
    'ember':    ('Ember', 'Warm charcoal with a flame accent. Added in #258 — onboarding offered it as a swatch long before it existed. html-scoped diff-only block.'),
    'ocean':    ('Ocean', 'Deep teal-sea ramp with a cyan accent. Added in #258, same story as ember. html-scoped diff-only block.'),
}

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


# ── WCAG contrast (r95, #259) ────────────────────────────────────────────────

def _srgb_to_linear(channel: int) -> float:
    c = channel / 255.0
    return c / 12.92 if c <= 0.04045 else ((c + 0.055) / 1.055) ** 2.4


def relative_luminance(hex_color: str) -> float | None:
    """WCAG 2.x relative luminance of an opaque #rrggbb colour, else None."""
    m = re.fullmatch(r'#([0-9a-fA-F]{6})', hex_color.strip())
    if not m:
        return None
    r, g, b = (int(m.group(1)[i:i + 2], 16) for i in (0, 2, 4))
    return (0.2126 * _srgb_to_linear(r)
            + 0.7152 * _srgb_to_linear(g)
            + 0.0722 * _srgb_to_linear(b))


def contrast_ratio(fg: str, bg: str) -> float | None:
    l1, l2 = relative_luminance(fg), relative_luminance(bg)
    if l1 is None or l2 is None:
        return None
    lighter, darker = max(l1, l2), min(l1, l2)
    return (lighter + 0.05) / (darker + 0.05)


def contrast_pairs(palette: dict[str, str]) -> list[tuple[str, float]]:
    """Text-on-surface ratios for one palette, measured on bg2.

    bg2 is the card/header surface the text ramp actually sits on; the
    original AA verification in #258 measured per pair on bg-2, so this
    reproduces those numbers. Only opaque #rrggbb values participate — the
    rgba() borders are translucent by design and have no single ratio.
    """
    pairs: list[tuple[str, float]] = []
    bg = palette.get('bg2', '')
    for field in ('text0', 'text1', 'text2', 'text3', 'accentText'):
        ratio = contrast_ratio(palette.get(field, ''), bg)
        if ratio is not None:
            pairs.append((f'{field} on bg2', ratio))
    on_accent = contrast_ratio(palette.get('onAccent', ''), palette.get('accent', ''))
    if on_accent is not None:
        pairs.append(('onAccent on accent', on_accent))
    return pairs


def build_tile_faces(palettes: dict[str, dict[str, str]]) -> str:
    """The settings picker's swatch faces, generated from the palette table.

    A tile previews its palette: background = bg0, text = text0, border =
    bg4 (a visible step from the palette's own ramp — the borders themselves
    are translucent rgba() and would render invisibly at 2px). 'auto' is not
    a palette and gets a hand-written two-tone face in the hand region.
    The face selectors are DOUBLED (0-2-0) for the same reason the base is:
    the picker buttons also carry .btn-3d, and styles-system.css (loaded
    last) sets background/color/border-color on .btn-3d at 0-1-0 — an
    undoubled face would lose all three to sheet order. Measured live:
    the undoubled faces rendered --bg-2 (#1e1e1e) instead of the palette.
    """
    lines = [
        '/* Theme picker tile faces — GENERATED from THEME_VARS. A swatch must',
        '   preview the real palette; hand-typed approximations drift (the old',
        '   "Dark Cyber" tile was navy #0f172a while dark is #0f0f0f). Selectors',
        '   are doubled: .btn-3d (styles-system.css, loaded last) also sets',
        '   background/color/border-color and would win at equal specificity. */',
    ]
    for theme in palettes:
        p = palettes[theme]
        lines.append(
            f'.theme-tile--{theme}.theme-tile--{theme} {{ background: {p["bg0"]}; '
            f'color: {p["text0"]}; border-color: {p["bg4"]}; }}')
    return '\n'.join(lines)


def palettes_json(palettes: dict[str, dict[str, str]]) -> str:
    """The structured artifact served by /api/docs/palettes."""
    out = []
    for theme in palettes:
        p = palettes[theme]
        name, blurb = PALETTE_META[theme]
        tokens = palette_tokens(p)
        pairs = contrast_pairs(p)
        weakest = min(pairs, key=lambda pr: pr[1]) if pairs else ('', 0.0)
        out.append({
            'id': theme,
            'name': name,
            'mode': 'light' if theme == 'light' else 'dark',
            'description': blurb,
            'tokens': {k.lstrip('-'): v for k, v in tokens.items()},
            'contrast': {label: round(ratio, 2) for label, ratio in pairs},
            'weakest_pair': weakest[0],
            'weakest_ratio': round(weakest[1], 2),
        })
    payload = {
        'generated_by': 'scripts/gen_theme_css.py from THEME_VARS (frontend/js/01-app-core.js)',
        'palettes': out,
    }
    return json.dumps(payload, indent=2, ensure_ascii=False) + '\n'


def palettes_md(palettes: dict[str, dict[str, str]]) -> str:
    """docs/palettes.md — the human-readable design-system reference."""
    lines = [
        '# Design-system palettes',
        '',
        '**Single source:** `THEME_VARS` in `frontend/js/01-app-core.js`. This',
        'file, the palette blocks + `.theme-tile--*` faces in',
        '`frontend/styles-tokens.css`, and `frontend/palettes.json` are all',
        '**generated** from that one table by `scripts/gen_theme_css.py`.',
        'Edit the table, then run:',
        '',
        '```bash',
        'python3 scripts/gen_theme_css.py   # --check fails CI on drift',
        '```',
        '',
        '## How the blocks are shaped (and why)',
        '',
        '* **dark / light** are full-set `[data-theme="..."]` blocks that also',
        '  match `<body>`. That body pin is load-bearing: it is what keeps a',
        '  saved custom accent *inert* in the two default themes, exactly as',
        '  the app behaved before the token system existed.',
        '* **The six exotic palettes** are `html[data-theme="..."]` blocks',
        '  carrying only the tokens that differ from the `:root` base. No body',
        '  pin, so a custom accent stays *visible* there — also the',
        '  pre-existing behaviour, deliberately preserved.',
        '* Unknown theme ids resolve to the dark base and warn.',
        '',
        '## Contrast methodology',
        '',
        'WCAG 2.x relative luminance, measured per pair. Text tokens are',
        'measured on `bg2` — the card/header surface the text ramp actually',
        'sits on. Translucent `rgba()` borders have no single ratio and are',
        'excluded. The weakest pairing of each palette is noted below. WCAG AA',
        'is 4.5:1 for body text and 3:1 for large text; the `onAccent`-on-`accent`',
        'pair is button-label text (large/bold by construction), so a value',
        'between 3 and 4.5 there is AA-large-compliant, not a body-text failure.',
        '',
    ]
    for theme in palettes:
        p = palettes[theme]
        name, blurb = PALETTE_META[theme]
        pairs = contrast_pairs(p)
        weakest = min(pairs, key=lambda pr: pr[1]) if pairs else ('—', 0.0)
        lines += [
            f'## {name} (`{theme}`)',
            '',
            blurb,
            '',
            '| Token | Value | | Pair | Ratio |',
            '|---|---|---|---|---|',
        ]
        tokens = palette_tokens(p)
        keys = list(tokens.items())
        for i in range(max(len(keys), len(pairs))):
            left = f'`{keys[i][0]}` | {keys[i][1]}' if i < len(keys) else ' | '
            right = f'`{pairs[i][0]}` | **{pairs[i][1]:.2f}:1**' if i < len(pairs) else ' | '
            lines.append(f'| {left} | | {right} |')
        lines += [
            '',
            f'Weakest pair: **{weakest[0]} at {weakest[1]:.2f}:1**'
            + (' (AA ✓)' if weakest[1] >= 4.5 else ' (AA large-text only — see methodology above)'),
            '',
        ]
    return '\n'.join(lines) + '\n'


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
    # The settings picker's swatch faces, from the same table (r95, #259).
    blocks.append(build_tile_faces(palettes))

    region = BEGIN + '\n' + '\n\n'.join(blocks) + '\n' + END
    out = tokens_css.split(BEGIN, 1)[0] + region + tokens_css.split(END, 1)[1]
    return out


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument('--check', action='store_true',
                    help='fail if any generated artifact has drifted from THEME_VARS')
    args = ap.parse_args()

    palettes = parse_theme_vars()
    artifacts = [
        ('styles-tokens.css', TOKENS_CSS, generate()),
        ('palettes.json', PALETTES_JSON, palettes_json(palettes)),
        ('palettes.md', PALETTES_MD, palettes_md(palettes)),
    ]
    drifted = [name for name, path, content in artifacts
               if not path.exists() or path.read_text(encoding='utf-8') != content]
    if not drifted:
        print('gen_theme_css: in sync (%d palettes, 3 artifacts)' % len(palettes))
        return 0
    if args.check:
        print('gen_theme_css: DRIFTED — %s do not match THEME_VARS.' % ', '.join(drifted))
        print('  Run: python3 scripts/gen_theme_css.py')
        return 1
    for name, path, content in artifacts:
        if name in drifted:
            path.write_text(content, encoding='utf-8')
            print('gen_theme_css: wrote %s' % path.relative_to(REPO))
    return 0


if __name__ == '__main__':
    sys.exit(main())
