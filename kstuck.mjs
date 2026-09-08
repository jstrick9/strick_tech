import { chromium } from 'playwright-core';
const b = await chromium.launch({ headless: true });
const p = await b.newPage();
const stuck = new Map();
await p.goto('http://localhost:8787/', { waitUntil:'domcontentloaded' });
await p.waitForFunction(()=>typeof window.nav==='function', null, {timeout:25000});
await p.waitForTimeout(500);
const panes = ['kanban','supervisor','a2a','settings','hierarchy','docs','prompts','templates','swarm','galaxy','dashboard','finops','evals','mcp','terminal','composer','goals','control','workflow','integrations','websearch','browser'];
for (const pane of panes) {
  try{ await p.evaluate((p2)=>window.nav(p2), pane); }catch(e){}
  await p.waitForTimeout(1800);
  // look for permanent loading skeletons / spinners left on screen
  const s = await p.evaluate(()=>{
    const loading = document.querySelector('.state-loading, .skeleton, [data-state="loading"], .data-state.state-loading');
    return loading ? 'has-loading-ui' : 'clean';
  });
  if (s !== 'clean') stuck.set(pane, s);
}
console.log('panes with leftover loading UI after 1.8s:', stuck.size);
[...stuck.keys()].forEach(k=>console.log('  ', k, stuck.get(k)));
await b.close();
