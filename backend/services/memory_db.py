"""
Agentic OS — Memory Service
Hybrid: SQLite FTS5 (always available) + Qdrant vectors (optional).
Falls back gracefully if Qdrant is not running.
"""

from __future__ import annotations
from typing import Optional, Union, Any, Dict, List

import contextlib
import json
import logging
import sqlite3
from pathlib import Path

log = logging.getLogger('agentic.memory')

from backend.config import get_data_dir
ROOT = get_data_dir()
import os
_env_data_dir = os.environ.get('AGENTIC_OS_DATA_DIR')
MEMORY_DIR = Path(_env_data_dir) / 'memory' if _env_data_dir else (ROOT / 'memory')
MEMORY_DIR.mkdir(parents=True, exist_ok=True)
DB_PATH = MEMORY_DIR / 'agentic.db'


# ── DB helpers ─────────────────────────────────────────────────────────────────
def get_conn() -> sqlite3.Connection:
    """Retrieve and return get conn."""
    DB_PATH.parent.mkdir(parents=True, exist_ok=True)
    con = sqlite3.connect(DB_PATH, check_same_thread=False, timeout=10)
    con.row_factory = sqlite3.Row
    con.execute('PRAGMA journal_mode=WAL')
    con.execute('PRAGMA foreign_keys=ON')
    con.execute('PRAGMA busy_timeout=10000')  # wait up to 10s on lock
    con.execute('PRAGMA synchronous=NORMAL')  # faster writes, still safe in WAL
    return con


def ensure_schema():
    """Execute or process ensure schema operation."""
    con = get_conn()
    try:
        con.executescript("""
    CREATE TABLE IF NOT EXISTS memory (
        id INTEGER PRIMARY KEY,
        source TEXT,
        content TEXT,
        tags TEXT,
        embedding_json TEXT,
        created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
    );
    CREATE VIRTUAL TABLE IF NOT EXISTS memory_fts
        USING fts5(content, tags, content='memory', content_rowid='id');
    CREATE TABLE IF NOT EXISTS goals (
        id INTEGER PRIMARY KEY,
        title TEXT, layer TEXT,
        progress INTEGER DEFAULT 0,
        status TEXT DEFAULT 'active',
        created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
    );
    CREATE TABLE IF NOT EXISTS chat_log (
        id INTEGER PRIMARY KEY,
        session_id TEXT,
        agent TEXT, role TEXT, message TEXT,
        tokens INTEGER DEFAULT 0, cost REAL DEFAULT 0,
        model TEXT DEFAULT '',
        created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
    );
    CREATE TABLE IF NOT EXISTS tasks (
        id INTEGER PRIMARY KEY,
        title TEXT,
        status TEXT DEFAULT 'todo',
        priority TEXT DEFAULT 'medium',
        agent TEXT,
        layer TEXT DEFAULT 'Tasks',
        description TEXT DEFAULT '',
        sort_order INTEGER DEFAULT 0,
        run_id TEXT,
        updated_at TIMESTAMP,
        created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
    );
    CREATE TABLE IF NOT EXISTS audit (
        id INTEGER PRIMARY KEY,
        action TEXT, detail TEXT,
        created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
    );
    CREATE TABLE IF NOT EXISTS file_versions (
        id INTEGER PRIMARY KEY,
        path TEXT, content TEXT,
        author TEXT DEFAULT 'builder',
        message TEXT,
        created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
    );
    CREATE TABLE IF NOT EXISTS e2e_traces (
        id INTEGER PRIMARY KEY,
        run_id TEXT, target TEXT,
        step_no INTEGER, step_name TEXT, status TEXT,
        screenshot_b64 TEXT, dom_snapshot TEXT, console TEXT, network_json TEXT,
        duration_ms INTEGER,
        created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
    );
    CREATE TABLE IF NOT EXISTS agents (
        id TEXT PRIMARY KEY,
        name TEXT NOT NULL,
        role TEXT DEFAULT '',
        model TEXT DEFAULT '',
        provider TEXT DEFAULT 'openrouter',
        system_prompt TEXT DEFAULT '',
        color TEXT DEFAULT '#7aa2f7',
        avatar TEXT DEFAULT '🤖',
        status TEXT DEFAULT 'idle',
        enabled INTEGER DEFAULT 1,
        created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
        updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
    );
    CREATE TABLE IF NOT EXISTS swarm_history (
        id INTEGER PRIMARY KEY,
        run_id TEXT,
        prompt TEXT,
        agents TEXT,
        strategy TEXT,
        winner TEXT,
        winner_output TEXT,
        judge_reason TEXT,
        total_latency_ms INTEGER,
        total_tokens INTEGER,
        created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
    );
    CREATE TABLE IF NOT EXISTS secrets (
        id INTEGER PRIMARY KEY,
        key TEXT UNIQUE NOT NULL,
        value_enc TEXT NOT NULL,
        scope TEXT DEFAULT 'global',
        agent TEXT DEFAULT '',
        fingerprint TEXT,
        length INTEGER,
        updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
    );
    """)
        try:
            con.execute('ALTER TABLE chat_log ADD COLUMN model TEXT DEFAULT ""')
        except Exception:
            pass
        con.commit()
    finally:
        con.close()


# ── Memory CRUD ────────────────────────────────────────────────────────────────
def memory_add(source: str, content: str, tags: str = '', embedding:Optional[ list] = None) -> int:
    """Execute or process memory add operation."""
    con = get_conn()
    try:
        emb_json = json.dumps(embedding) if embedding else None
        cur = con.execute(
            'INSERT INTO memory(source, content, tags, embedding_json) VALUES (?,?,?,?)',
            (source, content, tags, emb_json),
        )
        mid = cur.lastrowid
        # update FTS
        with contextlib.suppress(sqlite3.Error):
            con.execute('INSERT INTO memory_fts(rowid, content, tags) VALUES (?,?,?)', (mid, content, tags))
        con.execute("INSERT INTO audit(action, detail) VALUES ('memory_add', ?)", (f'{source}: {content[:80]}',))
        con.commit()
    finally:
        con.close()
    return mid


def memory_search_fts(q: str, limit: int = 20) -> list[dict]:
    """Execute or process memory search fts operation."""
    con = get_conn()
    try:
        rows = con.execute(
            """SELECT m.id, m.source, m.content, m.tags, m.created_at,
                      snippet(memory_fts, 0, '<b>', '</b>', '…', 32) as snippet
               FROM memory_fts
               JOIN memory m ON m.id = memory_fts.rowid
               WHERE memory_fts MATCH ?
               ORDER BY rank LIMIT ?""",
            (q, limit),
        ).fetchall()
        return [dict(r) for r in rows]
    except Exception as e:
        log.warning('FTS search error: %s', e)
        return []
    finally:
        con.close()


def memory_list(limit: int = 500, offset: int = 0, source: str = '') -> list[dict]:
    """Execute or process memory list operation."""
    con = get_conn()
    try:
        if source:
            rows = con.execute(
                'SELECT id, source, content, tags, created_at FROM memory WHERE source=? ORDER BY id DESC LIMIT ? OFFSET ?',
                (source, limit, offset),
            ).fetchall()
        else:
            rows = con.execute(
                'SELECT id, source, content, tags, created_at FROM memory ORDER BY id DESC LIMIT ? OFFSET ?',
                (limit, offset),
            ).fetchall()
        return [dict(r) for r in rows]
    finally:
        con.close()


def memory_stats() -> dict:
    """Execute or process memory stats operation."""
    con = get_conn()
    try:
        total = con.execute('SELECT COUNT(*) FROM memory').fetchone()[0]
        sources = con.execute('SELECT source, COUNT(*) as cnt FROM memory GROUP BY source ORDER BY cnt DESC').fetchall()
        vec_count = con.execute('SELECT COUNT(*) FROM memory WHERE embedding_json IS NOT NULL').fetchone()[0]
        return {
            'sqlite_memories': total,
            'total': total,  # alias for consistency with other endpoints
            'count': total,  # another alias
            'vectors_sqlite': vec_count,
            'sources': [dict(r) for r in sources],
            'status': 'active',
            'engine': 'sqlite-fts5 + in-db vectors',
        }
    finally:
        con.close()


def memory_galaxy_graph(limit: int = 200) -> dict:
    """Execute or process memory galaxy graph operation."""
    con = get_conn()
    try:
        rows = con.execute(
            'SELECT id, source, content, tags, created_at FROM memory ORDER BY id DESC LIMIT ?', (limit,)
        ).fetchall()
    finally:
        con.close()

    nodes, links = [], []
    source_map: dict[str, int] = {}

    for r in rows:
        d = dict(r)
        label = d['content'][:60].replace('\n', ' ')
        val = max(3, min(20, len(d['content']) // 40))
        nodes.append(
            {
                'id': d['id'],
                'mem_id': d['id'],
                'label': label,
                'source': d['source'] or 'unknown',
                'tags': d['tags'] or '',
                'val': val,
                'created_at': d['created_at'],
            }
        )
        # link nodes by shared source
        src = d['source']
        if src in source_map:
            links.append({'source': source_map[src], 'target': d['id']})
        source_map[src] = d['id']

    return {
        'nodes': nodes,
        'links': links,
        'total_memories': len(nodes),
        'sources': list(set(n['source'] for n in nodes)),
    }


# ── Agents CRUD ────────────────────────────────────────────────────────────────
DEFAULT_AGENTS = [
    {
        'id': 'orchestrator',
        'name': 'Orchestrator',
        'role': 'Fan-out • Judge • Merge',
        'model': 'claude',
        'provider': 'openrouter',
        'color': '#ff9e64',
        'avatar': '🌀',
        'status': 'active',
        'system_prompt': 'You are the Orchestrator — a master coordinator that breaks complex tasks into parallel sub-tasks, assigns them to specialized agents, judges their outputs, and synthesizes the best result. Always decompose problems before delegating.',
    },
    {
        'id': 'brain',
        'name': 'Brain',
        'role': 'Deep reasoning & planning',
        'model': 'claude',
        'provider': 'openrouter',
        'color': '#d97757',
        'avatar': '🧠',
        'status': 'idle',
        'system_prompt': 'You are Brain — a deep reasoning and strategic planning agent. You excel at long-form analysis, research synthesis, system design, and architectural decisions. Think step by step, consider edge cases, and provide thorough explanations.',
    },
    {
        'id': 'builder',
        'name': 'Builder',
        'role': 'Code • Monaco • Live preview',
        'model': 'hermes',
        'provider': 'openrouter',
        'color': '#7aa2f7',
        'avatar': '⚡',
        'status': 'idle',
        'system_prompt': 'You are Builder — an expert software engineer specializing in clean, production-ready code. You write TypeScript, Python, React, FastAPI, and SQL. Always include type hints, error handling, and brief docstrings. Output runnable code, not pseudocode.',
    },
    {
        'id': 'researcher',
        'name': 'Researcher',
        'role': 'Market • RAG • Deep search',
        'model': 'gemini',
        'provider': 'openrouter',
        'color': '#7dd3a7',
        'avatar': '🔭',
        'status': 'idle',
        'system_prompt': 'You are Researcher — a meticulous information gatherer and analyst. You synthesize research from multiple sources, identify trends, compare options objectively, and present findings with citations. Always distinguish facts from opinions and flag uncertainty.',
    },
    {
        'id': 'reviewer',
        'name': 'Reviewer',
        'role': 'Security • Perf • Tests',
        'model': 'gpt4o',
        'provider': 'openrouter',
        'color': '#e06b6b',
        'avatar': '🔨',
        'status': 'idle',
        'system_prompt': "You are Reviewer — a senior code reviewer and QA engineer. You review code for bugs, security vulnerabilities (OWASP Top 10), performance issues, and missing tests. Be specific about what's wrong, why it matters, and how to fix it.",
    },
    {
        'id': 'creative',
        'name': 'Creative',
        'role': 'Multi-modal • Images • Video',
        'model': 'grok',
        'provider': 'openrouter',
        'color': '#f7768e',
        'avatar': '🎨',
        'status': 'idle',
        'system_prompt': 'You are Creative — a multi-modal creative director. You craft compelling copy, design UI layouts, generate image prompts, and develop brand voices. Prioritize originality, visual clarity, and emotional resonance in all outputs.',
    },
    {
        'id': 'memory',
        'name': 'Memory',
        'role': 'Qdrant vector RAG',
        'model': 'llama',
        'provider': 'openrouter',
        'color': '#c084fc',
        'avatar': '🌌',
        'status': 'active',
        'system_prompt': "You are Memory — a knowledge retrieval specialist. You search the vector database for relevant context, synthesize stored knowledge, and answer questions grounded in the user's own data. Always cite which memories informed your response.",
    },
    {
        'id': 'orchestrator',
        'name': 'Swarm Orchestrator',
        'role': 'State Machine • DAG Pipeline Driver',
        'model': 'claude-opus',
        'provider': 'openrouter',
        'color': '#a855f7',
        'avatar': '✨',
        'status': 'idle',
        'system_prompt': 'You are Swarm Orchestrator — the state machine and DAG pipeline driver for Strick Tech Agentic OS. You decompose complex engineering tasks into modular sub-agent assignments, track execution state, verify behavioral rules (.agenticrules), and enforce zero-defect quality standards before shipping.',
    },
    {
        'id': 'visual_tester',
        'name': 'Visual UI Tester',
        'role': 'Figma Fidelity • Viewport QA',
        'model': 'gemini',
        'provider': 'openrouter',
        'color': '#ec4899',
        'avatar': '❖',
        'status': 'idle',
        'system_prompt': 'You are Visual UI Tester — a specialist pixel-perfect QA engineer. You compare live multi-preview viewports (desktop, tablet, mobile) against design guidelines and geometric UI/UX standards, checking for layout shifts, contrast WCAG AAA compliance, and visual hierarchy.',
    },
    {
        'id': 'functional_tester',
        'name': 'Functional Tester',
        'role': 'E2E Flows • API Verification',
        'model': 'gpt4o',
        'provider': 'openrouter',
        'color': '#3b82f6',
        'avatar': '◈',
        'status': 'idle',
        'system_prompt': 'You are Functional Tester — a dedicated automation and E2E test engineer. You verify backend REST endpoints, execute browser agent loops, and assert strict business logic constraints. Whenever a test fails, you generate actionable reproduction steps for the Coder/Builder.',
    },
    {
        'id': 'design_decomposer',
        'name': 'Design Decomposer',
        'role': 'Wireframe Scanner • Spec Architect',
        'model': 'claude',
        'provider': 'openrouter',
        'color': '#06b6d4',
        'avatar': '☷',
        'status': 'idle',
        'system_prompt': 'You are Design Decomposer — a UI/UX architect specializing in breaking down complex wireframes, user stories, and feature specs into clean, modular, reusable frontend components and backend schema definitions.',
    },
    {
        'id': 'test_creator',
        'name': 'Test Case Creator',
        'role': 'PyTest • Unit & Regression Architect',
        'model': 'hermes',
        'provider': 'openrouter',
        'color': '#10b981',
        'avatar': '⚗',
        'status': 'idle',
        'system_prompt': 'You are Test Case Creator — a PyTest and automated testing specialist. You inspect source code ASTs, identify edge cases and security boundaries, and write comprehensive, deterministic unit and regression test suites.',
    },
    {
        'id': 'local',
        'name': 'Local LLM',
        'role': 'Private • Ollama • Offline',
        'model': '',
        'provider': 'ollama',
        'color': '#e0af68',
        'avatar': '🏠',
        'status': 'idle',
        'system_prompt': "You are Local — a private, offline AI assistant running entirely on the user's machine. You prioritize privacy, work without internet access, and handle tasks that should never leave the local environment.",
    },
]


def agents_list() -> list[dict]:
    """Execute or process agents list operation."""
    con = get_conn()
    try:
        rows = con.execute('SELECT * FROM agents ORDER BY created_at').fetchall()
        agents = [dict(r) for r in rows]
    finally:
        con.close()
    if not agents or len(agents) < len(DEFAULT_AGENTS):
        agents_seed_defaults()
        if not agents:
            return agents_list()
        con2 = get_conn()
        try:
            return [dict(r) for r in con2.execute('SELECT * FROM agents ORDER BY created_at').fetchall()]
        finally:
            con2.close()
    return agents


def agents_seed_defaults():
    """Execute or process agents seed defaults operation."""
    con = get_conn()
    try:
        for a in DEFAULT_AGENTS:
            con.execute(
                """
                INSERT OR IGNORE INTO agents(id,name,role,model,provider,color,avatar,status,system_prompt)
                VALUES(:id,:name,:role,:model,:provider,:color,:avatar,:status,:system_prompt)
            """,
                {**a, 'system_prompt': a.get('system_prompt', '')},
            )
            # Also update existing agents that have empty system_prompt
            if a.get('system_prompt'):
                con.execute(
                    "UPDATE agents SET system_prompt=? WHERE id=? AND (system_prompt IS NULL OR system_prompt='')",
                    (a['system_prompt'], a['id']),
                )
        con.commit()
    finally:
        con.close()


def agent_upsert(data: dict) -> dict:
    """Execute or process agent upsert operation."""
    con = get_conn()
    try:
        existing = con.execute('SELECT id FROM agents WHERE id=?', (data['id'],)).fetchone()
        if existing:
            fields = ['name', 'role', 'model', 'provider', 'color', 'avatar', 'status', 'system_prompt', 'enabled']
            sets = ', '.join(f'{f}=?' for f in fields if f in data)
            vals = [data[f] for f in fields if f in data]
            if sets:
                con.execute(f'UPDATE agents SET {sets}, updated_at=CURRENT_TIMESTAMP WHERE id=?', vals + [data['id']])
        else:
            con.execute(
                """
                INSERT INTO agents(id,name,role,model,provider,color,avatar,status,system_prompt,enabled)
                VALUES(:id,:name,:role,:model,:provider,:color,:avatar,:status,:system_prompt,:enabled)
            """,
                {
                    'id': data['id'],
                    'name': data.get('name', data['id']),
                    'role': data.get('role', ''),
                    'model': data.get('model', ''),
                    'provider': data.get('provider', 'openrouter'),
                    'color': data.get('color', '#7aa2f7'),
                    'avatar': data.get('avatar', '🤖'),
                    'status': data.get('status', 'idle'),
                    'system_prompt': data.get('system_prompt', ''),
                    'enabled': data.get('enabled', 1),
                },
            )
        con.commit()
        row = con.execute('SELECT * FROM agents WHERE id=?', (data['id'],)).fetchone()
    finally:
        con.close()
    return dict(row) if row else {}


def agent_delete(agent_id: str) -> bool:
    """Execute or process agent delete operation."""
    con = get_conn()
    try:
        cur = con.execute('DELETE FROM agents WHERE id=?', (agent_id,))
        con.commit()
        return cur.rowcount > 0
    finally:
        con.close()


# ── Audit ──────────────────────────────────────────────────────────────────────
def audit_log(action: str, detail: str = ''):
    """Execute or process audit log operation."""
    import time as _time

    for _attempt in range(5):
        con = get_conn()
        try:
            con.execute('INSERT INTO audit(action, detail) VALUES (?,?)', (action, detail[:500]))
            con.commit()
            return
        except Exception as _e:
            if 'locked' in str(_e).lower() and _attempt < 4:
                _time.sleep(0.05 * (_attempt + 1))
            else:
                pass  # Non-critical audit write — don't crash caller on lock
        finally:
            con.close()


def audit_list(limit: int = 100) -> list[dict]:
    """Execute or process audit list operation."""
    con = get_conn()
    try:
        rows = con.execute(
            "SELECT action, detail, datetime(created_at,'localtime') as ts FROM audit ORDER BY id DESC LIMIT ?",
            (limit,),
        ).fetchall()
        return [dict(r) for r in rows]
    finally:
        con.close()


# ════════════════════════════════════════════════════════════════
#  SPRINT 14 — Qdrant Vector DB + sentence-transformers
#  Optional: gracefully degrades to FTS5 if unavailable
# ════════════════════════════════════════════════════════════════

import os as _os

# ── Optional: local embeddings (fastembed preferred, sentence-transformers fallback) ──
_ST_MODEL = None
_ST_AVAILABLE = False


def _load_st_model():
    global _ST_MODEL, _ST_AVAILABLE
    if _ST_AVAILABLE or _ST_MODEL:
        return True
    # Try fastembed first (lightweight, no torch required)
    try:
        from fastembed import TextEmbedding

        model_name = _os.getenv('ST_MODEL', 'BAAI/bge-small-en-v1.5')
        _ST_MODEL = TextEmbedding(model_name)
        _ST_AVAILABLE = True
        log.info('fastembed loaded: %s', model_name)
        return True
    except ImportError:
        pass
    except Exception as ex:
        log.warning('fastembed failed: %s', ex)
    # Fallback: sentence-transformers
    try:
        from sentence_transformers import SentenceTransformer

        model_name = _os.getenv('ST_MODEL', 'all-MiniLM-L6-v2')
        _ST_MODEL = SentenceTransformer(model_name)
        _ST_AVAILABLE = True
        log.info('sentence-transformers loaded: %s', model_name)
        return True
    except ImportError:
        log.debug('No embedding library installed — using SQLite FTS5 only')
        return False
    except Exception as ex:
        log.warning('sentence-transformers failed: %s', ex)
        return False


def embed_text(text: str) ->Optional[ list[float]]:
    """Embed text to a vector. Supports fastembed and sentence-transformers."""
    if not _load_st_model() or not _ST_MODEL:
        return None
    try:
        # fastembed returns a generator — convert differently
        from fastembed import TextEmbedding

        if isinstance(_ST_MODEL, TextEmbedding):
            vecs = list(_ST_MODEL.embed([text]))
            return [float(x) for x in vecs[0]]
        # sentence-transformers path
        vec = _ST_MODEL.encode(text, convert_to_numpy=True)
        return vec.tolist()
    except Exception as ex:
        log.warning('embed failed: %s', ex)
        return None


# ── Optional: Qdrant vector DB ────────────────────────────────────────────────
_QDRANT_CLIENT = None
_QDRANT_AVAILABLE = False


def _init_qdrant_inmemory():
    """Pre-initialize an in-memory Qdrant client as guaranteed fallback."""
    global _QDRANT_CLIENT, _QDRANT_AVAILABLE
    if _QDRANT_AVAILABLE:
        return
    with contextlib.suppress(Exception):
        from qdrant_client import QdrantClient as _QC
        from qdrant_client.models import Distance as _D
        from qdrant_client.models import VectorParams as _VP

        client = _QC(':memory:')
        client.create_collection(_QDRANT_COLLECTION, vectors_config=_VP(size=384, distance=_D.COSINE))
        _QDRANT_CLIENT = client
        _QDRANT_AVAILABLE = True


_QDRANT_COLLECTION = 'agentic_memory'


def _qdrant_client():
    global _QDRANT_CLIENT, _QDRANT_AVAILABLE
    if _QDRANT_AVAILABLE:
        return _QDRANT_CLIENT
    if _QDRANT_CLIENT is not None and not _QDRANT_AVAILABLE:
        # Don't return None — retry with in-memory if we haven't tried yet
        pass  # fall through to in-memory fallback below

    url = _os.getenv('QDRANT_URL', 'http://localhost:6333')
    key = _os.getenv('QDRANT_API_KEY', '')
    try:
        from qdrant_client import QdrantClient
        from qdrant_client.models import Distance, VectorParams

        kwargs: dict = {'url': url}
        if key:
            kwargs['api_key'] = key

        client = QdrantClient(**kwargs, timeout=3, check_compatibility=False)
        # Test connection
        client.get_collections()

        # Ensure collection exists
        cols = [c.name for c in client.get_collections().collections]
        if _QDRANT_COLLECTION not in cols:
            client.create_collection(
                collection_name=_QDRANT_COLLECTION,
                vectors_config=VectorParams(size=384, distance=Distance.COSINE),
            )

        _QDRANT_CLIENT = client
        _QDRANT_AVAILABLE = True
        log.info('Qdrant connected at %s, collection: %s', url, _QDRANT_COLLECTION)
        return _QDRANT_CLIENT
    except ImportError:
        log.debug('qdrant-client not installed (optional)')
        # Fallback: try in-memory Qdrant
        try:
            from qdrant_client import QdrantClient as _QC
            from qdrant_client.models import Distance as _D
            from qdrant_client.models import VectorParams as _VP

            client = _QC(':memory:')
            client.create_collection(_QDRANT_COLLECTION, vectors_config=_VP(size=384, distance=_D.COSINE))
            _QDRANT_CLIENT = client
            _QDRANT_AVAILABLE = True
            log.info('Qdrant in-memory mode active')
            return _QDRANT_CLIENT
        except Exception:
            return None
    except Exception as ex:
        log.debug('Qdrant remote unavailable (%s) — trying in-memory fallback', ex)
        # Auto-fallback to in-memory Qdrant if remote is down
        try:
            from qdrant_client import QdrantClient as _QC
            from qdrant_client.models import Distance as _D
            from qdrant_client.models import VectorParams as _VP

            client = _QC(':memory:')
            client.create_collection(_QDRANT_COLLECTION, vectors_config=_VP(size=384, distance=_D.COSINE))
            _QDRANT_CLIENT = client
            _QDRANT_AVAILABLE = True
            log.info('Qdrant in-memory fallback active')
            return _QDRANT_CLIENT
        except Exception as ex2:
            log.debug('Qdrant in-memory also failed: %s', ex2)
            return None


def qdrant_upsert(memory_id: int, content: str, metadata:Optional[ dict] = None):
    """Upsert a memory entry into Qdrant."""
    client = _qdrant_client()
    if not client:
        return False
    vec = embed_text(content)
    if not vec:
        return False
    try:
        from qdrant_client.models import PointStruct

        client.upsert(
            collection_name=_QDRANT_COLLECTION,
            points=[
                PointStruct(
                    id=memory_id,
                    vector=vec,
                    payload={**(metadata or {}), 'content': content[:1000]},
                )
            ],
        )
        return True
    except Exception as ex:
        log.warning('Qdrant upsert failed: %s', ex)
        return False


def qdrant_search(query: str, limit: int = 10) -> list[dict]:
    """Semantic search in Qdrant."""
    client = _qdrant_client()
    if not client:
        return []
    vec = embed_text(query)
    if not vec:
        return []
    try:
        # Support both old (.search) and new (.query_points) qdrant-client APIs
        try:
            resp = client.query_points(
                collection_name=_QDRANT_COLLECTION,
                query=vec,
                limit=limit,
                with_payload=True,
            )
            results = resp.points
        except AttributeError:
            results = client.search(
                collection_name=_QDRANT_COLLECTION,
                query_vector=vec,
                limit=limit,
                with_payload=True,
            )
        return [
            {
                'id': r.id,
                'score': round(r.score, 4),
                'content': r.payload.get('content', ''),
                'source': r.payload.get('source', ''),
                'tags': r.payload.get('tags', ''),
            }
            for r in results
        ]
    except Exception as ex:
        log.warning('Qdrant search failed: %s', ex)
        return []


def qdrant_delete(memory_id: int):
    """Delete a point from Qdrant."""
    client = _qdrant_client()
    if not client:
        return
    with contextlib.suppress(Exception):
        from qdrant_client.models import PointIdsList

        client.delete(
            collection_name=_QDRANT_COLLECTION,
            points_selector=PointIdsList(points=[memory_id]),
        )


def hybrid_search(query: str, limit: int = 20) -> list[dict]:
    """
    Hybrid search: Qdrant semantic search + SQLite FTS5.
    Merges and re-ranks results by score.
    If Qdrant unavailable, falls back to FTS5 only.
    """
    query = (query or '').strip()
    try:
        limit = min(100, max(1, int(limit)))
    except (TypeError, ValueError):
        limit = 20
    if not query:
        return []
    results: dict[int, dict] = {}

    # 1. Try Qdrant semantic search
    q_results = qdrant_search(query, limit=limit)
    for r in q_results:
        results[r['id']] = {**r, 'source_type': 'vector'}

    # 2. SQLite FTS5 search (always available)
    con = get_conn()
    try:
        fts_query = ' OR '.join(f'"{w}"' for w in query.split()[:8])
        rows = con.execute(
            'SELECT m.id, m.source, m.content, m.tags FROM memory m '
            'JOIN memory_fts ON memory_fts.rowid = m.id '
            'WHERE memory_fts MATCH ? ORDER BY rank LIMIT ?',
            (fts_query, limit),
        ).fetchall()
        for row in rows:
            rid = row['id']
            if rid not in results:
                results[rid] = {
                    'id': rid,
                    'score': 0.5,  # FTS5 default score
                    'content': row['content'],
                    'source': row['source'],
                    'tags': row['tags'],
                    'source_type': 'fts5',
                }
    except sqlite3.Error as e:
        log.debug('hybrid_search DB error: %s', e)
    finally:
        con.close()

    # Sort by score descending
    return sorted(results.values(), key=lambda x: x['score'], reverse=True)[:limit]


def memory_add_with_vector(source: str, content: str, tags: str = '', metadata:Optional[ dict] = None) -> int:
    """Add to SQLite + optionally embed and store in Qdrant."""
    # First embed (may be None)
    embedding = embed_text(content)

    # Store in SQLite
    mid = memory_add(source, content, tags, embedding)

    # Store in Qdrant if available
    if mid > 0:
        qdrant_upsert(mid, content, {'source': source, 'tags': tags, **(metadata or {})})

    return mid


def qdrant_status() -> dict:
    """Return Qdrant connection status."""
    client = _qdrant_client()
    if not client:
        return {
            'available': False,
            'url': _os.getenv('QDRANT_URL', 'http://localhost:6333'),
            'st_available': _ST_AVAILABLE,
            'fallback': 'SQLite FTS5',
        }
    try:
        info = client.get_collection(_QDRANT_COLLECTION)
        # Support both old (vectors_count) and new (points_count) Qdrant APIs
        vec_count = getattr(info, 'vectors_count', None) or getattr(info, 'points_count', 0) or 0
        return {
            'available': True,
            'url': _os.getenv('QDRANT_URL', 'http://localhost:6333'),
            'collection': _QDRANT_COLLECTION,
            'vectors_count': vec_count,
            'st_available': _ST_AVAILABLE,
        }
    except Exception as ex:
        return {'available': False, 'error': str(ex), 'st_available': _ST_AVAILABLE}


# Auto-initialize in-memory Qdrant on module load
_init_qdrant_inmemory()
