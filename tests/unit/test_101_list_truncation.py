"""A truncated list must say so.

TWO BUGS, FOUND BY COMPARING WHAT THE API RETURNS WITH WHAT IT REPORTS.

1. SILENTLY HIDDEN RECORDS.
   GET /api/goals returned 100 items and `{"total": 724}`. The Goals pane
   hardcoded `limit=100`, never requested more, and displayed no indication
   that 624 goals existed but were not shown. GET /api/prompts did the same
   with 100 of 103.

   This is worse than an explicit limit: a user who cannot find a goal
   reasonably concludes it was deleted. The server was already reporting the
   true count — the UI simply ignored it.

2. A STRAY ">" ON EVERY GOAL CARD.
   `<div ... data-goal-id="${...}" >>` — a duplicated bracket meant every card
   rendered a literal ">" as its first visible character. Pre-existing, and
   confirmed against the commit before this review's a11y work.
"""

from __future__ import annotations

import json
import re
import shutil
import subprocess
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[2]
GOALS_JS = ROOT / 'frontend' / 'js' / '49-goals.js'
PROMPTS_JS = ROOT / 'frontend' / 'js' / '14-prompt-library.js'


def _have_jsdom() -> bool:
    if not shutil.which('node'):
        return False
    return subprocess.run(
        ['node', '-e', "require('jsdom')"], cwd=ROOT, capture_output=True
    ).returncode == 0


requires_jsdom = pytest.mark.skipif(not _have_jsdom(), reason='jsdom not installed')


def _run(script: str) -> dict:
    probe = ROOT / 'zz_trunc_probe.js'
    probe.write_text(script, encoding='utf-8')
    try:
        r = subprocess.run(
            ['node', str(probe.name)], cwd=ROOT, capture_output=True, text=True
        )
        if not r.stdout.strip():
            pytest.skip(f'node produced no output: {r.stderr[-300:]}')
        return json.loads(r.stdout.strip().split('\n')[-1])
    finally:
        probe.unlink(missing_ok=True)


GOALS_HARNESS = """
const {JSDOM} = require('jsdom');
const fs = require('fs');
const dom = new JSDOM('<!doctype html><body><div id="gm-goal-list"></div></body>',
  {runScripts:'outside-only'});
const W = dom.window, D = W.document;
global.window = W; global.document = D;
W.escHtml = s => String(s).replace(/[&<>"']/g,
  c => ({'&':'&amp;','<':'&lt;','>':'&gt;','"':'&quot;',"'":'&#39;'}[c]));
const src = fs.readFileSync('frontend/js/49-goals.js','utf8');
const s = src.indexOf('function gmRenderList');
const e = src.indexOf('\\n}', src.indexOf('.join(', s)) + 2;
W.eval('var _goalList=[],_goalTotal=0,_goalSelected=null;'
  + 'var GOAL_PRIORITY_COLORS={},GOAL_STATUS_COLORS={},GOAL_DOMAIN_ICONS={};'
  + src.slice(s, e)
  + '\\nwindow.__drive=function(l,t){_goalList=l;_goalTotal=t;gmRenderList();};');
const GOAL = {id:'g1', title:'One', priority:'high', status:'active', progress:10};
"""


# ══ The API already reports the truth ═════════════════════════════════════════
def test_the_goals_api_reports_a_total(client):
    body = client.get('/api/goals').json()
    assert 'total' in body, (
        'without a total the UI cannot know it is showing a partial list'
    )


def test_the_prompts_api_reports_a_total(client):
    body = client.get('/api/prompts').json()
    assert 'total' in body


# ══ The UI must use it ════════════════════════════════════════════════════════
@requires_jsdom
def test_a_truncated_goal_list_says_so():
    out = _run(GOALS_HARNESS + """
W.__drive([GOAL], 724);
const html = D.getElementById('gm-goal-list').innerHTML;
console.log(JSON.stringify({
  notice: /Showing 1 of 724/.test(html),
  hidden: /723 more are hidden/.test(html),
}));
""")
    assert out['notice'], 'a list showing 1 of 724 gave no indication of truncation'
    assert out['hidden'], 'the number of hidden records should be explicit'


@requires_jsdom
def test_no_notice_when_the_list_is_complete():
    """A permanent 'showing N of N' banner is noise."""
    out = _run(GOALS_HARNESS + """
W.__drive([GOAL], 1);
console.log(JSON.stringify({
  notice: /Showing/.test(D.getElementById('gm-goal-list').innerHTML),
}));
""")
    assert not out['notice']


@requires_jsdom
def test_goal_cards_do_not_render_a_stray_bracket():
    """`data-goal-id="..." >>` put a literal '>' at the top of every card."""
    out = _run(GOALS_HARNESS + """
W.__drive([GOAL], 1);
const card = D.querySelector('.gm-goal-card');
console.log(JSON.stringify({text: card.textContent.trim().slice(0, 4)}));
""")
    assert not out['text'].startswith('>'), (
        f'goal card starts with a stray bracket: {out["text"]!r}'
    )


def test_the_prompt_library_surfaces_its_own_truncation():
    src = PROMPTS_JS.read_text(encoding='utf-8')
    assert 'promptsTotal' in src
    assert re.search(r'promptsTotal\s*>\s*promptsData\.length', src), (
        'the prompt grid does not compare the page against the true total'
    )


# ══ Keep the markup typo from coming back ═════════════════════════════════════
def test_no_template_emits_a_duplicated_closing_bracket():
    offenders = []
    for path in sorted((ROOT / 'frontend' / 'js').glob('*.js')):
        for i, line in enumerate(path.read_text(encoding='utf-8').split('\n'), 1):
            if line.lstrip().startswith(('//', '*', '/*')):
                continue
            if re.search(r'<[a-z]+[^>]*"\s*>>', line):
                offenders.append(f'{path.name}:{i}')
    assert not offenders, (
        'duplicated ">" renders a literal bracket in the UI:\n  '
        + '\n  '.join(offenders)
    )
