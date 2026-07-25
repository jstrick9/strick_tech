// Agentic OS — Onboarding Wizard
// Extracted from 01-app-core.js for modularity
// ── Onboarding Wizard ─────────────────────────────────────────────
let obStep = 0, obSteps = [], obPrefs = {};

async function checkOnboarding() {
  try {
    if (_safeLS.get('agentic_os_onboarded') === 'true' || window._onboardingDismissed) return;
    const r = await fetch('/api/onboarding/status');
    if (!r.ok) return;
    const s = await r.json();
    if (!s.complete) {
      const sr = await fetch('/api/onboarding/steps');
      if (!sr.ok) return;
      obSteps  = await sr.json();
      obPrefs  = {};
      obStep   = 0;
      showOnboarding();
    } else {
      // Load preferences and apply theme
      const pr = await fetch('/api/onboarding/preferences');
      if (!pr.ok) return;
      const p  = await pr.json();
      applyPreferences(p);
    }
  } catch(e) {
    console.warn('[Onboarding] checkOnboarding error:', e);
  }
}

function showOnboarding() {
  if (!obSteps.length) return;
  const step = obSteps[Math.min(obStep, obSteps.length-1)];
  const total = obSteps.length;

  document.getElementById('ob-icon').textContent    = ['🧠','🔑','🏠','🤖','📋','🎨','🚀'][obStep] || '⚙️';
  document.getElementById('ob-title').textContent   = step.title;
  document.getElementById('ob-subtitle').textContent = step.subtitle || '';
  document.getElementById('ob-body').textContent    = step.body;
  document.getElementById('ob-counter').textContent = `Step ${obStep+1} of ${total}`;

  // Progress dots
  document.getElementById('ob-dots').innerHTML = obSteps.map((_,i) =>
    `<div style="width:8px;height:8px;border-radius:50%;background:${i===obStep?'var(--accent)':i<obStep?'var(--green)':'var(--bg-4)'}"></div>`
  ).join('');

  // Input area
  const inputWrap = document.getElementById('ob-input-area');
  const inp       = document.getElementById('ob-input');
  const themeArea = document.getElementById('ob-theme-area');
  const agentsArea = document.getElementById('ob-agents-area');
  inputWrap.style.display  = 'none';
  themeArea.style.display  = 'none';
  agentsArea.style.display = 'none';

  if (step.id === 'api_key') {
    inputWrap.style.display = 'block';
    inp.type        = 'password';
    inp.placeholder = 'sk-or-v1-…';
    inp.value       = '';
  } else if (step.id === 'workspace') {
    inputWrap.style.display = 'block';
    inp.type        = 'text';
    inp.placeholder = 'e.g. My AI Agency, Solo Founder OS…';
    inp.value       = obPrefs.workspace_name || '';
    setTimeout(() => inp.focus(), 100);
  } else if (step.id === 'agents') {
    agentsArea.style.display = 'block';
    agentsArea.innerHTML = S.agents.slice(0,6).map(a =>
      `<div style="display:flex;align-items:center;gap:10px;padding:8px;background:var(--bg-3);border-radius:var(--radius-sm);margin-bottom:6px">
        <span style="font-size:20px">${a.avatar||'🤖'}</span>
        <div><div style="font-weight:600;font-size:13px">${escHtml(a.name)}</div>
        <div style="font-size:11px;color:var(--text-2)">${escHtml(a.role||'')}</div></div>
        <span class="tag" style="margin-left:auto">${a.model||'default'}</span>
      </div>`).join('');
  } else if (step.id === 'theme') {
    themeArea.style.display = 'flex';
    const themes = [
      {id:'dark',    name:'Dark',     bg:'#08090e', accent:'#5b8af8'},
      {id:'midnight',name:'Midnight', bg:'#050810', accent:'#9d74f5'},
      {id:'forest',  name:'Forest',   bg:'#0a100d', accent:'#4cc98a'},
      {id:'ember',   name:'Ember',    bg:'#100a08', accent:'#f08850'},
      {id:'ocean',   name:'Ocean',    bg:'#080d10', accent:'#38c5d8'},
    ];
    themeArea.innerHTML = themes.map(t => `
      <div onclick="selectObTheme(${JSON.stringify(t.id)},${JSON.stringify(t.accent)})"
           id="ob-theme-${t.id}"
           style="cursor:pointer;border-radius:10px;padding:10px 14px;border:2px solid ${obPrefs.theme===t.id?t.accent:'var(--border)'};background:${t.bg};text-align:center;transition:var(--transition)">
        <div style="width:32px;height:32px;border-radius:50%;background:${t.accent};margin:0 auto 6px"></div>
        <div style="font-size:12px;color:#ccc;font-weight:600">${t.name}</div>
      </div>`).join('');
  }

  // Back button
  document.getElementById('ob-back').style.display = obStep > 0 ? 'inline-flex' : 'none';
  // Skip button
  document.getElementById('ob-skip').style.display = step.skip ? 'inline-flex' : 'none';
  // Next button label
  const nextBtn = document.getElementById('ob-next');
  nextBtn.textContent = obStep === obSteps.length - 1 ? '🚀 Start Building' : 'Next →';

  document.getElementById('onboarding-modal').style.display = 'flex';
}

function selectObTheme(id, accent) {
  obPrefs.theme = id; obPrefs.accent_color = accent;
  document.querySelectorAll('[id^="ob-theme-"]').forEach(el => {
    el.style.borderColor = el.id.endsWith(id) ? accent : 'var(--border)';
  });
  applyTheme(id, accent);
}

async function obNext(skip = false) {
  const step = obSteps[obStep];
  if (!skip) {
    // Collect value
    const inp = document.getElementById('ob-input');
    if (inp) {
      if (step.id === 'api_key' && inp.value.trim()) {
        obPrefs.api_key = inp.value.trim();
      } else if (step.id === 'workspace' && inp.value.trim()) {
        obPrefs.workspace_name = inp.value.trim();
      }
    }
  }
  obStep++;
  if (obStep >= obSteps.length || skip === true) {
    // Complete immediately so modal always dismisses
    closeOnboardingModal();
    try {
      fetch('/api/onboarding/complete', {
        method:'POST', headers:{'Content-Type':'application/json'},
        body: JSON.stringify(obPrefs)
      }).then(r => r.json()).then(j => {
        applyPreferences(j.preferences || obPrefs);
        if (obPrefs.workspace_name) {
          const sbVer = document.getElementById('sb-version');
          if (sbVer) sbVer.textContent = `Agentic OS — ${obPrefs.workspace_name}`;
        }
      }).catch(()=>{});
    } catch(ex) {}
    showToast('🚀 Welcome to Agentic OS!');
  } else {
    showOnboarding();
  }
}

window.closeOnboardingModal = function() {
  const modal = document.getElementById('onboarding-modal');
  if (modal) {
    modal.style.display = 'none';
    if (modal.parentNode) modal.parentNode.removeChild(modal);
  }
  const overlay = document.getElementById('onboarding-overlay');
  if (overlay) {
    overlay.style.display = 'none';
    if (overlay.parentNode) overlay.parentNode.removeChild(overlay);
  }
  try { try { _safeLS.set('agentic_os_onboarded', 'true'); } catch {} } catch(e) {}
  try { if (window.nav) nav('chat'); } catch(e) {}
};

window.addEventListener('keydown', function(e) {
  if (e.key === 'Escape') {
    if (document.getElementById('onboarding-modal') || document.getElementById('onboarding-overlay')) {
      window.closeOnboardingModal();
    }
  }
});

function obBack() {
  if (obStep > 0) { obStep--; showOnboarding(); }
}

