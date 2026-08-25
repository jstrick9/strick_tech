"""ICM entry routing — decide which workspace and stage a request starts in.

WHY THIS MODULE EXISTS

From Jake Van Clief's notes on ICM in practice (skool.com/cliefnotes, "Folders,
not frameworks"), the single named failure mode of the methodology at scale:

    "When you add more and more folders agents begin to skip information.
     Guidelines are missed, rules are overlooked. What worked for one person
     doesn't work for another because the model scans economically and thinks
     it knows enough. The solution is again simple, the agent has to actually
     start in the right folder. Start in a central place and the layered
     context never loads; start in the right place and the agent is instantly
     grounded. In a team, 'just cd to the correct directory' is exactly the
     kind of invisible, error-prone step that breaks repeatability."

`icm.resolve_entry()` already solves half of this: given a workspace, it
computes the correct *stage*. It does not decide the *workspace*, and until now
nothing did. chat.py picked one with a bare substring test:

    if _d.name in _msg or str(_meta.get('name','')).lower() in _msg:

which is wrong in both directions, and measurably so:

    workspace 'os'              + "what is the cost of this?"      -> MATCHED
    workspace 'client-reports'  + "write the weekly client report" -> no match

The first is a false positive ('os' is a substring of 'cost'), and it is the
worse one: the agent silently loads a wholly unrelated workspace's identity,
routing and stage contract into its system prompt and answers confidently from
it. The second is the plain miss. Both are invisible at runtime because a run
with the wrong context still looks like a run.

THE DESIGN

Routing is a declared, inspectable, logged decision, not a guess:

  * Each workspace declares what enters it in a `## Routes` section of its L1
    `CONTEXT.md` -- one bullet per trigger phrase. This keeps the routing table
    in the filesystem where the canon says state belongs, editable by a human
    with a text editor, and it means the catalog still holds no books.
  * Matching is word-boundary and phrase-aware, never bare substring.
  * Scores are additive and explained. Every decision carries the evidence
    that produced it.
  * Ambiguity is surfaced, never broken by coin-flip: when the top two
    candidates are within AMBIGUITY_MARGIN, the caller is told to ask.
  * No match is an honest outcome. Routing to nowhere and using the plain
    system prompt is correct; routing to an arbitrary workspace is not.

The route decision is returned in full so it can be shown to the user and
written to the audit log. "Which folder did you start in, and why" must be
answerable after the fact, or this module has not actually fixed anything.
"""

from __future__ import annotations

import json
import re
import time
from pathlib import Path
from typing import Any

from . import icm

# A candidate must clear this to be used at all. Below it, "no workspace" is
# the honest answer and the caller falls back to the plain system prompt.
MIN_SCORE = 2.0

# If the runner-up is within this fraction of the winner, the request is
# genuinely ambiguous and the user gets asked instead of guessed at. Picking
# arbitrarily here is precisely the silent-wrong-folder failure this module
# exists to prevent, so it is a refusal, not a tiebreak.
AMBIGUITY_MARGIN = 0.20

# Score weights. Declared routes outrank incidental name mentions because a
# route is something a human wrote down on purpose.
W_EXPLICIT = 100.0   # caller named the workspace outright
W_ROUTE_PHRASE = 6.0  # multi-word declared trigger matched
W_ROUTE_WORD = 3.0    # single-word declared trigger matched
W_NAME = 4.0          # workspace name/id appeared as whole words
W_STAGE = 1.5         # a stage name appeared as whole words

# Words too common to carry routing signal on their own. A route declaring only
# these is a route that matches everything, which is the same as no route.
STOPWORDS = frozenset((
    'a', 'an', 'and', 'are', 'as', 'at', 'be', 'but', 'by', 'do', 'does',
    'for', 'from', 'get', 'go', 'had', 'has', 'have', 'how', 'i', 'if', 'in',
    'is', 'it', 'its', 'me', 'my', 'need', 'not', 'of', 'on', 'or', 'please',
    'should', 'so', 'than', 'that', 'the', 'their', 'them', 'then', 'there',
    'these', 'they', 'this', 'to', 'up', 'us', 'use', 'want', 'was', 'we',
    'were', 'what', 'when', 'where', 'which', 'who', 'why', 'will', 'with',
    'you', 'your',
))

ROUTES_SECTION = 'Routes'
_LOG_NAME = 'route-log.jsonl'
_LOG_LIMIT = 500


def _log_path() -> Path:
    return icm.WORKSPACES_DIR / _LOG_NAME


def _words(text: str) -> list[str]:
    return re.findall(r"[a-z0-9']+", str(text).lower())


def _normalise(text: str) -> str:
    """Collapse to a space-padded lowercase word stream for phrase testing.

    Padding both ends means a phrase test is a plain `in` against token
    boundaries, so 'os' can never match inside 'cost'.
    """
    return ' ' + ' '.join(_words(text)) + ' '


def parse_routes(ws: Path) -> list[str]:
    """Read declared triggers from the `## Routes` section of L1 CONTEXT.md.

    Format is deliberately the simplest thing a human will actually maintain:

        ## Routes
        - weekly client report
        - invoice
        - billing

    Bullets only. Anything else in the section is prose and is ignored, so a
    person can explain the routes without accidentally declaring one.
    """
    text = icm._read(ws / 'CONTEXT.md')
    if not text:
        return []
    section = icm._section(text, ROUTES_SECTION)
    if not section:
        return []
    out: list[str] = []
    for line in section.splitlines():
        m = re.match(r'^\s*[-*+]\s+(.+?)\s*$', line)
        if not m:
            continue
        phrase = ' '.join(_words(m.group(1).strip().strip('`"\'')))
        if not phrase:
            continue
        # A route made only of stopwords matches nearly every message. Dropping
        # it is better than letting one lazy line capture all traffic.
        if all(w in STOPWORDS for w in phrase.split()):
            continue
        if phrase not in out:
            out.append(phrase)
    return out


def _name_terms(ws_id: str, meta: dict[str, Any]) -> list[str]:
    """Identity terms for a workspace: its id and its human name, tokenised."""
    terms: list[str] = []
    for raw in (ws_id, str(meta.get('name') or '')):
        phrase = ' '.join(w for w in _words(raw.replace('-', ' ').replace('_', ' ')))
        if not phrase:
            continue
        # No minimum-length filter here on purpose. An earlier draft dropped
        # terms under 3 characters to stop the 'os' matching 'cost' bug, but
        # word-boundary matching already prevents that, and the revert proof
        # showed no test could tell the filter's presence from its absence --
        # it was unreachable. A short workspace id is legitimate and should
        # still match when it appears as a whole word ("reset the os").
        if phrase not in terms:
            terms.append(phrase)
    return terms


def score_workspace(message: str, ws: Path, requested: str = '') -> dict[str, Any]:
    """Score one workspace against a message, with the evidence that scored it."""
    meta = icm.read_meta(ws)
    hay = _normalise(message)
    score = 0.0
    evidence: list[str] = []

    if requested and requested == ws.name:
        return {
            'workspace_id': ws.name,
            'name': meta.get('name') or ws.name,
            'score': W_EXPLICIT,
            'evidence': ['explicitly requested'],
        }

    for phrase in parse_routes(ws):
        if f' {phrase} ' in hay:
            multi = ' ' in phrase
            score += W_ROUTE_PHRASE if multi else W_ROUTE_WORD
            evidence.append(f'route: {phrase!r}')

    for term in _name_terms(ws.name, meta):
        if f' {term} ' in hay:
            score += W_NAME
            evidence.append(f'name: {term!r}')

    for stage in icm.list_stages(ws):
        slug = ' '.join(_words(str(stage.get('slug') or '').replace('-', ' ')))
        if not slug or all(w in STOPWORDS for w in slug.split()):
            continue
        if f' {slug} ' in hay:
            score += W_STAGE
            evidence.append(f'stage: {slug!r}')

    return {
        'workspace_id': ws.name,
        'name': meta.get('name') or ws.name,
        'score': round(score, 2),
        'evidence': evidence,
    }


def list_workspace_dirs() -> list[Path]:
    root = icm.WORKSPACES_DIR
    if not root.is_dir():
        return []
    return sorted(
        d for d in root.iterdir()
        if d.is_dir() and not d.name.startswith('.') and icm.WORKSPACE_ID_RE.match(d.name)
    )


def resolve(message: str, requested: str = '', stage: str = '') -> dict[str, Any]:
    """Decide where a request enters. Always returns a full, explained decision.

    Outcomes, all of them explicit:
      matched     -> workspace_id + stage + reason
      ambiguous   -> two or more near-tied candidates; caller must ask
      no-match    -> nothing cleared MIN_SCORE; use the plain prompt
    """
    dirs = list_workspace_dirs()
    decision: dict[str, Any] = {
        'matched': False,
        'workspace_id': '',
        'name': '',
        'stage': '',
        'stage_reason': '',
        'reason': '',
        'status': 'no-match',
        'candidates': [],
        'alternatives': [],
    }
    if not dirs:
        decision['reason'] = 'no workspaces exist'
        return decision

    if requested and not any(d.name == requested for d in dirs):
        # An explicit pointer at something that is not there is a caller error
        # worth reporting, not a licence to fall back to fuzzy matching.
        decision['status'] = 'not-found'
        decision['reason'] = f'requested workspace {requested!r} does not exist'
        return decision

    scored = [score_workspace(message, d, requested) for d in dirs]
    scored.sort(key=lambda c: (-c['score'], c['workspace_id']))
    decision['candidates'] = scored

    top = scored[0]
    if top['score'] < MIN_SCORE:
        decision['reason'] = (
            'no workspace declared a route for this request '
            f'(best: {top["workspace_id"]} at {top["score"]})'
        )
        return decision

    runners = [c for c in scored[1:] if c['score'] >= MIN_SCORE]
    if runners and top['score'] < W_EXPLICIT:
        gap = (top['score'] - runners[0]['score']) / top['score']
        if gap < AMBIGUITY_MARGIN:
            tied = [top] + [c for c in runners if (top['score'] - c['score']) / top['score'] < AMBIGUITY_MARGIN]
            decision['status'] = 'ambiguous'
            decision['alternatives'] = tied
            decision['reason'] = (
                'two or more workspaces match closely; ask rather than guess '
                f'({", ".join(c["workspace_id"] for c in tied)})'
            )
            return decision

    ws = icm.WORKSPACES_DIR / top['workspace_id']
    stage_dir, stage_reason = icm.resolve_entry(ws, stage)
    decision.update({
        'matched': True,
        'status': 'matched',
        'workspace_id': top['workspace_id'],
        'name': top['name'],
        'stage': stage_dir,
        'stage_reason': stage_reason,
        'reason': '; '.join(top['evidence']) or 'scored highest',
        'alternatives': [c for c in scored[1:] if c['score'] >= MIN_SCORE][:3],
    })
    return decision


def resolve_and_assemble(message: str, requested: str = '', stage: str = '') -> dict[str, Any]:
    """Route, then load exactly that stage's layered context.

    Returns the decision with `compiled_context` and the token count attached,
    so a caller gets one object carrying both what was loaded and why.
    """
    decision = resolve(message, requested, stage)
    decision['compiled_context'] = ''
    decision['estimated_tokens'] = 0
    if not decision['matched'] or not decision['stage']:
        return decision
    ws = icm.WORKSPACES_DIR / decision['workspace_id']
    ctx = icm.assemble_context(ws, decision['stage'])
    decision['compiled_context'] = ctx.get('compiled_context', '')
    decision['estimated_tokens'] = ctx.get('estimated_tokens', 0)
    decision['missing_inputs'] = ctx.get('missing_inputs', [])
    return decision


def log_decision(message: str, decision: dict[str, Any]) -> None:
    """Append the routing decision to an inspectable JSONL log.

    "Which folder did the agent start in, and why" has to be answerable after
    the run, otherwise the routing is still invisible -- just invisible with
    more code behind it. Plain text, one line per decision, per the canon.
    """
    try:
        icm.WORKSPACES_DIR.mkdir(parents=True, exist_ok=True)
        entry = {
            'at': time.time(),
            'message': str(message)[:280],
            'status': decision.get('status'),
            'workspace_id': decision.get('workspace_id'),
            'stage': decision.get('stage'),
            'reason': decision.get('reason'),
            'estimated_tokens': decision.get('estimated_tokens', 0),
        }
        path = _log_path()
        with path.open('a', encoding='utf-8') as fh:
            fh.write(json.dumps(entry) + '\n')
        # Keep the log bounded in place. An unbounded append-only file in the
        # data dir is a slow disk leak, and the recent decisions are the ones
        # anybody debugs.
        lines = path.read_text(encoding='utf-8', errors='ignore').splitlines()
        if len(lines) > _LOG_LIMIT:
            path.write_text('\n'.join(lines[-_LOG_LIMIT:]) + '\n', encoding='utf-8')
    except (OSError, TypeError, ValueError):
        # Routing must never fail because logging failed.
        pass


def recent_decisions(limit: int = 50) -> list[dict[str, Any]]:
    path = _log_path()
    if not path.is_file():
        return []
    try:
        lines = path.read_text(encoding='utf-8', errors='ignore').splitlines()
    except OSError:
        return []
    out: list[dict[str, Any]] = []
    for line in lines[-max(1, min(limit, _LOG_LIMIT)):]:
        try:
            out.append(json.loads(line))
        except ValueError:
            continue
    out.reverse()
    return out


def route_table() -> list[dict[str, Any]]:
    """The whole routing catalog: every workspace and what enters it.

    This is the root context map rendered from the filesystem rather than
    hand-maintained, because a hand-curated index always drifts.
    """
    table: list[dict[str, Any]] = []
    for d in list_workspace_dirs():
        meta = icm.read_meta(d)
        stages = icm.list_stages(d)
        entry_stage, entry_reason = icm.resolve_entry(d)
        table.append({
            'workspace_id': d.name,
            'name': meta.get('name') or d.name,
            'description': meta.get('description') or '',
            'routes': parse_routes(d),
            'stages': [s['dir'] for s in stages],
            'entry_stage': entry_stage,
            'entry_reason': entry_reason,
            'complete': sum(1 for s in stages if s.get('complete')),
            'total_stages': len(stages),
        })
    return table
