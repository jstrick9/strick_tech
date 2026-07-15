"""
Agentic OS — Knowledge Graph Memory
Neo4j-style entity-relationship graph that persists across sessions.
Agents can add facts, link entities, and query relationships.

Unlike flat vector search, the graph captures:
  - Entities (Person, Project, Concept, Tool, Decision, etc.)
  - Relationships (CREATED_BY, DEPENDS_ON, RELATES_TO, DECIDED_ON, etc.)
  - Properties (attributes of entities)
  - Temporal context (when facts were learned)
  - Confidence scores

Query modes:
  - Direct: find entity by name/type
  - Traversal: follow relationships N hops
  - Semantic: find entities similar to a query
  - Timeline: what was learned when
"""
from __future__ import annotations
import json, logging, re, time, uuid
from pathlib import Path
from fastapi import APIRouter, Request

router = APIRouter(prefix="/api/knowledge-graph", tags=["knowledge_graph"])
log    = logging.getLogger("agentic.kg")

_SCHEMA = """
CREATE TABLE IF NOT EXISTS kg_entities (
    id           TEXT PRIMARY KEY,
    name         TEXT NOT NULL,
    type         TEXT DEFAULT 'concept',
    description  TEXT DEFAULT '',
    properties   TEXT DEFAULT '{}',
    source       TEXT DEFAULT '',
    confidence   REAL DEFAULT 1.0,
    created_at   TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    updated_at   TIMESTAMP DEFAULT CURRENT_TIMESTAMP
);
CREATE TABLE IF NOT EXISTS kg_relations (
    id           TEXT PRIMARY KEY,
    from_id      TEXT NOT NULL,
    to_id        TEXT NOT NULL,
    relation     TEXT NOT NULL,
    properties   TEXT DEFAULT '{}',
    confidence   REAL DEFAULT 1.0,
    source       TEXT DEFAULT '',
    created_at   TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    FOREIGN KEY(from_id) REFERENCES kg_entities(id),
    FOREIGN KEY(to_id)   REFERENCES kg_entities(id)
);
CREATE TABLE IF NOT EXISTS kg_facts (
    id           TEXT PRIMARY KEY,
    subject_id   TEXT NOT NULL,
    predicate    TEXT NOT NULL,
    object_text  TEXT NOT NULL,
    confidence   REAL DEFAULT 1.0,
    source       TEXT DEFAULT '',
    created_at   TIMESTAMP DEFAULT CURRENT_TIMESTAMP
);
CREATE VIRTUAL TABLE IF NOT EXISTS kg_entities_fts
    USING fts5(name, description, type, content='kg_entities', content_rowid='rowid');
CREATE INDEX IF NOT EXISTS idx_kg_rel_from ON kg_relations(from_id);
CREATE INDEX IF NOT EXISTS idx_kg_rel_to   ON kg_relations(to_id);
CREATE INDEX IF NOT EXISTS idx_kg_rel_type ON kg_relations(relation);
CREATE INDEX IF NOT EXISTS idx_kg_ent_type ON kg_entities(type);
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


# ── Entity operations ──────────────────────────────────────────────────────────
@router.post("/entities")
async def add_entity(req: Request):
    try:
        body = await req.json()
    except Exception:
        body = {}
    name = (body.get("name") or "").strip()
    if not name:
        return {"ok":False,"error":"name required"}
    from ..services.memory_db import get_conn
    con = get_conn()
    try:
        # Check if entity exists (upsert by name+type)
        etype = body.get("type","concept")
        existing = con.execute("SELECT id FROM kg_entities WHERE name=? AND type=?", (name,etype)).fetchone()
        if existing:
            eid = existing["id"]
            con.execute("UPDATE kg_entities SET description=?,properties=?,confidence=?,updated_at=CURRENT_TIMESTAMP WHERE id=?",
                        (body.get("description",""),json.dumps(body.get("properties",{})),
                         float(body.get("confidence",1.0)),eid))
        else:
            eid = f"ent_{uuid.uuid4().hex[:8]}"
            con.execute("INSERT INTO kg_entities(id,name,type,description,properties,source,confidence) VALUES (?,?,?,?,?,?,?)",
                        (eid,name,etype,body.get("description",""),
                         json.dumps(body.get("properties",{})),
                         body.get("source",""),float(body.get("confidence",1.0))))
        try:
            con.execute("INSERT INTO kg_entities_fts(kg_entities_fts) VALUES ('rebuild')")
        except Exception:
            pass
        con.commit()
    finally:
        con.close()
    return {"ok":True,"entity_id":eid,"name":name,"type":etype}


@router.post("/relations")
async def add_relation(req: Request):
    try:
        body = await req.json()
    except Exception:
        body = {}
    from_id  = body.get("from_id","")
    to_id    = body.get("to_id","")
    relation = (body.get("relation") or "RELATES_TO").upper().replace(" ","_")
    if not from_id or not to_id:
        return {"ok":False,"error":"from_id and to_id required"}
    rid = f"rel_{uuid.uuid4().hex[:8]}"
    from ..services.memory_db import get_conn
    con = get_conn()
    try:
        fe = con.execute("SELECT id FROM kg_entities WHERE id=?", (from_id,)).fetchone()
        te = con.execute("SELECT id FROM kg_entities WHERE id=?", (to_id,)).fetchone()
        if not fe or not te:
            return {"ok":False,"error":"from_id or to_id not found"}
        con.execute("INSERT INTO kg_relations(id,from_id,to_id,relation,properties,confidence,source) VALUES (?,?,?,?,?,?,?)",
                    (rid,from_id,to_id,relation,json.dumps(body.get("properties",{})),
                     float(body.get("confidence",1.0)),body.get("source","")))
        con.commit()
    finally:
        con.close()
    return {"ok":True,"relation_id":rid}


@router.post("/facts")
async def add_fact(req: Request):
    try:
        body = await req.json()
    except Exception:
        body = {}
    subject_id = body.get("subject_id","")
    predicate  = (body.get("predicate") or "").strip()
    object_text= (body.get("object") or "").strip()
    if not all([subject_id, predicate, object_text]):
        return {"ok":False,"error":"subject_id, predicate, object required"}
    fid = f"fct_{uuid.uuid4().hex[:8]}"
    from ..services.memory_db import get_conn
    con = get_conn()
    try:
        con.execute("INSERT INTO kg_facts(id,subject_id,predicate,object_text,confidence,source) VALUES (?,?,?,?,?,?)",
                    (fid,subject_id,predicate,object_text,float(body.get("confidence",1.0)),body.get("source","")))
        con.commit()
    finally:
        con.close()
    return {"ok":True,"fact_id":fid}


# ── Queries ────────────────────────────────────────────────────────────────────
@router.get("/entities")
def search_entities(q: str = "", type: str = "", limit: int = 30):
    from ..services.memory_db import get_conn
    con = get_conn()
    try:
        where, params = [], []
        if type: where.append("type=?"); params.append(type)
        if q:    where.append("(name LIKE ? OR description LIKE ?)"); params.extend([f"%{q}%"]*2)
        sql = "SELECT * FROM kg_entities" + (f" WHERE {' AND '.join(where)}" if where else "") + " ORDER BY confidence DESC, updated_at DESC LIMIT ?"
        params.append(min(limit,200))
        rows = con.execute(sql, params).fetchall()
    finally:
        con.close()
    entities = []
    for r in rows:
        d = dict(r)
        d["properties"] = json.loads(d.get("properties","{}") or "{}")
        entities.append(d)
    return {"entities":entities,"count":len(entities)}


@router.get("/entities/{entity_id}")
def get_entity(entity_id: str):
    from ..services.memory_db import get_conn
    con = get_conn()
    try:
        ent   = con.execute("SELECT * FROM kg_entities WHERE id=?", (entity_id,)).fetchone()
        rels  = con.execute("""SELECT r.*, e.name as to_name, e.type as to_type
            FROM kg_relations r JOIN kg_entities e ON e.id=r.to_id
            WHERE r.from_id=?""", (entity_id,)).fetchall()
        irels = con.execute("""SELECT r.*, e.name as from_name, e.type as from_type
            FROM kg_relations r JOIN kg_entities e ON e.id=r.from_id
            WHERE r.to_id=?""", (entity_id,)).fetchall()
        facts = con.execute("SELECT * FROM kg_facts WHERE subject_id=? ORDER BY created_at DESC", (entity_id,)).fetchall()
    finally:
        con.close()
    if not ent: return {"ok":False,"error":"Not found"}
    d = dict(ent); d["properties"] = json.loads(d.get("properties","{}") or "{}")
    d["outgoing_relations"] = [dict(r) for r in rels]
    d["incoming_relations"] = [dict(r) for r in irels]
    d["facts"]             = [dict(f) for f in facts]
    return d


@router.get("/traverse/{entity_id}")
def traverse_graph(entity_id: str, depth: int = 2, relation: str = ""):
    """BFS traversal from entity, following relationships up to N hops."""
    from ..services.memory_db import get_conn
    con = get_conn()
    visited  = set()
    queue    = [(entity_id, 0)]
    nodes    = []
    edges    = []
    try:
        while queue:
            eid, d = queue.pop(0)
            if eid in visited or d > min(depth,4):
                continue
            visited.add(eid)
            ent = con.execute("SELECT id,name,type,description FROM kg_entities WHERE id=?", (eid,)).fetchone()
            if ent:
                nodes.append(dict(ent))
            # Follow outgoing relations
            where = " AND relation=?" if relation else ""
            params = (eid,) if not relation else (eid, relation.upper())
            rels = con.execute(f"SELECT * FROM kg_relations WHERE from_id=?{where} ORDER BY confidence DESC LIMIT 20", params).fetchall()
            for r in rels:
                rd = dict(r)
                edges.append(rd)
                if rd["to_id"] not in visited:
                    queue.append((rd["to_id"], d+1))
    finally:
        con.close()
    return {"start_entity":entity_id,"depth":depth,"nodes":nodes,"edges":edges,"node_count":len(nodes),"edge_count":len(edges)}


# ── AI-powered graph operations ────────────────────────────────────────────────
@router.post("/extract")
async def extract_from_text(req: Request):
    """Extract entities and relationships from text using LLM."""
    try:
        body   = await req.json()
    except Exception:
        body   = {}
    text   = (body.get("text") or "").strip()[:5000]
    source = body.get("source","text_extraction")
    if not text:
        return {"ok":False,"error":"text required"}

    from ..services import llm as llm_svc
    prompt = f"""Extract entities and relationships from this text.

TEXT: {text}

Return JSON:
{{
  "entities": [
    {{"name": "entity name", "type": "person|project|tool|concept|decision|file|company", "description": "brief"}}
  ],
  "relations": [
    {{"from": "entity name", "to": "entity name", "relation": "CREATED_BY|DEPENDS_ON|USES|RELATED_TO|AUTHORED|PART_OF"}}
  ],
  "facts": [
    {{"subject": "entity name", "predicate": "has_property", "object": "value"}}
  ]
}}

Only extract clear, factual information. Return ONLY valid JSON."""

    result = await llm_svc.complete([{"role":"user","content":prompt}], agent_id="knowledge_graph", max_tokens=1000, temperature=0.1, inject_steering=False)
    extracted = {}
    m = re.search(r'\{.*\}', result.get("text",""), re.DOTALL)
    if m:
        try: extracted = json.loads(m.group(0))
        except Exception: pass

    if not extracted:
        return {"ok":False,"error":"Could not extract entities from text"}

    # Persist extracted entities — call DB logic directly, no fake Request
    from ..services.memory_db import get_conn as _get_conn
    created_entities = {}
    for ent in extracted.get("entities",[]):
        ent_name = ent.get("name","")
        if not ent_name: continue
        etype   = ent.get("type","concept")
        edesc   = ent.get("description","")
        _con = _get_conn()
        try:
            existing = _con.execute("SELECT id FROM kg_entities WHERE name=? AND type=?", (ent_name, etype)).fetchone()
            if existing:
                eid2 = existing["id"]
                _con.execute("UPDATE kg_entities SET description=?,updated_at=CURRENT_TIMESTAMP WHERE id=?", (edesc, eid2))
            else:
                eid2 = f"ent_{uuid.uuid4().hex[:8]}"
                _con.execute("INSERT INTO kg_entities(id,name,type,description,source,confidence) VALUES (?,?,?,?,?,?)",
                             (eid2, ent_name, etype, edesc, source, 1.0))
            try:
                _con.execute("INSERT INTO kg_entities_fts(kg_entities_fts) VALUES ('rebuild')")
            except Exception:
                pass
            _con.commit()
        finally:
            _con.close()
        created_entities[ent_name.lower()] = eid2

    # Persist relations
    created_rels = 0
    for rel in extracted.get("relations",[]):
        from_name = rel.get("from","").lower()
        to_name   = rel.get("to","").lower()
        relation  = rel.get("relation","RELATES_TO")
        from_id = created_entities.get(from_name)
        to_id   = created_entities.get(to_name)
        if from_id and to_id:
            from ..services.memory_db import get_conn
            con = get_conn()
            try:
                rid = f"rel_{uuid.uuid4().hex[:6]}"
                con.execute("INSERT OR IGNORE INTO kg_relations(id,from_id,to_id,relation,source) VALUES (?,?,?,?,?)",
                            (rid,from_id,to_id,relation.upper(),source))
                con.commit()
            finally:
                con.close()
            created_rels += 1

    # Persist facts
    created_facts = 0
    for fact in extracted.get("facts",[]):
        subj_name = fact.get("subject","").lower()
        subj_id   = created_entities.get(subj_name)
        if subj_id:
            from ..services.memory_db import get_conn
            con = get_conn()
            try:
                fid = f"fct_{uuid.uuid4().hex[:6]}"
                con.execute("INSERT INTO kg_facts(id,subject_id,predicate,object_text,source) VALUES (?,?,?,?,?)",
                            (fid,subj_id,fact.get("predicate",""),fact.get("object",""),source))
                con.commit()
            finally:
                con.close()
            created_facts += 1

    return {
        "ok":True,
        "entities_created":  len(created_entities),
        "relations_created": created_rels,
        "facts_created":     created_facts,
        "extracted":         extracted,
    }


@router.post("/query")
async def natural_language_query(req: Request):
    """Query the knowledge graph using natural language."""
    try:
        body  = await req.json()
    except Exception:
        body  = {}
    query = (body.get("query") or "").strip()
    if not query:
        return {"ok":False,"error":"query required"}

    # Find relevant entities
    from ..services.memory_db import get_conn
    con = get_conn()
    try:
        # Try FTS search first
        try:
            ent_rows = con.execute(
                "SELECT e.* FROM kg_entities e JOIN kg_entities_fts fts ON fts.rowid=e.rowid WHERE kg_entities_fts MATCH ? LIMIT 10",
                (query,)
            ).fetchall()
        except Exception:
            # Fallback to LIKE
            ent_rows = con.execute(
                "SELECT * FROM kg_entities WHERE name LIKE ? OR description LIKE ? LIMIT 10",
                (f"%{query}%",f"%{query}%")
            ).fetchall()
        # Get related facts
        facts = []
        for ent in ent_rows[:3]:
            f = con.execute("SELECT * FROM kg_facts WHERE subject_id=? LIMIT 5", (ent["id"],)).fetchall()
            facts.extend([dict(r) for r in f])
    finally:
        con.close()

    entities = [dict(e) for e in ent_rows]

    # Use LLM to synthesize answer
    if entities:
        from ..services import llm as llm_svc
        ctx = "\n".join(f"- {e['name']} ({e['type']}): {e['description']}" for e in entities[:5])
        fact_ctx = "\n".join(f"- {f['predicate']}: {f['object_text']}" for f in facts[:10])
        prompt = f"""Answer this question using the knowledge graph data:

Query: {query}

Entities found:
{ctx}

Related facts:
{fact_ctx}

Answer based on the graph data. If information isn't in the graph, say so."""

        result = await llm_svc.complete([{"role":"user","content":prompt}], agent_id="knowledge_graph", max_tokens=500, inject_steering=False)
        answer = result.get("text","")
    else:
        answer = f"No entities found in the knowledge graph for '{query}'. Try adding some with /api/knowledge-graph/extract."

    return {"ok":True,"query":query,"answer":answer,"entities_found":entities[:5],"fact_count":len(facts)}


@router.get("/stats")
def graph_stats():
    from ..services.memory_db import get_conn
    con = get_conn()
    try:
        entities  = con.execute("SELECT COUNT(*) FROM kg_entities").fetchone()[0]
        relations = con.execute("SELECT COUNT(*) FROM kg_relations").fetchone()[0]
        facts     = con.execute("SELECT COUNT(*) FROM kg_facts").fetchone()[0]
        by_type   = con.execute("SELECT type, COUNT(*) as cnt FROM kg_entities GROUP BY type ORDER BY cnt DESC").fetchall()
        by_rel    = con.execute("SELECT relation, COUNT(*) as cnt FROM kg_relations GROUP BY relation ORDER BY cnt DESC LIMIT 10").fetchall()
    finally:
        con.close()
    return {
        "entities":    entities,
        "relations":   relations,
        "facts":       facts,
        "by_type":     {r["type"]:r["cnt"] for r in by_type},
        "by_relation": {r["relation"]:r["cnt"] for r in by_rel},
    }


@router.delete("/clear")
def clear_graph():
    from ..services.memory_db import get_conn
    con = get_conn()
    try:
        con.execute("DELETE FROM kg_facts")
        con.execute("DELETE FROM kg_relations")
        con.execute("DELETE FROM kg_entities")
        con.commit()
    finally:
        con.close()
    return {"ok":True}
