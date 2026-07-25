// Agentic OS — Skills Hub
// Extracted from 01-app-core.js for modularity
// ── Skills Hub ────────────────────────────────────────────────────
let allSkills = [], activeSkill = null, skillCategory = 'all';

async function renderSkills() {
  const pane = document.getElementById('pane-skills');
  if (!pane) return;
  pane.innerHTML = `<div class="section-head">
    <div><h2>⚡ Skills Hub</h2><p>12 pre-built AI skills + create your own. Run any skill with one click.</p></div>
    <button onclick="openCreateSkill()" class="btn btn-primary btn-sm">＋ New Skill</button>
  </div>
  <div style="display:flex;gap:8px;flex-wrap:wrap;margin-bottom:16px" id="skill-cats"></div>
  <div style="display:grid;grid-template-columns:repeat(auto-fill,minmax(240px,1fr));gap:12px" id="skill-grid"></div>
  <!-- Run modal -->
  <div id="skill-run-modal" style="display:none;position:fixed;inset:0;background:rgba(4,6,14,.85);z-index:9000;align-items:center;justify-content:center;backdrop-filter:blur(6px)" onclick="if(event.target===this)closeSkillModal()">
    <div style="background:var(--bg-2);border:1px solid var(--border-hi);border-radius:var(--radius-lg);width:100%;max-width:600px;padding:24px;max-height:85vh;overflow-y:auto">
      <h2 id="srm-title" style="font-size:18px;font-weight:800;margin-bottom:6px"></h2>
      <p id="srm-desc" style="font-size:13px;color:var(--text-2);margin-bottom:18px"></p>
      <div id="srm-inputs" style="margin-bottom:16px"></div>
      <div style="display:flex;gap:8px;margin-bottom:16px">
        <button onclick="execSkill()" class="btn btn-primary" style="flex:1" id="srm-run">▶ Run Skill</button>
        <button onclick="closeSkillModal()" class="btn btn-ghost">Cancel</button>
      </div>
      <div id="srm-result" style="display:none;background:var(--bg-1);border:1px solid var(--border);border-radius:var(--radius-sm);padding:14px;font-size:13px;line-height:1.6;max-height:400px;overflow-y:auto"></div>
    </div>
  </div>`;

  await loadSkills();
}

async function loadSkills() {
  try {
    const [sData, cData] = await Promise.all([
      fetch('/api/skills').then(r=>r.ok?r.json().catch(()=>{}):{skills:[]}).catch(()=>({skills:[]})),
      fetch('/api/skills/categories').then(r=>r.ok?r.json().catch(()=>{}):{categories:[]}).catch(()=>({categories:[]}))
    ]);
    allSkills = Array.isArray(sData) ? sData : (Array.isArray(sData?.skills) ? sData.skills : []);
    const cats = Array.isArray(cData) ? cData : (Array.isArray(cData?.categories) ? cData.categories : []);
    // Render category pills
    const catEl = document.getElementById('skill-cats');
    if (catEl) catEl.innerHTML =
      `<span class="tag ${skillCategory==='all'?'blue':''}" data-cat="all" style="cursor:pointer;padding:5px 12px" onclick="filterSkills('all')">All (${allSkills.length})</span>` +
      cats.map(c => `<span class="tag ${skillCategory===c.id?'blue':''}" data-cat="${c.id}" style="cursor:pointer;padding:5px 12px" onclick="filterSkills('${escHtml(c.id)}')">${escHtml(c.id)} (${c.count})</span>`).join('');
    renderSkillGrid();
  } catch(e) { console.warn('Failed to load skills:', e); toast('Loaded offline skills', 'ok'); }
}

function filterSkills(cat) {
  skillCategory = cat;
  document.querySelectorAll('#skill-cats .tag').forEach(el => {
    const elCat = el.dataset.cat || (el.textContent.startsWith('All') ? 'all' : '');
    el.classList.toggle('blue', elCat === cat);
  });
  renderSkillGrid();
}

function renderSkillGrid() {
  const grid = document.getElementById('skill-grid');
  if (!grid) return;
  const filtered = skillCategory === 'all' ? allSkills : allSkills.filter(s => s.category === skillCategory);
  grid.innerHTML = filtered.map(s => `
    <div style="background:var(--bg-2);border:1px solid var(--border);border-radius:var(--radius-lg);padding:16px;cursor:pointer;transition:var(--transition)"
         onmouseover="this.style.borderColor='var(--border-hi)'" onmouseout="this.style.borderColor='var(--border)'"
         onclick="openSkillModal(${JSON.stringify(s.id)})">
      <div style="font-size:24px;margin-bottom:8px">${s.emoji||'⚡'}</div>
      <div style="font-weight:700;font-size:14px;margin-bottom:4px">${escHtml(s.name)}</div>
      <div style="font-size:12px;color:var(--text-2);margin-bottom:10px;min-height:32px">${escHtml(s.description||'')}</div>
      <div style="display:flex;align-items:center;justify-content:space-between">
        <span class="tag">${s.category||'general'}</span>
        <span style="font-size:11px;color:var(--text-2)">🤖 ${s.agent||'brain'}</span>
      </div>
    </div>`).join('');
}

function openSkillModal(skillId) {
  activeSkill = allSkills.find(s => s.id === skillId);
  if (!activeSkill) return;
  document.getElementById('srm-title').textContent = `${activeSkill.emoji||'⚡'} ${activeSkill.name}`;
  document.getElementById('srm-desc').textContent  = activeSkill.description || '';
  // Build inputs
  const inputsEl = document.getElementById('srm-inputs');
  inputsEl.innerHTML = (activeSkill.inputs||[]).map(inp => `
    <div style="margin-bottom:12px">
      <label style="font-size:11px;font-weight:700;color:var(--text-2);text-transform:uppercase;letter-spacing:.5px;display:block;margin-bottom:5px">
        ${escHtml(inp.label)}${inp.required?` <span style="color:var(--red)">*</span>`:''}
      </label>
      ${inp.type === 'textarea'
        ? `<textarea id="si-${inp.id}" placeholder="${escHtml(inp.label)}…" style="width:100%;background:var(--bg-1);border:1px solid var(--border);border-radius:var(--radius-sm);padding:8px;color:var(--text-0);font-size:13px;resize:vertical;min-height:80px;outline:none;font-family:inherit"></textarea>`
        : inp.type === 'select'
        ? `<select id="si-${inp.id}" style="width:100%;background:var(--bg-1);border:1px solid var(--border);border-radius:var(--radius-sm);padding:8px;color:var(--text-0);font-size:13px;outline:none">
             ${(inp.options||[]).map(o=>`<option value="${o}">${o}</option>`).join('')}
           </select>`
        : `<input id="si-${inp.id}" type="text" placeholder="${escHtml(inp.label)}…" style="width:100%;background:var(--bg-1);border:1px solid var(--border);border-radius:var(--radius-sm);padding:8px;color:var(--text-0);font-size:13px;outline:none">`
      }
    </div>`).join('') || '<div style="color:var(--text-2);font-size:13px">No inputs required — click Run to execute.</div>';
  document.getElementById('srm-result').style.display = 'none';
  document.getElementById('skill-run-modal').style.display = 'flex';
}

function closeSkillModal() {
  document.getElementById('skill-run-modal').style.display = 'none';
  activeSkill = null;
}

async function execSkill() {
  if (!activeSkill) return;
  // Collect inputs
  const inputs = {};
  (activeSkill.inputs||[]).forEach(inp => {
    const el = document.getElementById('si-' + inp.id);
    if (el) inputs[inp.id] = el.value;
  });
  // Validate required
  const missing = (activeSkill.inputs||[]).filter(i => i.required && !inputs[i.id]?.trim());
  if (missing.length) { toast('Required: ' + missing.map(m=>m.label).join(', '), 'warn'); return; }

  const btn = document.getElementById('srm-run');
  btn.disabled = true; btn.textContent = '⏳ Running…';
  const resEl = document.getElementById('srm-result');
  resEl.style.display = 'block';
  resEl.innerHTML = `<div style="color:var(--text-2)">Running ${escHtml(activeSkill.name)}…</div>`;

  try {
    const r = await fetch('/api/skills/run', {
      method: 'POST', headers: {'Content-Type':'application/json'},
      body: JSON.stringify({ skill_id: activeSkill.id, inputs })
    });
    if (!r.ok) throw new Error('Server error ' + r.status);
    const j = await r.json();
    resEl.innerHTML = `
      <div style="display:flex;align-items:center;gap:8px;margin-bottom:10px">
        <span style="color:${j.ok?'var(--green)':'var(--red)'};">${j.ok?'✅':'❌'}</span>
        <span style="font-size:12px;color:var(--text-2)">${escHtml(j.agent||'')} · ${j.latency_ms||0}ms · ${j.tokens||0} tokens · $${(j.cost||0).toFixed(5)}</span>
        <button onclick="speakText(${JSON.stringify((j.output||'').slice(0,1000)).replace(/'/g,'&#39;')}, '${j.agent||'default'}')" class="btn btn-ghost btn-sm" style="margin-left:auto">🔊 Listen</button>
      </div>
      <div style="white-space:pre-wrap;line-height:1.6">${renderMarkdown(j.output||'(empty)')}</div>`;
    if (j.ok) toast(`✅ ${activeSkill.name} complete · ${j.latency_ms}ms`, 'ok', 3000);
    else toast('Skill error: ' + (j.error||'check output'), 'err');
  } catch(e) {
    resEl.innerHTML = `<div style="color:var(--red)">Error: ${escHtml(e.message)}</div>`;
    toast('Skill failed', 'err');
  } finally {
    btn.disabled = false; btn.textContent = '▶ Run Skill';
  }
}

async function openCreateSkill() {
  const name = await gmPrompt('New Skill', 'Skill name (e.g. "LinkedIn Post Writer")');
  if (!name) return;
  const prompt_tmpl = await gmPrompt('Prompt Template', 'Use {placeholder} for inputs\ne.g. "Write a {tone} email about {topic}"', '', true);
  if (prompt_tmpl === null) return;
  const agent = await gmPrompt('Agent', 'e.g. brain, builder, researcher', 'brain') || 'brain';
  try {
    const r = await fetch('/api/skills', {
      method: 'POST', headers: {'Content-Type':'application/json'},
      body: JSON.stringify({ name, prompt_template: prompt_tmpl||'{prompt}', agent, category: 'custom', emoji: '⚡',
        inputs: [{id:'prompt',label:'Your input',type:'textarea',required:true}] })
    });
    if (!r.ok) { toast('Server error ' + r.status, 'err'); return; }
    const j = await r.json();
    if (j.ok) { toast(`✅ Skill "${name}" created`, 'ok'); loadSkills(); }
    else toast('Error: ' + (j.error||'unknown error'), 'err');
  } catch(ex) { toast('Failed to create skill: ' + ex.message, 'err'); }
}
window.renderSkills = renderSkills;
window.loadSkills = loadSkills;
window.filterSkills = filterSkills;
window.renderSkillGrid = renderSkillGrid;
window.openSkillModal = openSkillModal;
window.closeSkillModal = closeSkillModal;
window.execSkill = execSkill;
window.openCreateSkill = openCreateSkill;

