"""Gap #016: user-supplied git `branch` appended to a `git diff` argv.

A leading `-` is interpreted by git as an option, so
`branch="--no-index /etc/passwd /tmp/x"` (unstaged path) makes `git diff`
compare two arbitrary paths and embed their contents in the returned diff —
arbitrary file-content disclosure. Validate the branch as a git refname first
(like gitai.py's classify_git_command).
"""
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[2]))

from backend.routers import bugbot


class TestBugbotGitRefValidation:
    def test_leading_dash_flag_injection_rejected(self):
        for bad in ('--no-index /etc/passwd /tmp/x', '-c', '-', '--', '--ext-diff'):
            assert not bugbot._is_safe_branch(bad), f'{bad!r} accepted'

    def test_valid_refs_accepted(self):
        for good in ('main', 'feature/x', 'HEAD', 'v1.2.3', 'origin/main', 'release-1.0'):
            assert bugbot._is_safe_branch(good), f'{good!r} rejected'

    def test_ref_metacharacters_rejected(self):
        for bad in ('a b', 'abc..def', '..', 'x..', 'a@{b', 'a\\b', 'a~1', 'a^1', 'a:'):
            assert not bugbot._is_safe_branch(bad), f'{bad!r} accepted'

    def test_empty_is_rejected(self):
        assert not bugbot._is_safe_branch('')
        assert not bugbot._is_safe_branch('   ')
