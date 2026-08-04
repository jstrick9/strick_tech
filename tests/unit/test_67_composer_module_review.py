"""Module 14 — Composer (multi-file agent) review contracts.

Composer takes one instruction and lets the model create or edit ANY number of
files in the workspace. The paths come from the LLM's own output, which makes
path containment here a genuine trust boundary rather than input validation:
a prompt-injected instruction, a poisoned RAG memory, or simply a confused
model chooses where bytes land.

Reproduced live before the fix:

1. PATH CONTAINMENT used str.startswith() on the resolved path — a prefix test
   on a STRING, not on path components:

     '../preview_ESCAPED/pwn.html' -> <root>/preview_ESCAPED/pwn.html  ACCEPTED

   Fourth appearance of the same defect (imagegen M10, terminal M12,
   hierarchy M13), and the highest-impact one so far because the attacker-
   influenced value is the model's output.

2. DELETE /preview/branches/{name} STRIPPED unsafe characters instead of
   rejecting. A name of '..' or '...' reduced to '', so the path became the
   branches ROOT and rmtree deleted EVERY branch. Verified live: two branches
   existed, DELETE returned 200, both were gone along with the directory.

3. Validation failures returned HTTP 200.

4. The frontend never rendered file_error, so a refused file stayed on "⏳"
   forever with no explanation.
"""
from __future__ import annotations

import asyncio
import json
from pathlib import Path

import pytest

from backend.routers import multifile_agent as mfa

REPO = Path(__file__).resolve().parents[2]
SRC = (REPO / 'backend' / 'routers' / 'multifile_agent.py').read_text()
JS = (REPO / 'frontend' / 'js' / '19-composer.js').read_text()


# ── 1. Path containment ────────────────────────────────────────────────────────


class TestPathContainment:
    @pytest.mark.parametrize(
        'path',
        [
            '../preview_ESCAPED/pwn.html',
            '../../etc/passwd',
            'a/../../b.html',
            '../preview2/x.html',
            'x\x00.html',
            '',
        ],
    )
    def test_escapes_are_refused(self, path):
        assert mfa.safe_preview_path(path) is None, f'{path!r} must be refused'

    def test_the_sibling_prefix_trick_is_dead(self):
        """'<root>/preview_ESCAPED' starts with '<root>/preview' as a STRING."""
        assert mfa.safe_preview_path('../preview_ESCAPED/pwn.html') is None

    @pytest.mark.parametrize('path', ['index.html', 'js/app.js', 'styles/main.css'])
    def test_normal_paths_resolve_inside_the_workspace(self, path):
        resolved = mfa.safe_preview_path(path)
        assert resolved is not None
        assert resolved.is_relative_to(mfa.PREV.resolve())

    def test_an_absolute_path_is_clamped_not_honoured(self):
        """'/etc/passwd' must land inside preview/, never at the real /etc."""
        resolved = mfa.safe_preview_path('/etc/passwd')
        assert resolved is not None
        assert resolved.is_relative_to(mfa.PREV.resolve())

    @pytest.mark.parametrize(
        'path', ['.env', 'sub/.env', '.git/config', 'nested/.npmrc', '.ssh/id_rsa']
    )
    def test_protected_filenames_are_refused_at_any_depth(self, path):
        """An LLM writing .env or .git/config changes how the workspace behaves."""
        assert mfa.safe_preview_path(path) is None

    def test_no_write_site_still_uses_the_string_prefix_check(self):
        import ast
        import io
        import tokenize

        code = tokenize.untokenize(
            t for t in tokenize.generate_tokens(io.StringIO(SRC).readline)
            if t.type != tokenize.COMMENT
        )
        tree = ast.parse(code)
        docs = set()
        for node in ast.walk(tree):
            if isinstance(node, (ast.Module, ast.ClassDef, ast.FunctionDef, ast.AsyncFunctionDef)):
                body = getattr(node, 'body', [])
                if (body and isinstance(body[0], ast.Expr)
                        and isinstance(body[0].value, ast.Constant)
                        and isinstance(body[0].value.value, str)):
                    docs.update(range(body[0].lineno, (body[0].end_lineno or body[0].lineno) + 1))
        executable = '\n'.join(
            ln for i, ln in enumerate(code.splitlines(), 1) if i not in docs
        )
        assert 'startswith(str(PREV' not in executable


# ── 2. The LLM controls these paths — end to end ───────────────────────────────


class TestGeneratedPathsAreContained:
    """The real scenario: the MODEL asks for a file outside the workspace."""

    MALICIOUS = '''<PLAN>
{"summary": "build", "files": [{"path": "index.html", "action": "create", "reason": "x"}]}
</PLAN>

<FILE path="index.html">
<h1>legit</h1>
</FILE>

<FILE path="../preview_ESCAPED/pwn.html">
ESCAPED
</FILE>

<FILE path=".env">
OPENROUTER_API_KEY=stolen
</FILE>
'''

    def _run(self, monkeypatch):
        async def fake_stream(*a, **k):
            for line in self.MALICIOUS.split('\n'):
                yield 'data: ' + json.dumps({'delta': line + '\n'}) + '\n\n'

        monkeypatch.setattr(mfa.llm, 'stream', fake_stream)

        class Req:
            async def json(self):
                return {'instruction': 'build a page', 'stream': False}

        # asyncio.run(), not get_event_loop(): by the time this runs another
        # test may have closed the loop, which surfaced as a RuntimeError only
        # in a full-suite run and not in isolation.
        return asyncio.run(mfa.composer_run(Req()))

    def test_escape_is_not_written_and_legit_file_is(self, monkeypatch):
        escaped = REPO / 'preview_ESCAPED' / 'pwn.html'
        env = mfa.PREV / '.env'
        import shutil

        shutil.rmtree(REPO / 'preview_ESCAPED', ignore_errors=True)
        env.unlink(missing_ok=True)

        result = self._run(monkeypatch)
        written = [w['path'] for w in result.get('files_written', [])]

        assert 'index.html' in written, 'the legitimate file must still be written'
        assert not escaped.exists(), 'a model-chosen path escaped the workspace'
        assert not env.exists(), '.env must never be written by generated code'

    def test_refusals_are_reported_not_silently_skipped(self, monkeypatch):
        """A bare `continue` left a 'done' run with a missing file and no reason."""
        result = self._run(monkeypatch)
        errors = [e for e in result.get('events', []) if e.get('type') == 'file_error']
        assert len(errors) == 2
        assert all('refused' in e['error'] for e in errors)


# ── 3. Branch deletion ─────────────────────────────────────────────────────────


class TestBranchDeletionIsNotDestructive:
    @pytest.mark.parametrize('name', ['..', '...', '////', '-', '', '@@@'])
    def test_names_that_reduce_to_nothing_are_rejected(self, name):
        assert mfa.normalize_branch(name) == ''

    @pytest.mark.parametrize('name', ['feature-x', 'v1_2', 'preview-1700000000'])
    def test_legitimate_names_survive(self, name):
        assert mfa.normalize_branch(name) == name

    def test_deleting_a_reduced_name_cannot_wipe_every_branch(self, client):
        """Verified live before the fix: DELETE /branches/... removed both
        existing branches AND the branches directory itself."""
        client.post('/api/composer/preview/branch', json={'name': 'guard-a'})
        client.post('/api/composer/preview/branch', json={'name': 'guard-b'})
        try:
            for payload in ('...', '..', '%2e%2e'):
                r = client.delete(f'/api/composer/preview/branches/{payload}')
                assert r.status_code in (400, 404, 307), payload
            names = {
                b['name']
                for b in client.get('/api/composer/preview/branches').json()['branches']
            }
            assert {'guard-a', 'guard-b'} <= names, 'branches were destroyed'
        finally:
            client.delete('/api/composer/preview/branches/guard-a')
            client.delete('/api/composer/preview/branches/guard-b')

    def test_a_real_branch_can_still_be_deleted(self, client):
        client.post('/api/composer/preview/branch', json={'name': 'deleteme-x'})
        assert client.delete('/api/composer/preview/branches/deleteme-x').status_code == 200
        names = {
            b['name'] for b in client.get('/api/composer/preview/branches').json()['branches']
        }
        assert 'deleteme-x' not in names

    def test_deleting_a_missing_branch_is_404(self, client):
        assert client.delete('/api/composer/preview/branches/never-existed').status_code == 404

    def test_creating_with_an_unusable_name_is_400(self, client):
        assert client.post(
            '/api/composer/preview/branch', json={'name': '---'}
        ).status_code == 400


# ── 4. Status codes ────────────────────────────────────────────────────────────


class TestStatusCodes:
    def test_run_without_instruction_is_400(self, client):
        assert client.post('/api/composer/run', json={}).status_code == 400

    def test_screenshot_without_image_is_400(self, client):
        assert client.post('/api/composer/screenshot-to-code', json={}).status_code == 400


# ── 5. Frontend ────────────────────────────────────────────────────────────────


class TestFrontend:
    def test_file_error_is_rendered(self):
        """Without this a refused file sat on '⏳' with no explanation."""
        assert "ev.type === 'file_error'" in JS
        assert 'escHtml(ev.error' in JS

    def test_preview_url_is_not_injected_raw_into_an_href(self):
        import re

        code = re.sub(r'^\s*//.*$', '', JS, flags=re.MULTILINE)
        assert 'href="${j.preview_url}"' not in code
        assert 'safeUrl' in code

    def test_server_error_detail_is_surfaced(self):
        assert '(await r.json()).error' in JS
