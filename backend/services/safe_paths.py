"""Path containment — one implementation, used everywhere.

WHY THIS EXISTS
---------------
The same containment bug was found independently in four modules during the
module-by-module review, and a sweep afterwards found it in five more:

    if str(target).startswith(str(BASE.resolve())):
        ...treat as safe...

`str.startswith` compares STRINGS, not path components, so any sibling
directory whose name merely begins with the base directory's name passes:

    BASE = /home/user/repo/preview
    ../preview_ESCAPED/pwn.html  ->  /home/user/repo/preview_ESCAPED/pwn.html
    str(...).startswith(str(BASE))  ->  True        # accepted, but OUTSIDE

Note this survives `..` filtering: the *resolved* path contains no `..` at all.
It is not caught by rejecting suspicious input, only by comparing correctly.

`Path.relative_to()` compares components and raises for anything outside, so
the sibling trick cannot work.

WHERE IT MATTERED
-----------------
  * imagegen   (M10) — save_to wrote images outside the workspace
  * terminal   (M12) — cwd launched a SHELL outside the sandbox
  * hierarchy  (M13) — read files into the LLM system prompt
  * composer   (M14) — the LLM chose the write paths

Confirmed reachable in codeindex, codesearch, github, mcp, multitab and
testgen as well.

USAGE
-----
    from ..services.safe_paths import safe_path

    target = safe_path(user_input, base=PREVIEW_DIR)
    if target is None:
        return JSONResponse({'ok': False, 'error': '...'}, status_code=403)
"""

from __future__ import annotations

from pathlib import Path

# Names that must never be created or overwritten by generated code or user
# input, at any depth. These change how the surrounding tooling behaves rather
# than being project content — an agent writing `.env` or `.git/config` into a
# workspace is modifying the environment, not building in it.
PROTECTED_NAMES = frozenset({
    '.env',
    '.env.local',
    '.env.production',
    '.git',
    '.gitignore',
    '.npmrc',
    '.netrc',
    '.ssh',
    'id_rsa',
    'id_ed25519',
    'authorized_keys',
    '.bashrc',
    '.bash_profile',
    '.profile',
    '.zshrc',
})


def safe_path(
    relative: str,
    *,
    base: Path,
    protect_dotfiles: bool = False,
    must_exist: bool = False,
) -> Path | None:
    """Resolve `relative` inside `base`, or return None if it escapes.

    Args:
        relative: caller-supplied path fragment. A leading '/' is treated as
            relative to `base` rather than the filesystem root, so '/etc/passwd'
            is clamped to '<base>/etc/passwd' instead of being refused — callers
            that want it refused outright should check the input themselves.
        base: the directory the result must stay inside.
        protect_dotfiles: also refuse paths containing a PROTECTED_NAMES
            component. Use for anything writing model- or user-supplied files.
        must_exist: refuse paths that do not already exist on disk.

    Returns:
        The resolved absolute Path, or None if the input escapes `base`, is
        empty, contains a NUL byte, or fails one of the optional checks.

    Returning None rather than raising is deliberate: every call site needs to
    turn this into its own HTTP status and message, and an exception would
    invite a bare `except` that swallows the refusal.
    """
    if not relative or not isinstance(relative, str):
        return None
    if '\x00' in relative:
        return None

    try:
        root = Path(base).resolve()
        target = (root / relative.lstrip('/')).resolve()
        # The check. Compares path COMPONENTS, unlike str.startswith().
        target.relative_to(root)
    except (ValueError, OSError, RuntimeError):
        return None

    if protect_dotfiles:
        lowered = {part.lower() for part in target.parts}
        if lowered & PROTECTED_NAMES:
            return None

    if must_exist and not target.exists():
        return None

    return target


def is_within(target: Path | str, base: Path | str) -> bool:
    """True if an ALREADY-RESOLVED path lies inside `base`.

    For call sites holding a Path they built themselves and only needing the
    boolean — the direct replacement for
    `str(target).startswith(str(base.resolve()))`.
    """
    try:
        Path(target).resolve().relative_to(Path(base).resolve())
    except (ValueError, OSError, RuntimeError):
        return False
    return True
