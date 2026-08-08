// Agentic OS — Workstation consolidation
// ============================================================================
// The sidebar had grown to 67 top-level panes, including a 26-item catch-all
// "MONITORING" group. That is far past the point where a list can be scanned,
// and it hid genuinely duplicated destinations from each other (Code Index vs
// Code Search, Evals vs Eval Framework, MCP vs MCP Gateway, Pipelines vs
// Workflows, Observability vs Live Monitor, ...).
//
// This module groups related panes into a small number of WORKSTATIONS. A
// workstation is a host pane that renders a tab strip; each tab is one of the
// panes that used to sit in the sidebar on its own.
//
// Design constraints that make this safe and reversible:
//   • No renderer is rewritten. Every absorbed pane keeps its own DOM node and
//     its own entry in MASTER_PANE_REGISTRY; the workstation just moves that
//     node inside itself and shows/hides it. If this file is deleted, every
//     pane still works exactly as before.
//   • No feature is lost. Nothing is deleted or hidden behind a flag — every
//     absorbed pane is one click away, and still addressable by its own id.
//   • Deep links keep working. nav('finops') still resolves: it opens the host
//     workstation and selects the FinOps tab (see the redirect in nav()).
//
// Result: 67 top-level panes -> 24.
'use strict';

// host pane id -> ordered list of absorbed pane ids (tabs appear in this order,
// with the host itself always first).
window.WORKSTATIONS = {
  // Everything about "what is the system doing / did it do".
  'observability': ['agent-monitor', 'profiler', 'health', 'system', 'audit-log', 'replay', 'finops', 'dashboard', 'leaderboard'],
  // Everything about "is the output any good".
  'evals': ['eval-framework', 'arena', 'bugbot', 'testgen'],
  // Code intelligence belongs with the editor, not three sidebar entries away.
  'studio': ['codesearch', 'codeindex', 'multitab'],
  // Every outbound connection: tools, gateways, third-party services, events.
  // Connectors and the MCP gateway fold into the Connect hub ('mcp' pane):
  // they were separate panes over separate registries showing the same
  // question -- "what can my agent reach?". Integrations, webhooks and hooks
  // remain: inbound triggers and event automations are a different job from
  // outbound capability, not a duplicate catalog.
  'mcp': ['integrations', 'webhooks', 'hooks'],
  // Every knowledge store the agents can read from.
  'galaxy': ['rag', 'knowledge-graph', 'obsidian'],
  // Every "run this automatically" surface.
  'workflow': ['pipeline', 'loops', 'specs', 'ambient'],
  // Everything that extends the platform.
  // Marketplace folded into the Plugin Hub (the 'plugins' pane): it was a
  // second catalog over a second backend showing overlapping packs with
  // independent install state. Skills and the SDK remain — they are different
  // jobs (use what you installed / build your own), not duplicate catalogs.
  'plugins': ['skills', 'pluginsdk'],
  // Source control and shipping.
  'github': ['gitai', 'deploy'],
  // Secrets and cryptography.
  'secrets': ['pqc'],
  // Agent orchestration and identity.
  'supervisor': ['a2a', 'agent-identity', 'hitl', 'goals', 'swarm', 'fusion', 'finetune'],
  // Shared/multi-user surfaces.
  'workspaces': ['collabedit', 'control'],
};

// Reverse index: absorbed pane id -> host pane id.
window.PANE_TO_WORKSTATION = (function () {
  const map = {};
  Object.keys(window.WORKSTATIONS).forEach((host) => {
    window.WORKSTATIONS[host].forEach((child) => { map[child] = host; });
  });
  return map;
})();

// Human-readable tab labels. Falls back to a title-cased pane id.
window.WORKSTATION_LABELS = {
  'observability': '🔭 Traces', 'agent-monitor': '📡 Live Monitor', 'profiler': '📈 Profiler',
  'health': '💚 Health', 'system': '⚙ System', 'audit-log': '📝 Audit Log',
  'replay': '⟲ Replay', 'finops': '💰 Cost', 'dashboard': '📊 Dashboard',
  'leaderboard': '🏆 Leaderboard',
  'evals': '🧪 Evals', 'eval-framework': '🧬 Eval Framework', 'arena': '⚔ Model Arena',
  'bugbot': '🐛 Bug Finder', 'testgen': '🧾 Test Generator',
  'studio': '⚡ Editor', 'codesearch': '⌕ Code Search', 'codeindex': '🔍 Code Index',
  'multitab': '◫ Multi-Preview',
  'mcp': '🔌 Connect', 'mcp-gateway': '🚪 Gateway', 'connectors': '🔗 Connectors',
  'integrations': '🧩 Integrations', 'webhooks': '🔔 Webhooks', 'hooks': '⚡ Event Hooks',
  'galaxy': '🧠 Memory', 'rag': '📚 Knowledge Search', 'knowledge-graph': '🕸 Knowledge Graph',
  'obsidian': '📝 Obsidian Sync',
  'workflow': '⎈ Workflows', 'pipeline': '⎈ Pipelines', 'loops': '♾ Autonomous Loops',
  'specs': '📐 Spec Builder', 'ambient': '🌙 Ambient Mode',
  'plugins': '🧩 Plugin Hub', 'pluginsdk': '🔧 Build a Plugin', 'marketplace': '🛒 Marketplace',
  'skills': '⚡ Skills',
  'github': '🐙 GitHub', 'gitai': '⎇ Git Assistant', 'deploy': '🚀 Deploy',
  'secrets': '🔐 Secrets Vault', 'pqc': '🛡 Encryption',
  'supervisor': '🎯 Supervisor', 'a2a': '🌐 Agent Network', 'agent-identity': '🪪 Identity',
  'hitl': '👁 Review Queue', 'goals': '🎯 Goals', 'swarm': '🌀 Swarm',
  'fusion': '🔀 Model Fusion', 'finetune': '🧪 Fine-Tuning',
  'workspaces': '📂 Workspaces', 'collabedit': '👥 Collaborative Edit', 'control': '🎛 Control Tower',
};

function workstationLabel(pane) {
  return window.WORKSTATION_LABELS[pane] ||
    pane.replace(/[-_]+/g, ' ').replace(/\b\w/g, (c) => c.toUpperCase());
}

// Build (once) the tab strip for a host pane and move the absorbed panes into
// its body. Absorbed panes keep their own #pane-<id> element so their existing
// renderers, querySelectors and tests continue to work untouched.
window.initWorkstation = function (host) {
  const children = window.WORKSTATIONS[host];
  if (!children) return false;

  const hostEl = document.getElementById('pane-' + host);
  if (!hostEl) return false;

  // Idempotency is decided by the DOM, not by a flag.
  //
  // This used to be `hostEl.dataset.workstationReady === '1'`, and that flag
  // was a lie the moment the host's own renderer replaced the host's
  // innerHTML: the attribute survives on the element, the tab strip and every
  // absorbed pane inside it do not. initWorkstation then returned early
  // forever, so the workstation could never rebuild itself, and 7 of the 11
  // workstations were permanently destroyed the first time you opened them.
  //
  // Checking for the structure we actually need means a wiped workstation
  // simply rebuilds on the next navigation.
  if (hostEl.querySelector(':scope > .ws-tabs') &&
      hostEl.querySelector(':scope > .ws-bodies')) {
    return true;
  }

  const tabs = [host].concat(children);

  // Wrap the host's own existing content so it can live as the first tab.
  const ownBody = document.createElement('div');
  ownBody.id = 'ws-body-' + host;
  ownBody.className = 'ws-body';
  while (hostEl.firstChild) ownBody.appendChild(hostEl.firstChild);

  const strip = document.createElement('div');
  strip.className = 'ws-tabs';
  strip.setAttribute('role', 'tablist');
  strip.id = 'ws-tabs-' + host;

  const bodies = document.createElement('div');
  bodies.className = 'ws-bodies';
  bodies.appendChild(ownBody);

  tabs.forEach((pane) => {
    const btn = document.createElement('button');
    btn.type = 'button';
    btn.className = 'ws-tab' + (pane === host ? ' active' : '');
    btn.dataset.wsTab = pane;
    btn.setAttribute('role', 'tab');
    btn.setAttribute('aria-selected', pane === host ? 'true' : 'false');
    btn.textContent = workstationLabel(pane);
    btn.addEventListener('click', () => window.showWorkstationTab(host, pane, true));
    strip.appendChild(btn);

    if (pane === host) return;
    // Relocate the absorbed pane's element into this workstation.
    let childEl = document.getElementById('pane-' + pane);
    if (!childEl) {
      childEl = document.createElement('div');
      childEl.id = 'pane-' + pane;
    }
    childEl.classList.remove('pane', 'active');
    childEl.classList.add('ws-body');
    childEl.style.display = 'none';
    bodies.appendChild(childEl);
  });

  hostEl.appendChild(strip);
  hostEl.appendChild(bodies);
  hostEl.dataset.workstationReady = '1';
  window.watchWorkstationHost(host);
  return true;
};

// Show one tab within a workstation, invoking that pane's registered renderer
// the first time it is opened (and on every open, matching nav() semantics).
// Remember which tab a workstation should open next.
//
// 00-workstations.js owns this state. nav() needs to set it too (it records
// the wanted tab before navigating to the host), and having both files do
// `window._activeWorkstationTab = window._activeWorkstationTab || {}` tripped
// the duplicate-globals linter -- correctly, because two owners of one
// mutable global is how they drift.
// Record a pane in the URL, creating a history entry for real navigation.
//
// THE BUG THIS FIXES
// Every navigation used history.replaceState(), so four pane changes created
// ZERO history entries. Pressing Back therefore left the application
// entirely -- measured: about:blank, window.nav undefined, session gone. Back
// is a reflex action, so the worst possible outcome is losing everything.
//
// A `hashchange` listener that routes correctly already existed in
// 01-app-core.js; it simply never fired, because replaceState does not
// produce a hashchange.
//
// `userInitiated` distinguishes a click from a programmatic restore. A
// workstation re-opening its last tab must NOT add an entry, or Back would
// step through states the user never chose.
window.recordPaneInUrl = function (pane, userInitiated) {
  const target = '#/' + pane;
  try {
    // Collapse duplicates. nav() runs repeatedly for the same pane
    // (renderers re-navigate, workstation tabs re-open); stacking identical
    // entries makes Back appear to do nothing several times in a row.
    if (location.hash === target) return;
    if (userInitiated) history.pushState(null, '', target);
    else history.replaceState(null, '', target);
  } catch (e) { /* history is unavailable in some embeds; never block nav */ }
};

// Rebuild a workstation whose host wiped its own innerHTML.
//
// Batch 30 fixed the FIRST render: nav() now waits for an async host renderer
// before building the tab strip. But a host can re-render later -- on a poll,
// a filter change, or a slow second pass. Measured with 250 seeded goals:
// renderSupervisor() ran again ~3s after nav(), replaced #pane-supervisor's
// innerHTML, and destroyed the Goals tab that had already rendered 5,976
// characters. The user saw the Goals list appear and then vanish.
//
// initWorkstation() is idempotent and decides from the DOM, so re-running it
// is safe and cheap. Observing the host is what makes this cover every
// renderer rather than the one that happened to be caught.
window.watchWorkstationHost = function (host) {
  const hostEl = document.getElementById('pane-' + host);
  if (!hostEl || hostEl.dataset.wsWatched === '1') return;
  if (typeof MutationObserver !== 'function') return;
  hostEl.dataset.wsWatched = '1';

  let queued = false;
  new MutationObserver(() => {
    if (queued) return;
    // The tab strip is gone but this host owns one: it was wiped.
    if (hostEl.querySelector(':scope > .ws-tabs')) return;
    queued = true;
    // Coalesce the burst a single innerHTML assignment produces.
    setTimeout(() => {
      queued = false;
      try {
        if (hostEl.querySelector(':scope > .ws-tabs')) return;
        window.initWorkstation(host);
        const last = (window._activeWorkstationTab || {})[host] || host;
        window.showWorkstationTab(host, last, false);
      } catch (e) { /* never let recovery break a render */ }
    }, 60);
  }).observe(hostEl, {childList: true});
};

window.setWorkstationTab = function (host, pane) {
  window._activeWorkstationTab = window._activeWorkstationTab || {};
  window._activeWorkstationTab[host] = pane;
};

window.showWorkstationTab = function (host, pane, userInitiated) {
  if (!window.initWorkstation(host)) return;
  const hostEl = document.getElementById('pane-' + host);
  if (!hostEl) return;

  hostEl.querySelectorAll(':scope > .ws-bodies > .ws-body').forEach((el) => {
    const on = (el.id === 'ws-body-' + host ? pane === host : el.id === 'pane-' + pane);
    el.style.display = on ? '' : 'none';
    // Keep the `active` class in sync with visibility.
    //
    // initWorkstation() strips `active` when it absorbs a pane, because the
    // class also drives the top-level pane layout. But several renderers use
    // it as "am I on screen?" before doing work -- refreshControlTower() bails
    // out entirely unless `pane-control` has it, which left the Control Tower
    // stuck on its skeleton forever once it became a workstation tab. The
    // class is the app's own visibility signal, so an absorbed pane that IS
    // showing must carry it.
    el.classList.toggle('active', on);
  });
  hostEl.querySelectorAll(':scope > .ws-tabs > .ws-tab').forEach((btn) => {
    const on = btn.dataset.wsTab === pane;
    btn.classList.toggle('active', on);
    btn.setAttribute('aria-selected', on ? 'true' : 'false');
  });

  window.setWorkstationTab(host, pane);

  // Run the pane's own renderer. The host's renderer is driven by nav().
  if (pane !== host) {
    const renderer = window.MASTER_PANE_REGISTRY && window.MASTER_PANE_REGISTRY[pane];
    if (typeof renderer === 'function') {
      try { renderer(); } catch (e) { console.warn('Workstation renderer error for ' + pane + ':', e); }
    }
  }
  // Keep the URL addressable per tab so deep links and back/forward work.
  window.recordPaneInUrl(pane, !!userInitiated);
};
