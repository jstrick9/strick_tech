# Module 11 — MCP Gateway (policy engine)

**Reviewed:** 2026-08-10
**Pane:** `mcp-gateway`
**Frontend:** `frontend/js/50-mcp-gateway.js` (1,034 lines)
**Backend:** `backend/routers/mcp_gateway.py` (1,371 lines)
**Endpoints:** 20
**Risk score:** 18

---

## Summary

This is the component that decides whether an agent may invoke a tool, so
every defect here is a security defect. Seven found — and the last one turned
out to be **platform-wide**.

| # | Defect | Severity |
|---|---|---|
| 1 | `POST /policies` silently discarded `conditions` — a time-scoped rule became permanent | Critical |
| 2 | `/policies/from-template` hardcoded `conditions` to `'{}'` too | High |
| 3 | `"orchestrator, brain"` — a list with a space — matched only the first agent | Critical |
| 4 | Overnight time windows (22:00–06:00) never activated | High |
| 5 | Malformed conditions let an **allow** policy fire — fail-open | High |
| 6 | `/policies/simulate` evaluated no conditions, so the dry-run disagreed with the enforcer | High |
| 7 | **117 delegated handlers across 14 panes were unreachable** — the Gateway UI was entirely non-functional | Critical |

---

## 1–2. Conditions were collected, validated, read — and never stored

The policy builder collects a time window and a day-of-week set. The UI sends
them. `_evaluate_policy()` reads them. `PATCH /policies/{id}` persists them
*with validation*. Only the `INSERT` dropped them:

```sql
INSERT INTO mcp_gateway_policies (…,priority,enabled,created_at,updated_at)
VALUES (?,?,?,?,?,?,?,?,1,?,?)      -- no conditions column at all
```

`/policies/from-template` did have the column, and hardcoded `'{}'`.

A rule created as *"deny `code.run` between 22:00 and 06:00"* was stored
unconditional and **enforced 24/7**. Confirmed live: the policy came back with
`conditions: {}` and denied at 16:00.

Both paths now share `_normalise_conditions()`, which validates hour ranges,
rejects a lone `start_hour`, bounds `days_of_week` to 0–6, and returns a 400
with a specific message rather than silently storing something else.

---

## 3. A comma-separated list with a space protected only the first agent

```python
agent_match = pol['agent_id'] == '*' or agent_id in pol['agent_id'].split(',')
```

`"orchestrator, brain".split(',')` is `['orchestrator', ' brain']`. The second
entry carries a leading space and never equals `"brain"`. Confirmed live:

```
policy: DENY fs.read for "orchestrator, brain"
  agent=orchestrator -> deny  ✅
  agent=brain        -> allow ❌   (fell through to "Allow all built-in tools")
```

A security rule naming two agents silently protected one of them. The same
line governed `server_id`.

Now `_id_matches()` strips on read (so rows written before this fix behave)
and `_normalise_id_list()` cleans on write.

---

## 4. Overnight windows never fired

```python
if not (conds['start_hour'] <= _now_hour < conds['end_hour']):
```

For a 22:00–06:00 window this is `22 <= h < 6` — **false at every hour of the
day**. A maintenance-window restriction was inert around the clock.
`_window_active()` now handles wrap-around; `start == end` means all day.

---

## 5. Malformed conditions were a fail-open

```python
except (...):
    pass  # malformed conditions → ignore, policy still applies
```

For a `deny` that is merely surprising. For an **allow** it grants access
whose scope the system could not read. Now fail-closed: a restriction whose
conditions cannot be parsed applies at full scope; a permission does not fire.

---

## 6. The simulator disagreed with the enforcer

`/policies/simulate` is the feature users trust to answer *"what will the
gateway do?"*. It reimplemented agent/server/tool matching separately from
`_evaluate_policy()` **and evaluated no conditions at all** — so a time-scoped
rule appeared to match at every hour.

Both now call the same `_id_matches()` and a shared `_conditions_hold()`.
`fnmatch` was also replaced with `fnmatchcase`: `fnmatch` applies
`os.path.normcase`, which lowercases on Windows, so a tool allow-list would
have been case-insensitive on one platform and not another.

The trace table gained a **"When"** column, since a rule can now match
agent + server + tool and still not fire:

```
3  M11 overnight  ✓ *  ✓ code_exec  ✗ code.run  ✗ outside 22:00-06:00  ✗  🚫 deny
```

---

## 7. The whole pane was decorative — and so were 13 others

Driving the simulator in Chromium, the tab would not switch. The console said:

```
[delegate] unknown function: prbSetTab
```

`frontend/js/50-mcp-gateway.js` wraps its entire body in
`(function(S, nav, toast, …) { … })(…)`. The bundle concatenates
`frontend/js/*.js` at top level, so a plain `function f()` in an **unwrapped**
file becomes a global and the delegated dispatcher — which resolves handler
names by plain property lookup on `window` — can find it. Inside an IIFE the
declarations are module-private. Only `renderMCPGateway` was exported.

**Every tab, the simulator, the rule builder, delete, bulk actions and the
server kill-switch rendered perfectly and did nothing.** The dispatcher warns
and returns, so there was no error, no broken layout, no clue.

Scanning for the same shape found **14 IIFE-wrapped panes with 117 unreachable
handlers**. Verified dead in Chromium across 12 of them before the fix:
`a2aSetTab`, `bddDetectAll`, `gmCreateGoal`, `dagRefresh`, `lbExport`,
`fusionRun`, `connectorTest`, `identityRotateKeys`, `crcSetTab`,
`hitlTestInterrupt`, `finopsRecordCost`, `evalRunSuite` — all `undefined`.
After: **0 dead across all of them.**

| file | handlers |
|---|---|
| 49-goals.js | 15 |
| 52-a2a.js | 15 |
| 46-compliance-report.js | 14 |
| 53-agent-monitor.js | 11 |
| 45-leaderboard.js | 11 |
| 48-supervisor.js | 10 |
| 41-fusion.js | 8 |
| 01-app-core.js | 7 |
| 47-agent-identity.js, 55-eval-framework.js | 6 each |
| 50-mcp-gateway.js, 51-connectors.js | 5 each |
| 42-hitl.js, 54-finops.js | 2 each |

### A correction worth recording

My first static scan flagged **42** files. Spot-checking at runtime, `ciShowTab`
(Module 8, verified working) was on the list — the scan was wrong, because
non-IIFE files get their globals from bundle concatenation. Narrowing the rule
to IIFE-wrapped files only gave 14, and all 14 were confirmed dead in a real
browser. *"When a probe disagrees with the app, suspect the probe first"* held
again.

Separately, my runtime probe initially reported `prbApplyTemplateById` and
`prbQuickSimFromData` as present when they were not — they are defined *after*
the export block I had added, and the probe ran against a stale page. The
static test caught both. The two checks disagreeing is what found them.

---

## Verified working (no change needed)

- Policy enforcement itself: `deny` blocks, `require_hitl` writes a HITL
  interrupt and returns `pending`, and every outcome is written to the audit
  log with the deciding policy.
- The server kill-switch (`status='disabled'`) short-circuits to deny.
- Rate limiting is applied after policy and before dispatch.
- Unknown tools and unprovisioned agent identities are rejected downstream.
- Conflict detection correctly identifies overlapping scopes and names the
  winner by priority.

---

## Cross-module impact

- **Every pane in the table above** gains working buttons. This is the single
  highest-impact change in the review so far, and it touches 14 files.
- `/api/mcp-gateway/status` consumers: `clean` semantics unchanged; new
  `condition_match` / `condition_reason` / `conditions` fields in the simulate
  trace are additive.
- `POST /policies` now returns **400** for invalid conditions where it
  previously accepted and discarded them.
- Existing stored policies with unnormalised agent lists are handled by
  `_id_matches()` stripping on read — no migration needed.

---

## Tests

`tests/unit/test_144_module11_mcp_gateway.py` — **40 tests.**

Revert-proof (caches cleared, `mcp_gateway.py` reverted): **all 39 backend
tests fail** — the shared helpers do not exist in the original, so even the
parametrised cases collapse. The export test was proven separately by
stashing `frontend/js/`: it fails listing all 14 offending files.

An existing hardening test (`test_103_type_confusion`) caught one of *my*
changes: `.strip()` on an unchecked body field, which crashes when a client
sends a non-string. Switched to `as_text()`. Second time this review that the
repo's own guardrails have caught the person adding guardrails.

Full suite: **3,608 unit + 655 regression/system/uat = 4,263 passing, 0 failures.**
