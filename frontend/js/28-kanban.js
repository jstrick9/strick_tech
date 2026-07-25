// Agentic OS — Kanban
// Extracted from 01-app-core.js for modularity
// ── Kanban ────────────────────────────────────────────────────────
async function renderKanban() {
  const pane = document.getElementById('pane-kanban');
  pane.innerHTML = `<div style="display:flex;align-items:center;justify-content:space-between;margin-bottom:16px;flex-shrink:0">
    <div><div style="font-size:17px;font-weight:800">📋 Kanban</div><div style="font-size:13px;color:var(--text-2)">Drag tasks to update status</div></div>
    <button onclick="openNewTaskModal()" class="btn btn-primary btn-sm">＋ Task</button>
  </div>
  <div id="kb-board" style="display:grid;grid-template-columns:repeat(4,1fr);gap:14px;flex:1;overflow:hidden"></div>`;

  try {
    const data = await AgenticAPI.get('/api/kanban');
    const COLS = [
      {id:'todo',    label:'📋 To Do',   color:'#5b8af8'},
      {id:'doing',   label:'⚡ Doing',   color:'#f0c060'},
      {id:'blocked', label:'⛔ Blocked', color:'#f06080'},
      {id:'done',    label:'✅ Done',    color:'#4cc98a'},
    ];
    document.getElementById('kb-board').innerHTML = COLS.map(col => `
      <div class="kb-col" data-col="${col.id}" ondragover="event.preventDefault()" ondrop="kbDrop(event,'${col.id}')">
        <div style="display:flex;align-items:center;justify-content:space-between;padding:10px 12px;border-bottom:1px solid var(--border);font-weight:700;font-size:13px">
          <span>${col.label}</span>
          <span style="font-size:11px;background:var(--bg-3);padding:1px 7px;border-radius:99px;color:var(--text-2)">${(data[col.id]||[]).length}</span>
        </div>
        <div class="kb-drop" id="kbcol-${col.id}" style="padding:10px;min-height:200px;overflow-y:auto;max-height:calc(100vh - 300px)">
          ${(data[col.id]||[]).map(t => kbCard(t)).join('')}
        </div>
      </div>`).join('');
  } catch(e) {
    document.getElementById('kb-board').innerHTML = `<div style="color:var(--text-2);padding:20px">Failed to load Kanban</div>`;
  }
}

function kbCard(t) {
  const priColor = {high:'#f06080',medium:'#f0c060',low:'#7a8aaa'}[t.priority]||'#7a8aaa';
  return `<div class="kb-card" draggable="true" data-id="${t.id}"
    ondragstart="kbDragStart(event,${t.id})" style="margin-bottom:10px;cursor:grab">
    <div style="display:flex;align-items:center;gap:6px;margin-bottom:6px;font-size:11px;color:var(--text-2)">
      <span style="width:7px;height:7px;border-radius:50%;background:${priColor};flex-shrink:0"></span>
      <span style="background:var(--bg-3);padding:1px 7px;border-radius:99px;font-size:10.5px">${t.agent||'—'}</span>
      <span style="margin-left:auto;color:var(--text-3);font-size:10px">${t.layer||''}</span>
    </div>
    <div style="font-weight:600;font-size:13px;margin-bottom:6px">${escHtml(t.title)}</div>
    ${t.description ? `<div style="font-size:11.5px;color:var(--text-2);margin-bottom:6px;max-height:36px;overflow:hidden">${escHtml(t.description)}</div>` : ''}
    <div style="display:flex;gap:6px;opacity:0.7">
      <button onclick="deleteTask(${JSON.stringify(t.id)})" style="font-size:10px;background:none;border:none;color:var(--red);cursor:pointer">🗑</button>
    </div>
  </div>`;
}

let kbDragging = null;
function kbDragStart(e, id) { kbDragging = id; e.dataTransfer.effectAllowed = 'move'; }
async function kbDrop(e, status) {
  e.preventDefault();
  if (!kbDragging) return;
  await fetch(`/api/tasks/${encodeURIComponent(kbDragging)}`, {
    method:'PATCH', headers:{'Content-Type':'application/json'},
    body: JSON.stringify({status})
  });
  kbDragging = null;
  renderKanban();
}

async function deleteTask(id) {
  if (!(await gmDanger('Delete Task', 'This task will be permanently removed.'))) return;
  await fetch(`/api/tasks/${encodeURIComponent(id)}`, {method:'DELETE'});
  toast('🗑 Task deleted','ok',1500);
  renderKanban();
}

async function openNewTaskModal() {
  const title = await gmPrompt('New Task', 'What needs to be done?');
  if (!title) return;
  const agent = await gmPrompt('Assign to agent', 'e.g. builder, brain, researcher', 'builder') || 'builder';
  fetch('/api/tasks', {
    method:'POST', headers:{'Content-Type':'application/json'},
    body: JSON.stringify({title, agent, status:'todo', priority:'medium'})
  }).then(r=>r.ok?r.json():null).then(j => {
    if (j?.ok) { toast('✅ Task created','ok'); renderKanban(); }
  }).catch(()=>{});
}

