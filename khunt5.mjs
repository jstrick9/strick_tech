import { chromium } from 'playwright-core';
const b = await chromium.launch({ headless: true });
const p = await b.newPage();
await p.goto('http://localhost:8787/', { waitUntil: 'networkidle' });
await p.waitForTimeout(700);
// Stand up a MutationObserver-free check: function that, given the current DOM,
// finds VISIBLE overlay-ish scrims (position fixed, non-zero size, above content)
// that are NOT collected by collectOpenModals and NOT currently expected.
const check = async () => await p.evaluate(() => {
  const collected = new Set((window.collectOpenModals?window.collectOpenModals():[]).map(m=>m.id||m.className));
  const notReporter = r => (r.id||'').match(/studio-|con-panel|chat-dropzone|sb-|sidebar|agent-list|rag-|stream-/);
  const out = [];
  document.querySelectorAll('div,section,aside').forEach(el => {
    if (!el.isConnected) return;
    const id = el.id; const cls = String(el.className||'');
    if (!/overlay|modal|dialog|modal-back|^modal$/.test(cls) && !/^(gmodal|.*-overlay|.*-modal)$/.test(id)) return;
    if (collected.has(id) || (id && notReporter({id}))) return;
    const cs = getComputedStyle(el);
    if (cs.position !== 'fixed' && !/fixed/.test(el.style.cssText)) return; // overlays are fixed
    const r = el.getBoundingClientRect();
    // visible scrim: covers a good chunk of the viewport or has pointer events + bg
    const visible = cs.display !== 'none' && cs.visibility !== 'hidden' && r.width>150 && r.height>100;
    if (visible) out.push({id, cls: cls.slice(0,30), pos: cs.position, w:Math.round(r.width)});
  });
  return out;
});
// Walk ALL registered panes, and after each, look for uncollected visible scrims.
const paneKeys = await p.evaluate(()=>Object.keys(window.MASTER_PANE_REGISTRY||{}));
const found = {};
for (const pane of paneKeys) {
  try { await p.evaluate((pn)=>window.nav(pn), pane); await p.waitForTimeout(250); } catch(e){}
  const un = await check();
  if (un.length) found[pane] = un;
}
console.log('Panes with an OPEN but UNCOLLECTED visible scrim:', Object.keys(found).length);
for (const pane in found) console.log('  ', pane, '->', JSON.stringify(found[pane]));
await b.close();
