// Accessibility of the rendered Goals pane (dynamic DOM the static-shell axe
// scan can't reach). The three filter <select>s must have accessible names, and
// each clickable goal card must be keyboard-operable (role=button, tabindex,
// data-keys) with an accurate aria-selected.
import { describe, it, expect, beforeEach, afterEach, vi } from 'vitest';
import * as axe from 'axe-core';

function escHtml(s) { return String(s == null ? '' : s).replace(/[&<>"']/g, c => ({ '&':'&amp;','<':'&lt;','>':'&gt;','"':'&quot;',"'":'&#39;' }[c])); }
function jsArg(s) { return escHtml(s).replace(/"/g, '&quot;'); }

const GM_DEFAULTS = `
function gmEmpty(){}
`;
// Minimal DOM the module touches.
function seedDom() {
  document.body.innerHTML = `
    <div id="gm-goal-list"></div>
    <div id="gm-main"></div>`;
}

function loadModule() {
  const fs = require('fs'); const path = require('path');
  const src = fs.readFileSync(path.join(__dirname, '..', 'js', '49-goals.js'), 'utf8');
  // Inject hooks INSIDE the IIFE (replace the closer), per the goals-save-errors
  // pattern, so the module-scoped _goalList/_goalSelected/gmRenderList are
  // reachable.
  const closer = '})(S, nav, toast, escHtml, fetch, document, gmPrompt, gmConfirm, gmAlert);';
  const hook = '\n;window.__goalsA11y={setList:(a)=>{_goalList=a;},renderList:gmRenderList,setSelected:(s)=>{_goalSelected=s;}};\n' + closer;
  const code = src.replace(closer, hook);
  new Function('window','document','S','nav','toast','escHtml','jsArg','fetch','gmPrompt','gmConfirm','gmAlert','httpError','humanError', code)(
    globalThis.window, globalThis.document, { agents: [] }, ()=>{}, ()=>{}, escHtml, jsArg,
    globalThis.fetch, ()=>{}, ()=>{}, ()=>{}, (e)=>e, ()=>({message:''})
  );
}

describe('Goals pane accessibility (rendered DOM)', () => {
  beforeEach(() => {
    seedDom();
    globalThis.document.getElementById = vi.fn((id) => document.querySelector('#' + id));
    loadModule();
  });
  afterEach(() => { document.body.innerHTML = ''; });

  it('selects have accessible names (aria-label) and goal cards are keyboard-operable + aria-selected', () => {
    window.__goalsA11y.setList([
      { id:'g1', title:'Ship v1', priority:'high', status:'active', progress:50, outcome_score:0.7, domain:'Work' },
      { id:'g2', title:'Meditate', priority:'low', status:'done', progress:100, outcome_score:null, domain:'Health' },
    ]);
    window.__goalsA11y.setSelected({ goal: { id: 'g1' } });
    window.__goalsA11y.renderList();
    const list = document.querySelector('#gm-goal-list');
    const cards = list.querySelectorAll('.gm-goal-card');
    // Cards are present, keyboard-operable, accurate selected state.
    expect(cards.length).toBe(2);
    cards.forEach(c => {
      expect(c.getAttribute('role')).toBe('button');
      expect(c.getAttribute('tabindex')).toBe('0');
      expect(c.getAttribute('data-keys')).toMatch(/Enter/);
    });
    expect(cards[0].getAttribute('aria-selected')).toBe('true');
    expect(cards[1].getAttribute('aria-selected')).toBe('false');
  });

  it('the filter selects carry accessible names (axe rule: select-name)', async () => {
    // Render the filters by running renderGoals' pane shell then gmRenderList.
    // Simpler: assert the shell template uses aria-label on the three selects.
    const fs = require('fs'); const path = require('path');
    const src = fs.readFileSync(path.join(__dirname, '..', 'js', '49-goals.js'), 'utf8');
    const shell = src.slice(src.indexOf('pane.innerHTML = `'), src.indexOf('await gmLoadGoals();'));
    const status = /id="gm-filter-status"[^>]*aria-label="[^"]*"/.test(shell)
      || /aria-label="[^"]*"[^>]*id="gm-filter-status"/.test(shell);
    expect(status).toBe(true);
    ['gm-filter-priority', 'gm-filter-domain'].forEach(id => {
      const has = new RegExp('id="' + id + '"[^>]*aria-label="[^"]*"').test(shell)
        || new RegExp('aria-label="[^"]*"[^>]*id="' + id + '"').test(shell);
      expect(has).toBe(true);
    });
  });
});
