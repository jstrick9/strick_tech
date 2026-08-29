"""A user pulled five times, got the same stale app five times, and was told
the build succeeded every time.

Their diagnostic, verbatim:

    HEAD:   5e0d178 fix(build): the build script was never executable in git...
    commits behind origin/main: 5
    uncommitted files: 48

Five fixes -- including the sidebar hover fix they had reported twice -- were
never on their machine. Every `./build_macos_desktop.sh --bundle-python` ended
with "Built Successfully".

THE DEADLOCK
------------
Commit 03ee7d7 fixed `gzip.compress(raw, 9)` embedding a build timestamp, which
made every build rewrite 40 tracked files under frontend/dist. But that fix is
INSIDE the range the user could not pull. So:

    1. build  -> rewrites frontend/dist (timestamp churn, payload identical)
    2. pull   -> "error: Your local changes to the following files would be
                  overwritten by merge: frontend/dist/..."  -> ABORTS
    3. build  -> succeeds, using the old code, prints success
    4. goto 1

The fix for the churn was unreachable because the churn blocked the pull. The
user did nothing wrong and had no signal: the pull error scrolls past above a
long successful-looking build.

Reproduced end to end in a worktree pinned to the user's exact commit:

    dirty after a plain build on 5e0d178: 81 files
    payload identical, gzip header timestamp only
    git merge origin/main ->
        error: Your local changes to the following files would be
        overwritten by merge: frontend/dist/app.8bfba1038992.js.gz ...

THE FIX
-------
Gate 0 in build_macos_desktop.sh, before any compilation: fetch, compare to
origin, and if behind, print how many commits, list them, and -- when
frontend/dist is what is blocking the merge -- print the exact recovery
command. Interactively it requires confirmation before building something
knowingly stale; non-interactively it warns and proceeds so CI is not wedged.

It warns rather than refuses because being behind can be legitimate (offline,
a deliberate pin). What is never acceptable is being behind SILENTLY.
"""

from __future__ import annotations

import subprocess
from pathlib import Path

REPO = Path(__file__).resolve().parents[2]
SCRIPT = REPO / "build_macos_desktop.sh"


def _text() -> str:
    return SCRIPT.read_text(encoding="utf-8")


def _gate() -> str:
    """The gate block only.

    Slicing to the literal "Rebuilding the frontend bundle" cut through the
    MIDDLE of the following `echo "..."` line, leaving a dangling double quote.
    bash then reported `unexpected EOF while looking for matching quote` and
    both execution tests failed for a defect in this slice rather than in the
    gate -- whose output was already correct in the failure message. Cut at the
    start of that echo's line instead.
    """
    t = _text()
    i = t.index("# \u2500\u2500 Gate 0")
    j = t.index("Rebuilding the frontend bundle", i)
    j = t.rindex("\n", i, j) + 1
    return t[i:j]


def test_the_gate_runs_before_anything_is_compiled() -> None:
    """A warning after a two-minute cargo build is a warning nobody reads."""
    t = _text()
    assert t.index("# \u2500\u2500 Gate 0") < t.index("cargo tauri build"), (
        "the behind-origin check must precede the build, not follow it"
    )


def test_the_gate_actually_consults_the_remote() -> None:
    g = _gate()
    assert "git fetch" in g, "cannot know it is behind without fetching"
    assert "rev-list --count" in g, "must count commits behind origin"


def test_being_behind_is_reported_with_the_count_and_the_commits() -> None:
    g = _gate()
    assert "BEHIND" in g.upper()
    assert "log --oneline" in g, (
        "list the missing commits -- 'you are behind' alone does not tell the "
        "user that the fix they are waiting for is in that list"
    )


def test_the_dist_deadlock_gets_its_own_recovery_instruction() -> None:
    """The generic advice ('git pull') is exactly what was already failing."""
    g = _gate()
    assert "frontend/dist" in g
    assert "git checkout -- frontend/dist" in g, (
        "must print the command that actually unblocks the pull"
    )


def test_a_stale_build_requires_confirmation_when_interactive() -> None:
    g = _gate()
    assert "read -r" in g, "interactive runs must stop and ask"
    assert "exit 97" in g, "declining must abort the build"


def test_non_interactive_runs_are_not_wedged() -> None:
    """CI has no tty; blocking forever on `read` would be worse than stale."""
    g = _gate()
    assert "[ -t 0 ]" in g, "must detect whether stdin is a terminal"
    assert "non-interactive" in g


def _run_gate(tmp_path: Path, behind: int, dirty_dist: int) -> subprocess.CompletedProcess:
    """Execute the real gate against a fake git."""
    bindir = tmp_path / "bin"
    bindir.mkdir()
    porcelain = "\n".join(
        f" M frontend/dist/pane-{i}.js.gz" for i in range(dirty_dist)
    )
    log = "\n".join(f"abc{i:03d} fix: something important {i}" for i in range(behind))
    (bindir / "git").write_text(
        "#!/usr/bin/env bash\n"
        'case "$*" in\n'
        '  *"rev-parse --abbrev-ref"*) echo main ;;\n'
        '  *fetch*) exit 0 ;;\n'
        f'  *"rev-list --count"*) echo {behind} ;;\n'
        f'  *"status --porcelain"*) printf %s "{porcelain}" ;;\n'
        f'  *"log --oneline"*) printf "%s\\n" "{log}" ;;\n'
        "  *) exit 0 ;;\n"
        "esac\n",
        encoding="utf-8",
    )
    (bindir / "git").chmod(0o755)

    # Write the harness to a FILE rather than passing it to `bash -c`.
    # The gate contains an unbalanced `"` inside a case pattern, which is
    # perfectly valid in a script but makes `bash -c` report
    # "unexpected EOF while looking for matching quote" -- so both execution
    # tests failed for a harness defect, not a gate defect. The gate's own
    # output was already correct in the failure message.
    (tmp_path / ".git").mkdir(exist_ok=True)
    harness_file = tmp_path / "harness.sh"
    harness_file.write_text(
        f'REPO_ROOT="{tmp_path}"\n{_gate()}\necho REACHED_BUILD\n', encoding="utf-8"
    )
    return subprocess.run(
        ["bash", str(harness_file)],
        cwd=tmp_path,
        capture_output=True,
        text=True,
        timeout=60,
        env={"PATH": f"{bindir}:/usr/bin:/bin", "HOME": str(tmp_path)},
        stdin=subprocess.DEVNULL,
    )


def test_up_to_date_build_says_nothing_and_proceeds(tmp_path: Path) -> None:
    """No nagging on the normal path."""
    p = _run_gate(tmp_path, behind=0, dirty_dist=0)
    assert "REACHED_BUILD" in p.stdout
    assert "BEHIND" not in p.stdout.upper(), f"warned on an up-to-date repo:\n{p.stdout}"


def test_the_users_exact_situation_is_reported(tmp_path: Path) -> None:
    """5 commits behind, frontend/dist dirty -- their diagnostic, exactly."""
    p = _run_gate(tmp_path, behind=5, dirty_dist=40)
    assert "5 COMMIT(S) BEHIND" in p.stdout, p.stdout
    assert "git checkout -- frontend/dist" in p.stdout, (
        "did not print the command that unblocks the pull:\n" + p.stdout
    )
    assert "important 0" in p.stdout, "did not list the missing commits"
    # non-interactive: must not hang, must still build
    assert "REACHED_BUILD" in p.stdout


def test_script_is_syntactically_valid() -> None:
    p = subprocess.run(["bash", "-n", str(SCRIPT)], capture_output=True, text=True)
    assert p.returncode == 0, p.stderr
