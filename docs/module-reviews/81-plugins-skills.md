# 81 — Plugin Hub workstation: `plugins` host and the `skills` tab

**Destination:** `plugins`
**Tabs:** `plugins` (host), `skills` (this doc) · `pluginsdk` (doc 68) — 3/3 covered
**Frontend:** `frontend/js/34-plugin-hub.js`, `frontend/js/25-skills.js`
**Backend:** `backend/routers/plugins.py`, `backend/routers/plugin_hub.py`, `backend/services/plugin_safety.py`
**Tests:** `tests/unit/test_156_module20_plugins_skills.py` (28)
**Status:** reviewed, fixed, verified live

Destination 9 of 20.

---

## Why this destination

This is where **content written by somebody else** enters the platform and is
later fed to an agent. `backend/services/plugin_safety.py` exists because
`skills.run_skill()` renders templates with `template.format(**inputs)`, and
Python's format mini-language evaluates attribute access — so a plugin-supplied
template is executable to a degree:

```python
"Value: {topic.__class__.__mro__}".format(topic="hello")
# -> "Value: (<class 'str'>, <class 'object'>)"
```

**The scanner itself is good.** Its author drew the right distinction: *refuse*
format-string traversal (no legitimate use), *warn* about prompt injection (a
prompt-engineering pack that teaches about injection contains those very
strings, and a skill run has no tool access, so injected text can distort output
but cannot execute anything).

The problem was not the scanner. It was that **not every door used it.**

Five defects, all reproduced against a live server before any code changed.

---

## Findings

### 1. The safety scanner had a bypass: `/api/plugins/import`

Four of five entry points ran the review. `/import` appended `data['skills']`
straight to `skills.json` with no review at all. Verified live — the **same
payload**, both doors:

```
POST /api/plugins/install/json
  -> 400 {"error": "Plugin rejected by the safety check.",
          "problems": ["Bad: Template references a Python dunder attribute…",
                       "Bad: Template field \"{topic.__class__.__mro__}\" uses attribute access…"]}

POST /api/plugins/import      (identical skill object)
  -> 200 {"ok": true, "imported": {"skills": 1}}
```

The smuggled skill landed in the live Skills Hub, and its template rendered the
traversal exactly as the scanner's own docstring warns:

```
template : Value: {topic.__class__.__mro__}
rendered : Value: (<class 'str'>, <class 'object'>)
```

`format()` runs **before** any LLM call, so the no-provider gate in this sandbox
does not protect it.

What makes this the worst possible door to leave open is *social*: an export
file is the artefact a user is most likely to accept from someone else — *"here
is my workspace, import it"*. The least-reviewed entry point was also the most
trusted one. **Second door #18.**

**Fix:** `/import` now runs `review_skill()` per skill, refuses on the same
grounds as the front door, and reports what it refused.

### 2. `/import` returned HTTP 500 on malformed input

`{"skills": "not-a-list"}` and `{"skills": [null, "a string"]}` both produced
`Internal Server Error` — `skill.get(...)` on a non-dict. A bare JSON array or
string body did the same via `body.get(...)`.

**Fix:** type guards at both levels. Notably, the bare-array/string case was
found by **this module's own parametrised test after the first fix** — the
`isinstance(data, dict)` check I added came *after* the `body.get` that was
raising. That is what a table of malformed payloads is for.

### 3. The registry installer reviewed *after* writing

`/api/plugins/install/{plugin_id}` called `review_pack()` at the **bottom** of
the function, after `save_skills()` had already committed the pack to disk. It
was a report, not a gate. The built-in registry is curated today, which is why
nothing had escaped through it — but *"the input happens to be trustworthy"* is
not a safety property, and it is the identical reasoning that left `/import`
open. Now reviewed and refused before anything is written, and the plugin is not
recorded as installed either.

### 4. The Plugin Hub dropped every warning it was given

`/api/hub/install/{pack_id}` — the endpoint the pane **actually calls** —
wrapped the underlying installers and discarded their `warnings` array. Same in
the collection installer, and in all three frontend handlers.

The entire justification for *warning* rather than *refusing* prompt injection is
that **the user decides**. A user cannot decide about a warning that never
reaches the screen, so in practice the injection scanner was doing nothing at
all for the primary install flow.

**Fix:** warnings are forwarded through the hub wrapper and the collection
installer, and the UI now shows a dialog naming each one, with honest scoping
("skill runs have no tool or file access, so this cannot execute anything — but
the agent's answers may be affected"). The custom-URL door additionally
distinguishes a *refusal* from a network failure — previously both collapsed to
`Install failed:` with no detail.

### 5. A partial import reported a clean success

Skills the scanner refused were skipped and the response still returned
`ok: true` with a count of what landed. A workspace could arrive silently
incomplete. `ok` now means nothing was refused; `rejected`, `rejected_count` and
an explicit `error` describe the rest. The audit entry records
`rejected=N` instead of only the imported counts.

---

## Revert-proof

Each fix individually reverted, `__pycache__` cleared each time.
**12 of 12 real breakages caught**, baseline green before and after.

| # | Breakage | Tests failed |
|---|---|---|
| 1 | `/import` safety review removed | 6 |
| 1b | import warnings dropped | 1 |
| 2 | malformed payload guard removed | 2 |
| 2b | skill shape guard removed | 1 |
| 3 | partial import reports ok | 5 |
| 3b | import audit drops refusals | 1 |
| 4 | registry install gate removed | 1 |
| 5 | hub wrapper drops warnings | 2 |
| 6 | scanner allows attribute access | 1 |
| 6b | scanner allows dunders | 1 |
| 6c | scanner drops bare `{}` field | 1 |
| 6d | injection over-blocks installs | 4 |

Note 6d: the mirror case matters as much as the others. Making injection a hard
*error* would be over-blocking, and four tests fail if it happens — the scanner's
deliberate refuse/warn split is pinned in both directions.

### A 13th breakage that was proven redundant

Removing the outer `isinstance(skills_in, list)` guard failed **zero** tests. I
checked rather than assuming the test was weak: a string is iterable, so its
characters fall through to the per-entry `isinstance(skill, dict)` guard and are
each refused. Removing *both* together does fail two tests. The two checks are
genuine defence-in-depth for one failure mode, so the outer one stays — with a
comment recording that the inner one is the load-bearing check and why the tests
target it. A test that cannot fail is usually a bad test; occasionally it is
correctly redundant code, and the distinction is worth proving either way.

## Live verification

Server + real Chromium:

```
POST /import  {traversal template}  -> 400, rejected_count=2, NOT on disk
POST /import  {safe template}       -> 200, imported.skills=1
POST /import  {"skills":"not-a-list"} -> 200 (skipped), no 500
install/json  {injection template}  -> 200 with 2 warnings returned

pane tabs:  ['plugins', 'skills', 'pluginsdk']
handlers:   hubInstall, hubUninstall, hubInstallCollection,
            hubShowInstallCustom, hubWarnAfterInstall — all resolve
            0 unresolvable data-act-click attributes
warning dialog rendered from a real server payload: yes
console: no errors, no [delegate] refusals
```

`renderSkills` reads as `undefined` until the Skills tab is opened — that is the
lazy chunk loader working as designed, confirmed by clicking the tab and
re-checking (`undefined` → `function`). The call sites already guard with
`typeof`.

## Cross-module impact

- **`/api/plugins/import` is now stricter.** A workspace export containing a
  traversal template returns **400** where it previously returned 200. This is
  the fix, but it is a behaviour change for any caller that assumed import
  always succeeds. Response gains `rejected`, `rejected_count`, `warnings`,
  `error`.
- **`/api/plugins/install/{id}`** can now return **400** with `unsafe: true`.
- **`/api/hub/install/{id}`** and the collection installer gain `warnings` /
  `warning_count`.
- **`plugin_safety.py` is unchanged** — it was already correct. Its properties
  are now pinned by tests (attribute access, dunders, bare `{}`, and the
  refuse/warn split) so a future edit cannot quietly weaken it.
- `marketplace` → `install_pack` and the SDK publish path were probed: the SDK
  normalises templates to `{input}` on publish, so that chain does not carry a
  caller-supplied template. Left as-is.
- `pluginsdk` (doc 68) untouched.

## Suite

`3991 unit (2 skipped)` + `655 regression/system/uat (10 skipped)` =
**4,646 passing, 0 failures**. Linters clean.
