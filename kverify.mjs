import { chromium } from 'playwright-core';
const b = await chromium.launch({ headless: true });
const p = await b.newPage();
await p.goto('http://localhost:8787/', { waitUntil: 'networkidle' });
const r = await p.evaluate(() => {
  const src = document.querySelector('script[src*="app."]');
  return {
    bundle: src ? src.getAttribute('src') : 'none',
    hasCollect: typeof collectOpenModals === 'function',
  };
});
console.log(JSON.stringify(r));
await b.close();
