import { chromium } from 'playwright-core';
const b = await chromium.launch({ headless: true });
const p = await b.newPage();
await p.goto('http://localhost:8787/', { waitUntil: 'networkidle' });
await p.waitForTimeout(700);
// Simulate opening the panes that contain bespoke overlays, and trigger one
// overlay each where we can, then check collectOpenModals() vs all scrims.
const panes = ['supervisor','goals','a2a','kanban','hierarchy','settings','templates','prompts'];
const report = [];
for (const pane of panes) {
  await p.evaluate((pn)=>window.nav(pn), pane);
  await p.waitForTimeout(400);
  // Try to open a bespoke overlay if it exists in DOM after rendering
  const overlap = await p.evaluate(() => {
    const collected = new Set((window.collectOpenModals?window.collectOpenModals():[]).map(m=>m.id||m.className));
    const scrims = Array.from(document.querySelectorAll('div'))
      .filter(el => {
        const cls = el.className||'';
        return /overlay|modal|dialog|modal-back|panel/i.test(cls) && el.isConnected;
      })
      .map(el => ({id: el.id, cls: String(el.className).slice(0,40)}))
      .filter(x => x.id);
    // only keep ones NOT in the collected set, that look like real open scrims
    return scrims.filter(x => !collected.has(x.id));
  });
  if (overlap.length) report.push({pane, uncollected: overlap});
}
console.log('UNCOLLECTED bespoke overlays per pane (rendered scrims not in collectOpenModals):');
report.forEach(r=>console.log(' ', r.pane, JSON.stringify(r.uncollected)));
console.log('total panes with uncollected:', report.length);
await b.close();
