"""
Agentic OS — Notifications Router (/api/notifications)
Provides a notification center backend for system alerts, agent events, and user notifications.
"""

from __future__ import annotations

import time
import uuid
from typing import Optional, Union, Any, Dict, List, Tuple, Set, Callable, AsyncGenerator

from fastapi import APIRouter
from pydantic import BaseModel

router = APIRouter(prefix='/api/notifications', tags=['notifications'])

# In-memory notification store (initialized with helpful welcome and status notifications)
_NOTIFICATIONS: list[dict[str, Any]] = [
    {
        'id': 'notif-welcome',
        'title': 'Welcome to Agentic OS v6.0',
        'message': 'Explore the multi-agent Swarm, Memory Galaxy 3D, and Studio builder.',
        'type': 'info',
        'timestamp': time.time() - 3600,
        'read': False,
        'link': 'chat',
    },
    {
        'id': 'notif-security',
        'title': 'Security Shield Active',
        'message': 'Rate limiting, CSP security headers, and CSRF protection are enabled.',
        'type': 'success',
        'timestamp': time.time() - 1800,
        'read': False,
        'link': 'settings',
    },
]


class NotificationCreate(BaseModel):
    """Payload for creating a new notification."""

    title: str
    message: str
    type: str = 'info'  # info, success, warning, error
    link:Optional[ str] = None


@router.get('/list')
def list_notifications(unread_only: bool = False, limit: int = 50) -> dict[str, Any]:
    """Retrieve system and agent notifications, ordered from newest to oldest."""
    items = sorted(_NOTIFICATIONS, key=lambda x: x['timestamp'], reverse=True)
    if unread_only:
        items = [n for n in items if not n['read']]
    return {
        'ok': True,
        'count': len(items[:limit]),
        'unread_count': sum(1 for n in _NOTIFICATIONS if not n['read']),
        'notifications': items[:limit],
    }


@router.get('/unread-count')
def get_unread_count() -> dict[str, Any]:
    """Get the current count of unread notifications."""
    unread = sum(1 for n in _NOTIFICATIONS if not n['read'])
    return {'ok': True, 'unread_count': unread}


@router.post('/create')
def create_notification(payload: NotificationCreate) -> dict[str, Any]:
    """Create and broadcast a new system or agent notification."""
    notif = {
        'id': f'notif-{uuid.uuid4().hex[:8]}',
        'title': payload.title,
        'message': payload.message,
        'type': payload.type,
        'timestamp': time.time(),
        'read': False,
        'link': payload.link,
    }
    _NOTIFICATIONS.insert(0, notif)
    # Keep max 200 notifications in store
    if len(_NOTIFICATIONS) > 200:
        _NOTIFICATIONS.pop()
    return {'ok': True, 'notification': notif}


@router.post('/mark-read/{notif_id}')
def mark_read(notif_id: str) -> dict[str, Any]:
    """Mark a specific notification as read by ID."""
    for n in _NOTIFICATIONS:
        if n['id'] == notif_id:
            n['read'] = True
            return {'ok': True, 'notification': n}
    return {'ok': False, 'error': f"Notification '{notif_id}' not found"}


@router.post('/mark-all-read')
def mark_all_read() -> dict[str, Any]:
    """Mark all current notifications as read."""
    for n in _NOTIFICATIONS:
        n['read'] = True
    return {'ok': True, 'updated_count': len(_NOTIFICATIONS)}


@router.delete('/clear/{notif_id}')
def delete_notification(notif_id: str) -> dict[str, Any]:
    """Delete a specific notification by ID."""
    global _NOTIFICATIONS
    original_len = len(_NOTIFICATIONS)
    _NOTIFICATIONS = [n for n in _NOTIFICATIONS if n['id'] != notif_id]
    if len(_NOTIFICATIONS) == original_len:
        return {'ok': False, 'error': f"Notification '{notif_id}' not found"}
    return {'ok': True, 'deleted_id': notif_id}


@router.delete('/clear-all')
def clear_all_notifications() -> dict[str, Any]:
    """Clear all notifications from the store."""
    _NOTIFICATIONS.clear()
    return {'ok': True, 'message': 'All notifications cleared'}
