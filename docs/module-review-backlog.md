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
