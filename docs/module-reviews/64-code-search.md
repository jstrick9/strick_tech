# 64 — Module review 3: Code Search (`codesearch`)

**Risk rank 3 of 68** (score 34), sharing `01-app-core.js` with `dashboard`
and `prompts`.

---

## The defect: search could not see the user's code

`/api/project/search` and `/api/project/files` walked only `PREVIEW_DIR` — the
**global scaffold sandbox**. Measured on a live server:

| Directory | Files |
|---|---|
| `PREVIEW_DIR` | 3 (1 searchable) |
| `workspaces/` | **1,290** |

Every per-workspace project lives in `workspaces/<id>/preview/`, and none of it
was visible. Searching `function` returned **0 results**; `/api/project/files`
reported `total_files: 1`.

The engine was never broken — scoring, context lines and ranking all work. It
was pointed at the wrong directory.

**Why that is worse than a missing feature.** The pane promises *"Search every
file in your project"*. A search that confidently answers "No results" is
indistinguishable from "that string is not in your code", so the user concludes
their code does not contain the thing. That is a **wrong answer**, not an
absent one.

---

## The deeper bug underneath: a dangling workspace pointer

Extending the search to the active workspace *still* returned nothing, because
`_current_ws_id()` returned the contents of `workspaces/.current` whenever the
**file** existed — without checking the workspace it names still does.

Observed independently in two data directories:

```
repo:    .current -> '6b27c178'   no such directory  (DB active = '71951640')
server:  .current -> '0f4b398c'   no such directory
```

**This is not a Code Search problem.** `builder.py` alone uses this id in 8+
places to scope file versions:

```sql
SELECT * FROM file_versions WHERE id=? AND (workspace_id=? OR workspace_id='')
```

Scoped to an id nothing was ever saved under, **Studio's version history and
restore silently return nothing** for files the user has definitely edited — an
empty list, no error. A pointer to a deleted workspace is exactly what deleting
the workspace you are in leaves behind, so it is reachable by ordinary use.

Fixed by validating the pointer against disk *and* the database before trusting
it, then **healing** the file — leaving it stale means the next reader
disagrees with this one, and intermittent disagreement is harder to diagnose
than a consistently wrong answer.

---

## The second door

I fixed `/search` and left `/files` walking the scaffold only. Both are "the
current project", and the file tree drives Studio's sidebar and the search UI's
grouping — a hit in a file the tree does not list is a broken link. **Eighth
occurrence** of this pattern in the review.

---

## UI

- Results can now come from two roots that can both contain `index.html`.
  Grouping on the relative path alone merged two different files under one
  heading; the group key is scope-qualified and a badge reads **PROJECT** or
  **SCAFFOLD**.
- The catch block rendered `Error: ${e.message}` — raw `Failed to fetch`. Now
  routed through `humanError()`, matching the convention the failure-honesty
  audit enforces elsewhere.

---

## Cross-module impact

- **`workspaces.py` is shared.** The pointer fix affects Studio, Templates and
  anything scoping by workspace — all of which were silently reading a phantom
  id. Full suite re-run: 3,443 unit + 655 passing.
- The `codesearch` router also serves `/api/project/memory`, `/suggestions`,
  `/review` and `/share`, which were **not** in scope here and remain
  unreviewed.
- `codeindex` is a separate pane with its own semantic index; it does not share
  this code path.

## Verification

| Check | Result |
|---|---|
| Search a workspace file (`greetUser`) | 0 → **1 hit**, `scope: workspace` |
| `/api/project/files` | 1 → **2 files**, both scopes |
| Both endpoints agree | yes |
| Dangling `.current` | healed to the real active workspace |
| Revert all fixes | **14 of 14** tests fail |
| Full suite | 3,443 unit (2 skipped) + 655 (10 skipped), 0 failures |
