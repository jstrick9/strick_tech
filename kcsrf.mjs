import { chromium } from 'playwright-core';
const b = await chromium.launch({ headless: true });
const p = await b.newPage();
const pinHits = [];
p.on('request', r => {
  if (r.url().includes('/api/profile/pin-pane')) {
    pinHits.push({ url: r.url(), csrf: r.headers()['x-csrf-token'] ? 'present' : 'MISSING', method: r.method() });
  }
});
await p.goto('http://localhost:8787/', { waitUntil: 'domcontentloaded' });
await p.waitForFunction(()=>typeof window.nav==='function', null, {timeout:20000});
await p.waitForTimeout(500);
await p.evaluate(()=>window.nav('kanban'));
await p.waitForTimeout(400);
// find a real pin action and click it
const clicked = await p.evaluate(()=>{
  const el = Array.from(document.querySelectorAll('[data-act-click]')).find(e=>/pinPane|pin-pane|togglePin/.test(e.getAttribute('data-act-click')||''));
  if (!el) return null;
  el.click(); return el.getAttribute('data-act-click');
});
await p.waitForTimeout(600);
console.log('pin action clicked:', clicked);
console.log('pin-pane requests sent with CSRF header:');
pinHits.forEach(h=>console.log('  ', h.method, h.csrf, h.url.split('/pin-pane/').pop()));
await b.close();
