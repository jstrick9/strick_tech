import { chromium } from 'playwright-core';
const b = await chromium.launch({ headless: true });
const p = await b.newPage();
const errs = [];
p.on('pageerror', e => errs.push(String(e).slice(0,160)));
await p.goto('http://localhost:8787/', { waitUntil: 'networkidle' });
await p.waitForTimeout(700);
const panes = ['kanban','supervisor','a2a','settings','hierarchy'];
let clicks = 0;
for (const pane of panes) {
  await p.evaluate((pn)=>window.nav(pn), pane); await p.waitForTimeout(300);
  const n = await p.evaluate(() => Array.from(document.querySelectorAll('button, [data-act-click]')).filter(el=>el.isConnected&&el.getClientRects().length>0).length);
  for (let i=0;i<Math.min(n,45);i++) {
    const before = errs.length;
    try {
      await p.evaluate((idx) => {
        const els = Array.from(document.querySelectorAll('button, [data-act-click]')).filter(el=>el.isConnected&&el.getClientRects().length>0);
        const el = els[idx]; if (!el) return;
        const act = el.getAttribute('data-act-click')||'';
        if (/delete|remove|clear|wipe|confirm|submit|logout|disconnect|danger/i.test(act)) return;
        el.click();
      }, i);
      await p.waitForTimeout(30);
      clicks++;
    } catch(e){}
  }
}
console.log('clicks:', clicks, '| new errors:', errs.length);
[...new Set(errs)].slice(0,20).forEach(e=>console.log('  •', e));
await b.close();
