// Agentic OS v6.0 — Sprint features preamble
// Feature code extracted to modules 41-55 (IIFE-wrapped)
// This file contains: PWA registration, nav patches, HITL WebSocket listener

'use strict';

// PWA Registration
(function registerPWA() {
  if ('serviceWorker' in navigator) {
    window.addEventListener('load', () => {
      navigator.serviceWorker.register('/static/sw.js')
        .then(reg => {
          console.debug('%c✅ PWA Service Worker registered', 'color:#4cc98a');
          reg.addEventListener('updatefound', () => {
            const worker = reg.installing;
            if (worker) {
              worker.addEventListener('statechange', () => {
                if (worker.state === 'installed' && navigator.serviceWorker.controller) {
                  showToast('🔄 Update available — refresh to apply', 5000);
                }
              });
            }
          });
        })
        .catch(err => console.warn('SW registration failed:', err));
    });
  }

  let deferredPrompt = null;
  window.addEventListener('beforeinstallprompt', (e) => {
    e.preventDefault();
    deferredPrompt = e;
    const btn = document.getElementById('pwa-install-btn');
    if (btn) btn.style.display = 'flex';
  });

  window.installPWA = async () => {
    if (deferredPrompt) {
      deferredPrompt.prompt();
      const result = await deferredPrompt.userChoice;
      if (result.outcome === 'accepted') {
        showToast('✅ Agentic OS installed as desktop app!');
      }
      deferredPrompt = null;
    } else {
      gmAlert('To install: click Install Agentic OS or Add to Home Screen');
    }
  };
})();

// Nav patches for Sprint A-D features
(function patchNavSprint18() {
  const _base = window.nav || function(){};
  // intentional-override: wraps core nav (Sprint 18 pane hooks)
  window.nav = function masterNav18(pane) {
    _base(pane);
    // NOTE: renderFusion/renderHITL/etc. are defined in separate IIFE-wrapped
    // modules and only exposed via `window.render...`. Calling the bare
    // (undeclared) identifier with `?.()` still throws a ReferenceError —
    // optional chaining only guards null/undefined, not "not defined".
    // Always go through `window.` + `typeof` checks.
    if (pane==='fusion'         && typeof window.renderFusion === 'function')        window.renderFusion();
    if (pane==='hitl'           && typeof window.renderHITL === 'function')          window.renderHITL();
    if (pane==='browser'        && typeof window.renderBrowserAgent === 'function')  window.renderBrowserAgent();
    if (pane==='websearch'      && typeof window.renderWebSearch === 'function')     window.renderWebSearch();
    if (pane==='leaderboard'    && typeof window.renderLeaderboard === 'function')   window.renderLeaderboard();
    if (pane==='audit-log'      && typeof window.renderAuditLog === 'function')      window.renderAuditLog();
    if (pane==='agent-identity' && typeof window.renderAgentIdentity === 'function') window.renderAgentIdentity();
    if (pane==='supervisor'     && typeof window.renderSupervisor === 'function')    window.renderSupervisor();
    if (pane==='goals'          && typeof window.renderGoals === 'function')         window.renderGoals();
    if (pane==='mcp-gateway'    && typeof window.renderMCPGateway === 'function')    window.renderMCPGateway();
    if (pane==='connectors'     && typeof window.renderConnectors === 'function')    window.renderConnectors();
    if (pane==='agent-monitor'  && typeof window.renderAgentMonitor === 'function')  window.renderAgentMonitor();
    if (pane==='finops'         && typeof window.renderFinOps === 'function')        window.renderFinOps();
    if (pane==='eval-framework' && typeof window.renderEvalFramework === 'function') window.renderEvalFramework();
    if (pane==='a2a'            && typeof window.renderA2A === 'function')           window.renderA2A();
  };
  console.debug('%c✅ Sprint A+B+C+D features loaded', 'color:#3dba7a');
})();


// HITL WebSocket listener
(function listenForHITL() {
  function _connectHITLWS() {
    try {
      const ws = new WebSocket(`ws://${location.host}/api/ws`);
      ws.onclose = () => setTimeout(_connectHITLWS, 3000);
      ws.onerror = () => {};
      ws.onmessage = ({data}) => {
        try {
          const msg = JSON.parse(data);
          if (msg.type==='hitl_interrupt') {
            const toast = document.createElement('div');
            toast.style.cssText = 'position:fixed;top:60px;right:16px;background:var(--bg-2);border:2px solid var(--warning);border-radius:12px;padding:14px 16px;z-index:9995;max-width:340px;box-shadow:0 8px 32px rgba(0,0,0,.5);animation:voice-in .3s ease;';
            toast.innerHTML = `<div style="display:flex;align-items:center;gap:8px;margin-bottom:8px"><span style="font-size:20px">🛡️</span><strong style="color:var(--warning)">Agent Approval Required</strong><button onclick="this.closest('[style]').remove()" style="margin-left:auto;background:none;border:none;color:var(--text-3);cursor:pointer;font-size:16px">✕</button></div><div style="font-size:12px;color:var(--text-1);margin-bottom:10px">${escHtml(msg.action_summary||'Review required')}</div><div style="display:flex;gap:6px"><button onclick="hitlDecide('${msg.interrupt_id}','approve');this.closest('[style]').remove()" style="flex:1;padding:6px;background:var(--success);border:none;border-radius:6px;color:#fff;font-weight:600;cursor:pointer;font-size:12px">✅ Approve</button><button onclick="hitlDecide('${msg.interrupt_id}','reject');this.closest('[style]').remove()" style="padding:6px 12px;background:transparent;border:1px solid var(--danger);border-radius:6px;color:var(--danger);cursor:pointer;font-size:12px">Reject</button><button onclick="nav('hitl');this.closest('[style]').remove()" style="padding:6px 10px;background:var(--bg-3);border:1px solid var(--border);border-radius:6px;color:var(--text-1);cursor:pointer;font-size:12px">View</button></div>`;
            document.body.appendChild(toast);
            setTimeout(()=>toast.remove(), 30000);
          }
        } catch(e) {}
      };
    } catch(e) {}
  }
  _connectHITLWS();
})();

// Keyboard shortcuts Sprint 18
document.addEventListener('keydown', (e) => {
  if (!e.metaKey && !e.ctrlKey || !e.shiftKey) return;
  if (e.key==='F') { e.preventDefault(); nav('fusion'); }
  if (e.key==='L') { e.preventDefault(); nav('leaderboard'); }
  if (e.key==='X') { e.preventDefault(); nav('websearch'); }
});
