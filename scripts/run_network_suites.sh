#!/usr/bin/env bash
# Run the network test suites against a SANDBOXED, loopback-bound server.
#
# WHY THIS EXISTS
# ───────────────
# The gap / usability / sprint / integration / regression / system / uat /
# security suites drive a live server over HTTP on 127.0.0.1:8787. Pointed
# at the preview server they break in three ways that look like product
# bugs but are not:
#
#   1. The preview binds 0.0.0.0, so the terminal's fail-closed auth gate
#      401s every /api/terminal/* call (by design on non-loopback binds).
#   2. The preview uses the REPO data dir, so every suite's writes —
#      gateway policies, autonomous loops, licenses, specs — accumulate in
#      production state. Later runs then fail on policies an earlier run
#      left behind (26 orphaned test policies and 12 test loops were
#      cleaned out of the live DB after the first discovery), and the
#      suites leave residue behind, which is exactly what #201/#202 were
#      about preventing.
#   3. Suites become order- and history-dependent: pass/fail depends on
#      what ran against that server before.
#
# This script gives those suites what the in-process suites got in #202:
# a throwaway data dir, a loopback bind, and no rate limiter. Port 8787 is
# used so the suites' hardcoded BASE URLs work unchanged; the script
# refuses to start if something is already listening there.
#
# USAGE
#   scripts/run_network_suites.sh [pytest args...]   # e.g. tests/gap tests/uat
#
# Environment: OPENROUTER_BASE_URL / OLLAMA_BASE_URL are passed through so
# LLM-dependent routes can be pointed at scripts/mock_llm.py.

set -euo pipefail
cd "$(dirname "$0")/.."

PORT=8787
BASE_URL="http://127.0.0.1:${PORT}"

if command -v curl >/dev/null && curl -s -o /dev/null --max-time 2 "${BASE_URL}/api/health"; then
  echo "ERROR: something is already listening on ${BASE_URL}." >&2
  echo "Stop it (that is usually the preview server) or the suites will run" >&2
  echo "against it unsandboxed — the exact failure mode this script exists to prevent." >&2
  exit 1
fi

# Build the sandbox env using the SAME module the in-process suites use,
# so the two sandboxes cannot drift apart.
eval "$(python3 - <<'PY'
import os, sys
sys.path.insert(0, 'tests')
from _data_sandbox import activate
activate(prefix='agentic-network')
print('export AGENTIC_OS_DATA_DIR=' + os.environ['AGENTIC_OS_DATA_DIR'])
print('export AGENTIC_TEST_DB=' + os.environ['AGENTIC_TEST_DB'])
print('export AGENTIC_OS_HOST=127.0.0.1')
PY
)"
export RATE_LIMIT_MAX=1000000          # the suites' job is not to test the limiter
echo "sandbox data dir: ${AGENTIC_OS_DATA_DIR}"

python3 -m uvicorn backend.app:app --host 127.0.0.1 --port "${PORT}" --log-level warning &
SERVER_PID=$!
trap 'kill "${SERVER_PID}" 2>/dev/null || true' EXIT

for _ in $(seq 1 60); do
  if curl -s -o /dev/null --max-time 2 "${BASE_URL}/api/health"; then break; fi
  sleep 0.5
done
if ! curl -s -o /dev/null --max-time 2 "${BASE_URL}/api/health"; then
  echo "ERROR: sandboxed server failed to start on ${BASE_URL}" >&2
  exit 1
fi
echo "sandboxed server up: ${BASE_URL} (loopback, throwaway data dir)"

python3 -m pytest "$@"
rc=$?

kill "${SERVER_PID}" 2>/dev/null || true
echo "sandboxed server stopped; data dir kept for inspection: ${AGENTIC_OS_DATA_DIR}"
exit "${rc}"
