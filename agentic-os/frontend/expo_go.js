/* Expo Go — True Native Tunnel v4.4 */
(function(){
  console.log('[ExpoGo] loading v4.4');
  function inject(){
    const tabs=document.querySelector('.tabs');
    if(!tabs) return false;
    if(document.querySelector('.tab[data-tab="expogo"]')) return true;
    const b=document.createElement('div');
    b.className='tab';
    b.dataset.tab='expogo';
    b.innerHTML='📱 Expo Go';
    b.style.color='#8a5cf6';
    b.style.fontWeight='700';
    tabs.appendChild(b);
    // pane
    const center=document.querySelector('.center');
    if(center && !document.getElementById('pane-expogo')){
      const pane=document.createElement('div');
      pane.id='pane-expogo';
      pane.style.display='none';
      pane.style.height='100%';
      pane.style.overflow='auto';
      pane.style.background='#070912';
      pane.innerHTML=`
<div style="max-width:1180px;margin:0 auto;padding:20px">
  <div style="display:flex;align-items:center;gap:12px;flex-wrap:wrap;margin-bottom:16px">
    <div style="font-size:22px;font-weight:800;color:#d8c8ff">📱 Expo Go — True Native</div>
    <span style="font-size:11px;background:#221630;color:#c9a6ff;padding:3px 10px;border-radius:999px;border:1px solid #4a2c78">v4.4 NATIVE</span>
    <span style="font-size:11px;background:#13231b;color:#9ece6a;padding:3px 10px;border-radius:999px;border:1px solid #294a2b">Metro HMR</span>
    <span style="font-size:11px;background:#2a1a12;color:#ff9e64;padding:3px 10px;border-radius:999px;border:1px solid #5a3a20">iOS • Android</span>
    <span class="spacer"></span>
    <span id="eg-status-pill" style="font-size:11px;background:#1a2032;color:#9aa7c7;padding:4px 10px;border-radius:999px">idle</span>
  </div>

  <div style="display:grid;grid-template-columns:420px 1fr;gap:18px;align-items:start">
    <!-- left QR -->
    <div style="background:#0e1326;border:1px solid #2a2f5a;border-radius:18px;padding:18px;text-align:center">
      <div style="font-weight:700;color:#e2d8ff;margin-bottom:8px">Scan with Expo Go</div>
      <div id="eg-qr-wrap" style="background:#0b0d18;border:1px solid #1d2545;border-radius:14px;padding:16px;min-height:340px;display:flex;align-items:center;justify-content:center;flex-direction:column">
        <img id="eg-qr-img" src="" style="width:300px;height:300px;border-radius:12px;display:none;background:#fff" />
        <div id="eg-qr-placeholder" style="color:#7a88b8;font-size:13px">Press <b>Start Expo</b> →<br>QR appears in ~8-22s</div>
      </div>
      <div id="eg-qr-text" style="font-family:ui-monospace,monospace;font-size:11px;color:#9fb0e8;margin-top:10px;word-break:break-all;min-height:28px">exp:// — idle</div>
      <div style="display:grid;grid-template-columns:1fr 1fr;gap:8px;margin-top:12px">
        <button class="btn" id="eg-start" style="background:#8a5cf6">▶ Start Expo</button>
        <button class="btn btn-ghost" id="eg-stop">■ Stop</button>
      </div>
      <div style="display:flex;gap:6px;margin-top:8px;justify-content:center;flex-wrap:wrap">
        <button class="device-btn" data-egmode="tunnel">🌍 Tunnel</button>
        <button class="device-btn" data-egmode="lan">🏠 LAN</button>
        <button class="device-btn" data-egmode="localhost">💻 Local</button>
      </div>
      <button class="btn-sm btn-ghost" id="eg-sync" style="width:100%;margin-top:10px">⟳ Sync Monaco → Expo App.js</button>
      <div id="eg-meta" style="font-size:11px;color:#7d8ab8;margin-top:10px;text-align:left;line-height:1.5">
        <div>• Real iPhone / Android — Expo Go app</div>
        <div>• Camera • Haptics • Push • GPS — true native</div>
        <div>• Metro Fast Refresh &lt;800ms</div>
        <div>• Monaco edit → /preview/mobile/App.jsx → auto-sync → HMR</div>
      </div>
    </div>

    <!-- right details -->
    <div style="display:flex;flex-direction:column;gap:14px">
      <div style="background:#0e1326;border:1px solid #26325a;border-radius:16px;padding:16px">
        <div style="display:flex;justify-content:space-between;align-items:center;margin-bottom:10px">
          <b style="color:#d8ccff">Metro Logs — live</b>
          <button class="btn-sm btn-ghost" id="eg-logs-refresh">⟳</button>
        </div>
        <pre id="eg-logs" style="background:#060914;color:#9fb4e8;font-family:ui-monospace,monospace;font-size:11px;line-height:1.45;height:210px;overflow:auto;padding:10px;border-radius:10px;border:1px solid #1a2348;margin:0">Press Start Expo…</pre>
      </div>

      <div style="display:grid;grid-template-columns:1fr 1fr;gap:14px">
        <div style="background:#0e1326;border:1px solid #26325a;border-radius:14px;padding:14px">
          <div style="font-weight:700;color:#c9b6ff;font-size:13px;margin-bottom:8px">📲 Install Expo Go</div>
          <div style="font-size:12px;color:#a9b8e8;line-height:1.55">
            iPhone: <a href="https://apps.apple.com/app/expo-go/id982107779" target="_blank" style="color:#8a5cf6">App Store → Expo Go</a><br>
            Android: <a href="https://play.google.com/store/apps/details?id=host.exp.exponent" target="_blank" style="color:#8a5cf6">Play Store → Expo Go</a><br><br>
            1. Open Expo Go<br>
            2. Tap “Scan QR”<br>
            3. Point at left QR<br>
            4. App loads — true native
          </div>
        </div>
        <div style="background:#0e1326;border:1px solid #26325a;border-radius:14px;padding:14px">
          <div style="font-weight:700;color:#ffd4a6;font-size:13px;margin-bottom:8px">⚡ HMR Bridge</div>
          <div style="font-size:12px;color:#b9c5e8;line-height:1.55" id="eg-bridge-info">
            Source: <code>/preview/mobile/App.jsx</code><br>
            Target: <code>/preview/expo-app/App.js</code><br>
            Sync: <b style="color:#9ece6a">auto on Save</b><br><br>
            <button class="btn-sm btn-ghost" id="eg-open-app">📝 Open App.jsx in Monaco</button>
          </div>
        </div>
      </div>

      <div style="background:#101425;border:1px solid #232d52;border-radius:14px;padding:14px">
        <div style="display:flex;justify-content:space-between;align-items:center;margin-bottom:8px;flex-wrap:wrap;gap:8px">
          <b style="color:#e0d4ff">Tunnel URLs</b>
          <div style="font-size:11px;color:#8a97c5">Share with testers • TestFlight next</div>
        </div>
        <div id="eg-urls" style="font-family:ui-monospace,monospace;font-size:12px;color:#a9c0ff;line-height:1.7">
          <div>• <b>Expo Go:</b> <span id="eg-url-expo">—</span></div>
          <div>• <b>LAN:</b> <span id="eg-url-lan">—</span></div>
          <div>• <b>RN Web (fallback):</b> <span id="eg-url-web">—</span></div>
          <div>• <b>Metro:</b> <span id="eg-url-metro">http://localhost:8081</span></div>
        </div>
        <div style="margin-top:10px;display:flex;gap:8px;flex-wrap:wrap">
          <button class="btn-sm btn-ghost" id="eg-copy-url">📋 Copy Expo URL</button>
          <button class="btn-sm btn-ghost" id="eg-open-web">🌐 Open RN Web fallback</button>
          <button class="btn-sm btn-ghost" id="eg-eas">🚀 EAS Build → TestFlight (soon)</button>
        </div>
      </div>

      <div style="background:#12162a;border:1px solid #2a355a;border-radius:14px;padding:14px;font-size:12px;color:#9fb0d8">
        <b style="color:#ffcf8a">Troubleshooting</b><br>
        • <b>No QR?</b> → Install Node 18+ → <code>npm i -g expo</code><br>
        • <b>Tunnel slow?</b> → switch to LAN mode — phone must be same Wi-Fi<br>
        • <b>Camera / mic need HTTPS?</b> → Tunnel mode gives https automatically<br>
        • <b>Stuck “Starting”?</b> → Stop → Start → check Metro logs right → <code>npx expo doctor</code> locally<br>
        • <b>Windows Firewall?</b> → Allow Node.js / port 8081 inbound
      </div>
    </div>
  </div>
</div>`;
      const ref=document.getElementById('pane-swarm')||document.querySelector('[id^="pane-"]');
      if(ref && ref.parentNode) ref.parentNode.appendChild(pane);
      else document.querySelector('.center').appendChild(pane);
    }
    hookExpo();
    return true;
  }

  function hookExpo(){
    document.querySelectorAll('.tab').forEach(tab=>{
      if(tab._eg) return; tab._eg=true;
      tab.addEventListener('click', ()=>{
        const t=tab.dataset.tab;
        document.querySelectorAll('[id^="pane-"]').forEach(p=>p.style.display='none');
        const el=document.getElementById('pane-'+t);
        if(el) el.style.display='block';
        if(t==='expogo') refreshExpo();
      });
    });
    const et=document.querySelector('.tab[data-tab="expogo"]');
    if(et) et.addEventListener('click', ()=>{ document.querySelectorAll('.tab').forEach(x=>x.classList.remove('active')); et.classList.add('active'); });

    document.getElementById('eg-start')?.addEventListener('click', startExpo);
    document.getElementById('eg-stop')?.addEventListener('click', stopExpo);
    document.getElementById('eg-sync')?.addEventListener('click', syncExpo);
    document.getElementById('eg-logs-refresh')?.addEventListener('click', loadLogs);
    document.getElementById('eg-open-app')?.addEventListener('click', ()=>{
      document.querySelector('.tab[data-tab="builder"]')?.click();
      setTimeout(()=>{
        if(window.openFile) window.openFile('mobile/App.jsx');
        else alert('Open Live Builder → left file tree → mobile/App.jsx');
      }, 200);
    });
    document.getElementById('eg-copy-url')?.addEventListener('click', ()=>{
      const u=document.getElementById('eg-url-expo')?.textContent||'';
      if(u && u!=='—'){ navigator.clipboard.writeText(u).then(()=>alert('Copied: '+u)); } else alert('Start Expo first');
    });
    document.getElementById('eg-open-web')?.addEventListener('click', ()=>{
      window.open('/preview/mobile/index.html','_blank');
    });
    document.querySelectorAll('[data-egmode]').forEach(btn=>{
      btn.addEventListener('click', ()=>{
        document.querySelectorAll('[data-egmode]').forEach(b=>b.classList.remove('active'));
        btn.classList.add('active');
        const mode=btn.dataset.egmode;
        startExpo(mode);
      });
    });
    // auto-refresh status every 4s when on expo tab
    setInterval(()=>{ 
      const pane=document.getElementById('pane-expogo');
      if(pane && pane.style.display!=='none'){ refreshExpo(true); }
    }, 4000);
  }

  let currentMode='tunnel';
  async function startExpo(forceMode){
    if(typeof forceMode==='string') currentMode=forceMode;
    const btn=document.getElementById('eg-start');
    if(btn){ btn.disabled=true; btn.textContent='⏳ Starting…'; }
    setStatus('starting', '#ffcf6a');
    try{
      const r=await fetch('/api/expo/start',{method:'POST',headers:{'Content-Type':'application/json'},body:JSON.stringify({mode:currentMode})});
      const j=await r.json();
      if(j.demo){
        alert('Expo CLI not installed locally — showing DEMO QR.\n\nTo get TRUE native:\n\n  npm i -g expo\n  cd preview/expo-app\n  npx expo start --tunnel\n\nThen scan QR in Expo Go.');
      }
      setStatus(j.ok ? 'starting' : 'error', j.ok ? '#ffcf6a' : '#ff6b6b');
      // poll
      let tries=0;
      const poll = setInterval(async ()=>{
        tries++;
        const s=await refreshExpo(true);
        if(s?.qr_text && s?.qr_text.startsWith('exp')){ clearInterval(poll); }
        if(tries>30) clearInterval(poll);
      }, 1800);
    }catch(e){
      alert('Expo start error: '+e);
      setStatus('error', '#ff6b6b');
    }finally{
      if(btn){ btn.disabled=false; btn.textContent='▶ Start Expo'; }
      loadLogs();
    }
  }

  async function stopExpo(){
    await fetch('/api/expo/stop',{method:'POST'});
    setStatus('stopped', '#8a92aa');
    document.getElementById('eg-qr-img').style.display='none';
    document.getElementById('eg-qr-placeholder').style.display='block';
  }

  async function syncExpo(){
    const btn=document.getElementById('eg-sync');
    if(btn){ const t=btn.textContent; btn.textContent='⟳ Syncing…'; btn.disabled=true;
      try{
        const r=await fetch('/api/expo/sync',{method:'POST'}); const j=await r.json();
        if(j.ok){ btn.textContent='✓ Synced → Metro HMR'; setTimeout(()=>{btn.textContent=t; btn.disabled=false;},1400); }
        else { btn.textContent='Sync failed'; setTimeout(()=>{btn.textContent=t; btn.disabled=false;},1400);}
      }catch(e){ btn.textContent='Error'; setTimeout(()=>{btn.textContent=t; btn.disabled=false;},1400);}
      return;
    }
    await fetch('/api/expo/sync',{method:'POST'});
  }

  async function refreshExpo(silent){
    try{
      const r=await fetch('/api/expo/status'); const s=await r.json();
      // status pill
      const pill=document.getElementById('eg-status-pill');
      if(pill){
        if(s.running){ pill.textContent='● LIVE — Metro'; pill.style.background='#13231b'; pill.style.color='#9ece6a'; }
        else if(s.mode==='demo'){ pill.textContent='DEMO — install expo CLI'; pill.style.background='#2a1a12'; pill.style.color='#ff9e64'; }
        else { pill.textContent = s.mode==='starting' ? 'starting…' : 'idle'; pill.style.background='#1a2032'; pill.style.color='#9aa7c7'; }
      }
      // QR
      const qrText = s.qr_text || s.tunnel_url || s.local_url || '';
      document.getElementById('eg-qr-text').textContent = qrText || '—';
      document.getElementById('eg-url-expo').textContent = qrText || '—';
      document.getElementById('eg-url-lan').textContent = s.local_url || '—';
      document.getElementById('eg-url-web').textContent = (location.origin + '/preview/mobile/index.html');
      const img=document.getElementById('eg-qr-img');
      const ph=document.getElementById('eg-qr-placeholder');
      if(s.qr_data_url){
        img.src=s.qr_data_url; img.style.display='block'; if(ph) ph.style.display='none';
      } else if(qrText){
        // fallback to /api/expo/qr png
        img.src='/api/expo/qr?size=300&ts='+Date.now(); img.style.display='block'; if(ph) ph.style.display='none';
        img.onerror=()=>{ img.style.display='none'; if(ph) ph.style.display='block'; };
      }
      setStatus(s.running ? 'running' : (s.mode||'idle'), s.running ? '#9ece6a' : undefined);
      return s;
    }catch(e){
      if(!silent) console.warn(e);
      return null;
    }
  }

  function setStatus(txt, color){
    const el=document.getElementById('eg-status-pill');
    if(el){ el.textContent = txt; if(color){ el.style.color=color; } }
  }

  async function loadLogs(){
    try{
      const r=await fetch('/api/expo/logs?tail=90'); const j=await r.json();
      const pre=document.getElementById('eg-logs');
      if(pre){ pre.textContent = (j.logs||[]).join('\n') || 'No logs yet — press Start Expo'; pre.scrollTop = pre.scrollHeight; }
    }catch(e){}
  }

  // auto-sync after Monaco save — hook into existing preview_save if present
  let _lastSync=0;
  document.addEventListener('click', (e)=>{
    // crude: if Save button clicked in builder
    const t=e.target;
    if(t && t.textContent && t.textContent.includes('Save')){
      const now=Date.now();
      if(now-_lastSync>1800){
        _lastSync=now;
        setTimeout(()=>{ fetch('/api/expo/sync',{method:'POST'}).catch(()=>{}); }, 700);
      }
    }
  });

  // inject
  let tries=0;
  const ti=setInterval(()=>{ tries++; if(inject()||tries>35) clearInterval(ti); }, 350);
  console.log('[ExpoGo] injector ready');
})();
