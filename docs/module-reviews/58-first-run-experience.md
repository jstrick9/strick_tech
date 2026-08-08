# 58 — The first-run experience

**New dimension.** Not in the original register — added because the register
was empty and continuing required a genuinely different way of looking.

**Audit:** `scripts/audit/first_run.py` · **key:** `first-run-experience` ·
**baseline:** 4 → **0** (31 raw, 4 after triage)
**Tests:** `tests/unit/test_130_first_run_experience.py` (17) — 10 fail on
revert.

---

## Why nothing had ever measured this

All eighteen existing audits run against a database holding 250 goals, 200
tasks, agents and specs. That was the right choice for volume, truncation and
layout.

It also means **every audit in this repo had only ever seen the application in
a state no new user is ever in.**

An empty account is the first thing every single user experiences, and it is
the state most likely to have been eyeballed once during development and never
revisited. It fails differently from everything else measured so far: nothing
throws, nothing 500s, and the screen is simply blank.

Running against a truly empty `AGENTIC_OS_DATA_DIR` was the whole trick.

---

## The crash: a guard that caused the bug it was guarding against

`renderImageGen()` died on **every** empty account:

> Couldn't open the image generator. The response from the server was not what
> the app expected. (Cannot read properties of undefined (reading 'length'))

An earlier defensive fix had normalised the gallery response to a bare
**array**, to stop `gallery.map is not a function`. But four call sites below
it read the **object** shape:

```js
const gallery = Array.isArray(galleryRaw) ? galleryRaw : (galleryRaw?.images || []);
…
${gallery.count} images          // undefined
${gallery.images.length === 0    // TypeError — pane dead
```

So the guard converted a hypothetical crash into a real one. Invisible against
seeded data; fired for **every new user on their first visit to that pane**.

**A guard that converts a shape the callers do not accept is not a guard.** It
now normalises to `{images, count}` — the shape actually consumed — with the
inner value forced to an array and `count` falling back to its length.

This is a new variant of recurring pattern #11 (*unguarded array access on a
parsed response*): here the guard itself was the defect.

---

## The UX defect: four panes that never say what they are for

`kanban`, `codesearch`, `websearch`, `multitab` each offered a working control
and no explanation. A search box with no context is a prompt to guess.

Each now carries a short empty state — what the feature does, and what to try
first:

| Pane | Now says |
|---|---|
| Kanban | "Track work across the board" + drag explanation + **Add your first task** |
| Code search | "Search every file in your project" + what to try |
| Web search | Why it differs from chat: it searches first, **then cites every source** |
| Multi-preview | What the Grid button is for |

Kanban is deliberately **asymmetric** — only the first column carries the
pitch. Four columns each repeating it is noise, not help.

---

## The probe over-reported 23 findings, and most were wrong

The first run produced **31 findings**. Triage before fixing cut that to **4**.

**`BROKEN` matched any `/error|failed/` anywhere in the pane.** Five of six
`BROKEN-EMPTY` findings were false:

| Pane | Matched | Actually |
|---|---|---|
| control | `ERRORS 0` | a dashboard metric tile |
| leaderboard | `Error Rate 0%` | ditto |
| audit-log | `Failed Actions 0` | ditto |
| hooks | `🚨 Error` | the *name* of a trigger type users pick |
| testgen | "…mocks, and error handling" | feature copy |

A product reporting "Errors: 0" is working correctly and saying so. The pattern
now requires a failure *clause*, and exonerates a line whose match sits beside
a count.

**`ACTION` matched only creation verbs in a button label**, so panes whose
entry point is a *text box* were declared dead ends: websearch (an Ask field),
codesearch (a search input), swarm (a prompt textarea), multitab (a URL bar),
replay ("Run a workflow"). **For a search or prompt pane the input IS the entry
point.** Read-only dashboards were also exempted — an empty system monitor is
honest, not a dead end.

Had I trusted the first run, I would have rewritten a dozen working screens.

---

## The probe refuses to measure the wrong state

Against a seeded server it reports an informational note instead of a result:

```
-- the server has seeded data; this audit measures an EMPTY account and
   refuses to report a result against the wrong state.
```

And it is **ratcheted separately**, not as a row in the shared parametrize
list, because in that list it would pass on every seeded CI run without ever
measuring anything — a test that cannot fail, the pattern this review has now
hit nine times. It **skips loudly** instead. Verified both ways: skips on a
seeded server, passes for real on an empty one.

One more deliberate difference: unlike every other audit here, it does **not**
strip the onboarding modal. That is part of the first-run experience;
it is dismissed the way a user dismisses it, via its own close control.

---

## Verification

| Check | Result |
|---|---|
| `scripts/audit/first_run.py` | 4 → **0** |
| Remove one empty state | audit correctly reports `NO-EXPLAIN websearch` |
| Run against seeded data | refuses, with the reason |
| Ratchet on seeded server | **skips** (visible), does not pass vacuously |
| Ratchet on empty server | passes for real |
| Revert all fixes | **10 of 17** tests fail |
| Full suite | 3,353 unit (2 skipped) + 655 (10 skipped), 0 failures |

---

# 58b — Can a user actually finish a job?

**Audit:** `scripts/audit/task_completion.py` · **key:** `task-completion` ·
**baseline: 0**
**Tests:** `tests/unit/test_131_task_completion.py` (8)

## Why this is different from the other nineteen

Every other probe inspects a **rendered state** — control size, announcements,
timezone formatting. **None of them ever uses the product.** A screen can pass
all nineteen and still be impossible to get a job done in.

This one drives complete journeys through the real DOM and asserts the outcome
the user expects: create → appears → survives a reload → delete → stays
deleted.

## Result: no defects — and that is a measured claim

Verified independently at the data layer while developing the probe: **0 rows
→ 1 → 0**, every step driven by clicking the UI.

## Why the result is trustworthy: it was proven able to fail

`POST /api/tasks` was stubbed to answer `200 {ok: true}` **without writing a
row** — an optimistic-UI lie, and exactly what an API-level test cannot see,
because the API said yes. The probe reported:

```
PERSIST-FAIL  kanban: the task appeared, then was gone after a reload --
              the user was told it saved and it did not
-- delete: nothing to delete; journey skipped
```

Both halves matter: it caught the lie, **and** declared the dependent journey
skipped rather than counting it as a pass.

## Design decisions that make it mean something

- **Everything goes through the DOM.** A probe that POSTs to the API and then
  checks the API has verified the server and learned nothing about the
  product — the failure this whole review keeps finding is a working backend
  behind a broken screen.
- **Persistence uses a full page reload**, not a re-render: an in-memory list
  will happily show a record the server never stored.
- **Every journey verifies its precondition** and emits a `--` note if the
  entry control is missing — the trap that let the concurrency audit report
  `0 records created` as a PASS.
- **A unique marker per run**, so leftovers cannot make a broken create look
  successful.
