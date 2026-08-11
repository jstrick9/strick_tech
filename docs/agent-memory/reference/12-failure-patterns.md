# 12 — Failure Patterns

> **Read this one first when reviewing.** These are the shapes that recur across
> every agentic codebase. Each was observed in production systems, reproduced,
> and fixed. Learn the shapes and you find the bugs in minutes rather than days.

---

## Pattern 1 — Confident reporting of unverified things

**The dominant defect family.** A system asserts something it never measured.

Concrete forms observed:

| Surface | The claim | The reality |
|---|---|---|
| Eval harness | `safety_score: 1.0`, passed | Judge never ran; score from keyword overlap |
| Code reviewer | `score: 75`, no issues | Reviewer never ran; file had `eval(user_input)` |
| Repo health | Graded 100/A | Tree was never scanned |
| Risk assessor | "proceed", `is_reversible: true` | Action was `rm -rf /`; assessor returned prose |
| Secrets vault | 🔒 "AES-256 active" | Row was plaintext; padlock shown because the row existed |
| Deploy | ✅ Deployed | Every image and font silently dropped |
| Pipeline | `ok: true, status: complete` | Every stage errored, output empty |
| Git push | ✅ Pushed | 1 of 200 files uploaded; repo half-written |
| Undo | `ok: true, restored: file` | Nothing was written; no path recorded |
| Provider check | "✅ Verified! 338 models" | Probed a *public* endpoint that 200s for any key |
| Integration | "Stripe wired" | Model refused; zero bytes written |

**Why it happens:** the success path is the default and the failure path is an
afterthought. `ok` is written as a literal instead of computed.

**The fix pattern:**
1. Return `None`/`null` for unmeasured — never a plausible default.
2. Exclude unmeasured items from averages; renormalise.
3. Expose the basis (`"human decisions only; auto-approvals excluded"`).
4. State coverage (`"3 of 5 stages succeeded"`).
5. Make the status code match (`502` for "downstream produced nothing").

**⚠️ The `None` fix is half a fix.** Every consumer must be None-safe. This has
caused downstream crashes and false displays four separate times —
`_health_tip`, `round(overall, 2)`, `approval_rate || 0`, `j.score || 75`.
When you make a field nullable, **grep every reader**.

## Pattern 2 — The second door

**21 occurrences and counting.** A guard is added to one entry point and not to
its twin.

| Guarded | Unguarded twin |
|---|---|
| `install/json` safety scan | `/import` (no scan at all) |
| Non-streaming pipeline `ok` | SSE terminal event |
| Delete refusal 403 | `pause` / `resume` / `history` returned 200 |
| `test-connection` auth check | Onboarding wizard's identical check |
| Plugin URL fetch SSRF guard | A2A agent-card fetch; project `/share` |
| `stripe_wire` failure handling | `auth_wire` — same bug, plus worse |
| Deploy tunnel registry | `/share` tunnel — untracked, unstoppable |
| Read policy on secrets table | Write policy — delete was permitted |

**Detection:** after every fix, ask *where else does this shape exist?* Then
actually grep — for the endpoint pattern, the helper name, the phrase in the
comment. Streaming/non-streaming, create/import, read/write, and
UI-path/API-path are the four highest-yield axes.

## Pattern 3 — Stored but never read

Configuration accepted, persisted, displayed — and consulted by nothing.

- `max_runs` / `kill_after_success` — accepted with `ok: true`, loop unbounded.
- Webhook `filters` — set, shown, and never applied; agent ran on every event.
- Per-agent secret `scope` — stored, listed as scoped, read by no retrieval path.
- Budget rules — written by the UI to a table the enforcer never queries.
- MCP conditions — parsed and discarded.

**Why it is worse than absence:** the user configured it *deliberately*, sees it
confirmed, and believes they are protected.

**Detection:** for every config field, grep for a *reader*. If the only
references are the writer and the serialiser, it is decorative.

## Pattern 4 — Empty means unlimited

A guard written as `if required and scope and required not in scope` skips
entirely when `scope` is empty — and empty is usually the default
(`body.get('scope') or []`).

Observed: an **unscoped JIT token validated for every action** while a scoped
one was correctly refused. The least-privileged token was the most powerful.

Same shape: empty webhook secret → unauthenticated public endpoint; empty
filter → no filtering; missing confidence → treated as high.

**Rule:** empty means **nothing**, never everything. Require an explicit
wildcard (`['*']`) for unrestricted.

## Pattern 5 — Absent vs empty

`dict.get('k', default)` supplies the default only when the key is *missing*.
An explicitly-passed empty value bypasses it. `{"secret": ""}` is a blank form
field, not a request for no authentication.

## Pattern 6 — Identifier injection beside a parameterised value

```python
con.execute(f'DELETE FROM "{table}" WHERE "{pk}"=?', (value,))
```

The table was validated; `pk` was not. A `"` closes the identifier and the rest
becomes SQL. Verified: three rows deleted by a value that matched nothing. The
`?` sitting right there makes it *look* safe.

## Pattern 7 — Verification against a permissive oracle

Checking a credential against an endpoint that answers 200 for anything.
OpenRouter's `/models` is public; `/auth/key` is not. The wizard reported
"connected, 140+ models" for `sk-or-v1-total-garbage`.

**Rule:** verify against an endpoint that can say *no*.

## Pattern 8 — Guarding the read and not the write

Database Studio refused to *show* the secrets table and permitted `DELETE` from
it. Destroying credential material is strictly worse than reading it — reading
leaks one secret; deleting locks every agent out and the row is gone.

**Rule:** apply the policy to every verb, and rank the verbs by consequence.

## Pattern 9 — State that does not survive restart

Autonomous loops held in an in-process dict; every deploy silently destroyed
them. The failure is invisible — an empty list is indistinguishable from "you
never created one".

**Rule:** anything called autonomous must persist, restore, and restore
*paused things paused*.

## Pattern 10 — Timestamps: localtime published as UTC

`datetime(created_at,'localtime')` then stamped `Z` by the response layer.
Invisible in a UTC environment, wrong by the offset everywhere else. Found in
four routers.

## Pattern 11 — Silent capability discard

A caller asks for a safety limit; the endpoint returns `ok: true` and ignores
it. **Strictly worse than rejecting the request**, because the user believes the
limit is active.

## Pattern 12 — Fallback that writes garbage to disk

An extractor ending in `else: content = raw_model_output` wrote a model's
refusal to disk as `auth.html` and reported success. Prose served as a login
page. Require the output to be *shaped* like what you asked for.

---

## Test-side failure patterns

These cost as much as product bugs, because they hide them.

- **The test that cannot fail.** Assertions behind `if rows:` when rows are
  always empty; asserting on your own helper rather than the endpoint; reading a
  committed artefact instead of regenerating it. All three were found by
  revert-proofing and none by review.
- **Passing for the wrong reason.** A threshold coincidence, a harness artefact
  (unstarted scheduler → everything reads "paused"), or another layer already
  covering it.
- **The test that pins the bug.** Written against buggy behaviour, it now blocks
  the fix. Update in place with the reasoning inline; never silently delete.
- **A skip is not a pass.** 152 skips instead of 2 meant a wiped `node_modules`,
  not improved code.
- **The measuring instrument is broken.** A revert-proof harness reporting
  `MISSED` while printing the names of failing tests. Self-contradictory output
  is a signal to replace the instrument, not to keep debugging it. Use exit
  codes, not regexes over stdout.

## The review checklist

For any surface, in order:

1. What does this claim, and did it measure that?
2. Where is the twin of this entry point?
3. Is every config field read by something?
4. What happens on empty / absent / malformed input?
5. Does the status code match the outcome?
6. Is every nullable consumer None-safe?
7. Does the write path have the read path's guard?
8. Does it survive a restart?
9. Can it be stopped?
10. Is it in the audit log?
