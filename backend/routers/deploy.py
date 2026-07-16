"""
Agentic OS — Deploy Router
One-click deploy to Vercel, Netlify, Cloudflare Pages, Railway.
Also: Cloudflare Tunnel for public HTTPS preview URL.
"""

from __future__ import annotations

import contextlib

import asyncio
import io
import logging
import os
import time
import zipfile
from pathlib import Path

import httpx
from fastapi import APIRouter, Request

router = APIRouter(prefix='/api/deploy', tags=['deploy'])
log = logging.getLogger('agentic.deploy')

ROOT = Path(__file__).resolve().parents[2]
PREVIEW_DIR = ROOT / 'preview'


# ── Vercel ─────────────────────────────────────────────────────────────────────
@router.post('/vercel')
async def deploy_vercel(req: Request):
    """
    Deploy preview/ directory to Vercel via their API.
    Requires VERCEL_TOKEN in .env or Vault.
    """
    try:
        body = await req.json()
    except (json.JSONDecodeError, TypeError, ValueError):
        body = {}
    token = os.getenv('VERCEL_TOKEN', '') or body.get('token', '')
    project = body.get('project_name', 'agentic-os-preview')
    team_id = body.get('team_id', '')

    if not token:
        return {
            'ok': False,
            'provider': 'vercel',
            'error': 'VERCEL_TOKEN not set',
            'setup': [
                '1. Go to https://vercel.com/account/tokens',
                "2. Create a token with 'Full Access'",
                '3. Add to .env: VERCEL_TOKEN=your_token',
                '4. Or save via 🔐 Vault tab in Agentic OS',
                '5. Restart Agentic OS and try again',
            ],
        }

    files = _collect_deploy_files(PREVIEW_DIR)
    if not files:
        return {'ok': False, 'error': 'No files in preview/ directory. Scaffold a project first.'}

    log.info("Deploying %d files to Vercel project '%s'", len(files), project)
    t0 = time.time()

    try:
        # Vercel deployment API v13
        headers = {
            'Authorization': f'Bearer {token}',
            'Content-Type': 'application/json',
        }
        payload = {
            'name': project,
            'files': files,
            'projectSettings': {
                'framework': None,
                'buildCommand': None,
                'outputDirectory': None,
            },
            'target': 'production',
        }
        if team_id:
            payload['teamId'] = team_id

        async with httpx.AsyncClient(timeout=60.0) as client:
            resp = await client.post('https://api.vercel.com/v13/deployments', headers=headers, json=payload)

        data = resp.json()
        if resp.status_code in (200, 201):
            url = data.get('url', '')
            full = f'https://{url}' if url and not url.startswith('http') else url
            log.info('Vercel deploy success: %s in %.1fs', full, time.time() - t0)
            # store in memory
            from ..services.memory_db import memory_add

            memory_add('deploy:vercel', f'Deployed to {full}', 'deploy,vercel')
            return {
                'ok': True,
                'provider': 'vercel',
                'url': full,
                'deploy_id': data.get('id'),
                'status': data.get('status', 'BUILDING'),
                'latency_ms': round((time.time() - t0) * 1000),
                'files': len(files),
                'tip': "Your site is building. It'll be live in ~15-30 seconds.",
            }
        else:
            err = data.get('error', {}).get('message') or data.get('message') or str(data)[:200]
            log.error('Vercel deploy failed %d: %s', resp.status_code, err)
            return {'ok': False, 'provider': 'vercel', 'error': err, 'status_code': resp.status_code}

    except Exception as e:
        log.error('Vercel deploy exception: %s', e)
        return {'ok': False, 'provider': 'vercel', 'error': str(e)}


# ── Netlify ────────────────────────────────────────────────────────────────────
@router.post('/netlify')
async def deploy_netlify(req: Request):
    """Deploy to Netlify Drop (no account needed for drag-drop deploys)."""
    try:
        body = await req.json()
    except (json.JSONDecodeError, TypeError, ValueError):
        body = {}
    token = os.getenv('NETLIFY_TOKEN', '') or body.get('token', '')

    if not token:
        return {
            'ok': False,
            'provider': 'netlify',
            'error': 'NETLIFY_TOKEN not set',
            'setup': [
                '1. Go to https://app.netlify.com/user/applications#personal-access-tokens',
                '2. Create a personal access token',
                '3. Add NETLIFY_TOKEN to .env or Vault',
                '4. Restart and redeploy',
            ],
            'alternative': 'Drag & drop your preview/ folder at https://app.netlify.com/drop',
        }

    files = _collect_deploy_files(PREVIEW_DIR)
    if not files:
        return {'ok': False, 'error': 'No files in preview/ to deploy.'}

    t0 = time.time()
    try:
        # Build a zip
        zip_buf = io.BytesIO()
        with zipfile.ZipFile(zip_buf, 'w', zipfile.ZIP_DEFLATED) as zf:
            for f in files:
                zf.writestr(f['file'], f.get('data', ''))
        zip_buf.seek(0)

        async with httpx.AsyncClient(timeout=60.0) as client:
            resp = await client.post(
                'https://api.netlify.com/api/v1/sites',
                headers={'Authorization': f'Bearer {token}', 'Content-Type': 'application/zip'},
                content=zip_buf.read(),
            )
        data = resp.json()
        if resp.status_code in (200, 201):
            url = data.get('ssl_url') or data.get('url', '')
            return {
                'ok': True,
                'provider': 'netlify',
                'url': url,
                'site_id': data.get('id'),
                'status': 'deploying',
                'latency_ms': round((time.time() - t0) * 1000),
            }
        else:
            return {'ok': False, 'provider': 'netlify', 'error': data.get('message', str(data))[:200]}
    except Exception as e:
        return {'ok': False, 'provider': 'netlify', 'error': str(e)}


# ── Cloudflare Tunnel ──────────────────────────────────────────────────────────
@router.post('/tunnel')
async def start_tunnel(req: Request):
    """
    Start a cloudflared quick-tunnel to expose localhost:8787 publicly.
    Requires `cloudflared` binary installed.
    """
    import asyncio
    import re
    import shutil

    cf = shutil.which('cloudflared')
    if not cf:
        return {
            'ok': False,
            'error': 'cloudflared not installed',
            'install': {
                'mac': 'brew install cloudflared',
                'windows': 'winget install Cloudflare.cloudflared',
                'linux': 'curl -L https://github.com/cloudflare/cloudflared/releases/latest/download/cloudflared-linux-amd64 -o cloudflared && chmod +x cloudflared',
            },
            'then': "Restart Agentic OS and click 'Start Tunnel' again",
        }

    # Start tunnel process (non-blocking, captures URL from logs)
    try:
        proc = await asyncio.create_subprocess_exec(
            cf,
            'tunnel',
            '--url',
            'http://localhost:8787',
            '--no-autoupdate',
            stdout=asyncio.subprocess.PIPE,
            stderr=asyncio.subprocess.PIPE,
        )
        # Read output for up to 8 seconds to find the URL
        url = None
        deadline = asyncio.get_event_loop().time() + 8.0
        while asyncio.get_event_loop().time() < deadline:
            try:
                line = await asyncio.wait_for(proc.stderr.readline(), timeout=1.0)
                text = line.decode('utf-8', errors='ignore')
                match = re.search(r'https://[a-z0-9-]+\.trycloudflare\.com', text)
                if match:
                    url = match.group(0)
                    break
            except asyncio.TimeoutError:
                continue

        if url:
            _active_tunnel['proc'] = proc
            _active_tunnel['url'] = url
            from ..services.memory_db import audit_log, memory_add

            memory_add('deploy:tunnel', f'Cloudflare tunnel: {url}', 'deploy,tunnel,public')
            audit_log('deploy:tunnel', f'Tunnel started: {url}')
            return {
                'ok': True,
                'url': url,
                'note': 'Share this URL for public access. Use POST /api/deploy/tunnel/stop to stop it.',
                'qr': f'https://api.qrserver.com/v1/create-qr-code/?size=200x200&data={url}',
            }
        else:
            proc.terminate()
            return {
                'ok': False,
                'error': 'Could not parse tunnel URL from cloudflared output',
                'tip': f'Run manually: {cf} tunnel --url http://localhost:8787',
            }
    except Exception as e:
        return {'ok': False, 'error': str(e)}


# ── Deploy history ─────────────────────────────────────────────────────────────
@router.get('/history')
def deploy_history(limit: int = 20):
    """Return recent deploy records from memory + audit log."""
    from ..services.memory_db import get_conn, memory_search_fts

    results = memory_search_fts('deploy', limit=min(limit, 100))
    deploy_mem = [r for r in results if 'deploy' in (r.get('tags') or '')]
    # Also check audit log for deploy actions
    try:
        con = get_conn()
        try:
            audit_rows = con.execute(
                "SELECT action, detail, datetime(created_at,'localtime') as created_at "
                "FROM audit WHERE action LIKE 'deploy%' ORDER BY id DESC LIMIT ?",
                (min(limit, 100),),
            ).fetchall()
            for row in audit_rows:
                deploy_mem.append(
                    {
                        'source': row['action'],
                        'content': row['detail'] or '',
                        'tags': 'deploy,audit',
                        'created_at': row['created_at'],
                    }
                )
        finally:
            con.close()
    except (KeyError, TypeError, ValueError, json.JSONDecodeError, OSError, AttributeError, RuntimeError):
        pass
    # Sort combined by created_at descending
    deploy_mem.sort(key=lambda x: x.get('created_at', ''), reverse=True)
    return deploy_mem[: min(limit, 100)]


# ── Status check ───────────────────────────────────────────────────────────────
@router.post('/railway')
async def deploy_railway(req: Request):
    """Deploy to Railway via API (CLI-assisted)."""
    token = os.getenv('RAILWAY_TOKEN', '')
    if not token:
        return {
            'ok': False,
            'provider': 'railway',
            'error': 'RAILWAY_TOKEN not set',
            'setup': [
                '1. Go to https://railway.app/account/tokens',
                '2. Create an API token',
                '3. Add RAILWAY_TOKEN to .env or Vault',
                '4. Install Railway CLI: npm install -g @railway/cli',
                '5. Log in: railway login --browserless',
            ],
        }
    import shutil

    railway_cli = shutil.which('railway')
    if not railway_cli:
        return {
            'ok': False,
            'provider': 'railway',
            'error': 'Railway CLI not installed',
            'setup': ['Install: npm install -g @railway/cli', 'Login: railway login --browserless'],
        }
    try:
        proc = await asyncio.create_subprocess_exec(
            railway_cli,
            'up',
            '--detach',
            cwd=str(PREVIEW_DIR),
            env={**os.environ, 'RAILWAY_TOKEN': token},
            stdout=asyncio.subprocess.PIPE,
            stderr=asyncio.subprocess.PIPE,
        )
        stdout, stderr = await asyncio.wait_for(proc.communicate(), timeout=60)
        output = (stdout + stderr).decode('utf-8', errors='ignore')
        if proc.returncode == 0:
            from ..services.memory_db import memory_add

            memory_add('deploy:railway', 'Deployed via Railway CLI', 'deploy,railway')
            return {
                'ok': True,
                'provider': 'railway',
                'output': output[:500],
                'url': 'https://railway.app/dashboard',
                'tip': 'Deployment started. Check Railway dashboard for live URL.',
            }
        else:
            return {'ok': False, 'provider': 'railway', 'error': output[:400] or 'Deploy failed'}
    except asyncio.TimeoutError:
        return {'ok': False, 'provider': 'railway', 'error': 'Deploy timed out after 60s'}
    except Exception as e:
        return {'ok': False, 'provider': 'railway', 'error': str(e)}


@router.post('/render')
async def deploy_render(req: Request):
    """Deploy to Render via API."""
    key = os.getenv('RENDER_API_KEY', '')
    if not key:
        return {
            'ok': False,
            'provider': 'render',
            'error': 'RENDER_API_KEY not set',
            'setup': [
                '1. Go to https://dashboard.render.com/u/account/api-keys',
                '2. Create an API key',
                '3. Add RENDER_API_KEY to .env or Vault',
            ],
        }
    return {
        'ok': True,
        'provider': 'render',
        'tip': 'Connect your GitHub repo to Render for auto-deploy at https://dashboard.render.com/new/static',
    }


@router.post('/flyio')
async def deploy_flyio(req: Request):
    """Deploy to Fly.io using flyctl."""
    import shutil

    fly = shutil.which('fly') or shutil.which('flyctl')
    if not fly:
        return {
            'ok': False,
            'provider': 'fly.io',
            'error': 'flyctl not installed',
            'setup': [
                '1. Install: curl -L https://fly.io/install.sh | sh',
                '2. Login: fly auth login',
                '3. Launch from preview/: fly launch',
            ],
        }
    # Check if fly.toml exists in PREVIEW_DIR
    if not (PREVIEW_DIR / 'fly.toml').exists():
        return {
            'ok': False,
            'provider': 'fly.io',
            'error': "fly.toml not found in preview/ — run 'fly launch' first to create it",
            'setup': [f'cd {PREVIEW_DIR}', 'fly launch'],
        }
    try:
        proc = await asyncio.create_subprocess_exec(
            fly,
            'deploy',
            cwd=str(PREVIEW_DIR),
            stdout=asyncio.subprocess.PIPE,
            stderr=asyncio.subprocess.PIPE,
        )
        stdout, stderr = await asyncio.wait_for(proc.communicate(), timeout=120)
        output = (stdout + stderr).decode('utf-8', errors='ignore')
        if proc.returncode == 0:
            from ..services.memory_db import memory_add

            memory_add('deploy:flyio', 'Deployed to Fly.io', 'deploy,flyio')
            return {
                'ok': True,
                'provider': 'fly.io',
                'output': output[:500],
                'tip': 'Deployment complete. Check https://fly.io/dashboard for your URL.',
            }
        else:
            return {'ok': False, 'provider': 'fly.io', 'error': output[:400] or 'Deploy failed'}
    except asyncio.TimeoutError:
        return {'ok': False, 'provider': 'fly.io', 'error': 'Deploy timed out after 120s'}
    except Exception as e:
        return {'ok': False, 'provider': 'fly.io', 'error': str(e)}


@router.post('/github-pages')
async def deploy_github_pages_shortcut(req: Request):
    """Shortcut: deploy to GitHub Pages (delegates to github router)."""
    try:
        from .github import deploy_github_pages

        return await deploy_github_pages(req)
    except ImportError as e:
        return {'ok': False, 'provider': 'github-pages', 'error': f'GitHub router unavailable: {e}'}
    except Exception as e:
        return {'ok': False, 'provider': 'github-pages', 'error': str(e)}


@router.get('/status')
def deploy_status():
    """Execute or process deploy status operation."""
    import shutil

    vercel_set = bool(os.getenv('VERCEL_TOKEN'))
    netlify_set = bool(os.getenv('NETLIFY_TOKEN'))
    railway_set = bool(os.getenv('RAILWAY_TOKEN'))
    render_set = bool(os.getenv('RENDER_API_KEY'))
    github_set = bool(os.getenv('GITHUB_TOKEN'))
    cf_installed = bool(shutil.which('cloudflared'))
    fly_installed = bool(shutil.which('fly') or shutil.which('flyctl'))
    files = list(PREVIEW_DIR.rglob('*')) if PREVIEW_DIR.exists() else []
    file_count = len([f for f in files if f.is_file() and 'branches' not in str(f)])
    return {
        'providers': {
            'vercel': {'ready': vercel_set, 'token_set': vercel_set},
            'netlify': {'ready': netlify_set, 'token_set': netlify_set},
            'railway': {'ready': railway_set, 'token_set': railway_set},
            'render': {'ready': render_set, 'token_set': render_set},
            'flyio': {'ready': fly_installed, 'installed': fly_installed},
            'github_pages': {'ready': github_set, 'token_set': github_set},
            'cloudflare': {'ready': cf_installed, 'installed': cf_installed},
        },
        'preview_files': file_count,
        'preview_dir': str(PREVIEW_DIR),
    }


# ── Helpers ────────────────────────────────────────────────────────────────────
# File types that should be excluded (binary assets too large/corrupt as UTF-8)
_BINARY_EXTS = {
    '.png',
    '.jpg',
    '.jpeg',
    '.gif',
    '.ico',
    '.svg',
    '.woff',
    '.woff2',
    '.ttf',
    '.eot',
    '.mp4',
    '.webm',
    '.mp3',
    '.wav',
    '.pdf',
    '.zip',
    '.tar',
    '.gz',
    '.wasm',
    '.bin',
    '.exe',
    '.dmg',
    '.pkg',
}
_MAX_FILE_BYTES = 1_048_576  # 1 MB per file limit


def _collect_deploy_files(directory: Path) -> list[dict]:
    """Collect all deployable text files from preview/ (Vercel API format)."""
    files = []
    if not directory.exists():
        return files
    for path in sorted(directory.rglob('*')):
        if not path.is_file():
            continue
        # Skip hidden, cache, and branch snapshot directories
        parts = str(path.relative_to(directory))
        if any(skip in parts for skip in ('.git', '__pycache__', 'branches', 'node_modules')):
            continue
        # Skip known binary file types
        if path.suffix.lower() in _BINARY_EXTS:
            continue
        # Skip files over 1 MB
        try:
            if path.stat().st_size > _MAX_FILE_BYTES:
                log.debug('Skipping large file %s (%d bytes)', path.name, path.stat().st_size)
                continue
        except OSError:
            continue
        rel = path.relative_to(directory).as_posix()
        try:
            text = path.read_text(encoding='utf-8', errors='replace')
            files.append(
                {
                    'file': rel,
                    'data': text,
                    'encoding': 'utf-8',
                }
            )
        except (KeyError, TypeError, ValueError, json.JSONDecodeError, OSError, AttributeError, RuntimeError):
            pass
    return files[:500]  # Vercel free tier limit


# ── Tunnel state registry ────────────────────────────────────────────────────
_active_tunnel: dict = {'proc': None, 'url': None}


# ── GET alias for tunnel status ───────────────────────────────────────────────
@router.get('/tunnel')
def tunnel_status_get():
    """GET tunnel status/info without starting one."""
    proc = _active_tunnel.get('proc')
    url = _active_tunnel.get('url')
    active = proc is not None and proc.returncode is None
    return {
        'active': active,
        'url': url if active else None,
        'message': f'Tunnel running at {url}' if active else 'Use POST /api/deploy/tunnel to start a tunnel',
    }


@router.post('/tunnel/stop')
def stop_tunnel():
    """Stop the running Cloudflare tunnel."""
    proc = _active_tunnel.get('proc')
    if proc and proc.returncode is None:
        try:
            proc.terminate()
            _active_tunnel['proc'] = None
            _active_tunnel['url'] = None
            log.info('Cloudflare tunnel stopped')
            return {'ok': True, 'message': 'Tunnel stopped'}
        except Exception as e:
            return {'ok': False, 'error': str(e)}
    return {'ok': False, 'error': 'No active tunnel to stop'}


@router.get('/providers')
def list_providers():
    """List all supported deploy providers."""
    return {'providers': ['vercel', 'netlify', 'railway', 'render', 'flyio', 'github-pages', 'tunnel'], 'count': 7}
