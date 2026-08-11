# 88 — The deferred backlog

**Subject:** items carried over by earlier passes
**Backend:** `backend/routers/database.py` (Supabase), `backend/routers/codesearch.py`
**Frontend:** `frontend/js/14-prompt-library.js` (the review panel)
**Tests:** `tests/unit/test_163_module27_deferred_backlog.py` (22)
**Status:** reviewed, fixed, verified live

---

## Why these were deferred, and why that stopped being fine

Each item sat outside the destination being reviewed when it was found.
Deferring was the right call at the time — chasing every adjacent surface would
have made each pass unbounded. Leaving them deferred permanently is a different
thing, and all four turned out to belong to defect families this review has been
tracking all along.

Four defects, all reproduced against a live server before any code changed.

---

## Findings

### 1. The Supabase surface had no audit trail at all

Noted in doc 86, not addressed there. The SQLite half of Database Studio has
**18 `audit_sql()` call sites** — every query, insert, delete and schema change
recorded with an outcome and a risk level. The Supabase half had **zero**.
Verified live: after driving an insert through the endpoint,

```sql
SELECT COUNT(*) FROM audit WHERE action LIKE 'supabase%'   ->  0
```

The asymmetry *is* the defect. An operator reading the audit log sees a complete
history of local database activity and unbroken silence where the remote
database was written to — with nothing indicating a second surface exists. A gap
you cannot see is worse than one you can, because the log reads as authoritative
either way.

`_audit_supabase()` now records query / insert / ai-setup with outcome and risk,
best-effort so an audit write can never be the reason a user's database
operation fails — matching `audit_sql()`'s own failure posture.

### 2. A rejected Supabase write returned HTTP 200 with the error under `data`

```python
return {
    'ok': r.status_code in (200, 201),
    'data': r.json() if r.status_code in (200, 201) else r.text[:200],
}
```

`data` is the key a **successful** insert uses for its returned rows. Reproduced
with a 403 `"new row violates row-level security policy"`: a caller reading
`data` got a denial string where it expected records, at HTTP 200.

Fixed: errors go under `error`, the status reflects the refusal (400 for a
client-side rejection, 502 for a remote failure). The table name — which lands
in the request **path** — is now validated to the same shape the SQLite
endpoints already required, so a value like `../rpc/something` can no longer
reshape the URL.

**A third bug, found by my own test.** `ai-setup` checked only `if not sql:`,
but `_strip_markdown_sql()` returns prose unchanged — so
*"I'm sorry, I can't."* was handed back as the schema SQL the user is instructed
to paste into their production database. The response now requires DDL-shaped
output and says explicitly that nothing was executed here.

### 3. `/api/project/share` opened an untracked public tunnel

**Second door #21.** `deploy.py` maintains `_active_tunnel` precisely so a
tunnel can be listed and stopped, and module 19 hardened that path (duplicate
-start protection, stale-proc cleanup, audited stop). `/share` spawns the
identical `cloudflared` quick-tunnel and recorded it nowhere. Verified with a
stubbed cloudflared:

```
/share            -> public_url https://probe-share.trycloudflare.com
GET  /api/deploy/tunnel      -> no tunnel running
POST /api/deploy/tunnel/stop -> nothing to terminate
```

The machine was published to the internet and the only way to un-publish it was
to kill the process by hand. **A public tunnel you cannot see is bad; one you
cannot close is worse.**

Now shares the same registry: both surfaces list and stop the same tunnel, an
already-running one is reused rather than duplicated, a tunnel whose URL could
not be parsed is terminated instead of orphaned, and the response carries
`stop_endpoint` so a user who has just exposed their machine is told how to stop.

### 4. `/api/project/review` invented a passing score

```python
review = {'issues': [], 'summary': '', 'score': 75, 'highlights': []}
```

Every failure path fell back to that default. Reproduced against a file
containing `eval(user_input)` and `os.system("rm -rf " + user_input)`:

```
score 75 · issues [] · ok true
```

This is the module-9 gitai defect (graded an unscanned tree 100/A) and the
module-16 eval defect (scored a malware response "fully safe") appearing a
**third** time. A reviewer that invents a passing grade is worse than no
reviewer: it is a green tick over unexamined code.

Now returns **502** with `reviewed: false`, `score: null`, and an error saying
the empty issue list is not a pass.

**The consumer needed fixing too.** The review panel did `j.score||75` and
rendered `"✅ No issues!"` for an empty list — so an unreviewed file displayed a
green **75/100** above a clean bill of health. That is the nullable-value trap
this review has now hit **four** times (`_health_tip`, `round(overall, 2)`,
`approval_rate||0`, and here), and it is the reason a `None` fix is only half a
fix until every consumer is checked.

---

## Revert-proof

**11 of 11 breakages caught.** Baseline green before and after.

| # | Breakage | Tests failed |
|---|---|---|
| 1 | supabase insert not audited | 1 |
| 1b | supabase failure not audited | 1 |
| 1c | supabase query not audited | 1 |
| 2 | rejected insert returns 200 with error under `data` | 2 |
| 2b | supabase table name unvalidated | 1 |
| 2c | ai_setup accepts prose as SQL | 1 |
| 3 | share does not register its tunnel | 4 |
| 3b | share does not reuse a running tunnel | 1 |
| 3c | share hides the stop endpoint | 1 |
| 4 | review invents score 75 | 3 |
| 4b | review returns 200 when unrun | 1 |

The harness is the direct form adopted in module 26 — one subprocess per case,
restore between, **exit code as the authority** rather than a regex over stdout.
Case 4b's first anchor did not match and was reported as `ANCHOR MISSING` rather
than silently counted; it was then verified separately.

### Two corrections

**My own test found a bug my fix had missed** — the `ai-setup` prose-as-SQL case
above. Writing the failure case first is what surfaced it; an emptiness check
looked sufficient until something asserted on it.

**A wrong URL prefix, caught before it became a conclusion.** I probed
`/api/codesearch/review` and got a 404. The router's prefix is `/api/project`.
Had I stopped there I would have recorded "endpoint unreachable" — instead the
correct path showed both `/review` and `/share` *are* called from the UI, which
is what made the frontend fix necessary.

## Live verification

```
supabase insert (403)   -> 400, error under `error`, audited
supabase insert (201)   -> 200, data = rows, audited
supabase query  (200)   -> ok true, audited
table '../rpc/evil'     -> 400 Invalid table name
ai-setup prose          -> 502, nothing returned as SQL
share                   -> registry populated, stop_endpoint present
share again             -> tunnel_reused true, no second process
deploy GET /tunnel      -> active true
deploy POST /tunnel/stop-> ok, registry cleared, process terminated
review (unrun)          -> 502, score null, reviewed false
review (real)           -> score 12, 1 issue
```

## Cross-module impact

- **`/api/supabase/*`** can now return **400** and **502** where they always
  returned 200; the insert response no longer carries `data` on failure.
- **`/api/project/review`** can return **502**, and `score` is now nullable —
  the one frontend consumer was fixed; any other reader must be None-safe.
- **`/api/project/share`** now imports `deploy._active_tunnel`. That is a
  deliberate coupling: one registry is the point. It also means `/share` can
  return a tunnel it did not start.
- No change to the SQLite paths, `db_policy.py`, or the deploy router itself.

## Suite

`4192 unit (2 skipped)` + `664 regression/system/uat (1 skipped)` =
**4,856 passing, 0 failures**. Linters clean.

## Still open

- **Gap #4 (name the kernel)** and **#8 (scoped tool loading)** — both touch the
  agent runtime and are architectural rather than defect-driven. Genuinely the
  largest remaining items.
- **The `tauri` pane** — `scripts/tauri_build.py` exists with no router and no
  pane registration; it is a build script, not a user-facing destination. It
  should either be wired up or the reference dropped; it is not a bug today.
- **The command palette's own search** — reviewed as reachable, not deeply.
- **Known environmental:** ~11k CSP `style-src` console messages;
  `test_120_audit_ratchet.py` (~9 min) excluded from the fast loop; 238
  pre-existing ruff findings under `tests/`.
