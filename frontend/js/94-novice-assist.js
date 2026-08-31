/* 94-novice-assist.js
 * ─────────────────────────────────────────────────────────────────────────────
 *  NOVICE ASSIST  —  second-round AI-novice UX layer (2026-08)
 *
 *  Three cooperative, non-invasive additions for someone new to AI:
 *
 *  1. "Simple mode" navigational switch.  A novice lands on the 8 CORE panes
 *     only; the four advanced groups (AI TOOLS / BUILD & SHIP / CONNECT /
 *     OPERATE) are hidden behind a single "Show all features" toggle. The last
 *     choice is remembered; a brand-new install defaults to the simple view.
 *
 *  2. "Getting started" checklist  in the Chat pane's empty state, so a novice
 *     always has a "now try X" roadmap.  It auto-checks real actions (connect
 *     AI · send a message · create a task · save a note) and persists progress.
 *
 *  3. Terminology polish: the chat "Agent" picker is explained as an
 *     assistant/vocabulary choice, and plain-language affordances are applied.
 *
 *  Safe-by-construction: every element lookup is null-guarded, every action is
 *  wrapped in its own try/catch so a failure here never affects the rest of the
 *  app. It hooks only known `window` globals (the app's own event delegate
 *  resolves `data-act-*` handlers on `window`), so nothing is duplicated or
 *  broken.
 */
(function () {
  'use strict';

  const LS_KEY = 'aos_novice_assist';

  function readState() {
    try { return JSON.parse(localStorage.getItem(LS_KEY) || '{}') || {}; }
    catch (e) { return {}; }
  }
  function writeState() {
    try { localStorage.setItem(LS_KEY, JSON.stringify(_st)); } catch (e) {}
    return _st;
  }

  const _st = Object.assign({ simple: null, gsDismissed: false, done: {} }, readState());
  // Brand-new install (no stored choice) => simple view on. Otherwise remember.
  // A later user toggle is stored as a string '1'/'0' and read back here.
  if (_st.simple !== true && _st.simple !== false) {
    if (_st.simple === '1') _st.simple = true;
    else if (_st.simple === '0') _st.simple = false;
    else _st.simple = true; // default for a fresh/undecided user
  }

  // ─────────────────────────────────────────────────────────────────────────
  //  1. SIMPLE MODE
  // ─────────────────────────────────────────────────────────────────────────
  const ADVANCED_GROUP_IDS = ['build', 'ship', 'tools', 'enterprise'];
  // _st.simple may be a boolean or the persisted string '1'/'0'; normalize here.
  function simpleOn() { return _st.simple === true || _st.simple === '1'; }

  function applySimpleMode() {
    const simple = simpleOn();
    document.querySelectorAll('.nav-item[data-tier="advanced"]').forEach((el) => {
      el.style.display = simple ? 'none' : '';
    });
    // Hide the four advanced group dividers AND their collapsed bodies.
    document.querySelectorAll('.sidebar-group-label').forEach((lbl) => {
      const act = lbl.getAttribute('data-act-click') || '';
      const isCore = act.indexOf("'core'") !== -1;
      lbl.style.display = (simple && !isCore) ? 'none' : '';
    });
    ADVANCED_GROUP_IDS.forEach((id) => {
      const g = document.getElementById('group-' + id);
      if (g) g.style.display = simple ? 'none' : '';
    });
    const footer = document.getElementById('aos-show-all-features');
    if (footer) footer.style.display = simple ? '' : 'none';
    const header = document.getElementById('aos-simple-toggle');
    if (header) {
      header.textContent = simple ? '💡' : '≡';
      header.setAttribute('title', simple
        ? 'Simple view on — click to show all features'
        : 'All features shown — click to simplify');
      header.setAttribute('aria-label', simple
        ? 'Show all features' : 'Switch to simple view');
    }
    // Make sure hidden advanced panes are not accidentally left "active".
    if (simple) {
      document.querySelectorAll('.nav-item[data-tier="advanced"]').forEach((el) => {
        if (el.classList.contains('active')) {
          try { window.nav && window.nav('chat'); } catch (e) {}
        }
      });
    }
  }

  window.aosToggleSimpleMode = function () {
    _st.simple = simpleOn() ? '0' : '1'; // store as string for clean round-trip
    writeState();
    applySimpleMode();
  };
  window.aosSimpleMode = function () { return simpleOn(); };

  window.aosShowSimpleFooter = function () {
    // navigates to all-features view from the "…more" footer link
    window.aosToggleSimpleMode();
  };

  function mountSimpleMode() {
    const header = document.getElementById('sidebar-top-nav-header');
    if (header && !document.getElementById('aos-simple-toggle')) {
      const t = document.createElement('button');
      t.type = 'button';
      t.id = 'aos-simple-toggle';
      t.setAttribute('data-act-click', 'aosToggleSimpleMode()');
      t.setAttribute('data-self-click', '1');
      t.setAttribute('data-keys', 'Enter,Space');
      t.setAttribute('data-prevent', '1');
      t.style.cssText = 'width:24px;height:24px;padding:0;font-size:13px;background:transparent;border:none;color:var(--text-2);cursor:pointer;display:flex;align-items:center;justify-content:center;border-radius:6px;transition:all 0.15s';
      header.appendChild(t);
    }
    const scroll = document.querySelector('.sidebar-scroll');
    if (scroll && !document.getElementById('aos-show-all-features')) {
      const f = document.createElement('button');
      f.type = 'button';
      f.id = 'aos-show-all-features';
      f.setAttribute('data-act-click', 'aosToggleSimpleMode()');
      f.setAttribute('data-self-click', '1');
      f.style.cssText = 'width:100%;text-align:left;padding:10px 14px;font-size:11.5px;font-weight:700;color:var(--text-2);background:none;border:none;border-top:1px solid var(--border);cursor:pointer';
      f.textContent = 'Show all features ▾ (advanced tools)';
      scroll.appendChild(f);
    }
    applySimpleMode();
  }

  // ─────────────────────────────────────────────────────────────────────────
  //  2. GETTING STARTED CHECKLIST
  // ─────────────────────────────────────────────────────────────────────────
  const GS_STEPS = [
    { id: 'connect', icon: '🔌', label: 'Connect your AI',      hint: 'Add one API key or a local model — 1 minute, no card' },
    { id: 'message', icon: '💬', label: 'Send your first message', hint: 'Ask a question or paste anything in the box below' },
    { id: 'note',    icon: '🗂', label: 'Save your first note',  hint: 'Put something in Knowledge or let the Inbox file it' },
    { id: 'task',    icon: '📋', label: 'Create your first task', hint: 'Add a card to the Tasks board' },
  ];

  function isDone(id) { return !!_st.done[id]; }

  window.aosMarkStep = function (id) {
    if (!id || _st.done[id]) return;
    _st.done[id] = true;
    writeState();
    renderGettingStarted();
  };

  function renderGettingStarted() {
    if (_st.gsDismissed) return;
    const host = document.getElementById('chat-empty');
    if (!host) return;
    if (document.getElementById('aos-getting-started')) {
      // just refresh states on an existing card
    } else {
      const card = document.createElement('div');
      card.id = 'aos-getting-started';
      card.style.cssText = 'max-width:560px;margin:0 auto 22px;text-align:left;background:var(--bg-2);border:1px solid var(--border);border-radius:16px;padding:16px 18px';
      host.appendChild(card);
    }
    const card = document.getElementById('aos-getting-started');
    if (!card) return;
    const doneCount = GS_STEPS.filter((s) => isDone(s.id)).length;
    const allDone = doneCount === GS_STEPS.length;

    const row = (s) => {
      const done = isDone(s.id);
      return `<div style="display:flex;align-items:center;gap:12px;padding:8px 0;border-top:1px solid var(--border)">` +
        `<span style="font-size:18px;width:24px;text-align:center">${done ? '✅' : s.icon}</span>` +
        `<div style="flex:1;min-width:0">` +
        `<div style="font-size:13px;font-weight:700;color:${done ? 'var(--text-2)' : 'var(--text-0)'}">${s.label}</div>` +
        `<div style="font-size:11.5px;color:var(--text-3)">${s.hint}</div></div>` +
        `<span style="font-size:11px;color:var(--text-3)">${done ? 'Done' : '…'}</span>` +
        `</div>`;
    };

    card.innerHTML = `
      <div style="display:flex;align-items:center;justify-content:space-between;margin-bottom:4px">
        <div style="font-size:14px;font-weight:900;color:var(--text-0)">${allDone ? '🎉 You\u2019re all set!' : '🚀 Getting started'}</div>
        <button title="Hide this anytime" style="background:none;border:none;color:var(--text-3);cursor:pointer;font-size:16px;line-height:1" data-aos-dismiss="1">×</button>
      </div>
      ${allDone
        ? '<div style="font-size:12.5px;color:var(--text-2);padding:6px 0 2px">Nice work. Explore the rest of the app anytime — click the 💡 button in the top-left to see every feature, or press ⌘K to search.</div>'
        : `<div style="font-size:12px;color:var(--text-2);margin-bottom:6px">A few easy moves to feel at home. They check off automatically.</div>
           ${GS_STEPS.map(row).join('')}`}
    `;
    const x = card.querySelector('[data-aos-dismiss]');
    if (x) x.addEventListener('click', function (e) {
      e.stopPropagation();
      _st.gsDismissed = true;
      writeState();
      card.remove();
    });
  }

  // ─────────────────────────────────────────────────────────────────────────
  //  DETECTION (auto-check real actions)
  // ─────────────────────────────────────────────────────────────────────────
  function checkConnectReady() {
    const el = document.getElementById('chat-connection-status');
    if (el && el.classList.contains('ready')) return true;
    return false;
  }
  function checkMessageSent() {
    return document.querySelectorAll('#chat-messages .msg-bubble').length > 0;
  }
  function checkTaskCreated() {
    return document.querySelectorAll('#pane-kanban .kanban-card').length > 0;
  }
  function sweep() {
    if (checkConnectReady()) window.aosMarkStep('connect');
    if (checkMessageSent()) window.aosMarkStep('message');
    if (checkTaskCreated()) window.aosMarkStep('task');
  }

  function mountChecks() {
    // 1) connect — detected in sweep() by reading the app's own connection
    //    ready-state element (#chat-connection-status.ready). No re-wrapping of
    //    window.renderConnectionReadiness; that would clobber the core signal
    //    and trip the duplicate-globals linter (see scripts/lint_globals.py).
    // 2) message — catch the human send paths (send button + Enter).
    const sendBtn = document.getElementById('chat-send');
    if (sendBtn) sendBtn.addEventListener('click', function () {
      const inp = document.getElementById('chat-input');
      if (inp && String(inp.value || '').trim().length) window.aosMarkStep('message');
    });
    const input = document.getElementById('chat-input');
    if (input) input.addEventListener('keydown', function (e) {
      if (e.key === 'Enter' && !e.shiftKey) {
        const inp = document.getElementById('chat-input');
        if (inp && String(inp.value || '').trim().length) window.aosMarkStep('message');
      }
    });
    // 3) note — wrap the user-triggered save / create flows.
    ['icmwsSave', 'icmwsCreateFromDesc', 'icmwsNewWorkspace'].forEach((name) => {
      const fn = window[name];
      if (typeof fn === 'function') {
        window[name] = function () {
          const r = fn.apply(this, arguments);
          window.aosMarkStep('note');
          return r;
        };
      }
    });
    // 4) task — detected in sweep() by scanning for rendered `.kanban-card`
    //    elements once the board has been opened; creating a task re-renders
    //    the board, so the sweep picks it up. No window.kanbanSubmitCreate
    //    re-wrap (would clobber the core handler + trip the duplicate-globals
    //    linter).
    // Periodic + on-navigation sweep (cheap, all guards inside).
    window.addEventListener('hashchange', () => setTimeout(sweep, 600));
    setInterval(sweep, 4000);
    setTimeout(sweep, 1500);
  }

  // ─────────────────────────────────────────────────────────────────────────
  //  3. TERMINOLOGY POLISH (pure DOM, no index.html edit needed)
  // ─────────────────────────────────────────────────────────────────────────
  function mountTerminology() {
    const details = document.getElementById('chat-persona-details');
    if (details) {
      const sum = details.querySelector('summary');
      if (sum) {
        const label = sum.querySelector('span[style*="uppercase"]');
        if (label && /Agent/i.test(label.textContent)) label.textContent = 'Assistant';
        sum.setAttribute('title', 'Choose who replies: a general assistant or a specialist voice');
      }
    }
    // Plain-language tooltip on the "Memory" chat toggle already exists; nothing further.
  }

  // ─────────────────────────────────────────────────────────────────────────
  //  INIT
  // ─────────────────────────────────────────────────────────────────────────
  function init() {
    try { mountSimpleMode(); } catch (e) { console.debug('a11y simple-mode init', e); }
    try { mountTerminology(); } catch (e) {}
    try { mountChecks(); } catch (e) {}
    try {
      if (document.readyState === 'loading') document.addEventListener('DOMContentLoaded', () => {
        try { renderGettingStarted(); } catch (e) {}
      });
      else setTimeout(() => { try { renderGettingStarted(); } catch (e) {} }, 300);
    } catch (e) {}
    console.debug('%c✅ Novice Assist loaded (Simple mode + Getting started + terminology)', 'color:#38bdf8;font-weight:bold');
  }

  if (document.readyState === 'loading') document.addEventListener('DOMContentLoaded', init);
  else init();
})();
