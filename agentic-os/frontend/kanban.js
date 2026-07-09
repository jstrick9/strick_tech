/* Kanban Live DB — drag-drop — v5.1
   Agentic OS — Free Boardroom Clone
   Consumes:
     GET  /api/kanban
     POST /api/tasks
     PATCH /api/tasks/{id}
     POST /api/kanban/move
     POST /api/tasks/bulk_update
     DELETE /api/tasks/{id}
*/
(function(){
  console.log('[Kanban] loading Kanban v5.1 — live DB');
  const COLS = [
    {id:'todo', label:'📋 To Do', color:'#7aa2f7', wip:null},
    {id:'doing', label:'⚡ Doing', color:'#e0af68', wip:3},
    {id:'blocked', label:'⛔ Blocked', color:'#f7768e', wip:null},
    {id:'done', label:'✅ Done', color:'#9ece6a', wip:null},
  ];
  const AGENTS = ['hermes','builder','claude','openclaw','gemini','grok','galaxy','swarm','artemis','apollo','hephaestus','jarvis','expo','self','local'];
  const PRIORITIES = ['high','medium','low'];
  const LAYERS = ['Vision','Goals','Research','Tasks','Execution','Review','Ship','Memory'];

  let state = {
    board: {todo:[],doing:[],blocked:[],done:[]},
    filterAgent:'all',
    filterPriority:'all',
    filterLayer:'all',
    q:'',
    dragging:null,
    sort:'smart',
    autoRefresh:true,
    lastFetch:0
  };

  // ---- styles ----
  function injectCSS(){
    if(document.getElementById('kanban-css-v5')) return;
    const s=document.createElement('style');
    s.id='kanban-css-v5';
    s.textContent=`
# pane-kanban, #pane-kanban { background:#070a12 }
#kanbanBoard{font-family:Inter,system-ui,sans-serif;color:#dbe6ff;height:100%}
.kb-wrap{display:flex;flex-direction:column;height:calc(100vh - 142px);min-height:560px}
.kb-toolbar{display:flex;align-items:center;gap:10px;padding:12px 14px;background:#0e1322;border:1px solid #1d2745;border-radius:14px;margin-bottom:14px;flex-wrap:wrap}
.kb-toolbar input,.kb-toolbar select{background:#0b1020;color:#dbe6ff;border:1px solid #263250;border-radius:9px;padding:7px 10px;font-size:12.5px;outline:none}
.kb-toolbar input:focus,.kb-toolbar select:focus{border-color:#7aa2f7;box-shadow:0 0 0 2px rgba(122,162,247,.15)}
.kb-btn{background:#7aa2f7;color:#081028;border:none;padding:8px 14px;border-radius:9px;font-weight:700;cursor:pointer;font-size:12.5px}
.kb-btn:hover{filter:brightness(1.08)}
.kb-btn-ghost{background:#141b30;color:#b8c5e8;border:1px solid #263250;padding:7px 12px;border-radius:9px;cursor:pointer;font-size:12.5px}
.kb-btn-ghost:hover{background:#1a2340}
.kb-btn-sm{padding:5px 9px;font-size:11.5px;border-radius:7px}
.kb-pill{font-size:10.5px;padding:2px 8px;border-radius:999px;background:#151d34;border:1px solid #223055;color:#9fb4ea}
.kb-board{display:grid;grid-template-columns:repeat(4,1fr);gap:14px;flex:1;min-height:420px;align-items:start}
@media(max-width:1180px){.kb-board{grid-template-columns:repeat(2,1fr)}}
@media(max-width:680px){.kb-board{grid-template-columns:1fr}}
.kb-col{background:#0f1326;border:1px solid #1e2745;border-radius:16px;display:flex;flex-direction:column;min-height:420px;overflow:hidden;transition:border-color .18s}
.kb-col.drag-over{border-color:#7aa2f7;box-shadow:0 0 0 2px rgba(122,162,247,.18) inset}
.kb-col-head{display:flex;align-items:center;justify-content:space-between;padding:12px 13px;border-bottom:1px solid #1c2545;font-weight:700;font-size:13px;position:sticky;top:0;background:rgba(15,19,38,.98);backdrop-filter:blur(6px);z-index:2}
.kb-count{background:#151d3a;color:#9fb4ea;font-size:11px;padding:2px 8px;border-radius:999px;border:1px solid #243055;font-weight:600}
.kb-wip{font-size:10px;color:#9a8b6b;margin-left:6px}
.kb-wip.over{color:#ff8a8a}
.kb-drop{flex:1;padding:10px 10px 18px;overflow-y:auto;min-height:320px;max-height:calc(100vh - 300px)}
.kb-drop:empty::after{content:'Drop here';display:block;text-align:center;color:#3a4768;font-size:11.5px;padding:28px 0;border:1px dashed #223055;border-radius:12px;background:#0b1022}
.kb-card{background:linear-gradient(180deg,#141b34,#111831);border:1px solid #232f52;border-radius:13px;padding:11px 12px;margin-bottom:10px;cursor:grab;transition:transform .1s, box-shadow .12s, border-color .15s;position:relative}
.kb-card:hover{transform:translateY(-1px);box-shadow:0 8px 28px rgba(0,0,0,.33);border-color:#2f3d6a}
.kb-card.dragging{opacity:.55;transform:rotate(1.5deg) scale(.98)}
.kb-card-top{display:flex;align-items:center;gap:7px;font-size:11px;margin-bottom:6px;color:#8ea0c8}
.kb-pri{width:8px;height:8px;border-radius:50%;flex-shrink:0}
.kb-pri.high{background:#ff6b7a;box-shadow:0 0 6px rgba(255,107,122,.35)}
.kb-pri.medium{background:#e0af68}
.kb-pri.low{background:#7a8aaa}
.kb-agent{font-size:10.5px;background:#121a33;border:1px solid #25315a;color:#9ab4f0;padding:1px 7px;border-radius:999px;font-weight:600}
.kb-layer{font-size:10px;color:#6b7ca5;margin-left:auto}
.kb-title{font-weight:600;font-size:13px;color:#e8efff;line-height:1.35;margin-bottom:6px;word-break:break-word}
.kb-desc{font-size:11.5px;color:#9aa7c7;line-height:1.45;max-height:42px;overflow:hidden;display:-webkit-box;-webkit-line-clamp:2;-webkit-box-orient:vertical;margin-bottom:6px}
.kb-meta{display:flex;align-items:center;gap:8px;font-size:10.5px;color:#6b7ca5;flex-wrap:wrap}
.kb-id{font-family:ui-monospace,monospace;background:#0c1228;border:1px solid #1d2748;padding:1px 5px;border-radius:5px}
.kb-card-actions{display:flex;gap:5px;margin-top:8px;opacity:0;transition:opacity .15s}
.kb-card:hover .kb-card-actions{opacity:1}
.kb-card-actions button{background:#151d3a;color:#a9b9e3;border:1px solid #26335a;padding:3px 8px;border-radius:7px;font-size:10.5px;cursor:pointer}
.kb-card-actions button:hover{background:#1c2748;color:#fff}
.kb-card-actions button.danger{color:#ff8a9a;border-color:#4a2330}
.kb-empty{color:#4a5578;text-align:center;padding:22px 10px;font-size:12px}
.kb-footer{margin-top:10px;display:flex;justify-content:space-between;align-items:center;font-size:11px;color:#6b7ca5;padding:0 2px}
/* modal */
.kb-modal-back{position:fixed;inset:0;background:rgba(3,5,12,.78);z-index:9990;display:flex;align-items:center;justify-content:center;backdrop-filter:blur(4px)}
.kb-modal{background:#111734;border:1px solid #27335a;border-radius:16px;padding:18px;width:100%;max-width:560px;box-shadow:0 24px 80px rgba(0,0,0,.55);color:#dbe6ff}
.kb-modal h3{margin:0 0 12px;font-size:16px}
.kb-modal label{font-size:11.5px;color:#9aa7c7;display:block;margin:10px 0 4px}
.kb-modal input,.kb-modal textarea,.kb-modal select{width:100%;background:#0b1022;color:#e6efff;border:1px solid #2a355a;border-radius:9px;padding:9px 10px;font-size:13px;outline:none;box-sizing:border-box;font-family:inherit}
.kb-modal textarea{min-height:76px;resize:vertical}
.kb-modal input:focus,.kb-modal textarea:focus,.kb-modal select:focus{border-color:#7aa2f7;box-shadow:0 0 0 2px rgba(122,162,247,.15)}
.kb-modal-row{display:grid;grid-template-columns:1fr 1fr 1fr;gap:10px}
@media(max-width:560px){.kb-modal-row{grid-template-columns:1fr}}
.kb-modal-foot{display:flex;justify-content:flex-end;gap:8px;margin-top:14px}
/* toast */
#kb-toast{position:fixed;right:18px;bottom:18px;z-index:99999;display:flex;flex-direction:column;gap:8px;pointer-events:none}
.kb-toast{background:#0f1a2f;border:1px solid #2a3a60;color:#dbe6ff;padding:9px 13px;border-radius:11px;font-size:12.5px;box-shadow:0 12px 40px rgba(0,0,0,.45);opacity:0;transform:translateY(8px);transition:all .22s}
.kb-toast.show{opacity:1;transform:translateY(0)}
.kb-toast.ok{border-color:#2d5a3a;color:#b8f0c8}
.kb-toast.err{border-color:#5a2a3a;color:#ffc0c8}
`;
    document.head.appendChild(s);
  }

  function toast(msg, type='ok'){
    let c=document.getElementById('kb-toast');
    if(!c){ c=document.createElement('div'); c.id='kb-toast'; document.body.appendChild(c); }
    const t=document.createElement('div');
    t.className='kb-toast '+type;
    t.textContent=msg;
    c.appendChild(t);
    requestAnimationFrame(()=>t.classList.add('show'));
    setTimeout(()=>{ t.classList.remove('show'); setTimeout(()=>t.remove(),220)}, 2600);
  }

  function escapeHtml(s){
    return (s||'').replace(/[&<>\"']/g, m=>({'&':'&amp;','<':'&lt;','>':'&gt;','"':'&quot;',"'":'&#39;'}[m]));
  }

  // ---- API ----
  async function apiGetKanban(){
    const r = await fetch('/api/kanban?board=default&t='+Date.now());
    if(!r.ok) throw new Error('kanban '+r.status);
    return r.json();
  }
  async function apiMove(id, to_status, sort_order){
    const r = await fetch('/api/kanban/move', {
      method:'POST',
      headers:{'Content-Type':'application/json'},
      body: JSON.stringify({id, to_status, sort_order})
    });
    return r.json();
  }
  async function apiPatchTask(id, patch){
    const r = await fetch('/api/tasks/'+id, {
      method:'PATCH',
      headers:{'Content-Type':'application/json'},
      body: JSON.stringify(patch)
    });
    return r.json();
  }
  async function apiBulk(updates){
    const r = await fetch('/api/tasks/bulk_update', {
      method:'POST',
      headers:{'Content-Type':'application/json'},
      body: JSON.stringify({updates})
    });
    return r.json();
  }
  async function apiCreateTask(payload){
    const r = await fetch('/api/tasks', {
      method:'POST',
      headers:{'Content-Type':'application/json'},
      body: JSON.stringify(payload)
    });
    return r.json();
  }
  async function apiDeleteTask(id){
    const r = await fetch('/api/tasks/'+id, {method:'DELETE'});
    return r.json();
  }

  // ---- render ----
  function renderBoard(){
    const el = document.getElementById('kanbanBoard');
    if(!el) return;
    el.innerHTML = `
<div class="kb-wrap">
  <div class="kb-toolbar">
    <div style="font-weight:800;font-size:14.5px">📋 Kanban — Live DB</div>
    <span class="kb-pill" id="kb-total">— tasks</span>
    <span style="flex:1"></span>
    <input id="kb-q" placeholder="🔍 search tasks…" style="min-width:190px" value="${escapeHtml(state.q)}">
    <select id="kb-f-agent" title="Agent">
      <option value="all">all agents</option>
      ${AGENTS.map(a=>`<option value="${a}" ${state.filterAgent===a?'selected':''}>${a}</option>`).join('')}
    </select>
    <select id="kb-f-pri" title="Priority">
      <option value="all">all priority</option>
      ${PRIORITIES.map(p=>`<option value="${p}" ${state.filterPriority===p?'selected':''}>${p}</option>`).join('')}
    </select>
    <select id="kb-f-layer" title="Layer">
      <option value="all">all layers</option>
      ${LAYERS.map(l=>`<option value="${l}" ${state.filterLayer===l?'selected':''}>${l}</option>`).join('')}
    </select>
    <button class="kb-btn-ghost kb-btn-sm" id="kb-refresh">⟳ Refresh</button>
    <button class="kb-btn" id="kb-new">+ New Task</button>
  </div>
  <div class="kb-board" id="kb-board-cols">
    ${COLS.map(c=>`
      <div class="kb-col" data-status="${c.id}">
        <div class="kb-col-head" style="color:${c.color}">
          <span>${c.label}</span>
          <span>
            ${c.wip ? `<span class="kb-wip" id="kb-wip-${c.id}">WIP ${c.wip}</span>`:''}
            <span class="kb-count" id="kb-count-${c.id}">0</span>
          </span>
        </div>
        <div class="kb-drop" data-status="${c.id}" id="kb-drop-${c.id}">
          <div class="kb-empty">loading…</div>
        </div>
      </div>
    `).join('')}
  </div>
  <div class="kb-footer">
    <span>Drag → drop to move • Double-click card to edit • Right-click = quick move • Auto-refresh <b id="kb-autoref">${state.autoRefresh?'ON':'OFF'}</b></span>
    <span>API: <code>/api/kanban</code> • <code>/api/tasks</code> • Hermes autonomous loop picks up ‘doing’</span>
  </div>
</div>
<div id="kb-modal-root"></div>
`;
    bindToolbar();
    renderColumns();
  }

  function bindToolbar(){
    const q=document.getElementById('kb-q');
    if(q && !q._bound){ q._bound=true; let t; q.addEventListener('input', ()=>{ clearTimeout(t); t=setTimeout(()=>{ state.q=q.value.trim().toLowerCase(); renderColumns(); }, 180); }); }
    const fa=document.getElementById('kb-f-agent');
    if(fa) fa.onchange=()=>{ state.filterAgent=fa.value; renderColumns(); };
    const fp=document.getElementById('kb-f-pri');
    if(fp) fp.onchange=()=>{ state.filterPriority=fp.value; renderColumns(); };
    const fl=document.getElementById('kb-f-layer');
    if(fl) fl.onchange=()=>{ state.filterLayer=fl.value; renderColumns(); };
    document.getElementById('kb-refresh')?.addEventListener('click', ()=>loadKanban(true));
    document.getElementById('kb-new')?.addEventListener('click', ()=>openTaskModal());
    const ar=document.getElementById('kb-autoref');
    if(ar){ ar.style.cursor='pointer'; ar.onclick=()=>{ state.autoRefresh=!state.autoRefresh; ar.textContent=state.autoRefresh?'ON':'OFF'; toast('Auto-refresh '+(state.autoRefresh?'on':'off')); } }
  }

  function filterTask(t){
    if(state.filterAgent!=='all' && t.agent!==state.filterAgent) return false;
    if(state.filterPriority!=='all' && t.priority!==state.filterPriority) return false;
    if(state.filterLayer!=='all' && (t.layer||'Tasks')!==state.filterLayer) return false;
    if(state.q){
      const hay = (t.title+' '+(t.description||'')+' '+t.agent+' '+(t.layer||'')).toLowerCase();
      if(!hay.includes(state.q)) return false;
    }
    return true;
  }

  function renderColumns(){
    let total=0;
    COLS.forEach(col=>{
      const list = (state.board[col.id]||[]).filter(filterTask);
      total += list.length;
      const drop = document.getElementById('kb-drop-'+col.id);
      const countEl = document.getElementById('kb-count-'+col.id);
      if(countEl) countEl.textContent = list.length;
      const wipEl = document.getElementById('kb-wip-'+col.id);
      if(wipEl && col.wip){
        const over = list.length > col.wip;
        wipEl.classList.toggle('over', over);
        wipEl.textContent = `WIP ${list.length}/${col.wip}`;
      }
      if(!drop) return;
      if(!list.length){
        drop.innerHTML = `<div class="kb-empty">empty — drag here</div>`;
      } else {
        drop.innerHTML = list.map((t,i)=>cardHTML(t,i)).join('');
      }
      // drag events
      drop.ondragover = (e)=>{ e.preventDefault(); drop.parentElement.classList.add('drag-over'); e.dataTransfer.dropEffect='move'; };
      drop.ondragleave = ()=> drop.parentElement.classList.remove('drag-over');
      drop.ondrop = (e)=>{ e.preventDefault(); drop.parentElement.classList.remove('drag-over'); handleDrop(col.id, e); };
    });
    const totalEl=document.getElementById('kb-total');
    if(totalEl) totalEl.textContent = total+' tasks';
    bindCards();
  }

  function cardHTML(t, idx){
    const pri = t.priority||'medium';
    const agent = escapeHtml(t.agent||'hermes');
    const layer = escapeHtml(t.layer||'Tasks');
    const title = escapeHtml(t.title||'Untitled');
    const desc = escapeHtml((t.description||'').slice(0,160));
    const updated = t.updated_at ? new Date((t.updated_at+'').replace(' ','T')).toLocaleString([], {month:'short', day:'numeric', hour:'2-digit', minute:'2-digit'}) : '';
    return `<div class="kb-card" draggable="true" data-id="${t.id}" data-status="${t.status}" data-idx="${idx}">
      <div class="kb-card-top">
        <span class="kb-pri ${pri}" title="${pri}"></span>
        <span class="kb-agent">${agent}</span>
        <span class="kb-layer">${layer}</span>
      </div>
      <div class="kb-title">${title}</div>
      ${desc ? `<div class="kb-desc">${desc}</div>` : ''}
      <div class="kb-meta">
        <span class="kb-id">#${t.id}</span>
        ${updated ? `<span>• ${updated}</span>`:''}
        ${t.run_id ? `<span style="color:#7aa2f7">run ${String(t.run_id).slice(0,8)}</span>`:''}
      </div>
      <div class="kb-card-actions">
        <button data-act="start" data-id="${t.id}" title="Move to Doing">▶ start</button>
        <button data-act="done" data-id="${t.id}" title="Mark Done">✓ done</button>
        <button data-act="edit" data-id="${t.id}">edit</button>
        <button data-act="delete" data-id="${t.id}" class="danger">×</button>
      </div>
    </div>`;
  }

  function bindCards(){
    document.querySelectorAll('.kb-card').forEach(card=>{
      card.ondragstart = (e)=>{
        state.dragging = {
          id: parseInt(card.dataset.id),
          from: card.dataset.status,
        };
        card.classList.add('dragging');
        e.dataTransfer.effectAllowed='move';
        e.dataTransfer.setData('text/plain', card.dataset.id);
      };
      card.ondragend = ()=>{ card.classList.remove('dragging'); state.dragging=null; document.querySelectorAll('.kb-col').forEach(c=>c.classList.remove('drag-over')); };
      card.ondblclick = ()=> openTaskModal(parseInt(card.dataset.id));
      card.oncontextmenu = (e)=>{ e.preventDefault(); quickMoveMenu(parseInt(card.dataset.id), e.clientX, e.clientY); };
      // buttons
      card.querySelectorAll('button[data-act]').forEach(btn=>{
        btn.onclick = (ev)=>{ ev.stopPropagation(); handleCardAction(btn.dataset.act, parseInt(btn.dataset.id)); };
      });
    });
  }

  async function handleCardAction(act, id){
    if(act==='start'){
      await moveTask(id, 'doing');
    } else if(act==='done'){
      await moveTask(id, 'done');
    } else if(act==='edit'){
      openTaskModal(id);
    } else if(act==='delete'){
      if(!confirm('Delete task #'+id+' ?')) return;
      const j = await apiDeleteTask(id);
      if(j.ok){ toast('Task deleted'); loadKanban(true); } else { toast('Delete failed: '+(j.error||''), 'err'); }
    }
  }

  async function handleDrop(to_status, e){
    const drag = state.dragging;
    if(!drag || !drag.id) return;
    // compute sort_order = append at end (max+1)
    const colTasks = (state.board[to_status]||[]);
    const sort_order = (colTasks.reduce((m,t)=>Math.max(m, t.sort_order||t.id||0),0) + 10);
    await moveTask(drag.id, to_status, sort_order);
  }

  async function moveTask(id, to_status, sort_order){
    // optimistic UI
    let moved=false;
    let fromCol=null, taskObj=null;
    for(const col of COLS){
      const arr = state.board[col.id]||[];
      const idx = arr.findIndex(t=>t.id===id);
      if(idx>=0){ taskObj = arr.splice(idx,1)[0]; fromCol=col.id; break; }
    }
    if(taskObj){
      taskObj.status = to_status;
      if(!state.board[to_status]) state.board[to_status]=[];
      state.board[to_status].unshift(taskObj);
      renderColumns();
      moved=true;
    }
    try{
      const j = await apiMove(id, to_status, sort_order);
      if(j.ok){
        toast(`${to_status==='done'?'✓ Done':to_status==='doing'?'▶ Doing':'→ '+to_status}  #${id}`);
        // refresh in background to get server sort
        setTimeout(()=>loadKanban(false), 500);
      } else {
        throw new Error(j.error||'move failed');
      }
    }catch(err){
      toast('Move failed: '+err, 'err');
      // rollback by refetch
      loadKanban(true);
    }
  }

  function quickMoveMenu(id, x, y){
    // remove old
    document.getElementById('kb-quickmenu')?.remove();
    const m=document.createElement('div');
    m.id='kb-quickmenu';
    m.style.cssText=`position:fixed;left:${x}px;top:${y}px;background:#0f1530;border:1px solid #2a3a60;border-radius:10px;padding:6px;z-index:9999;box-shadow:0 14px 40px rgba(0,0,0,.45);font-size:12.5px;min-width:150px`;
    m.innerHTML = COLS.map(c=>`<div data-go="${c.id}" style="padding:7px 10px;border-radius:7px;cursor:pointer;color:${c.color}">→ ${c.label.replace(/^[^\s]+\s/,'')}</div>`).join('')+
      `<div style="border-top:1px solid #1d2745;margin:4px 0"></div>
       <div data-go="edit" style="padding:7px 10px;border-radius:7px;cursor:pointer;color:#b8c5e8">✏️ edit…</div>
       <div data-go="delete" style="padding:7px 10px;border-radius:7px;cursor:pointer;color:#ff8a9a">🗑 delete</div>`;
    document.body.appendChild(m);
    const close=()=>m.remove();
    setTimeout(()=>document.addEventListener('click', close, {once:true}), 20);
    m.querySelectorAll('[data-go]').forEach(d=>{
      d.onmouseenter=()=>d.style.background='#1a2346';
      d.onmouseleave=()=>d.style.background='transparent';
      d.onclick=async()=>{
        close();
        const go=d.dataset.go;
        if(go==='edit'){ openTaskModal(id); return; }
        if(go==='delete'){ handleCardAction('delete', id); return; }
        moveTask(id, go);
      };
    });
  }

  // ---- modal create / edit ----
  function openTaskModal(editId){
    const isEdit = !!editId;
    let task = null;
    if(isEdit){
      // find task
      COLS.forEach(c=>{ const f=(state.board[c.id]||[]).find(t=>t.id===editId); if(f) task=f; });
    }
    const root=document.getElementById('kb-modal-root');
    if(!root) return;
    root.innerHTML = `<div class="kb-modal-back" id="kb-modal-back">
      <div class="kb-modal" onclick="event.stopPropagation()">
        <h3>${isEdit ? '✏️ Edit Task #'+editId : '➕ New Task'}</h3>
        <label>Title</label>
        <input id="km-title" value="${task?escapeHtml(task.title):''}" placeholder="Build Stripe checkout — Next.js + Tailwind">
        <label>Description</label>
        <textarea id="km-desc" placeholder="Acceptance criteria, links, notes…">${task?escapeHtml(task.description||''):''}</textarea>
        <div class="kb-modal-row">
          <div>
            <label>Status</label>
            <select id="km-status">
              ${COLS.map(c=>`<option value="${c.id}" ${(task?.status||'todo')===c.id?'selected':''}>${c.label.replace(/^[^\s]+\s/,'')}</option>`).join('')}
            </select>
          </div>
          <div>
            <label>Priority</label>
            <select id="km-priority">
              ${PRIORITIES.map(p=>`<option value="${p}" ${(task?.priority||'medium')===p?'selected':''}>${p}</option>`).join('')}
            </select>
          </div>
          <div>
            <label>Agent</label>
            <select id="km-agent">
              ${AGENTS.map(a=>`<option value="${a}" ${(task?.agent||'hermes')===a?'selected':''}>${a}</option>`).join('')}
            </select>
          </div>
        </div>
        <div class="kb-modal-row">
          <div>
            <label>Layer</label>
            <select id="km-layer">
              ${LAYERS.map(l=>`<option value="${l}" ${(task?.layer||'Tasks')===l?'selected':''}>${l}</option>`).join('')}
            </select>
          </div>
          <div>
            <label>Sort order</label>
            <input id="km-sort" type="number" value="${task?.sort_order||0}">
          </div>
          <div>
            <label>Run ID <span style="color:#6b7ca5">(optional)</span></label>
            <input id="km-run" value="${task?.run_id||''}" placeholder="swarm_… / pipe_…">
          </div>
        </div>
        <div class="kb-modal-foot">
          ${isEdit ? `<button class="kb-btn-ghost kb-btn-sm" id="km-delete" style="margin-right:auto;color:#ff8a9a;border-color:#4a2a3a">🗑 Delete</button>` : `<span style="flex:1"></span>`}
          <button class="kb-btn-ghost" id="km-cancel">Cancel</button>
          <button class="kb-btn" id="km-save">${isEdit ? 'Save' : 'Create task'}</button>
        </div>
        ${isEdit ? `<div style="font-size:11px;color:#6b7ca5;margin-top:10px">Created: ${task?.created_at||'—'} • Updated: ${task?.updated_at||'—'}</div>`:''}
      </div>
    </div>`;
    document.getElementById('kb-modal-back').onclick = (e)=>{ if(e.target.id==='kb-modal-back') closeModal(); };
    document.getElementById('km-cancel').onclick = closeModal;
    document.getElementById('km-save').onclick = async ()=>{
      const payload = {
        title: document.getElementById('km-title').value.trim(),
        description: document.getElementById('km-desc').value.trim(),
        status: document.getElementById('km-status').value,
        priority: document.getElementById('km-priority').value,
        agent: document.getElementById('km-agent').value,
        layer: document.getElementById('km-layer').value,
        sort_order: parseInt(document.getElementById('km-sort').value)||0,
        run_id: document.getElementById('km-run').value.trim()||null,
      };
      if(!payload.title){ toast('Title required', 'err'); return; }
      try{
        let j;
        if(isEdit){
          j = await apiPatchTask(editId, payload);
          if(j.ok){ toast('✓ Task #'+editId+' saved'); closeModal(); loadKanban(true); }
          else throw new Error(j.error||'save failed');
        } else {
          j = await apiCreateTask(payload);
          if(j.ok){ toast('✓ Task #'+j.id+' created → '+payload.status); closeModal(); loadKanban(true); }
          else throw new Error(j.error||'create failed');
        }
      }catch(err){ toast(String(err), 'err'); }
    };
    const delBtn=document.getElementById('km-delete');
    if(delBtn){ delBtn.onclick=async()=>{ if(!confirm('Delete task #'+editId+' ?')) return; const j=await apiDeleteTask(editId); if(j.ok){ toast('Task deleted'); closeModal(); loadKanban(true);} else {toast('Delete failed','err')} }; }
    // esc close
    const esc = (e)=>{ if(e.key==='Escape'){ closeModal(); document.removeEventListener('keydown', esc);} };
    document.addEventListener('keydown', esc);
    // focus
    setTimeout(()=>document.getElementById('km-title')?.focus(), 60);

    function closeModal(){ const r=document.getElementById('kb-modal-root'); if(r) r.innerHTML=''; document.removeEventListener('keydown', esc); }
    window.__kbCloseModal = closeModal;
  }

  // ---- load ----
  async function loadKanban(force=false){
    const now=Date.now();
    if(!force && now - state.lastFetch < 2500) return; // debounce
    state.lastFetch = now;
    try{
      const data = await apiGetKanban();
      // data is {todo:[],doing:[],blocked:[],done:[]}
      state.board = data;
      // if board div not yet rendered, render full
      if(!document.getElementById('kb-board-cols')){
        renderBoard();
      } else {
        renderColumns();
      }
    }catch(e){
      console.warn('[Kanban] fetch failed', e);
      const el=document.getElementById('kanbanBoard');
      if(el && !el.querySelector('.kb-wrap')){
        el.innerHTML = `<div style="padding:24px;color:#ff8a8a">Kanban API error: ${escapeHtml(String(e))}<br><button onclick="window.loadKanban && window.loadKanban(true)" style="margin-top:10px" class="kb-btn-ghost">Retry</button></div>`;
      } else {
        toast('Kanban refresh failed', 'err');
      }
    }
  }

  // expose
  window.loadKanban = loadKanban;
  window.Kanban = {
    reload: ()=>loadKanban(true),
    create: openTaskModal,
    move: moveTask
  };

  // ---- init ----
  function init(){
    injectCSS();
    const el = document.getElementById('kanbanBoard');
    if(!el){ 
      // wait for DOM
      setTimeout(init, 400);
      return;
    }
    if(!el.querySelector('.kb-wrap')){
      renderBoard();
    }
    loadKanban(true);
    // auto refresh
    if(window.__kbTimer) clearInterval(window.__kbTimer);
    window.__kbTimer = setInterval(()=>{ if(state.autoRefresh && document.getElementById('pane-kanban')?.style.display!=='none'){ loadKanban(false); } }, 15000);
    // when tab clicked, refresh
    document.addEventListener('click', (e)=>{
      const tab = e.target.closest('.tab[data-tab="kanban"]');
      if(tab){ setTimeout(()=>loadKanban(false), 120); }
    }, true);
    console.log('[Kanban] ready — drag-drop • live DB • /api/kanban');
  }

  if(document.readyState==='loading'){
    document.addEventListener('DOMContentLoaded', init);
  } else {
    setTimeout(init, 300);
  }

  // also expose a tiny helper to create task from chat slash command
  document.addEventListener('keydown', async (e)=>{
    const inp = e.target;
    if(inp && inp.id==='chatInput' && e.key==='Enter' && !e.shiftKey){
      const v = inp.value.trim();
      const m = v.match(/^\/(kanban|task|todo)\s+(.+)/i);
      if(m){
        e.preventDefault(); e.stopPropagation();
        const title = m[2];
        inp.value='';
        // create quick task
        try{
          const r = await fetch('/api/tasks',{method:'POST',headers:{'Content-Type':'application/json'},body:JSON.stringify({title, status:'todo', priority:'medium', agent:'hermes', layer:'Tasks'})});
          const j = await r.json();
          if(j.ok){
            if(typeof addChat==='function') addChat(`📋 Kanban — task created\n\n**#${j.id} ${title}**\n→ status: todo • agent: hermes\n\nOpen Kanban tab to drag → Doing → Done`, 'agent');
            toast('Task #'+j.id+' created');
            loadKanban(true);
          }
        }catch(err){}
        return false;
      }
    }
  }, true);


})();
