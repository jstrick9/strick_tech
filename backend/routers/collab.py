"""
Agentic OS — Real-time Collaboration Router
Shared sessions, live cursors, presence indicators.
Uses in-memory state + WebSocket broadcast.
"""
from __future__ import annotations
import asyncio, json, time, uuid
from fastapi import APIRouter, Request, WebSocket, WebSocketDisconnect

router = APIRouter(prefix="/api/collab", tags=["collab"])

# ── In-memory session state ────────────────────────────────────────────────────
class CollabSession:
    def __init__(self, session_id: str):
        self.id         = session_id
        self.created    = time.time()
        self.peers: dict[str, dict]         = {}  # peer_id → {name, color, pane, cursor}
        self.connections: dict[str, WebSocket] = {}  # peer_id → ws
        self.shared_state: dict             = {}  # shared key-value store

    def add_peer(self, peer_id: str, name: str, color: str):
        self.peers[peer_id] = {
            "id": peer_id, "name": name, "color": color,
            "pane": "chat", "cursor": None, "last_seen": time.time(),
        }

    def remove_peer(self, peer_id: str):
        self.peers.pop(peer_id, None)
        self.connections.pop(peer_id, None)

    async def broadcast(self, event: dict, exclude: str = ""):
        dead = []
        for pid, ws in self.connections.items():
            if pid == exclude:
                continue
            try:
                await ws.send_text(json.dumps(event, default=str))
            except Exception:
                dead.append(pid)
        for pid in dead:
            self.remove_peer(pid)

    def snapshot(self) -> dict:
        return {
            "id":     self.id,
            "peers":  list(self.peers.values()),
            "state":  self.shared_state,
            "created": self.created,
        }


_sessions: dict[str, CollabSession] = {}

PEER_COLORS = [
    "#5b8af8", "#9d74f5", "#4cc98a", "#f0c060",
    "#f06080", "#38c5d8", "#f08850", "#c084fc",
]


def _get_or_create(session_id: str) -> CollabSession:
    if session_id not in _sessions:
        _sessions[session_id] = CollabSession(session_id)
    return _sessions[session_id]


# ── REST endpoints ─────────────────────────────────────────────────────────────
@router.get("/sessions")
def list_sessions():
    return [s.snapshot() for s in _sessions.values()]


@router.post("/sessions")
async def create_session():
    # FIX 1: removed broken 'req: dict = None' parameter — session creation needs no body
    sid = str(uuid.uuid4())[:8]
    _sessions[sid] = CollabSession(sid)
    return {"ok": True, "session_id": sid, "invite_url": f"/?collab={sid}"}


@router.get("/sessions/{session_id}")
def get_session(session_id: str):
    if session_id not in _sessions:
        return {"ok": False, "error": "Session not found"}
    return _sessions[session_id].snapshot()


@router.delete("/sessions/{session_id}")
def close_session(session_id: str):
    _sessions.pop(session_id, None)
    return {"ok": True}


@router.get("/sessions/{session_id}/state")
def get_shared_state(session_id: str, key: str = ""):
    sess = _sessions.get(session_id)
    if not sess:
        return {"ok": False, "error": "Session not found"}
    if key:
        return {"ok": True, "key": key, "value": sess.shared_state.get(key)}
    return {"ok": True, "state": sess.shared_state}


@router.post("/sessions/{session_id}/state")
async def set_shared_state(session_id: str, req: Request):
    # FIX 2: implement the stub — actually store state + broadcast to peers
    sess = _sessions.get(session_id)
    if not sess:
        return {"ok": False, "error": "Session not found"}
    try:
        try:
            body = await req.json()
        except Exception:
            body = {}
    except Exception:
        return {"ok": False, "error": "Invalid JSON body"}
    key   = str(body.get("key",""))[:64]
    value = body.get("value")
    if not key:
        return {"ok": False, "error": "key required"}
    sess.shared_state[key] = value
    # Broadcast to connected peers
    await sess.broadcast({"type": "state_changed", "key": key, "value": value})
    return {"ok": True, "key": key, "value": value}


# ── WebSocket endpoint ─────────────────────────────────────────────────────────
@router.websocket("/sessions/{session_id}/ws")
async def collab_ws(ws: WebSocket, session_id: str):
    """
    WebSocket for real-time collaboration.
    Client sends: {type, payload}
    Server broadcasts: {type, peer_id, payload, peers}
    """
    await ws.accept()

    # Assign peer ID and color
    peer_id = str(uuid.uuid4())[:8]
    sess    = _get_or_create(session_id)
    idx     = len(sess.peers) % len(PEER_COLORS)
    color   = PEER_COLORS[idx]

    try:
        # Wait for join message
        raw  = await asyncio.wait_for(ws.receive_text(), timeout=5.0)
        join = json.loads(raw)
        name = join.get("name", f"User {peer_id[:4]}")

        sess.add_peer(peer_id, name, color)
        sess.connections[peer_id] = ws

        # Send welcome
        await ws.send_text(json.dumps({
            "type":    "joined",
            "peer_id": peer_id,
            "color":   color,
            "session": sess.snapshot(),
        }))

        # Broadcast peer join
        await sess.broadcast({
            "type":    "peer_joined",
            "peer_id": peer_id,
            "name":    name,
            "color":   color,
            "peers":   list(sess.peers.values()),
        }, exclude=peer_id)

        # Message loop
        while True:
            try:
                raw = await asyncio.wait_for(ws.receive_text(), timeout=30.0)
                msg = json.loads(raw)
                await _handle_collab_msg(sess, peer_id, msg)
            except asyncio.TimeoutError:
                # Send ping
                await ws.send_text(json.dumps({"type": "ping"}))
            except WebSocketDisconnect:
                break

    except WebSocketDisconnect:
        pass
    except Exception:
        pass
    finally:
        sess.remove_peer(peer_id)
        await sess.broadcast({
            "type":    "peer_left",
            "peer_id": peer_id,
            "peers":   list(sess.peers.values()),
        })
        # Clean up empty sessions
        if not sess.peers:
            _sessions.pop(session_id, None)


async def _handle_collab_msg(sess: CollabSession, peer_id: str, msg: dict):
    mtype = msg.get("type", "")
    payload = msg.get("payload", {})

    if mtype == "pong":
        if peer_id in sess.peers:
            sess.peers[peer_id]["last_seen"] = time.time()
        return

    if mtype == "cursor":
        if peer_id in sess.peers:
            sess.peers[peer_id]["cursor"] = payload
            sess.peers[peer_id]["pane"]   = payload.get("pane", "chat")
        await sess.broadcast({"type": "cursor", "peer_id": peer_id, "payload": payload}, exclude=peer_id)

    elif mtype == "nav":
        if peer_id in sess.peers:
            sess.peers[peer_id]["pane"] = payload.get("pane", "")
        await sess.broadcast({"type": "nav", "peer_id": peer_id, "pane": payload.get("pane")}, exclude=peer_id)

    elif mtype == "chat":
        # Broadcast chat message to all peers
        await sess.broadcast({"type": "chat", "peer_id": peer_id,
                               "name": sess.peers.get(peer_id, {}).get("name", peer_id),
                               "message": str(payload.get("message", ""))[:2000]}, exclude=peer_id)

    elif mtype == "state_set":
        key   = str(payload.get("key", ""))[:64]
        value = payload.get("value")
        if key:
            sess.shared_state[key] = value
            await sess.broadcast({"type": "state_changed", "peer_id": peer_id,
                                   "key": key, "value": value}, exclude=peer_id)

    elif mtype == "file_edit":
        # Broadcast Monaco edit operations
        await sess.broadcast({"type": "file_edit", "peer_id": peer_id, "payload": payload}, exclude=peer_id)
