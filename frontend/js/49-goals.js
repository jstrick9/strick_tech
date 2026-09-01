// Goals — Extracted from 06-sprint-features.js
(function(S, nav, toast, escHtml, fetch, document, gmPrompt, gmConfirm, gmAlert) {
// NOTE: this state/constants block was originally (incorrectly) left in
// the separate 48-supervisor.js IIFE, which has its own private closure
// scope and cannot be seen from here. Moved here since it belongs to this
// module.
// ══════════════════════════════════════════════════════════════════
//  GOAL DECOMPOSITION & OUTCOME SCORING — Complete Implementation
// ══════════════════════════════════════════════════════════════════

// ── State ─────────────────────────────────────────────────────────
let _goalFilter   = { status: '', domain: '', priority: '' };
let _goalList     = [];           // cached goal array
// Set when the last goal load failed, so the list can say so instead of
// rendering an empty state that looks like "you have no goals".
let _goalLoadError = null;
let _goalTotal    = 0;            // true server-side count (may exceed the page)
// How many goals to request. Grows via "Load more".
//
// The list previously capped at 100 and told the user to "narrow the filters"
// to see the rest -- useless advice when all 250 match the current filters,
// and the only escape route offered. Measured with 250 seeded goals: 150 were
// unreachable through the UI.
let _goalLimit    = 100;
const GOAL_PAGE_SIZE = 100;
let _goalSelected = null;         // currently open goal detail {goal, milestones, checkins, decomposition, score_history}
let _goalTab      = 'overview';   // 'overview' | 'decompose' | 'score' | 'history'
let _goalPollTimer = null;

// ── Constants ──────────────────────────────────────────────────────
const GOAL_PRIORITY_COLORS = {
  critical: '#e85252', high: '#e8a237', medium: '#5b8af8', low: '#7a8aaa'
};
const GOAL_STATUS_COLORS = {
  active: '#3dba7a', paused: '#e8a237', done: '#9d74f5',
  cancelled: '#7a8aaa', blocked: '#e85252'
};
const GOAL_DOMAIN_ICONS = {
  Work:'💼', Health:'🏃', Finance:'💰', Learning:'📚',
  Home:'🏠', Travel:'✈️', Personal:'⭐', Research:'🔬'
};
const GOAL_AGENT_COLORS = {
  researcher:'#5b8af8', builder:'#3dba7a', reviewer:'#e8a237',
  creative:'#c084fc', memory:'#38c5d8', brain:'#9d74f5', orchestrator:'#f06080'
};
const GOAL_AGENT_ICONS = {
  researcher:'🔍', builder:'🔨', reviewer:'🔬', creative:'✍️',
  memory:'🧠', brain:'💡', orchestrator:'🎯'
};
const GRADE_COLORS = {
  'A+':'#3dba7a','A':'#3dba7a','A-':'#5b8af8',
  'B+':'#5b8af8','B':'#5b8af8','B-':'#e8a237',
  'C+':'#e8a237','C':'#e8a237','C-':'#e85252',
  'D':'#e85252','F':'#e85252'
};

async function renderGoals() {
  const pane = document.getElementById('pane-goals');
  if (!pane) return;

  // Show a pending state before awaiting anything. Measured on a 3s
  // connection: this pane stayed blank for the whole request with no
  // indication it was working, which is exactly when a user clicks the
  // action again and creates a duplicate.
  if (!pane.innerText.trim() && typeof skeletonPage === 'function') {
    pane.innerHTML = skeletonPage();
    pane.setAttribute('aria-busy', 'true');
  }

  // Content has arrived; clear the pending state set above. Leaving
  // aria-busy set would be its own bug -- a screen reader would keep saying
  // the region is updating forever.
  pane.removeAttribute('aria-busy');

  pane.innerHTML = `
  

  <div class="gm-root">
    <!-- ── Sidebar ── -->
    <div class="gm-sidebar">
      <div class="gm-sidebar-head">
        <p class="gm-sidebar-title">🎯 Goals</p>
        <div class="gm-stats-row" id="gm-stats-row">
          <div class="gm-stat"><div class="gm-stat-val" id="gm-stat-total" style="color:var(--accent-text)">—</div><div class="gm-stat-label">Total</div></div>
          <div class="gm-stat"><div class="gm-stat-val" id="gm-stat-active" style="color:var(--success)">—</div><div class="gm-stat-label">Active</div></div>
          <div class="gm-stat"><div class="gm-stat-val" id="gm-stat-avg" style="color:#9d74f5">—</div><div class="gm-stat-label">Avg%</div></div>
        </div>
        <div class="gm-filters">
          <div class="gm-filter-row">
            <select class="gm-filter-select" id="gm-filter-status" data-act-change="gmFilterChange()">
              <option value="">All statuses</option>
              <option value="active">Active</option>
              <option value="paused">Paused</option>
              <option value="done">Done</option>
              <option value="blocked">Blocked</option>
            </select>
            <select class="gm-filter-select" id="gm-filter-priority" data-act-change="gmFilterChange()">
              <option value="">All priorities</option>
              <option value="critical">Critical</option>
              <option value="high">High</option>
              <option value="medium">Medium</option>
              <option value="low">Low</option>
            </select>
          </div>
          <select class="gm-filter-select" id="gm-filter-domain" data-act-change="gmFilterChange()">
            <option value="">All domains</option>
            <option value="Work">💼 Work</option>
            <option value="Health">🏃 Health</option>
            <option value="Finance">💰 Finance</option>
            <option value="Learning">📚 Learning</option>
            <option value="Home">🏠 Home</option>
            <option value="Research">🔬 Research</option>
            <option value="Personal">⭐ Personal</option>
            <option value="Travel">✈️ Travel</option>
          </select>
        </div>
      </div>
      <div class="gm-goal-list" id="gm-goal-list">
        <div style="color:var(--text-3);font-size:12px;padding:10px">Loading…</div>
      </div>
      <div class="gm-sidebar-foot">
        <button class="gm-new-btn" data-act-click="gmOpenCreate()">+ New Goal</button>
      </div>
    </div>

    <!-- ── Main ── -->
    <div class="gm-main" id="gm-main">
      <div class="gm-empty" id="gm-empty-main">
        <div class="gm-empty-icon">🎯</div>
        <div class="gm-empty-title">No Goal Selected</div>
        <div class="gm-empty-sub">Select a goal from the sidebar to view its decomposition, live outcome score, and progress history — or create your first goal.</div>
        <button class="gm-new-btn" data-act-click="gmOpenCreate()" style="width:auto;padding:8px 20px;margin-top:16px">+ Create First Goal</button>
      </div>
    </div>
  </div>`;

  await gmLoadGoals();
}


// ── Load & render goal list ────────────────────────────────────────
async function gmLoadGoals() {
  // `.catch(() => ({goals: []}))` made a dropped connection look exactly like
  // an empty goal list. Measured with a body truncated mid-JSON: the pane
  // rendered its normal empty state and said nothing was wrong, so a user
  // would reasonably conclude their goals had been deleted. The failure is
  // now recorded and surfaced below.
  _goalLoadError = null;
  const [statsR, goalsR] = await Promise.all([
    fetch('/api/goals/stats/summary').then(r=>r.ok?r.json():{}).catch(()=>({})),
    fetch(`/api/goals?limit=${_goalLimit}${_goalFilter.status?'&status='+encodeURIComponent(_goalFilter.status):''}${_goalFilter.domain?'&domain='+encodeURIComponent(_goalFilter.domain):''}${_goalFilter.priority?'&priority='+encodeURIComponent(_goalFilter.priority):''}`)
      .then(r => {
        if (!r.ok) throw httpError(r);
        return r.json();
      })
      .catch(e => { _goalLoadError = e; return {goals: []}; }),
  ]);
  _goalList = (goalsR && goalsR.goals) || [];
  // The API caps at 100 but reports the true count. 724 goals existed in
  // testing while the list showed 100 and said nothing, so 624 were simply
  // unreachable -- the user has no way to know they are not seeing
  // everything, which is worse than an explicit limit.
  _goalTotal = goalsR.total ?? _goalList.length;
  gmUpdateStats(statsR);
  gmRenderList();
}

function gmUpdateStats(stats) {
  const s = (id, v) => { const el=document.getElementById(id); if(el) el.textContent=v; };
  s('gm-stat-total',  stats.total ?? _goalList.length);
  s('gm-stat-active', (stats.by_status||{}).active ?? _goalList.filter(g=>g.status==='active').length);
  s('gm-stat-avg',    Math.round(stats.avg_progress ?? 0) + '%');
}

window.gmLoadMoreGoals = function () {
  _goalLimit += GOAL_PAGE_SIZE;
  gmLoadGoals();
};

function gmRenderList() {
  const list = document.getElementById('gm-goal-list');
  if (!list) return;
  if (_goalLoadError) {
    // Distinguish "no goals" from "we could not load your goals". Saying
    // "No goals match these filters" after a failed request is a lie the
    // user has no way to detect.
    list.innerHTML = `<div role="alert" style="color:var(--text-2);font-size:12px;padding:12px;line-height:1.7">
        ${escHtml(humanError(_goalLoadError, {action: 'load your goals', dataSafe: true}))}
        <br><button type="button" class="btn btn-sm btn-primary" style="margin-top:8px"
                    data-act-click="renderGoals()">↻ Try again</button>
      </div>`;
    return;
  }
  if (!_goalList.length) {
    list.innerHTML = `<div style="color:var(--text-3);font-size:12px;padding:12px;line-height:1.7">No goals match these filters.</div>`;
    return;
  }
  const hidden = Math.max(0, _goalTotal - _goalList.length);
  const truncationNote = hidden
    ? `<div role="status" style="padding:8px 12px;margin-bottom:8px;border-radius:6px;background:var(--bg-3);border:1px solid var(--border);font-size:11.5px;color:var(--text-2)">
         Showing ${_goalList.length} of ${_goalTotal} goals.
         <span style="color:var(--text-3)">${hidden} more not shown.</span>
         <button type="button" class="btn btn-sm btn-ghost" style="margin-left:8px"
                 data-act-click="gmLoadMoreGoals()">Load more</button>
       </div>`
    : '';

  list.innerHTML = truncationNote + _goalList.map(g => {
    const pCol   = GOAL_PRIORITY_COLORS[g.priority]  || 'var(--accent)';
    const sCol   = GOAL_STATUS_COLORS[g.status]       || 'var(--text-3)';
    const prog   = g.progress || 0;
    const progC  = prog>=80?'var(--success)':prog>=40?'var(--warning)':'var(--danger)';
    const isActive = _goalSelected?.goal?.id === g.id;
    const score  = g.outcome_score != null ? Math.round(g.outcome_score*100) : null;
    const icon   = GOAL_DOMAIN_ICONS[g.domain] || '📌';
    return `<div class="gm-goal-card ${isActive?'active':''}" style="border-left-color:${pCol}" data-goal-id="${escHtml(g.id)}">
      <div class="gm-goal-card-top">
        <span class="gm-goal-icon">${icon}</span>
        <span class="gm-goal-title">${escHtml(g.title.slice(0,55))}</span>
      </div>
      <div class="gm-goal-meta">
        <span style="color:${pCol}">${g.priority}</span> ·
        <span style="color:${sCol}">${g.status}</span>
        ${g.deadline ? ` · ⏰ ${g.deadline}` : ''}
      </div>
      <div class="gm-progress-bar-wrap">
        <div class="gm-progress-track">
          <div class="gm-progress-fill" style="width:${prog}%;background:${progC}"></div>
        </div>
        <span class="gm-progress-pct" style="color:${progC}">${prog}%</span>
      </div>
      ${score != null ? `<div><span class="gm-score-chip" style="background:${(GRADE_COLORS[gmScoreToGrade(g.outcome_score)]||'#7a8aaa')}22;color:${GRADE_COLORS[gmScoreToGrade(g.outcome_score)]||'#7a8aaa'}">⭐ ${score}% ${gmScoreToGrade(g.outcome_score)}</span></div>` : ''}
    </div>`;
  }).join('');
}

  document.getElementById('gm-goal-list')?.addEventListener('click', e => { const card = e.target.closest('.gm-goal-card'); if (!card) return; const gid = card.dataset.goalId; if (gid) gmSelectGoal(gid); });


  document.querySelector('.gm-milestone-list')?.addEventListener('click', e => { const ms = e.target.closest('[data-ms-id]'); if (!ms) return; gmCompleteMilestone(ms.dataset.msId, parseInt(ms.dataset.msDone)); });
function gmFilterChange() {
  _goalFilter.status   = document.getElementById('gm-filter-status')?.value   || '';
  _goalFilter.domain   = document.getElementById('gm-filter-domain')?.value   || '';
  _goalFilter.priority = document.getElementById('gm-filter-priority')?.value || '';
  // A new filter is a new list. Without this, narrowing the filters after
  // pressing Load more keeps requesting the enlarged page size forever.
  _goalLimit = GOAL_PAGE_SIZE;
  gmLoadGoals();
}


// ── Select goal & render detail ────────────────────────────────────
async function gmSelectGoal(goalId) {
  const d = await fetch(`/api/goals/${encodeURIComponent(goalId)}/full`)
    .then(r=>r.ok?r.json():null).catch(()=>null);
  if (!d || !d.ok) { toast('Could not load goal'); return; }
  _goalSelected = d;
  _goalTab = 'overview';
  gmRenderList();
  gmRenderDetail();
}

function gmRenderDetail() {
  const main = document.getElementById('gm-main');
  if (!main || !_goalSelected) return;
  const g   = _goalSelected.goal;
  const pCol = GOAL_PRIORITY_COLORS[g.priority] || 'var(--accent)';
  const sCol = GOAL_STATUS_COLORS[g.status]     || 'var(--text-3)';
  const prog = g.progress || 0;
  const progC = prog>=80?'var(--success)':prog>=40?'var(--warning)':'var(--danger)';
  const score  = g.outcome_score != null ? Math.round(g.outcome_score*100) : null;
  const grade  = g.outcome_score != null ? gmScoreToGrade(g.outcome_score) : null;
  const decomp = _goalSelected.decomposition || [];
  const scores = _goalSelected.score_history || [];
  const ms     = _goalSelected.milestones    || [];

  main.innerHTML = `
    <div class="gm-detail-head">
      <div class="gm-detail-title">${escHtml(g.title)}</div>
      <div class="gm-detail-meta-row">
        <span class="gm-badge" style="background:${pCol}22;color:${pCol}">${g.priority}</span>
        <span class="gm-badge" style="background:${sCol}22;color:${sCol}">${g.status}</span>
        <span class="gm-badge" style="background:var(--bg-3);color:var(--text-2)">${GOAL_DOMAIN_ICONS[g.domain]||'📌'} ${g.domain}</span>
        ${g.deadline ? `<span style="font-size:11px;color:var(--text-3)">⏰ Due ${g.deadline}</span>` : ''}
        ${score != null ? `<span class="gm-badge" style="background:${(GRADE_COLORS[grade]||'#7a8aaa')}22;color:${GRADE_COLORS[grade]||'#7a8aaa'}">⭐ Score: ${score}% ${grade}</span>` : ''}
        ${g.iteration ? `<span style="font-size:10px;color:var(--text-3)">Iteration ${g.iteration}</span>` : ''}
      </div>
      <div class="gm-detail-progress-row">
        <span style="font-size:11px;color:var(--text-3)">Progress</span>
        <div class="gm-detail-progress-track">
          <div class="gm-detail-progress-fill" style="width:${prog}%;background:${progC}"></div>
        </div>
        <span class="gm-detail-progress-pct" style="color:${progC}">${prog}%</span>
      </div>
      <div class="gm-detail-actions">
        <button class="gm-action-btn primary" data-act-click="gmDecomposeGoal()">🧩 Decompose</button>
        <button class="gm-action-btn primary" data-act-click="gmScoreGoal()" style="background:rgba(157,116,245,.2);border-color:#9d74f5;color:#9d74f5">⭐ Score Outcome</button>
        <button class="gm-action-btn" data-act-click="gmLaunchGoal()">🚀 Launch Supervisor</button>
        <button class="gm-action-btn" data-act-click="gmAddCheckin()">📈 Check-in</button>
        <button class="gm-action-btn" data-act-click="gmAddMilestone()">📌 Add Milestone</button>
        <button class="gm-action-btn" data-act-click="gmEditGoal()">✏️ Edit</button>
        <button class="gm-action-btn danger" data-act-click="gmDeleteGoal()">🗑</button>
      </div>
    </div>

    <div class="gm-tabs">
      <div class="gm-tab ${_goalTab==='overview'?'active':''}"   data-act-click="gmSetTab('overview')" role="button" tabindex="0" data-keys="Enter,Space" data-self-click="1">Overview</div>
      <div class="gm-tab ${_goalTab==='decompose'?'active':''}"  data-act-click="gmSetTab('decompose')" role="button" tabindex="0" data-keys="Enter,Space" data-self-click="1">
        Decompose<span class="gm-tab-badge" id="gm-decomp-badge">${decomp.length||''}</span>
      </div>
      <div class="gm-tab ${_goalTab==='score'?'active':''}"      data-act-click="gmSetTab('score')" role="button" tabindex="0" data-keys="Enter,Space" data-self-click="1">Outcome Score</div>
      <div class="gm-tab ${_goalTab==='history'?'active':''}"    data-act-click="gmSetTab('history')" role="button" tabindex="0" data-keys="Enter,Space" data-self-click="1">
        History<span class="gm-tab-badge" id="gm-hist-badge">${scores.length||''}</span>
      </div>
    </div>

    <div class="gm-tab-content" id="gm-tab-content">
      ${gmRenderTabContent()}
    </div>
  `;
}

function gmSetTab(tab) {
  _goalTab = tab;
  const tc = document.getElementById('gm-tab-content');
  if (tc) tc.innerHTML = gmRenderTabContent();
  // Update tab active states
  document.querySelectorAll('.gm-tab').forEach(el => {
    el.classList.toggle('active', el.textContent.trim().toLowerCase().startsWith(tab));
  });
}

function gmRenderTabContent() {
  if (!_goalSelected) return '';
  if (_goalTab === 'overview')  return gmTabOverview();
  if (_goalTab === 'decompose') return gmTabDecompose();
  if (_goalTab === 'score')     return gmTabScore();
  if (_goalTab === 'history')   return gmTabHistory();
  return '';
}


// ── Tab: Overview ─────────────────────────────────────────────────
function gmTabOverview() {
  const g   = _goalSelected.goal;
  const ms  = _goalSelected.milestones || [];
  const ci  = _goalSelected.checkins   || [];
  const donems = ms.filter(m=>m.completed).length;

  return `
    ${g.description ? `
    <div class="gm-section">
      <div class="gm-section-title">📝 Description</div>
      <div class="gm-criteria-block">${escHtml(g.description)}</div>
    </div>` : ''}

    ${g.success_criteria ? `
    <div class="gm-section">
      <div class="gm-section-title">✅ Success Criteria</div>
      <div class="gm-criteria-block">${escHtml(g.success_criteria)}</div>
    </div>` : ''}

    <div class="gm-section">
      <div class="gm-section-title">📌 Milestones
        ${ms.length ? `<span style="color:var(--text-3);font-size:10px">(${donems}/${ms.length} done)</span>` : ''}
        <button data-act-click="gmAddMilestone()" style="margin-left:auto;font-size:10px;padding:2px 7px;border-radius:5px;background:var(--bg-3);border:1px solid var(--border);color:var(--text-2);cursor:pointer">+ Add</button>
      </div>
      ${ms.length ? `
      <div class="gm-milestone-list">
        ${ms.map(m=>`
        <div class="gm-milestone-item ${m.completed?'done':''}" data-ms-id="${escHtml(m.id)}" data-ms-done="${m.completed ? 1 : 0}" data-act-click="gmCompleteMilestone(${jsArg(m.id)},${m.completed ? 1 : 0})" role="button" tabindex="0" data-keys="Enter,Space" data-self-click="1">
          <span class="gm-milestone-check">${m.completed?'✅':'⬜'}</span>
          <span class="gm-milestone-title ${m.completed?'done':''}">${escHtml(m.title)}</span>
          ${m.due_date ? `<span style="font-size:10px;color:var(--text-3)">${m.due_date}</span>` : ''}
        </div>`).join('')}
      </div>` : '<div style="color:var(--text-3);font-size:12px">No milestones yet — add one to track progress.</div>'}
    </div>

    <div class="gm-section">
      <div class="gm-section-title">💬 Check-ins (${ci.length})</div>
      ${ci.length ? `
      <div class="gm-checkin-list">
        ${ci.slice(0,8).map(c=>`
        <div class="gm-checkin-item">
          <div class="gm-checkin-head">
            <span class="gm-checkin-agent" style="color:${GOAL_AGENT_COLORS[c.agent_id]||'var(--text-2)'}">${GOAL_AGENT_ICONS[c.agent_id]||'👤'} ${c.agent_id}</span>
            ${c.progress>0?`<span class="gm-checkin-pct">${c.progress}%</span>`:''}
            <span class="gm-checkin-time">${new Date(c.created_at).toLocaleDateString()}</span>
          </div>
          ${c.note?`<div class="gm-checkin-note">${escHtml(c.note)}</div>`:''}
        </div>`).join('')}
      </div>` : '<div style="color:var(--text-3);font-size:12px">No check-ins yet.</div>'}
    </div>

    ${g.supervisor_run_id ? `
    <div class="gm-section">
      <div class="gm-section-title">🧠 Supervisor Run</div>
      <div style="background:var(--bg-2);border:1px solid var(--border);border-radius:8px;padding:10px;font-size:12px;display:flex;align-items:center;gap:8px">
        <span style="color:var(--accent-text)">${g.supervisor_run_id}</span>
        <button data-act-click="nav('supervisor')" style="margin-left:auto;font-size:11px;padding:3px 9px;border-radius:6px;background:var(--bg-3);border:1px solid var(--border);color:var(--text-1);cursor:pointer">View DAG →</button>
      </div>
    </div>` : ''}
  `;
}


// ── Tab: Decompose ────────────────────────────────────────────────
function gmTabDecompose() {
  const decomp = _goalSelected.decomposition || [];

  if (!decomp.length) {
    return `
      <div style="text-align:center;padding:40px 20px">
        <div class="u-da61af79">🧩</div>
        <div style="font-size:15px;font-weight:600;color:var(--text-1);margin-bottom:8px">No Decomposition Yet</div>
        <div style="font-size:12px;color:var(--text-3);line-height:1.6;margin-bottom:20px">
          Click "Decompose" to have the Brain agent break this goal into<br>
          a dependency-ordered Task DAG with specialist assignments.
        </div>
        <button class="gm-new-btn" style="width:auto;padding:10px 24px;font-size:13px" data-act-click="gmDecomposeGoal()">🧩 Decompose This Goal</button>
      </div>`;
  }

  // Auto-layout the tasks
  const seqMap = {};
  decomp.forEach(t => { seqMap[t.seq] = t; });
  const waveOf = {};
  decomp.forEach(t => { if (!t.depends_on?.length) waveOf[t.seq] = 0; });
  let changed = true;
  while (changed) {
    changed = false;
    decomp.forEach(t => {
      if (t.depends_on?.length && waveOf[t.seq] == null) {
        if (t.depends_on.every(d => waveOf[d] != null)) {
          waveOf[t.seq] = Math.max(...t.depends_on.map(d => waveOf[d])) + 1;
          changed = true;
        }
      }
    });
  }
  const waves = {};
  decomp.forEach(t => { const w = waveOf[t.seq] ?? 0; (waves[w] = waves[w]||[]).push(t); });
  const NODE_W=190, NODE_H=100, H_GAP=60, V_GAP=16;
  Object.keys(waves).sort().forEach(w => {
    const wt = waves[w].sort((a,b)=>a.seq-b.seq);
    const totalH = wt.length*NODE_H + (wt.length-1)*V_GAP;
    const startY = Math.max(20, 220-totalH/2);
    wt.forEach((t,i) => {
      t._x = 20 + parseInt(w) * (NODE_W + H_GAP);
      t._y = startY + i*(NODE_H+V_GAP);
    });
  });
  const maxX = Math.max(...decomp.map(t=>(t._x||0)+NODE_W+40));
  const maxY = Math.max(...decomp.map(t=>(t._y||0)+NODE_H+40));

  const nodesHTML = decomp.map(t => {
    const col = GOAL_AGENT_COLORS[t.agent_hint] || '#7a8aaa';
    const icon = GOAL_AGENT_ICONS[t.agent_hint] || '🤖';
    return `<div class="gm-decomp-task" id="gdt-${t.id}"
      style="left:${t._x}px;top:${t._y}px;border-color:${col}33"
      data-decomp-id="${escHtml(t.id)}" data-act-click="gmSelectDecompTask(${jsArg(t.id)})">
      <div class="gm-decomp-task-hdr">
        <div class="gm-decomp-seq" style="background:${col}">${t.seq}</div>
        <span class="gm-decomp-label">${escHtml(t.title)}</span>
        <span class="gm-decomp-agent" style="background:${col}22;color:${col}">${icon}</span>
      </div>
      <div class="gm-decomp-desc">${escHtml((t.description||'').slice(0,80))}</div>
      <div class="gm-decomp-bar" style="background:${col}"></div>
    </div>`;
  }).join('');

  // Build SVG edges
  const edgesHTML = decomp.map(t => {
    return (t.depends_on||[]).map(depSeq => {
      const src = seqMap[depSeq];
      if (!src) return '';
      const x1=(src._x||0)+NODE_W, y1=(src._y||0)+NODE_H/2;
      const x2=(t._x||0),          y2=(t._y||0)+NODE_H/2;
      const cx=(x1+x2)/2;
      return `<path d="M${x1},${y1} C${cx},${y1} ${cx},${y2} ${x2},${y2}"
        stroke="rgba(255,255,255,.18)" stroke-width="1.5" fill="none"
        marker-end="url(#gm-arr)"/>`;
    }).join('');
  }).join('');

  return `
    <div style="display:flex;align-items:center;gap:8px;margin-bottom:10px;flex-wrap:wrap">
      <span style="font-size:12px;font-weight:600;color:var(--text-0)">${decomp.length} tasks · ${Object.keys(waves).length} waves</span>
      <span style="font-size:11px;color:var(--text-3)">Click any node to see detail · Scroll to pan</span>
      <button data-act-click="gmDecomposeGoal(true)" style="margin-left:auto;font-size:11px;padding:4px 10px;border-radius:6px;background:var(--bg-2);border:1px solid var(--border);color:var(--text-1);cursor:pointer">↺ Re-decompose</button>
    </div>
    <div class="gm-decomp-canvas-wrap" style="height:${Math.max(300,maxY+30)}px">
      <svg class="gm-decomp-edges-svg" width="${maxX}" height="${Math.max(300,maxY+30)}" style="position:absolute;top:0;left:0">
        <defs>
          <marker id="gm-arr" markerWidth="8" markerHeight="8" refX="7" refY="3" orient="auto">
            <path d="M0,0 L0,6 L8,3 z" fill="rgba(255,255,255,.2)"/>
          </marker>
        </defs>
        ${edgesHTML}
      </svg>
      <div style="position:relative;width:${maxX}px;height:${Math.max(300,maxY+30)}px">${nodesHTML}</div>
    </div>
    <div id="gm-decomp-detail" style="display:none">
      <div class="gm-decomp-task-detail" id="gm-decomp-task-detail-content"></div>
    </div>
    <div style="margin-top:12px;text-align:center">
      <button class="gm-new-btn" style="width:auto;padding:8px 20px" data-act-click="gmLaunchGoalFromDecomp()">🚀 Launch Supervisor with this Decomposition</button>
    </div>
  `;
}

function gmSelectDecompTask(taskId) {
  const decomp = _goalSelected?.decomposition || [];
  const t = decomp.find(t=>t.id===taskId);
  if (!t) return;
  // Highlight node
  document.querySelectorAll('.gm-decomp-task').forEach(el=>el.classList.remove('selected'));
  document.getElementById(`gdt-${taskId}`)?.classList.add('selected');
  // Show detail
  const detailEl = document.getElementById('gm-decomp-detail');
  const contentEl = document.getElementById('gm-decomp-task-detail-content');
  if (detailEl) detailEl.style.display = 'block';
  if (contentEl) {
    const col = GOAL_AGENT_COLORS[t.agent_hint] || '#7a8aaa';
    const icon = GOAL_AGENT_ICONS[t.agent_hint] || '🤖';
    contentEl.innerHTML = `
      <div style="display:flex;align-items:center;gap:8px;margin-bottom:10px">
        <div class="gm-decomp-seq" style="background:${col};width:24px;height:24px;border-radius:50%;display:flex;align-items:center;justify-content:center;font-size:11px;font-weight:800;color:#fff;flex-shrink:0">${t.seq}</div>
        <div>
          <div style="font-size:13px;font-weight:700;color:var(--text-0)">${escHtml(t.title)}</div>
          <div style="font-size:11px;color:${col}">${icon} ${t.agent_hint}</div>
        </div>
        ${t.risk_level && t.risk_level!=='low'?`<span style="margin-left:auto;padding:2px 7px;border-radius:4px;font-size:10px;font-weight:700;background:rgba(232,82,82,.15);color:#e85252">⚠️ ${t.risk_level} risk</span>`:''}
      </div>
      ${t.description?`<div style="font-size:12px;color:var(--text-1);line-height:1.5;margin-bottom:8px">${escHtml(t.description)}</div>`:''}
      <div style="font-size:11px;color:var(--text-3)">
        Depends on: ${t.depends_on?.length ? t.depends_on.map(d=>`<strong>seq ${d}</strong>`).join(', ') : 'none (starts immediately)'}
        ${t.est_tokens?` · Est. ${t.est_tokens} tokens`:''}
      </div>`;
  }
}


// ── Tab: Score ────────────────────────────────────────────────────
function gmTabScore() {
  const g      = _goalSelected.goal;
  const scores = _goalSelected.score_history || [];
  const latest = scores.length ? scores[scores.length-1] : null;
  const score  = latest ? latest.score : (g.outcome_score ?? null);
  const breakdown = latest ? (latest.breakdown || {}) : (g.score_breakdown ? (typeof g.score_breakdown === 'string' ? JSON.parse(g.score_breakdown||'{}') : g.score_breakdown) : {});
  const grade  = score != null ? gmScoreToGrade(score) : null;
  const gradeCol = grade ? (GRADE_COLORS[grade] || '#7a8aaa') : 'var(--text-3)';

  if (score == null) {
    return `
      <div style="text-align:center;padding:40px 20px">
        <div class="u-da61af79">⭐</div>
        <div style="font-size:15px;font-weight:600;color:var(--text-1);margin-bottom:8px">No Score Yet</div>
        <div style="font-size:12px;color:var(--text-3);line-height:1.6;margin-bottom:20px">
          Click "Score Outcome" to have the Evaluator agent assess this goal's<br>
          progress across 5 dimensions and generate actionable next steps.
        </div>
        <button class="gm-new-btn" style="width:auto;padding:10px 24px;font-size:13px;background:rgba(157,116,245,.25);color:#9d74f5" data-act-click="gmScoreGoal()">⭐ Score Outcome Now</button>
      </div>`;
  }

  const dimLabels = {completion:'Completion',quality:'Quality',on_schedule:'On Schedule',criteria_met:'Criteria Met',momentum:'Momentum'};
  const dimHTML = Object.entries(dimLabels).map(([k,label]) => {
    const v = breakdown[k] ?? 0;
    const col = v>=0.8?'var(--success)':v>=0.6?'var(--warning)':'var(--danger)';
    return `<div class="gm-dimension">
      <div class="gm-dimension-label">${label}</div>
      <div class="gm-dimension-bar-track">
        <div class="gm-dimension-bar-fill" style="width:${Math.round(v*100)}%;background:${col}"></div>
      </div>
      <div class="gm-dimension-val" style="color:${col}">${Math.round(v*100)}%</div>
    </div>`;
  }).join('');

  const note = latest?.notes || '';
  // Parse strengths/gaps/next_actions from the latest score history entry if stored
  // (they're stored in notes as JSON or as plain text)
  let strengths=[], gaps=[], nextActions=[];
  try {
    const parsed = JSON.parse(latest?.notes||'{}');
    strengths   = parsed.strengths    || [];
    gaps        = parsed.gaps         || [];
    nextActions = parsed.next_actions || [];
  } catch(e) {}

  return `
    <div class="gm-score-hero">
      <div class="gm-score-circle" style="border-color:${gradeCol}">
        <span class="gm-score-pct" style="color:${gradeCol}">${Math.round(score*100)}%</span>
        <span class="gm-score-grade" style="color:${gradeCol}">${grade}</span>
      </div>
      <div class="gm-score-summary">${escHtml(note.slice(0,200) || 'Outcome evaluated')}</div>
      <div style="font-size:10px;color:var(--text-3)">Iteration ${g.iteration||1} · ${g.last_scored_at ? new Date(g.last_scored_at).toLocaleString() : 'just now'}</div>
    </div>

    <div class="gm-section">
      <div class="gm-section-title">📊 5-Dimension Breakdown</div>
      <div class="gm-dimensions-grid">${dimHTML}</div>
    </div>

    ${(strengths.length||gaps.length) ? `
    <div class="gm-score-lists">
      ${strengths.length?`
      <div class="gm-score-list-box">
        <div class="gm-score-list-title">💪 Strengths</div>
        ${strengths.map(s=>`<div class="gm-score-list-item">✓ ${escHtml(s)}</div>`).join('')}
      </div>`:''}
      ${gaps.length?`
      <div class="gm-score-list-box">
        <div class="gm-score-list-title">⚠️ Gaps</div>
        ${gaps.map(s=>`<div class="gm-score-list-item">• ${escHtml(s)}</div>`).join('')}
      </div>`:''}
    </div>` : ''}

    ${nextActions.length?`
    <div class="gm-section">
      <div class="gm-section-title">🚀 Recommended Next Actions</div>
      <div class="gm-next-actions">
        ${nextActions.map((a,i)=>`<div class="gm-next-action"><span style="color:var(--accent-text);font-weight:700;flex-shrink:0">${i+1}.</span>${escHtml(a)}</div>`).join('')}
      </div>
    </div>`:''}

    <div style="display:flex;gap:8px;margin-top:12px;flex-wrap:wrap">
      <button class="gm-action-btn u-2cc6475e" data-act-click="gmScoreGoal()" >↺ Re-score (Iteration ${(g.iteration||1)+1})</button>
      <button class="gm-action-btn u-2cc6475e" data-act-click="gmSetTab('history')" >📈 View History</button>
    </div>
  `;
}


// ── Tab: History ──────────────────────────────────────────────────
function gmTabHistory() {
  const scores = _goalSelected.score_history || [];
  const ci     = _goalSelected.checkins      || [];

  if (!scores.length && !ci.length) {
    return `<div style="color:var(--text-3);font-size:13px;text-align:center;padding:40px">No history yet. Score the goal to start tracking progress over time.</div>`;
  }

  // Sparkline SVG
  let sparklineHTML = '';
  if (scores.length >= 2) {
    const W=400, H=60, pad=10;
    const vals = scores.map(s=>s.score);
    const minV=Math.min(...vals), maxV=Math.max(...vals);
    const range = maxV-minV || 0.1;
    const points = vals.map((v,i)=>{
      const x = pad + (i/(vals.length-1))*(W-pad*2);
      const y = H - pad - ((v-minV)/range)*(H-pad*2);
      return `${x},${y}`;
    }).join(' ');
    sparklineHTML = `<svg viewBox="0 0 ${W} ${H}" style="width:100%;height:60px">
      <polyline points="${points}" fill="none" stroke="#9d74f5" stroke-width="2"/>
      ${vals.map((v,i)=>{
        const x=pad+(i/(vals.length-1))*(W-pad*2);
        const y=H-pad-((v-minV)/range)*(H-pad*2);
        return `<circle cx="${x}" cy="${y}" r="3" fill="#9d74f5"/>
          <text x="${x}" y="${y-7}" text-anchor="middle" font-size="9" fill="#9d74f5">${Math.round(v*100)}%</text>`;
      }).join('')}
    </svg>`;
  }

  return `
    ${scores.length>=2?`
    <div class="gm-history-chart">
      <div class="gm-history-chart-title">Score Trajectory (${scores.length} iterations)</div>
      <div class="gm-sparkline-wrap">${sparklineHTML}</div>
    </div>`:scores.length===1?`
    <div class="gm-history-chart">
      <div style="font-size:12px;color:var(--text-3)">Score this goal again to see a trajectory chart.</div>
    </div>`:''}

    ${scores.length?`
    <div class="gm-section">
      <div class="gm-section-title">⭐ Score History</div>
      <table class="gm-history-table">
        <thead><tr><th>Iteration</th><th>Score</th><th>Grade</th><th>Date</th><th>Notes</th></tr></thead>
        <tbody>
          ${scores.map(s=>{
            const grade = gmScoreToGrade(s.score);
            const gCol  = GRADE_COLORS[grade]||'#7a8aaa';
            let note = s.notes||'';
            try { note = JSON.parse(s.notes)?.summary || note; } catch(e) {}
            return `<tr>
              <td style="color:var(--text-2)">#${s.iteration}</td>
              <td style="font-weight:700;color:${gCol}">${Math.round(s.score*100)}%</td>
              <td><span style="padding:1px 6px;border-radius:4px;font-size:10px;font-weight:800;background:${gCol}22;color:${gCol}">${grade}</span></td>
              <td style="color:var(--text-3);font-size:10px">${new Date(s.created_at).toLocaleDateString()}</td>
              <td style="color:var(--text-2);font-size:11px;max-width:200px">${escHtml(note.slice(0,80))}</td>
            </tr>`;
          }).join('')}
        </tbody>
      </table>
    </div>`:''}

    ${ci.length?`
    <div class="gm-section">
      <div class="gm-section-title">💬 All Check-ins (${ci.length})</div>
      <div class="gm-checkin-list">
        ${ci.map(c=>`
        <div class="gm-checkin-item">
          <div class="gm-checkin-head">
            <span class="gm-checkin-agent" style="color:${GOAL_AGENT_COLORS[c.agent_id]||'var(--text-2)'}">${GOAL_AGENT_ICONS[c.agent_id]||'👤'} ${c.agent_id}</span>
            ${c.progress>0?`<span class="gm-checkin-pct">${c.progress}%</span>`:''}
            <span class="gm-checkin-time">${new Date(c.created_at).toLocaleDateString()}</span>
          </div>
          ${c.note?`<div class="gm-checkin-note">${escHtml(c.note)}</div>`:''}
        </div>`).join('')}
      </div>
    </div>`:''}
  `;
}


// ── Actions ──────────────────────────────────────────────────────
async function gmDecomposeGoal(force=false) {
  if (!_goalSelected) return;
  const goalId = _goalSelected.goal.id;
  toast('🧩 Decomposing goal with Brain agent…');
  try {
    const r = await fetch(`/api/goals/${encodeURIComponent(goalId)}/decompose`, {
      method:'POST', headers:{'Content-Type':'application/json'},
      body: JSON.stringify({force})
    });
    const d = await r.json();
    if (!d.ok) { toast('⚠️ Decomposition failed: ' + (d.error||'')); return; }
    toast(`✅ Decomposed into ${d.task_count} tasks${d.cached?' (cached)':''}`);
    // Reload full goal
    await gmSelectGoal(goalId);
    gmSetTab('decompose');
  } catch(e) { toast('⚠️ ' + e.message); }
}

async function gmScoreGoal() {
  if (!_goalSelected) return;
  const goalId = _goalSelected.goal.id;
  toast('⭐ Evaluating outcome — calling Evaluator agent…');
  try {
    const r = await fetch(`/api/goals/${encodeURIComponent(goalId)}/score`, {
      method:'POST', headers:{'Content-Type':'application/json'}, body:'{}'
    });
    const d = await r.json();
    if (!d.ok) { toast('⚠️ Scoring failed: '+(d.error||'')); return; }
    toast(`✅ Score: ${d.overall_pct}% (${d.grade}) — Iteration ${d.iteration}`);
    await gmSelectGoal(goalId);
    gmSetTab('score');
  } catch(e) { toast('⚠️ '+e.message); }
}

async function gmLaunchGoal() {
  if (!_goalSelected) return;
  const g = _goalSelected.goal;
  const ok = await gmDanger('Launch Supervisor', `Autonomously work toward:\n\n"${g.title}"\n\nThe Brain will decompose and execute this goal using specialist agents.`);
  if (!ok) return;
  toast('🚀 Launching supervisor run…');
  try {
    const r = await fetch(`/api/goals/${encodeURIComponent(g.id)}/launch`, {
      method:'POST', headers:{'Content-Type':'application/json'}, body:'{}'
    });
    const d = await r.json();
    if (d.ok) {
      toast(`🧠 Supervisor run started: ${d.run_id}`);
      await gmSelectGoal(g.id);
    } else {
      toast('⚠️ Launch failed: '+(d.error||''));
    }
  } catch(e) { toast('⚠️ '+e.message); }
}

async function gmLaunchGoalFromDecomp() {
  await gmLaunchGoal();
}

async function gmAddCheckin() {
  if (!_goalSelected) return;
  const g = _goalSelected.goal;
  const pct = await gmPrompt(`Check-in: ${g.title.slice(0,40)}`, 'New progress % (0–100):');
  if (pct === null) return;
  const n = Math.max(0, Math.min(100, parseInt(pct)||0));
  const note = await gmPrompt('Check-in Note', 'Describe what was accomplished (or leave blank):') || '';
  const r = await fetch(`/api/goals/${encodeURIComponent(g.id)}`, {
    method:'PATCH', headers:{'Content-Type':'application/json'},
    body:JSON.stringify({progress:n})
  });
  if (!r.ok) { toast('⚠️ Progress not saved — goal no longer exists?', 'error'); await gmLoadGoals(); return; }
  if (note || n>0) {
    const rc = await fetch(`/api/goals/${encodeURIComponent(g.id)}/checkin`, {
      method:'POST', headers:{'Content-Type':'application/json'},
      body: JSON.stringify({progress:n, note, agent_id:'user'})
    });
    if (!rc.ok) { toast('⚠️ Check-in not saved', 'error'); await gmSelectGoal(g.id); return; }
  }
  toast(`📈 Progress updated: ${n}%`);
  await gmSelectGoal(g.id);
}

async function gmAddMilestone() {
  if (!_goalSelected) return;
  const g = _goalSelected.goal;
  const title = await gmPrompt('New Milestone', 'Milestone title:');
  if (!title?.trim()) return;
  const due = await gmPrompt('Due Date', 'Due date (YYYY-MM-DD) or blank:') || '';
  const r = await fetch(`/api/goals/${encodeURIComponent(g.id)}/milestones`, {
    method:'POST', headers:{'Content-Type':'application/json'},
    body: JSON.stringify({title, due_date: due})
  });
  if (!r.ok) { toast('⚠️ Milestone not added', 'error'); await gmSelectGoal(g.id); return; }
  toast('📌 Milestone added');
  await gmSelectGoal(g.id);
}

async function gmCompleteMilestone(msId, alreadyDone) {
  if (alreadyDone) return;
  if (!_goalSelected) return;
  const g = _goalSelected.goal;
  const r = await fetch(`/api/goals/${encodeURIComponent(g.id)}/milestones/${encodeURIComponent(msId)}/complete`, {method:'POST'});
  if (!r.ok) toast('⚠️ Milestone not completed', 'error');
  await gmSelectGoal(g.id);
}

async function gmEditGoal() {
  if (!_goalSelected) return;
  const g = _goalSelected.goal;
  const title = await gmPrompt('Edit Goal Title', 'Title:', g.title);
  if (title === null) return;
  const criteria = await gmPrompt('Success Criteria', 'Success criteria:', g.success_criteria||'') || '';
  const r = await fetch(`/api/goals/${encodeURIComponent(g.id)}`, {
    method:'PATCH', headers:{'Content-Type':'application/json'},
    body: JSON.stringify({title: title||g.title, success_criteria: criteria})
  });
  if (!r.ok) { toast('⚠️ Goal not updated', 'error'); await gmLoadGoals(); return; }
  toast('✏️ Goal updated');
  await gmSelectGoal(g.id);
  await gmLoadGoals();
}

async function gmDeleteGoal() {
  if (!_goalSelected) return;
  const g = _goalSelected.goal;
  const ok = await gmDanger('Delete Goal', `Delete "${g.title}" and all its data?`);
  if (!ok) return;
  const r = await fetch(`/api/goals/${encodeURIComponent(g.id)}`, {method:'DELETE'});
  if (!r.ok) { toast('⚠️ Goal not deleted', 'error'); await gmLoadGoals(); return; }
  toast('🗑 Goal deleted');
  _goalSelected = null;
  document.getElementById('gm-main').innerHTML = `
    <div class="gm-empty">
      <div class="gm-empty-icon">🎯</div>
      <div class="gm-empty-title">Goal Deleted</div>
      <div class="gm-empty-sub">Select another goal from the sidebar.</div>
    </div>`;
  await gmLoadGoals();
}

function gmOpenCreate() {
  const existing = document.getElementById('gm-create-modal');
  if (existing) { existing.remove(); return; }
  const overlay = document.createElement('div');
  overlay.id = 'gm-create-modal';
  overlay.className = 'gm-modal-overlay';
  overlay.innerHTML = `
    <div class="gm-modal">
      <h3>🎯 Create New Goal</h3>
      <p class="gm-modal-sub">Define your goal with clear success criteria. The Brain agent will decompose it into tasks and the Evaluator will score your progress over time.</p>
      <div class="gm-form-grid">
        <div class="gm-form-group full">
          <label class="gm-form-label">Goal Title *</label>
          <input class="gm-form-input" id="gcf-title" placeholder="What do you want to achieve?" required>
        </div>
        <div class="gm-form-group full">
          <label class="gm-form-label">Description</label>
          <textarea class="gm-form-textarea" id="gcf-desc" placeholder="More detail about this goal, constraints, context…" rows="3"></textarea>
        </div>
        <div class="gm-form-group full">
          <label class="gm-form-label">Success Criteria</label>
          <textarea class="gm-form-textarea" id="gcf-criteria" placeholder="What does success look like? Be specific and measurable.&#10;• Criterion 1&#10;• Criterion 2" rows="3"></textarea>
        </div>
        <div class="gm-form-group">
          <label class="gm-form-label">Domain</label>
          <select class="gm-form-select" id="gcf-domain">
            <option value="Work">💼 Work</option>
            <option value="Research">🔬 Research</option>
            <option value="Learning">📚 Learning</option>
            <option value="Health">🏃 Health</option>
            <option value="Finance">💰 Finance</option>
            <option value="Personal">⭐ Personal</option>
            <option value="Home">🏠 Home</option>
            <option value="Travel">✈️ Travel</option>
          </select>
        </div>
        <div class="gm-form-group">
          <label class="gm-form-label">Priority</label>
          <select class="gm-form-select" id="gcf-priority">
            <option value="medium">Medium</option>
            <option value="high">High</option>
            <option value="critical">Critical</option>
            <option value="low">Low</option>
          </select>
        </div>
        <div class="gm-form-group">
          <label class="gm-form-label">Deadline (YYYY-MM-DD)</label>
          <input class="gm-form-input" id="gcf-deadline" type="date" placeholder="2026-12-31">
        </div>
        <div class="gm-form-group">
          <label class="gm-form-label">Tags (comma-separated)</label>
          <input class="gm-form-input" id="gcf-tags" placeholder="sdk, python, api">
        </div>
        <div class="gm-form-group full">
          <label class="gm-form-label">Initial Milestones (optional)</label>
          <div class="gm-modal-ms-list" id="gcf-ms-list">
            <div class="gm-modal-ms-item"><input class="gm-modal-ms-input" placeholder="Milestone 1…"><button data-close="parent" style="background:none;border:none;color:var(--text-3);cursor:pointer;font-size:14px">✕</button></div>
          </div>
          <button data-act-click="gcfAddMilestone()" style="margin-top:6px;font-size:11px;padding:4px 10px;border-radius:5px;background:var(--bg-3);border:1px solid var(--border);color:var(--text-2);cursor:pointer">+ Add Milestone</button>
        </div>
        <div class="gm-form-group full" style="display:flex;align-items:center;gap:8px">
          <input type="checkbox" id="gcf-auto-decompose" checked class="u-f1722f0d">
          <label for="gcf-auto-decompose" style="font-size:12px;color:var(--text-1);cursor:pointer">Auto-decompose with Brain agent after creating</label>
        </div>
      </div>
      <div class="gm-modal-row">
        <button class="gm-action-btn" data-close="id:gm-create-modal">Cancel</button>
        <button class="gm-new-btn" style="width:auto;padding:8px 20px" data-act-click="gmCreateGoal()">✅ Create Goal</button>
      </div>
    </div>`;
  overlay.onclick = e => { if (e.target===overlay) overlay.remove(); };
  document.body.appendChild(overlay);
  setTimeout(() => document.getElementById('gcf-title')?.focus(), 50);
}

function gcfAddMilestone() {
  const list = document.getElementById('gcf-ms-list');
  if (!list) return;
  const item = document.createElement('div');
  item.className = 'gm-modal-ms-item';
  item.innerHTML = `<input class="gm-modal-ms-input" placeholder="Milestone…"><button data-close="parent" style="background:none;border:none;color:var(--text-3);cursor:pointer;font-size:14px">✕</button>`;
  list.appendChild(item);
}

async function gmCreateGoal() {
  const title    = document.getElementById('gcf-title')?.value?.trim();
  if (!title) { toast('⚠️ Title is required'); return; }
  const desc     = document.getElementById('gcf-desc')?.value?.trim()     || '';
  const criteria = document.getElementById('gcf-criteria')?.value?.trim() || '';
  const domain   = document.getElementById('gcf-domain')?.value           || 'Work';
  const priority = document.getElementById('gcf-priority')?.value         || 'medium';
  const deadline = document.getElementById('gcf-deadline')?.value         || '';
  const tags     = document.getElementById('gcf-tags')?.value?.trim()     || '';
  const autoDecomp = document.getElementById('gcf-auto-decompose')?.checked ?? true;
  const msList   = [...document.querySelectorAll('#gcf-ms-list .gm-modal-ms-input')]
                     .map(el=>el.value.trim()).filter(Boolean)
                     .map(t=>({title:t}));

  document.getElementById('gm-create-modal')?.remove();

  const r = await fetch('/api/goals', {
    method:'POST', headers:{'Content-Type':'application/json'},
    body: JSON.stringify({title, description:desc, success_criteria:criteria,
                          domain, priority, deadline, tags, milestones:msList})
  }).catch(()=>null);
  if (!r||!r.ok) { toast('⚠️ Create failed'); return; }
  const d = await r.json();
  if (!d.ok) { toast('⚠️ '+(d.error||'Create failed')); return; }
  toast(`🎯 Goal created: ${title.slice(0,40)}`);
  await gmLoadGoals();
  await gmSelectGoal(d.id || d.goal_id);

  if (autoDecomp) {
    setTimeout(() => gmDecomposeGoal(), 500);
  }
}

// ── Utility ───────────────────────────────────────────────────────
function gmScoreToGrade(score) {
  if (score >= 0.97) return 'A+';
  if (score >= 0.93) return 'A';
  if (score >= 0.90) return 'A-';
  if (score >= 0.87) return 'B+';
  if (score >= 0.83) return 'B';
  if (score >= 0.80) return 'B-';
  if (score >= 0.77) return 'C+';
  if (score >= 0.73) return 'C';
  if (score >= 0.70) return 'C-';
  if (score >= 0.60) return 'D';
  return 'F';
}

// ── Old compat aliases (nav patches + old code that calls goalCreate etc.) ──
async function goalCreate()             { gmOpenCreate(); }
async function goalView(goalId)         { await gmSelectGoal(goalId); nav('goals'); }
async function goalLaunch(goalId, title){ if(_goalSelected?.goal?.id===goalId) await gmLaunchGoal(); else { await gmSelectGoal(goalId); await gmLaunchGoal(); } }
async function goalProgress(goalId)     { if(_goalSelected?.goal?.id!==goalId) await gmSelectGoal(goalId); await gmAddCheckin(); }
async function goalDelete(goalId)       { if(_goalSelected?.goal?.id!==goalId) await gmSelectGoal(goalId); await gmDeleteGoal(); }
async function goalReloadCards()        { await gmLoadGoals(); }
function goalFilterChange()             { gmFilterChange(); }
function goalDomainFilter(domain)       { _goalFilter.domain=_goalFilter.domain===domain?'':domain; _goalLimit=GOAL_PAGE_SIZE; gmLoadGoals(); }
function renderGoalCard(g)              { return ''; } // no longer used standalone


window.renderGoals = renderGoals;
// ── Delegated-handler exports ─────────────────────────────────────────────
// These are referenced by data-act-* attributes in this pane. The
// delegated dispatcher resolves handler names by property lookup on
// window, and this file is IIFE-wrapped, so without these assignments
// every one of them silently no-ops.
window.gcfAddMilestone = gcfAddMilestone;
window.gmAddCheckin = gmAddCheckin;
window.gmAddMilestone = gmAddMilestone;
window.gmCompleteMilestone = gmCompleteMilestone;
window.gmCreateGoal = gmCreateGoal;
window.gmDecomposeGoal = gmDecomposeGoal;
window.gmDeleteGoal = gmDeleteGoal;
window.gmEditGoal = gmEditGoal;
window.gmFilterChange = gmFilterChange;
window.gmLaunchGoal = gmLaunchGoal;
window.gmLaunchGoalFromDecomp = gmLaunchGoalFromDecomp;
window.gmOpenCreate = gmOpenCreate;
window.gmScoreGoal = gmScoreGoal;
window.gmSelectDecompTask = gmSelectDecompTask;
window.gmSetTab = gmSetTab;
})(S, nav, toast, escHtml, fetch, document, gmPrompt, gmConfirm, gmAlert);

  document.querySelector('#gm-tab-content')?.addEventListener('click', e => { const t = e.target.closest('[data-decomp-id]'); if (!t) return; gmSelectDecompTask(t.dataset.decompId); });
