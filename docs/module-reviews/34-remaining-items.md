# 34 — Closing the outstanding items

Everything left on the "Not Solved" list, fixed rather than documented.

| Item | Status |
|---|---|
| 5 CDN origins in `script-src` | **Vendored.** `script-src 'self'`, zero external requests |
| 3rd-party CSP violations (Monaco, 3d-force-graph) | **Gone** — they are our files now |
| `connect-src` too permissive | **9 external origins → 0** |
| Rate limiting per-process | **Budget divided across workers** |
| CSRF unusable under multiple workers | **Fixed** — stateless signed tokens |
| `/api/tts/voices/{id}` accepts anything | **Bounded + 400/409** |
| ~20 idempotent DELETEs return bare `ok:true` | **All 20 report `deleted`** |
| 162 empty catch blocks | **Triaged**; user-visible ones now report |

---

## 1. Vendoring: the app makes no external requests at all

`script-src` allowed five CDNs. Each is an origin that can execute script with
full same-origin privileges, so a compromise or DNS hijack of any one of them
was a full application compromise — `'self'` plus five CDNs is materially
weaker than `'self'`. It also meant a "local-first agentic OS" did not work
offline.

Vendored into `frontend/vendor/` (13 MB, served from the existing `/static`
mount): `three.min.js`, `3d-force-graph.min.js`, `highlight.min.js` + its CSS,
Monaco `0.47.0` (`min/vs`, minus 9 non-English locale bundles ≈ 1.5 MB), and
Inter — the CSS plus 7 `woff2` subsets, rewritten to relative paths.

This also closed **the two CSP violations previously marked unfixable**. Monaco
and 3d-force-graph both inject inline styles; as third-party scripts they could
not be fixed and could not be reliably hashed, because the hash changes
whenever the CDN serves a new build. Pinned locally, that problem disappears.

**Enforcing CSP now:**
```
script-src 'self'
style-src  'self' 'unsafe-inline'
font-src   'self' data:
connect-src 'self' blob: ws: wss: http://127.0.0.1:* http://localhost:*
```

Verified in Chromium across all 27 panes: **0 CSP violations, 0 external
requests, 0 page errors**, Monaco/THREE/ForceGraph3D all load, all 6 Inter
weights render.

`PREVIEW_CSP` deliberately still allows the CDNs — AI-generated pages
legitimately load libraries from them, and that is a different trust boundary.

## 2. `connect-src`: 9 external origins → 0

The policy allowed `api.github.com`, `openrouter.ai`, `slack.com`,
`gmail.googleapis.com`, `graph.microsoft.com`, `oauth2.googleapis.com`,
`www.googleapis.com`, `*.atlassian.net`, `api.notion.com`.

**The browser never contacted a single one.** Verified two ways: a source scan
for `fetch`/XHR/WebSocket to an absolute external URL returns nothing (the only
occurrences of those hostnames in `frontend/` are link hrefs and help text),
and a Chromium run across every pane recorded zero external requests. All nine
integrations are called **server-side with httpx**, where CSP does not apply.

So the allowances bought nothing and cost real security: `connect-src` is the
directive that limits where injected script can exfiltrate to, and each origin
was another channel out — `api.github.com` and the Google endpoints accept
arbitrary attacker-controlled query strings.

## 3. CSRF under multiple workers: fixed, not warned about

Tokens lived in a per-process dict, so a token minted by worker A was unknown
to worker B. **Measured, `--workers 4`, 60 POSTs carrying one valid token:**

| | Accepted | Rejected |
|---|---|---|
| Before | **13** | 47 |
| After | **60** | **0** |

Forged tokens still refused 8/8.

The previous mitigation detected the topology and refused to enable enforcement
by default. That is a guard, not a fix — it left every multi-worker deployment
permanently unable to run with CSRF protection on.

A CSRF token does not need a server-side record; it needs to be unforgeable and
to expire. Tokens are now `<issued_at>.<nonce>.<hmac_sha256>`, signed with a key
from `$AGENTIC_CSRF_SECRET`, else a `0600` file in the data directory, else
in-process (warned). No Redis, no operational dependency added to the
single-process deployment the platform is built around.

The signature is verified **before** the timestamp is parsed — otherwise an
attacker picks their own expiry. Constant-time comparison throughout.

`csrf_strict_is_safe()` now returns True in every topology, with one honest
exception: an in-process key (no secret set *and* an unwritable data directory)
reproduces the original failure, so that case still reports unsafe and warns.

## 4. Rate limiting: the configured ceiling is the one that applies

Each worker counted independently, so N workers allowed N × the configured
limit. An operator who set 300 and ran 4 workers got 1200 and was never told.

`app.py` now divides the budget by the worker count:

| Workers | Configured | Per worker | Effective |
|---|---|---|---|
| 1 | 300 | 300 | 300 |
| 4 | 300 | 75 | 300 |
| 8 | 300 | 37 | 296 |

Load balancing is not perfectly even, so the residual error is in the
**conservative** direction: a client can be throttled slightly early, never
allowed past the ceiling. A shared counter would be exact and remains the
answer if exactness is needed; the trigger is still in `25-runtime-topology.md`.

## 5. Idempotent DELETEs: 20 of 20 now say what they did

`DELETE /api/specs/zzz-does-not-exist` returned `200 {"ok": true}`.

The **200 is deliberately kept** — a DELETE of something absent has achieved
what the caller asked for, and idempotency makes retries safe. What was wrong
is that the response could not distinguish the two cases, so the UI reported
success after a typo, a stale list, or a double-submit that raced. Every one of
these already had the number (`cursor.rowcount`) and discarded it. All 20 now
return `deleted: true|false`.

Three further bugs surfaced while doing this:

- **`/api/loops`** — APScheduler raises for an unknown job, so deleting an
  already-stopped loop returned `ok:false` **with HTTP 200**. Worse, `_jobs.pop`
  sat *after* the raising call, so the local registry was never cleaned: the job
  stayed listed in `/api/loops` forever and every retry hit the same error.
  Also, refusing to delete a protected system job returned 200 → now **403**.
- **`tts.py`** — DELETE looked up the raw `agent_id` while PATCH stored
  `agent_id.strip().lower()`. A preference saved as `"Researcher"` could never
  be reset; the endpoint answered `ok:true` while the setting persisted.
- **`agent_identity.py`** — logged a `permission_revoked` audit event even when
  nothing was revoked. This is the identity audit log; it must not contain
  fiction.

## 6. TTS voice preferences

`PATCH /api/tts/voices/{id}` returned **HTTP 200 with `ok:false`** for an
unknown voice — the same 200-on-failure pattern already corrected across ~180
endpoints. Now **400**.

It also accepted any `agent_id` and persisted it, rewriting the whole JSON file
each time; a loop over generated ids grew it until the disk filled. Now capped
at 500 with a **409**, and ids limited to 128 characters. Verified: 700 distinct
ids → 491 accepted, 209 rejected, file holds exactly 500.

## 7. Empty catch blocks: triaged, not bulk-edited

162 remain. Most are legitimate — localStorage probes that throw in private
mode (30), `JSON.parse` of optional cached data (34), read-only refreshes a
later poll retries (42). **17 wrapped a mutating request**, where the user's
action failed and nobody said so.

The user-visible ones now report:

- **Creating a spec** was the worst: it swallowed a non-2xx response, a
  non-JSON body, *and* a success with no `spec` (which throws on `d.spec.id`).
  In every case the dialog closed, the list did not change, and the user
  believed their spec existed. Verified with a forced 500 — the toast now reads
  *"Could not create the spec (HTTP 500)"*.
- **Marking a notification read** — silent failure left the badge count wrong
  and the notification returning on the next poll.

The genuinely fire-and-forget ones (UI-mode mirror, prompt use-counter) are
**commented as deliberate** rather than left looking like oversights.

---

## An animation bug the tests found

After the colour work, `test_every_pane_has_no_accessibility_violations`
started failing on Studio: the "⚡ LIVE" badge measured **2.44:1**.

The colour was fine — `--green` on `#0d2a1a` is **6.76:1**. The badge used
`animation: pulse`, which fades **opacity to .4** at the midpoint, and opacity
multiplies contrast. For most of every 2-second cycle it sat far below the
minimum.

This also made the audit itself unreliable: **an earlier sweep sampled a bright
frame and reported the pane clean.** Fixed by pulsing the border glow instead,
so the text stays at full opacity — plus a `prefers-reduced-motion` opt-out.
The test now **samples two animation phases**, and that change is proven: with
`animation: pulse` restored it catches ratios of 2.18, 2.61, 3.51 and 3.75.

## Tests

`tests/unit/test_107_remaining_items.py` — 25 tests. **Proven to catch the
bugs: with all changes reverted, 18 of 25 fail.**

Six pre-existing tests were **updated, not deleted**, because they pinned
limitations that no longer exist:

- `test_86` asserted the literal source `if csrf_token not in _CSRF_TOKENS`,
  pinning the per-process dict — the multi-worker bug itself. Now asserts the
  *behaviour* (bad token rejected, rejection not nested under strict mode).
- `test_92` asserted CSRF **must** default to OFF under multiple workers. That
  is now inverted, with a new test covering the one case that still yields.
- `test_51` asserted the 3d-force-graph CDN URL; now asserts the vendored path.

The 10th instance of the **"assertion matching its own fix comment"** trap was
hit here too: the first version of `test_no_frontend_file_references_a_cdn`
failed against the *fixed* build, because the HTML comment explaining why the
fonts were vendored names the very hostnames it asserts are gone. Fixed by
stripping multi-line HTML/CSS comments as blocks.

## Regression status

| Suite | Result |
|---|---|
| Full non-browser | **3990 passed, 19 skipped, 0 failed** |
| Browser E2E | **82 passed, 0 failed** |
| axe-core, 28 panes | 0 violations |
| CSP violations / external requests | **0 / 0** |
| ruff · inline-handler · globals linters | pass |
