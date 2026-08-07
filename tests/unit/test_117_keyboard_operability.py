"""Anything clickable must be operable from a keyboard.

THE FINDING
───────────
Walking all 68 panes and counting elements that carry `data-act-click` but are
neither a native control nor given `tabindex`/`role`:

    884  DIV.agent-row
      6  DIV (anonymous)
      3  DIV.file-row
      1  DIV.sdk-pack-card
      1  STRONG

`.agent-row` is how you choose which agent to chat with — a core interaction,
mouse-only. Unreachable by Tab, not announced as a control by screen readers,
and inoperable by keyboard, switch or voice input.

THE FIX
───────
`00-delegate.js` now promotes any non-native `data-act-click` element to
`tabindex="0"` + `role="button"`, and activates it on Enter/Space. Applied
centrally rather than at ~890 render sites: a rule applied at one call site is
a rule the next call site forgets — the "second door" pattern this review has
hit repeatedly. A MutationObserver re-applies after renders, because panes
rebuild their innerHTML constantly.

TWO EXCLUSIONS THAT MATTER
──────────────────────────
* **Native controls.** A `<button>` already turns Enter and Space into a real
  click; adding a synthetic one fires the handler TWICE per key press. This
  exact bug shipped once before (see the `data-self-click` note in
  00-delegate.js), so it is asserted here rather than assumed.
* **Modal backdrops** (`data-click-self="1"`). They use `data-act-click` for
  click-outside-to-close. They are not controls, and making them tab stops
  would put a focus ring on the dimmed background of every dialog.
"""

from __future__ import annotations

import re
from pathlib import Path

REPO = Path(__file__).resolve().parent.parent.parent
JS = REPO / 'frontend' / 'js'


def _strip_comments(source: str) -> str:
    """So an assertion cannot be satisfied by the comment explaining it."""
    source = re.sub(r'/\*.*?\*/', '', source, flags=re.S)
    return re.sub(r'(?m)^\s*//.*$', '', source)


DELEGATE = _strip_comments((JS / '00-delegate.js').read_text(encoding='utf-8'))


def test_delegate_promotes_non_native_clickables():
    assert 'makeKeyboardOperable' in DELEGATE
    assert "setAttribute('tabindex', '0')" in DELEGATE, (
        'clickable divs must become tab stops')
    assert "setAttribute('role', 'button')" in DELEGATE, (
        'they must also be announced as controls, not just focusable')


def test_native_controls_are_excluded_from_promotion():
    """A <button> already handles Enter/Space; a synthetic click double-fires.

    This is not hypothetical -- 92-pane-error-boundary.js shipped with exactly
    this bug when the older `data-self-click` polyfill was applied
    mechanically.
    """
    body = DELEGATE[DELEGATE.index('function makeKeyboardOperable'):]
    body = body[:body.index('\n  }')]
    assert 'NATIVELY_CLICKABLE.test(el.tagName)' in body, (
        'native controls must be skipped or they fire twice per key press')


def test_keyboard_activation_skips_native_controls_too():
    """The keydown handler must also ignore natives, not just the promoter."""
    handler = DELEGATE[DELEGATE.index("if (event.key !== 'Enter' && event.key !== ' '"):]
    handler = handler[:handler.index('\n  });')]
    assert 'NATIVELY_CLICKABLE.test(el.tagName)' in handler
    assert "getAttribute('role') !== 'button'" in handler, (
        'only elements this module promoted should be synthetically activated')


def test_modal_backdrops_do_not_become_tab_stops():
    """Backdrops use data-act-click for click-outside-to-close.

    Promoting them would put a focus ring on the dimmed background of every
    modal and add a meaningless stop to the tab order.
    """
    body = DELEGATE[DELEGATE.index('function makeKeyboardOperable'):]
    body = body[:body.index('\n  }')]
    assert "getAttribute('data-click-self') === '1'" in body


def test_existing_tabindex_and_roles_are_respected():
    """Author intent wins; this should only fill gaps."""
    body = DELEGATE[DELEGATE.index('function makeKeyboardOperable'):]
    body = body[:body.index('\n  }')]
    assert "hasAttribute('tabindex')" in body
    assert "role !== 'button'" in body, (
        'an element already given a role (tab, menuitem, link) must be left '
        'alone rather than relabelled a button')


def test_promotion_reapplies_after_renders():
    """Panes rebuild innerHTML constantly; a one-shot pass covers nothing."""
    assert 'MutationObserver' in DELEGATE
    assert 'queueUpgrade' in DELEGATE
    assert 'upgradeQueued' in DELEGATE, (
        'the mutation burst from a single render must coalesce into one pass')


def test_promotion_cannot_break_a_render():
    """A failure inside the upgrade must never propagate into app code."""
    section = DELEGATE[DELEGATE.index('function queueUpgrade'):]
    section = section[:section.index('\n  }')]
    assert 'try {' in section and 'catch' in section


def test_space_and_enter_are_both_handled():
    handler = DELEGATE[DELEGATE.index("if (event.key !== 'Enter' && event.key !== ' '"):]
    handler = handler[:handler.index('\n  });')]
    assert 'preventDefault' in handler, (
        'Space scrolls the page by default and Enter may submit a form')


def test_no_render_site_needs_to_opt_in():
    """The fix must be centralised, or the 891st clickable div will regress.

    Asserted by checking the promoter is driven by a selector over the whole
    document rather than an explicit allow-list of classes.
    """
    assert "KEYBOARDABLE_SELECTOR = '[data-act-click]'" in DELEGATE
    assert 'agent-row' not in DELEGATE, (
        'the fix should be generic, not a list of the classes that happened '
        'to be broken today')


def test_self_click_elements_are_not_activated_twice():
    """Elements carrying BOTH `data-self-click` and `role=button`.

    The older shim in this same file already re-dispatches a real click on
    Enter/Space for `data-self-click="1"`. Activating them again here ran the
    handler twice for a single key press. Caught by
    tests/unit/test_93_keyboard_accessibility.py, which asserts exactly one
    invocation for `div[role=button][data-self-click]`.
    """
    handler = DELEGATE[DELEGATE.index("if (event.key !== 'Enter' && event.key !== ' '"):]
    handler = handler[:handler.index('\n  });')]
    assert "getAttribute('data-self-click') === '1'" in handler, (
        'the new keydown path must defer to the existing self-click shim')
