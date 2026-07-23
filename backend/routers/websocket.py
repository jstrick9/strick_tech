"""
Agentic OS — WebSocket Router
Real-time agent status, live chat streaming, task updates.
Clients connect to /ws and receive JSON events.
"""

from __future__ import annotations

import contextlib

import asyncio
import json
import logging
import time

from fastapi import APIRouter, Request, WebSocket, WebSocketDisconnect

from ..security_auth import require_websocket_auth

router = APIRouter(tags=['websocket'])
log = logging.getLogger('agentic.ws')


# ── Connection manager ────────────────────────────────────────────────────────
class ConnectionManager:
    """Core management and execution class for ConnectionManager."""

    def __init__(self):
        self.connections: list[WebSocket] = []

    async def connect(self, ws: WebSocket):
        """Execute or process connect operation."""
        await ws.accept()
        self.connections.append(ws)
        log.info('WS connected — total: %d', len(self.connections))

    def disconnect(self, ws: WebSocket):
        """Execute or process disconnect operation."""
        self.connections.remove(ws)
        log.info('WS disconnected — total: %d', len(self.connections))

    async def broadcast(self, event: dict):
        """Send event to all connected clients."""
        msg = json.dumps(event, default=str)
        dead = []
        for ws in self.connections:
            try:
                await ws.send_text(msg)
            except (KeyError, TypeError, ValueError, json.JSONDecodeError, OSError, AttributeError, RuntimeError):
                dead.append(ws)
        for ws in dead:
            try:
                self.connections.remove(ws)
            except ValueError:
                pass

    async def send_to(self, ws: WebSocket, event: dict):
        """Execute or process send to operation."""
        with contextlib.suppress(Exception):
            await ws.send_text(json.dumps(event, default=str))


manager = ConnectionManager()


# ── Module-level broadcast helper (importable by other routers) ────────────────
async def broadcast(event: dict):
    """Module-level broadcast function — wrapper around manager.broadcast().
    Importable by other routers: from .websocket import broadcast
    """
    await manager.broadcast(event)


# ── WebSocket endpoint ────────────────────────────────────────────────────────
@router.websocket('/ws')
async def websocket_endpoint(ws: WebSocket):
    """Execute or process websocket endpoint operation."""
    if not await require_websocket_auth(ws):
        return
    await manager.connect(ws)
    try:
        # Send initial state
        await _send_init(ws)

        # Start background ping + status updates
        async def heartbeat():
            """Execute or process heartbeat operation."""
            while True:
                await asyncio.sleep(5)
                try:
                    await manager.send_to(ws, {'type': 'ping', 'ts': time.time()})
                except (KeyError, TypeError, ValueError, json.JSONDecodeError, OSError, AttributeError, RuntimeError):
                    break

        async def status_updates():
            """Execute or process status updates operation."""
            while True:
                await asyncio.sleep(8)
                try:
                    agents = await _get_agent_statuses()
                    await manager.send_to(ws, {'type': 'agent_status', 'agents': agents})
                    stats = await _get_memory_stats()
                    await manager.send_to(ws, {'type': 'memory_stats', **stats})
                except (KeyError, TypeError, ValueError, json.JSONDecodeError, OSError, AttributeError, RuntimeError):
                    break

        tasks = [
            asyncio.create_task(heartbeat()),
            asyncio.create_task(status_updates()),
        ]

        # Listen for client messages
        while True:
            try:
                data = await ws.receive_text()
                msg = json.loads(data)
                await _handle_message(ws, msg)
            except WebSocketDisconnect:
                break
            except Exception as e:
                log.warning('WS message error: %s', e)
                break

    except WebSocketDisconnect:
        pass
    finally:
        manager.disconnect(ws)
        for t in tasks:
            t.cancel()


# ── Broadcast helpers (called from other routers) ─────────────────────────────
async def broadcast_agent_status(agent_id: str, status: str, extra: dict = None):
    """Execute or process broadcast agent status operation."""
    await manager.broadcast(
        {
            'type': 'agent_status_update',
            'agent_id': agent_id,
            'status': status,
            **(extra or {}),
        }
    )


async def broadcast_chat_chunk(agent_id: str, delta: str, session_id: str = ''):
    """Execute or process broadcast chat chunk operation."""
    await manager.broadcast(
        {
            'type': 'chat_delta',
            'agent_id': agent_id,
            'delta': delta,
            'session_id': session_id,
        }
    )


async def broadcast_task_update(task: dict):
    """Execute or process broadcast task update operation."""
    await manager.broadcast({'type': 'task_update', 'task': task})


async def broadcast_toast(message: str, kind: str = 'ok'):
    """Execute or process broadcast toast operation."""
    await manager.broadcast({'type': 'toast', 'message': message, 'kind': kind})


async def broadcast_memory_added(memory_id: int, source: str, preview: str):
    """Execute or process broadcast memory added operation."""
    await manager.broadcast(
        {
            'type': 'memory_added',
            'id': memory_id,
            'source': source,
            'preview': preview[:100],
        }
    )


# ── Internal helpers ──────────────────────────────────────────────────────────
async def _send_init(ws: WebSocket):
    """Send initial state snapshot to new client."""
    try:
        agents = await _get_agent_statuses()
        stats = await _get_memory_stats()
        await manager.send_to(
            ws,
            {
                'type': 'init',
                'agents': agents,
                **stats,
                'ts': time.time(),
            },
        )
    except Exception as e:
        log.warning('Init send failed: %s', e)


async def _handle_message(ws: WebSocket, msg: dict):
    """Handle incoming WS message from client."""
    mtype = msg.get('type', '')

    if mtype == 'pong':
        pass  # keep-alive

    elif mtype == 'subscribe_agent':
        await manager.send_to(ws, {'type': 'subscribed', 'agent': msg.get('agent_id')})

    elif mtype == 'request_status':
        agents = await _get_agent_statuses()
        await manager.send_to(ws, {'type': 'agent_status', 'agents': agents})

    elif mtype == 'request_memory_stats':
        stats = await _get_memory_stats()
        await manager.send_to(ws, {'type': 'memory_stats', **stats})


async def _get_agent_statuses() -> list[dict]:
    try:
        from ..services.memory_db import agents_list

        agents = agents_list()
        return [{'id': a['id'], 'name': a['name'], 'status': a['status'], 'avatar': a['avatar']} for a in agents]
    except (KeyError, TypeError, ValueError, json.JSONDecodeError, OSError, AttributeError, RuntimeError):
        return []


async def _get_memory_stats() -> dict:
    try:
        from ..services.memory_db import memory_stats

        return memory_stats()
    except (KeyError, TypeError, ValueError, json.JSONDecodeError, OSError, AttributeError, RuntimeError):
        return {}


# ── REST endpoint to broadcast from external callers ─────────────────────────
@router.post('/api/ws/broadcast')
async def rest_broadcast(req: Request):
    """Execute or process rest broadcast operation."""
    try:
        body = await req.json()
    except (json.JSONDecodeError, TypeError, ValueError):
        body = {}
    await manager.broadcast(body)
    return {'ok': True, 'connections': len(manager.connections)}


@router.get('/api/ws/status')
def ws_status():
    """Execute or process ws status operation."""
    return {'connections': len(manager.connections)}
