#!/usr/bin/env bash
# ═══════════════════════════════════════════════════════════════
#  Agentic OS — Startup Script (macOS / Linux)
#  Run: ./start.sh
# ═══════════════════════════════════════════════════════════════
set -euo pipefail

ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
cd "$ROOT"

echo ""
echo "  🧠 Agentic OS v6.0 — Mission Control"
echo "  ══════════════════════════════════════"
echo ""

# ── Check Python ───────────────────────────────────────────────
PYTHON=""
for cmd in python3 python; do
  if command -v "$cmd" &>/dev/null; then
    version=$("$cmd" --version 2>&1 | grep -oE '[0-9]+\.[0-9]+')
    major=$(echo "$version" | cut -d. -f1)
    minor=$(echo "$version" | cut -d. -f2)
    if [ "$major" -ge 3 ] && [ "$minor" -ge 10 ]; then
      PYTHON="$cmd"
      break
    fi
  fi
done

if [ -z "$PYTHON" ]; then
  echo "  ❌ Python 3.10+ not found."
  echo "     Install: https://python.org"
  exit 1
fi

echo "  ✅ Python: $($PYTHON --version)"

# ── Check .env ─────────────────────────────────────────────────
if [ ! -f ".env" ]; then
  if [ -f ".env.example" ]; then
    echo ""
    echo "  ⚠️  No .env file found."
    echo "     Copying .env.example → .env"
    cp .env.example .env
    echo "     Edit .env and add your OPENROUTER_API_KEY"
    echo "     Get a free key: https://openrouter.ai/keys"
    echo ""
  fi
fi

# ── Install dependencies ──────────────────────────────────────
if [ ! -d ".venv" ] && [ ! -d "venv" ]; then
  echo ""
  echo "  📦 Installing dependencies..."
  $PYTHON -m pip install -r requirements.txt -q 2>/dev/null || {
    echo "  ⚠️  pip install failed. Trying with --user flag..."
    $PYTHON -m pip install -r requirements.txt --user -q
  }
fi

# ── Run ────────────────────────────────────────────────────────
echo ""
echo "  🚀 Starting Agentic OS..."
echo "  🌐 http://localhost:${AGENTIC_OS_PORT:-8787}"
echo ""

$PYTHON run.py
