import { chromium } from 'playwright-core';
const b = await chromium.launch({ headless: true });
const p = await b.newPage();
await p.addInitScript(() => {
  const orig = JSON.parse;
  window.__parsestack = [];
  JSON.parse = function (str, reviver) {
    try { return orig(str, reviver); }
    catch (e) {
      if (/Internal S|Unexpected token/.test(String(str).slice(0, 30))) {
        window.__parsestack.push(String((new Error('x')).stack).split('\n').slice(0, 9).join('|'));
      }
      throw e;
    }
  };
});
await p.goto('http://localhost:8787/', { waitUntil: 'domcontentloaded' });
await p.waitForFunction(() => typeof window.nav === 'function', null, { timeout: 25000 });
await p.waitForTimeout(600);
const panes = ['kanban','supervisor','a2a','settings','hierarchy','docs','prompts','templates','swarm','galaxy','dashboard','finops','evals','mcp','terminal','composer','goals'];
for (const pane of panes) {
  try { await p.evaluate((p2) => window.nav(p2), pane); } catch (e) {}
  await p.waitForTimeout(220);
  const n = await p.evaluate(() => Array.from(document.querySelectorAll('button,[data-act-click]')).filter(e => e.isConnected && e.getClientRects().length > 0).length);
  for (let i = 0; i < Math.min(n, 170); i++) {
    try {
      await p.evaluate((idx) => {
        const els = Array.from(document.querySelectorAll('button,[data-act-click]')).filter(e => e.isConnected && e.getClientRects().length > 0);
        const el = els[idx]; if (!el) return;
        const a = el.getAttribute('data-act-click') || '';
        if (/delete|remove|clear|wipe|confirm|submit|logout|disconnect|danger|destroy/i.test(a)) return;
        el.click();
      }, i);
      await p.waitForTimeout(9);
    } catch (e) {}
  }
}
const reported = await p.evaluate(() => window.__parsestack ? window.__parsestack.length : -1);
const stack = await p.evaluate(() => window.__parsestack || []);
console.log('JSON.parse failures observed:', reported);
stack.slice(0, 6).forEach(s => console.log('  •', s));
await b.close();
