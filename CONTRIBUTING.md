# Contributing to Agentic OS

## Quick Start

```bash
# 1. Clone and install
git clone https://github.com/jstrick9/strick_tech.git
cd strick_tech
pip install -r requirements.txt

# 2. Start the server
python run.py

# 3. Open http://localhost:8787
```

## Development Setup

### Backend (Python)

```bash
pip install -r requirements.txt     # Runtime dependencies
pip install -r requirements-test.txt # Test dependencies (ruff, pytest)
```

### Frontend (JavaScript)

```bash
cd frontend
npm install    # Vitest + ESLint + jsdom
npm test       # Run frontend tests
npm run lint   # Run ESLint
```

## Running Tests

```bash
# Unit tests (fast, no server needed)
python -m pytest tests/unit/ -q

# Full test battery (requires running server on :8787)
python -m pytest tests/unit/ tests/regression/ tests/system/ tests/sprint_a tests/sprint_b tests/sprint_c tests/sprint_d tests/uat/ tests/gap/ -q

# Performance benchmarks
python -m pytest tests/perf/ -q

# Frontend tests
cd frontend && npm test
```

## Code Quality

- **Python**: Ruff F821 gate enforced in CI. Run `python -m ruff check backend/` locally.
- **JavaScript**: ESLint configured in `frontend/eslint.config.js`. Run `cd frontend && npm run lint`.
- **Imports**: Sorted automatically by ruff `--fix`.
- **No bare `except:`**: Use specific exception types.
- **No hardcoded secrets**: Use environment variables or the secrets vault.

## Architecture

```
backend/
  app.py          # FastAPI application, middleware, startup
  config.py       # Configuration management
  routers/        # 96 API routers (one per feature)
  services/       # Shared services (LLM, DB, scheduler, sandbox)

frontend/
  index.html      # Single-page application shell + CSS
  js/             # 45 JavaScript modules
  styles.css      # Global styles + design tokens
  tests/          # Vitest frontend tests

tests/
  unit/           # Python unit tests
  regression/     # Regression tests
  system/         # System integration tests
  sprint_a-d/     # Sprint-specific feature tests
  uat/            # User acceptance tests
  gap/            # Gap analysis tests
  security/       # Security tests
  perf/           # Performance benchmarks
```

## Adding a New Feature

1. Create a router: `backend/routers/my_feature.py`
2. Register it in `backend/app.py`: `from .routers.my_feature import router as my_feature_router`
3. Add the pane to `frontend/js/00-pane-registry.js`
4. Create the renderer in a new JS module (e.g., `frontend/js/41-my-feature.js`)
5. Add the `<script>` tag to `frontend/index.html`
6. Add the nav item to the sidebar in `frontend/index.html`
7. Write tests in `tests/unit/` or `tests/regression/`

## Commit Messages

Format: `Type: brief description`

Types: `Fix`, `Add`, `Update`, `Remove`, `Refactor`, `Test`, `Docs`

## License

See LICENSE file.
