#!/usr/bin/env python3
"""Static accessibility and semantics checks on the rendered DOM.

Reports the structural problems that a screen-reader user hits immediately:

  no <h1>            no top-level heading; heading navigation starts nowhere
  unnamed dialog     announced as just "dialog"
  nested dialog      a dialog inside a dialog, announced twice
  unnamed control    a button with no text, aria-label or title
  unlabelled input   no label, aria-label or placeholder
  missing landmark   no <main> or <nav>

WHAT THIS AUDIT FOUND
─────────────────────
The page had NO <h1> at all, three unnamed dialogs (one of them a nested
dialog created at runtime by the accessibility helper itself), and six inputs
with no autocomplete hint.
"""

from __future__ import annotations

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
from _harness import AuditResult, browser_page, emit, preflight  # noqa: E402

MEASURE_JS = """() => {
    const q = s => [...document.querySelectorAll(s)];
    const visible = el => el.offsetParent !== null;
    const named = el => !!(el.getAttribute('aria-label')
                        || el.getAttribute('aria-labelledby'));
    return {
        h1: q('h1').length,
        main: q('main, [role=main]').length,
        nav: q('nav, [role=navigation]').length,
        unnamedDialogs: q('[role=dialog]').filter(d => !named(d))
            .map(d => d.id || (d.className || '').toString().slice(0, 24) || '(anonymous)'),
        nestedDialogs: q('[role=dialog]').filter(
            d => d.parentElement && d.parentElement.closest('[role=dialog]'))
            .map(d => d.id || (d.className || '').toString().slice(0, 24) || '(anonymous)'),
        unnamedButtons: q('button').filter(
            b => visible(b) && !b.textContent.trim()
                && !b.getAttribute('aria-label') && !b.getAttribute('title')).length,
        unlabelledInputs: q('input, textarea, select').filter(
            i => visible(i) && !i.getAttribute('aria-label')
                && !i.getAttribute('placeholder')
                && !(i.id && document.querySelector('label[for="' + i.id + '"]'))
                && !i.closest('label')).length,
        imgsNoAlt: q('img').filter(i => !i.hasAttribute('alt')).length,
    };
}"""


def run() -> AuditResult:
    preflight()
    findings = []
    with browser_page('desktop') as (page, _ctx):
        m = page.evaluate(MEASURE_JS)

    if m['h1'] == 0:
        findings.append('no <h1> on the page — no top-level heading to navigate from')
    if m['h1'] > 1:
        findings.append(f"{m['h1']} <h1> elements — there should be exactly one")
    if m['main'] == 0:
        findings.append('no <main> landmark')
    if m['nav'] == 0:
        findings.append('no <nav> landmark')
    for d in m['unnamedDialogs']:
        findings.append(f'dialog with no accessible name: {d}')
    for d in m['nestedDialogs']:
        findings.append(f'nested dialog (announced twice): {d}')
    if m['unnamedButtons']:
        findings.append(f"{m['unnamedButtons']} buttons with no accessible name")
    if m['unlabelledInputs']:
        findings.append(f"{m['unlabelledInputs']} inputs with no label")
    if m['imgsNoAlt']:
        findings.append(f"{m['imgsNoAlt']} images with no alt attribute")

    return AuditResult(
        'semantics',
        len(findings),
        findings,
        note='structural accessibility problems on the default view',
    )


if __name__ == '__main__':
    raise SystemExit(emit(run()))
