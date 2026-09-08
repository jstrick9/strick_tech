import { chromium } from 'playwright-core';
const b = await chromium.launch({ headless: true });
const p = await b.newPage();
await p.goto('http://localhost:8787/', { waitUntil: 'networkidle' });
await p.evaluate(() => window.nav('kanban'));
await p.waitForTimeout(500);
const id1 = await p.evaluate(() => {
  const el = document.querySelector('.kanban-card-action');
  const m = (el.getAttribute('data-act-click')||'').match(/kanbanOpenEditModal\((.+?)\)/);
  return m ? Number(m[1]) : null;
});
// open, Escape, reopen twice
await p.evaluate((t)=>window.kanbanOpenEditModal(t), id1);
await p.waitForTimeout(150);
await p.keyboard.press('Escape');
await p.waitForTimeout(150);
await p.evaluate((t)=>window.kanbanOpenEditModal(t), id1);
await p.waitForTimeout(150);
const r2 = await p.evaluate(()=>!!document.getElementById('kanban-modal-overlay'));
await p.evaluate((t)=>{const o=document.getElementById('kanban-modal-overlay'); if(o)o.remove();}, id1);
await p.waitForTimeout(150);
await p.evaluate((t)=>window.kanbanOpenEditModal(t), id1);
await p.waitForTimeout(150);
const r3 = await p.evaluate(()=>!!document.getElementById('kanban-modal-overlay'));
console.log(JSON.stringify({reopenAfterEscape:r2, reopenAfterForceRemove:r3}));
await b.close();
