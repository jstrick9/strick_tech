/*
 * Agentic OS — UI Ergonomics & Customization Engine (frontend/js/13-ui-ergonomics.js)
 * Implements Phase A: Drag-and-Drop Sidebar Pinning (`⭐ Pin to Core`) & Sticky Contextual Breadcrumb Bar.
 */
(function() {
  'use strict';

  const PINNED_STORAGE_KEY = 'agentic_os_pinned_panes';
  const ORDER_STORAGE_KEY = 'agentic_os_core_order';

  const PANE_METADATA = {
    'chat': { icon: '💬', title: 'Chat', desc: 'Multi-agent streaming conversations' },
    'studio': { icon: '🎬', title: 'Studio', desc: 'Live HTML/JS/Py code editor & instant preview' },
    'templates': { icon: '🎨', title: 'Templates', desc: 'Starter application templates' },
    'swarm': { icon: '🌀', title: 'Swarm', desc: 'Parallel multi-agent fan-out with AI judge synthesis' },
    'galaxy': { icon: '🌌', title: 'Memory', desc: '3D semantic vector knowledge graph' },
    'hierarchy': { icon: '🧭', title: 'Hierarchy', desc: '2-Tier AI Operating Manual (Universal Context + IVREN)' },
    'kanban': { icon: '📋', title: 'Kanban', desc: 'Task workflow board' },
    'settings': { icon: '⚙️', title: 'Settings', desc: 'System configuration & API keys' },
    'builder': { icon: '📝', title: 'Editor', desc: 'Advanced code builder' },
    'composer': { icon: '🪄', title: 'Composer', desc: 'Multi-file refactoring engine' },
    'pipeline': { icon: '🏛️', title: 'Pipeline', desc: 'Sequential agent workflow runs' },
    'skills': { icon: '⚡', title: 'Skills', desc: 'Agent capabilities & tool definitions' },
    'loops': { icon: '♾️', title: 'Loops', desc: 'Autonomous background agent tasks (`APScheduler`)' },
    'mcp': { icon: '🔧', title: 'MCP Tools', desc: 'Model Context Protocol tool router (`filesystem, browser, git, shell`)' },
    'fusion': { icon: '🔀', title: 'Fusion', desc: 'Multi-model consensus weighting & synthesis' },
    'arena': { icon: '⚔️', title: 'Arena', desc: 'Blind A/B prompt battles & ELO model leaderboard' },
    'github': { icon: '🐙', title: 'GitHub', desc: 'Repository issue/PR automation & code sync' },
    'deploy': { icon: '🚀', title: 'Deploy', desc: 'One-click Vercel, Netlify, Railway & native Tauri bundling' },
    'dbstudio': { icon: '🗄️', title: 'Database', desc: 'SQLite & Qdrant table schema inspector' },
    'dashboard': { icon: '📊', title: 'Dashboard', desc: 'Real-time platform metrics & active status' },
    'plugins': { icon: '🧩', title: 'Plugins', desc: 'Marketplace skill packs & custom connectors' },
    'terminal': { icon: '💻', title: 'Terminal', desc: 'Sandboxed shell & background job controller' },
    'secrets': { icon: '🔐', title: 'Vault', desc: 'Fernet AES-256 encrypted secrets management' },
    'system': { icon: '💻', title: 'System', desc: 'CPU, RAM, disk telemetry & HMR file watcher' },
    'workspaces': { icon: '📁', title: 'Workspaces', desc: 'Project isolation & ZIP snapshot exports' },
    'workflow': { icon: '🗺️', title: 'Workflows', desc: 'Visual DAG node dependency sorting' },
    'specs': { icon: '📋', title: 'Spec Builder', desc: 'Spec-Driven Workflow (`SDW`) requirement validation' },
    'steering': { icon: '🧭', title: 'Steering', desc: 'Dynamic in-flight prompt steering rules' },
    'bugbot': { icon: '🐛', title: 'BugBot', desc: 'Autonomous bug reproduction & patch verification' },
    'gitai': { icon: '🌿', title: 'Git AI', desc: 'AI commit generator & diff analysis' },
    'marketplace': { icon: '🛒', title: 'Marketplace', desc: 'Curated & community skill packs with 1-5 star ratings' },
    'replay': { icon: '⏮️', title: 'Replay', desc: 'Time-travel step scrubbing & execution frame deltas' },
    'collabedit': { icon: '✍️', title: 'Collab Edit', desc: 'Real-time CRDT Operational Transformation rooms' }
  };

  function getPinnedPanes() {
    try {
      return JSON.parse(localStorage.getItem(PINNED_STORAGE_KEY) || '[]');
    } catch(e) { return []; }
  }

  function savePinnedPanes(list) {
    try {
      localStorage.setItem(PINNED_STORAGE_KEY, JSON.stringify(list));
    } catch(e) {}
  }

  function getCoreOrder() {
    try {
      return JSON.parse(localStorage.getItem(ORDER_STORAGE_KEY) || '[]');
    } catch(e) { return []; }
  }

  function saveCoreOrder(list) {
    try {
      localStorage.setItem(ORDER_STORAGE_KEY, JSON.stringify(list));
    } catch(e) {}
  }

  window.togglePinNav = function(evt, navId) {
    if (evt) { evt.stopPropagation(); evt.preventDefault(); }
    let list = getPinnedPanes();
    if (list.includes(navId)) {
      list = list.filter(id => id !== navId);
      if (window.toast) toast(`📌 Unpinned '${PANE_METADATA[navId]?.title || navId}' from Core sidebar`, 'ok', 2500);
    } else {
      list.push(navId);
      if (window.toast) toast(`⭐ Pinned '${PANE_METADATA[navId]?.title || navId}' to Core sidebar!`, 'ok', 2500);
    }
    savePinnedPanes(list);
    renderSidebarErgonomics();
  };

  window.resetCoreOrder = function(evt) {
    if (evt) { evt.stopPropagation(); evt.preventDefault(); }
    localStorage.removeItem(ORDER_STORAGE_KEY);
    localStorage.removeItem(PINNED_STORAGE_KEY);
    if (window.toast) toast('🔄 Restored default Core navigation layout and unpinned custom items', 'ok', 3000);
    location.reload();
  };

  function renderSidebarErgonomics() {
    const scrollEl = document.querySelector('#sidebar .sidebar-scroll');
    if (!scrollEl) return;

    // 1. Inject star buttons onto all advanced items if not already present
    document.querySelectorAll('.nav-item[data-tier="advanced"]').forEach(el => {
      if (!el.querySelector('.pin-star-btn')) {
        const navId = el.getAttribute('data-nav');
        const star = document.createElement('span');
        star.className = 'pin-star-btn';
        star.style.cssText = 'margin-left:auto;cursor:pointer;font-size:12px;opacity:0.4;transition:opacity 0.15s;padding:0 4px';
        star.title = 'Pin to Core sidebar';
        star.innerHTML = '⭐';
        star.onmouseover = () => star.style.opacity = '1';
        star.onmouseout = () => star.style.opacity = '0.4';
        star.onclick = (e) => window.togglePinNav(e, navId);
        el.appendChild(star);
      }
    });

    // 2. Remove old dynamically rendered pinned items
    document.querySelectorAll('.pinned-core-item, .nav-reset-bar').forEach(el => el.remove());

    const pinned = getPinnedPanes();
    const advToggle = document.getElementById('advanced-toggle');
    if (!advToggle) return;

    // 3. Render pinned advanced items above advanced-toggle
    pinned.forEach(navId => {
      const meta = PANE_METADATA[navId] || { icon: '📌', title: navId, desc: '' };
      const el = document.createElement('div');
      el.className = 'nav-item pinned-core-item';
      el.setAttribute('data-nav', navId);
      el.setAttribute('data-tier', 'core');
      el.setAttribute('role', 'menuitem');
      el.setAttribute('aria-label', meta.title);
      el.setAttribute('draggable', 'true');
      el.onclick = () => window.nav(navId);
      el.innerHTML = `
        <span class="icon">${meta.icon}</span>
        <span class="label">${meta.title}</span>
        <span onclick="togglePinNav(event, '${navId}')" title="Unpin from Core" style="margin-left:auto;cursor:pointer;font-size:11px;opacity:.7;color:var(--danger)">📌</span>
      `;
      scrollEl.insertBefore(el, advToggle);
    });

    // 4. Render reset bar if any items pinned or ordered
    const order = getCoreOrder();
    if (pinned.length > 0 || order.length > 0) {
      const resetBar = document.createElement('div');
      resetBar.className = 'nav-reset-bar';
      resetBar.style.cssText = 'padding:6px 12px;font-size:10.5px;color:var(--text-3);text-align:center;cursor:pointer;border-top:1px solid var(--border);margin-bottom:6px;transition:color 0.15s';
      resetBar.innerHTML = '🔄 Reset Core Layout';
      resetBar.onmouseover = () => resetBar.style.color = 'var(--accent)';
      resetBar.onmouseout = () => resetBar.style.color = 'var(--text-3)';
      resetBar.onclick = window.resetCoreOrder;
      scrollEl.insertBefore(resetBar, advToggle);
    }

    // 5. Apply drag and drop reordering
    setupDragAndDrop(scrollEl, advToggle);

    // 6. Highlight active nav
    const activeNav = location.hash ? location.hash.slice(2) : 'chat';
    document.querySelectorAll('.nav-item').forEach(n => {
      n.classList.toggle('active', n.getAttribute('data-nav') === activeNav);
    });
  }

  let draggedItem = null;
  function setupDragAndDrop(scrollEl, advToggle) {
    const coreItems = Array.from(scrollEl.querySelectorAll('.nav-item[data-tier="core"], .pinned-core-item'));
    coreItems.forEach(el => {
      el.setAttribute('draggable', 'true');
      el.ondragstart = function(e) {
        draggedItem = this;
        e.dataTransfer.effectAllowed = 'move';
        this.style.opacity = '0.5';
      };
      el.ondragend = function(e) {
        this.style.opacity = '1';
        draggedItem = null;
      };
      el.ondragover = function(e) {
        e.preventDefault();
        e.dataTransfer.dropEffect = 'move';
        this.style.borderTop = '2px solid var(--accent)';
      };
      el.ondragleave = function(e) {
        this.style.borderTop = '';
      };
      el.ondrop = function(e) {
        e.preventDefault();
        this.style.borderTop = '';
        if (draggedItem && draggedItem !== this) {
          scrollEl.insertBefore(draggedItem, this);
          saveCurrentNavOrder(scrollEl, advToggle);
        }
      };
    });

    // Apply saved order on load
    const savedOrder = getCoreOrder();
    if (savedOrder.length > 0) {
      savedOrder.forEach(navId => {
        const item = scrollEl.querySelector(`.nav-item[data-nav="${navId}"][data-tier="core"], .pinned-core-item[data-nav="${navId}"]`);
        if (item && advToggle) {
          scrollEl.insertBefore(item, advToggle);
        }
      });
    }
  }

  function saveCurrentNavOrder(scrollEl, advToggle) {
    const items = Array.from(scrollEl.querySelectorAll('.nav-item[data-tier="core"], .pinned-core-item'));
    const order = items.map(i => i.getAttribute('data-nav')).filter(Boolean);
    saveCoreOrder(order);
    if (window.toast) toast('📌 Sidebar order saved!', 'ok', 1500);
  }

  // ── Contextual Breadcrumb Hook ──────────────────────────────────────────────
  const origNav = window.nav;
  if (typeof origNav === 'function') {
    window.nav = function(pane) {
      origNav.apply(this, arguments);
      updateBreadcrumbBar(pane);
    };
  }

  function updateBreadcrumbBar(pane) {
    const paneEl = document.getElementById('breadcrumb-current-pane');
    const subEl = document.getElementById('breadcrumb-sub-context');
    if (!paneEl || !subEl) return;

    const meta = PANE_METADATA[pane] || { icon: '🧭', title: pane.toUpperCase(), desc: '' };
    paneEl.innerHTML = `<span style="font-size:14px">${meta.icon}</span> <span>${escHtml(meta.title)}</span>`;

    // Dynamic sub-context summaries
    if (pane === 'hierarchy') {
      subEl.innerHTML = '<span style="color:var(--accent)">Active:</span> Universal Context & IVREN Deltas';
    } else if (pane === 'studio' || pane === 'builder') {
      subEl.innerHTML = '<span style="color:var(--success)">● Live Preview Sandbox:</span> index.html / app.js';
    } else if (pane === 'chat') {
      subEl.innerHTML = '<span style="color:var(--accent)">Engine:</span> Multi-Agent Streaming + Information Hierarchy';
    } else if (pane === 'swarm') {
      subEl.innerHTML = '<span style="color:var(--accent)">Active:</span> Parallel Agent Fan-Out & AI Judge Consensus';
    } else if (pane === 'galaxy') {
      subEl.innerHTML = '<span style="color:var(--accent)">Storage:</span> SQLite FTS5 + Qdrant Vector Embeddings';
    } else if (pane === 'control') {
      subEl.innerHTML = '<span style="color:var(--warning)">Control Tower:</span> Live Execution Traces & HITL Approval Queue';
    } else {
      subEl.innerHTML = meta.desc ? `<span style="opacity:.8">${escHtml(meta.desc)}</span>` : '';
    }
  }

  // Hook sub-tab changes inside Hierarchy for real-time breadcrumb updates
  const origSwitchTab = window.switchHierarchyTab;
  if (typeof origSwitchTab === 'function') {
    window.switchHierarchyTab = function(tab) {
      origSwitchTab.apply(this, arguments);
      const subEl = document.getElementById('breadcrumb-sub-context');
      if (subEl) {
        subEl.innerHTML = tab === 'tier1' 
          ? '<span style="color:var(--accent)">Tier 1:</span> Universal Business Context (4 Core Manuals)'
          : '<span style="color:var(--accent)">Tier 2:</span> Project IVREN Subfolders & Compounding Notes';
      }
    };
  }

  window.toggleHighContrastTheme = function() {
    const isHighContrast = document.body.classList.toggle('theme-high-contrast');
    try { localStorage.setItem('agentic_os_high_contrast', isHighContrast ? 'true' : 'false'); } catch(e) {}
    const btn = document.getElementById('high-contrast-toggle-btn');
    if (btn) {
      btn.textContent = isHighContrast ? 'Disable High Contrast' : 'Enable High Contrast';
      btn.classList.toggle('btn-primary', isHighContrast);
    }
    if (window.toast) toast(isHighContrast ? '♿ High-Contrast WCAG AAA theme active!' : 'Restored standard dark theme', 'ok', 2000);
  };

  // Restore on load
  try {
    if (localStorage.getItem('agentic_os_high_contrast') === 'true') {
      document.body.classList.add('theme-high-contrast');
      setTimeout(() => {
        const btn = document.getElementById('high-contrast-toggle-btn');
        if (btn) { btn.textContent = 'Disable High Contrast'; btn.classList.add('btn-primary'); }
      }, 500);
    }
  } catch(e) {}

  // Initial render after DOM loaded
  if (document.readyState === 'loading') {
    document.addEventListener('DOMContentLoaded', () => {
      renderSidebarErgonomics();
      updateBreadcrumbBar(location.hash ? location.hash.slice(2) : 'chat');
    });
  } else {
    setTimeout(() => {
      renderSidebarErgonomics();
      updateBreadcrumbBar(location.hash ? location.hash.slice(2) : 'chat');
    }, 100);
  }

  console.log('%c✅ UI Ergonomics Engine loaded (Phase A: Drag-and-Drop Pinning + Sticky Breadcrumb Bar)', 'color:#3b82f6;font-weight:bold');
})();
