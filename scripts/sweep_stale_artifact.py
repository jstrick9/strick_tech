#!/usr/bin/env python3
"""Sweep 3 of 4 — STALE BUILD ARTEFACT.

The class, from docs/BUG-SWEEP-PLAN.md: *shipped output diverging from source.*
The check: does every packaging path regenerate what it ships, and fail loudly
if it cannot?

This is the most expensive class in this codebase's history. Four separate
instances shipped, each one silently serving old JavaScript while reporting
success:

  5e0d178  build_macos_desktop.sh was not executable in git
  03ee7d7  the bundle embedded a build timestamp, so every build dirtied
           frontend/dist and BLOCKED the user's `git pull` for five commits
  d481a30  the packager selected the PREVIOUS build's .app
  e8bd391  nothing warned when the checkout was behind origin

In every case the fix was correct and the user did not have it. "The fix is
correct" and "the user has the fix" are different claims, and only the second
one matters.

WHAT MAKES A PATH "SHIPPING"
----------------------------
Any script, Dockerfile or workflow that packages or serves frontend/. The app
does NOT serve frontend/index.html as written -- backend/app.py rewrites it to
point at content-hashed bundles in frontend/dist. So a path that copies
frontend/ without regenerating dist ships whatever happened to be on disk.

CHECKS
------
  1. NO_BUNDLE_BUILD     a shipping path never runs scripts/build_bundle.py
  2. NO_VERIFY           it builds the bundle but never runs --check
  3. SOFT_FAILURE        a bundle step whose failure does not abort the build
  4. BUNDLE_AFTER_PACK   the bundle is rebuilt AFTER the thing that packages it
  5. DIST_NOT_REPRODUCIBLE  two consecutive builds differ byte-for-byte, which
                            is what dirties the tree and blocks `git pull`
  6. DIST_STALE          frontend/dist on disk does not match frontend/js

Usage:
    python3 scripts/sweep_stale_artifact.py
    python3 scripts/sweep_stale_artifact.py --json

Exit 0 = zero findings.
"""

from __future__ import annotations

import argparse
import hashlib
import json
import re
import subprocess
import sys
from pathlib import Path

REPO = Path(__file__).resolve().parents[1]
DIST = REPO / "frontend" / "dist"
BUILD_BUNDLE = REPO / "scripts" / "build_bundle.py"

# Paths that package or serve the frontend. Each is (path, why it ships).
SHIPPING_PATHS: list[tuple[str, str]] = [
    ("build_macos_desktop.sh", "packages the macOS .app/.dmg"),
    ("scripts/tauri-build.sh", "packages the Tauri desktop app for all platforms"),
    ("Dockerfile", "COPY frontend/ then runs the server from the image"),
    (".github/workflows/build-macos-dmg.yml", "CI produces the release .dmg"),
]

# Paths deliberately NOT swept, with the reason. Recorded so the exclusion is a
# decision rather than an oversight.
NOT_SHIPPING: list[tuple[str, str]] = [
    ("start.sh", "runs from the working tree; a developer's dist is their own"),
    ("scripts/tauri-dev.sh", "dev server, hot-reloads from source"),
    ("docker-compose.yml", "composes the image built by Dockerfile, adds nothing"),
    (".github/workflows/ci.yml", "runs tests; ships nothing"),
]


def _read(rel: str) -> str:
    p = REPO / rel
    return p.read_text(encoding="utf-8") if p.exists() else ""


def _strip_comments(text: str, rel: str) -> str:
    """Comments describing a check are not the check."""
    if rel.endswith((".sh", ".yml", ".yaml")) or rel == "Dockerfile":
        return re.sub(r"(?m)^\s*#.*$", "", text)
    return text


def check_paths() -> list[dict]:
    findings: list[dict] = []
    for rel, why in SHIPPING_PATHS:
        src = _read(rel)
        if not src:
            findings.append({"path": rel, "kind": "PATH_MISSING",
                             "detail": f"expected to exist ({why})"})
            continue
        body = _strip_comments(src, rel)

        # A workflow that delegates to a swept script inherits its guarantees.
        delegates = any(
            other in body for other, _ in SHIPPING_PATHS if other != rel
        )

        builds = "build_bundle.py" in body
        if not builds and not delegates:
            findings.append({
                "path": rel, "kind": "NO_BUNDLE_BUILD",
                "detail": f"{why}, but never runs scripts/build_bundle.py — it "
                          "ships whatever frontend/dist happens to be on disk",
            })
            continue
        if delegates and not builds:
            continue  # covered by the script it calls

        if "--check" not in body:
            findings.append({
                "path": rel, "kind": "NO_VERIFY",
                "detail": "builds the bundle but never runs "
                          "`build_bundle.py --check` to prove it matches source",
            })

        # Failure must abort. `|| true`, `continue-on-error`, or a bare
        # invocation with no `if !` / `set -e` guard is a soft failure.
        # `|| true` only matters on the BUNDLE line. Testing "both strings
        # appear somewhere in the file" flagged build_macos_desktop.sh for a
        # `git fetch ... || true` in the behind-origin gate, where tolerating
        # failure is correct (offline builds must still work). Check the line.
        for ln in body.splitlines():
            if "build_bundle" in ln and "|| true" in ln:
                findings.append({
                    "path": rel, "kind": "SOFT_FAILURE",
                    "detail": f"bundle step tolerates failure: {ln.strip()[:90]}",
                })
        if rel.endswith(".sh"):
            guarded = ("if !" in body and "build_bundle" in body) or "set -e" in body
            if not guarded:
                findings.append({
                    "path": rel, "kind": "SOFT_FAILURE",
                    "detail": "no `set -e` and no `if !` guard around the bundle "
                              "step — a failure would be ignored",
                })

        # Ordering: rebuilding after packaging packages the old bundle.
        #
        # `COPY frontend` is NOT a packaging step in this sense. In a
        # Dockerfile, COPY then RUN both contribute to the same final image --
        # rebuilding dist after copying is the ONLY way to do it, since the
        # bundler has to be inside the image to run. Treating COPY as "packed"
        # flagged the correct fix as a defect. The real packaging boundary for
        # an image is the end of the build, not a COPY.
        pack_markers = ("cargo tauri build", "docker build")
        pack = min(
            (body.index(t) for t in pack_markers if t in body),
            default=-1,
        )
        if pack != -1 and builds and body.index("build_bundle.py") > pack:
            findings.append({
                "path": rel, "kind": "BUNDLE_AFTER_PACK",
                "detail": "the bundle is rebuilt AFTER the step that packages it",
            })
    return findings


def _digest() -> str:
    h = hashlib.sha256()
    for p in sorted(DIST.glob("*")):
        if p.is_file():
            h.update(p.name.encode())
            h.update(p.read_bytes())
    return h.hexdigest()


def check_reproducible() -> list[dict]:
    """Two consecutive builds must be byte-identical.

    Non-reproducible output is not cosmetic: it dirties tracked files, which
    makes `git pull` abort, which is how five fixes failed to reach the user.
    """
    if not BUILD_BUNDLE.exists():
        return [{"path": "scripts/build_bundle.py", "kind": "PATH_MISSING",
                 "detail": "the bundler itself is missing"}]
    findings = []
    for _ in range(2):
        proc = subprocess.run(
            [sys.executable, str(BUILD_BUNDLE)],
            cwd=REPO, capture_output=True, text=True, timeout=600,
        )
        if proc.returncode != 0:
            return [{"path": "scripts/build_bundle.py", "kind": "BUILD_FAILED",
                     "detail": proc.stderr[-300:] or proc.stdout[-300:]}]
    first = _digest()
    subprocess.run([sys.executable, str(BUILD_BUNDLE)],
                   cwd=REPO, capture_output=True, timeout=600)
    if _digest() != first:
        findings.append({
            "path": "frontend/dist", "kind": "DIST_NOT_REPRODUCIBLE",
            "detail": "two consecutive builds produced different bytes — this "
                      "dirties tracked files and makes `git pull` abort",
        })

    proc = subprocess.run(
        [sys.executable, str(BUILD_BUNDLE), "--check"],
        cwd=REPO, capture_output=True, text=True, timeout=600,
    )
    if proc.returncode != 0:
        findings.append({
            "path": "frontend/dist", "kind": "DIST_STALE",
            "detail": "the committed bundle does not match frontend/js",
        })
    return findings


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--json", action="store_true")
    ap.add_argument("--skip-build", action="store_true",
                    help="static checks only; do not run the bundler")
    args = ap.parse_args()

    findings = check_paths()
    if not args.skip_build:
        findings += check_reproducible()

    if args.json:
        print(json.dumps(findings, indent=2))
    else:
        print("SWEEP 3/4 — STALE BUILD ARTEFACT")
        print(f"  shipping paths checked : {len(SHIPPING_PATHS)}")
        print(f"  deliberately excluded  : {len(NOT_SHIPPING)}")
        for rel, why in NOT_SHIPPING:
            print(f"      {rel:44} {why}")
        print("-" * 68)
        if not findings:
            print("  0 findings.")
        else:
            by: dict[str, list[dict]] = {}
            for f in findings:
                by.setdefault(f["kind"], []).append(f)
            for kind, items in sorted(by.items()):
                print(f"\n  {kind}  ({len(items)})")
                for f in items:
                    print(f"    {f['path']}")
                    print(f"        {f['detail']}")
            print(f"\n  TOTAL: {len(findings)}")
    return 1 if findings else 0


if __name__ == "__main__":
    raise SystemExit(main())
