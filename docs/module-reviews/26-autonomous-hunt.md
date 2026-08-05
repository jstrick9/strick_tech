# Autonomous hunt — findings and fixes

Fifteen batches, each verified against a live server, tested, and proven by
reverting the fix to confirm the test actually catches it.

**Full suite: 3891 passed, 19 skipped, 0 failed** (from 3845 at the start).

---

## What was found

### 1. The main navigation could not be used from a keyboard

The six ESSENTIALS items — Chat, Code Studio, Memory, Tasks, Templates,
Settings — carried `role="menuitem"` but no `tabindex`. Tab walked straight
past them, so a keyboard or screen-reader user could not navigate the product
at all. **86 clickable elements** were affected in total.

Also corrected: `role="menuitem"` is only valid inside a menu or menubar. The
sidebar is `role="navigation"`, so those six were an invalid pairing that
assistive tech may ignore. The markup was already inconsistent — 18 said
`button`, 6 said `menuitem` — which is the tell that they were copy-paste
rather than intent.

### 2. Failed requests told the user nothing

673 `fetch()` calls, and three mechanisms conspiring to hide every failure:
236 empty catch blocks, plus `window.onerror` and `window.onunhandledrejection`
both deliberately silent ("too noisy").

**50 of those empty catches wrap a POST/PUT/PATCH/DELETE.** A failed save and a
successful save looked identical, so a user could delete a goal, see no error,
and reasonably believe it worked.

`00-net-feedback.js` wraps fetch once and reports what a user can act on.
Because it reports *before* the caller's catch runs, all 50 silent-save paths
are fixed without editing any of them. The suppression rules are pinned as
hard as the reporting ones — the original authors were right that naive
reporting is unusable.

### 3. Double-clicking created duplicate records

Verified live: three rapid POSTs to `/api/goals` produced **three identical
goals**. 212 click-wired handlers perform a mutating request and disable
nothing; only ~26 of 570 async functions touch a disabled state and **none**
set `aria-busy`.

The two halves compound — with no pending state, double-clicking a slow button
is the natural response, not a mistake. Guarded at the delegation shim, so it
holds for every current and future control.

### 4. WCAG contrast failures in all six themes — 17 of them

`--text-3` failed in 5 of 6 themes; on `midnight` it measured **1.79:1**. White
on the accent fill failed in 5 of 6 — 2.14:1 on dark and obsidian — meaning
**primary buttons had the worst contrast in the product**.

The fill could not simply be brightened: 46 controls put a foreground on it,
and lightening makes that pairing worse. Two new tokens (`--accent-text`,
`--on-accent`) resolve the conflict. New values were computed by shifting
lightness in HLS with hue and saturation held, so each palette keeps its
character.

### 5. Dialogs were keyboard traps

Escape only worked on *prompts* — the handler was bound to the text input, so
confirm and delete dialogs could not be dismissed from the keyboard at all. No
focus trap, no focus restoration, no `role="dialog"`.

### 6. Unsent work was destroyed by a reload

49 textareas, **zero `beforeunload` handlers**. A long chat prompt was lost on
an accidental Cmd+R with no warning and no recovery.

### 7. Missing resources answered HTTP 200

29 GET/DELETE lookups returned `200 {"ok": false, "error": "... not found"}`.
This mattered more once the network reporter existed, because it keys off
status — a 200 produces silence and a blank screen.

Making the status honest immediately exposed **three tests that were green
against endpoints that do not exist** (`/api/marketplace/search`,
`/api/marketplace/installed`, `/api/integrations/list`), all passing only
because `/{param}` swallowed the literal segment.

### 8. Malformed JSON created junk records

179 handlers shared `except (...): body = {}`. The intent was sound — several
POSTs legitimately carry no body — but the same clause swallowed broken input:

```
POST /api/specs  body: not json  ->  200 {"title": "Untitled Feature"}
```

A client with a serialisation bug got a cheerful 200 and a junk row.

### 9. PATCH created phantom records

```
PATCH /api/agents/nope {"name": "x"}
-> 200 {"ok": true, "agent": {"id":"nope","role":"","model":"", ...}}
```

The half-built record persisted and appeared in the agent picker with no
model, where selecting it fails. Same shape found in `PUT /api/pluginsdk/packs`.
`PATCH /api/connectors/{id}/configure` was the worst variant: it silently
**discarded API credentials** while showing a success toast.

### 10. Database Studio discarded most of every row

`cols.slice(0, 5)` capped inserts at five columns. `goals_v2` has 23, `agents`
12, `tasks` 11 — so on most tables the majority of the record was dropped
silently. Rebuilt as a single form using the `notnull` and `type` metadata the
API already returned and the old flow ignored.

### 11. Lists hid records without saying so

`/api/goals` returned 100 items and `{"total": 724}`. The pane showed 100 and
said nothing, so **624 goals were unreachable**. A user who cannot find a goal
concludes it was deleted.

### 12. Smaller fixes

- the keyboard-shortcuts overlay could not be closed (dead ✕)
- a native `<button>` ran its action **twice** per Enter press
- 31 of 33 form controls had no accessible name
- 13 images had no `alt`
- no `prefers-reduced-motion` support across 90 animations/transitions
- a stray `>` rendered on every goal card
- `ragDeleteDoc` was the one destructive action with no confirmation

---

## Mistakes I made and corrected

Recording these because the verification discipline is the point.

**My own blanket a11y pass created a bug.** Treating every clickable div
identically gave modal *backdrops* `role="button"`, `tabindex="0"` and
Enter/Space bindings — a stray tab stop announcing a control that does nothing.
Five backdrops affected. My two tests then contradicted each other, and the
naive rule was the one that had to yield.

**A test that proved nothing.** The first escaped-quote probe passed against
both the fixed *and* the broken shim, because `\'` collapses to a plain quote
before reaching the attribute.

**A performance regression I introduced.** Fetching a CSRF token per internal
call took the suite from 165s to **437s** and broke two concurrency tests.

**A spot-check that felt thorough and was not.** My first contrast audit
checked text against `--bg-1` only and missed two failures. Writing the test
as a full theme × text × surface product surfaced both immediately.

**A static analysis that was simply wrong.** A route-shadowing scan flagged 21
literal routes as shadowed by `{param}` siblings. Probing all 21 against the
running server returned 200 for every one — FastAPI matches literals first.
Only the live check settled it.

---

## Deliberately not changed

- **`/api/tts/voices/{agent_id}` accepts any id** — it writes a preference
  keyed by arbitrary agent name, so any id is legitimate by design.
- **Idempotent DELETEs returning 200** — ~20 endpoints. Returning 200 for
  "already gone" is a defensible reading of DELETE semantics; only the ones
  claiming an *update* happened were changed.
- **236 empty catch blocks remain** — many are legitimate ("this optional
  thing may not exist"). They are simply no longer load-bearing for error
  visibility.
- **`style-src 'unsafe-inline'`** — unchanged from the earlier CSP work; a
  style injection cannot execute script under the current policy.

---

## Verification

Every batch: verified against a running server, covered by tests, and the
tests proven by reverting the fix.

| Batch | Tests | Fail on revert |
|---|---|---|
| Keyboard access | 8 | 5 of 8 |
| Network feedback | 20 | 8 of 20 |
| Double-submit | 5 | reproduces `assert 3 == 1` |
| Contrast | 77 | 4 of 77 |
| Dialog focus | 8 | 2 of 8 |
| Drafts | 11 | 1 of 11 |
| 404 status | 42 | 2 of 42 |
| Malformed bodies | 16 | 5 of 16 |
| DB insert form | 8 | — |
| List truncation | 7 | — |
| Write paths | 15 | 3 of 15 |

A final sweep across every category checked in this session returns **zero**
for all of them.
