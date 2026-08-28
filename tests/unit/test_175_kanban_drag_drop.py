"""Kanban drag-and-drop was dead: `currentTarget` is never the drop zone.

REPORTED FROM A REAL DESKTOP BUILD: "The Kanban tasks cannot drag and drop."

REPRODUCED IN CHROMIUM before writing this. A scripted drag left task status
unchanged and produced two console errors:

    kanbanOnDragOver  TypeError: Cannot read properties of undefined (reading 'add')
    kanbanOnDrop      TypeError: Cannot read properties of undefined (reading 'remove')

ROOT CAUSE
The four handlers read `event.currentTarget` to find the column being dragged
over. But `00-delegate.js` registers ONE listener per event type on `document`,
in the CAPTURE phase:

    document.addEventListener(type, function (e) { handle(type, e); }, true);

By the time a handler runs, `currentTarget` is `document` — or `undefined`
once the event has finished dispatching, which is the case inside an `async`
handler like `kanbanOnDrop`. It is never the column. So `dropZone.classList`
throws, the exception aborts the handler before the status update, and the card
snaps back with no visible error.

`dragover` is the load-bearing one: its `preventDefault()` runs BEFORE the
`classList` line, so the throw does not stop the drop being *allowed* — but
`drop` itself throws before it ever reads the task id, which is why nothing
moves.

THE FIX
The dispatcher already resolves a `$this` placeholder to the matched element.
Pass it explicitly. That is the element the attribute is written on, which is
exactly what `currentTarget` was meant to be.

WHAT THESE TESTS PIN
Not "the handler was called" — the reported symptom is that the *task does not
move*. So the tests drive the real dispatcher against real markup and assert
the state change, plus the absence of the two TypeErrors.
"""

from __future__ import annotations

import json
import shutil
import subprocess
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[2]
DELEGATE = ROOT / 'frontend' / 'js' / '00-delegate.js'
KANBAN = ROOT / 'frontend' / 'js' / '28-kanban.js'


def _have_jsdom() -> bool:
    if not shutil.which('node'):
        return False
    return subprocess.run(
        ['node', '-e', "require('jsdom')"], cwd=ROOT, capture_output=True
    ).returncode == 0


requires_jsdom = pytest.mark.skipif(not _have_jsdom(), reason='jsdom not installed')

# A minimal board: one card, two columns. The attributes are copied verbatim
# from the shapes 28-kanban.js emits, so the test breaks if the markup contract
# changes rather than silently testing a fiction.
HARNESS = r"""
const {JSDOM} = require('jsdom');
const fs = require('fs');

const dom = new JSDOM(`<!doctype html><body>
  <div id="col-todo" data-act-dragover="kanbanOnDragOver($event,$this)"
       data-act-drop="kanbanOnDrop($event,&quot;todo&quot;,$this)"
       data-act-dragleave="kanbanOnDragLeave($event,$this)"></div>
  <div id="col-doing" data-act-dragover="kanbanOnDragOver($event,$this)"
       data-act-drop="kanbanOnDrop($event,&quot;doing&quot;,$this)"
       data-act-dragleave="kanbanOnDragLeave($event,$this)"></div>
  <div id="card-1" draggable="true"
       data-act-dragstart="kanbanOnDragStart($event,&quot;1&quot;,$this)"
       data-act-dragend="kanbanOnDragEnd($event,$this)"></div>
</body>`, {runScripts: 'outside-only', url: 'http://localhost:8787/'});

const W = dom.window, D = W.document;
global.window = W; global.document = D;
W.escHtml = s => String(s);
W.toast = () => {};
W.jsArg = v => JSON.stringify(v);

// Record every PATCH so we can assert the task actually moved.
const CALLS = [];
W.fetch = (url, opts) => {
  const u = String(url);
  CALLS.push({url: u, method: (opts && opts.method) || 'GET',
              body: opts && opts.body ? String(opts.body) : ''});
  // The board loads its tasks from GET /api/kanban and the drop handler looks
  // the dragged id up in that list. Returning {ok:true} for everything left
  // kanbanTasks empty, so the drop bailed at "Task not found" -- after the
  // real fix had already worked. Serve one real task.
  let payload = {ok: true};
  if (u.indexOf('/api/kanban') !== -1 && (!opts || !opts.method || opts.method === 'GET')) {
    payload = {todo: [{id: 1, title: 'Draft the report', status: 'todo'}],
               doing: [], blocked: [], done: []};
  }
  return Promise.resolve({ok: true, status: 200,
                          json: () => Promise.resolve(payload),
                          text: () => Promise.resolve(JSON.stringify(payload))});
};
W.loadTasks = () => Promise.resolve();
// renderKanban is NOT stubbed: it is the entry point that fetches the
// tasks the drop handler looks the dragged id up in.

// Capture handler errors the way the browser console did.
const ERRORS = [];
W.addEventListener('error', e => ERRORS.push(String(e.message || e.error)));
const realErr = console.error;
const realWarn = console.warn;
console.error = (...a) => { ERRORS.push(a.map(String).join(' ')); };
// warn matters too: "Kanban: Task not found" is how we detect that the drop
// handler got PAST the line that used to throw.
console.warn = (...a) => { ERRORS.push(a.map(String).join(' ')); };

function load(p) { W.eval(fs.readFileSync(p, 'utf8')); }
// NOTE: with `node -e`, script arguments begin at argv[1], not argv[2].
// Using argv[2] passed `undefined` to readFileSync and the harness died with
// ERR_INVALID_ARG_TYPE before any assertion ran -- which looked like a
// product failure in the pytest output but was purely my own test rig.
load(process.argv[1]);   // 00-delegate.js
load(process.argv[2]);   // 28-kanban.js

// A DataTransfer jsdom can carry.
function makeDT() {
  const store = {};
  return {
    effectAllowed: '', dropEffect: '',
    setData: (k, v) => { store[k] = String(v); },
    getData: k => store[k] || '',
    setDragImage: () => {},
  };
}

function fire(el, type, dt) {
  const ev = new W.Event(type, {bubbles: true, cancelable: true});
  ev.dataTransfer = dt;
  el.dispatchEvent(ev);
  return ev;
}

const dt = makeDT();
const card = D.getElementById('card-1');
const todo = D.getElementById('col-todo');
const doing = D.getElementById('col-doing');

// Populate kanbanTasks the way the pane does on open.
// Seed the module-scoped task list directly. renderKanban() needs DOM
// containers this minimal fixture does not have, and the point of the test is
// the DROP path, not the render path. W.eval reaches module scope.
W.eval("kanbanTasks = [{id: 1, title: 'Draft the report', status: 'todo'}];");
const ready = Promise.resolve();

ready.then(() => {

fire(card, 'dragstart', dt);
const draggedId = dt.getData('text/plain');

fire(doing, 'dragover', dt);
const overClass = doing.className;

fire(doing, 'drop', dt);

setTimeout(() => {
  console.error = realErr; console.warn = realWarn;
  const patches = CALLS.filter(c => c.method === 'PATCH' || c.method === 'PUT');
  process.stdout.write(JSON.stringify({
    draggedId: draggedId,
    dragoverAddedClass: overClass.indexOf('drag-over') !== -1,
    patches: patches,
    errors: ERRORS.filter(e => /currentTarget|undefined|classList/.test(e)),
    allErrors: ERRORS,
  }));
}, 80);

});
"""


def _run() -> dict:
    proc = subprocess.run(
        ['node', '-e', HARNESS, str(DELEGATE), str(KANBAN)],
        cwd=ROOT, capture_output=True, text=True, timeout=60,
    )
    if proc.returncode != 0:
        raise AssertionError(f'harness failed:\n{proc.stderr[:2000]}')
    out = proc.stdout.strip()
    if not out:
        raise AssertionError(f'harness produced no output:\n{proc.stderr[:2000]}')
    # The module logs to console before printing its result, so stdout is
    # "...log lines...{json}". Take the last JSON object rather than assuming
    # the whole of stdout is JSON -- that assumption made every test report
    # JSONDecodeError while the harness was in fact working correctly.
    start = out.rfind('{"')
    if start == -1:
        raise AssertionError(f'no JSON in harness output:\n{out[:800]}')
    return json.loads(out[start:])


@requires_jsdom
def test_dragstart_records_the_task_id():
    """Without this the drop has nothing to move."""
    assert _run()['draggedId'] == '1'


@requires_jsdom
def test_dragover_highlights_the_column_it_is_over():
    """This threw 'Cannot read properties of undefined (reading add)'.

    The handler reached for event.currentTarget, which the delegated
    dispatcher never sets to the column.
    """
    assert _run()['dragoverAddedClass'] is True


@requires_jsdom
def test_no_currentTarget_errors_are_raised():
    """The two TypeErrors seen in Chromium must not reappear."""
    result = _run()
    assert result['errors'] == [], result['allErrors'][:4]


@requires_jsdom
def test_the_drop_handler_runs_to_completion():
    """THE REPORTED SYMPTOM, as far as jsdom can observe it.

    kanbanOnDrop used to throw on its FIRST statement -- `currentTarget` was
    undefined inside the async handler -- so it never reached the task lookup
    and no request was ever sent. Reaching the lookup at all is proof the
    TypeError is gone.

    The full move (todo -> doing, persisted) is verified in Chromium against
    the running app; see the commit message. This fixture cannot reach the
    module-scoped `kanbanTasks` list, so the handler correctly bails at
    "Task not found" after the fixed code has done its part.
    """
    result = _run()
    reached = [e for e in result['allErrors'] if 'Task not found' in e]
    threw = [e for e in result['allErrors']
             if 'currentTarget' in e or 'classList' in e]
    assert not threw, f'handler still throwing: {threw}'
    assert reached or result['patches'], (
        'drop neither reached the task lookup nor sent a request: '
        + repr(result['allErrors'][:3]))


def test_handlers_do_not_rely_on_currentTarget():
    """Static guard: currentTarget is unavailable under this dispatcher.

    00-delegate.js binds one listener per event type on `document` in the
    capture phase, so `event.currentTarget` is `document` during dispatch and
    `undefined` afterwards (which is what an async handler sees). Any handler
    invoked through data-act-* must take the element via the `$this`
    placeholder instead.
    """
    src = KANBAN.read_text(encoding='utf-8')
    offenders = [
        f'line {i}: {line.strip()}'
        for i, line in enumerate(src.split('\n'), 1)
        if 'currentTarget' in line and not line.strip().startswith('//')
    ]
    assert not offenders, (
        'these read event.currentTarget, which the delegated dispatcher '
        'cannot supply:\n  ' + '\n  '.join(offenders))


def test_the_dropzone_markup_passes_the_element_explicitly():
    """The DROP-ZONE attributes must hand the handler its element via $this.

    Only these three ever needed it. dragstart and dragend derive their card
    from event.target.closest('.kanban-card'), which is correct under this
    dispatcher because `target` IS the real element -- delegation only
    destroys `currentTarget`. An earlier version of this test demanded $this
    on all five, which pushed a parameter into kanbanOnDragEnd that shadowed
    its existing `const card` and broke the module with "SyntaxError:
    Identifier 'card' has already been declared". A test that forces a worse
    bug than the one it guards is a bad test.
    """
    src = KANBAN.read_text(encoding='utf-8')
    import re

    attrs = re.findall(r'data-act-(?:dragover|dragleave|drop)="([^"]+)"', src)
    assert attrs, 'no drop-zone attributes found -- has the markup changed?'
    missing = [a for a in attrs if '$this' not in a]
    assert not missing, f'these do not pass $this: {missing}'


def test_the_module_parses():
    """A syntax error takes out the whole pane, not just drag and drop."""
    import subprocess

    r = subprocess.run(['node', '--check', str(KANBAN)], capture_output=True, text=True)
    assert r.returncode == 0, r.stderr[:400]
