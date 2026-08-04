# Module 19 — Plugins

*(consolidated pane: `plugins` → **Plugin Hub**, absorbing `marketplace`; `skills` and `pluginsdk` retained)*

Routers: `plugin_hub.py` (new), `plugins.py`, `marketplace.py`, `skills.py`, `pluginsdk.py`
Frontend: `34-plugin-hub.js` (new), `23-plugin-marketplace.js`, `25-skills.js`

Five bugs, all reproduced live first. One is a genuine security hole; the rest
are the reason the feature did not feel finished.

---

## 1. SSRF in `POST /api/plugins/install/url`

"Install a plugin from a URL" is a server-side fetch of a user-supplied
address. That is the textbook SSRF primitive, and it was unguarded:

```
{"url": "http://localhost:8787/api/health"}         → reached its own API
{"url": "http://169.254.169.254/latest/meta-data/"} → HTTP 401 — it CONNECTED
```

A 401 from the cloud metadata endpoint is not a failure; it is proof the
request arrived. On a hosted deployment that endpoint hands out credentials.

The handler also returned `f'Failed to fetch: {e}'`, putting the upstream
response into the reply — **turning a blind SSRF into a read primitive.**

Fixed with four layers, because any one alone is bypassable:

| Layer | Bypass it stops |
|---|---|
| Scheme allow-list | `file:///etc/passwd`, `gopher://` |
| Host pattern block | `localhost`, `127.`, `10.`, `169.254.` |
| **DNS resolution check** | public hostname resolving to a private IP |
| No redirect following | public URL that `302`s to the metadata endpoint |

The DNS check is the important one. Matching the host *string* is the same
"check the label, not the thing" mistake as the SQL-prefix and path-prefix bugs
found in Modules 12 and 17. Responses are also capped at 2 MB, and upstream
content is never echoed back.

---

## 2. Two parallel, mutually unaware plugin systems

| | `/api/plugins` | `/api/marketplace` |
|---|---|---|
| Packs | 4 | 8 |
| Install state | `plugins/installed.json` | `mkt_installed` table |
| Pane | Installed | Marketplace |

They **overlapped** — `research-assistant` existed in both with different
skills — rendered in different panes, and each showed the other's installs as
still available. Answering *"what do I have installed?"* meant checking two
places and reconciling them by hand.

`backend/routers/plugin_hub.py` federates both. Neither backend is replaced;
both keep working and their endpoints are untouched.

Normalisation is the substance rather than cosmetics: the two disagree on field
names for identical concepts (`emoji`/`icon`, `version`/`latest_ver`,
`skill_count` computed two different ways), so **the UI previously had to know
which backend a card came from in order to render it**. Duplicate ids are
merged, preferring the installed (then richer) entry — showing the same pack
twice with independent Install buttons is precisely the confusion being removed.

---

## 3. Curated packs reported zero skills

The seeder wrote skills to a manifest **file** and left the `skills_json`
column at its `'[]'` default. `_pack_row_to_dict()` prefers the manifest, so
this was invisible on the machine that first seeded it — but any deployment
whose data dir differs (fresh install, container, moved `AGENTIC_OS_DATA_DIR`)
showed **every curated pack as empty while still advertising "12,493 downloads
· 4.7 stars"**.

```sql
SELECT id, skills_json FROM mkt_packs;
agenticai-core  []
code-wizard     []      -- all 8 rows
```

Fixing the `INSERT` was **not sufficient**: the seeder skips rows that already
exist, so every existing deployment would have stayed broken forever. Added an
in-place backfill that repairs the column when it is empty and the curated pack
has skills to offer. Worth stating as a rule — *a seeding fix that only helps
empty databases fixes nobody who already has the bug.*

---

## 4. Install counts lied

`install_pack` returned `len(skills)` — the pack's total — while the sync loop
skips ids that already exist. Verified: reported **6 added**, actually added
**5**. Now reports what happened, with `skills_already_present` separately. The
same *report what you did, not what you attempted* rule applied throughout this
review, and it is the number the UI puts in front of the user.

---

## 5. The user experience

`frontend/js/34-plugin-hub.js`, modelled on the surfaces users already know —
ChatGPT's GPT store, Claude's connector directory, Manus's tool catalog:

* **Starter collections up front.** *Getting Started*, *For Developers*, *For
  Creators*, *For Founders*, *For Researchers* — each installs a whole set in
  one click. An empty search box is a poor first run; three obvious buttons is
  not. A test asserts every referenced pack actually exists, because a starter
  bundle pointing at a missing pack is worse than no bundle.
* **One search box** over both backends, with category chips.
* **A preview drawer** showing the real skills, their inputs, and the actual
  prompt templates *before* installing. Previously unanswerable — the registry
  endpoint explicitly strips skills (`'skills': None`), so the only way to learn
  what a pack did was to install it and go look in a different pane.
* **Honest card state** from a single source.
* **Test residue filtered out.** `🧪 sysplugin_928ffc841e` sitting next to
  *Social Media Pack* teaches a first-run user that the catalog is not curated.

Sidebar: **4 panes → 2**. Marketplace folds into the Hub; Skills and the SDK
remain, because *"use what you installed"* and *"build your own"* are different
jobs, not duplicate catalogs.

### Verified end-to-end

```
1. Hub stats        11 packs · 54 skills available
2. Collections      5 offered, live install state
3. Preview          dev-toolkit → 5 skills, prompts visible
4. One-click set    "For Developers: 13 skill(s) added"
5. Installed list   7 packs, both sources, one list
6. Skills pane      48 skills ready to run
```

---

## Tests

`tests/unit/test_78_plugin_hub_module_review.py` — **38 cases**.
**Proven to catch the bugs: with `plugins.py` and `marketplace.py` stashed, 18
of 38 fail.** That run also takes 21s against 1.6s — the difference is real SSRF
connections being attempted, which is its own evidence.

### Self-corrections

1. My first leak test asserted on a message that the **DNS guard** produced
   before the fetch was ever attempted — it would have passed without testing
   the thing it named. Rewritten to stub the URL check and force a fetch
   failure carrying a marker string, then assert the marker never appears.
2. My replacement for a stale regression test used a *marketplace* pack against
   the `/api/plugins` uninstall route and failed. That was correct behaviour:
   the route only owns `BUILTIN_REGISTRY` packs. The asymmetry is exactly why
   `/api/hub` exists, and the test now says so.

Also updated two U-03 regression tests that guarded against a `405` but pinned
`200` for a nonexistent plugin. One asserted `status_code not in (404, 405)`,
which made a **correct 404 indistinguishable from the missing route it was
written to catch**.

Full suite: **3273 passed / 18 skipped / 0 failed** (was 3235).

---

## Recommended follow-ups

1. **Plugin installs are not sandboxed.** Packs are prompt templates today, so
   the risk is prompt injection into an agent rather than code execution — but
   `pluginsdk` accepts richer manifests, and nothing scans a pack's prompts for
   instructions targeting the agent that will run them.
2. **No signature or provenance on custom plugins.** `install/url` now refuses
   internal addresses, but a public URL is still trusted entirely on content.
3. **No update path for installed packs.** `mkt_releases` exists and
   `check-updates` is implemented, but the Hub does not surface it.
4. **Uninstall does not remove user edits.** A skill edited after install is
   deleted by uninstall with no warning.
5. **`07-marketplace.js` contains no marketplace code** — it holds BugBot,
   Health, GitAI and Ambient renderers. A misleading filename in a codebase
   this size is a real navigation cost.

---

# Follow-ups 1–5 (`da6b3e4`)

All five closed.

## 1. Plugin templates were executable

`skills.run_skill()` renders templates with `template.format(**inputs)`.
Python's format mini-language evaluates attribute access, so a plugin-supplied
template is executable to a degree. Verified against a skill installed through
the normal endpoint:

```
template : "Value: {topic.__class__.__mro__}"
rendered : "Value: (<class 'str'>, <class 'object'>)"
```

**Honest scope — checked, not assumed.** The usual escalation
`{x.__class__.__init__.__globals__[sys]}` fails here: inputs are coerced with
`str()`, and `str.__init__` is a `wrapper_descriptor` with no `__globals__`. A
skill run also reaches `llm.complete()` with **no tool or function access**. So
this is information disclosure, not RCE, and I am not going to describe it as
worse than it is.

It is still worth refusing. *"The escalation happens not to work today"* is not
a security property — it depends on a `str()` call in an unrelated function
staying where it is. A template has no legitimate reason to reach through an
attribute.

`backend/services/plugin_safety.py` refuses attribute access, indexing,
dunders, and positional fields. Plain `{name}` substitution is unaffected.

### Both doors, again

Enforced on `/api/plugins/install/{json,url}` **and** `POST /api/skills`.
Guarding only the plugin path would leave the identical primitive reachable one
endpoint over — the third instance of this pattern in the review (Module 17's
`/table/create`, Module 19's two install routes, now this).

### Injection is warned, not blocked

An injected instruction can distort an agent's **output** but cannot make it
execute anything. And over-blocking a text pattern rejects legitimate packs: a
prompt-engineering pack that *teaches* about injection contains those very
strings. The rule I settled on — **refuse what has no legitimate use; warn
about what does.** A refusal the user cannot override just teaches them to
distrust the check.

## 2. Provenance

Nothing recorded where an installed pack came from, so a plugin pasted from an
arbitrary URL was indistinguishable from curated content once installed. Each
install now records origin (`builtin`/`url`/`json`), source URL, content hash,
and any warnings it was accepted with.

`_BUILTIN_IDS` is captured **before** custom plugins are appended to
`BUILTIN_REGISTRY`. Both `_load_custom_registry()` and `_install_plugin_data()`
append to that list, so a membership test taken any later would label every
custom plugin "builtin" — precisely the distinction the record exists to make.

## 3. Updates

`mkt_releases` and `check-updates` already existed; **nothing surfaced them**,
so an installed pack could go stale indefinitely with no sign anywhere.
`GET /api/hub/updates` federates both backends; the hub shows a banner with
one-click Update.

## 4. Uninstall destroyed skills other packs still needed

Skills can be owned by more than one pack:

```
install dev-toolkit + devops-toolkit  → dockerfile present
uninstall dev-toolkit                 → dockerfile DELETED
devops-toolkit                        → still "installed", silently broken
```

`linkedin_post` has the same overlap (social-media-pack / content-creator).

A skill is now removed only when no other still-installed pack — in **either**
registry — claims it, and the response reports what it kept.

**The mirror-image bug**, found while verifying the fix: the marketplace
uninstall filtered on `source_plugin`, a tag only the *marketplace* installer
applies. Skills installed by the plugins backend were therefore **orphaned** —
after removing both owners, `dockerfile` was still in the Skills pane with no
pack behind it. Two backends writing to one `skills.json` with two different
removal strategies. Both now share one ownership rule.

## 5. Misleading filename

`07-marketplace.js` contained no marketplace code — `renderBugBot`,
`renderHealth`, `renderGitAI`, `renderAmbient`. Renamed to
`07-quality-tools.js`. It sent me to the wrong file twice while reviewing this
module, which is the argument for treating it as a real defect rather than
cosmetics.

## A 500 the tests found

`install_plugin` used bracket access for `version`/`author`/`category`/`emoji`
— fields a minimal custom plugin legitimately omits — so the documented "paste
your JSON" flow crashed with `KeyError` → **HTTP 500**. Reproduced with a
`{id, name, skills}` plugin. Defaults applied.

## Tests

`tests/unit/test_79_plugin_safety_followups.py` — **44 cases**.
**Proven to catch the bugs: with the four routers stashed, 16 of 44 fail.**

### Two self-corrections

1. My first scanner made *"template uses an undeclared input"* a **blocking
   error**, and it immediately rejected the create-skill endpoint's **own
   default template** `{prompt}` — which declares no inputs and is filled by
   the caller at run time. Rejecting a request for using the endpoint's own
   default is the check being wrong, not the caller. Demoted to a warning.
2. `{}` parses to a field name of `''`, which my truthiness filter silently
   dropped — bare positional braces slipped through. Caught by testing the
   scanner against its own edge cases rather than only against the exploit.

Full suite: **3317 passed / 18 skipped / 0 failed** (was 3273).

## Module 19 status

All five follow-ups closed. Nothing outstanding for Plugins.
