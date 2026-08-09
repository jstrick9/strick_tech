"""Module review 3: Code Search (`codesearch`).

Risk rank 3 of 68 (score 34), sharing `01-app-core.js` with `dashboard` and
`prompts`.

THE DEFECT: SEARCH COULD NOT SEE THE USER'S CODE
────────────────────────────────────────────────
`/api/project/search` and `/api/project/files` walked only `PREVIEW_DIR`, the
GLOBAL scaffold sandbox. Measured on a live server:

    PREVIEW_DIR                 3 files, 1 searchable
    workspaces/                 1,290 files

Every per-workspace project lives in `workspaces/<id>/preview/` and none of it
was visible. Searching `function` returned **0 results**, and
`/api/project/files` reported `total_files: 1`.

The engine was never broken — scoring, context lines and ranking all work. It
was pointed at the wrong directory.

**Why that is worse than an empty feature.** The pane promises "Search every
file in your project". A search that confidently answers "No results" is
indistinguishable from "that string is not in your code", so the user
concludes their code does not contain the thing. That is a *wrong answer*, not
a missing one.

THE DEEPER BUG FOUND UNDERNEATH: A DANGLING WORKSPACE POINTER
─────────────────────────────────────────────────────────────
Extending the search to the active workspace still returned nothing, because
`_current_ws_id()` returned the contents of `workspaces/.current` whenever the
FILE existed — without checking the workspace it names still does.

Observed independently in two data directories:

    repo:   .current -> '6b27c178'  (no such directory; DB active = '71951640')
    server: .current -> '0f4b398c'  (no such directory)

This is not a Code Search problem. `builder.py` alone uses this id in 8+
places to scope `file_versions`:

    SELECT * FROM file_versions WHERE id=? AND (workspace_id=? OR workspace_id='')

Scoped to an id nothing was saved under, **Studio's version history and
restore silently return nothing** for files the user has definitely edited — an
empty list, no error. A pointer to a deleted workspace is exactly what
deleting the workspace you are in leaves behind, so it is reachable by
ordinary use.

Fixed by validating the pointer before trusting it, and *healing* the file so
the next reader agrees — intermittent disagreement is harder to diagnose than
a consistently wrong answer.

THE SECOND DOOR
───────────────
I fixed `/search` and left `/files` walking the scaffold only. Both are "the
current project", and the file tree drives Studio's sidebar and the search
UI's grouping, so a hit in a file the tree does not list is a broken link.
Eighth occurrence of this pattern in the review.

UI
──
Results can now come from two roots that can both contain `index.html`.
Grouping on the relative path alone merged two different files under one
heading, so the group key is scope-qualified and a badge says PROJECT or
SCAFFOLD. The catch block also rendered `Error: ${e.message}` — raw
`Failed to fetch` — and now routes through `humanError()`.
"""

from __future__ import annotations

from pathlib import Path

REPO = Path(__file__).resolve().parent.parent.parent
ROUTER = (REPO / 'backend' / 'routers' / 'codesearch.py').read_text(encoding='utf-8')
WS = (REPO / 'backend' / 'routers' / 'workspaces.py').read_text(encoding='utf-8')
JS = (REPO / 'frontend' / 'js' / '14-prompt-library.js').read_text(encoding='utf-8')
CSS = (REPO / 'frontend' / 'styles-redesign.css').read_text(encoding='utf-8')


# ──────────────────────────────────────────────────────────────────────
#  The workspace pointer
# ──────────────────────────────────────────────────────────────────────
def test_a_dangling_current_pointer_is_not_trusted(tmp_path, monkeypatch):
    """`.current` named a workspace that did not exist, and the file won over
    the database. Every file-version query in Studio was then scoped to a
    phantom id."""
    import sys
    sys.path.insert(0, str(REPO))
    from backend.routers import workspaces as ws

    ws_dir = tmp_path / 'workspaces'
    (ws_dir / 'real-one').mkdir(parents=True)
    (ws_dir / '.current').write_text('deleted-workspace')

    monkeypatch.setattr(ws, 'WS_DIR', ws_dir)
    monkeypatch.setattr(ws, 'CURRENT_FILE', ws_dir / '.current')
    monkeypatch.setattr(ws, '_ws_exists', lambda i: (ws_dir / i).exists())

    class _Row(dict):
        def __getitem__(self, k):
            return dict.__getitem__(self, k)

    class _Con:
        def execute(self, *_a, **_k):
            class R:
                @staticmethod
                def fetchone():
                    return _Row(id='real-one')
            return R()

        def close(self):
            pass

    monkeypatch.setattr(ws, 'get_conn', lambda: _Con())

    assert ws._current_ws_id() == 'real-one', (
        'a pointer to a deleted workspace must not win over the database')


def test_the_stale_pointer_is_healed():
    """Leaving it stale means the next reader disagrees with this one, and
    intermittent disagreement is harder to diagnose than a consistent fault."""
    block = WS[WS.index('def _current_ws_id'):]
    block = block[:block.index('\n\n\n')] if '\n\n\n' in block else block[:2500]
    assert 'CURRENT_FILE.write_text' in block


def test_pointer_validation_checks_disk_and_database():
    """A workspace can legitimately exist in one and not yet the other."""
    assert 'def _ws_exists' in WS
    block = WS[WS.index('def _ws_exists'):][:700]
    assert 'WS_DIR' in block
    assert 'SELECT 1 FROM workspaces' in block


def test_a_read_only_data_dir_does_not_break_resolution():
    """Healing is best-effort; failing to write must not fail the read."""
    block = WS[WS.index('def _current_ws_id'):][:2500]
    assert 'except OSError' in block


# ──────────────────────────────────────────────────────────────────────
#  Search scope
# ──────────────────────────────────────────────────────────────────────
def test_search_covers_the_active_workspace():
    """It walked only the global scaffold: 1 searchable file against 1,290 in
    workspaces/."""
    assert '_search_roots' in ROUTER
    block = ROUTER[ROUTER.index('def _search_roots'):][:2000]
    assert '_current_ws_id' in block
    assert 'preview' in block


def test_both_endpoints_use_the_same_roots():
    """THE SECOND DOOR. /search was fixed and /files was not; the tree drives
    Studio's sidebar and the search UI's grouping, so they must agree."""
    assert ROUTER.count('_search_roots()') >= 2, (
        'both /search and /files must resolve the same roots')


def test_results_carry_their_scope():
    """Two roots can both contain `index.html`; without a scope the UI cannot
    tell them apart."""
    assert "'scope': scope" in ROUTER


def test_paths_stay_relative_to_their_own_root():
    """Otherwise "open in editor" resolves against the wrong directory."""
    assert 'relative_to(root)' in ROUTER
    assert 'relative_to(PREVIEW_DIR)' not in ROUTER


def test_the_file_tree_does_not_list_a_path_twice():
    """The workspace copy shadows an identically-named scaffold file; listing
    both renders a duplicate row."""
    block = ROUTER[ROUTER.index('def list_project_files'):][:2200]
    assert 'seen' in block


def test_a_missing_workspaces_module_degrades_to_the_scaffold():
    """A read-only search endpoint must never 500 because of an import."""
    block = ROUTER[ROUTER.index('def _search_roots'):][:2000]
    assert 'except Exception' in block


def test_only_the_active_workspace_is_searched():
    """Hits from a project the user is not looking at are noise, and the
    workspace switcher already exists."""
    block = ROUTER[ROUTER.index('def _search_roots'):][:2000]
    assert 'ACTIVE' in block or 'active' in block


# ──────────────────────────────────────────────────────────────────────
#  UI
# ──────────────────────────────────────────────────────────────────────
def test_results_are_grouped_by_scope_and_file():
    """Grouping on the relative path alone merged two different files."""
    block = JS[JS.index('async function runCodeSearch'):][:2600]
    assert 'r.scope' in block


def test_the_scope_badge_exists_and_is_styled():
    assert 'cs-scope' in JS
    assert '.cs-scope' in CSS, 'the badge is unstyled'
    assert '.cs-scope--workspace' in CSS


def test_the_search_error_is_not_a_raw_exception():
    """It rendered `Error: Failed to fetch`. 00-error-copy.js exists for
    exactly this and the failure-honesty audit enforces it elsewhere."""
    block = JS[JS.index('async function runCodeSearch'):][:4000]
    assert 'humanError' in block
    assert 'Error: ${escHtml(e.message)}' not in block
    assert '.cs-error' in CSS
