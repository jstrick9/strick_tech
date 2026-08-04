# Module 21 — OPERATE

*(panes: `observability` + agent-monitor, profiler, health, system, audit-log, replay, finops, dashboard, leaderboard; `evals` + eval-framework, arena, bugbot, testgen; `secrets` + pqc)*

14 routers, 7,207 lines. Three findings, each verified live before fixing.

---

## 1. Cost recording and budget enforcement were 1-in-30

**30 routers call `llm.complete()` and spend real money. Exactly one — `chat.py`
— recorded anything.**

```
before: total_events 80
  run a skill   → LLM call attempted
  run an MCP tool
after:  total_events 80        ← unchanged
```

So the FinOps dashboard, per-agent and per-model attribution, burn-rate
projection, per-goal spend and every alert were reporting **chat traffic only**
while presenting themselves as platform-wide. Routers that spend and recorded
nothing included `supervisor`, `swarm`, `pipeline`, `evals`, `eval_framework`,
`multifile_agent`, `builder`, `skills`, `imagegen`, `mcp` and 19 more.

**Budget caps had the identical shape.** `check_budget_before_spend()` exists,
is correct, and handles `pause`/`kill` properly — and `chat.py` was its only
caller. A cap set to `kill` stopped chat and nothing else, so *the runaway
loops most likely to burn money were exactly the ones no cap could stop.*

### Why the fix is at the LLM layer

Recording at the call site is the arrangement that produced a 1-in-30 hit rate,
and it regresses the moment a 31st caller appears. `complete()` already
computed `cost` and discarded it.

`complete()` is now a thin wrapper — **budget gate → `_complete_impl()` →
record** — so one site covers every provider and every return path. The budget
check **fails open** by design: a guardrail that blocks all inference when the
database hiccups is worse than the overspend it prevents. A ledger failure
never fails the user's request, only logs loudly.

### A latent production hazard this exposed

Wiring enforcement up broke `test_59`'s **provider-contract** tests, which have
nothing to do with budgets. Root cause: `test_28` created three *wildcard* caps
(`scope_id='*'`) at $0.01 with `on_breach` pause/kill and never deleted them.

Harmless while nothing read `on_breach`. Once enforced, a $0.01 global cap
denies every subsequent LLM call.

The same residue was in the **production database**: **58 rows** named
`Unit pause breach` / `Unit kill breach` from past runs, predating the DB
sandbox. On a real deployment those would now have blocked every LLM call in
the product. Removed (169 legitimate caps retained), and `test_28` cleans up.

> This is the strongest argument yet for the test-isolation work in `1b07a0f`:
> **residue stopped being cosmetic the moment a feature started reading it.**

---

## 2. The vault master key was world-readable

```
$ ls -la memory/.vault_key
-rw-r--r--  1 user user 44 ...      # mode 644
```

`_get_fernet()` calls `chmod(0o600)` — **only inside the branch that creates
the key**. Any vault created before that line was added kept its umask
permissions forever, because the existing-key path never checked.

That key decrypts every credential in the vault, so **its file mode is the
vault's entire at-rest protection**. Module 17 refused to let Database Studio
read the `secrets` table for precisely this reason; leaving the master key
readable by any local process undoes that work.

Now self-healing, with a warning naming the old mode. Fixing only the creation
path would have helped new installs and left every existing one exposed — the
same mistake as the Module 19 marketplace seeder, where a fix that only ran on
empty databases helped nobody who already had the bug.

Verified `644 → 600` on next load, with a round-trip encrypt/decrypt proving
the key material is untouched.

---

## 3. Eval runs on a nonexistent suite returned 200

```
POST /api/eval-framework/run {"suite_id": "nope_not_real"}
→ 200 OK
  data: {"error": "No cases in suite"}
```

The message was honest; **the status code was not.** Validation happened inside
the SSE generator, so the response was already committed as 200 before the
problem was known.

This matters more here than elsewhere: the entire point of the evals module is
producing **trustworthy quality numbers**, and anything piping the stream into
a dashboard recorded a run that never happened.

Now validated before the stream opens — `404` for a missing suite, `409` for
one that exists with no cases. Deliberately distinct: folding them together
would hide a real configuration mistake behind "not found".

---

## What was already correct

Worth recording, since the value of a review is partly in what it clears:

* **Secrets are properly encrypted and redacted.** Storing
  `sk-SUPER-SECRET-VALUE` and listing the vault leaks nothing; values never
  appear in list or detail responses.
* **Arena** returns 404 for unknown battles.
* **FinOps aggregation** is correct — the data was simply never being written.
* All 14 OPERATE routers are mounted and reachable. My first probe reported
  six 404s; **the paths I guessed were wrong, not the endpoints.**

---

## Tests

`tests/unit/test_83_operate_cost_and_budget.py` — 15 cases. **13 of 15 fail
with `llm.py` stashed.**
`tests/unit/test_84_operate_secrets_evals.py` — 10 cases. **4 of 10 fail with
the two routers stashed.**

Full suite: **3454 passed / 19 skipped / 0 failed**.

### Self-corrections

1. I passed the model as `source_id`, leaving the `model` column empty — every
   per-model cost breakdown would have been blank. Caught by **reading back the
   row I had just written** instead of trusting the insert.
2. A test asserted `_complete_impl` contains ≥5 `ok: True` returns. It contains
   one; the Ollama fallbacks live in `_ollama_complete`. The assertion
   described my mental model of the file rather than any behaviour — replaced
   with the property that matters (neither function records, so the wrapper
   cannot double-count).
3. Two tests called `llm_svc.complete()` after the session `client` fixture had
   replaced it with an `AsyncMock`, so they exercised the mock and failed **only
   in the full run**. Now capture `REAL_COMPLETE` at import time, the pattern
   `test_59` already uses.
4. My 409 test supplied its own `suite_id`, but `POST /suites` generates one
   server-side, so the test ran against a made-up id and hit the 404 path.

---

## Recommended follow-ups

1. **`llm.stream()` is not wrapped.** Chat records its own streamed cost, so
   there is no gap today — but any future streaming caller repeats the original
   1-in-30 bug. The wrapper pattern should be applied there too.
2. **Cost estimates are static per-model rates** (`_estimate_cost`), not
   provider-reported billing. Fine for burn-rate projection, misleading if
   presented as an invoice.
3. **`observability/traces` is empty** — nothing writes spans, so the pane
   renders a permanently blank list rather than saying it is not wired up.
4. **`profiler` has no cost attribution** despite being an LLM caller itself.
5. **PQC module is scaffold** — `/api/pqc` mounts, but the "ML-KEM-1024" claim
   in the OpenAPI description deserves verification against what it implements.

---

# Follow-ups 1–5 (`5161805`)

All five closed. The last one turned out to be the most serious finding in the
module.

## 5. PQC claimed cryptography it does not implement

Every endpoint advertised NIST-standard lattice cryptography — *"ML-KEM-1024
(NIST FIPS 203 / Kyber-1024 Level 5)"*, *"Dilithium-5"*, *"NIST Category 5"*,
*"Immune to Shor's Algorithm"*. The primitives are **SHA3 hashes and an XOR
mask**. The source comments already said `# simulated`; the API responses said
the opposite.

Two breaks, both verified against the running server:

**1. The KEM shared secret is public.**
```
shared_secret = sha256(public_key || ciphertext[:64])
```
Both inputs are public in any KEM by definition, so the "256-bit
quantum-resistant shared secret" is recoverable by anyone observing the
exchange.

**2. Vault encryption is XOR against a public value.**
```
POST /pqc/keypair/generate    → keypair_id: pqc_kp_1d3bda6d
POST /pqc/vault/encrypt {...} → post_quantum_protected_b64: dz/lwJ3F...
decrypt with sha256("pqc_kp_1d3bda6d")
→ "POSTGRES_PASSWORD=hunter2"
```

I recovered a stored secret using **only the public keypair id**. That is
**weaker than plaintext** — plaintext does not carry a label reading
*"Kyber-1024 Lattice-Protected"* encouraging you to trust it.

### Why the endpoints stay

Existing UI may call these routes, and a silent 404 converts a false claim into
a confusing one. Instead: every response declares `simulated: true`, the
security-theatre strings are gone, the OpenAPI tag is corrected, and **vault
encrypt/decrypt return 501** unless `AGENTIC_PQC_DEMO=1`. Keypair generation
and KEM are harmless curiosities; the vault operations are the ones that invite
an operator to put a live credential through a function offering no protection.

A test asserts the XOR break **still reproduces** under demo mode — so if the
primitive ever changes, the warning cannot silently become overstated.

## 1. `llm.stream()` was not wrapped

No gap existed at the time, because `chat.py` recorded its own streamed spend.
But that is the same per-call-site arrangement that produced the original
1-in-30 miss rate, and the next streaming caller would silently repeat it.

`stream()` now applies the budget gate — yielding the refusal **as an SSE
frame**, since a caller iterating frames cannot inspect a returned dict — and
records from the terminal frame. Chunks pass straight through; a test asserts
streaming is not buffered.

**This makes chat's own `record_cost()` a double count**, so it is removed in
the same commit. The two changes are inseparable, which is why they are not
split.

## 3. Traces were permanently empty

A complete tracing backend — schema, `create_trace`, `create_span`, analytics,
DORA metrics, an EU AI Act compliance report — and
`grep -rl obs_traces backend/` returned `observability.py` **alone**. Nothing
ever emitted a trace.

> A permanently empty observability view is worse than an absent one: it tells
> the operator their agents did nothing, which is a false statement about the
> system rather than a missing feature.

Now emitted from the LLM layer for both `complete()` and `stream()`. Traces
populate with real prompt/output/tokens/cost, and `/analytics` reports non-zero
totals.

## 2. Costs are estimates presented like invoices

An **unknown model silently fell back** to $0.001/$0.003 per 1K — off by an
order of magnitude either way (Haiku ~4× cheaper, Opus ~25× dearer). The
dashboard now returns `cost_basis: "estimated"`, a note that cached/batch
discounts are not modelled, and `unpriced_models` naming exactly which figures
are guesses.

That immediately surfaced **`gpt-4o` has no rate-card entry** — those numbers
were guesses all along.

## 4. Profiler flamegraph — *and a correction*

> **My original follow-up was wrong.** I wrote *"profiler has no cost
> attribution despite being an LLM caller"*. It makes **no LLM calls at all**;
> the `llm.complete()` node is a string in a hand-written tree.

The real defect: the flamegraph is illustrative sample data with only the
`real_endpoints` subtree reflecting this process, and the response never said
so. A flamegraph is read as measurement, so an unlabelled synthetic one invites
optimising a call path that was never profiled. Now returns `synthetic: true`.

## Tests

`tests/unit/test_85_operate_followups.py` — **22 cases**.
**Proven to catch the bugs: with the six files stashed, 19 of 22 fail.**

Two existing tests updated because they pinned the old behaviour:

* `test_36` asserted `"Kyber-1024" in security_guarantee` — **the test was
  enforcing the false cryptographic claim.** Fifth instance in this review of a
  test holding a bug in place, and the most consequential.
* `test_50` asserted `chat.py`'s **source text** contained `record_cost(...)`.
  The property still holds and now holds for all 30 callers; a source-text
  assertion pins an implementation, which is why it broke for the wrong reason.
  Rewritten to assert behaviour.

### Self-correction

My replacement `test_50` case captured `llm_svc.stream` at **call** time, so in
a full run it grabbed conftest's `AsyncMock` — **the exact trap I documented in
`test_83` and then walked into again.** Now captured at import time.

Full suite: **3477 passed / 19 skipped / 0 failed**.

## Module 21 status

All five follow-ups closed. Nothing outstanding for OPERATE.
