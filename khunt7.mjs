import { chromium } from 'playwright-core';
const b = await chromium.launch({ headless: true });
const p = await b.newPage();
const errs = new Set();
p.on('pageerror', e => errs.add('PAGE: '+String(e).slice(0,180)));
p.on('console', m => { if(m.type()==='error' && !/Content Security Policy|inline style|404|401|Failed to load resource/.test(m.text())) errs.add('C: '+m.text().slice(0,150)); });
await p.goto('http://localhost:8787/', { waitUntil: 'networkidle' });
await p.waitForTimeout(700);
const panes = ['kanban','supervisor','a2a','settings','hierarchy','docs','prompts','templates','swarm','galaxy','dashboard','finops','evals','mcp','terminal','composer','goals','loopswork'];
let clicks=0;
for (const pane of panes) {
  await p.evaluate((pn)=>window.nav(pn), pane); await p.waitForTimeout(300);
  const n = await p.evaluate(()=>Array.from(document.querySelectorAll('button, [data-act-click]')).filter(el=>el.isConnected&&el.getClientRects().length>0).length);
  for (let i=0;i<Math.min(n,180);i++) {
    try {
      await p.evaluate((idx) => {
        const els = Array.from(document.querySelectorAll('button, [data-act-click]')).filter(el=>el.isConnected&&el.getClientRects().length>0);
        const el = els[idx]; if (!el) return;
        const act = el.getAttribute('data-act-click')||'';
        if (/delete|remove|clear|wipe|confirm|submit|logout|disconnect|danger|destroy/i.test(act)) return;
        el.click();
      }, i);
      await p.waitForTimeout(20);
      clicks++;
    } catch(e){}
  }
}
console.log('clicks:', clicks, '| unique genuine errors:', errs.size);
[...errs].slice(0,25).forEach(e=>console.log('  •', e));
await b.close();
