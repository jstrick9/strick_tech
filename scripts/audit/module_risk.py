#!/usr/bin/env python3
"""Rank every pane by measurable risk, to sequence a module-by-module review.

WHY A MEASURED RANKING
──────────────────────
"Review all 68 modules" is only tractable if the order is right, and intuition
about which modules are weakest is exactly the thing that has been wrong
repeatedly in this review: the Image Generator looked fine and crashed for
every new user; the primary LLM provider looked well covered and had no test
seam at all.

So the order is derived from evidence, not opinion. Each pane scores on five
signals, all cheap to compute and all independently defensible:

  no-tests          nothing in tests/ mentions this pane or its renderer.
                    A module with no test is a module whose behaviour nobody
                    has pinned; it is also where a regression lands silently.

  no-backend        the pane makes no API calls. Sometimes correct (a
                    client-only tool) -- so it is a signal, not a verdict.

  size              lines of implementation. Big modules hide more, and a
                    defect in one affects more of the product.

  surface           how many distinct API paths it touches. Each is an
                    integration point that can 404, 500, or change shape.

  churn-risk        `TODO|FIXME|stub|not implemented` markers in CODE, with
                    docstrings and comments stripped -- this codebase is
                    heavily commented and counting prose gives nonsense.

WHAT THE SCORE IS NOT
─────────────────────
It is not a defect count. It ranks where defects are most LIKELY and most
COSTLY, so the review starts where it pays. A module can score low and still
be broken -- which is what the other twenty-two audits are for.
"""

from __future__ import annotations

import json
import re
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
from _harness import AuditResult, emit  # noqa: E402

REPO = Path(__file__).resolve().parent.parent.parent
JS_DIR = REPO / 'frontend' / 'js'
TESTS = REPO / 'tests'

API_PATH = re.compile(r"""['"`](/api/[A-Za-z0-9_\-/${}.]*)['"`]""")
MARKER = re.compile(r'\b(TODO|FIXME|XXX|HACK|not implemented|coming soon)\b', re.I)


def _strip_js_comments(source: str) -> str:
    source = re.sub(r'/\*[\s\S]*?\*/', '', source)
    return re.sub(r'(?m)//.*$', '', source)


def _pane_modules() -> dict[str, Path]:
    registry = (JS_DIR / '00-pane-registry.js').read_text(encoding='utf-8')
    panes = re.findall(r"^\s*'([a-z0-9-]+)':\s*(.*)$", registry, re.M)
    renderers = {}
    for pane, body in panes:
        match = re.search(r'window\.(render[A-Za-z0-9_]+)', body)
        renderers[pane] = match.group(1) if match else None

    sources = {f: f.read_text(encoding='utf-8', errors='replace')
               for f in sorted(JS_DIR.glob('*.js'))
               if f.name not in ('00-pane-registry.js', '00-render-dedupe.js')}

    out: dict[str, Path] = {}
    for pane, fn in renderers.items():
        if not fn:
            continue
        for path, src in sources.items():
            if re.search(rf'(async\s+)?function\s+{fn}\s*\(|'
                         rf'\b{fn}\s*=\s*(async\s*)?(function|\()|'
                         rf'window\.{fn}\s*=', src):
                out[pane] = path
                break
    return out


def _test_corpus() -> str:
    parts = []
    for path in TESTS.rglob('*.py'):
        parts.append(path.read_text(encoding='utf-8', errors='replace'))
    return '\n'.join(parts)


def run() -> AuditResult:
    modules = _pane_modules()
    corpus = _test_corpus()

    rows = []
    for pane, source_path in sorted(modules.items()):
        raw = source_path.read_text(encoding='utf-8', errors='replace')
        code = _strip_js_comments(raw)

        # Attribute only the renderer's own file; several panes share one file,
        # so size is divided by how many panes that file serves. Charging one
        # pane for a 5,000-line shared module would put it top of every list.
        shared = sum(1 for p in modules.values() if p == source_path)
        lines = len(raw.splitlines()) // max(shared, 1)

        paths = {p for p in API_PATH.findall(code) if not p.endswith('/api/')}
        markers = len(MARKER.findall(code))
        tested = bool(re.search(rf"\b{re.escape(pane)}\b", corpus))

        score = 0
        score += 40 if not tested else 0
        score += 15 if not paths else 0
        score += min(lines // 100, 20)
        score += min(len(paths), 15)
        score += min(markers * 2, 10)

        rows.append({
            'pane': pane, 'score': score, 'file': source_path.name,
            'lines': lines, 'endpoints': len(paths),
            'markers': markers, 'tested': tested,
        })

    rows.sort(key=lambda r: (-r['score'], r['pane']))

    findings = [
        f'{r["score"]:3}  {r["pane"]:18} {r["file"]:32} '
        f'{r["lines"]:5}ln {r["endpoints"]:3}ep '
        f'{"UNTESTED" if not r["tested"] else "        "} '
        f'{r["markers"] or "":>2}'
        for r in rows[:30]
    ]
    untested = [r['pane'] for r in rows if not r['tested']]
    findings.append(f'-- {len(untested)} pane(s) with no test mention: '
                    + ', '.join(untested[:15]))

    (REPO / 'docs' / 'module-risk.json').write_text(
        json.dumps(rows, indent=2) + '\n', encoding='utf-8')
    findings.append('-- full ranking written to docs/module-risk.json')

    # Informational by design: this is a planning instrument, not a defect
    # count, so it must never fail the ratchet.
    return AuditResult('module-risk', 0, findings,
                       note='risk ranking used to sequence the module review')


if __name__ == '__main__':
    raise SystemExit(emit(run()))
