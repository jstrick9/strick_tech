// Agentic OS — named handlers for the CSP migration's long tail
// ───────────────────────────────────────────────────────────────────────────
// Phase 2 converted 1029 of 1107 inline handlers mechanically. The remainder
// were bodies whose meaning could not be PROVEN from their text — variable
// declarations, arbitrary expressions, chained promises. The migration tool
// deliberately refused to guess at those, because a wrong guess produces a
// control that looks present and silently does nothing.
//
// This file gives each of them a real named function, so the attribute becomes
// a plain call the delegation shim can dispatch. Behaviour is preserved
// exactly, except where the original was already broken — noted inline.
(function () {
  'use strict';

  function byId(id) { return document.getElementById(id); }

  function on(name, fn) {
    // Defined on window so the shim can resolve them by name.
    window[name] = fn;
  }

  // ── Chat / core ────────────────────────────────────────────────────────
  on('hNavChat', function () { window.nav('chat'); });

  on('hPersonaChange', function (select) {
    if (typeof window.selectChatPersona === 'function') {
      window.selectChatPersona(select.value);
    }
    // Closes the <details> wrapper the <select> sits inside.
    var wrap = select.parentElement && select.parentElement.parentElement;
    if (wrap) wrap.removeAttribute('open');
  });

  on('hClickFileInput', function () {
    var el = byId('chat-file-input');
    if (el) el.click();
  });

  on('hClickElement', function (id) {
    var el = byId(id);
    if (el) el.click();
  });

  on('hSetActiveAgentFromChat', function (agent) {
    window.setActiveAgent(agent);
    var empty = byId('chat-empty');
    if (empty) empty.style.display = 'none';
  });

  on('hOpenStudioPreview', function () {
    if (typeof window.openExternalLink === 'function'
        && typeof window.studioPreviewUrl === 'function') {
      window.openExternalLink(location.origin + window.studioPreviewUrl());
    }
  });

  on('hStudioZoomIn', function () { window.studioZoom(10); });

  on('hNoviceApiGuide', function () {
    if (typeof window.showNoviceApiGuide === 'function') {
      window.showNoviceApiGuide();
    } else if (typeof window.openExternalLink === 'function') {
      window.openExternalLink('https://openrouter.ai/keys');
    }
  });

  // ── Settings / connections ─────────────────────────────────────────────
  on('hOllamaModelChange', function (select) {
    var inp = byId('ollama-custom-pull-inp');
    if (inp) inp.style.display = select.value === 'custom' ? 'block' : 'none';
  });

  on('hSetCustomBaseUrl', function (url) {
    var el = byId('custom-api-base-url');
    if (el) el.value = url;
    if (typeof window.saveCustomConnection === 'function') {
      window.saveCustomConnection();
    }
  });

  on('hExpandSidebar', function () {
    var sb = byId('sidebar');
    if (sb) {
      sb.style.width = '260px';
      sb.classList.remove('collapsed');
      try { localStorage.setItem('agentic_os_sidebar_w', '260px'); } catch (e) { /* private mode */ }
    }
    window.toast('Sidebar reset to default 260px');
  });

  on('hNoop', function () { /* attribute exists only for data-prevent/data-hover */ });

  on('hSetGroqPreset', function () {
    var url = byId('custom-api-base-url');
    if (url) url.value = 'https://api.groq.com/openai/v1';
    var key = byId('custom-api-key');
    if (key) key.focus();
  });

  // The split-pane resizer keeps its hover colour WHILE a drag is in
  // progress, so this cannot be a plain data-hover-out.
  on('hSplitResizerOut', function (el) {
    if (!window._isSplitResizing) el.style.background = 'var(--border)';
  });

  on('hSetBorder', function (el, colour) { if (el) el.style.borderColor = colour; });

  on('hHideSelf', function (el) { if (el) el.style.display = 'none'; });

  // ── Agents ─────────────────────────────────────────────────────────────
  // setActiveAgent used to receive the whole agent object serialised into the
  // attribute. The object now travels in a data attribute as JSON, so the
  // markup carries data, never code.
  on('hSetActiveAgent', function (agent) { window.setActiveAgent(agent); });

  on('hSetActiveAgentAndClose', function (agent) {
    window.setActiveAgent(agent);
    if (typeof window.closePalette === 'function') window.closePalette();
  });

  // ── Studio / console ───────────────────────────────────────────────────
  on('hClearConsole', function () {
    window.consoleMessages = [];
    if (typeof window.updateConsolePanel === 'function') {
      window.updateConsolePanel();
    }
  });

  on('hSaveNoviceKey', function () {
    var k = byId('novice-guide-key-inp');
    var key = k && k.value ? k.value.trim() : '';
    if (!key) {
      window.toast('Please paste your sk-or-v1-... key first', 'warn');
      return;
    }
    var o = byId('or-key-input');
    if (o) o.value = key;
    var modal = byId('novice-api-guide-modal');
    if (modal) modal.remove();
    window.saveApiKey();
  });

  on('hInsertAndClose', function (text) {
    window.insertCmd('Tell me about: ' + text);
    if (typeof window.closePalette === 'function') window.closePalette();
  });

  on('hTourPrev', function () { window.tourStep--; window.showTourStep(); });
  on('hTourNext', function () { window.tourStep++; window.showTourStep(); });

  // ── Workflow / multi-tab ───────────────────────────────────────────────
  on('hDeleteSelectedNode', function () { window.wfDeleteNode(window._wfSelected); });

  on('hMarkDirty', function (el) { el.style.color = 'var(--warning)'; });

  on('hNavigateFromUrlBar', function () {
    var el = byId('mt-url-bar');
    if (el) window.mtNavigate(el.value);
  });

  on('hActivateTabAndGrid', function (tabId) {
    window.mtActivateTab(tabId);
    var g = byId('mt-grid-btn');
    if (g) g.click();
  });

  on('hHideTauriBuild', function () {
    var s = byId('tauri-build-section');
    if (s) s.style.display = 'none';
  });

  on('hCloseOnboarding', function () {
    if (typeof window.closeOnboardingModal === 'function') {
      window.closeOnboardingModal();
    } else {
      var o = byId('onboarding-overlay');
      if (o) o.remove();
    }
  });

  // ── Voice ──────────────────────────────────────────────────────────────
  // The original attribute was NOT valid JavaScript:
  //   .then(().catch(()=>{})=>this.closest(...).remove())
  // `().catch(()=>{})=>` is a syntax error, so clicking "Clear History" threw
  // at parse time and the button did nothing at all. Presumably a botched
  // edit that shipped because a broken inline handler produces no build error
  // and no console output until the moment it is clicked. Restored to the
  // evident intent: delete, close the panel, confirm.
  on('hClearVoiceHistory', function (el) {
    var panel = el.closest('[style*=fixed]');
    fetch('/api/voice/history', { method: 'DELETE' })
      .then(function () {
        if (panel) panel.remove();
        window.showToast('🗑 History cleared');
      })
      .catch(function () {
        window.showToast('Could not clear history', 'err');
      });
  });

  // ── Clipboard ──────────────────────────────────────────────────────────
  on('hCopyText', function (text, message) {
    navigator.clipboard.writeText(text == null ? '' : String(text)).then(function () {
      var toast = window.showToast || window.toast;
      if (toast) toast(message || 'Copied!', 'ok', 1200);
    });
  });

  on('hCopyLastCommitMsg', function () {
    window.hCopyText(window._gitaiLastCommitMsg || '', '📋 Copied');
  });

  on('hCopyWebhookUrl', function (id) {
    window.hCopyText(
      location.origin + '/api/webhooks/' + encodeURIComponent(id) + '/trigger',
      '📋 Copied'
    );
  });

  // ── Field setters ──────────────────────────────────────────────────────
  on('hSetFieldValue', function (fieldId, value) {
    var el = byId(fieldId);
    if (el) el.value = value;
  });

  on('hSetFieldAndRun', function (fieldId, value, fnName) {
    window.hSetFieldValue(fieldId, value);
    var fn = window[fnName];
    if (typeof fn === 'function') fn();
  });

  on('hRememberImagePrompt', function (value) { window._imgLastPrompt = value; });

  on('hUpperSnakeCase', function (el) {
    el.value = el.value.toUpperCase().replace(/[^A-Z0-9_]/g, '');
  });

  on('hToggleVaultReveal', function (checkbox) {
    var el = byId('vault-value-input');
    if (el) el.type = checkbox.checked ? 'text' : 'password';
  });

  on('hPriorityInput', function (value) {
    var el = byId('prb-f-priority-val');
    if (el) el.textContent = value;
    if (typeof window.prbUpdatePreview === 'function') window.prbUpdatePreview();
  });

  on('hTogglePolicyEnabled', function (policyId, enabledStr) {
    window.prbToggleEnabled(policyId, enabledStr === 'true');
  });

  // ── Panel re-renders ───────────────────────────────────────────────────
  on('hResetConflicts', function () {
    window._prbConflicts = null;
    window.prbRenderConflictsTab(byId('prb-content'));
  });

  on('hResetDriftSelection', function () {
    window._driftSelected = null;
    window.bddRenderAgents(byId('bdd-content'));
  });

  on('hRenderA2ATasks', function () { window.a2aRenderTasks(byId('a2a-content')); });

  on('hSearchMarketplace', function () {
    var el = byId('mkt-search');
    if (el) window.mktSearch(el.value);
  });

  on('hRunSqlDryRun', function () { window.runSQL({ dryRun: true }); });

  on('hZoomOut', function (fnName) {
    var fn = window[fnName];
    if (typeof fn === 'function') fn(1 / 1.2);
  });

  on('hDownloadMarketplacePack', function (packId) {
    window.open(
      '/api/marketplace/' + encodeURIComponent(packId) + '/download', '_blank'
    );
  });

  on('hInstallAndClose', function (packId, name, isInstalled, el) {
    window.mktInstallOrUninstall(packId, name, isInstalled);
    var panel = el && el.closest ? el.closest('[style*="fixed"]') : null;
    if (panel) panel.remove();
  });

  on('hGitaiRunLastQuery', function () {
    window.gitaiNLExecute(window._gitaiLastQuery);
  });

  on('hCloseFixedPanel', function (el) {
    var panel = el && el.closest ? el.closest('[style*="fixed"]') : null;
    if (panel) panel.remove();
  });
})();

// Skip-link target focus.
//
// A bare href="#content" scrolls but does NOT move focus in most browsers, so
// the next Tab continues from the link -- back into the chrome the user just
// asked to skip. Moving focus explicitly is the whole point of the pattern.
window.skipTo = function (id) {
  var el = document.getElementById(id);
  if (!el) return;
  if (!el.hasAttribute('tabindex')) el.setAttribute('tabindex', '-1');
  try { el.focus({ preventScroll: false }); } catch (e) { el.focus(); }
  if (typeof el.scrollIntoView === 'function') {
    el.scrollIntoView({ block: 'start', behavior: 'auto' });
  }
};
