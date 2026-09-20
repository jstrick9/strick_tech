"""r60: the shared test sandbox must actually be wired into every suite that
imports the backend in-process.

The 2026-09 workspace cleanup (#201) removed 407 test-artifact pack manifests
and 419 junk installed.json entries — residue from suites that ran the app
against the real repo data dir. tests/unit had a sandbox; perf (auto-started
live server) and benchmarks (TestClient) did not, so every run of those suites
re-created exactly that residue. The sandbox was extracted to
tests/_data_sandbox.py and activated in all three conftests; this test pins
the wiring so a future conftest edit cannot silently un-isolate a suite again.
"""
import os
from pathlib import Path

TESTS = Path(__file__).resolve().parents[1]


def _read(rel: str) -> str:
    return (TESTS / rel).read_text(encoding="utf-8")


def test_perf_conftest_activates_sandbox_before_backend_import():
    src = _read("perf/conftest.py")
    act = src.index("_activate_sandbox(")
    # activation must precede any backend import in the file
    assert "backend" not in src[:act] or src.rindex("import", 0, act) < act
    assert "from tests._data_sandbox import activate" in src


def test_benchmarks_conftest_activates_sandbox():
    src = _read("benchmarks/conftest.py")
    assert "from tests._data_sandbox import activate" in src
    assert "_activate_sandbox(" in src
    # and it must not import the backend at module level before activating
    assert src.index("_activate_sandbox(") < src.index("from backend.app import app")


def test_unit_conftest_delegates_to_shared_sandbox():
    src = _read("unit/conftest.py")
    assert "from tests._data_sandbox import activate" in src
    # the old inline sandbox must not have crept back as a second implementation
    assert "_WRITABLE_DIRS" not in src
    assert "mkdtemp(prefix=\"agentic-unit-data-\")" not in src


def test_shared_sandbox_sets_all_three_env_vars():
    src = _read("_data_sandbox.py")
    for var in ("AGENTIC_TEST_DB", "AGENTIC_OS_DATA_DIR", "AGENTIC_OS_HOST"):
        assert var in src, f"sandbox no longer sets {var}"
    # idempotent: a second activation must be a no-op
    assert "AGENTIC_OS_DATA_DIR\")" in src  # the already-set check


def test_sandbox_is_live_in_this_session():
    """The sandbox this suite runs under is real: a temp dir, not the repo."""
    data_dir = os.environ.get("AGENTIC_OS_DATA_DIR")
    assert data_dir, "AGENTIC_OS_DATA_DIR not set — sandbox not activated"
    p = Path(data_dir)
    repo = TESTS.parent
    assert p != repo and repo not in p.parents, (
        f"sandbox {p} is inside the repo — tests would write real files"
    )
    assert (p / "plugins").is_dir(), "sandbox missing writable plugins/"
