"""
Agent hooks — condition-evaluation RCE (Gap #005) regression.

`create_hook`/`update_hook` persisted a user-controlled `condition` verbatim,
and `fire_event` ran it with `eval(cond, {'__builtins__': {}}, safe_locals)`.
Empty `__builtins__` does NOT sandbox Python: dunder attribute traversal is
intrinsic, so a condition like

    [x for x in ().__class__.__mro__[1].__subclasses__()
     if x.__name__=='Popen'][0].__init__.__globals__['os'].system('echo pwned')

reached `os.system` and executed an arbitrary command (reproduced: wrote
/tmp/hook_rce). Fix: replace `eval` with an AST allow-listed evaluator
(`_validate_condition_ast` / `_safe_eval_condition`) that only permits the
comparison/boolean expressions hooks legitimately need, and rejects calls,
subscripts, comprehension nodes and dunder/private attribute access both at
storage time and at evaluation time.
"""
from __future__ import annotations

import sys
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[2]))

from backend.routers.hooks import (  # noqa: E402
    _safe_eval_condition,
    _validate_condition_ast,
)


def _context():
    """Reproduce the namespace fire_event builds for a file_save-like event."""
    class _NS:
        def __init__(self, data):
            self.__dict__.update(data)

    event_data = {'path': 'src/app.py', 'extension': '.py', 'size_lines': 300}
    ns = _NS(event_data)
    return {'file': ns, 'event': ns, 'commit': ns, 'test': ns, **event_data}


_ESCAPES = [
    # The original confirmed RCE payload.
    "[x for x in ().__class__.__mro__[1].__subclasses__() if x.__name__=='Popen']"
    "[0].__init__.__globals__['os'].system('echo pwned > /tmp/hook_rce')",
    # Direct calls / builtins.
    "__import__('os').system('echo pwned')",
    "eval('1+1')",
    "open('/etc/passwd').read()",
    "getattr(__builtins__, 'eval')('1')",
    # Dunder / private attribute access.
    "().__class__",
    "file.__class__.__mro__",
    "file._private",
    # Comprehension / generator / subscript nodes.
    "[x for x in []]",
    "file['path']",
    "().__class__",
]


@pytest.mark.parametrize('payload', _ESCAPES)
def test_unsafe_condition_is_rejected(payload):
    with pytest.raises((ValueError, SyntaxError)):
        _validate_condition_ast(payload)
    # And the full evaluator must not execute it / must not return True.
    with pytest.raises((ValueError, SyntaxError)):
        _safe_eval_condition(payload, _context())


def test_legitimate_conditions_still_evaluate():
    c = _context()
    assert _safe_eval_condition(
        "file.extension in ['.py','.js','.ts'] and 'test' not in file.path", c
    ) is True
    assert _safe_eval_condition('file.size_lines > 200', c) is True
    assert _safe_eval_condition("file.extension not in ['.html']", c) is True
    assert _safe_eval_condition("file.extension == '.py'", c) is True
    # Empty / no condition means "always fire".
    assert _safe_eval_condition('', c) is True
    assert _safe_eval_condition(None, c) is True


def test_condition_false_cases():
    c = _context()
    assert _safe_eval_condition("file.extension in ['.ts']", c) is False
    assert _safe_eval_condition("file.size_lines > 1000", c) is False
