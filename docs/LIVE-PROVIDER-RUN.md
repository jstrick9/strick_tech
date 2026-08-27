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

## What the live run found

### Corrected: the first measurement was wrong

The first version of this document reported **17 failures** with a live
provider and concluded the integration suites were broadly timeout-bound. That
was wrong, and it is corrected here rather than quietly edited out.

A clean re-run, same model, same hardware, provider verified live (zero
`llm_unavailable` in the server log):

```
no provider:   1 failed, 655 passed,  9 skipped   (~90s)
live provider: 1 failed, 663 passed,  1 skipped   (276s)
```

Not 17 failures. **One.**

**What I got wrong.** The first run took 549s against this one's 276s — roughly
double. During it a model was already resident from my earlier manual probes,
on a box with ~500MB of headroom, so the suite was competing for memory with a
loaded model and every provider call crawled. I measured a contended machine
and attributed the result to the test suites.

I also wrote *"all 17 are client timeouts"* when the tally I had in front of me
showed 14 `ReadTimeout` plus several assertion failures. Those assertions were
almost certainly downstream of the same contention, but I stated a clean number
I had not actually established.

**The lesson is the one this codebase keeps relearning:** confident reporting
of an unverified thing. The measurement was real, the environment it described
was not the one I claimed.

### What is actually true

**Eight tests that SKIP without a provider now PASS with one.** That is the
substantive finding: those paths — bugbot review, swarm, supervisor decomposition,
knowledge-graph query, code review, SSE streaming — had never once been executed
in this series. They work.

**`uat_08` was never a defect.** `test_user_can_get_ai_risk_assessment` failed
in every run across this entire series and was carried as "pre-existing,
environmental" each time. With a provider present it **passes**. It was the
no-provider path all along, and the earlier characterisation was correct only
by accident.

**One genuine latency-bound test remains:**
`test_sys_10 ... test_eval_run_produces_valid_scores` fails with
`httpx.ReadTimeout`. An eval suite makes many model calls inside one HTTP
request, so at ~22 tok/s it exceeds the 30s client timeout in
`tests/system/conftest.py`. That is a real property of this hardware, not a
defect: on any normal machine it would finish well inside the limit.

No test file is modified by this work.

## For running this on your own machine

Your Ollama is on your computer; this sandbox is a remote container, so its
`localhost:11434` is not yours. To point the platform at your models:

```bash
OLLAMA_BASE_URL=http://localhost:11434 \
OLLAMA_FALLBACK_MODEL=llama3.1:8b \
DEFAULT_MODEL=ollama:llama3.1:8b \
python run.py
```

On real hardware with an 8B model the single remaining timeout should not
reproduce — it is a function of ~22 tok/s on two shared cores, not of the code.
If it does, that is a genuine finding worth reporting.

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
| Integration suite | **663 passed, 1 failed** with a live provider |
| 8 previously-skipped paths | Now executed and passing |
| `uat_08` risk assessment | **Passes** — was never a defect, only unprovided |
| 1 remaining failure | Eval suite, many calls in one request, ~22 tok/s |
