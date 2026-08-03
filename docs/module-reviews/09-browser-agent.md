# Module Review 09 — Browser Agent

**Reviewed:** 2026-08-03 · **Commit:** `8f8a938` · **Sidebar position:** Browser Agent (AI TOOLS)

**Scope:** `backend/routers/browser_agent.py` (639 lines, 10 endpoints) and
`frontend/js/43-browser-agent.js` (494 lines).

**Verification:** every finding reproduced against a running server, including a real local
model (Ollama + qwen2.5:0.5b) to confirm the success path still works.

---

## Findings

### 🔴 1. Runs "succeeded" with neither a browser nor a model

With Chromium unavailable the agent falls back to **simulation mode**: it asks an LLM to
describe the steps it would take, then splits the reply into one step per line.

When no AI provider is configured, `llm.complete()` returns a placeholder tagged
`provider='stub'`. That help text was rendered as a numbered sequence of **completed
browser actions**:

```
step 1: "⚠️ **No OPENROUTER_API_KEY set.**"
step 2: "To enable real AI responses:"
step 3: "1. Get a free key at https://openrouter.ai/keys"
```

The session was then recorded `status: done` with an empty error — so a run with **no
browser and no model** was indistinguishable from a real one.

This is the same stub-ignoring pattern found in Supervisor (Module 7). Worth noting it has
now appeared in three separate modules, which suggests the `provider='stub'` flag needs
handling at the `llm` layer rather than per-caller.

**Fixed** — detects the stub, fails with actionable guidance (install Chromium, *or*
configure a model — noting a local Ollama model works and is free), and persists the
session as an error.

### 🟠 2. The caller overwrote failures with success

After streaming the simulation it called `_db_update_session(session_id, 'done', ...)`
**unconditionally**. Even an outright failure was recorded as a completed session — and it
would have overwritten the error my fix above writes. Now respects an emitted error.

### 🟠 3. An unsafe `start_url` was silently swapped

```python
start_url = _validate_url(raw_url) or 'https://duckduckgo.com'
```

Asking the agent to visit an internal address produced a perfectly normal-looking run
**against a completely different site**, with nothing in the response indicating the URL had
been rejected. The SSRF block worked; the silence was the problem.

**Fixed** — 403 for a blocked target, 400 for a malformed one.

### 🟡 4. One error message covered two different failures

A well-formed URL rejected by the SSRF policy got *"Invalid URL — must be http:// or
https://"* — confusing for a URL that already is. Blocked targets now say so explicitly.

### 🟡 5. Five error paths returned HTTP 200

Including `DELETE /sessions/{id}`, which echoed back a `session_id` it had **not** deleted.
Mapped by class: validation 400, blocked target 403, missing session 404, internal 500.

---

## Verified working (no change needed)

- **SSRF protection is solid** — `_validate_url` reuses the platform policy. All eight
  payload families I tried were rejected: metadata endpoints, localhost, loopback,
  `file:`, `javascript:`, `data:`, `ftp:`, and empty.
- `/status` **honestly reports** `mode: "simulation"` and gives the exact install command —
  this module was upfront about its degraded state, which made the review easier.
- Session listing, deletion, screenshot capture and the gallery all work.
- **The frontend is sound** — every fetch checks `response.ok`, all rendered text is
  escaped, and the `img src` values are server-constructed (`/preview/browser_screenshots/…`,
  base64 from the server) rather than attacker-influenced. I checked specifically because
  the equivalent Web Search code had a `javascript:` href gap.

---

## Cross-module impact

| Module | Impact |
|---|---|
| **Web Search** | Shares the SSRF guard; both now reject blocked targets with a distinct 403. |
| **Supervisor** | Same stub-ignoring bug class — fixed there in Module 7. |
| **E2E / Testing** | Also depends on Playwright; its `/status` reporting is worth checking when I reach it. |

---

## Tests added

`tests/unit/test_58_browser_agent_module_review.py` — **25 contracts** covering stub
detection (including that the guard *precedes* step emission), failure persistence,
`start_url` handling, 8 families of unsafe URL, message clarity and status codes.

Two existing contracts updated: both POSTed bodies missing a required field and asserted
HTTP 200. The rejection they guard is unchanged and now asserted against a 400.

**Suite:** 2948 backend passed / 12 skipped / **0 failed** · 75 vitest passed · ruff clean.

---

## Recommended follow-ups

1. **Handle `provider='stub'` at the LLM layer.** This is the third module (after Chat and
   Supervisor) where a caller ignored the flag and reported fabricated success. A shared
   helper — or having `complete()` raise unless the caller opts into stubs — would close the
   whole class rather than one instance at a time.
2. **Chromium is not installed and cannot be here** (no root for the system libraries), so
   the real Playwright path is untested by me. It's worth exercising on a machine that has
   it before trusting the non-simulation branch.
3. **Simulation mode is inherently make-believe.** It's clearly labelled, which is the right
   call, but consider whether an agent that describes browsing it didn't do is worth keeping
   versus simply directing users to install Chromium.
