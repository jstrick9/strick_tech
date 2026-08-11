"""
Agentic OS — Deploy Router
One-click deploy to Vercel, Netlify, Cloudflare Pages, Railway.
Also: Cloudflare Tunnel for public HTTPS preview URL.
"""

from __future__ import annotations

import asyncio
import base64
import io
import json
import logging
import os
import time
import zipfile
from pathlib import Path

import httpx
from fastapi import APIRouter, Request

router = APIRouter(prefix='/api/deploy', tags=['deploy'])
log = logging.getLogger('agentic.deploy')

from backend.config import get_data_dir

from ..services.request_body import json_body_or_error

ROOT = get_data_dir()
PREVIEW_DIR = ROOT / 'preview'


# ── Vercel ─────────────────────────────────────────────────────────────────────
@router.post('/vercel')
async def deploy_vercel(req: Request):
    """
    Deploy preview/ directory to Vercel via their API.
    Requires VERCEL_TOKEN in .env or Vault.
    """
    body, _body_err = await json_body_or_error(req)
    if _body_err:
        return _body_err
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
                '3. Save it via 🔐 Vault tab in Agentic OS (takes effect immediately)',
                '4. Or add to .env: VERCEL_TOKEN=your_token (requires an app restart)',
                '5. Try again',
            ],
        }

    files, excluded = collect_deploy_files(PREVIEW_DIR)
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
            from ..services.memory_db import audit_log, memory_add

            memory_add('deploy:vercel', f'Deployed to {full}', 'deploy,vercel')
            audit_log('deploy:vercel', f'Deployed to {full}')
            return {
                'ok': True,
                'provider': 'vercel',
                'url': full,
                'deploy_id': data.get('id'),
                'status': data.get('status', 'BUILDING'),
                'latency_ms': round((time.time() - t0) * 1000),
                'files': len(files),
                'excluded': excluded,
                'excluded_count': len(excluded),
                'warning': _deploy_warning(excluded),
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
    body, _body_err = await json_body_or_error(req)
    if _body_err:
        return _body_err
    token = os.getenv('NETLIFY_TOKEN', '') or body.get('token', '')

    if not token:
        return {
            'ok': False,
            'provider': 'netlify',
            'error': 'NETLIFY_TOKEN not set',
            'setup': [
                '1. Go to https://app.netlify.com/user/applications#personal-access-tokens',
                '2. Create a personal access token',
                '3. Save it via 🔐 Vault (takes effect immediately) or add NETLIFY_TOKEN to .env (requires restart)',
                '4. Redeploy',
            ],
            'alternative': 'Drag & drop your preview/ folder at https://app.netlify.com/drop',
        }

    files, excluded = collect_deploy_files(PREVIEW_DIR)
    if not files:
        return {'ok': False, 'error': 'No files in preview/ to deploy.'}

    t0 = time.time()
    try:
        # Build a zip
        zip_buf = io.BytesIO()
        with zipfile.ZipFile(zip_buf, 'w', zipfile.ZIP_DEFLATED) as zf:
            for f in files:
                # Write the real bytes. This used to write f['data'] directly,
                # which for a base64 entry would put the base64 TEXT in the zip
                # -- a corrupt file at the other end.
                zf.writestr(f['file'], _file_bytes(f))
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
            # BUG FIX: netlify was the ONLY provider that never recorded its
            # deploy. vercel, railway, flyio and tunnel all memory_add; netlify
            # did not, so a successful Netlify deploy was missing from
            # /api/deploy/history and from memory search. The history pane
            # showed a gap where a real deploy had happened.
            from ..services.memory_db import audit_log, memory_add

            memory_add('deploy:netlify', f'Deployed to {url}', 'deploy,netlify')
            audit_log('deploy:netlify', f'Deployed to {url}')
            return {
                'ok': True,
                'provider': 'netlify',
                'url': url,
                'site_id': data.get('id'),
                'status': 'deploying',
                'files': len(files),
                'excluded': excluded,
                'excluded_count': len(excluded),
                'warning': _deploy_warning(excluded),
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

    # A second click of "Start Public Tunnel" (double-click, stale UI state
    # after a page reload, etc.) previously spawned a SECOND cloudflared
    # process and silently leaked the first one — _active_tunnel only ever
    # held one proc/url pair, so the original tunnel kept running
    # unreferenced (unstoppable via the UI's "Stop Tunnel" button, which
    # only knows about whatever is in _active_tunnel) while the new one
    # overwrote it. Return the already-active tunnel instead of starting a
    # duplicate.
    existing_proc = _active_tunnel.get('proc')
    if existing_proc is not None and existing_proc.returncode is None and _active_tunnel.get('url'):
        return {
            'ok': True,
            'url': _active_tunnel['url'],
            'note': 'Tunnel already running. Use POST /api/deploy/tunnel/stop to stop it.',
            'qr': f'https://api.qrserver.com/v1/create-qr-code/?size=200x200&data={_active_tunnel["url"]}',
            'already_active': True,
        }

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

    results = memory_search_fts('deploy', limit=max(1, min(limit, 100)))
    deploy_mem = [r for r in results if 'deploy' in (r.get('tags') or '')]
    # Also check audit log for deploy actions
    try:
        con = get_conn()
        try:
            audit_rows = con.execute(
                # `localtime` produced a local wall-clock value that the
                # response layer then stamped with a Z, publishing local time
                # labelled UTC. (Same defect as modules 17 and 18.)
                'SELECT action, detail, created_at '
                "FROM audit WHERE action LIKE 'deploy%' ORDER BY id DESC LIMIT ?",
                (max(1, min(limit, 100)),),
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
    return deploy_mem[: max(1, min(limit, 100))]


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
    """
    Render has no drag-and-drop / zip-upload deploy API like Netlify —
    their API only supports triggering a deploy on a service that's
    already connected to a GitHub repo via their dashboard. So unlike
    every other provider in this router, there is no actual deploy
    action this endpoint can perform; it can only confirm the API key is
    present and point the user at the one-time manual setup step.
    Previously this returned bare `{"ok": True, ...}` with no `no_action`
    flag, which the frontend's shared success-path rendering interpreted
    identically to a REAL deploy — showing "✅ Deployed!" even though
    literally nothing was deployed, and with no memory_add/audit_log
    entry either (unlike vercel/netlify/railway/flyio, which all record
    a real deploy event). Fixed to set `no_action: True` so the frontend
    can render an honest "no deploy happened yet" message instead.
    """
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
        'no_action': True,
        'tip': 'Render has no zip-upload API — connect your GitHub repo to Render for auto-deploy at https://dashboard.render.com/new/static',
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
    # BUG FIX: this counted every file on disk and the pane rendered it as
    # "N files ready in preview/". The deploy then shipped a DIFFERENT, smaller
    # set, because collect_deploy_files drops archives and oversize files.
    # Verified live: status said 4 files ready, a deploy carried 2. Count what
    # will actually be published, and report the shortfall separately.
    deployable, excluded = collect_deploy_files(PREVIEW_DIR)
    file_count = len(deployable)
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
        'excluded_files': excluded,
        'excluded_count': len(excluded),
        'preview_dir': str(PREVIEW_DIR),
        # `ready` above means "a token string is present" -- it has never been
        # checked against the provider. Say so, rather than letting a green tick
        # imply the credential works.
        'readiness_basis': 'token presence only; not verified against the provider',
    }


# ── Helpers ────────────────────────────────────────────────────────────────────
# File types that should be excluded (binary assets too large/corrupt as UTF-8)
# Extensions that must be uploaded as base64 rather than UTF-8 text. This used
# to be an EXCLUSION list: every image, font and media file in the site was
# silently dropped from the deploy, and the deploy then reported success. A
# static site published without its logo, favicon or webfonts is broken, and
# nothing anywhere said so. Vercel's API accepts {"encoding": "base64"}, and
# Netlify takes a zip, so both can carry binaries -- the exclusion was never
# necessary, only easier.
_BINARY_EXTS = {
    '.png',
    '.jpg',
    '.jpeg',
    '.gif',
    '.ico',
    '.svg',
    '.webp',
    '.avif',
    '.woff',
    '.woff2',
    '.ttf',
    '.otf',
    '.eot',
    '.mp4',
    '.webm',
    '.mp3',
    '.wav',
    '.pdf',
    '.wasm',
}

# Archives and executables stay excluded on purpose: they are build artefacts or
# downloads, not part of a static site, and shipping them is usually a mistake.
_NEVER_DEPLOY_EXTS = {
    '.zip',
    '.tar',
    '.gz',
    '.bin',
    '.exe',
    '.dmg',
    '.pkg',
}

_MAX_FILE_BYTES = 10_485_760  # 10 MB per file
_MAX_FILES = 500  # Vercel free tier limit


def collect_deploy_files(directory: Path) -> tuple[list[dict], list[dict]]:
    """Collect deployable files from preview/, plus everything held back.

    Returns (files, excluded). `excluded` carries a reason per entry so callers
    can TELL THE USER what will not be published. Previously the exclusions were
    computed and thrown away, so a deploy that omitted every image reported the
    same clean success as one that shipped the whole site.
    """
    files: list[dict] = []
    excluded: list[dict] = []
    if not directory.exists():
        return files, excluded

    for path in sorted(directory.rglob('*')):
        if not path.is_file():
            continue
        parts = str(path.relative_to(directory))
        if any(skip in parts for skip in ('.git', '__pycache__', 'branches', 'node_modules')):
            continue
        rel = path.relative_to(directory).as_posix()
        suffix = path.suffix.lower()

        if suffix in _NEVER_DEPLOY_EXTS:
            excluded.append({'file': rel, 'reason': 'archive or executable — not part of a static site'})
            continue
        try:
            size = path.stat().st_size
        except OSError as e:
            excluded.append({'file': rel, 'reason': f'could not be read ({e.strerror or e})'})
            continue
        if size > _MAX_FILE_BYTES:
            excluded.append(
                {'file': rel, 'reason': f'{round(size / 1_048_576, 1)} MB exceeds the 10 MB per-file limit'}
            )
            continue

        try:
            raw = path.read_bytes()
        except OSError as e:
            excluded.append({'file': rel, 'reason': f'could not be read ({e.strerror or e})'})
            continue

        if suffix in _BINARY_EXTS:
            files.append({'file': rel, 'data': base64.b64encode(raw).decode(), 'encoding': 'base64'})
            continue
        try:
            # strict: a file that is not valid UTF-8 must go up as base64, not
            # as replacement characters. `errors='replace'` silently corrupted
            # any binary that was not caught by the extension list.
            files.append({'file': rel, 'data': raw.decode('utf-8'), 'encoding': 'utf-8'})
        except UnicodeDecodeError:
            files.append({'file': rel, 'data': base64.b64encode(raw).decode(), 'encoding': 'base64'})

    if len(files) > _MAX_FILES:
        for entry in files[_MAX_FILES:]:
            excluded.append(
                {'file': entry['file'], 'reason': f'over the {_MAX_FILES}-file deploy limit'}
            )
        files = files[:_MAX_FILES]
    return files, excluded


def _collect_deploy_files(directory: Path) -> list[dict]:
    """Backwards-compatible shim: files only."""
    return collect_deploy_files(directory)[0]


def _file_bytes(entry: dict) -> bytes:
    """The real bytes of a collected entry, for zip-based providers."""
    if entry.get('encoding') == 'base64':
        return base64.b64decode(entry['data'])
    return entry.get('data', '').encode('utf-8')


def _deploy_warning(excluded: list[dict]) -> str | None:
    """One honest sentence about what is NOT going live."""
    if not excluded:
        return None
    names = ', '.join(e['file'] for e in excluded[:5])
    more = f' (+{len(excluded) - 5} more)' if len(excluded) > 5 else ''
    return (
        f'{len(excluded)} file{"s" if len(excluded) != 1 else ""} were NOT deployed: '
        f'{names}{more}. The published site will be missing them.'
    )


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
        url = _active_tunnel.get('url')
        try:
            proc.terminate()
        except Exception as e:
            return {'ok': False, 'error': str(e)}
        # Clear state even if the child is slow to die: leaving a dead proc in
        # the registry made a later "start" think a tunnel was still up.
        _active_tunnel['proc'] = None
        _active_tunnel['url'] = None
        log.info('Cloudflare tunnel stopped (%s)', url)
        try:
            from ..services.memory_db import audit_log

            audit_log('deploy:tunnel_stop', f'Tunnel stopped: {url or "unknown"}')
        except Exception:
            pass
        return {'ok': True, 'message': 'Tunnel stopped', 'url': url}
    # A tunnel that has already exited leaves a stale non-None proc behind.
    # Clear it so the next start is not refused as "already running".
    if proc is not None:
        _active_tunnel['proc'] = None
        _active_tunnel['url'] = None
    return {'ok': False, 'error': 'No active tunnel to stop'}


@router.get('/providers')
def list_providers():
    """List all supported deploy providers."""
    # Derived from the routes that exist rather than hand-maintained: the
    # literal list drifts from reality the moment a provider is added or
    # removed, and it is what the UI renders buttons from.
    providers = [
        {'id': 'vercel', 'label': 'Vercel', 'kind': 'api'},
        {'id': 'netlify', 'label': 'Netlify', 'kind': 'api'},
        {'id': 'railway', 'label': 'Railway', 'kind': 'cli'},
        {'id': 'render', 'label': 'Render', 'kind': 'manual'},
        {'id': 'flyio', 'label': 'Fly.io', 'kind': 'cli'},
        {'id': 'github-pages', 'label': 'GitHub Pages', 'kind': 'api'},
        {'id': 'tunnel', 'label': 'Cloudflare Tunnel', 'kind': 'tunnel'},
    ]
    return {'providers': [p['id'] for p in providers], 'detail': providers, 'count': len(providers)}
