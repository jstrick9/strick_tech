"""Platform-wide hardening contracts.

Two long-standing structural gaps, both flagged repeatedly across module
reviews and closed together.

1. TEST DATABASE ISOLATION
   tests/unit/conftest.py set AGENTIC_TEST_DB in an autouse session fixture
   whose docstring promised "unit tests never touch production agentic.db".
   Nothing in the backend read that variable — `grep -rn AGENTIC_TEST_DB
   backend/` returned zero hits — so every suite wrote straight into
   memory/agentic.db while appearing sandboxed.

   Proven before the fix: running tests/unit/test_08_sessions_prompts.py took
   the production prompt_library from 503 rows to 511. Accumulated residue
   interfered with six module reviews and twice degraded a fix mid-write.

2. DUPLICATE FRONTEND GLOBALS
   frontend/js has no module system: 63 scripts share one namespace via
   `window`. Two files claiming the same name is silent, load-order dependent,
   and has already shipped real bugs. scripts/lint_globals.py now fails CI on
   an unmarked cross-file collision.
"""
from __future__ import annotations

import os
import subprocess
import sys
from pathlib import Path

import pytest

REPO = Path(__file__).resolve().parents[2]
LINTER = REPO / 'scripts' / 'lint_globals.py'


# ── 1. Test database isolation ─────────────────────────────────────────────────


class TestDatabaseIsolation:
    def test_backend_actually_reads_the_env_var(self):
        """The whole gap was a fixture setting a variable nobody consumed."""
        hits = subprocess.run(
            ['grep', '-rn', 'AGENTIC_TEST_DB', str(REPO / 'backend')],
            capture_output=True, text=True,
        )
        assert hits.stdout.strip(), 'no backend module reads AGENTIC_TEST_DB'

    def test_db_path_is_resolved_per_call_not_at_import(self, monkeypatch, tmp_path):
        """A module-level constant binds before conftest can set the variable.

        ~40 routers call _ensure_schema() at import time, so the path has to be
        resolvable dynamically or the sandbox ends up missing their tables.
        """
        from backend.services import memory_db

        target = tmp_path / 'switched.db'
        monkeypatch.setenv('AGENTIC_TEST_DB', str(target))
        assert memory_db.db_path() == target

    def test_falls_back_to_the_real_path_when_unset(self, monkeypatch):
        from backend.services import memory_db

        monkeypatch.delenv('AGENTIC_TEST_DB', raising=False)
        assert memory_db.db_path() == memory_db.DB_PATH

    def test_the_running_suite_is_sandboxed(self):
        """Guards against a future edit quietly re-pointing tests at prod."""
        from backend.services import memory_db

        resolved = str(memory_db.db_path())
        assert os.environ.get('AGENTIC_TEST_DB'), 'conftest must set the sandbox before imports'
        assert resolved == os.environ['AGENTIC_TEST_DB']
        assert not resolved.endswith('memory/agentic.db'), 'running against production data'

    def test_writes_land_in_the_sandbox_not_production(self, client):
        """End-to-end: create a row and confirm which file it went into."""
        import sqlite3

        title = 'IsolationProbe_do_not_persist'
        r = client.post('/api/prompts', json={'title': title, 'content': 'x'})
        assert r.status_code == 201
        try:
            sandbox = sqlite3.connect(os.environ['AGENTIC_TEST_DB'])
            try:
                found = sandbox.execute(
                    'SELECT COUNT(*) FROM prompt_library WHERE title=?', (title,)
                ).fetchone()[0]
            finally:
                sandbox.close()
            assert found == 1, 'the write did not reach the sandbox'

            prod = REPO / 'memory' / 'agentic.db'
            if prod.exists():
                con = sqlite3.connect(f'file:{prod}?mode=ro', uri=True)
                try:
                    leaked = con.execute(
                        'SELECT COUNT(*) FROM prompt_library WHERE title=?', (title,)
                    ).fetchone()[0]
                finally:
                    con.close()
                assert leaked == 0, 'test data leaked into the production database'
        finally:
            client.delete(f"/api/prompts/{r.json()['id']}")

    def test_routers_with_their_own_connections_are_redirected_too(self):
        """database.py and websearch.py opened a hardcoded path directly.

        Compares against a comment/docstring-stripped copy: both files document
        the old connect-to-DB call in prose, so a raw substring search matches
        the explanation rather than the code.
        """
        import ast
        import io
        import tokenize

        def code_only(src):
            toks = [t for t in tokenize.generate_tokens(io.StringIO(src).readline)
                    if t.type != tokenize.COMMENT]
            stripped = tokenize.untokenize(toks)
            doc_lines = set()
            for node in ast.walk(ast.parse(stripped)):
                if isinstance(node, (ast.Module, ast.ClassDef, ast.FunctionDef, ast.AsyncFunctionDef)):
                    body = getattr(node, 'body', [])
                    if (body and isinstance(body[0], ast.Expr)
                            and isinstance(body[0].value, ast.Constant)
                            and isinstance(body[0].value.value, str)):
                        doc_lines.update(range(body[0].lineno, (body[0].end_lineno or body[0].lineno) + 1))
            return chr(10).join(ln for i, ln in enumerate(stripped.splitlines(), 1)
                                if i not in doc_lines)

        needle = 'sqlite3.connect(' + 'DB'
        for name in ('database', 'websearch'):
            src = (REPO / 'backend' / 'routers' / (name + '.py')).read_text()
            assert 'from ..services.memory_db import db_path' in src, name
            assert needle not in code_only(src), name + ' still bypasses the resolver'

    def test_health_reports_the_database_in_use(self, client):
        """Live-server suites can't see the fixture; they check this instead."""
        body = client.get('/api/health').json()
        assert 'db_path' in body
        assert body['db_is_test_sandbox'] is True

    @pytest.mark.parametrize(
        'conftest',
        ['system', 'integration', 'uat', 'regression', 'e2e_browser'],
    )
    def test_live_suites_verify_the_server_is_sandboxed(self, conftest):
        src = (REPO / 'tests' / conftest / 'conftest.py').read_text()
        assert '_assert_server_db_is_sandboxed' in src, f'{conftest} has no sandbox check'
        assert 'AGENTIC_REQUIRE_TEST_DB' in src

    def test_ci_enforces_the_sandbox_for_live_suites(self):
        ci = (REPO / '.github' / 'workflows' / 'ci.yml').read_text()
        assert 'AGENTIC_REQUIRE_TEST_DB' in ci
        assert 'AGENTIC_TEST_DB' in ci


# ── 2. Duplicate-globals linter ────────────────────────────────────────────────


def _run_linter(js_dir: Path | None = None):
    """Run the linter, optionally against a synthetic frontend/js directory."""
    cwd = js_dir.parents[1] if js_dir else REPO
    script = LINTER
    if js_dir:
        script = js_dir.parents[1] / 'scripts' / 'lint_globals.py'
    return subprocess.run(
        [sys.executable, str(script)], capture_output=True, text=True, cwd=str(cwd)
    )


@pytest.fixture
def fake_frontend(tmp_path):
    """A throwaway repo layout so the linter can be tested on real input."""
    js = tmp_path / 'frontend' / 'js'
    js.mkdir(parents=True)
    scripts = tmp_path / 'scripts'
    scripts.mkdir()
    (scripts / 'lint_globals.py').write_text(LINTER.read_text())
    return js


class TestDuplicateGlobalsLinter:
    def test_the_real_frontend_is_clean(self):
        result = _run_linter()
        assert result.returncode == 0, result.stdout + result.stderr

    def test_it_catches_a_cross_file_clobber(self, fake_frontend):
        (fake_frontend / 'a.js').write_text('window.doThing = function () {};\n')
        (fake_frontend / 'b.js').write_text('window.doThing = function () {};\n')
        result = _run_linter(fake_frontend)
        assert result.returncode == 1
        assert 'doThing' in result.stdout
        assert 'a.js' in result.stdout and 'b.js' in result.stdout

    def test_same_file_reassignment_is_not_flagged(self, fake_frontend):
        """`window._page = 1` then `= 2` is ordinary state, not a collision."""
        (fake_frontend / 'a.js').write_text(
            'window._page = 1;\nwindow._page = 2;\nwindow._page = 3;\n'
        )
        assert _run_linter(fake_frontend).returncode == 0

    def test_an_intentional_override_is_allowed(self, fake_frontend):
        (fake_frontend / 'a.js').write_text('window.nav = function () {};\n')
        (fake_frontend / 'b.js').write_text(
            '// intentional-override: wraps core nav to add focus handling\n'
            'window.nav = function () {};\n'
        )
        result = _run_linter(fake_frontend)
        assert result.returncode == 0, result.stdout

    def test_the_marker_may_sit_a_few_lines_above(self, fake_frontend):
        (fake_frontend / 'a.js').write_text('window.nav = function () {};\n')
        (fake_frontend / 'b.js').write_text(
            '// intentional-override: decorates nav\n'
            'const orig = window.nav;\n'
            'if (typeof orig === "function") {\n'
            '  window.nav = function () { orig.apply(this, arguments); };\n'
            '}\n'
        )
        assert _run_linter(fake_frontend).returncode == 0

    def test_a_distant_marker_does_not_count(self, fake_frontend):
        """Otherwise one comment would licence the whole file."""
        (fake_frontend / 'a.js').write_text('window.nav = function () {};\n')
        (fake_frontend / 'b.js').write_text(
            '// intentional-override: about something else entirely\n'
            + '\n' * 12
            + 'window.nav = function () {};\n'
        )
        assert _run_linter(fake_frontend).returncode == 1

    def test_umd_shims_are_ignored(self, fake_frontend):
        (fake_frontend / 'a.js').write_text('window.define = undefined;\n')
        (fake_frontend / 'b.js').write_text('window.define = undefined;\n')
        assert _run_linter(fake_frontend).returncode == 0

    def test_equality_comparison_is_not_an_assignment(self, fake_frontend):
        (fake_frontend / 'a.js').write_text('window.thing = 1;\n')
        (fake_frontend / 'b.js').write_text('if (window.thing === 1) { doStuff(); }\n')
        assert _run_linter(fake_frontend).returncode == 0

    def test_list_mode_reports_without_failing(self):
        result = subprocess.run(
            [sys.executable, str(LINTER), '--list'],
            capture_output=True, text=True, cwd=str(REPO),
        )
        assert result.returncode == 0
        assert 'distinct globals' in result.stdout

    def test_ci_runs_the_linter(self):
        ci = (REPO / '.github' / 'workflows' / 'ci.yml').read_text()
        assert 'scripts/lint_globals.py' in ci


class TestDeadDuplicateRemoved:
    def test_open_create_skill_is_defined_once(self):
        """Two divergent copies existed; 25-skills.js silently won.

        The dead copy in 01-app-core.js lacked the try/catch and response.ok
        check the surviving one has, so it would have thrown on a non-JSON
        error response — a real difference, not a harmless duplicate.
        """
        core = (REPO / 'frontend' / 'js' / '01-app-core.js').read_text()
        skills = (REPO / 'frontend' / 'js' / '25-skills.js').read_text()
        assert 'window.openCreateSkill = async function' not in core
        assert 'window.openCreateSkill = openCreateSkill' in skills
