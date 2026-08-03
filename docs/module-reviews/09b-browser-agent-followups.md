# Module 9 follow-ups — LLM stub handling & browser simulation

**Commit:** `9ea3683` · **Suite:** 2436 passed / 17 skipped / 0 failed · ruff clean

The Browser Agent review closed with three recommendations. Two were actionable;
this document covers implementing them. The third (exercising the real Playwright
path) still can't be done here — Chromium needs system libraries that require root,
which this sandbox doesn't have.

---

## 1. `provider='stub'` moved to the LLM layer

### The problem

When no AI provider is configured, `llm.complete()` returned a **placeholder** whose
`text` is human-readable setup help — *"⚠️ No OPENROUTER_API_KEY set…"* — tagged
`provider='stub'` / `ok=False`. Noticing that flag was left entirely to the caller.

Three modules shipped the identical bug independently:

| Module | Symptom |
|---|---|
| **Chat** | Setup help streamed to the user as a model reply |
| **Supervisor** | Runs finished `done`, `failed_count=0`, evaluator awarded 0.7 — a passing grade for a run in which no model ever executed |
| **Browser Agent** | Help text split into numbered "completed" browser steps; session recorded `done` |

That is three occurrences of one root cause, found one module at a time over three
separate reviews. A further **~30 of the 43 `complete()` call sites never checked at
all**, so the same failure was latent across the platform. Continuing to fix them
individually was never going to converge — the next reviewer would just find the
fourth.

### The fix

`complete()` now **raises `LLMUnavailableError`** unless the caller passes
`allow_stub=True`. `app.py` maps the exception to a 503 with an actionable body:

```json
{"ok": false, "code": "llm_unavailable", "error": "…", "model": "…", "setup_url": "…"}
```

Verified live, no key and no local model:

```
POST /api/chat/complete   before → HTTP 200, `text` = the setup help
                          after  → HTTP 503 {"code": "llm_unavailable"}
```

The default is the safe one. A caller has to *opt in* to receive a placeholder, and
opting in is greppable.

### Where opting in is legitimate

Exactly two situations, both because **no HTTP status is left to set**:

- **SSE generators** — the status line went out before the stub was discovered
  (Browser Agent).
- **Background tasks** — there is no response object at all (Supervisor task
  execution, the scheduler's goal loop).

Both still check the flag, now through the shared `llm.is_stub()` rather than a
private copy of the string comparison.

### `sse_guard()` — a bug I introduced and then fixed

Raising out of a generator that is **already streaming** truncates the response
mid-chunk. The client doesn't see the reason; it sees:

```
httpx.RemoteProtocolError: peer closed connection without sending complete message body
```

I hit this in the eval-framework stream while making this change. `llm.sse_guard()`
wraps a generator so `LLMUnavailableError` becomes a terminal error frame carrying
`code: llm_unavailable`, then closes cleanly. Applied to the **17 routers** whose
`StreamingResponse` can reach an LLM.

### A deliberate non-decision

`is_stub()` does **not** treat `ok=False` as a stub. A model that ran and failed
(HTTP 500 from OpenRouter, say) is a genuinely different condition from no model at
all, and collapsing the two would make the 503 lie in the other direction. There's a
test pinning this.

---

## 2. Browser simulation mode is opt-in

Simulation mode is make-believe by design: an LLM narrates the steps a browser agent
*would* take, and nothing is fetched. The review flagged it as clearly labelled but
questionable. The real problem turned out to be narrower and worse than "is it worth
keeping": **it was the silent fallback**. A user asking for a real browser run got an
invented one whenever Chromium was missing, unless they read the small print.

So rather than retire it, I made it honest:

- `POST /api/browser/task` requires `"simulate": true`; otherwise **503
  `browser_unavailable`** with the install command and a pointer to the flag.
- The decision happens **before the stream opens**, so the refusal is a real status
  code rather than an error buried inside a 200 SSE body.
- The warning frame now says plainly that *nothing is actually being fetched*.
- The frontend gained a **Simulate toggle** (pre-checked only when no browser is
  available) and now surfaces the server's explanation instead of a bare status
  number.

Verified live:

```
POST /api/browser/task {"task": "…"}                    → 503 browser_unavailable
POST /api/browser/task {"task": "…", "simulate": true}  → 200, SSE, honest warning
```

---

## Incidental findings

Verifying the above surfaced three more issues, all fixed in the same commit:

### 🔴 Swarm reported success for a run in which every agent failed

`ok: true` with a null winner and empty output — an entirely failed swarm rendered as
a successful one. Now 503 with the per-agent failures attached.

### 🟡 Swarm attributed failures to agent `'?'`

Exceptions from `asyncio.gather` were recorded against a literal `'?'`, so a partial
failure told you nothing about *which* agent broke. Results are now zipped back to
their agent ids.

### 🟡 `must()` in `tests/system/conftest.py` returned `{}` for any non-200

The same flaw already fixed in `tests/uat/conftest.py`: every error-body assertion
downstream of it was silently vacuous. Removed. This was on the outstanding-issues
list from earlier reviews.

---

## Tests

`tests/unit/test_59_llm_stub_contract.py` — **20 contracts** across the LLM layer, the
503 mapping, the opt-in call sites, simulation opt-in, and the swarm fixes.

The one I'd single out:

```python
def test_no_caller_reimplements_the_stub_literal(self):
    """The provider=='stub' comparison must live in exactly one place."""
```

This is the test that stops the bug class from coming back. The other 19 verify the
current fix; this one fails the moment a future caller starts hand-rolling the check
again.

**Proven to catch regressions** — with the raise reverted and `simulate` defaulted
back to `True`, 2 tests fail; restored, all 20 pass.

### Test-harness updates

Behaviour changed on purpose here, so a number of suites needed their contracts
updated rather than their expectations preserved. Both conftest layers gained
`skip_if_no_provider()` / `skip_if_no_provider_events()`, which distinguish *"this
endpoint is broken"* from *"this sandbox has no AI provider, and the endpoint said so
correctly"*. The suites stay meaningful on a machine that has a provider and skip
honestly on one that doesn't — rather than being loosened to accept anything.

---

## Cross-module impact

| Module | Impact |
|---|---|
| **Chat, Supervisor, Browser Agent** | Per-caller stub checks replaced with the shared helper |
| **Swarm, Eval Framework, BugBot, Knowledge Graph** | Now honestly 503 instead of returning empty "successful" results |
| **17 SSE routers** | Wrapped in `sse_guard`; streams close cleanly instead of truncating |
| **Scheduler** | Goal-loop iterations record an error rather than logging setup help as work product |

---

## Still outstanding

Unchanged from the running list, minus the two items closed here:

1. **Duplicate-global CI lint** — still my #1 structural recommendation.
2. **`config.yaml` says `version: "6.0"`** while `VERSION` is `11.5.0`.
3. **Tests write to the production DB** (`memory/agentic.db`).
4. **`PYTEST_CURRENT_TEST` rate-limit bypass structurally cannot fire** (wrong process).
5. **`safeUrl()` still local to `44-websearch.js`.**
6. **Playwright path untested** — needs a machine with root.
7. **vitest has 8 pre-existing failures** from a missing jsdom dep after a sandbox
   snapshot rollback — identical on a clean checkout with these changes stashed, so
   not caused by this work.
