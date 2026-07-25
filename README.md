# Agentic OS Platform

A local-first AI operating system with multi-agent swarm, live code preview, memory galaxy, and 95+ integrated tools.

## Quick Start

```bash
# 1. Clone
git clone https://github.com/jstrick9/strick_tech.git
cd strick_tech

# 2. Install dependencies
pip install -r requirements.txt

# 3. Start the server
python run.py

# 4. Open http://localhost:8787
```

## One-Click Setup

The platform auto-detects available AI backends:
- **Ollama** (local, free): Install from [ollama.com](https://ollama.com), it's detected automatically
- **OpenRouter** (cloud, 140+ models): Get a free key at [openrouter.ai](https://openrouter.ai/keys)
- **Custom**: Connect any OpenAI-compatible endpoint

## Architecture

```
backend/           # FastAPI server (57k lines)
  app.py           # Application entry point, middleware
  routers/         # 96 API routers (one per feature)
  services/        # Shared services (LLM, DB, scheduler, engine)
  config.py        # Configuration management

frontend/          # Vanilla JS SPA (31.5k lines)
  index.html       # Shell + CSS design system
  js/              # 60 JavaScript modules
  styles.css       # Global styles + design tokens
  tests/           # Vitest frontend tests

tests/             # Python test suite (47k lines)
  unit/            # 64 test files
  system/          # 13 test files
  security/        # 10 test files
  perf/            # 10 test files
  regression/      # 6 test files
```

## Key Features

### Chat & AI
- Multi-model support (Claude, GPT-4o, Gemini, Llama, Ollama)
- Streaming responses with stop/cancel
- RAG grounding from your knowledge base
- File/image upload support
- Chat history search

### Agent Execution Engine
- **Loop Engineering**: Adaptive intervals, backoff, circuit breaker
- **Harness Engineering**: Test harnesses, benchmarks, regression detection
- **Chain Engineering**: Sequential steps with context passing
- **Reflection Engineering**: Self-improving loops with quality thresholds
- **Guard Engineering**: Output validation, content filtering
- **Cost Engineering**: Token budgets, cost tracking, model routing
- **Checkpoint Engineering**: Save/restore execution state

### Code Studio
- Monaco editor with live preview
- Template gallery (14 production-ready templates)
- AI-assisted editing with diff preview
- Multi-file scaffolding

### Enterprise
- Agent identity and token management
- Audit log with chain verification
- Connector framework (Slack, Jira, GitHub, Email, etc.)
- MCP tool gateway
- Supervisor orchestration

## Testing

```bash
# Backend tests
python -m pytest tests/unit/ -q

# Full test battery
python -m pytest tests/unit/ tests/regression/ tests/system/ tests/sprint_a tests/sprint_b tests/sprint_c tests/sprint_d tests/uat/ tests/gap/ -q

# Frontend tests
cd frontend && npm test

# Frontend lint
cd frontend && npm run lint

# Ruff static analysis
python -m ruff check backend/
```

## Docker

```bash
# Build and run
docker build -t agentic-os .
docker run -p 8787:8787 agentic-os

# With Ollama
docker compose --profile ollama up

# With Qdrant vector DB
docker compose --profile qdrant up
```

## API Reference

The platform exposes 895 API endpoints. Key endpoints:

| Endpoint | Description |
|----------|-------------|
| `GET /api/health` | Health check with DB validation |
| `POST /api/chat` | Send a chat message (SSE streaming) |
| `GET /api/agents` | List all agents |
| `POST /api/swarm/run` | Run multi-agent swarm |
| `GET /api/engine/status` | Execution engine status |
| `GET /api/workspace/export` | Export full workspace |
| `GET /api/docs` | In-app documentation |

## License

See LICENSE file.

## Contributing

See [CONTRIBUTING.md](CONTRIBUTING.md).
