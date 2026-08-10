# Module 9 — Ambient (Project Health) · BugBot · Git AI

**Reviewed:** 2026-08-10
**Panes:** `ambient` (Project Health), `bugbot`, `gitai`
**Frontend:** `frontend/js/07-quality-tools.js` (787 lines)
**Backend:** `backend/routers/ambient.py`, `bugbot.py`, `gitai.py`
**Endpoints:** 30
**Risk score:** 20 (joint highest unreviewed)

---

## Summary

Six defects. The module's entire purpose is *telling the user the truth about
their code*, and five of the six were the tool being wrong about exactly that.

| # | Component | Defect | Severity |
|---|---|---|---|
| 1 | gitai | A failed git call was read as a clean repo — green **"✅ Clean"** badge on a directory that is not a repository | High |
| 2 | gitai | `.strip()` ate porcelain's significant leading column; first changed file rendered as **`.py`** | High |
| 3 | gitai | Untracked files reported as staged | Medium |
| 4 | bugbot | Streaming review stored **score 75 / severity low / 0 issues** for a diff containing `eval(user_input)`, with no provider configured | High |
| 5 | ambient | Health scanned a scratch dir with one file → confident **100/A**, while Git AI graded the same tree **F** | High |
| 6 | ambient | SQL-injection rule used `re.DOTALL` and flagged **89 of 120** backend files | Medium |

---

## 1–3. Git AI could not tell "no repository" from "nothing to report"

`_git()` returns a return code that every caller discarded:

```python
stdout, stderr, code = _git(['status', '--porcelain'])   # `code` never used
...
'clean': len(changed) == 0
```

`git status` in a non-repository exits **128** with empty stdout. Empty stdout
also means a clean tree. The two were indistinguishable, so the pane rendered:

> 🌿 **(no branch)** | 0 changed files ✅ **Clean**

for `/tmp/agentic-test-data`, which has no `.git` at all. Every other Git AI
feature then failed for a reason the user could not see.

`_repo_error()` now classifies the failure (`not_a_repo`, `no_commits`,
`git_error`) and `/status`, `/log` and `/diff` — **all three doors** — return
`ok:false, repo:false` with an actionable hint. The status bar shows the
reason instead of a green badge.

### The strip bug

`_git()` did `r.stdout.strip()`. `git status --porcelain` encodes index and
worktree state in the first two columns, so the leading space is data:

```
raw      ' M a.py'  -> line[3:] = 'a.py'   ✅
stripped 'M a.py'   -> line[3:] = '.py'    ❌
```

Only the **first** line loses its space, which is why this survived: a
one-file change showed a mangled name, a multi-file change corrupted just the
top row. `keep_output=True` preserves it, and the parser now reads the two
columns separately — which also fixes `'M '` (staged) and `' M'` (unstaged)
collapsing to the same value, and `'??'` untracked being reported as staged.

---

## 4. BugBot passed code it never reviewed

Non-streaming review routes are protected: `llm.complete()` raises
`LLMUnavailableError` and a global handler renders an honest 503.
`POST /review/diff/stream` uses `llm.stream()`, which **returns the
no-provider help text as content instead of raising** — so the handler never
fires. The stub text contains no JSON, the parser fell through to its
defaults, and this was written to the database:

```json
{"type":"done","review_id":"rev_...","issues":[],"score":75,"severity":"low"}
```

for a diff whose entire content was `+eval(user_input)`. Two such phantom
reviews were already sitting in `bugbot_reviews` at score 75, dragging
`avg_score` with them.

Now `llm_svc.is_stub()` is checked on the terminal frame and the stream emits
an explicit `error` frame **before** the INSERT. Nothing is persisted, and the
UI renders a "No review was performed" notice with a setup link.

This is the **11th "second door"**: the non-streaming route was fixed long
ago, its streaming twin was not.

---

## 5. Project Health graded an unscanned tree 100/A

`security` and `debt` scanned `PREVIEW_DIR` only — a scratch directory holding
a single `index.html` on a normal install — capped at 50 files. Result:

```
security: 100  "No obvious security issues found"
debt:     100  "0 TODO/FIXME/HACK/BUG comments, 0 files over 300 lines"
overall:  100  grade A
```

Meanwhile the **Git AI security scanner in the same module**, pointed at
`backend/`, returned 36 vulnerabilities (28 critical) and **grade F**; the
same tree holds 99 TODO comments and 81 files over 300 lines. Two panes, one
module, opposite verdicts — and the reassuring one drove the headline grade.

Module 6 had already fixed `complexity` and `docs` to return `None` when
unmeasured. `security` and `debt` were left emitting a confident 100 from an
empty scan — the same bug, two dimensions over.

**Fix:** a shared `_health_scan_files()` walks `preview/`, `workspaces/`,
`backend/` and `frontend/` (skipping vendor dirs, capped at 400). Both
dimensions return `None` when there is genuinely nothing to scan, rather than
100.

### Scores had to become densities

Once the scan saw a real tree, both scores pinned to exactly **0** — 304 TODOs
× 2 and 122 large files × 5 both blow past the 100 clamp. A fixed 0 is as
uninformative as a fixed 100. Scoring per-file keeps the number responsive:

| | before fix | after scan fix | after density fix |
|---|---|---|---|
| security | 100 | 0 | 78 |
| debt | 100 | 0 | 54 |
| **overall** | **100 (A)** | 23 (F) | **75 (C)** |

A defensible C, consistent with the other scanner.

---

## 6. The SQL rule matched almost every file

```python
re.compile(r'(?i)f["\'].*(SELECT|INSERT|UPDATE|DELETE).*{', re.DOTALL)
```

`re.DOTALL` makes `.*` cross newlines, so a benign `f"hello {user}"` near the
top of a file matched against the word `SELECT` in a comment hundreds of lines
below. Measured: **89 of 120** backend files flagged. Anchored to an
`execute()` call, on one line, with the interpolation inside the same string
literal: **27**.

Also removed: a dict literal in `project_health()` that built the snapshot row
and discarded it — the real `INSERT` follows immediately after.

---

## A test of mine was caught by an existing test

`test_86_cross_cutting_hardening.py::test_every_data_driven_href_is_sanitised`
failed on my new BugBot notice: I used `escHtml(d.setup_url)` in an `href`.
`escHtml` escapes quotes but leaves `javascript:` intact. The repo's own
hardening rule caught it and I switched to the existing `safeUrl()`. Worth
recording — the guardrail worked on the person adding the guardrails.

---

## Verified working (no change needed)

- Git AI's OWASP scanner: 97 files, 36 findings, correct severity split, and
  it already scans `backend/` rather than the scratch dir.
- `/gitai/deps/audit` → honest 503 with a setup URL (previously flagged as a
  possible gap; it is correct behaviour).
- BugBot's non-streaming routes (`/review/diff`, `/review/file`,
  `/review/github-pr`) all degrade to an honest 503.
- `/review/git` correctly reports "No changes to review".
- Natural-language git has a solid allow-list (`_READONLY_GIT`) and requires
  explicit caller opt-in for anything mutating — the model cannot escalate.
- Git AI happy path re-verified against a real throwaway repo: branch, log,
  diff, staged/unstaged all correct.

---

## Cross-module impact

- **Module 6 (quality-tools health grade)** and this module share
  `project_health()`. The grade moves from a fabricated 100/A to a measured
  75/C. `_health_tip()` still handles `None` correctly for the two newly
  nullable dimensions — covered by tests.
- **Module 8 (codeindex)** feeds `complexity` and `docs`; unchanged.
- `frontend/styles-redesign.css` gained `.qt-review-blocked`, `.qt-git-norepo`.
- Any consumer of `/api/gitai/status` must now handle `repo:false`; `clean` can
  be `null`. The only caller is this pane, updated in the same commit.

---

## Tests

`tests/unit/test_142_module9_quality_tools.py` — **23 tests.**

**A first attempt was blind.** Four SQL-rule tests re-declared the regex inside
the test file, so they passed against the broken DOTALL version and the fixed
one alike. The revert-proof exposed it: 17/23 failing instead of the expected
21. The patterns were hoisted to module scope (`ambient.SQL_INJECTION_PATTERN`)
and the tests now import the real object. **This is the 14th time an assertion
has matched its own fix rather than the code.**

Revert-proof after correction (caches cleared): **21 of 23 fail.** The two
survivors pin `_health_tip()` behaviour that the new `None` scores could break.

Full suite: **3,551 unit + 655 regression/system/uat = 4,206 passing, 0 failures.**
