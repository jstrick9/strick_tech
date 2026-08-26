"""Capture inbox — one door in, the router files it.

Closes G10. From the second-brain layout the canon points at:

    inbox/      Capture everything unsorted here first
    archive/    Closed projects, old notes

and the ICM invariant that makes it work: state is files on disk, so a captured
thought is a markdown file a human can open, not a row in a table nobody reads.

THE DESIGN, AND WHY IT IS ONE DOOR

The obvious way to "automate my life/computer/work/phone" is four integrations.
That is the hand-written map problem again, one layer up: four capture paths
means four places to change when the routing rules move, and they drift.

Instead there is ONE inbox and one sweep:

    phone share sheet ─┐
    email forward     ─┤
    a hook firing     ─┼─→ inbox/ (a markdown file) ─→ router ─→ workspace
    the terminal      ─┤
    a browser button  ─┘

Adding a source is writing a file into `inbox/`. The routing, the workspace
selection, the stage resolution and the audit trail are all already built and
tested (icm_router), so a new source inherits them for free.

WHY CAPTURE NEVER ROUTES SYNCHRONOUSLY

Capture must not fail because routing failed. Someone sharing a link from a
phone on a train is not in a position to debug a workspace mismatch, and a
capture that errors is a thought that is now lost. So `capture()` only writes
the file — it always succeeds if the disk is writable — and `sweep()` routes
later, separately, and can be re-run. An unroutable item stays in the inbox
rather than being dropped or filed somewhere wrong.

WHAT SWEEP DOES NOT DO

It does not delete. Swept items move to `inbox/_filed/` with a front-matter
record of where they went and why. "Never silently delete" applies here more
than anywhere: this is the folder holding the things a person did not have time
to think about yet.
"""

from __future__ import annotations

import json
import re
import time
from pathlib import Path
from typing import Any

from backend.config import get_data_dir

from .safe_paths import safe_path

ROOT = get_data_dir()
INBOX_DIR = ROOT / 'memory' / 'inbox'
FILED_DIR = INBOX_DIR / '_filed'

# Sources are a closed set so the inbox stays queryable. A free-text source
# field becomes six spellings of "phone" within a month.
SOURCES = ('share', 'email', 'hook', 'terminal', 'web', 'voice', 'api')

MAX_BODY_CHARS = 100_000
MAX_TITLE_CHARS = 120
# A sweep processes a bounded batch. An unbounded sweep over a neglected inbox
# is a request that never returns.
SWEEP_LIMIT = 50

ITEM_ID_RE = re.compile(r'^[0-9]{10}-[a-z0-9]{6}$')
_FM_RE = re.compile(r'^---\s*\n(.*?)\n---\s*\n?(.*)$', re.S)


def _slug(text: str, limit: int = 48) -> str:
    s = re.sub(r'[^a-z0-9]+', '-', str(text or '').lower()).strip('-')
    return s[:limit]


def _now() -> int:
    return int(time.time())


def item_path(item_id: str, filed: bool = False) -> Path | None:
    if not ITEM_ID_RE.match(str(item_id or '')):
        return None
    base = FILED_DIR if filed else INBOX_DIR
    return safe_path(f'{item_id}.md', base=base)


def _parse(text: str) -> tuple[dict[str, Any], str]:
    m = _FM_RE.match(text or '')
    if not m:
        return {}, (text or '').strip()
    meta: dict[str, Any] = {}
    for line in m.group(1).splitlines():
        if ':' not in line:
            continue
        key, _, raw = line.partition(':')
        meta[key.strip()] = raw.strip().strip('"\'')
    return meta, m.group(2).strip()


def _render(meta: dict[str, Any], body: str) -> str:
    lines = ['---']
    for key, val in meta.items():
        lines.append(f'{key}: {val}')
    lines.append('---')
    return '\n'.join(lines) + f'\n\n{body.strip()}\n'


# ── capture ───────────────────────────────────────────────────────────────────
def capture(text: str, title: str = '', source: str = 'api',
            url: str = '', tags: str = '') -> dict[str, Any]:
    """Write one captured item. Always succeeds if the disk is writable.

    Deliberately does no routing, no LLM call and no network I/O. Capture is
    the one operation that must not be able to fail for an interesting reason:
    the person capturing is usually mid-something-else and cannot recover from
    an error, and a failed capture is a lost thought.
    """
    body = str(text or '').strip()[:MAX_BODY_CHARS]
    url = str(url or '').strip()
    if not body and not url:
        return {'ok': False, 'error': 'nothing to capture'}
    if source not in SOURCES:
        source = 'api'

    # The title is for a human scanning the folder, so derive one rather than
    # leaving a wall of timestamps.
    title = str(title or '').strip()[:MAX_TITLE_CHARS]
    if not title:
        first = body.splitlines()[0] if body else url
        title = first.strip()[:MAX_TITLE_CHARS] or 'Captured item'

    ts = _now()
    # Six lowercase alphanumerics, padded, so the id shape holds even for a
    # title made entirely of punctuation or non-Latin characters.
    suffix = re.sub(r'[^a-z0-9]', '', _slug(title, 12) + 'xxxxxx')[:6]
    item_id = f'{ts}-{suffix}'

    INBOX_DIR.mkdir(parents=True, exist_ok=True)
    path = item_path(item_id)
    if path is None:
        return {'ok': False, 'error': 'could not build a safe item path'}
    # A second capture inside the same second must not overwrite the first.
    n = 0
    while path.exists():
        n += 1
        item_id = f'{ts}-{suffix[:5]}{n}'
        path = item_path(item_id)
        if path is None or n > 8:
            return {'ok': False, 'error': 'could not allocate an item id'}

    meta = {
        'id': item_id,
        'title': title,
        'source': source,
        'captured_at': ts,
        'status': 'inbox',
    }
    if url:
        meta['url'] = url
    if tags:
        meta['tags'] = str(tags)[:200]

    try:
        path.write_text(_render(meta, body or url), encoding='utf-8')
    except OSError as exc:
        return {'ok': False, 'error': str(exc)}
    return {'ok': True, 'id': item_id, 'title': title, 'source': source,
            'path': str(path)}


# ── reading ───────────────────────────────────────────────────────────────────
def _read_item(path: Path, filed: bool = False) -> dict[str, Any] | None:
    try:
        text = path.read_text(encoding='utf-8', errors='ignore')
    except OSError:
        return None
    meta, body = _parse(text)
    if not meta.get('id'):
        return None
    return {
        'id': meta['id'],
        'title': meta.get('title', ''),
        'source': meta.get('source', 'api'),
        'captured_at': int(meta.get('captured_at') or 0),
        'status': meta.get('status', 'filed' if filed else 'inbox'),
        'url': meta.get('url', ''),
        'tags': meta.get('tags', ''),
        'workspace': meta.get('workspace', ''),
        'stage': meta.get('stage', ''),
        'reason': meta.get('reason', ''),
        'body': body,
    }


def list_items(filed: bool = False, limit: int = 100) -> list[dict[str, Any]]:
    base = FILED_DIR if filed else INBOX_DIR
    if not base.is_dir():
        return []
    out: list[dict[str, Any]] = []
    for p in sorted(base.glob('*.md'), reverse=True)[:max(1, min(limit, 500))]:
        item = _read_item(p, filed=filed)
        if item:
            out.append(item)
    return out


def get_item(item_id: str) -> dict[str, Any] | None:
    for filed in (False, True):
        p = item_path(item_id, filed=filed)
        if p is not None and p.is_file():
            return _read_item(p, filed=filed)
    return None


def delete_item(item_id: str) -> bool:
    p = item_path(item_id)
    if p is None or not p.is_file():
        return False
    p.unlink()
    return True


# ── the sweep ─────────────────────────────────────────────────────────────────
def _route_text(item: dict[str, Any]) -> str:
    """What the router matches on: the title, the body, and any tags."""
    return ' '.join(filter(None, (item.get('title'), item.get('tags'),
                                  item.get('body', '')[:600])))


def sweep(dry_run: bool = False, limit: int = SWEEP_LIMIT) -> dict[str, Any]:
    """Route inbox items into workspaces. Re-runnable; never destructive.

    An item that routes cleanly is moved to `_filed/` with a record of where it
    went and why. An item that is ambiguous or matches nothing STAYS in the
    inbox — filing it somewhere plausible would be the wrong-folder failure the
    router exists to prevent, and it would be silent.
    """
    from . import icm_router

    filed: list[dict[str, Any]] = []
    left: list[dict[str, Any]] = []

    for item in list_items(limit=limit):
        decision = icm_router.resolve(_route_text(item))
        row = {
            'id': item['id'],
            'title': item['title'],
            'status': decision['status'],
            'workspace_id': decision.get('workspace_id', ''),
            'stage': decision.get('stage', ''),
            'reason': decision.get('reason', ''),
        }
        if not decision.get('matched'):
            left.append(row)
            continue
        if dry_run:
            filed.append(row)
            continue

        moved = _file_item(item, decision)
        row['filed_to'] = moved.get('path', '')
        (filed if moved.get('ok') else left).append(row)

    return {
        'ok': True,
        'dry_run': dry_run,
        'filed': filed,
        'left_in_inbox': left,
        'filed_count': len(filed),
        'remaining': len(left),
    }


def _file_item(item: dict[str, Any], decision: dict[str, Any]) -> dict[str, Any]:
    """Write the item into its workspace stage, then move it to _filed/.

    Two writes, in that order. If the workspace write fails the item is left in
    the inbox rather than being marked filed — reporting success for a capture
    that went nowhere is exactly the failure family this codebase keeps finding.
    """
    from . import icm

    ws = icm.WORKSPACES_DIR / decision['workspace_id']
    stage = decision.get('stage') or ''
    if stage:
        target_dir = ws / 'stages' / stage / 'output'
    else:
        # Non-pipeline forms have no stage sequence; the inbox lands in a
        # dedicated shelf rather than being forced into a stage that
        # does not exist.
        target_dir = ws / '_inbox'

    try:
        target_dir.mkdir(parents=True, exist_ok=True)
        name = f'{item["id"]}-{_slug(item["title"]) or "capture"}.md'
        dest = safe_path(name, base=target_dir)
        if dest is None:
            return {'ok': False, 'error': 'unsafe destination'}
        dest.write_text(
            _render(
                {
                    'id': item['id'],
                    'title': item['title'],
                    'source': item['source'],
                    'captured_at': item['captured_at'],
                    'filed_from': 'inbox',
                    **({'url': item['url']} if item.get('url') else {}),
                },
                item.get('body', ''),
            ),
            encoding='utf-8',
        )
    except OSError as exc:
        return {'ok': False, 'error': str(exc)}

    # Only now mark it filed.
    try:
        FILED_DIR.mkdir(parents=True, exist_ok=True)
        src = item_path(item['id'])
        moved = item_path(item['id'], filed=True)
        if src is None or moved is None:
            return {'ok': False, 'error': 'unsafe item path'}
        meta = {
            'id': item['id'],
            'title': item['title'],
            'source': item['source'],
            'captured_at': item['captured_at'],
            'status': 'filed',
            'filed_at': _now(),
            'workspace': decision['workspace_id'],
            'stage': stage,
            'reason': decision.get('reason', ''),
        }
        moved.write_text(_render(meta, item.get('body', '')), encoding='utf-8')
        if src.is_file():
            src.unlink()
    except OSError as exc:
        return {'ok': False, 'error': str(exc)}
    return {'ok': True, 'path': str(dest)}


def stats() -> dict[str, Any]:
    inbox = list_items(limit=500)
    by_source: dict[str, int] = {}
    for i in inbox:
        by_source[i['source']] = by_source.get(i['source'], 0) + 1
    oldest = min((i['captured_at'] for i in inbox), default=0)
    return {
        'inbox': len(inbox),
        'filed': len(list_items(filed=True, limit=500)),
        'by_source': by_source,
        'oldest_age_days': int((_now() - oldest) / 86400) if oldest else 0,
    }


# ── scheduled sweep ───────────────────────────────────────────────────────────
SWEEP_JOB_ID = 'capture-inbox-sweep'


def register_sweep(interval_minutes: int = 30) -> dict[str, Any]:
    """Run the sweep on a schedule.

    Uses the existing scheduler, which persists its jobs across restarts --
    a capture loop that dies with the process is the "state not surviving
    restart" defect this codebase has already been bitten by.
    """
    try:
        from apscheduler.triggers.interval import IntervalTrigger

        from . import scheduler as sched_svc
    except ImportError:
        return {'ok': False, 'error': 'scheduler unavailable'}

    sched = sched_svc.get_scheduler()
    if sched is None:
        return {'ok': False, 'error': 'scheduler not started'}

    def _job() -> None:
        try:
            sweep()
        except Exception:  # noqa: BLE001 - a sweep failure must not kill the scheduler
            pass

    sched.add_job(_job, IntervalTrigger(minutes=max(1, interval_minutes)),
                  id=SWEEP_JOB_ID, replace_existing=True)
    return {'ok': True, 'job_id': SWEEP_JOB_ID, 'interval_minutes': interval_minutes}


def export_items(filed: bool = False) -> str:
    """The whole inbox as JSONL, for anyone who wants it elsewhere."""
    return '\n'.join(json.dumps(i) for i in list_items(filed=filed, limit=500))
