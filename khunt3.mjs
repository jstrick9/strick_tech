import { chromium } from 'playwright-core';
const b = await chromium.launch({ headless: true });
const p = await b.newPage();
const bad = [];
p.on('response', r => { if(r.status()===404||r.status()===500||r.status()===401) bad.push(r.status()+' '+r.url()); });
await p.goto('http://localhost:8787/', { waitUntil: 'networkidle' });
await p.waitForTimeout(600);
const panes = ['kanban','supervisor','goals','a2a','settings','studio','terminal','mcp','dashboard'];
for (const pane of panes) { try { await p.evaluate((pn)=>window.nav(pn), pane); await p.waitForTimeout(400); } catch(e){} }
console.log('BAD responses:', bad.length);
[...new Set(bad)].forEach(r=>console.log('  ', r));
await b.close();
