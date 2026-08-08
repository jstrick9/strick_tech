// Agentic OS — Image Generation
// Generate AI images, import Figma designs, apply style transfer, and
// manage an asset library.
//
// ARCHITECTURE NOTE: this file uses plain top-level function declarations
// (not IIFE-wrapped), so — unlike the Web Search / Browser Agent modules
// fixed earlier this session — every handler function IS correctly
// visible on `window` and inline onclick attributes DO resolve. However,
// several onclick attributes interpolated `JSON.stringify(...)` directly
// into a double-quoted HTML attribute, which performs no HTML-entity
// escaping: the double quotes JSON.stringify wraps strings in collide
// with the onclick attribute's own double-quote delimiters, corrupting
// the HTML. Reproduced live for all three cases below (clicking a style
// chip, a gallery thumbnail, or a variation thumbnail all threw
// "Uncaught SyntaxError: Unexpected end of input" and did nothing):
//   - selectImageStyle(${JSON.stringify(s.id)}) in the style picker
//   - selectGalleryImage(${JSON.stringify(img.url)}, ${JSON.stringify(img.name)})
//     and igDeleteImage(${JSON.stringify(img.name)}) in the asset library
//   - igSelectVariation(${JSON.stringify(src)}, this) in the variations modal
// Fixed by switching every dynamically-generated onclick attribute in this
// file to `data-*` attributes + `addEventListener`, matching the pattern
// already used to fix this same bug class in other modules this session.
// Static onclick attributes with no interpolated data (Generate/Enhance/
// Vary/Download/Save to Gallery/Insert/Import/Apply/Refresh/Upload/Retry
// and the two modal-close buttons) are left as-is since they carry no
// user- or server-derived data and cannot collide.
//
// Also replaced every `showToast(...)` call with `toast(...)` — this
// codebase's standing rule is that `showToast` is a legacy compatibility
// alias for old code only; new/rewritten code must call `toast()`
// directly.

// ── Image Generation state ────────────────────────────────────────────
let selectedImageStyle = '';
let _imgLastPrompt     = '';

// The imagegen API returns real status codes with an explanatory JSON body.
// Reading only response.status threw away the reason the server gave us, so
// every failure looked like "HTTP 502" to the user.
async function igError(r, fallback) {
  let body = {};
  try { body = await r.json(); } catch (e) { /* non-JSON error body */ }
  return body.error || body.detail || fallback || ('HTTP ' + r.status);
}

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
    if (!sR.ok) throw httpError(sR);
    if (!gR.ok) throw httpError(gR);
    // A 200 with an unexpected shape passes the `!ok` checks above and then
    // throws "styles.map is not a function" into the pane. Coerce here.
    const stylesRaw  = await sR.json();
    const galleryRaw = await gR.json();
    const styles  = Array.isArray(stylesRaw)  ? stylesRaw  : (stylesRaw?.styles  || []);
    // Normalise to the OBJECT SHAPE the four call sites below expect
    // ({images, count}), not to a bare array.
    //
    // An earlier defensive fix coerced this to an array to stop
    // "gallery.map is not a function". That silenced one crash and created a
    // worse one: `gallery.images` became undefined, so `gallery.images.length`
    // on the very next line threw "Cannot read properties of undefined
    // (reading 'length')" and the whole pane died with
    // "Couldn't open the image generator."
    //
    // It was invisible against a seeded account and fired on EVERY empty one,
    // i.e. for every new user, on their first visit to this pane. A guard that
    // converts a shape the callers do not accept is not a guard.
    const galleryImages = Array.isArray(galleryRaw)
      ? galleryRaw
      : (galleryRaw?.images || galleryRaw?.gallery || []);
    const gallery = {
      images: Array.isArray(galleryImages) ? galleryImages : [],
      count: (galleryRaw && typeof galleryRaw.count === 'number')
        ? galleryRaw.count
        : (Array.isArray(galleryImages) ? galleryImages.length : 0),
    };
    const models  = mR.ok ? await mR.json() : {models:[], api_key_set:false};

    pane.innerHTML = `
      ${pageHeader?.({title:'🎨 Image Generator', subtitle:'Generate AI images, import Figma designs, manage your asset library',
        actions:[{label:'⬆ Upload', action:'igUpload()', primary:false}]})||'<div class="u-769fed37"><h2>🎨 Image Generator</h2></div>'}
      <div class="page-content">
      <div style="display:grid;grid-template-columns:1fr 1fr;gap:18px;margin-bottom:18px">
        <!-- Generate panel -->
        <div class="card">
          <h3 class="u-761d3add">✨ Generate Image</h3>
          ${!models.api_key_set ? `<div style="background:rgba(232,162,55,.1);border:1px solid var(--warning);border-radius:8px;padding:8px 12px;font-size:11px;color:var(--warning);margin-bottom:10px">
            ⚠️ No API key — you'll get a labelled placeholder, not a real image. Set <code>OPENROUTER_API_KEY</code> in Settings → Connect AI.
          </div>` : ''}
          ${models.models?.length ? `<select id="img-model" class="input" style="margin-bottom:8px;font-size:12px" title="Image model">
            ${models.models.map(m=>`<option value="${escHtml(m.id)}"${m.id===models.default?' selected':''}>${escHtml(m.name)}${m.free?' · free':''}</option>`).join('')}
          </select>` : ''}
          <textarea id="img-prompt" data-draft="imagegen-prompt" class="input" style="min-height:70px;margin-bottom:8px;font-size:13px" placeholder="A dark SaaS dashboard with charts, clean and modern…" data-act-input="hRememberImagePrompt($value)"></textarea>
          <div style="display:flex;flex-wrap:wrap;gap:5px;margin-bottom:8px" id="style-picker">
            ${styles.map(s=>`<button type="button" class="term-btn" id="style-${escHtml(s.id)}" data-style-id="${escHtml(s.id)}" title="${escHtml(s.prompt)}">${escHtml(s.label)}</button>`).join('')}
          </div>
          <div style="display:grid;grid-template-columns:1fr 1fr;gap:8px;margin-bottom:8px">
            <select id="img-size" style="background:var(--bg-1);border:1px solid var(--border);border-radius:var(--radius-sm);padding:6px 10px;color:var(--text-0);font-size:12px;outline:none">
              <option value="256x256">256×256 (Fastest)</option>
              <option value="512x512">512×512 (Fast)</option>
              <option value="1024x1024" selected>1024×1024</option>
              <option value="1792x1024">1792×1024 (Wide)</option>
              <option value="1024x1792">1024×1792 (Tall)</option>
            </select>
            <input id="img-save-to" class="input u-6cb285c6" placeholder="Save as: hero.png" >
          </div>
          <div style="display:flex;gap:6px;margin-bottom:8px">
            <button data-act-click="generateImage()" class="btn btn-primary u-97445a8d"  id="img-gen-btn">🎨 Generate</button>
            <button data-act-click="igEnhancePrompt()" class="btn-sm" title="AI-enhance the prompt">✨ Enhance</button>
            <button data-act-click="igVariations()" class="btn-sm" title="Generate 4 variations">⊞ Vary</button>
          </div>
          <div id="img-status" style="font-size:11px;color:var(--text-2);margin-top:4px;min-height:16px"></div>
          <div id="img-result" style="display:none;margin-top:10px">
            <img id="img-preview" style="max-width:100%;border-radius:var(--radius-sm);border:1px solid var(--border)" alt="Generated image preview">
            <div style="display:flex;gap:6px;margin-top:6px;flex-wrap:wrap">
              <button data-act-click="downloadImage()" class="btn btn-ghost btn-sm">⬇ Download</button>
              <button data-act-click="igSaveToGallery()" class="btn btn-ghost btn-sm">💾 Save to Gallery</button>
              <button data-act-click="insertImageIntoCode()" class="btn btn-ghost btn-sm">→ Insert</button>
            </div>
            <input type="hidden" id="img-url">
          </div>
        </div>

        <!-- Right column -->
        <div style="display:flex;flex-direction:column;gap:12px">
          <!-- Figma Import -->
          <div class="card">
            <h3 class="u-fdf33f23">🔗 Figma Import</h3>
            <p style="font-size:11px;color:var(--text-2);margin-bottom:8px">AI reconstructs your Figma design as working code.</p>
            <input id="figma-url" class="input" placeholder="https://www.figma.com/design/…" style="margin-bottom:6px;font-size:12px">
            <div style="display:flex;gap:6px;margin-bottom:6px">
              <select id="figma-framework" style="flex:1;background:var(--bg-1);border:1px solid var(--border);border-radius:var(--radius-sm);padding:6px 10px;color:var(--text-0);font-size:12px;outline:none">
                <option value="html">HTML + Tailwind</option>
                <option value="react">React + Tailwind</option>
                <option value="vue">Vue + Tailwind</option>
              </select>
              <button data-act-click="importFigma()" class="btn btn-primary btn-sm">🎯 Import</button>
            </div>
            <div id="figma-status" style="font-size:11px;color:var(--text-2);min-height:14px"></div>
          </div>

          <!-- Style Transfer -->
          <div class="card">
            <h3 class="u-fdf33f23">🎨 Style Transfer</h3>
            <input id="st-prompt" class="input" placeholder="Describe your subject…" style="margin-bottom:6px;font-size:12px">
            <div style="display:flex;gap:6px">
              <select id="st-style" style="flex:1;background:var(--bg-1);border:1px solid var(--border);border-radius:var(--radius-sm);padding:6px 10px;color:var(--text-0);font-size:12px;outline:none">
                ${['cinematic','anime','oil_painting','watercolor','neon_noir','minimal','fantasy','retro','sketch','pixel_art'].map(s=>`<option value="${s}">${s.replace(/_/g,' ')}</option>`).join('')}
              </select>
              <button data-act-click="igStyleTransfer()" class="btn btn-primary btn-sm">→ Apply</button>
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
            <button data-act-click="renderImageGen()" class="btn-sm">↻ Refresh</button>
            <button data-act-click="igUpload()" class="btn-sm">⬆ Upload</button>
          </div>
        </div>
        ${gallery.images.length === 0
          ? '<div style="text-align:center;padding:20px;color:var(--text-3);font-size:12px">No images yet — generate or upload one above</div>'
          : `<div style="display:grid;grid-template-columns:repeat(auto-fill,minmax(100px,1fr));gap:6px;max-height:220px;overflow-y:auto" id="asset-library-grid">
              ${gallery.images.map((img, idx)=>`
                <div data-gallery-idx="${idx}" style="aspect-ratio:1;border-radius:6px;overflow:hidden;border:1px solid var(--border);cursor:pointer;position:relative;group" title="${escHtml(img.name)}">
                  <img src="${escHtml(img.url)}" style="width:100%;height:100%;object-fit:cover" loading="lazy" alt="Generated image">
                  <button type="button" data-gallery-delete-idx="${idx}"
                          style="position:absolute;top:2px;right:2px;background:rgba(0,0,0,.6);border:none;border-radius:4px;color:#fff;font-size:10px;cursor:pointer;padding:1px 4px;display:none" class="ig-del-btn">🗑</button>
                </div>`).join('')}
            </div>`}
      </div>
      </div>`;

    wireGalleryEvents(gallery.images);

    // Add hover to show delete button
    setTimeout(() => {
      document.querySelectorAll('#pane-imagegen .ig-del-btn').forEach(btn => {
        const parent = btn.parentElement;
        parent.addEventListener('mouseenter', () => btn.style.display='block');
        parent.addEventListener('mouseleave', () => btn.style.display='none');
      });
    }, 100);

    // Style picker: wired via data-style-id + addEventListener (see file
    // header note) instead of the old JSON.stringify-in-attribute pattern.
    document.querySelectorAll('#style-picker [data-style-id]').forEach(btn => {
      btn.addEventListener('click', () => selectImageStyle(btn.dataset.styleId));
    });

  } catch(ex) {
    pane.innerHTML = `<div style="padding:20px;color:var(--danger)">${escHtml(humanError(ex, {action:'open the image generator'}))}<br>
      <button class="btn-sm u-8a77e5a3" data-act-click="renderImageGen()" >↻ Retry</button></div>`;
  }
}

// Delegated click handling for the asset library grid (thumbnail select /
// delete), looked up by numeric index into the real gallery array rather
// than ever re-serializing a filename/URL into an HTML attribute.
function wireGalleryEvents(images) {
  const grid = document.getElementById('asset-library-grid');
  if (!grid) return;
  grid.addEventListener('click', (e) => {
    const delBtn = e.target.closest('[data-gallery-delete-idx]');
    if (delBtn) {
      e.stopPropagation();
      const img = images[Number(delBtn.dataset.galleryDeleteIdx)];
      if (img) igDeleteImage(img.name);
      return;
    }
    const cell = e.target.closest('[data-gallery-idx]');
    if (cell) {
      const img = images[Number(cell.dataset.galleryIdx)];
      if (img) selectGalleryImage(img.url, img.name);
    }
  });
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
  if (!prompt) { toast('⚠️ Enter a prompt first', 'warn'); return; }

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
        model:   document.getElementById('img-model')?.value || '',
        save_to: saveTo ? `assets/images/${saveTo}` : '',
      })
    });
    const j = await r.json().catch(()=>({}));
    // The backend now returns real status codes with an explanatory body
    // (400 validation, 401 bad key, 402 no credit, 429 rate limit, 502
    // upstream, 504 timeout) instead of HTTP 200 + a placeholder for
    // everything. Surface the reason rather than a bare status number.
    if (!r.ok && !j.placeholder) {
      const msg = j.error || ('HTTP '+r.status);
      if (st) st.textContent = '✗ '+msg;
      toast('Image generation failed: '+msg, 'err');
      return;
    }

    if (j.ok || j.placeholder) {
      const res    = document.getElementById('img-result');
      const prev   = document.getElementById('img-preview');
      const urlEl  = document.getElementById('img-url');
      if (res) res.style.display = 'block';

      if (j.placeholder && j.svg) {
        const blob = new Blob([j.svg], {type:'image/svg+xml'});
        const url  = URL.createObjectURL(blob);
        if (prev)  prev.src  = url;
        if (urlEl) urlEl.value = url;
        if (st) st.innerHTML = '⚠️ Placeholder — no image was generated. '
          + escHtml(j.note || 'Set OPENROUTER_API_KEY for real images.');
      } else if (j.url || j.b64) {
        const src = j.url || `data:image/png;base64,${j.b64}`;
        if (prev)  prev.src   = src;
        if (urlEl) urlEl.value = src;
        if (st) st.textContent = `✅ ${j.saved_to ? 'Saved: '+j.saved_to : 'Generated!'}`;
        toast('🎨 Image ready!', 'ok');
      }
    } else {
      if (st) st.textContent = '✗ '+(j.error||'Generation failed');
      toast('Image generation failed: '+(j.error||'Unknown'), 'err');
    }
  } catch(ex) {
    if (st) st.textContent = '✗ '+(ex?.message||String(ex));
    toast('Image gen error: '+ex?.message, 'err');
  } finally {
    if (btn) { btn.disabled=false; btn.textContent='🎨 Generate'; }
  }
}

async function importFigma() {
  const url = document.getElementById('figma-url')?.value?.trim();
  const fw  = document.getElementById('figma-framework')?.value || 'html';
  if (!url) { toast('⚠️ Enter a Figma URL', 'warn'); return; }
  const st = document.getElementById('figma-status');
  if (st) st.textContent = 'Importing design…';
  try {
    const r = await fetch('/api/imagegen/figma/import', {
      method:'POST', headers:{'Content-Type':'application/json'},
      body: JSON.stringify({url, framework: fw})
    });
    if (!r.ok) { const m = await igError(r); if(st) st.textContent='✗ '+m; toast(m,'err'); return; }
    const j = await r.json();
    if (j.ok) {
      if (st) st.textContent = `✅ Imported → ${j.file}`;
      toast(`🎯 Imported → ${j.file}`, 'ok');
      studioLoadFileTree?.();
    } else {
      if (st) st.textContent = '✗ '+(j.error||'Import failed');
      toast('Figma import failed: '+(j.error||'Unknown'), 'err');
    }
  } catch(ex) {
    if (st) st.textContent = '✗ '+ex?.message;
    toast('Figma import error: '+ex?.message, 'err');
  }
}

async function igStyleTransfer() {
  const prompt  = document.getElementById('st-prompt')?.value?.trim();
  const styleId = document.getElementById('st-style')?.value || 'cinematic';
  if (!prompt) { toast('⚠️ Enter a subject description', 'warn'); return; }
  const st = document.getElementById('st-status');
  if (st) st.textContent = 'Applying style…';
  try {
    const r = await fetch('/api/imagegen/style-transfer', {
      method:'POST', headers:{'Content-Type':'application/json'},
      body: JSON.stringify({source_prompt: prompt, style: styleId})
    });
    if (!r.ok) { const m = await igError(r); if(st) st.textContent='✗ '+m; toast(m,'err'); return; }
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
      toast(`🎨 Style: ${styleId} applied`, 'ok');
    } else {
      if (st) st.textContent = '✗ '+(j.error||'Failed');
    }
  } catch(ex) {
    if (st) st.textContent = '✗ '+ex?.message;
    toast('Style transfer error: '+ex?.message, 'err');
  }
}

async function igEnhancePrompt() {
  const prompt = document.getElementById('img-prompt')?.value?.trim();
  if (!prompt) { toast('⚠️ Enter a prompt to enhance', 'warn'); return; }
  toast('✨ Enhancing prompt…', 'ok');
  try {
    const r = await fetch('/api/imagegen/enhance-prompt', {
      method:'POST', headers:{'Content-Type':'application/json'},
      body: JSON.stringify({prompt, style: selectedImageStyle})
    });
    if (!r.ok) { toast('Enhance failed: '+await igError(r), 'err'); return; }
    const j = await r.json();
    if (j.ok && j.enhanced) {
      const inp = document.getElementById('img-prompt');
      if (inp) inp.value = j.enhanced;
      toast('✨ Prompt enhanced!', 'ok');
    } else {
      toast('Enhance failed: '+(j.error||'Unknown'), 'err');
    }
  } catch(ex) {
    toast('Enhance error: '+ex?.message, 'err');
  }
}

async function igVariations() {
  const prompt = document.getElementById('img-prompt')?.value?.trim();
  if (!prompt) { toast('⚠️ Enter a prompt first', 'warn'); return; }
  toast('⊞ Generating 4 variations…', 'ok');
  try {
    const r = await fetch('/api/imagegen/variations', {
      method:'POST', headers:{'Content-Type':'application/json'},
      body: JSON.stringify({prompt, count: 4, size: '512x512'})
    });
    if (!r.ok) { toast('Variations failed: '+await igError(r), 'err'); return; }
    const j = await r.json();
    if (!j.ok) { toast('Variations failed: '+(j.error||'Unknown'), 'err'); return; }

    // Only render variations that actually produced an image. Failed ones
    // carry an error instead of a src; showing them as empty tiles implied
    // they had succeeded.
    const variations = (j.variations || []).filter(v => v.ok && v.url).map(v => ({
      src: v.url,
      modifier: v.modifier || '',
    }));
    if (j.failed) toast(`⚠️ ${j.failed} of ${j.requested} variations failed`, 'warn');
    if (!variations.length) { toast('No variations were generated', 'err'); return; }

    // Show variations in a modal
    const overlay = document.createElement('div');
    overlay.style.cssText = 'position:fixed;inset:0;background:rgba(0,0,0,.8);z-index:9999;display:flex;align-items:center;justify-content:center;padding:20px';
    const variantsHtml = variations.map((v, i) =>
      `<div data-variation-idx="${i}" style="cursor:pointer;border:2px solid var(--border);border-radius:8px;overflow:hidden">
        <img src="${escHtml(v.src)}" style="width:100%;height:140px;object-fit:cover" alt="Style transfer result">
        <div style="font-size:10px;color:var(--text-3);padding:4px 6px">${escHtml(v.modifier)}</div>
      </div>`
    ).join('');
    overlay.innerHTML = `
      <div style="background:var(--bg-2);border:1px solid var(--border);border-radius:16px;max-width:520px;width:100%;padding:20px">
        <div style="display:flex;justify-content:space-between;margin-bottom:12px">
          <h3 style="margin:0;color:var(--text-0)">⊞ Variations (${j.count})</h3>
          <button type="button" data-modal-close style="background:none;border:none;color:var(--text-3);font-size:18px;cursor:pointer">✕</button>
        </div>
        <div style="display:grid;grid-template-columns:1fr 1fr;gap:8px;margin-bottom:12px" id="var-grid">${variantsHtml}</div>
        <div style="display:flex;justify-content:flex-end">
          <button type="button" data-modal-close class="btn-sm">Close</button>
        </div>
      </div>`;
    overlay.addEventListener('click', (e) => {
      if (e.target === overlay || e.target.closest('[data-modal-close]')) { overlay.remove(); return; }
      const cell = e.target.closest('[data-variation-idx]');
      if (cell) igSelectVariation(variations[Number(cell.dataset.variationIdx)]?.src, cell);
    });
    document.body.appendChild(overlay);
    toast(`✅ ${j.count} variations generated`, 'ok');
  } catch(ex) {
    toast('Variations error: '+ex?.message, 'err');
  }
}

function igSelectVariation(src, el) {
  if (!src) return;
  const prev  = document.getElementById('img-preview');
  const urlEl = document.getElementById('img-url');
  const res   = document.getElementById('img-result');
  if (prev)  prev.src   = src;
  if (urlEl) urlEl.value = src;
  if (res)   res.style.display = 'block';
  document.querySelectorAll('#var-grid > div').forEach(d => d.style.borderColor = 'var(--border)');
  if (el) el.style.borderColor = 'var(--accent)';
  toast('✅ Variation selected', 'ok');
}

function downloadImage() {
  const u = document.getElementById('img-url')?.value;
  if (!u) { toast('⚠️ No image to download', 'warn'); return; }
  const prompt = document.getElementById('img-prompt')?.value?.trim() || 'image';
  const fname  = prompt.split(' ').slice(0,4).join('-').toLowerCase().replace(/[^a-z0-9-]/g,'') || 'image';
  const a = document.createElement('a');
  a.href = u;
  a.download = fname + (u.includes('svg') ? '.svg' : '.png');
  a.click();
  toast('⬇ Downloading…', 'ok');
}

async function igSaveToGallery() {
  const src = document.getElementById('img-url')?.value;
  const prompt = document.getElementById('img-prompt')?.value?.trim() || 'image';
  if (!src) { toast('⚠️ No image to save', 'warn'); return; }
  // If it's a blob URL (SVG placeholder), download and re-upload
  const fname = prompt.split(' ').slice(0,4).join('_').toLowerCase().replace(/[^a-z0-9_]/g,'') || 'image';
  try {
    const resp = await fetch(src);
    const blob = await resp.blob();
    const ext  = blob.type.includes('svg') ? '.svg' : '.png';
    const fd   = new FormData();
    fd.append('file', blob, fname + ext);
    const r = await fetch('/api/imagegen/gallery/upload', {method:'POST', body:fd});
    if (!r.ok) { toast('Save failed: '+await igError(r), 'err'); return; }
    const j = await r.json();
    if (j.ok) { toast('💾 Saved to gallery: '+j.name, 'ok'); }
    else toast('Save failed: '+(j.error||'Unknown'), 'err');
  } catch(ex) {
    toast('Save error: '+ex?.message, 'err');
  }
}

async function igDeleteImage(filename) {
  const ok = await gmDanger('Delete Image', `Delete "${filename}" from gallery?`);
  if (!ok) return;
  try {
    const r = await fetch(`/api/imagegen/gallery/${encodeURIComponent(filename)}`, {method:'DELETE'});
    if (!r.ok) { toast('Delete failed: '+await igError(r), 'err'); return; }
    const j = await r.json();
    if (j.ok) { toast('🗑 Deleted', 'ok'); renderImageGen(); }
    else toast('Delete failed: '+(j.error||'Unknown'), 'err');
  } catch(ex) {
    toast('Delete error: '+ex?.message, 'err');
  }
}

function insertImageIntoCode() {
  const u = document.getElementById('img-url')?.value;
  if (!u) { toast('⚠️ No image to insert', 'warn'); return; }
  const alt = (document.getElementById('img-prompt')?.value||'AI Generated').slice(0,60);
  nav('studio');
  setTimeout(() => {
    const tag = `<img src="${u}" alt="${alt}" style="max-width:100%;border-radius:8px">`;
    if (window.Studio?.editor) {
      const sel = Studio.editor.getSelection();
      Studio.editor.executeEdits('img', [{range:sel, text:tag}]);
      toast('→ Inserted into editor', 'ok');
    } else {
      navigator.clipboard.writeText(tag).then(() => toast('📋 Copied img tag', 'ok'));
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
  toast(`🖼️ ${name}`, 'ok');
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
    toast('⬆ Uploading…', 'ok');
    try {
      const r = await fetch('/api/imagegen/gallery/upload', {method:'POST', body:fd});
      if (!r.ok) { toast('Upload failed: '+await igError(r), 'err'); return; }
      const j = await r.json();
      if (j.ok) { toast(`✅ Uploaded: ${j.name}`, 'ok'); renderImageGen(); }
      else toast('Upload failed: '+(j.error||'Unknown'), 'err');
    } catch(ex) {
      toast('Upload error: '+ex?.message, 'err');
    }
  };
  inp.click();
}
