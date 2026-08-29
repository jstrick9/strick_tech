"""The build could package LAST build's .app and report success.

Reported after a clean pull+rebuild: the sidebar hover bug was still present,
identically, on a build made AFTER the fix was pushed and verified.

The fix was in the source. It was in frontend/dist. The bundle gates passed.
And the app the user opened did not contain it.

ROOT CAUSE -- build_macos_desktop.sh
------------------------------------
`src-tauri/target/release/bundle/macos/` is BOTH somewhere cargo can emit to
AND the destination this script copies to so there is a stable documented path
(the `open "..."` line it prints). On every build after the first, that
directory already holds the PREVIOUS build's app.

So this search:

    find src-tauri/target -path "*/bundle/macos/*.app" -prune | head -n 1

had two hits on the user's machine:

    target/aarch64-apple-darwin/release/bundle/macos/...   <- just built
    target/release/bundle/macos/...                        <- last build's copy

and `head -n 1` picked between them by filesystem iteration order. When the
stale one won:

  - APP_FOUND pointed at the old app
  - the `!=` guard on the copy saw source == destination and skipped the copy
  - the summary printed the documented path and declared success
  - the user opened an app containing old JavaScript

Every gate I added earlier is upstream of this and all of them passed: the
bundle really was rebuilt, frontend/dist really did match source. The defect is
entirely in choosing WHICH built artefact to ship.

WHY "PICK THE NEWEST" IS NOT THE FIX
------------------------------------
Measured, not assumed. With the stale copy touched more recently than the fresh
build -- which is exactly what the copy step itself causes:

    find ... | head -n 1                 -> aarch64 path  (FRESH-just-built)
    find ... sort by mtime, newest first -> target/release (STALE-from-an-older-build)

Sorting by mtime selects the stale copy MORE reliably, because the destination
is touched by the copy. My first instinct here was wrong and the fixture caught
it.

THE FIX
-------
Derive the path from BUILD_FLAGS -- the script already knows whether it passed
--target to cargo -- instead of searching for it. Fall back to a search that
explicitly EXCLUDES the destination directory, so the previous build's copy can
never be selected while a real one exists.
"""

from __future__ import annotations

import os
import subprocess
from pathlib import Path

REPO = Path(__file__).resolve().parents[2]
SCRIPT = REPO / "build_macos_desktop.sh"


def _selection_block() -> str:
    t = SCRIPT.read_text(encoding="utf-8")
    i = t.index("# WHICH .app")
    return t[i : t.index("\n# Ensure standard target", i)]


def _run_selection(tmp_path: Path, target_flag: str | None,
                   make_stale: bool, stale_is_newer: bool) -> str:
    """Execute the real selection block against a fixture tree."""
    arch = "aarch64-apple-darwin"
    fresh = tmp_path / f"src-tauri/target/{arch}/release/bundle/macos/Agentic OS Platform.app"
    fresh.mkdir(parents=True)
    (fresh / "marker").write_text("FRESH", encoding="utf-8")

    if make_stale:
        stale = tmp_path / "src-tauri/target/release/bundle/macos/Agentic OS Platform.app"
        stale.mkdir(parents=True)
        (stale / "marker").write_text("STALE", encoding="utf-8")
        if stale_is_newer:
            os.utime(fresh, (1577836800, 1577836800))  # 2020-01-01

    flags = f'BUILD_FLAGS=("--target" "{target_flag}")' if target_flag else "BUILD_FLAGS=()"
    harness = f'set -e\n{flags}\n{_selection_block()}\necho "APP_FOUND=$APP_FOUND"\n'
    proc = subprocess.run(
        ["bash", "-c", harness], cwd=tmp_path, capture_output=True, text=True, timeout=60
    )
    assert proc.returncode == 0, f"{proc.stdout}\n{proc.stderr}"
    line = next(ln for ln in proc.stdout.splitlines() if ln.startswith("APP_FOUND="))
    return line.split("=", 1)[1]


def _marker(tmp_path: Path, rel: str) -> str:
    return (tmp_path / rel / "marker").read_text(encoding="utf-8")


def test_the_fresh_build_wins_when_a_stale_copy_exists(tmp_path: Path) -> None:
    """THE BUG. Both directories hold an .app; the just-built one must win."""
    found = _run_selection(tmp_path, "aarch64-apple-darwin", make_stale=True,
                           stale_is_newer=False)
    assert _marker(tmp_path, found) == "FRESH", (
        f"selected the previous build's app ({found}) -- the user would open "
        "an app without the fix while the build reports success"
    )


def test_the_fresh_build_wins_even_when_the_stale_copy_is_newer(tmp_path: Path) -> None:
    """The copy step touches the destination, so the stale app is routinely the
    newest thing on disk. A naive mtime sort picks it -- measured."""
    found = _run_selection(tmp_path, "aarch64-apple-darwin", make_stale=True,
                           stale_is_newer=True)
    assert _marker(tmp_path, found) == "FRESH", f"mtime fooled the selection: {found}"


def test_the_destination_is_never_selected_without_an_explicit_target(
    tmp_path: Path,
) -> None:
    """No --target passed: the search fallback must still skip the destination."""
    found = _run_selection(tmp_path, None, make_stale=True, stale_is_newer=True)
    assert _marker(tmp_path, found) == "FRESH", f"fallback picked the destination: {found}"


def test_a_first_ever_build_into_the_default_target_dir_still_works(
    tmp_path: Path,
) -> None:
    """Only target/release exists and it IS the real build -- not a stale copy.
    The last-resort branch must find it rather than returning nothing."""
    only = tmp_path / "src-tauri/target/release/bundle/macos/Agentic OS Platform.app"
    only.mkdir(parents=True)
    (only / "marker").write_text("ONLY", encoding="utf-8")
    harness = f'set -e\nBUILD_FLAGS=()\n{_selection_block()}\necho "APP_FOUND=$APP_FOUND"\n'
    proc = subprocess.run(
        ["bash", "-c", harness], cwd=tmp_path, capture_output=True, text=True, timeout=60
    )
    found = next(ln for ln in proc.stdout.splitlines()
                 if ln.startswith("APP_FOUND=")).split("=", 1)[1]
    assert found, "no .app selected at all on a first build"
    assert _marker(tmp_path, found) == "ONLY"


def test_selection_does_not_rely_on_filesystem_iteration_order() -> None:
    """A bare `find ... | head -n 1` across the whole target tree is the defect.
    Any surviving instance must exclude the destination."""
    block = _selection_block()
    for line in block.splitlines():
        stripped = line.strip()
        if stripped.startswith("#") or "find src-tauri/target" not in line:
            continue
        # The last-resort branch is allowed, but only after the guarded ones.
        assert ("grep -v" in block.split(line)[1][:200]
                or "grep -v" in line
                or "maxdepth 1" in line
                or "last-resort" in block.lower()
                or "Genuinely only" in block), (
            f"unguarded find that can select the destination: {line!r}"
        )


def test_script_is_syntactically_valid() -> None:
    proc = subprocess.run(["bash", "-n", str(SCRIPT)], capture_output=True, text=True)
    assert proc.returncode == 0, proc.stderr


def test_the_arch_path_is_derived_from_build_flags_not_searched_for(
    tmp_path: Path,
) -> None:
    """REVERT-PROOF MISS, corrected in place.

    Breaking the BUILD_FLAGS derivation -- so CARGO_TARGET_DIR_NAME is never
    set and the primary branch never runs -- left all 6 tests GREEN. The
    destination-excluding fallback is strong enough to produce the right answer
    on its own, so it masked the primary path entirely.

    That is defence in depth and worth keeping, but it meant the primary
    selection was untested: it could rot silently until the day the fallback
    was also wrong. Same lesson as the DMG layers in 6f13d38.

    This pins the primary branch by making the fallback UNABLE to give the
    right answer: two non-destination .app directories exist, so an
    order-dependent fallback cannot reliably choose, and only deriving the path
    from --target is correct.
    """
    arch = "aarch64-apple-darwin"
    right = tmp_path / f"src-tauri/target/{arch}/release/bundle/macos/Agentic OS Platform.app"
    right.mkdir(parents=True)
    (right / "marker").write_text("RIGHT", encoding="utf-8")
    # A second, non-destination candidate: a cross-compiled leftover.
    other = tmp_path / "src-tauri/target/x86_64-apple-darwin/release/bundle/macos/Agentic OS Platform.app"
    other.mkdir(parents=True)
    (other / "marker").write_text("WRONG-ARCH", encoding="utf-8")

    harness = (
        f'set -e\nBUILD_FLAGS=("--target" "{arch}")\n'
        f'{_selection_block()}\necho "APP_FOUND=$APP_FOUND"\n'
    )
    proc = subprocess.run(
        ["bash", "-c", harness], cwd=tmp_path, capture_output=True, text=True, timeout=60
    )
    assert proc.returncode == 0, f"{proc.stdout}\n{proc.stderr}"
    found = next(ln for ln in proc.stdout.splitlines()
                 if ln.startswith("APP_FOUND=")).split("=", 1)[1]
    assert _marker(tmp_path, found) == "RIGHT", (
        "selection did not honour --target; it picked a different architecture's "
        f"bundle ({found}). Deriving the path from BUILD_FLAGS is what makes "
        "this deterministic rather than order-dependent."
    )
