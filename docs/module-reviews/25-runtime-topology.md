# Runtime topology, and CSRF enforcement on by default

Closes the last two items from `23-recommendations.md`: the multi-worker
rate-limit warning, and the dated CSRF strict-mode flip.

They were filed as separate items of different urgency. They are actually one
problem, and finding that out changed the plan.

## The thing the recommendation missed

The doc reasoned about rate limiting being per-process and concluded, correctly,
that the failure mode is a quiet *degradation*: each worker counts on its own,
so the effective limit becomes `workers × configured`. Nothing is bypassed, so
it rated the item low urgency.

`_CSRF_TOKENS` is **also** a per-process dict. That was not noticed, and it
makes the CSRF flip dangerous in a way the doc did not anticipate: a token
minted by worker A is not in worker B's store, so enforcement rejects requests
that are perfectly legitimate.

Measured against a real server, `--workers 4`, `AGENTIC_CSRF_STRICT=1`, 60 POSTs
each carrying a **valid** token:

| Result | Count |
|---|---|
| accepted | 27 |
| **rejected 403** | **33** |

That is not a degradation, it is an outage on roughly half of every user's
actions. Turning enforcement on by default without detecting topology first
would have shipped exactly that.

So the detector became a **prerequisite** for the flip rather than a parallel
low-priority task.

> An earlier run of the same probe reported only 1 failure in 20. That was HTTP
> keep-alive pinning the connection to a single worker — the 60-request run
> across fresh connections is the representative figure.

## What shipped

### `backend/services/runtime_topology.py`

Best-effort worker detection from `WEB_CONCURRENCY`, `UVICORN_WORKERS`,
`GUNICORN_WORKERS`, `WORKERS`, from `--workers N` / `-w N` on the command line
(how it is actually spelled in practice, and it sets no env var), and from
`SERVER_SOFTWARE` for gunicorn workers that cannot see the master's flag.

Detection only ever **warns** or **refuses an unsafe default** — it never
rejects traffic. A false negative costs a missing warning; a false positive
costs a spurious one. Neither breaks a request.

The startup warning names concrete numbers rather than restating the design:

```
[topology] Running with 4 worker processes, but rate limiting and CSRF
           tokens are stored PER PROCESS.
[topology]   Rate limit: each worker allows 300 requests/window, so the
             effective limit is ~1200, not 300.
[topology]   CSRF: AGENTIC_CSRF_STRICT is ON. A token minted by one worker is
             unknown to the others, so roughly (workers-1)/workers of all
             state-changing requests will be rejected with 403 despite
             carrying a valid token.
```

`AGENTIC_ACK_MULTIPROCESS=1` downgrades WARNING to INFO for an operator who has
understood the trade-off. It does not suppress the content — silencing it
entirely would lose the record.

### The CSRF default

| Situation | Result |
|---|---|
| single worker, unset | **ON** |
| multiple workers, unset | OFF, with a loud warning |
| `AGENTIC_CSRF_STRICT=1` | ON, honoured even when unsafe |
| `AGENTIC_CSRF_STRICT=0` | OFF, the documented escape hatch |

Explicit `1` is still honoured under multiple workers — an operator may have
sticky sessions — but they are warned. The evidence that the flip is safe for
the normal case: `frontend/js/00-csrf.js` wraps `window.fetch`, so all 282
frontend POST sites already send a token, including new ones. A bad token was
always rejected; the only behaviour that changes is that a **missing** token is
now rejected too.

## Two real bugs the flip exposed

Neither was introduced by it. Both were latent and became reachable.

### 1. The server was calling its own API without a token

Three routes reach their own API over loopback:

| Route | Calls |
|---|---|
| `/api/goals/{id}/launch` | `POST /api/supervisor/run` |
| mcp_gateway tool dispatch | `POST /api/mcp/call` |
| mcp_gateway HITL gate | `POST /api/hitl/interrupt` |

With enforcement on, the server rejected itself:

```
POST /api/goals/goal_3b6464443e/launch
{"ok": false, "error": "CSRF token required."}
```

A user-visible production failure — goal launch simply stopped working.

**The fix is not a loopback exemption.** That shortcut was considered and
rejected: a request from `127.0.0.1` is not inherently trustworthy. A malicious
`postinstall` script, a sidecar container sharing the network namespace, or a
browser extension proxying through a local port can all originate one.
Exempting the address turns CSRF from *"prove you are the app"* into *"prove you
are on this machine"* — a much weaker claim, and it would silently undo the
control for precisely the attacker who already has a local foothold. A test
asserts the middleware does not branch on any loopback marker.

`backend/services/internal_http.py` instead has internal callers obtain a
**real** token and send it like any other client. No new trust relationship, no
extra branch in the middleware.

### 2. A latent per-process split inside the app

The first version minted the token in-process. That failed under the in-process
`TestClient` suites: the app object under test writes to *its* `_CSRF_TOKENS`
while the loopback POST travels over TCP to a **separately started** server with
a different store, so the token was rejected as invalid.

The same per-process-state problem as the multi-worker case, appearing inside a
single application. Internal callers now prefer a token issued by the listening
server, falling back to local minting when it is unreachable.

## A performance regression I introduced, and caught

Fetching a token over HTTP on **every** internal call added a synchronous round
trip to each MCP dispatch and supervisor launch.

| | Full suite | Concurrency tests |
|---|---|---|
| before | 165s | pass |
| after the naive fix | **437s** | **2 failing** |
| after caching | 159s | pass |

A token is reusable until it expires, so re-fetching per call bought nothing.
Cached for 300s — well inside the 24h TTL, short enough that a server restart
self-heals. Pinned by a test.

## The test suites were the evidence

Flipping the default broke **479 tests**. That was not a bug in the flip; it was
the flip working, and it is exactly the *"scripted API clients will break"*
scenario the rollout plan predicted. The UAT / system / integration / regression
/ gap / security suites drive a **separately started** server over real HTTP, so
`PYTEST_CURRENT_TEST` is absent from *its* environment and the exemption
correctly does not apply — from the server's point of view they are ordinary
scripted clients.

The response was the one a real operator would take: fetch a token and send it
(`tests/_csrf_client.py`), not disable enforcement for tests. That keeps the
enforced path under test, so a regression in token issuance or validation shows
up as a failure instead of being masked.

Narrowing to zero took four passes, because clients are constructed in three
different places: suite conftests, inline inside test bodies, and per-file
`client` fixtures.

| Pass | Failures |
|---|---|
| flip applied | 479 |
| conftests wrapped | 63 |
| inline clients wrapped | 53 |
| internal loopback fixed | 49 |
| per-file fixtures wrapped | 3 |
| stale assertions updated | **0** |

## Rate limiting: still no Redis, and why

Unchanged, deliberately. The platform is local-first; `run.py` starts one
uvicorn process. For that deployment the bounded in-memory store is the correct
design, with no operational dependency. Adding Redis would impose a service on
every single-process user to serve a topology that may never exist.

**The written trigger for revisiting** — the thing that stops this being either
forgotten or prematurely over-engineered:

> Add a shared store when **either** holds:
> 1. a deployment runs more than one worker *and* intends to keep it that way, or
> 2. rate limiting is relied on as a **security control** rather than an abuse
>    backstop — e.g. to bound authentication attempts.
>
> Until then the correct fix for a multi-worker deployment is to put the limit
> in the reverse proxy, where it is shared by construction.

The interface is already contained: `_sweep_rate_limit_store()` and the store
are isolated enough that swapping the backend is a change, not a rewrite.

## The exemption-list guard

`23-recommendations.md` asked for a test that the CSRF exemption list stays
minimal, on the grounds that exemption lists grow quietly under delivery
pressure. Three tests now cover it:

- the exact set is pinned; adding an entry fails with a message explaining that
  each one is a route accepting state-changing requests with no CSRF protection
- `/api/webhooks/*` is asserted to be the **only** prefix exemption — a second
  wildcard would be a far bigger hole than a single path
- every exempt path must be a health probe or the token endpoint

## Verification

- 43 tests in `tests/unit/test_92_runtime_topology_and_csrf_default.py`
- **full suite: 3647 passed, 36 skipped, 0 failed**
- live behaviour confirmed by `curl`: no token → 403, valid token → 200, bad
  token → 403, webhook prefix unaffected, goal launch → `ok: true`
- the 27/33 multi-worker measurement reproduced against a real 4-worker server,
  and the gate re-measured: default yields to OFF, 40/40 requests succeed
- **regressions proven:** reverting the gate fails 14 of 43; reverting the
  loopback fix fails 1

### A test that proved nothing, and how it was caught

The first version of `_csrf_default()` re-implemented the decision inside the
helper and compared the result against itself. It therefore agreed with any
implementation: reverting `app.py` to the old permissive env read failed only
**1 of 39** tests. It now reads the value `backend.app` actually computes, and
the same revert fails **14 of 43**.

Worth recording as a pattern — a helper that reconstructs the logic it is
testing is indistinguishable from a passing test until something is deliberately
broken to check.
