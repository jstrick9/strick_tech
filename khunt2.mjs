import { chromium } from 'playwright-core';
const b = await chromium.launch({ headless: true });
const p = await b.newPage();
const errs = [];
p.on('pageerror', e => errs.push('PAGE: '+String(e).slice(0,220)));
p.on('console', m => { if(m.type()==='error' && !/Content Security Policy|inline style/.test(m.text())) errs.push('console: '+m.text().slice(0,200)); });
await p.goto('http://localhost:8787/', { waitUntil: 'networkidle' });
await p.waitForTimeout(800);
const panes = ['kanban','supervisor','goals','a2a','settings','studio','templates','composer','swarm','galaxy','hierarchy','dashboard','finops','evals','mcp','terminal'];
for (const pane of panes) {
  try { await p.evaluate((pn)=>window.nav(pn), pane); await p.waitForTimeout(400); } catch(e){}
}
console.log('GENUINE errors (non-CSP):', errs.length);
[...new Set(errs)].slice(0,25).forEach(e=>console.log('  •', e));
await b.close();
