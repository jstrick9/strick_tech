"""
Agentic OS — Plugin Sandbox
Provides isolated execution environment for third-party plugins.
Plugins run in a restricted namespace with access only to approved APIs.
"""
from __future__ import annotations

import ast
import logging
import re
import time
from typing import Any

log = logging.getLogger('agentic.sandbox')

# ── Allowed built-in functions for plugin code ─────────────────────────────
# These are the ONLY things a plugin may call. Critically, the object-graph
# traversal helpers are deliberately excluded: `getattr`, `type`, `setattr`,
# `delattr`, `vars`, `dir`, `globals`, `locals` and `eval`/`exec`/`compile`
# let a plugin walk `some_obj.__class__.__mro__[N].__subclasses__()` to reach
# the REAL `__builtins__['open']`/`__import__` and escape the sandbox (the
# static gate is bypassable by aliasing, e.g. `G = getattr`, then building the
# dunder string at runtime). No plugin needs these; removing them closes the
# escape even for code that slips past the scan.
ALLOWED_BUILTINS = {
    'abs', 'all', 'any', 'bool', 'chr', 'dict', 'divmod', 'enumerate',
    'filter', 'float', 'format', 'frozenset', 'hash', 'hasattr', 'hex', 'int',
    'isinstance', 'issubclass', 'iter', 'len', 'list', 'map', 'max', 'min',
    'next', 'oct', 'ord', 'pow', 'print', 'range', 'repr', 'reversed', 'round',
    'set', 'slice', 'sorted', 'str', 'sum', 'tuple', 'zip',
}

# Builtins that MUST never be handed to plugin code, even if a future edit
# re-adds them to ALLOWED_BUILTINS. Applied unconditionally in
# create_sandbox_globals() so the runtime sandbox can never re-expose them.
DENIED_BUILTINS = {
    'getattr', 'setattr', 'delattr', 'type', 'vars', 'dir', 'globals',
    'locals', 'eval', 'exec', 'compile', 'open', 'input', 'breakpoint',
    'memoryview', 'bytearray', 'object',
}

# ── Dangerous constructs that must not appear in plugin code ────────────────
BLOCKED_MODULES = {
    'os', 'sys', 'subprocess', 'shutil', 'pathlib', 'socket', 'http',
    'urllib', 'requests', 'httpx', 'ctypes', 'importlib', 'code',
    'codeop', 'compile', 'compileall', 'py_compile',
    'multiprocessing', 'threading', 'signal',
    'shelve', 'sqlite3', 'dbm',
    'pickle', 'marshal',
    'pty', 'fcntl', 'termios', 'tty',
}

BLOCKED_NAMES = {
    '__import__', 'eval', 'exec', 'compile', 'globals', 'locals',
    'breakpoint', 'exit', 'quit', 'open', 'input',
    'getattr', 'setattr', 'delattr',  # can be used for sandbox escape
}

BLOCKED_PATTERNS = [
    r'__\w+__',           # dunder attributes
    r'import\s+os',       # os imports
    r'import\s+sys',      # sys imports
    r'__builtins__',      # builtins manipulation
    r'open\s*\(',         # file I/O
    r'exec\s*\(',         # exec calls
    r'eval\s*\(',         # eval calls
    r'subprocess',        # subprocess
    r'os\.system',        # os.system
    r'os\.popen',         # os.popen
]


class SandboxViolationError(Exception):
    """Raised when plugin code violates sandbox restrictions."""
    pass


def validate_plugin_code(code: str) -> dict[str, Any]:
    """Static analysis: check plugin code for sandbox violations before execution.

    Returns:
        {'ok': True} if safe, {'ok': False, 'violations': [...]} if not.
    """
    violations = []

    # Check blocked patterns
    for pattern in BLOCKED_PATTERNS:
        matches = re.findall(pattern, code)
        if matches:
            violations.append(f'Blocked pattern: {pattern} ({len(matches)} occurrences)')

    # Check blocked module imports + object-graph traversal via AST.
    # The `__dunder__` regex cannot catch traversal built at runtime (e.g.
    # `G = getattr` then `G(x, chr(95)*2 + 'class' + chr(95)*2)`), so we also
    # reject the escape-enabling constructs structurally: any attribute access
    # whose name starts with an underscore, and any reference to the traversal
    # builtins even when aliased.
    try:
        tree = ast.parse(code)
        for node in ast.walk(tree):
            if isinstance(node, ast.Import):
                for alias in node.names:
                    mod = alias.name.split('.')[0]
                    if mod in BLOCKED_MODULES:
                        violations.append(f'Blocked import: {alias.name}')
            elif isinstance(node, ast.ImportFrom):
                if node.module:
                    mod = node.module.split('.')[0]
                    if mod in BLOCKED_MODULES:
                        violations.append(f'Blocked from-import: {node.module}')
            elif isinstance(node, ast.Call):
                if isinstance(node.func, ast.Name) and node.func.id in BLOCKED_NAMES:
                    violations.append(f'Blocked function call: {node.func.id}')
            # Any attribute access on a private/dunder name is the graph walk
            # that powers every sandbox escape (.__class__.__mro__.__subclasses__
            # .__globals__.__builtins__...). No plugin needs it.
            if isinstance(node, ast.Attribute) and node.attr.startswith('_'):
                violations.append(f'Blocked private attribute access: .{node.attr}')
            # A reference to a traversal builtin can be aliased and used to
            # synthesise attribute names at runtime.
            if isinstance(node, ast.Name) and node.id in ('getattr', 'type',
                                                          'setattr', 'delattr',
                                                          'vars', 'dir',
                                                          'globals', 'locals'):
                violations.append(f'Blocked traversal builtin: {node.id}')
            # A string literal that contains the escape-signature dunder pair
            # (e.g. '__class__', '__globals__', '__mro__').
            if isinstance(node, ast.Constant) and isinstance(node.value, str):
                if '__' in node.value:
                    violations.append('Blocked dunder string literal')
    except SyntaxError as e:
        violations.append(f'Syntax error: {e}')

    return {'ok': len(violations) == 0, 'violations': violations}


def create_sandbox_globals() -> dict:
    """Create a restricted globals dict for plugin execution."""
    import builtins

    safe_builtins = {}
    for name in ALLOWED_BUILTINS:
        # Hard deny-list wins over the allow-list, so a future edit that
        # re-adds a traversal helper to ALLOWED_BUILTINS cannot re-expose it.
        if name in DENIED_BUILTINS:
            continue
        if hasattr(builtins, name):
            safe_builtins[name] = getattr(builtins, name)
    # belt and suspenders: also strip any denied name that slipped in.
    for name in DENIED_BUILTINS:
        safe_builtins.pop(name, None)

    return {
        '__builtins__': safe_builtins,
        '__name__': '__sandbox__',
        '__doc__': None,
    }


def execute_plugin_sandboxed(code: str, context: dict = None, timeout_ms: int = 5000) -> dict:
    """Execute plugin code in a sandboxed environment.

    Args:
        code: Python code string to execute
        context: Variables to inject into the sandbox namespace
        timeout_ms: Maximum execution time in milliseconds

    Returns:
        {'ok': True, 'result': ..., 'output': ...} or {'ok': False, 'error': ...}
    """
    # Validate first
    validation = validate_plugin_code(code)
    if not validation['ok']:
        return {
            'ok': False,
            'error': f'Sandbox violation: {"; ".join(validation["violations"][:3])}',
            'violations': validation['violations'],
        }

    # Create sandbox
    sandbox = create_sandbox_globals()
    if context:
        for k, v in context.items():
            if not k.startswith('_'):
                sandbox[k] = v

    # Execute with timing
    t0 = time.time()
    try:
        compiled = compile(code, '<plugin>', 'exec')
        exec(compiled, sandbox)
        elapsed_ms = (time.time() - t0) * 1000

        if elapsed_ms > timeout_ms:
            return {'ok': False, 'error': f'Execution timeout ({elapsed_ms:.0f}ms > {timeout_ms}ms)'}

        # Extract result (plugins should set a 'result' variable)
        result = sandbox.get('result', None)
        output = sandbox.get('output', '')

        return {
            'ok': True,
            'result': result,
            'output': str(output) if output else '',
            'elapsed_ms': round(elapsed_ms, 1),
        }
    except SandboxViolationError as e:
        return {'ok': False, 'error': f'Sandbox violation: {e}'}
    except Exception as e:
        return {'ok': False, 'error': f'{type(e).__name__}: {e}'}
