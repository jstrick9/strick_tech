"""The onboarding overlay must never be able to trap the user.

REPORTED FROM A REAL DESKTOP BUILD: "the app keeps glitching on me where I
have trouble clicking in different modules."

WHAT I ACTUALLY FOUND, and it is narrower than the report suggested.

Measured in Chromium against the running app:

    first visit   #onboarding-modal display:flex, z-index 29000,
                  pointer-events:auto, and elementFromPoint over the sidebar
                  returns the modal -> nav genuinely unreachable
    Escape        modal removed, localStorage flag set, nav reachable
    reload        modal display:none, nav reachable

So the overlay does release, and it does persist its dismissal. The blocking
is real but confined to first visit, which is a modal behaving like a modal.

TWO THINGS I GOT WRONG WHILE INVESTIGATING, recorded because they are the
reason this file asserts what it does:

1. I reported "clicking Tasks BLOCKED" after reload. That was Playwright
   strict mode refusing an ambiguous locator, not a blocked click. The modal
   was display:none at the time.
2. The ambiguity is because `[data-nav="kanban"]` matches TWO elements: the
   sidebar entry and a Favorites copy. That is a feature, not a duplicate-id
   bug. Three nav ids are intentionally duplicated this way (chat, kanban,
   docs).

The risk worth guarding is therefore not "does the modal block" -- it should,
briefly -- but "can it ever fail to let go". These tests pin every escape
hatch, because a full-screen z-29000 overlay with pointer-events:auto is one
broken code path away from making the whole app unusable.
"""

from __future__ import annotations

import re
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
JS = (ROOT / 'frontend' / 'js' / '24-onboarding.js').read_text(encoding='utf-8')
HTML = (ROOT / 'frontend' / 'index.html').read_text(encoding='utf-8')


def test_the_modal_is_dismissible_by_clicking_the_backdrop():
    """A modal with no visible way out is a trap."""
    tag = re.search(r'<div[^>]*id="onboarding-modal"[^>]*>', HTML)
    assert tag, 'onboarding-modal not found in index.html'
    markup = tag.group(0)
    assert 'closeOnboardingModal' in markup, markup[:200]
    assert 'data-click-self' in markup, (
        'backdrop click must be scoped to the backdrop itself: ' + markup[:200])


def test_escape_closes_it():
    """The keyboard escape hatch. Verified live: Escape removed the modal."""
    assert re.search(r"key\s*===?\s*'Escape'", JS), 'no Escape handler'
    esc = JS[JS.index("'Escape'"):][:400]
    assert 'closeOnboardingModal' in esc, esc[:200]


def test_closing_removes_both_nodes_not_just_hides_them():
    """display:none still leaves a z-29000 node in the tree.

    Hiding is enough for pointer events, but removal is what stops a later
    bug re-showing it by flipping one style property. BOTH nodes must go: an
    earlier version of this test searched one 900-char slice for the word
    "removeChild", so deleting either removal still passed because the other
    one's call was inside the window.
    """
    close = JS[JS.index('window.closeOnboardingModal'):][:1200]
    modal_part = close[:close.index('onboarding-overlay')] if 'onboarding-overlay' in close else close
    overlay_part = close[close.index('onboarding-overlay'):] if 'onboarding-overlay' in close else ''
    assert 'removeChild(modal)' in modal_part.replace(' ', ''), modal_part[:300]
    assert 'removeChild(overlay)' in overlay_part.replace(' ', ''), overlay_part[:300]


def test_dismissal_is_remembered():
    """Otherwise it reappears on every launch -- the reported symptom."""
    close = JS[JS.index('window.closeOnboardingModal'):][:900]
    assert 'agentic_os_onboarded' in close, close[:300]


def test_the_boot_check_honours_the_flag():
    """checkOnboarding must return early once dismissed."""
    check = JS[JS.index('async function checkOnboarding'):][:600]
    assert 'agentic_os_onboarded' in check
    assert 'return' in check


def test_storage_failure_cannot_force_the_modal_open_forever():
    """localStorage throws in some packaged/private contexts.

    If reading the flag raised, checkOnboarding would fall through and show
    the modal on EVERY launch with no way to make it stop -- exactly the
    reported symptom, on a machine where storage is unavailable. The read is
    wrapped, and the writes are too.
    """
    check = JS[JS.index('async function checkOnboarding'):][:600]
    assert 'try' in check, 'the flag read must not be able to throw'
    close = JS[JS.index('window.closeOnboardingModal'):][:900]
    assert close.count('try') >= 1, 'the flag write must not be able to throw'


def test_there_is_a_second_independent_dismissal_flag():
    """`window._onboardingDismissed` works when storage is unusable."""
    check = JS[JS.index('async function checkOnboarding'):][:600]
    assert '_onboardingDismissed' in check, check[:300]


def test_the_overlay_is_not_left_behind_when_the_modal_closes():
    """Two nodes cover the screen; closing one and not the other still traps."""
    close = JS[JS.index('window.closeOnboardingModal'):][:1200]
    assert "getElementById('onboarding-overlay')" in close, close[:400]
    assert "getElementById('onboarding-modal')" in close, close[:400]


def test_the_modal_starts_hidden_in_the_markup():
    """It must be opt-in from JS, never visible before the flag is checked."""
    tag = re.search(r'<div[^>]*id="onboarding-modal"[^>]*>', HTML).group(0)
    assert 'display:none' in tag.replace(' ', ''), tag[:200]
