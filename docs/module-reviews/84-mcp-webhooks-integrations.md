# 84 — Connect workstation: `webhooks` and `integrations`

**Destination:** `mcp` ("🔌 Connect")
**Tabs:** `mcp` (host), `integrations`, `webhooks` (this doc) · `hooks` (doc 69) · `mcp-gateway` (doc 72) — 4/4 covered
**Frontend:** `frontend/js/35-connect-hub.js`, `33-webhooks.js`, `22-integrations.js`
**Backend:** `backend/routers/webhooks.py`, `backend/routers/integrations.py`
**Tests:** `tests/unit/test_159_module23_mcp_webhooks_integrations.py` (27)
**Status:** reviewed, fixed, verified live

Destination 11 of 20.

---

## Why this destination

Webhooks are the platform's **only inbound surface**: a public URL that an
external service calls and that starts an LLM agent on the user's account. Every
other destination reviewed so far is driven by someone already inside the app.
This one is reachable by anyone who learns the URL, which makes its
authentication the highest-stakes code here.

Six defects, all reproduced against a live server before any code changed.

---

## Findings

### 1. An empty secret created an unauthenticated public agent trigger

```python
secret = body.get('secret', uuid.uuid4().hex[:24])
```

`dict.get` only supplies its default when the key is **absent**. Posting
`{"secret": ""}` — a blank form field — stored an empty string. And the trigger
endpoint's entire authentication is `if secret:`. Verified live:

```
POST /api/webhooks {"name":"...","secret":""}   -> created, secret ''
POST /api/webhooks/<id>/trigger  (no credential) -> 200
   {"ok":true,"message":"Webhook received — agent 'brain' triggered"}
```

Anyone holding that URL could run the user's agent, repeatedly, at their
expense — and the payload they send becomes the agent's user message. An
unauthenticated webhook is never what `""` means; it is an empty text box.

**Fix:** a blank or whitespace-only secret generates a real one and the response
says so; a secret shorter than 8 characters is refused with an explanation. The
same guard is on `PATCH`, since an update could otherwise re-open the hole.

### 2. A stored empty secret still bypassed authentication

Rows created before the fix would keep working forever. The trigger path now
**fails closed** on an empty stored secret — 403 `webhook_unconfigured` — rather
than treating it as "no auth required". The endpoint is public and it starts an
agent; there is no safe reading of a missing credential.

### 3. Filters were stored, editable, displayed — and never read

`filters` is accepted at create, editable via `PATCH`, and rendered in the UI.
Nothing in `trigger_webhook` ever looked at it. Verified live: a webhook
filtered to `source: github-push` ran its agent for `{"totally":"unrelated"}`.

A filter that silently does nothing is worse than no filter at all, because the
user configured it *precisely* to stop paying for events they do not want — and
the UI confirms it is set.

**Fix:** `_filter_mismatch()` supports `source`, `event_type` and `contains`.
A non-matching event is accepted (the sender gets its 200 and does not retry)
but records `status='filtered'` and runs no agent, with the reason returned.
Unknown filter keys are **ignored rather than treated as a mismatch** — dropping
every event because of a typo'd key would be the same failure in the opposite
direction, and that mirror case has its own test.

### 4. `GET /api/webhooks` returned every secret in plaintext

The list endpoint did `SELECT *` and returned it. That secret is the only thing
standing between the public trigger endpoint and anyone who can reach the list.
Now returns `has_secret` and a 4-character `secret_hint`; the full value is
returned **once**, at creation, so the caller can still configure the sender.

### 5. `/integrations/stripe/wire` claimed success having written nothing

`ok` was hardcoded `True`. Reproduced with a model that answers *"I'm sorry, I
can't generate payment code."*: `saved_files: []`, `html_code: ''`, and
`ok: true` — the UI reported the Stripe integration as wired when not one byte
had been written. Nothing prompts the user to check; they find out when checkout
does not exist.

### 6. `/integrations/auth/wire` — the same defect, plus a worse one

Second door #20: the twin endpoint had the identical hardcoded `ok`. It also had
an extractor that ended in a bare fallback:

```python
else:
    html_code = code      # whatever the model said
```

So a refusal was **written to disk as `auth.html`** and reported as a successful
wire-up — prose served as a login page. `stripe_wire`'s extractor already
declined to guess this way. Both now require markup-shaped output, and both
return **502** with the raw preview when nothing usable came back.

---

## Revert-proof

Each fix individually reverted, `__pycache__` cleared each time.
**12 of 12 breakages caught**, baseline green before and after.

| # | Breakage | Tests failed |
|---|---|---|
| 1 | empty secret stored verbatim | 3 |
| 1b | short secret accepted | 1 |
| 1c | PATCH can reopen the hole | 1 |
| 2 | stored empty secret bypasses auth | 1 |
| 3 | filters never applied | 4 |
| 3b | filter over-blocks everything | 4 |
| 3c | filtered event not recorded | 1 |
| 4 | list leaks secrets | 1 |
| 4b | `has_secret` always false | 1 |
| 5 | stripe_wire claims success | 1 |
| 6 | auth_wire claims success | 1 |
| 6b | auth_wire writes prose as html | 2 |

Both directions are pinned for the filter logic (3 and 3b): under-filtering and
over-filtering each fail their own tests.

### Two pre-existing tests updated in place

`test_13_plugins_mcp_hooks.py` (4 cases) and `test_uat_05_platform_admin.py`
(2 cases) created webhooks with `"secret": "s"` — a one-character secret, now
refused. These cases assert webhook CRUD and the test/event-log journeys, **not**
the secret policy, so the fixture value was widened rather than the assertions
relaxed, with the reasoning recorded inline in both files. The policy itself is
covered by the new module tests.

### A patch script that aborted halfway

My first webhooks patch asserted on a response shape that did not match (the
list endpoint returns a bare array, not `{'webhooks': [...]}`). Because the
script writes the file only at the end, the assertion left **one** of five
sections applied. Caught by grepping for each marker rather than trusting the
"patched" message — worth recording, because a half-applied patch that still
lints and still passes most tests is an easy thing to ship by accident.

## Live verification

```
empty secret        -> 24-char secret generated + explanatory note
short secret        -> 400 "must be at least 8 characters"
legacy empty secret -> 403 webhook_unconfigured
filter mismatch     -> {"filtered": true, "reason": "source 'webhook' does not
                        match filter 'github-push'"}   (no agent run)
filter match        -> agent runs normally
no filter           -> agent runs normally
list                -> no `secret` field; has_secret true, hint '…alue'
stripe_wire refusal -> 502, saved_files []
auth_wire refusal   -> 502, nothing written
both, real code     -> 200, files saved
```

All four Connect tabs render in Chromium with **0 dead handlers** and no console
errors. (An initial probe reported the tab strip as empty; that was the probe
reading before the workstation had built — the same mistake made on the
supervisor destination. Re-run with a longer settle and all four are present.)

## Cross-module impact

- **`POST /api/webhooks` is stricter.** A caller passing `""` now gets a
  generated secret; one passing `"s"` gets a 400. Both were the bug, but they
  are behaviour changes for any script that created webhooks that way.
- **`GET /api/webhooks` no longer returns `secret`.** The one frontend consumer
  reads the secret from the *create* response, which is unchanged. Any other
  reader must switch to `has_secret`.
- **`POST /api/webhooks/{id}/trigger`** can now return **403**
  (`webhook_unconfigured`) and a `filtered: true` body that carries no `run_id`.
- **`/integrations/stripe/wire` and `/auth/wire`** can now return **502**.
- `hooks` (doc 69) and `mcp-gateway` (doc 72) untouched.

## Suite

`4093 unit (2 skipped)` + `655 regression/system/uat (10 skipped)` =
**4,748 passing, 0 failures**. Linters clean.
