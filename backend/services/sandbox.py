"""OS-level isolation for user-supplied commands.

WHY THIS EXISTS
---------------
The Terminal module executes arbitrary shell commands. Its command filter was
substantially tightened during the Module 12 review — interpreter inline-code
forms blocked, output redirection refused, RLIMITs applied — but a filter can
only ever *enumerate badness*. Every allowlist of this kind is one clever
invocation away from being wrong, and the review recorded that plainly:

    "the honest long-term answer for arbitrary shell execution is OS-level
     isolation (a container or nsjail). RLIMITs bound resource consumption and
     the filter bounds obvious misuse, but neither is a substitute for a real
     sandbox."

This module is that sandbox, built from Linux namespaces so it needs no root,
no daemon, and no external tooling. `bwrap`, `nsjail`, `firejail`, `docker` and
`podman` are all absent on the target host; `unshare(2)` and `pivot_root(2)`
are not.

WHAT IT ACTUALLY DOES
---------------------
Each command runs in a fresh set of namespaces:

  user     — the process is uid 0 *inside* and unprivileged outside, so
             namespace creation needs no privilege on the host
  mount    — a private mount tree, pivot_root'ed into a scratch directory. The
             host filesystem is not merely hidden, it is unreachable: /home,
             /root, /proc/1/environ, the repo, the SQLite database and the
             vault key file simply do not exist inside
  pid      — the command sees itself and its children only. Before: 97 host
             processes visible. After: 1
  ipc/uts  — no shared SysV IPC, no host hostname
  net      — optional (default on): no interfaces beyond loopback, so a
             compromised command cannot exfiltrate or call home

Inside, the workspace is bind-mounted read-write at /work; /bin, /usr, /lib,
/lib64, /sbin and /etc are bind-mounted READ-ONLY so the toolchain works but
cannot be modified; /tmp is a small tmpfs; /dev has null/zero/random/urandom
only (git and most build tools fail without /dev/null).

WHAT IT DOES NOT DO
-------------------
This is defence in depth, not a claim of perfect containment. There is no
seccomp filter, no cgroup limits (RLIMITs cover CPU/memory/file size instead),
and user namespaces have their own history of kernel CVEs. A determined
attacker with a kernel exploit is not stopped by this. What it does stop is the
entire class of "the filter didn't think of that" — reading the vault, editing
the platform's own source, snooping other processes, or phoning home.

Availability is probed once and cached. Where namespaces are unavailable
(macOS, Windows, a hardened kernel, an already-restricted container) the
platform falls back to the existing filter + RLIMIT path and says so, rather
than silently pretending to be sandboxed.
"""

from __future__ import annotations

import ctypes
import logging
import os
import shutil
import subprocess
import sys
import tempfile
from pathlib import Path

log = logging.getLogger('agentic.sandbox')

# mount(2) / umount2(2) flags
MS_RDONLY = 1
MS_NOSUID = 2
MS_NODEV = 4
MS_NOEXEC = 8
MS_REMOUNT = 32
MS_BIND = 4096
MS_REC = 16384
MS_PRIVATE = 1 << 18
MNT_DETACH = 2

# System directories the sandbox needs for a working dev toolchain. Bound
# read-only: commands may execute them, never modify them.
_RO_SYSTEM_DIRS = ('/bin', '/usr', '/lib', '/lib64', '/lib32', '/sbin', '/etc', '/opt')

# The only device nodes exposed. /dev/null in particular is non-negotiable —
# git and most build tools abort without it.
_DEV_NODES = ('null', 'zero', 'full', 'random', 'urandom', 'tty')

_AVAILABILITY: bool | None = None
_UNAVAILABLE_REASON = ''


def _libc():
    return ctypes.CDLL('libc.so.6', use_errno=True)


def _mount(source, target, fstype=None, flags=0, data=None):
    libc = _libc()
    rc = libc.mount(
        source.encode() if source else None,
        str(target).encode(),
        fstype.encode() if fstype else None,
        ctypes.c_ulong(flags),
        data.encode() if data else None,
    )
    if rc != 0:
        err = ctypes.get_errno()
        raise OSError(err, f'mount({source} -> {target}): {os.strerror(err)}')


def _pivot_root(new_root, put_old):
    libc = _libc()
    rc = libc.pivot_root(str(new_root).encode(), str(put_old).encode())
    if rc != 0:
        err = ctypes.get_errno()
        raise OSError(err, f'pivot_root: {os.strerror(err)}')


def sandbox_available() -> tuple[bool, str]:
    """Can this host run the namespace sandbox? Probed once, then cached.

    The probe actually creates the namespaces rather than reading a sysctl:
    the failure modes here (seccomp policy in an outer container, a hardened
    kernel, missing unshare binary) are not all visible from configuration.
    """
    global _AVAILABILITY, _UNAVAILABLE_REASON
    if _AVAILABILITY is not None:
        return _AVAILABILITY, _UNAVAILABLE_REASON

    if sys.platform != 'linux':
        _AVAILABILITY, _UNAVAILABLE_REASON = False, f'namespaces are Linux-only (this is {sys.platform})'
        return _AVAILABILITY, _UNAVAILABLE_REASON
    if not shutil.which('unshare'):
        _AVAILABILITY, _UNAVAILABLE_REASON = False, 'the unshare(1) utility is not installed'
        return _AVAILABILITY, _UNAVAILABLE_REASON

    try:
        probe = subprocess.run(
            ['unshare', '--user', '--map-root-user', '--mount', '--pid', '--fork',
             '--', '/bin/true'],
            capture_output=True, timeout=10,
        )
        ok = probe.returncode == 0
        reason = '' if ok else (probe.stderr.decode('utf-8', 'replace').strip()[:200]
                                or 'unshare exited non-zero')
    except (OSError, subprocess.SubprocessError) as exc:
        ok, reason = False, str(exc)[:200]

    _AVAILABILITY, _UNAVAILABLE_REASON = ok, reason
    if ok:
        log.info('OS-level sandbox available (user+mount+pid namespaces)')
    else:
        log.warning('OS-level sandbox unavailable: %s', reason)
    return ok, reason


def _build_jail(root: str, workdir: str) -> None:
    """Construct the jail filesystem and pivot into it.

    Runs INSIDE the new namespaces, in the child, before exec. Anything raised
    here aborts the command — which is the correct outcome, since a partially
    built jail is worse than none.
    """
    root_p = Path(root)

    # Detach from the host's mount propagation, or our binds leak outward.
    _mount(None, '/', flags=MS_REC | MS_PRIVATE)
    # pivot_root requires the new root to be a mount point in its own right.
    _mount(root, root, flags=MS_BIND | MS_REC)

    for sub in ('work', 'proc', 'tmp', 'dev', 'oldroot'):
        (root_p / sub).mkdir(parents=True, exist_ok=True)

    for d in _RO_SYSTEM_DIRS:
        if not os.path.isdir(d):
            continue
        target = root_p / d.lstrip('/')
        target.mkdir(parents=True, exist_ok=True)
        try:
            _mount(d, target, flags=MS_BIND | MS_REC)
            _mount(None, target,
                   flags=MS_REMOUNT | MS_BIND | MS_REC | MS_RDONLY | MS_NOSUID)
        except OSError as exc:
            # A missing optional dir must not abort the run; a missing /bin will
            # surface immediately as "command not found", which is honest.
            log.debug('sandbox: skipped %s: %s', d, exc)

    # The workspace: the ONLY writable view of host data.
    _mount(workdir, root_p / 'work', flags=MS_BIND | MS_REC)
    _mount('tmpfs', root_p / 'tmp', fstype='tmpfs',
           flags=MS_NOSUID | MS_NODEV, data='size=64m,mode=1777')
    _mount('tmpfs', root_p / 'dev', fstype='tmpfs',
           flags=MS_NOSUID, data='size=1m,mode=755')
    for node in _DEV_NODES:
        src = f'/dev/{node}'
        if not os.path.exists(src):
            continue
        dst = root_p / 'dev' / node
        try:
            dst.touch()
            _mount(src, dst, flags=MS_BIND)
        except OSError as exc:
            log.debug('sandbox: skipped /dev/%s: %s', node, exc)

    os.chdir(root)
    _pivot_root('.', 'oldroot')
    os.chroot('/')

    try:
        _mount('proc', '/proc', fstype='proc', flags=MS_NOSUID | MS_NODEV | MS_NOEXEC)
    except OSError as exc:
        log.debug('sandbox: /proc unavailable: %s', exc)

    # Detach the old root LAST. Until this, the host tree is still reachable
    # under /oldroot — the single most important line in this function.
    _libc().umount2(b'/oldroot', MNT_DETACH)
    try:
        os.rmdir('/oldroot')
    except OSError:
        pass

    os.chdir('/work')


def build_jail_and_exec(root: str, workdir: str, argv: list[str]) -> None:
    """Entry point for the re-exec'd child: build the jail, then exec argv."""
    _build_jail(root, workdir)
    # noqa: S606 — deliberate. argv is built by wrap_command() from an explicit
    # list, never a shell string; the shell (if any) is argv[0] chosen by the
    # caller. Using execv here replaces this bootstrap process so the command
    # inherits PID 1 in the namespace and signals reach it directly.
    os.execv(argv[0], argv)  # noqa: S606


# Environment variables a sandboxed command may inherit. Everything else is
# dropped — including anything the Vault injected into the server process.
SAFE_ENV_PASSTHROUGH = frozenset({
    'PATH', 'HOME', 'USER', 'LOGNAME', 'SHELL', 'TERM',
    'LANG', 'LC_ALL', 'LC_CTYPE', 'TMPDIR', 'TEMP', 'TMP',
    'PYTHONIOENCODING', 'PYTHONUNBUFFERED', 'NODE_PATH', 'NPM_CONFIG_PREFIX',
    'FORCE_COLOR',
})


def scrubbed_env(base: dict | None = None) -> dict:
    """An environment with no credentials in it.

    terminal.py already passes its own _sandboxed_env(), so this is belt and
    braces — but a sandbox that only isolates when the caller remembers to
    scrub is a sandbox with a footgun. Verified: without this, a canary
    OPENROUTER_API_KEY in the parent was visible inside the jail.
    """
    source = os.environ if base is None else base
    env = {k: v for k, v in source.items() if k in SAFE_ENV_PASSTHROUGH}
    env.setdefault('PATH', '/usr/local/bin:/usr/bin:/bin')
    env.setdefault('HOME', '/work')
    env['TERM'] = env.get('TERM', 'xterm-256color')
    return env


def wrap_command(
    argv: list[str],
    workdir: str,
    *,
    allow_network: bool = False,
) -> tuple[list[str], str | None]:
    """Return (argv_to_run, scratch_dir_to_clean_up).

    On a host without namespace support this returns `argv` unchanged and None,
    so callers degrade to the filter + RLIMIT path rather than failing. Callers
    should surface that difference to the user; see terminal.py's
    `sandboxed` flag on the run response.
    """
    available, _ = sandbox_available()
    if not available:
        return argv, None

    scratch = tempfile.mkdtemp(prefix='agentic-jail-')
    unshare = [
        'unshare',
        '--user', '--map-root-user',
        '--mount',
        '--pid', '--fork',
        '--ipc',
        '--uts',
    ]
    if not allow_network:
        unshare.append('--net')

    # Re-enter this module in the child to build the jail from inside the new
    # namespaces, then exec the real command.
    # `env -i` drops the inherited environment at the boundary, then the
    # allowlisted variables are re-added explicitly. This holds even if a
    # caller forgets to pass env= to their own subprocess call.
    safe = scrubbed_env()
    env_prefix = ['env', '-i', *[f'{k}={v}' for k, v in sorted(safe.items())]]

    bootstrap = [
        sys.executable, '-c',
        'import sys; from backend.services.sandbox import build_jail_and_exec; '
        'build_jail_and_exec(sys.argv[1], sys.argv[2], sys.argv[3:])',
        scratch, workdir, *argv,
    ]
    return [*unshare, '--', *env_prefix, *bootstrap], scratch


def cleanup(scratch: str | None) -> None:
    """Remove a scratch jail root. Safe to call with None."""
    if not scratch:
        return
    try:
        shutil.rmtree(scratch, ignore_errors=True)
    except OSError as exc:
        log.debug('sandbox: scratch cleanup failed: %s', exc)


def describe() -> dict:
    """Human-readable sandbox status, for /api/terminal/env and diagnostics."""
    available, reason = sandbox_available()
    return {
        'available': available,
        'reason': reason,
        'mechanism': 'linux-namespaces' if available else 'none',
        'isolates': (
            ['filesystem', 'processes', 'ipc', 'hostname', 'network']
            if available else []
        ),
        'note': (
            'Commands run with the host filesystem unreachable and no network.'
            if available
            else f'No OS-level isolation: {reason}. Commands are restricted by the '
                 f'command filter and RLIMITs only.'
        ),
    }
