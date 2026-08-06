# 36 — Honest responses: refused writes and fake progress bars

Autonomous hunt, batch 23. Two findings, same family: **the server told the
user something had worked when it had not.**

---

## 1. 62 mutating endpoints answered HTTP 200 when they refused the write

Probed live against every bodyless POST/PATCH/PUT route — 226 of them.
**62 returned `200 {"ok": false, "error": ...}`**:

```
POST /api/agents      -> 200  {"ok":false,"error":"name is required"}
POST /api/hooks       -> 200  {"ok":false,"error":"prompt is required"}
POST /api/evals/run   -> 200  {"ok":false,"error":"prompt and response required"}
```

### Why this matters more than it looks

`frontend/js/00-net-feedback.js` — the global network layer — reports failures
**by status code** (5xx, 429, 401, 403). A 200 sails straight through it. So
the dialog closes, the list does not change, and **the user is told nothing at
all.** Same class of bug already fixed ~180 times endpoint-by-endpoint.

### Fixed in the middleware, not at 390 call sites

`return {'ok': False, ...}` appears **390 times across 60 routers**. Editing
each is 390 chances to miss one, and every *new* endpoint would reintroduce it.
One rule covers all of them, including routes added later.

Result: **62 → 7**, and the 7 remaining are correct (nested `ok:false` inside a
results array, or deliberately exempt).

### What is exempt, and why

The distinction is: did the server **decline to do what was asked** (refusal →
4xx), or did it **do exactly what was asked and the answer is negative**
(report → 200)?

| Exempt | Because |
|---|---|
| `/api/secrets/test-connection`, `/api/pluginsdk/validate`, `/api/security/validate-csrf`, `/api/rbac/tokens/verify` | Diagnostics. Asked "is this valid?"; "no" is a successful answer. |
| `/api/system/git/commit`, `/api/tauri/build/cancel`, `/api/gitai/changelog`, `/api/memory/qdrant/sync-all` | "Nothing to do" is a normal outcome. |
| `/api/deploy/vercel`, `/api/deploy/netlify` | Unconfigured integration. The body carries **setup instructions** — turning first-run guidance into a client error would be worse. |
| `/api/mcp-gateway/call`, `/api/connectors/*/execute` | **Policy verdicts.** The engine ran successfully and returned "deny", with `policy_decision`, `denied` and an audit `call_id`. A 4xx would make "the guardrail worked" indistinguishable from "the guardrail is broken". |

---

## 2. Two setup flows showed a fake progress bar

Tauri (Rust + tauri-cli) and Browser Agent (Playwright + Chromium) both had:

```
POST /setup/auto-install   spawns the installer, returns ok:true instantly
GET  /setup/stream         yields HARDCODED percentages on a timer
```

The stream was pure theatre — `asyncio.sleep(0.6)` between five fixed steps,
then:

> ✅ Setup complete! Rust & Tauri CLI are ready.

**having checked nothing.** The UI toasted success **about three seconds** after
the click, against a `cargo install` that takes on the order of ten minutes.

Three consequences, worst first:
1. The user acts on "ready", clicks Build, and gets a confusing failure.
2. A **failed** install reported success — nothing to retry, no error text.
3. `auto-install` returned `ok:true` whenever `Popen` did not raise, which is
   essentially always, even for a missing binary or a non-zero exit.

### Fixed

`backend/services/install_jobs.py` tracks the real process: captured stdout,
real exit code, bounded log buffer, one job per key. Both streams now report
what is actually happening, derive progress from **observed milestones** in the
output, and never reach 100% unless the process exited 0. An idle stream says
*"No installation is running"* instead of inventing one.

The UI now branches on `ok` rather than on `done` alone: a failure keeps the
card up with the server's own error text, because that is the only thing the
user can act on.

Verified in all three states — success (`done`, rc 0), failure (`failed`, rc 1,
error captured), and spawn failure (the case the old `try/except Popen` got
wrong).

**Found while probing:** `POST /api/tauri/build` started a genuine Rust
compilation that consumed the sandbox. The install is real; only the reporting
was fake.

---

## Two mistakes I made, corrected

Worth recording because the second one nearly shipped as a silent no-op.

**v1 consumed the response body.** Reading `response.body_iterator` to inspect
the payload *exhausts* it — SSE endpoints and downloads were left with a dead
iterator and returned **HTTP 500**. Caught by
`tests/unit/test_103_type_confusion.py` on `/api/chat`.

**v2 was a no-op, and I reported its predecessor's numbers.** Skipping anything
with a `body_iterator` looks like the safe fix, but `BaseHTTPMiddleware` wraps
**every** response in a streaming shim — so that attribute is always present
and v2 did nothing. I had already reported "62 → 7" from v1; that figure was
not valid for v2. Re-measured after v3: **62 → 7 confirmed**, with SSE intact.

v3 reads the iterator **and rebuilds it**, and identifies real streams by
`content-type` rather than by the presence of a wrapper.

---

## Tests

`tests/unit/test_108_honest_responses.py` — 23 tests. **Proven to catch the
bugs: with all changes reverted, 16 of 23 fail.**

**21 pre-existing tests were updated, not deleted.** Every one asserted
`status_code == 200` for an operation the server refused — they were pinning
the bug. The behaviour under test is unchanged and still asserted; only the
status moved. Two are worth calling out:

- `test_preview_sibling_path_is_rejected` and
  `test_marketplace_zip_rejects_path_traversal` are **security** tests. A
  rejected path traversal answering **400** is strictly better than 200, and
  asserting 200 was holding that wrong in place.

11th instance of the **"assertion matching its own fix comment"** trap: the
first version of `test_setup_streams_no_longer_emit_invented_progress` failed
against the *fixed* build, because the docstring explaining what the fake
stream used to emit quotes the very string it asserts is gone. Now strips
triple-quoted blocks as well as `#` comments.

## Regression status

| Suite | Result |
|---|---|
| `tests/unit` | **2969 passed, 2 skipped, 0 failed** |
| `tests/regression` + `system` + `integration` + `uat` | **1044 passed, 17 skipped, 0 failed** |
| ruff · inline-handler · globals linters | pass |

**Browser suite not verified this session.** It is unstable in this sandbox —
`page.goto` times out partway through a file as the spawned server is torn
down. Confirmed **pre-existing**: the identical run against the committed tree
(`git stash`) produces the same `8 passed, 6 errors`, so it is environmental
rather than a regression from this batch. Flagged rather than claimed green.
