# Cross-cutting — path containment

**Commit:** `c9646f2` · **Suite:** 2922 passed / 17 skipped / 0 failed · ruff clean

Consolidating `safe_preview_path()` into one shared helper. What started as
"four correct copies should be one" turned up **five more modules still carrying
the original defect**.

---

## The defect

```python
if str(target).startswith(str(BASE.resolve())):
    ...treat as safe...
```

`str.startswith()` compares **strings**, not path components. Any sibling
directory whose name merely begins with the base name passes:

```
BASE = <root>/preview
'../preview_ESCAPED/x'  →  <root>/preview_ESCAPED/x
startswith(BASE)        →  True        ← accepted, but OUTSIDE
```

Worth stating plainly, because it's what makes this class of bug survive review:
**it is not caught by `..` filtering.** The *resolved* path contains no `..` at
all. Input sanitisation never sees anything suspicious — only comparing
correctly catches it.

---

## Scope was wider than the modules I'd reviewed

Fixed individually during the module reviews:

| Module | Consequence |
|---|---|
| imagegen (M10) | wrote images outside the workspace |
| terminal (M12) | launched a **shell** outside the sandbox |
| hierarchy (M13) | read files into the **LLM system prompt** |
| composer (M14) | the **model** chose the write path |

Still vulnerable — found by sweeping for the pattern rather than waiting to
review each module in turn:

| Site | Consequence |
|---|---|
| `codeindex.py:283` | index a directory outside the project root |
| `codesearch.py:450` | read a file outside `preview/` |
| **`github.py:256`** | **push a directory outside the project root to a remote repo** |
| `github.py:363` | write a cloned file outside its target directory |
| `mcp.py:305` | escape the MCP tool sandbox |
| `multitab.py:268` | read a file outside `preview/` |
| `testgen.py:58,115` | read a source file — and **write** a test file — outside `preview/` |
| `integrations.py` | already component-based, but duplicated the logic |

I verified each root is genuinely bypassable before changing anything:
`<root>_ESCAPED` passes `startswith()` and is refused by `relative_to()` for
every single one.

**`github.py:256` is the one I'd single out.** It selects a directory to push to
a *remote repository*, so the failure mode there is exfiltration rather than a
local write — the worst consequence of the nine, in a module I hadn't reached yet.

---

## The fix

`backend/services/safe_paths.py` — `safe_path()` and `is_within()`, both built
on `Path.relative_to()`.

Every module keeps its own wrapper name and signature; only the rule moved, so
no call site changed shape. That was deliberate: a refactor that also rewrites
twelve call sites is a refactor whose failures are hard to attribute.

Two design decisions:

- **`protect_dotfiles=True`** refuses `.env`, `.git/config`, `.npmrc`,
  `.ssh/id_rsa` and similar at *any* depth. Composer opts in because its paths
  come from the LLM — generated code writing those files modifies the
  environment rather than building in it. Off by default, since most callers
  handle user-chosen names where a leading dot is unremarkable.
- **Returns `None` rather than raising.** Each call site turns this into its own
  status code and message, and an exception would invite a bare `except` that
  swallows the refusal — a pattern this codebase already has too much of.

---

## The part that matters most

`tests/unit/test_68_shared_path_containment.py` — **37 contracts**. The one that
earns its place:

```python
def test_no_startswith_containment_anywhere_in_backend(self):
    """This is the test that stops a tenth module repeating the mistake."""
```

It walks every `.py` under `backend/` and fails on any string-prefix containment
check, comparing against a comment- and docstring-stripped copy so the fixes'
own explanations don't match themselves.

**Nine modules had this bug.** Fixing them one at a time would leave nothing to
catch the tenth. Centralising is only half the work; the guard is the other half.

Proven by reintroducing the pattern in `multitab.py` — the test fails naming
`backend/routers/multitab.py:253`.

---

## Verification

```
sibling-prefix bypass, post-migration:
  composer     : REFUSED
  imagegen     : REFUSED
  hierarchy    : REFUSED
  integrations : REFUSED
  terminal     : /home/user/repo/preview   (clamped to the sandbox)

legitimate paths still work:
  composer ok.html : True
  imagegen a/b.png : True
  hierarchy proj   : True
```

All 12 modules import cleanly; full suite green.

---

## What this doesn't cover

`safe_paths.py` bounds *where* a path resolves. It says nothing about whether
the caller should be touching the filesystem at all — that's authorisation, and
it remains per-module. The Terminal review's standing recommendation (OS-level
isolation for anything executing arbitrary code) is unaffected by this change.
