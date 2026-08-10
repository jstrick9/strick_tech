"""Module 11 regression tests — MCP Gateway policy engine.

This is the component that decides whether an agent may invoke a tool, so
every defect here is a security defect.

1. POST /policies silently discarded `conditions`. The builder UI collects a
   time window and a day-of-week set and sends them, _evaluate_policy() reads
   them, and PATCH persists them with validation -- only the INSERT dropped
   them, hardcoding '{}'. A rule created as "deny code.run between 22:00 and
   06:00" was stored unconditional and enforced 24/7.
2. /policies/from-template hardcoded conditions to '{}' as well.
3. Agent/server lists were matched with a bare `id in value.split(',')`, so
   "orchestrator, brain" -- the way a human types a list -- produced [' brain']
   and the second agent never matched. A DENY naming two agents protected only
   the first.
4. Time windows used `start <= now < end`, which is false at every hour of an
   overnight window. A 22:00-06:00 maintenance rule never activated.
5. Malformed conditions were ignored and the policy fired anyway. For a DENY
   that is safe; for an ALLOW it is a fail-open.
6. /policies/simulate reimplemented matching and evaluated NO conditions, so
   the dry-run users rely on disagreed with the enforcer it predicts.
"""

from __future__ import annotations

import json

import pytest

from backend.routers import mcp_gateway as gw


# ── 4. overnight windows ──────────────────────────────────────────────────────
@pytest.mark.parametrize('hour,expected', [
    (22, True), (23, True), (0, True), (3, True), (5, True),
    (6, False), (7, False), (16, False), (21, False),
])
def test_window_crossing_midnight(hour, expected):
    """22:00-06:00 must be active overnight. `start <= now < end` never was."""
    assert gw._window_active(22, 6, hour) is expected


@pytest.mark.parametrize('hour,expected', [
    (8, False), (9, True), (12, True), (16, True), (17, False),
])
def test_ordinary_daytime_window_still_works(hour, expected):
    assert gw._window_active(9, 17, hour) is expected


def test_equal_hours_means_all_day():
    assert gw._window_active(0, 0, 13) is True


# ── 3. comma-separated lists with whitespace ──────────────────────────────────
def test_agent_list_tolerates_spaces_after_commas():
    """'orchestrator, brain' must match BOTH agents."""
    spec = 'orchestrator, brain'
    assert gw._id_matches('orchestrator', spec) is True
    assert gw._id_matches('brain', spec) is True


def test_wildcard_matches_everything():
    assert gw._id_matches('anything', '*') is True


def test_unlisted_agent_does_not_match():
    assert gw._id_matches('researcher', 'orchestrator, brain') is False


def test_candidate_whitespace_is_tolerated():
    assert gw._id_matches(' brain ', 'orchestrator,brain') is True


def test_id_list_is_normalised_on_write():
    assert gw._normalise_id_list('orchestrator, brain ,  ops') == 'orchestrator,brain,ops'
    assert gw._normalise_id_list('') == '*'
    assert gw._normalise_id_list(None) == '*'


# ── 1/2. conditions must round-trip ───────────────────────────────────────────
def test_conditions_accepts_a_dict():
    out, err = gw._normalise_conditions({'start_hour': 22, 'end_hour': 6})
    assert err is None
    assert json.loads(out) == {'start_hour': 22, 'end_hour': 6}


def test_conditions_accepts_a_json_string():
    out, err = gw._normalise_conditions('{"days_of_week": [0, 1]}')
    assert err is None
    assert json.loads(out)['days_of_week'] == [0, 1]


def test_conditions_empty_is_an_empty_object():
    assert gw._normalise_conditions(None) == ('{}', None)
    assert gw._normalise_conditions('') == ('{}', None)


@pytest.mark.parametrize('bad,fragment', [
    ({'start_hour': 99, 'end_hour': 6}, 'between 0 and 23'),
    ({'start_hour': 22}, 'set together'),
    ({'days_of_week': [9]}, 'between 0'),
    ({'days_of_week': []}, 'non-empty'),
    ('not json at all', 'valid JSON'),
    ([1, 2, 3], 'JSON object'),
])
def test_invalid_conditions_are_rejected(bad, fragment):
    out, err = gw._normalise_conditions(bad)
    assert err is not None and fragment in err
    assert out == '{}'


def test_create_policy_persists_conditions():
    """The exact defect: the INSERT must carry conditions, not '{}'."""
    import inspect

    src = inspect.getsource(gw.create_policy)
    src = '\n'.join(ln for ln in src.split('\n') if not ln.strip().startswith('#'))
    assert '_normalise_conditions' in src
    assert "VALUES (?,?,?,?,?,?,?,?,1,?,?)" not in src, 'conditions column still missing'


def test_from_template_persists_conditions():
    import inspect

    src = inspect.getsource(gw.create_policy_from_template)
    src = '\n'.join(ln for ln in src.split('\n') if not ln.strip().startswith('#'))
    assert "'{}'" not in src, 'conditions still hardcoded empty'
    assert '_normalise_conditions' in src


# ── 5. fail-closed on malformed conditions ────────────────────────────────────
def test_malformed_conditions_do_not_grant_an_allow():
    """An ALLOW whose scope cannot be parsed must NOT fire."""
    holds, reason = gw._conditions_hold('{not json', 'allow', 12, 2)
    assert holds is False
    assert reason


def test_malformed_conditions_keep_a_deny_in_force():
    """A DENY whose scope cannot be parsed applies at full scope."""
    holds, _ = gw._conditions_hold('{not json', 'deny', 12, 2)
    assert holds is True


def test_conditions_hold_when_absent():
    assert gw._conditions_hold('{}', 'allow', 12, 2) == (True, '')


def test_day_of_week_condition():
    conds = json.dumps({'days_of_week': [0, 1, 2, 3, 4]})
    assert gw._conditions_hold(conds, 'deny', 12, 2)[0] is True   # Wednesday
    assert gw._conditions_hold(conds, 'deny', 12, 6)[0] is False  # Sunday


def test_overnight_condition_reports_a_readable_reason():
    holds, reason = gw._conditions_hold(json.dumps({'start_hour': 22, 'end_hour': 6}), 'deny', 16, 2)
    assert holds is False
    assert '22:00' in reason and '06:00' in reason


# ── 6. the simulator must not diverge from the enforcer ───────────────────────
def test_simulator_and_enforcer_share_the_matchers():
    import inspect

    sim = inspect.getsource(gw.simulate_policy)
    enf = inspect.getsource(gw._evaluate_policy)
    for src, who in ((sim, 'simulator'), (enf, 'enforcer')):
        body = '\n'.join(ln for ln in src.split('\n') if not ln.strip().startswith('#'))
        assert '_id_matches' in body, f'{who} still hand-rolls id matching'
        assert '_conditions_hold' in body, f'{who} does not evaluate conditions'


def test_simulator_no_longer_hand_rolls_split_matching():
    import inspect

    src = inspect.getsource(gw.simulate_policy)
    assert "agent_id in pol_d['agent_id'].split(',')" not in src


# ── tool matching must be case-exact ──────────────────────────────────────────
def test_tool_matching_is_case_sensitive_on_every_platform():
    """fnmatch applies os.path.normcase, which lowercases on Windows.

    A tool allow-list must not be case-insensitive on one OS and not another.
    """
    import inspect

    enf = inspect.getsource(gw._evaluate_policy)
    sim = inspect.getsource(gw.simulate_policy)
    assert 'fnmatch.fnmatchcase' in enf
    assert 'fnmatch.fnmatchcase' in sim


# ── 7. every handler the markup names must be reachable ───────────────────────
def test_every_delegated_handler_in_an_iife_pane_is_exported():
    """Systemic: 117 handlers across 14 panes were unreachable.

    The bundle concatenates frontend/js/*.js at top level, so a plain
    `function f()` in an unwrapped file becomes a global and the delegated
    dispatcher can resolve it. Fourteen panes wrap their whole body in
    `(function(...){ ... })(...)`, making their functions module-private -- so
    every `data-act-click="f()"` in those panes resolved to nothing. The
    dispatcher logs "[delegate] unknown function" and returns, so the panes
    rendered perfectly and did nothing.

    Verified dead in Chromium before the fix: all five MCP Gateway tabs, the
    policy simulator, the rule builder, plus a2aSetTab, bddDetectAll,
    gmCreateGoal, dagRefresh, lbExport, fusionRun, connectorTest and more.
    """
    import re
    from pathlib import Path

    offenders = {}
    for f in sorted(Path('frontend/js').glob('*.js')):
        src = f.read_text(encoding='utf-8')
        if not re.search(r'^\(function\s*\(', src, re.M):
            continue  # top-level file: declarations are already globals
        referenced = set()
        for attr in ('click', 'input', 'change', 'keydown', 'submit'):
            referenced |= set(re.findall(rf'data-act-{attr}="([a-zA-Z_$][\w$]*)\(', src))
        defined = {
            n for n in referenced
            if re.search(rf'^\s*(?:async\s+)?function\s+{re.escape(n)}\s*\(', src, re.M)
        }
        exported = set(re.findall(r'window\.([a-zA-Z_$][\w$]*)\s*=', src))
        missing = sorted(defined - exported)
        if missing:
            offenders[f.name] = missing

    assert not offenders, (
        'handlers defined inside an IIFE but never exported to window '
        f'(they will silently no-op): {offenders}'
    )
