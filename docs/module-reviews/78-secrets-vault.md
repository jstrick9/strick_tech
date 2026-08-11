# 78 — Secrets Vault (`secrets`)

**Pane:** `secrets`
**Tabs:** Secrets Vault, 🛡 Encryption (`pqc`) — 2/2 covered
**Frontend:** `frontend/js/16-terminal.js` (vault section), `frontend/js/03-features-a.js` (pqc tab)
**Backend:** `backend/routers/secrets.py`, `backend/routers/onboarding.py`, `backend/services/llm.py`
**Tests:** `tests/unit/test_153_module17_secrets_vault.py` (29)
**Status:** reviewed, fixed, verified live

Destination 6 of 20 in the consolidated review.

---

## Why this destination, measured against ICM

ICM's standard is that every layer states its own basis and never asserts more
than it established. The Secrets Vault is where the review's dominant defect
theme — **confident reporting of unverified things** — carries the highest cost,
because every claim this screen makes is a security claim. A padlock icon that
is decorative is worse than no padlock at all: it actively discourages the user
from checking.

Seven defects were found. All were reproduced against a live server before any
code changed, and each has a test proven to fail against the unfixed code
(13/13 individual breakages caught — see *Revert-proof* below).

---

## Findings

### 1. The pencil icon widened a secret's blast radius — privilege escalation

`set_secret` read scope and agent as:

```python
scope = body.get('scope') or 'global'
agent = body.get('agent') or ''
```

and then wrote them through an `ON CONFLICT ... DO UPDATE SET scope=excluded.scope`.
An **omitted** field was therefore indistinguishable from an explicit "global".

`vaultEdit()` — the ✏️ button on every row — sends `{key, value}` and nothing
else. So changing the *value* of a secret scoped to a single agent silently
promoted it to **every agent on the platform**. Verified live:

```
POST /set {"key":"PROBE_SCOPE_KEY","value":"v1","scope":"agent","agent":"builder"}
  -> scope=agent  agent=builder
POST /set {"key":"PROBE_SCOPE_KEY","value":"v2"}          # what vaultEdit sends
  -> scope=global agent=""
```

No warning, no audit distinction, nothing in the UI. The user's only signal was
the scope column changing on the next refresh.

**Fix:** an absent `scope`/`agent` now means *leave the stored value alone*. An
explicit change is still honoured (test:
`test_explicit_scope_change_is_still_honoured`), so this is not a "scope can
never be changed" regression.

### 2. The per-agent scope had no reader anywhere in the platform

The vault has offered a `global | agent` dropdown since it was written. Nothing
ever read it back. `_inject_to_env()` selected `WHERE scope='global'` and loaded
those into `os.environ`; every consumer — the LLM client, tools, subprocesses —
then read `os.environ`. An agent-scoped secret was stored, listed in the UI as
scoped, and **used by nobody**. The dropdown was decorative.

Confirmed by grep across the whole backend: outside `secrets.py` itself, no
query ever referenced `scope='agent'`.

**Fix:** added `secrets_for_agent(agent_id)`, which resolves globals as the base
layer and lets an agent-scoped secret of the same name override it for that
agent only, and wired it into `llm._or_key(agent_id)` — the one place the
OpenRouter credential is actually read. `agent_id` was already threaded through
`complete()` and `_complete_impl()`, so no signature churn was needed.

Both the streaming and non-streaming OpenRouter call sites were updated
together. Fixing one and not its twin is the **"second door"** pattern that has
now appeared 16 times in this review; it was explicitly checked for here.

### 3. …and `set_secret` leaked the scoped value into `os.environ` anyway

Even with (2) unfixed, the write path made the scope moot immediately:

```python
os.environ[key] = value      # unconditional
```

`os.environ` is process-global. Choosing "agent — specific agent" stored the
restriction and then published the value to the entire process until the next
restart, at which point startup injection's `scope='global'` filter finally
applied. The isolation was inconsistent as well as absent.

**Fix:** only global secrets reach `os.environ`; narrowing a previously global
secret now actively pops the stale copy.

### 4. `scope` was never validated

`scope='agent'` with a blank agent name stored a secret that matched no agent
and could never be reached by anything — invisible dead weight holding a live
credential. An arbitrary string (`scope='everyone'`) was accepted verbatim and
stored.

**Fix:** `scope` must be `global` or `agent`; `agent` scope requires a non-blank
agent name. Both return 400 and store nothing.

### 5. Onboarding wrote the API key into the vault in plaintext

`/api/onboarding/quick-setup` did:

```python
con.execute("INSERT OR REPLACE INTO secrets (key, value_enc, scope) VALUES (?, ?, 'global')",
            ('OPENROUTER_API_KEY', api_key))
```

The raw key went straight into `value_enc` — the column every other writer fills
with a Fernet token. Verified live; the row read back as:

```
{'key': 'OPENROUTER_API_KEY', 'value_enc': 'sk-or-v1-PLAINTEXT-PROBE-123456',
 'fingerprint': None, 'length': None}
```

Three consequences, all confirmed:

1. The key sat in the SQLite file **in the clear** while the Secrets Vault
   screen displayed it with a 🔒 badge beneath the banner *"AES-256 Fernet
   Encryption Active"*. Module 17 previously refused to let Database Studio read
   the secrets table precisely to protect this data; the wizard wrote it in a
   form where that protection bought nothing.
2. `fingerprint` and `length` were NULL, so the vault listed the key as
   **"0 chars"**.
3. `_decrypt()` could not read it back, so `_inject_to_env()` **skipped it on
   every restart** and "Reveal" returned an empty string. The key the user
   pasted into the setup wizard never actually reached the LLM client — the
   wizard's whole purpose, silently unfulfilled.

**Fix:** one shared writer, `_store_openrouter_key()`, used by both
`/quick-setup` and `/complete` (the second door again — `/complete` already
encrypted correctly, so the two paths had drifted into different storage
formats). It returns `False` rather than falling back to a weaker store, and
callers surface that as a 503.

### 6. The padlock was assumed, never measured

`list_secrets` reported `encrypted: True` for the whole vault based only on
`_get_fernet()` returning a cipher — i.e. on the *library being installed*. Each
row was then rendered with 🔒 purely because it existed. Whether the stored
ciphertext could actually be decrypted was never checked, which is exactly how
the plaintext row from (5) earned a padlock.

Same shape on reveal: `_decrypt` returns `''` both for "the plaintext was empty"
and "this did not decrypt", and `get_secret` returned
`{'ok': True, 'value': ''}` either way — so the UI popped its *"🔐 copy it now
— this value is encrypted at rest"* dialog around an empty box.

**Fix:** `_is_readable()` attempts a real decrypt per row. `/list` now returns
`readable` and `storage` per item plus an `unreadable` count and a specific
warning; `/get?reveal=true` returns **422** with an actionable message instead of
an empty success. The list also stopped shipping `value_enc` to the browser at
all (it was added to the query for the readability check and is popped before
serialisation — covered by `test_list_never_returns_the_ciphertext_itself`).

In the UI: unreadable rows get a distinct `⚠️ unreadable` badge, their Reveal
button is **disabled**, and a banner states how many of the stored secrets are
not in use by any agent. The 🔒 now means "verified readable" and nothing else.

### 7. Second door #16 — the setup wizard verified keys against a public endpoint

`/api/secrets/test-connection` was fixed in an earlier module: it used to call
`GET /api/v1/models`, which is **public** on OpenRouter and answers 200 with the
full catalogue for a garbage key, a revoked key, or no `Authorization` header at
all.

The onboarding wizard contained the identical code and was never touched.
Verified live:

```
POST /api/onboarding/quick-setup {"api_key":"sk-or-v1-total-garbage-not-a-real-key"}
  -> {"backend":"openrouter","status":"available","models":401}
  -> "OpenRouter connected. 140+ models available including Claude, GPT-4o, …"
```

…and it then **stored that rejected key**, overwriting whatever working key was
there and injecting it into `os.environ`. The user's first interaction with the
product ended with a green check and a completely broken install. The
`/quick-setup/status` endpoint disagreed (`openrouter: false`) but is a
different screen.

**Fix:** verify via `GET /api/v1/auth/key` (401 on a bad key), report
`invalid_key` vs `unreachable` distinctly, and **refuse to persist a key the
provider rejected** — returning 400 with the reason rather than saving it.

### 8. `updated_at` published local wall-clock time labelled as UTC

`list_secrets` selected `datetime(updated_at,'localtime')`, and the global
response layer (`backend/services/timestamps.py`) then appends a `Z` to any
naive timestamp under a time-shaped key — correctly, because its documented
contract is that such values come from SQLite `CURRENT_TIMESTAMP`, which is UTC.

The `localtime` conversion broke that contract. On any server not running in UTC
the vault published a local time **stamped as UTC**, wrong by the offset, with
no way for a client to tell. Invisible in this sandbox (TZ=UTC), which is why it
survived; it would misreport credential rotation times on any real deployment.

**Fix:** return the raw UTC column and let the existing normaliser label it.

---

## Revert-proof

Every fix was individually reverted against the finished test file, with
`__pycache__` cleared each time, to prove the tests catch the behaviour rather
than the diff. **13 of 13 breakages caught**, baseline green before and after:

| # | Breakage reintroduced | Tests that failed |
|---|---|---|
| 1 | scope reset on value-only edit | 1 |
| 2 | agent scope has no reader | 4 |
| 3 | scoped secret leaks to `os.environ` | 2 |
| 4 | scope not validated | 3 |
| 5 | onboarding stores plaintext | 3 |
| 5b | onboarding drops fingerprint/length | 1 |
| 6 | readability assumed | 2 |
| 6b | reveal claims ok on empty value | 1 |
| 6c | list ships ciphertext | 1 |
| 7 | wizard verifies via public endpoint | 2 |
| 7b | rejected key still stored | 2 |
| 8 | llm ignores agent scope | 1 |
| 9 | `updated_at` shifted off UTC | 1 |

## Live verification

Against a running server and real Chromium, with one healthy Fernet row
(agent-scoped) and one plaintext row inserted directly:

```
GOOD_KEY      🔒              agent   13 chars   reveal enabled
LEGACY_PLAIN  ⚠️ unreadable   global  —          reveal DISABLED
banner: "1 of 2 stored secrets cannot be decrypted and are NOT in use by any agent."
console: no errors, no [delegate] unknown function
```

All nine vault handlers resolve on `window` (this file is not IIFE-wrapped).

## Cross-module impact

- **`backend/services/llm.py`** — `_or_key()`/`_or_headers()` take an optional
  `agent_id`. Both OpenRouter call sites pass it. Falls back to `os.environ` on
  any vault failure, proven by `test_llm_key_lookup_survives_a_broken_vault`; a
  vault outage must never break every AI call.
- **`backend/routers/onboarding.py`** — `/quick-setup` can now return **400**
  (key rejected) and **503** (cannot encrypt) where it previously always
  returned 200. Its `backends[]` entries gained `http_status` on `unreachable`.
- **`frontend/js/17-database-studio.js`** posts to `/api/secrets/set` with an
  explicit `scope:'global'`, so it is unaffected by the absent-means-unchanged
  change.
- **API additions** (all additive): `/list` items gain `readable` and `storage`;
  `/list` gains `unreadable`. `/get?reveal=true` gains a 422 status.
- Left as-is: `pqc` tab (reviewed in module 71), and the vault's use of
  `data-act-click` with `jsArg()` — safe because the server-side key pattern
  `^[A-Z][A-Z0-9_]{0,127}$` admits no quote characters.

## Suite

`3898 unit (2 skipped)` + `655 regression/system/uat (10 skipped)` =
**4,553 passing, 0 failures**. Linters clean.

### Self-correction

The first full run failed `test_18_voice_tts_imagegen.py::test_imagegen_with_prompt`
with a real HTTP 401. That was **my test's fault, not a pre-existing issue**:
`_store_openrouter_key()` injects into `os.environ` by design, and my probe key
escaped the test into the session, so imagegen made a live request with it. The
fixture now pins `OPENROUTER_API_KEY` via `monkeypatch` for the module's
duration. A skip is not a pass, and neither is blaming the environment.
