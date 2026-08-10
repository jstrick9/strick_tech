# Module 12 — Information Hierarchy (Tier 1 / IVREN)

**Reviewed:** 2026-08-10
**Pane:** `hierarchy`
**Frontend:** `frontend/js/12-information-hierarchy.js` (788 lines)
**Backend:** `backend/routers/hierarchy.py` (567 lines)
**Endpoints:** 12
**Risk score:** 18

---

## Summary

This module compiles the context block injected into **every AI call in the
platform**, so a defect here misinforms every agent at once. Three found.

| # | Defect | Severity |
|---|---|---|
| 1 | Answering the guided interview with whitespace produced a "configured" profile and **silently removed the anti-hallucination guard** from every agent's context | High |
| 2 | `POST /projects/{id}/save` reported "updated successfully" when it wrote nothing | Medium |
| 3 | A pre-existing test pinned the weaker detection rule | — |

The module had already been hardened in an earlier pass (`configured` vs
`initialized`, "do not invent details" guard, traversal blocking on
`project_id`). These are the gaps that survived that pass.

---

## 1. A blank interview created a profile that looked real

`_is_placeholder()` detected an unfilled Tier 1 file by looking for an explicit
`<!-- agentic-os:unfilled -->` marker. That is the right idea for the shipped
templates. But **the guided interview generates its files from scratch**, so
they never carry the marker — and nothing checked whether the answers
contained anything.

Reproduced live, answering all four questions with whitespace:

```
POST /hierarchy/tier1/interview {"name_and_role":"   ", … all blank}
  -> ok: true

GET /hierarchy/status
  -> configured: true      (was false)
     tier1_unfilled: []    (was all four)

GET /hierarchy/compiled-context
  -> "# About Me
      - **Name / Role:**
      - **Background & Mission:**"
```

The compiled context is the block `chat.py` injects into every conversation.
Before: it carried an explicit guard —

> *The user has not set up their profile yet. Do not invent details about them,
> their business, their voice, or their pricing. If such a detail is needed, ask.*

After a blank interview that guard **disappeared**, replaced by four files of
empty headings. That is precisely the blank-context-invites-invention scenario
the guard exists to prevent — the module removed its own safety rail in
response to no information at all.

**Fix, at both doors:**

- `_has_substance()` strips Markdown scaffolding (headings, bullets, bold
  labels, blockquotes, `_(placeholder)_` prompts) and asks whether anything
  remains. `_is_placeholder()` is now *marker OR no substance*, so the direct
  `POST /tier1` save path is covered too — verified separately.
- The interview refuses blank answers with a 422 naming each empty field, and
  writes nothing.

### I got this wrong once

My first `_has_substance()` still returned `True` for the blank scaffold. The
cause: I stripped bullets *before* bold labels, so `- **Name:**` left an orphan
`-` that counted as content. Caught by running the seven-case table rather than
trusting the patch — reordering fixed it.

---

## 2. A save that wrote nothing said it succeeded

`POST /projects/{id}/save` takes five optional fields. If a request named none
of them it fell through every branch and returned:

```json
{"ok": true, "message": "Project 'm12' IVREN hierarchy updated successfully"}
```

A typo'd field name, or a client sending the wrong shape, was indistinguishable
from a real save — and the UI shows `✅ Saved IVREN section: <name>` on `ok`.

Now returns 422 when nothing was provided, and on success reports
`sections_saved: [...]` so the caller can verify what actually landed. An
**empty string is still a valid edit** (deliberately clearing a section); only
absent fields are the no-op — covered by a test.

---

## 3. A pre-existing test pinned the weaker rule

`test_66_hierarchy_module_review.py::test_detection_survives_partial_edits`
failed against the fix. Its premise:

```python
edited = DEFAULT_TIER1['about_me'].replace(PLACEHOLDER_MARKER, '')
assert h._is_placeholder(edited) is False
```

It simulates "the user edited this file" by **deleting the marker** — but the
result still reads:

```
- **Name:** _(your name)_
- **Role:** _(what you do)_
```

Zero user content. The test was pinning marker-stripping, not editing.
**Updated in place, not deleted**: it now asserts the stripped-but-empty file
is still a placeholder, then performs a *real* one-line edit and asserts the
flag clears — preserving the property the test exists to protect
(marker-based, not equality-based, so a partial edit isn't flagged forever).

---

## Verified working (no change needed)

- Path traversal on `project_id` is blocked (`project_dir()` returns `None`;
  `/compiled-context` 400s). Probed with `..%2f..%2f` — correctly refused.
- The `_(your name)_` templates contain no invented personal or pricing
  details (an earlier fix; still holding, and now enforced by two rules).
- `/tier1/reset`, project create/delete, and note-append all behave; notes
  append with a timestamp and author rather than overwriting.
- The pane is IIFE-wrapped but **correctly exports all 25 handlers** — clean
  against the Module 11 defect class. Verified in Chromium: no
  `[delegate] unknown function` warnings, no page errors.
- `/compiled-context` already appends the Steering Rules block, so the
  "Preview Injection" UI shows the complete picture.

---

## Cross-module impact

- **Every agent conversation.** `chat.py` injects `/compiled-context`; the
  guard is now restored for any install whose profile is scaffolding-only,
  including ones that already ran a blank interview (detection is computed on
  read, so no migration is needed).
- **Steering / AI Guidelines** shares this pane and endpoint — unchanged.
- `POST /projects/{id}/save` now returns **422** where it previously returned
  a false success. The only caller is this pane, which always sends exactly
  one section.

---

## Tests

`tests/unit/test_145_module12_hierarchy.py` — **21 tests.**

Revert-proof (caches cleared, `hierarchy.py` reverted): **19 of 21 fail.**
The two survivors are deliberate guards on behaviour my change could have
broken — `test_explicit_marker_still_wins` (the original rule must keep
working) and `test_interview_accepts_real_answers` (the happy path the new
422 could have blocked).

Plus one pre-existing test updated in place with an in-file explanation.

Full suite: **3,629 unit + 655 regression/system/uat = 4,284 passing, 0 failures.**
