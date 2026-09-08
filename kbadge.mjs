import { chromium } from 'playwright-core';
const b = await chromium.launch({ headless: true });
const p = await b.newPage();
await p.goto('http://localhost:8787/', { waitUntil: 'domcontentloaded' });
await p.waitForFunction(()=>typeof window.nav==='function', null, {timeout:25000});
await p.evaluate(()=>window.nav('studio'));
await p.waitForTimeout(2500);
const r = await p.evaluate(()=>({
  consoleBadgeCount: document.querySelectorAll('#console-count-badge').length,
  btnBadgeCount: document.querySelectorAll('#console-btn-count-badge').length,
}));
console.log('live studio:', JSON.stringify(r));
await b.close();
