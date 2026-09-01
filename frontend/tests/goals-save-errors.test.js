// Frontend correctness: goal mutations must not claim success when the save
// failed. gmAddCheckin/gmAddMilestone/gmCompleteMilestone/gmEditGoal/gmDeleteGoal
// awaited fetch() and toasted success unconditionally, so a failed save (goal
// deleted elsewhere / network) showed "Updated"/"added"/"deleted" while nothing
// persisted. Only gmCreateGoal checked response.ok.
import { describe, it, expect, beforeEach, vi } from 'vitest';

function escHtml(s) { return String(s ?? '').replace(/[&<>"']/g, c => ({ '&': '&amp;', '<': '&lt;', '>': '&gt;', '"': '&quot;', "'": '&#39;' }[c])); }

function loadModule() {
  const fs = require('fs'); const path = require('path');
  const source = fs.readFileSync(path.join(__dirname, '..', 'js', '49-goals.js'), 'utf8');
  const closer = '})(S, nav, toast, escHtml, fetch, document, gmPrompt, gmConfirm, gmAlert);';
  const hook = `\n;window.__setGoal=(g)=>{_goalSelected={goal:g}};window.__del=()=>gmDeleteGoal();\n` + closer;
  const code = source.replace(closer, hook);
  new Function('window','document','navigator','location','localStorage','console','fetch','toast','gmDanger','gmPrompt','gmConfirm','gmAlert','escHtml','S','setTimeout','nav','httpError','humanError', code)(
    globalThis.window, globalThis.document, globalThis.navigator, {}, globalThis.localStorage,
    globalThis.console, globalThis.fetch, globalThis.toast, globalThis.gmDanger, globalThis.gmPrompt, globalThis.gmConfirm, globalThis.gmAlert,
    escHtml, { agents: [] }, setTimeout, { toast: ()=>{} }, (e)=>e, ()=>({ message: 'err' })
  );
}

// We drive gmDeleteGoal (simplest; the DELETE path). Mock fetch ok:false.
describe('goal mutations surface failed saves', () => {
  let toasts;
  beforeEach(() => {
    document.body.innerHTML = '';
    toasts = [];
    globalThis.toast = vi.fn((m, t) => toasts.push({ m, t }));
    globalThis.gmDanger = vi.fn(async () => true);
    globalThis.gmPrompt = vi.fn(async () => null);
    globalThis.gmConfirm = vi.fn(async () => true);
    globalThis.gmAlert = vi.fn(() => {});
    // fetch fails (ok:false) for the DELETE
    globalThis.fetch = vi.fn(async () => ({ ok: false, status: 404, json: async () => ({}) }));
    globalThis.gmLoadGoals = vi.fn(async () => {});
    loadModule();
  });

  it('gmDeleteGoal reports an error and does not claim deleted', async () => {
    window.__setGoal({ id: 'g1', title: 'Goal One' });
    await window.__del();
    expect(toasts.some(t => /not deleted/i.test(t.m) && t.t === 'error')).toBe(true);
    expect(toasts.some(t => /deleted/.test(t.m) && !/not/i.test(t.m))).toBe(false);
  });
});
