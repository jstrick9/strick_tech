"""Two defects observed in a real macOS desktop build (v11.5.0, Apple Silicon).

Reported build log, verbatim:

    Bundling Agentic OS Platform.app  (... /aarch64-apple-darwin/release/bundle/macos/)
    Bundling Agentic OS Platform_11.5.0_aarch64.dmg
    Running bundle_dmg.sh
    Error failed to bundle project: error running bundle_dmg.sh
    /Library/.../python3: can't open file '.../scripts/diagnose_desktop.py':
        [Errno 2] No such file or directory

DEFECT A -- the frontend bundle gates never ran.
    build_macos_desktop.sh does `cd src-tauri` at line ~134. The three build
    gates added for the stale-JS bug were inserted AFTER that cd, so they
    referenced `scripts/build_bundle.py` and `frontend/index.html` relative to
    src-tauri/, where neither exists. The first gate is:

        if [ ! -f scripts/build_bundle.py ]; then ... exit 1

    ...so on a correct checkout the script would have aborted every build with
    "build_bundle.py is missing". It did not abort, which means the gates were
    reached only on a path where that was somehow true -- either way the gates
    were not doing their job. The fix anchors every gate to $REPO_ROOT.

DEFECT B -- a DMG failure threw away a good .app.
    `set -e` is active. bundle_dmg.sh failed (stale /Volumes mount, no GUI
    session, or a Finder/AppleScript timeout -- none of which say anything
    about the application). The script died on that line, so the copy step
    that places the bundle at the DOCUMENTED path,

        src-tauri/target/release/bundle/macos/Agentic OS Platform.app

    never ran. The user's `open "src-tauri/target/release/bundle/macos/..."`
    therefore had nothing to open, and the diagnostic they were asked to run
    was never fetched because the build aborted first. The .app HAD been built
    successfully at the aarch64 path. A DMG wrapper failing must not destroy a
    good app build.

Both tests execute the real text of the real script, not a paraphrase of it.
"""

from __future__ import annotations

import os
import re
import subprocess
from pathlib import Path

REPO = Path(__file__).resolve().parents[2]
SCRIPT = REPO / "build_macos_desktop.sh"


def _text() -> str:
    return SCRIPT.read_text(encoding="utf-8")


def _slice(start_marker: str, end_marker: str) -> str:
    t = _text()
    i = t.index(start_marker)
    j = t.index(end_marker, i)
    return t[i:j]


# --------------------------------------------------------------------------
# DEFECT A: the gates must resolve from the repo root, not from src-tauri/
# --------------------------------------------------------------------------


def test_gate_block_appears_after_the_cd_into_src_tauri() -> None:
    """Documents the trap. If someone moves the gates above `cd src-tauri`
    this test fails and the $REPO_ROOT anchoring can be simplified -- it is a
    prompt to revisit, not a requirement that the bug stay possible."""
    t = _text()
    assert t.index("\ncd src-tauri\n") < t.index("Rebuilding the frontend bundle"), (
        "The gates moved above `cd src-tauri`. Re-read this test file."
    )


def test_repo_root_is_defined_before_any_gate_uses_it() -> None:
    t = _text()
    assert 'REPO_ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"' in t, (
        "REPO_ROOT must be derived from the script's own location, not from $PWD."
    )
    assert t.index("REPO_ROOT=") < t.index("build_bundle.py")


def test_repo_root_is_resolved_before_the_first_cd() -> None:
    """The `dirname` of a relative invocation is "." -- which means whatever the
    CURRENT directory is at the moment it is evaluated. Resolving REPO_ROOT
    after `cd src-tauri` therefore yields src-tauri/, not the repo root.
    It must be resolved before ANY cd in the script."""
    t = _text()
    root_at = t.index('REPO_ROOT="$(cd "$(dirname')
    first_cd = min(
        (t.index(m) for m in ("\ncd src-tauri\n", "\ncd ..\n") if m in t),
        default=len(t),
    )
    assert root_at < first_cd, (
        "REPO_ROOT is resolved after a `cd`, so a relative invocation "
        "(./build_macos_desktop.sh) resolves it to the wrong directory."
    )


def test_repo_root_is_resolved_exactly_once() -> None:
    """A second derivation later in the file re-introduces the bug even if the
    first one is correct."""
    n = _text().count('REPO_ROOT="$(cd "$(dirname')
    assert n == 1, f"REPO_ROOT derived {n} times; a later one will be wrong"


def test_real_script_invoked_relatively_passes_its_own_gates(tmp_path: Path) -> None:
    """THE TEST I SHOULD HAVE WRITTEN FIRST.

    The user ran, from the repo root:

        ./build_macos_desktop.sh --bundle-python

    and got "scripts/build_bundle.py is missing". My earlier gate test extracted
    the block into a harness file and ran it directly, which never exercised the
    relative-path invocation that caused the failure. This runs the REAL script,
    by relative path, from the repo root, and asserts the gates pass.

    Everything before the gates (toolchain checks, embedded Python, cargo) is
    stubbed out via PATH so the test stays fast and hermetic; the script is
    stopped by a cargo stub right after the gates it is here to verify.
    """
    bindir = tmp_path / "bin"
    bindir.mkdir()
    for name in ("cargo", "cargo-tauri", "rustup"):
        stub = bindir / name
        stub.write_text('#!/usr/bin/env bash\nif [ "$1" = "tauri" ] && [ "$2" = "build" ]; '
                        'then echo "GATES_PASSED_REACHED_CARGO"; exit 0; fi\nexit 0\n',
                        encoding="utf-8")
        stub.chmod(0o755)
    proc = subprocess.run(
        ["bash", "./build_macos_desktop.sh"],
        cwd=REPO,
        capture_output=True,
        text=True,
        timeout=600,
        env={**os.environ, "PATH": f"{bindir}:{os.environ['PATH']}"},
    )
    assert "is missing. Cannot verify the frontend bundle" not in proc.stdout, (
        "the gate wrongly reports build_bundle.py missing -- REPO_ROOT resolved "
        f"to the wrong directory.\nstdout:\n{proc.stdout[-3000:]}"
    )
    assert "Frontend bundle rebuilt and verified against source" in proc.stdout, (
        f"the gates did not complete.\nstdout:\n{proc.stdout[-3000:]}\n"
        f"stderr:\n{proc.stderr[-2000:]}"
    )


def test_every_build_bundle_invocation_is_anchored_to_repo_root() -> None:
    """A bare `python3 scripts/build_bundle.py` inside src-tauri/ silently
    cannot work."""
    for line in _text().splitlines():
        if "build_bundle.py" not in line:
            continue
        if line.lstrip().startswith("#") or "echo" in line:
            continue
        assert "$REPO_ROOT" in line, f"unanchored build_bundle.py reference: {line!r}"


def test_index_html_canary_is_anchored_to_repo_root() -> None:
    line = next(ln for ln in _text().splitlines() if "CORE MODULES" in ln and "grep" in ln)
    assert "$REPO_ROOT/frontend/index.html" in line, line


def test_gate_block_actually_succeeds_when_run_from_src_tauri() -> None:
    """SUPERSEDED IN PLACE by test_real_script_invoked_relatively_passes_its_own
    _gates, which is the honest version of this check.

    This test used to extract the gate block into a harness file and execute it.
    That was too weak in one direction and too strong in the other:

      - Too weak: the harness assigned BASH_SOURCE itself, so it never
        exercised the relative-path invocation (`./build_macos_desktop.sh`)
        that actually broke on the user's machine. It passed while the real
        script failed.
      - Too strong: once REPO_ROOT moved to the top of the file where it
        belongs, the slice from "REPO_ROOT=" swept in the whole toolchain
        preamble, so the test started running rustup and pip.

    What remains here is the narrow, still-useful invariant: the gate block
    must not contain any path that is relative to the current directory,
    because the current directory at that point is src-tauri/.
    """
    block = _slice("Rebuilding the frontend bundle", "# Apply Apple Code Signing")
    for line in block.splitlines():
        stripped = line.strip()
        if stripped.startswith("#") or "echo" in line:
            continue
        for path in ("scripts/build_bundle.py", "frontend/index.html"):
            if path in line:
                assert "$REPO_ROOT" in line, (
                    f"gate references {path} relative to src-tauri/: {line!r}"
                )


# --------------------------------------------------------------------------
# DEFECT B: a bundle_dmg.sh failure must not discard a successfully built .app
# --------------------------------------------------------------------------


def _failure_handler_block() -> str:
    # Start AFTER the `TAURI_BUILD_RC=$?` capture line. Including it re-assigns
    # the variable from the harness's own last exit status (0), which silently
    # neutered two of these tests on the first run -- they "passed the fix" by
    # testing rc=0. Caught by revert-proofing.
    block = _slice("TAURI_BUILD_RC=$?", "cd ..")
    return block.split("\n", 1)[1]


def test_cargo_tauri_build_return_code_is_captured_not_fatal(tmp_path: Path) -> None:
    """REVERT-PROOF MISS, corrected in place.

    This test originally only grepped for the string `set +e`. Deleting that
    line and replacing it with `: # set +e removed` -- which restores the exact
    bug B, a fatal DMG failure -- left all 11 tests GREEN. A string check is not
    a behaviour check. It now EXECUTES the block with a cargo stub that exits
    non-zero and asserts the script survives to capture the return code."""
    t = _text()
    block = _slice("set +e", "TAURI_BUILD_RC=$?") + 'TAURI_BUILD_RC=$?\n'
    stub = tmp_path / "cargo"
    stub.write_text("#!/usr/bin/env bash\nexit 7\n", encoding="utf-8")
    stub.chmod(0o755)
    harness = (
        f'set -e\nexport PATH="{tmp_path}:$PATH"\nBUILD_FLAGS=()\nSIGN_APP=0\n'
        f'{block}\necho "SURVIVED rc=$TAURI_BUILD_RC"\n'
    )
    proc = subprocess.run(
        ["bash", "-c", harness], cwd=tmp_path, capture_output=True, text=True, timeout=60
    )
    assert proc.returncode == 0, (
        "a failing `cargo tauri build` killed the script outright, so the .app "
        f"is never installed at the documented path.\nstdout:\n{proc.stdout}\n"
        f"stderr:\n{proc.stderr}"
    )
    assert "SURVIVED rc=7" in proc.stdout, proc.stdout
    assert "set -e" in t[t.index("TAURI_BUILD_RC=$?") :][:200], (
        "`set -e` must be restored immediately after the capture"
    )


def test_dmg_only_failure_keeps_going_when_the_app_exists(tmp_path: Path) -> None:
    """rc != 0 but a .app is on disk -> continue, warn, do not exit."""
    (tmp_path / "target" / "release" / "bundle" / "macos" / "Agentic OS Platform.app").mkdir(
        parents=True
    )
    harness = f'set -e\nTAURI_BUILD_RC=1\n{_failure_handler_block()}\necho REACHED_COPY_STEP\n'
    proc = subprocess.run(
        ["bash", "-c", harness], cwd=tmp_path, capture_output=True, text=True, timeout=60
    )
    assert proc.returncode == 0, (
        "A DMG-only failure aborted the build and the .app was never installed "
        f"at the documented path.\nstdout:\n{proc.stdout}\nstderr:\n{proc.stderr}"
    )
    assert "REACHED_COPY_STEP" in proc.stdout
    assert "bundle_dmg.sh" in proc.stdout, "the warning must name the real culprit"


def test_a_genuine_build_failure_still_aborts(tmp_path: Path) -> None:
    """The escape hatch must not swallow real failures: rc != 0 and NO .app
    is a genuine build failure and must exit non-zero."""
    harness = f'set -e\nTAURI_BUILD_RC=101\n{_failure_handler_block()}\necho SHOULD_NOT_REACH\n'
    proc = subprocess.run(
        ["bash", "-c", harness], cwd=tmp_path, capture_output=True, text=True, timeout=60
    )
    assert proc.returncode == 101, (
        f"a real build failure was swallowed (rc={proc.returncode})\n{proc.stdout}"
    )
    assert "SHOULD_NOT_REACH" not in proc.stdout
    assert "no .app bundle" in proc.stdout


def test_final_summary_tells_the_truth_about_a_missing_dmg() -> None:
    """If the DMG failed, the success banner must not imply one was produced."""
    t = _text()
    assert "DMG_BUILD_FAILED" in t
    i = t.index('DMG Installer : NOT built')
    banner = t.index("macOS Desktop App Built Successfully")
    assert banner < i, "the honest-DMG notice belongs in the final summary block"


def test_script_is_syntactically_valid() -> None:
    proc = subprocess.run(["bash", "-n", str(SCRIPT)], capture_output=True, text=True)
    assert proc.returncode == 0, proc.stderr


def test_documented_launch_path_matches_the_path_the_script_populates() -> None:
    """The message the user copy-pastes must point where the copy step writes."""
    t = _text()
    # The path is emitted from a single-quoted echo, so the quotes are literal
    # double quotes with no backslashes. My first regex looked for escaped
    # quotes and matched nothing, then asserted on the empty list.
    documented = re.findall(r'open "([^"]+\.app)"', t)
    assert documented, "no documented `open` path found"
    for path in documented:
        assert f'cp -R "$APP_FOUND" "{path}"' in t, (
            f"the script tells the user to open {path} but never copies the bundle there"
        )
