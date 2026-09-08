import { chromium } from 'playwright-core';
const b = await chromium.launch({ headless: true });
const p = await b.newPage();
await p.goto('http://localhost:8787/', { waitUntil: 'domcontentloaded' });
await p.waitForFunction(()=>typeof window.nav==='function', null, {timeout:25000});
await p.waitForTimeout(600);
const panes = ['kanban','supervisor','a2a','settings','hierarchy','docs','prompts','templates','swarm','galaxy','dashboard','finops','evals','mcp','terminal','composer','goals','imagegen','replay','workflow'];
const dupes = new Set();
for (const pane of panes) {
  try{ await p.evaluate((p2)=>window.nav(p2), pane); }catch(e){}
  await p.waitForTimeout(250);
  const found = await p.evaluate(() => {
    const seen = new Set(), dup = [];
    document.querySelectorAll('[id]').forEach(el => {
      const id = el.id;
      if (seen.has(id)) dup.push(id); else seen.add(id);
    });
    return dup;
  });
  found.forEach(id => dupes.add(pane+' -> '+id));
}
console.log('Duplicate element IDs found:', dupes.size);
[...dupes].slice(0,40).forEach(d=>console.log('  ', d));
await b.close();
