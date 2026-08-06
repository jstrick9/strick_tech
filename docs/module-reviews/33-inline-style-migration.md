# 33 — Starting the inline-style migration

You asked to "start chipping away" at the inline styles blocking a strict
`style-src`. This is the first batch plus the tooling to keep going safely.

## Result

| | Before | After |
|---|---|---|
| Inline `style=` attributes | 4,783 | **4,410** |
| Migrated in this batch | — | **373** |
| Utility classes added | — | 21 |
| Rendered difference | — | **0 properties across 79,297 elements** |

## The tool

`scripts/migrate_inline_styles.py`. Content-addressed class names
(`u-<sha1[:8]>`) so re-running is idempotent and produces an empty diff when
nothing changed. `--check` reports without writing; `--limit N` does the N most
repeated values; `--min-uses` sets the threshold.

Declarations are lifted **verbatim, in order**, into flat `0-0-1-0` selectors,
so the cascade result is identical to the attribute they replace.

## The bug this tool had, and the guard that came out of it

The first run migrated `style="display:none"` — 67 occurrences, the single most
repeated value. That looks like styling. **It is state.**

```js
// 01-app-core.js, toggleSidebarGroup()
isOpen = content.style.display === 'none';    // READ
content.style.display = isOpen ? '' : 'none'; // write
```

`element.style` exposes only the inline attribute, never a class. Once the
value moved into a class the read always returned `''`, so the toggle concluded
the group was already open and **the collapsible sidebar groups stopped
expanding**.

Caught by the verification harness, not by review: **549 properties changed
across 160 elements**, including `display: block → none` on collapsed groups.
Reverted immediately.

### Only *reads* matter

The obvious fix — refuse any property JS touches — was measured and rejected:
it shrank the migratable set from **1,280 attributes to 39**, because it
excludes `color`, `background` and `width`, i.e. most of the corpus.

A property JS merely *writes* is safe: the write lands on the inline attribute,
which beats a class on specificity, so the runtime value still wins. Only a
**read-back** breaks, because a class is invisible to `element.style`.

`runtime_read_properties()` scans the source for `.style.X ===`, `.style.X)`,
`getPropertyValue('x')` and friends. It is derived from the code, not
hardcoded, so a newly added `if (el.style.foo === …)` protects `foo`
automatically. Currently excluded: `display`, `width`, `height`, `transform`,
`opacity`, `color`.

## How "no visual change" was actually proved

A computed-style snapshot of every element on every pane, before and after,
comparing 19 properties.

**The first harness was wrong and said so loudly.** It compared the two runs
**positionally**, by array index. The app renders live data (plugin lists, log
rows, agent counts), so element *count* differs between runs and everything
after the first insertion shifts by one. Two runs of the *identical* build
reported **212,794 differences**.

Rewritten to key each element on a structural path (`TAG:index/TAG:index/…`
plus `id` and `data-nav`) and compare only elements present in both runs:

| Comparison | Differing properties |
|---|---|
| Identical build vs itself (noise floor) | **0** |
| Pre-migration vs post-migration | **0** |

79,297 elements compared. Had I kept the positional harness, the real 549-property
regression would have been indistinguishable from its own noise.

## Tests

`tests/unit/test_106_inline_style_migration.py` — 4 tests:

- read-back properties are never migrated (and `display` specifically is in the
  excluded set)
- the property list is derived from source, not hardcoded — a stale hardcoded
  list fails silently months later as a broken toggle
- every generated class is used and every used class is defined
- the script is idempotent

**Proven to catch the bug:** breaking the source scan makes 2 of 4 fail.

## Remaining, and the honest limit of this approach

4,410 attributes remain. Of those, only ~1,199 are fully static *and* safe;
21 values met the ≥10 threshold. The rest are long tail — 474 distinct values,
most used once or twice — where a utility class per value trades one problem
for another.

Getting to an enforceable strict `style-src` needs a different move for the
tail: component-level classes written by hand as each pane is touched, or
nonce-based `style-src`. **This batch does not make strict `style-src`
enforceable**; it removes 373 attributes and, more usefully, leaves a safe
repeatable tool and a verification harness that can prove the next batch
changes nothing.

## Regression status

| Suite | Result |
|---|---|
| Full non-browser | **3963 passed, 19 skipped, 0 failed** (+4 new) |
| Browser E2E | **82 passed, 0 failed** |
| axe-core, 28 panes | 0 violations |
| ruff | pass |
