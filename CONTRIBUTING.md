# Contributing to Agentic OS

Thank you for your interest in contributing to Agentic OS! This document provides guidelines and instructions for contributing.

## 🚀 Quick Start

```bash
# 1. Fork and clone
git clone https://github.com/jstrick9/strick_tech.git
cd agentic-os

# 2. Create a virtual environment
python -m venv .venv
source .venv/bin/activate  # macOS/Linux
# .venv\Scripts\activate   # Windows

# 3. Install dependencies
pip install -r requirements.txt

# 4. Create a .env file
cp .env.example .env
# Add your OPENROUTER_API_KEY

# 5. Run the application
python run.py
```

## 🧪 Running Tests

```bash
# All unit tests
python -m pytest tests/unit/ -v

# With coverage
python -m pytest tests/unit/ --cov=backend --cov-report=html

# Specific test file
python -m pytest tests/unit/test_07_agents.py -v

# Security tests
python -m pytest tests/security/ -v

# Integration tests
python -m pytest tests/integration/ -v
```

## 📝 Code Style

We use **Ruff** for linting and formatting:

```bash
# Install ruff
pip install ruff

# Check for issues
ruff check backend/

# Auto-fix issues
ruff check backend/ --fix

# Format code
ruff format backend/
```

### Python Guidelines
- Use type hints for all function parameters and return values
- Add docstrings to all public functions
- Keep functions focused and small
- Use async/await for I/O operations
- Handle errors gracefully with proper error messages

### JavaScript Guidelines
- Use strict mode (`'use strict'`)
- Prefer `const` and `let` over `var`
- Use camelCase for variables and functions
- Add JSDoc comments for complex functions

## 🏗️ Project Structure

```
agentic-os/
├── backend/
│   ├── app.py           ← FastAPI entry point
│   ├── config.py        ← Configuration validation
│   ├── routers/         ← API endpoints (76 routers)
│   └── services/        ← Business logic
├── frontend/
│   ├── index.html       ← Main UI
│   ├── styles.css       ← Design system
│   └── js/              ← Modular JavaScript
├── tests/               ← Test suites
├── agents/              ← Agent definitions
├── skills/              ← Skill definitions
└── workspaces/          ← User workspaces
```

## 🐛 Reporting Bugs

1. Check existing issues first
2. Create a new issue with:
   - Clear title and description
   - Steps to reproduce
   - Expected vs actual behavior
   - Environment details (OS, Python version, browser)

## 💡 Suggesting Features

1. Check the roadmap in README.md
2. Create a new issue with:
   - Feature description
   - Use case
   - Proposed implementation (if any)

## 📤 Pull Requests

1. Fork the repository
2. Create a feature branch (`git checkout -b feature/amazing-feature`)
3. Make your changes
4. Add tests for new functionality
5. Ensure all tests pass
6. Commit your changes (`git commit -m 'Add amazing feature'`)
7. Push to the branch (`git push origin feature/amazing-feature`)
8. Open a Pull Request

### PR Guidelines
- Keep PRs focused on a single feature/fix
- Include tests for new functionality
- Update documentation if needed
- Follow the existing code style
- Write clear commit messages

## 📚 Documentation

- Update README.md for user-facing changes
- Add docstrings to new functions
- Update API documentation if adding new endpoints

## 🙏 Thank You!

Your contributions make Agentic OS better for everyone!
