# 10 — Engineering: Python, Full-Stack, APIs

> Craft-level practice for building the thing. Opinionated, because unopinionated
> guidance produces inconsistent codebases.

---

## API design for agentic systems

**Status codes carry meaning.** The single most common API defect in these
systems is HTTP 200 with `{"ok": false}`. A sender — GitHub, Stripe, a CI
system, another agent — sees success and never retries or alerts.

| Situation | Code |
|---|---|
| Validation refusal | 400 |
| Unauthenticated / bad credential | 401 |
| Understood and deliberately refused (protected resource) | **403** |
| Not found | 404 |
| Already decided / state conflict | 409 |
| Well-formed but semantically impossible | 422 |
| Downstream provider failed or returned nothing usable | **502** |
| Dependency unavailable (no provider configured) | 503 |

A refusal answered with 200 tells every status-aware client it succeeded.

**Response shape.** `ok` must be *computed*, never hardcoded. If a field can be
unmeasured, return `null` and add a sibling explaining the basis:

```json
{
  "ok": false,
  "assessed": false,
  "score": null,
  "error": "The reviewer returned no usable output. This file was NOT assessed —
            do not read the absence of issues as a pass.",
  "basis": "human decisions only; auto-approvals excluded"
}
```

**Partial success is its own state.** `complete` / `partial` / `failed` with
counts and the names of what failed. Never collapse partial into either
neighbour.

**Absent ≠ empty.** `dict.get('x', default)` supplies the default only when the
key is *missing*. An explicitly-passed empty string bypasses it — which is how
`{"secret": ""}` becomes an unauthenticated endpoint. Distinguish deliberately:

```python
raw = body.get('secret')
if raw is None:          # absent → generate
    ...
elif not raw.strip():    # present but empty → reject or generate, and SAY SO
    ...
```

**Idempotency.** Deleting something already gone is a *success* — the caller
asked for it not to exist, and it does not. Creating something that exists is a
409. Be deliberate about which.

## Python

**Typing and validation.** Type hints everywhere; Pydantic at boundaries.
Validate at the edge, trust inside.

**Coercion is a boundary concern.** `int(body.get('x'))` raises on garbage and
returns HTTP 500. Write one bounded coercion helper and use it:

```python
def bounded(value, default: int, lo: int, hi: int) -> int | None:
    if value is None or value == '':
        return default
    try:
        n = int(value)
    except (TypeError, ValueError):
        return None          # caller returns 400 — never a 500
    return max(lo, min(n, hi))
```

Clamp **both** ends. Clamping only the upper bound lets `ttl=-500` mint an
already-expired credential and return it as `ok: true`.

**Exceptions.** Catch narrowly. A bare `except Exception: pass` around a
security check silently disables it. If you must swallow, log and say why in a
comment — future-you will assume the empty block was deliberate.

**Async.** Never block the event loop: `asyncio.create_subprocess_exec`, not
`subprocess.run`. Bound every `await` with a timeout. `asyncio.gather(...,
return_exceptions=True)` and then zip against the input list — a failed task
that reports itself as `'?'` is useless for diagnosis.

**Resource hygiene.** Context managers or `try/finally` for every connection.
Close in `finally`, not at the end of the happy path.

**Time.** Store UTC. Serialise ISO-8601 with `Z`. Never apply a `localtime`
conversion and then label the result UTC — invisible in a UTC environment,
wrong everywhere else.

## Data layer

- Parameterise values **and** validate identifiers. `?` protects the value;
  interpolated table/column names are wide open.
- Migrations forward-only and idempotent (`CREATE TABLE IF NOT EXISTS`).
- Distinguish `rowcount == 0` from an error — it usually means "nothing
  matched", which is often success.
- Never `SELECT *` into an API response. New sensitive columns join the payload
  automatically the day someone adds them.
- Atomic writes to files: write `.tmp`, then `replace()`.

## Frontend

- **Escape everything interpolated into HTML.** Attribute context needs
  attribute escaping — `JSON.stringify` inside a double-quoted attribute
  terminates it at the first inner quote and silently kills the handler.
- Prefer `data-*` + delegated listeners over inline handlers; where a framework
  requires inline, use one audited argument-encoding helper.
- Guard nullable values at the render point: `value == null ? '—' : value`.
- Never render a success state from a response you did not check.
- Bundle-scoped `let` is not on `window`; verify handler resolution in a real
  browser, not by reading the source.

## Testing

Covered in depth in `11-quality.md`. The three rules that belong here:

1. A test that has never failed is unproven. Break the behaviour and watch.
2. Test the endpoint, not your own helpers. Building the artefact yourself in
   the test and asserting on it proves nothing about the code path.
3. Fixtures must seed what they assert on. `if rows:` around an assertion makes
   it vacuous the day the fixture is empty.

## Code review discipline

- **Reproduce before fixing.** A fix for an unobserved bug is a guess.
- **Comment the *why*, especially the counter-intuitive.** Record the evidence:
  "Verified live: X returned Y". Future maintainers cannot re-derive it.
- **When you revert your own change, say so in the comment.** "I "corrected"
  this to N; that broke test T, which exists to pin exactly this. The test was
  right." saves the next person the same mistake.
- **Mark defensive code as defensive.** If removing it breaks no test and you
  keep it anyway, say why — otherwise someone hunts for a bug that was never
  there.
- Small, single-purpose commits with messages that explain root cause and
  evidence, not just the diff.

## Observability

OpenTelemetry spans: one per agent run, child per model call, grandchild per
tool call, with tokens, cost, latency, and model on every span. Structured logs
with a correlation ID. Metrics: p50/p95/p99 latency, error rate by class, cost
per run, tool failure rate, cache hit rate.

**Record at the layer, not the call site.** Instrumenting 30 callers yields a
1-in-30 hit rate and regresses the day someone adds the 31st.
