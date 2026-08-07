"""An outage must never look like "you have nothing", and never like fake data.

THE FINDINGS
────────────
Driven by a live probe that forced every `/api/` call to return HTTP 500 and
then walked the panes.

1. **Kanban fabricated tasks.** `kanbanFetchTasks()` fell back to
   `kanbanGetSampleTasks()` on BOTH the non-ok branch and the catch. With the
   API down the board rendered "6 tasks" of invented work. A user could drag,
   edit or delete cards that do not exist, and would reasonably believe real
   tasks had been lost. This is the worst class of the bug: not merely
   unhelpful, actively misleading.

2. **334 fetch sites across 33 files** resolve failure to an empty collection
   (`r.ok ? r.json() : {goals: []}`). Individually defensible; collectively
   they make a server outage indistinguishable from an empty account.
   Verified: Goals, Skills and Loops all rendered calm, normal-looking empty
   states with nothing to suggest the data was simply missing.

3. **A delete with no confirmation.** `deleteHistoryEntry()` removed a search
   on one click, with no prompt and no undo, while every other delete in the
   app confirms first.

THE FIXES
─────────
Kanban reports the failure and offers a retry. A transport-level watcher
(`00-connection-status.js`) shows one app-wide banner when API failures
cluster, which covers all 334 sites and every pane added later without
touching a single render path. The delete now confirms.
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


KANBAN = _strip_comments((JS / '28-kanban.js').read_text(encoding='utf-8'))
CONN = _strip_comments((JS / '00-connection-status.js').read_text(encoding='utf-8'))
CSRF = _strip_comments((JS / '00-csrf.js').read_text(encoding='utf-8'))
WEBSEARCH = _strip_comments((JS / '44-websearch.js').read_text(encoding='utf-8'))
INDEX = (REPO / 'frontend' / 'index.html').read_text(encoding='utf-8')


# ──────────────────────────────────────────────────────────────────────
#  1. No fabricated data, anywhere
# ──────────────────────────────────────────────────────────────────────
def test_kanban_no_longer_fabricates_tasks_on_failure():
    """The board must not invent work when the API is down."""
    assert 'kanbanGetSampleTasks' not in KANBAN, (
        'the sample-task generator is back; a failed load must not render '
        'invented tasks as though they were the user\'s real ones')


def test_kanban_records_and_surfaces_the_load_error():
    assert 'kanbanLoadError' in KANBAN
    # The failure path must clear the list rather than leave stale content.
    assert re.search(r'catch[^{]*\{[^}]*kanbanTasks\s*=\s*\[\]', KANBAN, re.S), (
        'a failed load must empty the task list, not keep whatever was there')
    assert "role=\"alert\"" in KANBAN or "role='alert'" in KANBAN, (
        'the failure message must be announced, not only shown')


def test_kanban_failure_message_reassures_and_offers_retry():
    """Wording matters here: the screen has just gone empty.

    A user seeing an empty board needs to know their work still exists. "No
    tasks" would be a lie; a bare error code would be alarming.
    """
    assert 'renderKanban()' in KANBAN, 'the failure state needs a retry action'
    lowered = KANBAN.lower()
    assert 'safe' in lowered or 'connection problem' in lowered, (
        'tell the user their data is not lost')


def test_no_module_substitutes_sample_data_on_a_failure_path():
    """Guard the whole pattern, not just the one instance that was found."""
    suspicious = re.compile(r'(getSample|sampleData|mockData|demoData|'
                            r'fallbackTasks|placeholderData)\w*\s*\(')
    offenders = []
    for path in sorted(JS.glob('*.js')):
        code = _strip_comments(path.read_text(encoding='utf-8'))
        for match in suspicious.finditer(code):
            # Only care when it sits on an error path.
            window = code[max(0, match.start() - 400):match.start()]
            if 'catch' in window or re.search(r'\.ok\b[^{]*\{[^}]*$', window, re.S):
                offenders.append(f'{path.name}: {match.group(0)}')
    assert not offenders, f'fabricated data on a failure path: {offenders}'


# ──────────────────────────────────────────────────────────────────────
#  2. The global connection banner
# ──────────────────────────────────────────────────────────────────────
def test_connection_watcher_is_loaded_before_the_fetch_wrapper():
    """It must be defined before 00-csrf.js, which reports into it."""
    assert '00-connection-status.js' in INDEX
    assert INDEX.index('00-connection-status.js') < INDEX.index('00-csrf.js'), (
        'the watcher must exist before the fetch wrapper starts reporting')


def test_the_banner_complements_the_transient_toasts():
    """Why a banner when 00-net-feedback.js already toasts on 5xx?

    Because those toasts auto-dismiss after 6 seconds. Measured against a
    live server with every API returning 500: ten seconds later the Skills
    pane read "All (0)" with no toast left and nothing on screen indicating
    a failure -- indistinguishable from an account with no skills. The
    toasts tell you at the moment it happens; the banner is what is still
    there when you look up.

    They are deliberately different channels: transient per-request detail
    versus a persistent, dismissible "things are broken right now" state.
    """
    feedback = _strip_comments((JS / '00-net-feedback.js').read_text(encoding='utf-8'))
    assert '6000' in feedback, (
        'if the toasts became persistent, this banner would be redundant '
        'and should be reconsidered')
    assert 'snoozedUntil' in CONN, 'the banner must persist until dismissed'


def test_watcher_requires_clustered_failures_not_a_single_one():
    """One failed endpoint is normal; shouting about it trains users to ignore
    the banner entirely."""
    assert 'THRESHOLD' in CONN
    threshold = int(re.search(r'THRESHOLD\s*=\s*(\d+)', CONN).group(1))
    assert threshold >= 2, 'a single failure must not raise the banner'


def test_watcher_ignores_routinely_absent_endpoints():
    """`/api/secrets/get` 404s constantly when a key is simply not configured."""
    assert '/api/secrets/get' in CONN


def test_watcher_only_counts_server_side_failures():
    """A 404 usually means the client asked for something that isn't there.

    Counting those would fire the banner during ordinary use.
    """
    assert 'status >= 500' in CONN
    assert '429' in CONN and '408' in CONN, (
        'rate limiting and timeouts are retryable and should count')


def test_watcher_resets_on_success():
    """Unrelated failures spread over hours must not accumulate into a false
    alarm."""
    assert re.search(r'response\.ok[^}]*clearFailures\(\)', CONN, re.S), (
        'a successful response should clear the failure tally')


def test_the_watcher_did_not_add_a_third_fetch_wrapper():
    """The app already layers two fetch wrappers, by design and documented:
    00-csrf.js attaches tokens, then 00-net-feedback.js reports failures on
    top of it. Each is marked `intentional-override` for lint_globals.py.

    The first version of the connection watcher added a THIRD, which the
    duplicate-globals linter caught. Rather than deepen a chain where load
    order silently decides behaviour, the watcher now exposes hooks that an
    existing wrapper calls.
    """
    pattern = re.compile(r'(?m)^\s*window\.fetch\s*=')
    owners = [f.name for f in sorted(JS.glob('*.js'))
              if pattern.search(_strip_comments(f.read_text(encoding='utf-8')))]
    assert owners == ['00-csrf.js', '00-net-feedback.js'], (
        f'unexpected set of fetch wrappers: {owners}')
    assert '00-connection-status.js' not in owners


def test_the_single_fetch_wrapper_reports_to_the_watcher():
    assert 'observeResponse' in CSRF, (
        'the fetch wrapper must tell the watcher about responses')
    assert 'observeNetworkError' in CSRF, (
        'network-level failures must be reported too')
    assert 'throw err;' in CSRF, 'network errors must still reach the caller'


def test_watcher_observation_cannot_break_a_request():
    """A bug inside the watcher must never take down an API call."""
    assert CSRF.count('try { window.connectionStatus') == 2, (
        'both observation hooks must be guarded so a watcher error cannot '
        'propagate into the request path')


def test_banner_retry_rerenders_rather_than_reloading():
    """A full reload would discard whatever the user had typed."""
    assert 'window.nav(pane)' in CONN
    assert 'location.reload()' in CONN, 'reload is the fallback, not the default'
    assert CONN.index('window.nav(pane)') < CONN.index('location.reload()')


def test_banner_can_be_dismissed_and_stays_quiet():
    assert 'snoozedUntil' in CONN
    assert 'Dismiss connection warning' in CONN, (
        'the icon-only dismiss button needs an accessible name')


def test_banner_is_announced_politely():
    """`alert` would interrupt a screen-reader user mid-sentence; the app is
    still usable, so `status` is correct."""
    assert "setAttribute('role', 'status')" in CONN
    assert "aria-live" in CONN


# ──────────────────────────────────────────────────────────────────────
#  3. Destructive action confirmation
# ──────────────────────────────────────────────────────────────────────
def test_delete_history_entry_confirms_first():
    body = WEBSEARCH[WEBSEARCH.index('function deleteHistoryEntry'):]
    body = body[:body.index('\n}')]
    assert 'gmDanger' in body, (
        'deleting a history entry removed it on one click with no prompt and '
        'no undo, unlike every other delete in the app')
    assert body.index('gmDanger') < body.index('fetch('), (
        'the confirmation must come before the request')
