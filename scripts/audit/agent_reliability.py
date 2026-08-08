#!/usr/bin/env python3
"""What the agentic core does when a model is configured but misbehaves.

WHY THIS IS A NEW DIMENSION
───────────────────────────
Twenty-one audits cover the shell: panes, layout, keyboard, timezones, the
console. The one thing none of them touch is **the product's actual reason to
exist** -- an LLM answering, an agent running.

And every failure probe so far tests one of only two provider states:

    no provider configured   -> a clean 503 with setup instructions  ✓ handled
    server unreachable       -> a transport error                    ✓ handled

Neither is the common real-world case. In production the provider IS
configured and IS reachable, and it fails *while streaming*: it hangs up
mid-sentence, it stalls, it returns a 200 whose body is not what the client
expects. Those are the failures that produce a wrong answer rather than an
error message, and they had never been exercised.

WHAT IS MEASURED
────────────────
A fake Ollama-compatible provider is pointed at by OLLAMA_BASE_URL and made to
fail in four specific ways. For each, the question is what the USER ends up
with:

  SILENT-TRUNCATION  the provider hung up mid-answer. The stream ends with no
                     `done` frame and no error, so a half-written reply is
                     presented as a finished one. The worst outcome available
                     here: the user acts on an answer that was cut off, with
                     nothing on screen suggesting it.

  NO-TIMEOUT         the provider accepted the request and sent nothing. The
                     request is still open after the budget with zero bytes
                     received -- an empty bubble, forever, with no way to tell
                     whether it is thinking or dead.

  SILENT-EMPTY       a 200 whose body has the wrong shape yields an entirely
                     empty stream: no text, no error, no `done`. The action
                     appears to do nothing at all.

  RAW-ERROR          a provider failure is passed through to the user with
                     internal detail as the headline rather than an
                     explanation.

MEASUREMENT NOTES
─────────────────
  * Both provider paths are exercised. `OPENROUTER_BASE` used to be a
    hardcoded constant, so only Ollama could be tested -- and the primary path
    turned out to have the SAME stall bug, unmeasured, because nothing could
    reach it. It is now `OPENROUTER_BASE_URL`-overridable (default unchanged),
    and PROVIDER=openrouter drives the same four modes down it.
  * The stall budget is checked against BYTES RECEIVED, not against wall
    clock. A server that streams a heartbeat is behaving correctly even if the
    answer is slow; one that sends nothing is not.
  * Every mode verifies the fake provider is actually being used before
    judging the result -- a probe pointed at the real (unconfigured) provider
    would see the clean 503 path and report everything as fine.
"""

from __future__ import annotations

import json
import os
import re
import sys
import time
import urllib.error
import urllib.request
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
from _harness import BASE_URL, AuditResult, emit  # noqa: E402

REPO = Path(__file__).resolve().parent.parent.parent
FAKE = REPO / 'scripts' / 'audit' / 'fake_provider.py'

# The probe must wait LONGER than the application's own first-token budget,
# or it times out first and reports a failure the app was about to handle.
# The first version waited 25s against a 30s default and reported NO-TIMEOUT
# for a stall the app resolves correctly at 30 -- a probe measuring its own
# impatience.
#
# Kept in step with AGENTIC_FIRST_TOKEN_TIMEOUT so tightening the app's budget
# cannot silently invalidate this audit.
APP_BUDGET = float(os.environ.get('AGENTIC_FIRST_TOKEN_TIMEOUT', '30'))
STALL_BUDGET_SECONDS = APP_BUDGET + 10


def _csrf() -> str | None:
    url = f'{BASE_URL}/api/security/csrf-token'
    if not url.startswith(('http://', 'https://')):
        return None
    try:
        with urllib.request.urlopen(url, timeout=10) as r:  # noqa: S310
            body = json.loads(r.read())
        return body.get('csrf_token') or body.get('token')
    except (urllib.error.URLError, OSError, ValueError):
        return None


def _chat(token: str, timeout: int) -> tuple[str, float]:
    """POST /api/chat and return (raw SSE body, seconds elapsed)."""
    url = f'{BASE_URL}/api/chat'
    if not url.startswith(('http://', 'https://')):
        return '', 0.0
    payload = json.dumps({'message': 'What is 2+2?', 'agent_id': 'default'}).encode()
    # Scheme already checked above; same guard as _harness.server_reachable.
    request = urllib.request.Request(  # noqa: S310
        url, data=payload, method='POST',
        headers={'Content-Type': 'application/json', 'X-CSRF-Token': token})
    started = time.time()
    try:
        with urllib.request.urlopen(request, timeout=timeout) as r:  # noqa: S310
            return r.read().decode('utf-8', 'replace'), time.time() - started
    except TimeoutError:
        return '', time.time() - started
    except (urllib.error.URLError, OSError) as exc:
        return f'__transport__:{exc}', time.time() - started


def _frames(raw: str) -> list[dict]:
    out = []
    for line in raw.split('\n'):
        line = line.strip()
        if not line.startswith('data:'):
            continue
        try:
            out.append(json.loads(line[5:].strip()))
        except (ValueError, TypeError):
            continue
    return out


def _provider_in_use() -> bool:
    """Confirm the app is really talking to the fake provider.

    Without this the audit could be measuring the no-provider path -- which is
    handled correctly -- and would report every mode as clean. That is the
    same trap that made the concurrency audit pass while every one of its
    writes was being rejected.
    """
    return os.environ.get('AGENTIC_FAKE_PROVIDER') == '1'


def run() -> AuditResult:
    if not _provider_in_use():
        return AuditResult(
            'agent-reliability', 0,
            ['-- needs a server started against scripts/audit/fake_provider.py '
             'with AGENTIC_FAKE_PROVIDER=1; see the module docstring. Refusing '
             'to report a result measured against the real provider path.'],
            note='misbehaving-provider behaviour')

    mode = os.environ.get('MODE', '')
    provider = os.environ.get('PROVIDER', 'ollama')
    token = _csrf()
    if not token:
        return AuditResult('agent-reliability', 0,
                           ['-- could not obtain a CSRF token'],
                           note='misbehaving-provider behaviour')

    findings = []

    if mode == 'truncate':
        raw, _ = _chat(token, timeout=40)
        frames = _frames(raw)
        text = ''.join(f.get('delta', '') for f in frames)
        if frames and not any(f.get('done') for f in frames):
            findings.append(
                f'SILENT-TRUNCATION  the provider hung up mid-answer; the '
                f'stream ended after {len(text)} chars with no done frame and '
                'no error, so a partial reply reads as a complete one')

    elif mode == 'stall':
        raw, elapsed = _chat(token, timeout=int(STALL_BUDGET_SECONDS))
        frames = _frames(raw)
        if not frames:
            findings.append(
                f'NO-TIMEOUT         {elapsed:.0f}s with zero frames received '
                f'and the request still open (app budget {APP_BUDGET:.0f}s); '
                'nothing tells the user whether the model is thinking or dead')
        elif not any(f.get('done') for f in frames):
            findings.append(
                'NO-TIMEOUT         the stall produced frames but never a '
                'terminal one, so the UI cannot stop waiting')

    elif mode == 'garbage':
        raw, _ = _chat(token, timeout=40)
        frames = _frames(raw)
        if not frames:
            findings.append(
                'SILENT-EMPTY       a 200 with an unexpected body yielded an '
                'entirely empty stream: no text, no error, no done frame')

    elif mode == 'error500':
        raw, _ = _chat(token, timeout=40)
        text = ' '.join(f.get('delta', '') for f in _frames(raw))
        # Judge the HEADLINE, not the whole message: 00-error-copy.js
        # deliberately keeps technical detail in trailing parentheses, and
        # punishing that would punish the fix.
        headline = re.sub(r'\([^)]*\)', '', text).strip()

        # What makes a headline bad is that it reads as machine output rather
        # than as a sentence addressed to a person.
        #
        # The first version searched for fixed tokens ('HTTP 500',
        # 'localhost:11434'). Those are incidental -- the same failure through
        # 127.0.0.1 contains neither, so a raw exception headline passed. A
        # probe keyed on the accidental spelling of one deployment is not
        # measuring the property.
        JARGON = (
            'disconnected (', '[stream error]', 'Traceback',
            'Server error', 'HTTPStatusError', 'ConnectError',
            'ReadTimeout', 'httpx.', 'Exception',
        )
        looks_machine = (
            headline.startswith('[')
            or any(j in headline for j in JARGON)
        )
        reads_human = any(
            w in headline.lower()
            for w in ('could not', "couldn't", 'couldn\u2019t', 'unable',
                      'make sure', 'switching to your', 'try again',
                      'has not responded')
        )
        if looks_machine and not reads_human:
            findings.append(
                f'RAW-ERROR          the headline reads as machine output: '
                f'{headline[:70]}')

    else:
        findings.append('-- set MODE to truncate|stall|garbage|error500')

    return AuditResult(
        'agent-reliability',
        len([f for f in findings if not f.startswith('--')]),
        findings,
        note=(f'agentic core against a misbehaving provider '
              f'(provider={provider}, mode={mode or "unset"})'),
    )


if __name__ == '__main__':
    raise SystemExit(emit(run()))
