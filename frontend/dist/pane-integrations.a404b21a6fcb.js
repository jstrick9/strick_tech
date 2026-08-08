
;/* 22-integrations.js */
async function renderIntegrations() {
const pane=document.getElementById('pane-integrations'); if(!pane)return;
pane.innerHTML='<div style="padding:20px;color:var(--text-2)">Loading…</div>';
try {
const [iR,cR,dR,rR]=await Promise.all([
fetch('/api/integrations'),
fetch('/api/integrations/categories'),
fetch('/api/integrations/docs/types'),
fetch('/api/integrations/rules'),
]);
if (!iR.ok||!cR.ok||!dR.ok||!rR.ok) throw new Error('Failed to load integrations data');
const [intsRaw,catsRaw,docTypesRaw,rulesRaw]=await Promise.all([iR.json(),cR.json(),dR.json(),rR.json()]);
const ints     = Array.isArray(intsRaw)     ? intsRaw     : (intsRaw?.integrations || []);
const cats     = Array.isArray(catsRaw)     ? catsRaw     : (catsRaw?.categories   || []);
const docTypes = Array.isArray(docTypesRaw) ? docTypesRaw : (docTypesRaw?.types     || []);
const rules    = Array.isArray(rulesRaw)    ? rulesRaw    : (rulesRaw?.rules        || []);
const catColors={payments:'#4cc98a',auth:'#5b8af8',backend:'#9d74f5',ai:'#e8a237',email:'#38c5d8',database:'#f08850',analytics:'#f06080'};
pane.innerHTML=`
    ${pageHeader?.({title:'🔌 Integrations & Docs',subtitle:'Scaffold Stripe, Auth, Email. Generate docs. Set AI project rules.'})||'<div class="u-769fed37"><h2>🔌 Integrations</h2></div>'}
    <div class="page-content">
    <div style="display:flex;gap:2px;background:var(--bg-2);border-radius:var(--radius-sm);padding:3px;margin-bottom:16px;width:fit-content">
      <button data-act-click="switchIntTab('ints')" id="inttab-ints" class="btn btn-primary btn-sm">🔌 Integrations</button>
      <button data-act-click="switchIntTab('docs')" id="inttab-docs" class="btn btn-ghost btn-sm">📖 Docs</button>
      <button data-act-click="switchIntTab('rules')" id="inttab-rules" class="btn btn-ghost btn-sm">📋 Rules</button>
    </div>
    <div id="int-tab-ints">
      <div style="display:flex;gap:8px;margin-bottom:12px;flex-wrap:wrap;align-items:center">
        <div style="display:flex;gap:5px;flex-wrap:wrap;flex:1">
          <button data-act-click="filterInts('all')" class="term-btn" id="intcat-all" style="border-color:var(--accent-text);color:var(--accent-hi)">All (${ints.length})</button>
          ${cats.map(c=>`<button data-act-click="filterInts(${JSON.stringify(c.id)})" class="term-btn" id="intcat-${c.id}">${escHtml(c.id)} (${c.count})</button>`).join('')}
        </div>
        <div style="display:flex;gap:6px;flex-shrink:0">
          <button class="btn-sm" data-act-click="intStripeWire()" title="Generate Stripe checkout page">💳 Stripe Wire</button>
          <button class="btn-sm" data-act-click="intAuthWire()" title="Generate auth login page">🔐 Auth Wire</button>
        </div>
      </div>
      <div id="ints-grid" style="display:grid;grid-template-columns:repeat(auto-fill,minmax(270px,1fr));gap:10px">
        ${ints.map(i=>`
          <div class="card card-interactive" id="int-card-${i.id}" data-category="${i.category}">
            <div style="display:flex;align-items:center;gap:10px;margin-bottom:8px">
              <span class="u-881f70f9">${i.emoji}</span>
              <div><div class="u-88697aec">${escHtml(i.name)}</div>
              <span style="font-size:10px;padding:2px 7px;border-radius:99px;background:${catColors[i.category]||'var(--bg-4)'}22;color:${catColors[i.category]||'var(--text-2)'}">${i.category}</span></div>
            </div>
            <p style="font-size:12px;color:var(--text-2);margin-bottom:8px;line-height:1.5;min-height:28px">${escHtml(i.description)}</p>
            <div style="display:flex;gap:5px;margin-bottom:8px;flex-wrap:wrap">${i.env_vars.slice(0,2).map(v=>`<code style="font-size:10px;background:var(--bg-0);padding:1px 5px;border-radius:3px;color:var(--text-2)">${v}</code>`).join('')}${i.env_vars.length>2?`<span style="font-size:10px;color:var(--text-3)">+${i.env_vars.length-2}</span>`:''}</div>
            <div style="display:flex;gap:5px"><button data-act-click="scaffoldIntegration(${JSON.stringify(i.id)})" class="btn btn-primary btn-sm u-97445a8d" >⚡ Scaffold</button><a href="${safeUrl(i.docs_url)}" target="_blank" class="btn btn-ghost btn-sm">Docs ↗</a></div>
            <div id="int-status-${i.id}" style="font-size:11px;color:var(--text-2);margin-top:5px;display:none"></div>
          </div>`).join('')}
      </div>
    </div>
    <div id="int-tab-docs" style="display:none">
      <div style="display:grid;grid-template-columns:1fr 1fr;gap:16px">
        <div class="card">
          <h3 class="u-da12f285">Auto-generate documentation</h3>
          <div style="display:flex;flex-direction:column;gap:7px">
            ${docTypes.map(d=>`<div style="display:flex;align-items:center;justify-content:space-between;background:var(--bg-3);border-radius:var(--radius-sm);padding:9px 12px"><div><div class="u-eb673ec6">${d.label}</div><div style="font-size:11.5px;color:var(--text-2)">${d.desc}</div></div><button data-act-click="generateDoc(${JSON.stringify(d.id)})" class="btn btn-primary btn-sm" id="docbtn-${d.id}">Generate</button></div>`).join('')}
          </div>
          <div id="doc-status" style="font-size:12px;color:var(--text-2);margin-top:10px"></div>
        </div>
        <div class="card"><h3 class="u-fdf33f23">Preview</h3><div id="docs-preview" style="font-size:12px;color:var(--text-3)">Generate a doc to see it here</div></div>
      </div>
    </div>
    <div id="int-tab-rules" style="display:none">
      <div style="display:grid;grid-template-columns:1fr 1fr;gap:16px">
        <div class="card">
          <h3 class="u-4e420aff">📋 .agenticrules</h3>
          <p style="font-size:12px;color:var(--text-2);margin-bottom:10px">Like Cursor's .cursorrules — all AI agents read these rules before every response.</p>
          <textarea id="rules-editor" style="width:100%;min-height:280px;background:var(--bg-1);border:1px solid var(--border);border-radius:var(--radius-sm);padding:10px;color:var(--text-0);font-size:12px;font-family:'JetBrains Mono',monospace;resize:vertical;outline:none;line-height:1.6">${escHtml(rules.content||'')}</textarea>
          <div style="display:flex;gap:8px;margin-top:8px"><button data-act-click="saveProjectRules()" class="btn btn-primary u-97445a8d" >💾 Save</button><button data-act-click="loadDefaultRules()" class="btn btn-ghost btn-sm">Reset</button></div>
        </div>
        <div class="card">
          <h3 class="u-761d3add">How rules work</h3>
          <p style="font-size:12.5px;color:var(--text-2);line-height:1.65;margin-bottom:12px">Rules enforce consistency across all AI agents in your workspace — tech stack, code style, behavior patterns.</p>
          <div class="u-6cb285c6">
            ${[['Tech Stack','- Framework: Next.js 15\n- CSS: Tailwind + shadcn'],['Code Style','- TypeScript always\n- async/await preferred'],['Behavior','- Complete code only\n- Add error handling']].map(([l,e])=>`<div style="margin-bottom:8px;background:var(--bg-3);border-radius:6px;padding:8px"><div style="font-weight:600;font-size:11px;color:var(--text-2);margin-bottom:3px">${l}</div><pre style="font-size:11px;color:var(--text-1);white-space:pre-wrap;font-family:monospace">${escHtml(e)}</pre></div>`).join('')}
          </div>
        </div>
      </div>
    </div>
    </div>`;
} catch(e) {
pane.innerHTML = '<div style="padding:20px;color:var(--error)">Error loading integrations: ' + escHtml(e?.message||'') + '</div>';
}
}
let currentIntTab='ints';
function switchIntTab(tab){currentIntTab=tab;['ints','docs','rules'].forEach(t=>{const e=document.getElementById(`int-tab-${t}`);const b=document.getElementById(`inttab-${t}`);if(e)e.style.display=t===tab?'':'none';if(b)b.className=`btn ${t===tab?'btn-primary':'btn-ghost'} btn-sm`;});}
function filterInts(cat){document.querySelectorAll('#ints-grid .card').forEach(c=>{c.style.display=cat==='all'||c.dataset.category===cat?'':'none';});document.querySelectorAll('[id^="intcat-"]').forEach(b=>{b.style.borderColor=b.id===`intcat-${cat}`?'var(--accent)':'';b.style.color=b.id===`intcat-${cat}`?'var(--accent-hi)':'';})}
async function scaffoldIntegration(id){
const btn=document.querySelector(`#int-card-${JSON.stringify(id).replace(/"/g,'')} .btn-primary`)||document.querySelector(`[data-act-click="scaffoldIntegration(${JSON.stringify(id)})"]`);
const st=document.getElementById(`int-status-${id}`);
if(btn){btn.disabled=true;btn.textContent='⏳…';}
if(st){st.style.display='block';st.textContent='Scaffolding…';}
try {
const r=await fetch(`/api/integrations/${encodeURIComponent(id)}/scaffold`,{method:'POST',headers:{'Content-Type':'application/json'},body:JSON.stringify({framework:'web'})});
if(!r.ok){if(st)st.textContent='✗ HTTP '+r.status;showToast('Scaffold failed: HTTP '+r.status);return;}
const j=await r.json();
if(j.ok){
if(st)st.innerHTML=`✅ ${j.files?.length||0} files · <span style="color:var(--text-3)">${escHtml((j.next_steps||[]).slice(0,1).join(''))}</span>`;
showToast(`✅ ${escHtml(j.integration||id)} scaffolded`);
studioLoadFileTree?.();
} else {
if(st)st.textContent='✗ '+(j.error||'Failed');
showToast('Scaffold failed: '+(j.error||'Unknown error'));
}
} catch(ex) {
if(st)st.textContent='✗ '+ex?.message;
showToast('Scaffold error: '+ex?.message);
}
if(btn){btn.disabled=false;btn.textContent='⚡ Scaffold';}
}
async function generateDoc(type) {
const btn  = document.getElementById(`docbtn-${type}`);
const st   = document.getElementById('doc-status');
const prev = document.getElementById('docs-preview');
if (btn) { btn.disabled=true; btn.textContent='⏳…'; }
if (st)  st.textContent = `Generating ${type}…`;
try {
const r = await fetch('/api/integrations/docs/generate', {
method:'POST', headers:{'Content-Type':'application/json'},
body: JSON.stringify({type})
});
if (!r.ok) { if(st) st.textContent='✗ HTTP '+r.status; return; }
const j = await r.json();
if (j.ok) {
if (st)   st.textContent = `✅ ${escHtml(j.filename||type+'.md')} saved`;
if (prev) prev.innerHTML = `
        <div class="u-d3e5189a">${escHtml(j.filename||'')}</div>
        <pre style="font-size:11px;white-space:pre-wrap;max-height:260px;overflow-y:auto;color:var(--text-1)">${escHtml((j.content||'').slice(0,1200))}</pre>`;
showToast(`📄 ${j.filename} generated`);
studioLoadFileTree?.();
} else {
if (st) st.textContent = '✗ '+(j.error||'Generation failed');
showToast('Doc generation failed: '+(j.error||'Unknown'));
}
} catch(ex) {
if (st) st.textContent = '✗ '+ex?.message;
showToast('Doc error: '+ex?.message);
}
if (btn) { btn.disabled=false; btn.textContent='Generate'; }
}
async function saveProjectRules() {
const c = document.getElementById('rules-editor')?.value || '';
if (!c.trim()) { showToast('⚠️ Rules cannot be empty'); return; }
try {
const r = await fetch('/api/integrations/rules', {
method:'POST', headers:{'Content-Type':'application/json'},
body: JSON.stringify({content: c})
});
if (!r.ok) { showToast('Save failed: HTTP '+r.status); return; }
const j = await r.json();
if (j.ok) showToast('📋 Rules saved — agents will follow them');
else showToast('Save failed: '+(j.error||'Unknown'));
} catch(ex) {
showToast('Save error: '+ex?.message);
}
}
async function loadDefaultRules() {
try {
const r = await fetch('/api/integrations/rules');
if (!r.ok) { showToast(humanError(httpError(r), {action:'load your project rules'})); return; }
const j = await r.json();
const e = document.getElementById('rules-editor');
if (e && j.content) { e.value = j.content; showToast('📋 Rules loaded'); }
} catch(ex) {
showToast('Load error: '+ex?.message);
}
}
async function intStripeWire() {
const mode     = await gmPrompt('Stripe mode (payment|subscription):', 'payment');
if (!mode) return;
const product  = await gmPrompt('Product name:', 'Pro Plan');
if (!product) return;
const amtStr   = await gmPrompt('Amount in cents (e.g. 1999 for $19.99):', '1999');
const amount   = parseInt(amtStr||'1999');
showToast('⚡ Generating Stripe integration…');
try {
const r = await fetch('/api/integrations/stripe/wire', {
method:'POST', headers:{'Content-Type':'application/json'},
body: JSON.stringify({mode, product_name: product, amount_cents: amount, include_webhook: true})
});
if (!r.ok) { gmAlert('Stripe wire failed: HTTP '+r.status); return; }
const d = await r.json();
if (d.ok) {
showToast(`✅ Stripe checkout generated → ${d.preview_url}`);
studioLoadFileTree?.();
} else {
gmAlert('Stripe wire failed: '+(d.error||'Unknown'));
}
} catch(ex) {
gmAlert('Stripe wire error: '+ex?.message);
}
}
async function intAuthWire() {
const provider = await gmPrompt('Auth provider (nextauth|clerk|supabase|firebase|auth0|magic):', 'clerk');
if (!provider) return;
showToast('⚡ Generating auth integration…');
try {
const r = await fetch('/api/integrations/auth/wire', {
method:'POST', headers:{'Content-Type':'application/json'},
body: JSON.stringify({provider, oauth_providers:['google','github']})
});
if (!r.ok) { gmAlert('Auth wire failed: HTTP '+r.status); return; }
const d = await r.json();
if (d.ok) {
showToast(`✅ Auth page generated → ${d.preview_url}`);
studioLoadFileTree?.();
} else {
gmAlert('Auth wire failed: '+(d.error||'Unknown'));
}
} catch(ex) {
gmAlert('Auth wire error: '+ex?.message);
}
}
