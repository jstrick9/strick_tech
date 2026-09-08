import { chromium } from 'playwright-core';
const b = await chromium.launch({ headless: true });
const p = await b.newPage();
let loaderCount = 0, defineErr = 0;
p.on('request', r => { if (r.url().includes('/monaco/vs/loader.js')) loaderCount++; });
p.on('pageerror', e => { if (/define|_amdLoaderGlobal/.test(String(e))) defineErr++; });
await p.goto('http://localhost:8787/', { waitUntil: 'domcontentloaded' });
await p.waitForTimeout(300);
// open studio repeatedly FAST (before monaco loads)
for (let k=0;k<4;k++){ try{ await p.evaluate(()=>window.nav('studio')); }catch(e){} await p.waitForTimeout(150); }
await p.waitForTimeout(1500);
console.log('loader.js requests:', loaderCount, '| monaco define errors:', defineErr);
await b.close();
