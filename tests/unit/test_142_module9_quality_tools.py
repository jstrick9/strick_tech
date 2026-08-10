"""Module 9 regression tests — ambient (project health), bugbot, gitai.

Defects found by probing the running module:

1. gitai `_git()` discarded the return code, so "fatal: not a git repository"
   (rc 128) produced empty output that git_status() read as an empty-and-
   therefore-clean tree. The pane showed a green "Clean" badge for a directory
   not under version control.
2. `_git()` .strip()ed the whole stdout, eating the significant leading column
   of `git status --porcelain`: ' M a.py' became 'M a.py' and line[3:] sliced
   the filename to '.py'.
3. Untracked entries ('??') were reported as staged.
4. bugbot's streaming review used llm.stream(), which returns the no-provider
   help text as content rather than raising, so the global LLMUnavailableError
   handler never fired. A diff containing eval(user_input) was persisted as
   score 75 / severity low / 0 issues.
5. ambient's project-health security and debt dimensions scanned PREVIEW_DIR
   only -- one file on a normal install -- and reported a confident 100 while
   the Git AI scanner graded the same tree F.
6. The health SQL-injection rule used re.DOTALL with `.*`, so it matched a
   benign f-string against the word SELECT hundreds of lines later. It flagged
   89 of 120 backend files.
"""

from __future__ import annotations

import subprocess

import pytest

from backend.routers import ambient, gitai


# ── 1. a failed git call is not a clean repo ──────────────────────────────────
def test_repo_error_detects_missing_repository():
    err = gitai._repo_error('fatal: not a git repository (or any of the parent directories)', 128)
    assert err is not None
    assert err['code'] == 'not_a_repo'
    assert err['hint']


def test_repo_error_returns_none_on_success():
    assert gitai._repo_error('', 0) is None


def test_repo_error_passes_through_other_failures():
    err = gitai._repo_error('fatal: bad revision', 1)
    assert err is not None
    assert err['code'] == 'git_error'


def test_status_in_non_repo_is_not_reported_clean(tmp_path, monkeypatch):
    """The exact defect: an empty result must not render as a clean tree."""
    monkeypatch.setattr(gitai, 'ROOT', tmp_path)
    out = gitai.git_status()
    assert out['ok'] is False
    assert out['repo'] is False
    # `clean` must NOT be True — that is what drew the green badge.
    assert out['clean'] is not True
    assert out['code'] == 'not_a_repo'


def test_log_in_non_repo_reports_the_reason(tmp_path, monkeypatch):
    monkeypatch.setattr(gitai, 'ROOT', tmp_path)
    out = gitai.git_log()
    assert out['ok'] is False and out['repo'] is False
    assert out['code'] == 'not_a_repo'


def test_diff_in_non_repo_reports_the_reason(tmp_path, monkeypatch):
    monkeypatch.setattr(gitai, 'ROOT', tmp_path)
    out = gitai.git_diff()
    assert out['ok'] is False and out['repo'] is False


# ── 2/3. porcelain parsing ────────────────────────────────────────────────────
@pytest.fixture
def real_repo(tmp_path):
    def run(*args):
        subprocess.run(
            ['git', *args], cwd=tmp_path, check=True,
            capture_output=True, text=True,
        )

    run('init', '-q', '.')
    run('config', 'user.email', 't@t.t')
    run('config', 'user.name', 't')
    (tmp_path / 'a.py').write_text('print(1)\n')
    run('add', '-A')
    run('commit', '-qm', 'first')
    return tmp_path


def test_filename_is_not_truncated(real_repo, monkeypatch):
    """' M a.py' must yield 'a.py', not '.py'.

    _git() stripped the whole stdout, removing porcelain's leading column, so
    the FIRST changed file lost its first character.
    """
    monkeypatch.setattr(gitai, 'ROOT', real_repo)
    (real_repo / 'a.py').write_text('print(1)\nprint(2)\n')
    out = gitai.git_status()
    assert out['repo'] is True
    paths = [f['path'] for f in out['changed_files']]
    assert 'a.py' in paths, paths
    assert '.py' not in paths, 'filename was truncated by the leading-space strip'


def test_untracked_file_is_not_marked_staged(real_repo, monkeypatch):
    monkeypatch.setattr(gitai, 'ROOT', real_repo)
    (real_repo / 'brand_new.py').write_text('x = 1\n')
    out = gitai.git_status()
    entry = next(f for f in out['changed_files'] if f['path'] == 'brand_new.py')
    assert entry['untracked'] is True
    assert entry['staged'] is False


def test_staged_and_unstaged_are_distinguished(real_repo, monkeypatch):
    monkeypatch.setattr(gitai, 'ROOT', real_repo)
    (real_repo / 'staged.py').write_text('x = 1\n')
    subprocess.run(['git', 'add', 'staged.py'], cwd=real_repo, check=True, capture_output=True)
    (real_repo / 'a.py').write_text('print(1)\nprint(99)\n')
    out = gitai.git_status()
    by_path = {f['path']: f for f in out['changed_files']}
    assert by_path['staged.py']['staged'] is True
    assert by_path['a.py']['staged'] is False


def test_clean_repo_reports_clean(real_repo, monkeypatch):
    monkeypatch.setattr(gitai, 'ROOT', real_repo)
    out = gitai.git_status()
    assert out['repo'] is True and out['clean'] is True
    assert out['changed_count'] == 0


def test_git_keeps_leading_whitespace_only_when_asked():
    out, _, _ = gitai._git(['--version'], keep_output=True)
    assert out
    stripped, _, _ = gitai._git(['--version'])
    assert stripped == stripped.strip()


# ── 4. bugbot must not fabricate a score ──────────────────────────────────────
def test_stream_review_refuses_when_provider_is_stubbed():
    """The stub reply must produce an error frame, not a stored score of 75."""
    import inspect

    from backend.routers import bugbot

    src = inspect.getsource(bugbot.review_diff_stream)
    src = '\n'.join(ln for ln in src.split('\n') if not ln.strip().startswith('#'))
    assert 'is_stub' in src, 'stub replies must be detected'
    assert 'stubbed' in src
    # It must bail out before the INSERT rather than storing a default score.
    assert src.index('stubbed or not parsed') < src.index('INSERT INTO bugbot_reviews')


def test_stream_review_error_frame_carries_setup_url():
    import inspect

    from backend.routers import bugbot

    src = inspect.getsource(bugbot.review_diff_stream)
    assert 'setup_url' in src
    assert "'type': 'error'" in src or '"type": "error"' in src


# ── 5. health must scan real source, not just the scratch dir ─────────────────
def test_health_scan_reaches_beyond_preview(tmp_path, monkeypatch):
    """PREVIEW_DIR alone holds one file; backend/ and workspaces/ must count."""
    (tmp_path / 'preview').mkdir()
    (tmp_path / 'preview' / 'index.html').write_text('<html></html>')
    (tmp_path / 'backend').mkdir()
    (tmp_path / 'backend' / 'thing.py').write_text('# TODO: fix\n')
    (tmp_path / 'workspaces').mkdir()
    (tmp_path / 'workspaces' / 'w.py').write_text('x = 1\n')

    monkeypatch.setattr(ambient, 'ROOT', tmp_path)
    monkeypatch.setattr(ambient, 'PREVIEW_DIR', tmp_path / 'preview')
    files = ambient._health_scan_files(exts=('.py',))
    names = {f.name for f in files}
    assert 'thing.py' in names
    assert 'w.py' in names


def test_health_scan_skips_vendor_directories(tmp_path, monkeypatch):
    (tmp_path / 'backend').mkdir()
    (tmp_path / 'backend' / 'node_modules').mkdir()
    (tmp_path / 'backend' / 'node_modules' / 'dep.js').write_text('x')
    (tmp_path / 'backend' / 'real.py').write_text('x = 1')
    monkeypatch.setattr(ambient, 'ROOT', tmp_path)
    monkeypatch.setattr(ambient, 'PREVIEW_DIR', tmp_path / 'nope')
    names = {f.name for f in ambient._health_scan_files()}
    assert 'real.py' in names
    assert 'dep.js' not in names


def test_health_scan_respects_cap(tmp_path, monkeypatch):
    (tmp_path / 'backend').mkdir()
    for i in range(60):
        (tmp_path / 'backend' / f'f{i}.py').write_text('x = 1')
    monkeypatch.setattr(ambient, 'ROOT', tmp_path)
    monkeypatch.setattr(ambient, 'PREVIEW_DIR', tmp_path / 'nope')
    assert len(ambient._health_scan_files(cap=25)) == 25


# ── 6. the SQL rule must not match across a whole file ────────────────────────
def _sql_rule():
    """The ACTUAL rule the health scan uses.

    An earlier version of this helper re-declared the regex, so all four SQL
    tests passed against the broken DOTALL implementation as well as the fixed
    one -- they were testing their own copy. Import the real object.
    """
    return ambient.SQL_INJECTION_PATTERN


def test_sql_rule_ignores_unrelated_fstring_and_distant_keyword():
    """The DOTALL version matched this; it is not an injection."""
    benign = 'name = f"hello {user}"\n' + '\n' * 40 + '# a comment about SELECT queries\n'
    assert not _sql_rule().search(benign)


def test_sql_rule_still_catches_real_injection():
    bad = 'cur.execute(f"SELECT * FROM users WHERE id={uid}")'
    assert _sql_rule().search(bad)


def test_sql_rule_ignores_parameterised_query():
    good = 'cur.execute("SELECT * FROM users WHERE id=?", (uid,))'
    assert not _sql_rule().search(good)


def test_sql_rule_does_not_span_newlines():
    spanning = 'x = f"{a}"\ncur.execute("SELECT 1")'
    assert not _sql_rule().search(spanning)


# ── health honesty ────────────────────────────────────────────────────────────
def test_health_tip_survives_unmeasured_dimensions():
    tip = ambient._health_tip({'security': None, 'debt': None, 'complexity': None,
                               'docs': None, 'deps': None})
    assert isinstance(tip, str) and tip


def test_health_tip_targets_the_weakest_measured_dimension():
    tip = ambient._health_tip({'security': 20, 'debt': 90, 'complexity': None,
                               'docs': None, 'deps': 100})
    assert 'security' in tip.lower() or 'secret' in tip.lower()


def test_health_module_has_no_dead_snapshot_literal():
    """A dict literal was built and discarded above the real INSERT."""
    import inspect

    src = inspect.getsource(ambient.project_health)
    # The discarded statement started a bare dict at 4-space indent.
    assert "\n    {\n        'overall_score': overall," not in src
