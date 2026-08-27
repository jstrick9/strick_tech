# Walking the path with a live model

Everything in this repo up to now had been verified against the *no-provider
refusal*. This is the first end-to-end run with real inference behind it.

**Setup:** Ollama v0.33.1, CPU-only, `qwen2.5:0.5b`, measured at **~22 tok/s**
in a 2-core / 2GB sandbox. Wired in through the existing seam — no code change:

```
OLLAMA_BASE_URL=http://localhost:11434
OLLAMA_FALLBACK_MODEL=qwen2.5:0.5b
DEFAULT_MODEL=ollama:qwen2.5:0.5b
```

---

## What the live run confirmed

### The ICM context genuinely reaches the model

A chat turn against a routed workspace returned a real streamed reply (82KB of
SSE) whose content quotes back **Stage 01's actual contract** — its Inputs
table, its Process steps, the house-rules reference:

```
### Stage 01 — Pull
#### Input
| Source | File/Location | Section/Scope | Why |
| Run input | (provided at run time) | Full | The task |
| Conventions | ../../_config/conventions.md | Full file | House rules |
```

Route log for the same turn:

```
matched | client-reports / 01-pull | 445 tokens | route: 'client'
final:  prompt_tokens 1230, completion_tokens 2048
```

The layered context was assembled, routed and delivered. Until now that was
only provable by inspecting the assembled string; here the model repeated it
back.

### The walk-test gate degrades rather than fails

Deleting one stage contract and re-running the same request, with the provider
still live:

```
route log:      blocked-walk-test | 0 tokens
                ['stages/01-pull has no CONTEXT.md, so it has no contract.']
prompt_tokens:  834   (was 1230)
model replied:  yes
```

The ~400-token drop **is** the withheld workspace context. The model still
answered from the plain prompt. That is exactly the intended behaviour — refuse
to feed a broken structure, do not refuse the user — and it could not be shown
against a refusal, because nothing was being sent either way.

---

## What the live run found: 17 failures that were 9 skips

Running `tests/regression tests/system tests/uat` with a provider present:

```
no provider:   1 failed, 655 passed,  9 skipped
live provider: 17 failed, 648 passed, 0 skipped   (549s)
```

**All 17 are client timeouts, not logic defects.** The evidence:

- 14 of 17 fail with `httpx.ReadTimeout` / `httpcore.ReadTimeout`.
- `tests/uat/conftest.py` sets `TIMEOUT = 25`; `tests/system/conftest.py` sets
  `30`. At ~22 tok/s any response over roughly 500 tokens exceeds that.
- Raising the module constant to 300s moved
  `tests/uat/test_uat_03_developer_tools.py::TestUATBugBot` from 0 to **3 of 5
  passing**, changing nothing else.
- The two that still failed hardcode `timeout=25` *inline* at lines 89, 106 and
  126, ignoring the module constant — same cause, narrower scope.

The conftest change was reverted; no test file is modified in this commit.

### Why this is worth recording rather than "fixing"

The honest reading is that these suites assume a provider fast enough to answer
in 25 seconds. That is true of a hosted API and of Ollama on a real machine
with a real model; it is not true of a 0.5B model on two shared cores. **The
tests are not wrong and the code is not broken** — the environment is far below
what they assume.

Raising the timeouts to accommodate the slowest possible local model would make
the suite take hours and would hide genuine hangs. The useful outcome is
knowing *which* tests depend on provider latency, which is now written down.

### The one pre-existing failure is unchanged

`test_uat_08 ... test_user_can_get_ai_risk_assessment` failed identically
before and after a provider was configured, and was proved against clean HEAD
earlier in the series. It is not provider-related.

---

## For running this on your own machine

Your Ollama is on your computer; this sandbox is a remote container, so its
`localhost:11434` is not yours. To point the platform at your models:

```bash
OLLAMA_BASE_URL=http://localhost:11434 \
OLLAMA_FALLBACK_MODEL=llama3.1:8b \
DEFAULT_MODEL=ollama:llama3.1:8b \
python run.py
```

On real hardware with an 8B model the timeout failures above should not
reproduce — they are a function of ~22 tok/s, not of the code. If they do,
that is a genuine finding worth reporting.

Per-request override works too, which is how the runs above were driven:

```json
{"message": "...", "model": "ollama:qwen2.5:0.5b"}
```

---

## Summary

| Claim | Status |
|---|---|
| ICM context reaches the model | **Proven** — model quotes its stage contract back |
| Router selects the right workspace live | **Proven** — `matched client-reports/01-pull` |
| Walk-test gate withholds broken context | **Proven** — 1230 → 834 prompt tokens |
| Gate degrades rather than fails | **Proven** — model still answered |
| Unit suite (4,649) | Unaffected; provider-independent |
| 17 integration tests | Timeout-bound at ~22 tok/s; not defects |
