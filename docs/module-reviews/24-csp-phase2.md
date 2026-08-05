# Phase 2 — removing `script-src 'unsafe-inline'`

**Status: complete.** The enforcing Content-Security-Policy no longer permits
inline script.

```
script-src 'self' https://cdn.jsdelivr.net https://cdnjs.cloudflare.com
           https://cdn.tailwindcss.com https://unpkg.com
           https://cdn.monaco-editor.net
```

## Why it mattered

The platform makes ~714 `innerHTML` assignments. While `'unsafe-inline'` was
present, none of them were protected by CSP — XSS defence rested entirely on
`escHtml()` being called correctly at every single site. Modules 10 and 17 each
found a stored-XSS hole of exactly that shape, which is the evidence that
per-call-site escaping does not hold on its own.

With the directive removed, an injected `<script>` or `on*=` attribute is
refused by the browser even when a call site forgets to escape. The escaping
still matters; it is simply no longer the only thing standing between a
malicious agent name and code execution.

## What blocked it

| | Before | After |
|---|---|---|
| Inline `on*=` handlers | **1107** | **0** |
| Inline `<script>` blocks | **5** | **0** |

The previously-reported figure of 859 handlers was wrong. It counted only
`frontend/js/*.js`. `index.html` held another 248 — and `index.html` is the one
file that must be clean for the switch to work at all.

## The design

### `frontend/js/00-delegate.js` — the shim

Handlers moved from executable attributes to data attributes:

```html
<button onclick="doThing()">          →  <button data-act-click="doThing()">
<input  oninput="f(this.value)">      →  <input  data-act-input="f($value)">
```

One delegated listener per event type reads the matching attribute. Dispatch is
**not `eval`** — that would reintroduce the injection surface phase 1 closed and
would still require `'unsafe-eval'`. Instead the value is *parsed* as
`name(arg, …)` where every argument is a JSON literal or a fixed placeholder,
and the name is resolved by plain property lookup on `window`. Anything else is
refused and logged.

A `data-act-*` value can therefore never execute attacker-supplied code. It can
only *name* a function the application already exposes.

**Placeholders** cover the largest category of non-mechanical handlers — values
read off the element:

`$value` · `$nvalue` · `$checked` · `$this` · `$event` · `$text` · `$id` ·
`$data.key` · `$json.key`

**Declarative intents** cover the DOM-poking idioms without adding ~70 one-line
globals:

`data-close` · `data-hide` · `data-stop` · `data-prevent` · `data-keys` ·
`data-click-self` · `data-self-click` · `data-hover` / `data-hover-out` ·
`data-hide-on-error`

### `frontend/js/00-handlers.js` — the tail

78 handlers had bodies whose meaning could not be proven from their text —
variable declarations, chained promises, arbitrary expressions. The migration
tool deliberately refused to guess at those, because a wrong guess produces a
control that looks present and silently does nothing. Each got a real named
function instead.

### Extracted `<script>` blocks

| File | Loading |
|---|---|
| `00-theme-boot.js` | **render-blocking** — applies the saved theme before first paint |
| `90-sidebar-shortcut.js` | `defer` |
| `91-mode-switcher.js` | `defer` |
| `92-pane-error-boundary.js` | `defer` |
| `93-shortcuts-overlay.js` | `defer` |

Execution order is preserved exactly. The theme block must stay blocking or the
app flashes the wrong appearance on every load.

## Bugs found

Four real bugs surfaced during this work. Three were found *before* the bulk
migration ran, by probing the shim under jsdom rather than trusting it.

**1. Type-blind dispatch (would have hit all 1029 conversions).**
v1 used a single `data-act` attribute and registered all nine event types
against it. The listener could not tell which event the author had written, so
a handler converted from `oninput` also fired on `click` and `change`. Measured:
**3 invocations for 1 intended handler** — double saves, double POSTs,
duplicated navigation, all silent. Fixed by putting the event type in the
attribute name.

**2. Escaped quotes stalled the argument scanner (~25 handlers).**
Handlers emitted from inside a JS string literal arrive as `nav(\'chat\')`. Both
the Python and JS scanners treated the backslash-quote as an opening quote and
stayed "inside a string" forever, silently skipping the handler.

**3. A dotted DOM expression converted as a function name.**
`index.html`'s persona `<select>` carried
`this.parentElement.parentElement.removeAttribute('open')`. The migrator's
`PLAIN_CALL` matched it as a dotted *function name*. The shim resolves dotted
names by walking `window`, where that path does not exist — the dropdown would
have silently stopped closing. Found by resolving all 632 dispatched names
against every function defined anywhere in the frontend.

**4. A dead button that predates this work.**
`03-features-b.js`, the voice panel's *Clear History*:

```js
.then(().catch(()=>{})=>this.closest('[style*=fixed]').remove())
```

`().catch(()=>{})=>` is not valid JavaScript. Confirmed with `new Function()`:
`SyntaxError: Unexpected token )`. The handler threw the instant it was clicked,
so the button did nothing — no delete, no panel close, no toast. A botched edit
that shipped because a broken inline handler produces no build error and no
console output until someone clicks it.

That is precisely the class of bug inline handlers hide, and the clearest
argument for having done this migration.

## A bug this migration introduced

`92-pane-error-boundary.js` spells the space key as `\' '\'` because the handler
is built inside a JS string. The key-guard regex captured the backslash along
with the key name and emitted `data-keys="Enter\, \"`, which terminates the
attribute early and mangles the markup. One site affected; the other 47 are the
clean `data-keys="Enter,Space"`. Fixed at the site and in the regex.

## Deliberate exceptions

**`style-src` keeps `'unsafe-inline'`.** The codebase sets `element.style`
throughout and templates carry `style=""` attributes. Removing it is a much
larger piece of work with a far smaller payoff, since a style injection cannot
execute script under this policy. This is now asserted by a test so the
exception stays a decision rather than drifting into an accident.

**`/preview/` is excluded** from the app CSP and keeps its own sandbox policy.

## Guards

| Guard | What it holds |
|---|---|
| `scripts/lint_inline_handlers.py` | fails CI on any inline `on*=` (now a *dead control*), and on unsafe interpolation into any handler or `data-act-*` |
| `scripts/migrate_inline_handlers.py` | reports `total handlers : 0`; also asserted by a test |
| `tests/unit/test_91_csp_no_unsafe_inline.py` | 17 tests binding the header and the frontend into one invariant |
| `tests/unit/test_88_delegation_shim.py` | 36 tests on the shim, including both pre-migration regressions |

The header and the frontend are tested as **one invariant**, not two.
Re-introducing either half silently restores the weakness: an inline handler
added after the switch is a dead control, and `'unsafe-inline'` added back
re-opens the ~714 `innerHTML` sites.

## Tests inverted

Three existing tests asserted the *old* state as a contract and had to be
turned around. Recording them because a test that pins a known weakness in
place is a pattern this review has now hit seven times:

- `test_89::test_enforcing_policy_still_permits_inline_so_nothing_breaks`
- `test_86::test_unsafe_inline_is_documented_not_silently_shipped`
- `test_88` — several cases asserted the shim *refuses* idioms v2 supports

Two others (`test_87`, `test_51`) asserted the literal string `onclick="…"`.
Both protections still hold — `selectMention` still goes through `jsArg()`,
workspace actions still read arguments off the element — so both were changed
to assert the *property* and accept either syntax.

## Verification

- `node --check` on all 57 JS files
- both linters clean; `ruff` clean
- live server: `GET /` → 200, enforcing header confirmed by `curl -D-`
- all extracted scripts serve 200
- every `data-act-*` value re-parsed under jsdom: 0 unparseable
- 631 of 632 dispatched names resolve (the 1 is the shim's doc example)
- new handler behaviour exercised under jsdom, including an XSS-shaped agent
  name (`X'),alert(1),('`) arriving as an inert string
- **full suite: 3625 passed, 19 skipped, 0 failed**
- regressions proven: 3 of 17 fail when the CSP fix is reverted; 2 of 36 for
  type-blind dispatch; 1 of 36 for escaped quotes

### A verification mistake worth recording

The first escaped-quote test passed against both the fixed *and* the broken
shim — it proved nothing. Writing `doThing(\'chat\')` in the probe source
collapses to a plain quote before the attribute is ever created. It now builds
the value with `String.fromCharCode(92)` and asserts a literal backslash reached
the DOM before dispatching.

I also committed `e1f2bdd` while its test run was still in flight and reported
it as done; two tests were failing. Both turned out to be the extraction making
pre-existing conditions visible rather than behaviour changes — but the claim
was made before the evidence existed, which is the thing to avoid.

## Not done

- **`style-src 'unsafe-inline'`** — deliberate, documented above.
- **Real-browser E2E.** `tests/e2e_browser` skips cleanly here because Chromium
  cannot launch in this sandbox (needs `libnss3`, requires root). `baebaf2`
  makes desktop installs run `playwright install chromium` on first launch, so
  those 31 tests execute on a real install. Verification here was done under
  jsdom plus static resolution of all 632 dispatched names, which catches the
  dead-control failure mode but not visual or layout regressions.
