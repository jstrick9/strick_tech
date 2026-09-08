import { chromium } from 'playwright-core';
const b = await chromium.launch({ headless: true });
const p = await b.newPage();
const five = new Set();
p.on('response', r => {
  if (r.status()===500 || r.status()===502 || r.status()===503) five.add(r.status()+' '+r.url());
});
await p.goto('http://localhost:8787/', { waitUntil: 'domcontentloaded' });
await p.waitForFunction(()=>typeof window.nav==='function', null, {timeout:20000});
await p.waitForTimeout(600);
const panes = ['kanban','supervisor','a2a','settings','hierarchy','docs','prompts','templates','swarm','galaxy','dashboard','finops','evals','mcp','terminal','composer','goals'];
for (const pane of panes) {
  try{ await p.evaluate((p2)=>window.nav(p2), pane); }catch(e){}
  await p.waitForTimeout(250);
  const n = await p.evaluate(()=>Array.from(document.querySelectorAll('button,[data-act-click]')).filter(e=>e.isConnected&&e.getClientRects().length>0).length);
  for (let i=0;i<Math.min(n,160);i++){
    try{ await p.evaluate((idx)=>{const els=Array.from(document.querySelectorAll('button,[data-act-click]')).filter(e=>e.isConnected&&e.getClientRects().length>0);const el=els[idx];if(!el)return;const a=el.getAttribute('data-act-click')||'';if(/delete|remove|clear|wipe|confirm|submit|logout|disconnect|danger|destroy/i.test(a))return;el.click();},i); await p.waitForTimeout(12);}catch(e){}
  }
}
console.log('5xx responses:', five.size);
[...five].forEach(h=>console.log('  ', h));
await b.close();
