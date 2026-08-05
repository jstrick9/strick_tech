"""Database Studio's row insert must not silently discard columns.

TWO BUGS IN ONE FUNCTION
────────────────────────
1. `cols.slice(0, 5)` capped the insert at five columns and dropped the rest
   with no message. Real tables in this very database: `goals_v2` has 23
   columns, `agents` 12, `tasks` 11 — so on most tables the majority of the
   record was discarded. If any dropped column is NOT NULL the insert then
   fails with a raw SQL error the user cannot act on; if they are all
   nullable it "succeeds" and writes a mostly-empty row.

2. Five sequential blocking prompts, one per column: no view of the whole
   record, no way back, and cancelling on the fourth threw away the first
   three.

Replaced with a single form showing every column, using the `notnull` and
`type` metadata the API already returned and the old flow ignored.
"""

from __future__ import annotations

import json
import shutil
import subprocess
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[2]
MODULE = ROOT / 'frontend' / 'js' / '17-database-studio.js'


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
const W = dom.window, D = W.document;
global.window = W; global.document = D;
W.escHtml = s => String(s).replace(/[&<>"']/g,
  c => ({'&':'&amp;','<':'&lt;','>':'&gt;','"':'&quot;',"'":'&#39;'}[c]));
W.jsArg = v => JSON.stringify(v).replace(/&/g,'&amp;').replace(/"/g,'&quot;');
W.__toasts = [];
W.toast = m => W.__toasts.push(m);
W.dbLoadTable = () => {};
W.eval(fs.readFileSync('frontend/js/00-delegate.js','utf8'));
const src = fs.readFileSync('frontend/js/17-database-studio.js','utf8');
W.eval(src.slice(src.indexOf('async function dbInsertRow'),
                 src.indexOf('async function dbDeleteRow')));
function wideTable() {
  const cols = [{name:'title',type:'TEXT',notnull:true},
                {name:'description',type:'TEXT'},
                {name:'priority',type:'INTEGER'}];
  for (let i = 0; i < 20; i++) cols.push({name:'extra'+i, type:'TEXT'});
  return cols;
}
"""


def _run(script: str) -> dict:
    probe = ROOT / 'zz_dbinsert_probe.js'
    probe.write_text(HARNESS + script, encoding='utf-8')
    try:
        r = subprocess.run(
            ['node', str(probe.name)], cwd=ROOT, capture_output=True, text=True
        )
        if not r.stdout.strip():
            pytest.skip(f'node produced no output: {r.stderr[-300:]}')
        return json.loads(r.stdout.strip().split('\n')[-1])
    finally:
        probe.unlink(missing_ok=True)


def test_the_five_column_cap_is_gone():
    """The whole bug in one line. goals_v2 has 23 columns.

    Comments are stripped first: the replacement documents the old
    `cols.slice(0, 5)` so the reasoning survives, and matching against the raw
    file would flag that explanation as the bug — the "assertions matching
    their own fix comments" trap this review has now hit seven times.
    """
    code = '\n'.join(
        line for line in MODULE.read_text(encoding='utf-8').split('\n')
        if not line.lstrip().startswith(('//', '*', '/*'))
    )
    assert 'cols.slice(0,5)' not in code.replace(' ', '')


@requires_jsdom
def test_every_column_is_offered():
    out = _run("""
W.dbShowInsertForm('goals_v2', wideTable());
const m = D.getElementById('db-insert-modal');
console.log(JSON.stringify({fields: m.querySelectorAll('[data-col]').length}));
""")
    assert out['fields'] == 23, (
        f"only {out['fields']} of 23 columns offered — data would be lost"
    )


@requires_jsdom
def test_required_columns_are_marked_and_enforced():
    """NOT NULL was in the API response all along and the old flow ignored it,
    so the user found out via a raw SQL error."""
    out = _run("""
W.dbShowInsertForm('goals_v2', wideTable());
const m = D.getElementById('db-insert-modal');
const marked = m.querySelectorAll('[title="Required"]').length;
W.fetch = async () => ({ok:true, json: async () => ({ok:true})});
W.dbSubmitInsertForm('goals_v2');
setTimeout(() => console.log(JSON.stringify({
  marked,
  toasts: W.__toasts,
  stillOpen: !!D.getElementById('db-insert-modal'),
})), 20);
""")
    assert out['marked'] == 1
    assert any('required' in t.lower() for t in out['toasts'])
    assert out['stillOpen'], 'the form closed on a validation error'


@requires_jsdom
def test_input_type_follows_the_column_type():
    out = _run("""
W.dbShowInsertForm('goals_v2', wideTable());
const m = D.getElementById('db-insert-modal');
console.log(JSON.stringify({
  textarea: m.querySelectorAll('textarea[data-col]').length > 0,
  numeric: !!m.querySelector('input[type="number"][data-col="priority"]'),
}));
""")
    assert out['textarea'], 'TEXT columns should get a textarea'
    assert out['numeric'], 'INTEGER columns should get a number input'


@requires_jsdom
def test_a_valid_submit_closes_and_confirms():
    out = _run("""
W.dbShowInsertForm('goals_v2', wideTable());
const m = D.getElementById('db-insert-modal');
m.querySelector('[data-col="title"]').value = 'My goal';
W.fetch = async () => ({ok:true, json: async () => ({ok:true})});
W.dbSubmitInsertForm('goals_v2');
setTimeout(() => console.log(JSON.stringify({
  toasts: W.__toasts,
  closed: !D.getElementById('db-insert-modal'),
})), 20);
""")
    assert out['closed']
    assert any('inserted' in t.lower() for t in out['toasts'])


@requires_jsdom
def test_a_server_error_keeps_the_users_input():
    """Discarding a filled-in record on a validation error is how people learn
    not to trust a form."""
    out = _run("""
W.dbShowInsertForm('goals_v2', wideTable());
const m = D.getElementById('db-insert-modal');
m.querySelector('[data-col="title"]').value = 'Typed with care';
W.fetch = async () => ({ok:false, status:400, json: async () => ({ok:false, error:'constraint failed'})});
W.dbSubmitInsertForm('goals_v2');
setTimeout(() => {
  const still = D.getElementById('db-insert-modal');
  console.log(JSON.stringify({
    open: !!still,
    preserved: still ? still.querySelector('[data-col="title"]').value : null,
    toasts: W.__toasts,
  }));
}, 20);
""")
    assert out['open'], 'the form was destroyed on a server error'
    assert out['preserved'] == 'Typed with care'
    assert any('constraint failed' in t for t in out['toasts']), (
        'the server reason must reach the user'
    )


@requires_jsdom
def test_blank_fields_become_null_not_empty_string():
    """An empty string in a numeric or date column is a different, worse kind
    of wrong than NULL."""
    out = _run("""
W.dbShowInsertForm('goals_v2', wideTable());
const m = D.getElementById('db-insert-modal');
m.querySelector('[data-col="title"]').value = 'Only this';
let sent = null;
W.fetch = async (u, o) => { sent = JSON.parse(o.body); return {ok:true, json: async () => ({ok:true})}; };
W.dbSubmitInsertForm('goals_v2');
setTimeout(() => console.log(JSON.stringify({keys: Object.keys(sent.row)})), 20);
""")
    assert out['keys'] == ['title'], (
        f'blank fields were sent as empty strings: {out["keys"]}'
    )


def test_the_dialog_follows_the_modal_conventions():
    src = MODULE.read_text(encoding='utf-8')
    block = src[src.index('function dbShowInsertForm'):src.index('function dbCloseInsertForm')]
    assert "setAttribute('role', 'dialog')" in block
    assert "aria-modal" in block
    assert "data-click-self" in block, 'backdrop click should dismiss it'
