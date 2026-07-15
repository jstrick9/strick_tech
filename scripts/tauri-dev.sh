#!/usr/bin/env bash
# ═══════════════════════════════════════════════════════════════════
#  Agentic OS — Tauri Dev Mode (hot-reload)
#  Runs backend + Tauri window with live reload
# ═══════════════════════════════════════════════════════════════════
set -euo pipefail

ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
cd "$ROOT"

echo "🚀 Starting Agentic OS in Tauri dev mode…"
echo "   Backend: http://localhost:8787"
echo "   Press Ctrl+C to stop"
echo ""

# Kill any existing backend
pkill -f "uvicorn backend" 2>/dev/null || true
sleep 0.5

# Start backend in background
python3 run.py --no-browser &
BACKEND_PID=$!
echo "   Backend PID: $BACKEND_PID"

# Wait for backend to be ready
echo "   Waiting for backend…"
for i in $(seq 1 20); do
  if curl -s http://localhost:8787/api/system/stats > /dev/null 2>&1; then
    echo "   ✅ Backend ready"
    break
  fi
  sleep 0.5
done

# Start Tauri dev window
cargo tauri dev &
TAURI_PID=$!

# Cleanup on exit
cleanup() {
  echo ""
  echo "🛑 Stopping…"
  kill $BACKEND_PID 2>/dev/null || true
  kill $TAURI_PID  2>/dev/null || true
}
trap cleanup EXIT INT TERM

wait
