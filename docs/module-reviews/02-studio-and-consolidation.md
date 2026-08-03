# Module Review 02 — Code Studio · Platform Consolidation · Budget Guardrails

**Reviewed:** 2026-08-03 · **Commits:** `1f76d8d`, `a35c3e3`, `79f60a0`, `7586321`

Covers three pieces of work: the Code Studio module review, the platform-wide
consolidation you approved (workstation model + removing unreachable routers), and
the first agentic-core addition (real budget enforcement).

---

## Part 1 — Code Studio module review

### 🔴 The Lint button could never report a problem with your code

`POST /api/studio/lint` **ignored the request body entirely** and instead walked
Agentic OS's own `backend/*.py` and `frontend/js/*.js`. Linting your broken file in
Studio always returned *"Syntax validation passed."*

Compounding it, the frontend's `catch` block logged *"Syntax validation check green."*
even when the request **failed**. Between the two, the feature was structurally
incapable of surfacing an error.

**Fixed:** lints the submitted content (py/js/jsx/mjs/cjs/json), strips Node's internal
stack trace so errors are readable, and reports real per-error detail. The old
whole-platform self-check is preserved behind an explicit `{"scope":"platform"}` opt-in.

### 🔴 AI edit could silently blank or corrupt your file

Fence-stripping was `text.split('\n').slice(1).join('\n')` — which assumes a code fence
always spans multiple lines and that nothing follows the closing fence. Two real
corruptions:

| Model reply | Old result |
|---|---|
| `` ```Hello World``` `` | **empty string** → "Accept & Apply" wiped the file |
| ``` ```html\n<h1>Hi</h1>\n```\nHope that helps! ``` | fence **and** prose written into the source |

Replaced with a shared `window.extractCodeFromResponse()` handling all 8 shapes, now
used by both the AI-edit and AI-format paths (AI-format had the same defect via a pair
of anchored regexes).

### 🟠 Valid short edits were discarded as "empty"

A `proposed.length < 20` guard rejected legitimate small changes — a heading tweak, a
one-line CSS fix — with a misleading *"AI returned empty response"*. Now only genuinely
empty output is rejected, and a no-op suggestion is reported honestly.

### 🟠 Delete could target the preview root

`DELETE /api/preview/delete` with no path resolved to `PREVIEW_DIR` itself, **passed the
traversal guard**, and raised `IsADirectoryError` as an unhandled HTTP 500 — one missing
guard away from attempting to unlink the entire preview directory. Now rejects empty
paths, the preview root and directories; handles `OSError`; and accepts the path from
the query string as well as the body.

**Verified working, no change needed:** path traversal blocked on read/save/delete,
version history + restore, scaffold, file CRUD, Monaco offline fallback.

---

## Part 2 — Consolidation (your decisions: workstation model + remove)

### 67 → 24 top-level panes

43 panes folded into **11 tabbed workstations**. The old 26-item "MONITORING" group was
the worst offender and is now one workstation:

| Workstation | Absorbs |
|---|---|
| **Observability** | agent-monitor, profiler, health, system, audit-log, replay, finops, dashboard, leaderboard |
| **Supervisor** | a2a, agent-identity, hitl, goals, swarm, fusion, finetune |
| **Tools (MCP)** | mcp-gateway, connectors, integrations, webhooks, hooks |
| **Evals** | eval-framework, arena, bugbot, testgen |
| **Workflows** | pipeline, loops, specs, ambient |
| **Studio** | codesearch, codeindex, multitab |
| **Memory** | rag, knowledge-graph, obsidian |
| **Plugins** | pluginsdk, marketplace, skills |
| **GitHub** | gitai, deploy |
| **Workspaces** | collabedit, control |
| **Secrets** | pqc |

Sidebar regrouped into five intent-based sections: **ESSENTIALS · AI TOOLS ·
BUILD & SHIP · CONNECT · OPERATE**.

**The consolidation is lossless and reversible** — this was the primary design constraint:

- No renderer was rewritten. Each absorbed pane keeps its own `#pane-<id>` element and its
  `MASTER_PANE_REGISTRY` entry; the workstation only relocates the node and toggles
  visibility. **Delete `00-workstations.js` and everything works exactly as before.**
- Nothing hidden or feature-flagged — every pane is one click away.
- Deep links, command palette, keyboard shortcuts and cross-module `nav()` calls all still
  use the original ids. `nav('finops')` opens Observability with the Cost tab selected, and
  the URL stays addressable per tab (`#/finops`).

Implementation care: the tab strip is built *after* the host's renderer runs (so hosts that
replace their `innerHTML` can't wipe it), `initWorkstation()` is idempotent, a throwing child
renderer is caught so one broken pane can't take down a workstation, and tabs are real
`<button role="tab">` elements with `aria-selected` and focus-visible styling.

### Removed 7 unreachable routers

`robotics`, `bci`, `satellite`, `digital_twin`, `compiler`, `p2p_sharding`, `telephony` —
**zero frontend references, no sidebar pane**, so a user could never reach them. None could
do what its OpenAPI description advertised: "ROS 2 / MQTT" robotics has no ROS, MQTT or
serial client; "WebRTC / Twilio" telephony has no telephony client. All were JSON echo
handlers over module-level dicts. ~1,042 lines of pure audit surface removed.

### ⚠️ But one "unreachable" router turned out to be the opposite

`cluster` had **zero API call sites too** — yet Supervisor has a full "Multi-Node Edge
Radar" tab. Investigating that discrepancy found the inverse problem: a **real, working**
`/api/cluster` router (join / nodes / heartbeat / dispatch / status) wired to a **completely
fake UI**:

- the node list was three hardcoded cards naming invented laptop/GPU hardware with
  fabricated sub-millisecond latencies, shown regardless of what was registered
- *"Add Edge Node"* never contacted the host you gave it — just a delayed
  *"✅ Edge Node verified & joined cluster mesh"* toast
- *"Scan Local Network"* claimed to have scanned 254 addresses and discovered 2 nodes
  **without sending a packet**
- *"Rebalance Swarm Load"* announced invented percentages

All four now use the real endpoints. Scan is honest that the backend has no subnet-discovery
capability and points at the add-by-URL flow instead of inventing a sweep. Dispatch sends
`task_prompt` — the field the API actually requires; the obvious-looking `task_type` would
have 422'd.

**This is why I checked reachability in both directions rather than trusting the pane list.**

---

## Part 3 — Budget guardrails (agentic-core addition)

### Caps looked complete but enforced nothing

The FinOps API accepts, validates and persists an `on_breach` action of `alert` / `pause` /
`kill`. **Nothing in the codebase ever read that column.** The only enforcement path runs
inside `record_cost()` — *after* the money is spent — and its entire effect is an alert row,
`breached=1`, and a log line. A cap could be exceeded without limit.

Compounding it, **Chat never wrote to `cost_ledger` at all**, so caps had nothing to measure
and the FinOps dashboard could only ever report zero. (Chat only started producing real token
counts after the Module 1 fix — before that there was nothing to record.)

**Added:** `check_budget_before_spend()` — a pre-flight guardrail, also exposed as
`GET /api/finops/preflight` so any surface can honour caps. Chat consults it and refuses to
call a paid model once an enforcing cap is reached, naming the cap and offering the free
local-model alternative. Chat also now records real usage to the ledger.

Design decisions worth flagging:

- **`alert` caps still never block.** Existing installs configured caps when they had no
  teeth; silently converting those to hard blocks would be a nasty surprise.
- **A limit of `0` means "unset"**, consistent with the rest of the module — never treated as
  instantly breached, or one malformed row would halt all spend platform-wide.
- **The guardrail fails open.** A spend check that throws must not take every AI call down
  with it. The fail-open test caught that `_get_conn()` was originally outside the `try`.

Also purged **116 test-suite budget caps, 8 ledger rows with ~$8bn of synthetic spend, and
32 rows whose `agent_id` was an injection payload** — all left in the shared database by
earlier test runs.

---

## Test results

| | Before | After |
|---|---|---|
| Backend | 2703 | **2722 passed, 12 skipped, 0 failed** |
| Frontend (vitest) | 45 | **69 passed** |
| ruff | clean | **clean** |

**+61 tests added:** 19 Studio contracts, 8 jsdom fence-extraction cases (exercising the
shipped extractor for every shape, including the two that destroyed content), 12
consolidation guards, 16 workstation behavioural tests, 13 budget-enforcement tests.

`test_38` was rewritten: rather than pinning a pane count that changes with every intentional
merge, it now asserts the **losslessness invariant** directly — every absorbed pane keeps a
container, keeps a renderer, and stays reachable through `nav()`.

### A note on 16 "failures" you may see locally

Tests that exercise LLM-backed endpoints time out when a real CPU-only model is serving them.
I confirmed these are **pre-existing and environmental** by reproducing them on a clean
checkout with my changes stashed — and all pass when inference isn't the bottleneck.

---

## Recommended follow-ups

1. **Wire the remaining spend sources into the ledger** — Swarm, Composer and Supervisor
   also call paid models and still don't record. Caps are only as good as their coverage.
2. **Move the memory-ingest guard into `memory_db.memory_add()`** (carried over from Module 1)
   — Chat and Webhooks both poisoned the store independently.
3. **Add a duplicate-global CI lint** (carried over from the initial review) — still the
   highest-leverage structural fix; two Module 1 bugs came from one file silently
   clobbering another.
4. Consider persisting `prompt_tokens`/`completion_tokens` separately in `chat_log`
   (`cost_ledger` now does) for input-vs-output cost attribution.
