"""
Plugin sandbox escape regression.

The plugin sandbox runs third-party plugin code via `exec(code, sandbox)` with a
static gate (`validate_plugin_code`). The gate is a blacklist-checking AST scan,
but the runtime `__builtins__` still exposed `getattr`, `type` and `setattr`.
That allowed a payload that PASSES static validation to alias `getattr` and
traverse the Python object graph to reach real `__builtins__['open']` — proving
arbitrary file read (and, by the same primitive, arbitrary code execution).

Regression guard: no payload that passes `validate_plugin_code` may be able to
reach `fork`/`open`/`system`/`subprocess`/`__builtins__` via object traversal.
"""
from __future__ import annotations

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[2]))

from backend.services.plugin_sandbox import (  # noqa: E402
    execute_plugin_sandboxed,
    validate_plugin_code,
)

# The exact class of payload that previously escaped: no literal dunder, no
# blocked module keyword, no 'open(' call, all built via getattr + chr().
ESCAPE_PAYLOAD = (
    "G = getattr\n"
    "u = chr(95)*2\n"
    "ob = G(G((), u+'class'+u), u+'mro'+u)[1]\n"
    "subs = G(ob, u+'subclasses'+u)()\n"
    "gd = None\n"
    "for c in subs:\n"
    "    m = G(c, u+'init'+u, None)\n"
    "    if m is None:\n"
    "        continue\n"
    "    d = G(m, u+'globals'+u, None)\n"
    "    if isinstance(d, dict) and u+'builtins'+u in d:\n"
    "        gd = d\n"
    "        break\n"
    "b = gd[u+'builtins'+u]\n"
    "b['open']('/etc/hostname').read()\n"
)


def test_escape_payload_is_rejected_by_validation():
    """The static gate must refuse an object-graph-traversal payload.

    Previously this returned `{'ok': True}` — the escape payload sailed through
    validation and read files at runtime.
    """
    result = validate_plugin_code(ESCAPE_PAYLOAD)
    assert result['ok'] is False, (
        f"escape payload passed validation: {result.get('violations')}"
    )


def test_escape_payload_cannot_read_files_at_execution():
    """Even if validation were somehow bypassed, execution must not reach open."""

    result = execute_plugin_sandboxed(ESCAPE_PAYLOAD)
    # Must not succeed (no benign 'ok: True' with a read file).
    assert result['ok'] is False, 'escape payload executed successfully'
    # And no file content may leak into the output.
    out = str(result.get('output', ''))
    assert 'e2b' not in out and 'localhost' not in out


def test_getattr_and_type_are_not_handed_to_plugin_code():
    """The runtime builtins must not expose object-graph traversal helpers."""
    from backend.services.plugin_sandbox import create_sandbox_globals

    g = create_sandbox_globals()
    b = g.get('__builtins__', {})
    for n in ('getattr', 'type', 'setattr', 'delattr', 'vars', 'dir', 'globals', 'locals'):
        assert n not in b, f'{n} must not be exposed to plugin code'
