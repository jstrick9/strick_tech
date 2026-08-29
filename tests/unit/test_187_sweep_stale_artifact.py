"""Sweep 3/4 — stale build artefact — must stay at zero findings.

docs/BUG-SWEEP-PLAN.md: "Does every packaging path regenerate what it ships,
and fail loudly if it cannot?"

This is the most expensive class in this repository's history. Four instances
shipped, each silently serving old JavaScript while reporting success:

    5e0d178  build_macos_desktop.sh was not executable in git
    03ee7d7  the bundle embedded a build timestamp, so every build dirtied
             frontend/dist and BLOCKED `git pull` for five commits
    d481a30  the packager selected the PREVIOUS build's .app
    e8bd391  nothing warned when the checkout was behind origin

In every case the fix was correct and the user did not have it.

WHAT THE SWEEP FOUND — TWO MORE PATHS WITH THE ORIGINAL DEFECT
---------------------------------------------------------------
    scripts/tauri-build.sh   packages the desktop app for macOS/Windows/Linux
    Dockerfile               COPY frontend/ then serves it from the image

Neither ran scripts/build_bundle.py. backend/app.py does not serve
frontend/index.html as written -- it rewrites it to load content-hashed bundles
from frontend/dist -- so both shipped whatever dist happened to be on the
builder's disk. Identical to the macOS defect that cost five sessions, sitting
in two paths nobody had looked at because the reported bug came from the third.

Both now build AND `--check` the bundle, and abort on failure.

TWO CORRECTIONS TO THE SWEEP ITSELF
-----------------------------------
  1. SOFT_FAILURE fired on build_macos_desktop.sh because `|| true` and
     `build_bundle` both appeared somewhere in the file. The `|| true` is on
     `git fetch` in the behind-origin gate, where tolerating failure is
     correct -- an offline build must still work. Now checked per line.

  2. BUNDLE_AFTER_PACK fired on my own Dockerfile fix, treating `COPY frontend`
     as a packaging boundary. In a Dockerfile, COPY and RUN both contribute to
     the same final image; rebuilding dist after copying is the ONLY way to do
     it, because the bundler must be inside the image to run. The check flagged
     the correct fix as the defect.

Both corrections narrowed the check rather than deleting it: the SOFT_FAILURE
and ordering rules still fire, they just fire on the right thing.
"""

from __future__ import annotations

import json
import re
import subprocess
import sys
from pathlib import Path

REPO = Path(__file__).resolve().parents[2]
SWEEP = REPO / "scripts" / "sweep_stale_artifact.py"


def _run(*args: str) -> subprocess.CompletedProcess:
    return subprocess.run(
        [sys.executable, str(SWEEP), *args],
        cwd=REPO, capture_output=True, text=True, timeout=900,
    )


def test_the_sweep_script_exists() -> None:
    assert SWEEP.exists(), "sweep 3 of 4 is missing; the finish line cannot be checked"


def test_the_sweep_reports_zero_findings() -> None:
    """THE GATE."""
    p = _run("--json")
    findings = json.loads(p.stdout)
    assert findings == [], (
        "stale-artefact sweep found regressions:\n"
        + json.dumps(findings, indent=2)[:4000]
    )
    assert p.returncode == 0


def test_tauri_build_regenerates_and_verifies_the_bundle() -> None:
    """One of the two real findings. This path packages for every platform."""
    src = (REPO / "scripts" / "tauri-build.sh").read_text(encoding="utf-8")
    body = re.sub(r"(?m)^\s*#.*$", "", src)
    assert "build_bundle.py" in body, (
        "tauri-build.sh would ship whatever frontend/dist is on disk"
    )
    assert "--check" in body, "builds the bundle but never proves it matches source"
    assert body.index("build_bundle.py") < body.index("cargo tauri build"), (
        "the bundle must be rebuilt BEFORE cargo packages it"
    )


def test_the_docker_image_regenerates_and_verifies_the_bundle() -> None:
    """The other real finding. An image that serves stale JS is worse than a
    stale desktop build: it looks like a clean deploy."""
    src = (REPO / "Dockerfile").read_text(encoding="utf-8")
    body = re.sub(r"(?m)^\s*#.*$", "", src)
    assert "build_bundle.py" in body
    assert "--check" in body
    assert "COPY scripts/build_bundle.py" in body, (
        "the bundler must be inside the image to run there"
    )


def test_the_bundle_step_aborts_the_image_build_on_failure() -> None:
    """`&&` chaining is what makes a stale bundle fail the build rather than
    become a running container that lies about its version."""
    src = (REPO / "Dockerfile").read_text(encoding="utf-8")
    block = src[src.index("RUN python scripts/build_bundle.py"):]
    assert "&&" in block[:200], "a failed bundle build must abort the image build"
    assert "|| true" not in block[:200], "failure is being swallowed"


def test_the_sweep_does_not_flag_git_fetch_tolerance() -> None:
    """Guard against correction #1 regressing. `git fetch ... || true` in the
    behind-origin gate is correct: an offline build must still work."""
    p = _run("--json")
    findings = json.loads(p.stdout)
    bogus = [f for f in findings
             if f["kind"] == "SOFT_FAILURE" and "git fetch" in f.get("detail", "")]
    assert not bogus, f"the per-line SOFT_FAILURE fix regressed: {bogus}"


def test_the_sweep_does_not_treat_docker_copy_as_a_packaging_boundary() -> None:
    """Guard against correction #2 regressing — it flagged the correct fix."""
    src = SWEEP.read_text(encoding="utf-8")
    assert "COPY frontend" not in src.split("pack_markers")[1][:200], (
        "COPY is back in the packaging markers; it will flag the Dockerfile fix"
    )


def test_excluded_paths_are_declared_with_a_reason() -> None:
    """An exclusion without a reason is indistinguishable from an oversight."""
    src = SWEEP.read_text(encoding="utf-8")
    assert "NOT_SHIPPING" in src
    for path in ("start.sh", "docker-compose.yml", "ci.yml", "tauri-dev.sh"):
        assert path in src, f"{path} is neither swept nor explicitly excluded"


def test_the_sweep_checks_reproducibility() -> None:
    """Non-reproducible dist is what blocked the user's `git pull` for five
    commits. It belongs in this class, not just in test_180."""
    src = SWEEP.read_text(encoding="utf-8")
    assert "DIST_NOT_REPRODUCIBLE" in src
    assert "DIST_STALE" in src
