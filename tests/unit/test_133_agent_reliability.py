"""The agentic core against a provider that is configured but misbehaving.

WHY THIS DIMENSION HAD NEVER BEEN MEASURED
──────────────────────────────────────────
Twenty-one audits cover the shell — panes, layout, keyboard, timezones, the
console. None touched **the product's actual reason to exist**: an LLM
answering, an agent running.

And every provider failure probed so far was one of only two states:

| State | Result |
|---|---|
| no provider configured | clean 503 with setup instructions ✓ |
| server unreachable | transport error ✓ |

Neither is the common production case. There, the provider **is** configured
and **is** reachable, and it fails *while streaming*. Those are the failures
that produce a **wrong answer** instead of an error message.

`scripts/audit/fake_provider.py` is an Ollama-compatible server that fails in
four chosen ways. Three of the four found real defects.

THE DEFECTS
───────────

**1. SILENT-TRUNCATION — the worst of the three.** The provider hung up
mid-sentence. `generate()` had a `finally` but no `except`, so the exception
propagated and the response simply stopped: no error frame, no `done`.
Measured: the reply ended at `"The answer is that "` and the UI rendered it as
a **completed answer**. The user acts on a truncated reply with nothing on
screen suggesting it was cut off.

**2. SILENT-EMPTY.** A 200 whose body has the wrong shape produced an entirely
empty stream — no text, no error, no `done`. Sending a message appeared to do
nothing at all.

**3. NO-TIMEOUT.** A provider that accepts the request and sends nothing held
the connection for **65+ seconds with zero bytes**. `httpx.AsyncClient(
timeout=120)` is a socket read timeout and an open, silent connection
satisfies it. The user watches an empty bubble with no way to tell thinking
from dead.

`error500` was already handled correctly — recorded as a result, not silence.

THE FIXES
─────────
* **A terminal-frame guarantee** in `generate()`. Whatever happens inside the
  stream loop, a `done` frame is emitted, with `truncated: true` and wording
  that distinguishes "stopped early" from "returned nothing". One fix closed
  defects 1 and 2 — they were the same missing guarantee seen from two angles.
* **A first-token timeout** (`AGENTIC_FIRST_TOKEN_TIMEOUT`, default 30s),
  separate from the total timeout. Total time is the wrong thing to bound: a
  long answer streaming steadily is healthy, a provider that has sent nothing
  is not. Stall time went 65s → **8.05s** at an 8s budget.

TWO MISTAKES OF MINE, BOTH CAUGHT BY MEASURING
──────────────────────────────────────────────
* The first timeout guard was placed at the top of `async for line in
  resp.aiter_lines()`. That body only runs when a line **arrives** — never,
  for a silent provider — so the check could not fire and the request still
  hung the full 35s. The wait itself must be bounded (`asyncio.wait_for`), not
  something inside it.
* The probe waited 25s against the app's 30s budget and reported `NO-TIMEOUT`
  for a stall the app resolves correctly. **A probe measuring its own
  impatience.** Its budget is now derived from the app's.
"""

from __future__ import annotations

import json
import re
from pathlib import Path

REPO = Path(__file__).resolve().parent.parent.parent
AUDIT = REPO / 'scripts' / 'audit'
CHAT = (REPO / 'backend' / 'routers' / 'chat.py').read_text(encoding='utf-8')
LLM = (REPO / 'backend' / 'services' / 'llm.py').read_text(encoding='utf-8')
PROBE = (AUDIT / 'agent_reliability.py').read_text(encoding='utf-8')
FAKE = (AUDIT / 'fake_provider.py').read_text(encoding='utf-8')


def _strip_py_comments(source: str) -> str:
    """So an assertion cannot be satisfied by the comment explaining the fix.

    Twelve occurrences of that in this review so far.
    """
    source = re.sub(r'"""[\s\S]*?"""', '', source)
    return re.sub(r'(?m)^\s*#.*$', '', source)


CHAT_SRC = _strip_py_comments(CHAT)
LLM_SRC = _strip_py_comments(LLM)


# ──────────────────────────────────────────────────────────────────────
#  The terminal-frame guarantee
# ──────────────────────────────────────────────────────────────────────
def test_a_mid_stream_failure_is_caught():
    """There was a `finally` but no `except`, so a provider dying mid-stream
    propagated and the response just stopped."""
    generate = CHAT_SRC[CHAT_SRC.index('async def generate('):]
    generate = generate[:generate.index('\n    return ')] if '\n    return ' in generate else generate
    assert 'except Exception' in generate, (
        'a provider failing mid-stream must not escape the generator'
    )


def test_a_terminal_frame_is_always_emitted():
    """The client treats `done` as "the answer is complete". Without one, a
    half-written reply renders as a finished one."""
    assert 'saw_done' in CHAT_SRC
    assert "'truncated': True" in CHAT_SRC


def test_the_truncation_notice_distinguishes_partial_from_empty():
    """"stopped early" and "returned nothing" need different advice: one has
    text worth keeping, the other does not."""
    assert 'stopped before finishing' in CHAT
    assert "didn't return anything" in CHAT


def test_truncated_output_is_not_ingested_into_memory():
    """An earlier batch found error text being written into long-term memory
    and re-injected into later prompts -- a self-poisoning loop. A truncated
    reply is not knowledge either."""
    block = CHAT_SRC[CHAT_SRC.index('saw_done'):]
    assert 'is_real_completion = False' in block


# ──────────────────────────────────────────────────────────────────────
#  The first-token timeout
# ──────────────────────────────────────────────────────────────────────
def test_first_token_timeout_exists_and_is_configurable():
    assert 'FIRST_TOKEN_TIMEOUT' in LLM_SRC
    assert 'AGENTIC_FIRST_TOKEN_TIMEOUT' in LLM


def test_the_wait_is_bounded_rather_than_checked_inside_the_loop():
    """THE MISTAKE. A check at the top of `async for` only runs when a line
    arrives -- which for a silent provider is never. Verified live: the
    request still hung for the full 35s."""
    assert 'asyncio.wait_for' in LLM_SRC, (
        'the wait itself must be bounded, not tested from inside it')


def test_only_the_first_token_is_bounded():
    """A long answer that is streaming steadily is healthy and must not be
    cut off; only silence is a fault."""
    assert '_first_token_seen' in LLM_SRC
    block = LLM_SRC[LLM_SRC.index('_first_token_seen'):]
    block = block[:2000]
    assert 'if _first_token_seen:' in block, (
        'once tokens flow, the deadline must no longer apply')


def test_the_timeout_emits_a_terminal_frame():
    """Closing the connection silently would leave the UI spinning."""
    # Anchor BEFORE the payload, not on the error key: 'first_token_timeout'
    # appears inside the dict, so slicing from it starts past 'done'.
    idx = LLM.index('has not responded in')
    block = LLM[max(0, idx - 400):idx + 600]
    assert "'done': True" in block
    assert "'error': 'first_token_timeout'" in block


# ──────────────────────────────────────────────────────────────────────
#  The probe
# ──────────────────────────────────────────────────────────────────────
def test_the_probe_refuses_to_run_against_the_real_provider():
    """Pointed at the unconfigured provider it would see the clean 503 path
    and report every mode as fine."""
    assert '_provider_in_use' in PROBE
    assert 'AGENTIC_FAKE_PROVIDER' in PROBE


def test_the_probe_budget_exceeds_the_application_budget():
    """It waited 25s against a 30s app budget and reported a failure the app
    was about to handle -- measuring its own impatience."""
    assert 'APP_BUDGET' in PROBE
    assert 'APP_BUDGET + 10' in PROBE


def test_the_fake_provider_covers_all_four_modes():
    for mode in ('truncate', 'stall', 'garbage', 'error500'):
        assert mode in FAKE, f'{mode} is not implemented'


def test_the_fake_provider_answers_the_liveness_probe():
    """Ollama is only considered available if /api/tags responds; without it
    the app takes the no-provider path and nothing under test runs."""
    assert '/api/tags' in FAKE


def test_the_audit_is_registered_but_not_in_the_shared_walk():
    """In the shared list it would report 0 on every ordinary run while
    measuring nothing."""
    run_all = (AUDIT / 'run_all.py').read_text(encoding='utf-8')
    assert 'agent_reliability' in run_all
    assert "    'agent_reliability',\n" not in run_all, (
        'must not be in the AUDITS list; it needs its own server'
    )
    ratchet = (REPO / 'tests' / 'unit' / 'test_120_audit_ratchet.py').read_text(
        encoding='utf-8')
    assert 'test_agent_reliability_audit_has_not_regressed' in ratchet
    baseline = json.loads((AUDIT / 'baseline.json').read_text(encoding='utf-8'))
    assert baseline.get('agent-reliability') == 0


# ──────────────────────────────────────────────────────────────────────
#  The primary provider path
# ──────────────────────────────────────────────────────────────────────
def test_the_primary_provider_base_is_overridable():
    """`OPENROUTER_BASE` was a hardcoded constant while `OLLAMA_BASE` was
    env-driven, so the PRIMARY provider had no seam for testing failure at
    all -- and turned out to carry the same stall bug, unmeasured, because
    nothing could reach it.

    Default unchanged, so no deployment behaves differently.
    """
    assert 'OPENROUTER_BASE_URL' in LLM
    assert "'https://openrouter.ai/api/v1'" in LLM


def test_both_provider_paths_bound_the_first_token_wait():
    """The Ollama path was fixed first only because it had a seam. Measured on
    the primary path once one existed: 40s of silence with an 8s budget."""
    assert LLM_SRC.count('asyncio.wait_for') >= 2, (
        'both the OpenRouter and Ollama stream loops must bound the wait')
    assert LLM_SRC.count('first_token_timeout') >= 2


def test_the_fallback_notice_leads_with_an_explanation():
    """It led with the raw httpx exception repr:

        [OpenRouter disconnected (Server error '500 Internal Server Error'
         for url '...'). Auto-falling back to local llama3.1:8b...]

    00-error-copy.js's convention is plain words first, detail in trailing
    parentheses.
    """
    assert 'OpenRouter disconnected' not in LLM
    assert 'switching to your' in LLM


def test_the_terminal_failure_message_is_human():
    assert '[stream error]' not in LLM_SRC
    assert 'could not be reached' in LLM


def test_the_probe_judges_the_headline_not_incidental_tokens():
    """The first version searched for 'HTTP 500' and 'localhost:11434'. Those
    are incidental -- the same failure through 127.0.0.1 contains neither, so a
    raw exception headline passed. And splitting the headline on '.' cut
    "llama3.1:8b" at the version number, truncating a correct message into a
    fragment that looked wrong.
    """
    assert 'looks_machine' in PROBE
    assert 'reads_human' in PROBE
    assert "re.sub(r'\\([^)]*\\)'" in PROBE, (
        'trailing parenthesised detail must be stripped, not split on')


def test_the_fake_provider_speaks_both_protocols():
    """OpenRouter is SSE with an OpenAI-shaped delta; Ollama is NDJSON. One
    fake must serve both or only half the product can be exercised."""
    assert 'openai_style' in FAKE
    assert 'choices' in FAKE
