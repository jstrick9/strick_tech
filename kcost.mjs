import { chromium } from 'playwright-core';
const b = await chromium.launch({ headless: true });
const p = await b.newPage();
let cost=0;
p.on('request', r => { if(r.url().includes('/api/cost')) cost++; });
await p.goto('http://localhost:8787/', { waitUntil:'domcontentloaded' });
await p.waitForFunction(()=>typeof window.nav==='function', null, {timeout:25000});
await p.waitForTimeout(33500); // > one 30s cycle
console.log('/api/cost requests in ~33.5s:', cost, '(was 2/cycle, now 1)');
await b.close();
