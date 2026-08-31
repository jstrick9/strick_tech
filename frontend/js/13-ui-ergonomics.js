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
    'imagegen': { icon: '🎨', title: 'Image Generator', desc: 'AI image generation, Figma import, style transfer, and asset library management' },
    'prompts': { icon: '💡', title: 'Prompt Library', desc: 'Save, organize, and reuse your best AI prompts' },
    'docs': { icon: '📖', title: 'Docs & Help', desc: 'Quick-starts, guides, FAQ, and keyboard shortcuts' },
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
    'supervisor': { icon: '🎯', title: 'Supervisor', desc: 'Autonomous goal DAG execution with multi-agent swarm' },
    'goals': { icon: '🎯', title: 'Goals', desc: 'Strategic objective tracking and milestone planning' },
    'connectors': { icon: '🔗', title: 'Integrations', desc: 'External system integrations and API connectors' },
    'mcp-gateway': { icon: '🚪', title: 'Gateway', desc: 'MCP gateway routing and protocol bridging' },
    'collabedit': { icon: '✍️', title: 'Collab Edit', desc: 'Real-time CRDT Operational Transformation rooms' }
  };

  // ── Novice-friendly additions (2026-08) ─────────────────────────────────────
  // 'icm' is the personal knowledge-base pane. It was missing from the metadata
  // table, so its breadcrumb fell back to a raw "ICM", and its sidebar item was
  // confusingly labelled "Workspaces" (colliding with the code-project
  // "Workspaces" pane). Give it a real title so the top bar and the sidebar agree.
  PANE_METADATA['icm'] = {
    icon: '🗂',
    title: 'Knowledge',
    desc: 'Your personal knowledge base — notes, files & folders',
  };

  // Plain-language "what does this do?" sentences for the help affordance.
  // Kept separate from `desc` (which is technical) so a novice gets a human line.
  const NOVICE_WHAT = {
    chat: 'Talk to your AI here — it’s the place to start. Ask a question, give it a doc, or paste anything.',
    studio: 'Write a small app or webpage and see it run live on the right, with AI help.',
    templates: 'Start from a ready-made project instead of a blank screen.',
    swarm: 'Have several AI agents work on a question at once and then compare answers.',
    galaxy: 'Everything the AI remembers about your work lives here — search it, add to it.',
    icm: 'A tidy place for your notes and files. The Inbox drops things here and files them for you.',
    inbox: 'Throw anything in here and it gets sorted. “Capture anything — the router files it.”',
    kanban: 'Your to-do board. Create a task, assign it to an agent, and track it to done.',
    settings: 'Connect an AI model (paste one key) and choose colors, sizes and how things behave.',
    websearch: 'Search the real web. Unlike chat, it looks things up first and cites every source.',
    browser: 'Let an agent open a website, take a screenshot, and fill things in for you.',
    imagegen: 'Create images from a description, or restyle one you already have.',
    prompts: 'Save your best instructions to reuse instead of retyping them.',
    terminal: 'Run commands on your own machine from inside the app.',
    hierarchy: 'Rules and background about you that every AI agent follows.',
    docs: 'Guides, answers and keyboard shortcuts for the whole app.',
    composer: 'Write long documents (reports, emails, drafts) with AI help, file by file.',
    workflow: 'Chain a few AI steps together and run them as one repeatable process.',
    github: 'Connect your code repositories and let AI read, write and commit to them.',
    dbstudio: 'Look at and edit the data stored in your app (a database viewer).',
    workspaces: 'Your code projects — each one keeps its own files and can be exported.',
    plugins: 'Install extra abilities and skill packs to add to the app.',
    mcp: 'Hook up outside tools and services so your agents can use them.',
    observability: 'Watch what your agents are doing and have done, live.',
    evals: 'Test how good your AI answers are and compare them.',
    secrets: 'Securely store API keys and passwords the agents can use.',
  };

  // Hover tooltips for the collapsed advanced nav items. CSS drives [data-tooltip],
  // so setting the dataset is all that is needed. Core items already carry theirs.
  const NAV_TOOLTIPS = {
    supervisor: 'Let AI run multi-step jobs for you',
    websearch: 'Search the web, with cited sources',
    browser: 'Let an agent browse the web for you',
    imagegen: 'Generate images with AI',
    prompts: 'Save & reuse your best prompts',
    terminal: 'Run commands in your workspace',
    hierarchy: 'Set rules your agents follow',
    docs: 'Guides & help for every feature',
    composer: 'Write long documents with AI',
    workflow: 'Chain AI steps into workflows',
    github: 'Connect your code repositories',
    dbstudio: 'Browse and edit your data',
    workspaces: 'Your code project workspaces',
    plugins: 'Install add-on packs',
    mcp: 'Hook up outside services & tools',
    observability: 'Watch what your agents do',
    evals: 'Test how well your AI answers',
    secrets: 'Store keys & secrets securely',
  };


  // ── Contextual Breadcrumb Hook ──────────────────────────────────────────────
  const origNav = window.nav;
  if (typeof origNav === 'function') {
    // intentional-override: wraps core nav to add ergonomics behaviour
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
    paneEl.innerHTML = `<span class="u-433de30b">${meta.icon}</span> <span>${escHtml(meta.title)}</span>`;
    renderPaneHelp(pane, meta);

    // Dynamic sub-context summaries
    if (pane === 'hierarchy') {
      subEl.innerHTML = '<span style="color:var(--accent-text)">Active:</span> Universal Context & IVREN Deltas';
    } else if (pane === 'studio') {
      // MODULE MERGE: 'builder' (Code Editor) retired and folded into
      // 'studio' — nav('builder') redirects here, so this branch never
      // needs to special-case the old id anymore.
      subEl.innerHTML = '<span style="color:var(--success)">● Live Preview Sandbox:</span> index.html / app.js';
    } else if (pane === 'chat') {
      subEl.innerHTML = '<span style="color:var(--accent-text)">Engine:</span> Multi-Agent Streaming + Information Hierarchy';
    } else if (pane === 'swarm') {
      subEl.innerHTML = '<span style="color:var(--accent-text)">Active:</span> Parallel Agent Fan-Out & AI Judge Consensus';
    } else if (pane === 'galaxy') {
      subEl.innerHTML = '<span style="color:var(--accent-text)">Storage:</span> SQLite FTS5 + Qdrant Vector Embeddings';
    } else if (pane === 'control') {
      subEl.innerHTML = '<span style="color:var(--warning)">Control Tower:</span> Live Execution Traces & HITL Approval Queue';
    } else {
      // BUG FIX: opacity:.8 on 11.5px --text-3 computed to #7b7b7b on #171717
      // = 4.23:1, failing WCAG AA. opacity is invisible to a token-level
      // contrast audit: it silently multiplies whatever ratio the token
      // achieved, so a token that passes on its own can still fail on screen.
      // --text-3 is already tuned for this surface; it needs no dimming.
      subEl.innerHTML = meta.desc ? `<span>${escHtml(meta.desc)}</span>` : '';
    }
  }

  // ── "What is this?" help affordance ────────────────────────────────────────
  let _helpBtn = null;
  let _helpPop = null;
  let _setupBtn = null;

  function ensureHelpElements() {
    const bar = document.getElementById('sticky-breadcrumb-bar');
    if (bar && !_helpBtn) {
      _helpBtn = document.createElement('button');
      _helpBtn.type = 'button';
      _helpBtn.id = 'pane-help-btn';
      _helpBtn.setAttribute('aria-label', 'What does this do?');
      _helpBtn.setAttribute('title', 'What does this do?');
      _helpBtn.style.cssText = 'margin-left:auto;width:24px;height:24px;min-width:24px;border-radius:50%;border:1px solid var(--border);background:transparent;color:var(--text-2);font-size:12px;font-weight:700;cursor:pointer;display:inline-flex;align-items:center;justify-content:center;line-height:1;flex:none';
      _helpBtn.textContent = '?';
      _helpBtn.addEventListener('click', (ev) => {
        ev.stopPropagation();
        if (_helpPop) _helpPop.style.display = (_helpPop.style.display === 'block') ? 'none' : 'block';
      });
      bar.appendChild(_helpBtn);

      _helpPop = document.createElement('div');
      _helpPop.id = 'pane-help-popover';
      _helpPop.setAttribute('role', 'tooltip');
      _helpPop.style.cssText = 'position:fixed;z-index:9999;max-width:340px;background:var(--bg-2);color:var(--text-0);border:1px solid var(--border);border-radius:10px;padding:12px 14px;font-size:12.5px;line-height:1.5;box-shadow:0 10px 30px rgba(0,0,0,.5);display:none';
      document.body.appendChild(_helpPop);

      // Close on click elsewhere or Escape
      document.addEventListener('click', (ev) => {
        if (_helpPop && !_helpPop.contains(ev.target) && !(ev.target === _helpBtn)) {
          _helpPop.style.display = 'none';
        }
      });
      document.addEventListener('keydown', (ev) => {
        if (ev.key === 'Escape' && _helpPop) _helpPop.style.display = 'none';
      });

      // ── "Setup AI" one-time nudge ──────────────────────────────────────────
      // The Quick Setup modal (showQuickSetup) was never surfaced anywhere, so
      // a first-run novice had to hunt in Settings to connect a key. Put a small
      // CTA in the top bar that opens it. It auto-hides once an AI connection is
      // ready (cloud key or local models).
      _setupBtn = document.createElement('button');
      _setupBtn.type = 'button';
      _setupBtn.id = 'top-setup-btn';
      _setupBtn.setAttribute('aria-label', 'Set up your AI');
      _setupBtn.textContent = '✨ Setup AI';
      _setupBtn.style.cssText = 'flex:none;font-size:11.5px;font-weight:700;padding:4px 10px;border-radius:8px;border:1px solid var(--accent);color:var(--accent-text);background:transparent;cursor:pointer';
      _setupBtn.addEventListener('click', (ev) => {
        ev.stopPropagation();
        if (window.showQuickSetup) window.showQuickSetup();
        else if (window.nav) window.nav('settings');
      });
      bar.appendChild(_setupBtn);

      const _origReadiness = window.renderConnectionReadiness;
      if (typeof _origReadiness === 'function') {
        // intentional-override: wraps the core readiness signal so the Setup AI
        // nudge auto-hides once a cloud key or local model is genuinely ready.
        window.renderConnectionReadiness = function(readiness = {}) {
          _origReadiness.apply(this, arguments);
          if (_setupBtn) {
            _setupBtn.style.display =
              (readiness.cloudReady || Number(readiness.localModels) > 0) ? 'none' : '';
          }
        };
      }
    }
    return Boolean(_helpBtn && _helpPop);
  }

  function renderPaneHelp(pane, meta) {
    const paneEl = document.getElementById('breadcrumb-current-pane');
    if (!paneEl) return;
    if (!ensureHelpElements()) return;
    const what = NOVICE_WHAT[pane] || meta.desc || '';
    _helpPop.innerHTML =
      `<div style="font-weight:800;margin-bottom:6px;display:flex;gap:6px;align-items:center">${meta.icon || '🧭'} ${escHtml(meta.title || pane)}</div>` +
      `<div style="color:var(--text-1)">${escHtml(what)}</div>`;
  }

  // Attach plain-language hover tooltips to collapsed nav items by id.
  function applyNavTooltips() {
    document.querySelectorAll('.nav-item[data-nav]').forEach((el) => {
      const id = el.getAttribute('data-nav');
      const tip = NAV_TOOLTIPS[id] || NOVICE_WHAT[id];
      if (tip && !el.dataset.tooltip) el.dataset.tooltip = tip;
    });
  }

  // Hook sub-tab changes inside Hierarchy for real-time breadcrumb updates
  const origSwitchTab = window.switchHierarchyTab;
  if (typeof origSwitchTab === 'function') {
    // intentional-override: wraps switchHierarchyTab to persist the active tab
    window.switchHierarchyTab = function(tab) {
      origSwitchTab.apply(this, arguments);
      const subEl = document.getElementById('breadcrumb-sub-context');
      if (subEl) {
        subEl.innerHTML = tab === 'tier1' 
          ? '<span style="color:var(--accent-text)">Tier 1:</span> Universal Business Context (4 Core Manuals)'
          : '<span style="color:var(--accent-text)">Tier 2:</span> Project IVREN Subfolders & Compounding Notes';
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
  const initErgonomics = () => {
    applyNavTooltips();
    updateBreadcrumbBar(location.hash ? location.hash.slice(2) : 'chat');
  };
  if (document.readyState === 'loading') {
    document.addEventListener('DOMContentLoaded', initErgonomics);
  } else {
    setTimeout(initErgonomics, 100);
  }

  console.debug('%c✅ UI Ergonomics Engine loaded (Breadcrumb Bar + High Contrast)', 'color:#3b82f6;font-weight:bold');
})();
