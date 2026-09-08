// Onboarding flow: pressing Enter in the text field must advance to the next
// step. Previously Enter did nothing, so a user typing an API key or workspace
// name had to stop and hunt for the "Next" button.
import { describe, it, expect, beforeEach, afterEach, vi } from 'vitest';

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

function loadModule() {
  const fs = require('fs'); const path = require('path');
  let src = fs.readFileSync(path.join(__dirname, '..', 'js', '24-onboarding.js'), 'utf8');
  // Inject hooks inside the module scope so we can drive obSteps/obStep/obNext.
  src += '\n;window.__setob=function(steps,step){obSteps=steps;obStep=step||0;};window.__getob=function(){return obStep;};window.__obNext=obNext;window.__obShow=showOnboarding;';
  new Function('window','document','_safeLS','S','escHtml','jsArg','fetch','toast','gmAlert','gmPrompt','gmConfirm','nav', src)(
    globalThis.window, globalThis.document, { get:()=>null, set:()=>{} },
    { agents: [{ id:'a1', name:'Agent', role:'dev', model:'default' }] },
    escHtml, jsArg, undefined, ()=>{}, ()=>{}, ()=>{}, ()=>{}, ()=>{}
  );
}

describe('onboarding input advances on Enter', () => {
  beforeEach(() => {
    document.body.innerHTML = OB_DOM;
    globalThis.document.getElementById = vi.fn((id) => document.querySelector('#' + id));
    loadModule();
    // A 2-step flow starting at step 0 (a text-input step).
    window.__setob([
      { id:'workspace', title:'Name your workspace', subtitle:'', body:'', skip:false },
      { id:'theme', title:'Pick a theme', subtitle:'', body:'', skip:true },
    ], 0);
  });
  afterEach(() => { document.body.innerHTML = ''; });

  it('Enter in the text input advances obStep by one', () => {
    window.__obShow();             // bind Enter listener, render step 0
    expect(window.__getob()).toBe(0);
    const inp = document.querySelector('#ob-input');
    const ev = new KeyboardEvent('keydown', { key: 'Enter', bubbles: true, cancelable: true });
    inp.dispatchEvent(ev);
    expect(ev.defaultPrevented).toBe(true);      // handler calls preventDefault()
    expect(window.__getob()).toBe(1);            // advanced to step 2 (theme)
  });

  it('does not advance on other keys', () => {
    window.__obShow();
    const inp = document.querySelector('#ob-input');
    inp.dispatchEvent(new KeyboardEvent('keydown', { key: 'a', bubbles: true }));
    expect(window.__getob()).toBe(0);
  });
});
