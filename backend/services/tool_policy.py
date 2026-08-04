"""Per-agent authorisation for MCP tool calls.

WHY THIS EXISTS
───────────────
`agent_permissions` has existed since Sprint A. It is populated on provisioning
(`_seed_default_permissions`), exposed on agent cards, and counted in the
identity UI — and **nothing has ever consulted it to authorise anything**. The
only two readers in the codebase (`a2a.get_agent_card`,
`mcp_gateway.get_agent_card`) both use it for DISPLAY.

Verified live against a running server, with an agent holding neither
`write_files` nor `delete_files`:

    POST /api/mcp/call {"tool":"fs.write",  "agent_id":"probe_readonly"} -> ok
    POST /api/mcp/call {"tool":"fs.delete", "agent_id":"probe_readonly"} -> ok
    POST /api/mcp/call {"tool":"fs.write",  "agent_id":"i_do_not_exist"} -> ok

The last one matters most: a completely fictional agent id wrote a file. The
`agent_id` field was carried through the whole call path — accepted, logged,
echoed back in the response, recorded in the audit chain — and never once used
to make a decision. That is worse than having no field at all, because the
audit trail reads as though authorisation happened.

DESIGN
──────
1. TOOL → ACTION mapping, not tool → tool. Permissions are already expressed as
   coarse verbs (`read_files`, `write_files`, `run_code`), which is the right
   granularity: it survives new tools being added, and an operator reasoning
   about "can this agent write files" should not have to enumerate `fs.write`,
   `fs.append`, `git.commit`.

2. DENY BY DEFAULT for unknown agents, ALLOW for unmapped tools.
   Those look inconsistent; they are not. An unknown *agent* is an
   authentication failure — there is no basis for any decision. An unmapped
   *tool* is an omission in this file, and failing closed there would break
   every caller the moment someone adds a tool without touching the map. The
   map is checked by a test that fails when a tool has no mapping, so the gap
   gets closed at review time rather than in production.

3. `system` is the platform itself, not an agent. Internal callers that pass no
   agent_id must keep working; enforcement applies to identified agents. This is
   deliberately explicit rather than implicit-by-omission.

4. High-risk tools require an explicit grant even for elevated agents. See
   HIGH_RISK: `shell.run` and `http.get` are the two primitives this review has
   repeatedly found to be the sharp edges (Module 12's interpreter bypass,
   Module 20's agent-callable SSRF).
"""

from __future__ import annotations

import logging

log = logging.getLogger('agentic.tool_policy')

# The pseudo-agent used by internal platform code paths. Not subject to
# per-agent policy: it IS the platform.
SYSTEM_AGENTS = frozenset({'system', '', None})

# Tool name -> the coarse permission action it requires.
TOOL_ACTIONS: dict[str, str] = {
    # Filesystem
    'fs.read': 'read_files',
    'fs.list': 'read_files',
    'fs.exists': 'read_files',
    'fs.write': 'write_files',
    'fs.delete': 'delete_files',
    # Shell / code execution
    'shell.run': 'run_code',
    'shell.run_background': 'run_code',
    # code.run executes a Python snippet and was entirely absent from this map
    # in my first version -- meaning the "unmapped tools are allowed" default
    # would have handed arbitrary Python execution to every agent, including
    # unknown ones. Found by test_tool_map_covers_every_registered_tool, which
    # is precisely why that guard exists rather than trusting the map to stay
    # complete.
    'code.run': 'run_code',
    # Git
    'git.status': 'read_files',
    'git.log': 'read_files',
    'git.diff': 'read_files',
    'git.commit': 'write_files',
    'git.checkout': 'write_files',
    # Network
    'http.get': 'web_search',
    'http.post': 'send_webhook',
    'search.web': 'web_search',
    # Memory
    'memory.add': 'write_chat',
    'memory.search': 'read_memory',
    'memory.list': 'read_memory',
    # Browser
    'browser.navigate': 'web_search',
    'browser.click': 'web_search',
    'browser.screenshot': 'web_search',
    'browser.extract_text': 'web_search',
    # Database / tasks
    'db.query': 'read_memory',
    'tasks.list': 'read_tasks',
    'tasks.create': 'write_tasks',
    # Pure computation, no side effects and no I/O.
    'json.parse': 'use_tools',
}

# Tools that need their action granted EXPLICITLY — never satisfied by a
# blanket 'use_tools'. These are the primitives that have produced the sharpest
# findings in this review: arbitrary command execution and arbitrary outbound
# HTTP from an agent.
HIGH_RISK: frozenset[str] = frozenset({
    'shell.run', 'shell.run_background', 'http.post',
    # Every MUTATING tool requires its action explicitly. My first version left
    # fs.write out, and the standard authority level grants 'use_tools' but not
    # 'write_files' -- so the wildcard silently re-opened the exact bypass this
    # module was written to close: an agent with no write permission wrote a
    # file and got HTTP 200. Caught by re-running the original reproduction
    # against the fix instead of assuming it worked.
    #
    # The rule that follows: 'use_tools' is a convenience grant for READ-shaped
    # tools. Anything that changes state on disk, in the repo, or on another
    # system needs its own permission.
    'fs.write', 'fs.delete', 'git.commit', 'git.checkout', 'code.run',
})

# A blanket grant that satisfies ordinary tools but never HIGH_RISK ones.
WILDCARD_ACTION = 'use_tools'


class ToolDeniedError(PermissionError):
    """Raised when an agent is not authorised for a tool."""

    def __init__(self, agent_id: str, tool: str, action: str, reason: str):
        self.agent_id = agent_id
        self.tool = tool
        self.action = action
        self.reason = reason
        super().__init__(reason)


def required_action(tool: str) -> str | None:
    """The permission action a tool needs, or None if unmapped."""
    return TOOL_ACTIONS.get(tool)


def _agent_actions(agent_id: str) -> set[str] | None:
    """Granted actions for an agent, or None if the agent has no identity.

    None and set() mean different things: None is "no such agent" (deny), an
    empty set is "a real agent with nothing granted" (also deny, but for a
    reason the operator can act on).
    """
    try:
        from .memory_db import get_conn
    except Exception:  # pragma: no cover
        return None

    con = get_conn()
    try:
        ident = con.execute(
            'SELECT agent_id, status FROM agent_identities WHERE agent_id=?', (agent_id,)
        ).fetchone()
        if not ident:
            return None
        if (ident['status'] or 'active') not in ('active', ''):
            return set()
        rows = con.execute(
            'SELECT action FROM agent_permissions WHERE agent_id=? '
            "AND (expires_at = '' OR expires_at > datetime('now'))",
            (agent_id,),
        ).fetchall()
        return {r['action'] for r in rows}
    except Exception as e:
        # A policy lookup that fails must not silently authorise. Returning None
        # denies, and the error is loud.
        log.error('tool_policy: permission lookup failed for %s: %s', agent_id, e)
        return None
    finally:
        con.close()


def check_tool_permission(agent_id: str, tool: str) -> tuple[bool, str]:
    """Return (allowed, reason). Reason is empty when allowed."""
    if agent_id in SYSTEM_AGENTS:
        return True, ''

    action = required_action(tool)
    if action is None:
        # Unmapped tool: allow, but say so in the log. Failing closed here would
        # break every caller the moment a tool is added; a test enumerates the
        # map so the gap is caught at review time instead.
        log.warning('tool_policy: %r has no action mapping — allowing by default', tool)
        return True, ''

    granted = _agent_actions(agent_id)
    if granted is None:
        return False, (
            f"Unknown agent '{agent_id}'. Tool calls must come from a provisioned "
            f'agent identity, or omit agent_id for internal system calls.'
        )

    if action in granted:
        return True, ''

    if tool not in HIGH_RISK and WILDCARD_ACTION in granted:
        return True, ''

    if tool in HIGH_RISK and WILDCARD_ACTION in granted:
        return False, (
            f"Agent '{agent_id}' has general tool access but '{tool}' is high-risk "
            f"and needs the '{action}' permission granted explicitly."
        )

    return False, (
        f"Agent '{agent_id}' is not permitted to use '{tool}' "
        f"(requires '{action}')."
    )


def require_tool_permission(agent_id: str, tool: str) -> None:
    """Raise ToolDeniedError if the agent may not use the tool."""
    allowed, reason = check_tool_permission(agent_id, tool)
    if not allowed:
        raise ToolDeniedError(agent_id, tool, required_action(tool) or '', reason)


def allowed_tools(agent_id: str) -> list[str]:
    """Every tool this agent may call. Powers the UI and agent cards."""
    if agent_id in SYSTEM_AGENTS:
        return sorted(TOOL_ACTIONS)
    return sorted(t for t in TOOL_ACTIONS if check_tool_permission(agent_id, t)[0])
