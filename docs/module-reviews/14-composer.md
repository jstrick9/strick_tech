# Module 14 — Composer (multi-file agent)

**Commit:** `acfcca0` · **Suite:** 2885 passed / 17 skipped / 0 failed · ruff clean
**Surface:** `backend/routers/multifile_agent.py` (533 lines, 8 endpoints) ·
`frontend/js/19-composer.js` (290 lines)

Composer takes one instruction and lets the model create or edit **any number of
files** in the workspace. The write paths come from the LLM's own output, which
changes the character of path validation here: it isn't sanitising a form field,
it's a **trust boundary against the model**. A prompt-injected instruction, a
poisoned RAG memory, or simply a confused model decides where bytes land.

---

## 🔴 1. Path containment used a string prefix — for LLM-chosen paths

Every write site tested containment like this:

```python
target = (PREV / path).resolve()
if not str(target).startswith(str(PREV.resolve())):
    continue
```

That compares **strings**, not path components, so a sibling directory whose name
merely begins with `preview` passes:

```
'../preview_ESCAPED/pwn.html'  →  <root>/preview_ESCAPED/pwn.html   ACCEPTED
```

This is the **fourth appearance** of the identical defect — imagegen (M10),
terminal (M12), hierarchy (M13), and now here. It's the highest-impact instance
so far precisely because the value being checked is *model output*, not a
user-typed field.

### The fix

A shared `safe_preview_path()` using `Path.relative_to()`. It also refuses
**protected filenames at any depth** — `.env`, `.git/config`, `.npmrc`,
`.ssh/id_rsa` — because generated code writing those alters how the workspace
itself behaves rather than adding project content.

Proven end to end with a mocked LLM emitting a plan containing an escape path
and a `.env` alongside a legitimate `index.html`:

```
files written : ['index.html']
files refused : ../preview_ESCAPED/pwn.html, .env
escaped file on disk: False
.env written        : False
```

Refusals are now `file_error` events. The old code did a bare `continue`, so the
run reported **"done"** with a file silently missing and no indication why.

---

## 🔴 2. Deleting one branch could delete every branch

```python
branch_dir = PREV / 'branches' / re.sub(r'[^a-zA-Z0-9_-]', '', branch_name)
if branch_dir.exists():
    shutil.rmtree(branch_dir)
```

It **strips** unsafe characters instead of rejecting the name. `'..'`, `'...'`
and `'////'` all reduce to `''`, so the path becomes `PREV/'branches'/''` — the
**branches root** — and `rmtree` takes everything.

Verified live:

```
before: ['keep-me-b', 'keep-me-a']
DELETE /api/composer/preview/branches/...   →  HTTP 200
after : []                                      ← both gone, directory too
```

Stripping-instead-of-rejecting is a recurring theme: it turns malformed input
into *different valid-looking* input rather than an error. Now normalises and
**rejects**, with an explicit guard that the resolved directory is never the
branches root. All four payloads refused, both branches intact, legitimate
delete still 200.

---

## 🟡 3. Status codes

Missing instruction, missing image, and unusable branch names all returned
HTTP 200. Now 400; a missing branch is 404.

---

## 🟡 4. Frontend

| Issue | Detail |
|---|---|
| **`file_error` never rendered** | A refused file sat on "⏳" forever — exactly the events the backend fix now emits, so this had to be wired up alongside it. |
| **`preview_url` unescaped in an `href`** | Now validated as a same-origin path and escaped. |
| **Bare status numbers** | Replaced with the server's explanation. |

---

## Verified working (no change needed)

- The `provider='stub'` handling is already correct here — a previous fix added
  an explicit `result.get('ok') is False` check with a comment explaining that
  the stub text was once written over `index.html`. Worth noting because three
  other modules got this wrong.
- Branch snapshot copying already runs in a thread executor rather than blocking
  the event loop.
- File writes are versioned into `file_versions`, so Studio's history can
  recover a composer overwrite.
- All rendered file paths and plan summaries are escaped.

---

## Cross-module impact

| Module | Impact |
|---|---|
| **Studio / Preview** | Shares `PREVIEW_DIR`; composer writes are what Studio displays |
| **Terminal** | Same sandbox root — both now use component-based containment |
| **Workspaces** | `activate` rmtree's `PREVIEW_DIR`, so branches vanish on a switch |
| **Memory / RAG** | Composer reads RAG hits into its system prompt — a poisoned memory is one route to a hostile file path, which is why containment matters |

---

## Tests

`tests/unit/test_67_composer_module_review.py` — **37 contracts**, including an
end-to-end run against a mocked LLM that attempts to escape, and a guard that no
write site regresses to the string-prefix check (compiled against a
comment/docstring-stripped copy, since the fix comment quotes the old pattern).

**Proven to catch the bugs: 36 of 37 fail against the pre-fix code.**

One of my own tests used `asyncio.get_event_loop()`, which passed in isolation
and failed in a full-suite run once another test had closed the loop. Switched to
`asyncio.run()`. Worth recording: a test that only passes when run alone is not
evidence.

---

## Recommended follow-ups

1. **`safe_preview_path()` should be one shared helper, not four.** Composer,
   imagegen, terminal and hierarchy now each have their own correct
   implementation of the same containment rule. Four correct copies is better
   than four broken ones, but it's still four places for the fifth module to not
   look at. This belongs in `backend/services/` with the others importing it.
2. **Composer has no dry-run.** It writes files immediately; the plan is shown
   *as* the writes happen, not before. A confirm step between `plan_ready` and
   the first write would make a bad instruction recoverable without digging
   through `file_versions`.
3. **No spend recording.** `max_tokens=8192` per run at `builder` model rates is
   among the most expensive operations in the platform, and it doesn't touch the
   cost ledger — the same gap still open in Swarm and Supervisor.
4. **`_extract_files()` trusts the model's `<FILE>` fencing.** Malformed or
   nested fences fall through to `_extract_code_blocks()`, which guesses. Worth
   surfacing "I could not parse a file list" rather than silently guessing at
   what to write.
