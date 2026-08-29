#!/usr/bin/env bash
# Reproducible functional-validation bootstrap for Strick Tech Agentic OS.
set -euo pipefail

ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
cd "$ROOT"

python3 -m pip install --upgrade -r requirements-test.txt
python3 -m playwright install --with-deps chromium

for file in frontend/js/*.js; do
  node --check "$file"
done

PYTHONPATH=. python3 -m pytest tests/unit/ -q --tb=short
PYTHONPATH=. python3 debug_e2e.py
PYTHONPATH=. python3 tests/e2e/test_chat_and_buttons_live.py
PYTHONPATH=. python3 tests/e2e/test_product_experience_live.py

echo "✅ Strick Tech product validation completed successfully."
