# Recommendations for the Deliberately-Unfixed Items

Three items were left open at the end of the cross-cutting work, each for a
stated reason. This document is my recommendation as to what to do about them,
in priority order, with the evidence behind each call.

**The headline: while analysing item 1, I found that the "wait for a refactor"
framing was wrong. There is a live, exploitable stored XSS in the current
codebase. That changes the recommendation from "plan a migration" to "ship a
targeted fix now, then migrate."**

---

## Item 1 — `script-src 'unsafe-inline'`

### What I originally said

> Cannot be removed: 772 inline `onclick` handlers break the moment it goes.
> Tracked as a refactor, not a security patch.

That remains true about the *CSP directive*. It was the wrong frame for the
*risk*, because it treated "we can't turn on the mitigation" as equivalent to
"there's nothing to do."

### What the evidence actually shows

Breaking the 772 handlers down by shape:

| Shape | Count | Migration difficulty |
|---|---|---|
| `foo()` — no arguments | 300 | Trivial (mechanical) |
| Already using `this.dataset.*` | 33 | Already done |
| Inline arguments | 429 | Varies |

Of the 429, **191 interpolate a template variable into executable JavaScript**.
133 of those wrap the value in `JSON.stringify()`, which is *mostly* safe.
**58 interpolate raw values directly.**

One of those 58 is exploitable today:

```js
// frontend/js/01-app-core.js:3783
`<div onclick="selectMention('@${a.name}')" ...>`
```

Agent names have **no character validation** server-side (`agents.py` applies
only `.strip()[:80]`). Verified against the running server:

```
POST /api/agents  {"name": "X'),alert(document.cookie),('"}
→ stored verbatim

renders as:
  onclick="selectMention('@X'),alert(document.cookie),('')"

new Function(body) → PARSES AS VALID JS → executes on click
```

This is **stored XSS**, persisted in the database, triggered whenever a user
opens the @-mention dropdown. `escHtml()` does not help — the payload contains
no HTML metacharacters, only a quote and parentheses, which are perfectly legal
inside an HTML attribute and become code when the browser parses the handler.

`unsafe-inline` is precisely what allows it to execute.

### Recommendation

**Three phases. Do phase 1 immediately; it is hours, not weeks.**

**Phase 1 — Close the live hole (do now).**
Fix the 58 raw-interpolation handlers. Two mechanical options, in preference
order:

1. Convert to the `data-*` + `dataset` pattern already used in 33 places and
   established during the Module 17 review. There is in-repo prior art in nine
   files, so this is a known-good shape for this codebase, not a novel one.
2. Where that is disproportionate, wrap the value in `JSON.stringify()` — the
   pattern the other 133 already use.

Add a lint rule (`scripts/lint_globals.py` is the natural home — it already
runs in CI) that **fails on any `on*="` attribute containing `${` without
`JSON.stringify` or `this.dataset`**. That converts a 58-instance cleanup into
a permanent invariant, which matters more than the cleanup itself.

Separately, **validate agent names server-side.** Defence in depth: the
frontend fix stops this instance, the server fix stops the whole class from
reaching any renderer. `[:80]` with no character policy is too permissive for a
value that reaches five different UI surfaces.

**Phase 2 — Migrate the remaining handlers (1–2 focused sessions).**
The 300 no-argument `foo()` handlers are a scripted find-and-replace to
delegated listeners. The remainder are per-file work. Do it file by file, with
the pane exercised after each — the review has shown repeatedly that
frontend regressions here are silent.

**Phase 3 — Drop `unsafe-inline`, in report-only first.**
Ship `Content-Security-Policy-Report-Only` with the strict policy alongside the
enforcing permissive one. Collect violations from real usage for a week. Only
then swap. This is the step that stops a strict CSP from being reverted within
a day, which is exactly what I predicted would happen if it were forced.

**What I would not do:** try to remove `unsafe-inline` before phase 1. It
would fail, get reverted, and leave the actual XSS unfixed while creating the
impression that CSP had been "tried and didn't work."

---

## Item 2 — Rate limiting is per-process

### What I said

> The bounded in-memory store is correct for a single-process deployment;
> multi-process needs Redis or equivalent.

### Assessment: this one is genuinely fine as-is, for now

I want to be careful not to manufacture work. The platform is explicitly
**local-first** (`run.py` starts a single uvicorn process; the README leads with
local usage). For that deployment the in-memory store with bounded eviction is
not a compromise — it is the correct design, with no operational dependency.

The failure mode only appears with multiple workers, and it is a *degradation*
rather than a breach: each worker enforces its own limit, so the effective
limit becomes `N × configured`. Nothing is bypassed; the ceiling is just higher
than the operator asked for.

### Recommendation

**Do not add Redis now.** Do three cheap things instead:

1. **Detect and warn.** If the process starts with more than one worker
   (`WEB_CONCURRENCY`, `--workers`, or a Gunicorn master), log a warning at
   startup naming the effective multiplier. An operator who scales out
   discovers the limitation at the moment it becomes true, not during an
   incident.
2. **Document the ceiling** in `config.yaml` next to the rate-limit settings —
   one line stating the limit is per-process.
3. **Define the trigger for revisiting**: the first deployment that runs more
   than one worker, or the first time rate limiting is relied on as a security
   control rather than an abuse backstop. Writing the trigger down is what
   stops this from being either forgotten or prematurely over-engineered.

The interface is already correct — `_sweep_rate_limit_store()` and the store
are isolated enough that swapping in a shared backend later is a contained
change, not a rewrite.

---

## Item 3 — `AGENTIC_CSRF_STRICT` defaults off

### What I said

> Deliberate for upgrade safety. New deployments should set it.

### Assessment: right call, wrong default trajectory

Defaulting off was correct **for the commit that introduced it** — flipping it
in the same change that added client-side token attachment would have risked
breaking scripted API clients with no warning, and the log line exists exactly
so operators can see the impact first.

But "off by default" is a migration state, not an end state. Left indefinitely,
it means the protection ships disabled and most deployments never turn it on.
The security property only exists for operators who read the release notes.

### Recommendation

**A dated flip, with the evidence to justify it.**

1. **Now:** leave off. Let the warning log accumulate. The line
   (`CSRF: POST /path accepted WITHOUT a token`) is the data.
2. **Next release:** review the logs. If the only unauthenticated mutations are
   the already-exempt webhook and bootstrap routes, that is the evidence the
   flip is safe.
3. **Then flip the default to on**, with `AGENTIC_CSRF_STRICT=0` as the
   documented escape hatch, and a `CHANGELOG` entry stating plainly that
   scripted clients must fetch a token from `/api/security/csrf-token`.

Additionally: **the exemption list deserves a test that it stays minimal.**
Right now it contains two entries plus the webhook prefix. Exemption lists grow
quietly under delivery pressure, and a CSRF exemption is exactly the kind of
thing added at 5pm to unblock something. A test asserting the list has not
grown without deliberate change makes each addition a decision rather than a
diff.

---

## Summary

| Item | Verdict | Urgency |
|---|---|---|
| `unsafe-inline` | **Wrong framing — live stored XSS found** | **Phase 1 now** |
| Per-process rate limiting | Correct as-is; add detection + a written trigger | Low |
| CSRF default off | Correct for now; needs a dated flip, not indefinite | Medium |

The pattern worth noting across all three: **each was described in terms of
what could not be done, and in two of the three cases that framing hid
something that could.** "We can't enable the mitigation" is not the same
statement as "the risk is accepted", and separating them is what turned item 1
from a backlog entry into a verified exploit.


---

# Phase 1 — Executed (`18f6364`)

Done. The live exploit is closed, and the invariant is in CI.

## What the analysis got wrong, corrected

Two things were worse than the recommendation above stated:

1. **64 handlers, not 58.** My original grep undercounted; a proper AST-shaped
   scan across all 28 files found 64.
2. **The `escHtml()` handlers were not "mostly safe" — they were vulnerable.**
   ~24 of the 64 wrapped values in `escHtml()`, which *reads* like protection
   and is not. The browser HTML-decodes an attribute before the JS parser runs,
   so `&#39;` becomes `'` again:

   ```
   escHtml("a'),alert(1),('")  ->  a&#39;),alert(1),(&#39;
   rendered : onclick="f('a&#39;),alert(1),(&#39;')"
   decoded  : f('a'),alert(1),('')      <- executes
   ```

   This is the more dangerous shape, because a reviewer skimming the code sees
   an escaper and moves on.

## What shipped

**`jsArg()`** — `JSON.stringify` for the JS context, then HTML-encoding for the
attribute context. Both halves are required: stringify alone leaves double
quotes that close the attribute; HTML-encoding alone is undone by the decode.
Applied to 58 sites.

**8 left deliberately**, each verified: `${v.id}`/`${f.id}` are INTEGER primary
keys (checked against the schema), and `${a.action}` is developer-authored JS
by design — its only dynamic call site interpolates an internal pane id.

**Server-side validation** on agent names, rejecting with 400 rather than
silently stripping. Non-ASCII names still work.

**`scripts/lint_inline_handlers.py` in CI.** It classifies by *shape* rather
than a name allowlist, which would go stale. It skips comment lines — several
files document a previously-fixed handler bug by quoting the old code, and
flagging that prose would push people to delete the explanation.

The lint earned itself immediately: **it found 7 sites my rewriter's regex had
missed**, one a genuine `escHtml()`-in-JS-context vulnerability in
`openCodeInStudio`.

## Verification

```
POST /api/agents {"name": "X'),alert(document.cookie),('"}
  -> 400 "Agent name cannot contain quotes, angle brackets, ..."

even if such a name existed, the handler now receives:
  "@X'),alert(document.cookie),('"    <- inert string, not code
```

Both layers were tested independently, so neither is load-bearing alone.

24 tests, **9 fail with the fix reverted**. One asserts the *lint itself* fails
on a bad handler and passes a good one — a guard nobody has seen fail is not
evidence of anything.

Full suite: **3536 passed / 19 skipped / 0 failed**.

## Still open

Phases 2 and 3 are unchanged and now genuinely are refactors rather than
security work, because the exploitable surface is closed and CI prevents its
return:

- **Phase 2:** migrate the 772 handlers to delegated listeners (300 are trivial
  no-argument calls).
- **Phase 3:** `Content-Security-Policy-Report-Only` with the strict policy for
  a week, then drop `unsafe-inline`.


---

# Phases 2 & 3 — partially executed, and why I stopped where I did

Committed: `a5d129e` (delegation shim + migration tooling), `0a20f20` (strict
CSP in Report-Only mode with violation collection).

**Not committed: the bulk migration of 859 handlers.** That was a judgement
call, and the reasoning matters more than the outcome.

## What measurement showed

The recommendation said "772 handlers, 300 trivial". Measured properly:

| | Count |
|---|---|
| Inline handlers total | **859** (the earlier grep undercounted) |
| Convertible automatically (proven plain calls) | **546** |
| Need hand-written listeners | **313** |
| Inline `<script>` blocks in `index.html` | **5** (~15KB) |

The 313 break down as: 146 use `this` (`this.parentElement.remove()`), 72 other
expressions, 37 use the `event` object, 26 complex interpolation, 20
multi-statement bodies, 12 non-delegated events.

## Why the migration did not ship

Three reasons, in order of weight:

**1. Partial migration buys nothing.** `unsafe-inline` is required if *one*
inline handler remains. Converting the easy 546 would touch **49 files** and
leave the CSP exactly as permissive as before — all of the regression risk,
none of the security benefit.

**2. I cannot verify it.** Chromium will not install here (no root for
libnss3), so all **31 tests in `tests/e2e_browser` error out**. The failure mode
of a bad conversion is *"button does nothing, no error anywhere"* — silent,
and precisely the shape of bug this review has spent 22 modules removing. A
546-site, 49-file UI refactor that I cannot click a single button of is not
something to push.

**3. The security value was already banked.** Phase 1 closed the actual
exploit. What remains is defence-in-depth, and defence-in-depth does not
justify shipping an unverifiable refactor.

## What shipped instead

**`frontend/js/00-delegate.js`** — the shim the handlers migrate *onto*, with
the design decision that matters: it **does not eval**. A `data-act` value is
parsed as `name(arg, ...)`, the name resolved by plain property lookup on
`window`, every argument required to be a JSON literal. Anything else is
refused and logged. Eval would have reintroduced phase 1's injection surface
*and* still required `'unsafe-eval'`, defeating the purpose.

Verified with **6 real DOM-event tests under jsdom** — including delegation
from a nested target, because clicks land on inner `<span>`s and without
`closest()` the migration would silently break every icon button.

**`scripts/migrate_inline_handlers.py`** — the classifier and rewriter, which
converts only what it can *prove* is a plain call and reports the rest. The
tool is the durable artefact: whoever does phase 2 with a browser available
runs it and reviews 313 cases, rather than starting from 859.

**`scripts/lint_inline_handlers.py` now covers `data-act`.** Without that, the
migration would move 546 handlers out from under the guard protecting them.

**Report-Only CSP + `/api/security/csp-report`.** This is phase 3's genuinely
useful half. Browsers enforce the permissive policy and only *report* on the
strict one, so nothing breaks while every would-be violation is collected and
aggregated. It turns *"we think 313 handlers need work"* into a measured list
from real usage — the evidence that was missing when I first wrote this
recommendation.

## What is left, and what unblocks it

1. **313 hand-written listeners + 5 inline `<script>` blocks extracted.**
   Needs a browser to verify. `tests/e2e_browser` already exists and is written;
   it needs Chromium, which needs root.
2. **Then flip enforcing.** By then `/api/security/csp-report` will say whether
   it is safe, rather than anyone guessing.

The honest summary: **phase 2 is blocked on verification capability, not on
effort or understanding.** I have removed every part of that blocker I can —
the shim is proven, the tooling exists, the remaining work is enumerated, and
the measurement infrastructure is live and collecting.
