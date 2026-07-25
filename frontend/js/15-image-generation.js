// Agentic OS — Image Generation
// Extracted from 01-app-core.js for modularity
// ── Image Generation state ────────────────────────────────────────────────────
let selectedImageStyle = '';
let _imgLastPrompt     = '';

async function renderImageGen() {
  const pane = document.getElementById('pane-imagegen');
  if (!pane) return;
  pane.innerHTML = '<div style="padding:20px;color:var(--text-2)">Loading…</div>';
  try {
    const [sR, gR, mR] = await Promise.all([
      fetch('/api/imagegen/styles'),
      fetch('/api/imagegen/gallery'),
      fetch('/api/imagegen/models'),
    ]);
    if (!sR.ok) throw new Error('Styles load failed: HTTP '+sR.status);
    if (!gR.ok) throw new Error('Gallery load failed: HTTP '+gR.status);
    const styles  = await sR.json();
    const gallery = await gR.json();
    const models  = mR.ok ? await mR.json() : {models:[], api_key_set:false};

    pane.innerHTML = `
      ${pageHeader?.({title:'🎨 Image Generator', subtitle:'Generate AI images, import Figma designs, manage your asset library',
        actions:[{label:'⬆ Upload', action:'igUpload()', primary:false}]})||'<div style="padding:20px"><h2>🎨 Image Generator</h2></div>'}
      <div class="page-content">
      <div style="display:grid;grid-template-columns:1fr 1fr;gap:18px;margin-bottom:18px">
        <!-- Generate panel -->
        <div class="card">
          <h3 style="margin-bottom:10px">✨ Generate Image</h3>
          ${!models.api_key_set ? `<div style="background:rgba(232,162,55,.1);border:1px solid var(--warning);border-radius:8px;padding:8px 12px;font-size:11px;color:var(--warning);margin-bottom:10px">
            ⚠️ No API key — generating placeholders. Set <code>OPENROUTER_API_KEY</code> in Settings for real images.
          </div>` : ''}
          <textarea id="img-prompt" class="input" style="min-height:70px;margin-bottom:8px;font-size:13px" placeholder="A dark SaaS dashboard with charts, clean and modern…" oninput="_imgLastPrompt=this.value"></textarea>
          <div style="display:flex;flex-wrap:wrap;gap:5px;margin-bottom:8px" id="style-picker">
            ${styles.map(s=>`<button class="term-btn" id="style-${s.id}" onclick="selectImageStyle(${JSON.stringify(s.id)})" title="${escHtml(s.prompt)}">${escHtml(s.label)}</button>`).join('')}
          </div>
          <div style="display:grid;grid-template-columns:1fr 1fr;gap:8px;margin-bottom:8px">
            <select id="img-size" style="background:var(--bg-1);border:1px solid var(--border);border-radius:var(--radius-sm);padding:6px 10px;color:var(--text-0);font-size:12px;outline:none">
              <option value="256x256">256×256 (Fastest)</option>
              <option value="512x512">512×512 (Fast)</option>
              <option value="1024x1024" selected>1024×1024</option>
              <option value="1792x1024">1792×1024 (Wide)</option>
              <option value="1024x1792">1024×1792 (Tall)</option>
            </select>
            <input id="img-save-to" class="input" placeholder="Save as: hero.png" style="font-size:12px">
          </div>
          <div style="display:flex;gap:6px;margin-bottom:8px">
            <button onclick="generateImage()" class="btn btn-primary" style="flex:1" id="img-gen-btn">🎨 Generate</button>
            <button onclick="igEnhancePrompt()" class="btn-sm" title="AI-enhance the prompt">✨ Enhance</button>
            <button onclick="igVariations()" class="btn-sm" title="Generate 4 variations">⊞ Vary</button>
          </div>
          <div id="img-status" style="font-size:11px;color:var(--text-2);margin-top:4px;min-height:16px"></div>
          <div id="img-result" style="display:none;margin-top:10px">
            <img id="img-preview" style="max-width:100%;border-radius:var(--radius-sm);border:1px solid var(--border)">
            <div style="display:flex;gap:6px;margin-top:6px;flex-wrap:wrap">
              <button onclick="downloadImage()" class="btn btn-ghost btn-sm">⬇ Download</button>
              <button onclick="igSaveToGallery()" class="btn btn-ghost btn-sm">💾 Save to Gallery</button>
              <button onclick="insertImageIntoCode()" class="btn btn-ghost btn-sm">→ Insert</button>
            </div>
            <input type="hidden" id="img-url">
          </div>
        </div>

        <!-- Right column -->
        <div style="display:flex;flex-direction:column;gap:12px">
          <!-- Figma Import -->
          <div class="card">
            <h3 style="margin-bottom:8px">🔗 Figma Import</h3>
            <p style="font-size:11px;color:var(--text-2);margin-bottom:8px">AI reconstructs your Figma design as working code.</p>
            <input id="figma-url" class="input" placeholder="https://www.figma.com/design/…" style="margin-bottom:6px;font-size:12px">
            <div style="display:flex;gap:6px;margin-bottom:6px">
              <select id="figma-framework" style="flex:1;background:var(--bg-1);border:1px solid var(--border);border-radius:var(--radius-sm);padding:6px 10px;color:var(--text-0);font-size:12px;outline:none">
                <option value="html">HTML + Tailwind</option>
                <option value="react">React + Tailwind</option>
                <option value="vue">Vue + Tailwind</option>
              </select>
              <button onclick="importFigma()" class="btn btn-primary btn-sm">🎯 Import</button>
            </div>
            <div id="figma-status" style="font-size:11px;color:var(--text-2);min-height:14px"></div>
          </div>

          <!-- Style Transfer -->
          <div class="card">
            <h3 style="margin-bottom:8px">🎨 Style Transfer</h3>
            <input id="st-prompt" class="input" placeholder="Describe your subject…" style="margin-bottom:6px;font-size:12px">
            <div style="display:flex;gap:6px">
              <select id="st-style" style="flex:1;background:var(--bg-1);border:1px solid var(--border);border-radius:var(--radius-sm);padding:6px 10px;color:var(--text-0);font-size:12px;outline:none">
                ${['cinematic','anime','oil_painting','watercolor','neon_noir','minimal','fantasy','retro','sketch','pixel_art'].map(s=>`<option value="${s}">${s.replace(/_/g,' ')}</option>`).join('')}
              </select>
              <button onclick="igStyleTransfer()" class="btn btn-primary btn-sm">→ Apply</button>
            </div>
            <div id="st-status" style="font-size:11px;color:var(--text-2);margin-top:4px;min-height:14px"></div>
          </div>
        </div>
      </div>

      <!-- Asset Library -->
      <div class="card">
        <div style="display:flex;align-items:center;justify-content:space-between;margin-bottom:10px">
          <h3>🖼️ Asset Library <span style="font-size:11px;color:var(--text-3);font-weight:400">(${gallery.count} images)</span></h3>
          <div style="display:flex;gap:6px">
            <button onclick="renderImageGen()" class="btn-sm">↻ Refresh</button>
            <button onclick="igUpload()" class="btn-sm">⬆ Upload</button>
          </div>
        </div>
        ${gallery.images.length === 0
          ? '<div style="text-align:center;padding:20px;color:var(--text-3);font-size:12px">No images yet — generate or upload one above</div>'
          : `<div style="display:grid;grid-template-columns:repeat(auto-fill,minmax(100px,1fr));gap:6px;max-height:220px;overflow-y:auto">
              ${gallery.images.map(img=>`
                <div style="aspect-ratio:1;border-radius:6px;overflow:hidden;border:1px solid var(--border);cursor:pointer;position:relative;group"
                     onclick="selectGalleryImage(${JSON.stringify(img.url)},${JSON.stringify(img.name)})" title="${escHtml(img.name)}">
                  <img src="${escHtml(img.url)}" style="width:100%;height:100%;object-fit:cover" loading="lazy">
                  <button onclick="event.stopPropagation();igDeleteImage(${JSON.stringify(img.name)})"
                          style="position:absolute;top:2px;right:2px;background:rgba(0,0,0,.6);border:none;border-radius:4px;color:#fff;font-size:10px;cursor:pointer;padding:1px 4px;display:none" class="ig-del-btn">🗑</button>
                </div>`).join('')}
            </div>`}
      </div>
      </div>`;

    // Add hover to show delete button
    setTimeout(() => {
      document.querySelectorAll('#pane-imagegen .ig-del-btn').forEach(btn => {
        const parent = btn.parentElement;
        parent.addEventListener('mouseenter', () => btn.style.display='block');
        parent.addEventListener('mouseleave', () => btn.style.display='none');
      });
    }, 100);

  } catch(ex) {
    pane.innerHTML = `<div style="padding:20px;color:var(--danger)">Error loading Image Gen: ${escHtml(ex?.message||String(ex))}<br>
      <button class="btn-sm" onclick="renderImageGen()" style="margin-top:8px">↻ Retry</button></div>`;
  }
}

function selectImageStyle(id) {
  selectedImageStyle = id;
  document.querySelectorAll('#style-picker .term-btn').forEach(b => {
    const active = b.id === `style-${id}`;
    b.style.borderColor = active ? 'var(--accent)' : '';
    b.style.color       = active ? 'var(--accent-hi)' : '';
  });
}

async function generateImage() {
  const prompt = document.getElementById('img-prompt')?.value?.trim();
  const size   = document.getElementById('img-size')?.value || '1024x1024';
  const saveTo = document.getElementById('img-save-to')?.value?.trim() || '';
  if (!prompt) { showToast('⚠️ Enter a prompt first'); return; }

  const btn = document.getElementById('img-gen-btn');
  const st  = document.getElementById('img-status');
  if (btn) { btn.disabled=true; btn.textContent='⏳ Generating…'; }
  if (st)  st.textContent = 'Creating image…';

  try {
    const r = await fetch('/api/imagegen/generate', {
      method:'POST', headers:{'Content-Type':'application/json'},
      body: JSON.stringify({
        prompt, size,
        style:   selectedImageStyle,
        save_to: saveTo ? `assets/images/${saveTo}` : '',
      })
    });
    if (!r.ok) { if(st) st.textContent='✗ HTTP '+r.status; return; }
    const j = await r.json();

    if (j.ok) {
      const res    = document.getElementById('img-result');
      const prev   = document.getElementById('img-preview');
      const urlEl  = document.getElementById('img-url');
      if (res) res.style.display = 'block';

      if (j.svg) {
        const blob = new Blob([j.svg], {type:'image/svg+xml'});
        const url  = URL.createObjectURL(blob);
        if (prev)  prev.src  = url;
        if (urlEl) urlEl.value = url;
        if (st) st.innerHTML = '⚠️ Placeholder — set <code>OPENROUTER_API_KEY</code> for real images';
      } else if (j.url || j.b64) {
        const src = j.url || `data:image/png;base64,${j.b64}`;
        if (prev)  prev.src   = src;
        if (urlEl) urlEl.value = src;
        if (st) st.textContent = `✅ ${j.saved_to ? 'Saved: '+j.saved_to : 'Generated!'}`;
        showToast('🎨 Image ready!');
      }
    } else {
      if (st) st.textContent = '✗ '+(j.error||'Generation failed');
      showToast('Image generation failed: '+(j.error||'Unknown'));
    }
  } catch(ex) {
    if (st) st.textContent = '✗ '+(ex?.message||String(ex));
    showToast('Image gen error: '+ex?.message);
  } finally {
    if (btn) { btn.disabled=false; btn.textContent='🎨 Generate'; }
  }
}

async function importFigma() {
  const url = document.getElementById('figma-url')?.value?.trim();
  const fw  = document.getElementById('figma-framework')?.value || 'html';
  if (!url) { showToast('⚠️ Enter a Figma URL'); return; }
  const st = document.getElementById('figma-status');
  if (st) st.textContent = 'Importing design…';
  try {
    const r = await fetch('/api/imagegen/figma/import', {
      method:'POST', headers:{'Content-Type':'application/json'},
      body: JSON.stringify({url, framework: fw})
    });
    if (!r.ok) { if(st) st.textContent='✗ HTTP '+r.status; return; }
    const j = await r.json();
    if (j.ok) {
      if (st) st.textContent = `✅ Imported → ${j.file}`;
      showToast(`🎯 Imported → ${j.file}`);
      studioLoadFileTree?.();
    } else {
      if (st) st.textContent = '✗ '+(j.error||'Import failed');
      showToast('Figma import failed: '+(j.error||'Unknown'));
    }
  } catch(ex) {
    if (st) st.textContent = '✗ '+ex?.message;
    showToast('Figma import error: '+ex?.message);
  }
}

async function igStyleTransfer() {
  const prompt  = document.getElementById('st-prompt')?.value?.trim();
  const styleId = document.getElementById('st-style')?.value || 'cinematic';
  if (!prompt) { showToast('⚠️ Enter a subject description'); return; }
  const st = document.getElementById('st-status');
  if (st) st.textContent = 'Applying style…';
  try {
    const r = await fetch('/api/imagegen/style-transfer', {
      method:'POST', headers:{'Content-Type':'application/json'},
      body: JSON.stringify({source_prompt: prompt, style: styleId})
    });
    if (!r.ok) { if(st) st.textContent='✗ HTTP '+r.status; return; }
    const j = await r.json();
    if (j.ok) {
      if (st) st.textContent = '✅ Style applied';
      // Display in main result area
      const prev  = document.getElementById('img-preview');
      const urlEl = document.getElementById('img-url');
      const res   = document.getElementById('img-result');
      if (j.svg) {
        const blob = new Blob([j.svg], {type:'image/svg+xml'});
        const url  = URL.createObjectURL(blob);
        if (prev)  prev.src   = url;
        if (urlEl) urlEl.value = url;
      } else if (j.url) {
        if (prev)  prev.src   = j.url;
        if (urlEl) urlEl.value = j.url;
      }
      if (res) res.style.display = 'block';
      showToast(`🎨 Style: ${styleId} applied`);
    } else {
      if (st) st.textContent = '✗ '+(j.error||'Failed');
    }
  } catch(ex) {
    if (st) st.textContent = '✗ '+ex?.message;
    showToast('Style transfer error: '+ex?.message);
  }
}

async function igEnhancePrompt() {
  const prompt = document.getElementById('img-prompt')?.value?.trim();
  if (!prompt) { showToast('⚠️ Enter a prompt to enhance'); return; }
  showToast('✨ Enhancing prompt…');
  try {
    const r = await fetch('/api/imagegen/enhance-prompt', {
      method:'POST', headers:{'Content-Type':'application/json'},
      body: JSON.stringify({prompt, style: selectedImageStyle})
    });
    if (!r.ok) { showToast('Enhance failed: HTTP '+r.status); return; }
    const j = await r.json();
    if (j.ok && j.enhanced) {
      const inp = document.getElementById('img-prompt');
      if (inp) inp.value = j.enhanced;
      showToast('✨ Prompt enhanced!');
    } else {
      showToast('Enhance failed: '+(j.error||'Unknown'));
    }
  } catch(ex) {
    showToast('Enhance error: '+ex?.message);
  }
}

async function igVariations() {
  const prompt = document.getElementById('img-prompt')?.value?.trim();
  if (!prompt) { showToast('⚠️ Enter a prompt first'); return; }
  showToast('⊞ Generating 4 variations…');
  try {
    const r = await fetch('/api/imagegen/variations', {
      method:'POST', headers:{'Content-Type':'application/json'},
      body: JSON.stringify({prompt, count: 4, size: '512x512'})
    });
    if (!r.ok) { showToast('Variations failed: HTTP '+r.status); return; }
    const j = await r.json();
    if (!j.ok) { showToast('Variations failed: '+(j.error||'Unknown')); return; }
    // Show variations in a modal
    const overlay = document.createElement('div');
    overlay.style.cssText = 'position:fixed;inset:0;background:rgba(0,0,0,.8);z-index:9999;display:flex;align-items:center;justify-content:center;padding:20px';
    const variants = (j.variations||[]).map((v,i) => {
      const src = v.svg
        ? URL.createObjectURL(new Blob([v.svg], {type:'image/svg+xml'}))
        : (v.url || '');
      return `<div style="cursor:pointer;border:2px solid var(--border);border-radius:8px;overflow:hidden" onclick="igSelectVariation(${JSON.stringify(src)},this)">
        <img src="${escHtml(src)}" style="width:100%;height:140px;object-fit:cover">
        <div style="font-size:10px;color:var(--text-3);padding:4px 6px">${escHtml(v.modifier||'')}</div>
      </div>`;
    }).join('');
    overlay.innerHTML = `
      <div style="background:var(--bg-2);border:1px solid var(--border);border-radius:16px;max-width:520px;width:100%;padding:20px">
        <div style="display:flex;justify-content:space-between;margin-bottom:12px">
          <h3 style="margin:0;color:var(--text-0)">⊞ Variations (${j.count})</h3>
          <button onclick="this.closest('[style*=fixed]').remove()" style="background:none;border:none;color:var(--text-3);font-size:18px;cursor:pointer">✕</button>
        </div>
        <div style="display:grid;grid-template-columns:1fr 1fr;gap:8px;margin-bottom:12px" id="var-grid">${variants}</div>
        <div style="display:flex;justify-content:flex-end">
          <button onclick="this.closest('[style*=fixed]').remove()" class="btn-sm">Close</button>
        </div>
      </div>`;
    overlay.onclick = e => { if(e.target===overlay) overlay.remove(); };
    document.body.appendChild(overlay);
    showToast(`✅ ${j.count} variations generated`);
  } catch(ex) {
    showToast('Variations error: '+ex?.message);
  }
}

function igSelectVariation(src, el) {
  const prev  = document.getElementById('img-preview');
  const urlEl = document.getElementById('img-url');
  const res   = document.getElementById('img-result');
  if (prev)  prev.src   = src;
  if (urlEl) urlEl.value = src;
  if (res)   res.style.display = 'block';
  document.querySelectorAll('#var-grid > div').forEach(d => d.style.borderColor = 'var(--border)');
  if (el) el.style.borderColor = 'var(--accent)';
  showToast('✅ Variation selected');
}

function downloadImage() {
  const u = document.getElementById('img-url')?.value;
  if (!u) { showToast('⚠️ No image to download'); return; }
  const prompt = document.getElementById('img-prompt')?.value?.trim() || 'image';
  const fname  = prompt.split(' ').slice(0,4).join('-').toLowerCase().replace(/[^a-z0-9-]/g,'') || 'image';
  const a = document.createElement('a');
  a.href = u;
  a.download = fname + (u.includes('svg') ? '.svg' : '.png');
  a.click();
  showToast('⬇ Downloading…');
}

async function igSaveToGallery() {
  const src = document.getElementById('img-url')?.value;
  const prompt = document.getElementById('img-prompt')?.value?.trim() || 'image';
  if (!src) { showToast('⚠️ No image to save'); return; }
  // If it's a blob URL (SVG placeholder), download and re-upload
  const fname = prompt.split(' ').slice(0,4).join('_').toLowerCase().replace(/[^a-z0-9_]/g,'') || 'image';
  try {
    const resp = await fetch(src);
    const blob = await resp.blob();
    const ext  = blob.type.includes('svg') ? '.svg' : '.png';
    const fd   = new FormData();
    fd.append('file', blob, fname + ext);
    const r = await fetch('/api/imagegen/gallery/upload', {method:'POST', body:fd});
    if (!r.ok) { showToast('Save failed: HTTP '+r.status); return; }
    const j = await r.json();
    if (j.ok) { showToast('💾 Saved to gallery: '+j.name); }
    else showToast('Save failed: '+(j.error||'Unknown'));
  } catch(ex) {
    showToast('Save error: '+ex?.message);
  }
}

async function igDeleteImage(filename) {
  const ok = await gmDanger('Delete Image', `Delete "${filename}" from gallery?`);
  if (!ok) return;
  try {
    const r = await fetch(`/api/imagegen/gallery/${encodeURIComponent(filename)}`, {method:'DELETE'});
    if (!r.ok) { showToast('Delete failed: HTTP '+r.status); return; }
    const j = await r.json();
    if (j.ok) { showToast('🗑 Deleted'); renderImageGen(); }
    else showToast('Delete failed: '+(j.error||'Unknown'));
  } catch(ex) {
    showToast('Delete error: '+ex?.message);
  }
}

function insertImageIntoCode() {
  const u = document.getElementById('img-url')?.value;
  if (!u) { showToast('⚠️ No image to insert'); return; }
  const alt = (document.getElementById('img-prompt')?.value||'AI Generated').slice(0,60);
  nav('studio');
  setTimeout(() => {
    const tag = `<img src="${u}" alt="${alt}" style="max-width:100%;border-radius:8px">`;
    if (window.Studio?.editor) {
      const sel = Studio.editor.getSelection();
      Studio.editor.executeEdits('img', [{range:sel, text:tag}]);
      showToast('→ Inserted into editor');
    } else {
      navigator.clipboard.writeText(tag).then(() => showToast('📋 Copied img tag'));
    }
  }, 500);
}

function selectGalleryImage(url, name) {
  const p = document.getElementById('img-preview');
  const u = document.getElementById('img-url');
  const r = document.getElementById('img-result');
  if (p) p.src  = url;
  if (u) u.value = url;
  if (r) r.style.display = 'block';
  showToast(`🖼️ ${name}`);
}

function igUpload() {
  const inp = document.createElement('input');
  inp.type   = 'file';
  inp.accept = 'image/*';
  inp.onchange = async () => {
    const file = inp.files?.[0];
    if (!file) return;
    const fd = new FormData();
    fd.append('file', file);
    showToast('⬆ Uploading…');
    try {
      const r = await fetch('/api/imagegen/gallery/upload', {method:'POST', body:fd});
      if (!r.ok) { showToast('Upload failed: HTTP '+r.status); return; }
      const j = await r.json();
      if (j.ok) { showToast(`✅ Uploaded: ${j.name}`); renderImageGen(); }
      else showToast('Upload failed: '+(j.error||'Unknown'));
    } catch(ex) {
      showToast('Upload error: '+ex?.message);
    }
  };
  inp.click();
}


