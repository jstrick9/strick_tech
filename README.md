# 🧠 Agentic OS v6.0 — Mission Control

> **Local-first Agentic AI Operating System** — Multi-agent swarm, Monaco editor, Memory Galaxy, live preview, and more. Runs entirely on your machine.

![Version](https://img.shields.io/badge/version-6.0-blue)
![Python](https://img.shields.io/badge/python-3.10%2B-blue)
![License](https://img.shields.io/badge/license-MIT-green)

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

Then open: **http://localhost:8787**

Get a free OpenRouter key: https://openrouter.ai/keys

---

## 🎯 What is Agentic OS?

Agentic OS is a **local-first AI operating system** you run on your own machine. It's a complete environment for working with multiple AI agents, building apps with live code preview, managing tasks, and storing a semantic memory of everything you build.

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
- Search commands, navigate panes, create agents

---

## 🏗️ Architecture

```
agentic-os/
├── backend/
│   ├── app.py              ← FastAPI entry point
│   ├── routers/
│   │   ├── chat.py         ← Streaming LLM chat + slash commands
│   │   ├── swarm.py        ← Multi-agent fan-out + judge
│   │   ├── memory.py       ← Memory Galaxy endpoints
│   │   ├── agents.py       ← Agent CRUD (create/edit/delete)
│   │   ├── secrets.py      ← Encrypted vault
│   │   └── builder.py      ← Preview files, scaffold, PM, deploy
│   └── services/
│       ├── llm.py          ← OpenRouter + Ollama client (streaming)
│       └── memory_db.py    ← SQLite schema + CRUD
├── frontend/
│   └── index.html          ← v6.0 Mission Control UI
├── agents/
│   └── agents.yaml         ← Default agent definitions
├── skills/
│   └── skills.json         ← Skills registry
├── preview/                ← Live app files (served at /preview)
├── memory/
│   └── agentic.db          ← SQLite database
├── .env                    ← Your API keys (never committed)
├── .env.example            ← Template
├── config.yaml             ← App configuration
├── requirements.txt        ← Python dependencies
└── run.py                  ← Launcher
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

Get your key: https://openrouter.ai/keys

### Ollama (Local — free, private)
Run LLMs entirely on your machine:

```bash
# 1. Install Ollama
# macOS: brew install ollama
# Windows/Linux: https://ollama.com

# 2. Pull a model
ollama pull llama3.1:8b     # 4.7GB — good for most tasks
ollama pull codellama:7b    # 3.8GB — code-focused
ollama pull mistral:7b      # 4.1GB — fast, capable

# 3. Ollama runs automatically on localhost:11434
# 4. In Agentic OS, create an agent with provider=Ollama, model=llama3.1:8b
```

---

## 🛠️ Configuration

Edit `.env`:
```env
OPENROUTER_API_KEY=sk-or-v1-...    # Required for cloud LLMs
OLLAMA_BASE_URL=http://localhost:11434  # For local models
AGENTIC_OS_PORT=8787
```

Or use the 🔐 **Vault** tab in the UI — encrypted, auto-injected.

---

## 📦 Optional Dependencies

```bash
# Playwright E2E testing
pip install playwright
playwright install chromium

# Vector embeddings (local, ~1GB download)
pip install torch sentence-transformers numpy

# Qdrant vector database
docker run -p 6333:6333 qdrant/qdrant
pip install qdrant-client
```

---

## 🗺️ Roadmap

### v6.0 (Current)
- [x] Real LLM chat with streaming (OpenRouter + Ollama)
- [x] Custom agent create/edit/delete from UI
- [x] Multi-agent swarm with AI judge
- [x] Memory Galaxy (3D graph + FTS5 search)
- [x] Monaco editor + Git time-travel + diff viewer
- [x] Secrets Vault (Fernet AES-256)
- [x] Command palette (⌘K)
- [x] Toast notification system
- [x] Clean modular backend (routers + services)

### v6.1 (Next)
- [ ] Tauri desktop app (macOS/Windows/Linux native)
- [ ] MCP Tool Router (filesystem, browser, git, shell)
- [ ] Real autonomous agent loops (APScheduler)
- [ ] Voice agent (Whisper STT + TTS)
- [ ] One-click Vercel/Netlify deploy
- [ ] Playwright E2E auto-fix loop
- [ ] WebSocket real-time agent status

### v7.0 (Future)
- [ ] Plugin/skill marketplace
- [ ] Multi-user collaboration
- [ ] Mobile app (Expo)
- [ ] Cloud sync (self-hosted)

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

## 📄 License

MIT — Build freely. Attribution appreciated.

---

*Built with ❤️ in Charlotte, NC*
