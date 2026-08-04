"""One shared path-containment helper, used everywhere.

The same defect was found independently in four modules during the
module-by-module review, and a sweep afterwards found it in five more:

    if str(target).startswith(str(BASE.resolve())):
        ...treat as safe...

str.startswith() compares STRINGS, not path components, so any sibling
directory whose name merely begins with the base name passes:

    BASE = <root>/preview
    '../preview_ESCAPED/x'  ->  <root>/preview_ESCAPED/x
    startswith(BASE)        ->  True     # accepted, but OUTSIDE

Note this survives `..` filtering: the RESOLVED path contains no `..` at all.
It is only caught by comparing correctly.

Where it mattered:
  imagegen  (M10) wrote images outside the workspace
  terminal  (M12) launched a SHELL outside the sandbox
  hierarchy (M13) read files into the LLM system prompt
  composer  (M14) let the MODEL choose the write path

Confirmed reachable in codeindex, codesearch, github, mcp, multitab, testgen
and integrations as well — nine modules in total.
"""
from __future__ import annotations

import ast
import io
import tokenize
from pathlib import Path

import pytest

from backend.services.safe_paths import PROTECTED_NAMES, is_within, safe_path

REPO = Path(__file__).resolve().parents[2]
BACKEND = REPO / 'backend'


# ── The helper itself ──────────────────────────────────────────────────────────


class TestSafePath:
    BASE = Path('/tmp/agentic-safe-path-base')

    @pytest.mark.parametrize(
        'evil',
        [
            '../base_ESCAPED/x',
            '../../etc/passwd',
            'a/../../b',
            'x\x00.html',
            '',
        ],
    )
    def test_escapes_are_refused(self, evil):
        assert safe_path(evil, base=self.BASE) is None

    def test_the_sibling_prefix_trick_is_dead(self):
        """The exact shape that defeated str.startswith() in nine modules."""
        base = Path('/tmp/preview')
        evil = '../preview_ESCAPED/pwn.html'
        naive = str((base / evil).resolve()).startswith(str(base.resolve()))
        assert naive is True, 'the old check really did accept this'
        assert safe_path(evil, base=base) is None, 'the new one must not'

    @pytest.mark.parametrize('good', ['index.html', 'js/app.js', 'a/b/c.txt'])
    def test_normal_paths_resolve_inside(self, good):
        resolved = safe_path(good, base=self.BASE)
        assert resolved is not None
        assert resolved.is_relative_to(self.BASE.resolve())

    def test_absolute_input_is_clamped_not_honoured(self):
        resolved = safe_path('/etc/passwd', base=self.BASE)
        assert resolved is not None
        assert resolved.is_relative_to(self.BASE.resolve())

    def test_non_string_input_is_refused(self):
        assert safe_path(None, base=self.BASE) is None
        assert safe_path(123, base=self.BASE) is None

    @pytest.mark.parametrize('name', ['.env', 'sub/.env', '.git/config', 'a/.ssh/id_rsa'])
    def test_protected_names_are_refused_when_requested(self, name):
        assert safe_path(name, base=self.BASE, protect_dotfiles=True) is None

    def test_protected_names_are_allowed_when_not_requested(self):
        """Off by default: only callers writing model/user files need it."""
        assert safe_path('.env', base=self.BASE) is not None

    def test_must_exist_is_honoured(self, tmp_path):
        (tmp_path / 'real.txt').write_text('x')
        assert safe_path('real.txt', base=tmp_path, must_exist=True) is not None
        assert safe_path('ghost.txt', base=tmp_path, must_exist=True) is None

    def test_protected_names_are_not_empty(self):
        assert '.env' in PROTECTED_NAMES and '.git' in PROTECTED_NAMES


class TestIsWithin:
    def test_sibling_prefix_is_outside(self):
        assert is_within('/tmp/preview_ESCAPED/x', '/tmp/preview') is False

    def test_a_real_child_is_inside(self):
        assert is_within('/tmp/preview/a/b', '/tmp/preview') is True

    def test_the_base_itself_is_inside(self):
        assert is_within('/tmp/preview', '/tmp/preview') is True

    def test_a_parent_is_outside(self):
        assert is_within('/tmp', '/tmp/preview') is False

    def test_garbage_is_outside_not_an_exception(self):
        assert is_within('\x00', '/tmp/preview') is False


# ── Repo-wide guard ────────────────────────────────────────────────────────────


def _executable_source(path: Path) -> str:
    """Source with comments and docstrings removed.

    The fixes are documented in comments that necessarily quote the old broken
    pattern, so a raw substring search matches the explanation rather than the
    code — a trap already hit in Modules 10, 12 and 14.
    """
    src = path.read_text(encoding='utf-8', errors='ignore')
    try:
        stripped = tokenize.untokenize(
            t for t in tokenize.generate_tokens(io.StringIO(src).readline)
            if t.type != tokenize.COMMENT
        )
        tree = ast.parse(stripped)
    except (SyntaxError, tokenize.TokenError, IndentationError):
        return src
    doc_lines: set[int] = set()
    for node in ast.walk(tree):
        if isinstance(node, (ast.Module, ast.ClassDef, ast.FunctionDef, ast.AsyncFunctionDef)):
            body = getattr(node, 'body', [])
            if (body and isinstance(body[0], ast.Expr)
                    and isinstance(body[0].value, ast.Constant)
                    and isinstance(body[0].value.value, str)):
                doc_lines.update(range(body[0].lineno, (body[0].end_lineno or body[0].lineno) + 1))
    return '\n'.join(
        ln for i, ln in enumerate(stripped.splitlines(), 1) if i not in doc_lines
    )


class TestNoModuleReintroducesTheBug:
    def test_no_startswith_containment_anywhere_in_backend(self):
        """This is the test that stops a tenth module repeating the mistake.

        Nine modules had it. Fixing them individually would leave nothing to
        catch the next one — the whole point of centralising was to make the
        wrong version detectable.
        """
        offenders = []
        for path in sorted(BACKEND.rglob('*.py')):
            if path.name == 'safe_paths.py':
                continue  # documents the anti-pattern by design
            code = _executable_source(path)
            for lineno, line in enumerate(code.splitlines(), 1):
                if '.startswith(str(' in line and 'resolve()' in line:
                    offenders.append(f'{path.relative_to(REPO)}:{lineno}')
        assert offenders == [], (
            'string-prefix path containment found; use safe_paths.safe_path() '
            f'or is_within() instead: {offenders}'
        )

    def test_the_shared_helper_is_actually_imported(self):
        """A helper nobody imports is not a fix."""
        importers = [
            p.name
            for p in sorted((BACKEND / 'routers').glob('*.py'))
            if 'safe_paths import' in p.read_text(encoding='utf-8', errors='ignore')
        ]
        assert len(importers) >= 10, f'only {len(importers)} modules use it: {importers}'


# ── Per-module behaviour after migration ───────────────────────────────────────


class TestMigratedModulesStillContain:
    """Each module kept its own wrapper name and signature; only the rule moved."""

    def test_composer(self):
        from backend.routers.multifile_agent import safe_preview_path

        assert safe_preview_path('../preview_ESCAPED/x.html') is None
        assert safe_preview_path('.env') is None, 'composer protects dotfiles'
        assert safe_preview_path('index.html') is not None

    def test_imagegen(self):
        from backend.routers.imagegen import _safe_preview_path

        assert _safe_preview_path('../preview_ESCAPED/x.png') is None
        assert _safe_preview_path('assets/images/a.png') is not None

    def test_hierarchy(self):
        from backend.routers.hierarchy import project_dir

        assert project_dir('../projects_ESCAPED') is None
        assert project_dir('../secretdir') is None
        assert project_dir('valid_project') is not None

    def test_integrations(self):
        from backend.routers.integrations import _safe_preview_path

        assert _safe_preview_path('../preview_ESCAPED/x') is None
        assert _safe_preview_path('page.html') is not None

    def test_terminal(self):
        from backend.routers.terminal import PREVIEW_DIR, _get_work_dir

        assert Path(_get_work_dir('../preview_ESCAPED')) == PREVIEW_DIR.resolve()
        assert Path(_get_work_dir('../../etc')) == PREVIEW_DIR.resolve()

    def test_mcp_sandbox_denies_traversal(self):
        from backend.routers import mcp

        with pytest.raises(Exception):
            mcp._sandboxed_path('../preview_ESCAPED/x')

    @pytest.mark.parametrize(
        'module', ['codeindex', 'codesearch', 'github', 'multitab', 'testgen', 'obsidian']
    )
    def test_sweep_modules_use_the_helper(self, module):
        src = (BACKEND / 'routers' / f'{module}.py').read_text()
        assert 'safe_paths import' in src
        assert 'is_within(' in src or 'safe_path(' in src
