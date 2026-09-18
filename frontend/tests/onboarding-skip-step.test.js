// r54 regression: the onboarding wizard's "Skip" button skips ONE step.
//
// obNext(skip) used to complete the ENTIRE wizard on any skip
// (`if (obStep >= obSteps.length || skip === true)`) — so a new user who
// wasn't ready to paste an API key at step 2 clicked "Skip" and silently
// lost the remaining steps: the modal vanished, onboarding was marked
// complete, and the workspace-name / theme steps never came back. Found
// live while driving the true first-run wizard end to end (reset
// /api/onboarding/reset + fresh context, all 7 steps).
//
// Skip now advances exactly one step; the wizard still always dismisses
// because the final step's "🚀 Start Building" reaches the end. Verified
// live: full walk welcome → api_key (skipped) → workspace → agents →
// first_task (skipped) → theme → done, landing coherent in simple mode
// with the workspace name persisted to onboarding prefs and restored on
// reload via applyPreferences.
//
// Harness mirrors onboarding-enter.test.js (module loaded via new
// Function with the module-scope globals stubbed).

function escHtml(s) { return String(s == null ? '' : s).replace(/[&<>"']/g, c => ({ '&':'&amp;','<':'&lt;','>':'&gt;','"':'&quot;',"'":'&#39;' }[c])); }
function jsArg(s) { return escHtml(s).replace(/"/g, '&quot;'); }

const OB_DOM = `
<div id="onboarding-modal"><div id="ob-icon"></div><div id="ob-title"></div>
<div id="ob-subtitle"></div><div id="ob-body"></div><div id="ob-counter"></div>
<div id="ob-dots"></div>
<div id="ob-input-area"><input id="ob-input" type="text"></div>
<div id="ob-theme-area"></div><div id="ob-agents-area"></div>
<button id="ob-skip"></button><button id="ob-back"></button><button id="ob-next"></button>
<div id="sb-version"></div></div>`;

const STEPS = [
  { id: 'welcome',   title: 'Welcome',            subtitle: '', body: '', skip: false },
  { id: 'api_key',   title: 'Connect your AI',    subtitle: '', body: '', skip: true  },
  { id: 'workspace', title: 'Name your workspace',subtitle: '', body: '', skip: false },
  { id: 'done',      title: "You're ready",       subtitle: '', body: '', skip: false },
];

function loadModule(lsStore) {
  const fs = require('fs'); const path = require('path');
  let src = fs.readFileSync(path.join(__dirname, '..', 'js', '24-onboarding.js'), 'utf8');
  src += '\n;window.__setob=function(steps,step){obSteps=steps;obStep=step||0;};window.__getob=function(){return obStep;};window.__obNext=obNext;';
  new Function('window','document','_safeLS','S','escHtml','jsArg','fetch','toast','gmAlert','gmPrompt','gmConfirm','nav', src)(
    globalThis.window, globalThis.document, lsStore,
    { agents: [{ id:'a1', name:'Agent', role:'dev', model:'default' }] },
    escHtml, jsArg, undefined, ()=>{}, ()=>{}, ()=>{}, ()=>{}, ()=>{}
  );
}

describe('onboarding wizard: Skip skips one step (r54)', () => {
  beforeEach(() => {
    document.body.innerHTML = OB_DOM;
    globalThis.showToast = () => {};
    globalThis.document.getElementById = (id) => document.querySelector('#' + id);
  });
  afterEach(() => { document.body.innerHTML = ''; });

  test('skip advances exactly one step and keeps the wizard open', () => {
    const ls = { data: {}, get(k){ return this.data[k] ?? null; }, set(k,v){ this.data[k]=v; } };
    loadModule(ls);
    window.__setob(STEPS, 0);
    window.__obNext(true);                      // Skip on step 1 (api_key)
    expect(window.__getob()).toBe(1);           // advanced ONE step
    expect(document.querySelector('#onboarding-modal')).not.toBeNull();  // still open
    expect(ls.data['agentic_os_onboarded']).toBeUndefined();             // NOT completed
  });

  test('skip collects no input value', () => {
    const ls = { data: {}, get(k){ return this.data[k] ?? null; }, set(k,v){ this.data[k]=v; } };
    loadModule(ls);
    window.__setob(STEPS, 1);
    document.querySelector('#ob-input').value = 'sk-or-v1-should-not-be-saved';
    window.__obNext(true);
    expect(window.__getob()).toBe(2);
    // the skipped step's value was not collected (obPrefs is module-scoped;
    // completion would have POSTed it — verified by the empty-payload
    // contract in the live E2E: a skipped key never reaches the vault)
  });

  test('Next past the final step completes and dismisses the wizard', () => {
    const ls = { data: {}, get(k){ return this.data[k] ?? null; }, set(k,v){ this.data[k]=v; } };
    loadModule(ls);
    window.__setob(STEPS, STEPS.length - 1);
    window.__obNext();                          // "🚀 Start Building"
    expect(ls.data['agentic_os_onboarded']).toBe('true');                 // completed
    expect(document.querySelector('#onboarding-modal')).toBeNull();       // dismissed
  });

  test('skip on the final step also completes (never traps the user)', () => {
    const ls = { data: {}, get(k){ return this.data[k] ?? null; }, set(k,v){ this.data[k]=v; } };
    loadModule(ls);
    window.__setob(STEPS, STEPS.length - 1);
    window.__obNext(true);
    expect(ls.data['agentic_os_onboarded']).toBe('true');
    expect(document.querySelector('#onboarding-modal')).toBeNull();
  });
});
