# Module 11 — Prompt Library

**Commit:** `6aabd52` · **Suite:** 2541 passed / 17 skipped / 0 failed · ruff clean
**Surface:** `backend/routers/prompts.py` (525 lines, 11 endpoints) ·
`frontend/js/14-prompt-library.js` (896 lines)

Every finding below was reproduced against a live server before the fix and
re-verified after.

---

## 🔴 1. The advertised `{placeholder}` variables were never implemented

The prompt editor tells users, in its own placeholder text:

> *"The full prompt text… Use `{placeholder}` for variables."*

**Nothing anywhere substituted them.** Clicking "→ Use" copied the raw content
straight into the chat box, braces and all, and sent
`Review this {language} code in {repo}` to the model verbatim.

This is half a feature: the instruction shipped, the mechanism never did. A user
following the app's own guidance would get visibly broken prompts and no
indication why.

### What I added

- `extract_variables()` / `render_prompt()` in the router
- `POST /api/prompts/{id}/render` — fills values, returns finished text
- `POST /api/prompts/preview-variables` — for live editor hints
- `variables: [...]` exposed on list, get and search responses
- A fill-in dialog in the UI that appears only when a prompt has variables,
  with **Use as-is** for the case where you want the raw text
- A `⚙ 2 vars` badge on cards so parameterised prompts are visible at a glance

Two deliberate design calls:

- **Unfilled variables are reported, not blanked.** `missing: ["repo"]` and the
  token stays in place. Blanking silently changes what the prompt means.
- **`{{double braces}}` are not variables.** Prompts frequently contain JSON or
  code samples; treating `{{"ok": true}}` as a variable would corrupt them.

```
Review this {language} code in {repo} for {language} bugs. Return {{"json": true}}
  values {language: Python, repo: strick_tech}
→ Review this Python code in strick_tech for Python bugs. Return {{"json": true}}
```

---

## 🔴 2. An unknown `?category=` returned the *entire* library

```python
if category and category in VALID_CATEGORIES:   # ← unknown value just vanishes
    where.append('category=?')
```

An unrecognised category was dropped from the `WHERE` clause entirely. Verified
live: `?category=NOTREAL` returned **all 100 prompts** — the exact opposite of a
filter, with nothing to signal it hadn't applied.

The same class of bug on the write path: an unknown category on create/update
was silently rewritten to `'general'`, filing the prompt somewhere the user never
chose and would never think to look. A typo lost your prompt.

Both are `400` now with the valid set in the response. `sort` had the identical
hole and got the same treatment.

---

## 🔴 3. LIKE wildcards passed straight through

Search interpolated the query into `LIKE '%…%'` without escaping, so the user's
input was being interpreted as a pattern:

| Query | Meant | Actually matched |
|---|---|---|
| `%` | prompts containing a percent sign | **every row** |
| `_` | prompts containing an underscore | any single character |

Now escaped with `ESCAPE '\'`. Verified: `q='%'` went from 10 results
(everything) to only rows that genuinely contain a percent sign.

---

## 🔴 4. Import duplicated everything it touched

The docstring promised *"skips duplicates by title"*. The only guard was:

```python
INSERT OR IGNORE INTO prompt_library(id, …) VALUES(?, …)   # id = fresh uuid4
```

`INSERT OR IGNORE` protects the **primary key** — a freshly generated UUID that
never collides. The dedup was decorative. Verified live: importing the same title
three times produced three rows.

The practical consequence is worse than it sounds: **export → import doubled the
library every single time**. That's the most obvious thing a user does with these
two buttons, and there's now a round-trip idempotency test for exactly it.

Deduplicates by title now, with an explicit `replace_existing` flag for the
overwrite case, reporting `imported` / `replaced` / `skipped` separately.

---

## 🔴 5. Two hard 500s in import

- **A non-dict entry** (string, number, `null`) raised `AttributeError` on
  `.get()` and aborted the whole import with a bare 500.
- **Tags supplied as a list** crashed — even though `create()` *explicitly*
  accepts that shape. So a library exported from this very API could fail to
  import back into it.

Both are handled per-entry now: one bad row is skipped with a reason attached,
the good ones still import.

---

## 🟡 Also fixed

| Issue | Detail |
|---|---|
| **Seven endpoints 200-on-missing** | get / patch / delete / use / duplicate / render all returned `{"ok": false}` with HTTP 200. Now 404; validation 400; create and duplicate 201. |
| **Duplicate naming** | Duplicating twice produced two prompts both called "Copy of X", and `Copy of Copy of …` accumulated. Copies are numbered, and long titles truncate in the **middle** so the distinguishing tail survives the 120-char cap. |
| **No indexes** | Nothing indexed on `category`, `updated_at`, `use_count`, `is_favorite` or `agent_id` — every list request was a full table scan. Added five. |
| **Tag junk** | `",,,   ,,,"` stored verbatim. Now de-duped, trimmed, capped. |
| **Frontend hid reasons** | Bare status numbers discarded the server's explanation, including which categories are valid. |

---

## Test-harness fix

`tests/integration/conftest.py`'s `ok_or()` returned `{}` for anything other than
200 — **including the other codes the caller explicitly allowed**. So
`ok_or(r, 200, 201)["id"]` raised `KeyError` on a 201, and every assertion about a
non-200 body downstream of it was silently vacuous.

This is the same flaw already fixed in `tests/uat/conftest.py`'s `j()` (Module 7)
and `tests/system/conftest.py`'s `must()` (Module 9 follow-ups). **That's now all
three of them** — this particular item is off the outstanding list for good.

---

## Data hygiene

The production library had grown to **614 prompts of which only 212 titles were
distinct** — 44 copies each of test fixtures named `GetPrompt`, `IDPrompt`,
`DuplicateSource`, `UpdatedPrompt`. Left behind by suites that write to
`memory/agentic.db`. Pruned to 173 distinct prompts.

The underlying cause — tests sharing the production database — **has now
interfered with five separate reviews**. A per-run temp database remains my
standing recommendation.

---

## Verified working (no change needed)

- The card rendering is genuinely well-built: a previous fix replaced
  `onclick="usePrompt(${JSON.stringify(p.content)})"` with delegated
  `data-prompt-action` handlers, and everything rendered is escaped.
- Route ordering is correct — `/categories`, `/search` and `/export` are declared
  before `/{prompt_id}`, so they aren't shadowed.
- Export produces clean, re-importable JSON (which is what made the import
  duplication bug so visible once tested).

---

## Cross-module impact

| Module | Impact |
|---|---|
| **Chat** | Receives the rendered prompt; previously received raw `{braces}` |
| **Agents** | `agent_id` on a prompt is still unvalidated — see follow-ups |
| **Integration/UAT suites** | Create now returns 201; contracts updated in 5 files |

---

## Tests

`tests/unit/test_61_prompts_module_review.py` — **47 contracts** across variables,
category/sort validation, wildcard escaping, import dedup and crash-resistance,
status codes, duplicate naming and schema.

**Proven to catch the bugs: 45 of 47 fail against the pre-fix code.**

Two of my own tests were initially order-dependent — a sibling test left a
`50% off` prompt behind and broke the "wildcards are escaped" assertion. Rewritten
to assert the *property* (a bare `%` must match fewer rows than the total, and
every hit must genuinely contain one) rather than an absolute count, then
re-verified that they still fail against the unescaped code.

---

## Follow-up 1 — `agent_id` validation ✅ *done in `33dd786`*

A prompt could be pinned to any string. Verified live:
`POST /api/prompts {"agent_id": "not-a-real-agent-xyz"}` → **201 Created**. Since
`?agent_id=` filters on exact equality, the prompt then sat in the library
permanently unreachable through the agent filter — no error at write time, none
at read time. A typo in the free-text box silently lost the prompt.

Fixed with `check_agent_id()` on create, update and the list filter (400 with the
valid ids), plus `GET /api/prompts/agents` feeding a **picker** that replaces the
free-text input which caused the problem.

Two deliberate calls:

- **Validation fails open.** If the agents table can't be read, writes proceed
  rather than blocking on an unrelated failure — a validation helper that
  hard-fails is worse than the gap it closes. There's a test pinning this.
- **Import drops an unknown pin** rather than rejecting the row. An export from
  another machine will legitimately name agents this one lacks; the content is
  the valuable part, so it imports unpinned with a warning.

The endpoint also reports `orphaned` pins — agent_ids referenced by prompts whose
agent no longer exists. Setting `<select>.value` to a missing option silently
selects nothing, so the editor adds an explicit *"(no longer exists)"* option
rather than letting an orphaned pin look cleared.

**Also found:** the `agents` table had grown to 242 rows, 230 of them test
residue — including agents named `' OR '1'='1'; DROP TABLE agents; --` and
`<script>alert(document.cookie)</script>`. The core 12 were intact, but the
payloads made the new error message useless. Pruned. **Sixth review affected by
tests sharing the production database.**

18 new contracts (65 total for this module); 12 fail against the pre-fix code.

---

## Follow-ups 2–4 ✅ *done in `fba53fa`*

### Version history

Editing overwrote in place with no history — for a library whose value is
iterating on wording, the phrasing that worked was gone the moment you changed
it. `prompt_versions` now snapshots the current state before every substantive
edit, with `GET /{id}/versions` and `POST /{id}/versions/{n}/restore`.

Four decisions worth recording:

- **A restore is itself snapshotted first** (`reason='pre-restore-vN'`), so
  rolling back by mistake isn't the thing that loses your work.
- **Only substantive edits create a version.** Toggling favourite, or saving
  identical text, does not — otherwise history fills with noise and the real
  revisions get buried.
- **Restore repairs dangling references rather than reintroducing them.** If the
  snapshot's category or agent was deleted since, the wording is restored (that's
  the point) but the category falls back to `general` and the agent pin clears.
  The response flags both, and the UI says so.
- History is capped at 50 versions per prompt.

### Usage analytics

`use_count` answered "how often" but never "when" or "in what context".
`prompt_usage` records surface, rendered length, and variables filled vs missing.
`GET /usage/stats` ranks by real usage over a window and reports `never_used` —
the library's dead weight.

The `variables_missing` column is the interesting one: **a prompt whose
placeholders are habitually left unfilled is a prompt whose design isn't
working**, and that was previously invisible.

### User-defined categories

Once the previous commit started correctly *rejecting* unknown categories rather
than silently rewriting them to `general`, the hardcoded set of 12 became a wall
— the fix made the rigidity felt. `prompt_categories` layers user categories on
top of the built-ins; names fold to an id (`"Marketing Copy"` →
`marketing-copy`). Built-ins can't be deleted, and a category still in use
returns 409 rather than orphaning its prompts into a state the validator rejects.

**Found while wiring this up:** `GET /categories` did a `GROUP BY` over
`prompt_library`, so it only reported categories that already had prompts. A
category with none — *including one just created* — was invisible, making a new
category look like it hadn't saved. It now lists every known category with
`builtin`/`label`/`count`, plus `orphaned`. The editor's dropdown was a hardcoded
list of the same 12, so a custom category could never be selected even once it
existed.

### Housekeeping

`DELETE /{id}` now also clears that prompt's versions and usage rows. There are
no FK cascades on these tables, so orphaned history would accumulate and
re-attach if an id were ever reissued.

39 new contracts (**104 total for this module**); 33 fail against the pre-change
code.

---

## Module status

All four follow-ups are complete. Remaining items are platform-wide rather than
specific to this module:

1. **Tests share the production database** (`memory/agentic.db`) — has now
   interfered with six reviews and twice degraded a fix while I was writing it.
   A per-run temp database remains my strongest standing recommendation.
2. **Duplicate-global CI lint** — still the top structural recommendation from
   the platform review.
