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

# ── LLM provider for the sandboxed server (r70) ──────────────────────────────
# The header documents passing OPENROUTER_BASE_URL / OLLAMA_BASE_URL through
# "so LLM-dependent routes can be pointed at scripts/mock_llm.py" — but
# nothing provisioned one, so in the canonical no-env invocation every
# LLM-dependent route 503'd ('llm_unavailable') and 7 suite tests failed
# (gap_01: supabase-ai-setup, imagegen-variations, integrations×3,
# complete-endpoint; perf_07: gitai deps audit) — tests written against a
# working provider, red in the very topology the script exists to make
# canonical. When the caller has not pointed the server at a provider, point
# it at scripts/mock_llm.py: reuse one that is already running, or start
# (and stop on exit) our own.
if [ -z "${OPENROUTER_BASE_URL:-}" ] && [ -z "${OLLAMA_BASE_URL:-}" ]; then
  _mock_ready() {
    curl -s -m 2 http://127.0.0.1:8790/v1/models 2>/dev/null | grep -q '"data"' \
      && curl -s -m 2 http://127.0.0.1:8791/api/tags 2>/dev/null | grep -q '"models"'
  }
  MOCK_PID=""
  if ! _mock_ready; then
    # Ports busy with something that does not answer like the mock: refuse
    # rather than half-work. Free ports: start our own.
    if curl -s -m 2 -o /dev/null http://127.0.0.1:8790/v1/models 2>/dev/null \
       || curl -s -m 2 -o /dev/null http://127.0.0.1:8791/api/tags 2>/dev/null; then
      echo "ERROR: something other than scripts/mock_llm.py is listening on 8790/8791." >&2
      echo "Stop it, or export OPENROUTER_BASE_URL / OLLAMA_BASE_URL to your own provider." >&2
      exit 1
    fi
    python3 scripts/mock_llm.py >/dev/null 2>&1 &
    MOCK_PID=$!
    for _ in $(seq 1 40); do
      if _mock_ready; then break; fi
      sleep 0.25
    done
    if ! _mock_ready; then
      echo "ERROR: scripts/mock_llm.py failed to start on 8790/8791." >&2
      exit 1
    fi
  fi
  export OPENROUTER_BASE_URL=http://127.0.0.1:8790/v1
  export OPENROUTER_API_KEY="${OPENROUTER_API_KEY:-mock-key}"
  export OLLAMA_BASE_URL=http://127.0.0.1:8791
  echo "LLM provider: scripts/mock_llm.py on 8790/8791 (reused: $([ -n "${MOCK_PID}" ] && echo no || echo yes))"
fi
# One trap for everything this script may have started. SERVER_PID is
# assigned later; the trap reads it at exit time.
trap '[ -n "${MOCK_PID:-}" ] && kill "${MOCK_PID}" 2>/dev/null; kill "${SERVER_PID:-}" 2>/dev/null; true' EXIT

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
# (exit trap already installed above, alongside the mock-LLM lifecycle)

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
