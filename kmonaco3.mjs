import { chromium } from 'playwright-core';
const b = await chromium.launch({ headless: true });
const p = await b.newPage();
await p.goto('http://localhost:8787/', { waitUntil: 'domcontentloaded' });
await p.waitForFunction(()=>typeof window.nav==='function', null, {timeout:20000});
await p.evaluate(()=>window.nav('studio'));
await p.waitForTimeout(3500);
const r = await p.evaluate(()=>({
  hasMonaco: typeof window.monaco === 'object',
  hasEditor: !!(window.Studio && window.Studio.editor && typeof window.Studio.editor.getValue === 'function'),
  editorValue: window.Studio?.editor ? String(window.Studio.editor.getValue()).slice(0,40) : null,
}));
console.log(JSON.stringify(r));
await b.close();
