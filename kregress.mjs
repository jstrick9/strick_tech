import { chromium } from 'playwright-core';
const b = await chromium.launch({ headless: true });
const p = await b.newPage();
await p.goto('http://localhost:8787/', { waitUntil: 'networkidle' });
await p.evaluate(() => window.nav('kanban'));
await p.waitForTimeout(500);
const openCount = async () => await p.evaluate(() => ({
  btn: !!document.getElementById('kanban-modal-overlay'),
}));
// open edit task 1
const id1 = await p.evaluate(() => {
  const el = document.querySelector('.kanban-card-action');
  const m = (el.getAttribute('data-act-click')||'').match(/kanbanOpenEditModal\((.+?)\)/);
  return m ? Number(m[1]) : null;
});
await p.evaluate((tid) => window.kanbanOpenEditModal(tid), id1);
await p.waitForTimeout(200);
console.log('after open 1, overlay:', await openCount());
// close via Escape
await p.keyboard.press('Escape');
await p.waitForTimeout(200);
console.log('after esc 1, overlay:', await openCount());
// try to open again
await p.evaluate((tid) => window.kanbanOpenEditModal(tid), id1);
await p.waitForTimeout(200);
console.log('after open 2, overlay:', await openCount(), '<-- if false, REOPEN BROKEN');
await b.close();
