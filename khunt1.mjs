import { chromium } from 'playwright-core';
const b = await chromium.launch({ headless: true });
const p = await b.newPage();
const errs = [];
p.on('pageerror', e => errs.push(String(e).slice(0,180)));
p.on('console', m => { if(m.type()==='error') errs.push('console: '+m.text().slice(0,150)); });
await p.goto('http://localhost:8787/', { waitUntil: 'networkidle' });
await p.waitForTimeout(800);
// Exercise several panes whose renderers mount overlays/modals, and collect
// uncaught page errors on load of each.
const panes = ['kanban','supervisor','goals','a2a','settings','studio','templates','composer'];
for (const pane of panes) {
  const before = errs.length;
  try {
    await p.evaluate((pn)=>window.nav(pn), pane);
    await p.waitForTimeout(500);
  } catch(e) {}
}
console.log('UNCAUGHT/PAGE ERRORS after walking panes:', errs.length);
errs.slice(0,20).forEach(e=>console.log('  -', e));
await b.close();
