#!/usr/bin/env python3
"""Migrate repeated static inline `style="..."` attributes to utility classes.

WHY
───
The CSP phase 3 measurement found 4,783 inline style attributes across 118
distinct violation sites. Enforcing a strict `style-src` (no 'unsafe-inline')
is blocked on that number coming down. This is the incremental path: every
attribute converted to a class is one fewer thing standing between the app and
an enforced style-src, and the work is safe to do in small batches.

HOW IT IS KEPT SAFE
───────────────────
1. Only EXACT, byte-identical, fully static values are migrated. Anything
   containing `${` (a template interpolation) is skipped entirely — those are
   computed per render and cannot become a static class.
2. Only values seen at least MIN_USES times, so each class earns its place.
3. The generated CSS declares exactly the same declarations in the same order,
   so the cascade result is identical. Utility classes are emitted in one
   block appended to styles-redesign.css (the sheet that wins the cascade)
   with no selector nesting, so specificity is a flat 0-0-1-0.
4. An element that already has a `class` gets the utility appended, never
   replaced.
5. `--check` reports what would change without writing anything.

WHAT IT DELIBERATELY DOES NOT DO
────────────────────────────────
It does not touch `element.style` assignments in JS (measured NOT blocked by
CSP — verified in Chromium), `.cssText`, `<style>` blocks, or dynamic styles.
Those are separate problems with different tradeoffs.

VERIFICATION
────────────
tests/e2e_browser/test_e2e_browser_08_style_migration.py compares the COMPUTED
style of every element on every pane against the pre-migration baseline. A
migration that changes any rendered pixel fails there.
"""
from __future__ import annotations

import argparse
import collections
import glob
import hashlib
import os
import re
import sys

REPO = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
TARGETS = [os.path.join(REPO, 'frontend', 'index.html')] + sorted(
    glob.glob(os.path.join(REPO, 'frontend', 'js', '*.js')))
SHEET = os.path.join(REPO, 'frontend', 'styles-redesign.css')

MIN_USES = 10
BEGIN = '/* ==== BEGIN generated utility classes (scripts/migrate_inline_styles.py) ==== */'
END = '/* ==== END generated utility classes ==== */'

# `style="..."` with no template interpolation and no nested quote of the same
# kind. Single-quoted variants are matched separately.
_DQ = re.compile(r'style="([^"]*)"')
_SQ = re.compile(r"style='([^']*)'")


def existing_utilities() -> dict[str, str]:
    """Classes emitted by a PREVIOUS run, read back out of the sheet.

    WHY THIS IS NECESSARY. The generated block is rebuilt from the style
    attributes that are inline right now. On a second run the attributes the
    first run already converted no longer exist in the source, so their classes
    are not regenerated -- and rewriting the block drops them.

    Measured by running the tool twice: 21 classes were referenced in the JS
    and defined nowhere, including `.u-4ff818ff { font-size:18px }`, which
    showed up in the computed-style harness as `18px -> 14px` on the agent
    panes.

    Carrying the old definitions forward makes the tool idempotent, which is
    the property it silently lacked.
    """
    if not os.path.exists(SHEET):
        return {}
    with open(SHEET, encoding='utf-8') as fh:
        text = fh.read()
    if BEGIN not in text or END not in text:
        return {}
    block = text.split(BEGIN, 1)[1].split(END, 1)[0]
    out: dict[str, str] = {}
    for match in re.finditer(
            r'\.(u-[0-9a-f]{8})(?:\.u-[0-9a-f]{8})?\s*\{([^}]*)\}', block):
        out[match.group(1)] = match.group(2).strip()
    return out


def referenced_classes() -> set[str]:
    """Utility classes still mentioned anywhere in the source."""
    seen: set[str] = set()
    for path in TARGETS:
        with open(path, encoding='utf-8') as fh:
            seen |= set(re.findall(r'u-[0-9a-f]{8}', fh.read()))
    return seen


def runtime_read_properties() -> set[str]:
    """CSS properties that JavaScript READS BACK off `element.style`.

    THIS GUARD EXISTS BECAUSE THE FIRST VERSION OF THIS SCRIPT BROKE THE APP.

    It migrated `style="display:none"` (67 occurrences) to a utility class.
    That looks like styling; it is STATE. `toggleSidebarGroup()` does:

        isOpen = content.style.display === 'none';    // READ
        content.style.display = isOpen ? '' : 'none'; // write

    `element.style` exposes only the inline attribute, never a class. Moving
    the value into a class made the read always return '' -- so the toggle
    concluded the group was already open and the collapsed sidebar groups
    stopped expanding. Caught by a computed-style baseline of 79,297 elements
    across 24 panes: 549 properties changed on 160 elements.

    ONLY READS MATTER. A property JS merely *writes* is safe to migrate: the
    write lands on the inline attribute, which beats a class on specificity,
    so the runtime value still wins. Blocking on writes too was measured to
    shrink the migratable set from 1,280 attributes to 39 -- it would have
    excluded `color`, `background` and `width`, which is most of the corpus,
    for no safety benefit.

    Derived from source, so a newly added `if (el.style.foo === ...)`
    protects `foo` automatically.
    """
    props: set[str] = set()
    sources = [os.path.join(REPO, 'frontend', 'index.html')] + sorted(
        glob.glob(os.path.join(REPO, 'frontend', 'js', '*.js')))
    read_pat = re.compile(r'\.style\.([A-Za-z][A-Za-z0-9]*)\s*(?:===|==|!==|!=|\?|\)|\.)')
    for path in sources:
        with open(path, encoding='utf-8') as fh:
            src = fh.read()
        for m in read_pat.finditer(src):
            props.add(_kebab(m.group(1)))
        for m in re.finditer(r"getPropertyValue\(\s*['\"]([-a-zA-Z]+)", src):
            props.add(m.group(1).lower())
    return props


def _kebab(js_name: str) -> str:
    return re.sub(r'([A-Z])', lambda m: '-' + m.group(1).lower(), js_name)


def _properties_of(value: str) -> set[str]:
    out = set()
    for decl in value.split(';'):
        if ':' in decl:
            out.add(decl.split(':', 1)[0].strip().lower())
    return out


def _is_static(value: str) -> bool:
    if '${' in value or '`' in value:
        return False
    # A bare `{` or `}` almost always means an unterminated template fragment.
    return '{' not in value and '}' not in value and value.strip() != ''


def _normalise(value: str) -> str:
    """Collapse insignificant whitespace so `a: 1;b:2` and `a:1; b:2` unify.

    Declaration ORDER is preserved — reordering could change the result for
    duplicated properties, so it is never done.
    """
    decls = [d.strip() for d in value.split(';')]
    decls = [re.sub(r'\s*:\s*', ':', d) for d in decls if d]
    return ';'.join(decls)


def _class_name(value: str) -> str:
    """Stable, collision-resistant name derived from the value itself.

    Content-addressed so re-running produces identical names and the diff is
    empty when nothing changed.
    """
    return 'u-' + hashlib.sha1(value.encode()).hexdigest()[:8]


def collect() -> collections.Counter:
    counts: collections.Counter = collections.Counter()
    unsafe = runtime_read_properties()
    for path in TARGETS:
        with open(path, encoding='utf-8') as fh:
            src = fh.read()
        for pattern in (_DQ, _SQ):
            for m in pattern.finditer(src):
                v = m.group(1)
                if not _is_static(v):
                    continue
                # Skip anything JS reads back off element.style -- see the
                # docstring on runtime_read_properties().
                if _properties_of(v) & unsafe:
                    continue
                counts[_normalise(v)] += 1
    return counts


def build_css(chosen: dict[str, str]) -> str:
    lines = [
        BEGIN,
        '/* Generated. Do not edit by hand -- run scripts/migrate_inline_styles.py.',
        ' *',
        ' * Each class is one repeated inline style attribute, lifted verbatim:',
        ' * same declarations, in the same order.',
        ' *',
        ' * SPECIFICITY. The selector is doubled (`.u-x.u-x`, 0-0-2-0) rather',
        ' * than flat 0-0-1-0. An inline `style` attribute beats every selector',
        ' * in the cascade; a plain class does not, so a lifted declaration can',
        ' * simply lose to a rule that never used to compete with it.',
        ' *',
        ' * That is not hypothetical -- it shipped. `<h2 style="font-size:20px">`',
        ' * inside `.section-head` became `.u-89c33dcc`, and',
        ' * `.section-head h2 { font-size:17px }` (0-0-1-1) beat it. The heading',
        ' * silently shrank. Caught by scripts/audit/computed_style_diff.py.',
        ' *',
        ' * Doubling restores the "wins against ordinary component CSS" property',
        ' * the attribute had, without resorting to !important, which would also',
        ' * beat legitimate state rules like `.is-hidden` or `:hover`.',
        ' *',
        ' * This exists to bring the inline-style count down far enough to enforce',
        ' * a strict style-src. See docs/module-reviews/28-csp-phase3.md.',
        ' */',
    ]
    for value, name in sorted(chosen.items(), key=lambda kv: kv[1]):
        body = '; '.join(d for d in value.split(';') if d)
        lines.append(f'.{name}.{name} {{ {body}; }}')
    lines.append(END)
    return '\n'.join(lines) + '\n'


def apply_to_file(path: str, chosen: dict[str, str]) -> int:
    with open(path, encoding='utf-8') as fh:
        src = fh.read()
    original = src
    changed = 0

    def repl(m: re.Match, quote: str) -> str:
        nonlocal changed
        raw = m.group(1)
        if not _is_static(raw):
            return m.group(0)
        name = chosen.get(_normalise(raw))
        if not name:
            return m.group(0)
        changed += 1
        # Signal to the caller that this attribute is gone and a class is owed.
        return f'\x00{name}\x00'

    src = _DQ.sub(lambda m: repl(m, '"'), src)
    src = _SQ.sub(lambda m: repl(m, "'"), src)

    # Fold each marker into the element's class attribute.
    def fold(match: re.Match) -> str:
        name = match.group(1)
        return f'\x01{name}\x01'

    src = re.sub(r'\x00([\w-]+)\x00', fold, src)

    out = []
    i = 0
    marker = re.compile(r'\x01([\w-]+)\x01')
    for m in marker.finditer(src):
        name = m.group(1)
        # Find the enclosing tag so the class can be merged into an existing
        # class attribute rather than producing a duplicate one.
        start = src.rfind('<', 0, m.start())
        head = src[start:m.start()]
        existing = re.search(r'class="([^"]*)"', head)
        out.append(src[i:m.start()])
        if existing:
            # Remove the marker; the class is appended below by patching the
            # already-emitted text.
            emitted = ''.join(out)
            at = emitted.rfind('class="', len(''.join(out)) - len(head) - 1)
            if at != -1:
                close = emitted.index('"', at + 7)
                emitted = emitted[:close] + ' ' + name + emitted[close:]
                out = [emitted]
            else:
                out.append(f'class="{name}"')
        else:
            out.append(f'class="{name}"')
        i = m.end()
    out.append(src[i:])
    src = ''.join(out)

    if src != original:
        with open(path, 'w', encoding='utf-8') as fh:
            fh.write(src)
    return changed


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument('--check', action='store_true', help='report only, write nothing')
    ap.add_argument('--min-uses', type=int, default=MIN_USES)
    ap.add_argument('--limit', type=int, default=0,
                    help='migrate only the N most repeated values (0 = all qualifying)')
    args = ap.parse_args()

    counts = collect()
    qualifying = [(v, n) for v, n in counts.most_common() if n >= args.min_uses]
    if args.limit:
        qualifying = qualifying[:args.limit]

    chosen = {v: _class_name(v) for v, _ in qualifying}
    covered = sum(n for _, n in qualifying)
    total = sum(counts.values())

    print(f'static inline style attributes : {total}')
    print(f'distinct values                : {len(counts)}')
    print(f'values used >= {args.min_uses:<3}             : {len(qualifying)}')
    print(f'attributes they cover          : {covered} '
          f'({covered * 100 // max(total, 1)}% of static)')

    if args.check:
        print('\n--check: nothing written')
        return 0

    changed_total = 0
    for path in TARGETS:
        changed_total += apply_to_file(path, chosen)
    print(f'\nrewrote {changed_total} attributes across {len(TARGETS)} files')

    # Carry forward classes emitted by a PREVIOUS run. build_css() only knows
    # about values that are still inline, and after a run they are not -- so
    # rewriting the block from `chosen` alone silently deletes every class the
    # last run created. Measured by running the tool twice: 21 classes were
    # referenced in the JS and defined nowhere, which the computed-style
    # harness reported as `font-size: 18px -> 14px` on the agent panes.
    #
    # A class is dropped only when nothing references it any more.
    with open(SHEET, encoding='utf-8') as fh:
        sheet = fh.read()

    still_used = referenced_classes()
    inherited = {name: decls for name, decls in existing_utilities().items()
                 if name in still_used and name not in set(chosen.values())}

    block = build_css(chosen)
    if inherited:
        carried = '\n'.join(f'.{name}.{name} {{ {decls} }}'
                             for name, decls in sorted(inherited.items()))
        # INSIDE the END marker, not after it. Appending past END put these
        # classes outside the block that the next run replaces -- so they
        # would be duplicated on one run and orphaned on the next, and
        # test_106's "every reference is defined" check could not see them
        # at all because it reads only between BEGIN and END.
        insert = (
            '\n/* carried forward from earlier runs (still referenced) */\n'
            + carried + '\n')
        block = block.replace(END, insert + END, 1)
        print(f'carried forward {len(inherited)} class(es) from a previous run')
    if BEGIN in sheet:
        pre, rest = sheet.split(BEGIN, 1)
        _, post = rest.split(END, 1)
        sheet = pre + block.rstrip('\n') + post
    else:
        sheet = sheet.rstrip('\n') + '\n\n' + block
    with open(SHEET, 'w', encoding='utf-8') as fh:
        fh.write(sheet)
    print(f'wrote {len(chosen)} utility classes to {os.path.relpath(SHEET, REPO)}')
    return 0


if __name__ == '__main__':
    sys.exit(main())
