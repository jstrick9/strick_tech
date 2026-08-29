#!/usr/bin/env python3
"""Run every UX audit and report the headline numbers.

    python3 scripts/audit/run_all.py                # human readable
    python3 scripts/audit/run_all.py --json         # machine readable
    python3 scripts/audit/run_all.py --write-baseline

The numbers this prints are the ones ratcheted by
tests/unit/test_120_audit_ratchet.py against scripts/audit/baseline.json. A
number going UP fails the build; a number going DOWN is an improvement and the
baseline should be lowered in the same commit.

Browser audits need a live server:
    AGENTIC_OS_DATA_DIR=/tmp/agentic-data python run.py
`source_patterns` needs neither a browser nor a server.
"""

from __future__ import annotations

import importlib
import json
import sys
from pathlib import Path

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE))

BASELINE = HERE / 'baseline.json'

# Cheapest first, so a source-only regression is reported even when no browser
# is available.
AUDITS = [
    'source_patterns',
    'semantics',
    'pane_health',
    'keyboard',
    'touch_targets',
    'responsive',
    'failure_honesty',
    'concurrency',
    'announcements',
    'slow_network',
    'history_navigation',
    'large_data',
    'session_expiry',
    'offline_reconnect',
    'adversarial_input',
    'timezones',
    'preferences',
    'print_and_multitab',
    # Needs a server started against an EMPTY data dir. Against a seeded
    # one it reports 0 with an informational note rather than a result,
    # so including it here is safe but only meaningful on a fresh server.
    'first_run',
    'task_completion',
    'console_health',
    # Needs no browser -- it compares the frontend's call sites against
    # FastAPI's own route table. It existed but was never in this list and
    # never in the baseline, so nothing enforced it: an unenforced audit is a
    # file, not a gate. Its four standing findings were all probe defects and
    # are fixed; it is at 0 and ratcheted here so it stays there.
    'module_completeness',
    # NOT in this list: agent_reliability. It needs a server started against
    # scripts/audit/fake_provider.py with OLLAMA_BASE_URL pointed at it, and
    # one MODE per invocation. Run it directly:
    #
    #   MODE=truncate AGENTIC_FAKE_PROVIDER=1 python3 scripts/audit/agent_reliability.py
    #
    # Included here it would report 0 on every normal run without measuring
    # anything -- the vacuous-pass trap this review has hit nine times.
]


def main() -> int:
    as_json = '--json' in sys.argv
    write_baseline = '--write-baseline' in sys.argv

    results, skipped = {}, {}
    for name in AUDITS:
        module = importlib.import_module(name)
        try:
            result = module.run()
        except SystemExit as exc:
            # preflight() exits 2 when there is no browser or no server.
            if exc.code == 2:
                skipped[name] = 'no browser or no server'
                continue
            raise
        results[name] = result
        if not as_json:
            result.print_human()

    if as_json:
        print(json.dumps({
            'counts': {r.name: r.count for r in results.values()},
            'skipped': skipped,
            'detail': {r.name: r.to_dict() for r in results.values()},
        }, indent=1))
    else:
        print('\n' + '─' * 62)
        print('SUMMARY')
        for result in results.values():
            print(f'  {result.count:6}  {result.name}')
        for name, why in skipped.items():
            print(f'  {"SKIP":>6}  {name}  ({why})')

    if write_baseline:
        existing = {}
        if BASELINE.exists():
            existing = json.loads(BASELINE.read_text(encoding='utf-8'))
        existing.update({r.name: r.count for r in results.values()})
        BASELINE.write_text(json.dumps(existing, indent=2, sort_keys=True) + '\n',
                            encoding='utf-8')
        print(f'\nbaseline written to {BASELINE.relative_to(HERE.parent.parent)}')
        if skipped:
            print('NOTE: skipped audits were left at their previous baseline')

    return 0


if __name__ == '__main__':
    raise SystemExit(main())
