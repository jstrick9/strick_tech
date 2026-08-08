# 61 — The agentic core against a misbehaving provider

**New dimension.** Twenty-one audits cover the shell. None touched the
product's actual reason to exist: an LLM answering, an agent running.

**Audit:** `scripts/audit/agent_reliability.py` + `fake_provider.py` ·
**key:** `agent-reliability` · **baseline:** 3 → **0**
**Tests:** `tests/unit/test_133_agent_reliability.py` (13) — 8 fail on revert.

---

## The gap in every previous failure probe

Every provider failure tested so far was one of two states:

| State | Result |
|---|---|
| no provider configured | clean 503 with setup instructions ✓ |
| server unreachable | transport error ✓ |

**Neither is the common production case.** There, the provider *is* configured
and *is* reachable, and it fails **while streaming** — which produces a wrong
answer rather than an error message.

`fake_provider.py` is an Ollama-compatible server that fails in four chosen
ways. Three found real defects.

---

## The defects

### 1. SILENT-TRUNCATION — the worst of the three

The provider hung up mid-sentence. `generate()` had a `finally` but **no
`except`**, so the exception propagated and the response simply stopped: no
error frame, no `done`.

```
data: {"delta": "The ",    "done": false}
data: {"delta": "answer ", "done": false}
data: {"delta": "is ",     "done": false}
data: {"delta": "that ",   "done": false}
                                            ← nothing. Rendered as COMPLETE.
```

The user acts on a truncated reply with nothing on screen suggesting it was cut
off. This is recurring pattern **#9** — *the response not describing its own
completeness*.

### 2. SILENT-EMPTY

A 200 whose body has the wrong shape produced an **entirely empty stream** — no
text, no error, no `done`. Sending a message appeared to do nothing at all.

### 3. NO-TIMEOUT

A provider that accepts and sends nothing held the connection for **65+ seconds
with zero bytes**. `httpx.AsyncClient(timeout=120)` is a socket read timeout,
and an open silent connection satisfies it. An empty bubble with no way to tell
thinking from dead.

**`error500` was already handled correctly** — recorded as a result, not
silence.

---

## The fixes

**A terminal-frame guarantee** in `generate()`. Whatever happens inside the
stream loop, a `done` frame is emitted — with `truncated: true` and wording
that distinguishes "stopped early" (keep the text, warn it is partial) from
"returned nothing" (nothing to keep). Truncated output is also excluded from
long-term memory ingestion, which an earlier batch found was re-injecting error
text into later prompts.

**One fix closed defects 1 and 2** — they were the same missing guarantee seen
from two angles.

**A first-token timeout** (`AGENTIC_FIRST_TOKEN_TIMEOUT`, default 30s),
separate from the total timeout. Total time is the wrong thing to bound: a long
answer streaming steadily is healthy; a provider that has sent nothing is not.
Stall time went **65s → 8.05s** at an 8s budget.

---

## Two mistakes of mine, both caught by measuring

**The first timeout guard could never fire.** I put the elapsed-time check at
the top of `async for line in resp.aiter_lines()`. That body only runs when a
line **arrives** — which, for a silent provider, is never. The request still
hung the full 35s. *The wait itself must be bounded* (`asyncio.wait_for`), not
something inside it.

**The probe measured its own impatience.** It waited 25s against the app's 30s
budget and reported `NO-TIMEOUT` for a stall the app resolves correctly at 30.
Its budget is now derived from `AGENTIC_FIRST_TOKEN_TIMEOUT`, so tightening the
app cannot silently invalidate the audit.

Also worth recording: a stale `fake_llm.py` from an earlier experiment kept
port 11434 while my `pkill` matched only the new filename, so every mode was
secretly measured against `error500`. All four reported 0. **A probe pointed at
the wrong provider looks exactly like a clean result.**

---

## A testability gap found on the way

`OPENROUTER_BASE` is a hardcoded constant; `OLLAMA_BASE` is env-overridable.
The **primary** provider therefore has no seam for testing failure at all, and
this audit had to use the Ollama path. Worth closing separately.

---

## Verification

| Check | Result |
|---|---|
| `agent_reliability.py` (4 modes) | 3 findings → **0** |
| Remove the terminal-frame guarantee | `SILENT-TRUNCATION` + `SILENT-EMPTY` return |
| Remove the first-token timeout | `NO-TIMEOUT` returns (40s, zero frames) |
| Revert both fixes | **8 of 13** tests fail |
| No-provider path | unchanged (`done` + `stub: true`) |
| Full suite | 3,390 unit (2 skipped) + 655 (10 skipped), 0 failures |

---

# 61b — Closing the testability gap on the primary provider

The audit above had to drive all four failure modes down the **Ollama** path,
because `OPENROUTER_BASE` was a hardcoded constant while `OLLAMA_BASE` was
env-driven. The primary provider — the one almost every deployment actually
uses — had **no seam for testing failure at all**.

`OPENROUTER_BASE_URL` is now overridable (default unchanged). The fake provider
learned the OpenAI SSE shape alongside Ollama's NDJSON, so the same four modes
run against either path.

## What that immediately found

**The stall bug was on the primary path too, and the earlier fix had not
covered it.** Measured with an 8-second budget configured: **40 seconds** of
silence. The `_openrouter_stream` loop had its own `async for` with no bound.
Now 40s → **8.04s**.

**A raw exception as the headline:**

```
[OpenRouter disconnected (Server error '500 Internal Server Error' for
 url 'http://127.0.0.1:11434/chat/completions'...). Auto-falling back...]
```

Reworded to lead with the explanation and demote the detail —
`00-error-copy.js`'s convention, which the failure-honesty audit enforces on
the frontend and this backend path predated.

> _Couldn't reach the cloud model — switching to your local llama3.1:8b
> instead. (…)_

## A probe bug found in the same pass

The `RAW-ERROR` check keyed on fixed tokens (`HTTP 500`, `localhost:11434`) and
split the headline on `.`. Both were wrong:

- The identical failure through `127.0.0.1` contains **neither token**, so a
  raw exception headline passed. *A probe keyed on the accidental spelling of
  one deployment is not measuring the property.*
- Splitting on `.` cut `llama3.1:8b` at the version number, truncating a
  **correct** message into a fragment that looked broken.

It now strips trailing parenthesised detail and asks whether the headline reads
as machine output or as a sentence addressed to a person. Verified both ways:
the bad wording is flagged, the good one is not.

## Coverage now

| | truncate | stall | garbage | error500 |
|---|---|---|---|---|
| **Ollama** | 0 | 0 | 0 | 0 |
| **OpenRouter** | 0 | 0 | 0 | 0 |

Full suite: 3,396 unit (2 skipped) + 655 (10 skipped), 0 failures.
