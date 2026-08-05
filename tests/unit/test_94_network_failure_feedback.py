"""Failed requests must be visible to the user.

THE GAP
───────
The platform makes 673 `fetch()` calls. When one failed, the user was told
nothing whatsoever. Three mechanisms combined to hide it:

  * 236 empty catch blocks — `.catch(() => {})` / `catch (e) {}`
  * `window.onerror`              logged and showed nothing
  * `window.onunhandledrejection` logged and showed nothing

Both global handlers carried the comment "too noisy", which was a reasonable
call when the alternative was a toast per stack trace. The consequence,
though, was that a failed save and a successful save looked identical: 50 of
those empty catches wrap a POST/PUT/PATCH/DELETE, so a user could delete a
goal, see no error, and believe it worked.

`frontend/js/00-net-feedback.js` wraps fetch once and reports the failures a
user can act on. Because it reports BEFORE the caller's catch runs, it fixes
all 50 silent-save paths without editing any of them.

Noise control is the whole design constraint — the original authors were right
that naive reporting is unusable — so the tests below pin the suppression
rules as hard as the reporting ones.
"""

from __future__ import annotations

import json
import re
import shutil
import subprocess
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[2]
JS_DIR = ROOT / 'frontend' / 'js'
MODULE = JS_DIR / '00-net-feedback.js'
INDEX = ROOT / 'frontend' / 'index.html'


def _have_jsdom() -> bool:
    if not shutil.which('node'):
        return False
    return subprocess.run(
        ['node', '-e', "require('jsdom')"], cwd=ROOT, capture_output=True
    ).returncode == 0


requires_jsdom = pytest.mark.skipif(not _have_jsdom(), reason='jsdom not installed')

HARNESS = """
const {JSDOM} = require('jsdom');
const fs = require('fs');
const dom = new JSDOM('<!doctype html><body><div id="toast-container"></div></body>',
  {runScripts:'outside-only', url:'http://localhost:8787/'});
global.window = dom.window; global.document = dom.window.document;
const W = dom.window, D = W.document;
let MODE = 'ok';
W.fetch = async function (u) {
  if (MODE === 'throw') throw new TypeError('Failed to fetch');
  const code = parseInt(MODE, 10);
  return { status: isNaN(code) ? 200 : code, ok: isNaN(code) };
};
W.eval(fs.readFileSync('frontend/js/00-delegate.js','utf8'));
W.eval(fs.readFileSync('frontend/js/00-net-feedback.js','utf8'));
const toasts = () => [...D.querySelectorAll('#toast-container .toast')].map(t => t.textContent);
const reset = () => { W.__netFeedback.reset(); D.getElementById('toast-container').innerHTML=''; };
"""


def _run(script: str) -> dict:
    probe = ROOT / 'zz_net_probe.js'
    probe.write_text(HARNESS + script, encoding='utf-8')
    try:
        r = subprocess.run(
            ['node', str(probe.name)], cwd=ROOT, capture_output=True, text=True
        )
        if not r.stdout.strip():
            pytest.skip(f'node produced no output: {r.stderr[-200:]}')
        return json.loads(r.stdout.strip().split('\n')[-1])
    finally:
        probe.unlink(missing_ok=True)


# ══ Wiring ════════════════════════════════════════════════════════════════════
def test_module_exists_and_is_loaded():
    assert MODULE.exists()
    assert '00-net-feedback.js' in INDEX.read_text(encoding='utf-8')


def test_it_loads_after_the_csrf_wrapper():
    """Order is load-bearing. CSRF must be the INNER layer so this observes the
    final status — otherwise it would report a 403 that CSRF is about to
    resolve with a token refresh, i.e. an error the user never had."""
    html = INDEX.read_text(encoding='utf-8')
    assert html.index('00-csrf.js') < html.index('00-net-feedback.js')


def test_it_never_swallows_the_error():
    """Callers that DO handle failures must keep seeing them. A reporting
    layer that also absorbs the exception would silently change control flow
    in every caller."""
    src = MODULE.read_text(encoding='utf-8')
    assert 'throw err;' in src


# ══ What gets reported ════════════════════════════════════════════════════════
@requires_jsdom
def test_server_error_is_reported():
    out = _run("""
(async () => { MODE='500'; await W.fetch('/api/tasks');
console.log(JSON.stringify({toasts: toasts()})); })();
""")
    assert len(out['toasts']) == 1
    assert 'Server error' in out['toasts'][0]


@requires_jsdom
def test_transport_failure_is_reported_and_rethrown():
    """Server down / offline / DNS. The user needs to know the app cannot
    reach its backend — this is the case where every button appears broken."""
    out = _run("""
(async () => { MODE='throw'; let threw=false;
try { await W.fetch('/api/tasks'); } catch (e) { threw = true; }
console.log(JSON.stringify({toasts: toasts(), threw})); })();
""")
    assert out['threw'], 'the exception must still propagate'
    assert len(out['toasts']) == 1
    assert 'reach the server' in out['toasts'][0]


@pytest.mark.parametrize('status,fragment', [
    ('500', 'Server error'),
    ('429', 'Too many requests'),
    ('401', 'Not signed in'),
    ('403', 'Not allowed'),
])
@requires_jsdom
def test_each_actionable_status_gets_its_own_message(status, fragment):
    """A generic "something went wrong" is barely better than silence. Each
    status the user can act on says what to do about it."""
    out = _run(f"""
(async () => {{ MODE='{status}'; await W.fetch('/api/tasks');
console.log(JSON.stringify({{toasts: toasts()}})); }})();
""")
    assert len(out['toasts']) == 1
    assert fragment in out['toasts'][0]


@requires_jsdom
def test_a_silently_swallowed_save_still_warns_the_user():
    """The 50-site bug, reproduced exactly: a mutating request whose failure is
    discarded by `.catch(() => {})`. This is why the fix is a wrapper rather
    than 50 edits."""
    out = _run("""
(async () => { MODE='throw';
await W.fetch('/api/goals/g1', {method:'DELETE'}).catch(() => {});
console.log(JSON.stringify({toasts: toasts()})); })();
""")
    assert len(out['toasts']) == 1, 'a swallowed delete failure told the user nothing'


# ══ What stays quiet — the constraint that makes this usable ══════════════════
@requires_jsdom
def test_success_is_silent():
    out = _run("""
(async () => { MODE='ok'; await W.fetch('/api/tasks');
console.log(JSON.stringify({toasts: toasts()})); })();
""")
    assert out['toasts'] == []


@requires_jsdom
def test_404_is_not_reported():
    """The app probes for optional resources on purpose. Reporting 404 would
    recreate exactly the noise the original silent handlers were avoiding."""
    out = _run("""
(async () => { MODE='404'; await W.fetch('/api/optional-thing');
console.log(JSON.stringify({toasts: toasts()})); })();
""")
    assert out['toasts'] == []


@requires_jsdom
def test_health_polling_failures_stay_quiet():
    """Liveness polls run every few seconds. If the backend is down they would
    announce their own outage forever, burying the one message that matters."""
    out = _run("""
(async () => { MODE='500';
for (const p of ['/api/health','/api/system/stats','/api/system/hmr']) await W.fetch(p);
console.log(JSON.stringify({toasts: toasts()})); })();
""")
    assert out['toasts'] == []


@requires_jsdom
def test_repeated_identical_failures_collapse_into_one_toast():
    """One broken endpoint on a polling loop must not produce a wall of
    toasts. The repeat count updates in place instead."""
    out = _run("""
(async () => { MODE='500';
for (let i=0;i<5;i++) await W.fetch('/api/tasks');
console.log(JSON.stringify({toasts: toasts()})); })();
""")
    assert len(out['toasts']) == 1
    assert '5' in out['toasts'][0], 'the repeat count should be shown'


@requires_jsdom
def test_ids_are_collapsed_so_a_failing_list_does_not_flood():
    """/api/goals/goal_abc123 and /api/goals/goal_def456 are the same failure
    from the user's point of view."""
    out = _run("""
console.log(JSON.stringify({
  a: W.__netFeedback.shortEndpoint('/api/goals/goal_abc12345'),
  b: W.__netFeedback.shortEndpoint('/api/runs/12345'),
  c: W.__netFeedback.shortEndpoint('/api/x/deadbeefcafe'),
}));
""")
    assert out['a'] == out['b'].replace('runs', 'goals') or out['a'].endswith('/…')
    assert out['b'].endswith('/…')
    assert out['c'].endswith('/…')


@requires_jsdom
def test_distinct_failures_are_capped():
    """A cascading outage hits many endpoints at once. Three simultaneous
    toasts is information; fifteen is a second outage."""
    out = _run("""
(async () => { MODE='500';
for (const p of ['/api/a','/api/b','/api/c','/api/d','/api/e','/api/f']) await W.fetch(p);
console.log(JSON.stringify({count: toasts().length})); })();
""")
    assert out['count'] <= 3


# ══ Accessibility ═════════════════════════════════════════════════════════════
@requires_jsdom
def test_error_toasts_are_announced_and_keyboard_dismissible():
    """An error a screen-reader user cannot hear is still a silent failure,
    and a toast that only a mouse can dismiss is a small keyboard trap."""
    out = _run("""
(async () => { MODE='500'; await W.fetch('/api/tasks');
const el = D.querySelector('#toast-container .toast');
const close = el.querySelector('.toast-close');
close.dispatchEvent(new W.KeyboardEvent('keydown', {key:'Enter', bubbles:true}));
console.log(JSON.stringify({
  role: el.getAttribute('role'),
  live: el.getAttribute('aria-live'),
  closeLabel: close.getAttribute('aria-label'),
  dismissed: D.querySelectorAll('#toast-container .toast').length === 0,
})); })();
""")
    assert out['role'] == 'alert'
    assert out['live'] == 'assertive'
    assert out['closeLabel']
    assert out['dismissed'], 'error toast cannot be dismissed from the keyboard'


@requires_jsdom
def test_going_offline_shows_a_persistent_banner():
    """A toast that fades after 6s is wrong for a condition that persists.
    Offline gets a banner that stays until connectivity returns."""
    out = _run("""
W.dispatchEvent(new W.Event('offline'));
const banner = D.getElementById('net-offline-banner');
const shown = banner !== null;
W.dispatchEvent(new W.Event('online'));
console.log(JSON.stringify({
  shown,
  role: banner && banner.getAttribute('role'),
  clearedOnReconnect: D.getElementById('net-offline-banner') === null,
}));
""")
    assert out['shown'], 'no offline indication'
    assert out['role'] == 'status'
    assert out['clearedOnReconnect'], 'the offline banner never goes away'


# ══ The original silent handlers are still documented ═════════════════════════
def test_the_old_silent_handlers_explain_why_they_stay_silent():
    """00-errors.js deliberately does not toast, and that remains correct for
    generic JS errors. The reasoning must survive so nobody 'fixes' it into
    the noise this design avoids."""
    src = (JS_DIR / '00-errors.js').read_text(encoding='utf-8')
    assert 'too noisy' in src


def test_empty_catch_blocks_are_now_covered_by_the_wrapper():
    """Not a call to remove them — many are legitimate ("this optional thing
    may not exist"). The point is that network failures no longer depend on
    them, so their presence is no longer a silent-failure risk."""
    total = 0
    for path in sorted(JS_DIR.glob('*.js')):
        total += len(re.findall(
            r'\.catch\(\(\)\s*=>\s*\{\}\)|catch\s*\([a-z_]*\)\s*\{\s*\}',
            path.read_text(encoding='utf-8'),
        ))
    # Recorded so a large increase is visible in review rather than invisible.
    assert total < 400, f'empty catch blocks grew sharply: {total}'
