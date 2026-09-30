"""One key, one action — the resolved double-binds stay resolved (r96, #260).

#259 verified the help overlay against the real bindings and documented four
keys by their FINAL effect because two or three handlers fired on each press
(the follow-up table in docs/module-reviews/92-honest-help-and-palettes.md).
#260 resolves them by deleting the losing handler, so the documented
behaviour is the ONLY behaviour and nothing paints underneath:

    ⌘⇧E  Health       07-quality-tools wins alone; 05-evals' dead nav deleted
    ⌘⇧P  Profiler     03-features-a wins alone; app-core's studio nav deleted
    ⌘P   palette      app-core wins alone; 14-prompt-library's code-search
                      nav deleted
    ⌘\\   sidebar      app-core wins alone; 90-sidebar-shortcut.js deleted
                      outright and 14's split-workspace keydown binding with
                      it (split workspace keeps buttons + palette entry)
    ⌘R   review file  14-prompt-library's guard used to ask for a lowercase
                      'r' WITH shift held — shift makes e.key 'R', so the
                      condition never matched: dead code the overlay
                      documented anyway. The guard now matches the key.

Also pins the platform modal contract the overlay joined in #260 (locked
scope (e) of the design-system work): the `kbd-modal-overlay` class enrolls
the overlay in collectOpenModals()'s ad-hoc discovery, masterEscapeHandler's
teardown and isTrapRoot's Tab focus trap. Browser-level pins for the same
contract live in tests/e2e_browser/test_e2e_browser_13_modal_contract.py.
"""

from __future__ import annotations

import re
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
JS = ROOT / 'frontend' / 'js'
INDEX = ROOT / 'frontend' / 'index.html'
OVERLAY = JS / '93-shortcuts-overlay.js'
CORE = JS / '01-app-core.js'
EVALS = JS / '05-evals-observability.js'
QUALITY = JS / '07-quality-tools.js'
FEATURES_A = JS / '03-features-a.js'
PROMPT = JS / '14-prompt-library.js'


def _src(p: Path) -> str:
    return p.read_text(encoding='utf-8')


# ══ The modal contract ════════════════════════════════════════════════════════
def test_overlay_joins_the_platform_modal_contract():
    """`kbd-modal-overlay` enrolls the overlay in the same machinery every
    other modal answers to: ad-hoc discovery, Esc teardown, Tab trap."""
    src = _src(OVERLAY)
    assert "className = 'kbs-overlay kbd-modal-overlay'" in src
    core = _src(CORE)
    # the discovery selector and the trap test that must keep recognising it
    assert '[class*="-modal-overlay"]' in core
    assert re.search(r'return /-modal-overlay/\.test\(cls\)', core)
    # the class we put on the overlay satisfies the trap's own pattern
    assert re.search(r'-modal-overlay', 'kbs-overlay kbd-modal-overlay')


def test_overlay_no_longer_documents_double_binds_as_final_effect():
    """The 'documented by their FINAL effect' era is over — and the overlay's
    Esc branch is documented as belt-and-braces, not the owner."""
    src = _src(OVERLAY)
    assert 'documented by their FINAL effect' not in src
    assert 'belt-and-braces' in src


# ══ ⌘\ — sidebar, and only the sidebar ═══════════════════════════════════════
def test_backslash_has_exactly_one_handler():
    """90-sidebar-shortcut.js (a width-toggle duplicate of toggleSidebar())
    is deleted, and 14-prompt-library's split-workspace binding with it."""
    assert not (JS / '90-sidebar-shortcut.js').exists()
    assert '90-sidebar-shortcut.js' not in _src(INDEX)
    prompt = _src(PROMPT)
    assert 'e.preventDefault();toggleSplitWorkspace();' not in prompt, (
        'the split-workspace ⌘\\ keydown binding is back'
    )
    # the surviving handler is app-core's toggleSidebar
    assert "e.code === 'Backslash'" in _src(CORE)
    # split workspace itself stays reachable: buttons + palette entry
    assert 'toggleSplitWorkspace(true' in _src(FEATURES_A)
    assert 'Split Workspace' in prompt


# ══ ⌘P — the palette, and only the palette ═══════════════════════════════════
def test_cmd_p_is_the_palette_alone():
    """14-prompt-library used to nav('codesearch') underneath the palette on
    every ⌘P press (code search is a Studio workstation tab anyway)."""
    assert "e.key==='p'" not in _src(PROMPT)
    assert "e.key === 'p'" in _src(CORE)  # openPalette survives


# ══ ⌘⇧E — Health, and only Health ════════════════════════════════════════════
def test_cmd_shift_e_is_health_alone():
    """05-evals' nav('evals') painted Evals once underneath Health on every
    press (07-quality-tools loads later and always won)."""
    assert "e.key==='E'" not in _src(EVALS)
    assert "nav('health')" in _src(QUALITY)


# ══ ⌘⇧P — Profiler, and only Profiler ════════════════════════════════════════
def test_cmd_shift_p_is_profiler_alone():
    """app-core's nav('studio') painted Studio underneath Profiler on every
    press; the palette's Open Studio entry must not claim the key either."""
    core = _src(CORE)
    assert "e.shiftKey && e.key === 'P'" not in core
    assert "nav('profiler')" in _src(FEATURES_A)
    assert "Chat + Editor + Live Preview (⌘⇧P)" not in core


# ══ ⌘R — review, and actually review ═════════════════════════════════════════
def test_cmd_r_guard_matches_the_documented_key():
    """The old guard (`e.key==='r' && e.shiftKey`) could never fire — with
    shift held e.key is 'R'. The overlay documents ⌘R; the binding, the
    review button tooltip and the palette entry must all agree on it."""
    prompt = _src(PROMPT)
    assert "e.key==='r'&&!e.shiftKey" in prompt
    assert "e.key==='r'&&e.shiftKey" not in prompt
    assert "AI code review (⌘R)" in prompt
    assert "AI code review (⌘⇧R)" not in prompt
    # ⌘⇧R belongs to Replay alone (08-replay-collab), as the overlay documents
    assert "{keys: ['⌘', 'R'], desc: 'Review current file'}" in _src(OVERLAY)
    replay = _src(JS / '08-replay-collab.js')
    assert "e.key==='R'" in replay
