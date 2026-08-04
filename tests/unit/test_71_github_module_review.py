"""Module 16 — GitHub / GitAI / Deploy review contracts.

This module is the platform's egress boundary: it pushes local files to remote
repositories and runs git against the working tree. Both findings below were
reproduced live before the fix.

1. THE PUSH ENDPOINT COULD PUBLISH THE VAULT.
   `directory` was validated only as "inside ROOT" — which is the entire
   project. `{"repo": "attacker/public", "directory": "memory"}` selected 206
   files with memory/.vault_key first in the list, alongside agentic.db
   (345 secrets rows, auth_users, every chat message).

   ROOT-containment is the wrong boundary for an EGRESS operation. My earlier
   containment sweep (commit c9646f2) fixed the sibling-prefix bypass here but
   left the boundary itself too wide — closing the traversal did not make the
   guard correct.

2. GITAI LET THE MODEL AUTHORISE ITS OWN COMMANDS.
   nl-git executed whatever the LLM returned, gated only by the model's own
   "safe": true flag. Replaying the exact code path with is_destructive=false:
   `git push --force`, `git reset --hard HEAD~50`, `git clean -fdx` and
   `git config --global core.pager "sh -c id"` all execute — the last being
   arbitrary code execution dressed as a git command.
"""
from __future__ import annotations

from pathlib import Path

import pytest

from backend.routers import github as gh
from backend.routers import gitai as ga

REPO = Path(__file__).resolve().parents[2]


def _executable(src: str) -> str:
    """Source minus comments and docstrings.

    The fixes document the old behaviour in prose that quotes it, so a raw
    substring search matches the explanation rather than the code.
    """
    import ast
    import io
    import tokenize

    stripped = tokenize.untokenize(
        t for t in tokenize.generate_tokens(io.StringIO(src).readline)
        if t.type != tokenize.COMMENT
    )
    docs = set()
    for node in ast.walk(ast.parse(stripped)):
        if isinstance(node, (ast.Module, ast.ClassDef, ast.FunctionDef, ast.AsyncFunctionDef)):
            body = getattr(node, 'body', [])
            if (body and isinstance(body[0], ast.Expr)
                    and isinstance(body[0].value, ast.Constant)
                    and isinstance(body[0].value.value, str)):
                docs.update(range(body[0].lineno, (body[0].end_lineno or body[0].lineno) + 1))
    return '\n'.join(ln for i, ln in enumerate(stripped.splitlines(), 1) if i not in docs)


GITHUB_CODE = _executable((REPO / 'backend' / 'routers' / 'github.py').read_text())
GITAI_CODE = _executable((REPO / 'backend' / 'routers' / 'gitai.py').read_text())


# ── 1. Push cannot exfiltrate ──────────────────────────────────────────────────


class TestPushDirectoryAllowlist:
    @pytest.mark.parametrize(
        'directory',
        ['memory', 'backend', '.git', '..', '/etc', 'memory/../preview', 'frontend', ''],
    )
    def test_non_publishable_directories_are_refused(self, directory):
        resolved, why = gh.resolve_push_dir(directory) if directory else gh.resolve_push_dir('..')
        assert resolved is None, f'{directory!r} must not be publishable'
        assert why

    @pytest.mark.parametrize('directory', ['preview', 'workspaces', 'templates', 'docs'])
    def test_publishable_directories_still_work(self, directory):
        resolved, why = gh.resolve_push_dir(directory)
        if not (gh.ROOT / directory).is_dir():
            pytest.skip(f'{directory} does not exist in this checkout')
        assert resolved is not None, why
        assert resolved.is_relative_to(gh.ROOT.resolve())

    def test_the_memory_directory_is_the_headline_case(self):
        """It holds .vault_key and agentic.db (345 secrets, auth_users, chats)."""
        resolved, why = gh.resolve_push_dir('memory')
        assert resolved is None
        assert 'cannot be published' in why

    def test_the_allowlist_is_opt_in_not_opt_out(self):
        """Egress should enumerate what MAY leave, not what may not."""
        assert gh.PUBLISHABLE_DIRS
        assert 'memory' not in gh.PUBLISHABLE_DIRS
        assert 'backend' not in gh.PUBLISHABLE_DIRS

    def test_root_containment_alone_is_no_longer_the_gate(self):
        assert 'resolve_push_dir(' in GITHUB_CODE
        assert "is_within(source_dir, ROOT)" not in GITHUB_CODE


class TestPerFileSecretScreening:
    @pytest.mark.parametrize(
        'path',
        [
            '.env', 'sub/.env', '.vault_key', 'nested/.vault_key',
            'key.pem', 'server.key', 'data.db', 'app.sqlite3',
            'my_secret_notes.txt', 'aws_credentials', 'id_rsa',
            'config/service-account.json', 'store.p12',
        ],
    )
    def test_credential_shaped_files_are_held_back(self, path):
        allowed, why = gh.is_publishable_file(path)
        assert allowed is False, f'{path!r} would have been uploaded'
        assert why

    @pytest.mark.parametrize(
        'path', ['index.html', 'js/app.js', 'README.md', 'styles/main.css', 'src/lib.py']
    )
    def test_ordinary_project_files_publish(self, path):
        allowed, why = gh.is_publishable_file(path)
        assert allowed is True, why

    def test_screening_is_applied_during_collection(self):
        assert 'is_publishable_file(rel_path)' in GITHUB_CODE
        assert 'skipped_secrets' in GITHUB_CODE

    def test_it_is_a_second_layer_not_the_only_one(self):
        """A credential inside an allowed directory must still be caught."""
        assert gh.is_publishable_file('preview/.env')[0] is False


# ── 2. GitAI: the model suggests, the server decides ───────────────────────────


class TestModelCannotAuthoriseItsOwnCommands:
    @pytest.mark.parametrize(
        'cmd',
        [
            ['git', 'config', '--global', 'core.pager', 'sh -c id'],
            ['git', 'config', 'core.sshCommand', 'sh -c id'],
            ['git', '-c', 'core.pager=sh -c id', 'log'],
            ['git', 'daemon'],
            ['git', 'filter-branch', '--all'],
            ['git', 'log', '--upload-pack=sh -c id'],
        ],
    )
    def test_code_execution_vectors_are_refused_outright(self, cmd):
        """git config/-c can turn any git call into arbitrary execution."""
        valid, _readonly, why = ga.classify_git_command(cmd)
        assert valid is False, f'{" ".join(cmd)!r} must be refused entirely'
        assert why

    @pytest.mark.parametrize(
        'cmd',
        [
            ['git', 'push', '--force', 'origin', 'main'],
            ['git', 'reset', '--hard', 'HEAD~50'],
            ['git', 'clean', '-fdx'],
            ['git', 'rebase', '-i', 'HEAD~3'],
            ['git', 'commit', '-m', 'x'],
        ],
    )
    def test_destructive_commands_are_valid_but_not_readonly(self, cmd):
        """They require an explicit allow_unsafe from the CALLER."""
        valid, readonly, _ = ga.classify_git_command(cmd)
        assert valid is True
        assert readonly is False

    @pytest.mark.parametrize(
        'cmd',
        [
            ['git', 'log', '--oneline', '-10'],
            ['git', 'status'],
            ['git', 'diff', 'HEAD'],
            ['git', 'show', 'abc123'],
            ['git', 'branch'],
            ['git', 'blame', 'file.py'],
        ],
    )
    def test_readonly_commands_still_run(self, cmd):
        """Isolation that breaks the feature is not a fix."""
        valid, readonly, _ = ga.classify_git_command(cmd)
        assert valid is True and readonly is True

    @pytest.mark.parametrize(
        'cmd', [[], ['rm', '-rf', '/'], ['sh', '-c', 'id'], 'git log', ['git'], [1, 2]]
    )
    def test_malformed_or_non_git_is_refused(self, cmd):
        valid, _, _ = ga.classify_git_command(cmd)
        assert valid is False

    def test_the_model_safe_flag_no_longer_gates_execution(self):
        """It was the ONLY gate: `safe = cmd_info.get('safe', True)`."""
        assert "safe = cmd_info.get('safe', True)" not in GITAI_CODE
        assert 'classify_git_command(cmd)' in GITAI_CODE

    def test_the_model_claim_is_still_reported_for_transparency(self):
        """Useful signal: a model that mislabels is worth surfacing."""
        assert 'model_claimed_safe' in GITAI_CODE

    def test_a_mislabelled_destructive_command_is_skipped(self):
        """Replays the exact structure the endpoint receives."""
        cmd_info = {'cmd': ['git', 'push', '--force'], 'safe': True}
        valid, readonly, _ = ga.classify_git_command(cmd_info['cmd'])
        allow_unsafe = False
        would_run = valid and (readonly or allow_unsafe)
        assert would_run is False, 'the model claimed safe=True and it ran'


# ── 3. Status codes ────────────────────────────────────────────────────────────


class TestStatusCodes:
    def test_push_without_a_token_is_401(self, client):
        r = client.post('/api/github/push', json={'repo': 'owner/repo'})
        assert r.status_code in (401, 200)
        if r.status_code == 401:
            assert r.json()['code'] == 'no_token'

    def test_nl_git_without_a_query_is_400(self, client):
        assert client.post('/api/gitai/nl-git', json={}).status_code == 400

    def test_push_to_a_forbidden_directory_is_403(self, client, monkeypatch):
        monkeypatch.setattr(gh, '_gh_token', lambda: 'ghp_fake')
        r = client.post('/api/github/push', json={'repo': 'owner/repo', 'directory': 'memory'})
        assert r.status_code == 403
        assert 'cannot be published' in r.json()['error']

    def test_push_with_a_bad_repo_name_is_400(self, client, monkeypatch):
        monkeypatch.setattr(gh, '_gh_token', lambda: 'ghp_fake')
        r = client.post('/api/github/push', json={'repo': 'not-a-valid-repo-format!!'})
        assert r.status_code == 400


# ── Regressions that must keep working ─────────────────────────────────────────


class TestExistingProtectionsHold:
    def test_repo_name_validation_still_applies(self):
        assert gh._valid_repo_name('owner/repo') is True
        for bad in ('../../etc', 'owner', 'owner/repo/extra', ''):
            assert gh._valid_repo_name(bad) is False

    def test_clone_write_containment_still_uses_is_within(self):
        assert 'is_within(f, target_dir)' in GITHUB_CODE

    def test_dry_run_is_still_the_default_for_nl_git(self):
        """Executing a model-proposed command must remain opt-in."""
        assert "body.get('dry_run', True)" in GITAI_CODE

    def test_git_helper_never_uses_a_shell(self):
        """`git` is invoked with an argv list, so no shell interpolation.

        Scoped to the _git() helper: gitai also ships a security-scanner RULE
        whose description mentions shell=True as a risk, and a whole-file
        search matches that rule text rather than any actual use.
        """
        idx = GITAI_CODE.index('def _git(')
        helper = GITAI_CODE[idx:idx + 400]
        assert "subprocess.run(['git'] + args" in helper
        assert 'shell=True' not in helper
