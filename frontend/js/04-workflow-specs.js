// Agentic OS v6.0 — Workflow builder, specs, steering, hooks, code index, arena
// Extracted from index.html (block 4)


'use strict';
// NOTE: _safeLS is declared once in 00-store.js (loaded before this file).
// Do not redeclare it here — a duplicate top-level `const _safeLS` throws a
// SyntaxError that aborts this entire file at load time.

// ══════════════════════════════════════════════════════════════════
//  GLOBAL STATE — loaded once on boot
// ══════════════════════════════════════════════════════════════════
let _UI = {
  profile:    null,
  tier:       'trial',
  daysLeft:   14,
  isTrial:    true,
  uiMode:     'simple',   // 'simple' | 'power'
  loaded:     false,
};

async function loadUIConfig() {
  try {
    const r = await fetch('/api/profile/ui-config');
    if (!r.ok) throw new Error(`HTTP ${r.status}`);
    const d = await r.json();
    _UI.profile  = d.profile;
    _UI.tier     = d.tier;
    _UI.daysLeft = d.days_left;
    _UI.isTrial  = d.is_trial;
    _UI.uiMode   = d.ui_mode || 'simple';
    _UI.loaded   = true;

    applyUIMode(_UI.uiMode);
    applyProfileTheme(d.profile);
    applyHiddenPanes(d.hidden_panes || []);
    renderTrialBanner(d);
    renderNextActionBar();

    if (!d.onboarding_done) {
      setTimeout(showOnboarding, 800);
    } else if (d.show_tour) {
      setTimeout(startTour, 1200);
    }
  } catch(e) {
    console.warn('UI config load failed:', e);
  }
}

// Boot on load
window.addEventListener('load', () => setTimeout(loadUIConfig, 400));


// ══════════════════════════════════════════════════════════════════
//  TRIAL BANNER
// ══════════════════════════════════════════════════════════════════
function renderTrialBanner(cfg) {
  const existing = document.getElementById('trial-banner');
  if (existing) existing.remove();

  if (!cfg.is_trial || cfg.days_left <= 0) return;

  const daysLeft = cfg.days_left;
  const urgency  = daysLeft <= 3 ? 'var(--danger)' : daysLeft <= 7 ? 'var(--warning)' : 'var(--accent)';
  const msg      = daysLeft === 1 ? 'Last day of trial!' : `${daysLeft} days left in your free trial`;

  const banner = document.createElement('div');
  banner.id = 'trial-banner';
  banner.style.cssText = `
    position:fixed;top:0;left:0;right:0;height:32px;
    background:${urgency};color:#fff;
    display:flex;align-items:center;justify-content:center;gap:10px;
    font-size:12px;font-weight:600;z-index:9990;
    animation:slideDown .3s ease;
  `;
  banner.innerHTML = `
    
    <span>⏰ ${msg}</span>
    <button onclick="showUpgradeModal('trial-banner')" style="background:#fff2;border:1px solid #fff6;border-radius:5px;color:#fff;padding:2px 10px;cursor:pointer;font-size:11px;font-weight:700">Upgrade</button>
    <button onclick="this.closest('#trial-banner').remove()" style="background:none;border:none;color:#fff8;cursor:pointer;font-size:14px;margin-left:4px">✕</button>
  `;
  document.body.prepend(banner);

  // Push content down
  const topbar = document.getElementById('topbar');
  if (topbar) topbar.style.top = '32px';
  const sidebar = document.getElementById('sidebar');
  if (sidebar) sidebar.style.top = '84px';
  const content = document.getElementById('content');
  if (content) content.style.paddingTop = '32px';
}


// ══════════════════════════════════════════════════════════════════
//  SIMPLE / POWER MODE
// ══════════════════════════════════════════════════════════════════
const SIMPLE_MODE_PANES = new Set([
  'chat','kanban','templates','settings','docs','dashboard'
]);

function applyUIMode(mode) {
  _UI.uiMode = mode;
  document.documentElement.setAttribute('data-ui-mode', mode);

  const sidebar = document.getElementById('sidebar');
  if (!sidebar) return;

  if (mode === 'simple') {
    // Hide all nav items except simple mode panes
    sidebar.querySelectorAll('.nav-item[data-nav]').forEach(el => {
      const pane = el.getAttribute('data-nav') || '';
      el.style.display = SIMPLE_MODE_PANES.has(pane) ? '' : 'none';
    });
    // Hide section labels that have no visible items under them
    sidebar.querySelectorAll('.sidebar-group-label,.sidebar-label').forEach(el => {
      el.style.display = 'none';
    });
    // Add simple-mode header
    ensureSimpleHeader();
  } else {
    // Power mode — show everything (except user-hidden panes)
    sidebar.querySelectorAll('.nav-item[data-nav]').forEach(el => {
      el.style.display = '';
    });
    sidebar.querySelectorAll('.sidebar-group-label,.sidebar-label').forEach(el => {
      el.style.display = '';
    });
    document.getElementById('simple-mode-header')?.remove();
    applyHiddenPanes(_UI.profile?.hidden_panes || []);
  }
}

function ensureSimpleHeader() {
  if (document.getElementById('simple-mode-header')) return;
  const sidebar = document.getElementById('sidebar');
  if (!sidebar) return;

  const hdr = document.createElement('div');
  hdr.id = 'simple-mode-header';
  hdr.style.cssText = `padding:10px 12px;border-bottom:1px solid var(--border);background:var(--bg-1)`;
  hdr.innerHTML = `
    <div style="font-size:11px;font-weight:700;color:var(--text-3);text-transform:uppercase;letter-spacing:.5px;margin-bottom:6px">
      Simple Mode
    </div>
    <div style="font-size:11px;color:var(--text-2);line-height:1.5;margin-bottom:8px">
      Showing core features only.
    </div>
    <button onclick="switchUIMode('power')" style="width:100%;padding:5px;background:var(--accent);border:none;border-radius:6px;color:#fff;font-size:11px;font-weight:600;cursor:pointer">
      ⚡ Switch to Power Mode
    </button>`;
  sidebar.insertBefore(hdr, sidebar.querySelector('.sidebar-section') || sidebar.firstChild);
}




// ══════════════════════════════════════════════════════════════════
//  HIDDEN PANES & SIDEBAR CUSTOMIZATION
// ══════════════════════════════════════════════════════════════════
function applyHiddenPanes(hiddenPanes) {
  if (_UI.uiMode === 'simple') return; // simple mode handles its own visibility (only 6 core panes ever show)
  document.querySelectorAll('.nav-item[data-nav]').forEach(el => {
    const pane = el.getAttribute('data-nav') || '';
    // NOTE: previously this set el.style.display = 'none' directly, but an
    // inline style has lower CSS specificity than the tier rules below
    // (.nav-item[data-tier="core"] and [data-ui-mode="power"]
    // .nav-item[data-tier="advanced"], both !important), so hiding a pane
    // never actually worked — the button/profile state updated correctly,
    // but the pane stayed visible in the sidebar. Using a class lets the
    // dedicated .pane-hidden-by-user CSS rule win via higher specificity.
    el.classList.toggle('pane-hidden-by-user', hiddenPanes.includes(pane));
  });
}

async function togglePaneVisibility(paneId) {
  // FIX 2+3: try/catch + update _UI.profile in-memory so reopening customizer is accurate
  try {
    const r = await fetch(`/api/profile/toggle-pane/${encodeURIComponent(paneId)}`,{method:'POST'});
    const d = await r.json();
    const newHidden = d.hidden_panes || [];
    applyHiddenPanes(newHidden);
    if (_UI.profile) _UI.profile.hidden_panes = newHidden; // FIX 3: keep in-memory state current
    showToast(d.action === 'hidden' ? `🙈 ${paneId} hidden from sidebar` : `👁 ${paneId} shown in sidebar`);
    // Update just this row in place instead of destroying/rebuilding the
    // whole customizer (which reset scroll position back to the top on
    // every single click).
    updateCustomizerRow(paneId, {hidden: d.action === 'hidden'});
  } catch(e) {
    showToast('⚠️ Could not update sidebar — check connection');
  }
}

function updateCustomizerRow(paneId, {hidden, pinned} = {}) {
  const row = document.getElementById(`cust-row-${paneId}`);
  if (!row) return;
  if (hidden !== undefined) {
    row.style.borderColor = hidden ? 'var(--border)' : 'var(--border-hi)';
    const toggleBtn = row.querySelector('.cust-toggle-btn');
    if (toggleBtn) {
      toggleBtn.textContent = hidden ? 'Show' : 'Hide';
      toggleBtn.style.background = hidden ? 'var(--bg-4)' : 'rgba(91,138,248,.15)';
    }
  }
  if (pinned !== undefined) {
    const favBtn = row.querySelector('.cust-pin-btn');
    if (favBtn) {
      favBtn.innerHTML = pinned ? '★ Favorited' : '☆ Favorite';
      favBtn.style.background = pinned ? 'rgba(234,179,8,.15)' : 'none';
      favBtn.style.color = pinned ? 'var(--warning)' : 'var(--text-3)';
      favBtn.title = pinned ? 'Remove from Favorites' : 'Add to Favorites';
    }
  }
}

// NOTE: the line that used to be here —
//   window.showSidebarCustomizer = function() { showSidebarCustomizer(); };
// — created infinite self-recursion: this file is a plain (non-module)
// script, so `window.showSidebarCustomizer` and the bare identifier
// `showSidebarCustomizer` are the SAME binding. Assigning a wrapper to
// `window.showSidebarCustomizer` silently replaced what the bare name
// resolved to, so the wrapper's call to `showSidebarCustomizer()` called
// itself forever ("Maximum call stack size exceeded"). The function
// declaration below already becomes `window.showSidebarCustomizer`
// automatically in a global script — no wrapper needed.
function showSidebarCustomizer() {
  const existing = document.getElementById('sidebar-customizer');
  if (existing) { closeSidebarCustomizer(); return; }

  const profile = _UI.profile || {};
  const hidden  = profile.hidden_panes || [];
  const pinned  = profile.pinned_panes || [];

  // Grouped by the SAME 5 categories used in the real sidebar
  // (#group-core/build/ship/tools/enterprise in index.html), so this
  // customizer visually matches what the user actually sees & organizes.
  // Previously this was one flat, ungrouped 2-column list of all panes.
  const PANE_GROUPS = [
    {id: 'core', label: 'Essentials', color: 'var(--accent)', panes: [
      {id:'chat',label:'Chat',icon:'💬'},{id:'studio',label:'Code Studio',icon:'⚡'},
      {id:'templates',label:'Templates',icon:'📋'},{id:'galaxy',label:'Memory',icon:'🧠'},
      {id:'kanban',label:'Tasks',icon:'✅'},{id:'settings',label:'Settings',icon:'⚙️'},
    ]},
    {id: 'build', label: 'AI Tools', color: '#7dd3fc', panes: [
      {id:'swarm',label:'Multi-Agent Swarm',icon:'🌀'},{id:'hierarchy',label:'AI Context & Guidelines',icon:'🧭'},
      {id:'websearch',label:'Web Search',icon:'🔍'},
      {id:'browser',label:'Browser Agent',icon:'🌐'},{id:'imagegen',label:'Image Generator',icon:'🎨'},
      {id:'prompts',label:'Prompt Library',icon:'💡'},{id:'docs',label:'Docs & Help',icon:'📖'},
      {id:'terminal',label:'Terminal',icon:'💻'},{id:'skills',label:'Skills',icon:'⚡'},
    ]},
    {id: 'ship', label: 'Build', color: '#a855f7', panes: [
      {id:'composer',label:'Composer',icon:'✍️'},{id:'pipeline',label:'Pipelines',icon:'⎈'},
      {id:'workflow',label:'Workflows',icon:'⎈'},{id:'github',label:'GitHub',icon:'🐙'},
      {id:'deploy',label:'Deploy',icon:'🚀'},{id:'specs',label:'Spec Builder',icon:'📐'},
      {id:'dbstudio',label:'Database',icon:'🗄️'},{id:'workspaces',label:'Workspaces',icon:'📂'},
      {id:'plugins',label:'Plugins',icon:'🧩'},
    ]},
    {id: 'tools', label: 'Agents', color: '#34d399', panes: [
      {id:'supervisor',label:'Supervisor',icon:'🎯'},{id:'goals',label:'Goals',icon:'🎯'},
      {id:'connectors',label:'Integrations',icon:'🔗'},{id:'mcp',label:'Tool Connections',icon:'🔧'},
      {id:'mcp-gateway',label:'Gateway',icon:'🚪'},{id:'a2a',label:'Agent Network',icon:'🌐'},
      {id:'agent-identity',label:'Agent Identity',icon:'🪪'},{id:'hitl',label:'Review Queue',icon:'👁️'},
      {id:'fusion',label:'Model Fusion',icon:'🔀'},
      {id:'arena',label:'Model Arena',icon:'⚔️'},{id:'loops',label:'Autonomous Loops',icon:'♾️'},
      {id:'replay',label:'Execution Replay',icon:'⟲'},{id:'collabedit',label:'Collaborative Edit',icon:'👥'},
    ]},
    {id: 'enterprise', label: 'Monitoring', color: '#f43f5e', panes: [
      {id:'dashboard',label:'Dashboard',icon:'📊'},{id:'audit-log',label:'Audit Log',icon:'📝'},
      {id:'leaderboard',label:'Leaderboard',icon:'🏆'},{id:'agent-monitor',label:'Live Monitor',icon:'📡'},
      {id:'finops',label:'Cost Tracking',icon:'💰'},{id:'eval-framework',label:'Evaluation',icon:'🧪'},
      {id:'observability',label:'Observability',icon:'🔭'},{id:'evals',label:'Evals',icon:'🧪'},
      {id:'health',label:'Health',icon:'💚'},{id:'profiler',label:'Profiler',icon:'📈'},
      {id:'secrets',label:'Secrets Vault',icon:'🔐'},{id:'pqc',label:'Encryption',icon:'🛡️'},
      {id:'obsidian',label:'Obsidian Sync',icon:'📝'},{id:'webhooks',label:'Webhooks',icon:'🔔'},
      {id:'integrations',label:'Docs & Integrations',icon:'🔗'},{id:'knowledge-graph',label:'Knowledge Graph',icon:'🕸️'},
      {id:'rag',label:'Knowledge Search',icon:'📚'},{id:'hooks',label:'Event Hooks',icon:'⚡'},
      {id:'codeindex',label:'Code Index',icon:'🔍'},{id:'codesearch',label:'Code Search',icon:'⌕'},
      {id:'gitai',label:'Git Assistant',icon:'⎇'},{id:'bugbot',label:'Bug Finder',icon:'🐛'},
      {id:'testgen',label:'Test Generator',icon:'🧪'},{id:'marketplace',label:'Marketplace',icon:'🛒'},
      {id:'pluginsdk',label:'Plugin SDK',icon:'🔧'},{id:'multitab',label:'Multi-Preview',icon:'◫'},
      {id:'control',label:'Control Tower',icon:'🎛️'},{id:'system',label:'System',icon:'⚙️'},
      {id:'ambient',label:'Ambient Mode',icon:'🌙'},{id:'finetune',label:'Fine-Tuning',icon:'🧪'},
    ]},
  ];
  const totalPanes = PANE_GROUPS.reduce((n, g) => n + g.panes.length, 0);

  const overlay = document.createElement('div');
  overlay.id = 'sidebar-customizer';
  overlay.style.cssText = 'position:fixed;inset:0;background:rgba(0,0,0,.65);z-index:9998;display:flex;align-items:center;justify-content:center;padding:20px';
  overlay.innerHTML = `
    <div style="background:var(--bg-2);border:1px solid var(--border);border-radius:16px;max-width:720px;width:100%;max-height:82vh;overflow:hidden;display:flex;flex-direction:column">
      <div style="padding:16px 20px;border-bottom:1px solid var(--border);display:flex;align-items:center;gap:8px;flex-shrink:0">
        <span style="font-size:18px">🎛️</span>
        <h3 style="margin:0;color:var(--text-0)">Customize Sidebar</h3>
        <span style="font-size:11px;color:var(--text-3);margin-left:4px">${totalPanes} panes</span>
        <button type="button" id="sidebar-customizer-close-x" style="margin-left:auto;background:none;border:none;color:var(--text-3);font-size:18px;cursor:pointer">✕</button>
      </div>
      <div style="padding:12px 16px;font-size:12px;color:var(--text-2);border-bottom:1px solid var(--border);flex-shrink:0">
        Toggle which panes appear in your sidebar. Hidden panes are still accessible via keyboard shortcuts.
      </div>
      <div style="overflow-y:auto;padding:12px 16px" id="sidebar-customizer-groups"></div>
      <div style="padding:12px 16px;border-top:1px solid var(--border);display:flex;align-items:center;gap:8px;flex-shrink:0;flex-wrap:wrap">
        <button type="button" id="sidebar-customizer-reset" class="btn-sm" title="Shows all hidden panes again. Does not change your Favorites.">↺ Reset to Defaults</button>
        <div style="margin-left:auto;display:flex;gap:8px">
          <button type="button" id="sidebar-customizer-simple" class="btn-sm">✨ Simple Mode</button>
          <button type="button" id="sidebar-customizer-power" class="btn-sm">⚡ Power Mode</button>
        </div>
      </div>
    </div>`;

  const groupsWrap = overlay.querySelector('#sidebar-customizer-groups');
  PANE_GROUPS.forEach(group => {
    const section = document.createElement('div');
    section.style.cssText = 'margin-bottom:16px';
    section.innerHTML = `
      <div style="font-size:10.5px;font-weight:800;letter-spacing:.6px;text-transform:uppercase;color:${group.color};padding:2px 2px 8px">
        ${escHtml(group.label)} <span style="color:var(--text-3);font-weight:600">(${group.panes.length})</span>
      </div>
      <div style="display:grid;grid-template-columns:1fr 1fr;gap:6px" data-group-grid="${group.id}"></div>`;
    const grid = section.querySelector(`[data-group-grid="${group.id}"]`);
    group.panes.forEach(p => {
      const isHidden = hidden.includes(p.id);
      const isFavorited = pinned.includes(p.id);
      const row = document.createElement('div');
      row.id = `cust-row-${p.id}`;
      row.style.cssText = `display:flex;align-items:center;gap:6px;padding:7px 8px;background:var(--bg-3);border-radius:8px;border:1px solid ${isHidden ? 'var(--border)' : 'var(--border-hi)'}`;
      row.innerHTML = `
        <span style="font-size:14px">${p.icon}</span>
        <span style="font-size:12px;color:var(--text-1);flex:1;overflow:hidden;text-overflow:ellipsis;white-space:nowrap">${escHtml(p.label)}</span>
        <button type="button" class="cust-toggle-btn" data-pane-id="${p.id}" style="font-size:11px;background:${isHidden ? 'var(--bg-4)' : 'rgba(91,138,248,.15)'};border:1px solid var(--border);border-radius:5px;color:var(--text-2);padding:2px 7px;cursor:pointer;flex-shrink:0;white-space:nowrap">${isHidden ? 'Show' : 'Hide'}</button>
        <button type="button" class="cust-pin-btn" data-pane-id="${p.id}" title="${isFavorited ? 'Remove from Favorites' : 'Add to Favorites'}" style="font-size:11px;background:${isFavorited ? 'rgba(234,179,8,.15)' : 'none'};border:1px solid var(--border);border-radius:5px;color:${isFavorited ? 'var(--warning)' : 'var(--text-3)'};padding:2px 7px;cursor:pointer;flex-shrink:0;white-space:nowrap">${isFavorited ? '★ Favorited' : '☆ Favorite'}</button>`;
      grid.appendChild(row);
    });
    groupsWrap.appendChild(section);
  });

  // Event delegation instead of inline onclick="...(${JSON.stringify(id)})" —
  // the inline-onclick version broke on every pane id because
  // JSON.stringify() wraps the id in double quotes, which collide with the
  // double quotes delimiting the onclick="" attribute itself, truncating
  // the handler (e.g. onclick="togglePaneVisibility(" with nothing after
  // the open paren) and throwing "Uncaught SyntaxError: Unexpected end of
  // input" the moment any toggle/pin button was clicked.
  groupsWrap.addEventListener('click', (e) => {
    const toggleBtn = e.target.closest('.cust-toggle-btn');
    if (toggleBtn) { togglePaneVisibility(toggleBtn.dataset.paneId); return; }
    const pinBtn = e.target.closest('.cust-pin-btn');
    if (pinBtn) { pinPaneToggle(pinBtn.dataset.paneId); return; }
  });

  overlay.querySelector('#sidebar-customizer-close-x').addEventListener('click', () => closeSidebarCustomizer());
  overlay.querySelector('#sidebar-customizer-reset').addEventListener('click', () => resetSidebarToDefaults());
  overlay.querySelector('#sidebar-customizer-simple').addEventListener('click', () => switchUIMode('simple'));
  overlay.querySelector('#sidebar-customizer-power').addEventListener('click', () => switchUIMode('power'));

  overlay.addEventListener('click', e => { if(e.target===overlay) closeSidebarCustomizer(); });
  document.addEventListener('keydown', sidebarCustomizerEscHandler);
  document.body.appendChild(overlay);
}

// Closes the Customize Sidebar popup and, if it was opened from Account
// Settings > Preferences, returns you there instead of just dropping back
// to whatever pane is underneath. Account Settings is only hidden (not
// destroyed) while the customizer is open, specifically so this can
// restore it — see the "Customize Sidebar" button handler in
// 57-account-settings.js.
function closeSidebarCustomizer() {
  document.getElementById('sidebar-customizer')?.remove();
  document.removeEventListener('keydown', sidebarCustomizerEscHandler);
  window.restoreAccountSettings?.();
}
function sidebarCustomizerEscHandler(e) {
  if (e.key === 'Escape' && document.getElementById('sidebar-customizer')) {
    e.preventDefault(); e.stopPropagation(); closeSidebarCustomizer();
  }
}

async function resetSidebarToDefaults() {
  // FIX 5+6: try/catch + update _UI.profile in-memory
  try {
    const rr = await fetch('/api/profile',{method:'PATCH',headers:{'Content-Type':'application/json'},body:JSON.stringify({hidden_panes:[]})});
    if (!rr.ok) throw new Error(`HTTP ${rr.status}`);
    if (_UI.profile) _UI.profile.hidden_panes = [];
    applyHiddenPanes([]);
    // NOTE: previously this called closeSidebarCustomizer() immediately,
    // which closed the whole popup before you could see anything change —
    // combined with the fact that only hidden_panes was ever cleared (not
    // Favorites/pinned_panes, left alone on purpose — Favorites is a
    // separate preference), it looked like "Reset to Defaults" did
    // nothing at all. Keep the popup open and refresh every row in place
    // instead, so un-hiding is immediately visible before you close it
    // yourself.
    document.querySelectorAll('#sidebar-customizer .cust-toggle-btn').forEach(btn => {
      updateCustomizerRow(btn.dataset.paneId, {hidden: false});
    });
    showToast('✅ All panes shown again — sidebar reset to defaults');
  } catch(ex) {
    showToast('⚠️ Could not reset sidebar: ' + (ex?.message||String(ex)));
  }
}


async function pinPaneToggle(paneId) {
  try {
    const r = await fetch(`/api/profile/pin-pane/${encodeURIComponent(paneId)}`, {method:'POST'});
    if (!r.ok) throw new Error(`HTTP ${r.status}`);
    const d = await r.json();
    if (_UI.profile) _UI.profile.pinned_panes = d.pinned_panes || [];
    const isFavorited = d.action === 'pinned';
    showToast(isFavorited ? `⭐ ${paneId} added to Favorites` : `${paneId} removed from Favorites`);
    // Update just this row in place — see togglePaneVisibility for why we
    // stopped destroying/rebuilding the whole customizer on every click.
    updateCustomizerRow(paneId, {pinned: isFavorited});
    // Keep the REAL sidebar's ⭐ Favorites section (sidebar-enhancements.js)
    // in sync too — "Add to Favorites" here and the sidebar's own ☆/★
    // hover buttons both call this same function so both surfaces always
    // agree, whichever one you use.
    window.refreshSidebarFavorites?.(d.pinned_panes || []);
  } catch(ex) {
    showToast('⚠️ Could not update Favorites: ' + (ex?.message||String(ex)));
  }
}

async function saveSidebarOrder(order) {
  try {
    const r = await fetch('/api/profile/sidebar-order', {method:'POST', headers:{'Content-Type':'application/json'}, body: JSON.stringify({order})});
    if (!r.ok) throw new Error(`HTTP ${r.status}`);
    if (_UI.profile) _UI.profile.sidebar_order = order;
  } catch(ex) {
    showToast('⚠️ Could not save sidebar order: ' + (ex?.message||String(ex)));
  }
}


// ══════════════════════════════════════════════════════════════════
//  UPGRADE GATE MODAL
// ══════════════════════════════════════════════════════════════════
async function checkPaneAccess(paneId) {
  try {
    const r = await fetch(`/api/license/pane-access/${encodeURIComponent(paneId)}`);
    if (!r.ok) return true; // Fail open on server error
    const d = await r.json();
    if (!d.allowed) {
      showUpgradeModal(paneId, d.required_tier, d.current_tier);
      return false;
    }
    return true;
  } catch(e) {
    return true; // Fail open on network error
  }
}

function showUpgradeModal(paneId, requiredTier='pro', currentTier='free') {
  const existing = document.getElementById('upgrade-modal');
  if (existing) existing.remove();

  const tierNames = {pro:'Pro',enterprise:'Enterprise',free:'Free',trial:'Trial'};
  const tierColors = {pro:'var(--accent)',enterprise:'#f0c060',free:'var(--text-3)'};
  const tierPrices = {pro:'$29/mo',enterprise:'Contact us'};

  const paneLabel = paneId.replace(/-/g,' ').replace(/\b\w/g,c=>c.toUpperCase());
  const reqColor  = tierColors[requiredTier] || 'var(--accent)';

  const modal = document.createElement('div');
  modal.id = 'upgrade-modal';
  modal.style.cssText = 'position:fixed;inset:0;background:rgba(0,0,0,.7);z-index:9999;display:flex;align-items:center;justify-content:center;padding:20px';
  modal.innerHTML = `
    <div style="background:var(--bg-2);border:2px solid ${reqColor}44;border-radius:20px;max-width:460px;width:100%;padding:28px;text-align:center">
      <div style="font-size:48px;margin-bottom:12px">🔒</div>
      <h2 style="margin:0 0 8px;color:var(--text-0)">${paneLabel} is a ${tierNames[requiredTier]||'Pro'} Feature</h2>
      <p style="color:var(--text-2);font-size:13px;margin:0 0 20px;line-height:1.6">
        You're on the ${tierNames[currentTier]||'Free'} tier. Upgrade to <strong style="color:${reqColor}">${tierNames[requiredTier]}</strong>
        to unlock ${paneLabel} and ${requiredTier==='enterprise'?'all Enterprise features':'all Pro features'}.
      </p>

      <!-- Feature preview -->
      <div style="background:var(--bg-3);border-radius:10px;padding:12px 16px;margin-bottom:20px;text-align:left">
        <div style="font-size:11px;font-weight:700;color:var(--text-3);text-transform:uppercase;margin-bottom:8px">What you unlock</div>
        ${requiredTier==='enterprise'?`
          <div style="font-size:12px;color:var(--text-2);line-height:1.8">
            ✅ Agent Evals (DeepEval-level scoring)<br>
            ✅ LLM Observability + DORA metrics<br>
            ✅ EU AI Act compliance dashboard<br>
            ✅ Knowledge Graph memory<br>
            ✅ RAG pipeline builder
          </div>`:requiredTier==='pro'?`
          <div style="font-size:12px;color:var(--text-2);line-height:1.8">
            ✅ All 50+ panes unlocked<br>
            ✅ Swarm agents & workflows<br>
            ✅ BugBot, Specs, Steering files<br>
            ✅ Arena mode A/B testing<br>
            ✅ Voice coding & web search
          </div>`:''}
      </div>

      <div style="display:flex;gap:10px;justify-content:center">
        <button onclick="this.closest('#upgrade-modal').remove()" class="btn-sm">Maybe Later</button>
        <button onclick="showTierPlans();this.closest('#upgrade-modal').remove()" class="btn" style="background:${reqColor};border-color:${reqColor};min-width:140px">
          View Plans — ${tierPrices[requiredTier]||'Contact us'}
        </button>
      </div>

      <div style="margin-top:14px;font-size:11px;color:var(--text-3)">
        ${_UI.isTrial && _UI.daysLeft > 0
          ? `✨ You have ${_UI.daysLeft} days left in your trial — all features are active until then`
          : 'Enter a license key in Settings → License to activate'}
      </div>
    </div>`;
  modal.addEventListener('click', e => { if(e.target===modal) modal.remove(); });
  document.body.appendChild(modal);
}

async function showTierPlans() {
  let tiers = [];
  try {
    const r = await fetch('/api/license/tiers');
    if (!r.ok) throw new Error(`HTTP ${r.status}`);
    const d = await r.json();
    tiers = d.tiers || [];
  } catch(e) {
    showToast('⚠️ Could not load plans — check your connection');
    return;
  }

  const modal = document.createElement('div');
  modal.id = 'tier-plans-modal';
  modal.style.cssText = 'position:fixed;inset:0;background:rgba(0,0,0,.75);z-index:9999;display:flex;align-items:center;justify-content:center;padding:20px;overflow-y:auto';
  modal.innerHTML = `
  <div style="background:var(--bg-2);border:1px solid var(--border);border-radius:20px;max-width:860px;width:100%;padding:28px">
    <div style="display:flex;justify-content:space-between;align-items:center;margin-bottom:20px">
      <h2 style="margin:0;color:var(--text-0)">Choose Your Plan</h2>
      <button onclick="this.closest('#tier-plans-modal').remove()" style="background:none;border:none;color:var(--text-3);font-size:20px;cursor:pointer">✕</button>
    </div>
    <div style="display:grid;grid-template-columns:repeat(3,1fr);gap:16px">
      ${tiers.map((t) =>`
        <div style="background:var(--bg-3);border:2px solid ${t.highlight?'var(--accent)':'var(--border)'};border-radius:14px;padding:20px;position:relative">
          ${t.highlight?'<div style="position:absolute;top:-11px;left:50%;transform:translateX(-50%);background:var(--accent);color:#fff;font-size:11px;font-weight:700;padding:2px 12px;border-radius:20px">MOST POPULAR</div>':''}
          <div style="font-size:22px;font-weight:800;color:var(--text-0);margin-bottom:4px">${t.name}</div>
          <div style="font-size:24px;font-weight:800;color:${t.highlight?'var(--accent)':'var(--text-0)'};margin-bottom:8px">${t.price}</div>
          <div style="font-size:12px;color:var(--text-2);margin-bottom:16px">${t.description}</div>
          <div style="margin-bottom:14px">
            ${t.features.map((f) =>`<div style="font-size:11px;color:var(--text-1);padding:3px 0">✅ ${f}</div>`).join('')}
            ${t.locked.length?`<div style="margin-top:8px">${t.locked.map((f) =>`<div style="font-size:11px;color:var(--text-3);padding:2px 0">🔒 ${f}</div>`).join('')}</div>`:''}
          </div>
          <button onclick="handlePlanCTA(${JSON.stringify(t.id)},${JSON.stringify(t.cta)})" style="width:100%;padding:10px;background:${t.highlight?'var(--accent)':'var(--bg-4)'};border:1px solid ${t.highlight?'var(--accent)':'var(--border)'};border-radius:8px;color:${t.highlight?'#fff':'var(--text-0)'};font-weight:700;cursor:pointer;font-size:13px">
            ${t.cta}
          </button>
        </div>`).join('')}
    </div>
    <div style="text-align:center;margin-top:16px;font-size:12px;color:var(--text-3)">
      Have a license key? <button onclick="showLicenseActivation()" style="background:none;border:none;color:var(--accent);cursor:pointer;text-decoration:underline">Enter it here</button> &nbsp;·&nbsp; <button onclick="showSetUserModal()" style="background:none;border:none;color:var(--text-3);cursor:pointer;text-decoration:underline;font-size:11px">Update user details</button>
    </div>
  </div>`;
  modal.addEventListener('click', e => { if(e.target===modal) modal.remove(); });
  document.body.appendChild(modal);
}

async function handlePlanCTA(tierId, cta) {
  if (tierId === 'enterprise') {
    window.open('mailto:sales@agentic-os.ai?subject=Enterprise+License', '_blank');
    return;
  }
  if (tierId === 'free') {
    document.getElementById('tier-plans-modal')?.remove();
    return;
  }
  showLicenseActivation();
}

function showLicenseActivation() {
  document.getElementById('tier-plans-modal')?.remove();
  document.getElementById('license-activation-modal')?.remove(); // idempotency
  const modal = document.createElement('div');
  modal.id = 'license-activation-modal'; // FIX B: give modal a stable id
  modal.style.cssText = 'position:fixed;inset:0;background:rgba(0,0,0,.7);z-index:9999;display:flex;align-items:center;justify-content:center;padding:20px';
  modal.innerHTML = `
    <div style="background:var(--bg-2);border:1px solid var(--border);border-radius:16px;padding:28px;max-width:420px;width:100%">
      <h3 style="margin:0 0 12px;color:var(--text-0)">🔑 Activate License</h3>
      <p style="font-size:13px;color:var(--text-2);margin:0 0 14px">Enter your license key to unlock Pro or Enterprise features. Keys start with PRO- or ENT-.</p>
      <input id="license-key-input" placeholder="PRO-XXXX-XXXX-XXXX or ENT-XXXX-XXXX" style="width:100%;background:var(--bg-3);border:1px solid var(--border);border-radius:8px;color:var(--text-0);font-size:13px;padding:10px 12px;box-sizing:border-box;margin-bottom:10px;font-family:monospace" onkeydown="if(event.key==='Enter')activateLicense()">
      <div style="display:flex;gap:8px">
        <button onclick="document.getElementById('license-activation-modal')?.remove()" class="btn-sm">Cancel</button>
        <button onclick="activateLicense()" class="btn" style="flex:1">✅ Activate</button>
      </div>
    </div>`;
  modal.addEventListener('click', e => { if(e.target===modal) modal.remove(); });
  document.body.appendChild(modal);
  // Auto-focus the input for quick keyboard entry
  setTimeout(() => (document.getElementById('license-key-input'))?.focus(), 50);
}

async function activateLicense() {
  const key = (document.getElementById('license-key-input'))?.value?.trim();
  if (!key) { gmAlert('Enter a license key'); return; }
  try {
    const r = await fetch('/api/license/activate',{method:'POST',headers:{'Content-Type':'application/json'},body:JSON.stringify({license_key:key})});
    const d = await r.json();
    if (d.ok) {
      document.getElementById('license-activation-modal')?.remove(); // FIX B: use stable id
      showToast(`🎉 ${d.tier} license activated! Refreshing…`);
      setTimeout(() => location.reload(), 1500);
    } else {
      gmAlert('❌ ' + (d.error||'Invalid key'));
    }
  } catch(ex) { gmAlert('Activation failed: ' + (ex?.message||String(ex))); }
}

async function showSetUserModal() {
  // Wire POST /api/license/set-user to a profile-details form
  document.getElementById('set-user-modal')?.remove();
  let existing = {};
  try {
    const r = await fetch('/api/license/status');
    if (r.ok) { const d = await r.json(); existing = {name: d.user_name||'', email: d.user_email||'', org: d.org||''}; }
  } catch(e) {}
  const modal = document.createElement('div');
  modal.id = 'set-user-modal';
  modal.style.cssText = 'position:fixed;inset:0;background:rgba(0,0,0,.7);z-index:9999;display:flex;align-items:center;justify-content:center;padding:20px';
  modal.innerHTML = `
    <div style="background:var(--bg-2);border:1px solid var(--border);border-radius:16px;padding:28px;max-width:400px;width:100%">
      <h3 style="margin:0 0 16px;color:var(--text-0)">👤 License User Details</h3>
      <input id="set-user-name"  placeholder="Your name"         value="${escHtml(existing.name||'')}"  style="width:100%;background:var(--bg-3);border:1px solid var(--border);border-radius:8px;color:var(--text-0);font-size:13px;padding:9px 12px;box-sizing:border-box;margin-bottom:8px">
      <input id="set-user-email" placeholder="Email address"     value="${escHtml(existing.email||'')}" style="width:100%;background:var(--bg-3);border:1px solid var(--border);border-radius:8px;color:var(--text-0);font-size:13px;padding:9px 12px;box-sizing:border-box;margin-bottom:8px" type="email">
      <input id="set-user-org"   placeholder="Organization (opt)"value="${escHtml(existing.org||'')}"   style="width:100%;background:var(--bg-3);border:1px solid var(--border);border-radius:8px;color:var(--text-0);font-size:13px;padding:9px 12px;box-sizing:border-box;margin-bottom:14px">
      <div style="display:flex;gap:8px">
        <button onclick="document.getElementById('set-user-modal')?.remove()" class="btn-sm">Cancel</button>
        <button onclick="saveSetUser()" class="btn" style="flex:1">Save Details</button>
      </div>
    </div>`;
  modal.addEventListener('click', e => { if(e.target===modal) modal.remove(); });
  document.body.appendChild(modal);
  setTimeout(()=>document.getElementById('set-user-name')?.focus(), 50);
}

async function saveSetUser() {
  const name  = document.getElementById('set-user-name')?.value?.trim()  || '';
  const email = document.getElementById('set-user-email')?.value?.trim() || '';
  const org   = document.getElementById('set-user-org')?.value?.trim()   || '';
  try {
    const r = await fetch('/api/license/set-user', {method:'POST', headers:{'Content-Type':'application/json'}, body: JSON.stringify({name, email, org})});
    if (!r.ok) throw new Error(`HTTP ${r.status}`);
    const d = await r.json();
    if (!d.ok) throw new Error(d.error || 'Save failed');
    document.getElementById('set-user-modal')?.remove();
    showToast('✅ License user details saved');
  } catch(ex) {
    showToast('⚠️ ' + (ex?.message||String(ex)), 'error');
  }
}


// ══════════════════════════════════════════════════════════════════
//  ONBOARDING WIZARD (6 steps)
// ══════════════════════════════════════════════════════════════════
let _onboardingStep = 0;

const ONBOARDING_STEPS = [
  {
    id:       'welcome',
    title:    'Welcome to Agentic OS! 👋',
    subtitle: 'Your local-first AI operating system. Let\'s get you set up in 2 minutes.',
    content:  `
      <div style="text-align:center;padding:8px 0">
        <div style="font-size:56px;margin-bottom:12px">🤖</div>
        <p style="font-size:14px;color:var(--text-2);line-height:1.7;max-width:360px;margin:0 auto">
          Agentic OS lets you chat with any AI model, build agent workflows, review code with BugBot, and much more — all running locally on your machine.
        </p>
        <div style="background:rgba(91,138,248,.1);border:1px solid var(--accent)33;border-radius:10px;padding:12px;margin-top:16px;font-size:12px;color:var(--accent)">
          ✨ You're on a <strong>14-day free trial</strong> of all Pro & Enterprise features!
        </div>
      </div>`,
    action_label: 'Get Started →',
  },
  {
    id:       'name',
    title:    'What should we call you?',
    subtitle: 'Personalize your experience',
    content:  `
      <div style="padding:8px 0">
        <label style="font-size:12px;font-weight:700;color:var(--text-3);text-transform:uppercase;display:block;margin-bottom:6px">Your Name</label>
        <input id="ob-name" placeholder="Joshua Strickland, Strick Tech Leader, Senior Architect…" style="width:100%;background:var(--bg-3);border:1px solid var(--border);border-radius:10px;color:var(--text-0);font-size:15px;padding:12px 14px;box-sizing:border-box;margin-bottom:14px">
        <label style="font-size:12px;font-weight:700;color:var(--text-3);text-transform:uppercase;display:block;margin-bottom:6px">What best describes you?</label>
        <div style="display:grid;grid-template-columns:1fr 1fr;gap:8px" id="ob-roles">
          ${[['developer','💻','Developer'],['analyst','📊','Analyst'],['writer','✍️','Writer'],['designer','🎨','Designer'],['manager','📋','Manager'],['student','🎓','Student']].map(([id,icon,label])=>`
            <button onclick="selectRole(${JSON.stringify(id)})" id="obr-${id}" style="padding:10px;background:var(--bg-3);border:1px solid var(--border);border-radius:9px;color:var(--text-1);cursor:pointer;font-size:13px;transition:all .12s;display:flex;align-items:center;gap:8px">
              <span>${icon}</span><span>${label}</span>
            </button>`).join('')}
        </div>
      </div>`,
    action_label: 'Continue →',
  },
  {
    id:       'mode',
    title:    'Choose your experience',
    subtitle: 'You can always change this later in Settings',
    content:  `
      <div style="display:grid;grid-template-columns:1fr 1fr;gap:14px;padding:8px 0">
        <button onclick="selectMode('simple')" id="obmode-simple" style="padding:20px 16px;background:var(--bg-3);border:2px solid var(--accent);border-radius:14px;color:var(--text-0);cursor:pointer;text-align:left">
          <div style="font-size:28px;margin-bottom:8px">✨</div>
          <div style="font-weight:700;font-size:15px;margin-bottom:6px">Simple Mode</div>
          <div style="font-size:12px;color:var(--text-2);line-height:1.5">Clean interface with just the core features. Perfect for getting started quickly.</div>
          <div style="margin-top:10px;font-size:11px;color:var(--accent);font-weight:600">Recommended for beginners</div>
        </button>
        <button onclick="selectMode('power')" id="obmode-power" style="padding:20px 16px;background:var(--bg-3);border:2px solid var(--border);border-radius:14px;color:var(--text-0);cursor:pointer;text-align:left">
          <div style="font-size:28px;margin-bottom:8px">⚡</div>
          <div style="font-weight:700;font-size:15px;margin-bottom:6px">Power Mode</div>
          <div style="font-size:12px;color:var(--text-2);line-height:1.5">Full access to all 50+ panes and advanced features from the start.</div>
          <div style="margin-top:10px;font-size:11px;color:var(--text-3);font-weight:600">For experienced users</div>
        </button>
      </div>`,
    action_label: 'Continue →',
  },
  {
    id:       'apikey',
    title:    'Add your AI API key',
    subtitle: 'Required for AI chat and agents. Free to get — no credit card needed.',
    content:  `
      <div style="padding:8px 0">
        <div style="background:var(--bg-3);border-radius:10px;padding:12px 14px;margin-bottom:14px;font-size:12px;color:var(--text-2);line-height:1.7">
          <strong style="color:var(--text-0)">Get a free OpenRouter key:</strong><br>
          1. Visit <a href="https://openrouter.ai" target="_blank" style="color:var(--accent)">openrouter.ai</a><br>
          2. Sign up (free, no credit card)<br>
          3. Go to Keys → Create Key<br>
          4. Paste it below
        </div>
        <label style="font-size:12px;font-weight:700;color:var(--text-3);text-transform:uppercase;display:block;margin-bottom:6px">OpenRouter API Key</label>
        <input id="ob-apikey" placeholder="sk-or-v1-…" type="password" style="width:100%;background:var(--bg-3);border:1px solid var(--border);border-radius:10px;color:var(--text-0);font-size:14px;padding:11px 14px;box-sizing:border-box;font-family:monospace">
        <div style="margin-top:10px;font-size:12px;color:var(--text-3)">
          Your key is stored encrypted on this machine only. Never shared.
        </div>
        <button onclick="obSkipApiKey()" style="margin-top:8px;background:none;border:none;color:var(--text-3);font-size:12px;cursor:pointer;text-decoration:underline">Skip for now →</button>
      </div>`,
    action_label: 'Save Key & Continue →',
  },
  {
    id:       'template',
    title:    'What do you want to build first?',
    subtitle: 'We\'ll set up a quick-start for you',
    content:  `
      <div style="display:grid;grid-template-columns:1fr;gap:8px;padding:8px 0">
        ${[
          {id:'chat',icon:'💬',title:'Chat with AI',desc:'Ask questions, get help, explore ideas'},
          {id:'workflow',icon:'🗺️',title:'Build an AI workflow',desc:'Chain multiple agents together'},
          {id:'code',icon:'💻',title:'Code review & analysis',desc:'BugBot, code search, git AI'},
          {id:'research',icon:'🔬',title:'Research & analysis',desc:'Web search, RAG, knowledge graph'},
          {id:'explore',icon:'🚀',title:'Just explore everything',desc:'Start with the full platform tour'},
        ].map(t=>`
          <button onclick="selectTemplate(${JSON.stringify(t.id)})" id="obt-${t.id}" style="padding:12px 14px;background:var(--bg-3);border:1px solid var(--border);border-radius:10px;color:var(--text-0);cursor:pointer;text-align:left;display:flex;align-items:center;gap:10px;transition:all .12s">
            <span style="font-size:22px">${t.icon}</span>
            <div><div style="font-weight:600;font-size:13px">${t.title}</div><div style="font-size:11px;color:var(--text-2)">${t.desc}</div></div>
          </button>`).join('')}
      </div>`,
    action_label: 'Continue →',
  },
  {
    id:       'done',
    title:    'You\'re all set! 🎉',
    subtitle: 'Here\'s how to get the most out of Agentic OS',
    content:  `
      <div style="padding:8px 0">
        <div style="display:flex;flex-direction:column;gap:10px">
          ${[
            ['💬','Start chatting','Click Chat in the sidebar and type anything'],
            ['📖','Read the docs','Docs pane has guides for every feature'],
            ['⌘K','Command palette','Press ⌘K to search and navigate anywhere'],
            ['❓','Contextual help','Every pane has a ? button with instant help'],
          ].map(([icon,title,desc])=>`
            <div style="display:flex;align-items:center;gap:10px;padding:10px 12px;background:var(--bg-3);border-radius:9px">
              <span style="font-size:18px">${icon}</span>
              <div><div style="font-weight:600;font-size:13px;color:var(--text-0)">${title}</div><div style="font-size:12px;color:var(--text-2)">${desc}</div></div>
            </div>`).join('')}
        </div>
        <label style="display:flex;align-items:center;gap:8px;margin-top:14px;font-size:13px;color:var(--text-2);cursor:pointer">
          <input type="checkbox" id="ob-tour-check" checked style="width:14px;height:14px">
          Start the interactive feature tour
        </label>
      </div>`,
    action_label: '🚀 Launch Agentic OS',
  },
];

let _obRole = 'developer', _obMode = 'simple', _obTemplate = 'chat';

function selectRole(roleId) {
  _obRole = roleId;
  document.querySelectorAll('#ob-roles button').forEach(b => {
    b.style.borderColor = 'var(--border)';
    b.style.background  = 'var(--bg-3)';
    b.style.color       = 'var(--text-1)';
  });
  const btn = document.getElementById(`obr-${roleId}`);
  if (btn) { btn.style.borderColor='var(--accent)'; btn.style.background='rgba(91,138,248,.1)'; btn.style.color='var(--text-0)'; }
}

function selectMode(mode) {
  _obMode = mode;
  ['simple','power'].forEach(m => {
    const btn = document.getElementById(`obmode-${m}`);
    if (btn) btn.style.borderColor = m===mode ? 'var(--accent)' : 'var(--border)';
  });
}

function selectTemplate(tid) {
  _obTemplate = tid;
  document.querySelectorAll('[id^="obt-"]').forEach(b => {
    b.style.borderColor = 'var(--border)';
    b.style.background  = 'var(--bg-3)';
  });
  const btn = document.getElementById(`obt-${tid}`);
  if (btn) { btn.style.borderColor='var(--accent)'; btn.style.background='rgba(91,138,248,.08)'; }
}

function obSkipApiKey() {
  _onboardingStep++;
  renderOnboardingStep();
}

function showOnboarding() {
  try { if (_safeLS.get('agentic_os_onboarded') === 'true' || window._onboardingDismissed) return; } catch(e) {}
  if (document.getElementById('onboarding-overlay')) return;
  _onboardingStep = 0;

  const overlay = document.createElement('div');
  overlay.id = 'onboarding-overlay';
  overlay.style.cssText = 'position:fixed;inset:0;background:rgba(7,8,15,.92);z-index:99999;display:flex;align-items:center;justify-content:center;padding:20px';
  overlay.onclick = function(e) { if (e.target === overlay) { if (typeof window.closeOnboardingModal === 'function') window.closeOnboardingModal(); else overlay.remove(); } };
  overlay.innerHTML = `
    <div id="onboarding-card" style="background:var(--bg-2);border:1px solid var(--border);border-radius:20px;max-width:500px;width:100%;box-shadow:0 32px 64px rgba(0,0,0,.5);overflow:hidden;position:relative">
      <button onclick="if(typeof window.closeOnboardingModal==='function')window.closeOnboardingModal();else document.getElementById('onboarding-overlay')?.remove();" style="position:absolute;top:16px;right:20px;background:none;border:none;color:var(--text-2);font-size:26px;cursor:pointer;z-index:999999;line-height:1">×</button>
      <!-- Progress bar -->
      <div style="height:3px;background:var(--bg-4)">
        <div id="ob-progress" style="height:100%;background:var(--accent);transition:width .3s;width:0%"></div>
      </div>
      <div style="padding:28px" id="ob-content"></div>
      <div style="padding:0 28px 24px;display:flex;align-items:center;justify-content:space-between">
        <div id="ob-dots" style="display:flex;gap:6px"></div>
        <div style="display:flex;gap:8px">
          <button id="ob-back-btn" onclick="obBack()" style="display:none;background:var(--bg-3);border:1px solid var(--border);border-radius:8px;color:var(--text-1);padding:8px 16px;cursor:pointer;font-size:13px">← Back</button>
          <button id="ob-next-btn" onclick="obNext()" style="background:var(--accent);border:none;border-radius:8px;color:#fff;padding:8px 20px;cursor:pointer;font-size:13px;font-weight:700">Get Started →</button>
        </div>
      </div>
    </div>`;
  document.body.appendChild(overlay);
  renderOnboardingStep();
}

function renderOnboardingStep() {
  const step    = ONBOARDING_STEPS[_onboardingStep];
  const total   = ONBOARDING_STEPS.length;
  const pct     = Math.round((_onboardingStep/total)*100);

  const prog    = document.getElementById('ob-progress');
  const content = document.getElementById('ob-content');
  const dots    = document.getElementById('ob-dots');
  const backBtn = document.getElementById('ob-back-btn');
  const nextBtn = document.getElementById('ob-next-btn');

  if (!step || !content) return;

  if (prog) prog.style.width = pct + '%';
  if (nextBtn) nextBtn.textContent = step.action_label;
  if (backBtn) backBtn.style.display = _onboardingStep > 0 ? '' : 'none';

  content.innerHTML = `
    <h2 style="margin:0 0 4px;color:var(--text-0);font-size:20px">${step.title}</h2>
    <p style="margin:0 0 18px;color:var(--text-2);font-size:13px">${step.subtitle}</p>
    ${step.content}`;

  if (dots) dots.innerHTML = ONBOARDING_STEPS.map((_,i)=>`
    <div style="width:8px;height:8px;border-radius:50%;background:${i===_onboardingStep?'var(--accent)':'var(--bg-4)'}"></div>`).join('');

  // Auto-select defaults
  if (step.id === 'mode')     selectMode('simple');
  if (step.id === 'template') selectTemplate('chat');
}

function obBack() {
  if (_onboardingStep > 0) { _onboardingStep--; renderOnboardingStep(); }
}

// Persists the name typed in the 'name' step so it can be used at completion
let _obName = '';

async function obNext() {
  const step = ONBOARDING_STEPS[_onboardingStep];
  if (!step) return;

  try {
    // Collect and persist data per step — network errors are non-fatal
    if (step.id === 'name') {
      _obName = document.getElementById('ob-name')?.value?.trim() || '';
      const patch = {role: _obRole};
      if (_obName) patch.name = _obName;
      const r1 = await fetch('/api/profile', {method:'PATCH', headers:{'Content-Type':'application/json'}, body:JSON.stringify(patch)});
      if (!r1.ok) console.warn('[Onboarding] Profile patch failed: HTTP', r1.status);
      await fetch('/api/profile/role/' + encodeURIComponent(_obRole), {method:'POST'}).catch(()=>{});
    }
    else if (step.id === 'mode') {
      const r2 = await fetch('/api/profile', {method:'PATCH', headers:{'Content-Type':'application/json'}, body:JSON.stringify({ui_mode:_obMode})});
      if (!r2.ok) console.warn('[Onboarding] Mode patch failed: HTTP', r2.status);
      else _UI.uiMode = _obMode;
    }
    else if (step.id === 'apikey') {
      const key = document.getElementById('ob-apikey')?.value?.trim();
      if (key) {
        const r3 = await fetch('/api/secrets/set', {method:'POST', headers:{'Content-Type':'application/json'}, body:JSON.stringify({key:'OPENROUTER_API_KEY', value:key})});
        if (!r3.ok) console.warn('[Onboarding] API key save failed: HTTP', r3.status);
        else showToast('🔑 API key saved');
      }
    }
    else if (step.id === 'done') {
      const showTour = document.getElementById('ob-tour-check')?.checked;
      window._onboardingDismissed = true;
      try { try { _safeLS.set('agentic_os_onboarded', 'true'); } catch {} } catch(e) {}
      if (typeof window.closeOnboardingModal === 'function') window.closeOnboardingModal();
      else document.getElementById('onboarding-overlay')?.remove();
      
      try { applyUIMode(_obMode); } catch(e) {}
      showToast('🚀 Welcome to Agentic OS!');

      try {
        fetch('/api/profile/complete-onboarding', {
          method:'POST', headers:{'Content-Type':'application/json'},
          body: JSON.stringify({name:_obName, role:_obRole, ui_mode:_obMode, show_tour:showTour})
        }).catch(()=>{});
        fetch('/api/onboarding/complete', {
          method:'POST', headers:{'Content-Type':'application/json'},
          body: JSON.stringify({ui_mode: _obMode})
        }).catch(()=>{});
      } catch(e) {}

      setTimeout(() => {
        const dest = {chat:'chat', workflow:'workflow', code:'studio', research:'websearch', explore:'docs'};
        try { if (window.nav) nav(dest[_obTemplate] || 'chat'); } catch(e) {}
        if (showTour) setTimeout(startTour, 800);
      }, 300);
      return;
    }
  } catch(ex) {
    window._onboardingDismissed = true;
    if (typeof window.closeOnboardingModal === 'function') window.closeOnboardingModal();
    else { const ov = document.getElementById('onboarding-overlay'); if (ov) ov.remove(); }
    console.warn('[Onboarding] Step save failed (non-critical):', ex?.message || String(ex));
  }

  _onboardingStep++;
  if (_onboardingStep < ONBOARDING_STEPS.length) {
    renderOnboardingStep();
  }
}


// ══════════════════════════════════════════════════════════════════
//  INTERACTIVE FEATURE TOUR
// ══════════════════════════════════════════════════════════════════
// FIX 1: renamed from TOUR_STEPS → _TOUR_STEPS to avoid const re-declaration
// conflict with the legacy Sprint-10 TOUR_STEPS in an earlier script block.
// Both blocks share global scope; re-declaring 'const' across script blocks
// throws a SyntaxError that would crash this entire script block.
const _TOUR_STEPS = [
  {target:'#topbar',          title:'Top Bar',            desc:'Model switcher, AI OPs Manual shortcut, and User Identity Hub live here.',         position:'bottom'},
  {target:'#sidebar',         title:'Sidebar Navigation', desc:'All 60+ features are categorized across 5 folders. Toggle Simple vs Power mode anytime.',position:'right'},
  {target:'#pane-chat',       title:'Chat — Your AI Hub', desc:'Single-model chat default or Swarm Fan-out. Switch agents, pick models, and save prompts.',position:'center', group:'core'},
  {target:'[onclick="toggleSidebarGroup(\'core\')"]', title:'Core Workstation', desc:'Essential daily tools: Chat, Studio live code editor, Swarm fan-out, and your 3D Memory Galaxy.', position:'right', group:'core'},
  {target:'[onclick="toggleSidebarGroup(\'build\')"]', title:'Build & AI Engine', desc:'Full developer engine room: AST Code Graph, Specialist Skills Hub, and LoRA Fine-Tuning workstation.', position:'right', group:'build'},
  {target:'[onclick="toggleSidebarGroup(\'ship\')"]', title:'Ship & Governance', desc:'One-click deployment to Vercel/Netlify, GitHub PR automation, and executive Control Tower.', position:'right', group:'ship'},
  {target:'[onclick="toggleSidebarGroup(\'tools\')"]', title:'Agentic Orchestration', desc:'Spec Builder, BugBot automated repair, real-time CRDT Collaboration, and Marketplace packs.', position:'right', group:'tools'},
  {target:'[onclick="toggleSidebarGroup(\'enterprise\')"]', title:'Enterprise Governance & Telemetry', desc:'Executive SLA Tower, HITL Approval Gates (<85% confidence interrupt), and Post-Quantum Lattice Cryptography.', position:'right', group:'enterprise'},
  {target:'[data-nav="docs"]',  title:'Documentation & Video Guides',   desc:'Everything explained — interactive video walkthroughs, Quick Starts, FAQ, and keyboard shortcuts.',   position:'right', group:'enterprise'},
  {target:'[data-nav="settings"]',title:'Settings & Open WebUI Hub',       desc:'Open WebUI 3-card connection hub (`OpenRouter`, `Ollama`, `Custom URL`), themes, and identity branding.', position:'right', group:'core'},
];

let _tourStep = 0;

// FIX 2: inject tour-pulse CSS once per page load, not per step
(function injectTourCSS() {
  if (document.getElementById('tour-pulse-style')) return;
  const s = document.createElement('style');
  s.id = 'tour-pulse-style';
  s.textContent = '@keyframes tour-pulse{0%,100%{box-shadow:0 0 0 9999px rgba(7,8,15,.75),0 0 12px var(--accent-glow)}50%{box-shadow:0 0 0 9999px rgba(7,8,15,.75),0 0 24px var(--accent-glow)}}';
  document.head.appendChild(s);
})();

// FIX 3: ESC key handler to dismiss the tour
(function addTourEscHandler() {
  document.addEventListener('keydown', function _tourEsc(e) {
    if (e.key === 'Escape' && document.getElementById('tour-tooltip')) {
      cleanTour();
    }
  });
})();

function startTour() {
  _tourStep = 0;
  showTourStep();
  // Persist show_tour:false so tour doesn't re-show on next load (fire-and-forget)
  fetch('/api/profile',{method:'PATCH',headers:{'Content-Type':'application/json'},body:JSON.stringify({show_tour:false})}).catch(()=>{});
}

function showTourStep() {
  cleanTour();
  if (_tourStep >= _TOUR_STEPS.length) {
    showToast('✅ Tour complete! Press ⌘K to search anything.');
    return;
  }
  const step = _TOUR_STEPS[_tourStep];
  if (step.group && typeof window.toggleSidebarGroup === 'function') {
    window.toggleSidebarGroup(step.group, true);
  }
  const target = document.querySelector(step.target);

  // Skip step if target element not found in DOM
  if (!target && step.target !== '#pane-chat') { _tourStep++; showTourStep(); return; }

  // Backdrop (pointer-events:none so UI stays interactive during tour)
  const backdrop = document.createElement('div');
  backdrop.id = 'tour-backdrop';
  backdrop.style.cssText = 'position:fixed;inset:0;background:rgba(7,8,15,.75);z-index:9900;pointer-events:none';
  document.body.appendChild(backdrop);

  // Highlight ring around target
  if (target) {
    const rect = target.getBoundingClientRect();
    const hl   = document.createElement('div');
    hl.id = 'tour-highlight';
    hl.style.cssText = `position:fixed;left:${rect.left-4}px;top:${rect.top-4}px;width:${rect.width+8}px;height:${rect.height+8}px;border:2px solid var(--accent);border-radius:10px;z-index:9901;box-shadow:0 0 0 9999px rgba(7,8,15,.75),0 0 24px var(--accent-glow);pointer-events:none;animation:tour-pulse 1.5s infinite`;
    document.body.appendChild(hl);
  }

  // Tooltip card
  const tooltip = document.createElement('div');
  tooltip.id = 'tour-tooltip';
  tooltip.style.cssText = `position:fixed;background:var(--bg-2);border:1px solid var(--accent);border-radius:14px;padding:16px 18px;z-index:9902;max-width:280px;box-shadow:0 8px 32px rgba(0,0,0,.5)`;
  tooltip.innerHTML = `
    <div style="display:flex;align-items:center;justify-content:space-between;gap:6px;margin-bottom:8px">
      <span style="font-size:11px;font-weight:700;color:var(--accent)">STEP ${_tourStep+1} OF ${_TOUR_STEPS.length}</span>
      <span style="font-size:10px;color:var(--text-3)">Press Esc to close</span>
    </div>
    <div style="font-weight:700;font-size:14px;color:var(--text-0);margin-bottom:6px">${step.title}</div>
    <div style="font-size:12px;color:var(--text-2);line-height:1.6;margin-bottom:12px">${step.desc}</div>
    <div style="display:flex;gap:8px">
      <button onclick="cleanTour()" style="background:none;border:1px solid var(--border);border-radius:6px;color:var(--text-2);padding:5px 12px;cursor:pointer;font-size:11px">Skip tour</button>
      ${_tourStep>0?`<button onclick="tourBack()" style="background:var(--bg-3);border:1px solid var(--border);border-radius:6px;color:var(--text-1);padding:5px 12px;cursor:pointer;font-size:11px">← Back</button>`:''}
      <button onclick="tourNext()" style="background:var(--accent);border:none;border-radius:6px;color:#fff;padding:5px 14px;cursor:pointer;font-size:11px;font-weight:700;margin-left:auto">${_tourStep===_TOUR_STEPS.length-1?'Done ✓':'Next →'}</button>
    </div>`;

  // Position tooltip relative to target element
  if (target) {
    const rect = target.getBoundingClientRect();
    const pos  = step.position;
    let top=0, left=0;
    if      (pos==='bottom') { top=rect.bottom+12; left=rect.left; }
    else if (pos==='right')  { top=rect.top;       left=rect.right+12; }
    else                     { top=window.innerHeight/2-100; left=window.innerWidth/2-140; }
    // Clamp to viewport so tooltip never goes off-screen
    tooltip.style.top  = Math.max(8, Math.min(top,  window.innerHeight-180))+'px';
    tooltip.style.left = Math.max(8, Math.min(left, window.innerWidth-300))+'px';
  } else {
    // Center fallback when target not found
    tooltip.style.top  = '50%';
    tooltip.style.left = '50%';
    tooltip.style.transform = 'translate(-50%,-50%)';
  }
  document.body.appendChild(tooltip);
}

function cleanTour() {
  // FIX 4: also remove legacy S10 tour-popup so it doesn't linger
  document.getElementById('tour-popup')?.remove();
  document.getElementById('tour-backdrop')?.remove();
  document.getElementById('tour-highlight')?.remove();
  document.getElementById('tour-tooltip')?.remove();
}

function tourNext() {
  _tourStep++;
  if (_tourStep < _TOUR_STEPS.length) showTourStep();
  else { cleanTour(); showToast('✅ Tour complete! Press ⌘K to search anything.'); }
}

function tourBack() {
  if (_tourStep > 0) { _tourStep--; showTourStep(); }
}


// ══════════════════════════════════════════════════════════════════
//  DOCS CENTER PANE
// ══════════════════════════════════════════════════════════════════
async function renderDocs() {
  const pane = document.getElementById('pane-docs');
  if (!pane) return;

  pane.innerHTML = `
  

  <div style="display:flex;flex-direction:column;height:100%;overflow:hidden">
    <!-- Header -->
    <div style="padding:20px 24px 0;background:linear-gradient(180deg,var(--bg-1),transparent);flex-shrink:0">
      <h2 style="margin:0 0 4px;color:var(--text-0);font-size:22px">📖 Documentation Center</h2>
      <p style="margin:0 0 16px;color:var(--text-2);font-size:13px">Quick-starts, guides, FAQ, and keyboard shortcuts</p>

      <!-- Search -->
      <div style="position:relative;margin-bottom:16px">
        <input id="docs-search" aria-label="Search documentation" placeholder="Search docs… (e.g. 'how to create an agent', 'keyboard shortcuts')"
          style="width:100%;background:var(--bg-2);border:1px solid var(--border);border-radius:10px;color:var(--text-0);font-size:13px;padding:11px 14px 11px 38px;box-sizing:border-box"
          oninput="docsSearch(this.value)">
        <span style="position:absolute;left:12px;top:50%;transform:translateY(-50%);font-size:16px">🔍</span>
      </div>

      <!-- Tabs -->
      <div style="display:flex;border-bottom:1px solid var(--border);overflow-x:auto">
        <button class="docs-tab active" onclick="docsTab('quickstarts',this)">🚀 Quick Starts</button>
        <button class="docs-tab" onclick="docsTab('features',this)">📘 Features</button>
        <button class="docs-tab" onclick="docsTab('faq',this)">❓ FAQ</button>
        <button class="docs-tab" onclick="docsTab('shortcuts',this)">⌨️ Shortcuts</button>
        <button class="docs-tab" onclick="docsTab('videos',this)">🎥 Videos</button>
      </div>
    </div>

    <!-- Content -->
    <div style="flex:1;overflow-y:auto;padding:20px 24px" id="docs-content">
      <div style="color:var(--text-2)">Loading…</div>
    </div>
  </div>`;

  if (!window._docsPreventAutoTab) {
    docsTab('quickstarts', pane.querySelector('.docs-tab.active'));
  }
}

async function docsTab(tab, el) {
  document.querySelectorAll('#pane-docs .docs-tab').forEach(b=>b.classList.remove('active'));
  el?.classList.add('active');
  const content = document.getElementById('docs-content');
  if (!content) return;

  if (tab === 'quickstarts') {
    const d = await fetch('/api/docs/quick-starts').then(r=>r.ok?r.json():null).catch(()=>({quick_starts:[]}));
    content.innerHTML = `
      <div style="font-size:13px;font-weight:700;color:var(--text-0);margin-bottom:12px">Get started with these guides</div>
      <div style="display:grid;grid-template-columns:repeat(auto-fill,minmax(280px,1fr));gap:12px">
        ${(d.quick_starts||[]).map((qs) =>`
          <div class="qs-card" onclick="docsShowQuickStart(${JSON.stringify(qs.id)})">
            <span style="font-size:30px;flex-shrink:0">${qs.icon}</span>
            <div>
              <div style="font-weight:700;color:var(--text-0);font-size:14px;margin-bottom:4px">${escHtml(qs.title)}</div>
              <div style="font-size:11px;color:var(--text-3);margin-bottom:6px">⏱ ${qs.time} · ${qs.level}</div>
              <div style="font-size:12px;color:var(--text-2)">${qs.steps?.length||0} steps</div>
            </div>
          </div>`).join('')}
      </div>`;
  }
  else if (tab === 'features') {
    const d = await fetch('/api/docs/features').then(r=>r.ok?r.json():null).catch(()=>({features:[]}));
    content.innerHTML = `
      <div style="font-size:13px;font-weight:700;color:var(--text-0);margin-bottom:12px">Feature Reference</div>
      <div style="display:grid;grid-template-columns:repeat(auto-fill,minmax(220px,1fr));gap:8px">
        ${(d.features||[]).map((f) =>`
          <div class="feature-card" onclick="docsShowFeature(${JSON.stringify(f)})">
            <div style="display:flex;align-items:center;gap:8px;margin-bottom:6px">
              <span style="font-size:20px">${f.icon||'🔧'}</span>
              <span style="font-weight:600;color:var(--text-0);font-size:13px">${escHtml(f.title||'')}</span>
              <span style="margin-left:auto;font-size:9px;padding:1px 5px;border-radius:3px;background:${f.tier==='free'?'rgba(61,186,122,.15)':f.tier==='enterprise'?'rgba(240,192,96,.15)':'rgba(91,138,248,.15)'};color:${f.tier==='free'?'var(--success)':f.tier==='enterprise'?'#f0c060':'var(--accent)'}">
                ${f.tier?.toUpperCase()||'PRO'}
              </span>
            </div>
            <div style="font-size:11px;color:var(--text-2);line-height:1.5">${escHtml((f.summary||'').slice(0,80))}</div>
          </div>`).join('')}
      </div>`;
  }
  else if (tab === 'faq') {
    const d = await fetch('/api/docs/faq').then(r=>r.ok?r.json():null).catch(()=>({faq:[]}));
    content.innerHTML = `
      <div style="font-size:13px;font-weight:700;color:var(--text-0);margin-bottom:12px">Frequently Asked Questions</div>
      ${(d.faq||[]).map((f, i)=>`
        <div class="faq-item">
          <div class="faq-q" onclick="const a=this.nextElementSibling; const arr=this.querySelector('.faq-arrow') || this.querySelectorAll('span')[1]; const open=a.style.display==='block'; a.style.display=open?'none':'block'; if(arr) arr.textContent=open?'▼':'▲';">
            <span style="flex:1;font-weight:600">${escHtml(f.q||'')}</span>
            <span class="faq-arrow" style="color:var(--text-3);font-size:11px">▼</span>
          </div>
          <div class="faq-a">${escHtml(f.a||'')}</div>
        </div>`).join('')}`;
  }
  else if (tab === 'shortcuts') {
    const d = await fetch('/api/docs/shortcuts').then(r=>r.ok?r.json():null).catch(()=>({shortcuts:[]}));
    content.innerHTML = `
      <div style="font-size:13px;font-weight:700;color:var(--text-0);margin-bottom:12px">Keyboard Shortcuts</div>
      <div style="background:var(--bg-2);border:1px solid var(--border);border-radius:12px;padding:12px 16px">
        ${(d.shortcuts||[]).map((s) =>`
          <div class="shortcut-row">
            <span class="shortcut-key">${escHtml(s.key||'')}</span>
            <span style="color:var(--text-1)">${escHtml(s.desc||'')}</span>
          </div>`).join('')}
      </div>`;
  }
  else if (tab === 'videos') {
    content.innerHTML = `
      <div style="font-size:13px;font-weight:700;color:var(--text-0);margin-bottom:12px">Video Guides</div>
      <div style="display:grid;grid-template-columns:repeat(auto-fill,minmax(260px,1fr));gap:14px">
        ${[
          {icon:'💬',title:'Getting Started: Your First Chat',dur:'2:30',level:'Beginner'},
          {icon:'🤖',title:'Creating Your First Agent',dur:'3:45',level:'Beginner'},
          {icon:'🗺️',title:'Building Workflows',dur:'5:20',level:'Intermediate'},
          {icon:'📋',title:'Spec-Driven Development',dur:'8:00',level:'Intermediate'},
          {icon:'🐛',title:'BugBot Code Review',dur:'4:15',level:'Intermediate'},
          {icon:'⚔️',title:'Arena Mode: A/B Model Testing',dur:'3:00',level:'Intermediate'},
          {icon:'🧮',title:'Agent Evals & Red Teaming',dur:'6:30',level:'Advanced'},
          {icon:'📚',title:'Building a RAG Pipeline',dur:'7:00',level:'Advanced'},
        ].map(v=>`
          <div onclick="if(typeof docsShowVideoGuide==='function') docsShowVideoGuide(${JSON.stringify(v).replace(/"/g, '&quot;')})" style="background:var(--bg-2);border:1px solid var(--border);border-radius:12px;overflow:hidden;cursor:pointer;transition:all .12s" onmouseover="this.style.borderColor='var(--accent)'" onmouseout="this.style.borderColor='var(--border)'">
            <div style="background:var(--bg-3);height:120px;display:flex;align-items:center;justify-content:center;flex-direction:column;gap:8px">
              <span style="font-size:40px">${v.icon}</span>
              <div style="background:rgba(0,0,0,.5);border:1px solid rgba(255,255,255,.1);border-radius:20px;padding:4px 12px;font-size:11px;color:#fff;display:flex;align-items:center;gap:5px">
                ▶ ${v.dur}
              </div>
            </div>
            <div style="padding:12px 14px">
              <div style="font-weight:600;font-size:13px;color:var(--text-0);margin-bottom:4px">${escHtml(v.title)}</div>
              <span style="font-size:10px;padding:1px 6px;border-radius:3px;background:var(--bg-3);color:var(--text-3)">${v.level}</span>
            </div>
          </div>`).join('')}
      </div>
      <div style="text-align:center;margin-top:20px;padding:16px;background:var(--bg-2);border:1px solid var(--border);border-radius:12px">
        <div style="font-size:13px;color:var(--text-2);margin-bottom:8px">More videos coming soon! Have a request?</div>
        <button class="btn-sm" onclick="(async()=>{const req=await gmPrompt('Video Request','Which feature would you like a video for?','e.g. Workflow Builder, RAG Pipeline…');if(req)showToast('🎬 Video request noted: '+req);})()">📹 Request a Video</button>
      </div>`;
  }
}

async function docsSearch(q) {
  if (!q) { const activeTab = document.querySelector('#pane-docs .docs-tab.active') || document.querySelector('#pane-docs .docs-tab'); docsTab('quickstarts', activeTab); return; }
  const content = document.getElementById('docs-content');
  if (!content || q.length < 2) return;

  const d = await fetch(`/api/docs/search?q=${encodeURIComponent(q)}`).then(r=>r.ok?r.json():null).catch(()=>({results:[]}));
  const results = d.results || [];

  content.innerHTML = `
    <div style="font-size:13px;color:var(--text-2);margin-bottom:12px">
      ${results.length} results for "<strong style="color:var(--text-0)">${escHtml(q)}</strong>"
    </div>
    ${results.length===0?'<div style="color:var(--text-3);text-align:center;padding:24px">No results found. Try different keywords.</div>':''}
    ${results.map((r) =>`
      <div style="background:var(--bg-2);border:1px solid var(--border);border-radius:10px;padding:12px 14px;margin-bottom:6px;cursor:pointer;transition:all .12s" onclick="docsSearchResultClick(${JSON.stringify(r).replace(/"/g,'&quot;')})" onmouseover="this.style.borderColor='var(--accent)'" onmouseout="this.style.borderColor='var(--border)'">
        <div style="display:flex;align-items:center;gap:8px;margin-bottom:4px">
          <span style="font-size:11px;padding:1px 6px;border-radius:3px;background:var(--bg-3);color:var(--text-3);text-transform:uppercase">${r.type||'doc'}</span>
          <span style="font-weight:600;color:var(--text-0);font-size:13px">${escHtml(r.title||'')}</span>
          ${r.shortcut?`<span style="background:var(--bg-3);border:1px solid var(--border);border-radius:4px;padding:1px 6px;font-family:monospace;font-size:10px;color:var(--accent)">${escHtml(r.shortcut)}</span>`:''}
        </div>
        ${r.answer_preview?`<div style="font-size:12px;color:var(--text-2)">${escHtml(r.answer_preview)}</div>`:''}
      </div>`).join('')}`;
}

function docsSearchResultClick(result) {
  if (result.type==='quickstart') docsShowQuickStart(result.id);
  else if (result.type==='feature') nav(result.id);
  else if (result.type==='faq') {
    const tab = document.querySelector('#pane-docs .docs-tab:nth-child(3)');
    docsTab('faq', tab);
  }
}

async function docsShowQuickStart(qsId) {
  window._docsPreventAutoTab = true;
  if (typeof nav === 'function') nav('docs');
  const content = document.getElementById('docs-content');
  if (!content) return;
  content.innerHTML = '<div style="color:var(--text-2);padding:20px">Loading quick start steps…</div>';
  try {
    const r = await fetch(`/api/docs/quick-starts/${encodeURIComponent(qsId)}`);
    if (!r.ok) throw new Error(`HTTP ${r.status}`);
    const qs = await r.json();
    content.innerHTML=`
      <button onclick="window._docsPreventAutoTab=false;docsTab('quickstarts',document.querySelector('#pane-docs .docs-tab'))" class="btn-sm btn-3d" style="background:var(--bg-3);color:var(--text-1);border:1px solid var(--border);cursor:pointer;margin-bottom:16px">← Back to Quick Starts</button>
      <div style="display:flex;align-items:center;gap:10px;margin-bottom:12px">
        <span style="font-size:32px">${escHtml(qs.icon||'📄')}</span>
        <div>
          <h2 style="margin:0;color:var(--text-0)">${escHtml(qs.title||'')}</h2>
          <span style="font-size:12px;color:var(--text-3)">⏱ ${escHtml(qs.time||'')} · ${escHtml(qs.level||'')}</span>
        </div>
      </div>
      ${(qs.steps||[]).map(s =>`
        <div style="display:flex;gap:14px;margin-bottom:16px;background:var(--bg-2);padding:14px;border-radius:12px;border:1px solid var(--border)">
          <div style="width:28px;height:28px;border-radius:50%;background:var(--accent);display:flex;align-items:center;justify-content:center;font-size:12px;font-weight:700;color:#fff;flex-shrink:0;margin-top:2px">${s.step}</div>
          <div style="flex:1">
            <div style="font-weight:700;color:var(--text-0);font-size:14px;margin-bottom:4px">${escHtml(s.title||'')}</div>
            <div style="font-size:13px;color:var(--text-2);line-height:1.6;margin-bottom:6px">${escHtml(s.desc||'')}</div>
            ${s.tip?`<div style="font-size:11px;background:rgba(91,138,248,.1);border:1px solid var(--accent)33;border-radius:6px;padding:6px 10px;color:var(--accent)">💡 Pro Tip: ${escHtml(s.tip)}</div>`:''}
          </div>
        </div>`).join('')}
      ${(qs.related||[]).length?`<div style="margin-top:20px;border-top:1px solid var(--border);padding-top:14px"><div style="font-size:12px;font-weight:700;color:var(--text-3);margin-bottom:8px">RELATED GUIDES</div><div style="display:flex;gap:8px">${(qs.related||[]).map(rel=>`<button onclick="docsShowQuickStart(${JSON.stringify(rel)})" class="btn-sm btn-3d">${escHtml(rel.replace('qs_','').replace(/_/g,' '))}</button>`).join('')}</div></div>`:''}`;
  } catch(ex) {
    content.innerHTML = `<div style="color:var(--danger);padding:20px">${escHtml(ex?.message||String(ex))}<br><button class="btn-sm btn-3d" style="margin-top:8px" onclick="docsShowQuickStart(${JSON.stringify(qsId)})">Retry</button></div>`;
  }
}

function docsShowFeature(feature) {
  window._docsPreventAutoTab = true;
  if (typeof nav === 'function') nav('docs');
  const content = document.getElementById('docs-content');
  if (!content) return;
  content.innerHTML=`
    <button onclick="window._docsPreventAutoTab=false;docsTab('features',document.querySelectorAll('#pane-docs .docs-tab')[1])" class="btn-sm btn-3d" style="background:var(--bg-3);color:var(--text-1);border:1px solid var(--border);cursor:pointer;margin-bottom:16px">← Back to Features</button>
    <div style="display:flex;align-items:center;gap:10px;margin-bottom:14px">
      <span style="font-size:36px">${feature.icon||'🔧'}</span>
      <div>
        <h2 style="margin:0;color:var(--text-0)">${escHtml(feature.title||'')}</h2>
        <span style="font-size:11px;padding:2px 8px;border-radius:4px;background:${feature.tier==='free'?'rgba(61,186,122,.15)':feature.tier==='enterprise'?'rgba(240,192,96,.15)':'rgba(91,138,248,.15)'};color:${feature.tier==='free'?'var(--success)':feature.tier==='enterprise'?'#f0c060':'var(--accent)'}">
          ${(feature.tier||'pro').toUpperCase()} FEATURE
        </span>
      </div>
    </div>
    <p style="font-size:14px;color:var(--text-1);line-height:1.7;margin:0 0 14px">${escHtml(feature.details||feature.summary||'')}</p>
    ${(feature.tips||[]).length?`
      <div style="background:var(--bg-2);border:1px solid var(--border);border-radius:10px;padding:14px 16px;margin-bottom:14px">
        <div style="font-size:11px;font-weight:700;color:var(--text-3);text-transform:uppercase;margin-bottom:8px">💡 PRO TIPS</div>
        ${(feature.tips||[]).map((t) =>`<div style="font-size:12px;color:var(--text-2);padding:3px 0;border-bottom:1px solid var(--border)">→ ${escHtml(t)}</div>`).join('')}
      </div>`:''}
    <button onclick="nav('${(feature.id||'chat')}')" class="btn btn-primary btn-3d">Open ${escHtml(feature.title||'')} →</button>`;
}
window.openFeatureDoc = function(doc) {
  window._docsPreventAutoTab = true;
  if (typeof nav === 'function') nav('docs');
  setTimeout(() => { if (typeof docsShowFeature === 'function') docsShowFeature(doc); }, 30);
};
window.docsShowQuickStart = docsShowQuickStart;
window.docsShowFeature = docsShowFeature;
window.docsTab = docsTab;
window.docsSearch = docsSearch;
window.docsSearchResultClick = docsSearchResultClick;

window.docsShowVideoGuide = function(video) {
  const content = document.getElementById('docs-content');
  if (!content) return;
  const vidId = 'vid-frame-' + Math.random().toString(36).slice(2, 8);
  content.innerHTML = `
    <button onclick="docsTab('videos',document.querySelector('#pane-docs .docs-tab:nth-child(4)'))" class="btn-sm btn-3d" style="background:var(--bg-3);color:var(--text-1);border:1px solid var(--border);cursor:pointer;margin-bottom:16px">← Back to Video Guides</button>
    <div style="background:var(--bg-1);border:1px solid var(--border-hi);border-radius:16px;padding:24px;max-width:800px;margin:0 auto;box-shadow:var(--shadow)">
      <div style="display:flex;align-items:center;gap:12px;margin-bottom:16px">
        <span style="font-size:38px">${escHtml(video.icon||'🎬')}</span>
        <div>
          <h3 style="margin:0;font-size:20px;color:var(--text-0)">${escHtml(video.title)}</h3>
          <span class="tech-badge" style="color:var(--accent);border-color:var(--accent);margin-top:4px;display:inline-block">⏱ ${escHtml(video.dur)} · ${escHtml(video.level)} Walkthrough</span>
        </div>
      </div>
      
      <div id="${vidId}" style="background:#04060e;border-radius:12px;aspect-ratio:16/9;display:flex;flex-direction:column;align-items:center;justify-content:center;color:#fff;position:relative;overflow:hidden;margin-bottom:20px;border:1px solid var(--border-hi);box-shadow:inset 0 0 40px rgba(0,0,0,0.8)">
        <div style="position:absolute;inset:0;background:radial-gradient(circle at 50% 50%, rgba(56,189,248,0.15), rgba(0,0,0,0.85));pointer-events:none"></div>
        <div id="${vidId}-play-btn" style="font-size:54px;z-index:2;cursor:pointer;transition:transform 0.15s" onclick="startInteractiveVideoWalkthrough('${vidId}', ${JSON.stringify(video.title).replace(/"/g, '&quot;')})">▶️</div>
        <div id="${vidId}-label" style="font-size:14px;font-weight:700;margin-top:12px;z-index:2;color:#e2e8f0">Click to Play Interactive Walkthrough (${escHtml(video.title)})</div>
        <div id="${vidId}-sim-box" style="display:none;z-index:2;width:90%;height:75%;background:rgba(8,12,28,0.9);border:1px solid rgba(56,189,248,0.3);border-radius:8px;padding:16px;font-family:monospace;font-size:12px;color:#38bdf8;overflow-y:auto;text-align:left"></div>
        <div style="position:absolute;bottom:12px;left:14px;right:14px;display:flex;justify-content:space-between;font-size:11px;color:#94a3b8;z-index:2">
          <span id="${vidId}-progress">0:00 / ${escHtml(video.dur)}</span>
          <span>HD 1080p · Strick Tech Studio</span>
        </div>
      </div>

      <h4 style="margin:0 0 10px;font-size:15px;color:var(--text-0)">Video Script & Key Takeaways</h4>
      <div style="background:var(--bg-2);border:1px solid var(--border);border-radius:10px;padding:16px;font-size:13px;color:var(--text-2);line-height:1.7">
        <div style="margin-bottom:8px"><strong>0:00 - Introduction:</strong> Welcome to ${escHtml(video.title)}. In this quick guide, we cover step-by-step best practices.</div>
        <div style="margin-bottom:8px"><strong>1:10 - Core Concepts:</strong> How to configure your workspace, attach context files, and trigger the right specialist agent.</div>
        <div><strong>2:00 - Pro Tip:</strong> Use <code style="color:var(--accent)">⌘K</code> anytime to jump directly to this component or run automated actions.</div>
      </div>
    </div>
  `;
};

window.startInteractiveVideoWalkthrough = function(vidId, title) {
  const playBtn = document.getElementById(vidId + '-play-btn');
  const label   = document.getElementById(vidId + '-label');
  const simBox  = document.getElementById(vidId + '-sim-box');
  const prog    = document.getElementById(vidId + '-progress');
  if (playBtn) playBtn.style.display = 'none';
  if (label)   label.style.display   = 'none';
  if (simBox) {
    simBox.style.display = 'block';
    const steps = [
      `▶ [00:01] Launching walkthrough: ${title}...`,
      `▶ [00:05] Connecting to local-first Agentic OS engine (port 8787)...`,
      `▶ [00:12] Synchronizing 4-Tier information hierarchy & memory Galaxy...`,
      `▶ [00:25] Spawning Swarm Fan-out: 7 specialist neural agents online...`,
      `▶ [00:42] Executing live code preview inside Studio workstation...`,
      `▶ [01:10] Running E2E verification suite... 100% green passing checks ✅`,
      `▶ [01:30] Walkthrough complete! Press Esc or ← Back to explore more.`
    ];
    let i = 0;
    simBox.innerHTML = `<div style="color:#7dd3fc;font-weight:700;margin-bottom:8px">🎬 STRICK TECH INTERACTIVE PLAYER</div>`;
    const interval = setInterval(() => {
      if (i < steps.length && document.getElementById(vidId + '-sim-box')) {
        simBox.innerHTML += `<div style="margin-top:6px;animation:fadeIn 0.2s">${steps[i]}</div>`;
        simBox.scrollTop = simBox.scrollHeight;
        if (prog) prog.textContent = `0:${(i+1)*15 < 10 ? '0' : ''}${(i+1)*15} / 2:30`;
        i++;
      } else {
        clearInterval(interval);
      }
    }, 1200);
  }
};

// Contextual help button — added to every pane's header on navigation
function addContextualHelp(paneId, container) {
  if (!container || container.querySelector('.ctx-help-btn')) return;

  const header = container.querySelector('.section-head > div:first-child, .chat-header, h2, .page-header > div:first-child') || container.querySelector('.section-head, h2') || container;
  const btn = document.createElement('button');
  btn.className = 'ctx-help-btn btn-3d';
  btn.style.cssText = 'position:relative;display:inline-flex;width:24px;height:24px;border-radius:50%;background:var(--bg-3);border:1px solid var(--border);align-items:center;justify-content:center;cursor:pointer;font-size:12px;color:var(--text-3);transition:all .12s;z-index:10;margin-left:8px;vertical-align:middle;flex-shrink:0';
  btn.innerHTML = '?';
  btn.title = 'Help for this feature';

  btn.onclick = async () => {
    try {
      const r = await fetch(`/api/docs/contextual/${encodeURIComponent(paneId)}`);
      const d = await r.json();
      const doc = d.doc;
      if (doc) {
        openInspectionDrawer(doc);
      } else {
        nav('docs');
      }
    } catch(e) {
      console.warn('Contextual help fetch failed:', e);
      nav('docs');
    }
  };

  btn.onmouseover = () => { btn.style.borderColor='var(--accent)'; btn.style.color='var(--accent)'; };
  btn.onmouseout  = () => { btn.style.borderColor='var(--border)'; btn.style.color='var(--text-3)'; };
  header.appendChild(btn);
}

window.openInspectionDrawer = function(doc) {
  if (!doc) return;
  let drawer = document.getElementById('inspection-drawer');
  if (!drawer) {
    drawer = document.createElement('div');
    drawer.id = 'inspection-drawer';
    drawer.style.cssText = 'position:fixed;top:0;right:0;width:360px;height:100vh;z-index:9950;background:var(--bg-1);border-left:1px solid var(--border-hi);box-shadow:-12px 0 48px rgba(0,0,0,0.65);display:flex;flex-direction:column;transform:translateX(100%);transition:transform 0.25s cubic-bezier(0,0,.2,1)';
    document.body.appendChild(drawer);
  }
  drawer.innerHTML = `
    <div style="display:flex;align-items:center;justify-content:space-between;padding:16px 20px;background:var(--bg-2);border-bottom:1px solid var(--border);flex-shrink:0">
      <div style="display:flex;align-items:center;gap:10px">
        <span style="font-size:24px">${escHtml(doc.icon||'📘')}</span>
        <div>
          <h3 style="margin:0;font-size:15px;font-weight:800;color:var(--text-0)">${escHtml(doc.title||'Workstation Inspection')}</h3>
          <span style="font-size:11px;color:var(--accent);font-weight:700">${escHtml((doc.tier||'PRO').toUpperCase())} TIER WORKSTATION</span>
        </div>
      </div>
      <button onclick="closeInspectionDrawer()" class="btn-3d btn-ghost btn-sm" style="padding:4px 10px;font-size:14px">✕</button>
    </div>
    <div style="flex:1;overflow-y:auto;padding:20px;display:flex;flex-direction:column;gap:16px">
      <div class="surface-z2" style="padding:14px;border-radius:12px;font-size:13px;color:var(--text-1);line-height:1.65">
        ${escHtml(doc.summary||doc.details||'No summary available.')}
      </div>
      ${doc.tips?.length ? `
        <div class="surface-z1" style="padding:14px;border-radius:12px;border:1px solid var(--border)">
          <div style="font-size:11px;font-weight:800;color:var(--text-3);text-transform:uppercase;margin-bottom:8px">💡 Pro Tips & Best Practices</div>
          ${doc.tips.map(t => `<div style="font-size:12.5px;color:var(--text-2);padding:4px 0;border-bottom:1px solid var(--border)">→ ${escHtml(t)}</div>`).join('')}
        </div>` : ''}
      <div style="display:flex;flex-direction:column;gap:8px;margin-top:auto;padding-top:14px;border-top:1px solid var(--border)">
        <button onclick="closeInspectionDrawer();if(typeof openFeatureDoc === 'function') openFeatureDoc(${JSON.stringify(doc).replace(/"/g, '&quot;')}); else { nav('docs'); docsShowFeature(${JSON.stringify(doc).replace(/"/g, '&quot;')}); }" class="btn-3d btn-primary" style="width:100%">Read Full Documentation ↗</button>
        <button onclick="closeInspectionDrawer();if(typeof toggleSplitWorkspace==='function') toggleSplitWorkspace(true, '${doc.id||'docs'}')" class="btn-3d btn-ghost" style="width:100%">🗂️ Dock in Secondary Slot</button>
      </div>
    </div>
  `;
  drawer.style.display = 'flex';
  setTimeout(() => drawer.style.transform = 'translateX(0)', 20);
};

window.closeInspectionDrawer = function() {
  const drawer = document.getElementById('inspection-drawer');
  if (drawer) {
    drawer.style.transform = 'translateX(100%)';
    setTimeout(() => {
      if (drawer.style.transform === 'translateX(100%)') drawer.style.display = 'none';
    }, 250);
  }
};

// FIX 1 (CRITICAL): Wire ? button into every pane navigation.
// Called by masterNav20 after each nav() so the button appears on the active pane.
function _attachContextualHelpToPane(pane) {
  const paneEl = document.getElementById(`pane-${pane}`);
  if (!paneEl) return;
  // Prefer named header containers; fall back to the pane element itself
  const container = (
    paneEl.querySelector('.section-head') ||
    paneEl.querySelector('.chat-header') ||
    paneEl.querySelector('.pane-header') ||
    paneEl
  );
  addContextualHelp(pane, container);
}

// ══════════════════════════════════════════════════════════════════
//  NEXT-ACTION BAR (Contextual AI suggestions)
// ══════════════════════════════════════════════════════════════════
const NEXT_ACTIONS = {
  chat:          [{label:'Create Agent',icon:'🤖',action:"nav('chat')",tip:'Turn this conversation into a specialized agent'},{label:'Save to Prompts',icon:'💬',action:"nav('prompts')",tip:'Save your best prompts for reuse'},{label:'Web Search',icon:'🔎',action:"nav('websearch')",tip:'Ground your answers with live web results'}],
  kanban:        [{label:'Create Task via AI',icon:'🤖',action:"nav('chat')",tip:'Describe a feature and let AI create the task'},{label:'Generate Tests',icon:'🧪',action:"nav('testgen')",tip:'Generate tests for your current tasks'},{label:'Daily Standup',icon:'📋',action:"nav('ambient')",tip:'Get an AI-generated daily summary'}],
  studio:        [{label:'Run BugBot',icon:'🐛',action:"nav('bugbot')",tip:'Review this code for issues'},{label:'Generate Tests',icon:'🧪',action:"nav('testgen')",tip:'Auto-generate unit tests'},{label:'Code Search',icon:'🔍',action:"nav('codeindex')",tip:'Find related code in your codebase'}],
  workflow:      [{label:'View Replay',icon:'⏮️',action:"nav('replay')",tip:'Step through your last run'},{label:'Run BugBot on Output',icon:'🐛',action:"nav('bugbot')",tip:'Review workflow output for issues'},{label:'Save as Spec',icon:'📋',action:"nav('specs')",tip:'Convert to a formal spec document'}],
  bugbot:        [{label:'View Security Rules',icon:'🔒',action:"nav('gitai')",tip:'See all OWASP security rules'},{label:'Eval Agent Quality',icon:'🧮',action:"nav('evals')",tip:'Score this review with Evals'},{label:'Push to GitHub',icon:'🐙',action:"nav('github')",tip:'Create a PR with these fixes'}],
  specs:         [{label:'Run Workflow',icon:'🗺️',action:"nav('workflow')",tip:'Execute this spec as a workflow'},{label:'Generate Tests',icon:'🧪',action:"nav('testgen')",tip:'Create tests from requirements'},{label:'Code Review',icon:'🐛',action:"nav('bugbot')",tip:'Review the generated code'}],
  docs:          [{label:'Start Quick Tour',icon:'🎯',action:"startTour()",tip:'Interactive walkthrough of the platform'},{label:'Try Chat',icon:'💬',action:"nav('chat')",tip:'Put your learning into practice'}],
  evals:         [{label:'Red Team',icon:'🔴',action:"evalRedTeam()",tip:'Run OWASP attacks against your agent'},{label:'View Observability',icon:'👁️',action:"nav('observability')",tip:'See traces for your agent runs'},{label:'A/B Test Prompts',icon:'🔀',action:"evalTab('ab',document.querySelector('#pane-evals .eval-tab'))",tip:'Compare prompt variants'}],
  observability: [{label:'Check Compliance',icon:'🇪🇺',action:"obsTab('compliance',document.querySelector('#pane-observability .obs-tab:last-child'))",tip:'EU AI Act compliance status'},{label:'DORA Metrics',icon:'📊',action:"obsTab('dora',document.querySelectorAll('#pane-observability .obs-tab')[1])",tip:'Deployment frequency and reliability'}],
  rag:           [{label:'Eval RAG Quality',icon:'🧮',action:"nav('evals')",tip:'Check faithfulness and relevancy'},{label:'Add to Knowledge Graph',icon:'🕸',action:"nav('knowledge-graph')",tip:'Extract entities from your documents'}],
};

let _currentPane = 'chat';

function renderNextActionBar() {
  let bar = document.getElementById('next-action-bar');
  if (!bar) {
    bar = document.createElement('div');
    bar.id = 'next-action-bar';
    bar.style.cssText = `
      position:fixed;bottom:0;left:var(--sidebar-w);right:0;
      height:42px;background:var(--bg-1);border-top:1px solid var(--border);
      display:flex;align-items:center;gap:6px;padding:0 12px;z-index:100;
      overflow-x:auto;flex-shrink:0;
    `;
    document.body.appendChild(bar);
    // FIX 3: push content area up so fixed bar doesn't obscure bottom of panes
    const content = document.getElementById('content');
    if (content) content.style.paddingBottom = '42px';
  }
  // FIX 1: always restore display when renderNextActionBar is called
  bar.style.display = 'flex';
  updateNextActionBar(_currentPane);
}

function updateNextActionBar(pane) {
  const bar = document.getElementById('next-action-bar');
  if (!bar) return;
  const actions = NEXT_ACTIONS[pane] || [];

  // FIX 2: hide bar entirely (not just empty innerHTML) when no actions for this pane
  if (actions.length === 0) {
    bar.style.display = 'none';
    return;
  }

  // FIX 1: restore display when there ARE actions (even if bar was dismissed on another pane)
  bar.style.display = 'flex';
  bar.innerHTML = `
    <span style="font-size:10px;font-weight:700;color:var(--text-3);white-space:nowrap;flex-shrink:0">NEXT:</span>
    ${actions.map(a=>`
      <button onclick="${a.action}" title="${escHtml(a.tip)}" style="
        background:var(--bg-2);border:1px solid var(--border);border-radius:7px;
        color:var(--text-2);padding:4px 10px;cursor:pointer;font-size:11px;font-weight:600;
        white-space:nowrap;flex-shrink:0;display:flex;align-items:center;gap:5px;
        transition:all .12s;
      " onmouseover="this.style.borderColor='var(--accent)';this.style.color='var(--text-0)'"
         onmouseout="this.style.borderColor='var(--border)';this.style.color='var(--text-2)'">
        ${a.icon} ${escHtml(a.label)}
      </button>`).join('')}
    <button onclick="document.getElementById('next-action-bar').style.display='none'" style="margin-left:auto;background:none;border:none;color:var(--text-3);cursor:pointer;font-size:11px;flex-shrink:0" title="Dismiss (re-shows on next pane)">✕</button>`;
}


// ══════════════════════════════════════════════════════════════════
//  USER PROFILE PANEL + TOPBAR PROFILE BUTTON — REMOVED (superseded)
//  This used to render a separate "Identity & Custom App Branding"
//  panel (triggered by a "Me" pill in the topbar) that duplicated and
//  drifted out of sync with the "Your Profile" panel from 01-app-core.js.
//  Both are now unified into a single Account Settings modal — see
//  57-account-settings.js (window.openAccountSettings). The old
//  window.showUserProfile / window.openUserProfileModal names are kept
//  as aliases there so any remaining callers still work.
// ══════════════════════════════════════════════════════════════════


// ══════════════════════════════════════════════════════════════════
//  PATCH MASTER NAV — Sprint 20 (docs + tier check + next-action)
// ══════════════════════════════════════════════════════════════════
(function patchNavSprint20() {
  const _base = window.nav || function(){};
  window.nav = async function masterNav20(pane) {
    // Update current pane for next-action bar
    _currentPane = pane;
    updateNextActionBar(pane);

    // Docs pane
    if (pane === 'docs') { _base(pane); renderDocs?.(); return; }

    // Tier gate check for Pro/Enterprise panes
    // FIX C: Complete set of ALL Pro + Enterprise panes that require tier >= pro.
    // Previously 23 pro panes (studio, builder, swarm, github, deploy, etc.) were missing,
    // allowing free-tier users to navigate to them without seeing the upgrade gate.
    // MODULE MERGE (AI Operating Manual + AI Guidelines): 'hierarchy' was
    // completely absent from this set — a real gating bug letting free-tier
    // users open the AI Operating Manual pane with no upgrade prompt at all,
    // even though the backend's PANE_TIERS already defaulted it to 'pro'.
    // Added it explicitly now that it's also the merged home for what used
    // to be the separate 'steering' (AI Guidelines) pane, which is removed
    // from the sidebar/gate list below (folded into 'hierarchy' as a tab).
    // MODULE MERGE (Code Editor + Code Studio): 'builder' was retired and
    // folded into 'studio' — nav('builder') now redirects to nav('studio')
    // in 01-app-core.js, so the pane id is removed from this gate list
    // (it can no longer be reached directly; 'studio' alone still gates
    // correctly for the merged functionality).
    const gatedPanes = new Set([
      // Enterprise panes
      'evals','observability','knowledge-graph','rag',
      // Pro panes
      'studio','swarm','galaxy','hierarchy','loops','mcp','github','deploy','dbstudio',
      'plugins','obsidian','system','control','workspaces','webhooks','testgen','terminal','secrets',
      'integrations','imagegen','prompts','codesearch','workflow','profiler','pluginsdk',
      'multitab','replay','collabedit','marketplace','specs','hooks','codeindex','arena',
      'bugbot','health','gitai','ambient','fusion','hitl','browser','websearch',
      'leaderboard','voice','pipeline',
    ]);

    if (gatedPanes.has(pane) && _UI.loaded) {
      const tier = _UI.tier;
      if (tier === 'free') {
        // Check if this specific pane is allowed
        const r = await fetch(`/api/license/pane-access/${encodeURIComponent(pane)}`).catch(()=>null);
        const d = r ? await r.json().catch(()=>null) : null;
        if (d && !d.allowed) {
          showUpgradeModal(pane, d.required_tier, tier);
          return;
        }
      }
    }

    _base(pane);

    // FIX 1 (CRITICAL): attach contextual ? button to the active pane after navigation
    // Small delay so the pane's innerHTML is rendered before we try to find containers
    setTimeout(() => _attachContextualHelpToPane(pane), 150);
  };
  console.debug('%c✅ Sprint 20: UX — Onboarding, Docs, Tiers, Simple Mode, Profile, Tour', 'color:#4cc98a;font-weight:bold');
})();

// Update profile button name when profile loads (FIX F: wrapped in try/catch)
window.addEventListener('load', async () => {
  try {
    await new Promise(r=>setTimeout(r,600));
    const p = await fetch('/api/profile').then(r=>r.ok?r.json():null).catch(()=>null);
    if (p?.name) {
      const btn = document.getElementById('profile-btn-name');
      if (btn) btn.textContent = p.name.split(' ')[0];
    }
  } catch(e) {
    // Non-critical — button stays as default 'Me'
  }
});

// Keyboard shortcut to open profile
document.addEventListener('keydown', (e) => {
  if ((e.metaKey||e.ctrlKey) && e.shiftKey && e.key==='I') { e.preventDefault(); showUserProfile(); }
  if ((e.metaKey||e.ctrlKey) && e.key==='/' ) { e.preventDefault(); nav('docs'); }
});

