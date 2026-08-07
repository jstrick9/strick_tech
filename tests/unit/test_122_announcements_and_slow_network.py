"""Two more seams closed: screen-reader announcement, and slow/flaky networks.

FINDINGS
────────
**Slow network.** Everything until now tested two states -- server up, or a
hard 500. Real connections fail in messier ways, and those produce the worst
UI. With a 3s delay and with a body truncated mid-JSON:

    NO-PENDING  goals       blank for 3.0s with no loading state
    TRUNCATED   webhooks    "Unterminated string in JSON at position 29"
    TRUNCATED   workspaces  "Unterminated string in JSON at position 29"
    TRUNCATED   goals       renders 413 chars from a broken response,
                            saying nothing is wrong

The last one is the same class as the Kanban fabrication: a dropped connection
rendered as "No goals match these filters", so a user would reasonably
conclude their goals had been deleted.

**Announcements.** The app already announces navigation and toasts through a
live region, and dialogs by moving focus into a named `role=dialog`. Both were
verified working rather than assumed -- see the correction below.
"""

from __future__ import annotations

import re
from pathlib import Path

REPO = Path(__file__).resolve().parent.parent.parent
JS = REPO / 'frontend' / 'js'
AUDIT = REPO / 'scripts' / 'audit'


def _strip_comments(source: str) -> str:
    """So an assertion cannot be satisfied by the comment explaining it."""
    source = re.sub(r'/\*.*?\*/', '', source, flags=re.S)
    return re.sub(r'(?m)^\s*//.*$', '', source)


GOALS = _strip_comments((JS / '49-goals.js').read_text(encoding='utf-8'))
WEBHOOKS = _strip_comments((JS / '33-webhooks.js').read_text(encoding='utf-8'))
WORKSPACES = _strip_comments((JS / '30-workspaces.js').read_text(encoding='utf-8'))
SLOW_AUDIT = (AUDIT / 'slow_network.py').read_text(encoding='utf-8')
ANN_AUDIT = (AUDIT / 'announcements.py').read_text(encoding='utf-8')


# ──────────────────────────────────────────────────────────────────────
#  Slow network: the app
# ──────────────────────────────────────────────────────────────────────
def test_goals_shows_a_pending_state_before_awaiting():
    """A pane blank for 3s with no feedback is when users click again.

    That is how duplicate submissions get created -- the same failure the
    idempotency work in batch 37 had to clean up after.
    """
    body = GOALS[GOALS.index('async function renderGoals'):]
    body = body[:body.index('pane.innerHTML = `')]
    assert 'skeletonPage()' in body, 'no pending state before the first await'
    assert "setAttribute('aria-busy', 'true')" in body


def test_goals_clears_the_pending_state():
    """Leaving aria-busy set is its own bug: a screen reader would keep
    saying the region is updating forever."""
    assert "removeAttribute('aria-busy')" in GOALS


def test_goals_distinguishes_a_failed_load_from_an_empty_list():
    """`.catch(() => ({goals: []}))` made a dropped connection look exactly
    like "you have no goals"."""
    assert '_goalLoadError' in GOALS
    assert re.search(r'catch\(e\s*=>\s*\{\s*_goalLoadError\s*=\s*e', GOALS), (
        'the failure must be recorded, not swallowed')
    render = GOALS[GOALS.index('function gmRenderList'):]
    render = render[:render.index('_goalList.map')]
    assert 'if (_goalLoadError)' in render, (
        'the list must check for a load failure BEFORE rendering "no goals"')
    assert render.index('_goalLoadError') < render.index('No goals match'), (
        'saying "No goals match these filters" after a failed request is a '
        'lie the user cannot detect')


def test_truncated_responses_do_not_leak_parse_errors():
    """"Unterminated string in JSON at position 29" is a stack detail."""
    for name, code in (('33-webhooks.js', WEBHOOKS), ('30-workspaces.js', WORKSPACES)):
        assert 'humanError(' in code, f'{name} still shows the raw message'
        assert 'body:e.message' not in code.replace(' ', ''), (
            f'{name} passes the raw exception straight to the user')


def test_failed_loads_offer_a_retry():
    for name, code in (('33-webhooks.js', WEBHOOKS), ('30-workspaces.js', WORKSPACES)):
        assert 'Try again' in code, f'{name} gives the user no way forward'


# ──────────────────────────────────────────────────────────────────────
#  The audits must not be able to pass by measuring the wrong thing
# ──────────────────────────────────────────────────────────────────────
def test_slow_audit_does_not_block_the_driver_loop():
    """A sync route handler runs on Playwright's event loop.

    The first version used `time.sleep()` there and deadlocked the driver for
    eight minutes before being cancelled. The delay is now injected in the
    page.
    """
    # Check executable code, not prose: the docstring deliberately MENTIONS
    # time.sleep to explain why it is not used, and a naive substring test
    # therefore failed against correct code.
    code_only = re.sub(r'""".*?"""', '', SLOW_AUDIT, flags=re.S)
    code_only = re.sub(r'(?m)^\s*#.*$', '', code_only)
    assert 'time.sleep' not in code_only, (
        'blocking Playwright\'s event loop deadlocks the driver')
    assert 'setTimeout' in SLOW_AUDIT, 'the delay must be injected in the page'


def test_slow_audit_judges_only_the_headline():
    """Detail in trailing parentheses is the documented design.

    An earlier version flagged "Couldn't load your specs. Nothing was lost.
    (Unterminated string…)" as a raw parse error -- punishing the fix instead
    of finding a bug.
    """
    assert 'headline = re.sub(' in SLOW_AUDIT, (
        'parenthesised detail must be stripped before checking for leaks')
    assert "in headline" in SLOW_AUDIT, (
        'the leak check must run against the stripped headline, not the '
        'full text')


def test_slow_audit_only_falls_back_when_the_pane_is_hidden():
    """Falling back because a pane is EMPTY hides the thing being measured.

    With that fallback the host's content satisfied the "something is
    showing" check, and removing the goals skeleton produced no finding at
    all -- verified.
    """
    assert 'offsetParent === null' in SLOW_AUDIT
    section = SLOW_AUDIT[SLOW_AUDIT.index('let el = document.getElementById'):]
    section = section[:section.index('if (!el) return')]
    assert '!el.innerText.trim()' not in section, (
        'an empty pane must not trigger the visible-pane fallback')


def test_informational_lines_are_not_counted():
    """A '--' line records behaviour without failing the ratchet."""
    for audit in (SLOW_AUDIT, ANN_AUDIT):
        assert "not f.startswith('--')" in audit


def test_announcement_audit_checks_dialogs_by_focus_not_live_regions():
    """A screen reader announces a dialog when focus moves into it.

    The first version expected a live-region message and reported the command
    palette as SILENT -- wrong. Verified: opening it moves focus to
    #palette-input inside a dialog labelled "Command palette", which is the
    correct pattern.
    """
    assert 'DIALOG-NO-FOCUS' in ANN_AUDIT
    assert 'DIALOG-NO-NAME' in ANN_AUDIT
    assert 'focusInside' in ANN_AUDIT


def test_announcement_audit_watches_before_acting():
    """Observers installed after the action would miss the announcement."""
    assert 'MutationObserver' in ANN_AUDIT
    assert ANN_AUDIT.index('WATCH_JS') < ANN_AUDIT.index('ACTIONS = [')


def test_nav_and_toasts_still_announce():
    """Both are wired today; this pins them so a refactor cannot silently
    drop the only announcements the app makes."""
    a11y = _strip_comments((JS / '11-ux-accessibility.js').read_text(encoding='utf-8'))
    assert 'announceToScreenReader' in a11y
    assert 'Switched to' in a11y, 'navigation must announce the destination'
    index = (REPO / 'frontend' / 'index.html').read_text(encoding='utf-8')
    assert 'id="toast-container"' in index and 'aria-live' in index
