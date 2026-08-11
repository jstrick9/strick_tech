# 83 — Supervisor workstation: `agent-identity`, `swarm`, `fusion`, `a2a`

**Destination:** `supervisor`
**Tabs:** `agent-identity`, `swarm`, `fusion`, `a2a` (this doc) · `supervisor` + `hitl` (doc 82) · `finetune` (doc 71) · `goals` (shares the DAG surface in doc 82)
**Backend:** `backend/routers/agent_identity.py`, `swarm.py`, `fusion.py`, `a2a.py`
**Tests:** `tests/unit/test_158_module22_supervisor_rest.py` (34)
**Status:** supervisor destination complete — 8/8 tabs

Destination 10 of 20, now finished.

---

## Scope

Doc 82 covered the host pane and `hitl`. This pass closes the four remaining
tabs with substantive backend surface — the ones that **authorise and run**
agents:

| Tab | Router | Lines |
|---|---|---|
| `agent-identity` | `agent_identity.py` | 746 |
| `a2a` | `a2a.py` | 1,563 |
| `fusion` | `fusion.py` | 629 |
| `swarm` | `swarm.py` | 300 |

Five defects, all reproduced against a live server before any code changed.

---

## Findings

### 1. An empty token scope granted every action

`validate_jit_token` is the zero-trust check every agent-authenticated route is
meant to call. Its scope guard read:

```python
if required_action and scope and required_action not in scope:
    return 403
```

The `and scope` clause means an **empty scope skips the check entirely**.
Verified live against two tokens on the same agent:

| token scope | `required_action` | result |
|---|---|---|
| `['read_file']` | `delete_everything` | **403** ✅ |
| `[]` | `delete_everything` | **200 ok** |

The **unscoped token was the more powerful one**. In a zero-trust design an
empty scope is the least privilege there is — it has to mean *nothing*, not
*everything*. This is the same shape as module 11's MCP conditions (a guard that
silently no-ops on an empty value), and it is the most dangerous version of it
because the empty case is also the default: `scope = body.get('scope') or []`.

**Fix:** the check no longer depends on scope being non-empty. An unrestricted
token is still available via an explicit `['*']`, so the capability is not lost
— it just has to be asked for. Plain "is this token valid" (no
`required_action`) still authenticates, and a corrupt `scope` column now denies
rather than raising.

### 2. Token TTL: a 500 on garbage, and a credential born expired

```python
ttl = min(int(body.get('ttl_seconds') or DEFAULT), 86400)
```

Two problems: `int('abc')` raised **HTTP 500**, and only the *upper* bound was
clamped, so `ttl_seconds: -500` minted a token that had **already expired** and
returned it as `{"ok": true, "expires_in": -500}`. A credential that cannot
possibly work, handed over as if it can, is a debugging trap — every later use
fails with "token expired" and nothing points back at the moment of issue. Same
for `max_uses`. Both now coerce safely and clamp both ends, and a non-list
`scope` is rejected rather than iterated.

### 3. The swarm judge's winner was trusted verbatim

`swarm_run` asks a judge model to pick the best response and used
`j.get('winner')` as-is. A judge that names an agent which never ran produced:

```
winner: ghost_agent | winner_output: '' | winner_score: 0.99
improvement_vs_single: 'score: 99%'   ok: true
```

Two real agents had produced usable answers; both were **discarded in favour of
a name the judge invented**, and the run reported 99% confidence in an empty
result. Hallucinated identifiers are routine LLM behaviour, so a verdict about
*which* agent won has to be checked against the agents that actually ran.

**Fix:** the winner must appear in the set of runs that succeeded. Otherwise the
result falls back to the longest valid answer, clears the fabricated score, and
says so: *"Judge named 'ghost_agent', which did not produce a response — fell
back to the longest valid answer (brain)."* A **valid** verdict is still
honoured untouched, pinned by its own test so the fix cannot degrade into
ignoring the judge.

### 4. Fusion returned setup instructions as a model's answer

`/api/fusion/route` hardcoded `'ok': True` beside an `error` field read from the
result — two fields disagreeing about the same call, and the one clients check
first never varied. With no provider configured:

```json
{"ok": true, "error": false,
 "text": "[Stub: anthropic/claude-3.5-sonnet — set OPENROUTER_API_KEY]"}
```

**Root cause, one level down:** `_call_model` hand-rolled its own stub dict with
`error: False` and none of the markers `llm.is_stub()` looks for, so *no*
consumer could tell. Fixing it at the source repairs `/route`, the panel paths
and anything added later, rather than patching one call site. `/route` now
returns `ok: false`, an empty `text`, and a plain-language `error_message`.

### 5. The A2A agent-card fetch was an SSRF primitive

`POST /api/a2a/agents/{id}/verify` fetched whatever URL had been registered for
the agent — caller-supplied — with no address check and redirects followed by
default. Verified live: registering an agent at
`http://169.254.169.254/latest/meta-data` and calling verify made the server
attempt **all three** link-local URLs. It failed only because nothing answers on
that address in this sandbox; on a cloud host that is the instance metadata
endpoint.

The plugin installer refuses the identical URL with *"Refusing to contact
internal address"* — `backend/services/safe_fetch.py` already existed and this
endpoint simply never got the guard. The **"second door"** pattern again, now 19
occurrences.

**Fix:** `url_is_safe()` on every candidate URL, redirects no longer followed,
and blocked attempts reported distinctly (`blocked_urls` plus a different
`error`) so an operator can tell "refused for safety" from "nobody answered".
Loopback stays allowed on purpose — the platform registers its own agents at
`http://localhost:8787/a2a/<id>`, and a localhost agent still verifies
successfully (confirmed live, `status: active`).

---

## Revert-proof

Each fix individually reverted, `__pycache__` cleared each time.
**11 of 11 real breakages caught**, baseline green before and after.

| # | Breakage | Tests failed |
|---|---|---|
| 1 | empty scope grants everything | 5 |
| 1b | corrupt scope not handled | 1 |
| 2 | ttl 500 / negative allowed | 2 |
| 2b | max_uses 500 / negative allowed | 2 |
| 2c | scope type not validated | 1 |
| 3 | hallucinated winner trusted | 5 |
| 4 | fusion route hardcodes ok | 1 |
| 4b | stub unmarked at source | 3 |
| 4c | stub text returned as answer | 1 |
| 5 | a2a SSRF guard removed | 5 |
| 5b | loopback over-blocked | 1 |

Note 5b: the mirror case is pinned too. Over-blocking would break the platform's
own self-registration, so "refuses internal addresses" and "still allows
loopback" are both asserted.

### A "fix" that fixed nothing

Reverting my fanout change failed **zero** tests. Rather than assume a weak
test, I traced it: the original
`next((r for r in runs if r.get('ok')), runs[0])` **already** skipped failed
runs, and `runs[0]` was only reachable when nothing succeeded — a case the
existing 503 catches first. So the "bug" I described in the comment did not
exist. The clearer form is kept, but the comment now records that it is
defensive rather than a fix, so nobody goes hunting for the defect it appeared
to describe.

Two genuinely useful tests came out of chasing it (`fanout` picks the surviving
agent; all-fail returns 503), and both are kept.

## Live verification

```
identity: scope [] + 'delete_everything'      -> 403 (was 200)
          scope ['*'] + anything              -> 200
          no required_action                  -> 200
          ttl_seconds 'abc'                   -> 400 (was 500)
          ttl_seconds -500                    -> expires_in 1 (was -500)

swarm:    judge names 'ghost_agent'
            -> winner brain, real output, score None,
               reason explains the fallback

fusion:   /route with no provider
            -> ok false, error true, stub true, text '',
               "No AI provider is configured…"

a2a:      verify 169.254.169.254 -> blocked_urls x3,
            "Refused to fetch the agent card: the address is internal…"
          verify localhost:8787  -> ok true, status active
```

## Environment note

A sandbox rollback landed mid-session: the server was down, `frontend/dist` was
deleted and `node_modules` was wiped. All committed work was intact (HEAD still
`294553c`); `dist` was restored from git. The wiped `node_modules` caused the
first full run to report **152 skips instead of 2** — every acorn/jsdom-backed
JS test quietly opting out. *A skip is not a pass*: the count was checked against
the known baseline, `acorn`/`jsdom` reinstalled, and the suite re-run before any
result was accepted.

## Cross-module impact

- **`validate_jit_token` is now stricter.** Any caller relying on an empty scope
  to pass an action check will start receiving 403. That reliance was the bug,
  but it is a behaviour change; `['*']` is the explicit replacement.
- **`issue-token`** can now return **400** where it previously 500'd or silently
  accepted nonsense.
- **`fusion._call_model`** returns `error: True` + `stub: True` when no key is
  set. Every consumer of that helper — `/route`, the panel and judge paths —
  sees the change; the panel paths already filtered on `error`.
- **`/api/fusion/route`** can now return `ok: false`.
- **`/api/a2a/agents/{id}/verify`** gains `blocked_urls` and refuses internal
  addresses; a deployment that genuinely pointed an agent at a private-range
  host will now be refused (loopback excepted).
- `swarm` response shape is unchanged; only the values are now checked.

## Suite

`4066 unit (2 skipped)` + `655 regression/system/uat (10 skipped)` =
**4,721 passing, 0 failures**. Linters clean.
