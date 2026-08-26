# The Van Clief Blueprint for this Agentic OS

Research findings from Jake Van Clief's public work (YouTube **@JEVanClief**, Skool
**skool.com/cliefnotes**, the ICM paper arXiv:2603.16021, and the two reference
repos `RinDig/Interpretable-Context-Methodology` and `RinDig/icm-architect`),
mapped against what this platform implements today, with the gap list and the
proposed build.

**This document is the coordination surface for the work.** Section 3 is the
live gap register: every gap carries a status and, when shipped, the commit
that closed it. Update it in the same commit that changes the status — a
tracker edited later is a tracker that drifts.

**Progress: 12 of 12 gaps closed.** Every gap in the register is shipped, and
P1–P10 of the build plan are complete. Further work is new scope, not backlog.

---

## 1. What Jake actually teaches (the canon, distilled)

### 1.1 The one-line thesis
> Stop building smarter agents. Build smarter folder structures. The folder *is*
> the app; the filesystem is the orchestrator.

Stage sequencing is folder numbering. Context scoping is folder hierarchy. State
management is files on disk. Coordination is one folder's `output/` being the
next folder's input. The filesystem does the work a framework would do in code.

### 1.2 Five design principles
| # | Principle | Borrowed from |
|---|---|---|
| 1 | **One stage, one job** — a stage that researches does not also write | Unix / Parnas |
| 2 | **Plain text is the interface** — markdown + JSON, no binary, no DB in the loop | Kernighan & Pike |
| 3 | **Layered context loading** — load only what this stage needs; prevention, not compression | ICM |
| 4 | **Every output is an edit surface** — a human can open, edit, save between stages | Horvitz / Shneiderman |
| 5 | **Configure the factory, not the product** — set up once, every run reuses it | Continuous delivery |

### 1.3 The five-layer hierarchy (the load protocol)
| Layer | File | Question | Role | Budget |
|---|---|---|---|---|
| L0 | `CLAUDE.md` / `AGENTS.md` / `IDENTITY.md` | Where am I? | routing | 300–800 tok |
| L1 | root `CONTEXT.md` | Where do I go? | routing | 200–500 tok |
| L2 | stage `CONTEXT.md` | What do I do? | **the control point** | 200–500 tok |
| L3 | `references/`, `_shared/`, `_config/` | What rules apply? | factory (stable) | 500–2k tok |
| L4 | `output/`, run artifacts | What am I working with? | product (per-run) | varies |

Target working set per stage: **2,000–8,000 tokens**. The monolithic equivalent
runs 30k–50k. ICM never loads those tokens rather than compressing them later.

### 1.4 The six forms (from `icm-architect`)
Selection question: **what is the repeating unit of work?**

| Unit | Form | Shape |
|---|---|---|
| a run (same stages, new deliverable) | **Pipeline** | `stages/01_.. 02_..`, `_shared/`, `setup/questionnaire.md` |
| several kinds of run, one identity | **Umbrella** | root map + N self-contained pipelines + shared factory layers |
| a record that accumulates | **Record library** | `_index/log.md`, `_templates/record-template/`, `records/<slug>/` |
| the knowledge itself | **Knowledge bundle** | `corpus/` + `extraction/` (factory) + `bundle/` layered A/B/C with typed YAML frontmatter and `access_tier` |
| an organization as a graph | **Context map** | node cards with `type:`, generated `FILE-MAP.md`, `_meta/schema.md`, `dashboards/` |
| a folder later agents must edit | **System map** | nouns / movements / change-impact index cards over a repo |

Forms compose and recurse. A record can internally be a pipeline; a pipeline can
sit under an umbrella.

### 1.5 The invariants that keep it alive
- **The catalog holds no books.** Routing files point; they never store payload.
- **One home per fact; a link beats a copy.** Duplication is how structures rot.
- **Generated indexes are never hand-edited.** Script the file map or it drifts.
- **The structure is the documentation.** Explanation lives in that folder's `CONTEXT.md`.
- **Method and instance live apart.** Extract the blank template before it tangles with data.
- **Working sessions end in artifacts**, not vibes.
- **One-way references.** If A points at B, B does not point at A.
- **Docs over outputs.** Agents learn conventions from L3 reference docs, never
  from previous outputs — early outputs are the worst outputs.
- **Underscore prefix = about the workspace, not of the work** (`_meta/`, `_shared/`).
- **Stage folders `NN_kebab-name`.**

### 1.6 The walk test (the acceptance criterion)
An agent **with no memory** must open the root, find its way, act, and report
status from the files alone. If it can't, the structure is wrong — not the agent.

### 1.7 The newest material (2026, past the paper)
These are the things Jake has said *since* the paper, and they are the most
valuable part of this research because they are the known failure modes:

1. **"The agent has to actually start in the right folder."** The #1 practical
   failure of ICM at scale. As folders multiply, the model scans economically,
   thinks it knows enough, and skips guidelines. Starting central = layered
   context never loads. Starting in the right place = instantly grounded.
   In a team, "just `cd` to the right directory" is exactly the invisible,
   error-prone step that breaks repeatability.
2. **Three layers of working with AI:** L1 chat/copy-paste → L2 skills & refined
   prompts → L3 folders and one agent. Most people automate L1/L2 — the wrong
   layer.
3. **Dialogue is the source of every workflow.** Structure should be *extracted*
   from how you already talk about your work, not designed up front. (Jake's
   cofounder's tool pulls goals, constraints and decisions out of any chat.)
4. **Skills are ICM in miniature** — plain-text scripts and processes an agent
   navigates; markdown that can embed Python for determinism.
5. **Reported effect:** 20–40% token reduction, faster outcomes, no infra.
6. **The MCP tool-count wall** (community, verbatim problem): one gateway in
   front of many MCP servers means the agent sees every tool at once and past a
   certain count *picks worse, not better*. Hand-written per-task tool maps rot.
   Load tools lazily by intent. — This is exactly gap **#8** already on our list.
7. **"Obsidian is bloat."** Moving from a static knowledge base to an active
   agentic workflow, the folder system itself becomes both the agent
   architecture *and* the user interface. No specialized app required.
8. **Cloud direction (Eduba):** upload your ICM folders, one strong model with a
   good harness reads the map and becomes the agent you need; each workspace in
   its own container that renders markdown, edits files, installs packages, runs
   Python and Playwright, multi-player in real time. This is, almost exactly,
   the product this platform should be.
9. **System map form (Aug 2026):** walk a repo and write index-card pages —
   what the pieces are in *your* words vs the code's words, what is real vs
   leftover vs fake, and "if you change X, what else moves." Not a 40-page audit.

---

## 2. What this platform already has

| Canon element | Here | Where |
|---|---|---|
| L0/L1/L2/L3/L4 layering | ✅ | `backend/services/icm.py` |
| Stage contracts, Inputs/Process/Outputs parsing | ✅ | `parse_contract()` |
| Layered context assembly with token accounting | ✅ | `assemble_context()` |
| Walk-test validation | ✅ | `validate()` |
| Scaffolding | ⚠️ pipeline only | `scaffold()` |
| Ontology / shared vocabulary | ✅ (beyond canon) | `services/ontology.py` |
| Agent-memory knowledge base, ICM-layered | ✅ | `docs/agent-memory/` |
| Hooks/event automation | ✅ | `routers/hooks.py` |
| Skills | ⚠️ registry JSON, not `SKILL.md` folders | `routers/skills.py`, `skills/skills.json` |
| Scheduler / loops | ✅ | `services/scheduler.py`, `routers/loops.py` |
| MCP gateway | ✅ | `routers/mcp_gateway.py` |
| UI for ICM | ⚠️ one tab inside Information Hierarchy | `frontend/index.html` `#h-view-icm` |

## 3. Gap register (live)

Legend: ✅ shipped · 🟡 partial · ⬜ open · 🚧 claimed, work in flight

**Claiming protocol:** before starting a gap, set its status to 🚧 and push
that single commit first. G6 was built twice simultaneously because nothing
announced the work; this is the mechanism that prevents a repeat.

**A numbering correction, stated plainly:** several commit messages and
progress summaries referred to the intent-scoped MCP work as "G7". In this
register that is **G8**; G7 is typed frontmatter. This table is authoritative.

| # | Gap | Severity | Status | Closed by |
|---|---|---|---|---|
| **G1** | **Only one form.** `scaffold()` always builds a Pipeline. No umbrella, record library, knowledge bundle, context map, system map. | High | ✅ | `88c8035` |
| **G2** | **No "start in the right folder" router.** Nothing decides *where* a request enters. This is Jake's named #1 failure mode and we have it wholesale. | **Critical** | ✅ | `9d7c896` |
| **G3** | **No restructure mode.** Cannot point at an existing repo/vault, classify every file (catalog/contract/factory/product/dead), propose a migration map, migrate, validate. | High | ✅ | `09a6030` |
| **G4** | **No dialogue→structure extraction.** No path from "describe your work in chat" to a scaffolded workspace. Jake's core onboarding move. | High | ✅ | `a673a2e` |
| **G5** | **No generated FILE-MAP.** Indexes would be hand-maintained, i.e. guaranteed to drift. | Medium | ✅ | `88c8035` + `820c53a` |
| **G6** | **Skills aren't ICM.** `skills.json` registry instead of `SKILL.md` folders with progressive disclosure. | Medium | ✅ | `9e60e38` + `0bc8ffd` |
| **G7** | **No typed frontmatter / queryable layer.** Knowledge-bundle and context-map forms need `type:`, `layer:`, `access_tier:`, `strength:` and dashboards querying them. | Medium | ✅ | `88c8035` + `820c53a` |
| **G8** | **MCP tools not lazily scoped by intent** (already tracked as gap #8). | High | ✅ | `dd1b7a1` |
| **G9** | **Workspaces aren't the home screen.** ICM is a tab inside a pane; in the canon the folder *is* the interface. | High | ✅ | `9d7c896` |
| **G10** | **No life/computer/phone automation surface** — no ambient capture inbox, no phone entry point wired to workspaces. | Medium | ✅ | `804eabb` |
| **G11** | **Walk test isn't enforced as a gate**, only reported. | Low | ✅ | `edc7e69` |
| **G12** | **No template/method library.** "Method and instance live apart" — we have no blank, reusable, shareable workspace templates. | Medium | ✅ | `47fde43` |

---

## 4. The build

Ten pieces. Each follows the same bar: verified live against a running server,
every real bug given a test proven to fail first, revert-proved break by break,
full suite green before commit.

**Shipped:** P1 `9d7c896` · P2 `88c8035` · P3 `09a6030` · P4 `a673a2e` ·
P6 `9e60e38` · P7 `dd1b7a1` · P8 `9d7c896` · P9 `804eabb`
**Partial:** P5 — the generated FILE-MAP exists for context maps, not all forms
**Open:** none — P1–P10 all shipped

### P1 — The Router (fixes G2, the critical one)
A **root context map** for the whole OS: `brain/CONTEXT.md` listing every
workspace with a one-line "what enters here." Every chat turn, every hook, every
scheduled loop resolves through it before any work happens. The agent literally
cannot start in the wrong folder because the entry decision is a logged,
inspectable step: *request → matched route → workspace → stage → loaded files →
token count.* Ambiguity opens a two-option chip instead of guessing.

### P2 — Six forms in `scaffold()` (G1)
Port the `icm-architect` form catalog: pipeline, umbrella, record library,
knowledge bundle, context map, system map — with the selection question
("what is the repeating unit of work?") as the first onboarding prompt.

### P3 — Restructure mode (G3)
Point at any folder or GitHub repo → classify each file (catalog / contract /
factory / product / dead) → render a migration map → **wait for approval** →
migrate → re-run the walk test. Uses the existing HITL approval gate.

### P4 — Dialogue → workspace (G4)
"Describe your work" in the Chat pane. Extract stages, human gates, and what's
stable vs per-run. Propose a form. Scaffold. This is the single highest-leverage
UX move for a novice and it is Jake's actual onboarding.

### P5 — Generated FILE-MAP + dashboards (G5, G7)
A script (not a human) rebuilds `FILE-MAP.md` from YAML frontmatter on every
write, plus dashboard views that query frontmatter (`ai-level`, `value`, `pain`,
`status`) so "what should I automate next" is a live answer, not an opinion.

### P6 — Skills as `SKILL.md` folders (G6)
Migrate to three-level progressive disclosure (frontmatter ~30–100 tok / body
<5k / bundled files ~0), with the existing safety scanner on the import path.
Markdown that can call Python for determinism, as Jake demos.

### P7 — Intent-scoped MCP tool loading (G8)
Tag every tool, expose a searchable catalog, load lazily by intent, cap the live
tool set. Retires the hand-written map before it becomes its own maintenance job.

### P8 — Workspace-first shell (G9)
The folder becomes the interface: a real file tree, markdown rendered and
editable in place, stage status derived from `stages/*/output/`, one-click
"run this stage." Every output an edit surface, as the canon requires.

### P9 — Capture inbox + automation surface (G10)
`inbox/` for anything from anywhere (phone share sheet, email, hook, voice),
swept on a schedule into the right workspace by the P1 router. This is the
"automate my life/computer/work/phone" ask, done the ICM way.

### P10 — Template library (G12)
Blank, shareable workspace templates separate from instances; export/import as a
folder or zip. Ships with a starter set: software project, content pipeline,
client records, personal second brain, home/life ops.

---

## 5. Sources
- ICM paper — *Interpretable Context Methodology: Folder Structure as Agent Architecture*, Van Clief & McDermott, arXiv:2603.16021
- `github.com/RinDig/Interpretable-Context-Methodology` — README, `_core/CONVENTIONS.md` (15 patterns)
- `github.com/RinDig/icm-architect` — `SKILL.md`, `references/core.md`, `references/forms.md`, `references/system-map.md`
- YouTube @JEVanClief — *You're Automating The Wrong Layer* (three layers, dialogue-as-source, skills connection); *Stop Building AI Agents. Use This Folder System Instead.*
- skool.com/cliefnotes — *Folders, not frameworks: how Taurus makes Claude repeatable for a whole team* (start-in-the-right-folder), *Obsidian is BLOAT*, the MCP tool-count thread, System map announcement
- LinkedIn / Eduba platform announcement (containerised multiplayer ICM workspaces)

---

## 6. Delivery log

Newest first. Each entry names what was actually **wrong**, because the defect
is the durable part — the fix is obvious once the defect is stated.

| Commit | Gap | What was wrong |
|---|---|---|
| `820c53a` | G5, G7 | Five of six forms generated no index at all, so an agent had to crawl the tree — the thing the catalog exists to prevent. And the frontmatter was being **written and never read**: the context map shipped a `dashboards/00-tracker.md` containing a prose description of a query ("Sort process nodes by value desc, then pain desc, where ai-level is L0 or L1") with nothing that ran it — a dashboard that cannot answer its own question, which looks like a working feature. One shared reader now generates the map for every form and executes the queries, with `access_tier` enforced on every path that returns nodes. |
| `edc7e69` | G11 | The walk test was a report nothing read. Measured live: delete one stage contract and `/validate` said `ok: False` while the router returned `matched`, chat returned 200, and the route log recorded `matched, 214 tokens` — the agent was handed a context with no stage contract and every surface looked normal. The check now gates the READ path (assembly refuses, the log says `blocked-walk-test`, tokens 0) and never the write path, because editing is how a broken workspace gets repaired. Every refusal carries the specific repair. |
| `47fde43` | G12 | No way to reuse a proven structure: every new workspace started blank or was copied by hand, so method and instance stayed tangled. Extraction now keeps L0–L3 and drops L4 — which is not a judgement call, it is the factory/product split the runtime already enforces. A template carries the contracts and reference material and **no run data**, so one can be shared without leaking client work. Five starters seeded; instantiation is a folder copy, not a schema render. |
| `804eabb` | G10 | Nothing from a phone could reach the platform: the PWA manifest declared no `share_target`, so the OS never offered the app in a share sheet. And there was no inbox — the four obvious integrations (phone, email, hooks, terminal) would each have been a separate routing path that drifts. Now one folder and one sweep: capture writes a file and does **nothing else**, so it cannot fail because routing failed; the sweep routes later, is re-runnable, and leaves anything it cannot confidently place in the inbox rather than filing it somewhere plausible and silent. |
| `0bc8ffd` | G6 | Follow-up to `9e60e38`. Its level-1 catalogue went through `read_skill()`, so building a listing read **every body in full off disk**: a skill with a 160KB body cost 160,043 bytes of I/O to show a name and a description. The token accounting was honest; the disk read was not. Now a bounded 2KB head per skill — measured 160,043 bytes → 0. |
| `9e60e38` | G6 | 83 skills in one JSON blob; discovery returned all of them in full. Three-level disclosure, both stores merged on read, folder form winning an id clash. *(Built in parallel with an independent implementation of the same gap — see the note below.)* |
| `dd1b7a1` | G8 | The gateway federated 53 tools **no agent could reach**, while the agent loop inlined its own 23 into every prompt regardless of task. Connecting them naively would have put 76 tools in front of the model — the exact "past a certain count it picks worse" wall. Now one catalog, tags derived per tool, capped at 12 by intent. |
| `88c8035` | G1, G5, G7 | `scaffold()` built a Pipeline and only a Pipeline, so a record library got numbered stages for something with no stages. Harder half: `validate()` treated "no numbered stages" as an **error**, so every correctly-built non-pipeline form failed its own walk test. |
| `a673a2e` | G4 | No path from plain English to a workspace. Extraction is rule-based on purpose: it must work with no API key on first run, and every stage must cite the phrase that produced it. |
| `09a6030` | G3 | No way to point at an existing folder. Migration is gated: reads never touch the tree, apply refuses without explicit approval, files are **copied** not moved, nothing is ever deleted. |
| `9d7c896` | G2, G9 | Entry selection was a bare substring test: workspace `os` matched *"what is the **cost** of this?"* and loaded an unrelated project's context into the system prompt. Silent, and confidently wrong. |

### A note on parallel work

G6 was implemented twice, independently and simultaneously, by two sessions.
`9e60e38` reached the remote first and is the surviving implementation; the
other was discarded rather than force-merged. Both had found the same shape
(three levels, non-destructive migration, containment on bundled reads), and
each had one thing the other lacked — the surviving one merges both stores on
read, the discarded one bounded the level-1 disk read. The bound was ported
across as a follow-up rather than lost. **Never force-push to resolve this.**

### Recurring defect shapes in this work

Worth naming, because they recurred across every commit above:

1. **A guard that cannot fire.** Four unreachable lines so far (the router's
   short-id filter, `get_route_log`'s int coercion, `tags_for`'s namespace
   split, and an earlier sanitise-then-accept). All found by revert proof, all
   deleted rather than kept.
2. **A rule applied to the wrong scope.** Pipeline logic applied to every form,
   twice: the stage-count guardrail and the walk test.
3. **Cheap on the wire, expensive on disk.** The skills catalogue reported an
   honest token saving while reading every byte it claimed to avoid. A
   measurement of the *output* cannot detect this; only counting the read can.
4. **Diagnostics discarded on the error path.** The tool selection vanished
   when the model was unreachable — exactly when it was needed.
5. **A probe disagreeing with the app, and the probe being wrong.** Five times
   (`meta` vs `workspace`, `/agent` vs `/agent/run`, a stale `/tmp` artifact, a
   200 that middleware correctly makes 400, and a byte-counter that hooked only
   one of two read paths). Suspecting the probe first was correct every time.
