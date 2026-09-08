import { chromium } from 'playwright-core';
const b = await chromium.launch({ headless: true });
const p = await b.newPage();
const bad = new Set();
p.on('response', async r => {
  if (r.status()>=500) {
    let body=''; try{ body=(await r.text()).slice(0,120);}catch(e){}
    const ct = r.headers()['content-type']||'';
    if (!/json/.test(ct)) bad.add(r.url()+' :: '+JSON.stringify(ct)+' :: '+body.replace(/\n/g,' '));
  }
});
await p.goto('http://localhost:8787/', { waitUntil: 'domcontentloaded' });
await p.waitForFunction(()=>typeof window.nav==='function', null, {timeout:20000});
await p.waitForTimeout(600);
const panes = ['kanban','supervisor','a2a','settings','hierarchy','docs','prompts','templates','swarm','galaxy','dashboard','finops','evals','mcp','terminal','composer','goals','imagegen','replay'];
for (const pane of panes) {
  try{ await p.evaluate((p2)=>window.nav(p2), pane); }catch(e){}
  await p.waitForTimeout(250);
  const n = await p.evaluate(()=>Array.from(document.querySelectorAll('button,[data-act-click]')).filter(e=>e.isConnected&&e.getClientRects().length>0).length);
  for (let i=0;i<Math.min(n,170);i++){
    try{ await p.evaluate((idx)=>{const els=Array.from(document.querySelectorAll('button,[data-act-click]')).filter(e=>e.isConnected&&e.getClientRects().length>0);const el=els[idx];if(!el)return;const a=el.getAttribute('data-act-click')||'';if(/delete|remove|clear|wipe|confirm|submit|logout|disconnect|danger|destroy/i.test(a))return;el.click();},i); await p.waitForTimeout(10);}catch(e){}
  }
}
console.log('NON-JSON 5xx endpoints:', bad.size);
[...bad].forEach(x=>console.log('  ', x));
await b.close();
