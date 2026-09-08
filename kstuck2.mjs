import { chromium } from 'playwright-core';
const b = await chromium.launch({ headless: true });
const p = await b.newPage();
await p.goto('http://localhost:8787/', { waitUntil:'domcontentloaded' });
await p.waitForFunction(()=>typeof window.nav==='function', null, {timeout:25000});
await p.waitForTimeout(500);
const panes = ['kanban','a2a','settings','docs','prompts','templates','swarm','galaxy','dashboard','finops','evals','mcp','terminal','composer','goals','control','workflow','websearch','browser','imagegen'];
for (const pane of panes) {
  try{ await p.evaluate((p2)=>window.nav(p2), pane); }catch(e){}
  await p.waitForTimeout(2200);
  const s = await p.evaluate(()=>{
    const vis = document.querySelector('.data-state.state-loading, .state-loading, .skeleton');
    if (!vis) return null;
    const cs = getComputedStyle(vis);
    const rect = vis.getBoundingClientRect();
    const visible = cs.display!=='none' && cs.visibility!=='hidden' && rect.width > 20;
    return { visible, text: (vis.textContent||'').slice(0,40).trim() };
  });
  if (s && s.visible) console.log(`  [${pane}] VISIBLE loading: "${s.text}"`);
}
await b.close();
