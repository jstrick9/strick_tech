import { chromium } from 'playwright-core';
const b = await chromium.launch({ headless: true });
const p = await b.newPage();
const errors = [];
p.on('console', m => { if (m.type()==='error') errors.push(m.text()); });
await p.goto('http://localhost:8787/', { waitUntil: 'networkidle' });
await p.evaluate(() => window.nav('kanban'));
await p.waitForTimeout(600);
// find a real task id from an Edit action
const act = await p.evaluate(() => {
  const el = document.querySelector('.kanban-card-action[aria-label*="Edit"], .kanban-card-action');
  return el ? (el.getAttribute('data-act-click')||'') : '';
});
const m = act.match(/kanbanOpenEditModal\((.+?)\)/);
const id = m ? JSON.parse(m[1] === '\'\'' ? '"":-' : m[1].replace(/'/g,'"')) : null;
console.log('found action:', act, '-> id', id);
const opened = await p.evaluate((tid) => {
  if (typeof window.kanbanOpenEditModal === 'function') { window.kanbanOpenEditModal(tid); return true; }
  return false;
}, id);
console.log('opened:', opened);
await p.waitForTimeout(400);
const before = await p.evaluate(() => {
  const ov = document.getElementById('kanban-modal-overlay');
  return {
    exists: !!ov,
    visible: !!ov && (ov.style.display !== 'none') && ov.offsetParent !== null,
    collected: (typeof collectOpenModals === 'function') ? collectOpenModals().map(x=>x.id||x.className) : null
  };
});
console.log('BEFORE:', JSON.stringify(before));
// Escape
await p.keyboard.press('Escape');
await p.waitForTimeout(300);
const after = await p.evaluate(() => ({
  exists: !!document.getElementById('kanban-modal-overlay'),
  active: (document.activeElement && (document.activeElement.id || document.activeElement.className)) || String(document.activeElement)
}));
console.log('AFTER ESCAPE:', JSON.stringify(after));
console.log('CONSOLE ERRORS:', errors.slice(0,10));
await b.close();
