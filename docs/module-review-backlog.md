# Module Review Backlog — Agentic OS

Ordered by *highest user impact first* (per user direction). Each module is
reviewed → fixed → verified (unit tests + live browser probe + audit suite
green) → committed. Large architectural rewrites are deferred; defects and UX
polish are in scope.

| # | Module | Frontend | Backend | Priority | Status |
|---|--------|----------|---------|----------|--------|
| 1 | **Chat** | 01-app-core.js (chat) | chat.py, engine.py, llm.py | Core daily | DONE (#077) |
| 2 | **Studio** | 02-studio.js | builder.py, multifile_agent.py, multitab.py | Core daily | DONE (#078) |
| 3 | **Tasks / Kanban** | 28-kanban.js | tasks.py | Core daily | VERIFIED (no defect) |
| 4 | **ICM Workspaces** | 59-icm-workspaces.js, 60-inbox.js | icm.py + icm_* services | Core daily | VERIFIED (no defect) |
| 5 | **Settings / Account** | 57-account-settings.js | secrets.py, userprofile.py, auth.py | Core daily | VERIFIED (no defect) |
| 6 | **Knowledge Graph** | 05-evals-observability.js | knowledge_graph.py | Knowledge | VERIFIED (no defect) |
| 7 | **RAG** | 05-evals-observability.js | rag.py | Knowledge | VERIFIED (no defect) |
| 8 | **Docs / Knowledge** | 12-information-hierarchy.js | hierarchy.py, docs_center.py | Knowledge | VERIFIED (no defect) |
| 9 | **Search / Code** | (search) | search.py, codesearch.py, codeindex.py | Knowledge | VERIFIED (no defect) |
| 10 | **ICM Router / Memory** | — | icm_router.py, memory.py, memory_tiers.py | Ops | VERIFIED (no defect) |
| 11 | **Supervisor / Swarm** | 48-supervisor.js, 26-swarm.js | supervisor.py, swarm.py | Ops/collab | VERIFIED (no defect) |
| 12 | **Goals / Loops / Fusion** | 49-goals.js, 40-loops.js, 41-fusion.js | goal_manager.py, loops.py, fusion.py | Ops/collab | VERIFIED (no defect) |
| 13 | **MCP / Connectors / Plugins** | 39-mcp-panel.js, 50-mcp-gateway.js, 35-connect-hub.js, 34-plugin-hub.js | mcp.py, mcp_gateway.py, connectors.py | Integrations | VERIFIED (no defect) |
| 14 | **Evals / Observability** | 05-evals-observability.js | evals.py, observability.py, eval_framework.py | Quality | VERIFIED (no defect) |
| 15 | **Terminal / Security / System** | 16-terminal.js | terminal.py, security.py, system.py | Ops | VERIFIED (no defect) |
| 16 | **Templates / Prompts / Skills** | 21-template-gallery.js, 14-prompt-library.js, 25-skills.js | templates.py, prompts.py, skills.py | Content | VERIFIED (no defect) |
| 17 | **Workspaces / Deploy / Git** | 30-workspaces.js, 35-deploy.js, 18-github.js | workspaces.py, deploy.py, github.py, gitai.py | Ops | VERIFIED (no defect) |

Rules:
- Each module: enumerate endpoints + UI behaviour → find real defects /
  incompleteness / improvement opportunities → fix (tools + tests) → live probe
  → run audit + full test suite → commit with `#NNN`.
- Record findings in docs/round-5-progress.md as `#NNN`.
- Do NOT re-litigate already-fixed items (#064–#076).

---

## Deeper Work Round (2026-09-10) — auth flow, secrets vault, real-key LLM path

Follow-up to the 17-module review: the three "optional deeper work" tracks.
Same rules — every fix verified by unit tests, the live security suite, and a
live browser probe before commit.

### #079 (auth) — the backend had a complete auth system; the frontend had none
Register/login/logout/rotate-key existed server-side since the beginning, with
ZERO frontend call sites. The terminal's "authentication required" error told
users to curl POST /api/auth/register; the lost-session banner's Sign-in button
opened Settings, which had no sign-in form. Built the Access & Sign-in card
(Settings → Security): three states (auth off → create first admin account;
configured → sign in; signed in → identity, expiry, sign out, rotate key),
one-shot credential reveals that persist until dismissed, register→auto-login.
`00-csrf.js` (the app's single fetch wrapper) now attaches the session bearer
token to same-origin API calls; the banner routes to the Security tab.

### #080 (auth) — password hashing, throttling, session hygiene
- SHA-256 password hashes → PBKDF2-HMAC-SHA256 (200k iterations,
  self-describing format, transparent upgrade on next login of legacy hashes).
- Unknown usernames now burn the same PBKDF2 cost as wrong passwords
  (no username-enumeration timing oracle).
- Per-(username, ip) failed-login throttle: 10 failures/15 min → 429 +
  Retry-After; other users and IPs unaffected; success clears the counter.
- Expired sessions swept on every login (they were only deleted if their own
  token was presented again — which never happens).

### #081 (vault) — _decrypt's base64 fallback produced mojibake, not secrets
Python's b64decode discards invalid characters and decodes the rest, so a
tampered/plaintext value_enc "decrypted" into garbage that went straight into
os.environ as an API key. Fallback removed: Fernet or nothing, consistent with
what the vault UI already reports. Reveal responses now carry
Cache-Control: no-store.

### #082 (vault) — agent-scoped secrets erased operator environment variables
Storing an agent-scoped secret ran `os.environ.pop(key)` unconditionally, so
with OPENROUTER_API_KEY set in the server's environment, a scoped write (or a
later delete) removed the operator's key for the rest of the process — every
global consumer silently fell back to local inference. Measured live. The
vault now tracks which env vars IT injected (`_VAULT_INJECTED_KEYS`) and only
takes those back.

### #083 (app) — DNS-rebinding defense (Host header validation)
A localhost server is not protected by CORS against DNS rebinding: a public
name that flips to 127.0.0.1 makes the browser treat attacker pages as
same-origin, with /api/secrets/get?reveal=true as the crown-jewel read. The
middleware now refuses unrecognised Hosts (403) before any handler runs.
Allowed: IP literals, localhost, *.localhost, *.local, *.internal, plus
AGENTIC_OS_ALLOWED_HOSTS (exact or *.wildcard). OPTIONS and /api/webhooks/
exempt (preflight carries no data; webhooks arrive via registered public
hostnames).

### #084 (idempotency) — login responses were replayed after logout
Sign in → sign out → sign back in inside the 10s idempotency window replayed
the FIRST login's cached response: the client stored the token logout had just
revoked, every authenticated call 401'd, and the UI showed the sign-in form
even though login "succeeded". Session-lifecycle routes (/api/auth/*) are now
exempt from replay.

### #085 (builder) — /api/health leaked filesystem paths by default
db_path and data_dir shipped to any unauthenticated caller (username, OS,
layout disclosure), contradicting the security suite's own rule. Paths now
require ?debug=paths; the sandbox flags remain in the default response.

### Test-infrastructure repairs (the suite was lying about its own health)
- sec_03 terminal tests asserted the pre-hardening 200+error contract; updated
  to accept the hardened 403 refusals.
- sec_04 tier-reset test now understands unlocked-mode (`stored_tier`).
- sec_08's git-commit injection test REALLY committed — every suite run left
  ~6 junk commits ("$(whoami)") plus swept-up untracked files in the user's
  repo. Autouse fixture restores HEAD now.
- `sec_ok` treats 503 + code=llm_unavailable as honest degradation, not a
  crash (nine LLM-backed endpoints otherwise "fail" on a provider-less
  server); the test client timeout is 30s so a blackholed DDG egress (two
  sequential 8–12s timeouts) doesn't race the server.
- tests/security/conftest.py documents the live-server recipe
  (AGENTIC_OS_HOST=127.0.0.1 RATE_LIMIT_MAX=100000) — with neither set the
  suite shows ~26 failures that are all environment, not defects.
- Stale unit tests updated (dashboard retry mechanism, health debug flag,
  webhook-exemption count pinned at two gates).
- Restored the executable bit on all five tracked .sh scripts (lost to a
  history rewrite; fresh clones got "permission denied").

### Real-key LLM path — verified end-to-end with a mock provider
Mock OpenRouter + Ollama servers (127.0.0.1:8790/8791) wired through the real
env seams (OPENROUTER_BASE_URL / OLLAMA_BASE_URL). Live browser probe, 33/33:
streaming + non-streaming chat, correct bearer key + model observed at the
provider, agent-scoped vault key actually used for that agent, provider-500 →
Ollama fallback with telemetry note, FinOps ledger + observability traces
recorded, zero JS page errors.

### Known environmental items (not defects, documented for future rounds)
- tests/unit/test_120 audit-ratchet browser checks flip between runs in this
  sandbox (console NOISE volume, touch-target counts vary with server state);
  a control run on pre-change code reproduces the same failures — pre-existing.
- The security sweep writes payload-named rows into runtime stores (skills
  catalog, ICM route log, preview templates). The git-commit site now cleans
  up after itself; the others are inert residue worth fixture-izing later.
- With no LLM provider, /api/websearch/search can take ~20s (two outbound
  timeouts back to back) on a blackholed network.

**Suites:** frontend 310/310 · backend unit 4,782+ (5 environmental ratchet
flakes, proven pre-existing) · security 329 passed / 2 skipped · live probe
33/33.

---

## UX / Full-Stack Hunt Round (2026-09-10, afternoon) — #086–#088 + instance hygiene

A dedicated end-user UX sweep: all 64 panes walked in a real browser at
desktop + mobile widths, first-run journey, core user journeys (kanban,
inbox, webhooks, settings), contrast sampling, focus order, command
palette, onboarding overlay, shortcuts overlay.

### #086 marketplace — install/uninstall updated the WRONG button
Featured strip and all-packs grid both rendered id="mkt-btn-<pack>" and the
handler resolved via getElementById (first match wins), so clicking Install
in the grid flipped the featured card's button and left the clicked one
saying "Install". Now data-pack-btn + update-every-card-for-that-pack.
4 guard tests.

### #087 touch targets + keyboard-revealed actions
156 webhook copy buttons at 8×15px, 156 delete buttons at 7px, 68+68 chat
sidebar buttons at 14–15px, obsidian/workspaces/a2a/workflow buttons at
6–13px — several of them destructive. All brought to ≥22px (mostly via the
established .icon-btn pattern); chat-history row actions were opacity:0
until hover, so keyboard users tabbed onto invisible buttons — focusin/
focusout now mirror the hover reveal.

### #088 the keyboard help lied
Backend feed documented "New agent (planned)" / "Run swarm (planned)" for
⌘⇧A/⌘⇧S while the keys were actually bound (undocumented) to Arena/Specs;
⌘/ had THREE document-level handlers that all fired per keypress (measured:
kanban → docs pane under a stacked modal, focus dropped); the ⌨️ button and
the ? key opened two different overlays. One overlay, one handler per key,
all real bindings documented (incl. the previously invisible ⌘⇧H/⌘⇧G), and
Sprint-16's bindings no longer fire while typing. 5 guard tests.

### Instance hygiene (the big one)
The live instance had ~24,000 rows of accumulated test residue from
repeated suite runs — 862 kanban cards, 169 webhooks, 279 MCP servers, 822
supervisor tasks, 6,400 audit entries, payload-named skills/templates —
plus a seed agent (brain) whose name and prompt had been overwritten by an
injection payload. All cleaned with the operator's genuine data preserved
(pre-09-09: 11 roadmap tasks, 12 seed agents, 3 chat sessions, seed
integrations). DB 59MB → 6.3MB.

The security suite now carries a three-layer pollution guard (autouse):
row-addition removal by rowid-set diff (with FTS pairing), full-content
restore for the small seed tables the suite can mutate in place, and a
session-final sweep for telemetry rows the server writes asynchronously
after a response. Verified: full suite green with ZERO table deltas and
byte-identical seed agents afterwards.

### Also
- Welcome notification version derives from backend/version.py (was a
  hardcoded "v6.0" four majors stale).
- Terminal tests skip honestly on a deliberately networked bind (the gate
  correctly fails closed there; the loopback recipe runs the assertions).
- Verified-clean: mobile layout (no overflow, ☰ nav, no tiny targets),
  onboarding flow, command palette (156 commands, filters + search), WCAG
  contrast (only accent-on-accent icon cases below 4.5:1, which pass the
  3:1 graphical-object rule), skip links + focus outlines, toasts are
  aria-live, first-run chat E2E with streaming.

**Suites at end of round:** frontend 319/319 · security 321 passed /
10 skipped (zero pollution) · live probes all green.

---

## Round 10 (2026-09-10, evening) — the test infrastructure was lying in both directions

### The unit suite failed 51 tests on a fresh environment — all flakes
`asyncio.get_event_loop().run_until_complete(...)` in 7 sync-test modules
raises "There is no current event loop" once ANY async test has run earlier
in the session (pytest-asyncio ≥ 1.0 closes and clears the MainThread loop).
Pure ordering: 246/246 green together, 48 failures in the full run. test_67
had already documented the exact fix in situ — applied to the other seven
modules (asyncio.run()). Suite: 4795 passed / 0 failed, fully green for the
first time under current tooling.

### The audit ratchet was permanently red (the opposite lie)
baseline.json was all zeros, but the audits had grown stricter and the app
had grown 16 panes since those zeros were recorded: touch-targets 200+,
console noise over budget, pane-health 1 on any non-loopback bind. A ratchet
that can never pass is as worthless as one that can never fail. Now:
- touch targets honestly baselined at 216 (the .btn 44×28 dense design —
  AA-compliant everywhere after bumping the last 22px controls to 24px);
  the ratchet enforces downward-only from truth.
- console-noise budget scales per pane (300 × panes walked) instead of a
  fixed 12,000 that organic pane growth trips every time.
- audit `visit()` waits for the app's own settle signal (aria-busy cleared,
  skeletons gone) — touch-target count was flapping 193–216 on identical
  builds; now stable.
- pane-health exempts the CSP refusal thrown as a pageerror by
  3d-force-graph's rare new Function() path (blocked by policy, graph fine).

### The audits polluted the operator's kanban
adversarial_input writes 9 hostile payloads through the real API;
print_and_multitab writes a marker task. Neither cleaned up: 91 junk rows
(XSS strings, AAAA, lorem) after one day of audit runs — the same disease
the security-suite guard fixed for tests. _harness now snapshots task IDs
before and sweeps what appeared after, through the real API. Verified: both
audits run green and leave the count unchanged. (Historical 91 rows deleted;
11 real tasks remain.)

### UX fixes found by journey-walking
- #089 a11y labeler OVERWROTE real labels: the runtime fallback
  (placeholder || title || id) never checked for an associated <label for>
  and an explicit aria-label overrides it — kanban's Priority/Assignee/
  Column selects announced as "kb-priority"/"kb-agent"/"kb-status". Now
  defers to native labels. Kanban per-column "+" buttons named.
- #090 webhooks "▶ Test" quick action was a designed button that never
  existed: ['▶ Test', ""] — the renderer's guard silently dropped the empty
  action. Now tests the most recently created webhook, or says "create one
  first". Guard test bans phantom entries.
- #091 four identical key-status fetches on every cold load (all 404s on a
  fresh install) collapsed to one via a shared de-duplicated helper with
  save/remove invalidation.

**Suites at end of round:** unit 4795/0 · security 328/3 (loopback: terminal
assertions live) · frontend 326/326 · audits green against the honest
baseline · DB clean after every suite.

---

## Round 11 (2026-09-10, night) — labels that labelled nothing, and error copy at the boundary

### #092 51 labels visually paired with controls but associated with nothing
Forms across 11 files pair a bare <label> with the following id'd control —
visually adjacent, no for=, so no assistive technology associates them, and
the runtime fallback announced placeholders or machine ids ("gcf-domain",
"Input field"). All 51 statically-id'd pairs now carry for= (mechanical
transform, guard test bans future bare labels before id'd controls); the
runtime fixer gained the missing middle case (bare sibling label before an
id-less dynamic row). MCP gateway: filter selects and per-rule bulk-select
checkboxes named.

### #093 MCP gateway condition fields ignored their toggles (real bug)
style="display:none;…;display:flex" — duplicate display, last wins — so the
time-window and day-picker condition groups rendered expanded with their
toggles unchecked. Verified fixed live: none → flex on check → none on
uncheck.

### #094 every browser audit silently skipped on a fresh environment
_CHROME_CANDIDATES pinned playwright's chromium-1148 path; current Playwright
installs chromium-1234/chrome-linux64. On any fresh environment the audits
SKIPped while a good Chromium sat one directory over. Now globs any
downloaded build. Found live: the fresh sandbox exposed it immediately.

### #095 160 raw error strings upgraded at the toast boundary
humanError() was opt-in; 17 files adopted it, ~25 files still toast
"Create failed: server error 500" / "runs.filter is not a function". The
upgrade moved to the one boundary all error toasts cross: toast() passes
'err' messages through humanizeRawError() — keeps the caller's lead
sentence, appends what the status means, demotes stack frames to
parentheses, passes human/custom messages through untouched.

### Also
- Touch-target baseline 216 → 217: the old number was measured against a
  stale dist missing 6 pane registrations (70 panes walk now, not 64).
- history-navigation audit: Back-restore wait was a fixed 1400ms sleep —
  flaked red under ratchet load (NO-RESTORE for a pane about to render);
  now waits for real content, bounded.
- DB residue: task 6's title had been destroyed by a Sept-9 edit-probe
  (renamed honestly, flagged in-description); probe task 11 deleted;
  goals live in goals_v2 (the conftest guard already covers it — zero
  pollution verified across the whole 126-table schema this round).

**Suites at end of round:** frontend 332/332 · all 19 ratchet audits green
against the honest baseline · DB clean.

---

## Round 12 (2026-09-11) — the Cancel button that meant "run it anyway"

### #096 the terminal pane rendered a healthy prompt over a dead backend
renderTerminal() swallowed the /api/terminal/env failure with catch(e){} —
tabs, quick commands, "Type a command", zero indication everything would
fail (the last SILENT finding in failure-honesty), and the auth gate's own
401 guidance never reached the screen. Now: 401/403 guidance verbatim,
other failures via humanError(), network failure named. failure-honesty 1→0.

### #097 Cancel meant "proceed with defaults" at 23 gmPrompt sites
`await gmPrompt(..., default) || default` turns a Cancel (null) into the
default: cancelling an eval run ran it anyway; cancelling a budget rule
created it scoped to '*' (ALL agents); cancelling the last prompt of a hook
edit PATCHed condition:null and WIPED the stored value; the goals check-in
note was asked for and then silently discarded; connectors/JIT-token had
dead null-checks (`|| ''` before the check) so cancel surfaced as
"Invalid JSON". 23 sites across 11 files now null-check before defaulting
(the pattern github push/template edit already used). Guard test bans any
gmPrompt call followed by `||` (balanced-paren scan) — including the
"safe because a later empty-check catches it" variant.

### Also this round
- Verified no unenforced audits (agent_reliability visibly skips without
  the fake provider; computed_style_diff is a migration tool, tested by
  test_106; module_risk is a generator with its own tests).
- Journeys walked green: settings (vault audit reports real facts), eval
  framework (create→run→results), workspaces (create→list→delete),
  specs (healthy empty state).
- Instance hygiene: 85 orphan hex-named workspace dirs deleted (DB had 1
  workspace; all 441 tracked files under plugin_sdk/specs/workflows
  restored intact after the first sweep over-reached — lesson: positive
  pattern match, not exclusion lists).

**Suites at end of round:** frontend 334/334 · security 321/10 (0.0.0.0
bind: honest terminal skips) · failure-honesty 0 · DB clean.

## Round 13 — arena journey (two live bugs)

### #098 — OPENROUTER_BASE_URL ignored; stream 401s silently rendered EMPTY
Arena battles against anything but the real OpenRouter endpoint produced
two blank panels and zero errors. Three routers bypassed the override:
arena `_run_model` hardcoded the full chat/completions URL, fusion and
imagegen hardcoded `OR_BASE = 'https://openrouter.ai/api/v1'`. Worse,
httpx `client.stream` does not raise on 401 — the SSE reader just saw no
data lines and emitted a clean 0-token "response", and the server log
had the real 401s all along. arena now uses `OPENROUTER_BASE` from
services.llm and raises on non-200 (failure becomes an error chunk the
user sees); fusion/imagegen import the same constant.

### #099 — workstation host re-render destroyed absorbed panes mid-use
Starting an arena battle inside the enterprise workstation worked for
~1.5s, then the host renderer's async `innerHTML` rebuild wiped every
absorbed pane moved into it; the MutationObserver recovery rebuilt the
workstation with EMPTY pane shells and re-rendered, so any transient
state (live battle, terminal scrollback, half-written form) was lost.
Probe evidence: the `#pane-arena` element itself was replaced at
t=1500ms. Fix: initWorkstation stashes each absorbed pane's element in
`window._wsPaneNodes` and re-attaches the ORIGINAL (detached-but-intact)
element after a host wipe instead of creating an empty shell; plus an
`_arenaBattleActive` lifecycle flag so the legitimate post-rebuild
re-render doesn't replace a battle in progress. Full journey green:
battle renders both sides, Cancel leaves unvoted, vote+reason records,
ELO leaderboard updates.

### #100 — eval picker: free-text where a select belongs (+ gmChoose)
"Run Eval Suite" made you TYPE an exact agent id (list shown as bullets
in the prompt body; typo -> error toast) and an exact suite_id from
memory. The shared gm dialog gained a select mode (`#gm-select`,
`_gm_show({select})`, `gmChoose()` helper, Enter commits, focus lands
on the select); eval agent + suite pickers now offer real choices —
suites listed live from the API with case counts, free-text fallback
only when the API is unreachable. Fixing `_gm_click` also killed a
latent leak: the old `inp.value || ta.value` chain let text left in
the hidden input by a PREVIOUS dialog win over an empty textarea.

### #101 — connectors: configure accepted non-object credentials
PATCH /configure stored any truthy `credentials` (string/list/number)
verbatim and flipped the connector to status='active' — a "configured"
connector that could never work, bricking every later execute inside
`{**db_creds, ...}`. Now 400s unless credentials/config are JSON
objects ({} still clears). Surveyed and left as documented internal
contracts: unknown-connector execute returns 200 {ok:false}
(execute_connector serves agents, not just HTTP); /test is a status
check; webhook targets are per-call payload.url by design.
tests/connectors/ is a legacy live-verification directory (real Notion
workspace, live server, no CSRF token) outside every gate — left in
place, removal needs owner approval.

### #102 — workspace import: non-object rows were a 500
The backup/restore journey passed end-to-end (export -> delete task ->
import -> task restored by upsert; hostile archives handled) except
one: `{'tasks': ['not','objects',42]}` crashed POST /api/workspace/
import with HTTP 500 — row.keys() on a string sat OUTSIDE the per-row
try that only wrapped the execute. Non-dict rows are now skipped;
regression test added to test_63.

### Mobile-width pass (green)
responsive audit 0 document overflow at phone/tablet/desktop across
all panes; touch targets 215 (baseline 217, ratchet enforces
downward); the new gmChoose/gmPrompt dialogs measured at 390×844 —
modal spans exactly the viewport, select is 44px tall, buttons above
the fold, tap+select works; workstation tab strip does not overflow.
Probe note: dismissing the first-run tour reliably requires
window.closeOnboardingModal() — hiding the overlay leaves the tour
alive and it re-asserts itself over the UI.

### #103 — addendum: the full-audit sweep on the 0.0.0.0 topology
Running all 22 audits against the preview topology (not just the four
checked during the mobile pass) surfaced five more findings, two of
them real app bugs:

- **skills pane swallowed load failures** (session-expiry: SILENT):
  !r.ok became {skills:[]} and the catch toasted "Loaded offline
  skills" in the success style — a dead backend was indistinguishable
  from having no skills. Now: error state with retry; empty state only
  on a successful empty fetch.
- **ensurePaneRendered wiped healthy hosts** (slow-network: STUCK):
  the failsafe's skeleton check swept HIDDEN absorbed tabs — a hidden
  Control Tower tab's 21 skeleton elements made it "rescue" a fully
  loaded workspaces host by resetting it to skeleton and refetching
  everything. And its 3s window raced every slow-but-successful load.
  Now: visible skeletons only, 8s window.
- Three audit detectors were loopback-biased or vocabulary-blind:
  pane-health and console-health counted the terminal's DESIGNED
  fail-closed 401/403 gate (surfaced honestly as a pane banner) as a
  console error on non-loopback binds; session-expiry's ACKNOWLEDGES
  regex didn't recognize the message the app renders verbatim from the
  server's own 401 body; slow-network's pending detector matched
  hidden absorbed-tab skeletons. All four fixed with documented,
  attribution-based exemptions or visibility filters — never wholesale
  suppression (a NON-terminal 401 still reports).

Also: tests/connectors/ (see #101) confirmed dead-as-run against a
CSRF-enforcing server — legacy live-verification scripts, not a gate.
Sandbox resets this round wiped pip/playwright/node_modules//tmp twice;
recovery recipe held (mock provider recreated from the session recipe).

## Round 14 — cancel-semantics sweep + picker migration, part two (cont.)

### #109 — same id pass-through in five more routers
plugins (the user-reachable one: pasted/URL-installed plugin JSON can
carry any id — install succeeded, every manage call after 404'd),
hooks, marketplace packs, observability traces/spans, and crdt docs
all stored client-supplied ids verbatim. All five now slugify to the
[a-z0-9_-] alphabet pluginsdk already used; agents keeps its explicit
400. New unit test proves install/json with id "my/plugin?x=1" is
stored as a slug, listed, and deletable. Verified the four other UIs
never send ids (API-only hardening).

Unit 4778/0/187 · vitest 335/335 · security 321/10 (live server up —
NOTE: the security suite requires the live server; run with the
server DOWN it fails ~325 tests environmentally).

### #108 — client-supplied agent ids passed through unsanitized
create_agent slugifies name-derived ids but stored a client-supplied
id verbatim — an id with '/', '?' or '#' is unaddressable by every
/api/agents/{id} route (and path-confusable), leaving an agent the
API can list but never edit or delete. Client ids are now rejected
unless they match the same [a-z0-9_-] alphabet the auto-slug uses.
The UI never sends an id (verified — the agent modal posts name/
model/provider/avatar/color/system_prompt only), so only direct API
callers are affected. Verified live: a/b, x?y, Upper → 400; a valid
slug is accepted and deletable. Workflow deep-flow journey same
round: create → run-input cancel (no run started) → delete all clean.

Unit 4777/0/187 (+2 new) · vitest 335/335 · security 321/10.

### #107 — double-encoded query strings made marketplace/leaderboard filters no-ops
A secondary-flows journey surfaced malformed URLs in the server access
log (`/api/marketplace?q%3D%26sort%3Dfeatured%26limit%3D48`): both
list views built params with URLSearchParams and then wrapped the
serialized string in encodeURIComponent. The server saw one giant 'q'
value and used defaults — so marketplace search, category, sort and
page size, and the leaderboard period/task filters, silently did
nothing while the UI claimed "N results". Verified after the fix: a
no-match search returns "0 results" with a clean URL; leaderboard
days=7 reaches the server. Same journey also confirmed prompt
version save/restore round-trips correctly, and noted one management
gap (no delete for eval suites — they accumulate; small future item,
no data risk).

vitest 335/335 · security 321/10.

### #106 — 25 mutating calls toasted success without reading the response
Same family as the load-path honesty work: a scan of all 338 mutating
fetches found 45 fire-and-forget calls, 25 of which toasted success
unconditionally — a 403/500 was reported as "✅ done" and local state
was updated to match the lie (vault key "removed", fork "created",
HITL decision "approved", alerts "resolved", …). All 25 now check the
response and toast the failure before touching local state; the
existing humanizeRawError toast filter renders the reason in the
standard human copy. Verified live by forcing 500/503 responses
through a fetch shim: error toast shown, success suppressed. The
remaining 20 unchecked calls are refresh-after-fire-and-forget
(no lying toast) or deliberate best-effort telemetry — left as is.

vitest 335/335 · security 321/10 · failure-honesty audit 0.

### Round 14 close-out — all gates green
Three units shipped (#104 pickers, #105 cancel sweep, url-safety
hardening), all pushed (`7999e87`). Close-out verification on the
rebuilt bundle, live server on 0.0.0.0:

- full 22-audit sweep: **all at 0** (touch-targets 215 ≤ 217)
- unit suite (server down): **4775 passed / 0 failed / 187 skipped** —
  identical to the round-13 baseline
- vitest 335/335 · security 321/10 (run per unit)
- every fixed flow verified live: cancel leaves no server-side record
  (specs, hooks, memories, integrations, packs, templates, caps,
  budget rules, entities, pipelines), pickers render their choices,
  full creates persist the chosen values

Also scanned this round and found clean: gmDanger guards (all 60+
destructive confirms check the result), URL interpolation (all ids
server-generated/sanitized except the one pack-export path fixed),
parseInt/parseFloat inputs (all have fallbacks).

### #105 — the cancel sweep found eight more act-on-Cancel flows
After #104, a systematic scan of ALL gmPrompt sites (does the value
get a null-check before it's used?) found the pattern's long tail —
eight flows where dismissing the dialog acted anyway, five of them
mutating, two of them RUNS:

- workflow run (cancel ran it with null input) and hook manual run
  (cancel RAN THE HOOK) — the worst two.
- spec create, plugin-SDK pack create, template create (four
  unguarded prompts in one flow!), Stripe wire (cancel generated the
  integration at the default price), galaxy memory add.

Plus five more fixed-choice fields migrated to gmChoose: rule-file
category, eval suite domain, eval case difficulty, connector auth
type, finops cap scope + period.

Empty input still passes where the field is optional — only Cancel
aborts. Every flow verified live server-side (record counts
unchanged after cancel). vitest 335/335 · security 321/10.

## Round 14 — picker migration, part two

### #104 — six more fixed-choice prompts typed free-hand
The gmChoose migration (#100) left its siblings behind. Six prompts
still made you TYPE a value from a fixed set, and three of them had NO
cancel check — dismissing the dialog proceeded with the default (the
cancel-semantics class from round 12, missed because the `||` sat on a
later line than the gmPrompt call, outside the guard test's scan):

- kg add-entity type + add-relation type: Cancel previously created
  the entity/relation anyway (`type || 'concept'`,
  `relation || 'RELATED_TO'`). Now pickers + null checks, verified
  server-side that cancel leaves no record.
- RAG new-pipeline chunk strategy: same fix.
- marketplace review rating: free text "1-5" with a validate-and-alert
  round trip → five-option star picker.
- control tower budget rule agent: "e.g. builder or * for all" free
  text (typo = rule that never matches) → picker over '*' + the LIVE
  agent list from app state; action stop/warn → two-way picker.

All six verified live (choices, defaults, cancel-aborts, full create
with the chosen agent/action persisted). vitest 335/335 · security
321/10.

**Suites at end of round (final):** full audit sweep on 0.0.0.0 — all
22 audits at 0 (touch-targets 215 <= 217 baseline) · frontend vitest
335/335 · security 321/10 (image-capable mock provider) · unit 4775
passed / 0 failed / 187 skipped without a live server (each browser
audit instead run directly against the live server, all <= baseline;
the earlier "4796" figure in this file counted audit subprocesses
differently — the ratchet assertions are identical).

## Round 15 (2026-09-12) — the model was being taught its own error messages

Chat/Studio pane journeys with a mock-provider harness (two fake
providers on 8790/8791, one with a FAIL-MARKER that force-fails every
non-image request, so failure paths could be exercised live in a real
browser).

### #110 — provider error prose was ingested into long-term memory
When Ollama streams an error mid-conversation, llm.py emitted a
terminal frame with the raw error text as delta and no `error` marker.
The chat pipeline treats a finished stream's text as assistant
knowledge: the memory-ingestion step filed "Ollama stream error: 500 …"
as a `memory` row (verified: 3 rows after repeated failures), and the
next conversation's RAG context could retrieve the error as if it were
something the assistant had said. The terminal frame now carries
`"error": "ollama_stream_error"` (delta kept for display), and the
Studio AI-edit guard, formatter and test-generator gates all treat
`error` frames like stubs — refuse to buffer them as product, say so in
chat instead. Verified live: failure probe → guidance rendered, 0 new
memory rows, transcript still logged, both providers' happy paths still
stream. llm.py + testgen.py + 01-app-core.js.

### #111 — /clear's confirmation shipped to the model as conversation history
/clear streams "✅ Cleared N messages…" as an assistant reply, then
wipes the transcript (action: clear_history). clearChatHistory()
emptied S.chatHistory mid-stream, but sendChat's post-stream
bookkeeping pushed the confirmation onto the fresh history — so the
NEXT message sent the phantom prior turn "✅ Cleared 2 messages from
this conversation." as history to the provider (captured in the actual
/api/chat POST payload). sendChat now skips the assistant push when the
clear action was seen in the stream. Verified live: S.chatHistory ===
[] after /clear and the next send's history field is []; visible UX
unchanged (the confirmation bubble was already wiped by the clear
action itself; the toast remains).

### #112 — the Replay pane had nothing to replay
The Replay pane's whole feature set — timeline scrubbing, frame
inspection, run diff, re-run from here — only worked for runs made via
the API-only /api/replay/workflow/{id}/run endpoint, which no frontend
code calls. Runs launched from the Workflow pane went through
/api/workflow/{id}/run: a workflow_runs row was persisted (FIX 6) but
with no frames, total_ms=0 and node_count=0 (verified live), so every
real run showed an empty timeline in the pane whose own empty state
says "Run a workflow first". run_workflow now records through
replay.py's writers (_create_run/_record_frame/_finish_run — one frame
schema for both entry points): a 'running' row before the first node so
interrupted runs stay auditable, node_start+node_output frames per node
(failed nodes record their error), and real duration/node counts at
completion. Recording is best-effort and guarded — a DB hiccup can't
abort a live run — and the SSE stream is byte-identical to before.
Verified live: 3-node workflow → 6 frames; pane renders the timeline on
click; diff of two runs shows the input difference; rerun-from streams;
a run with failing agent nodes records status='failed' with the
provider error in its frames.

Journeyed clean this round (no defects): HITL queue (high-risk queues,
low-risk auto-approves AND is recorded, unrecognized risk level fails
towards 'high', pane approve/reject, audit rows for both, unknown id
404), Image Generator (mock image round-trip incl. save-to-gallery,
path-traversal delete rejected, gallery delete removes the file, 404
for missing), slash commands (/help /models /goal /memory /clear),
Studio AI-edit (happy diff overlay + Accept & Apply; both-providers
failure → plain chat text with the honest fallback chain, no overlay,
editor untouched), Regenerate/Fork/Stop.

Suites at round close: unit 4774/166 skipped (test_120_audit_ratchet
excluded, server down) · vitest 335/335 · security 328/3 skipped —
live-server recipe per tests/security/conftest.py: AGENTIC_OS_HOST=
127.0.0.1 RATE_LIMIT_MAX=100000 (with the plain 0.0.0.0 recipe the
per-IP rate limit saturates mid-run and ~27 tests cascade-fail
environmentally; the conftest documents this).

Commits: abe58e1 (#110), 294d83a (#111), 93ca33c (#112).

## Round 16 — Unit 2: CollabEdit (fixed in this round, uncommitted→this commit)

### #114 — the busy guard disabled the collaborative editor while you typed in it
The delegated-action busy guard (00-delegate.js) set a real `disabled`
attribute on the clicked control while an action ran. Controls that
happen to be form fields — #ce-editor (a textarea), chat inputs, gm
inputs — were being disabled by the very act of interacting with them:
clicking into the collab editor gave it `disabled`, the browser dropped
focus to <body>, and every keystroke went nowhere. Typing "worked" only
in elements that aren't form controls. markBusy/clearBusy now skip the
real `disabled` for INPUT/TEXTAREA/SELECT/OPTION/OPTGROUP (a
NEVER_DISABLE pattern + busyDisables() helper); the data-act-busy
attribute alone still blocks double-dispatch, and the aria-busy string
is unchanged so the a11y tests (unit_122, e2e_browser_03) keep their
signal. Verified live: click into #ce-editor keeps activeElement on it
and keyboard input lands.

### #115 — debounce shipped only the LAST keystroke, so typing never persisted
ceHandleInput's 80ms debounce replaced the pending op on every
keystroke: a 14-keystroke burst produced ONE op — computed against the
client's final buffer, while the server still had the ORIGINAL content.
The server's _validate_op correctly rejected the mismatched op
("refers to 13 characters but the document has 0") and the client just
dropped the error, so NOTHING from a typing burst ever reached the
document — the server doc stayed empty at revision 0 while the editor
showed the typed text (silent divergence; a reload lost the work).
_cePendingOps existed but was never wired in. Each op is now pushed to
the queue and the whole batch is flushed in order after 80ms of quiet
(kept queued if the socket isn't open yet). Verified live: 14 ops → 14
acks, server content+revision exact; journey typing round-trips at
revision 27.

### #116 — every cold boot landed on Settings (and stomped early navigation)
setupSettingsWorkstation() restores the saved settings tab on EVERY
boot by calling switchSettingsTab(), which unconditionally did
history.replaceState('#/settings/<tab>') — rewriting the URL hash before
the deep-link router's 100ms timer read it. The router then treated the
app's own hash write as a user deep link and navigated to Settings:
verified live, a returning user (onboarded, currentPane=chat) opened
the app and got the Settings pane every single load, and any navigation
performed in the first ~2s of a page load (e.g. a second tab opening a
collab doc) could be silently overridden by the late boot nav. The
rewrite is now gated on Settings actually being the active pane, so
tab URLs still update while the user is in Settings, real deep links
(#/settings/security) still work, and cold boots land where the user
expectes (chat / last pane).

### #117 — one peer closing their tab killed the OTHER user's editor socket
CrdtDoc.broadcast() tried to clean up dead peers but its except tuple
(KeyError, TypeError, ValueError, ...) doesn't include
WebSocketDisconnect/ClientDisconnected — the exceptions a dead socket
actually raises. A peer disconnecting mid-broadcast let the exception
escape into the SENDING peer's collab_ws handler, tearing down their
connection too (ASGI traceback in the server log; the surviving user's
editor showed a disconnect blip until the client auto-reconnected).
Now any send failure marks that peer dead and broadcast continues to
everyone else. Verified live: hard-close one editor tab mid-typing in
the other — sender stays Live (badge, revision, content all correct)
and the log is clean.

Journeyed clean this unit: full two-tab CollabEdit journey — doc list
renders, doc create+open, WS status Live, typing persists (rev 27),
tab two sees the same content, tab one receives tab two's edit live,
undo, snapshot, delete, no page errors. e2e_browser_03's two nav tests
hardened from fixed 600ms sleeps to wait_for_function after one
environmental flake (both pass, full file 2× since).

Suites at unit close: unit 4774/166 skipped (test_120_audit_ratchet
excluded, server down) · vitest 335/335 · security 328/3 skipped
(live-server recipe per tests/security/conftest.py) ·
e2e_browser_03 20 passed/1 skipped ×2 full runs.

Commits: (this commit) #114, #115, #116, #117.

## Round 16 — Unit 3: composer sub-surfaces + dashboard timer

### #118 — branch snapshot "share with clients" URL was hardcoded localhost
The gmAlert after creating a branch preview told the user to share
`http://localhost:8787/preview/branches/<name>/` — a dead link for every
client not sitting at the server's own machine (LAN IP, proxied host,
tunnel: all broken). The frontend now shows `location.origin + url`
(the URL the user is actually browsing), and the API's `share_url`
field is likewise built from the request's own base URL instead of a
hardcoded literal. Verified live: alert shows 127.0.0.1:8787 when
browsed there (and would show any real host).

### #119 — the branch list kept ghost rows under its empty/loading states
stateFeedback's setEmpty/setError/setLoading only remove their own
.data-state nodes, never rows a previous load rendered. After deleting
the last snapshot, the deleted row stayed on screen ABOVE the "No
snapshots yet" empty state (verified live), and a pane re-visit stacked
"Loading…" under the existing list. loadBranchPreviews now clears the
container before injecting a state. Verified live: delete-last → clean
empty state, no ghost row.

### #120 — dashboard "auto-refresh" guard was dead code — it polled forever
The 30s auto-refresh only re-rendered when
`dash-body.closest('[style*="display:none"]')` matched — but panes are
hidden by the .pane/.pane.active CSS classes, never inline styles, so
the guard could not ever match. One visit to the dashboard meant a
/analytics/dashboard fetch every 30s for the rest of the session,
hidden or not. The check is now offsetParent-based (null exactly when
an ancestor is display:none). Verified live: 1 fetch on visit, ZERO
fetches across 70s hidden, refresh resumes on return.

### #121 — one failed dashboard fetch permanently killed auto-refresh
The !r.ok branch `return`ed past the timer re-arm, so a single failed
fetch silently stopped the promised 30s auto-refresh and the pane sat
on a stale error forever. The re-arm now lives in `finally`, so every
path (success, HTTP error, network error) keeps the chain alive while
the pane is visible.

Journeyed clean this unit: composer sub-surfaces 14/14 — screenshot→code
live round-trip (upload → convert → honest success → preview file
replaced → jump to studio), branch snapshot create via gmPrompt, share
URL uses real origin, snapshot URL serves frozen content, live project
changes while snapshot keeps old content, delete removes snapshot 404 +
clean empty state, no page errors. (The mock providers gained an s2c
branch that answers 'Recreate this design' with a full HTML doc, and a
composer <PLAN>/<FILE> branch, so these paths stay journeyable.)

Environment note: the sandbox reset mid-unit (wiped /tmp, pip, npm,
processes). Restored per the recovery recipe: requirements + test reqs,
playwright + chromium system deps, npm install, mocks rebuilt, servers
restarted. Repo and uncommitted fixes were unaffected.

Suites at unit close: vitest 335/335 · unit 4774/166 skipped ×3
consecutive clean runs (the first run after env restore had 4
environmental flakes — cold caches; three full re-runs clean) ·
security 328/3 skipped · e2e_browser_03 20 passed/1 skipped in 7 of 8
runs (one intermittent single-test flake whose name was never captured
— every immediate re-run passed; the two nav tests were already
hardened to wait_for_function earlier in the round).

Commits: (this commit) #118, #119, #120, #121.

## Round 16 — Unit 4: ambient agent + obsidian vault

### #122 — every ambient re-scan duplicated its findings, and dismissals resurrected
ambient_scan INSERTed each finding unconditionally: three scans a minute
apart left three identical rows per TODO (measured 5 → 10 → 15 → 20), and
a DISMISSED suggestion came back as a fresh active row on the next scan —
dismissing anything was pointless. (Within a 10s window the app's fetch
idempotency key masked this, which is why a quick double-click looked
fine while real re-scans duplicated.) The save loop now skips findings
already recorded — regardless of dismissed state — so repeated scans are
stable and a dismissal sticks. The scan toast now honestly reports
"N findings · M new". Verified live: scan → 1 row; re-scan after the
idempotency window → still 1 row (per-finding and per-agent); dismiss +
re-scan → no resurrection.

### #123 — one failed endpoint crashed the whole ambient pane render
renderAmbient fetched suggestions/tasks with `r.ok ? r.json() : null` and
then read `suggs.suggestions` — a single non-OK response (proxy 502 with
an HTML body, a DB error) handed null straight into the property access
and threw "Cannot read properties of null", leaving the pane broken
instead of showing an error. The fetches now fall back to empty shapes
while keeping the failure signal, and the pane renders a retryable
errorElement banner ("Couldn't reach the ambient agent") instead of a
false "no suggestions yet". Verified live with a monkey-patched 502:
no crash, error state + Retry button rendered.

### #124 — failed background tasks reported as done
_execute_background_task treated llm.complete's graceful failure shape
(ok=False, human-readable error in text) as success: a task whose
provider call failed got status 'done' and a ✅ in the list, with the LLM
error text as its "result" (verified live against a failing provider).
ok=False now maps to status 'failed' — the pane shows ❌ — while the
message is kept as the result so the reason is still visible.

### #125 — quick notes were HTML-escaped into the markdown file
saveQuickNote ran escHtml() over the title AND body before writing the
.md: a note "Tom & Jerry <3" was permanently stored as
"Tom &amp; Jerry &lt;3" on disk. Notes are now stored as-typed;
escaping stays where it belongs, in viewNote's display path. Verified
live: save a note full of &/</quotes, read the file back raw — content
and title unescaped.

### #126 — no note could ever be deleted from the Obsidian pane
The list/read APIs return vault-relative paths ('agentic-os/x.md'), and
the pane's Delete buttons send that path back — but delete_note joined
it onto the NOTES dir, producing 'agentic-os/agentic-os/x.md' and a 404
for every note the app itself created. The server log showed every
DELETE /api/obsidian/note in history returning 404. delete_note now
accepts the vault-relative form too (resolved against the vault root,
with the same containment check still the authority); vault-root paths
outside agentic-os and traversal paths remain refused (verified live:
403/404 both still enforced, UI delete now works end-to-end).

Journeyed clean this unit: ambient 9/9 (scan finds planted TODO, re-scan
>10s no dup, dismiss no resurrection, endpoint-failure error state,
FAIL-MARKER task → failed ❌, happy task → done with result, no page
errors); obsidian (pane renders, quick-note save round-trip unescaped,
view overlay on top with content, delete via gmDanger, daily note,
search no-match, index counts, export, security refusals). Probe-artifact
false alarms during verification (overlay looked unstyled/truncated and
delete looked hung) were traced to attribute-selector normalization
('z-index: 9999' with spaces), a 60-char dump slice, and awaiting a
modal-opening promise inside evaluate — the app was right; the probes
were wrong.

Note: brain/agentic-os runtime files (old exports/dailies) are tracked
in git; cleanup restored them after a probe over-deleted.

Suites at unit close: vitest 335/335 · unit 4774/166 skipped ·
security 328/3 skipped · e2e_browser_03 20 passed/1 skipped.

Commits: (this commit) #122, #123, #124, #125, #126.

### #127 — every project-health GET wrote a snapshot; the history was render noise
GET /api/ambient/health unconditionally INSERTed a health_snapshots row on
every call — and the bugbot pane's render fetches it (twice, a second
apart). A month of ordinary use had accumulated 336 rows, nearly all
byte-identical, so the "history" was a log of pane renders, not of
changes. A snapshot is now written only when the six scores differ from
the most recent row; the history becomes a timeline of actual changes.
Verified live: 3 direct GETs + 2 bugbot pane renders → zero new rows
(unchanged scores). Existing rows left untouched.

Suites: unit 4774/166sk · security 328/3sk · e2e_browser_03 20/1sk
(vitest unaffected — backend-only change; green at unit 4).

Round 16 closed: #113–#127 shipped across five units
(0cd0cd2, 321c528, 9475c2d, ccbbcc9, aaf922d, and this commit).
