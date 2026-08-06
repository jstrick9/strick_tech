"""Track a background install so its progress can be reported honestly.

WHY THIS EXISTS
───────────────
Two setup flows -- Tauri (Rust + tauri-cli) and Browser Agent (Playwright +
Chromium) -- had the same shape:

    POST /setup/auto-install   spawns the installer, returns ok:true instantly
    GET  /setup/stream         yields HARDCODED percentages on a timer

The stream was pure theatre. `tauri_build.py` slept 0.6s between five fixed
steps and then emitted:

    "✅ Setup complete! Rust & Tauri CLI are ready."

with no check of any kind. `browser_agent.py` did the same over four steps at
0.5s. So the UI showed a progress bar reaching 100% and toasted
"✅ Rust & Tauri CLI ready!" **about three seconds** after the click, while the
real `cargo install tauri-cli` takes on the order of ten minutes -- and would
still be running, or already failed, when the user was told it had finished.

Measured: probing POST /api/tauri/build on this machine started a genuine Rust
compilation that consumed the box. The install is real; only the reporting was
fake.

Consequences of the lie, in order of how much they cost the user:
  * They act on "ready" -- click Build -- and get a confusing failure.
  * A failed install reports success, so there is nothing to retry and no
    error text to search for.
  * `auto-install` returned ok:true whenever `Popen` itself did not raise,
    which is almost always, even if the command is missing or exits 1.

WHAT THIS PROVIDES
──────────────────
A tiny registry of running install jobs. The spawner records the process; the
stream reports what the process is ACTUALLY doing -- real stdout lines, real
exit code, real success or failure -- and says so plainly when it cannot tell.

Deliberately not a task queue. One job per key, in memory, no persistence: the
installs are one-shot, user-initiated, and a restart mid-install is already
visible because the tool is either on PATH afterwards or it is not.
"""
from __future__ import annotations

import subprocess
import threading
import time
from typing import Any

_MAX_LINES = 400          # bounded so a chatty compiler cannot exhaust memory
_jobs: dict[str, dict[str, Any]] = {}
_lock = threading.Lock()


def start(key: str, argv: list[str], *, shell_cmd: str | None = None,
          cwd: str | None = None, env: dict[str, str] | None = None) -> dict[str, Any]:
    """Spawn an install and start capturing its output.

    Returns the job record. If one is already running under this key the
    existing job is returned untouched rather than spawning a second copy --
    two concurrent `cargo install` runs fight over the same lock file and both
    fail confusingly.
    """
    with _lock:
        existing = _jobs.get(key)
        if existing and existing['status'] == 'running':
            return existing

        job: dict[str, Any] = {
            'key': key,
            'status': 'running',
            'lines': [],
            'started_at': time.time(),
            'finished_at': None,
            'returncode': None,
            'error': None,
            'command': shell_cmd or ' '.join(argv),
        }
        _jobs[key] = job

    try:
        if shell_cmd:
            proc = subprocess.Popen(
                shell_cmd, shell=True, executable='/bin/bash', cwd=cwd, env=env,
                stdout=subprocess.PIPE, stderr=subprocess.STDOUT,
                text=True, bufsize=1, start_new_session=True,
            )
        else:
            proc = subprocess.Popen(
                argv, cwd=cwd, env=env,
                stdout=subprocess.PIPE, stderr=subprocess.STDOUT,
                text=True, bufsize=1, start_new_session=True,
            )
    except Exception as exc:
        # THE BUG THIS REPLACES: the old code caught this and returned ok:true
        # anyway in the common path. A spawn failure is a failure.
        with _lock:
            job['status'] = 'failed'
            job['error'] = str(exc)
            job['finished_at'] = time.time()
        return job

    job['pid'] = proc.pid

    def _pump() -> None:
        try:
            assert proc.stdout is not None
            for raw in proc.stdout:
                line = raw.rstrip('\n')
                with _lock:
                    job['lines'].append(line)
                    if len(job['lines']) > _MAX_LINES:
                        # Keep the head (what it set out to do) and the tail
                        # (where it went wrong); the middle of a compile log is
                        # the least useful part.
                        job['lines'] = job['lines'][:40] + ['… (truncated) …'] + job['lines'][-(_MAX_LINES - 41):]
        except Exception as exc:  # pragma: no cover - stream closed early
            with _lock:
                job['error'] = job['error'] or str(exc)
        finally:
            code = proc.wait()
            with _lock:
                job['returncode'] = code
                job['status'] = 'done' if code == 0 else 'failed'
                job['finished_at'] = time.time()
                if code != 0 and not job['error']:
                    tail = [ln for ln in job['lines'][-8:] if ln.strip()]
                    job['error'] = (tail[-1] if tail else f'exited with code {code}')

    threading.Thread(target=_pump, daemon=True, name=f'install:{key}').start()
    return job


def get(key: str) -> dict[str, Any] | None:
    with _lock:
        job = _jobs.get(key)
        return dict(job, lines=list(job['lines'])) if job else None


def snapshot(key: str) -> dict[str, Any]:
    """Everything a progress UI needs, with no invented numbers."""
    job = get(key)
    if not job:
        return {'status': 'idle', 'lines': [], 'elapsed': 0}
    return {
        'status': job['status'],
        'lines': job['lines'],
        'returncode': job['returncode'],
        'error': job['error'],
        'command': job['command'],
        'elapsed': round((job['finished_at'] or time.time()) - job['started_at'], 1),
    }


def reset(key: str | None = None) -> None:
    """Clear job state (used by tests)."""
    with _lock:
        if key is None:
            _jobs.clear()
        else:
            _jobs.pop(key, None)
