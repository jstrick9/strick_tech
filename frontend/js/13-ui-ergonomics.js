/*
 * Agentic OS — UI Ergonomics & Customization Engine (frontend/js/13-ui-ergonomics.js)
 * Contextual Breadcrumb Bar & High Contrast Theme
 */
(function() {
  'use strict';

  // Safe localStorage wrapper
  const _safeLS = {
    get: (k) => { try { return localStorage.getItem(k); } catch { return null; } },
    set: (k, v) => { try { localStorage.setItem(k, v); } catch {} },
    rm: (k) => { try { localStorage.removeItem(k); } catch {} },
  };

  const PANE_METADATA = {
    'chat': { icon: '💬', title: 'Chat', desc: 'Multi-agent streaming conversations' },
    'studio': { icon: '🎬', title: 'Studio', desc: 'Live HTML/JS/Py code editor & instant preview' },
    'templates': { icon: '🎨', title: 'Templates', desc: 'Starter application templates' },
    'swarm': { icon: '🌀', title: 'Swarm', desc: 'Parallel multi-agent fan-out with AI judge synthesis' },
    'galaxy': { icon: '🌌', title: 'Memory', desc: '3D semantic vector knowledge graph' },
    'hierarchy': { icon: '🧭', title: 'AI Context & Guidelines', desc: 'Universal business context, project deltas, and coding/steering rules injected into every AI call' },
    'kanban': { icon: '📋', title: 'Kanban', desc: 'Task workflow board' },
    'settings': { icon: '⚙️', title: 'Settings', desc: 'System configuration & API keys' },
    'websearch': { icon: '🔎', title: 'Web Search', desc: 'Grounded AI answers, raw search, and deep research with live web citations' },
    'browser': { icon: '🌐', title: 'Browser Agent', desc: 'Autonomous Playwright-driven browser tasks, screenshots, and session history' },
    // MODULE MERGE: 'builder' (Code Editor) retired and folded into
    // 'studio' (Code Studio) — nav('builder') redirects to nav('studio')
    // so this pane id no longer appears in the breadcrumb bar directly.
    'composer': { icon: '🪄', title: 'Composer', desc: 'Multi-file refactoring engine' },
    'pipeline': { icon: '🏛️', title: 'Pipeline', desc: 'Sequential agent workflow runs' },
    'skills': { icon: '⚡', title: 'Skills', desc: 'Agent capabilities & tool definitions' },
    'loops': { icon: '♾️', title: 'Loops', desc: 'Autonomous background agent tasks' },
    'mcp': { icon: '🔧', title: 'MCP Tools', desc: 'Model Context Protocol tool router' },
    'fusion': { icon: '🔀', title: 'Fusion', desc: 'Multi-model consensus weighting & synthesis' },
    'arena': { icon: '⚔️', title: 'Arena', desc: 'Blind A/B prompt battles & ELO model leaderboard' },
    'github': { icon: '🐙', title: 'GitHub', desc: 'Repository issue/PR automation & code sync' },
    'deploy': { icon: '🚀', title: 'Deploy', desc: 'One-click deployment & native Tauri bundling' },
    'dbstudio': { icon: '🗄️', title: 'Database', desc: 'SQLite & Qdrant table schema inspector' },
    'dashboard': { icon: '📊', title: 'Dashboard', desc: 'Real-time platform metrics & active status' },
    'plugins': { icon: '🧩', title: 'Plugins', desc: 'Marketplace skill packs & custom connectors' },
    'terminal': { icon: '💻', title: 'Terminal', desc: 'Sandboxed shell & background job controller' },
    'secrets': { icon: '🔐', title: 'Vault', desc: 'Fernet AES-256 encrypted secrets management' },
    'system': { icon: '💻', title: 'System', desc: 'CPU, RAM, disk telemetry & HMR file watcher' },
    'workspaces': { icon: '📁', title: 'Workspaces', desc: 'Project isolation & ZIP snapshot exports' },
    'workflow': { icon: '🗺️', title: 'Workflows', desc: 'Visual DAG node dependency sorting' },
    'specs': { icon: '📋', title: 'Spec Builder', desc: 'Spec-Driven Workflow requirement validation' },
    'bugbot': { icon: '🐛', title: 'BugBot', desc: 'Autonomous bug reproduction & patch verification' },
    'gitai': { icon: '🌿', title: 'Git AI', desc: 'AI commit generator & diff analysis' },
    'marketplace': { icon: '🛒', title: 'Marketplace', desc: 'Curated & community skill packs' },
    'replay': { icon: '⏮️', title: 'Replay', desc: 'Time-travel step scrubbing & execution frame deltas' },
    'collabedit': { icon: '✍️', title: 'Collab Edit', desc: 'Real-time CRDT Operational Transformation rooms' }
  };

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
    } else if (pane === 'studio') {
      // MODULE MERGE: 'builder' (Code Editor) retired and folded into
      // 'studio' — nav('builder') redirects here, so this branch never
      // needs to special-case the old id anymore.
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
    try { try { _safeLS.set('agentic_os_high_contrast', isHighContrast ? 'true' : 'false'); } catch {} } catch(e) {}
    const btn = document.getElementById('high-contrast-toggle-btn');
    if (btn) {
      btn.textContent = isHighContrast ? 'Disable High Contrast' : 'Enable High Contrast';
      btn.classList.toggle('btn-primary', isHighContrast);
    }
    if (window.toast) toast(isHighContrast ? '♿ High-Contrast WCAG AAA theme active!' : 'Restored standard dark theme', 'ok', 2000);
  };

  // Restore on load
  try {
    if (_safeLS.get('agentic_os_high_contrast') === 'true') {
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
      updateBreadcrumbBar(location.hash ? location.hash.slice(2) : 'chat');
    });
  } else {
    setTimeout(() => {
      updateBreadcrumbBar(location.hash ? location.hash.slice(2) : 'chat');
    }, 100);
  }

  console.debug('%c✅ UI Ergonomics Engine loaded (Breadcrumb Bar + High Contrast)', 'color:#3b82f6;font-weight:bold');
})();
