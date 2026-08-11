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

  no-tests          no test mentions this pane id, its renderer, or its
                    module file. A module with no test is one whose behaviour
                    nobody has pinned, and where a regression lands silently.

                    Matching is deliberately three-way, because both simpler
                    versions were wrong. Searching the pane id alone reported
                    `collabedit` as untested after 17 tests were written for
                    it -- they name the renderer and the router, never the
                    pane id. Searching loosely is worse: the id `docs` appears
                    in 104 test files as ordinary English, so that pane would
                    score fully tested whatever the truth. The id must appear
                    as a quoted or underscored TOKEN, not as a bare word.

  no-backend        the pane makes no API calls. Sometimes correct (a
                    client-only tool) -- so it is a signal, not a verdict.

  size              lines of implementation. Big modules hide more, and a
                    defect in one affects more of the product.

  surface           how many distinct API paths it touches. Each is an
                    integration point that can 404, 500, or change shape.

  churn-risk        `TODO|FIXME|stub|not implemented` markers in CODE, with
                    docstrings and comments stripped -- this codebase is
                    heavily commented and counting prose gives nonsense.

REVIEWED MODULES ARE EXCLUDED FROM THE TOP OF THE LIST
──────────────────────────────────────────────────────
The score is driven by size and integration surface, so a module stays high
after it has been reviewed and fixed -- `docs` still scores 35 with 1,828
lines and 15 endpoints even though its defects are now closed. That is honest
(it remains a big, risky module) but useless for SEQUENCING, which is the only
job this instrument has.

Modules with a committed review doc are therefore listed separately rather
than competing for the next slot. `docs/module-reviews/` is the register.

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


def _strip_js(source: str) -> str:
    """Source with comments AND string literals removed.

    String literals matter as well as comments: `data-act-click="renderX()"`
    inside a template would otherwise read as a call site strong enough to
    claim the pane.
    """
    source = re.sub(r'/\*[\s\S]*?\*/', ' ', source)
    source = re.sub(r'(?m)//.*$', ' ', source)
    source = re.sub(r'`(?:[^`\\]|\\.)*`', ' `` ', source)
    source = re.sub(r"'(?:[^'\\\n]|\\.)*'", " '' ", source)
    source = re.sub(r'"(?:[^"\\\n]|\\.)*"', ' "" ', source)
    return source


def _strip_js_comments(source: str) -> str:
    source = re.sub(r'/\*[\s\S]*?\*/', '', source)
    return re.sub(r'(?m)//.*$', '', source)


RENDERERS_BY_PANE: dict[str, str] = {}


def _is_tested(pane: str, renderer: str, filename: str, corpus: str) -> bool:
    """Does any test pin this module?

    Three signals, any of which counts:
      * the pane id as a QUOTED or underscored token -- `'kanban'`,
        `"kanban"`, `_kanban_`, `pane-kanban`. A bare word match is useless:
        `docs` occurs in 104 test files as ordinary English.
      * the renderer name (`renderCollabEdit`) -- how a test usually reaches a
        pane it never names.
      * the module filename (`08-replay-collab.js`) -- how a source-level test
        refers to it.
    """
    token = re.escape(pane)
    patterns = [
        rf"['\"]{token}['\"]",
        rf'pane-{token}',
        rf'_{token}[_\b]',
    ]
    if renderer:
        patterns.append(re.escape(renderer))
    if filename:
        patterns.append(re.escape(filename))
    return any(re.search(p, corpus) for p in patterns)


def _pane_modules() -> dict[str, Path]:
    registry = (JS_DIR / '00-pane-registry.js').read_text(encoding='utf-8')
    panes = re.findall(r"^\s*'([a-z0-9-]+)':\s*(.*)$", registry, re.M)
    renderers = {}
    for pane, body in panes:
        match = re.search(r'window\.(render[A-Za-z0-9_]+)', body)
        renderers[pane] = match.group(1) if match else None
    RENDERERS_BY_PANE.clear()
    RENDERERS_BY_PANE.update({k: v for k, v in renderers.items() if v})

    sources = {f: f.read_text(encoding='utf-8', errors='replace')
               for f in sorted(JS_DIR.glob('*.js'))
               if f.name not in ('00-pane-registry.js', '00-render-dedupe.js')}

    # Match against code with comments and string literals removed.
    #
    # THE BUG THIS FIXES. The search ran against raw source, so a COMMENT
    # counted as a definition:
    #
    #     01-app-core.js:3183  // top-level `function renderDashboard(){}` IS
    #                          // `window.renderDashboard`
    #
    # `dashboard` was attributed to 01-app-core.js (1,945 lines) rather than
    # 36-dashboard.js (159) -- a 12x error in the size signal, which feeds the
    # risk score. It inflated three panes to joint 3rd and would have kept
    # misdirecting the queue.
    stripped = {path: _strip_js(src) for path, src in sources.items()}

    out: dict[str, Path] = {}
    for pane, fn in renderers.items():
        if not fn:
            continue
        # A real definition beats a bare `window.renderX = ...` re-export: a
        # module may legitimately re-export a function defined elsewhere, and
        # the defining file is the one worth reviewing.
        defines = re.compile(
            rf'(async\s+)?function\s+{fn}\s*\(|\b{fn}\s*=\s*(async\s*)?(function|\()')
        exports = re.compile(rf'window\.{fn}\s*=')

        chosen = next((path for path, src in stripped.items() if defines.search(src)), None)
        if chosen is None:
            chosen = next((path for path, src in stripped.items() if exports.search(src)), None)
        if chosen is not None:
            out[pane] = chosen
    return out


def _test_corpus() -> str:
    parts = []
    for path in TESTS.rglob('*.py'):
        parts.append(path.read_text(encoding='utf-8', errors='replace'))
    return '\n'.join(parts)


def run() -> AuditResult:
    modules = _pane_modules()
    renderers_by_pane = RENDERERS_BY_PANE
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
        renderer = renderers_by_pane.get(pane) or ''
        tested = _is_tested(pane, renderer, source_path.name, corpus)

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

    # ── Consolidation: rank what the USER can navigate to ─────────────────
    # The pane surface was consolidated into a workstation model. A pane that
    # was absorbed into a host (e.g. `replay` into `observability`) is a tab,
    # not a destination, and must not appear as its own queue entry -- ranking
    # it re-inflates the module count back to the pre-consolidation 68 and
    # reports progress against a denominator the product no longer has.
    ws_src = (REPO / 'frontend' / 'js' / '00-workstations.js').read_text(
        encoding='utf-8', errors='ignore')
    _m = re.search(r'WORKSTATIONS\s*=\s*\{(.*?)\n\}', ws_src, re.S)
    hosts: dict[str, list[str]] = {}
    if _m:
        hosts = {
            k: re.findall(r"'([\w-]+)'", v)
            for k, v in re.findall(r"'([\w-]+)'\s*:\s*\[([^\]]*)\]", _m.group(1))
        }
    absorbed = {child for kids in hosts.values() for child in kids}

    index_src = (REPO / 'frontend' / 'index.html').read_text(
        encoding='utf-8', errors='ignore')
    destinations = set(re.findall(r"nav\('([\w-]+)'\)", index_src))

    # Keep a row only if the user can actually navigate to it. Fold each
    # absorbed pane's score into its host so a heavy tab still raises the
    # destination that owns it.
    host_of = {child: h for h, kids in hosts.items() for child in kids}
    folded: dict[str, int] = {}
    for row in rows:
        owner = host_of.get(row['pane'], row['pane'])
        folded[owner] = max(folded.get(owner, 0), row['score'])
    rows = [r for r in rows if r['pane'] in destinations and r['pane'] not in absorbed]
    for row in rows:
        row['score'] = folded.get(row['pane'], row['score'])
        row['tabs'] = len(hosts.get(row['pane'], []))

    # Which modules already have a committed review doc.
    #
    # This used to match the pane name against the review FILENAMES, which
    # silently under-reports: a doc covering three panes cannot name them all
    # in its filename. `ambient`, `bugbot` and `gitai` are the subject of
    # 70-quality-tools-trio.md and `knowledge-graph` of
    # 74-evals-rag-observability-kg.md, yet all four kept appearing at the top
    # of the queue as unreviewed -- twice sending the review back to modules
    # that were already done.
    #
    # Each doc declares its subjects on a `**Pane:**` / `**Panes:**` line, so
    # read that and fall back to the filename for older docs.
    reviewed_panes: set[str] = set()
    review_dir = REPO / 'docs' / 'module-reviews'
    # BUG FIX: this read `**Pane:**`/`**Panes:**` only, and stopped at the first
    # match. Docs written since the consolidation declare their subject as
    # `**Destination:**` with the tabs on a separate `**Tabs:**` line, so their
    # tabs were never counted: the evals workstation showed 3/5 tabs covered on
    # the queue after all five had been reviewed and fixed. Under-reporting here
    # sends the review back to work that is already done -- the exact failure
    # this tracker exists to prevent, and the second time it has occurred (see
    # f4e6c22). Every header form is now read, and all of them, not just the
    # first one found.
    header = re.compile(r'\s*\*\*(Panes?|Destinations?|Tabs?):\*\*\s*(.+)', re.I)
    for f in review_dir.glob('*.md'):
        stem = f.stem.lower()
        # BUG FIX (third occurrence of this same class). The token pattern
        # `[a-z0-9][a-z0-9-]*` swallows the numeric prefix, so `10-imagegen.md`
        # yielded the single token '10-imagegen' and never the pane id
        # 'imagegen'. The early pane-based reviews (docs 00-42) all carry that
        # shape and name their subject only in a `**Surface:**` line of FILE
        # PATHS, which cannot credit a pane either -- so `imagegen` and
        # `prompts` sat near the top of the queue as unreviewed while
        # docs/module-reviews/10-imagegen.md and 11-prompt-library.md had
        # already fixed 8 and 4 bugs in them respectively.
        #
        # Dropping a leading `NN-` before tokenising, and also keeping the
        # hyphen-split parts, credits those docs without loosening the match for
        # anything else. Verified against the queue before and after.
        stem_nonum = re.sub(r'^\d+[-_]', '', stem)
        for token in (stem, stem_nonum):
            reviewed_panes.update(re.findall(r'[a-z0-9][a-z0-9-]*', token))
            reviewed_panes.update(t for t in token.split('-') if t and not t.isdigit())
        for line in f.read_text(encoding='utf-8', errors='ignore').splitlines():
            m = header.match(line)
            if m:
                # e.g. "`arena`, `codeindex`, `hooks`, `specs`"
                reviewed_panes.update(re.findall(r'`([^`]+)`', m.group(2)))
                continue
            # Earlier docs name their subject in the H1 instead:
            #   "# 63 — Module review 2: Docs & Help (`docs`)"
            if line.startswith('# '):
                reviewed_panes.update(re.findall(r'`([^`]+)`', line))

    for row in rows:
        unit = [row['pane']] + hosts.get(row['pane'], [])
        row['covered'] = sum(1 for u in unit if u in reviewed_panes)
        row['unit'] = len(unit)
        # A destination is only done when every tab inside it is done.
        row['reviewed'] = row['covered'] == row['unit']

    rows.sort(key=lambda r: (r['reviewed'], -r['score'], r['pane']))

    findings = [
        f'{r["score"]:3}  {r["pane"]:18} {r["file"]:32} '
        f'{r["lines"]:5}ln {r["endpoints"]:3}ep '
        f'{r["covered"]}/{r["unit"]}tab '
        f'{"UNTESTED" if not r["tested"] else "        "} '
        f'{"REVIEWED" if r["reviewed"] else "        "} '
        f'{r["markers"] or "":>2}'
        for r in rows[:30]
    ]
    _done = sum(1 for r in rows if r['reviewed'])
    findings.insert(0, (
        f'-- {_done} of {len(rows)} user-facing destinations fully reviewed '
        f'(consolidated from {len(rows) + len(absorbed)} panes)'
    ))
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
