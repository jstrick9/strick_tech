"""
Specs router — path traversal regression.

`spec_id` and `filename` arrive from the URL and are used to build a filesystem
path (SPECS_DIR / spec_id / filename). Prior to this guard, a crafted spec_id
like `../../evil` (reachable as PUT /api/specs/../../evil/artifacts/x.md) made
_spec_dir / _save_artifact write the artifact OUTSIDE the workspace — an
arbitrary-file-write. The filename sanitizer also allowed `..` by stripping it,
silently relocating writes.

Guard: a strict spec-id regex (_SPEC_ID_RE) and a filename that refuses path
separators / dot-dot. Both must reject the traversal cases and keep valid
writes working.
"""
from __future__ import annotations

import sys
import tempfile
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[2]))

from backend.routers import specs  # noqa: E402


@pytest.fixture()
def isolated_specs_dir(monkeypatch):
    """Point the specs dir at a throwaway sandbox dir."""
    base = Path(tempfile.mkdtemp()) / 'base'
    base.mkdir(parents=True, exist_ok=True)
    monkeypatch.setattr(specs, 'SPECS_DIR', base)
    return base


class TestSpecPathTraversal:
    def test_traversal_spec_id_is_refused(self, isolated_specs_dir):
        with pytest.raises(ValueError):
            specs._save_artifact('../../evil', 'x.md', 'PWNED')
        # No file may be written outside the base dir.
        assert not (isolated_specs_dir.parent / 'evil' / 'x.md').exists()

    def test_dotdot_filename_is_refused(self, isolated_specs_dir):
        with pytest.raises(ValueError):
            specs._save_artifact('spec_x', '../../x.md', 'PWNED')

    def test_separator_filename_is_refused(self, isolated_specs_dir):
        with pytest.raises(ValueError):
            specs._save_artifact('spec_x', 'sub/x.md', 'PWNED')
        with pytest.raises(ValueError):
            specs._save_artifact('spec_x', r'sub\\x.md', 'PWNED')

    def test_leading_dot_filename_is_refused(self, isolated_specs_dir):
        with pytest.raises(ValueError):
            specs._save_artifact('spec_x', '.hidden', 'PWNED')

    def test_valid_spec_and_filename_still_write(self, isolated_specs_dir):
        specs._save_artifact('spec_abc', 'notes.md', 'hello')
        assert specs._load_artifact('spec_abc', 'notes.md') == 'hello'

    def test_load_rejects_traversal_spec_id(self, isolated_specs_dir):
        with pytest.raises(ValueError):
            specs._load_artifact('../../evil', 'notes.md')

    def test_valid_spec_id_shape_is_accepted_for_directory(self, isolated_specs_dir):
        specs._save_artifact('spec_abc-def_1', 'n.md', 'x')
        assert specs._load_artifact('spec_abc-def_1', 'n.md') == 'x'
