#!/usr/bin/env python3
"""Fail on duplicate `window.X = ...` assignments across frontend modules.

WHY THIS EXISTS
---------------
`frontend/js/` has no module system. All 63 scripts are plain <script> tags
sharing one global namespace, and they communicate by assigning to `window`.
Nothing prevents two files from claiming the same name: the last one loaded
silently wins, with no error, no warning, and no indication at the call site
that a different implementation is now in effect.

This has already caused real, shipped bugs — two were found in the Chat module
review alone, where one file's `window.X` quietly replaced another's. The
failure mode is nasty because it is *load-order dependent*: reorder the tags in
index.html, or add a `defer`, and behaviour changes with no code change.

WHAT COUNTS AS A PROBLEM
------------------------
Only CROSS-FILE collisions. Reassigning your own global inside one file is
ordinary mutable state (`window._chatCurrentPage = 3`) and is not flagged.

INTENTIONAL OVERRIDES
---------------------
Decorating an existing global is a legitimate pattern here — accessibility and
ergonomics layers wrap `nav` and `toast` to add behaviour, capturing the
original first:

    const origNav = window.nav;
    window.nav = function (...) { origNav.apply(this, arguments); ... };

Mark those with a comment on, or directly above, the assignment:

    // intentional-override: adds focus management on top of core nav
    window.nav = function (pane) { ... };

The marker is deliberately explicit. The point is not to ban overrides but to
make the difference between "I meant this" and "I did not know that name was
taken" visible in review.

USAGE
    python scripts/lint_globals.py            # check, exit 1 on failure
    python scripts/lint_globals.py --list     # show every global and its owner
"""

from __future__ import annotations

import argparse
import re
import sys
from collections import defaultdict
from pathlib import Path

REPO = Path(__file__).resolve().parents[1]
JS_DIR = REPO / 'frontend' / 'js'

ASSIGN_RE = re.compile(r'^\s*window\.([A-Za-z_$][\w$]*)\s*=(?!=)')
MARKER = 'intentional-override'

# Names that are expected to appear in several files because they are not
# ownership claims: UMD/AMD shims and the like.
IGNORED = {'define', 'require', 'module', 'exports'}


class Assignment:
    __slots__ = ('name', 'file', 'line', 'intentional')

    def __init__(self, name: str, file: str, line: int, intentional: bool):
        self.name = name
        self.file = file
        self.line = line
        self.intentional = intentional

    def __repr__(self) -> str:
        return f'{self.file}:{self.line}'


def scan() -> dict[str, list[Assignment]]:
    """Collect every top-level `window.X =` assignment, keyed by global name."""
    found: dict[str, list[Assignment]] = defaultdict(list)
    for path in sorted(JS_DIR.glob('*.js')):
        lines = path.read_text(encoding='utf-8', errors='ignore').splitlines()
        for idx, line in enumerate(lines):
            match = ASSIGN_RE.match(line)
            if not match:
                continue
            name = match.group(1)
            if name in IGNORED:
                continue
            # The marker may sit on the assignment itself or on any of the
            # three lines above it (room for a short explanation).
            context = '\n'.join(lines[max(0, idx - 3): idx + 1])
            found[name].append(
                Assignment(name, path.name, idx + 1, MARKER in context)
            )
    return found


def cross_file_collisions(found: dict[str, list[Assignment]]) -> dict[str, list[Assignment]]:
    """Globals claimed by more than one file, excluding marked overrides.

    Same-file reassignment is just mutable state and is never reported.
    """
    collisions = {}
    for name, assignments in found.items():
        by_file: dict[str, list[Assignment]] = defaultdict(list)
        for a in assignments:
            by_file[a.file].append(a)
        if len(by_file) < 2:
            continue
        # A file is "unmarked" if none of its assignments carry the marker.
        unmarked = [
            first
            for first, *_ in (sorted(v, key=lambda a: a.line) for v in by_file.values())
            if not any(a.intentional for a in by_file[first.file])
        ]
        # One unmarked definition is the owner; anything beyond that is a clobber.
        if len(unmarked) > 1:
            collisions[name] = sorted(unmarked, key=lambda a: (a.file, a.line))
    return collisions


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--list', action='store_true', help='list every global and its owner')
    args = parser.parse_args()

    if not JS_DIR.is_dir():
        print(f'error: {JS_DIR} not found', file=sys.stderr)
        return 2

    found = scan()
    total = sum(len(v) for v in found.values())

    if args.list:
        for name in sorted(found):
            owners = sorted({a.file for a in found[name]})
            print(f'{name:40} {", ".join(owners)}')
        print(f'\n{len(found)} distinct globals, {total} assignments')
        return 0

    collisions = cross_file_collisions(found)
    if not collisions:
        print(f'✓ no duplicate globals ({len(found)} distinct names, {total} assignments)')
        return 0

    print('✗ duplicate window.* globals across files\n')
    print('  The last file loaded silently wins. If the override is deliberate,')
    print(f'  add a "// {MARKER}: <why>" comment on or above the assignment.\n')
    for name in sorted(collisions):
        print(f'  window.{name}')
        for a in collisions[name]:
            print(f'      {a.file}:{a.line}')
        print()
    print(f'{len(collisions)} duplicated global(s)')
    return 1


if __name__ == '__main__':
    sys.exit(main())
