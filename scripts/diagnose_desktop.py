#!/usr/bin/env python3
"""Diagnose a packaged Agentic OS desktop build.

Answers the questions that cannot be answered by reading the repo:

  1. Is the running app serving the code you think it is?
  2. Does its backend actually report the unlocked tier?
  3. Is a local Ollama visible to it?

Run with the desktop app OPEN, then paste the whole output:

    python3 scripts/diagnose_desktop.py

No secrets are printed: anything that looks like a key or token is redacted.

WHY PYTHON AND NOT A SHELL SCRIPT
The shell version of this produced FIVE false alarms in a row -- reporting a
current build as stale, a running app as unreachable, and an expected hash
difference as a fault -- every one of them a shell-quoting or pipeline artefact
rather than a real finding. A diagnostic that invents faults is worse than no
diagnostic, because it sends you hunting things that were never wrong.
"""

from __future__ import annotations

import json
import os
import re
import subprocess
import sys
import urllib.error
import urllib.request
from datetime import datetime, timezone

PORT = os.environ.get('AGENTIC_PORT', '8787')
BASE = f'http://127.0.0.1:{PORT}'
OLLAMA = os.environ.get('OLLAMA_BASE_URL', 'http://127.0.0.1:11434').rstrip('/')

SECRET_RE = re.compile(r'([A-Za-z_]*(?:KEY|TOKEN|SECRET|PASSWORD)[A-Za-z_]*\s*=\s*)\S+', re.I)


def line() -> None:
    print('-' * 60)


def get(url: str, timeout: int = 8) -> tuple[int, str]:
    # Only ever called with the http(s) endpoints built above from a fixed
    # host and port; refuse anything else so a stray env var cannot turn this
    # into a file: read.
    if not url.startswith(('http://', 'https://')):
        return 0, ''
    try:
        with urllib.request.urlopen(url, timeout=timeout) as r:  # noqa: S310
            return r.status, r.read().decode('utf-8', 'replace')
    except urllib.error.HTTPError as e:
        return e.code, ''
    except Exception:
        return 0, ''


def get_json(url: str, timeout: int = 8) -> dict:
    code, body = get(url, timeout)
    if code != 200 or not body:
        return {}
    try:
        return json.loads(body)
    except ValueError:
        return {}


def sh(cmd: list[str]) -> str:
    try:
        return subprocess.run(cmd, capture_output=True, text=True, timeout=20).stdout.strip()
    except Exception:
        return ''


print('AGENTIC OS DESKTOP DIAGNOSTIC')
print('generated:', datetime.now(timezone.utc).strftime('%Y-%m-%dT%H:%M:%SZ'))
line()

# ── 1. repo state ─────────────────────────────────────────────────────────────
print('[1] REPO STATE')
if sh(['git', 'rev-parse', '--git-dir']):
    print('  HEAD:  ', sh(['git', 'log', '--oneline', '-1']))
    print('  branch:', sh(['git', 'rev-parse', '--abbrev-ref', 'HEAD']))
    dirty = [x for x in sh(['git', 'status', '--porcelain']).split('\n') if x.strip()]
    print('  uncommitted files:', len(dirty))
    subprocess.run(['git', 'fetch', '-q', 'origin'], capture_output=True, timeout=60)
    behind = sh(['git', 'rev-list', '--count', 'HEAD..origin/main'])
    print('  commits behind origin/main:', behind or '?')
else:
    print('  not a git checkout')
line()

# ── 2. the running app ────────────────────────────────────────────────────────
print(f'[2] RUNNING APP on {BASE}')
code, _ = get(f'{BASE}/api/health', 5)
print(f'  /api/health -> {code}')
if code != 200:
    print('  !! Not reachable. Open the app first, or set AGENTIC_PORT.')
    line()
    print('END')
    sys.exit(0)

code, html = get(f'{BASE}/')
print(f'  GET / -> {code}, {len(html)} bytes')
if not html:
    # This exact case previously made every canary read ABSENT, which I
    # misread as a stale build. Unreachable is not the same as absent.
    print('  !! Empty body. Canaries below would all read ABSENT for that')
    print('     reason alone, which is NOT evidence of a stale frontend.')
    line()
    print('END')
    sys.exit(0)

# The app REWRITES index.html to point at content-hashed bundles under
# frontend/dist. So the served bytes SHOULD differ from the file on disk when
# bundling is on -- judge staleness by content, never by a hash comparison.
print('  served script tags:')
for tag in re.findall(r'/static/(?:dist|js)/[A-Za-z0-9._-]+\.js', html)[:4]:
    print('   ', tag)

print('  content canaries:')
CANARIES = [
    ('CORE MODULES', 'the renamed sidebar section (post-unlock)'),
    ('data-nav="icm"', 'the Workspaces pane'),
    ('data-nav="inbox"', 'the Inbox pane'),
    ('data-nav="kanban"', 'the Tasks pane'),
]
stale = False
for needle, what in CANARIES:
    ok = needle in html
    if not ok:
        stale = True
    print(f'    {"present" if ok else "ABSENT ":8} {needle:22} {what}')
if stale:
    print()
    print('  => The served frontend is OLDER than this checkout.')
    print('     If you are seeing a Pro/upgrade popup, this is the cause:')
    print('     the app serves pre-built JS from frontend/dist, and yours is stale.')
    print('     Fix:  python3 scripts/build_bundle.py   then rebuild the app.')
else:
    print('  => served frontend matches this checkout.')

# The canaries above only prove index.html is current. index.html is served
# from the checkout, so it is ALWAYS current -- even when the packaged .app
# ships months-old JavaScript. That gap is exactly how a stale desktop build
# passed this diagnostic while still exhibiting a fixed bug.
#
# Fetch the actual served bundle and look for behaviour, not markup.
print('  served JS canaries (these prove the JAVASCRIPT is current):')
_app_tag = None
for tag in re.findall(r'/static/dist/app\.[a-f0-9]+\.js', html):
    _app_tag = tag
    break
if not _app_tag:
    print('    (bundling off -- individual modules served, nothing to check)')
else:
    _code, _js = get(f'{BASE}{_app_tag}', 20)
    if _code != 200 or not _js:
        print(f'    !! {_app_tag} -> {_code}. The page references a bundle the')
        print('       server will not serve. That alone breaks the whole app.')
    else:
        JS_CANARIES = [
            ('SELF_CLICK_EVENTS',
             'hover no longer fires click actions (sidebar glitch fix)'),
            ('autoDetectLocalModels',
             'Ollama is probed at startup'),
            # NOTE: only symbols that live in the MAIN bundle belong here.
            # kanbanOnDrop was in this list briefly and read ABSENT against a
            # perfectly current build -- Kanban is a lazily-loaded pane chunk
            # (pane-kanban.*.js), not part of app.*.js. A canary that reports a
            # false ABSENT is worse than no canary; it is what sent me chasing
            # a phantom the last time this tool asserted something it had not
            # measured.
        ]
        js_stale = False
        for needle, what in JS_CANARIES:
            ok = needle in _js
            if not ok:
                js_stale = True
            print(f'    {"present" if ok else "ABSENT ":8} {needle:22} {what}')
        if js_stale:
            print()
            print('  => THE SERVED JAVASCRIPT IS STALE.')
            print('     index.html is current but the bundle is not, so the app')
            print('     LOOKS up to date and behaves like an old build.')
            print('     If you are running the packaged .app, it is almost')
            print('     certainly an older bundle. Rebuild and relaunch:')
            print('       ./build_macos_desktop.sh --bundle-python')

if os.path.isdir('frontend/dist'):
    n = len(os.listdir('frontend/dist'))
    print(f'  frontend/dist: {n} files')
    if n and os.path.exists('scripts/build_bundle.py'):
        out = sh([sys.executable, 'scripts/build_bundle.py', '--check'])
        print('  bundle freshness:', out.splitlines()[-1] if out else '(no output)')
else:
    print('  frontend/dist: MISSING -- the app cannot serve current JS.')
    print('     Fix: python3 scripts/build_bundle.py')
line()

# ── 3. licence / unlock ───────────────────────────────────────────────────────
print('[3] LICENCE + UNLOCK')
lic = get_json(f'{BASE}/api/license/status')
for k in ('tier', 'unlocked', 'all_features', 'is_trial', 'trial_days_left'):
    if k in lic:
        print(f'  license.{k:<16} = {lic[k]}')
ui = get_json(f'{BASE}/api/profile/ui-config')
for k in ('tier', 'unlocked', 'all_features'):
    print(f'  ui-config.{k:<14} = {ui.get(k)}')
enforce = os.environ.get('AGENTIC_ENFORCE_LICENSE', '')
print(f'  AGENTIC_ENFORCE_LICENSE = {enforce or "<unset>"}')
if enforce.strip().lower() in ('1', 'true', 'yes'):
    print('  !! Set. The paywall is ON BY REQUEST. Unset it to unlock.')
if lic.get('unlocked') and ui.get('unlocked'):
    print('  => backend is fully unlocked. A popup here means STALE FRONTEND JS.')
line()

# ── 4. Ollama ─────────────────────────────────────────────────────────────────
print('[4] OLLAMA')
print(f'  probing {OLLAMA}/api/tags')
tags = get_json(f'{OLLAMA}/api/tags', 5)
models = [m.get('name') for m in tags.get('models', [])] if tags else []
if models:
    print(f'  reachable, {len(models)} model(s):')
    for m in models[:12]:
        print('   -', m)
else:
    print('  NOT reachable from this shell.')
    print('   - is `ollama serve` running?  try: ollama list')
print(f'  OLLAMA_BASE_URL = {os.environ.get("OLLAMA_BASE_URL", "<unset>")}')
code, _ = get(f'{BASE}/api/onboarding/quick-setup/status', 5)
print(f'  app /api/onboarding/quick-setup/status -> {code}')

# Probe the detect endpoint rather than asserting anything about it. The
# previous version printed "this build has no standalone Ollama detect
# endpoint" as a HARDCODED line -- it never made the request. Once the endpoint
# shipped, the diagnostic kept reporting it missing, on a build that had it.
# A diagnostic that states conclusions it did not measure is worse than no
# diagnostic: it sends you hunting for a bug that is not there.
dcode, dbody = get(f'{BASE}/api/onboarding/detect-local-models', 8)
print(f'  app /api/onboarding/detect-local-models -> {dcode}')
if dcode == 200:
    try:
        d = json.loads(dbody)
    except Exception:
        d = {}
    print(f'    available       = {d.get("available")}')
    print(f'    backend         = {d.get("backend")}')
    print(f'    base_url        = {d.get("base_url")}')
    print(f'    models seen     = {len(d.get("models") or [])}')
    print(f'    suggested_model = {d.get("suggested_model") or "<none>"}')
    if models and not d.get('available'):
        print('  !! This shell sees Ollama but the APP does not. The app is')
        print('     probably sandboxed away from 127.0.0.1:11434, or is using a')
        print('     different OLLAMA_BASE_URL. This is the real defect.')
elif dcode == 404:
    print('  !! Endpoint missing -- this build predates the Ollama detect route.')
    print('     Pull the latest main and rebuild.')
else:
    print(f'  !! Unexpected status {dcode}.')
line()

# ── 5. process ────────────────────────────────────────────────────────────────
print('[5] APP PROCESS')
ps = sh(['ps', 'ax', '-o', 'pid,command'])
for row in ps.split('\n'):
    if re.search(r'Agentic OS|run\.py|tauri', row, re.I) and 'diagnose' not in row:
        print('  ', SECRET_RE.sub(r'\1<redacted>', row.strip())[:180])
line()
print('END — paste everything above.')
