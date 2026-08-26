"""The walk test as a gate, not a report.

Closes G11. The canon calls the walk test the ACCEPTANCE CRITERION:

    "Every result gets checked cold. An agent with no memory has to open the
     root, find its way, act, and report status from the files alone. If it
     can't, the structure gets fixed until it can."

`icm.validate()` has always run those checks. Nothing ever acted on the result,
which made it a report rather than a criterion.

WHY THAT MATTERS, MEASURED LIVE BEFORE WRITING THIS

Delete one stage contract -- L2, the control point that scopes what a stage
loads -- and the platform behaves like this:

    /validate            ok: False, "stages/01-gather has no CONTEXT.md"
    /api/icm/route       status: matched, stage: 01-gather
    POST /api/chat       200, route-log: matched, 214 tokens

The validator KNEW. The router routed anyway, the agent was handed a context
with no stage contract in it, and the route log recorded a normal-looking run.
Nothing anywhere said the workspace was broken. That is the dominant defect
family in this codebase -- confident reporting of unverified things -- and the
fix is to make the check load-bearing at the one place where being wrong is
expensive: the moment a workspace is about to be fed to a model.

WHAT THIS GATE DOES *NOT* DO

It does not block writes. "Every output is an edit surface" is an invariant,
and a validator that refuses to let a human save a half-finished contract makes
the workspace unusable exactly when it is being repaired. Editing is how a
broken workspace gets fixed; gating the repair path would be perverse.

So the gate sits on the READ side:

    write   -> always allowed, warnings returned alongside the save
    route   -> a workspace failing the walk test is not silently used
    run     -> refuses, and says which check failed and how to fix it

Severity is honest about the difference between "broken" and "untidy":
`validate()` already separates errors from warnings, and only errors gate.
A workspace with a long CONTEXT.md is not a workspace that will mislead a model.
"""

from __future__ import annotations

import time
from pathlib import Path
from typing import Any

# How long a passing result stays trusted. Validation walks the whole tree, and
# the router runs on every chat turn; re-walking per turn would put a
# filesystem crawl in the hot path. Short enough that a repair is picked up
# almost immediately.
CACHE_SECONDS = 5.0

# Errors mean "an agent reading this will be misled". These are the checks that
# gate. Anything else validate() reports is a warning and never blocks.
_cache: dict[str, tuple[float, dict[str, Any]]] = {}


def clear_cache() -> None:
    _cache.clear()


def check(ws: Path, use_cache: bool = True) -> dict[str, Any]:
    """Run the walk test on a workspace and cache the verdict briefly."""
    from . import icm

    key = str(ws)
    now = time.time()
    if use_cache:
        hit = _cache.get(key)
        if hit and (now - hit[0]) < CACHE_SECONDS:
            return hit[1]

    result = icm.validate(ws)
    verdict = {
        'workspace_id': ws.name,
        'passes': bool(result.get('ok')),
        'errors': list(result.get('errors') or []),
        'warnings': list(result.get('warnings') or []),
        'walk_test': result.get('walk_test') or {},
        'checked_at': now,
    }
    _cache[key] = (now, verdict)
    return verdict


def _remedy(error: str) -> str:
    """Turn a validator error into the thing a person should actually do.

    A gate that blocks without saying how to unblock is a gate people route
    around. Every refusal has to carry its own repair instruction.
    """
    e = error.lower()
    if 'no context.md' in e and 'stages/' in e:
        return 'Add a CONTEXT.md to that stage declaring its Inputs, Process and Outputs.'
    if 'no l0 identity' in e:
        return 'Add an IDENTITY.md at the workspace root saying what this workspace is.'
    if 'no l1 context.md' in e:
        return 'Add a CONTEXT.md at the workspace root routing to the stages.'
    if 'numbered stages' in e:
        return 'Add at least one stages/NN-name/ folder — the numbering is the execution order.'
    if 'duplicate stage number' in e:
        return 'Renumber one of the stages so the order is unambiguous.'
    if 'runs later' in e or 'point backwards' in e:
        return 'A stage may only read from earlier stages. Fix that Inputs row.'
    if 'is missing' in e:
        return 'Recreate the missing file; this form needs it to be walkable.'
    return 'Open the workspace and fix the structure until the walk test passes.'


def gate(ws: Path, action: str = 'run') -> dict[str, Any]:
    """Decide whether a workspace may be used. Returns a refusal, not an error.

    Callers get a dict rather than an exception because every caller here is on
    a path where a raised exception would surface as a 500 to somebody who did
    nothing wrong. A refusal is data: it can be logged, shown, and acted on.
    """
    verdict = check(ws)
    if verdict['passes']:
        return {'allowed': True, **verdict}
    return {
        'allowed': False,
        'action': action,
        'reason': (
            f'{ws.name} does not pass the walk test, so an agent reading it would be '
            f'working from an incomplete structure.'
        ),
        'remedies': [{'error': e, 'fix': _remedy(e)} for e in verdict['errors']],
        **verdict,
    }


def gate_workspace_id(workspace_id: str, action: str = 'run') -> dict[str, Any]:
    from . import icm

    ws = icm.workspace_dir(workspace_id)
    if ws is None or not ws.is_dir():
        return {'allowed': False, 'action': action, 'passes': False,
                'workspace_id': workspace_id,
                'reason': f'workspace {workspace_id!r} does not exist',
                'errors': ['workspace not found'], 'warnings': [], 'remedies': []}
    return gate(ws, action)


def audit_all() -> dict[str, Any]:
    """Walk-test every workspace. The dashboard answer to "what is broken?"."""
    from . import icm

    root = icm.WORKSPACES_DIR
    if not root.is_dir():
        return {'total': 0, 'passing': 0, 'failing': 0, 'workspaces': []}

    rows: list[dict[str, Any]] = []
    for d in sorted(root.iterdir()):
        if not d.is_dir() or d.name.startswith('.') or not icm.WORKSPACE_ID_RE.match(d.name):
            continue
        v = check(d, use_cache=False)
        rows.append({
            'workspace_id': d.name,
            'passes': v['passes'],
            'errors': v['errors'],
            'warnings': v['warnings'],
            'remedies': [{'error': e, 'fix': _remedy(e)} for e in v['errors']],
        })
    return {
        'total': len(rows),
        'passing': sum(1 for r in rows if r['passes']),
        'failing': sum(1 for r in rows if not r['passes']),
        'workspaces': rows,
    }
