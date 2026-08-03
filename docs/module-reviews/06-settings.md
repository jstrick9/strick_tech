# Module Review 06 — Settings

**Reviewed:** 2026-08-03 · **Commit:** `21bc7ef` · **Sidebar position:** Settings (ESSENTIALS)

**Scope:** the six Settings tabs (API, Appearance, Layout, Agents, Ollama, System), their
backing routers (`secrets.py`, `onboarding.py`, `userprofile.py`), and the Account Settings
modal (`57-account-settings.js`).

This completes the **ESSENTIALS** group — all six panes reviewed.

---

## Findings

### 🔴 1. "Test Connection" reported success for any input

The endpoint validated an OpenRouter key by calling `GET /api/v1/models`. That's a
**public** endpoint. Verified against the live API:

| Request | Response |
|---|---|
| Valid key | 200 |
| Garbage string | **200** |
| No `Authorization` header at all | **200** |

So the button reported *"✅ Verified OpenRouter connection! 338 models available"* no matter
what was pasted.

The practical failure is worse than a cosmetic one: paste a typo'd or revoked key, get a
green check and an `ONLINE (338 MODELS)` badge, then have **every chat request fail** with
no idea why — the one screen built to diagnose exactly that problem actively confirmed the
broken configuration was fine.

**Fixed** — now calls `/api/v1/auth/key`, the authenticated endpoint (401 for bad or
missing keys, verified live), queries the catalogue only after the key is accepted, and
surfaces the key's own label / usage / credit-remaining metadata.

### 🟠 2. An unverified key was saved and made live before being tested

`saveApiKey()` wrote to the vault **first** and verified afterwards — so a key already
known to be broken was persisted and injected into the process environment regardless,
leaving the platform actively configured with a bad credential.

**Fixed** — verify first, save only on success, and state plainly that nothing was saved
and the previous connection is unchanged on failure. This removes the confusing
`SAVED / UNVERIFIED` state entirely.

### 🟠 3. Preference *values* were never validated

Keys were allowlisted, but values were accepted verbatim:

```
font_size: "enormous"   → saved
font_size: 99999        → saved
sidebar_width: -1       → saved
theme: "not-a-theme"    → saved
```

Each corrupts the UI on next load — an unusable font, a negative sidebar, a theme with no
stylesheet.

**Fixed** with `validate_preference()`: booleans coerced (checked *before* numerics, since
`bool` subclasses `int`), numerics **clamped** rather than rejected so a slider overshoot
settles at the limit, enums checked against the themes actually shipped, text length-capped,
and `shortcuts` filtered to known names. Rejections are reported per-key rather than
silently dropped. A test asserts every shipped default passes its own validator.

### 🟠 4. Font size silently reverted on every startup

It's stored in **two incompatible places**:

| Store | Format | Written by |
|---|---|---|
| `/api/profile` | `'sm'` / `'base'` / `'lg'` | `saveFontSize()` |
| `/api/onboarding/preferences` | number (`14`) | **nothing** |

`applyPreferences()` read the *numeric* one — which nothing ever writes, so it was always
the `14` default — and stamped `14px` over the user's chosen scale on every load. Choosing
"Large" appeared to work, then quietly undid itself on refresh.

**Fixed** — prefers the saved scale, treats the numeric preference as a fallback, and both
call sites now share one `FONT_SCALE_PX` token map so they can't drift again. Verified in
jsdom across all four cases.

### 🟡 5. Status codes

Secrets `GET`/`DELETE` returned 200 for keys that don't exist — `DELETE` even reported
`{"deleted": <key>}` for a key that was never there. Unknown preference reads returned 200.
Now 404, with 400 for validation failures and 503 when the encrypted vault is unavailable.

---

## Verified working (no change needed)

- **Secrets vault security is solid** — values are encrypted, `/list` returns only
  fingerprints and masked placeholders, and `/get` never reveals plaintext
- Preference **key** allowlisting (arbitrary keys correctly rejected)
- Ollama connection testing, including the `/api/tags` → `/v1/models` fallback
- Account Settings modal — all save paths check `ok !== false` and surface failures
- Backup with rotation; all six tab handlers defined and wired
- `/api/profile` has its own correct `font_size` validation (422 on bad input)

---

## Cross-module impact

| Module | Impact |
|---|---|
| **Chat** | Directly affected — a key that "verified" here but was invalid produced unexplained chat failures. Verification is now meaningful. |
| **All panes** | Theme, font size and UI mode come from preferences; bad values could previously corrupt any pane. |
| **Onboarding** | Shares `DEFAULT_PREFS` and the preferences endpoints, so it inherits validation. |

---

## Tests added

`tests/unit/test_55_settings_module_review.py` — **39 contracts** covering real key
verification (and that `/models` is no longer the gate), verify-before-save ordering, value
validation (invalid rejected, out-of-range clamped, valid passthrough, defaults
self-consistent), status codes, and font-size unification.

One existing contract updated: `test_38` pinned the literal inline `sizeMap` declaration.
The scale *values* it guards are unchanged — the assertion now targets the shared constant
and its reuse, which is a stronger check.

**Suite:** 2870 backend passed / 12 skipped / **0 failed** · 75 vitest passed · ruff clean.

---

## Housekeeping

Purged **84 test-suite budget caps and 6 absurd ledger rows** that had re-accumulated and
were blocking chat behind a $0.01 cap. This is the third module where test residue in the
shared database interfered with live behaviour — see follow-up #2.

---

## Recommended follow-ups

1. **Consolidate the two font-size stores.** I fixed the symptom; the root cause is that
   `/api/profile` and `/api/onboarding/preferences` both own overlapping settings with
   different formats. One should be authoritative.
2. **Tests must stop writing to the production database.** Test caps, injection-payload
   secrets and fake ledger rows have now interfered with three separate reviews. A
   per-run temp database (or a `conftest` fixture that snapshots and restores) would end
   this class of problem permanently.
3. **`/api/secrets/list` returns 170 entries**, almost all test artifacts. Worth a cleanup
   pass and pagination.
4. **Settings has no "unsaved changes" indicator** — several controls save instantly while
   others need an explicit button, with no visual distinction between the two.
