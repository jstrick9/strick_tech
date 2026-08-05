// ══════════════════════════════════════════════════════════════════
//  UNIFIED ACCOUNT SETTINGS — single source of truth for "me" stuff
//  Replaces the two previously-separate, overlapping entry points:
//    1. "Me" pill (topbar)      → Identity & Custom App Branding panel
//    2. Avatar icon (topbar)    → "Your Profile" panel
//  Both wrote to overlapping/duplicate fields (name, role, avatar) on
//  /api/profile and drifted out of sync. This is the single modal that
//  replaces both, organized like Discord/Slack/Linear account settings:
//  a centered modal with a left-hand tab rail.
// ══════════════════════════════════════════════════════════════════

(function () {
  'use strict';

  const AVATAR_EMOJIS = ['👤','🧑‍💻','👨‍💻','👩‍💻','🤖','🧠','⚡','🔧','🎨','📊','🧪','💡','🚀','🌟','🦄','🐉','🦊','🐱','🐶','🦉'];
  const ROLE_PRESETS = [
    {id: 'developer', label: 'Developer'},
    {id: 'analyst', label: 'Analyst'},
    {id: 'writer', label: 'Writer'},
    {id: 'designer', label: 'Designer'},
    {id: 'manager', label: 'Manager'},
    {id: 'student', label: 'Student'},
  ];
  const SKILL_LEVELS = ['beginner', 'intermediate', 'advanced', 'expert'];
  const THEMES = [
    {id: 'light', label: 'Light', icon: '☀️'},
    {id: 'dark', label: 'Dark Cyber', icon: '🌑'},
    {id: 'auto', label: 'Auto (Device)', icon: '🌓'},
    {id: 'obsidian', label: 'Obsidian', icon: '🪨'},
    {id: 'jet', label: 'Jet', icon: '✈️'},
    {id: 'midnight', label: 'Midnight Blue', icon: '🌌'},
    {id: 'forest', label: 'Forest Emerald', icon: '🌲'},
  ];

  const TABS = [
    {id: 'profile', label: 'Profile', icon: '👤'},
    {id: 'preferences', label: 'Preferences', icon: '🎨'},
    {id: 'notifications', label: 'Notifications', icon: '🔔'},
    {id: 'workspace', label: 'Workspace & Branding', icon: '🏷️'},
    {id: 'plan', label: 'Plan', icon: '💳'},
  ];

  let _state = null;      // merged {profile, prefs, license} loaded from backend
  let _activeTab = 'profile';

  function esc(s) { return typeof escHtml === 'function' ? escHtml(String(s ?? '')) : String(s ?? ''); }
  function fireToast(msg, type, dur) { if (typeof toast === 'function') toast(msg, type, dur); }

  // ── Data loading ───────────────────────────────────────────────────
  async function loadAccountData() {
    let profile = {}, prefs = {}, license = {tier: 'trial', is_trial: true, trial_days_left: 14};
    try {
      const [p, pr, lic] = await Promise.all([
        fetch('/api/profile').then(r => r.ok ? r.json() : null).catch(() => null),
        fetch('/api/onboarding/preferences').then(r => r.ok ? r.json() : null).catch(() => null),
        fetch('/api/license/status').then(r => r.ok ? r.json() : null).catch(() => null),
      ]);
      if (p) profile = p;
      if (pr) prefs = pr;
      if (lic) license = lic;
    } catch (e) { console.warn('Account settings: data load failed', e); }
    return {profile, prefs, license};
  }

  // ── Persist helpers ──────────────────────────────────────────────────
  async function patchProfile(body) {
    try {
      const r = await fetch('/api/profile', {method: 'PATCH', headers: {'Content-Type': 'application/json'}, body: JSON.stringify(body)});
      const j = await r.json().catch(() => ({}));
      return j && j.ok !== false;
    } catch (e) { return false; }
  }
  async function patchPrefs(body) {
    try {
      const r = await fetch('/api/onboarding/preferences', {method: 'PATCH', headers: {'Content-Type': 'application/json'}, body: JSON.stringify(body)});
      const j = await r.json().catch(() => ({}));
      return j && j.ok !== false;
    } catch (e) { return false; }
  }

  // ── Modal shell ──────────────────────────────────────────────────────
  window.openAccountSettings = async function (initialTab) {
    const existing = document.getElementById('account-settings-modal');
    if (existing) { existing.remove(); }

    _activeTab = initialTab || _activeTab || 'profile';
    _state = await loadAccountData();

    const overlay = document.createElement('div');
    overlay.id = 'account-settings-modal';
    overlay.setAttribute('role', 'dialog');
    overlay.setAttribute('aria-modal', 'true');
    overlay.style.cssText = 'position:fixed;inset:0;background:rgba(4,6,14,.72);backdrop-filter:blur(3px);z-index:9990;display:flex;align-items:center;justify-content:center;padding:24px';
    overlay.innerHTML = `
      <div id="account-settings-card" style="background:var(--bg-1);border:1px solid var(--border-hi);border-radius:18px;width:100%;max-width:860px;height:min(680px,90vh);display:flex;overflow:hidden;box-shadow:0 30px 90px rgba(0,0,0,.6)">
        <div id="account-settings-rail" style="width:220px;flex-shrink:0;background:var(--bg-2);border-right:1px solid var(--border);display:flex;flex-direction:column;overflow-y:auto">
          <div style="padding:18px 16px 10px;font-size:11px;font-weight:800;color:var(--text-3);text-transform:uppercase;letter-spacing:.8px">Account Settings</div>
          <div id="account-settings-tabs" style="display:flex;flex-direction:column;gap:2px;padding:0 8px"></div>
          <div style="flex:1"></div>
          <div style="padding:12px;border-top:1px solid var(--border)">
            <button type="button" id="account-settings-close-btn" style="width:100%;padding:8px;background:var(--bg-3);border:1px solid var(--border);border-radius:8px;color:var(--text-2);cursor:pointer;font-size:12px;font-weight:700">Close</button>
          </div>
        </div>
        <div id="account-settings-body" style="flex:1;overflow-y:auto;padding:26px 30px"></div>
      </div>`;
    document.body.appendChild(overlay);

    // Tab rail
    const tabRail = overlay.querySelector('#account-settings-tabs');
    tabRail.innerHTML = TABS.map(t => `
      <button type="button" class="account-tab-btn" data-tab="${t.id}" style="display:flex;align-items:center;gap:10px;padding:10px 12px;border-radius:9px;background:${t.id === _activeTab ? 'var(--accent)' : 'transparent'};color:${t.id === _activeTab ? '#fff' : 'var(--text-1)'};border:none;cursor:pointer;font-size:13px;font-weight:700;text-align:left;transition:background .12s,color .12s">
        <span>${t.icon}</span><span>${esc(t.label)}</span>
      </button>`).join('');
    tabRail.querySelectorAll('.account-tab-btn').forEach(btn => {
      btn.addEventListener('click', () => selectAccountTab(btn.dataset.tab));
    });

    overlay.querySelector('#account-settings-close-btn').addEventListener('click', window.closeAccountSettings);
    overlay.addEventListener('mousedown', (e) => { if (e.target === overlay) window.closeAccountSettings(); });
    document.addEventListener('keydown', accountSettingsEscHandler);

    renderAccountTabBody(_activeTab);
  };

  function accountSettingsEscHandler(e) {
    if (e.key === 'Escape' && document.getElementById('account-settings-modal')) {
      e.preventDefault(); e.stopPropagation(); window.closeAccountSettings();
    }
  }

  window.closeAccountSettings = function () {
    const el = document.getElementById('account-settings-modal');
    if (el) el.remove();
    document.removeEventListener('keydown', accountSettingsEscHandler);
  };

  // Re-shows the modal if it's just hidden (display:none) rather than
  // removed — used when returning from "Customize Sidebar" so closing that
  // popup takes you back to Account Settings instead of dropping you back
  // to whatever pane was underneath with no way back in one click.
  window.restoreAccountSettings = function () {
    const el = document.getElementById('account-settings-modal');
    if (el) {
      el.style.display = 'flex';
      document.addEventListener('keydown', accountSettingsEscHandler);
    } else {
      window.openAccountSettings(_activeTab);
    }
  };

  function selectAccountTab(tabId) {
    _activeTab = tabId;
    const overlay = document.getElementById('account-settings-modal');
    if (!overlay) return;
    overlay.querySelectorAll('.account-tab-btn').forEach(btn => {
      const active = btn.dataset.tab === tabId;
      btn.style.background = active ? 'var(--accent)' : 'transparent';
      btn.style.color = active ? '#fff' : 'var(--text-1)';
    });
    renderAccountTabBody(tabId);
  }

  function fieldLabel(text) {
    return `<label style="font-size:11px;font-weight:700;color:var(--text-3);text-transform:uppercase;letter-spacing:.5px;display:block;margin-bottom:5px">${esc(text)}</label>`;
  }
  function textInputStyle() {
    return 'width:100%;background:var(--bg-2);border:1px solid var(--border);border-radius:8px;padding:9px 12px;color:var(--text-0);font-size:13px;outline:none;font-family:inherit';
  }

  // ── Tab renderers ────────────────────────────────────────────────────
  function renderAccountTabBody(tabId) {
    const body = document.querySelector('#account-settings-modal #account-settings-body');
    if (!body) return;
    const renderers = {
      profile: renderProfileTab,
      preferences: renderPreferencesTab,
      notifications: renderNotificationsTab,
      workspace: renderWorkspaceTab,
      plan: renderPlanTab,
    };
    (renderers[tabId] || renderProfileTab)(body);
  }

  // ── TAB: Profile ─────────────────────────────────────────────────────
  function renderProfileTab(body) {
    const p = _state.profile || {};
    body.innerHTML = `
      <div style="margin-bottom:22px">
        <h2 style="margin:0 0 4px;font-size:20px;font-weight:900">👤 Profile</h2>
        <p style="margin:0;color:var(--text-2);font-size:12.5px">How you appear across chat, agents, and collaboration.</p>
      </div>

      <div style="display:flex;align-items:center;gap:16px;margin-bottom:22px">
        <div id="acct-avatar-display" style="width:64px;height:64px;border-radius:50%;background:var(--bg-3);border:1px solid var(--border-hi);display:flex;align-items:center;justify-content:center;font-size:32px;flex-shrink:0;overflow:hidden">${p.avatar && p.avatar.startsWith('data:') ? `<img src="${p.avatar}" style="width:100%;height:100%;object-fit:cover" alt="">` : esc(p.avatar || '👤')}</div>
        <div style="flex:1">
          <div style="display:flex;gap:8px;margin-bottom:8px">
            <input type="file" id="acct-avatar-file" accept="image/*" style="display:none">
            <button type="button" id="acct-upload-picture-btn" class="btn-3d btn-sm" style="font-size:11px">📸 Upload Picture</button>
          </div>
          <div id="acct-avatar-picker" style="display:flex;flex-wrap:wrap;gap:4px;max-width:340px"></div>
        </div>
      </div>

      <div style="display:grid;grid-template-columns:1fr 1fr;gap:14px;margin-bottom:14px">
        <div>${fieldLabel('Display Name')}<input id="acct-name" type="text" value="${esc(p.name || '')}" style="${textInputStyle()}"></div>
        <div>${fieldLabel('Email')}<input id="acct-email" type="email" value="${esc(p.email || '')}" placeholder="you@example.com" style="${textInputStyle()}"></div>
      </div>

      <div style="display:grid;grid-template-columns:1fr 1fr;gap:14px;margin-bottom:14px">
        <div>
          ${fieldLabel('Job Title')}
          <input id="acct-title" type="text" value="${esc(p.job_title || '')}" placeholder="e.g. Senior Architect" style="${textInputStyle()}">
        </div>
        <div>
          ${fieldLabel('Role Preset (personalizes defaults)')}
          <select id="acct-role" style="${textInputStyle()};cursor:pointer">
            ${ROLE_PRESETS.map(r => `<option value="${r.id}" ${p.role === r.id ? 'selected' : ''}>${esc(r.label)}</option>`).join('')}
          </select>
        </div>
      </div>

      <div style="margin-bottom:20px">
        ${fieldLabel('Skill Level')}
        <select id="acct-skill" style="${textInputStyle()};cursor:pointer;max-width:220px">
          ${SKILL_LEVELS.map(s => `<option value="${s}" ${p.skill_level === s ? 'selected' : ''}>${s.charAt(0).toUpperCase() + s.slice(1)}</option>`).join('')}
        </select>
      </div>

      <div style="background:var(--bg-2);border-radius:10px;padding:12px 14px;margin-bottom:20px;display:grid;grid-template-columns:1fr 1fr;gap:8px">
        <div style="text-align:center">
          <div style="font-size:15px;font-weight:800;color:var(--text-0)">${p.created_at ? new Date(p.created_at).toLocaleDateString() : '—'}</div>
          <div style="font-size:10px;color:var(--text-3)">Joined</div>
        </div>
        <div style="text-align:center">
          <div style="font-size:15px;font-weight:800;color:var(--text-0)">${p.onboarding_done ? '✅' : '⏳'}</div>
          <div style="font-size:10px;color:var(--text-3)">Onboarding</div>
        </div>
      </div>

      <button type="button" id="acct-save-profile-btn" class="btn btn-primary" style="width:100%;padding:11px;border-radius:10px;font-weight:700;background:var(--accent);color:var(--on-accent);border:none;cursor:pointer">💾 Save Profile</button>
    `;

    const picker = body.querySelector('#acct-avatar-picker');
    AVATAR_EMOJIS.forEach(emoji => {
      const btn = document.createElement('button');
      btn.type = 'button';
      btn.textContent = emoji;
      btn.style.cssText = `width:28px;height:28px;border-radius:7px;background:var(--bg-3);border:2px solid ${(p.avatar || '👤') === emoji ? 'var(--accent)' : 'transparent'};cursor:pointer;font-size:14px`;
      btn.addEventListener('click', () => {
        picker.querySelectorAll('button').forEach(b => b.style.borderColor = 'transparent');
        btn.style.borderColor = 'var(--accent)';
        const disp = document.getElementById('acct-avatar-display');
        if (disp) disp.textContent = emoji;
        disp.dataset.pendingAvatar = emoji;
      });
      picker.appendChild(btn);
    });

    body.querySelector('#acct-upload-picture-btn').addEventListener('click', () => body.querySelector('#acct-avatar-file').click());
    body.querySelector('#acct-avatar-file').addEventListener('change', (e) => {
      const file = e.target.files && e.target.files[0];
      if (!file) return;
      const reader = new FileReader();
      reader.onload = (ev) => {
        const dataUri = ev.target.result;
        const disp = document.getElementById('acct-avatar-display');
        if (disp) { disp.innerHTML = `<img src="${dataUri}" style="width:100%;height:100%;object-fit:cover" alt="">`; disp.dataset.pendingAvatar = dataUri; }
      };
      reader.readAsDataURL(file);
    });

    body.querySelector('#acct-save-profile-btn').addEventListener('click', async () => {
      const disp = document.getElementById('acct-avatar-display');
      const avatar = disp?.dataset.pendingAvatar || p.avatar || '👤';
      const name = body.querySelector('#acct-name').value.trim();
      const email = body.querySelector('#acct-email').value.trim();
      const jobTitle = body.querySelector('#acct-title').value.trim();
      const role = body.querySelector('#acct-role').value;
      const skill = body.querySelector('#acct-skill').value;

      const ok = await patchProfile({name, email, job_title: jobTitle, role, skill_level: skill, avatar});
      if (ok) {
        fireToast('✅ Profile saved!', 'ok', 2000);
        syncTopbarIdentity({name, avatar});
        _state.profile = {..._state.profile, name, email, job_title: jobTitle, role, skill_level: skill, avatar};
      } else {
        fireToast('❌ Could not save profile', 'err', 3000);
      }
    });
  }

  // ── TAB: Preferences (theme, typography, UI mode, sidebar) ─────────
  function renderPreferencesTab(body) {
    const prefs = _state.prefs || {};
    const currentTheme = prefs.theme || (typeof _safeLS !== 'undefined' ? _safeLS.get('agentic_os_theme') : null) || 'light';
    const currentMode = (typeof _UI !== 'undefined' && _UI.uiMode) || (typeof _safeLS !== 'undefined' ? _safeLS.get('agentic_os_mode') : null) || 'simple';
    const currentFontSize = _state.profile?.font_size || 'base';

    body.innerHTML = `
      <div style="margin-bottom:22px">
        <h2 style="margin:0 0 4px;font-size:20px;font-weight:900">🎨 Preferences</h2>
        <p style="margin:0;color:var(--text-2);font-size:12.5px">Theme, workstation complexity, typography, and layout.</p>
      </div>

      <div style="margin-bottom:22px">
        ${fieldLabel('Appearance Theme')}
        <div id="acct-theme-grid" style="display:grid;grid-template-columns:repeat(auto-fit,minmax(110px,1fr));gap:10px;margin-top:8px"></div>
      </div>

      <div style="margin-bottom:22px">
        ${fieldLabel('Workstation Mode')}
        <div style="display:grid;grid-template-columns:1fr 1fr;gap:12px;margin-top:8px">
          <button type="button" id="acct-mode-simple" style="padding:14px;border-radius:12px;border:2px solid ${currentMode === 'simple' ? 'var(--accent)' : 'var(--border)'};background:${currentMode === 'simple' ? 'rgba(91,138,248,.12)' : 'var(--bg-2)'};color:var(--text-0);cursor:pointer;text-align:left">
            <div style="font-size:18px;margin-bottom:4px">⚡</div>
            <div style="font-weight:800;font-size:13px;margin-bottom:2px">Simple</div>
            <div style="font-size:11px;color:var(--text-2)">7 core features only</div>
          </button>
          <button type="button" id="acct-mode-power" style="padding:14px;border-radius:12px;border:2px solid ${currentMode === 'power' ? 'var(--accent)' : 'var(--border)'};background:${currentMode === 'power' ? 'rgba(91,138,248,.12)' : 'var(--bg-2)'};color:var(--text-0);cursor:pointer;text-align:left">
            <div style="font-size:18px;margin-bottom:4px">🌌</div>
            <div style="font-weight:800;font-size:13px;margin-bottom:2px">Power</div>
            <div style="font-size:11px;color:var(--text-2)">All 65+ features</div>
          </button>
        </div>
      </div>

      <div style="display:flex;gap:24px;flex-wrap:wrap;margin-bottom:22px">
        <div>
          ${fieldLabel('Typography Scale')}
          <div style="display:flex;gap:6px" id="acct-fontsize-group">
            ${['sm', 'base', 'lg'].map(s => `<button type="button" class="acct-fs-btn" data-size="${s}" style="padding:7px 14px;border-radius:8px;background:${currentFontSize === s ? 'var(--accent)' : 'var(--bg-3)'};color:${currentFontSize === s ? '#fff' : 'var(--text-0)'};border:1px solid var(--border);cursor:pointer;font-weight:600;font-size:12px">${s === 'sm' ? 'Small' : s === 'base' ? 'Medium' : 'Large'}</button>`).join('')}
          </div>
        </div>
        <div>
          ${fieldLabel('Accessibility')}
          <button type="button" id="acct-high-contrast-btn" style="padding:7px 16px;border-radius:8px;background:var(--bg-3);border:1px solid var(--border-hi);color:var(--text-0);font-weight:700;cursor:pointer;font-size:12px">Toggle High Contrast</button>
        </div>
      </div>

      <div style="background:var(--bg-2);border:1px solid var(--border);border-radius:12px;padding:16px;display:flex;align-items:center;justify-content:space-between;gap:12px;flex-wrap:wrap">
        <div>
          <div style="font-weight:700;font-size:13px;margin-bottom:2px">🎛️ Sidebar & Navigation</div>
          <div style="font-size:11.5px;color:var(--text-2)">Choose which panes show in your sidebar and star your Favorites.</div>
        </div>
        <button type="button" id="acct-customize-sidebar-btn" class="btn-3d btn-sm">Customize Sidebar</button>
      </div>
    `;

    const themeGrid = body.querySelector('#acct-theme-grid');
    THEMES.forEach(t => {
      const btn = document.createElement('button');
      btn.type = 'button';
      btn.style.cssText = `padding:12px 8px;border-radius:10px;border:2px solid ${currentTheme === t.id ? 'var(--accent)' : 'var(--border)'};background:var(--bg-2);color:var(--text-0);cursor:pointer;text-align:center;font-size:12px;font-weight:700`;
      btn.innerHTML = `<div style="font-size:18px;margin-bottom:4px">${t.icon}</div>${esc(t.label)}`;
      btn.addEventListener('click', () => {
        if (typeof window.applyTheme === 'function') window.applyTheme(t.id);
        fireToast(`✨ ${t.label} theme applied`, 'ok', 1800);
        themeGrid.querySelectorAll('button').forEach(b => b.style.borderColor = 'var(--border)');
        btn.style.borderColor = 'var(--accent)';
      });
      themeGrid.appendChild(btn);
    });

    body.querySelector('#acct-mode-simple').addEventListener('click', () => { window.switchUIMode?.('simple'); selectAccountTab('preferences'); fireToast('✨ Simple mode active', 'ok', 1600); });
    body.querySelector('#acct-mode-power').addEventListener('click', () => { window.switchUIMode?.('power'); selectAccountTab('preferences'); fireToast('🌌 Power mode active', 'ok', 1600); });

    body.querySelectorAll('.acct-fs-btn').forEach(btn => {
      btn.addEventListener('click', () => { window.saveFontSize?.(btn.dataset.size); selectAccountTab('preferences'); });
    });

    body.querySelector('#acct-high-contrast-btn').addEventListener('click', () => window.toggleHighContrastTheme?.());
    body.querySelector('#acct-customize-sidebar-btn').addEventListener('click', () => {
      // NOTE: previously this called window.closeAccountSettings() which
      // REMOVES the modal from the DOM entirely, so there was nothing to
      // "go back to" once the sidebar customizer was closed. Instead, hide
      // it (keep it in the DOM) and let showSidebarCustomizer() restore it
      // when the customizer itself closes — see window.restoreAccountSettings.
      const modal = document.getElementById('account-settings-modal');
      if (modal) modal.style.display = 'none';
      document.removeEventListener('keydown', accountSettingsEscHandler);
      window.showSidebarCustomizer?.();
    });
  }

  // ── TAB: Notifications ───────────────────────────────────────────────
  function renderNotificationsTab(body) {
    const n = (_state.profile && _state.profile.notifications) || {};
    const items = [
      {key: 'agent_complete', label: 'Agent completes a task', checked: n.agent_complete !== false},
      {key: 'hitl_interrupt', label: 'Human review needed', checked: n.hitl_interrupt !== false},
      {key: 'daily_summary', label: 'Daily summary email', checked: n.daily_summary === true},
      {key: 'sound', label: 'Sound effects', checked: n.sound !== false},
    ];
    body.innerHTML = `
      <div style="margin-bottom:22px">
        <h2 style="margin:0 0 4px;font-size:20px;font-weight:900">🔔 Notifications</h2>
        <p style="margin:0;color:var(--text-2);font-size:12.5px">Choose what you want to be notified about.</p>
      </div>
      <div style="display:flex;flex-direction:column;gap:2px">
        ${items.map(it => `
          <label style="display:flex;align-items:center;justify-content:space-between;padding:12px 4px;border-bottom:1px solid var(--border);cursor:pointer">
            <span style="font-size:13px;color:var(--text-1)">${esc(it.label)}</span>
            <input type="checkbox" class="acct-notif-toggle" data-key="${it.key}" ${it.checked ? 'checked' : ''} style="width:17px;height:17px;cursor:pointer;accent-color:var(--accent-text)">
          </label>`).join('')}
      </div>
      <button type="button" id="acct-save-notifs-btn" class="btn btn-primary" style="width:100%;padding:11px;border-radius:10px;font-weight:700;background:var(--accent);color:var(--on-accent);border:none;cursor:pointer;margin-top:20px">💾 Save Notification Preferences</button>
    `;
    body.querySelector('#acct-save-notifs-btn').addEventListener('click', async () => {
      const notifs = {};
      body.querySelectorAll('.acct-notif-toggle').forEach(t => { notifs[t.dataset.key] = t.checked; });
      const ok = await patchProfile({notifications: notifs});
      fireToast(ok ? '✅ Notification preferences saved!' : '❌ Could not save', ok ? 'ok' : 'err', 2200);
      if (ok) _state.profile.notifications = notifs;
    });
  }

  // ── TAB: Workspace & Branding ────────────────────────────────────────
  function renderWorkspaceTab(body) {
    const prefs = _state.prefs || {};
    body.innerHTML = `
      <div style="margin-bottom:22px">
        <h2 style="margin:0 0 4px;font-size:20px;font-weight:900">🏷️ Workspace & Branding</h2>
        <p style="margin:0;color:var(--text-2);font-size:12.5px">Customize the name shown in your topbar and browser tab.</p>
      </div>

      <div style="margin-bottom:20px">
        ${fieldLabel('Workspace / App Name')}
        <input id="acct-workspace-name" type="text" value="${esc(prefs.workspace_name || '')}" placeholder="e.g. Strick Tech Command Center" style="${textInputStyle()}">
        <div style="font-size:11px;color:var(--text-3);margin-top:6px">Shown in the topbar title and browser tab.</div>
      </div>

      <button type="button" id="acct-save-workspace-btn" class="btn btn-primary" style="width:100%;padding:11px;border-radius:10px;font-weight:700;background:var(--accent);color:var(--on-accent);border:none;cursor:pointer;margin-bottom:24px">💾 Save Workspace Name</button>

      <div style="display:flex;flex-direction:column;gap:2px">
        ${[
          {icon: '🎯', label: 'Restart Product Tour', action: 'restartTour'},
          {icon: '📖', label: 'Documentation', action: 'openDocs'},
        ].map(it => `<button type="button" class="acct-quicklink-btn" data-action="${it.action}" style="width:100%;display:flex;align-items:center;gap:10px;padding:11px 10px;background:none;border:none;border-radius:8px;color:var(--text-1);cursor:pointer;font-size:13px;text-align:left"><span>${it.icon}</span><span>${esc(it.label)}</span></button>`).join('')}
      </div>
    `;

    body.querySelector('#acct-save-workspace-btn').addEventListener('click', async () => {
      const appName = body.querySelector('#acct-workspace-name').value.trim() || 'Agentic OS';
      // NOTE: workspace_name genuinely lives on /api/onboarding/preferences,
      // NOT /api/profile — the old "Identity & Branding" panel wrote this
      // field to /api/profile, where it was silently ignored/never persisted.
      const ok = await patchPrefs({workspace_name: appName});
      if (ok) {
        fireToast('✅ Workspace name saved!', 'ok', 2000);
        const titleEl = document.getElementById('custom-app-title');
        if (titleEl) titleEl.innerHTML = `${esc(appName)} <span style="color:var(--accent-text)">Agentic OS</span>`;
        if (document.title) document.title = `${appName} Agentic OS — Mission Control`;
        _state.prefs.workspace_name = appName;
      } else {
        fireToast('❌ Could not save workspace name', 'err', 3000);
      }
    });

    body.querySelectorAll('.acct-quicklink-btn').forEach(btn => {
      btn.addEventListener('mouseover', () => btn.style.background = 'var(--bg-3)');
      btn.addEventListener('mouseout', () => btn.style.background = 'none');
      btn.addEventListener('click', () => {
        const action = btn.dataset.action;
        if (action === 'restartTour') { window.closeAccountSettings(); window.startTour?.(); }
        if (action === 'openDocs') { window.closeAccountSettings(); window.nav?.('docs'); }
      });
    });
  }

  // ── TAB: Plan ─────────────────────────────────────────────────────────
  function renderPlanTab(body) {
    const lic = _state.license || {};
    const tierColors = {free: 'var(--text-3)', trial: 'var(--accent)', pro: 'var(--accent)', enterprise: '#f0c060'};
    const tierColor = tierColors[lic.tier || 'trial'] || 'var(--accent)';
    body.innerHTML = `
      <div style="margin-bottom:22px">
        <h2 style="margin:0 0 4px;font-size:20px;font-weight:900">💳 Plan</h2>
        <p style="margin:0;color:var(--text-2);font-size:12.5px">Your current tier and available upgrades.</p>
      </div>

      <div style="background:var(--bg-2);border:1px solid var(--border-hi);border-radius:14px;padding:20px;margin-bottom:20px">
        <div style="display:flex;align-items:center;justify-content:space-between;margin-bottom:8px">
          <span style="font-size:18px;font-weight:900;color:${tierColor}">${esc((lic.tier || 'trial').toUpperCase())}</span>
          ${lic.is_trial && lic.trial_days_left > 0 ? `<span style="font-size:12px;color:var(--text-2)">⏰ ${lic.trial_days_left} days left</span>` : ''}
        </div>
        ${lic.is_trial ? `<p style="font-size:12.5px;color:var(--text-2);margin:0 0 14px">You're on a trial with full feature access. Upgrade anytime to keep it after the trial ends.</p>` : `<p style="font-size:12.5px;color:var(--text-2);margin:0 0 14px">Thanks for being a ${esc(lic.tier || '')} member.</p>`}
        <button type="button" id="acct-view-plans-btn" class="btn btn-primary" style="width:100%;padding:10px;border-radius:9px;font-weight:700;background:var(--accent);color:var(--on-accent);border:none;cursor:pointer">View Upgrade Options</button>
      </div>

      <div style="font-size:11.5px;color:var(--text-3)">Org: ${esc(lic.org || '—')} &middot; Account: ${esc(lic.user_email || '—')}</div>
    `;
    body.querySelector('#acct-view-plans-btn').addEventListener('click', () => { window.closeAccountSettings(); window.showTierPlans?.(); });
  }

  // ── Sync topbar avatar/name after saving ───────────────────────────
  function syncTopbarIdentity({name, avatar}) {
    const avEl = document.getElementById('topbar-user-avatar');
    if (avEl) {
      if (avatar && avatar.startsWith('data:')) avEl.innerHTML = `<img src="${avatar}" style="width:20px;height:20px;border-radius:50%;object-fit:cover" alt="">`;
      else avEl.textContent = avatar || '👤';
    }
  }

  // ══════════════════════════════════════════════════════════════════
  //  TOPBAR: single entry point — replace both old buttons
  // ══════════════════════════════════════════════════════════════════
  function installUnifiedAccountButton() {
    // Remove the old "Me" pill entirely — its Identity & Branding content
    // now lives in Account Settings → Workspace & Branding / Profile tabs.
    const oldMeBtn = document.getElementById('profile-btn');
    if (oldMeBtn) oldMeBtn.remove();

    // Repoint the existing avatar icon (#user-identity-hub) at the new modal.
    const hub = document.getElementById('user-identity-hub');
    if (hub) {
      hub.setAttribute('title', 'Account Settings');
      hub.onclick = function () { window.openAccountSettings(); };
    } else {
      setTimeout(installUnifiedAccountButton, 500);
    }
  }

  // Old global entry points now redirect into the unified modal so any
  // remaining callers (keyboard shortcuts, other code paths) still work.
  window.showUserProfile = function () { window.openAccountSettings('profile'); };
  window.openUserProfileModal = function () { window.openAccountSettings('profile'); };
  window.openProfilePanel = function () { window.openAccountSettings('profile'); };

  // Restored from the old 04-workflow-specs.js "USER PROFILE PANEL" block —
  // still called from loadUIConfig() on boot to apply the saved font size.
  window.applyProfileTheme = function (profile) {
    if (!profile) return;
    const size = {sm: '12px', base: '14px', lg: '16px'}[profile.font_size] || '14px';
    document.documentElement.style.setProperty('--text-base', size);
  };

  setTimeout(installUnifiedAccountButton, 900);

  console.debug('%c✅ Unified Account Settings loaded (Profile + Identity/Branding merged)', 'color:#4cc98a;font-weight:bold');
})();
