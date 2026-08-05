# Real-browser E2E

The blocker that stood through this entire review is gone. Chromium launches,
the browser suite runs, and it immediately found four bugs that neither jsdom
nor static analysis could see.

**53 browser tests passing** (was 31 skipped). **3947 unit tests passing.**

---

## Why it was blocked, and what changed

Chromium downloaded fine and then failed to start: the 120MB binary needs
`libnss3` and a dozen other shared libraries, and installing them needs root.
Every previous attempt recorded the same conclusion — *"Chromium CANNOT be
installed here"*.

Passwordless `sudo` turns out to be available in this sandbox. That was worth
re-testing rather than inheriting as fact.

`scripts/ensure_browser.py` now installs the libraries itself when it can:

- probes with `sudo -n`, so it can **never** block a desktop launch on a
  password prompt
- installs the core set directly rather than relying on
  `playwright install-deps`, which exits non-zero when **any** package is
  unavailable. Two font packages are unavailable on Debian 13, and treating
  that as fatal skipped the libraries that actually matter. Fonts affect glyph
  coverage; they do not affect whether the browser starts.

---

## Four bugs only a real browser could find

### 1. Contrast was still broken in the stylesheets that actually load

Commit `167df61` fixed 17 WCAG failures by correcting `THEME_VARS` and the
`:root` block in `index.html`. Both were real fixes. Neither is what the
browser uses.

`index.html` loads:

```html
<link rel="stylesheet" href="/static/styles-unified.css">
<link rel="stylesheet" href="/static/styles-redesign.css">
```

`styles-redesign.css` loads last and wins the cascade. And `styles.css` — 228KB,
also corrected in that commit — **is not linked at all.**

Measured in Chromium against the running app:

| | |
|---|---|
| token table promised | 4.73:1 |
| browser computed | **2.5:1** |

Sixteen pairs failed across the two loaded sheets, the worst at **2.05:1**.

This is the lesson of the whole exercise: every input to the original audit was
correct, and the conclusion was still wrong, because the cascade decides which
value applies.

### 2. A `ReferenceError` on every page load

```js
window.filterPlugins = filterPlugins;   // no such function, anywhere
```

`23-plugin-marketplace.js` threw on every single load and aborted the rest of
the module. Only function hoisting kept the exports below it working — any
`const` or `let` added after that line would have been silently missing.
Nothing calls it, so the dead export is removed rather than a stub invented.

### 3. A high-contrast mode with worse contrast than the default

`@media (prefers-contrast: high)` set `--text-3` to `#7080a0` = **3.61:1**,
below the 4.73:1 a user gets *without* asking for high contrast. A setting that
makes things worse for the people who need it most.

### 4. A stale expectation and its orphaned CSS

The suite asserted `#pane-builder`, retired in `6a8260e` when the Code Editor
was merged into Code Studio. Nothing caught it because these tests had never
run in a browser. A dead `#pane-builder` CSS rule went with it.

**Also:** the existing POST test predated CSRF enforcement and was POSTing
without a token — the 403 it started returning was the control working. It now
fetches a token, and a new test asserts a token-less POST is still refused.

---

## What the 21 new tests cover

Only things that need a real engine:

- **CSP actually enforced** — an injected `<script>` and an injected `on*=`
  handler are both refused, and the app trips no violations of its own policy.
  The entire phase-2 migration was previously verified by static analysis only.
- **Native keyboard semantics** — jsdom does not synthesise a click from Enter
  on a `<button>`, which is the exact behaviour behind the double-fire bug.
- **Real focus** — traversal, `:focus-visible`, and the dialog focus trap.
- **Computed contrast** — read after the cascade, not from the token table.
- **Layout** — horizontal overflow, and a clean console on boot.
- **Double-submit** — driven by real clicks at real speed.

---

## The harness fought back

Several "failures" were the test, not the app. Each took real work to tell
apart, and getting this wrong in either direction is expensive — a false
positive sends you fixing working code, a false negative hides a real bug.

**The first-run modal intercepts every click.** `#onboarding-overlay` is a
full-viewport `z-index:99999` layer, which is correct: a new user should be
greeted first. But Playwright's auto-retry turned it into a multi-minute hang
rather than a clean failure. The fixture now dismisses it, and a separate test
asserts it *is* dismissible — an unclosable welcome modal would lock a new user
out of the product entirely.

**`element.focus()` does not satisfy `:focus-visible`.** Chromium grants that
pseudo-class for keyboard interaction, not programmatic focus. A `.focus()`
based test reported a 0px outline against a working app.

**Playwright's `focus()` delivers a click to a `[role=button]`.** The counter
was already at 1 before the key press. Five attempts to narrow that window —
reset after focus, DOM-level focus, late listener binding, added settle time, a
sequence assertion — each moved the flake without removing it. That pattern was
the signal that the *measurement* was wrong, not the timing. The assertion is
now a delta that tolerates harness interference while still failing on a
genuine double-fire (verified by injecting one).

**20 browser contexts exhaust 1.9GB of RAM.** The run hung partway while every
test passed in isolation. A shared page with per-test `goto()` fits the
machine; the one test that *counts events* keeps its own context.

**A stdout substring check.** `test_e2e_collection_no_longer_errors` grepped
collection output for `"error"` — and a new test named
`test_a_server_error_produces_a_visible_toast` made it fail on a clean
collection. It checks the return code now.

---

## Verification

- browser suite: **53 passed**, five consecutive clean runs
- full suite: **3947 passed, 19 skipped, 0 failed**
- reverting `unsafe-inline` into `script-src` fails **3 of 4** CSP tests
- injecting a double-fire into the shim fails **both** keyboard tests
- contrast confirmed at 4.73:1 in the browser, up from 2.5:1

One earlier full-suite run failed with `CPU time limit exceeded` — sandbox
throttling from running Chromium repeatedly, not a code failure. Re-run clean
after a pause.
