import { chromium } from 'playwright-core';
const b = await chromium.launch({ headless: true });
const p = await b.newPage();
const errs = new Set();
p.on('pageerror', e => errs.add('PAGE: '+String(e).slice(0,160)));
p.on('console', m => { if(m.type()==='error' && !/Content Security Policy|inline style|404|401|Failed to load resource/.test(m.text())) errs.add('C: '+m.text().slice(0,140)); });
await p.goto('http://localhost:8787/', { waitUntil:'domcontentloaded' });
await p.waitForFunction(()=>typeof window.nav==='function', null, {timeout:25000});
await p.waitForTimeout(500);
await p.evaluate(()=>{ const o=document.getElementById('onboarding-modal'); if(o){ try{window.closeOnboardingModal&&window.closeOnboardingModal();}catch(e){o.style.display='none';} } });
await p.evaluate(()=>window.nav('kanban'));
await p.waitForTimeout(1500);
const cardCount = await p.evaluate(()=>document.querySelectorAll('.kanban-card').length);
console.log('kanban cards:', cardCount);
// create a task via the create modal
await p.evaluate(()=>window.kanbanOpenCreateModal('todo'));
await p.waitForTimeout(200);
const modalOpen = await p.evaluate(()=>!!document.getElementById('kanban-modal-overlay'));
console.log('create modal open:', modalOpen);
// fill form
await p.fill('#kb-title', 'Probe task ' + Date.now());
await p.selectOption('#kb-status','todo');
await p.click('button[type="submit"]');
await p.waitForTimeout(1200);
const afterCreate = await p.evaluate(()=>({
  modalGone: !document.getElementById('kanban-modal-overlay'),
  cards: document.querySelectorAll('.kanban-card').length,
  createdVisible: /Probe task/.test(document.querySelector('#pane-kanban')?.textContent||'')
}));
console.log('after create:', JSON.stringify(afterCreate));
console.log('errors:', errs.size);
[...errs].slice(0,10).forEach(e=>console.log('  •',e));
await b.close();
