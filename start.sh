#!/bin/bash
# Agentic OS v6.0 — Unix Launcher (macOS / Linux)
set -e

cd "$(dirname "$0")"

# Check Python
if ! command -v python3 &>/dev/null; then
  echo "❌ Python 3 not found. Install from https://python.org"
  exit 1
fi

PYTHON=$(command -v python3)
VERSION=$($PYTHON --version 2>&1 | cut -d' ' -f2 | cut -d'.' -f1-2)
echo "✓ Python $VERSION"

# Create .env from example if missing
if [ ! -f .env ] && [ -f .env.example ]; then
  cp .env.example .env
  echo "📝 Created .env from .env.example — add your OPENROUTER_API_KEY"
fi

# Install dependencies
echo "📦 Installing dependencies..."
$PYTHON -m pip install -r requirements.txt -q

# Run
echo "🚀 Starting Agentic OS..."
$PYTHON run.py
