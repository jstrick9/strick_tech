import { chromium } from 'playwright-core';
const b = await chromium.launch({ headless: true });
const p = await b.newPage();
await p.goto('http://localhost:8787/', { waitUntil: 'domcontentloaded' });
await p.waitForTimeout(4000);
const r = await p.evaluate(()=>({ hasNav: typeof window.nav==='function', hasCollect: typeof window.collectOpenModals==='function', scripts: document.querySelectorAll('script[src]').length }));
console.log(JSON.stringify(r));
await b.close();
