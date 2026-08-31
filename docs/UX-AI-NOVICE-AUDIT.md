# Agentic OS — "AI Novice" Usability Audit & Improvement Plan

**Goal area:** make the platform the most user-friendly it can be for an **AI Novice** — someone new to AI, not
technical, using it for personal productivity. Findings come from genuinely walking the running app as such a user
(fresh install, no API key) and reading the shipped navigation/onboarding code. Every finding is grounded in the
actual served UI or the authored source.

**Important context and honesty up front:**
- I could not render pixel screenshots in this sandbox (no root to install Chromium's system libraries), so this
  audit is built from the **real served DOM/IA**, the **live first-run API state**, and the authored frontend code —
  not from eyeballed screenshots. The structural findings below (labels, duplicates, onboarding, empty states) are
  exact and verifiable; visual polish/aesthetic judgement is where screenshots would have helped most, and I've left
  that class of finding out rather than guess.
- The good news: **the platform is already far better than typical for a novice.** Read on — this is mostly polish
  and de-confusion on top of a strong base, not a redesign.

---

## 1. What's already strong for a novice (do NOT break these)

- **The onboarding modal is excellent.** Plain language, "You have a full team of AI agents… Let's get set up in 3
  minutes," one API key unlocks all model families, "Meet your team," name your workspace, first task, theme. This is
  exactly the right novice shape and should be preserved.
- **Progressive disclosure exists.** Only 8 "CORE MODULES" are expanded; the 18 advanced panes are grouped into
  labeled, collapsed groups (AI TOOLS / BUILD & SHIP / CONNECT / OPERATE). Novices aren't hit with everything at once.
- **Every core item has a tooltip** ("Chat with AI — start here", "Start from a template", etc.).
- **The first-run/empty-state audit already fixed 4 panes** that were blank or unexplained (kanban, code search,
  web search, multi-preview) and added honest empty states. That work is real and good.
- Consistent dark theme, keyboard shortcuts, accessibility pass, touch targets — all mature.

---

## 2. Confirmed novice-confusion findings (with exact evidence)

### 2.1 🔴 (A) Two different features BOTH labeled "Workspaces" in the same sidebar — the #1 confusion
- Core group (line 121): `data-nav="icm"` → icon 🗂 → **label "Workspaces"**, tooltip "Folder-as-architecture
  workspaces" (meaningless to a novice), aria-label "Workspaces".
- BUILD & SHIP group (line 158): `data-nav="workspaces"` → icon 📂 → **label "Workspaces"**.
- **These are two unrelated things.** ICM is the folder-architecture notes/content system (fed by the Inbox);
  the BUILD & SHIP one is code/project workspaces. A novice will click the first one, get a system they don't
  recognize, and never understand they are different. This is a real, high-impact defect.

### 2.2 🟠 (B) Jargon labels with no tooltip on collapsed panes
Advanced items have labels novices can't parse and **no** one-line explanation (unlike core):
`Supervisor`, `Composer`, `Evals`, `Observability`, `Tool Connections` (MCP). A novice poking into a group hits a
wall of specialized vocabulary with no "what does this do."

### 2.3 🟠 (C) 12 default agents, several specialized and coded-tooling-flavored
The onboarding says "8 specialist agents" but 12 are seeded, including `visual_tester` (Visual UI Tester),
`functional_tester`, `design_decomposer`, `test_creator` (Test Case Creator). For personal use these are noise that
adds to "wait, what is a Functional Tester?" overwhelm.

### 2.4 🟡 (D) "Galaxy" ↔ label "Memory" mismatch; "ICM" is an internal acronym
Core item is `data-nav="galaxy"` but labeled **"Memory"** (tooltip "Your saved knowledge & memories"). And the
system internally/repeatedly calls the core workspace system "ICM" (Inbox & Content Management) which never
appears in the UI in plain English.

### 2.5 🟡 (E) Post-onboarding, there's no single "now try X" affordance
Onboarding closes onto the Chat pane; a novice benefits from a short "3 quick things to try" or a persistent
"Next: connect your key" cue, since the #1 real gate (an API key) is easy to miss in Settings.

---

## 3. Recommended changes, by novice impact vs. risk

These are intentionally **low-risk, highest-leverage** — mostly copy/labels + one small helper surface. I'd do them in
this order.

| # | Change | Impact | Risk |
|---|---|---|---|
| **1 (P0)** | Rename the core **ICM** nav so there is only one "Workspaces." Recommend: core → **"Projects"** (tooltip "Organize your notes, files & folders") OR keep "Workspaces" on ICM and rename BUILD & SHIP → "Code Workspaces." My recommendation: **core = "Knowledge"**, BUILD & SHIP stays "Workspaces" — but I want your preference (see questions). | High | Very low (label/tooltip only) |
| **2 (P1)** | Add plain-English `data-tooltip` to every collapsed advanced nav item ("Supervisor — let AI run multi-step jobs for you," "Evals — test how well your AI answers do," "Observability — watch what your agents are doing," "Tool Connections — hook up outside services"). Mirrors the pattern core already uses. | High | Very low |
| **3 (P1)** | Add a **"What does this do?" (help) affordance** per pane — a small ℹ button that opens a two-line plain-language explainer; reuse existing per-pane empty-state copy. | High | Low |
| **4 (P2)** | **Simplify the default agent roster** for personal use: add "Hide advanced agents" (collapses visual_tester/functional_tester/design_decomposer/test_creator) ON by default, or group them under an "Advanced agents" section. Keep them reachable. | Medium | Low |
| **5 (P2)** | Post-onboarding "3 quick things to try" card or a persisted "Still need your AI key?" banner that deep-links to Settings → API. | Medium | Low |
| **6 (P2/optional)** | Rename the "Memory" pane label to match its content or offer "My Knowledge" as the label — small plain-language win. | Low | Very low |

**Deliberately out of scope (and why):** no re-architecting nav beyond labels; no engine/backend changes; no visual
redesign (I can't verify pixels here). These are additive and safe.

---

## 4. What I need from you before implementing

The user explicitly asked I confirm before making changes. Two decisions genuinely change direction, and rest are
just a yes/no on scope.

1. **The "Workspaces" collision — which label wins?** (my recommendation: `icm` → **"Knowledge"**)
2. **How far to go:** just the low-risk copy/tooltip fixes (1–2, 6), or also add the help affordance + simplify
   agents + post-onboarding nudge (3–5)?
3. **Scope of agent simplification:** hide advanced testing agents by default, or just re-label/group them?
4. **Do you want these pushed to `main`** (like last time) or left as a local proposal for your review first?

---

## Round 2 (implemented, commit pending) — activation & de-clutter

Round 1 fixed **labels & confusion**. Round 2 tackles **"now what?"** — the thing that actually decides whether a
novice keeps using it. Shipped in a new trailing module `frontend/js/94-novice-assist.js` plus an `index.html` tweak:

1. **"Simple mode" navigational switch.** A novice lands on the 8 CORE panes only. The four advanced groups
   (AI TOOLS / BUILD & SHIP / CONNECT / OPERATE — 24 panes) are tucked behind a single **💡** toggle in the sidebar
   header and a **"Show all features ▾"** footer link. The last choice is remembered; a fresh install defaults to the
   simple view. (Implementation is display-only — no DOM nodes removed, so existing nav-count logic is untouched.)
2. **"🚀 Getting started" checklist** in the Chat empty state — Connect your AI → Send your first message → Save your
   first note → Create your first task. It **auto-checks real actions** (reads the app's own connection-ready state,
   the send/Enter paths, and wraps the user-triggered save/task flows), persists progress, collapses to a "🎉 You're
   all set" card when done, and is dismissible for good.
3. **Terminology polish:** the chat's **"Agent"** picker is now **"Assistant"** with a plain-language explanation
   ("Choose who replies: a general assistant or a specialist voice").

**Verification:** 19/19 jsdom runtime checks pass (simple-mode default + round-trip persist, all 4 checklist steps
auto-marking, dismiss, persona copy). `node --check` clean. ESLint: 0 errors on the new module. Frontend suite:
67 pass / 8 fail — the 8 are the *same pre-existing* failures confirmed on the prior commit; no regressions.
