# Cross-Cutting Hardening

Items that spanned modules and were never owned by any single one. Seven
closed; two were already fixed and my list was stale.

---

## 1. CSRF protected nobody

```python
if csrf_token and csrf_token not in _CSRF_TOKENS:   # reject
```

A request that **omitted** the header skipped validation entirely. Verified
against a running server with `PYTEST_CURRENT_TEST` unset, so the real path ran:

| Request | Before |
|---|---|
| `POST /api/tasks` (no header) | **200** |
| `POST /api/tasks` (bogus token) | 403 |

An attacker's forged cross-site request does not send the header. **The control
rejected only honest mistakes.**

### Why it was written that way

The frontend never sent a token across any of its **282 POST call sites**, so
requiring one would have broken the app. That is why this could not be fixed
server-side alone, and why it survived so long.

`frontend/js/00-csrf.js` wraps `window.fetch` **once**, so every same-origin
mutation gets the token — and a *new* call site is protected by default, which
the per-call-site arrangement could never achieve. It refuses to attach the
token cross-origin (that would turn a CSRF fix into a token-disclosure bug) and
retries once on expiry, since the 24h TTL and server restarts would otherwise
surface as unexplained 403s mid-session.

Server enforcement is opt-in (`AGENTIC_CSRF_STRICT`) so upgrading does not break
scripted API clients, but a missing token is **logged either way** — operators
can see what would break before switching it on. A bad token is always
rejected. Webhooks are exempt: inbound deliveries from GitHub/Stripe/CI
authenticate by HMAC and cannot know a CSRF token.

Verified under `AGENTIC_CSRF_STRICT=1`: no token 403, bad token 403, valid token
200, GET unaffected, webhooks reachable, and a simulated frontend flow succeeds.

## 2. `safeUrl()` existed in one file; eight needed it

`escHtml()` does **not** make a URL safe. It escapes quotes and angle brackets,
so `javascript:alert(document.cookie)` survives intact and still executes on
click — confirmed in node.

Moved to `01-app-core.js` and applied to all **19** data-driven hrefs. Several
were entirely unescaped (`${j.url}`, `${u.html_url}`). This is the same *one
local copy of a control* shape that let SSRF recur across three modules.

A repo-wide test now fails on any `href="${...}"` not routed through it — and
**it immediately found one I had missed.** That one turned out to be a local
variable literally named `safeUrl`, shadowing the global function. Not
exploitable (the value was already same-origin-restricted), but any later edit
in that scope reaching for `safeUrl()` would have silently got a string.

## 3. Rate-limit store was unbounded

A `defaultdict` keyed by client IP with no eviction: every new source address
added a permanent entry. A scan across a /16 grows it without limit and the
process never returns the memory. **Rate limiting should not become the thing
that fails under abuse.**

Opportunistic sweep (no timer, no lock) plus a 10k-client cap with least-recent
eviction, logging that a shared store is needed for multi-process deployments.

## 4. Version drift

`config.yaml` said `"6.0"`; `VERSION` said `11.5.0` — five majors stale, and
**nothing parses the key**, so it was pure misinformation for anyone reading the
config. A test now enforces the match, because a comment can drift again.

## 5. Control Tower runs were not durable

`agent_traces.status` defaults to `'running'` and `_active_runs` is in-memory,
so a restart mid-run stranded the row as permanently running — the UI showing an
in-progress run for a process that no longer exists. Reproduced, then fixed with
startup reconciliation mirroring `supervisor.reconcile_orphaned_runs()`.

> **Correction.** My open-items list said *"Supervisor runs not durable"*.
> Supervisor was already fixed in an earlier module (21 DB references,
> reconciliation at import). The stale entry was mine; **Control Tower** was the
> one still affected.

## 6. CSP

`object-src 'none'`, `base-uri 'self'`, `form-action 'self'` and
`frame-ancestors` added — all free (nothing uses them), each closing a real
vector. An injected `<base>` silently reroutes every relative URL on the page,
including script sources.

`script-src 'unsafe-inline'` **cannot** be removed: the frontend renders **772
inline `onclick` handlers** and 5 inline `<script>` blocks. A CSP that breaks
the product gets reverted within a day. It is now documented in the code as a
known weakness, stating plainly that ~714 `innerHTML` assignments are
unprotected and XSS defence rests on `escHtml()` per call site — which Modules
10 and 17 each proved insufficient alone.

**This is deliberately not "fixed".** Removing it needs the inline handlers
gone first; that is a dedicated refactor, not something to slip into a security
commit while claiming the CSP is strict.

## 7. `chat_log` discarded 12000 characters per message

The API accepts 16000 characters; `_log_chat` stored `message[:4000]`. The full
reply renders in the stream and a **truncated one appears on reload**, with
nothing to explain the difference. SQLite `TEXT` has no fixed width, so the cap
protected nothing. Verified: 9000 characters now store as 9000.

---

## Two items that were already fixed

Recorded rather than quietly dropped, because a stale worry-list is its own kind
of misinformation:

* **Fine-tuning honest but unimplemented** — `finetune.py` already refuses
  honestly instead of returning a fabricated `eval_loss` and `status:
  "completed"`.
* **Knowledge Graph has no UI for relations** — `kgAddRelation()` exists behind
  an *"＋ Add Relation"* button on the entity detail view. Verified live by
  creating two entities and relating them through the API that button calls.

---

## Tests

`tests/unit/test_86_cross_cutting_hardening.py` — **34 cases**.
**Proven to catch the bugs: with the changed files stashed, 19 of 32 fail.**

Two existing tests updated because they asserted **location** rather than
behaviour:

* `test_54` pinned `app.py` under 800 lines. The hardening legitimately added
  lines — a size threshold measures the wrong thing. Now asserts the task CRUD
  is not back in `app.py`.
* `test_57` required `safeUrl` to be defined *in websearch.js*. It moved to the
  shared core; the test now checks both that the core defines it and that
  websearch still uses it.

### Self-correction

My guard test for the truncation fix asserted `'[:4000]' not in chat_py` against
the **raw source**, and failed on the explanatory comment mentioning the old
value — the *"assertion matching its own fix comment"* trap this review has hit
in six modules. My second attempt tokenised the file, which joins tokens with
spaces and turns `[:16000]` into `[ : 16000 ]`. The working version strips
comment-only lines while preserving spacing.

Full suite: **3512 passed / 19 skipped / 0 failed**.

---

## What remains open, and why

Stated explicitly so the list is honest rather than empty:

1. **`script-src 'unsafe-inline'`** — needs 772 inline handlers removed first.
   Tracked as a refactor, not a security patch.
2. **Rate limiting is per-process.** The bounded in-memory store is correct for
   a single-process deployment; multi-process needs Redis or equivalent. The
   code says so where it matters.
3. **`AGENTIC_CSRF_STRICT` defaults off.** Deliberate for upgrade safety. New
   deployments should set it; the log line tells operators when it is safe to.
