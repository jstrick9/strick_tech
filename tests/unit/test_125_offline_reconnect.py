"""Going offline, and coming back.

THE DEFECT
──────────
Three independent `window.addEventListener('offline', …)` handlers each raised
their own message, and all three were on screen at the same moment. Measured
in a real Chromium with `context.set_offline(True)`:

    ⚠️ You are offline — local features still work          (01-app-core.js)
    Some data couldn't load. Your work is safe — this        (00-connection-status.js)
      looks like a connection problem.
    ⚠ You are offline — changes will not be saved until      (00-net-feedback.js)
      the connection returns.

"Your work is safe" and "changes will not be saved" are **opposite advice about
the same event**, presented simultaneously with equal authority. A user with
unsaved work cannot act on that. This is recurring pattern #4 in this review —
the same behaviour implemented at several call sites — showing up in the UI
layer rather than the security layer.

The fix gives offline state ONE owner. `00-net-feedback.js` keeps the banner,
because its message is the accurate one. The other two stand down: app-core
now only colours the status dot (a job nothing else does), and
connection-status actively hides itself while the browser reports no network,
because "your work is safe" is right for a cluster of 5xx and wrong for
offline.

WHY THE REDUNDANCY WAS ALSO A MEASUREMENT PROBLEM
─────────────────────────────────────────────────
Disabling one handler entirely left the audit reporting **clean**, because two
others still spoke. Three overlapping owners meant no single one could be
proven necessary. Only after consolidation could the probe be shown to fail
when the remaining owner was removed — which is the evidence that it measures
anything at all.
"""

from __future__ import annotations

import json
import re
from pathlib import Path

REPO = Path(__file__).resolve().parent.parent.parent
JS = REPO / 'frontend' / 'js'
AUDIT = REPO / 'scripts' / 'audit'


def _strip_comments(source: str) -> str:
    """So an assertion cannot be satisfied by the comment explaining the fix.

    This has caught a test asserting its own fix comment eleven times.
    """
    source = re.sub(r'/\*.*?\*/', '', source, flags=re.S)
    return re.sub(r'(?m)^\s*//.*$', '', source)


APP_CORE = _strip_comments((JS / '01-app-core.js').read_text(encoding='utf-8'))
CONN = _strip_comments((JS / '00-connection-status.js').read_text(encoding='utf-8'))
NETFB = _strip_comments((JS / '00-net-feedback.js').read_text(encoding='utf-8'))


# ──────────────────────────────────────────────────────────────────────
#  One owner for offline state
# ──────────────────────────────────────────────────────────────────────
def test_only_one_module_shows_an_offline_message():
    """Three modules announced the same event with three different messages."""
    announcers = []
    if re.search(r"offline[^\n]*local features still work", APP_CORE):
        announcers.append('01-app-core.js')
    if 'showOffline' in NETFB:
        announcers.append('00-net-feedback.js')

    assert announcers == ['00-net-feedback.js'], (
        f'expected exactly one owner of the offline message, found {announcers}')


def test_app_core_offline_handler_does_not_toast():
    """It kept the status dot -- the one job nothing else does -- and lost the
    toast that duplicated the banner.

    UPDATED, NOT DELETED. The original version sliced from `const
    offlineHandler` to the next `};` and asserted `sb-dot` appeared inside.
    That held while the handler was an inline arrow body; a later batch
    extracted the shared `setDot()` helper (so that going offline updates the
    dot's aria-label as well as its colour, for forced-colors mode), and the
    handler became a one-line delegation. The BEHAVIOUR is unchanged and
    still correct, but the assertion was pinned to the old shape.

    It now checks the pair that actually matters: the dot is still updated
    somewhere in this module, and the offline handler still raises no toast.
    """
    assert 'sb-dot' in APP_CORE, 'the status dot must still be updated'

    handler = APP_CORE[APP_CORE.index('const offlineHandler'):]
    handler = handler[:handler.index('\n')]
    assert 'toast(' not in handler, (
        'app-core must not raise its own offline toast; 00-net-feedback.js '
        'owns that message')

    # The helper it delegates to must not toast either, or the message is
    # simply one indirection further away.
    helper = APP_CORE[APP_CORE.index('const setDot'):]
    helper = helper[:helper.index('};')]
    assert 'toast(' not in helper


def test_connection_banner_stands_down_while_offline():
    """"Your work is safe" is correct for a cluster of 5xx and WRONG for
    offline, where unsaved work is exactly what is at risk."""
    assert 'browserOffline' in CONN
    offline_handler = CONN[CONN.index("addEventListener('offline'"):]
    offline_handler = offline_handler[:offline_handler.index('});')]
    assert 'browserOffline = true' in offline_handler
    assert 'hide()' in offline_handler, (
        'going offline must hide this banner, not raise it')
    assert 'show()' not in offline_handler, (
        'this module must not raise its own banner while offline')


def test_going_back_online_re_enables_the_connection_banner():
    """Standing down must be temporary, or a genuine post-reconnect outage
    would go unreported for the rest of the session."""
    online_handler = CONN[CONN.index("addEventListener('online'"):]
    online_handler = online_handler[:online_handler.index('});')]
    assert 'browserOffline = false' in online_handler


def test_record_respects_the_offline_suppression():
    """The guard has to be in record(), not only in the listener: failures
    keep arriving while offline and would otherwise cross the threshold."""
    record = CONN[CONN.index('function record('):]
    record = record[:record.index('\n  }')]
    assert 'browserOffline' in record, (
        'record() must not raise the banner while the browser is offline')


def test_the_offline_banner_says_work_is_not_saved():
    """The surviving message must be the accurate one. Losing the honest
    warning and keeping a reassuring one would be a regression that still
    passes the "only one owner" test above."""
    assert re.search(r'will not be saved|not be saved', NETFB), (
        'the offline banner must warn that changes are not being saved')


# ──────────────────────────────────────────────────────────────────────
#  The probe that found this
# ──────────────────────────────────────────────────────────────────────
def test_the_audit_scopes_to_status_surfaces():
    """The probe's first bug: searching all visible text for /offline/ matched
    `Private • Ollama • Offline`, a product feature label. That produced a
    false RECONNECT finding -- and, far worse, would have let a total absence
    of offline reporting pass the GOING-OFFLINE check.
    """
    src = (AUDIT / 'offline_reconnect.py').read_text(encoding='utf-8')
    assert 'STATUS_SELECTOR' in src
    assert 'net-offline-banner' in src
    assert 'Ollama' in src, 'record why whole-document text is not used'


def test_the_audit_checks_for_contradiction():
    """Counting distinct messages is what caught this; a presence check alone
    reported clean."""
    src = (AUDIT / 'offline_reconnect.py').read_text(encoding='utf-8')
    assert 'CONTRADICTORY' in src


def test_the_audit_uses_real_offline_not_a_route_error():
    """set_offline also flips navigator.onLine and fires the offline/online
    events, which is the code path the app actually listens on. Faking it at
    the route layer would test different code."""
    src = (AUDIT / 'offline_reconnect.py').read_text(encoding='utf-8')
    assert 'set_offline' in src


def test_the_audit_is_registered():
    src = (AUDIT / 'run_all.py').read_text(encoding='utf-8')
    assert 'offline_reconnect' in src
    ratchet = (REPO / 'tests' / 'unit' / 'test_120_audit_ratchet.py').read_text(
        encoding='utf-8')
    assert 'offline-reconnect' in ratchet
    baseline = json.loads((AUDIT / 'baseline.json').read_text(encoding='utf-8'))
    assert baseline.get('offline-reconnect') == 0
