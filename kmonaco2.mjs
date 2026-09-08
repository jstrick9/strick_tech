import { chromium } from 'playwright-core';
const b = await chromium.launch({ headless: true });
const p = await b.newPage();
let loaderReq = 0; const errs = new Set();
p.on('request', r => { if (r.url().includes('/monaco/vs/loader.js')) loaderReq++; });
p.on('pageerror', e => { const s=String(e); if (/define|_amdLoaderGlobal|is not a function|already been declared/.test(s)) errs.add(s.slice(0,120)); });
await p.goto('http://localhost:8787/', { waitUntil: 'domcontentloaded' });
await p.waitForFunction(()=>typeof window.nav==='function', null, {timeout:20000});
// Rapidly toggle studio open/close MANY times before monaco finishes loading.
for (let k=0;k<10;k++){
  try{ await p.evaluate(()=>window.nav('studio')); }catch(e){}
  await p.waitForTimeout(120);
}
await p.waitForTimeout(2500);
console.log('loader.js requests:', loaderReq);
console.log('monaco errors:', errs.size);
[...errs].forEach(e=>console.log('  •',e));
await b.close();
