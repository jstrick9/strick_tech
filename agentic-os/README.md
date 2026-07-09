# Agentic OS — Agent Team OS v5.0
### Free • Local-first • MIT • /goal /research /code /review /ship pipeline

**Agent roles — Apollo • Artemis • Hermes • Hephaestus • Jarvis — autonomous construction company**

Free Boardroom Clone — AI Profit Boardroom Agentic OS — Charlotte, NC

---

## v5.0 — Agent Team Orchestration — NEW

**Pre-wired team — turns Agentic OS from chat → autonomous construction company**

### Agents

| ID | Name | Role | Emoji | Model | Color |
|----|------|------|-------|-------|-------|
| apollo | Apollo | **planner** | 🏛️ | claude-3.5-sonnet | #f5c542 |
| artemis | Artemis | **researcher** | 🔭 | gemini-2.5-pro | #7dd3a7 |
| hermes | Hermes | **builder** | ⚡ | qwen-2.5-coder-32b | #7aa2f7 |
| hephaestus | Hephaestus | **reviewer** | 🔨 | claude-3-haiku | #e06b6b |
| jarvis | Hermes-Jarvis | **voice** | 🎙️ | whisper+piper | #2ac3de |

Plus: claude, gemini, grok, openclaw, galaxy, swarm, builder, expo, self, local

---

### Pipeline — /goal /research /code /review /ship

**One prompt → autonomous team executes end-to-end**

```
/goal "launch Stripe checkout SaaS"
  → Apollo
  → breaks into Goldie Mission Stack 4-layer
  → 5-9 Kanban tasks auto-created
  → assigned: apollo, artemis, hermes, hephaestus, openclaw

/research "competitors"
  → Artemis
  → Qdrant RAG hybrid first
  → Market brief — Charlotte NC — TAM, competitors, tech stack, risks
  → auto-saved to Memory Galaxy

/code "build checkout"
  → Hermes
  → triggers /api/preview/scaffold
  → Monaco multi-file — HMR
  → E2E auto-run

/review
  → Hephaestus
  → runs Playwright E2E → gets score
  → static analysis: eval(), innerHTML, TODO, console.log, API_KEY leak
  → scoring: 0.92 base − E2E penalty − security issues
  → verdict: APPROVED ✓ / NEEDS_WORK
  → auto-fix loop: if failed + auto_fix=true → runs e2e_autofix → re-review — max 3 iters

/ship
  → Hermes
  → POST /api/deploy/vercel
  → returns https://agentic-xxxx.vercel.app
  → QR auto-updates
```

**Full pipeline API**
```
POST /api/pipeline/run
{
  "goal": "launch Stripe checkout SaaS",
  "stages": ["goal","research","code","review","ship"],
  "target": "web|expo",
  "auto_fix": true,
  "force_ship": false
}
→ {
  ok: true,
  run_id: "pipe_172065...",
  strategy: "apollo→artemis→hermes→hephaestus→ship",
  results: [
    {stage:"goal", agent:"apollo", tokens:..., duration_ms:...},
    {stage:"research", agent:"artemis", ...},
    {stage:"code", agent:"hermes", ...},
    {stage:"review", agent:"hephaestus", score:0.91, approved:true, ...},
    {stage:"ship", agent:"hermes", url:"https://...", ...}
  ],
  status:"done",
  duration_ms: ~4200,
  ship_url:"https://agentic-os-xxxx.vercel.app",
  ...
}
```

**Single-stage endpoints**
```
POST /api/goal      {goal:"..."}       → Apollo
POST /api/research  {query:"..."}      → Artemis
POST /api/code      {prompt:"..."}     → Hermes
POST /api/review    {target:"web"}     → Hephaestus
POST /api/ship      {target:"web"}     → Deploy
```

**Voice agent — Hermes-Jarvis**

```
POST /api/agent/voice
  {text:"Hey Hermes, build me a Stripe checkout page"}
  OR {audio_b64:"..."}  # Whisper STT stub
→ {
  ok:true,
  agent:"jarvis",
  transcript:"Hey Hermes, build me a Stripe checkout page",
  reply_text:"Hey — Jarvis here…",
  tts_url:null,
  tts_note:"Piper TTS not installed … use Web Speech API",
  actions:[{type:"code",status:"done"}],
  rag_used:true,
  stt_engine:"text-input-stub — integrate Whisper.cpp local"
}
```
- RAG-grounded via Memory Galaxy
- If prompt contains build/code/create/make/launch/ship → auto-triggers `stage_code`
- Result auto-ingested to memory — `source:"jarvis:voice"`
- Frontend TTS: Web Speech API — `speechSynthesis.speak()` — voice pick: Nova/Zira/Samantha
- STT: Web Speech API — “🎤 Hold to talk” — hands-free building while walking

---

### Mission Control UI — 🏛️ Pipeline tab

`/static/pipeline.js` — 9.7 KB

- New tab: **🏛️ Pipeline** — gold `#f5c542` — after 🌌 Memory Galaxy, before 🌀 Swarm
- Top: agent roles row — 5 cards:
  - 🏛️ **Apollo** — planner — #f5c542 — “Vision → Goals → Kanban”
  - 🔭 **Artemis** — researcher — #7dd3a7 — “Market • competitors • RAG”
  - ⚡ **Hermes** — builder — #7aa2f7 — “Code • E2E • HMR”
  - 🔨 **Hephaestus** — reviewer — #e06b6b — “Security • perf • tests”
  - 🎙️ **Jarvis** — voice — #2ac3de — “STT → build → TTS”
- Left control (380px sticky):
  - **/goal — Apollo planner** textarea
  - Pipeline stages checkboxes:
    - ☑ `/goal` — Apollo — Vision → Kanban
    - ☑ `/research` — Artemis — Market • RAG
    - ☑ `/code` — Hermes — Build • E2E
    - ☑ `/review` — Hephaestus — Security • perf
    - ☑ `/ship` — Hermes — Vercel deploy
  - Target: `web | expo` dropdown
  - ☑ auto-fix — ☑ force ship
  - Button: **🚀 Run /goal → /ship pipeline** — gold gradient
  - Slash commands help:
    ```
    /goal … → Apollo plans
    /research … → Artemis
    /code … → Hermes builds
    /review → Hephaestus
    /ship → Vercel
    Hey Hermes, … → Jarvis voice
    ```
- Right results:
  - Stage tracker — 5-step visual: `/goal → /research → /code → /review → /ship`
    - colors: done=#13231b green • active=#2a2108 gold • todo=#141a2a
    - arrows →
  - Output cards per stage:
    - header: emoji • STAGE — agent • ms • tokens • status pill
    - `<pre>` — 2600 chars — `max-height:260px` — scroll
    - review shows: score, e2e_score, issues, warnings
  - Merged ship box — green — if `ship_url` returned:
    - 🚀 Shipped → `https://agentic-…vercel.app` — clickable
    - Copy URL • Open →
  - run_id footer
- **Jarvis voice modal**
  - Button top-right: **🎙️ Jarvis voice**
  - Modal: `“Hey Hermes, build me a Stripe checkout page” → voice → STT → agent builds → TTS reply → preview updates`
  - Textarea + **🎤 Hold to talk** — Web Speech API
    - `SpeechRecognition` / `webkitSpeechRecognition` — `en-US` — interimResults
    - auto-send on final transcript after 500ms
  - **Send → Hermes** button
  - Output box: RAG answer + actions
  - TTS: `speechSynthesis.speak()` — auto-plays reply — picks Nova/Zira/Samantha voice if available
  - If code action → auto-refresh Monaco file tree + preview iframe HMR after 900ms
- **Slash commands in Chat**
  - Chat input intercept:
    - `/goal …` → switches to Pipeline tab → fills goal → auto-runs
    - `/research …`, `/code …`, `/review`, `/ship` → POST to `/api/{stage}` → alert with output preview
    - `Hey Hermes, …` / `Jarvis, …` / `ok hermes …` → opens Jarvis modal → pre-fills transcript
- **History**
  - Button: **📜 History**
  - `GET /api/pipeline/history?limit=12`
  - Alert shows: `[ts] done — review — prompt… — https://… — run_id: pipe_…`

**Database**
```sql
CREATE TABLE pipeline_runs (
  id, run_id TEXT, goal TEXT,
  status TEXT,           -- running|done|needs_review|failed
  current_stage TEXT,    -- goal|research|code|review|ship
  created_at, completed_at,
  duration_ms INTEGER,
  result_url TEXT
);
CREATE TABLE pipeline_steps (
  id, run_id TEXT,
  stage TEXT, agent TEXT,
  input_text TEXT, output_text TEXT,
  status TEXT,
  tokens INTEGER, duration_ms INTEGER,
  created_at TIMESTAMP
);
```

---

## Full Agentic OS — v1 → v5.0

| v | Feature | Status |
|---|---------|--------|
| v1 | Mission Control • 7 agents • SQLite FTS5 • Kanban • Goals • Cost • 16 skills | ✅ |
| v2 | Live App Builder — HMR | ✅ |
| v3 | Monaco • multi-file tabs • Git time-travel • Diff • Expo RNW • QR tunnel | ✅ |
| v3.4-3.6 | Playwright E2E auto-fix • Trace Viewer • Ghost autocomplete • Cmd+K | ✅ |
| v4.1 | One-click Deploy — Vercel | ✅ |
| v4.2 | **Memory Galaxy** — Qdrant vector RAG 384d | ✅ |
| v4.3 | **Swarm** — fan-out judge merge | ✅ |
| v4.4 | **Expo Go Native** — Metro tunnel — true iOS/Android | ✅ |
| v4.5 | **Scaffolder Pro** — Next.js / SvelteKit / Expo templates | ✅ |
| v4.6 | **Auto-Heal** — Live error overlay + Hermes fix | ✅ |
| v4.7 | **Component Inspector** — click-to-code | ✅ |
| v4.8 | **Package Manager** — npm / pnpm inside OS | ✅ |
| v4.9 | **Secrets Vault** — Fernet AES-256 — per-agent scoping | ✅ |
| **v5.0** | **Agent Team OS** — **/goal /research /code /review /ship + Jarvis voice** | ✅ |

**18 skills • 11+5 role agents • $0/mo • MIT**

```
Agents:
  swarm       Swarm Orchestrator   Fan-out • Judge • Merge
  galaxy      Memory Galaxy        Qdrant vector RAG
  apollo      Apollo               Planner — /goal
  artemis     Artemis              Researcher — /research
  hermes      Hermes               Builder — /code
  hephaestus  Hephaestus           Reviewer — /review
  jarvis      Hermes-Jarvis        Voice — STT/TTS
  builder     App Builder          Monaco + Git
  expo        Expo RN              Mobile live + QR + Expo Go
  claude      Claude               The brain
  openclaw    OpenClaw             Browser + Playwright
  gemini      Gemini CLI           Code
  grok        Grok Studio          Multi-modal
  self        Self Layer           Obsidian memory
  local       Local LLM            Ollama private
```

---

## Quick start

```bash
cd agentic-os
pip install -r requirements.txt
# fastapi uvicorn httpx pydantic apscheduler
# qdrant-client sentence-transformers torch numpy
# qrcode pillow
# cryptography
python run.py
# → http://localhost:8787
```

**Try Agent Team pipeline:**
1. Open **🏛️ Pipeline** tab
2. Input: `/goal launch Stripe checkout SaaS for Charlotte SEO agency`
3. Stages: ☑ goal ☑ research ☑ code ☑ review ☑ ship — target: web — auto-fix: on
4. **🚀 Run /goal → /ship pipeline**
5. Watch:
   - 🏛️ Apollo — 5-9 Kanban tasks created — 680ms
   - 🔭 Artemis — research brief + Memory Galaxy RAG — 420ms
   - ⚡ Hermes — scaffold → Next.js 17 files → E2E 4/4 green
   - 🔨 Hephaestus — review score 0.91 — APPROVED ✓
   - 🚀 Ship — https://agentic-os-pipeline-xxxx.vercel.app — 18s
6. Total: ~4.2s local (+ deploy)
7. Kanban auto-updated — tasks move todo → doing → done
8. **🎙️ Jarvis voice** — top right → Hold to talk → “Hey Hermes, add pricing toggle monthly/yearly” → STT → Hermes builds → TTS reply → preview HMR

**Slash commands — anywhere in Chat:**
- `/goal …` → Apollo
- `/research …` → Artemis
- `/code …` → Hermes
- `/review` → Hephaestus
- `/ship` → Vercel
- `Hey Hermes, …` → Jarvis voice modal opens

API:
```
POST /api/pipeline/run
POST /api/goal
POST /api/research
POST /api/code
POST /api/review
POST /api/ship
POST /api/agent/voice
GET  /api/pipeline/history
GET  /api/pipeline/status?run_id=...
```

---

MIT — Agentic OS v5.0 — Agent Team OS
Built 2026-07-09 Charlotte, NC
Free Boardroom Clone — $0/mo — Local-first

**Claude • Hermes • Apollo • Artemis • Hephaestus • Jarvis • Galaxy • Swarm • Expo • OpenClaw • Gemini • Grok • Local • Self • Builder**
— 16 agents — 18 skills — Qdrant RAG — Swarm fan-out — Expo Go Native — Monaco CmdK — E2E Trace — Vercel Ship — Auto-Heal — Inspector click-to-code — PM npm/pnpm — Secrets Vault Fernet —
**/goal /research /code /review /ship — autonomous**
