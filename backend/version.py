"""Canonical Agentic OS application version."""
from __future__ import annotations

from pathlib import Path

_ROOT = Path(__file__).resolve().parent.parent
_DEFAULT_VERSION = '11.5.0'


def get_version() -> str:
    """Read the repository/package version from the canonical VERSION file."""
    try:
        value = (_ROOT / 'VERSION').read_text(encoding='utf-8').strip()
        if value:
            return value
    except (OSError, UnicodeError):
        pass
    return _DEFAULT_VERSION


VERSION = get_version()
