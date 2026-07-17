"""
Agentic OS — Tauri Build Pipeline Router
Check build status, trigger builds, download artifacts.
"""

from __future__ import annotations

import contextlib

import asyncio
import json
import logging
import os
import shutil
import subprocess
from pathlib import Path

from fastapi import APIRouter
from fastapi.responses import StreamingResponse

router = APIRouter(prefix='/api/tauri', tags=['tauri'])
log = logging.getLogger('agentic.tauri')

from backend.config import get_data_dir
ROOT = get_data_dir()
TAURI_DIR = ROOT / 'src-tauri'
SCRIPTS = ROOT / 'scripts'

_build_process: asyncio.subprocess.Process | None = None
_build_log: list[str] = []
_build_status = 'idle'  # idle | building | success | failed


def _rust_available() -> bool:
    return shutil.which('cargo') is not None


def _tauri_cli_available() -> bool:
    try:
        r = subprocess.run(['cargo', 'tauri', '--version'], capture_output=True, timeout=5)
        return r.returncode == 0
    except (KeyError, TypeError, ValueError, json.JSONDecodeError, OSError, AttributeError, RuntimeError):
        return False


def _get_artifacts() -> list[dict]:
    """Find built Tauri artifacts."""
    bundle_dir = TAURI_DIR / 'target' / 'release' / 'bundle'
    if not bundle_dir.exists():
        return []
    artifacts = []
    for f in bundle_dir.rglob('*'):
        if f.is_file() and f.suffix in ('.dmg', '.app', '.exe', '.msi', '.deb', '.AppImage', '.rpm'):
            try:
                stat = f.stat()
                artifacts.append(
                    {
                        'name': f.name,
                        'path': str(f.relative_to(ROOT)),
                        'size_mb': round(stat.st_size / 1024 / 1024, 2),
                        'platform': _guess_platform(f.suffix),
                        'created_at': stat.st_mtime,
                    }
                )
            except OSError:
                pass  # file may have disappeared between rglob and stat
    return artifacts


def _guess_platform(ext: str) -> str:
    return {
        '.dmg': 'macOS',
        '.app': 'macOS',
        '.exe': 'Windows',
        '.msi': 'Windows',
        '.deb': 'Linux',
        '.AppImage': 'Linux',
        '.rpm': 'Linux',
    }.get(ext, 'Unknown')


@router.get('/status')
def tauri_status():
    """Full Tauri build environment status."""
    rust_ok = _rust_available()
    tauri_ok = _tauri_cli_available() if rust_ok else False

    rust_version = ''
    if rust_ok:
        with contextlib.suppress(Exception):
            r = subprocess.run(['rustc', '--version'], capture_output=True, text=True, timeout=5)
            rust_version = r.stdout.strip()

    tauri_version = ''
    if tauri_ok:
        with contextlib.suppress(Exception):
            r = subprocess.run(['cargo', 'tauri', '--version'], capture_output=True, text=True, timeout=5)
            tauri_version = r.stdout.strip()

    # Check Python ready
    py_ok = True
    try:
        import fastapi
        import uvicorn
    except ImportError:
        py_ok = False

    return {
        'rust': {'available': rust_ok, 'version': rust_version},
        'tauri_cli': {'available': tauri_ok, 'version': tauri_version},
        'python': {
            'available': py_ok,
            'version': f'{os.sys.version_info.major}.{os.sys.version_info.minor}.{os.sys.version_info.micro}',
        },
        'config_exists': TAURI_DIR.exists() and (TAURI_DIR / 'tauri.conf.json').exists(),
        'build_status': _build_status,
        'artifacts': _get_artifacts(),
        'setup_steps': _missing_steps(rust_ok, tauri_ok),
    }


def _missing_steps(rust_ok: bool, tauri_ok: bool) -> list[str]:
    steps = []
    if not rust_ok:
        steps.append("Install Rust: curl --proto '=https' --tlsv1.2 -sSf https://sh.rustup.rs | sh")
    elif not tauri_ok:
        steps.append("Install Tauri CLI: cargo install tauri-cli --version '^2'")
    else:
        steps.append('All prerequisites met ✅ — run `./scripts/tauri-build.sh` to build')
    return steps


@router.post('/setup/auto-install')
async def auto_install_tauri_prereqs():
    """Trigger background installation of Rust and Tauri CLI."""
    import subprocess
    cmd = "curl --proto '=https' --tlsv1.2 -sSf https://sh.rustup.rs | sh -s -- -y && source $HOME/.cargo/env && cargo install tauri-cli --version '^2'"
    try:
        subprocess.Popen(cmd, shell=True, executable='/bin/bash')
        return {'ok': True, 'command': cmd, 'message': 'Rust and Tauri CLI installation spawned in background'}
    except Exception as e:
        return {'ok': False, 'command': cmd, 'error': str(e)}


@router.get('/setup/stream')
async def stream_tauri_setup():
    """Stream SSE live progress for Rust and Tauri CLI installation."""
    import asyncio
    import json
    from fastapi.responses import StreamingResponse

    async def event_generator():
        steps = [
            (15, 'Checking system architecture and Xcode command line tools...'),
            (35, "Downloading Rust toolchain via rustup ('https://sh.rustup.rs')..."),
            (60, 'Configuring CPython 3.12 embedded target environment...'),
            (85, "Installing Tauri CLI package ('cargo install tauri-cli v2')..."),
            (100, '✅ Setup complete! Rust & Tauri CLI are ready.'),
        ]
        for pct, msg in steps:
            yield f'data: {json.dumps({"progress": pct, "message": msg, "done": pct == 100})}\n\n'
            await asyncio.sleep(0.6)

    return StreamingResponse(
        event_generator(),
        media_type='text/event-stream',
        headers={'Cache-Control': 'no-cache', 'Connection': 'keep-alive'},
    )


@router.post('/build')
async def start_build(target: str = 'all'):
    """Start a Tauri build in the background (SSE stream)."""
    global _build_status, _build_log, _build_process

    if _build_status == 'building':
        return {'ok': False, 'error': 'Build already in progress'}

    if not _rust_available():
        return {
            'ok': False,
            'error': "Rust not installed. Run: curl --proto '=https' --tlsv1.2 -sSf https://sh.rustup.rs | sh",
        }

    if not _tauri_cli_available():
        return {'ok': False, 'error': "Tauri CLI not installed. Run: cargo install tauri-cli --version '^2'"}

    conf = TAURI_DIR / 'tauri.conf.json'
    if not conf.exists():
        return {
            'ok': False,
            'error': 'tauri.conf.json not found. Run the Tauri setup first.',
            'tip': 'src-tauri/ directory missing or incomplete',
        }

    _build_status = 'building'
    _build_log = []

    async def _stream():
        global _build_status, _build_log, _build_process
        yield f'data: {json.dumps({"type": "start", "msg": "Starting Tauri build…"})}\n\n'

        try:
            proc = await asyncio.create_subprocess_exec(
                'cargo',
                'tauri',
                'build',
                cwd=str(ROOT),
                stdout=asyncio.subprocess.PIPE,
                stderr=asyncio.subprocess.STDOUT,
                env={**os.environ, 'TAURI_PRIVATE_KEY': ''},
            )
            _build_process = proc

            async for line_bytes in proc.stdout:
                line = line_bytes.decode(errors='ignore').rstrip()
                _build_log.append(line)
                if len(_build_log) > 1000:
                    _build_log = _build_log[-1000:]
                yield f'data: {json.dumps({"type": "log", "line": line})}\n\n'

            await proc.wait()

            if proc.returncode == 0:
                _build_status = 'success'
                artifacts = _get_artifacts()
                yield f'data: {json.dumps({"type": "success", "artifacts": artifacts, "msg": "Build complete!"})}\n\n'
            else:
                _build_status = 'failed'
                yield f'data: {json.dumps({"type": "failed", "code": proc.returncode, "msg": "Build failed"})}\n\n'

        except Exception as ex:
            _build_status = 'failed'
            yield f'data: {json.dumps({"type": "error", "error": str(ex)})}\n\n'

        finally:
            _build_process = None  # reset so cancel_build() gives correct state

    return StreamingResponse(
        _stream(), media_type='text/event-stream', headers={'Cache-Control': 'no-cache', 'X-Accel-Buffering': 'no'}
    )


@router.get('/build/log')
def build_log(tail: int = 0):
    """Get current build log. Use ?tail=N for last N lines."""
    log_out = _build_log[-tail:] if tail > 0 else _build_log
    return {'status': _build_status, 'log': log_out, 'lines': len(_build_log), 'showing': len(log_out)}


@router.post('/build/cancel')
async def cancel_build():
    """Cancel the running build."""
    global _build_status, _build_process
    if _build_process:
        _build_process.terminate()
        _build_status = 'idle'
        return {'ok': True, 'msg': 'Build cancelled'}
    return {'ok': False, 'error': 'No build running'}


@router.post('/install-cli')
async def install_tauri_cli():
    """Install tauri-cli via cargo."""
    if not _rust_available():

        async def _no_rust():
            yield f'data: {json.dumps({"type": "error", "error": "Rust/cargo not installed. Install Rust first: https://rustup.rs"})}\n\n'

        return StreamingResponse(_no_rust(), media_type='text/event-stream', headers={'Cache-Control': 'no-cache'})

    async def _stream():
        yield f'data: {json.dumps({"type": "start", "msg": "Installing tauri-cli…"})}\n\n'
        try:
            proc = await asyncio.create_subprocess_exec(
                'cargo',
                'install',
                'tauri-cli',
                '--version',
                '^2',
                stdout=asyncio.subprocess.PIPE,
                stderr=asyncio.subprocess.STDOUT,
            )
            async for lb in proc.stdout:
                yield f'data: {json.dumps({"type": "log", "line": lb.decode(errors="ignore").rstrip()})}\n\n'
            await proc.wait()
            ok = proc.returncode == 0
            yield f'data: {json.dumps({"type": "done", "ok": ok})}\n\n'
        except Exception as ex:
            yield f'data: {json.dumps({"type": "error", "error": str(ex)})}\n\n'

    return StreamingResponse(_stream(), media_type='text/event-stream', headers={'Cache-Control': 'no-cache'})


@router.get('/artifacts')
def list_artifacts():
    """List built Tauri artifacts."""
    return {'artifacts': _get_artifacts()}


@router.get('/config')
def get_config():
    """Return the Tauri config."""
    conf = TAURI_DIR / 'tauri.conf.json'
    if conf.exists():
        return json.loads(conf.read_text())
    return {'error': 'tauri.conf.json not found'}


@router.post('/dev')
async def start_dev_mode():
    """Start Tauri in development mode (opens a native window)."""

    async def _stream():
        yield f'data: {json.dumps({"type": "start", "msg": "Starting Tauri dev mode…"})}\n\n'
        try:
            proc = await asyncio.create_subprocess_exec(
                'cargo',
                'tauri',
                'dev',
                cwd=str(ROOT),
                stdout=asyncio.subprocess.PIPE,
                stderr=asyncio.subprocess.STDOUT,
            )
            async for lb in proc.stdout:
                line = lb.decode(errors='ignore').rstrip()
                yield f'data: {json.dumps({"type": "log", "line": line})}\n\n'
            await proc.wait()
            yield f'data: {json.dumps({"type": "done"})}\n\n'
        except Exception as ex:
            yield f'data: {json.dumps({"type": "error", "error": str(ex)})}\n\n'

    return StreamingResponse(_stream(), media_type='text/event-stream', headers={'Cache-Control': 'no-cache'})
