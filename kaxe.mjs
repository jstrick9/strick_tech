import { chromium } from 'playwright-core';
import { readFileSync } from 'fs';
const axeSrc = readFileSync('/home/user/repo/frontend/node_modules/axe-core/axe.min.js','utf8');
const b = await chromium.launch({ headless: true });
const p = await b.newPage();
await p.goto('http://localhost:8787/', { waitUntil: 'domcontentloaded' });
await p.waitForFunction(()=>typeof window.nav==='function', null, {timeout:25000});
await p.waitForTimeout(600);
await p.addScriptTag({ content: axeSrc });
const panes = ['kanban','settings','hierarchy','templates','prompts','dashboard'];
const totals = {};
for (const pane of panes) {
  try{ await p.evaluate((p2)=>window.nav(p2), pane); }catch(e){}
  await p.waitForTimeout(450);
  const res = await p.evaluate(async () => {
    const r = await window.axe.run(document, { runOnly: ['cat.aria','cat.keyboard','cat.contrast','cat.name-role-value'] });
    return r.violations.map(v => v.impact + ' :: ' + v.id + ' :: ' + v.nodes.length);
  });
  totals[pane] = res;
  console.log('['+pane+'] violations:', res.length);
  res.filter(x=>/critical|serious/.test(x)).slice(0,10).forEach(x=>console.log('    ', x));
}
await b.close();
