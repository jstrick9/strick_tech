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
ALLOWED_BUILTINS = {
    'abs', 'all', 'any', 'bool', 'chr', 'dict', 'divmod', 'enumerate',
    'filter', 'float', 'format', 'frozenset', 'getattr', 'hasattr', 'hash',
    'hex', 'int', 'isinstance', 'issubclass', 'iter', 'len', 'list', 'map',
    'max', 'min', 'next', 'oct', 'ord', 'pow', 'print', 'range', 'repr',
    'reversed', 'round', 'set', 'setattr', 'slice', 'sorted', 'str', 'sum',
    'tuple', 'type', 'zip',
}

# ── Dangerous constructs that must not appear in plugin code ────────────────
BLOCKED_MODULES = {
    'os', 'sys', 'subprocess', 'shutil', 'pathlib', 'socket', 'http',
    'urllib', 'requests', 'httpx', 'ctypes', 'importlib', 'code',
    'codeop', 'compile', 'compileall', 'py_compile',
    'multiprocessing', 'threading', 'signal',
    'shelve', 'sqlite3', 'dbm',
    'pickle', 'shelve', 'marshal',
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


class SandboxViolation(Exception):
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

    # Check blocked module imports
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
    except SyntaxError as e:
        violations.append(f'Syntax error: {e}')

    return {'ok': len(violations) == 0, 'violations': violations}


def create_sandbox_globals() -> dict:
    """Create a restricted globals dict for plugin execution."""
    import builtins

    safe_builtins = {}
    for name in ALLOWED_BUILTINS:
        if hasattr(builtins, name):
            safe_builtins[name] = getattr(builtins, name)

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
    except SandboxViolation as e:
        return {'ok': False, 'error': f'Sandbox violation: {e}'}
    except Exception as e:
        return {'ok': False, 'error': f'{type(e).__name__}: {e}'}
