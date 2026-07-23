"""
Agentic OS — Builder Router
Preview file management, Git time-travel, scaffold, E2E, package manager,
deploy hooks, and LLM-powered code assistance.
"""

from __future__ import annotations

import contextlib

import ast
import base64
import io
import json
import os
import shutil
import socket
import subprocess
from pathlib import Path

from fastapi import APIRouter, Request
from fastapi.responses import PlainTextResponse, StreamingResponse

from ..services import llm, memory_db

router = APIRouter(tags=['builder'])

from backend.config import get_data_dir
ROOT = get_data_dir()
PREVIEW_DIR = ROOT / 'preview'
MOBILE_DIR = PREVIEW_DIR / 'mobile'
PREVIEW_DIR.mkdir(exist_ok=True)
MOBILE_DIR.mkdir(exist_ok=True)

DB = memory_db.get_conn


# ── Studio validation ─────────────────────────────────────────────────────────
@router.post('/api/studio/lint')
def studio_lint():
    """Run bounded local syntax checks for the Studio console."""
    errors: list[str] = []
    python_root = ROOT / 'backend'
    for source in python_root.rglob('*.py'):
        try:
            ast.parse(source.read_text(encoding='utf-8'), filename=str(source))
        except (OSError, SyntaxError) as exc:
            errors.append(f'{source.relative_to(ROOT)}: {exc}')

    node = shutil.which('node')
    if node:
        for source in (ROOT / 'frontend' / 'js').glob('*.js'):
            result = subprocess.run(
                [node, '--check', str(source)],
                capture_output=True,
                text=True,
                timeout=10,
                check=False,
            )
            if result.returncode:
                errors.append(f'{source.relative_to(ROOT)}: {result.stderr.strip()[:500]}')

    return {
        'ok': not errors,
        'message': 'Syntax validation passed.' if not errors else f'{len(errors)} syntax issue(s) found.',
        'errors': errors[:100],
    }


# ── Preview files ──────────────────────────────────────────────────────────────
@router.get('/api/preview/files')
def preview_files():
    """Execute or process preview files operation."""
    files = []
    for base, prefix in [(PREVIEW_DIR, ''), (MOBILE_DIR, 'mobile/')]:
        if base.exists():
            for p in base.rglob('*'):
                if p.is_file() and '.git' not in str(p):
                    rel = prefix + p.relative_to(base).as_posix() if prefix else p.relative_to(PREVIEW_DIR).as_posix()
                    if rel.startswith('mobile/mobile/'):
                        continue
                    files.append({'path': rel, 'size': p.stat().st_size, 'ext': p.suffix.lstrip('.') or 'txt'})
    seen = set()
    out = []
    for f in files:
        if f['path'] not in seen:
            seen.add(f['path'])
            out.append(f)
    return sorted(out, key=lambda x: (0 if x['path'].startswith('mobile/') else 1, x['path']))


@router.get('/api/preview/read')
def preview_read(path: str = 'index.html'):
    """Execute or process preview read operation."""
    f = (PREVIEW_DIR / path).resolve()
    if not str(f).startswith(str(PREVIEW_DIR.resolve())):
        return PlainTextResponse('forbidden', 403)
    if not f.exists():
        return PlainTextResponse('', 404)
    return PlainTextResponse(f.read_text(encoding='utf-8', errors='ignore'))


@router.post('/api/preview/save')
async def preview_save(req: Request):
    """Execute or process preview save operation."""
    d = await req.json()
    path = d.get('path', 'index.html').lstrip('/')
    content = d.get('content', '')
    f = (PREVIEW_DIR / path).resolve()
    if not str(f).startswith(str(PREVIEW_DIR.resolve())):
        return {'ok': False, 'error': 'path traversal'}
    f.parent.mkdir(parents=True, exist_ok=True)
    old = f.read_text(encoding='utf-8', errors='ignore') if f.exists() else ''
    f.write_text(content, encoding='utf-8')
    con = DB()
    if old != content:
        con.execute(
            'INSERT INTO file_versions(path,content,author,message) VALUES (?,?,?,?)',
            (
                path,
                old,
                d.get('author', 'builder'),
                d.get('message', 'save')[:240],
            ),  # FIX 2: store pre-save state (even if ""), not new content
        )
        con.execute("INSERT INTO audit(action,detail) VALUES ('preview_save',?)", (path,))
        con.commit()
    v = con.execute('SELECT COUNT(*) FROM file_versions WHERE path=?', (path,)).fetchone()[0]
    con.close()
    # Trigger HMR broadcast
    try:
        import asyncio

        from .system import _hmr_broadcast

        asyncio.create_task(_hmr_broadcast({'type': 'file_changed', 'path': path, 'ts': __import__('time').time()}))
    except (KeyError, TypeError, ValueError, json.JSONDecodeError, OSError, AttributeError, RuntimeError):
        pass
    return {'ok': True, 'versions': v}


@router.post('/api/preview/new')
async def preview_new(req: Request):
    """Execute or process preview new operation."""
    d = await req.json()
    path = d.get('path', 'untitled.html').lstrip('/')
    f = (PREVIEW_DIR / path).resolve()
    if not str(f).startswith(str(PREVIEW_DIR.resolve())):
        return {'ok': False, 'error': 'path traversal'}
    if f.exists():
        return {'ok': False, 'error': 'file already exists'}
    f.parent.mkdir(parents=True, exist_ok=True)
    f.write_text(d.get('content', ''), encoding='utf-8')
    memory_db.audit_log('preview_new', path)
    return {'ok': True, 'path': path}


@router.delete('/api/preview/delete')
async def preview_delete(req: Request):
    """Execute or process preview delete operation."""
    try:
        d = await req.json()
    except (KeyError, TypeError, ValueError, json.JSONDecodeError, OSError, AttributeError, RuntimeError):
        d = {}
    path = d.get('path', '').lstrip('/')
    f = (PREVIEW_DIR / path).resolve()
    if not str(f).startswith(str(PREVIEW_DIR.resolve())):
        return {'ok': False, 'error': 'path traversal'}
    if not f.exists():
        return {'ok': False, 'error': 'not found'}
    f.unlink()
    memory_db.audit_log('preview_delete', path)
    return {'ok': True}


@router.get('/api/preview/history')
def preview_history(path: str = 'index.html'):
    """Execute or process preview history operation."""
    con = DB()
    rows = con.execute(
        """SELECT id, author, message, datetime(created_at,'localtime') as ts, length(content) as bytes
           FROM file_versions WHERE path=? ORDER BY id DESC LIMIT 150""",
        (path,),
    ).fetchall()
    con.close()
    return [dict(r) for r in rows]


@router.get('/api/preview/version')
def preview_version(id: int):
    """Execute or process preview version operation."""
    con = DB()
    r = con.execute('SELECT * FROM file_versions WHERE id=?', (id,)).fetchone()
    con.close()
    return dict(r) if r else {'ok': False}


@router.post('/api/preview/restore')
async def preview_restore(req: Request):
    """Execute or process preview restore operation."""
    d = await req.json()
    con = DB()
    row = con.execute('SELECT path,content FROM file_versions WHERE id=?', (d.get('version_id'),)).fetchone()
    con.close()
    if not row:
        return {'ok': False}
    # FIX 3: re-validate path from DB to prevent traversal (defence in depth)
    p = (PREVIEW_DIR / row['path']).resolve()
    if not str(p).startswith(str(PREVIEW_DIR.resolve())):
        return {'ok': False, 'error': 'path traversal denied'}
    p.parent.mkdir(parents=True, exist_ok=True)
    p.write_text(row['content'], encoding='utf-8')
    con = DB()
    con.execute(
        'INSERT INTO file_versions(path,content,author,message) VALUES (?,?,?,?)',
        (row['path'], row['content'], 'builder', f'restore v{d.get("version_id")}'),
    )
    con.commit()
    con.close()
    return {'ok': True}


@router.post('/api/preview/commit')
async def preview_commit(req: Request):
    """Execute or process preview commit operation."""
    d = await req.json()
    path = d.get('path', 'index.html')
    f = (PREVIEW_DIR / path).resolve()
    # FIX 4: traversal guard on commit path
    if not str(f).startswith(str(PREVIEW_DIR.resolve())):
        return {'ok': False, 'error': 'path traversal denied'}
    if not f.exists():
        f = (MOBILE_DIR / path.replace('mobile/', '')).resolve()
        # FIX B: validate MOBILE fallback path too
        if not str(f).startswith(str(MOBILE_DIR.resolve())):
            return {'ok': False, 'error': 'path traversal denied'}
    if not f.exists():
        return {'ok': False}
    content = f.read_text(encoding='utf-8', errors='ignore')
    con = DB()
    con.execute(
        'INSERT INTO file_versions(path,content,author,message) VALUES (?,?,?,?)',
        (path, content, d.get('author', 'builder'), d.get('message', 'checkpoint')),
    )
    vid = con.execute('SELECT last_insert_rowid()').fetchone()[0]
    con.commit()
    con.close()
    return {'ok': True, 'version_id': vid}


# ── AI-powered code assistance ─────────────────────────────────────────────────
@router.post('/api/agent/edit')
async def agent_edit(req: Request):
    """Streaming inline code edit (⌘K). Diff-friendly output."""
    d = await req.json()
    instruction = (d.get('instruction') or '').strip()
    code = d.get('code') or ''
    language = d.get('language') or 'javascript'
    filepath = d.get('filepath') or ''

    if not instruction:
        return {'ok': False, 'error': 'instruction required'}

    messages = [
        {
            'role': 'system',
            'content': f'You are an expert {language} developer. '
            f'The user wants to edit the code in `{filepath}`. '
            f'Return ONLY the complete edited code, no explanation, no markdown fences unless the language uses them. '
            f'Instruction: {instruction}',
        },
        {'role': 'user', 'content': f'```{language}\n{code[:8000]}\n```'},
    ]

    async def generate():
        """Execute or process generate operation."""
        async for chunk in llm.stream(messages, agent_id='builder', max_tokens=4096, inject_steering=False):  # FIX M
            yield chunk

    return StreamingResponse(generate(), media_type='text/event-stream', headers={'Cache-Control': 'no-cache'})


@router.post('/api/agent/fix')
async def agent_fix(req: Request):
    """Auto-fix an error in a file."""
    d = await req.json()
    error = (d.get('error') or '').strip()
    code = d.get('code') or ''
    language = d.get('language') or 'javascript'

    messages = [
        {
            'role': 'system',
            'content': f'You are debugging a {language} file. Fix the error and return ONLY the corrected code.',
        },
        {'role': 'user', 'content': f'Error: {error}\n\nCode:\n```{language}\n{code[:6000]}\n```'},
    ]
    result = await llm.complete(messages, agent_id='builder', max_tokens=4096, inject_steering=False)  # FIX K
    return {'ok': result.get('ok'), 'fixed_code': result.get('text', ''), 'model': result.get('model')}


@router.post('/api/complete')
async def complete_code(req: Request):
    """Ghost-text autocomplete. Fast, low-token."""
    try:
        d = await req.json()
    except (KeyError, TypeError, ValueError, json.JSONDecodeError, OSError, AttributeError, RuntimeError):
        d = {}
    prefix = d.get('prefix', '')[-1800:]
    suffix = d.get('suffix', '')[:400]
    filepath = d.get('filepath', 'index.html')
    language = d.get('language', '')

    if not language:
        ext = filepath.rsplit('.', 1)[-1] if '.' in filepath else 'html'
        language = {
            'tsx': 'typescript',
            'jsx': 'javascript',
            'ts': 'typescript',
            'py': 'python',
            'css': 'css',
            'md': 'markdown',
        }.get(ext, ext)

    messages = [
        {
            'role': 'system',
            'content': f'Complete the {language} code. Return ONLY the completion text, no explanation.',
        },
        {
            'role': 'user',
            'content': f'FILE: {filepath}\n<PREFIX>{prefix}</PREFIX>\n<SUFFIX>{suffix}</SUFFIX>\nCOMPLETION:',
        },
    ]
    result = await llm.complete(
        messages, agent_id='free', max_tokens=200, temperature=0.3, timeout=8.0, inject_steering=False
    )  # FIX L
    text = result.get('text', '').strip()
    return {
        'completions': [{'text': text, 'insertText': text}] if text else [],
        'model': result.get('model', ''),
    }


# ── Scaffold ───────────────────────────────────────────────────────────────────
@router.post('/api/preview/scaffold')
async def preview_scaffold(req: Request):
    """Execute or process preview scaffold operation."""
    d = await req.json()
    prompt_raw = d.get('prompt', 'app')
    prompt = prompt_raw.lower()
    framework = d.get('framework', 'auto')

    if framework == 'auto':
        if any(k in prompt for k in ['next', 'nextjs', 'next.js', 'vercel', 'react server']):
            framework = 'nextjs'
        elif any(k in prompt for k in ['svelte', 'sveltekit', 'kit']):
            framework = 'sveltekit'
        elif any(k in prompt for k in ['expo', 'react native', 'rn', 'ios', 'android', 'mobile']):
            framework = 'expo'
        else:
            framework = 'web'

    created_files = []
    con = DB()

    def write_rel(rel_path: str, content: str):
        """Execute or process write rel operation."""
        f = PREVIEW_DIR / rel_path
        f.parent.mkdir(parents=True, exist_ok=True)
        f.write_text(content, encoding='utf-8')
        created_files.append(rel_path)
        try:
            con.execute(
                'INSERT INTO file_versions(path,content,author,message) VALUES (?,?,?,?)',
                (rel_path, content, 'scaffolder', f'{framework} scaffold: {prompt_raw[:80]}'),
            )
        except (KeyError, TypeError, ValueError, json.JSONDecodeError, OSError, AttributeError, RuntimeError):
            pass

    title = prompt_raw.title() or 'My App'

    if framework == 'web':
        write_rel(
            'index.html',
            f"""<!DOCTYPE html>
<html lang="en">
<head>
<meta charset="UTF-8"><meta name="viewport" content="width=device-width,initial-scale=1">
<title>{title}</title>
<script src="https://cdn.tailwindcss.com"></script>
<link rel="stylesheet" href="styles.css">
</head>
<body class="bg-gray-950 text-gray-100 min-h-screen">
<header class="border-b border-gray-800 px-6 py-4 flex items-center gap-3">
  <span class="text-2xl">✨</span>
  <span class="font-bold text-lg">{title}</span>
  <span class="ml-auto text-xs text-gray-500">Built with Agentic OS</span>
</header>
<main class="max-w-4xl mx-auto px-6 py-16">
  <h1 class="text-5xl font-black mb-4">{title}</h1>
  <p class="text-gray-400 text-xl mb-8">Built with Agentic OS — Monaco · Git · E2E · Memory Galaxy · Swarm</p>
  <div class="flex gap-3 mb-12">
    <button id="cta-primary" class="bg-blue-500 hover:bg-blue-400 text-white font-bold px-6 py-3 rounded-xl transition">Get Started</button>
    <button class="border border-gray-700 text-gray-300 px-6 py-3 rounded-xl hover:bg-gray-800 transition">View Demo</button>
  </div>
  <div class="grid grid-cols-3 gap-4 mb-12" id="stats">
    <div class="bg-gray-900 border border-gray-800 rounded-xl p-4">
      <div class="text-gray-400 text-xs mb-1">MRR</div>
      <div class="text-2xl font-bold">$12,480</div>
      <div class="text-green-400 text-xs">+18%</div>
    </div>
    <div class="bg-gray-900 border border-gray-800 rounded-xl p-4">
      <div class="text-gray-400 text-xs mb-1">Users</div>
      <div class="text-2xl font-bold">1,842</div>
      <div class="text-blue-400 text-xs">live</div>
    </div>
    <div class="bg-gray-900 border border-gray-800 rounded-xl p-4">
      <div class="text-gray-400 text-xs mb-1">E2E Tests</div>
      <div class="text-2xl font-bold text-green-400">✓ Green</div>
    </div>
  </div>
  <div class="grid grid-cols-3 gap-4" id="features">
    {
                ''.join(
                    f'<div class="bg-gray-900 border border-gray-800 rounded-xl p-5"><div class="text-2xl mb-2">{e}</div><div class="font-semibold mb-1">{t}</div><div class="text-gray-400 text-sm">{d}</div></div>'
                    for e, t, d in [
                        ('🚀', 'Live Builder', 'Monaco · Git · Diff · HMR'),
                        ('📱', 'Expo Go', 'React Native mobile live'),
                        ('🧪', 'Playwright E2E', 'Auto-fix loop · Trace Viewer'),
                        ('🌌', 'Memory Galaxy', 'Qdrant 384d · <40ms RAG'),
                        ('🌀', 'Swarm', '4-6 agents fan-out · judge · merge'),
                        ('⚡', 'Deploy', 'Vercel 1-click · 18s'),
                    ]
                )
            }
  </div>
</main>
<script src="app.js" type="module"></script>
</body>
</html>""",
        )
        write_rel('styles.css', 'body{font-family:Inter,system-ui,sans-serif}\n')
        write_rel(
            'app.js',
            f"""// {title} — Agentic OS
document.getElementById('cta-primary')?.addEventListener('click', () => {{
  alert('🚀 {title} — built with Agentic OS!');
}});
console.log('[Agentic OS] {title} loaded');
""",
        )
        preview_url = '/preview/index.html'

    elif framework == 'nextjs':
        write_rel(
            'package.json',
            json.dumps(
                {
                    'name': 'agentic-next-app',
                    'version': '0.1.0',
                    'private': True,
                    'scripts': {'dev': 'next dev', 'build': 'next build', 'start': 'next start'},
                    'dependencies': {
                        'next': '15.0.0',
                        'react': '^18',
                        'react-dom': '^18',
                        'tailwindcss': '^3.4.1',
                        'clsx': '^2.1.0',
                        'lucide-react': '^0.400.0',
                    },
                    'devDependencies': {
                        'typescript': '^5',
                        '@types/react': '^18',
                        '@types/node': '^20',
                        'postcss': '^8',
                        'autoprefixer': '^10',
                    },
                },
                indent=2,
            ),
        )
        write_rel(
            'app/page.tsx',
            f"""export default function Home() {{
  return (
    <main className="min-h-screen bg-gray-950 text-gray-100 p-8">
      <h1 className="text-4xl font-black mb-4">{title}</h1>
      <p className="text-gray-400">Built with Agentic OS + Next.js 15</p>
    </main>
  )
}}
""",
        )
        write_rel(
            'app/layout.tsx',
            """import type { Metadata } from 'next'
export const metadata: Metadata = { title: 'Agentic OS App' }
export default function RootLayout({ children }: { children: React.ReactNode }) {
  return <html lang="en"><body>{children}</body></html>
}
""",
        )
        write_rel(
            'tailwind.config.ts',
            """import type { Config } from 'tailwindcss'
const config: Config = { content: ['./app/**/*.{ts,tsx}'], theme: { extend: {} }, plugins: [] }
export default config
""",
        )
        preview_url = '/preview/index.html'

    elif framework == 'expo':
        write_rel(
            'mobile/App.jsx',
            f"""import React, {{ useState }} from 'react';
import {{ View, Text, Pressable, StyleSheet, ScrollView }} from 'react-native';

export default function App() {{
  const [taps, setTaps] = useState(0);
  return (
    <ScrollView style={{{{backgroundColor:'#0b0d12'}}}}>
      <View style={{{{padding:24, paddingTop:60}}}}>
        <Text style={{{{color:'#fff',fontSize:28,fontWeight:'800',marginBottom:4}}}}>🧠 {title}</Text>
        <Text style={{{{color:'#9aa7c7',marginBottom:24}}}}>Expo · React Native · Agentic OS</Text>
        <Pressable onPress={{()=>setTaps(t=>t+1)}} style={{{{backgroundColor:'#7aa2f7',padding:16,borderRadius:14,alignItems:'center'}}}}>
          <Text style={{{{color:'#081028',fontWeight:'800',fontSize:16}}}}>Tap — {{taps}} — Hermes ✓</Text>
        </Pressable>
        <Text style={{{{color:'#5a647e',fontSize:11,textAlign:'center',marginTop:24}}}}>Monaco · Git · E2E · Memory Galaxy · Swarm · Deploy</Text>
      </View>
    </ScrollView>
  );
}}
""",
        )
        write_rel(
            'mobile/package.json',
            json.dumps(
                {
                    'name': 'agentic-expo-app',
                    'version': '1.0.0',
                    'main': 'expo-router/entry',
                    'dependencies': {
                        'expo': '~52.0.0',
                        'expo-router': '^4.0.0',
                        'react': '18.3.1',
                        'react-native': '0.76.5',
                    },
                },
                indent=2,
            ),
        )
        preview_url = '/preview/mobile/index.html'

    else:  # sveltekit
        write_rel(
            'package.json',
            json.dumps(
                {
                    'name': 'agentic-sveltekit',
                    'version': '0.0.1',
                    'type': 'module',
                    'scripts': {'dev': 'vite dev', 'build': 'vite build', 'preview': 'vite preview'},
                    'devDependencies': {
                        '@sveltejs/adapter-auto': '^3.0.0',
                        '@sveltejs/kit': '^2.0.0',
                        'svelte': '^4.2.7',
                        'vite': '^5.0.3',
                        'tailwindcss': '^3.4.1',
                    },
                },
                indent=2,
            ),
        )
        write_rel(
            'src/routes/+page.svelte',
            f"""<script lang="ts">
  let count = 0;
</script>
<main class="min-h-screen bg-gray-950 text-gray-100 p-8">
  <h1 class="text-4xl font-black mb-4">{title}</h1>
  <p class="text-gray-400 mb-6">SvelteKit · Agentic OS</p>
  <button on:click={{()=>count++}} class="bg-blue-500 text-white px-6 py-3 rounded-xl font-bold">
    Tapped {{count}}× — HMR ✓
  </button>
</main>
""",
        )
        preview_url = '/preview/index.html'

    con.commit()
    con.close()
    return {
        'ok': True,
        'framework': framework,
        'files': created_files,
        'count': len(created_files),
        'preview_url': preview_url,
        'message': f'{framework} scaffold — {len(created_files)} files created',
    }


# ── QR / Tunnel ────────────────────────────────────────────────────────────────
def _get_lan_ip() -> str:
    s = None
    try:
        s = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
        s.connect(('8.8.8.8', 80))
        return s.getsockname()[0]
    except (KeyError, TypeError, ValueError, json.JSONDecodeError, OSError, AttributeError, RuntimeError):
        try:
            return socket.gethostbyname(socket.gethostname())
        except (KeyError, TypeError, ValueError, json.JSONDecodeError, OSError, AttributeError, RuntimeError):
            return '127.0.0.1'
    finally:
        if s:
            with contextlib.suppress(OSError):
                s.close()


def _qr_data_url(text: str, box_size: int = 8) -> str:
    try:
        import qrcode

        qr = qrcode.QRCode(error_correction=qrcode.constants.ERROR_CORRECT_M, box_size=box_size, border=2)
        qr.add_data(text)
        qr.make(fit=True)
        img = qr.make_image(fill_color='#e6e6f0', back_color='#0b0d12')
        buf = io.BytesIO()
        img.save(buf, format='PNG')
        return 'data:image/png;base64,' + base64.b64encode(buf.getvalue()).decode()
    except (KeyError, TypeError, ValueError, json.JSONDecodeError, OSError, AttributeError, RuntimeError):
        import urllib.parse

        return 'https://api.qrserver.com/v1/create-qr-code/?size=280x280&data=' + urllib.parse.quote(text)


@router.get('/api/tunnel/info')
def tunnel_info():
    """Execute or process tunnel info operation."""
    port = int(os.getenv('AGENTIC_OS_PORT', '8787'))
    ip = _get_lan_ip()
    base = f'http://{ip}:{port}'
    urls = {
        'local': f'http://localhost:{port}',
        'lan': base,
        'web_preview': f'{base}/preview/index.html',
        'expo_preview': f'{base}/preview/mobile/index.html',
        'mission_control': f'{base}/',
    }
    return {
        'lan_ip': ip,
        'port': port,
        'urls': urls,
        'qr_expo': _qr_data_url(urls['expo_preview']),
        'qr_web': _qr_data_url(urls['web_preview']),
        'instructions': [
            '1. Phone must be on the SAME Wi-Fi as this machine',
            '2. Open iPhone Camera → scan QR → tap notification',
            '3. Add to Home Screen for full-screen feel',
            '4. Edits in Monaco → Hot Reload → phone updates <1s',
        ],
        'firewall_note': 'Allow Python/uvicorn through firewall. Port 8787 TCP inbound.',
    }


# ── Package manager ────────────────────────────────────────────────────────────
@router.get('/api/pm/list')
def pm_list():
    """Read package.json from preview dir."""
    for path in [PREVIEW_DIR / 'package.json', PREVIEW_DIR / 'app' / 'package.json']:
        if path.exists():
            try:
                data = json.loads(path.read_text())
                deps = [{'name': k, 'wanted': v} for k, v in data.get('dependencies', {}).items()]
                dev_deps = [{'name': k, 'wanted': v} for k, v in data.get('devDependencies', {}).items()]
                return {
                    'ok': True,
                    'path': str(path),
                    'name': data.get('name', ''),
                    'version': data.get('version', ''),
                    'dependencies': deps,
                    'devDependencies': dev_deps,
                }
            except (KeyError, TypeError, ValueError, json.JSONDecodeError, OSError, AttributeError, RuntimeError):
                pass
    return {'ok': False, 'dependencies': [], 'devDependencies': [], 'path': 'package.json'}


@router.post('/api/pm/add')
async def pm_add(req: Request):
    """Execute or process pm add operation."""
    d = await req.json()
    name = (d.get('name') or '').strip()
    ver = (d.get('version') or 'latest').strip()
    dev = bool(d.get('dev', False))
    if not name:
        return {'ok': False, 'error': 'name required'}
    # update package.json
    for path in [PREVIEW_DIR / 'package.json', PREVIEW_DIR / 'app' / 'package.json']:
        if path.exists():
            try:
                data = json.loads(path.read_text())
                key = 'devDependencies' if dev else 'dependencies'
                data.setdefault(key, {})[name] = f'^{ver}' if ver != 'latest' else '*'
                path.write_text(json.dumps(data, indent=2))
                return {'ok': True, 'name': name, 'version': ver, 'dev': dev, 'package_json': str(path)}
            except Exception as e:
                return {'ok': False, 'error': str(e)}
    # create package.json
    pkg = {
        'name': 'agentic-app',
        'version': '0.1.0',
        'dependencies' if not dev else 'devDependencies': {name: f'^{ver}'},
    }
    (PREVIEW_DIR / 'package.json').write_text(json.dumps(pkg, indent=2))
    return {'ok': True, 'name': name, 'version': ver}


@router.post('/api/pm/remove')
async def pm_remove(req: Request):
    """Execute or process pm remove operation."""
    d = await req.json()
    name = (d.get('name') or '').strip()
    if not name:
        return {'ok': False, 'error': 'name required'}
    for path in [PREVIEW_DIR / 'package.json']:
        if path.exists():
            try:  # FIX J: handle malformed JSON
                data = json.loads(path.read_text())
                data.get('dependencies', {}).pop(name, None)
                data.get('devDependencies', {}).pop(name, None)
                path.write_text(json.dumps(data, indent=2))
            except Exception as e:
                return {'ok': False, 'error': str(e)}
    return {'ok': True, 'removed': name}


@router.get('/api/pm/search')
async def pm_search(q: str = '', size: int = 12):
    # curated list for offline use + live npm registry attempt
    """Execute or process pm search operation."""
    CURATED = [
        {
            'name': 'react',
            'version': '18.3.1',
            'description': 'A JavaScript library for building user interfaces',
            'score': 0.99,
        },
        {'name': 'next', 'version': '15.0.0', 'description': 'The React Framework for the Web', 'score': 0.98},
        {'name': 'tailwindcss', 'version': '3.4.1', 'description': 'Utility-first CSS framework', 'score': 0.97},
        {'name': 'framer-motion', 'version': '11.0.0', 'description': 'Animation library for React', 'score': 0.92},
        {'name': 'zod', 'version': '3.23.0', 'description': 'TypeScript-first schema validation', 'score': 0.91},
        {'name': 'prisma', 'version': '5.15.0', 'description': 'Next-generation ORM for Node.js', 'score': 0.90},
        {'name': 'stripe', 'version': '16.0.0', 'description': 'Stripe API library for Node.js', 'score': 0.88},
        {'name': '@supabase/supabase-js', 'version': '2.44.0', 'description': 'Supabase client library', 'score': 0.87},
        {'name': 'lucide-react', 'version': '0.400.0', 'description': 'Beautiful & consistent icon set', 'score': 0.85},
        {'name': 'axios', 'version': '1.7.0', 'description': 'Promise based HTTP client', 'score': 0.84},
        {
            'name': 'clsx',
            'version': '2.1.0',
            'description': 'Utility for constructing className strings',
            'score': 0.83,
        },
        {
            'name': 'date-fns',
            'version': '3.6.0',
            'description': 'Modern JavaScript date utility library',
            'score': 0.82,
        },
    ]
    if not q:
        return {'results': CURATED[:size]}
    filtered = [p for p in CURATED if q.lower() in p['name'].lower() or q.lower() in p['description'].lower()]
    return {
        'results': filtered[:size]
        or [{'name': q, 'version': 'latest', 'description': 'Package from npm registry', 'score': 0.5}]
    }


# ── Deploy ─────────────────────────────────────────────────────────────────────
# FIX 1: /api/deploy/vercel is handled by deploy.py (prefix=/api/deploy).
# Stub removed here to prevent route shadowing — deploy.py's real implementation wins.


# ── Health ─────────────────────────────────────────────────────────────────────
@router.get('/api/health')
def health():
    """Execute or process health operation."""
    return {'ok': True, 'version': '6.0', 'service': 'Agentic OS'}
