"""Capture inbox API (`/api/inbox`).

One door in. A phone share sheet, a forwarded email, a hook, the terminal and
the web UI all land in the same folder, and the ICM entry router files them.

The share target is the interesting endpoint: it accepts a FORM post, because
that is what the Web Share Target API sends, and it redirects rather than
returning JSON, because the thing on the other end is a phone browser that has
just been handed control by the OS share sheet — a JSON body there is a blank
white screen with braces on it.
"""

from __future__ import annotations

from typing import Any

from fastapi import APIRouter, HTTPException, Request
from fastapi.responses import PlainTextResponse, RedirectResponse

from ..services import capture_inbox as svc
from ..services.request_body import as_text, json_body_or_error

router = APIRouter(prefix='/api/inbox', tags=['inbox'])


@router.get('')
def list_inbox(filed: bool = False, limit: int = 100) -> dict[str, Any]:
    """Everything waiting, newest first."""
    return {'ok': True, 'items': svc.list_items(filed=filed, limit=limit),
            'stats': svc.stats()}


@router.get('/stats')
def inbox_stats() -> dict[str, Any]:
    return {'ok': True, **svc.stats()}


@router.post('')
async def capture_item(req: Request) -> dict[str, Any]:
    """Capture one item. Writes a file and nothing else."""
    body, err = await json_body_or_error(req)
    if err:
        return err
    result = svc.capture(
        text=as_text(body.get('text')),
        title=as_text(body.get('title')),
        source=as_text(body.get('source')) or 'api',
        url=as_text(body.get('url')),
        tags=as_text(body.get('tags')),
    )
    if not result.get('ok'):
        raise HTTPException(status_code=422, detail=result.get('error', 'capture failed'))
    return result


@router.post('/share')
async def share_target(req: Request):
    """PWA Web Share Target endpoint. Accepts a form post, returns a redirect.

    The OS share sheet posts `title`, `text` and `url` as form fields and then
    shows whatever comes back. Returning JSON here would leave the user staring
    at a raw object, so this redirects into the Inbox pane — the phone-side
    confirmation that the capture landed.

    Capture never fails for an interesting reason, so even a malformed share
    lands somewhere a human can find it rather than erroring on a train.
    """
    try:
        form = await req.form()
        title = str(form.get('title') or '')
        text = str(form.get('text') or '')
        url = str(form.get('url') or '')
    except Exception:
        title = text = url = ''

    if not (text.strip() or url.strip() or title.strip()):
        return RedirectResponse('/?pane=inbox&captured=empty', status_code=303)

    result = svc.capture(text=text or title, title=title, source='share', url=url)
    status = 'ok' if result.get('ok') else 'error'
    return RedirectResponse(f'/?pane=inbox&captured={status}', status_code=303)


@router.get('/items/{item_id}')
def get_item(item_id: str) -> dict[str, Any]:
    item = svc.get_item(item_id)
    if item is None:
        raise HTTPException(status_code=404, detail=f'Item {item_id!r} not found')
    return {'ok': True, 'item': item}


@router.delete('/items/{item_id}')
def delete_item(item_id: str) -> dict[str, Any]:
    if not svc.delete_item(item_id):
        raise HTTPException(status_code=404, detail=f'Item {item_id!r} not found')
    return {'ok': True, 'deleted': item_id}


@router.get('/sweep/preview')
def sweep_preview(limit: int = 50) -> dict[str, Any]:
    """Where would everything go? Read-only; files nothing."""
    return svc.sweep(dry_run=True, limit=limit)


@router.post('/sweep')
async def run_sweep(req: Request) -> dict[str, Any]:
    """File everything the router can place. Leaves the rest in the inbox."""
    body, err = await json_body_or_error(req)
    if err:
        return err
    limit = body.get('limit')
    try:
        limit = max(1, min(int(limit), 200)) if limit is not None else svc.SWEEP_LIMIT
    except (TypeError, ValueError):
        limit = svc.SWEEP_LIMIT
    return svc.sweep(dry_run=body.get('dry_run') is True, limit=limit)


@router.post('/sweep/schedule')
async def schedule_sweep(req: Request) -> dict[str, Any]:
    """Run the sweep automatically. Persisted by the existing scheduler."""
    body, err = await json_body_or_error(req)
    if err:
        return err
    try:
        minutes = int(body.get('interval_minutes') or 30)
    except (TypeError, ValueError):
        minutes = 30
    return svc.register_sweep(max(1, min(minutes, 1440)))


@router.get('/export')
def export_inbox(filed: bool = False) -> PlainTextResponse:
    return PlainTextResponse(svc.export_items(filed=filed), media_type='application/x-ndjson')
