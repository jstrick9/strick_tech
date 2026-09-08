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
const id = await p.evaluate(()=>{ const el=document.querySelector('.kanban-card-action'); const m=(el?.getAttribute('data-act-click')||'').match(/kanbanOpenEditModal\((.+?)\)/); return m?Number(m[1]):null; });
// CREATE a fresh task so delete has a stable target
await p.evaluate(()=>window.kanbanOpenCreateModal('todo'));
await p.waitForTimeout(200);
const uniq='DELME'+Date.now();
await p.fill('#kb-title', uniq);
await p.click('button[type="submit"]');
await p.waitForTimeout(900);
// find the new task's id from its edit action
const newId = await p.evaluate((title)=>{
  const cards=[...document.querySelectorAll('.kanban-card')];
  const c=cards.find(cr=>cr.textContent.includes(title));
  const el=c?.querySelector('.kanban-card-action');
  const m=(el?.getAttribute('data-act-click')||'').match(/kanbanOpenEditModal\((.+?)\)/);
  return m?Number(m[1]):null;
}, uniq);
console.log('new task id to delete:', newId);
await p.evaluate((tid)=>window.kanbanOpenEditModal(tid), newId);
await p.waitForTimeout(300);
await p.click('#kanban-delete-btn');
await p.waitForTimeout(700);
// The gmDanger confirm: find its "Delete" button and click
const clicked = await p.evaluate(()=>{
  const btns=[...document.querySelectorAll('button')].filter(b=>/^Delete$/i.test(b.textContent.trim()));
  if(btns.length){ btns[0].click(); return true; }
  return false;
});
await p.waitForTimeout(1000);
const gone = await p.evaluate((title)=>!Array.from(document.querySelectorAll('.kanban-card')).some(c=>c.textContent.includes(title)), uniq);
console.log('delete confirmed->task gone:', gone);
console.log('errors:', errs.size);
[...errs].slice(0,8).forEach(e=>console.log('  •',e));
await b.close();
