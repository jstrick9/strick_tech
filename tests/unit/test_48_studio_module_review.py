"""
Unit Tests — Code Studio module review (`tests/unit/test_48_studio_module_review.py`)

Regression guards for real defects found during the Code Studio review:

1. POST /api/studio/lint ignored the request body and linted the PLATFORM'S OWN
   source instead of the user's file, so the Studio "Lint" button could never
   report a problem with your code — it always said "Syntax validation passed."
2. DELETE /api/preview/delete with no path resolved to PREVIEW_DIR itself, passed
   the traversal guard, and raised IsADirectoryError as an unhandled HTTP 500 —
   one missing guard away from trying to unlink the whole preview root.
3. Path traversal must stay blocked on read/save/delete.
"""

from __future__ import annotations

from pathlib import Path

from backend.routers.builder import _lint_source

ROOT = Path(__file__).resolve().parents[2]
BUILDER_PY = (ROOT / 'backend' / 'routers' / 'builder.py').read_text(encoding='utf-8')
CORE_JS = (ROOT / 'frontend' / 'js' / '01-app-core.js').read_text(encoding='utf-8')
CONSOLE_JS = (ROOT / 'frontend' / 'js' / '14-prompt-library.js').read_text(encoding='utf-8')


class TestLintChecksUserCode:
    """The linter must analyse the submitted file, not Agentic OS's own source."""

    def test_detects_broken_python(self):
        errors = _lint_source('def f(\n    return 1', 'a.py')
        assert errors, 'broken Python must be reported'
        assert 'a.py' in errors[0]

    def test_accepts_valid_python(self):
        assert _lint_source('def f():\n    return 1\n', 'a.py') == []

    def test_detects_broken_json(self):
        errors = _lint_source('{"a": }', 'a.json')
        assert errors and 'a.json' in errors[0]

    def test_accepts_valid_json(self):
        assert _lint_source('{"a": 1}', 'a.json') == []

    def test_unknown_extension_is_not_an_error(self):
        assert _lint_source('anything at all', 'notes.txt') == []

    def test_endpoint_reads_request_body(self):
        # The old implementation took no arguments at all.
        assert 'async def studio_lint(req: Request)' in BUILDER_PY
        assert "body.get('content')" in BUILDER_PY

    def test_platform_selfcheck_is_opt_in_only(self):
        assert "scope != 'platform'" in BUILDER_PY

    def test_node_stack_trace_is_stripped_from_user_errors(self):
        # node --check appends a Node.js internal trace that is noise in an
        # editor console.
        assert "line.strip().startswith('at ')" in BUILDER_PY


class TestLintConsoleReportsHonestly:
    """The Studio console must surface real results, including failures."""

    def test_console_sends_the_open_file(self):
        assert "AgenticAPI.post('/api/studio/lint', { path: file, content })" in CONSOLE_JS

    def test_console_no_longer_claims_green_on_error(self):
        # The old catch block logged "Syntax validation check green." on failure.
        # Strip comment lines so the explanatory note about the bug doesn't
        # satisfy (or defeat) the assertion.
        code_only = '\n'.join(
            ln for ln in CONSOLE_JS.splitlines() if not ln.lstrip().startswith('//')
        )
        assert "logStudioConsole('lint', 'Syntax validation check green.')" not in code_only
        assert 'Lint request failed' in code_only


class TestPreviewDeleteSafety:
    """Deleting must never target the preview root or crash."""

    def test_empty_path_is_rejected(self):
        assert "return {'ok': False, 'error': 'path required'}" in BUILDER_PY

    def test_preview_root_itself_is_rejected(self):
        assert 'f == PREVIEW_DIR.resolve()' in BUILDER_PY

    def test_directories_are_rejected(self):
        assert "'cannot delete a directory'" in BUILDER_PY

    def test_unlink_errors_are_handled(self):
        assert 'except OSError as exc:' in BUILDER_PY

    def test_accepts_path_from_query_string(self):
        assert "req.query_params.get('path')" in BUILDER_PY


class TestAiEditCodeExtraction:
    """Fenced-code extraction must not destroy or corrupt the user's file."""

    def test_shared_extractor_exists_and_is_used(self):
        assert 'window.extractCodeFromResponse = function(raw)' in CORE_JS
        # Both the AI-edit and AI-format paths must use it.
        assert CORE_JS.count('window.extractCodeFromResponse(') >= 2

    def test_naive_slice_logic_is_gone(self):
        # The old logic blanked single-line fenced replies entirely.
        assert "proposed.split('\\n').slice(1).join('\\n')" not in CORE_JS

    def test_short_but_valid_edits_are_not_discarded(self):
        # The old guard rejected anything under 20 chars as "empty".
        assert 'proposed.length < 20' not in CORE_JS

    def test_no_op_edits_are_reported_clearly(self):
        assert 'suggested no changes' in CORE_JS
