import { chromium } from 'playwright-core';
const b = await chromium.launch({ headless: true });
const p = await b.newPage();
await p.goto('http://localhost:8787/', { waitUntil: 'networkidle' });
await p.evaluate(() => window.nav('kanban'));
await p.waitForTimeout(500);
// find a real id
const act = await p.evaluate(() => {
  const el = document.querySelector('.kanban-card-action');
  return el ? (el.getAttribute('data-act-click')||'') : '';
});
const m = act.match(/kanbanOpenEditModal\((.+?)\)/);
const id = m ? Number(m[1]) : 6;
await p.evaluate((tid) => window.kanbanOpenEditModal(tid), id);
await p.waitForTimeout(300);
// Focus a control inside the overlay
await p.evaluate(() => {
  const ov = document.getElementById('kanban-modal-overlay');
  const first = ov.querySelector('input,button,textarea,select');
  if (first) first.focus();
});
// Check focus-trap: focus the LAST control, press Tab, expect wrap to first
const focusResult = await p.evaluate(() => {
  const ov = document.getElementById('kanban-modal-overlay');
  const items = Array.from(ov.querySelectorAll('button,input,textarea,select,a[href],[tabindex]'))
    .filter(el => el.offsetParent !== null && el.getAttribute('tabindex') !== '-1');
  const last = items[items.length - 1], first = items[0];
  last.focus();
  return { n: items.length, lastId: last.id || last.className, firstId: first.id || first.className };
});
console.log('TRAP items:', JSON.stringify(focusResult));
// dispatch Tab
await p.keyboard.press('Tab');
await p.waitForTimeout(120);
const afterTab = await p.evaluate(() => {
  const a = document.activeElement;
  return a ? (a.id || a.className || a.tagName) : String(a);
});
console.log('AFTER TAB (should wrap to first):', afterTab, 'expected', focusResult.firstId, 'onLast=', focusResult.lastId);
// Now Escape and check focus returns to opener
await p.keyboard.press('Escape');
await p.waitForTimeout(200);
const postEsc = await p.evaluate(() => ({
  overlayGone: !document.getElementById('kanban-modal-overlay'),
  active: (document.activeElement && (document.activeElement.id || document.activeElement.className)) || String(document.activeElement)
}));
console.log('AFTER ESCAPE:', JSON.stringify(postEsc));
await b.close();
