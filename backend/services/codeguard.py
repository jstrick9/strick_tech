"""
Code-execution guard for server-side `exec()` of user-supplied source.

`profiler.py` and `replay.py` author-intended a "prevent RCE" sandbox by
passing a restricted `__builtins__` allow-list to `exec()`. That is not a
sandbox: Python permits dunder attribute traversal regardless of builtins, so
a snippet could reach `().__class__.__mro__[1].__subclasses__()` → a subclass
whose `__init__.__globals__` exposes `__import__` → `__import__('os').system(...)`.
(Reproduced in both callers; the `type` built-in both callers expose makes the
graph trivially reachable.)

The escape always requires dunder/private attribute access (`. __class__`,
`. __mro__`, `. __subclasses__`, `. __globals__`, `. __init__`, …). Blocking
any attribute whose name begins with `_`, and any reference to a dunder name,
closes the traversal while leaving ordinary user code (loops, comprehensions,
calls on the user's own objects, string/build-in helpers) fully intact.

This is intentionally minimal: it guards the traversal primitive, not a general
bytecode sandbox. Callers MUST still treat the result as untrusted — no
executor should present this as a hardened boundary against adversarial code
beyond dunder/private access.
"""
from __future__ import annotations

import ast


def reject_unsafe_attribute_usage(code: str, *, name: str = '<code>') -> ast.Module:
    """Parse `code` in exec mode and raise ValueError on any attribute access
    or name reference that targets a dunder/private member (the object-graph
    traversal primitive used to escape a restricted-builtins `exec()`).

    Returns the parsed tree on success so the caller can compile/execute it.
    """
    if not isinstance(code, str) or not code.strip():
        raise ValueError(f'{name}: empty code')
    try:
        tree = ast.parse(code, filename=name)
    except SyntaxError as exc:
        raise ValueError(f'{name}:{exc.lineno}: {exc.msg}') from exc

    for node in ast.walk(tree):
        if isinstance(node, ast.Attribute):
            if node.attr.startswith('_'):
                raise ValueError(
                    f'{name}: dunder/private attribute access is not allowed '
                    f'(.{node.attr})'
                )
        elif isinstance(node, ast.Name):
            # A dunder *global/name* (e.g. `__import__`, any `__foo__` used
            # directly) is never needed for legitimate transform code and is
            # the usual first step of an escape, so reject it.
            if node.id.startswith('__'):
                raise ValueError(f'{name}: dunder name is not allowed ({node.id})')
    return tree


def run_guarded_exec(code: str, globals_: dict, locals_: dict | None = None,
                     *, name: str = '<code>'):
    """Compile and exec `code` after the dunder/private-access guard passes.

    `globals_` must already carry a restricted `__builtins__`. Raises ValueError
    if the guard rejects the code; raises the underlying execution error normally.
    """
    tree = reject_unsafe_attribute_usage(code, name=name)
    exec(compile(tree, name, 'exec'), globals_, locals_)  # noqa: S102
