# 80 — GitHub workstation: `github` host and the `deploy` tab

**Destination:** `github`
**Tabs:** `github` (host), `deploy` (this doc) · `gitai` (doc 70) — 3/3 covered
**Frontend:** `frontend/js/18-github.js`, `frontend/js/35-deploy.js`
**Backend:** `backend/routers/deploy.py`, `backend/routers/github.py`
**Tests:** `tests/unit/test_155_module19_github_deploy.py` (27)
**Status:** reviewed, fixed, verified live

Destination 8 of 20.

---

## Why this destination

This is the **publishing surface** — the last step before something the user
built becomes public. A false success here costs more than one on a dashboard,
because the artefact is *already live and wrong* by the time anybody looks. The
review's running theme (confident reporting of unverified things) shows up here
as its most concrete form: a deploy that shipped two thirds of a website and
called it done.

Eight defects. All reproduced against a live server before any code changed.

---

## Findings

### 1. Every image, font and media file was silently dropped from the deploy

`_BINARY_EXTS` was an **exclusion** list. `.png`, `.jpg`, `.gif`, `.ico`,
`.svg`, `.woff`, `.woff2`, `.ttf`, `.mp4`, `.mp3`, `.pdf`, `.wasm` — all skipped
outright, and the deploy then returned a clean success. Verified live with a
preview directory containing `index.html`, `app.js` and `assets/logo.png`:

```
collected: ['app.js', 'index.html']        # logo.png simply gone
```

A static site published without its logo, favicon or webfonts is **broken**, and
nothing anywhere reported it. The exclusion was never necessary either: Vercel's
API accepts `{"encoding": "base64"}` and Netlify takes a zip, so both providers
could always have carried binaries. It was just easier to skip them.

`.svg` deserves its own mention — it is plain text and was excluded anyway.

**Fix:** `_BINARY_EXTS` is now an *encoding* list, not an exclusion list.
Binaries go up base64; text goes up UTF-8. Only archives and executables
(`.zip`, `.tar`, `.gz`, `.exe`, `.dmg`, …) stay excluded, deliberately — they are
build artefacts, not part of a static site.

### 2. Oversize files and archives were dropped just as silently

The 1 MB per-file cap and the archive skip both `continue`d with at most a
`log.debug`. The exclusions were computed and thrown away.

**Fix:** `collect_deploy_files()` now returns `(files, excluded)` with a reason
per entry, the cap is raised to a realistic 10 MB, and every caller reports it:

```
bundle.zip -> archive or executable — not part of a static site
huge.css   -> 11.4 MB exceeds the 10 MB per-file limit
```

### 3. Undeclared binaries were corrupted rather than skipped

`path.read_text(encoding='utf-8', errors='replace')` meant any binary *not*
caught by the extension list was uploaded as a string of U+FFFD replacement
characters — a **corrupt** file at the far end, which is worse than an absent
one because it looks like it deployed. Now a `UnicodeDecodeError` routes the
file to base64 instead.

### 4. The Netlify zip would have carried base64 text

`zf.writestr(f['file'], f.get('data', ''))` writes the *data field*. Once (1)
was fixed, a base64 entry would have put the base64 **string** into the archive.
Now writes `_file_bytes(f)`.

### 5. The pane promised more files than it would publish

`/api/deploy/status` counted every file on disk; the pane rendered it as
*"N files ready in preview/"*. The deploy then shipped a different, smaller set.
Verified live:

```
UI shows preview_files = 4
actually deployable    = 2
```

**Fix:** `/status` counts what will actually be published and reports
`excluded_files` / `excluded_count` alongside. The pane now reads
*"4 files ready to publish · 2 file(s) will NOT be deployed"*.

### 6. Netlify was the only provider that recorded nothing

`vercel`, `railway`, `flyio` and `tunnel` all `memory_add` on success. Netlify
did neither `memory_add` nor `audit_log`, so a **real** Netlify deploy was
missing from `/api/deploy/history` and from memory search — a gap in the history
exactly where a deploy had happened. Now records both, and `vercel` gained the
`audit_log` it was also missing.

### 7. A partial GitHub push reported success

```python
'ok': files_pushed > 0
```

So a push where **1 of 200 files uploaded and 199 returned 422** reported
success, and the UI rendered *"✅ Pushed to GitHub!"*. The repository is left
half-written — the worst state to be quiet about, because the next push diffs
against a tree the user believes is complete.

**Fix:** `ok` now means every attempted file landed. A partial push returns
`status: 'partial'` with `files_attempted` / `files_failed` and an explicit
message; the UI renders *"⚠️ Partially pushed — N of M"* and tells the user to
re-run. The audit entry records the real ratio (`1/2 files (partial)`) instead of
a bare count that made a partial push look complete.

### 8. Smaller honesty gaps

- **`ready` was never verified.** `/status`'s per-provider `ready` flag is
  computed purely from `bool(os.getenv('VERCEL_TOKEN'))` — a token *string*
  existing. It has never been checked against the provider, so a revoked or
  typo'd token shows a green tick. Rather than issue seven live API calls on
  every status poll, the response now states its own basis
  (`readiness_basis: 'token presence only; not verified against the provider'`).
  This is the same class of defect as the vault's padlock (module 17) and the
  wizard's key check (module 17, finding 7).
- **Deploy history used `localtime`** and the response layer then appended `Z` —
  local wall-clock time labelled UTC. Third occurrence of this exact defect
  (modules 17, 18, now 19).
- **`/providers` hardcoded `count: 7`** next to a hand-maintained list; the
  count is now derived, and each provider carries a `kind` (`api` / `cli` /
  `manual` / `tunnel`) so the UI can stop treating Render's manual-only flow as
  equivalent to a real deploy.
- **`tunnel/stop` left stale state** when `terminate()` threw, and a tunnel that
  had already exited kept a non-`None` proc in the registry — which made the
  next *start* refuse with "already running". Both now clear the registry.

---

## Revert-proof

Each fix individually reverted, `__pycache__` cleared each time.
**18 of 18 breakages caught**, baseline green before and after.

| # | Breakage | Tests failed |
|---|---|---|
| 1 | binaries silently dropped | 5 |
| 1b | undeclared binary corrupted | 1 |
| 2 | oversize exclusion silent | 1 |
| 2b | archive exclusion silent | 6 |
| 2c | deploy warning suppressed | 4 |
| 4 | netlify zip writes base64 text | 1 |
| 5 | status counts disk files | 2 |
| 5b | readiness basis hidden | 1 |
| 5c | providers count drifts | 1 |
| 6 | netlify records nothing | 1 |
| 6b | netlify hides exclusions | 1 |
| 6c | vercel hides exclusions | 1 |
| 6d | deploy history off UTC | 1 |
| 7 | partial push reported ok | 1 |
| 7b | push status always complete | 3 |
| 7c | push audit drops the ratio | 1 |
| 8 | tunnel stop leaves state | 1 |
| 8b | dead tunnel not cleared | 1 |

### A test that could not catch its own bug

`test_the_netlify_zip_contains_the_real_binary` **did not fail** when I reverted
the router's `zf.writestr` line. Cause: the test built the zip *itself* from
`collect_deploy_files` + `_file_bytes` — helpers that were already correct —
rather than exercising the endpoint. It asserted my own test code.

Rewritten to capture the archive the endpoint actually POSTs to Netlify, by
stubbing `httpx.AsyncClient.post` and unzipping the captured body. It now fails
correctly when the router regresses (re-proven individually). This is the same
class of mistake as the harness artifact in module 18 — a test can only be
trusted once it has been *seen* to fail.

## Live verification

Server + real Chromium:

```
collect: index.html utf-8 | app.js utf-8 | assets/logo.png base64
zip:     logo.png first bytes b'\x89PNG\r\n\x1a\n'   (valid header)
status:  preview_files=4  excluded=2
           bundle.zip -> archive or executable
           huge.css   -> 11.4 MB exceeds the 10 MB per-file limit
pane:    "📁 4 files ready to publish from preview/ · 2 file(s) will NOT be deployed"
github:  all data-act-click handlers resolve; 0 unresolvable
console: no errors, no [delegate] refusals
```

## Cross-module impact

- **`collect_deploy_files()` is new and public**; `_collect_deploy_files()`
  remains as a files-only shim so nothing that imported it breaks.
- **Per-file cap raised 1 MB → 10 MB** and binaries now included, so deploy
  payloads get materially larger. The 500-file limit still applies and now
  reports the overflow instead of truncating silently.
- **API additions** (all additive): `/deploy/status` gains `excluded_files`,
  `excluded_count`, `readiness_basis`; vercel/netlify gain `files`, `excluded`,
  `excluded_count`, `warning`; `/providers` gains `detail`; `/github/push` gains
  `status`, `files_attempted`, `files_failed`, and `error` on a partial push.
  `/github/push`'s `ok` is now **stricter** — a partial push that previously
  returned `ok:true` now returns `ok:false` with `status:'partial'`, and the UI
  handles that branch explicitly.
- **`deploy/github-pages`** delegates into `routers/github.py`; unchanged.
- `gitai` (module 9) untouched.

## Suite

`3963 unit (2 skipped)` + `655 regression/system/uat (10 skipped)` =
**4,618 passing, 0 failures**. Linters clean.
