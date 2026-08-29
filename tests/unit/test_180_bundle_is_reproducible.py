"""The frontend bundle must be byte-reproducible across builds.

Reported symptom, from the desktop diagnostic on a clean checkout:

    uncommitted files: 8

...and, on the build before that, a `git pull` refused to run:

    error: Your local changes to the following files would be overwritten by
    merge: build_macos_desktop.sh

The user had not edited anything. Running the build was enough to dirty the
working tree, because build_macos_desktop.sh now rebuilds frontend/dist as a
hard gate -- so every build rewrote 40 tracked .gz files.

ROOT CAUSE
----------
`gzip.compress(raw, 9)` writes the CURRENT TIME into bytes 5-8 of the gzip
header (the MTIME field, RFC 1952 s2.3.1). Byte-identical JavaScript therefore
produced a byte-different .gz on every run. Verified directly:

    cmp -l committed.gz rebuilt.gz
         5 350 253
         6  32 116          <- only header bytes differ
    zcat both -> identical

Fixed with mtime=0. The content hash is already in the filename, so the header
timestamp carried no information.

Brotli has no timestamp field and was already deterministic; asserted anyway so
that a future switch to a non-deterministic setting is caught here.

WHY THIS MATTERS BEYOND TIDINESS
--------------------------------
A build that dirties tracked files makes `git pull` fail for a user who has
done nothing wrong, makes the diagnostic report a dirty checkout, and makes
`build_bundle.py --check` -- the gate that exists to prove the shipped
JavaScript matches source -- unable to distinguish "stale bundle" from "built
at a different second".
"""

from __future__ import annotations

import gzip
import subprocess
import sys
from pathlib import Path

REPO = Path(__file__).resolve().parents[2]
DIST = REPO / "frontend" / "dist"
BUILD = REPO / "scripts" / "build_bundle.py"


def _digest(pattern: str) -> str:
    import hashlib

    h = hashlib.sha256()
    for path in sorted(DIST.glob(pattern)):
        h.update(path.name.encode())
        h.update(path.read_bytes())
    return h.hexdigest()


def _build() -> None:
    proc = subprocess.run(
        [sys.executable, str(BUILD)], cwd=REPO, capture_output=True, text=True, timeout=600
    )
    assert proc.returncode == 0, f"build_bundle failed:\n{proc.stdout}\n{proc.stderr}"


def test_gzip_members_carry_no_build_timestamp() -> None:
    """The direct assertion on the defect: MTIME must be zero."""
    offenders = []
    for path in sorted(DIST.glob("*.gz")):
        header = path.read_bytes()[:8]
        mtime = int.from_bytes(header[4:8], "little")
        if mtime != 0:
            offenders.append((path.name, mtime))
    assert not offenders, (
        "these .gz files embed a build timestamp, so every build rewrites them "
        f"and dirties the working tree: {offenders[:5]}"
    )


def test_rebuilding_does_not_change_a_single_gzip_byte() -> None:
    """Behavioural form: build twice, compare."""
    _build()
    first = _digest("*.gz")
    _build()
    assert _digest("*.gz") == first, (
        "rebuilding produced different .gz bytes for identical sources"
    )


def test_rebuilding_does_not_change_brotli_output() -> None:
    if not list(DIST.glob("*.br")):
        import pytest

        pytest.skip("brotli not installed in this environment; nothing to assert")
    _build()
    first = _digest("*.br")
    _build()
    assert _digest("*.br") == first, "brotli output is not reproducible"


def test_a_build_leaves_the_git_working_tree_clean() -> None:
    """The user-facing property. A build must not dirty tracked files, or
    `git pull` fails for someone who changed nothing."""
    _build()
    proc = subprocess.run(
        ["git", "status", "--porcelain", "--", "frontend/dist"],
        cwd=REPO,
        capture_output=True,
        text=True,
        check=True,
    )
    dirty = [ln for ln in proc.stdout.splitlines() if ln.strip()]
    assert not dirty, (
        f"a plain rebuild dirtied {len(dirty)} tracked files under frontend/dist. "
        "This is what blocked the user's `git pull` and made the desktop "
        f"diagnostic report an unclean checkout.\nFirst few:\n" + "\n".join(dirty[:5])
    )


def test_decompressed_content_is_unaffected_by_the_fix() -> None:
    """mtime=0 must change only the header, never the payload."""
    for path in sorted(DIST.glob("*.js.gz"))[:5]:
        source = DIST / path.name[: -len(".gz")]
        if not source.exists():
            continue
        assert gzip.decompress(path.read_bytes()) == source.read_bytes(), (
            f"{path.name} does not decompress to {source.name}"
        )
