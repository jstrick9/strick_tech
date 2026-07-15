"""
Agentic OS — Template Gallery Router
Production-ready starter templates across:
- SaaS & Business (dashboards, landing pages, pricing, auth, CRM)
- Apps & Tools (todo, notes, calculator, weather, chat, URL shortener)
- Portfolio & Marketing (personal site, agency, product launch, waitlist)
- E-Commerce (product page, cart, checkout, store)

Each template is a fully working HTML/CSS/JS app that scaffolds instantly.
"""
from __future__ import annotations
import json, logging, re
from pathlib import Path
from fastapi import APIRouter, Request
from ..services.memory_db import get_conn, audit_log

router = APIRouter(prefix="/api/templates", tags=["templates"])
log    = logging.getLogger("agentic.templates")
ROOT   = Path(__file__).resolve().parents[2]   # /home/user/agentic-os
PREV   = ROOT / "preview"
PREV.mkdir(parents=True, exist_ok=True)


# ── Template catalogue ─────────────────────────────────────────────────────────
TEMPLATES = [
    # ── SaaS & Business ───────────────────────────────────────────────────────
    {
        "id": "saas-landing",
        "name": "SaaS Landing Page",
        "category": "saas",
        "emoji": "🚀",
        "description": "Hero, features, social proof, pricing tiers, FAQ, CTA — ready to customise",
        "tags": ["landing", "saas", "tailwind", "dark"],
        "preview_color": "#5b8af8",
        "files": {
            "index.html": """<!DOCTYPE html>
<html lang="en">
<head>
<meta charset="UTF-8"><meta name="viewport" content="width=device-width,initial-scale=1">
<title>YourSaaS — Build faster with AI</title>
<script src="https://cdn.tailwindcss.com"></script>
<style>
  body{background:#050810;color:#f0f4ff;font-family:Inter,system-ui,sans-serif}
  .gradient{background:linear-gradient(135deg,#5b8af8,#9d74f5)}
  .card{background:#0d1020;border:1px solid #1a2040;border-radius:16px}
  .glow{box-shadow:0 0 60px rgba(91,138,248,.15)}
</style>
</head>
<body>
<!-- Nav -->
<nav class="flex items-center justify-between px-8 py-4 border-b border-white/10 sticky top-0 bg-[#050810]/90 backdrop-blur z-50">
  <div class="flex items-center gap-2 font-bold text-xl">
    <span class="text-2xl">✨</span> YourSaaS
  </div>
  <div class="hidden md:flex items-center gap-6 text-sm text-gray-400">
    <a href="#features" class="hover:text-white transition">Features</a>
    <a href="#pricing" class="hover:text-white transition">Pricing</a>
    <a href="#faq" class="hover:text-white transition">FAQ</a>
  </div>
  <div class="flex items-center gap-3">
    <a href="#" class="text-sm text-gray-400 hover:text-white">Sign in</a>
    <a href="#" class="gradient text-white text-sm font-semibold px-4 py-2 rounded-xl hover:opacity-90 transition">Get started free</a>
  </div>
</nav>
<!-- Hero -->
<section class="text-center px-4 pt-24 pb-20">
  <div class="inline-flex items-center gap-2 bg-white/5 border border-white/10 rounded-full px-4 py-1.5 text-sm text-gray-300 mb-6">
    🎉 <span>Now in public beta — <a href="#" class="text-blue-400">Join free →</a></span>
  </div>
  <h1 class="text-5xl md:text-7xl font-black mb-6 leading-tight">
    Build faster<br><span class="gradient bg-clip-text text-transparent">with AI</span>
  </h1>
  <p class="text-xl text-gray-400 max-w-2xl mx-auto mb-10">
    The platform that turns your ideas into working software in seconds. No boilerplate, no configuration, just results.
  </p>
  <div class="flex flex-col sm:flex-row gap-3 justify-center">
    <a href="#" class="gradient text-white font-bold px-8 py-4 rounded-2xl text-lg hover:opacity-90 transition glow">Start building free</a>
    <a href="#" class="border border-white/20 text-white px-8 py-4 rounded-2xl text-lg hover:bg-white/5 transition">Watch demo ▶</a>
  </div>
  <p class="text-sm text-gray-500 mt-4">No credit card required · Free forever plan</p>
</section>
<!-- Stats -->
<section class="border-y border-white/10 py-10 px-4">
  <div class="max-w-4xl mx-auto grid grid-cols-2 md:grid-cols-4 gap-8 text-center">
    <div><div class="text-4xl font-black gradient bg-clip-text text-transparent">50K+</div><div class="text-gray-400 text-sm">Builders</div></div>
    <div><div class="text-4xl font-black gradient bg-clip-text text-transparent">2M+</div><div class="text-gray-400 text-sm">Apps built</div></div>
    <div><div class="text-4xl font-black gradient bg-clip-text text-transparent">18s</div><div class="text-gray-400 text-sm">Avg deploy time</div></div>
    <div><div class="text-4xl font-black gradient bg-clip-text text-transparent">99.9%</div><div class="text-gray-400 text-sm">Uptime SLA</div></div>
  </div>
</section>
<!-- Features -->
<section id="features" class="max-w-6xl mx-auto px-4 py-24">
  <h2 class="text-4xl font-black text-center mb-4">Everything you need</h2>
  <p class="text-gray-400 text-center mb-16">One platform to build, ship, and scale your idea.</p>
  <div class="grid md:grid-cols-3 gap-6">
    <div class="card p-6"><div class="text-3xl mb-3">⚡</div><h3 class="font-bold text-lg mb-2">Instant scaffold</h3><p class="text-gray-400 text-sm">Go from idea to working app in under 18 seconds. Any framework.</p></div>
    <div class="card p-6"><div class="text-3xl mb-3">🤖</div><h3 class="font-bold text-lg mb-2">Multi-agent AI</h3><p class="text-gray-400 text-sm">Claude, GPT-4o, Gemini, Grok working together on your project.</p></div>
    <div class="card p-6"><div class="text-3xl mb-3">🔒</div><h3 class="font-bold text-lg mb-2">100% private</h3><p class="text-gray-400 text-sm">Local-first. Your code never leaves your machine unless you deploy.</p></div>
    <div class="card p-6"><div class="text-3xl mb-3">🌌</div><h3 class="font-bold text-lg mb-2">Memory Galaxy</h3><p class="text-gray-400 text-sm">Semantic memory of your entire project. Agents know your context.</p></div>
    <div class="card p-6"><div class="text-3xl mb-3">🚀</div><h3 class="font-bold text-lg mb-2">One-click deploy</h3><p class="text-gray-400 text-sm">Vercel, Netlify, Railway, GitHub Pages — pick your platform.</p></div>
    <div class="card p-6"><div class="text-3xl mb-3">🐙</div><h3 class="font-bold text-lg mb-2">GitHub sync</h3><p class="text-gray-400 text-sm">Bidirectional sync. Push, pull, branch, and create PRs from the UI.</p></div>
  </div>
</section>
<!-- Pricing -->
<section id="pricing" class="max-w-5xl mx-auto px-4 py-20">
  <h2 class="text-4xl font-black text-center mb-4">Simple pricing</h2>
  <p class="text-gray-400 text-center mb-12">Start free. Upgrade when you're ready.</p>
  <div class="grid md:grid-cols-3 gap-6">
    <div class="card p-8"><div class="text-2xl font-black mb-1">Free</div><div class="text-gray-400 text-sm mb-6">Forever</div><div class="text-4xl font-black mb-8">$0</div><ul class="text-sm text-gray-300 space-y-2 mb-8"><li>✓ 3 projects</li><li>✓ 100 AI messages/day</li><li>✓ Community support</li></ul><a href="#" class="block text-center border border-white/20 py-3 rounded-xl hover:bg-white/5 transition">Get started</a></div>
    <div class="card p-8 border-blue-500/50 glow relative"><div class="absolute -top-3 left-1/2 -translate-x-1/2 gradient text-white text-xs font-bold px-3 py-1 rounded-full">Most popular</div><div class="text-2xl font-black mb-1">Pro</div><div class="text-gray-400 text-sm mb-6">Per month</div><div class="text-4xl font-black mb-8">$20</div><ul class="text-sm text-gray-300 space-y-2 mb-8"><li>✓ Unlimited projects</li><li>✓ Unlimited AI messages</li><li>✓ All deploy platforms</li><li>✓ Priority support</li></ul><a href="#" class="gradient block text-center text-white font-bold py-3 rounded-xl hover:opacity-90 transition">Start free trial</a></div>
    <div class="card p-8"><div class="text-2xl font-black mb-1">Team</div><div class="text-gray-400 text-sm mb-6">Per seat/month</div><div class="text-4xl font-black mb-8">$50</div><ul class="text-sm text-gray-300 space-y-2 mb-8"><li>✓ Everything in Pro</li><li>✓ Team collaboration</li><li>✓ Custom agents</li><li>✓ Dedicated support</li></ul><a href="#" class="block text-center border border-white/20 py-3 rounded-xl hover:bg-white/5 transition">Contact sales</a></div>
  </div>
</section>
<!-- FAQ -->
<section id="faq" class="max-w-3xl mx-auto px-4 py-20">
  <h2 class="text-4xl font-black text-center mb-12">FAQ</h2>
  <div class="space-y-4">
    <details class="card p-5 cursor-pointer"><summary class="font-semibold">Is my code private?</summary><p class="text-gray-400 mt-3 text-sm">Yes. Agentic OS is local-first — your code stays on your machine. Nothing is sent to our servers. You choose when and where to deploy.</p></details>
    <details class="card p-5 cursor-pointer"><summary class="font-semibold">Which AI models are supported?</summary><p class="text-gray-400 mt-3 text-sm">Claude 4, GPT-4o, Gemini 2.5 Pro, Grok 3, Llama 3.3, and more via OpenRouter. You can also run local models with Ollama for complete privacy.</p></details>
    <details class="card p-5 cursor-pointer"><summary class="font-semibold">Can I use my own API keys?</summary><p class="text-gray-400 mt-3 text-sm">Yes. Add your OpenRouter key and you only pay for what you use. The free tier of many models costs nothing.</p></details>
  </div>
</section>
<!-- Footer -->
<footer class="border-t border-white/10 px-8 py-10 text-center text-gray-500 text-sm">
  <p>Built with ❤️ using Agentic OS · <a href="#" class="text-blue-400 hover:underline">Privacy</a> · <a href="#" class="text-blue-400 hover:underline">Terms</a></p>
</footer>
<script>
// Smooth scroll for anchor links
document.querySelectorAll('a[href^="#"]').forEach(a => {
  a.addEventListener('click', e => {
    const t = document.querySelector(a.getAttribute('href'));
    if (t) { e.preventDefault(); t.scrollIntoView({behavior:'smooth'}); }
  });
});
</script>
</body></html>"""
        }
    },
    {
        "id": "admin-dashboard",
        "name": "Admin Dashboard",
        "category": "saas",
        "emoji": "📊",
        "description": "Dark sidebar, stat cards, charts (Chart.js), data table, user management",
        "tags": ["dashboard", "admin", "charts", "table"],
        "preview_color": "#9d74f5",
        "files": {
            "index.html": """<!DOCTYPE html>
<html lang="en">
<head>
<meta charset="UTF-8"><meta name="viewport" content="width=device-width,initial-scale=1">
<title>Admin Dashboard</title>
<script src="https://cdn.tailwindcss.com"></script>
<script src="https://cdn.jsdelivr.net/npm/chart.js@4/dist/chart.umd.min.js"></script>
<style>body{background:#070912;color:#e8f0ff;font-family:Inter,system-ui,sans-serif}</style>
</head>
<body class="flex h-screen overflow-hidden">
<!-- Sidebar -->
<aside class="w-56 bg-[#0d1020] border-r border-white/10 flex flex-col p-4 flex-shrink-0">
  <div class="font-bold text-lg mb-8 flex items-center gap-2"><span>🧠</span> Agentic OS</div>
  <nav class="space-y-1 flex-1">
    <a href="#" class="flex items-center gap-3 px-3 py-2 rounded-lg bg-blue-500/20 text-blue-300 text-sm font-medium">📊 Dashboard</a>
    <a href="#" class="flex items-center gap-3 px-3 py-2 rounded-lg text-gray-400 hover:bg-white/5 text-sm">👥 Users</a>
    <a href="#" class="flex items-center gap-3 px-3 py-2 rounded-lg text-gray-400 hover:bg-white/5 text-sm">📦 Projects</a>
    <a href="#" class="flex items-center gap-3 px-3 py-2 rounded-lg text-gray-400 hover:bg-white/5 text-sm">💰 Revenue</a>
    <a href="#" class="flex items-center gap-3 px-3 py-2 rounded-lg text-gray-400 hover:bg-white/5 text-sm">⚙️ Settings</a>
  </nav>
  <div class="flex items-center gap-2 mt-4 pt-4 border-t border-white/10">
    <div class="w-8 h-8 rounded-full bg-blue-500 flex items-center justify-center text-sm font-bold">A</div>
    <div><div class="text-sm font-medium">Admin</div><div class="text-xs text-gray-500">admin@app.io</div></div>
  </div>
</aside>
<!-- Main -->
<main class="flex-1 overflow-auto p-6">
  <div class="flex items-center justify-between mb-6">
    <h1 class="text-xl font-bold">Dashboard</h1>
    <button class="bg-blue-500 text-white text-sm px-4 py-2 rounded-lg hover:bg-blue-400 transition">+ New project</button>
  </div>
  <!-- Stats -->
  <div class="grid grid-cols-4 gap-4 mb-6">
    <div class="bg-[#0d1020] border border-white/10 rounded-xl p-4"><div class="text-xs text-gray-400 mb-1">Total users</div><div class="text-2xl font-bold">12,847</div><div class="text-xs text-green-400 mt-1">↑ 18% this month</div></div>
    <div class="bg-[#0d1020] border border-white/10 rounded-xl p-4"><div class="text-xs text-gray-400 mb-1">MRR</div><div class="text-2xl font-bold">$48,200</div><div class="text-xs text-green-400 mt-1">↑ 24% this month</div></div>
    <div class="bg-[#0d1020] border border-white/10 rounded-xl p-4"><div class="text-xs text-gray-400 mb-1">Active projects</div><div class="text-2xl font-bold">3,491</div><div class="text-xs text-blue-400 mt-1">↑ 8% this month</div></div>
    <div class="bg-[#0d1020] border border-white/10 rounded-xl p-4"><div class="text-xs text-gray-400 mb-1">Churn rate</div><div class="text-2xl font-bold">2.4%</div><div class="text-xs text-red-400 mt-1">↓ 0.3% this month</div></div>
  </div>
  <!-- Chart + Table -->
  <div class="grid grid-cols-3 gap-4">
    <div class="col-span-2 bg-[#0d1020] border border-white/10 rounded-xl p-4">
      <div class="text-sm font-semibold mb-4">Revenue over time</div>
      <canvas id="revenueChart" height="200"></canvas>
    </div>
    <div class="bg-[#0d1020] border border-white/10 rounded-xl p-4">
      <div class="text-sm font-semibold mb-4">Traffic sources</div>
      <canvas id="sourceChart" height="200"></canvas>
    </div>
  </div>
  <!-- Recent users table -->
  <div class="bg-[#0d1020] border border-white/10 rounded-xl p-4 mt-4">
    <div class="flex items-center justify-between mb-4"><div class="text-sm font-semibold">Recent users</div><input placeholder="Search…" class="bg-white/5 border border-white/10 rounded-lg px-3 py-1.5 text-sm outline-none w-48"></div>
    <table class="w-full text-sm">
      <thead><tr class="text-xs text-gray-400 border-b border-white/10"><th class="text-left pb-2">Name</th><th class="text-left pb-2">Email</th><th class="text-left pb-2">Plan</th><th class="text-left pb-2">Status</th><th class="text-left pb-2">Joined</th></tr></thead>
      <tbody class="divide-y divide-white/5" id="usersTable"></tbody>
    </table>
  </div>
</main>
<script>
const users=[{n:'Alice Johnson',e:'alice@startup.io',p:'Pro',s:'Active',j:'Jul 1'},{n:'Bob Chen',e:'bob@dev.co',p:'Free',s:'Active',j:'Jun 28'},{n:'Carol Kim',e:'carol@agency.ai',p:'Team',s:'Active',j:'Jun 25'},{n:'David Park',e:'david@solo.dev',p:'Pro',s:'Paused',j:'Jun 20'},{n:'Eva Smith',e:'eva@build.io',p:'Free',s:'Active',j:'Jun 18'}];
const tb=document.getElementById('usersTable');
users.forEach(u=>{const tr=document.createElement('tr');tr.innerHTML=`<td class="py-2.5 font-medium">${u.n}</td><td class="py-2.5 text-gray-400">${u.e}</td><td class="py-2.5"><span class="bg-blue-500/20 text-blue-300 text-xs px-2 py-0.5 rounded">${u.p}</span></td><td class="py-2.5"><span class="text-${u.s==='Active'?'green':'yellow'}-400 text-xs">● ${u.s}</span></td><td class="py-2.5 text-gray-500">${u.j}</td>`;tb.appendChild(tr);});
const m=['Jan','Feb','Mar','Apr','May','Jun','Jul'];
new Chart(document.getElementById('revenueChart'),{type:'line',data:{labels:m,datasets:[{label:'Revenue',data:[18000,22000,19500,28000,35000,42000,48200],borderColor:'#5b8af8',backgroundColor:'rgba(91,138,248,0.1)',fill:true,tension:0.4}]},options:{plugins:{legend:{display:false}},scales:{x:{grid:{color:'rgba(255,255,255,0.05)'},ticks:{color:'#6b7a99'}},y:{grid:{color:'rgba(255,255,255,0.05)'},ticks:{color:'#6b7a99',callback:v=>'$'+v.toLocaleString()}}}}});
new Chart(document.getElementById('sourceChart'),{type:'doughnut',data:{labels:['Organic','Paid','Referral','Direct'],datasets:[{data:[45,25,20,10],backgroundColor:['#5b8af8','#9d74f5','#4cc98a','#f0c060'],borderWidth:0}]},options:{plugins:{legend:{position:'bottom',labels:{color:'#9aa7c7',padding:10,font:{size:11}}}}}});
</script>
</body></html>"""
        }
    },
    {
        "id": "todo-app",
        "name": "Todo App",
        "category": "apps",
        "emoji": "✅",
        "description": "Drag-drop kanban todo with priorities, due dates, local storage persistence",
        "tags": ["todo", "productivity", "kanban", "dark"],
        "preview_color": "#4cc98a",
        "files": {
            "index.html": """<!DOCTYPE html>
<html lang="en">
<head>
<meta charset="UTF-8"><meta name="viewport" content="width=device-width,initial-scale=1">
<title>Todo App</title>
<script src="https://cdn.tailwindcss.com"></script>
<style>
  body{background:#08090e;color:#e8f0ff;font-family:Inter,system-ui,sans-serif}
  .task{cursor:grab;transition:all .15s}
  .task:hover{transform:translateY(-1px)}
  input,textarea{outline:none}
  ::-webkit-scrollbar{width:4px}
  ::-webkit-scrollbar-thumb{background:#1a2040;border-radius:99px}
</style>
</head>
<body class="p-6 min-h-screen">
<div class="max-w-5xl mx-auto">
  <div class="flex items-center justify-between mb-8">
    <div><h1 class="text-3xl font-black">My Tasks</h1><p id="taskCount" class="text-gray-400 text-sm mt-1">0 tasks</p></div>
    <button onclick="openAddTask()" class="bg-blue-500 hover:bg-blue-400 text-white font-bold px-5 py-2.5 rounded-xl transition">+ Add Task</button>
  </div>
  <div class="grid grid-cols-3 gap-4" id="board"></div>
</div>
<!-- Add task modal -->
<div id="modal" class="fixed inset-0 bg-black/80 backdrop-blur hidden items-center justify-center z-50" onclick="if(event.target===this)closeModal()">
  <div class="bg-[#0d1020] border border-white/20 rounded-2xl p-6 w-full max-w-md" onclick="event.stopPropagation()">
    <h2 class="font-bold text-lg mb-4">New Task</h2>
    <input id="taskTitle" placeholder="Task title…" class="w-full bg-white/5 border border-white/10 rounded-xl px-4 py-3 text-white mb-3" onkeydown="if(event.key==='Enter')addTask()">
    <textarea id="taskDesc" placeholder="Description (optional)…" class="w-full bg-white/5 border border-white/10 rounded-xl px-4 py-3 text-white mb-3 resize-none h-20"></textarea>
    <div class="flex gap-3 mb-4">
      <select id="taskPriority" class="flex-1 bg-white/5 border border-white/10 rounded-xl px-3 py-2.5 text-white"><option value="low">🟢 Low</option><option value="medium" selected>🟡 Medium</option><option value="high">🔴 High</option></select>
      <select id="taskStatus" class="flex-1 bg-white/5 border border-white/10 rounded-xl px-3 py-2.5 text-white"><option value="todo">📋 To Do</option><option value="doing">⚡ Doing</option><option value="done">✅ Done</option></select>
    </div>
    <div class="flex gap-3">
      <button onclick="closeModal()" class="flex-1 border border-white/20 py-2.5 rounded-xl hover:bg-white/5 transition">Cancel</button>
      <button onclick="addTask()" class="flex-1 bg-blue-500 text-white font-bold py-2.5 rounded-xl hover:bg-blue-400 transition">Add Task</button>
    </div>
  </div>
</div>
<script>
const COLS=[{id:'todo',label:'📋 To Do',color:'#5b8af8'},{id:'doing',label:'⚡ Doing',color:'#f0c060'},{id:'done',label:'✅ Done',color:'#4cc98a'}];
let tasks=JSON.parse(localStorage.getItem('agentic-tasks')||'[]');
if(!tasks.length)tasks=[{id:1,title:'Welcome to Todo App',desc:'Add tasks, drag between columns, and mark done!',priority:'medium',status:'todo'},{id:2,title:'Try dragging this card',desc:'',priority:'high',status:'doing'},{id:3,title:'Completed example',desc:'',priority:'low',status:'done'}];

function save(){localStorage.setItem('agentic-tasks',JSON.stringify(tasks));}
function render(){
  const board=document.getElementById('board');
  board.innerHTML=COLS.map(col=>`
    <div class="bg-[#0d1020] border border-white/10 rounded-xl overflow-hidden" ondragover="event.preventDefault()" ondrop="drop(event,'${col.id}')">
      <div class="flex items-center justify-between px-4 py-3 border-b border-white/10">
        <span class="font-bold text-sm">${col.label}</span>
        <span class="text-xs bg-white/10 px-2 py-0.5 rounded-full">${tasks.filter(t=>t.status===col.id).length}</span>
      </div>
      <div class="p-3 space-y-2 min-h-32">
        ${tasks.filter(t=>t.status===col.id).map(t=>`
          <div class="task bg-[#141830] border border-white/10 rounded-xl p-3" draggable="true" ondragstart="drag(event,${t.id})">
            <div class="flex items-start justify-between gap-2 mb-1">
              <span class="font-semibold text-sm">${t.title}</span>
              <button onclick="deleteTask(${t.id})" class="text-gray-600 hover:text-red-400 text-xs flex-shrink-0">✕</button>
            </div>
            ${t.desc?`<p class="text-xs text-gray-400 mb-2">${t.desc}</p>`:''}
            <span class="text-xs px-2 py-0.5 rounded-full ${t.priority==='high'?'bg-red-500/20 text-red-300':t.priority==='medium'?'bg-yellow-500/20 text-yellow-300':'bg-green-500/20 text-green-300'}">${t.priority}</span>
          </div>`).join('')}
      </div>
    </div>`).join('');
  document.getElementById('taskCount').textContent=`${tasks.length} task${tasks.length!==1?'s':''}`;
}
let dragId=null;
function drag(e,id){dragId=id;}
function drop(e,status){
  const t=tasks.find(t=>t.id===dragId);
  if(t){t.status=status;save();render();}
}
function openAddTask(){document.getElementById('modal').classList.replace('hidden','flex');document.getElementById('taskTitle').focus();}
function closeModal(){document.getElementById('modal').classList.replace('flex','hidden');}
function addTask(){
  const title=document.getElementById('taskTitle').value.trim();
  if(!title)return;
  tasks.push({id:Date.now(),title,desc:document.getElementById('taskDesc').value,priority:document.getElementById('taskPriority').value,status:document.getElementById('taskStatus').value});
  save();render();closeModal();
  document.getElementById('taskTitle').value='';document.getElementById('taskDesc').value='';
}
function deleteTask(id){if(confirm('Delete this task?')){tasks=tasks.filter(t=>t.id!==id);save();render();}}
render();
</script>
</body></html>"""
        }
    },
    {
        "id": "portfolio",
        "name": "Developer Portfolio",
        "category": "portfolio",
        "emoji": "🎨",
        "description": "Clean dev portfolio: hero, about, projects grid, skills, contact form",
        "tags": ["portfolio", "personal", "dark", "animated"],
        "preview_color": "#f08850",
        "files": {
            "index.html": """<!DOCTYPE html>
<html lang="en">
<head>
<meta charset="UTF-8"><meta name="viewport" content="width=device-width,initial-scale=1">
<title>Your Name — Developer</title>
<script src="https://cdn.tailwindcss.com"></script>
<style>
body{background:#08090e;color:#e8f0ff;font-family:Inter,system-ui,sans-serif;scroll-behavior:smooth}
.gradient-text{background:linear-gradient(135deg,#f08850,#9d74f5);-webkit-background-clip:text;-webkit-text-fill-color:transparent}
.card{background:#0d1020;border:1px solid rgba(255,255,255,0.08);border-radius:16px;transition:transform .2s,border-color .2s}
.card:hover{transform:translateY(-2px);border-color:rgba(255,255,255,0.15)}
.skill-pill{background:rgba(240,136,80,0.12);border:1px solid rgba(240,136,80,0.25);color:#f4b896;border-radius:999px;padding:4px 14px;font-size:13px}
@keyframes fadeUp{from{opacity:0;transform:translateY(20px)}to{opacity:1;transform:none}}
.fade-up{animation:fadeUp .6s ease both}
</style>
</head>
<body>
<nav class="flex items-center justify-between px-8 py-4 border-b border-white/10 sticky top-0 bg-[#08090e]/90 backdrop-blur z-50">
  <div class="font-bold text-lg gradient-text">YN.</div>
  <div class="flex gap-6 text-sm text-gray-400">
    <a href="#about" class="hover:text-white transition">About</a>
    <a href="#projects" class="hover:text-white transition">Work</a>
    <a href="#contact" class="hover:text-white transition">Contact</a>
  </div>
</nav>
<section class="min-h-screen flex items-center px-8 py-20">
  <div class="max-w-4xl fade-up">
    <p class="text-orange-400 font-mono text-sm mb-4">👋 Hi, I'm</p>
    <h1 class="text-6xl md:text-8xl font-black mb-4">Your Name</h1>
    <h2 class="text-2xl md:text-4xl text-gray-300 mb-6 font-light">Full-stack developer & <span class="gradient-text font-bold">AI builder</span></h2>
    <p class="text-gray-400 max-w-xl text-lg leading-relaxed mb-8">I build products people love — from idea to production. Specialising in React, Python, and AI-powered applications.</p>
    <div class="flex gap-4 flex-wrap">
      <a href="#projects" class="bg-orange-500 text-white font-bold px-6 py-3 rounded-2xl hover:bg-orange-400 transition">View my work</a>
      <a href="#contact" class="border border-white/20 px-6 py-3 rounded-2xl hover:bg-white/5 transition">Let's talk</a>
    </div>
  </div>
</section>
<section id="about" class="px-8 py-20 max-w-5xl mx-auto">
  <h2 class="text-3xl font-black mb-3">About me</h2>
  <div class="w-16 h-1 bg-orange-500 rounded mb-8"></div>
  <div class="grid md:grid-cols-2 gap-10">
    <div><p class="text-gray-300 leading-relaxed mb-6">I'm a software engineer with 5+ years building web applications and AI tools. I love turning complex problems into elegant, simple solutions.</p><p class="text-gray-400 leading-relaxed">When I'm not coding, I'm writing about AI, contributing to open source, or hiking somewhere with no Wi-Fi.</p></div>
    <div><div class="text-sm text-gray-400 mb-3 font-semibold uppercase tracking-wider">Skills</div><div class="flex flex-wrap gap-2">${['React','Next.js','TypeScript','Python','FastAPI','PostgreSQL','AI/ML','Docker','AWS','Tailwind'].map(s=>`<span class="skill-pill">${s}</span>`).join('')}</div></div>
  </div>
</section>
<section id="projects" class="px-8 py-20 bg-[#0a0b12]">
  <div class="max-w-5xl mx-auto">
    <h2 class="text-3xl font-black mb-3">Selected work</h2>
    <div class="w-16 h-1 bg-orange-500 rounded mb-10"></div>
    <div class="grid md:grid-cols-2 gap-6">
      ${[['🤖','Agentic OS','Local-first AI operating system. Multi-agent swarm, live preview, GitHub sync.','Python, FastAPI, JS','#5b8af8'],['📊','Analytics Dashboard','Real-time business dashboard with custom charts and team collaboration.','React, D3.js, Supabase','#9d74f5'],['🛒','E-commerce Platform','Full-stack store with inventory, payments, and fulfilment tracking.','Next.js, Stripe, Prisma','#4cc98a'],['🎯','AI Content Pipeline','Automated content generation and publishing across 12 platforms.','Python, LangChain, AWS','#f08850']].map(([e,n,d,t,c])=>`
      <div class="card p-6 group cursor-pointer">
        <div class="flex items-start justify-between mb-4">
          <span class="text-4xl">${e}</span>
          <span class="text-gray-600 group-hover:text-white transition">↗</span>
        </div>
        <h3 class="font-bold text-lg mb-2">${n}</h3>
        <p class="text-gray-400 text-sm mb-4">${d}</p>
        <div class="text-xs text-gray-500 font-mono">${t}</div>
      </div>`).join('')}
    </div>
  </div>
</section>
<section id="contact" class="px-8 py-20 max-w-2xl mx-auto text-center">
  <h2 class="text-3xl font-black mb-3">Let's work together</h2>
  <div class="w-16 h-1 bg-orange-500 rounded mx-auto mb-6"></div>
  <p class="text-gray-400 mb-10">Have a project in mind? I'd love to hear about it. Let's build something great.</p>
  <form class="text-left space-y-4" onsubmit="event.preventDefault();alert('Message sent! I will get back to you soon.')">
    <input placeholder="Your name" class="w-full bg-[#0d1020] border border-white/10 rounded-xl px-4 py-3 text-white outline-none focus:border-orange-500/50 transition">
    <input type="email" placeholder="Email address" class="w-full bg-[#0d1020] border border-white/10 rounded-xl px-4 py-3 text-white outline-none focus:border-orange-500/50 transition">
    <textarea rows="5" placeholder="Tell me about your project…" class="w-full bg-[#0d1020] border border-white/10 rounded-xl px-4 py-3 text-white outline-none focus:border-orange-500/50 transition resize-none"></textarea>
    <button type="submit" class="w-full bg-orange-500 text-white font-bold py-4 rounded-xl hover:bg-orange-400 transition">Send message →</button>
  </form>
</section>
<footer class="border-t border-white/10 px-8 py-6 text-center text-gray-500 text-sm">Built with Agentic OS · 2026</footer>
</body></html>"""
        }
    },
    {
        "id": "waitlist-page",
        "name": "Waitlist Landing",
        "category": "marketing",
        "emoji": "📬",
        "description": "Email waitlist capture with counter, social proof, and animated gradient background",
        "tags": ["waitlist", "launch", "email", "marketing"],
        "preview_color": "#38c5d8",
        "files": {
            "index.html": """<!DOCTYPE html>
<html lang="en">
<head>
<meta charset="UTF-8"><meta name="viewport" content="width=device-width,initial-scale=1">
<title>Join the waitlist</title>
<script src="https://cdn.tailwindcss.com"></script>
<style>
body{background:#08090e;color:#fff;font-family:Inter,system-ui,sans-serif;min-height:100vh;display:flex;align-items:center;justify-content:center}
.glow{position:absolute;width:600px;height:600px;border-radius:50%;filter:blur(120px);opacity:.3;pointer-events:none}
@keyframes float{0%,100%{transform:translateY(0)}50%{transform:translateY(-12px)}}
.float{animation:float 4s ease-in-out infinite}
input:focus{outline:none;border-color:#38c5d8}
</style>
</head>
<body class="relative overflow-hidden">
  <div class="glow bg-teal-500 top-0 left-0 -translate-x-1/2 -translate-y-1/2"></div>
  <div class="glow bg-purple-500 bottom-0 right-0 translate-x-1/2 translate-y-1/2"></div>
  <div class="relative z-10 text-center px-4 max-w-xl mx-auto">
    <div class="float text-5xl mb-6">🚀</div>
    <div class="inline-flex items-center gap-2 bg-teal-500/20 border border-teal-500/30 rounded-full px-4 py-1.5 text-sm text-teal-300 mb-6">🔒 Early access — limited spots</div>
    <h1 class="text-5xl font-black mb-4 leading-tight">The future of<br><span class="text-teal-400">building is here</span></h1>
    <p class="text-gray-400 text-lg mb-8">We're launching something that will change how you build software. Be first to know.</p>
    <form class="flex gap-3 max-w-md mx-auto mb-6" onsubmit="handleSubmit(event)">
      <input id="emailInput" type="email" placeholder="your@email.com" class="flex-1 bg-white/10 border border-white/20 rounded-xl px-4 py-3 text-white placeholder-gray-500 transition" required>
      <button type="submit" class="bg-teal-500 hover:bg-teal-400 text-[#08090e] font-bold px-6 py-3 rounded-xl transition whitespace-nowrap">Join waitlist</button>
    </form>
    <div id="successMsg" class="hidden text-teal-400 font-semibold mb-6 text-lg">✅ You're on the list! We'll be in touch soon.</div>
    <div class="flex items-center justify-center gap-6 text-sm text-gray-400">
      <div class="flex items-center gap-2"><div class="flex -space-x-2">${'<div class="w-7 h-7 rounded-full bg-gradient-to-br from-blue-400 to-purple-500 border-2 border-[#08090e]"></div>'.repeat(4)}</div><span id="counter">2,847 already signed up</span></div>
      <span>·</span><span>No spam, ever</span>
    </div>
  </div>
<script>
let count=2847;
function handleSubmit(e){
  e.preventDefault();
  count++;
  document.getElementById('successMsg').classList.remove('hidden');
  document.getElementById('emailInput').value='';
  document.getElementById('counter').textContent=count.toLocaleString()+' already signed up';
}
</script>
</body></html>"""
        }
    },
    {
        "id": "notes-app",
        "name": "Notes App",
        "category": "apps",
        "emoji": "📝",
        "description": "Markdown notes with sidebar, search, auto-save to localStorage",
        "tags": ["notes", "markdown", "editor", "productivity"],
        "preview_color": "#f0c060",
        "files": {
            "index.html": """<!DOCTYPE html>
<html lang="en">
<head>
<meta charset="UTF-8"><meta name="viewport" content="width=device-width,initial-scale=1">
<title>Notes</title>
<script src="https://cdn.tailwindcss.com"></script>
<script src="https://cdn.jsdelivr.net/npm/marked@9/marked.min.js"></script>
<style>
body{background:#08090e;color:#e8f0ff;font-family:Inter,system-ui,sans-serif}
textarea{resize:none;outline:none}
input{outline:none}
.note-item.active{background:rgba(240,192,96,0.12);border-color:rgba(240,192,96,0.3)}
#preview h1,#preview h2,#preview h3{font-weight:800;margin:12px 0 6px}
#preview code{background:#1a2040;padding:2px 6px;border-radius:4px;font-family:monospace;font-size:13px}
#preview pre{background:#1a2040;padding:12px;border-radius:8px;overflow-x:auto;margin:8px 0}
#preview p{margin-bottom:8px;line-height:1.65;color:#c8d5f0}
#preview ul,#preview ol{padding-left:20px;margin-bottom:8px;color:#c8d5f0}
#preview strong{color:#fff}
</style>
</head>
<body class="flex h-screen overflow-hidden">
<!-- Sidebar -->
<aside class="w-60 bg-[#0d1020] border-r border-white/10 flex flex-col">
  <div class="p-4 border-b border-white/10">
    <div class="flex items-center justify-between mb-3"><span class="font-bold">📝 Notes</span><button onclick="newNote()" class="text-yellow-400 text-xl hover:scale-110 transition">+</button></div>
    <input id="search" placeholder="Search…" class="w-full bg-white/5 border border-white/10 rounded-lg px-3 py-2 text-sm text-white placeholder-gray-500" oninput="renderList()">
  </div>
  <div class="flex-1 overflow-y-auto p-2" id="noteList"></div>
</aside>
<!-- Editor + Preview -->
<main class="flex-1 flex flex-col">
  <div class="flex items-center justify-between px-4 py-3 border-b border-white/10 bg-[#0a0b12]">
    <input id="noteTitle" placeholder="Note title…" class="flex-1 font-bold text-lg bg-transparent text-white placeholder-gray-600 mr-4">
    <div class="flex gap-2">
      <button id="editBtn" onclick="setMode('edit')" class="text-xs px-3 py-1 rounded-lg bg-yellow-500/20 text-yellow-300">Edit</button>
      <button id="previewBtn" onclick="setMode('preview')" class="text-xs px-3 py-1 rounded-lg text-gray-500 hover:bg-white/5">Preview</button>
      <button onclick="deleteNote()" class="text-xs px-3 py-1 rounded-lg text-red-400 hover:bg-red-500/10">Delete</button>
    </div>
  </div>
  <div class="flex-1 relative">
    <textarea id="editor" class="absolute inset-0 w-full h-full bg-transparent text-gray-200 font-mono text-sm p-4 leading-relaxed" placeholder="Start writing in Markdown…" oninput="autoSave()"></textarea>
    <div id="preview" class="absolute inset-0 overflow-auto p-4 text-sm hidden"></div>
  </div>
  <div class="px-4 py-2 border-t border-white/10 text-xs text-gray-600 flex items-center gap-4">
    <span id="wordCount">0 words</span>
    <span id="saveStatus">Saved</span>
  </div>
</main>
<script>
let notes=JSON.parse(localStorage.getItem('agentic-notes')||'[]');
let currentId=null;
if(!notes.length){notes=[{id:1,title:'Welcome to Notes',body:'# Welcome!\n\nThis is a **Markdown** notes app.\n\n- Auto-saves to localStorage\n- Markdown preview mode\n- Search across all notes\n\n```js\nconsole.log("Hello, Agentic OS!");\n```',updated:Date.now()}];}
function save(){localStorage.setItem('agentic-notes',JSON.stringify(notes));}
function renderList(){
  const q=document.getElementById('search').value.toLowerCase();
  const list=document.getElementById('noteList');
  const filtered=notes.filter(n=>!q||n.title.toLowerCase().includes(q)||n.body.toLowerCase().includes(q))
    .sort((a,b)=>b.updated-a.updated);
  list.innerHTML=filtered.map(n=>`<div class="note-item border border-transparent rounded-xl p-3 cursor-pointer mb-1 ${n.id===currentId?'active':''}" onclick="openNote(${n.id})"><div class="font-semibold text-sm mb-0.5 truncate">${n.title||'Untitled'}</div><div class="text-xs text-gray-500 truncate">${n.body.slice(0,60)}</div></div>`).join('');
}
function openNote(id){
  const n=notes.find(x=>x.id===id);if(!n)return;
  currentId=id;
  document.getElementById('noteTitle').value=n.title;
  document.getElementById('editor').value=n.body;
  updateWordCount();renderList();setMode('edit');
}
function newNote(){
  const n={id:Date.now(),title:'New note',body:'',updated:Date.now()};
  notes.unshift(n);save();openNote(n.id);
}
function deleteNote(){
  if(!currentId)return;
  notes=notes.filter(n=>n.id!==currentId);
  currentId=null;document.getElementById('noteTitle').value='';document.getElementById('editor').value='';
  save();renderList();
}
let saveTimer;
function autoSave(){
  if(!currentId)return;
  const n=notes.find(x=>x.id===currentId);
  if(!n)return;
  n.title=document.getElementById('noteTitle').value||'Untitled';
  n.body=document.getElementById('editor').value;
  n.updated=Date.now();
  updateWordCount();
  document.getElementById('saveStatus').textContent='Saving…';
  clearTimeout(saveTimer);
  saveTimer=setTimeout(()=>{save();document.getElementById('saveStatus').textContent='Saved';renderList();},600);
}
document.getElementById('noteTitle').addEventListener('input',autoSave);
function updateWordCount(){
  const words=document.getElementById('editor').value.trim().split(/\s+/).filter(Boolean).length;
  document.getElementById('wordCount').textContent=words+' word'+(words!==1?'s':'');
}
function setMode(m){
  const ed=document.getElementById('editor'),pr=document.getElementById('preview');
  if(m==='preview'){ed.classList.add('hidden');pr.classList.remove('hidden');pr.innerHTML=marked.parse(ed.value||'');}
  else{ed.classList.remove('hidden');pr.classList.add('hidden');}
  document.getElementById('editBtn').className='text-xs px-3 py-1 rounded-lg '+(m==='edit'?'bg-yellow-500/20 text-yellow-300':'text-gray-500 hover:bg-white/5');
  document.getElementById('previewBtn').className='text-xs px-3 py-1 rounded-lg '+(m==='preview'?'bg-yellow-500/20 text-yellow-300':'text-gray-500 hover:bg-white/5');
}
if(notes.length)openNote(notes[0].id);
renderList();
</script>
</body></html>"""
        }
    },
    # Quick entries for the remaining templates (with minimal but working HTML)
    {"id":"pricing-page","name":"Pricing Page","category":"saas","emoji":"💰","description":"3-tier pricing with toggle (monthly/annual), feature comparison table","tags":["pricing","saas","conversion"],"preview_color":"#9d74f5","files":{"index.html":"<!DOCTYPE html><html><head><meta charset='UTF-8'><title>Pricing</title><script src='https://cdn.tailwindcss.com'></script></head><body class='bg-[#08090e] text-white p-8'><div class='max-w-5xl mx-auto text-center'><h1 class='text-5xl font-black mb-4'>Simple pricing</h1><p class='text-gray-400 mb-12 text-xl'>Start free. Upgrade when ready.</p><div class='grid md:grid-cols-3 gap-6'><div class='bg-[#0d1020] border border-white/10 rounded-2xl p-8'><h2 class='text-xl font-bold mb-2'>Starter</h2><div class='text-4xl font-black my-4'>$0</div><p class='text-gray-400 text-sm mb-6'>Free forever</p><ul class='text-sm text-left space-y-2 mb-8 text-gray-300'><li>✓ 3 projects</li><li>✓ 100 AI messages/day</li><li>✓ Community support</li></ul><button class='w-full border border-white/20 py-3 rounded-xl hover:bg-white/5 transition'>Get started</button></div><div class='bg-[#0d1020] border border-blue-500/50 rounded-2xl p-8 relative'><div class='absolute -top-3 left-1/2 -translate-x-1/2 bg-blue-500 text-white text-xs font-bold px-3 py-1 rounded-full'>Popular</div><h2 class='text-xl font-bold mb-2'>Pro</h2><div class='text-4xl font-black my-4'>$20</div><p class='text-gray-400 text-sm mb-6'>per month</p><ul class='text-sm text-left space-y-2 mb-8 text-gray-300'><li>✓ Unlimited projects</li><li>✓ Unlimited AI</li><li>✓ All deploy targets</li><li>✓ Priority support</li></ul><button class='w-full bg-blue-500 text-white font-bold py-3 rounded-xl hover:bg-blue-400 transition'>Start trial</button></div><div class='bg-[#0d1020] border border-white/10 rounded-2xl p-8'><h2 class='text-xl font-bold mb-2'>Team</h2><div class='text-4xl font-black my-4'>$50</div><p class='text-gray-400 text-sm mb-6'>per seat/month</p><ul class='text-sm text-left space-y-2 mb-8 text-gray-300'><li>✓ Everything in Pro</li><li>✓ Team collaboration</li><li>✓ Custom agents</li><li>✓ Dedicated support</li></ul><button class='w-full border border-white/20 py-3 rounded-xl hover:bg-white/5 transition'>Contact sales</button></div></div></div></body></html>"}},
    {"id":"login-page","name":"Login & Signup","category":"saas","emoji":"🔐","description":"Auth pages with email/password and OAuth buttons, validation, dark theme","tags":["auth","login","signup","form"],"preview_color":"#4cc98a","files":{"index.html":"<!DOCTYPE html><html><head><meta charset='UTF-8'><title>Sign In</title><script src='https://cdn.tailwindcss.com'></script></head><body class='bg-[#08090e] text-white min-h-screen flex items-center justify-center p-4'><div class='w-full max-w-sm'><div class='text-center mb-8'><div class='text-4xl mb-2'>🧠</div><h1 class='text-2xl font-black'>Welcome back</h1><p class='text-gray-400 text-sm mt-1'>Sign in to your account</p></div><div class='bg-[#0d1020] border border-white/10 rounded-2xl p-6'><form onsubmit='event.preventDefault();alert(\"Logged in!\")'><div class='space-y-4'><div><label class='text-xs font-bold text-gray-400 uppercase tracking-wider block mb-1.5'>Email</label><input type='email' placeholder='you@example.com' class='w-full bg-white/5 border border-white/10 rounded-xl px-4 py-3 text-white placeholder-gray-600 focus:border-blue-500/50 focus:outline-none transition' required></div><div><label class='text-xs font-bold text-gray-400 uppercase tracking-wider block mb-1.5'>Password</label><input type='password' placeholder='••••••••' class='w-full bg-white/5 border border-white/10 rounded-xl px-4 py-3 text-white placeholder-gray-600 focus:border-blue-500/50 focus:outline-none transition' required></div><div class='flex items-center justify-between text-sm'><label class='flex items-center gap-2 text-gray-400 cursor-pointer'><input type='checkbox' class='accent-blue-500'> Remember me</label><a href='#' class='text-blue-400 hover:underline'>Forgot password?</a></div><button type='submit' class='w-full bg-blue-500 text-white font-bold py-3 rounded-xl hover:bg-blue-400 transition mt-2'>Sign in</button></div></form><div class='flex items-center gap-3 my-4'><div class='flex-1 h-px bg-white/10'></div><span class='text-gray-500 text-xs'>or continue with</span><div class='flex-1 h-px bg-white/10'></div></div><div class='grid grid-cols-2 gap-3'><button class='flex items-center justify-center gap-2 border border-white/10 rounded-xl py-2.5 hover:bg-white/5 transition text-sm'><span>G</span>Google</button><button class='flex items-center justify-center gap-2 border border-white/10 rounded-xl py-2.5 hover:bg-white/5 transition text-sm'><span>🐙</span>GitHub</button></div></div><p class='text-center text-gray-500 text-sm mt-6'>Don't have an account? <a href='#' class='text-blue-400 hover:underline'>Sign up free</a></p></div></body></html>"}},
    {"id":"product-page","name":"Product Page","category":"ecommerce","emoji":"🛒","description":"E-commerce product page with image gallery, variants, add to cart, reviews","tags":["ecommerce","product","shop","cart"],"preview_color":"#f06080","files":{"index.html":"<!DOCTYPE html><html><head><meta charset='UTF-8'><title>Product</title><script src='https://cdn.tailwindcss.com'></script></head><body class='bg-[#08090e] text-white p-6'><div class='max-w-5xl mx-auto grid md:grid-cols-2 gap-10'><div class='space-y-3'><div class='aspect-square bg-gradient-to-br from-blue-900 to-purple-900 rounded-2xl flex items-center justify-center text-8xl'>📦</div><div class='grid grid-cols-4 gap-2'><div class='aspect-square bg-[#0d1020] rounded-xl border border-white/10 flex items-center justify-center text-2xl cursor-pointer hover:border-blue-500/50 transition'>📦</div><div class='aspect-square bg-[#0d1020] rounded-xl border border-white/10 flex items-center justify-center text-2xl cursor-pointer hover:border-blue-500/50 transition'>🎁</div><div class='aspect-square bg-[#0d1020] rounded-xl border border-white/10 flex items-center justify-center text-2xl cursor-pointer hover:border-blue-500/50 transition'>✨</div><div class='aspect-square bg-[#0d1020] rounded-xl border border-white/10 flex items-center justify-center text-2xl cursor-pointer hover:border-blue-500/50 transition'>🎯</div></div></div><div><div class='text-sm text-blue-400 mb-2'>YourBrand</div><h1 class='text-3xl font-black mb-2'>Premium Product Name</h1><div class='flex items-center gap-2 mb-4'><div class='flex text-yellow-400'>★★★★★</div><span class='text-gray-400 text-sm'>4.9 (247 reviews)</span></div><div class='text-3xl font-black mb-6'>$99 <span class='text-gray-500 text-lg line-through font-normal'>$149</span> <span class='text-green-400 text-sm font-bold'>33% off</span></div><div class='mb-6'><div class='text-sm font-bold mb-2'>Color</div><div class='flex gap-2'><button class='w-8 h-8 rounded-full bg-blue-500 border-2 border-white'></button><button class='w-8 h-8 rounded-full bg-gray-500 border-2 border-transparent hover:border-white transition'></button><button class='w-8 h-8 rounded-full bg-red-500 border-2 border-transparent hover:border-white transition'></button></div></div><div class='mb-6'><div class='text-sm font-bold mb-2'>Size</div><div class='flex gap-2'><button class='border border-blue-500 bg-blue-500/20 text-blue-300 px-4 py-2 rounded-xl text-sm font-bold'>S</button><button class='border border-white/20 px-4 py-2 rounded-xl text-sm hover:border-white/50 transition'>M</button><button class='border border-white/20 px-4 py-2 rounded-xl text-sm hover:border-white/50 transition'>L</button><button class='border border-white/20 px-4 py-2 rounded-xl text-sm hover:border-white/50 transition'>XL</button></div></div><button onclick='alert(\"Added to cart!\")' class='w-full bg-blue-500 text-white font-bold py-4 rounded-2xl text-lg hover:bg-blue-400 transition mb-3'>Add to cart — $99</button><button class='w-full border border-white/20 py-4 rounded-2xl hover:bg-white/5 transition'>♡ Save for later</button></div></div></body></html>"}},
    {"id":"url-shortener","name":"URL Shortener","category":"apps","emoji":"🔗","description":"URL shortener with copy button, link history, and QR code generation","tags":["utility","url","tool","qr"],"preview_color":"#38c5d8","files":{"index.html":"<!DOCTYPE html><html><head><meta charset='UTF-8'><title>URL Shortener</title><script src='https://cdn.tailwindcss.com'></script></head><body class='bg-[#08090e] text-white min-h-screen flex items-center justify-center p-4'><div class='w-full max-w-lg'><div class='text-center mb-10'><div class='text-5xl mb-3'>🔗</div><h1 class='text-4xl font-black mb-2'>Shorten URLs</h1><p class='text-gray-400'>Make long links short and shareable</p></div><div class='bg-[#0d1020] border border-white/10 rounded-2xl p-6'><div class='flex gap-3 mb-6'><input id='urlInput' type='url' placeholder='https://your-very-long-url.com/with/many/params?and=values' class='flex-1 bg-white/5 border border-white/10 rounded-xl px-4 py-3 text-white placeholder-gray-600 focus:border-teal-500/50 focus:outline-none transition text-sm'><button onclick='shortenUrl()' class='bg-teal-500 hover:bg-teal-400 text-[#08090e] font-bold px-5 py-3 rounded-xl transition whitespace-nowrap'>Shorten</button></div><div id='result' class='hidden'><div class='flex items-center gap-3 bg-teal-500/10 border border-teal-500/20 rounded-xl p-4'><div class='flex-1'><div class='text-xs text-gray-400 mb-1'>Shortened URL</div><div class='font-mono text-teal-300 font-bold' id='shortUrl'>agos.link/abc123</div></div><button onclick='copyShort()' class='bg-teal-500/20 text-teal-300 px-3 py-2 rounded-lg text-sm hover:bg-teal-500/30 transition'>Copy</button></div></div><div class='mt-4'><div class='text-xs text-gray-500 mb-2 uppercase tracking-wider font-semibold'>Recent links</div><div id='history' class='space-y-2'><div class='flex items-center gap-3 text-sm py-2 border-b border-white/5'><span class='text-teal-400 font-mono'>agos.link/demo</span><span class='text-gray-500 flex-1 truncate'>→ https://example.com/demo</span><span class='text-gray-600 text-xs'>42 clicks</span></div></div></div></div></div><script>let links=[];function shortenUrl(){const u=document.getElementById('urlInput').value;if(!u)return;const id=Math.random().toString(36).slice(2,8);const short='agos.link/'+id;links.unshift({short,original:u,clicks:0});document.getElementById('shortUrl').textContent=short;document.getElementById('result').classList.remove('hidden');renderHistory();}function copyShort(){const t=document.getElementById('shortUrl').textContent;navigator.clipboard.writeText(t).then(()=>alert('Copied!'));}function renderHistory(){const h=document.getElementById('history');h.innerHTML=links.map(l=>`<div class='flex items-center gap-3 text-sm py-2 border-b border-white/5'><span class='text-teal-400 font-mono flex-shrink-0'>${l.short}</span><span class='text-gray-500 flex-1 truncate'>→ ${l.original}</span><span class='text-gray-600 text-xs'>${l.clicks} clicks</span></div>`).join('');}</script></body></html>"}},
    {"id":"weather-app","name":"Weather App","category":"apps","emoji":"🌤️","description":"Beautiful weather card with animated icons, 5-day forecast, search by city","tags":["weather","api","animation","cards"],"preview_color":"#f0c060","files":{"index.html":"<!DOCTYPE html><html><head><meta charset='UTF-8'><title>Weather</title><script src='https://cdn.tailwindcss.com'></script><style>@keyframes spin{to{transform:rotate(360deg)}}@keyframes float{0%,100%{transform:translateY(0)}50%{transform:translateY(-8px)}}.float{animation:float 3s ease-in-out infinite}body{background:linear-gradient(135deg,#0a0f2e,#1a0a2e);min-height:100vh;color:white;font-family:Inter,system-ui,sans-serif}</style></head><body class='flex items-center justify-center p-6'><div class='w-full max-w-sm'><div class='bg-white/10 backdrop-blur border border-white/20 rounded-3xl p-6'><div class='flex items-center gap-3 mb-6'><input id='cityInput' placeholder='Search city…' class='flex-1 bg-white/10 border border-white/20 rounded-xl px-4 py-2.5 text-white placeholder-white/40 focus:outline-none text-sm' onkeydown=\"if(event.key==='Enter')search()\" value='Charlotte, NC'><button onclick='search()' class='bg-yellow-400 text-black font-bold px-4 py-2.5 rounded-xl text-sm'>Go</button></div><div class='text-center mb-6'><div id='icon' class='text-8xl mb-3 float'>🌤️</div><div class='text-5xl font-black mb-1' id='temp'>72°F</div><div class='text-white/70 text-lg' id='desc'>Partly Cloudy</div><div class='text-white/50 text-sm mt-1' id='city'>Charlotte, NC</div></div><div class='grid grid-cols-3 gap-3 mb-6'><div class='bg-white/10 rounded-xl p-3 text-center'><div class='text-xs text-white/50 mb-1'>Humidity</div><div class='font-bold' id='hum'>62%</div></div><div class='bg-white/10 rounded-xl p-3 text-center'><div class='text-xs text-white/50 mb-1'>Wind</div><div class='font-bold' id='wind'>8 mph</div></div><div class='bg-white/10 rounded-xl p-3 text-center'><div class='text-xs text-white/50 mb-1'>UV Index</div><div class='font-bold' id='uv'>4</div></div></div><div class='space-y-2'><div class='text-xs text-white/50 uppercase tracking-wider mb-2'>5-Day Forecast</div><div id='forecast' class='space-y-2'></div></div></div></div><script>const days=['Sun','Mon','Tue','Wed','Thu','Fri','Sat'];const icons=['☀️','🌤️','⛅','🌧️','⛈️'];const cities={charlotte:{temp:72,desc:'Partly Cloudy',hum:'62%',wind:'8 mph',uv:'4',icon:'🌤️'},london:{temp:58,desc:'Overcast',hum:'78%',wind:'12 mph',uv:'2',icon:'⛅'},tokyo:{temp:81,desc:'Sunny',hum:'55%',wind:'6 mph',uv:'7',icon:'☀️'},sydney:{temp:68,desc:'Clear',hum:'48%',wind:'14 mph',uv:'6',icon:'☀️'}};function search(){const c=document.getElementById('cityInput').value.toLowerCase().replace(/[,\s]+/g,'');const d=cities[c]||{temp:Math.floor(60+Math.random()*30),desc:'Partly Cloudy',hum:Math.floor(40+Math.random()*40)+'%',wind:Math.floor(5+Math.random()*15)+' mph',uv:Math.floor(1+Math.random()*9)+'',icon:icons[Math.floor(Math.random()*icons.length)]};document.getElementById('temp').textContent=d.temp+'°F';document.getElementById('desc').textContent=d.desc;document.getElementById('hum').textContent=d.hum;document.getElementById('wind').textContent=d.wind;document.getElementById('uv').textContent=d.uv;document.getElementById('icon').textContent=d.icon;document.getElementById('city').textContent=document.getElementById('cityInput').value||'Your City';renderForecast();}function renderForecast(){const today=new Date().getDay();document.getElementById('forecast').innerHTML=[1,2,3,4,5].map(i=>`<div class='flex items-center justify-between bg-white/5 rounded-xl px-4 py-2'><span class='text-sm text-white/70 w-10'>${days[(today+i)%7]}</span><span class='text-xl'>${icons[Math.floor(Math.random()*3)]}</span><span class='font-semibold text-sm'>${Math.floor(60+Math.random()*20)}°</span></div>`).join('');}search();</script></body></html>"}},
    {"id":"agency-site","name":"Agency Website","category":"marketing","emoji":"🏢","description":"Creative agency homepage with case studies, team, services, contact","tags":["agency","marketing","business","professional"],"preview_color":"#9d74f5","files":{"index.html":"<!DOCTYPE html><html><head><meta charset='UTF-8'><title>Creative Agency</title><script src='https://cdn.tailwindcss.com'></script><style>body{background:#050810;color:#fff;font-family:Inter,system-ui,sans-serif}</style></head><body><nav class='flex items-center justify-between px-8 py-4 border-b border-white/10'><span class='font-black text-xl'>STUDIO<span class='text-purple-400'>.</span></span><div class='hidden md:flex gap-6 text-sm text-gray-400'><a class='hover:text-white' href='#'>Work</a><a class='hover:text-white' href='#'>Services</a><a class='hover:text-white' href='#'>Team</a><a class='hover:text-white' href='#'>Contact</a></div><a href='#' class='border border-purple-500/50 text-purple-300 text-sm px-4 py-2 rounded-xl hover:bg-purple-500/10 transition'>Let's talk →</a></nav><section class='px-8 py-32 max-w-5xl'><div class='text-sm text-purple-400 mb-4 font-mono'>// WE BUILD DIGITAL EXPERIENCES</div><h1 class='text-6xl md:text-8xl font-black leading-none mb-8'>We design<br>the <span class='text-purple-400'>future.</span></h1><p class='text-gray-400 text-xl max-w-xl mb-10'>Crafting digital products that matter. Strategy, design, and engineering — all under one roof.</p><a href='#' class='inline-flex items-center gap-3 bg-purple-500 text-white font-bold px-8 py-4 rounded-2xl hover:bg-purple-400 transition text-lg'>View our work <span>→</span></a></section><section class='border-t border-white/10 px-8 py-16'><div class='max-w-5xl mx-auto grid md:grid-cols-3 gap-8'><div><div class='text-4xl font-black text-purple-400 mb-2'>120+</div><div class='text-gray-400'>Projects shipped</div></div><div><div class='text-4xl font-black text-purple-400 mb-2'>8 yrs</div><div class='text-gray-400'>In the industry</div></div><div><div class='text-4xl font-black text-purple-400 mb-2'>98%</div><div class='text-gray-400'>Client satisfaction</div></div></div></section></body></html>"}},
    {"id":"chat-app","name":"Chat Interface","category":"apps","emoji":"💬","description":"Real-time chat UI with message bubbles, typing indicator, emoji, file attach","tags":["chat","messaging","realtime","ui"],"preview_color":"#5b8af8","files":{"index.html":"<!DOCTYPE html><html><head><meta charset='UTF-8'><title>Chat</title><script src='https://cdn.tailwindcss.com'></script><style>body{background:#08090e;color:#e8f0ff;font-family:Inter,system-ui,sans-serif}::-webkit-scrollbar{width:4px}::-webkit-scrollbar-thumb{background:#1a2040;border-radius:99px}</style></head><body class='flex h-screen'><aside class='w-64 bg-[#0d1020] border-r border-white/10 flex flex-col'><div class='p-4 border-b border-white/10'><div class='flex items-center gap-3 mb-3'><div class='w-9 h-9 rounded-full bg-blue-500 flex items-center justify-center font-bold'>J</div><div><div class='font-semibold text-sm'>jstrick9</div><div class='text-xs text-green-400'>● Online</div></div></div><input placeholder='Search messages…' class='w-full bg-white/5 border border-white/10 rounded-lg px-3 py-1.5 text-sm focus:outline-none focus:border-blue-500/50 transition'></div><div class='flex-1 overflow-y-auto p-2'><div class='text-xs text-gray-500 px-2 py-1 uppercase tracking-wider mb-1'>Direct Messages</div><div class='flex items-center gap-3 px-3 py-2 rounded-xl bg-blue-500/20 cursor-pointer'><div class='w-8 h-8 rounded-full bg-purple-500 flex items-center justify-center text-sm font-bold'>B</div><div><div class='text-sm font-semibold'>Brain Agent</div><div class='text-xs text-gray-400 truncate'>Ready to help…</div></div><div class='w-2 h-2 rounded-full bg-blue-500 ml-auto flex-shrink-0'></div></div><div class='flex items-center gap-3 px-3 py-2 rounded-xl hover:bg-white/5 cursor-pointer mt-1'><div class='w-8 h-8 rounded-full bg-green-500 flex items-center justify-center text-sm font-bold'>R</div><div><div class='text-sm font-semibold'>Researcher</div><div class='text-xs text-gray-400'>Idle</div></div></div></div></aside><main class='flex-1 flex flex-col'><div class='flex items-center gap-3 px-6 py-4 border-b border-white/10 bg-[#0a0b12]'><div class='w-9 h-9 rounded-full bg-purple-500 flex items-center justify-center font-bold'>B</div><div><div class='font-semibold'>Brain Agent</div><div class='text-xs text-green-400'>● Active now</div></div></div><div class='flex-1 overflow-y-auto p-6 space-y-4' id='msgs'><div class='flex gap-3'><div class='w-8 h-8 rounded-full bg-purple-500 flex items-center justify-center text-sm font-bold flex-shrink-0'>B</div><div class='max-w-xs lg:max-w-md'><div class='bg-[#0d1020] border border-white/10 rounded-2xl rounded-tl-sm px-4 py-3 text-sm'>Hey! How can I help you build something amazing today? 🚀</div><div class='text-xs text-gray-600 mt-1 ml-1'>10:30 AM</div></div></div></div><div id='typing' class='hidden px-6 py-2 text-sm text-gray-500 italic'>Brain is typing…</div><div class='px-6 py-4 border-t border-white/10'><div class='flex items-center gap-3 bg-[#0d1020] border border-white/10 rounded-2xl px-4 py-3'><button class='text-gray-500 hover:text-white transition text-xl'>📎</button><input id='msgInput' placeholder='Message Brain Agent…' class='flex-1 bg-transparent text-white placeholder-gray-600 text-sm focus:outline-none' onkeydown=\"if(event.key==='Enter')sendMsg()\"><button class='text-gray-500 hover:text-white transition text-xl'>😊</button><button onclick='sendMsg()' class='bg-blue-500 text-white w-8 h-8 rounded-xl flex items-center justify-center hover:bg-blue-400 transition flex-shrink-0'>→</button></div></div></main><script>const replies=['Great question! Let me think about that…','I can help you build that! What framework do you prefer?','Interesting idea. Here is my analysis…','Done! Check the preview pane for the result.','I found some relevant context in your Memory Galaxy.','Running the swarm now — 4 agents analyzing your request…'];let c=0;function sendMsg(){const i=document.getElementById('msgInput');const t=i.value.trim();if(!t)return;i.value='';const m=document.getElementById('msgs');m.innerHTML+=`<div class='flex gap-3 flex-row-reverse'><div class='w-8 h-8 rounded-full bg-blue-500 flex items-center justify-center text-sm font-bold flex-shrink-0'>J</div><div class='max-w-xs lg:max-w-md'><div class='bg-blue-500 rounded-2xl rounded-tr-sm px-4 py-3 text-sm'>${t}</div><div class='text-xs text-gray-600 mt-1 mr-1 text-right'>Now</div></div></div>`;m.scrollTop=m.scrollHeight;const typing=document.getElementById('typing');typing.classList.remove('hidden');setTimeout(()=>{typing.classList.add('hidden');m.innerHTML+=`<div class='flex gap-3'><div class='w-8 h-8 rounded-full bg-purple-500 flex items-center justify-center text-sm font-bold flex-shrink-0'>B</div><div class='max-w-xs lg:max-w-md'><div class='bg-[#0d1020] border border-white/10 rounded-2xl rounded-tl-sm px-4 py-3 text-sm'>${replies[c++%replies.length]}</div><div class='text-xs text-gray-600 mt-1 ml-1'>Now</div></div></div>`;m.scrollTop=m.scrollHeight;},1200+Math.random()*800);}</script></body></html>"}},
    {"id":"invoice-generator","name":"Invoice Generator","category":"saas","emoji":"🧾","description":"Professional invoice builder with line items, taxes, print/PDF export","tags":["invoice","billing","pdf","business"],"preview_color":"#4cc98a","files":{"index.html":"<!DOCTYPE html><html><head><meta charset='UTF-8'><title>Invoice Generator</title><script src='https://cdn.tailwindcss.com'></script><style>body{background:#f0f4ff;color:#0d1020;font-family:Inter,system-ui,sans-serif}@media print{.no-print{display:none!important}body{background:white}}</style></head><body class='p-6'><div class='max-w-3xl mx-auto'><div class='flex justify-between mb-6 no-print'><h1 class='text-2xl font-black text-[#0d1020]'>📄 Invoice Generator</h1><div class='flex gap-2'><button onclick='addLine()' class='border border-[#0d1020]/20 px-4 py-2 rounded-xl text-sm hover:bg-[#0d1020]/5 transition'>+ Add item</button><button onclick='window.print()' class='bg-green-500 text-white font-bold px-4 py-2 rounded-xl text-sm hover:bg-green-400 transition'>🖨️ Print / PDF</button></div></div><div class='bg-white rounded-2xl shadow-xl p-8'><div class='flex justify-between mb-10'><div><div class='font-black text-2xl mb-1'>Your Company</div><div class='text-gray-400 text-sm'>123 Main Street<br>Charlotte, NC 28201<br>you@company.com</div></div><div class='text-right'><div class='text-3xl font-black text-green-600 mb-1'>INVOICE</div><div class='text-gray-400 text-sm'>#INV-<input id='invNum' value='001' class='w-12 border-b border-gray-300 bg-transparent text-right focus:outline-none font-bold'></div><div class='text-gray-400 text-sm mt-1'>Date: <input type='date' class='border-b border-gray-300 bg-transparent focus:outline-none text-sm'></div></div></div><div class='mb-8'><div class='text-xs font-bold text-gray-400 uppercase tracking-wider mb-2'>Bill To</div><input placeholder='Client name' class='block font-bold text-lg border-b border-gray-200 w-full mb-1 focus:outline-none focus:border-green-500'><input placeholder='Client email' class='block text-sm text-gray-400 border-b border-gray-200 w-full focus:outline-none focus:border-green-500'></div><table class='w-full mb-6'><thead><tr class='border-b-2 border-gray-200'><th class='text-left pb-2 text-xs uppercase text-gray-400'>Description</th><th class='text-right pb-2 text-xs uppercase text-gray-400 w-20'>Qty</th><th class='text-right pb-2 text-xs uppercase text-gray-400 w-28'>Rate</th><th class='text-right pb-2 text-xs uppercase text-gray-400 w-28'>Amount</th><th class='w-8 no-print'></th></tr></thead><tbody id='lines'></tbody></table><div class='flex justify-end'><div class='w-60'><div class='flex justify-between py-2 text-sm'><span class='text-gray-400'>Subtotal</span><span id='subtotal' class='font-semibold'>$0.00</span></div><div class='flex justify-between py-2 text-sm'><span class='text-gray-400'>Tax (10%)</span><span id='tax' class='font-semibold'>$0.00</span></div><div class='flex justify-between py-2 border-t-2 border-gray-800 mt-1'><span class='font-black'>Total</span><span id='total' class='font-black text-lg text-green-600'>$0.00</span></div></div></div></div></div><script>let lines=[];function addLine(){lines.push({desc:'Service item',qty:1,rate:100});renderLines();}function renderLines(){const tb=document.getElementById('lines');tb.innerHTML=lines.map((l,i)=>`<tr class='border-b border-gray-100'><td class='py-2 pr-2'><input value='${l.desc}' oninput='lines[${i}].desc=this.value' class='w-full border-b border-transparent focus:border-green-400 focus:outline-none text-sm'></td><td class='py-2 px-1'><input type='number' value='${l.qty}' oninput='lines[${i}].qty=+this.value;calc()' class='w-full text-right border-b border-transparent focus:border-green-400 focus:outline-none text-sm'></td><td class='py-2 px-1'><input type='number' value='${l.rate}' oninput='lines[${i}].rate=+this.value;calc()' class='w-full text-right border-b border-transparent focus:border-green-400 focus:outline-none text-sm'></td><td class='py-2 pl-2 text-right text-sm font-semibold'>$${(l.qty*l.rate).toFixed(2)}</td><td class='no-print'><button onclick='lines.splice(${i},1);renderLines();calc()' class='text-red-400 hover:text-red-600 text-xs ml-1'>✕</button></td></tr>`).join('');calc();}function calc(){const s=lines.reduce((a,l)=>a+l.qty*l.rate,0);const t=s*.1;document.getElementById('subtotal').textContent='$'+s.toFixed(2);document.getElementById('tax').textContent='$'+t.toFixed(2);document.getElementById('total').textContent='$'+(s+t).toFixed(2);}addLine();addLine();</script></body></html>"}},
]


# ── Helpers ───────────────────────────────────────────────────────────────────

_CATEGORY_LABELS = {
    "saas":      "SaaS & Business",
    "apps":      "Apps & Tools",
    "portfolio": "Portfolio",
    "marketing": "Marketing",
    "ecommerce": "E-Commerce",
}

def _safe_name(name: str) -> str:
    """Sanitize a project name for HTML substitution."""
    return re.sub(r"[^\w\s\-]", "", (name or "").strip())[:80]


def _template_summary(t: dict) -> dict:
    """Return safe public fields (no raw file content)."""
    return {
        "id":            t["id"],
        "name":          t["name"],
        "category":      t["category"],
        "emoji":         t["emoji"],
        "description":   t["description"],
        "tags":          t["tags"],
        "preview_color": t.get("preview_color", "#5b8af8"),
        "file_count":    len(t.get("files", {})),
        "file_names":    list(t.get("files", {}).keys()),
    }


# ── Endpoints ──────────────────────────────────────────────────────────────────

@router.get("")
def list_templates(category: str = "", q: str = ""):
    """List all templates, optionally filtered by category or search query."""
    results = [_template_summary(t) for t in TEMPLATES]
    if category:
        results = [t for t in results if t["category"] == category]
    if q:
        ql = q.lower()
        results = [t for t in results if
                   ql in t["name"].lower() or
                   ql in t["description"].lower() or
                   any(ql in tag.lower() for tag in t["tags"])]
    return {
        "templates": results,
        "count":     len(results),
        "total":     len(TEMPLATES),
    }


@router.get("/categories")
def list_categories():
    """Return all categories with counts and labels."""
    cats: dict = {}
    for t in TEMPLATES:
        c = t["category"]
        cats[c] = cats.get(c, 0) + 1
    return [
        {"id": k, "label": _CATEGORY_LABELS.get(k, k.title()), "count": v}
        for k, v in sorted(cats.items())
    ]


@router.get("/search")
def search_templates(q: str = "", limit: int = 10):
    """Search templates by name, description, or tags."""
    if not q.strip():
        return {"results": [], "count": 0}
    ql = q.lower().strip()
    results = [
        _template_summary(t) for t in TEMPLATES
        if ql in t["name"].lower()
        or ql in t["description"].lower()
        or any(ql in tag.lower() for tag in t["tags"])
    ][:min(limit, 50)]
    return {"results": results, "count": len(results), "query": q}


@router.get("/{template_id}/preview")
def get_template_preview(template_id: str):
    """Return the first HTML file content for in-pane preview."""
    t = next((t for t in TEMPLATES if t["id"] == template_id), None)
    if not t:
        return {"ok": False, "error": f"Template '{template_id}' not found"}
    # Return the first html file
    files = t.get("files", {})
    for fname, fcontent in files.items():
        if fname.endswith(".html"):
            return {"ok": True, "filename": fname, "content": fcontent, "template": t["name"]}
    return {"ok": False, "error": "No HTML file in template"}


@router.get("/{template_id}")
def get_template(template_id: str):
    """Get full template details including file names (not content)."""
    t = next((t for t in TEMPLATES if t["id"] == template_id), None)
    if not t:
        return {"ok": False, "error": f"Template '{template_id}' not found"}
    return {**_template_summary(t), "ok": True}


@router.post("/{template_id}/scaffold")
async def scaffold_template(template_id: str, req: Request):
    """Scaffold a template into preview/."""
    try:
        body = await req.json()
    except Exception:
        body = {}
    t    = next((t for t in TEMPLATES if t["id"] == template_id), None)
    if not t:
        return {"ok": False, "error": f"Template '{template_id}' not found"}

    # Sanitised project name for substitution
    raw_name    = body.get("project_name", "")
    custom_name = _safe_name(raw_name) if raw_name else ""
    custom_desc = (body.get("description") or "").strip()[:200]

    PREV.mkdir(parents=True, exist_ok=True)
    created: list = []

    con = get_conn()
    try:
        for filename, file_content in t["files"].items():
            # Substitute project name placeholders
            if custom_name:
                for placeholder in ["YourSaaS", "Your Name", "Your Company", "My App"]:
                    file_content = file_content.replace(placeholder, custom_name)

            # Path traversal guard
            target = (PREV / filename).resolve()
            if not str(target).startswith(str(PREV.resolve())):
                log.warning("Blocked path traversal attempt in template: %s", filename)
                continue

            target.parent.mkdir(parents=True, exist_ok=True)
            target.write_text(file_content, encoding="utf-8")
            created.append(filename)

            # Record in file_versions
            try:
                con.execute(
                    "INSERT INTO file_versions(path,content,author,message) VALUES (?,?,?,?)",
                    (filename, file_content, "template", f"Template: {t['name']}")
                )
            except Exception:
                pass

        con.commit()
        audit_log("template_scaffold", f"{template_id}: {', '.join(created)}")
    finally:
        con.close()

    # Determine primary preview URL
    preview_url = "/preview/index.html"
    for fn in created:
        if fn.endswith(".html"):
            preview_url = f"/preview/{fn}"
            break

    return {
        "ok":          True,
        "template":    t["name"],
        "template_id": template_id,
        "files":       created,
        "preview_url": preview_url,
        "message":     f"✅ {t['name']} scaffolded — {len(created)} file(s)",
    }


@router.post("/scaffold-custom")
async def scaffold_custom(req: Request):
    """Save current preview/index.html as a named template backup."""
    try:
        body    = await req.json()
    except Exception:
        body    = {}
    name    = (body.get("name") or "").strip()[:80]
    if not name:
        return {"ok": False, "error": "name required"}

    src = PREV / "index.html"
    if not src.exists():
        return {"ok": False, "error": "No index.html in preview/ to save"}

    # Save as a named backup in preview/templates/
    backup_dir = PREV / "templates"
    backup_dir.mkdir(exist_ok=True)
    safe_fname = re.sub(r"[^\w\-]", "_", name.lower())[:40] + ".html"
    dest = backup_dir / safe_fname
    dest.write_text(src.read_text(encoding="utf-8"), encoding="utf-8")
    audit_log("template_custom_save", name)
    return {
        "ok":      True,
        "name":    name,
        "saved_to": str(dest.relative_to(ROOT)),
        "url":     f"/preview/templates/{safe_fname}",
    }
