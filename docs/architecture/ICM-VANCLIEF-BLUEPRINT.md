# The Van Clief Blueprint for this Agentic OS

Research findings from Jake Van Clief's public work (YouTube **@JEVanClief**, Skool
**skool.com/cliefnotes**, the ICM paper arXiv:2603.16021, and the two reference
repos `RinDig/Interpretable-Context-Methodology` and `RinDig/icm-architect`),
mapped against what this platform implements today, with the gap list and the
proposed build.

Status: **proposal awaiting owner sign-off.** Nothing here is built yet.

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

## 3. The gaps (what Jake teaches that we do not do)

| # | Gap | Severity |
|---|---|---|
| **G1** | **Only one form.** `scaffold()` always builds a Pipeline. No umbrella, record library, knowledge bundle, context map, system map. | High |
| **G2** | **No "start in the right folder" router.** Nothing decides *where* a request enters. This is Jake's named #1 failure mode and we have it wholesale. | **Critical** |
| **G3** | **No restructure mode.** Cannot point at an existing repo/vault, classify every file (catalog/contract/factory/product/dead), propose a migration map, migrate, validate. | High |
| **G4** | **No dialogue→structure extraction.** No path from "describe your work in chat" to a scaffolded workspace. Jake's core onboarding move. | High |
| **G5** | **No generated FILE-MAP.** Indexes would be hand-maintained, i.e. guaranteed to drift. | Medium |
| **G6** | **Skills aren't ICM.** `skills.json` registry instead of `SKILL.md` folders with progressive disclosure. | Medium |
| **G7** | **No typed frontmatter / queryable layer.** Knowledge-bundle and context-map forms need `type:`, `layer:`, `access_tier:`, `strength:` and dashboards querying them. | Medium |
| **G8** | **MCP tools not lazily scoped by intent** (already tracked as gap #8). | High |
| **G9** | **Workspaces aren't the home screen.** ICM is a tab inside a pane; in the canon the folder *is* the interface. | High |
| **G10** | **No life/computer/phone automation surface** — no ambient capture inbox, no phone entry point wired to workspaces. | Medium |
| **G11** | **Walk test isn't enforced as a gate**, only reported. | Low |
| **G12** | **No template/method library.** "Method and instance live apart" — we have no blank, reusable, shareable workspace templates. | Medium |

---

## 4. Proposed build (the extraordinary version)

Ten pieces. Each is buildable, testable, and follows the existing bar
(verified live, test proven to fail first, full suite green).

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
