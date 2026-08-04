# Module 20 — CONNECT

*(consolidated pane: `mcp` → **Connect**, absorbing `mcp-gateway` and `connectors`; `integrations`, `webhooks`, `hooks` retained)*

Routers: `connect_hub.py` (new), `mcp.py`, `mcp_gateway.py`, `connectors.py`,
`integrations.py`, `webhooks.py`, `hooks.py` — 7,777 lines
New service: `backend/services/safe_fetch.py`
Frontend: `35-connect-hub.js` (new)

---

## 1. SSRF in the `http.get` / `http.post` MCP tools

**These are agent-callable.** That is what makes this the most serious finding
in the review so far.

```
{"tool":"http.get","args":{"url":"http://localhost:8787/api/connectors"}}
→ {"ok": true, ..., "body": "{\"connectors\":[..."}
```

The full internal API response, returned to the caller. It also reached
`169.254.169.254` — HTTP 401, which is a *response*, therefore a successful
connection. `follow_redirects` was `True`, so a check on the original host
alone would have been walked past by a 302.

Everything Module 19 established about prompt injection becomes materially
worse when the model holds a primitive that reads arbitrary internal URLs and
hands back the body.

## 2. SSRF in the outbound-webhook connector

```
{"action":"post","payload":{"url":"http://169.254.169.254/..."}}
→ {"ok": false, "status_code": 501, "response": "..."}
```

`ok: false` reads like a refusal. It is not — a 501 is a reply from the
metadata service.

### Why there were two more after fixing the first

Module 19 fixed this exact primitive in the plugin installer by putting
`_url_is_safe()` **inside `backend/routers/plugins.py`**. A guard that lives in
a router cannot be reused, so the vulnerability survived in two other routers.

The guard now lives in `services/safe_fetch.py`, `plugins.py` delegates to it,
and a **repo-wide test fails if any router hand-rolls its own**.

That test immediately found a **fourth** copy, in `websearch.py` — and reading
it showed it was the *best* of the four. It handled integer and hex IP
encodings (`2130706433`, `0x7f000001` → `127.0.0.1`) that mine missed, plus
Alibaba's `100.100.100.200` and `metadata.google.internal`. **Those checks were
merged into the shared helper rather than replaced.** Consolidation should keep
the strongest implementation, not the newest one — the opposite instinct would
have made the platform less safe while looking like cleanup.

## 3. `fs.write` reported a path the file was not written to

```
fs.write {"path": "/tmp/mcp_escape.txt"}
→ {"ok": true, "path": "/tmp/mcp_escape.txt", "bytes_written": 5}
```

`/tmp/mcp_escape.txt` did not exist. `_safe_path()` had correctly clamped it
into the sandbox. **The clamping is right; echoing back the requested path is
not.** An agent told it wrote to `/tmp/x` will read back `/tmp/x`, get nothing,
and have no way to discover why — the same class of dishonesty as the "success
while doing nothing" results in Modules 15 and 19.

## 4. The experience: five panes, three registries

| Source | Count |
|---|---|
| `/api/mcp/tools` | 23 built-in tools |
| `/api/mcp-gateway/servers` | 6 servers |
| `/api/connectors` | 53 rows — **8 real, 45 test residue** |

Mutually unaware, in different panes, disagreeing on every field name for the
same concept (`server_id`/`connector_id`, `icon`/`emoji`,
`capabilities`/`tools`). The single question a user has — *"what can my agent
do right now, and what do I need to set up?"* — required visiting five panes
and reconciling three vocabularies. The eight real connectors were invisible
among 45 rows named `UAT Custom CRM uat_15b4fa33`.

`connect_hub.py` federates all three; `35-connect-hub.js` renders it:

* **Ready items sort above items needing setup.** "What works now" first.
* **A banner naming exactly what needs credentials**, with one button.
* **Setup guidance attached to the thing that needs it** — which fields, where
  to get them, which scopes, docs link, for all six credentialed connectors.
  This text previously existed *only inside the error message of a failed
  call*: **you had to get it wrong to find out how to get it right.**
* **Guided credential entry** using the provider's real field names.
* **A Test button**, because *configured* and *working* are different things.
* **Test residue filtered out.**

Sidebar **6 panes → 4**. Integrations, webhooks and hooks stay: inbound
triggers and event automation are a different job, not a duplicate catalog.

### Verified end-to-end

```
31 ready · 6 need setup · 23 tools, 8 apps, 6 servers
Needs setup: Email, GitHub, Google Workspace, Jira, Notion, Salesforce
Notion setup → needs ['api_key'] at notion.so/my-integrations
http.get → 169.254.169.254  → refused
http.get → api.github.com   → ok
```

## 5. 200-on-failure

Unknown MCP tool returned `200`. An agent retrying a typo'd name against a 200
has no signal that the name is the problem. Now `404` with the tool list.

---

## Self-corrections

1. **My own `/api/connect/test` reported `ok: true` for an unconfigured
   connector**, because `connectors.test_connector()` returns `ok: true` to
   mean "I answered your question" — including when the answer is "not
   configured". That is the exact configured-vs-working conflation the endpoint
   exists to remove. Caught by testing my own feature against a real
   unconfigured connector rather than assuming it worked.
2. **My residue filter missed 15 of 23 connectors.** The generated names read
   `Sys SDK Test sys_d52...` — the underscore markers I matched on live in the
   id half, not the human-readable half. Now matches the description too.
3. **My `fs.write` "relocated" note never fired**, because it compared raw
   strings and `/tmp/x` differs from `tmp/x` only by the leading slash.

## Tests

`tests/unit/test_80_connect_hub_module_review.py` — **45 cases**, including the
repo-wide guard that found the fourth SSRF copy.
**Proven to catch the bugs: with the three routers stashed, 9 of 45 fail.**

Four existing tests asserted that a webhook POST to `127.0.0.1` **succeeds** —
they encoded the SSRF hole as expected behaviour, the third time this review
has found tests pinning a bug in place. Updated to assert dispatch, `exec_id`
and refusal, which is what they were actually testing.

Full suite: **3362 passed / 18 skipped / 0 failed** (was 3317).

---

## Recommended follow-ups

1. **`mcp_gateway.tool_count` is `null` for all six servers** — the gateway
   never populates it, so the UI cannot show how many tools a server offers.
2. **No per-agent tool permissions.** Any agent can call any of the 23 tools,
   including `shell.run` and `http.get`. `agent_permissions` exists (Module 19)
   but nothing in the MCP path consults it.
3. **`shell.run`'s allow-list is command-name based** — the Module 12 lesson
   about prefix/name matching applies; `git` is allowed and `git` can run
   arbitrary code via `-c core.pager` or aliases.
4. **Webhooks have no signature verification** on inbound calls.
5. **No rate limiting on connector execution** — an agent loop could exhaust a
   third-party API quota with no local backstop.

---

# Follow-up 1 — Per-agent tool permissions (`6a24ffe`)

The top follow-up, and the one with the widest blast radius.

## The gap

`agent_permissions` has existed since Sprint A. It is populated on
provisioning, displayed on agent cards, and counted in the identity UI.
**Nothing has ever consulted it to authorise anything.** Both readers in the
codebase use it for display.

Verified live, with an agent holding neither `write_files` nor `delete_files`:

| Call | Result |
|---|---|
| `fs.write` as `probe_readonly` | **200 — file written** |
| `fs.delete` as `probe_readonly` | **200 — file deleted** |
| `fs.write` as `i_do_not_exist` | **200 — file written** |

The last one is the worst. A **fictional agent id** wrote a file, and the audit
chain recorded it as that agent's action.

An identity field that is accepted, logged, echoed back in the response and
written to the immutable audit chain — but never used to make a decision — is
**worse than no field at all**. The trail reads as though authorisation
happened. Every governance surface built in this review (Module 17's ledger,
the agent cards, the receipts) was describing a control that did not exist.

## The design

`backend/services/tool_policy.py` maps each tool to the coarse permission verb
it needs, matching how grants are already expressed. Enforced in
`/api/mcp/call`, which the gateway dispatches through — so one guard covers
both doors, asserted by a test rather than assumed, since "second door" gaps
have now appeared three times in this review.

Two decisions that look inconsistent and are not:

* **Unknown *agent* → deny.** An unauthenticated caller gives no basis for any
  decision.
* **Unmapped *tool* → allow.** Failing closed here would break every caller the
  moment someone adds a tool. Instead, a test enumerates the map against the
  live `TOOLS` dict, so the gap is caught at review time.

That test earned itself immediately: it found **`code.run` — which executes
arbitrary Python — entirely absent from the map**. Allow-by-default would have
handed Python execution to every agent, including unknown ones.

Also: `system` (and a missing `agent_id`) stays unrestricted because it is the
platform, not an agent; `expires_at` is now honoured; denials are audited and
name the missing permission; and `GET /api/connect/permissions/{agent_id}`
answers the operator's actual question — *given these grants, what can this
agent do?*

## Self-correction

My first version left `fs.write` out of `HIGH_RISK`. The standard authority
level grants `use_tools` but not `write_files`, so **the wildcard silently
re-opened the exact bypass this module was written to close** — an agent with
no write permission wrote a file and got HTTP 200.

Caught by re-running the original reproduction against the fix rather than
assuming it worked. The rule that came out of it: `use_tools` is a convenience
grant for *read-shaped* tools; anything that mutates state on disk, in the
repo, or on another system needs its own permission. A test now asserts that
every tool mapped to a mutating action is in `HIGH_RISK`.

## A correction to the record

A workspace snapshot rollback wiped uncommitted work mid-session. Commit
`da6b3e4`'s **message** describes the full Module 19 follow-up set, but
`git show --stat da6b3e4` is a **single file rename** — the code was lost
before staging, and that commit message overstates what landed.

I am stating this plainly rather than quietly backfilling, because a commit
message that describes work not in the diff is exactly the kind of misleading
record this review keeps flagging in the code itself.

Recovered and verified by the 44 tests in `test_79` that were failing against
`origin/main`:

* `plugin_safety` wiring in `skills.py` (the second door for template execution)
* `/api/hub/provenance`, `/api/hub/updates`, `/api/hub/review`
* shared-skill-aware uninstall in `marketplace.py`

## Tests

`tests/unit/test_81_agent_tool_permissions.py` — **27 cases**.
**Proven to catch the bug: with `mcp.py` stashed, 8 of 27 fail.**

Two worth calling out: one asserts a denied call **does not perform the action
anyway** (a 403 that still writes the file would be worse than no check), and
one asserts that **granting the permission restores access** — proving
enforcement is table-driven rather than hardcoded.

Full suite: **3389 passed / 18 skipped / 0 failed**.

## Remaining CONNECT follow-ups

2. `mcp_gateway.tool_count` is `null` for all six servers.
3. `shell.run`'s allow-list is command-name based (`git` can run arbitrary code
   via `-c core.pager`).
4. Webhooks have no inbound signature verification.
5. No rate limiting on connector execution.
