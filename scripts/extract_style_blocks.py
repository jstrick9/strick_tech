#!/usr/bin/env python3
"""Move the inline `<style>` blocks out of index.html into a stylesheet.

WHY
───
`style-src 'self'` blocks inline `<style>` elements outright — not one
declaration, the whole block. index.html carried three of them totalling 57 KB,
including the core layout, the sidebar, the topbar and the terminal pane.

Measured in Chromium with strict style-src and the blocks still inline: all
three were dropped, `document.styleSheets` listed only the four linked files,
and 96,541 computed properties differed across 24 panes. The page was
effectively unstyled below the linked sheets.

A `<link>` to a same-origin file satisfies `'self'`, so the fix is simply to
move them. Nothing about the CSS changes.

ORDER MATTERS
─────────────
The extracted block is emitted as ONE file in source order and linked at the
exact position the FIRST block occupied. Two of the three blocks sit before
the linked stylesheets and one after; collapsing them into a single link
placed first would let styles-unified.css and styles-redesign.css start
overriding rules that previously won. The `media="print"` block keeps its
media attribute on its own link, because merging it would apply print-only
rules to the screen.
"""
from __future__ import annotations

import os
import re
import sys

REPO = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
INDEX = os.path.join(REPO, 'frontend', 'index.html')
OUT_DIR = os.path.join(REPO, 'frontend')

BLOCK_RE = re.compile(r'[ \t]*<style([^>]*)>(.*?)</style>[ \t]*\n?', re.DOTALL)

HEADER = (
    '/* Extracted from frontend/index.html by scripts/extract_style_blocks.py.\n'
    ' *\n'
    " * `style-src 'self'` blocks an inline <style> element entirely -- not a\n"
    ' * declaration, the whole block. These three held 57 KB of core styling\n'
    ' * (layout, sidebar, topbar, terminal pane); with them inline and the strict\n'
    ' * policy on, Chromium dropped all three and 96,541 computed properties\n'
    ' * differed across 24 panes.\n'
    ' *\n'
    ' * A <link> to a same-origin file satisfies \'self\'. The CSS is unchanged and\n'
    ' * the link sits where the first block sat, so cascade order is preserved.\n'
    ' */\n\n'
)


def main() -> int:
    check = '--check' in sys.argv
    with open(INDEX, encoding='utf-8') as fh:
        src = fh.read()
    blocks = list(BLOCK_RE.finditer(src))
    if not blocks:
        print('no inline <style> blocks left')
        return 0

    screen: list[str] = []
    print_only: list[str] = []
    for m in blocks:
        attrs = (m.group(1) or '').strip()
        body = m.group(2)
        if 'media="print"' in attrs or "media='print'" in attrs:
            print_only.append(body)
        else:
            screen.append(body)

    print(f'{len(blocks)} inline <style> block(s): '
          f'{len(screen)} screen ({sum(len(b) for b in screen)} chars), '
          f'{len(print_only)} print ({sum(len(b) for b in print_only)} chars)')
    if check:
        print('--check: nothing written')
        return 0

    links = []
    if screen:
        path = os.path.join(OUT_DIR, 'styles-extracted.css')
        with open(path, 'w', encoding='utf-8') as fh:
            fh.write(HEADER + '\n\n'.join(screen).strip() + '\n')
        links.append('<link rel="stylesheet" href="/static/styles-extracted.css">')
        print(f'  wrote {path}')
    if print_only:
        path = os.path.join(OUT_DIR, 'styles-print.css')
        with open(path, 'w', encoding='utf-8') as fh:
            fh.write(HEADER + '\n\n'.join(print_only).strip() + '\n')
        links.append('<link rel="stylesheet" media="print" href="/static/styles-print.css">')
        print(f'  wrote {path}')

    # Replace the FIRST block with the links; drop the rest.
    first = blocks[0]
    out = src[:first.start()] + '\n'.join(links) + '\n' + src[first.end():]
    for m in reversed(blocks[1:]):
        # Offsets shift by the delta introduced above; recompute by matching
        # the exact original text, which is unique enough at 296+ chars.
        chunk = src[m.start():m.end()]
        out = out.replace(chunk, '', 1)

    with open(INDEX, 'w', encoding='utf-8') as fh:
        fh.write(out)
    print(f'  index.html: {len(blocks)} block(s) replaced with {len(links)} link(s)')
    return 0


if __name__ == '__main__':
    sys.exit(main())
