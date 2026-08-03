# Module Review 03 — Template Gallery

**Reviewed:** 2026-08-03 · **Commit:** `b541606` · **Sidebar position:** Templates (ESSENTIALS)

**Scope:** `backend/routers/templates.py` (912 lines, 7 endpoints, 14 built-in templates),
`frontend/js/21-template-gallery.js` (466 lines), and the scaffold path into `preview/`.

**Verification:** every finding reproduced against a running server before fixing, and
re-verified after.

---

## Findings

### 🔴 1. Scaffolding silently destroyed unsaved work

The most serious defect in this module. `scaffold_template()` wrote into `preview/`
unconditionally — no confirmation, no undo.

I reproduced it directly:

```
before scaffold:  1   (hand-written index.html present)
after scaffold:   0   ** USER WORK DESTROYED **
```

What makes this worse than a normal overwrite: the template's **new** content *was*
written to `file_versions`, but the user's **replaced** content never was. So the work
wasn't merely hidden — it was genuinely unrecoverable. Clicking "⚡ Studio" on any
template card was enough to lose it.

**Fixed:** the endpoint now detects which files it would clobber and refuses with
`{needs_confirmation, conflicts:[...]}` unless the caller passes `overwrite:true`.
Anything replaced is first snapshotted into `file_versions` as *"Auto-backup before
scaffolding: &lt;template&gt;"*, so Studio's version history can restore it. The gallery
asks first, naming the exact files at risk, and reports how many were backed up.

### 🟠 2. Naming your project did nothing for 11 of 14 templates

The UI collects a project name and sends it on **every** scaffold. But substitution only
replaced four hardcoded strings — `YourSaaS`, `Your Name`, `Your Company`, `My App` —
which appear in only 3 of the 14 templates.

```
scaffolded todo-app as "MyCoolProject"
grep MyCoolProject → 0 matches
<title>Todo App</title>          ← unchanged
```

**Fixed:** `_apply_project_name()` falls back to rewriting the document `<title>` and the
first `<h1>` when no placeholder is present. The test asserts this for **all 14**
templates rather than spot-checking, so a future template can't quietly regress it.

### 🟠 3. Missing templates returned HTTP 200

`GET /{id}`, `GET /{id}/preview` and `POST /{id}/scaffold` all returned **200** with
`{"ok": false}` for a nonexistent template. Any caller branching on `if (r.ok)` — which
the gallery does — treated "not found" as success. All three now return 404.

### 🟡 4. "Save current work as a template" was unreachable

`POST /api/templates/scaffold-custom` shipped **fully working** — it snapshots the current
`preview/index.html` into `preview/templates/` — but **no control in the UI ever called
it**. The only way to keep a design was "＋ New Template", which stores a *prompt* in
localStorage (browser-scoped, lost on clear), not your actual code.

**Fixed:** added a "💾 Save Current Work" action wired to the real endpoint.

### 🟡 5. Hardening

- `_within_preview()` replaces a `str.startswith()` containment check that treated a
  sibling directory sharing a name prefix (`preview_backup/`) as being *inside* `preview/`.
- Removed a dead statement that read `description` from the request body and discarded
  the result.

---

## Verified working (no change needed)

- All 14 templates are structurally valid: unique ids, required fields, an HTML
  entrypoint each, no unsafe filenames
- List / categories / search filtering, category counts, tag search
- `file_versions` rows correctly tagged with the current `workspace_id`
- Project names are XSS-safe (`_safe_name` strips markup; `html.escape` adds
  defence-in-depth — confirmed a `<script>` payload cannot be injected)

---

## Cross-module impact

| Module | Impact |
|---|---|
| **Code Studio** | Primary beneficiary — scaffolding is the main way work lands in Studio, and it could previously destroy the file you had open. Version history is now the recovery path. |
| **Workspaces** | Backups are tagged with the active `workspace_id`, so restores stay scoped correctly. |
| **Chat** | "Insert into chat" is unaffected — it only writes to the chat input. |

---

## Tests added

`tests/unit/test_51_templates_module_review.py` — **22 contracts**:

- catalogue integrity (unique ids, required fields, HTML entrypoint, safe filenames)
- overwrite protection end to end (refusal, conflict list, pre-overwrite snapshot,
  UI confirmation, explicit opt-in)
- path containment, including the prefix-sibling case the old check got wrong
- project-name substitution across **all 14** templates + XSS safety
- 404 status codes
- reachability of the save-current-work feature

**Suite:** 2744 backend passed / 12 skipped / 0 failed · 69 vitest passed · ruff clean.

> As in earlier modules, ~4 LLM-backed tests time out when a real CPU-only model is
> serving. Confirmed environmental: all 54 in those files pass with inference stopped.

---

## Recommended follow-ups

1. **Templates are single-file only.** All 14 ship just `index.html`, yet the scaffold
   code, `file_versions` writes and preview-URL selection all already handle multi-file
   templates. A React/Vite or FastAPI starter would exercise that path and is the most
   valuable addition to this module.
2. **The catalogue is hardcoded in Python.** ~700 of the router's 912 lines are inline
   HTML string literals. Moving templates to `templates/<id>/` on disk would make them
   editable without touching backend code, and would let the marketplace ship new ones.
3. **`preview/templates/` has no listing endpoint.** Work saved via "Save Current Work"
   is written to disk but can only be reached by direct URL — it should appear in the
   gallery alongside built-ins.
