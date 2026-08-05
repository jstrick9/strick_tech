// Simple/Power mode switching and pane gating.
// Extracted from index.html so that script-src can drop
// 'unsafe-inline'. Execution order is unchanged: this file is loaded
// with defer, after every other deferred script.
'use strict';
(function() {
  var STORAGE_KEY = 'agentic_os_mode';
  var currentMode = localStorage.getItem(STORAGE_KEY) || 'power';
  var advancedOpen = false;

  function applyMode(mode) {
    currentMode = mode;
    localStorage.setItem(STORAGE_KEY, mode);
    document.documentElement.setAttribute('data-ui-mode', mode);
    var simpleBtn = document.getElementById('mode-simple-btn');
    var powerBtn  = document.getElementById('mode-power-btn');
    if (simpleBtn) simpleBtn.classList.toggle('active', mode === 'simple');
    if (powerBtn)  powerBtn.classList.toggle('active', mode === 'power');
    var advItems = document.querySelectorAll('.nav-item[data-tier="advanced"]');
    var countEl = document.getElementById('advanced-count');
    if (countEl) countEl.textContent = advItems.length + ' features';
    if (mode === 'power') { advancedOpen = true; showAdv(true); }
    else { advancedOpen = false; showAdv(false); }
  }

  function showAdv(show) {
    document.querySelectorAll('[data-tier="advanced"]').forEach(function(el) {
      el.style.display = show ? '' : 'none';
    });
    var arrow = document.getElementById('adv-arrow');
    var toggle = document.getElementById('advanced-toggle');
    if (arrow) arrow.textContent = show ? '\u25BC' : '\u25B6';
    if (toggle) toggle.classList.toggle('open', show);
  }

  window.toggleAdvanced = function() { advancedOpen = !advancedOpen; showAdv(advancedOpen); };
  window.setMode = function(mode) {
    if (typeof window.switchUIMode === 'function') window.switchUIMode(mode);
    else applyMode(mode);
  };

  function injectModeToggle() {
    var topbar = document.getElementById('topbar-actions');
    if (!topbar || document.getElementById('mode-toggle-container')) return;
    var c = document.createElement('div');
    c.id = 'mode-toggle-container';
    c.className = 'mode-toggle';
    c.style.marginRight = '6px';
    var btn1 = document.createElement('button');
    btn1.id = 'mode-simple-btn';
    btn1.textContent = '\u2728 Simple';
    btn1.title = 'Simple mode \u2014 7 core features';
    btn1.onclick = function() { setMode('simple'); };
    var btn2 = document.createElement('button');
    btn2.id = 'mode-power-btn';
    btn2.textContent = '\u26A1 Power';
    btn2.title = 'Power mode \u2014 all 60+ features';
    btn2.onclick = function() { setMode('power'); };
    c.appendChild(btn1);
    c.appendChild(btn2);
    topbar.insertBefore(c, topbar.firstChild);
  }

  function showOnboarding() {
    try { if (localStorage.getItem('agentic_os_onboarded')) return; } catch(e) {}
    var overlay = document.createElement('div');
    overlay.id = 'onboarding-overlay';
    overlay.className = 'onboarding-back';
    overlay.style.cssText = 'position:fixed;inset:0;background:rgba(2,4,10,0.92);z-index:99999;display:flex;align-items:center;justify-content:center;backdrop-filter:blur(8px);';
    overlay.onclick = function(e) { if (e.target === overlay) dismissOnboarding('power'); };
    
    var card = document.createElement('div');
    card.className = 'onboarding-card';
    card.style.cssText = 'background:var(--bg-2);border:1px solid var(--border-hi);border-radius:24px;padding:36px;max-width:560px;width:92%;box-shadow:0 30px 80px rgba(0,0,0,0.8);position:relative;text-align:center;color:var(--text-0);';
    card.innerHTML =
      '<button type="button" id="ob-close-top" data-act-click="dismissOnboarding(\'power\')" style="position:absolute;top:18px;right:20px;background:none;border:none;color:var(--text-2);font-size:24px;cursor:pointer;line-height:1">×</button>' +
      '<div style="font-size:48px;margin-bottom:12px">\uD83E\uDDE0</div>' +
      '<h2>Welcome to Agentic OS</h2>' +
      '<p style="color:var(--text-2);font-size:14px;margin-top:6px;line-height:1.5">Your local-first AI operating system. Chat with AI agents, build apps with live preview, manage tasks, and store everything in your Memory Galaxy.</p>' +
      '<div style="background:var(--bg-3);border-radius:14px;padding:18px;margin:20px 0;text-align:left">' +
        '<div style="font-size:13px;font-weight:700;color:var(--accent);margin-bottom:8px">Quick Start</div>' +
        '<div style="font-size:12px;color:var(--text-1);line-height:1.75">' +
          '<div style="margin-bottom:6px">1. <strong>Add your API key</strong> in Settings (get a free key at openrouter.ai/keys)</div>' +
          '<div style="margin-bottom:6px">2. <strong>Chat with an agent</strong> \u2014 try typing /help or ask any question</div>' +
          '<div style="margin-bottom:6px">3. <strong>Explore the Studio</strong> \u2014 live code editor with AI-powered preview</div>' +
          '<div>4. <strong>Try the Swarm</strong> \u2014 send one prompt to multiple AI models at once</div>' +
        '</div>' +
      '</div>' +
      '<div style="font-size:12.5px;color:var(--text-2);margin-bottom:20px"><strong>Simple mode</strong> shows 7 core features. Switch to <strong>Power mode</strong> anytime for all 60+ features.</div>' +
      '<div style="display:flex;gap:10px;justify-content:center;flex-wrap:wrap">' +
        '<button class="btn btn-primary" id="ob-power-btn" style="padding:11px 26px;font-size:14px;font-weight:700;cursor:pointer;border-radius:10px;border:none;background:var(--accent);color:#fff">Power Mode (All 60+ Features) →</button>' +
        '<button class="btn btn-ghost" id="ob-simple-btn" style="padding:11px 22px;font-size:14px;cursor:pointer;border-radius:10px;border:1px solid var(--border);background:var(--bg-3);color:var(--text-1)">Simple Mode (7 Core)</button>' +
      '</div>';
    overlay.appendChild(card);
    document.body.appendChild(overlay);
    var pBtn = document.getElementById('ob-power-btn'); if (pBtn) pBtn.onclick = function() { dismissOnboarding('power'); };
    var sBtn = document.getElementById('ob-simple-btn'); if (sBtn) sBtn.onclick = function() { dismissOnboarding('simple'); };
  }

  window.dismissOnboarding = function(mode) {
    try { localStorage.setItem('agentic_os_onboarded', 'true'); } catch(e) {}
    var overlay = document.getElementById('onboarding-overlay');
    if (overlay) {
      overlay.style.display = 'none';
      if (overlay.parentNode) overlay.parentNode.removeChild(overlay);
    }
    try { setMode(mode || 'power'); } catch(e) {}
    try { if (window.nav) nav('chat'); } catch(e) {}
  };

  applyMode(currentMode);
  setTimeout(injectModeToggle, 200);
  setTimeout(showOnboarding, 1000);
  console.log('%c\u2705 Sidebar Mode System loaded', 'color:#5b8af8;font-weight:bold');
})();
