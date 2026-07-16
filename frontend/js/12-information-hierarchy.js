/*
 * Agentic OS — Information Hierarchy Engine (frontend/js/12-information-hierarchy.js)
 * Implements Strick Tech's 2-Tier Architecture (Universal Context + IVREN Project Deltas).
 */
(function() {
  'use strict';

  let currentHierarchyTab = 'tier1';
  let currentTier1File = 'about_me';
  let currentTier2Project = null;
  let currentIvrenSection = 'instructions';
  let tier1Cache = {};
  let tier2Cache = {};

  async function renderHierarchyPane() {
    try {
      const r = await fetch('/api/hierarchy/status');
      const data = await r.json();
      if (data.ok) {
        const pcountEl = document.getElementById('h-project-count');
        if (pcountEl) pcountEl.textContent = data.project_count || 0;
        
        // Populate project list if Tier 2 projects exist
        if (data.projects && data.projects.length > 0) {
          renderProjectList(data.projects);
          if (!currentTier2Project) {
            currentTier2Project = data.projects[0].project_id;
          }
        }
      }
      if (currentHierarchyTab === 'tier1') {
        await loadTier1File(currentTier1File);
      } else {
        await loadIvrenSection(currentTier2Project, currentIvrenSection);
      }
    } catch(err) {
      console.warn('Render Hierarchy Pane error:', err);
      if (window.showPaneError) window.showPaneError('hierarchy', err);
    }
  }

  window.switchHierarchyTab = function(tab) {
    currentHierarchyTab = tab;
    document.getElementById('h-tab-tier1').classList.toggle('active', tab === 'tier1');
    document.getElementById('h-tab-tier2').classList.toggle('active', tab === 'tier2');
    document.getElementById('h-tab-tier1').style.borderBottom = tab === 'tier1' ? '2px solid var(--accent)' : '2px solid transparent';
    document.getElementById('h-tab-tier1').style.color = tab === 'tier1' ? 'var(--text-0)' : 'var(--text-2)';
    document.getElementById('h-tab-tier2').style.borderBottom = tab === 'tier2' ? '2px solid var(--accent)' : '2px solid transparent';
    document.getElementById('h-tab-tier2').style.color = tab === 'tier2' ? 'var(--text-0)' : 'var(--text-2)';

    document.getElementById('h-view-tier1').style.display = tab === 'tier1' ? 'flex' : 'none';
    document.getElementById('h-view-tier2').style.display = tab === 'tier2' ? 'flex' : 'none';

    if (tab === 'tier1') {
      loadTier1File(currentTier1File);
    } else {
      loadIvrenSection(currentTier2Project, currentIvrenSection);
    }
  };

  window.selectTier1File = async function(fileKey) {
    currentTier1File = fileKey;
    document.querySelectorAll('.t1-file-item').forEach(el => {
      el.style.background = 'transparent';
      el.style.border = '1px solid transparent';
    });
    const activeEl = document.getElementById('t1-item-' + fileKey);
    if (activeEl) {
      activeEl.style.background = 'rgba(91,138,248,.1)';
      activeEl.style.border = '1px solid var(--border-hi)';
    }
    await loadTier1File(fileKey);
  };

  async function loadTier1File(fileKey) {
    const titleMap = {
      'about_me': 'about_me.md (Who I am & My Mission)',
      'about_my_business': 'about_my_business.md (Company, ICP & Unique Value)',
      'about_my_voice': 'about_my_voice.md (Tone, Words to Love/Avoid — Highest Leverage)',
      'about_my_offers': 'about_my_offers.md (Core Products, Pricing & Deliverables)'
    };
    const titleEl = document.getElementById('t1-editor-title');
    if (titleEl) titleEl.textContent = 'Editing: ' + (titleMap[fileKey] || fileKey + '.md');

    try {
      const r = await fetch('/api/hierarchy/tier1');
      const data = await r.json();
      if (data.ok) {
        tier1Cache = data;
        const textarea = document.getElementById('t1-editor-textarea');
        if (textarea) textarea.value = data[fileKey] || '';
        if (typeof updateLiveHierarchySplitPreview === 'function') updateLiveHierarchySplitPreview();
      }
    } catch(err) {
      console.warn('Load Tier1 error:', err);
    }
  }

  window.saveCurrentTier1File = async function() {
    const textarea = document.getElementById('t1-editor-textarea');
    if (!textarea) return;
    const content = textarea.value;
    const payload = {};
    payload[currentTier1File] = content;

    try {
      const r = await fetch('/api/hierarchy/tier1', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify(payload)
      });
      const data = await r.json();
      if (data.ok) {
        if (window.toast) toast('✅ Saved ' + currentTier1File + '.md to Universal Context!', 'ok', 3000);
        tier1Cache[currentTier1File] = content;
      } else {
        if (window.toast) toast('Error saving file: ' + data.detail, 'err');
      }
    } catch(err) {
      if (window.toast) toast('Network error saving file', 'err');
    }
  };

  function renderProjectList(projects) {
    const listEl = document.getElementById('t2-project-list');
    if (!listEl) return;
    listEl.innerHTML = projects.map(p => {
      const pid = p.project_id || p.name;
      const name = p.meta?.name || pid;
      const isSelected = currentTier2Project === pid;
      return `<div onclick="selectTier2Project('${pid}')" id="t2-proj-item-${pid}" style="padding:9px 12px;border-radius:var(--radius-sm);cursor:pointer;background:${isSelected ? 'rgba(91,138,248,.1)' : 'transparent'};border:1px solid ${isSelected ? 'var(--border-hi)' : 'transparent'};font-size:13px;font-weight:${isSelected ? 700 : 500};display:flex;align-items:center;justify-content:space-between">
        <span style="white-space:nowrap;overflow:hidden;text-overflow:ellipsis">📁 ${escHtml(name)}</span>
      </div>`;
    }).join('');
  }

  window.selectTier2Project = async function(pid) {
    currentTier2Project = pid;
    document.querySelectorAll('#t2-project-list > div').forEach(el => {
      el.style.background = 'transparent';
      el.style.border = '1px solid transparent';
      el.style.fontWeight = '500';
    });
    const activeEl = document.getElementById('t2-proj-item-' + pid);
    if (activeEl) {
      activeEl.style.background = 'rgba(91,138,248,.1)';
      activeEl.style.border = '1px solid var(--border-hi)';
      activeEl.style.fontWeight = '700';
    }
    await loadIvrenSection(pid, currentIvrenSection);
  };

  window.switchIvrenSection = async function(sec) {
    currentIvrenSection = sec;
    document.querySelectorAll('.ivren-tab').forEach(el => {
      el.style.borderBottom = '2px solid transparent';
      el.style.color = 'var(--text-2)';
    });
    const activeTab = document.getElementById('ivren-tab-' + sec);
    if (activeTab) {
      activeTab.style.borderBottom = '2px solid var(--accent)';
      activeTab.style.color = 'var(--text-0)';
    }

    const appendBar = document.getElementById('t2-notes-append-bar');
    if (appendBar) appendBar.style.display = sec === 'notes' ? 'flex' : 'none';

    await loadIvrenSection(currentTier2Project, sec);
  };

  async function loadIvrenSection(pid, sec) {
    if (!pid) {
      const textarea = document.getElementById('t2-ivren-textarea');
      if (textarea) textarea.value = '# No Project Selected\nClick "+ New Project Hierarchy" to get started.';
      return;
    }
    const titleEl = document.getElementById('t2-project-title');
    if (titleEl) titleEl.textContent = pid.replace(/_/g, ' ').toUpperCase() + ' — ' + sec.toUpperCase();

    try {
      const r = await fetch('/api/hierarchy/projects/' + encodeURIComponent(pid));
      const data = await r.json();
      if (data.ok && data.ivren) {
        tier2Cache[pid] = data.ivren;
        const textarea = document.getElementById('t2-ivren-textarea');
        if (textarea) textarea.value = data.ivren[sec] || '';
        if (typeof updateLiveHierarchySplitPreview === 'function') updateLiveHierarchySplitPreview();
      }
    } catch(err) {
      console.warn('Load IVREN error:', err);
    }
  }

  window.saveCurrentIvrenSection = async function() {
    if (!currentTier2Project) return;
    const textarea = document.getElementById('t2-ivren-textarea');
    if (!textarea) return;
    const content = textarea.value;
    const payload = {};
    payload[currentIvrenSection] = content;

    try {
      const r = await fetch('/api/hierarchy/projects/' + encodeURIComponent(currentTier2Project) + '/save', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify(payload)
      });
      const data = await r.json();
      if (data.ok) {
        if (window.toast) toast('✅ Saved IVREN section: ' + currentIvrenSection + ' for project ' + currentTier2Project, 'ok', 3000);
      } else {
        if (window.toast) toast('Error saving section: ' + data.detail, 'err');
      }
    } catch(err) {
      if (window.toast) toast('Network error saving IVREN section', 'err');
    }
  };

  window.appendNoteToCurrentProject = async function() {
    if (!currentTier2Project) return;
    const inputEl = document.getElementById('t2-notes-input');
    if (!inputEl || !inputEl.value.trim()) return;
    const noteText = inputEl.value.trim();

    try {
      const r = await fetch('/api/hierarchy/projects/' + encodeURIComponent(currentTier2Project) + '/notes/append', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ note: noteText, author: 'user' })
      });
      const data = await r.json();
      if (data.ok) {
        inputEl.value = '';
        if (window.toast) toast('📈 Compounding Feedback Note Logged!', 'ok', 3000);
        await loadIvrenSection(currentTier2Project, 'notes');
      }
    } catch(err) {
      if (window.toast) toast('Error appending feedback note', 'err');
    }
  };

  // ── Modals & Wizards ────────────────────────────────────────────────────────
  window.openHierarchyInterview = function() {
    let modal = document.getElementById('hierarchy-interview-modal');
    if (!modal) {
      modal = document.createElement('div');
      modal.id = 'hierarchy-interview-modal';
      modal.className = 'modal-back';
      modal.style.cssText = 'position:fixed;inset:0;background:rgba(4,6,14,.85);z-index:11000;display:flex;align-items:center;justify-content:center;backdrop-filter:blur(6px)';
      modal.innerHTML = `
        <div class="modal" style="background:var(--bg-1);border:1px solid var(--border-hi);border-radius:16px;width:100%;max-width:640px;max-height:90vh;overflow-y:auto;padding:28px;box-shadow:0 32px 80px rgba(0,0,0,.7)">
          <div style="display:flex;align-items:center;justify-content:space-between;margin-bottom:16px">
            <div style="font-size:18px;font-weight:800;display:flex;align-items:center;gap:8px">
              <span>🤖</span> AI Interview: Build Universal Context in 2 Minutes
            </div>
            <button onclick="document.getElementById('hierarchy-interview-modal').style.display='none'" style="background:none;border:none;color:var(--text-2);font-size:20px;cursor:pointer">×</button>
          </div>
          <div style="font-size:13px;color:var(--text-2);line-height:1.6;margin-bottom:20px">
            Answer these 4 master questions once. We'll automatically structure your 4 Tier 1 Markdown files (<code style="color:var(--accent)">about_me</code>, <code style="color:var(--accent)">about_my_business</code>, <code style="color:var(--accent)">about_my_voice</code>, <code style="color:var(--accent)">about_my_offers</code>).
          </div>
          <div style="display:flex;flex-direction:column;gap:16px">
            <div>
              <label style="font-size:12.5px;font-weight:700;display:block;margin-bottom:6px;color:var(--text-0)">1. Who are you & what is your mission? (The 1-line dinner party intro)</label>
              <textarea id="inv-q1" placeholder="e.g. I am Alex, founder of Apex AI. I build autonomous multi-agent operating systems that save engineering teams 20 hours a week..." style="width:100%;height:64px;background:var(--bg-2);border:1px solid var(--border);border-radius:var(--radius-sm);padding:10px;color:var(--text-0);font-size:13px;resize:none"></textarea>
            </div>
            <div>
              <label style="font-size:12.5px;font-weight:700;display:block;margin-bottom:6px;color:var(--text-0)">2. What does your business do & who is your Ideal Customer Profile (ICP)?</label>
              <textarea id="inv-q2" placeholder="e.g. We sell Agentic OS Studio to technical founders, dev shops, and enterprise leaders who want local-first agent orchestration..." style="width:100%;height:64px;background:var(--bg-2);border:1px solid var(--border);border-radius:var(--radius-sm);padding:10px;color:var(--text-0);font-size:13px;resize:none"></textarea>
            </div>
            <div>
              <label style="font-size:12.5px;font-weight:700;display:block;margin-bottom:6px;color:var(--text-0)">3. How do you like things written? Tone, Words to LOVE & Words to AVOID (Highest Leverage)</label>
              <textarea id="inv-q3" placeholder="e.g. Crisp, punchy, high-signal. Use bullet points and exact code. LOVE: high-leverage, compounding, robust. AVOID: delve, synergy, game-changer..." style="width:100%;height:64px;background:var(--bg-2);border:1px solid var(--border);border-radius:var(--radius-sm);padding:10px;color:var(--text-0);font-size:13px;resize:none"></textarea>
            </div>
            <div>
              <label style="font-size:12.5px;font-weight:700;display:block;margin-bottom:6px;color:var(--text-0)">4. What are your current offers, pricing & packages?</label>
              <textarea id="inv-q4" placeholder="e.g. Agentic OS Open Source (Free local app), Pro Pack ($49/mo), and Enterprise Governance Tower ($2,500 setup)..." style="width:100%;height:64px;background:var(--bg-2);border:1px solid var(--border);border-radius:var(--radius-sm);padding:10px;color:var(--text-0);font-size:13px;resize:none"></textarea>
            </div>
          </div>
          <div style="display:flex;justify-content:flex-end;gap:10px;margin-top:24px">
            <button onclick="document.getElementById('hierarchy-interview-modal').style.display='none'" class="btn btn-ghost">Cancel</button>
            <button onclick="submitHierarchyInterview()" class="btn btn-primary">⚡ Generate 4 Tier 1 Context Files</button>
          </div>
        </div>
      `;
      document.body.appendChild(modal);
    }
    modal.style.display = 'flex';
  };

  window.submitHierarchyInterview = async function() {
    const q1 = document.getElementById('inv-q1')?.value || 'AI Builder';
    const q2 = document.getElementById('inv-q2')?.value || 'Agentic OS Platform';
    const q3 = document.getElementById('inv-q3')?.value || 'Clear, punchy, actionable';
    const q4 = document.getElementById('inv-q4')?.value || 'Open Source & Pro Edition';

    try {
      const r = await fetch('/api/hierarchy/tier1/interview', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({
          name_and_role: q1,
          business_and_icp: q2,
          voice_and_words: q3,
          offers_and_pricing: q4
        })
      });
      const data = await r.json();
      if (data.ok) {
        document.getElementById('hierarchy-interview-modal').style.display = 'none';
        if (window.toast) toast('⚡ Universal Context generated & saved across all 4 files!', 'ok', 4000);
        await renderHierarchyPane();
      }
    } catch(err) {
      if (window.toast) toast('Error submitting interview', 'err');
    }
  };

  window.openNewProjectIvrenModal = function() {
    let modal = document.getElementById('hierarchy-new-project-modal');
    if (!modal) {
      modal = document.createElement('div');
      modal.id = 'hierarchy-new-project-modal';
      modal.className = 'modal-back';
      modal.style.cssText = 'position:fixed;inset:0;background:rgba(4,6,14,.85);z-index:11000;display:flex;align-items:center;justify-content:center;backdrop-filter:blur(6px)';
      modal.innerHTML = `
        <div class="modal" style="background:var(--bg-1);border:1px solid var(--border-hi);border-radius:16px;width:100%;max-width:480px;padding:28px;box-shadow:0 32px 80px rgba(0,0,0,.7)">
          <div style="display:flex;align-items:center;justify-content:space-between;margin-bottom:16px">
            <div style="font-size:18px;font-weight:800;display:flex;align-items:center;gap:8px">
              <span>📁</span> Create Tier 2 Project Hierarchy (IVREN)
            </div>
            <button onclick="document.getElementById('hierarchy-new-project-modal').style.display='none'" style="background:none;border:none;color:var(--text-2);font-size:20px;cursor:pointer">×</button>
          </div>
          <div style="font-size:12.5px;color:var(--text-2);margin-bottom:18px">
            Every project gets the exact same 5 compounding subfolders: <strong style="color:var(--text-0)">I</strong>nstructions, <strong style="color:var(--text-0)">V</strong>oice, <strong style="color:var(--text-0)">R</strong>eferences, <strong style="color:var(--text-0)">E</strong>xamples, and <strong style="color:var(--text-0)">N</strong>otes.
          </div>
          <div style="display:flex;flex-direction:column;gap:12px">
            <div>
              <label style="font-size:12px;font-weight:700;display:block;margin-bottom:4px;color:var(--text-0)">Project ID (URL-friendly)</label>
              <input id="np-id" placeholder="e.g. newsletter, client_work, youtube" style="width:100%;background:var(--bg-2);border:1px solid var(--border);border-radius:var(--radius-sm);padding:8px 12px;color:var(--text-0);font-size:13px">
            </div>
            <div>
              <label style="font-size:12px;font-weight:700;display:block;margin-bottom:4px;color:var(--text-0)">Display Name</label>
              <input id="np-name" placeholder="e.g. Weekly AI Newsletter" style="width:100%;background:var(--bg-2);border:1px solid var(--border);border-radius:var(--radius-sm);padding:8px 12px;color:var(--text-0);font-size:13px">
            </div>
            <div>
              <label style="font-size:12px;font-weight:700;display:block;margin-bottom:4px;color:var(--text-0)">Target Audience</label>
              <input id="np-audience" placeholder="e.g. AI builders and product managers" style="width:100%;background:var(--bg-2);border:1px solid var(--border);border-radius:var(--radius-sm);padding:8px 12px;color:var(--text-0);font-size:13px">
            </div>
            <div>
              <label style="font-size:12px;font-weight:700;display:block;margin-bottom:4px;color:var(--text-0)">Brief Description</label>
              <input id="np-desc" placeholder="e.g. Weekly high-signal deep dives" style="width:100%;background:var(--bg-2);border:1px solid var(--border);border-radius:var(--radius-sm);padding:8px 12px;color:var(--text-0);font-size:13px">
            </div>
          </div>
          <div style="display:flex;justify-content:flex-end;gap:10px;margin-top:20px">
            <button onclick="document.getElementById('hierarchy-new-project-modal').style.display='none'" class="btn btn-ghost">Cancel</button>
            <button onclick="submitNewProjectIvren()" class="btn btn-primary">✨ Create IVREN Folders</button>
          </div>
        </div>
      `;
      document.body.appendChild(modal);
    }
    modal.style.display = 'flex';
  };

  window.submitNewProjectIvren = async function() {
    const pid = document.getElementById('np-id')?.value.trim();
    const name = document.getElementById('np-name')?.value.trim() || pid;
    const audience = document.getElementById('np-audience')?.value.trim() || 'General audience';
    const desc = document.getElementById('np-desc')?.value.trim() || 'Specialized project hierarchy';

    if (!pid) {
      if (window.toast) toast('Please enter a Project ID', 'err');
      return;
    }

    try {
      const r = await fetch('/api/hierarchy/projects/create', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ project_id: pid, name: name, audience: audience, description: desc })
      });
      const data = await r.json();
      if (data.ok) {
        document.getElementById('hierarchy-new-project-modal').style.display = 'none';
        if (window.toast) toast('🎉 Project ' + pid + ' IVREN Hierarchy created!', 'ok', 3500);
        currentTier2Project = pid;
        switchHierarchyTab('tier2');
        await renderHierarchyPane();
      }
    } catch(err) {
      if (window.toast) toast('Error creating project hierarchy', 'err');
    }
  };

  let isHierarchySplitOpen = false;
  let hierarchySplitTimeout = null;

  window.toggleHierarchySplitPreview = function() {
    isHierarchySplitOpen = !isHierarchySplitOpen;
    const splitPanel = document.getElementById('h-live-split-panel');
    const toggleBtn = document.getElementById('h-split-toggle-btn');
    if (splitPanel) {
      splitPanel.style.display = isHierarchySplitOpen ? 'flex' : 'none';
    }
    if (toggleBtn) {
      toggleBtn.classList.toggle('btn-primary', isHierarchySplitOpen);
      toggleBtn.classList.toggle('btn-ghost', !isHierarchySplitOpen);
    }
    if (isHierarchySplitOpen) {
      updateLiveHierarchySplitPreview();
    }
  };

  function updateLiveHierarchySplitPreview() {
    if (!isHierarchySplitOpen) return;
    if (hierarchySplitTimeout) clearTimeout(hierarchySplitTimeout);
    hierarchySplitTimeout = setTimeout(async () => {
      try {
        const url = '/api/hierarchy/compiled-context' + (currentTier2Project && currentHierarchyTab === 'tier2' ? '?project_id=' + encodeURIComponent(currentTier2Project) : '');
        const r = await fetch(url);
        const data = await r.json();
        if (data.ok) {
          const textarea = document.getElementById('h-live-split-textarea');
          const stats = document.getElementById('h-live-split-stats');
          if (textarea) textarea.value = data.compiled_context || '';
          if (stats) stats.textContent = `📊 ${data.char_count} chars (~${data.estimated_tokens} tokens)`;
        }
      } catch(err) {}
    }, 250);
  }

  // Bind live typing inside editors
  setTimeout(() => {
    const t1Text = document.getElementById('t1-editor-textarea');
    const t2Text = document.getElementById('t2-ivren-textarea');
    if (t1Text) t1Text.addEventListener('input', updateLiveHierarchySplitPreview);
    if (t2Text) t2Text.addEventListener('input', updateLiveHierarchySplitPreview);
  }, 500);

  window.previewCompiledContext = async function() {
    let modal = document.getElementById('hierarchy-preview-modal');
    if (!modal) {
      modal = document.createElement('div');
      modal.id = 'hierarchy-preview-modal';
      modal.className = 'modal-back';
      modal.style.cssText = 'position:fixed;inset:0;background:rgba(4,6,14,.85);z-index:11000;display:flex;align-items:center;justify-content:center;backdrop-filter:blur(6px)';
      modal.innerHTML = `
        <div class="modal" style="background:var(--bg-1);border:1px solid var(--border-hi);border-radius:16px;width:100%;max-width:760px;max-height:88vh;display:flex;flex-direction:column;padding:24px;box-shadow:0 32px 80px rgba(0,0,0,.7)">
          <div style="display:flex;align-items:center;justify-content:space-between;margin-bottom:12px;flex-shrink:0">
            <div style="font-size:17px;font-weight:800;display:flex;align-items:center;gap:8px">
              <span>📜</span> Live XML System Prompt Injection Preview
            </div>
            <button onclick="document.getElementById('hierarchy-preview-modal').style.display='none'" style="background:none;border:none;color:var(--text-2);font-size:20px;cursor:pointer">×</button>
          </div>
          <div style="font-size:12.5px;color:var(--text-2);margin-bottom:12px;flex-shrink:0">
            This exact XML/Markdown context is automatically injected into every Agentic OS chat, swarm query, and specialized agent session:
          </div>
          <textarea id="preview-compiled-textarea" readonly style="flex:1;min-height:360px;width:100%;background:var(--bg-0);border:1px solid var(--border);border-radius:var(--radius-sm);padding:14px;color:var(--text-0);font-family:monospace;font-size:12px;line-height:1.5;resize:none;outline:none"></textarea>
          <div style="display:flex;justify-content:space-between;align-items:center;margin-top:16px;flex-shrink:0">
            <span id="preview-compiled-stats" style="font-size:11.5px;color:var(--text-3);font-weight:600"></span>
            <button onclick="document.getElementById('hierarchy-preview-modal').style.display='none'" class="btn btn-primary">Close Preview</button>
          </div>
        </div>
      `;
      document.body.appendChild(modal);
    }
    modal.style.display = 'flex';

    try {
      const url = '/api/hierarchy/compiled-context' + (currentTier2Project && currentHierarchyTab === 'tier2' ? '?project_id=' + encodeURIComponent(currentTier2Project) : '');
      const r = await fetch(url);
      const data = await r.json();
      if (data.ok) {
        document.getElementById('preview-compiled-textarea').value = data.compiled_context || '';
        document.getElementById('preview-compiled-stats').textContent = `📊 Character Count: ${data.char_count} (~${data.estimated_tokens} tokens)`;
      }
    } catch(err) {
      document.getElementById('preview-compiled-textarea').value = 'Error fetching compiled context.';
    }
  };

  // Register with window.PANE_RENDERERS
  if (typeof window.PANE_RENDERERS === 'undefined') window.PANE_RENDERERS = {};
  window.PANE_RENDERERS['hierarchy'] = renderHierarchyPane;

  // Register command in PALETTE_CMDS if available
  setTimeout(() => {
    if (typeof PALETTE_CMDS !== 'undefined') {
      PALETTE_CMDS.unshift({
        icon: '🧭',
        label: 'Information Hierarchy',
        desc: 'Universal Business Context + Project IVREN',
        action: () => nav('hierarchy')
      });
    }
  }, 300);

  console.log('%c✅ Information Hierarchy Engine (Universal Context + IVREN) loaded', 'color:#a78bfa;font-weight:bold');
})();
