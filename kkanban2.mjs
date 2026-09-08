import { chromium } from 'playwright-core';
const b = await chromium.launch({ headless: true });
const p = await b.newPage();
const errs = new Set();
p.on('pageerror', e => errs.add('PAGE: '+String(e).slice(0,160)));
await p.goto('http://localhost:8787/', { waitUntil:'domcontentloaded' });
await p.waitForFunction(()=>typeof window.nav==='function', null, {timeout:25000});
await p.waitForTimeout(500);
await p.evaluate(()=>{ const o=document.getElementById('onboarding-modal'); if(o){ try{window.closeOnboardingModal&&window.closeOnboardingModal();}catch(e){o.style.display='none';} } });
await p.evaluate(()=>window.nav('kanban'));
await p.waitForTimeout(1500);
// get an edit action id
const id = await p.evaluate(()=>{ const el=document.querySelector('.kanban-card-action'); const m=(el?.getAttribute('data-act-click')||'').match(/kanbanOpenEditModal\((.+?)\)/); return m?Number(m[1]):null; });
console.log('edit id:', id);
await p.evaluate((tid)=>window.kanbanOpenEditModal(tid), id);
await p.waitForTimeout(300);
const editOpen = await p.evaluate(()=>!!document.getElementById('kanban-modal-overlay'));
// change title and save
await p.fill('#kb-edit-title', 'Edited title ' + Date.now());
await p.click('button[type="submit"]');
await p.waitForTimeout(1000);
const saved = await p.evaluate(()=>({ modalGone: !document.getElementById('kanban-modal-overlay'), sawEdits: /Edited title/.test(document.querySelector('#pane-kanban')?.textContent||'') }));
console.log('edit open:', editOpen, '| save:', JSON.stringify(saved));
// Now delete: reopen and use delete
await p.evaluate((tid)=>window.kanbanOpenEditModal(tid), id);
await p.waitForTimeout(300);
// gmDanger is an in-app modal - click delete then confirm
const delBtn = await p.evaluate(()=>!!document.getElementById('kanban-delete-btn'));
console.log('delete btn present:', delBtn);
if (delBtn) {
  await p.click('#kanban-delete-btn');
  await p.waitForTimeout(600);
  // confirm gmDanger
  const confirmBtn = await p.evaluate(()=>{ const btns=[...document.querySelectorAll('#gmodal button, .gm-modal button, [data-act-click]')]; return btns.map(b=>b.textContent.trim()).filter(t=>/Yes|Delete|Confirm|OK/i.test(t)); });
  console.log('confirm buttons:', confirmBtn);
}
console.log('errors:', errs.size);
[...errs].slice(0,8).forEach(e=>console.log('  •',e));
await b.close();
