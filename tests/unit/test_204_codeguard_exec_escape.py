"""
`codeguard` — exec()-sandbox escape regression (Gap #006).

`profiler.py` `/profile/run` and `replay.py` code nodes executed user-supplied
source with `exec(compile(code, ...), {'__builtins__': <restricted allow-list>})`.
A restricted `__builtins__` is NOT a sandbox: dunder attribute traversal is
intrinsic, so a snippet could reach

    [x for x in ().__class__.__mro__[1].__subclasses__()
     if x.__name__=='_DummyModuleLock'][0].__init__.__globals__['__import__']
      ('os').system('echo pwned > /tmp/pwned')

and execute an arbitrary command. Both callers also exposed `type`, making the
graph trivially reachable. Reproduced: wrote /tmp/prof_rce.

Fix: guard with `codeguard.reject_unsafe_attribute_usage` / `run_guarded_exec`,
which reject dunder/private attribute access and dunder name references before
exec, and drop `type` from the allow-lists. Legitimate transform/profiling code
(no dunder/private access) still runs.
"""
from __future__ import annotations

import sys
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[2]))

from backend.services.codeguard import (  # noqa: E402
    reject_unsafe_attribute_usage,
    run_guarded_exec,
)


def _restricted_builtins():
    """Match the (fixed) allow-list now used by profiler/replay — no `type`."""
    return {
        'print': print, 'len': len, 'range': range, 'list': list, 'dict': dict,
        'set': set, 'tuple': tuple, 'str': str, 'int': int, 'float': float,
        'bool': bool, 'abs': abs, 'sum': sum, 'min': min, 'max': max,
        'sorted': sorted, 'enumerate': enumerate, 'zip': zip, 'map': map,
        'filter': filter, 'round': round, 'isinstance': isinstance,
        '__builtins__': None,
    }


ESCAPES = [
    # Confirmed RCE: subclass traversal to a class exposing __import__ -> os.system.
    "[x for x in ().__class__.__mro__[1].__subclasses__() if x.__name__=='_DummyModuleLock']"
    "[0].__init__.__globals__['__import__']('os').system('echo x')",
    # Dunder / private attribute access at various points.
    "().__class__",
    "x.__class__.__mro__",
    "x._private",
    "().__reduce_ex__(2)",
    # Dunder name references.
    "__import__('os')",
    "x = __builtins__",
]


@pytest.mark.parametrize('code', ESCAPES)
def test_dunder_or_private_usage_is_rejected(code):
    with pytest.raises(ValueError):
        reject_unsafe_attribute_usage(code)


def test_real_escape_does_not_execute(tmp_path):
    marker = tmp_path / 'pwned'
    escape = (
        "[x for x in ().__class__.__mro__[1].__subclasses__() "
        "if x.__name__=='_DummyModuleLock']"
        f"[0].__init__.__globals__['__import__']('os').system('echo x > {marker}')"
    )
    with pytest.raises(ValueError):
        run_guarded_exec(escape, {'__builtins__': _restricted_builtins()})
    assert not marker.exists()


def test_import_is_inert_under_restricted_builtins():
    # `import` has no `__import__` to call under the restricted builtins, so it
    # must fail (ImportError) rather than grant filesystem/OS access.
    with pytest.raises((ImportError, TypeError)):
        run_guarded_exec("import os; os.system('echo nope')",
                         {'__builtins__': _restricted_builtins()})


def test_legitimate_code_still_runs():
    code = (
        "def fib(n):\n"
        "    a, b = 0, 1\n"
        "    for i in range(n):\n"
        "        a, b = b, a + b\n"
        "    return a\n"
        "result = [fib(i) for i in range(10)]\n"
        "print('sum', sum(result))\n"
    )
    run_guarded_exec(code, {'__builtins__': _restricted_builtins()})  # no exception


def test_empty_and_unparseable_code_rejected():
    with pytest.raises(ValueError):
        reject_unsafe_attribute_usage('')
    with pytest.raises(ValueError):
        reject_unsafe_attribute_usage('def broken(:')
