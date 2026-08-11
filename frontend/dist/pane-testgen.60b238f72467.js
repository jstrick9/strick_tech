
;/* 34-test-generator.js */
let generatedTestCode = '';
async function renderTestGen() {
const pane = document.getElementById('pane-testgen');
if (!pane) return;
pane.innerHTML = skeletonPage();
try {
const [fr, fwr] = await Promise.all([fetch('/api/preview/files'), fetch('/api/testgen/frameworks')]);
if (!fr.ok || !fwr.ok) {
throw new Error('The server could not return your project files.');
}
const [files, fws] = await Promise.all([fr.json(), fwr.json()]);
const fileList = Array.isArray(files) ? files : (files && files.files) || [];
const fwList = Array.isArray(fws) ? fws : (fws && fws.frameworks) || [];
const codeFiles = fileList.filter(f => /\.(js|jsx|ts|tsx|py)$/.test(f.path));
pane.innerHTML = `
      ${pageHeader({title:'🧪 Test Generator', subtitle:'AI writes comprehensive test suites for any file',actions:[]})}
      <div class="page-content">
      ${helpPanel({title:"AI generates tests you'd spend hours writing",body:'Select a file, choose your framework, get a complete test suite with happy paths, edge cases, mocks, and error handling.',steps:['Select a code file','Choose test framework','Click Generate','Review and save']})}
      <div style="display:grid;grid-template-columns:1fr 1fr;gap:18px">
        <div class="card">
          <h3 class="u-2b583d73">Generate Tests</h3>
          <div class="form-group"><label class="form-label">Source File</label>
            <select id="tg-file" style="width:100%;background:var(--bg-1);border:1px solid var(--border);border-radius:var(--radius-sm);padding:7px 10px;color:var(--text-0);font-size:13px;outline:none">
              <option value="">Select a file…</option>
              ${codeFiles.map(f=>`<option value="${escHtml(f.path)}">${escHtml(f.path)}</option>`).join('')}
            </select>
          </div>
          <div class="form-group"><label class="form-label">Framework</label>
            <select id="tg-framework" style="width:100%;background:var(--bg-1);border:1px solid var(--border);border-radius:var(--radius-sm);padding:7px 10px;color:var(--text-0);font-size:13px;outline:none">
              ${fwList.map(f=>`<option value="${f.id}">${f.id} — ${f.lang}</option>`).join('')}
            </select>
          </div>
          <button data-act-click="generateTests()" class="btn btn-primary" style="width:100%" id="tg-gen-btn">🧪 Generate</button>
          <div id="tg-status" style="font-size:12px;color:var(--text-2);margin-top:8px"></div>
        </div>
        <div class="card">
          <div style="display:flex;align-items:center;justify-content:space-between;margin-bottom:10px">
            <h3>Generated Tests</h3>
            <button data-act-click="saveGeneratedTests()" class="btn btn-primary btn-sm" id="tg-save-btn" style="display:none">💾 Save</button>
          </div>
          <pre id="tg-result" style="background:var(--bg-1);border:1px solid var(--border);border-radius:var(--radius-sm);padding:10px;font-family:'JetBrains Mono',monospace;font-size:11px;min-height:180px;max-height:360px;overflow-y:auto;white-space:pre-wrap;color:var(--text-1)">Select a file and click Generate →</pre>
        </div>
      </div>
      </div>`;
} catch(e) { pane.innerHTML=`<div class="page-content">${emptyState({icon:'⚠️',title:'Error',body:e.message})}</div>`; }
}
async function generateTests() {
const filepath = document.getElementById('tg-file')?.value;
const framework = document.getElementById('tg-framework')?.value||'jest';
if (!filepath) { toast('Select a file first','warn'); return; }
const btn = document.getElementById('tg-gen-btn');
const st  = document.getElementById('tg-status');
const res = document.getElementById('tg-result');
const saveBtn = document.getElementById('tg-save-btn');
btn.disabled=true; btn.textContent='⏳ Generating…';
st.textContent=`Generating ${framework} tests…`;
res.textContent=''; generatedTestCode='';
try {
const resp = await fetch('/api/testgen/generate',{method:'POST',headers:{'Content-Type':'application/json'},
body:JSON.stringify({filepath,framework,stream:true})});
if (!resp.ok) { throw new Error(`Server error: HTTP ${resp.status}`); }
if (!resp.body) { throw new Error('No response body — check server logs'); }
const reader=resp.body.getReader(); const dec=new TextDecoder(); let genError='';
while(true) {
const {done,value}=await reader.read(); if(done) break;
for(const line of dec.decode(value,{stream:true}).split('\n')) {
if(!line.startsWith('data:')) continue;
try {
const d=JSON.parse(line.slice(5).trim());
if(d.type==='error'){ genError=d.error||'No tests were generated.'; continue; }
if(d.delta){generatedTestCode+=d.delta;res.textContent=generatedTestCode;res.scrollTop=res.scrollHeight;}
} catch(e) {}
}
}
if(genError){
generatedTestCode='';
res.textContent=genError;
st.textContent='✗ No tests generated';
if(saveBtn) saveBtn.style.display='none';
toast(genError,'err',5000);
return;
}
st.textContent=`✅ ${generatedTestCode.split('\n').length} lines generated`;
if(saveBtn) saveBtn.style.display='';
} catch(e) { st.textContent='✗ '+e.message; toast('Failed: '+e.message,'err'); }
finally { btn.disabled=false; btn.textContent='🧪 Generate'; }
}
async function saveGeneratedTests() {
const fp = document.getElementById('tg-file')?.value;
const fw = document.getElementById('tg-framework')?.value||'jest';
if(!generatedTestCode||!fp) return;
const extMap={jest:'.test.js',vitest:'.test.ts',pytest:'_test.py',mocha:'.test.js',playwright:'.spec.ts'};
const name = fp.replace(/\.[^.]+$/,'') + (extMap[fw]||'.test.js');
const r = await fetch('/api/preview/save',{method:'POST',headers:{'Content-Type':'application/json'},
body:JSON.stringify({path:name,content:generatedTestCode,author:'testgen',message:`${fw} tests`})});
const j = await r.json();
if(j.ok) { toast(`💾 Saved: ${name}`,'ok',2000); studioLoadFileTree?.(); }
else toast('Save failed','err');
}
