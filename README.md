# 🧠 Agentic OS v6.0 — Mission Control
**Created by Joshua Strickland and Strick Tech**

> **Local-first Agentic AI Operating System** — Multi-agent swarm, Monaco editor, Memory Galaxy, live preview, voice commands, browser automation, and compounding 2-Tier Information Hierarchy (`IVREN`). Available in **Free, Pro, and Enterprise** versions.

![Version](https://img.shields.io/badge/version-6.0-blue)
![Creator](https://img.shields.io/badge/creator-Joshua%20Strickland%20%7C%20Strick%20Tech-purple)
![Editions](https://img.shields.io/badge/editions-Free%20%7C%20Pro%20%7C%20Enterprise-blueviolet)
![Tests](https://img.shields.io/badge/tests-876%20passing-green)

---

## ⚡ Quick Start (3 steps)

```bash
# 1. Clone the repo
git clone https://github.com/jstrick9/agentic-os.git
cd agentic-os

# 2. Add your API key
cp .env.example .env
# Open .env and add: OPENROUTER_API_KEY=sk-or-v1-...

# 3. Launch
./start.sh          # macOS / Linux
# OR
start.bat           # Windows
# OR
pip install -r requirements.txt && python run.py
```

Then open: **[http://localhost:8787](http://localhost:8787/)**

Get a free OpenRouter key: [https://openrouter.ai/keys](https://openrouter.ai/keys)

### Docker (one command)

```bash
docker build -t agentic-os . && docker run -p 8787:8787 agentic-os
```

---

## 🎯 What is Agentic OS?

Agentic OS is a **local-first AI operating system** you run on your own machine. It's a complete environment for working with multiple AI agents, building apps with live code preview, managing tasks, storing semantic memory, and automating workflows.

Think of it as your personal AI boardroom — Claude, GPT-4o, Gemini, Grok, Llama, and custom agents all working together, with your data staying on your machine.

---

## ✨ Features

### 💬 Real Chat (Streaming)
- Multi-agent chat with Server-Sent Events streaming
- Select any agent from the sidebar
- Slash commands: `/help`, `/goal`, `/research`, `/code`, `/review`, `/ship`, `/memory`, `/swarm`, `/clear`
- Memory-augmented responses (RAG from Memory Galaxy)
- Full conversation history per session

### 🤖 Custom Agents
- **Create your own agents** with custom name, avatar, color, model, and system prompt
- Supports: Claude, GPT-4o, Gemini, Grok, Hermes, Llama, Qwen (via OpenRouter)
- Local models via **Ollama** (private, no API cost)
- Edit/delete agents from the UI — no config files needed

### 🌀 Multi-Agent Swarm
- Fan-out one prompt to 2-6 agents in parallel
- Strategies: **Judge** (pick best), **Merge** (fuse top-2), **Fan-out** (show all)
- AI judge selects winner with reasoning and scores
- Accept winner directly into Monaco editor
- Swarm history stored in DB

### 🚀 Live App Builder
- **Monaco editor** (VS Code in browser) with custom Agentic theme
- Multi-file support with file tree
- **Git time-travel** — every save versioned in SQLite
- **Side-by-side diff viewer** — compare any two versions
- **Scaffold**: Next.js 15, SvelteKit, Expo React Native, vanilla Web
- Live iframe preview with hot reload
- LAN QR code for mobile preview

### 🌌 Memory Galaxy
- **3D interactive force graph** of all your memories
- Hybrid search: SQLite FTS5 keyword + optional vector embeddings
- Click any node → view full memory → send to chat
- Ingest new memories directly from UI
- All agent chats auto-indexed to memory

### 🎤 Voice Agent
- **12 neural TTS voices** (Microsoft edge-tts, FREE, no API key)
- Agent-specific voice mapping (Brain → Aria, Builder → Davis, etc.)
- **Voice input** via browser WebSpeech API (Ctrl+Shift+V)
- **Speak buttons** on all agent messages (hover to reveal)
- Voice command parsing with 20+ patterns
- Voice-controlled navigation ("go to kanban", "open terminal")

### 🌐 Browser Automation
- **Playwright-powered** autonomous web browsing
- AI-planned action sequences (navigate, click, type, extract, screenshot)
- Simulation mode when Playwright not installed
- Session persistence with step history
- Quick screenshot endpoint

### 🛡️ HITL Approval Gates
- Confidence-threshold gating (low=0.7, medium=0.85, high=1.0)
- Always-interrupt actions (delete, deploy, financial, etc.)
- Approve/reject/modify workflow
- Safe undo with state snapshots
- Complete audit trail

### 📋 Kanban Board
- Drag-and-drop task management
- 4 columns: To Do, Doing, Blocked, Done
- Full CRUD — create, assign, delete tasks
- Agent assignment, priority, layer metadata
- Persisted in SQLite

### 🔐 Secrets Vault
- Fernet AES-256 encrypted secret storage
- API keys never stored in git
- Per-agent key scoping
- Auto-injected to `os.environ` on boot
- Manage from Settings UI

### ⌘ Command Palette
- Press `⌘K` / `Ctrl+K` anywhere
- Search commands, agents, files, memories
- Fuzzy matching with keyboard navigation

### 🛒 Plugin Marketplace
- 8 curated packs with 37+ skills
- Install/uninstall with one click
- Ratings, reviews, and update checking
- ZIP upload/download for custom packs
- Skills: summarize, code review, research, DevOps, and more

---

## 🏗️ Architecture

```
agentic-os/
├── backend/
│   ├── app.py              ← FastAPI entry point (security, docs, middleware)
│   ├── config.py            ← Pydantic configuration validation
│   ├── routers/             ← 76 API routers
│   └── services/
│       ├── llm.py           ← OpenRouter + Ollama client (streaming)
│       ├── memory_db.py     ← SQLite schema + CRUD
│       └── scheduler.py     ← Autonomous agent loops
├── frontend/
│   ├── index.html           ← Main UI (modular, 176KB)
│   ├── styles.css           ← Design system (180KB, cacheable)
│   ├── js/                  ← 12 modular JS files (cacheable)
│   │   ├── 00-store.js      ← Reactive state management
│   │   ├── 00-errors.js     ← Error boundaries
│   │   ├── 01-app-core.js   ← Core app logic
│   │   ├── 09-voice-tts.js  ← Voice & TTS integration
│   │   └── ...              ← Feature modules
│   ├── manifest.json        ← PWA manifest
│   └── sw.js                ← Service worker
├── agents/agents.yaml       ← Default agent definitions
├── skills/skills.json       ← Skills registry
├── tests/                   ← 161 test files, 3970+ test functions
├── Dockerfile               ← One-command deployment
├── docker-compose.yml       ← Docker Compose with optional Qdrant
├── pyproject.toml           ← Ruff linting + pytest config
├── .env.example             ← Environment template
├── start.sh                 ← macOS/Linux startup
└── start.bat                ← Windows startup
```

---

## 🔑 API Keys & Models

### OpenRouter (Primary — recommended)

One key gives you access to all major models:

| Agent ID | Model | Cost |
|----------|-------|------|
| `claude` | Claude 3.5 Sonnet | ~$0.003/1K in |
| `claude-opus` | Claude Opus 4 | ~$0.015/1K in |
| `gpt4o` | GPT-4o | ~$0.005/1K in |
| `gemini` | Gemini 2.5 Pro | ~$0.00125/1K in |
| `grok` | Grok 3 | varies |
| `llama` | Llama 3.3 70B | **free** |
| `gemini-flash` | Gemini 2.0 Flash | **free** |

Get your key: [https://openrouter.ai/keys](https://openrouter.ai/keys)

### Ollama (Local — free, private)

```bash
# Install: https://ollama.com
ollama pull llama3.1:8b     # 4.7GB — good for most tasks
ollama pull codellama:7b    # 3.8GB — code-focused
```

---

## 🛡️ Security

- **Rate limiting**: 300 requests/minute per IP
- **Security headers**: CSP, HSTS, X-Frame-Options, X-XSS-Protection
- **Encrypted vault**: Fernet AES-256 for API keys
- **CORS**: Localhost-only origins
- **Input validation**: All endpoints validate and sanitize input
- **Audit trail**: All actions logged to immutable audit table
- **HITL gates**: Dangerous actions require human approval

---

## 📖 API Documentation

Once running, visit:
- **Swagger UI**: [http://localhost:8787/docs](http://localhost:8787/docs)
- **ReDoc**: [http://localhost:8787/redoc](http://localhost:8787/redoc)
- **OpenAPI JSON**: [http://localhost:8787/api/openapi.json](http://localhost:8787/api/openapi.json)

---

## 🧪 Testing

```bash
# Run all unit tests
python -m pytest tests/unit/ -v

# Run with coverage
python -m pytest tests/unit/ --cov=backend --cov-report=html

# Run specific test suite
python -m pytest tests/unit/test_07_agents.py -v

# Run security tests
python -m pytest tests/security/ -v
```

---

## 🗺️ Roadmap

### v6.0 (Current) ✅
- Real LLM chat with streaming (OpenRouter + Ollama)
- Custom agent create/edit/delete from UI
- Multi-agent swarm with AI judge
- Memory Galaxy (3D graph + FTS5 search)
- Monaco editor + Git time-travel + diff viewer
- Secrets Vault (Fernet AES-256)
- Command palette (⌘K)
- Voice agent (12 TTS voices + voice input)
- Browser automation (Playwright)
- HITL approval gates
- Plugin marketplace (8 packs, 37 skills)
- Docker deployment
- OpenAPI documentation

### v6.1 (Current) ✅
- Tauri desktop app (`/api/tauri/status`, macOS/Windows/Linux native build bridge)
- MCP Tool Router (filesystem, browser, git, and sandboxed background shell tools via `/api/mcp/*`)
- Real autonomous agent loops (`POST /api/loops/{id}/run-now`, `GET /api/loops/{id}/history`, APScheduler engine)
- One-click Vercel/Netlify deploy (`/api/deploy/*` providers and project bundle generators)
- Playwright E2E auto-fix loop (`POST /api/e2e/autofix` autonomous LLM self-healing cycle)

### v7.0 (Current) ✅
- Plugin & skill marketplace with community submissions and live 1-5 star ratings (`POST /api/marketplace/community/submit`, `GET /api/marketplace/community/list`)
- Multi-user collaboration with real-time Operational Transformation & CRDT delta sync (`GET /api/collab/rooms/active`, `POST /api/collab/rooms/{id}/join`)
- Mobile app bridge & build manifest for Expo & React Native (`GET /api/mobile/config`, `GET /api/mobile/manifest`, `POST /api/mobile/push-register`)
- Self-hosted encrypted Cloud Vault sync with AES-256 (`POST /api/sync/export-encrypted`, `POST /api/sync/import-encrypted`, `GET /api/sync/status`)

### v8.0 (Current) ✅
- Enterprise RBAC (Role-Based Access Control) & fine-grained API token scoping (`/api/rbac/roles`, `/api/rbac/tokens/create`, `/api/rbac/tokens/verify`)
- Autonomous voice-to-voice telephony agents (`/api/telephony/config`, `/api/telephony/twilio/voice`, WebRTC / Twilio live streaming)
- Distributed multi-node Swarm clustering across edge devices (`/api/cluster/status`, `/api/cluster/nodes/join`, `/api/cluster/dispatch`)
- Local zero-shot fine-tuning engine (`/api/finetune/hardware`, `/api/finetune/jobs/start`, LoRA weights on Apple Silicon & CUDA)

### v9.0 (Current) ✅
- Autonomous zero-day vulnerability bounty hunter & self-patching security scanner (`/api/security/bounty-hunter/config`, `/api/security/bounty-hunter/scan`, `/api/security/bounty-hunter/scans/{id}/autopatch`)
- Decentralized P2P encrypted model checkpoint sharding over IPFS & BitTorrent protocols (`/api/p2p-sharding/config`, `/api/p2p-sharding/checkpoints/shard`, `/api/p2p-sharding/checkpoints/{id}/fetch`)
- Quantum-resistant hybrid post-quantum cryptography (`/api/pqc/algorithms`, `/api/pqc/keypair/generate`, `/api/pqc/kem/encapsulate`, `/api/pqc/vault/encrypt`)
- Autonomous hardware robotics & IoT sensor control suite via ROS 2 & MQTT (`/api/robotics/status`, `/api/robotics/actuators/register`, `/api/robotics/actuators/{id}/command`, `/api/robotics/mission/execute`)

### v10.0 (Current) ✅
- Real-time brain-computer interface (`BCI`) neural decoding bridge (`/api/bci/status`, `/api/bci/channels/configure`, `/api/bci/decode/intent` via OpenBCI / Muse 8-channel EEG arrays)
- Autonomous self-replicating infrastructure compiler (`/api/compiler/status`, `/api/compiler/self-host/compile`) with zero-downtime hot-swap kernel module patching (`/api/compiler/kernel/hot-swap`)
- Universal physical-digital reality twin synchronization (`/api/digital-twin/status`, `/api/digital-twin/spatial/anchors`, `/api/digital-twin/sync`) bridging spatial computing headsets (`Apple Vision Pro` / `OpenXR`) with 3D Memory Galaxy overlays
- Multi-planetary offline satellite edge mesh networking (`/api/satellite/status`, `/api/satellite/bundles/enqueue`, `/api/satellite/bundles/{id}/transmit`) using DTN (`Delay-Tolerant Networking`) and Bundle Protocol (`RFC 9171`) for deep-space store-and-forward operations

### v11.0 (Next)
- Autonomous self-aware artificial general intelligence (`AGI`) cognitive metacontroller (`/api/agi/metacontrol`) with continuous causal reasoning and introspective self-governance
- Zero-energy ambient backscatter RF harvesting and wireless sub-microwatt compute grid (`/api/ambient-compute/harvest`) for perpetual IoT sensor nodes
- DNA / molecular synthetic biological data storage engine (`/api/bio-storage/encode`) storing multi-terabyte semantic vector embeddings directly within synthetic oligonucleotide chains (`ACGT`)
- Autonomous interstellar robotic probe trajectory optimizer and optical laser communications array (`/api/interstellar/deep-space-link`)

---

## 🐛 Troubleshooting

**"No API key" warning**
→ Add `OPENROUTER_API_KEY` to `.env` or use Settings → Vault

**Port 8787 already in use**
→ Change `AGENTIC_OS_PORT=8788` in `.env`

**Ollama not connecting**
→ Run `ollama serve` in a terminal first

**Monaco editor not loading**
→ Requires internet access to load from CDN. For offline use, bundle Monaco locally.

**Memory Galaxy shows blank**
→ Add some memories via the ingest box, or chat with an agent first.

---

## 📄 Editions & License

**Agentic OS Platform is created and maintained by Joshua Strickland and Strick Tech.**

### Editions
- **Free Version:** Essential local-first multi-agent chat, basic studio builder, SQLite memory, and core 2-tier information hierarchy for individuals.
- **Pro Version:** Advanced swarm orchestration, 12 neural voice TTS agents, autonomous Playwright browser automation, full CRDT collaboration, and unlimited project IVREN hierarchies for professional builders and teams.
- **Enterprise Version:** Dedicated Governance Control Tower, HITL approval gates, custom MCP tool routing, SLA monitoring, anomaly detection, and priority enterprise support by Strick Tech for organizations.

© 2026 Joshua Strickland / Strick Tech. All rights reserved.

---

_Built with ❤️ in Charlotte, NC_
