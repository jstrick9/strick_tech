// Agentic OS v6.0 — Studio — Monaco editor, live preview, file management
// Extracted from index.html (block 1)


// ═══════════════════════════════════════════════════════════════
// MASTER NAV DISPATCHER comment (duplicate removed by S11 audit)
// ═══════════════════════════════════════════════════════════════

// ═══════════════════════════════════════════════════════════════
//  SPRINT 11 — Competitive Feature Parity + Polish
//  Global search, tour, quick actions, model switcher, UX polish
// ═══════════════════════════════════════════════════════════════

// ── 1. Enhanced Global Search (⌘K already exists, enhance it) ────
// Add file + memory search to the command palette
async function enhanceCommandPalette() {
  // Add memory search to palette items dynamically  
  if (typeof PALETTE_CMDS === 'undefined') return;
  
  // Add smart search that queries memory and files
  const originalFilterPalette = window.filterPalette;
  window.filterPalette = async function() {
    if (typeof originalFilterPalette === 'function') originalFilterPalette();
    const q = document.getElementById('palette-input')?.value?.trim();
    if (!q || q.length < 2) return;
    
    // Add memory results
    try {
      const r = await fetch(`/api/memory/search?q=${encodeURIComponent(q)}&limit=3`);
      if (!r.ok) return;
      const memories = await r.json();
      if (Array.isArray(memories) && memories.length) {
        const results = document.getElementById('palette-results');
        if (!results) return;
        const section = document.createElement('div');
        section.innerHTML = `<div class="palette-section">🌌 Memory Results</div>` +
          memories.map(m => `<div class="palette-item" onclick="insertCmd('Tell me about: '+${JSON.stringify((m.content||'').slice(0,50))});closePalette()">
            <span class="p-icon">💾</span>
            <span class="p-label" style="font-size:12px">${escHtml((m.content||'').slice(0,60))}…</span>
            <span class="p-desc">${escHtml(m.source||'')}</span>
          </div>`).join('');
        results.appendChild(section);
      }
    } catch(e) {}
  };
}
setTimeout(enhanceCommandPalette, 2000);

// ── 2. Feature Tour System ─────────────────────────────────────
let tourStep = 0;
const TOUR_STEPS = [
  {
    target: '[data-nav="chat"]',
    title: '💬 Chat with AI Agents',
    body: 'Start here. Type any question, use /commands like /goal or /code, or click an agent to switch who responds.',
    position: 'right'
  },
  {
    target: '[data-nav="studio"]',
    title: '🎬 Live Studio',
    body: 'Build apps with a split Editor + Live Preview. Changes save automatically and the preview updates in real-time.',
    position: 'right'
  },
  {
    target: '[data-nav="templates"]',
    title: '🎨 Start with Templates',
    body: '14 production-ready templates. SaaS landing pages, dashboards, todo apps, portfolios — one click to scaffold.',
    position: 'right'
  },
  {
    target: '[data-nav="swarm"]',
    title: '🌀 Multi-Agent Swarm',
    body: 'Send one prompt to multiple AI agents simultaneously. An AI judge picks the best response. 23% better quality.',
    position: 'right'
  },
  {
    target: '[data-nav="deploy"]',
    title: '🚀 One-Click Deploy',
    body: 'Deploy to Vercel, Netlify, Railway, GitHub Pages and more. Set your token once, deploy forever.',
    position: 'right'
  },
  {
    target: '[data-nav="control"]',
    title: '🎛️ Control Tower',
    body: 'Monitor every agent run live. Kill switch, budget guardrails, cost per step. The governance layer no other local platform has.',
    position: 'right'
  },
];

function startTour() {
  tourStep = 0;
  showTourStep();
}

function showTourStep() {
  // Remove existing tour popup
  document.getElementById('tour-popup')?.remove();
  if (tourStep >= TOUR_STEPS.length) {
    toast('✅ Tour complete! You know Agentic OS.', 'ok', 3000);
    return;
  }
  
  const step = TOUR_STEPS[tourStep];
  const target = document.querySelector(step.target);
  
  if (!target) { tourStep++; showTourStep(); return; }
  
  const rect = target.getBoundingClientRect();
  const popup = document.createElement('div');
  popup.id = 'tour-popup';
  popup.style.cssText = `
    position:fixed;z-index:99998;
    background:var(--bg-2);border:1px solid var(--accent);
    border-radius:var(--radius-lg);padding:16px 18px;
    box-shadow:0 16px 48px rgba(0,0,0,.7),0 0 0 9999px rgba(0,0,0,.3);
    max-width:280px;animation:scaleIn .2s ease;
    left:${rect.right + 16}px;
    top:${Math.max(8, rect.top - 20)}px;
  `;
  popup.innerHTML = `
    <div style="display:flex;align-items:flex-start;justify-content:space-between;gap:8px;margin-bottom:8px">
      <div style="font-size:14px;font-weight:700;color:var(--text-0)">${step.title}</div>
      <button onclick="document.getElementById('tour-popup')?.remove()" style="background:none;border:none;color:var(--text-3);cursor:pointer;font-size:16px;flex-shrink:0;padding:0">×</button>
    </div>
    <p style="font-size:12.5px;color:var(--text-2);line-height:1.6;margin-bottom:12px">${step.body}</p>
    <div style="display:flex;align-items:center;justify-content:space-between">
      <span style="font-size:11px;color:var(--text-3)">${tourStep + 1} / ${TOUR_STEPS.length}</span>
      <div style="display:flex;gap:6px">
        ${tourStep > 0 ? '<button onclick="tourStep--;showTourStep()" class="btn btn-ghost btn-sm">← Back</button>' : ''}
        <button onclick="tourStep++;showTourStep()" class="btn btn-primary btn-sm">${tourStep === TOUR_STEPS.length - 1 ? 'Finish ✓' : 'Next →'}</button>
      </div>
    </div>`;
  document.body.appendChild(popup);
  
  // Highlight target
  target.style.outline = '2px solid var(--accent)';
  target.style.outlineOffset = '2px';
  setTimeout(() => { target.style.outline = ''; target.style.outlineOffset = ''; }, 3000);
}

// Add tour to palette
if (typeof PALETTE_CMDS !== 'undefined') {
  PALETTE_CMDS.unshift({icon:'🎯', label:'Start Guided Tour', desc:'Learn Agentic OS in 6 steps', action:()=>startTour()});
}

// ── 3. Quick Action Bar (context-sensitive) ────────────────────
// Shows relevant actions based on current pane
const QUICK_ACTIONS = {
  chat:       [['💬 New Session','newSession()'],['🌀 Run Swarm',"nav('swarm')"],['⚡ Skills',"nav('skills')"]],
  studio:     [['⚡ Scaffold',"studioScaffold?.()"],['💾 Save',"studioSaveFile?.()"],['🧪 Test',"runE2EFull?.('web')"]],
  kanban:     [['＋ Task',"openNewTaskModal()"],['📋 Done',""],['♾️ Auto',"nav('loops')"]],
  dashboard:  [['⟳ Refresh',"renderDashboard?.()"],['📤 Export',"exportWorkspace?.('current')"]],
  github:     [['⬆ Push',"showGHPush?.()"],['⬇ Pull',"showGHPull?.()"],['🌐 Pages',"showGHPages?.()"]],
  deploy:     [['▲ Vercel',"doDeploy?.('vercel')"],['◈ Netlify',"doDeploy?.('netlify')"],['🌐 Pages',"showGHPages?.()"]],
  templates:  [['🎨 Gallery',"renderTemplates?.()"],['🚀 SaaS',"scaffoldTemplate?.('saas-landing')"]],
  composer:   [['🪄 Build',"runComposer?.()"],['📷 Screenshot',"document.getElementById('screenshot-file')?.click()"]],
  control:    [['🛑 Kill All',"killAllRuns?.()"],['＋ Rule',"addBudgetRule?.()"],['⟳ Refresh',"refreshControlTower?.()"]],
  workspaces: [['＋ Project',"createNewWorkspace?.()"],['📦 Export',"exportCurrentZip?.()"]],
  webhooks:   [['＋ Webhook',"createWebhook?.()"],['▶ Test',""]],
  testgen:    [['🧪 Generate',"generateTests?.()"]],
};

function showQuickActions(pane) {
  const actions = QUICK_ACTIONS[pane];
  const bar = document.getElementById('quick-action-bar');
  if (!bar) return;
  if (!actions || !actions.length) { bar.style.display = 'none'; return; }
  bar.style.display = 'flex';
  bar.innerHTML = `<span style="font-size:10px;color:var(--text-3);margin-right:4px;flex-shrink:0">Quick:</span>` +
    actions.map(([label, action]) =>
      action ? `<button onclick="${action}" class="chat-tool" style="font-size:11px;padding:3px 9px">${label}</button>` : ''
    ).join('');
}

// ── 4. Word/Token counter on chat input ───────────────────────
function addTokenCounter() {
  const inputArea = document.querySelector('.chat-input-area');
  if (!inputArea || document.getElementById('token-counter')) return;
  
  const counter = document.createElement('div');
  counter.id = 'token-counter';
  counter.style.cssText = 'font-size:10.5px;color:var(--text-3);text-align:right;margin-top:4px;padding:0 2px';
  counter.textContent = '0 tokens';
  inputArea.appendChild(counter);
  
  const input = document.getElementById('chat-input');
  if (input) {
    input.addEventListener('input', () => {
      const text = input.value;
      const words = text.trim() ? text.trim().split(/\s+/).length : 0;
      const tokens = Math.ceil(text.length / 4); // rough token estimate
      counter.textContent = tokens > 0 ? `~${tokens} tokens · ${words} words` : '';
      counter.style.color = tokens > 3000 ? 'var(--warning)' : tokens > 6000 ? 'var(--danger)' : 'var(--text-3)';
    });
  }
}
setTimeout(addTokenCounter, 1000);

// ── 5. Model switcher in topbar ───────────────────────────────
function addModelSwitcher() {
  const topbarActions = document.getElementById('topbar-actions');
  if (!topbarActions || document.getElementById('model-switcher')) return;
  
  const switcher = document.createElement('select');
  switcher.id = 'model-switcher';
  switcher.title = 'Switch AI model for current agent';
  switcher.style.cssText = `
    background:var(--bg-2);border:1px solid var(--border);border-radius:var(--radius-sm);
    color:var(--text-1);font-size:11px;padding:4px 7px;cursor:pointer;
    outline:none;transition:var(--transition);
  `;
  
  const models = [
    ['claude',       'Claude 3.5 Sonnet'],
    ['claude-opus',  'Claude Opus 4'],
    ['gpt4o',        'GPT-4o'],
    ['gemini',       'Gemini 2.5 Pro'],
    ['grok',         'Grok 3'],
    ['llama',        'Llama 3.3 (free)'],
    ['gemini-flash', 'Gemini Flash (free)'],
  ];
  
  switcher.innerHTML = models.map(([id, name]) => 
    `<option value="${id}">${name}</option>`
  ).join('');
  
  switcher.addEventListener('change', () => {
    const modelId = switcher.value;
    if (window.S?.currentAgent) {
      S.currentAgent.model = modelId;
      const badge = document.getElementById('active-model-badge');
      if (badge) badge.textContent = modelId;
      toast(`🤖 Model: ${models.find(m=>m[0]===modelId)?.[1]||modelId}`, 'ok', 1500);
    }
  });
  
  // Insert before settings button
  const settingsBtn = topbarActions.querySelector('[title="Settings (⌘,)"]') ||
                     topbarActions.querySelector('[onclick*="settings"]');
  if (settingsBtn) {
    topbarActions.insertBefore(switcher, settingsBtn);
  } else {
    topbarActions.prepend(switcher);
  }
}
setTimeout(addModelSwitcher, 1500);

// ── 6. Pane-specific quick action bar in topbar area ──────────
function addQuickActionBar() {
  const content = document.getElementById('content');
  if (!content || document.getElementById('quick-action-bar')) return;
  
  const bar = document.createElement('div');
  bar.id = 'quick-action-bar';
  bar.style.cssText = `
    height:32px;flex-shrink:0;
    display:none;align-items:center;gap:5px;
    padding:0 14px;border-bottom:1px solid var(--border);
    background:var(--bg-1);overflow-x:auto;
  `;
  content.insertBefore(bar, content.firstChild);
}
setTimeout(addQuickActionBar, 500);

// ── 7. Enhance Master Nav to show quick actions ────────────────
(function patchMasterNavForQA() {
  const originalMasterNav = window.nav;
  if (!originalMasterNav || typeof originalMasterNav !== 'function') {
    setTimeout(patchMasterNavForQA, 500);
    return;
  }
  const patched = window.nav;
  window.nav = function(pane) {
    patched(pane);
    setTimeout(() => showQuickActions(pane), 100);
  };
})();

// ── 8. Improve chat empty state agent selection ────────────────
(function upgradeAgentPickerInEmpty() {
  const refreshPicker = () => {
    const container = document.getElementById('quick-agent-select');
    if (!container || !window.S?.agents?.length) { 
      setTimeout(refreshPicker, 1000); return; 
    }
    if (container.children.length > 0) return; // already populated
    container.innerHTML = S.agents.slice(0,6).map(a =>
      `<button onclick="setActiveAgent(${JSON.stringify(a).replace(/"/g,'&quot;')});document.getElementById('chat-empty').style.display='none'"
        style="display:flex;align-items:center;gap:6px;background:var(--bg-3);border:1px solid var(--border);border-radius:8px;padding:6px 10px;cursor:pointer;transition:var(--transition);font-size:12px;color:var(--text-1)"
        onmouseover="this.style.borderColor='var(--accent)';this.style.color='var(--text-0)'"
        onmouseout="this.style.borderColor='var(--border)';this.style.color='var(--text-1)'">
        <span>${a.avatar||'🤖'}</span><span>${escHtml(a.name)}</span>
      </button>`
    ).join('');
  };
  setTimeout(refreshPicker, 1500);
})();

// ── 9. Settings keyboard shortcut ⌘, ─────────────────────────
document.addEventListener('keydown', e => {
  if ((e.metaKey||e.ctrlKey) && e.key === ',') {
    e.preventDefault(); nav('settings');
  }
  // ⌘? shows keyboard shortcuts
  if ((e.metaKey||e.ctrlKey) && e.key === '/') {
    e.preventDefault();
    if (typeof showShortcuts === 'function') showShortcuts();
  }
  // ? (question mark) alone — show help
  if (e.key === '?' && !e.metaKey && !e.ctrlKey && !e.altKey && document.activeElement?.tagName !== 'INPUT' && document.activeElement?.tagName !== 'TEXTAREA') {
    if (typeof showShortcuts === 'function') showShortcuts();
  }
});

// ── 10. Status bar live metrics ────────────────────────────────
(function liveStatusBar() {
  setInterval(async () => {
    try {
      const r = await fetch('/api/control/stats');
      const s = await r.json();
      
      // Update cost in status bar  
      const costEl = document.getElementById('sb-cost');
      if (costEl) costEl.textContent = `$${(s.total_cost||0).toFixed(4)}`;
      
      // Show active run indicator
      const versionEl = document.getElementById('sb-version');
      if (versionEl && s.active_runs > 0) {
        versionEl.style.color = 'var(--warning)';
        versionEl.textContent = `⚡ ${s.active_runs} agent${s.active_runs>1?'s':''} running`;
      } else if (versionEl && versionEl.textContent.includes('agent')) {
        versionEl.style.color = '';
        versionEl.textContent = 'Agentic OS v6.0';
      }
    } catch(e) {}
  }, 10000);
})();

// ── 11. Ensure all panes render on first nav ──────────────────
// This is the failsafe — if a pane still shows skeleton after 3s,
// try calling its render function directly
function ensurePaneRendered(pane) {
  const el = document.getElementById('pane-' + pane);
  if (!el) return;
  
  // Check if still showing skeleton
  setTimeout(() => {
    if (el.classList.contains('active') && el.querySelector('.skeleton')) {
      console.warn('[Agentic OS] Pane still showing skeleton after 3s, forcing re-render:', pane);
      // Try all known render function names
      const renderFns = [
        `render${pane.charAt(0).toUpperCase()}${pane.slice(1)}`,
        `render${pane.toUpperCase()}`,
        `init${pane.charAt(0).toUpperCase()}${pane.slice(1)}`,
      ];
      for (const fn of renderFns) {
        if (typeof window[fn] === 'function') {
          try { window[fn](); break; } catch(e) {}
        }
      }
    }
  }, 3000);
}

// Patch into master nav
(function patchNavForEnsure() {
  const original = window.nav;
  if (!original) { setTimeout(patchNavForEnsure, 500); return; }
  window.nav = function(pane) {
    original(pane);
    ensurePaneRendered(pane);
  };
  console.log('%c✅ Sprint 11 UX polish loaded', 'color:#9d74f5;font-weight:bold');
})();


// ── Scroll panes to top when navigating ───────────────────────
(function addScrollToTop() {
  const observer = new MutationObserver(mutations => {
    for (const m of mutations) {
      if (m.type === 'attributes' && m.attributeName === 'class') {
        const el = m.target;
        if (el.classList.contains('active') && el.id?.startsWith('pane-')) {
          el.scrollTop = 0;
        }
      }
    }
  });
  document.querySelectorAll('.pane').forEach(pane => {
    observer.observe(pane, { attributes: true });
  });
  // Also handle dynamic panes added later
  setTimeout(() => {
    document.querySelectorAll('.pane').forEach(pane => {
      observer.observe(pane, { attributes: true });
    });
  }, 2000);
})();


// ── API key health indicator ─────────────────────────────────────
(function checkApiKeyHealth() {
  const keyDot  = document.getElementById('key-dot');
  const keyLabel = document.getElementById('key-label');
  fetch('/api/secrets/get?key=OPENROUTER_API_KEY').then(r=>r.ok?r.json():{}).then(j=>{
    const hasKey = j.ok && j.fingerprint;
    if (keyDot) keyDot.className = hasKey ? 'key-dot ok' : 'key-dot';
    if (keyLabel) keyLabel.textContent = hasKey ? 'API key set ✓' : 'No API key';
    // Also update the model badge visibility
    const badge = document.getElementById('active-model-badge');
    if (badge && !hasKey) badge.style.opacity = '0.4';
  }).catch(()=>{});
})();

