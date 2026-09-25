"""Management/debug surface for the Jev decision service (TypeSafe System One).

/api/jev/status — is Jev configured, what model/endpoint would be used.
/api/jev/ask   — ad-hoc playground: state + typed questions -> answers.
                 This is the human-driven door; feature integrations use
                 services.jev.ask_or_none() and never surface here.

The ask endpoint deliberately lets JevUnavailableError propagate: a person
explicitly asking Jev something deserves the honest 503 (with setup
guidance) rather than a silent empty answer. Feature integrations fail
open instead — see services/jev.py for the split.
"""
from fastapi import APIRouter, Request
from fastapi.responses import JSONResponse

from ..services import jev
from ..services.jev import JEV_API_KEY_ENV, JEV_BASE_URL, JEV_MODEL, JEV_USD_PER_1K_TOKENS
from ..services.request_body import as_text, json_body_or_error

router = APIRouter(prefix='/api/jev', tags=['jev'])

# Public ask endpoint caps — tighter than the service's internal ones, since
# this surface is reachable by any signed-in browser while the service is
# only reachable from our own feature code.
ASK_MAX_STATE_CHARS = 50_000
ASK_MAX_QUESTIONS = 16


@router.get('/status')
def jev_status():
    """Configuration status. Never echoes the key itself."""
    return {
        'ok': True,
        'configured': jev.is_configured(),
        'model': JEV_MODEL,
        'base_url': JEV_BASE_URL,
        'api_key_env': JEV_API_KEY_ENV,
        'usd_per_1k_tokens': JEV_USD_PER_1K_TOKENS,
        'question_types': ['choice', 'score', 'noul'],
        'docs': 'https://docs.typesafe.ai',
    }


@router.post('/ask')
async def jev_ask(req: Request):
    """Ask Jev typed questions against a state (playground/debug).

    Body:
      {
        "state": "...",
        "questions": {
          "my_choice": {"type": "choice", "instructions": "...",
                        "criteria": {"a": "...", "b": "..."}},
          "my_score":  {"type": "score", "instructions": "...",
                        "criteria": ["low", "high"]},
          "my_noul":   {"type": "noul", "instructions": "..."}
        },
        "model": "jev-latest"        // optional
      }
    """
    body, _body_err = await json_body_or_error(req)
    if _body_err:
        return _body_err

    state = as_text(body.get('state'))
    if not state:
        return JSONResponse({'ok': False, 'error': 'state is required'}, status_code=400)
    if len(state) > ASK_MAX_STATE_CHARS:
        return JSONResponse(
            {'ok': False, 'error': f'state exceeds {ASK_MAX_STATE_CHARS} characters'},
            status_code=400,
        )

    questions = body.get('questions')
    if not isinstance(questions, dict) or not questions:
        return JSONResponse(
            {'ok': False, 'error': 'questions must be a non-empty {key: question} object'},
            status_code=400,
        )
    if len(questions) > ASK_MAX_QUESTIONS:
        return JSONResponse(
            {'ok': False, 'error': f'too many questions ({len(questions)} > {ASK_MAX_QUESTIONS})'},
            status_code=400,
        )

    model = as_text(body.get('model'))

    try:
        result = await jev.ask(
            state,
            questions,
            agent_id='jev_playground',
            model=model,
        )
    except ValueError as e:
        return JSONResponse({'ok': False, 'error': str(e)}, status_code=400)

    return {
        'ok': True,
        'model': result['model'],
        'answers': result['answers'],
        'usage': result['usage'],
        'latency_ms': result['latency_ms'],
    }
