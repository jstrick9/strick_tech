import { chromium } from 'playwright-core';
const b = await chromium.launch({ headless: true });
const p = await b.newPage();
const got = [];
p.on('response', async r => {
  if (r.url().includes('pin-pane')) {
    let body=''; try{ body = (await r.text()).slice(0,200);}catch(e){body='<err>';}
    got.push({ status: r.status(), csrfHeader: r.request().headers()['x-csrf-token']?'yes':'NO', body });
  }
});
await p.goto('http://localhost:8787/', { waitUntil: 'domcontentloaded' });
await p.waitForFunction(()=>typeof window.nav==='function', null, {timeout:20000});
await p.waitForTimeout(600);
// call pinPaneToggle directly (real handler, real fetch wrapper)
await p.evaluate(()=>window.pinPaneToggle('kanban')).catch(e=>{});
await p.waitForTimeout(1000);
got.forEach(g=>console.log('status', g.status, '| csrf', g.csrfHeader, '| body:', g.body.replace(/\n/g,' ')));
if(!got.length) console.log('NO pin-pane request fired');
await b.close();
