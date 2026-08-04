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
