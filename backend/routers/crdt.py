"""
Agentic OS — Collaborative Editing (OT / CRDT) Router
Operational Transform for real-time multi-peer text editing.

Architecture:
  - Each document has a revision history (ops log)
  - Clients submit ops with their local revision number
  - Server transforms incoming op against any concurrent ops (OT)
  - Broadcasts transformed op to all peers via WebSocket
  - In-memory + SQLite persistence for durability

OT operation types:
  - retain(n)         — keep n characters unchanged
  - insert(str)       — insert text at current position
  - delete(n)         — delete n characters from current position
"""

from __future__ import annotations

import contextlib

import asyncio
import json
import logging
import time
import uuid
from pathlib import Path

from fastapi import APIRouter, Request, WebSocket, WebSocketDisconnect

router = APIRouter(prefix='/api/crdt', tags=['crdt'])
log = logging.getLogger('agentic.crdt')

ROOT = Path(__file__).resolve().parents[2]
DOCS_DIR = ROOT / 'workspaces' / 'collab_docs'
DOCS_DIR.mkdir(parents=True, exist_ok=True)

# ── DB schema ──────────────────────────────────────────────────────────────────
_SCHEMA = """
CREATE TABLE IF NOT EXISTS crdt_docs (
    id          TEXT PRIMARY KEY,
    title       TEXT,
    content     TEXT DEFAULT '',
    revision    INTEGER DEFAULT 0,
    created_at  TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    updated_at  TIMESTAMP DEFAULT CURRENT_TIMESTAMP
);
CREATE TABLE IF NOT EXISTS crdt_ops (
    id          INTEGER PRIMARY KEY AUTOINCREMENT,
    doc_id      TEXT NOT NULL,
    revision    INTEGER NOT NULL,
    peer_id     TEXT,
    peer_name   TEXT,
    op_json     TEXT NOT NULL,
    created_at  TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    FOREIGN KEY(doc_id) REFERENCES crdt_docs(id)
);
CREATE INDEX IF NOT EXISTS idx_crdt_ops_doc ON crdt_ops(doc_id, revision);
"""


def _ensure_schema():
    from ..services.memory_db import get_conn

    con = get_conn()
    try:
        con.executescript(_SCHEMA)
        con.commit()
    finally:
        con.close()


_ensure_schema()


# ── Pure OT logic ──────────────────────────────────────────────────────────────
def _apply_op(text: str, op: list) -> str:
    """Apply a list of OT operations to text. Returns new text."""
    result = []
    pos = 0
    for component in op:
        if isinstance(component, int) and component > 0:
            # retain(n)
            result.append(text[pos : pos + component])
            pos += component
        elif isinstance(component, str):
            # insert(str)
            result.append(component)
        elif isinstance(component, int) and component < 0:
            # delete(n)  — represented as negative integer
            pos += abs(component)
        # ignore 0 / unknown
    result.append(text[pos:])  # retain rest
    return ''.join(result)


def _op_length(op: list) -> tuple[int, int]:
    """Return (base_length_consumed, output_length_produced)."""
    base = 0
    out = 0
    for c in op:
        if isinstance(c, int) and c > 0:
            base += c
            out += c
        elif isinstance(c, str):
            out += len(c)
        elif isinstance(c, int) and c < 0:
            base += abs(c)
    return base, out


def _transform(op_a: list, op_b: list, side: str = 'left') -> tuple[list, list]:
    """
    OT transform: given ops A and B applied to the same base document,
    return (A', B') such that apply(apply(doc, A), B') == apply(apply(doc, B), A').
    Uses the classic 'left wins / right wins' tie-breaking.
    """
    a_prime: list = []
    b_prime: list = []

    i = j = 0
    a_idx = b_idx = 0  # position within current component
    ai = list(op_a)
    bi = list(op_b)

    def peek_a():
        """Execute or process peek a operation."""
        return ai[i] if i < len(ai) else None

    def peek_b():
        """Execute or process peek b operation."""
        return bi[j] if j < len(bi) else None

    while i < len(ai) or j < len(bi):
        pa = peek_a()
        pb = peek_b()

        # Both exhausted — done
        if pa is None and pb is None:
            break

        # A = insert
        if isinstance(pa, str):
            a_prime.append(pa)
            b_prime.append(len(pa))  # retain over A's insert
            i += 1
            continue

        # B = insert
        if isinstance(pb, str):
            if side == 'left':
                a_prime.append(len(pb))
            b_prime.append(pb)
            if side == 'right':
                a_prime.append(len(pb))
            j += 1
            continue

        # Both retain
        if isinstance(pa, int) and pa > 0 and isinstance(pb, int) and pb > 0:
            n = min(pa, pb)
            a_prime.append(n)
            b_prime.append(n)
            ai[i] = pa - n
            bi[j] = pb - n
            if ai[i] == 0:
                i += 1
            if bi[j] == 0:
                j += 1
            continue

        # A = delete, B = retain
        if isinstance(pa, int) and pa < 0 and isinstance(pb, int) and pb > 0:
            n = min(abs(pa), pb)
            a_prime.append(-n)
            ai[i] = pa + n
            bi[j] = pb - n
            if ai[i] == 0:
                i += 1
            if bi[j] == 0:
                j += 1
            continue

        # A = retain, B = delete
        if isinstance(pa, int) and pa > 0 and isinstance(pb, int) and pb < 0:
            n = min(pa, abs(pb))
            b_prime.append(-n)
            ai[i] = pa - n
            bi[j] = pb + n
            if ai[i] == 0:
                i += 1
            if bi[j] == 0:
                j += 1
            continue

        # Both delete same range
        if isinstance(pa, int) and pa < 0 and isinstance(pb, int) and pb < 0:
            n = min(abs(pa), abs(pb))
            ai[i] = pa + n
            bi[j] = pb + n
            if ai[i] == 0:
                i += 1
            if bi[j] == 0:
                j += 1
            continue

        # Fallback: skip
        i += 1
        j += 1

    return _compact(a_prime), _compact(b_prime)


def _compose(op_a: list, op_b: list) -> list:
    """Compose two sequential ops into one equivalent op."""
    result: list = []
    i = j = 0
    ai = list(op_a)
    bi = list(op_b)

    while i < len(ai) or j < len(bi):
        pa = ai[i] if i < len(ai) else None
        pb = bi[j] if j < len(bi) else None

        if isinstance(pb, str):  # B insert
            result.append(pb)
            j += 1
            continue
        if isinstance(pa, int) and pa < 0:  # A delete
            result.append(pa)
            i += 1
            continue
        if pa is None:
            result.append(pb)
            j += 1
            continue
        if pb is None:
            result.append(pa)
            i += 1
            continue

        if isinstance(pa, int) and pa > 0 and isinstance(pb, int) and pb > 0:
            n = min(pa, pb)
            result.append(n)
            ai[i] = pa - n
            bi[j] = pb - n
            if ai[i] == 0:
                i += 1
            if bi[j] == 0:
                j += 1
        elif isinstance(pa, int) and pa > 0 and isinstance(pb, int) and pb < 0:
            n = min(pa, abs(pb))
            result.append(-n)
            ai[i] = pa - n
            bi[j] = pb + n
            if ai[i] == 0:
                i += 1
            if bi[j] == 0:
                j += 1
        elif isinstance(pa, str) and isinstance(pb, int) and pb > 0:
            n = min(len(pa), pb)
            result.append(pa[:n])
            ai[i] = pa[n:] if len(pa) > n else None
            bi[j] = pb - n
            if not ai[i]:
                i += 1
            if bi[j] == 0:
                j += 1
        else:
            i += 1
            j += 1

    return _compact(result)


def _compact(op: list) -> list:
    """Merge adjacent same-type components."""
    result: list = []
    for c in op:
        if not c and not isinstance(c, str):
            continue  # skip zero-retains
        if (
            result
            and isinstance(result[-1], type(c))
            and not isinstance(c, str)
            or result
            and isinstance(result[-1], str)
            and isinstance(c, str)
        ):
            result[-1] += c
        else:
            result.append(c)
    return [c for c in result if c != 0 and c != '']


# ── In-memory document + peer state ──────────────────────────────────────────
class CRDTDoc:
    """Data structure or service class representing CRDTDoc."""

    def __init__(self, doc_id: str, title: str = '', content: str = ''):
        self.id = doc_id
        self.title = title
        self.content = content
        self.revision = 0
        self.ops_log: list[dict] = []  # [{revision, peer_id, op}]
        self.peers: dict[str, dict] = {}
        self.connections: dict[str, WebSocket] = {}
        self.undo_stacks: dict[str, list] = {}  # peer_id → [op, ...]
        self.redo_stacks: dict[str, list] = {}

    async def apply_and_broadcast(self, peer_id: str, peer_name: str, client_rev: int, op: list) -> dict:
        """
        Transform op against all ops since client_rev, apply, broadcast.
        Returns the server-side applied op and new revision.
        """
        concurrent = [e['op'] for e in self.ops_log if e['revision'] > client_rev]

        # Transform against each concurrent op
        transformed_op = op
        for concurrent_op in concurrent:
            transformed_op, _ = _transform(transformed_op, concurrent_op, side='left')

        # Apply
        old_content = self.content
        self.content = _apply_op(self.content, transformed_op)
        self.revision += 1

        # Store
        entry = {
            'revision': self.revision,
            'peer_id': peer_id,
            'peer_name': peer_name,
            'op': transformed_op,
            'ts': time.time(),
        }
        self.ops_log.append(entry)
        if len(self.ops_log) > 5000:
            self.ops_log = self.ops_log[-5000:]

        # Track undo
        self.undo_stacks.setdefault(peer_id, []).append(
            {'op': self._invert(transformed_op, old_content), 'rev': self.revision}
        )
        if len(self.undo_stacks[peer_id]) > 100:
            self.undo_stacks[peer_id].pop(0)
        self.redo_stacks[peer_id] = []  # reset redo on new edit

        # Persist to DB
        self._persist_op(entry)
        self._persist_doc()

        # Broadcast
        event = {
            'type': 'op',
            'revision': self.revision,
            'peer_id': peer_id,
            'peer_name': peer_name,
            'op': transformed_op,
        }
        await self.broadcast(event, exclude=peer_id)

        return {'revision': self.revision, 'op': transformed_op}

    def _invert(self, op: list, base_text: str) -> list:
        """Invert an op for undo (approximate)."""
        inv: list = []
        pos = 0
        for c in op:
            if isinstance(c, int) and c > 0:
                inv.append(c)
                pos += c
            elif isinstance(c, str):
                inv.append(-len(c))  # delete what was inserted
            elif isinstance(c, int) and c < 0:
                inv.append(base_text[pos : pos + abs(c)])  # reinsert deleted
                pos += abs(c)
        return _compact(inv)

    async def undo(self, peer_id: str) -> dict | None:
        """Execute or process undo operation."""
        stack = self.undo_stacks.get(peer_id, [])
        if not stack:
            return None
        entry = stack.pop()
        return await self.apply_and_broadcast(peer_id, f'{peer_id}(undo)', self.revision, entry['op'])

    async def redo(self, peer_id: str) -> dict | None:
        """Execute or process redo operation."""
        stack = self.redo_stacks.get(peer_id, [])
        if not stack:
            return None
        entry = stack.pop()
        return await self.apply_and_broadcast(peer_id, f'{peer_id}(redo)', self.revision, entry['op'])

    def _persist_op(self, entry: dict):
        from ..services.memory_db import get_conn

        try:
            con = get_conn()
            try:
                con.execute(
                    'INSERT INTO crdt_ops(doc_id,revision,peer_id,peer_name,op_json) VALUES (?,?,?,?,?)',
                    (self.id, entry['revision'], entry['peer_id'], entry['peer_name'], json.dumps(entry['op'])),
                )
                con.commit()
            finally:
                con.close()
        except Exception as ex:
            log.warning('crdt op persist failed: %s', ex)

    def _persist_doc(self):
        from ..services.memory_db import get_conn

        try:
            con = get_conn()
            try:
                con.execute(
                    """INSERT INTO crdt_docs(id,title,content,revision,updated_at)
                       VALUES (?,?,?,?,CURRENT_TIMESTAMP)
                       ON CONFLICT(id) DO UPDATE SET
                         content=excluded.content, revision=excluded.revision,
                         updated_at=CURRENT_TIMESTAMP""",
                    (self.id, self.title, self.content, self.revision),
                )
                con.commit()
            finally:
                con.close()
        except Exception as ex:
            log.warning('crdt doc persist failed: %s', ex)

    async def broadcast(self, event: dict, exclude: str = ''):
        """Execute or process broadcast operation."""
        dead = []
        for pid, ws in self.connections.items():
            if pid == exclude:
                continue
            try:
                await ws.send_text(json.dumps(event, default=str))
            except (KeyError, TypeError, ValueError, json.JSONDecodeError, OSError, AttributeError, RuntimeError):
                dead.append(pid)
        for pid in dead:
            self.peers.pop(pid, None)
            self.connections.pop(pid, None)

    def snapshot(self) -> dict:
        """Execute or process snapshot operation."""
        return {
            'id': self.id,
            'title': self.title,
            'content': self.content,
            'revision': self.revision,
            'peers': list(self.peers.values()),
        }

    def get_ops_since(self, since_rev: int) -> list[dict]:
        """Retrieve and return get ops since."""
        return [e for e in self.ops_log if e['revision'] > since_rev]


_docs: dict[str, CRDTDoc] = {}

PEER_COLORS = ['#5b8af8', '#9d74f5', '#4cc98a', '#f0c060', '#f06080', '#38c5d8', '#f08850', '#c084fc']


def _get_doc(doc_id: str) -> CRDTDoc:
    if doc_id in _docs:
        return _docs[doc_id]
    # Load from DB
    from ..services.memory_db import get_conn

    con = get_conn()
    try:
        row = con.execute('SELECT * FROM crdt_docs WHERE id=?', (doc_id,)).fetchone()
        ops = con.execute(
            'SELECT revision,peer_id,peer_name,op_json FROM crdt_ops WHERE doc_id=? ORDER BY revision', (doc_id,)
        ).fetchall()
    finally:
        con.close()
    if row:
        doc = CRDTDoc(doc_id, row['title'] or '', row['content'] or '')
        doc.revision = row['revision'] or 0
        doc.ops_log = [
            {
                'revision': r['revision'],
                'peer_id': r['peer_id'],
                'peer_name': r['peer_name'],
                'op': json.loads(r['op_json']),
            }
            for r in ops
        ]
    else:
        doc = CRDTDoc(doc_id)
    _docs[doc_id] = doc
    return doc


# ── REST endpoints ─────────────────────────────────────────────────────────────
@router.get('/docs')
def list_docs():
    """Retrieve and return list docs."""
    from ..services.memory_db import get_conn

    con = get_conn()
    try:
        rows = con.execute(
            'SELECT id,title,revision,length(content) as size,updated_at FROM crdt_docs ORDER BY updated_at DESC LIMIT 100'
        ).fetchall()
    finally:
        con.close()
    return {'docs': [dict(r) for r in rows], 'count': len(rows)}


@router.post('/docs')
async def create_doc(req: Request):
    """Create and initialize a new doc."""
    try:
        body = await req.json()
    except (json.JSONDecodeError, TypeError, ValueError):
        body = {}
    doc_id = body.get('id') or f'doc_{uuid.uuid4().hex[:8]}'
    title = (body.get('title') or 'Untitled Document')[:120]
    content = body.get('content') or ''
    doc = CRDTDoc(doc_id, title, content)
    _docs[doc_id] = doc
    doc._persist_doc()
    return {'ok': True, 'doc': doc.snapshot()}


@router.get('/docs/{doc_id}')
def get_doc(doc_id: str):
    """Retrieve and return get doc."""
    doc = _get_doc(doc_id)
    return doc.snapshot()


@router.delete('/docs/{doc_id}')
def delete_doc(doc_id: str):
    """Delete or remove specified doc."""
    _docs.pop(doc_id, None)
    from ..services.memory_db import get_conn

    con = get_conn()
    try:
        con.execute('DELETE FROM crdt_ops WHERE doc_id=?', (doc_id,))
        con.execute('DELETE FROM crdt_docs WHERE id=?', (doc_id,))
        con.commit()
    finally:
        con.close()
    return {'ok': True}


@router.get('/docs/{doc_id}/ops')
def get_ops(doc_id: str, since: int = 0):
    """Retrieve and return get ops."""
    doc = _get_doc(doc_id)
    return {'ops': doc.get_ops_since(since), 'revision': doc.revision}


@router.post('/docs/{doc_id}/op')
async def submit_op(doc_id: str, req: Request):
    """Submit a single operation via HTTP (alternative to WebSocket)."""
    try:
        body = await req.json()
    except (json.JSONDecodeError, TypeError, ValueError):
        body = {}
    op = body.get('op', [])
    client_rev = int(body.get('revision', 0))
    peer_id = body.get('peer_id', 'http')
    peer_name = body.get('peer_name', 'API')

    if not op:
        return {'ok': False, 'error': 'op required'}

    doc = _get_doc(doc_id)
    result = await doc.apply_and_broadcast(peer_id, peer_name, client_rev, op)
    return {'ok': True, **result, 'content_preview': doc.content[:200]}


@router.get('/docs/{doc_id}/history')
def get_history(doc_id: str, limit: int = 100):
    """Retrieve and return get history."""
    from ..services.memory_db import get_conn

    con = get_conn()
    try:
        rows = con.execute(
            'SELECT revision,peer_id,peer_name,op_json,created_at FROM crdt_ops WHERE doc_id=? ORDER BY revision DESC LIMIT ?',
            (doc_id, min(limit, 500)),
        ).fetchall()
    finally:
        con.close()
    return {
        'history': [{**dict(r), 'op': json.loads(r['op_json'])} for r in rows],
        'count': len(rows),
    }


@router.post('/docs/{doc_id}/snapshot')
async def create_snapshot(doc_id: str):
    """Save current doc content as a file version snapshot."""
    doc = _get_doc(doc_id)
    snap_path = DOCS_DIR / f'{doc_id}_rev{doc.revision}.txt'
    snap_path.write_text(doc.content, encoding='utf-8')
    return {'ok': True, 'revision': doc.revision, 'path': str(snap_path)}


@router.post('/docs/{doc_id}/restore/{revision}')
async def restore_revision(doc_id: str, revision: int):
    """Restore document content to a specific revision by replaying ops."""
    from ..services.memory_db import get_conn

    con = get_conn()
    try:
        ops = con.execute(
            'SELECT op_json FROM crdt_ops WHERE doc_id=? AND revision<=? ORDER BY revision', (doc_id, revision)
        ).fetchall()
    finally:
        con.close()

    content = ''
    for row in ops:
        op = json.loads(row['op_json'])
        content = _apply_op(content, op)

    doc = _get_doc(doc_id)
    old = doc.content
    doc.content = content
    doc._persist_doc()
    return {'ok': True, 'restored_revision': revision, 'content': content[:500]}


# ── OT helpers endpoint ────────────────────────────────────────────────────────
@router.post('/transform')
async def transform_ops(req: Request):
    """Test the OT transform function with two ops."""
    try:
        body = await req.json()
    except (json.JSONDecodeError, TypeError, ValueError):
        body = {}
    op_a = body.get('op_a', [])
    op_b = body.get('op_b', [])
    text = body.get('text', '')
    a_prime, b_prime = _transform(op_a, op_b, side='left')
    # Verify convergence
    text_ab = _apply_op(_apply_op(text, op_a), b_prime)
    text_ba = _apply_op(_apply_op(text, op_b), a_prime)
    return {
        'a_prime': a_prime,
        'b_prime': b_prime,
        'converges': text_ab == text_ba,
        'result': text_ab,
    }


# ── WebSocket endpoint (real OT collaboration) ────────────────────────────────
@router.websocket('/docs/{doc_id}/ws')
async def collab_ws(ws: WebSocket, doc_id: str):
    """
    WebSocket for real-time OT collaborative editing.

    Messages client → server:
      {type:"join", name:"Alice"}
      {type:"op",   op:[...], revision:N}
      {type:"undo"}
      {type:"redo"}
      {type:"cursor", position:N, selection:{from,to}}
      {type:"presence", pane:"workflow", status:"active"}

    Messages server → client:
      {type:"init",   doc:{id,title,content,revision,peers}}
      {type:"op",     op:[...], revision:N, peer_id, peer_name}
      {type:"cursor", peer_id, position, selection}
      {type:"peer_joined", peer_id, name, color}
      {type:"peer_left",   peer_id}
      {type:"ack",    revision:N}
      {type:"ping"}
    """
    await ws.accept()

    peer_id = uuid.uuid4().hex[:8]
    doc = _get_doc(doc_id)
    peer_idx = len(doc.peers) % len(PEER_COLORS)
    color = PEER_COLORS[peer_idx]

    try:
        # Wait for join
        raw = await asyncio.wait_for(ws.receive_text(), timeout=8.0)
        join = json.loads(raw)
        name = join.get('name', f'Peer_{peer_id[:4]}')

        doc.peers[peer_id] = {
            'id': peer_id,
            'name': name,
            'color': color,
            'position': 0,
            'selection': None,
            'last_seen': time.time(),
        }
        doc.connections[peer_id] = ws

        # Send full document state
        await ws.send_text(
            json.dumps(
                {
                    'type': 'init',
                    'peer_id': peer_id,
                    'color': color,
                    'doc': doc.snapshot(),
                }
            )
        )

        # Announce to others
        await doc.broadcast(
            {
                'type': 'peer_joined',
                'peer_id': peer_id,
                'name': name,
                'color': color,
                'peers': list(doc.peers.values()),
            },
            exclude=peer_id,
        )

        # Message loop
        while True:
            try:
                raw = await asyncio.wait_for(ws.receive_text(), timeout=30.0)
                msg = json.loads(raw)
                mtype = msg.get('type', '')

                if mtype == 'op':
                    op = msg.get('op', [])
                    rev = int(msg.get('revision', doc.revision))
                    if not op:
                        continue
                    result = await doc.apply_and_broadcast(peer_id, name, rev, op)
                    await ws.send_text(json.dumps({'type': 'ack', 'revision': result['revision']}))

                elif mtype == 'undo':
                    result = await doc.undo(peer_id)
                    if result:
                        await ws.send_text(json.dumps({'type': 'ack', 'revision': result['revision']}))
                    else:
                        await ws.send_text(json.dumps({'type': 'ack', 'nothing': True}))

                elif mtype == 'redo':
                    result = await doc.redo(peer_id)
                    if result:
                        await ws.send_text(json.dumps({'type': 'ack', 'revision': result['revision']}))

                elif mtype == 'cursor':
                    if peer_id in doc.peers:
                        doc.peers[peer_id]['position'] = msg.get('position', 0)
                        doc.peers[peer_id]['selection'] = msg.get('selection')
                    await doc.broadcast(
                        {
                            'type': 'cursor',
                            'peer_id': peer_id,
                            'name': name,
                            'color': color,
                            'position': msg.get('position', 0),
                            'selection': msg.get('selection'),
                        },
                        exclude=peer_id,
                    )

                elif mtype == 'presence':
                    if peer_id in doc.peers:
                        doc.peers[peer_id]['last_seen'] = time.time()
                        doc.peers[peer_id]['status'] = msg.get('status', 'active')
                    await doc.broadcast(
                        {
                            'type': 'presence',
                            'peer_id': peer_id,
                            'status': msg.get('status', 'active'),
                            'pane': msg.get('pane', ''),
                        },
                        exclude=peer_id,
                    )

                elif mtype == 'pong':
                    if peer_id in doc.peers:
                        doc.peers[peer_id]['last_seen'] = time.time()

                elif mtype == 'chat':
                    await doc.broadcast(
                        {
                            'type': 'chat',
                            'peer_id': peer_id,
                            'name': name,
                            'message': str(msg.get('message', ''))[:2000],
                        },
                        exclude=peer_id,
                    )

            except asyncio.TimeoutError:
                await ws.send_text(json.dumps({'type': 'ping'}))
            except WebSocketDisconnect:
                break
            except Exception as ex:
                log.warning('crdt ws error: %s', ex)

    except (WebSocketDisconnect, asyncio.TimeoutError):
        pass
    except Exception as ex:
        log.error('crdt ws outer error: %s', ex)
    finally:
        doc.peers.pop(peer_id, None)
        doc.connections.pop(peer_id, None)
        await doc.broadcast(
            {
                'type': 'peer_left',
                'peer_id': peer_id,
                'peers': list(doc.peers.values()),
            }
        )
        # Persist doc on disconnect
        if doc.content:
            doc._persist_doc()
