"""
Agentic OS — Jev decision service (TypeSafe System One)

Jev (https://docs.typesafe.ai) is NOT a text-generation model. It is a
System One decision model: you send a `state` plus a set of typed
QUESTIONS, and it returns structured answers your code can branch on:

    Choice  — pick one option from a described set  -> choice, probabilities,
                                                           confidence
    Score   — rate the state against ordered levels -> score, probabilities,
                                                           confidence
    Noul    — "is this statement true?"             -> noul (0..1)

All questions in one call are evaluated in parallel and in isolation, so
a fan-out of N questions costs one round-trip and does not rot the
context. There is nothing to parse: no JSON-in-prose, no regex over a
chatty model's answer. That property is why this service exists as its
own layer next to llm.py rather than as another provider entry there —
`complete()` returns text; this returns decisions.

Wiring decisions, recorded so they are not re-litigated:

  * RAW HTTP, not typesafe-sdk. The API is a single endpoint
    (POST /v1/systemone, Bearer auth, one JSON body); httpx is already
    pinned, and a second HTTP stack would double the failure surface the
    tests have to reason about. The env seam below keeps the mock
    topology (scripts/mock_llm.py) usable exactly like OPENROUTER_BASE_URL.

  * The API key is read from the environment AT CALL TIME
    (TYPESAFE_API_KEY). The vault injects global secrets into
    os.environ at boot, so a key stored in the vault is picked up with
    no code change — and a key set later in the process is honoured
    without a restart.

  * Cost + observability are recorded HERE, not at call sites, for the
    same reason llm.complete() records them centrally: the one time a
    caller forgets is the one time the FinOps pane lies. Jev reports
    token usage but the docs do not publish a price, so cost_usd is
    tokens * JEV_USD_PER_1K_TOKENS / 1000 (default 0) — the ledger
    tracks usage from day one and turns into dollars the moment a price
    is configured.

  * Unconfigured raises JevUnavailableError (mirroring
    LLMUnavailableError; app.py maps it to an honest 503). Feature
    integrations must NOT make users pay for our integration: they use
    ask_or_none(), which swallows every failure and returns None so the
    caller keeps its existing behaviour. Jev is an upgrade, not a
    dependency.
"""

from __future__ import annotations

import asyncio
import logging
import os
import time
from typing import Any

import httpx

log = logging.getLogger('agentic.jev')

# ── Configuration (all overridable; base URL seam is how tests and the mock
# topology redirect traffic without monkeypatching) ──────────────────────────
JEV_BASE_URL = os.environ.get('JEV_BASE_URL', 'https://api.typesafe.ai').rstrip('/')
JEV_MODEL = os.environ.get('JEV_MODEL', 'jev-latest')
JEV_TIMEOUT = float(os.environ.get('JEV_TIMEOUT', '20'))
JEV_API_KEY_ENV = 'TYPESAFE_API_KEY'
API_PATH = '/v1/systemone'

# Protective caps. The docs do not publish request limits; these are not
# claims about the service, they are backstops so a bug in OUR callers
# cannot build an unbounded request.
MAX_QUESTIONS = 32
MAX_STATE_BYTES = 200_000

# Price per 1k tokens (in+out combined), as a string env for consistency with
# the rest of the config. 0 until TypeSafe publishes pricing.
JEV_USD_PER_1K_TOKENS = float(os.environ.get('JEV_USD_PER_1K_TOKENS', '0') or 0)


class JevUnavailableError(Exception):
    """Jev cannot answer: not configured, unreachable, or returned an error.

    Mirrors LLMUnavailableError so app.py can map both to an honest 503
    with setup guidance instead of letting a missing key surface as a
    fabricated success.
    """

    def __init__(self, message: str, detail: str = ''):
        super().__init__(message)
        self.message = message
        self.detail = detail


def _api_key() -> str:
    """Call-time key read (vault injection / runtime updates both work)."""
    return (os.environ.get(JEV_API_KEY_ENV) or '').strip()


def is_configured() -> bool:
    """Whether a Jev API key is present. Cheap; call freely.

    Feature integrations gate on this so an unconfigured deployment keeps
    its existing behaviour with zero added latency.
    """
    return bool(_api_key())


# ── Question builders ─────────────────────────────────────────────────────────
# Plain dicts, not classes: raw httpx was chosen precisely so there is no SDK
# type system to mirror, and dict literals compose in the caller's own code.
# These helpers exist for validation-at-construction and readability.

def choice(instructions: str, criteria: dict[str, str]) -> dict:
    """A Choice question: pick one option from a described set.

    `criteria` maps option id -> short description of when to pick it.
    """
    if not isinstance(criteria, dict) or len(criteria) < 2:
        raise ValueError('choice criteria must be a dict of >= 2 options')
    return {'type': 'choice', 'instructions': instructions, 'criteria': dict(criteria)}


def score(instructions: str, criteria: list[str]) -> dict:
    """A Score question: rate the state against ordered, descriptive levels.

    `criteria` is ordered worst->best (or otherwise monotone); the answer's
    `score` is the index into it.
    """
    if not isinstance(criteria, (list, tuple)) or len(criteria) < 2:
        raise ValueError('score criteria must be a list of >= 2 ordered levels')
    return {'type': 'score', 'instructions': instructions, 'criteria': list(criteria)}


def noul(instructions: str) -> dict:
    """A Noul question: the probability that the statement is true."""
    return {'type': 'noul', 'instructions': instructions}


def _validate_questions(questions: dict[str, dict]) -> dict[str, dict]:
    if not isinstance(questions, dict) or not questions:
        raise ValueError('questions must be a non-empty dict of question_key -> question')
    if len(questions) > MAX_QUESTIONS:
        raise ValueError(f'too many questions ({len(questions)} > {MAX_QUESTIONS})')
    out: dict[str, dict] = {}
    for key, q in questions.items():
        if not isinstance(key, str) or not key:
            raise ValueError('question keys must be non-empty strings')
        if not isinstance(q, dict):
            raise ValueError(f'question {key!r} must be a dict')
        qtype = q.get('type')
        instr = q.get('instructions')
        if qtype not in ('choice', 'score', 'noul'):
            raise ValueError(f'question {key!r}: type must be choice|score|noul')
        if not isinstance(instr, str) or not instr.strip():
            raise ValueError(f'question {key!r}: instructions must be a non-empty string')
        crit = q.get('criteria')
        if qtype == 'choice':
            if not isinstance(crit, dict) or len(crit) < 2 or len(crit) > 24:
                raise ValueError(f'question {key!r}: choice criteria must be a dict of 2..24 options')
            if not all(isinstance(v, str) and v for v in crit.values()):
                raise ValueError(f'question {key!r}: choice criteria values must be non-empty strings')
        elif qtype == 'score':
            if not isinstance(crit, (list, tuple)) or len(crit) < 2 or len(crit) > 10:
                raise ValueError(f'question {key!r}: score criteria must be a list of 2..10 ordered levels')
            if not all(isinstance(v, str) and v for v in crit):
                raise ValueError(f'question {key!r}: score levels must be non-empty strings')
        # noul needs no criteria
        out[key] = q
    return out


# ── The one HTTP seam ─────────────────────────────────────────────────────────
# Everything above is pure; everything below talks to the network. Tests and
# the mock topology hook here (or redirect JEV_BASE_URL), which keeps the
# request-building and answer-parsing logic testable without sockets.

async def _post_json(url: str, headers: dict, payload: dict, timeout: float) -> dict:
    """Issue the POST and return the parsed JSON body. Raises on any failure."""
    async with httpx.AsyncClient(timeout=timeout) as client:
        r = await client.post(url, headers=headers, json=payload)
    if r.status_code != 200:
        # Surface the service's own error text when present — it is the only
        # thing an operator can act on.
        detail = ''
        try:
            detail = str((r.json() or {}).get('error') or r.text or '')[:300]
        except Exception:
            detail = (r.text or '')[:300]
        raise JevUnavailableError(f'Jev API returned HTTP {r.status_code}', detail=detail)
    try:
        return r.json()
    except Exception as e:
        raise JevUnavailableError('Jev API returned a non-JSON body', detail=str(e)[:200]) from e


async def ask(
    state: str,
    questions: dict[str, dict],
    *,
    agent_id: str = 'jev',
    model: str = '',
    timeout: float | None = None,
) -> dict:
    """Ask Jev a batch of typed questions against one state.

    Returns:
        {
          'ok': True,
          'model': <served model, e.g. 'jev-1.13.0'>,
          'answers': {key: {'type', ...answer fields..., 'confidence'?, 'probabilities'?}},
          'usage': {'input_tokens', 'output_tokens'},
          'latency_ms': int,
        }

    Raises:
        JevUnavailableError — no key configured, request failed, or the
        response was malformed. Never returns ok=False; failure is an
        exception so no caller can mistake it for an answer.
    """
    if not isinstance(state, str) or not state.strip():
        raise ValueError('state must be a non-empty string')
    if len(state.encode('utf-8', errors='ignore')) > MAX_STATE_BYTES:
        raise ValueError(f'state exceeds {MAX_STATE_BYTES} bytes')
    questions = _validate_questions(questions)

    # Key check AFTER validation: a malformed question is the caller's bug
    # and deserves a 400 even on an unconfigured deployment; a missing key is
    # an environment fact and deserves the 503. Checking in this order means
    # the playground can be developed against validation alone.
    key = _api_key()
    if not key:
        raise JevUnavailableError(
            f'No {JEV_API_KEY_ENV} set — Jev decisions are unavailable.',
            detail='Store the key in the vault (secrets, scope global) or set the env var.',
        )

    payload = {'state': state, 'model': model or JEV_MODEL, 'questions': questions}
    t0 = time.perf_counter()
    body = await _post_json(
        f'{JEV_BASE_URL}{API_PATH}',
        {'Authorization': f'Bearer {key}', 'Content-Type': 'application/json'},
        payload,
        timeout if timeout is not None else JEV_TIMEOUT,
    )
    latency_ms = int((time.perf_counter() - t0) * 1000)

    answers = body.get('answers')
    if not isinstance(answers, dict) or not answers:
        raise JevUnavailableError('Jev API response missing answers', detail=str(body)[:300])
    usage = body.get('usage') or {}
    result = {
        'ok': True,
        'model': str(body.get('model') or payload['model']),
        'answers': answers,
        'usage': {
            'input_tokens': int(usage.get('input_tokens') or 0),
            'output_tokens': int(usage.get('output_tokens') or 0),
        },
        'latency_ms': latency_ms,
    }
    _record(agent_id, result, state, questions)
    return result


async def ask_or_none(
    state: str,
    questions: dict[str, dict],
    *,
    agent_id: str = 'jev',
    model: str = '',
    timeout: float | None = None,
) -> dict | None:
    """Fail-open wrapper for FEATURE integrations.

    Chat re-ranking, arena judging, confidence routing: these are upgrades
    on top of behaviour that already works. If Jev is unconfigured,
    unreachable, slow, or returns garbage, the integration must degrade to
    the pre-existing path — a missing decision model must never break a
    feature that predates it. Only ask() (the explicit, human-driven
    management endpoint) lets failures surface.
    """
    try:
        return await ask(state, questions, agent_id=agent_id, model=model, timeout=timeout)
    except (JevUnavailableError, ValueError, OSError, asyncio.TimeoutError, httpx.HTTPError) as e:
        log.info('Jev decision skipped (%s): %s', type(e).__name__, getattr(e, 'message', e))
        return None


# ── Recording (cost ledger + observability), never raises into the caller ────

def _record(agent_id: str, result: dict, state: str, questions: dict[str, dict]) -> None:
    """One Jev call -> cost ledger row + obs trace. Failures are logged, not raised.

    Same contract as llm._record_llm_cost: a recording failure must not fail
    the decision the caller asked for, but it must be loud.
    """
    usage = result.get('usage') or {}
    tokens_in = int(usage.get('input_tokens') or 0)
    tokens_out = int(usage.get('output_tokens') or 0)
    tokens = tokens_in + tokens_out
    cost = round((tokens / 1000.0) * JEV_USD_PER_1K_TOKENS, 6)
    if tokens <= 0 and cost <= 0:
        return
    model = str(result.get('model') or JEV_MODEL)
    latency_ms = int(result.get('latency_ms') or 0)
    keys = ','.join(sorted(questions.keys()))[:200]
    try:
        from ..routers.finops import record_cost

        record_cost(
            agent_id=agent_id or 'jev',
            source_type='jev',
            cost_usd=cost,
            tokens=tokens,
            tokens_in=tokens_in,
            tokens_out=tokens_out,
            model=model,
            description=f'jev questions: {keys}',
            latency_ms=latency_ms,
        )
    except Exception as e:  # pragma: no cover
        log.warning('Jev cost recording failed: %s', e)
    try:
        from ..routers.observability import record_llm_trace

        record_llm_trace(
            agent_id=agent_id or 'jev',
            name=f'jev:{model}',
            prompt=(state or '')[:500],
            output=keys,
            tokens=tokens,
            cost=cost,
            latency_ms=latency_ms,
            model=model,
            status='success',
        )
    except Exception as e:  # pragma: no cover
        log.debug('Jev trace emit failed: %s', e)
