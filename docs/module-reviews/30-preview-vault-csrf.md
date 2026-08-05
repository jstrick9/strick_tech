# 30 — Live Preview was dead, a vault audit that could not fail, and a CSRF test that could not pass

Autonomous hunt, batch 20. Three bugs, all found by driving the real app in
Chromium and reading what the browser actually reported.

---

## Bug 1 — CSP phase 2 silently killed the entire Live Preview feature

### What was wrong

Phase 2 dropped `script-src 'unsafe-inline'` from the enforcing policy. That
was correct **for the application**. But the middleware applied the same policy
to `/preview/`, and `/preview/` is not the application — it serves the HTML the
user writes in Code Studio and the HTML the agent generates, essentially all of
which carries inline `<script>`.

### Evidence

A probe page written to the preview directory:

```html
<h1 id="h">BEFORE</h1>
<script>document.getElementById("h").textContent="INLINE SCRIPT RAN";</script>
```

| | Before | After |
|---|---|---|
| `<h1>` text in Chromium | `BEFORE` | `INLINE SCRIPT RAN` |
| Console | `Refused to execute inline script … "script-src 'self'"` | clean |

So **no generated page containing script could run at all.** For a platform
whose headline feature is an agent that writes you a working app and shows it
to you live, this was the feature not working.

It also broke Studio's own instrumentation. `01-app-core.js:4147` and `:4923`
inject two scripts into the preview frame — one forwards `console.*` output to
the Studio console, the other forwards runtime errors to the "🔧 Fix with AI"
error bar. Both were blocked on every single load, measured at boot and on
every navigation to Studio. The preview console showed nothing and JS errors
were never surfaced, so the "Fix with AI" button could never appear.

### The "second door" again

The **Report-Only** policy already carried a `/preview/` exemption, with a
comment explaining exactly why preview pages legitimately carry inline script.
The **enforcing** policy never got the matching change. This is the fifth-plus
instance of the same pattern in this review: a control correctly applied at one
call site while an identical site goes unprotected.

### The fix

A `PREVIEW_CSP` scoped to `/preview/`, applied after the blanket
`SECURITY_HEADERS` loop so it replaces rather than being replaced. It restores
inline script for preview documents only, and is **tighter** than the
application policy where it matters for untrusted content:

| Directive | Value | Why |
|---|---|---|
| `frame-ancestors` | `'self'` | only our own Studio may frame it |
| `form-action` | `'none'` | generated markup cannot POST credentials out |
| `object-src` | `'none'` | no plugin content |
| `base-uri` | `'none'` | an injected `<base>` cannot reroute the page |

The iframe also runs under a `sandbox` attribute (`index.html:1712`), so this
is defence in depth rather than the only boundary.

**Ordering verified**: the SVG lockdown (`default-src 'none'; … sandbox`) is
applied later in the middleware and still wins for `/preview/*.svg`. Confirmed
live — an SVG from the preview directory still comes back fully locked down. If
the looser preview policy had overwritten it, a stored SVG would have regained
the ability to run same-origin script, which is a strictly worse bug than the
one being fixed. That has its own test.

---

## Bug 2 — the vault audit could not fail

`checkVaultIntegrity()` — behind the **"🔍 Run Cryptographic Vault Audit"**
button in Settings — fetched `/api/secrets/get?key=OPENROUTER_API_KEY` and
then, whatever came back, rendered:

> ✅ Local Cryptographic Secret Vault Verified (100% Zero-Trust)

and toasted "🔒 Cryptographic vault audit green!". The only thing that varied
with the response was one word on one line: `ENCRYPTED IN VAULT` vs
`NOT CONFIGURED`. A **404** — the normal answer when no key is stored, and the
answer observed on a fresh install — still produced a full pass. So did a vault
running with **no encryption at all**.

It also printed claims the backend never made and nothing ever checked:

- a macOS storage root `~/Library/Application Support/com.stricktech.agenticos/secrets/`
- a "Hardware Master Key" at `~/.vault_key`
- "AES-256-GCM + Kyber-1024 hybrid wrapping"

A security control that always reports success is worse than no control: it
tells the user their secrets are encrypted at rest when they may not be.

`/api/secrets/list` already returns the real signal — `encrypted` (is a Fernet
key actually loaded), `engine`, `vault_path`, `count`, `warning` — and the
audit ignored all of it. It now reports those values and fails loudly.

Verified live, all three states:

| State | Rendered |
|---|---|
| Encryption on | ✅ Vault is encrypted at rest · `Fernet AES-256` · real `vault_path` · `OpenRouter key: not configured` |
| `encrypted:false` | ❌ Vault is NOT encrypted — secrets are stored in recoverable form · surfaces the backend's `Install cryptography` remediation |
| `/api/secrets/list` → 500 | ❌ Vault audit failed: could not read the vault (HTTP 500) |

Note "not configured" is now reported as a **fact, not a failure** — no stored
OpenRouter key is a normal state and must not be alarming.

---

## Bug 3 — the only browser CSRF test could never pass

`test_a_post_without_a_csrf_token_is_refused` was failing with
`assert 200 == 403` and the message "CSRF is not enforced".

**CSRF is enforced.** The harness was the problem. `backend/app.py` disables
both rate limiting and CSRF validation whenever `PYTEST_CURRENT_TEST` is set:

```python
if request.method in ('POST', ...) and not os.environ.get('PYTEST_CURRENT_TEST'):
```

`tests/e2e_browser/conftest.py` starts the server with
`multiprocessing.Process`, which **forks** — so the server inherited that
variable and ran with both controls switched off. Every security assertion the
browser suite made was made against a server that had them disabled.

Confirmed pre-existing: stashing all of this session's changes and re-running
against the committed tree reproduces the same failure, so it is a harness bug,
not a regression.

A test that cannot pass is as bad as one that cannot fail, and this was the
only guard on CSRF from a real browser. Fixed by clearing the variable in the
**child only** (the parent keeps it, so the rest of pytest is unaffected), and
raising `RATE_LIMIT_MAX` for the child rather than reintroducing the blanket
bypass being removed.

Result: `17 passed` in that file, and the CSRF assertion is now real.

---

## Tests

`tests/e2e_browser/test_e2e_browser_05_preview_and_vault.py` — 7 tests.

**Proven to catch the bugs.** With both fixes reverted: **5 failed, 2 passed**.
The two that still pass are the guard tests — "the app itself still forbids
inline script" and "SVG hardening still wins" — which correctly pass either
way, because they exist to catch *this change* regressing something, not to
catch the original bug.

With the fixes in place: **7 passed**.

## Regression status

| Suite | Result |
|---|---|
| Full non-browser | **3959 passed, 19 skipped, 0 failed** (unchanged) |
| Browser E2E | **68 passed, 0 failed** (was 67 passed / 1 permanently failing) |
| `ruff check backend frontend scripts` | pass |
