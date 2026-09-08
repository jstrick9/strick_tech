import { chromium } from 'playwright-core';
const b = await chromium.launch({ headless: true });
const p = await b.newPage();
let counts = {};
p.on('request', r => { const u=r.url(); for(const key of ['/api/control/stats','/api/system/metrics','/api/dashboard','/api/supervisor','/api/agents']) if(u.includes(key)) counts[key]=(counts[key]||0)+1; });
await p.goto('http://localhost:8787/', { waitUntil:'domcontentloaded' });
await p.waitForFunction(()=>typeof window.nav==='function', null, {timeout:25000});
await p.waitForTimeout(500);
// visit control tower, wait 12s (2+ poll cycles)
await p.evaluate(()=>window.nav('control')); 
await p.waitForTimeout(12000);
const duringControl = {...counts};
counts={}; const reset={...counts};
// navigate away, wait 12s
await p.evaluate(()=>window.nav('chat'));
await p.waitForTimeout(12000);
const afterLeave = {...counts};
console.log('control/stats during control pane:', duringControl['/api/control/stats']||0);
console.log('control/stats AFTER leaving (should stop):', afterLeave['/api/control/stats']||0);
await b.close();
