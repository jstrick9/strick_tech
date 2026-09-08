import { chromium } from 'playwright-core';
const b = await chromium.launch({ headless: true });
const p = await b.newPage();
const errs = [];
p.on('pageerror', e => errs.push('PAGE: '+String(e).slice(0,160)));
p.on('console', m => { if(m.type()==='error' && !/Content Security Policy|inline style/.test(m.text())) errs.push('C: '+m.text().slice(0,120)); });
await p.goto('http://localhost:8787/', { waitUntil: 'networkidle' });
await p.waitForTimeout(500);
await p.evaluate(()=>window.nav('docs'));
await p.waitForTimeout(800);
const quick = await p.evaluate(()=>{
  const grid = document.getElementById('docs-qs-grid');
  return { hasGrid: !!grid, cards: grid?grid.querySelectorAll('.qs-card').length:0 };
});
// force the tab again + features
await p.evaluate(()=>window.docsTab('quickstarts', document.querySelector('.docs-tab[data-tab="quickstarts"]')));
await p.waitForTimeout(400);
const q2 = await p.evaluate(()=>document.querySelectorAll('#docs-qs-grid .qs-card').length);
await p.evaluate(()=>window.docsTab('features', document.querySelector('.docs-tab[data-tab="features"]')));
await p.waitForTimeout(400);
const feat = await p.evaluate(()=>{
  const c = document.getElementById('docs-content');
  return c ? c.textContent.includes('Feature Reference') : false;
});
console.log(JSON.stringify({quick, q2, featuresTab:feat, errors: errs}));
await b.close();
