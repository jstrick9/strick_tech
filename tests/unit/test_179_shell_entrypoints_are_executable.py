"""Shell entrypoints must be executable IN GIT, not just on one laptop.

Reported, verbatim, from a clean checkout on macOS:

    git checkout -- build_macos_desktop.sh
    ./build_macos_desktop.sh --bundle-python
    zsh: permission denied: ./build_macos_desktop.sh

build_macos_desktop.sh was recorded in the tree as mode 100644. The user had
run `chmod +x` on an earlier attempt, but a chmod is a working-tree change that
git only tracks as the executable BIT of the tracked mode -- and `git checkout
--` restores the tracked mode, which was 644. So the documented invocation
worked once, then silently stopped working the moment the file was restored or
freshly cloned.

This is the "capability present but never triggered" defect class from
docs/BUG-SWEEP-PLAN.md, in its file-permission form: the script is correct and
complete, and cannot be run the way its own instructions say to run it.

The sweep found the same 644 on every tracked shell script in the repository,
not just the one that was reported:

    build_macos_desktop.sh
    start.sh
    scripts/tauri-dev.sh
    scripts/tauri-build.sh
    scripts/run_product_validation.sh

All five are now 100755. This test asserts the property for any shell script
added later, so the next one is caught here rather than by a user.

Note it reads the INDEX (`git ls-files -s`), not the filesystem. Checking
os.access(X_OK) would pass on a machine where someone had chmod'd locally --
exactly the false green that let this ship.
"""

from __future__ import annotations

import subprocess
from pathlib import Path

REPO = Path(__file__).resolve().parents[2]

# Executable-bit semantics are a POSIX concept. On a Windows checkout the mode
# is whatever core.fileMode says; the assertion is still meaningful because it
# reads the index, which is platform-independent.
EXPECTED_MODE = "100755"


def _index_entries() -> list[tuple[str, str]]:
    """[(mode, path)] for every tracked file."""
    out = subprocess.run(
        ["git", "ls-files", "-s"],
        cwd=REPO,
        capture_output=True,
        text=True,
        check=True,
    ).stdout
    entries = []
    for line in out.splitlines():
        if not line.strip():
            continue
        meta, path = line.split("\t", 1)
        mode = meta.split()[0]
        entries.append((mode, path))
    return entries


def _tracked_shell_scripts() -> list[str]:
    return sorted(p for _, p in _index_entries() if p.endswith(".sh"))


def _mode_of(path: str) -> str:
    return next(m for m, p in _index_entries() if p == path)


def test_the_reported_script_is_executable_in_the_index() -> None:
    """The exact file from the bug report."""
    mode = _mode_of("build_macos_desktop.sh")
    assert mode == EXPECTED_MODE, (
        f"build_macos_desktop.sh is mode {mode} in git. A fresh clone or a "
        "`git checkout --` will produce 'permission denied: "
        "./build_macos_desktop.sh', which is what the user hit."
    )


def test_every_tracked_shell_script_is_executable_in_the_index() -> None:
    """The class, not just the instance."""
    scripts = _tracked_shell_scripts()
    assert scripts, "no tracked .sh files found -- has the glob or cwd changed?"
    bad = [p for p in scripts if _mode_of(p) != EXPECTED_MODE]
    assert not bad, (
        "these tracked shell scripts are not executable in git, so `./script.sh` "
        f"fails on a fresh clone: {bad}\n"
        "Fix with: git update-index --chmod=+x " + " ".join(bad)
    )


def test_a_shell_script_with_a_shebang_is_meant_to_be_invoked_directly() -> None:
    """A shebang is a declaration of intent: this file is run, not sourced.
    Any tracked file carrying one should be executable."""
    offenders = []
    for mode, path in _index_entries():
        full = REPO / path
        if not full.is_file():
            continue
        if not path.endswith(".sh"):
            continue
        try:
            first = full.read_text(encoding="utf-8", errors="ignore").split("\n", 1)[0]
        except OSError:
            continue
        if first.startswith("#!") and mode != EXPECTED_MODE:
            offenders.append((path, mode, first))
    assert not offenders, f"shebang present but not executable in git: {offenders}"


def test_the_build_script_can_actually_be_executed_from_a_clean_worktree(
    tmp_path: Path,
) -> None:
    """The strongest form: materialise HEAD into a fresh worktree -- which is
    what a user's clone or `git checkout --` gives them -- and invoke the
    script the way the instructions say to. Pre-fix this raises PermissionError.

    Invoked with --help so it exits immediately instead of starting a real
    build. (The script had no --help until this change; a flag that lets you
    ask an entrypoint what it does, without it doing anything, is worth having
    on its own merits and is what makes this test cheap.)

    We only need to prove the kernel will exec it, so the run is allowed to
    fail for any *later* reason; the assertion is specifically that it is not
    rejected for permissions.
    """
    dest = tmp_path / "clean"
    subprocess.run(
        ["git", "worktree", "add", "--detach", "-f", str(dest), "HEAD"],
        cwd=REPO,
        capture_output=True,
        text=True,
        check=True,
    )
    try:
        script = dest / "build_macos_desktop.sh"
        assert script.exists()
        try:
            proc = subprocess.run(
                ["./build_macos_desktop.sh", "--help"],
                cwd=dest,
                capture_output=True,
                text=True,
                timeout=120,
            )
        except PermissionError as exc:  # pragma: no cover - the pre-fix path
            raise AssertionError(
                "the kernel refused to execute ./build_macos_desktop.sh from a "
                f"clean worktree: {exc}"
            ) from exc
        assert proc.returncode != 126, (
            "exit 126 means 'command found but not executable' -- the shell "
            f"could not run the script.\nstderr:\n{proc.stderr}"
        )
        assert "permission denied" not in (proc.stderr + proc.stdout).lower(), (
            f"stdout:\n{proc.stdout[-2000:]}\nstderr:\n{proc.stderr[-2000:]}"
        )
        assert proc.returncode == 0, (
            f"--help should exit 0, got {proc.returncode}\n{proc.stderr[-2000:]}"
        )
        assert "--bundle-python" in proc.stdout, (
            "--help must document the flag the build instructions tell users to "
            f"pass.\nstdout:\n{proc.stdout}"
        )
    finally:
        subprocess.run(
            ["git", "worktree", "remove", "--force", str(dest)],
            cwd=REPO,
            capture_output=True,
            text=True,
        )
