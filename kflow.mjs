import { chromium } from 'playwright-core';
const b = await chromium.launch({ headless: true });
const p = await b.newPage();
const errs = new Set();
p.on('pageerror', e => errs.add('PAGE: '+String(e).slice(0,160)));
p.on('unhandledrejection', e => errs.add('REJECT: '+String(e).slice(0,160)));
p.on('console', m => { if(m.type()==='error' && !/Content Security Policy|inline style|404|401|Failed to load resource/.test(m.text())) errs.add('C: '+m.text().slice(0,150)); });
await p.goto('http://localhost:8787/', { waitUntil: 'domcontentloaded' });
await p.waitForFunction(()=>typeof window.nav==='function', null, {timeout:25000});
await p.waitForTimeout(800);
// Dismiss onboarding if present
await p.evaluate(()=>{ const o=document.getElementById('onboarding-modal'); if(o){ try{ window.closeOnboardingModal&&window.closeOnboardingModal(); }catch(e){ o.style.display='none'; } } });
await p.waitForTimeout(300);
await p.evaluate(()=>window.nav('chat'));
await p.waitForTimeout(500);
const inputVisible = await p.evaluate(()=>{ const i=document.getElementById('chat-input'); return !!i && i.offsetParent!==null; });
console.log('chat input visible:', inputVisible);
if (inputVisible) {
  await p.fill('#chat-input', 'Hello, reply with the single word OK.');
  await p.click('#chat-send');
  await p.waitForTimeout(4500);
  const chatState = await p.evaluate(()=>({
    bubbles: document.querySelectorAll('#chat-messages .msg').length,
    hasError: /Error|❌/.test(document.getElementById('chat-messages')?.textContent||'')
  }));
  console.log('chat flow:', JSON.stringify(chatState));
}
console.log('errors during real flows:', errs.size);
[...errs].slice(0,15).forEach(e=>console.log('  •',e));
await b.close();
