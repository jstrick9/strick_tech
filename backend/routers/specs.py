"""
Agentic OS — Spec-Driven Development Router (Kiro-style)
Four-phase pipeline: Requirements → Design → Tasks → Code

Phase 1: requirements.md  — user stories, acceptance criteria (EARS notation)
Phase 2: design.md        — architecture, data models, API contracts, sequence diagrams
Phase 3: tasks.md         — dependency-mapped implementation task list
Phase 4: wave execution   — group independent tasks, run concurrently per wave

All artifacts stored in workspaces/<workspace>/specs/<spec_id>/
"""
from __future__ import annotations
import asyncio, json, logging, os, time, uuid
from pathlib import Path
from fastapi import APIRouter, Request
from fastapi.responses import StreamingResponse

router = APIRouter(prefix="/api/specs", tags=["specs"])
log    = logging.getLogger("agentic.specs")


def _parse_delta(chunk: str) -> str:
    """Extract text delta from an SSE chunk string yielded by llm.stream()."""
    try:
        if chunk.startswith("data:"):
            parsed = json.loads(chunk[5:].strip())
            return parsed.get("delta", "")
    except Exception:
        pass
    return ""


ROOT      = Path(__file__).resolve().parents[2]
SPECS_DIR = ROOT / "workspaces" / "specs"
SPECS_DIR.mkdir(parents=True, exist_ok=True)

# ── DB schema ──────────────────────────────────────────────────────────────────
_SCHEMA = """
CREATE TABLE IF NOT EXISTS specs (
    id           TEXT PRIMARY KEY,
    title        TEXT NOT NULL,
    description  TEXT DEFAULT '',
    phase        TEXT DEFAULT 'requirements',
    status       TEXT DEFAULT 'draft',
    workspace_id TEXT DEFAULT 'default',
    requirements TEXT DEFAULT '',
    design       TEXT DEFAULT '',
    tasks_json   TEXT DEFAULT '[]',
    created_at   TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    updated_at   TIMESTAMP DEFAULT CURRENT_TIMESTAMP
);
CREATE TABLE IF NOT EXISTS spec_tasks (
    id           INTEGER PRIMARY KEY AUTOINCREMENT,
    spec_id      TEXT NOT NULL,
    task_no      INTEGER NOT NULL,
    title        TEXT NOT NULL,
    description  TEXT DEFAULT '',
    wave         INTEGER DEFAULT 1,
    depends_on   TEXT DEFAULT '[]',
    status       TEXT DEFAULT 'pending',
    output       TEXT DEFAULT '',
    agent_id     TEXT DEFAULT 'builder',
    created_at   TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    FOREIGN KEY(spec_id) REFERENCES specs(id)
);
CREATE INDEX IF NOT EXISTS idx_spec_tasks_spec ON spec_tasks(spec_id, wave, task_no);
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


# ── Helpers ───────────────────────────────────────────────────────────────────
def _spec_dir(spec_id: str) -> Path:
    d = SPECS_DIR / spec_id
    d.mkdir(parents=True, exist_ok=True)
    return d

def _save_artifact(spec_id: str, filename: str, content: str):
    (_spec_dir(spec_id) / filename).write_text(content, encoding="utf-8")

def _load_artifact(spec_id: str, filename: str) -> str:
    p = _spec_dir(spec_id) / filename
    return p.read_text(encoding="utf-8") if p.exists() else ""

def _get_spec(spec_id: str) -> dict | None:
    from ..services.memory_db import get_conn
    con = get_conn()
    try:
        row = con.execute("SELECT * FROM specs WHERE id=?", (spec_id,)).fetchone()
        return dict(row) if row else None
    finally:
        con.close()

def _update_spec(spec_id: str, **kwargs):
    from ..services.memory_db import get_conn
    con = get_conn()
    try:
        sets  = [f"{k}=?" for k in kwargs]
        vals  = list(kwargs.values()) + [spec_id]
        sets.append("updated_at=CURRENT_TIMESTAMP")
        con.execute(f"UPDATE specs SET {','.join(sets)} WHERE id=?", vals)
        con.commit()
    finally:
        con.close()


# ── REST CRUD ─────────────────────────────────────────────────────────────────
@router.get("")
def list_specs(workspace_id: str = "default"):
    from ..services.memory_db import get_conn
    con = get_conn()
    try:
        rows = con.execute(
            "SELECT * FROM specs WHERE workspace_id=? ORDER BY updated_at DESC",
            (workspace_id,)
        ).fetchall()
    finally:
        con.close()
    return {"specs": [dict(r) for r in rows], "count": len(rows)}


@router.post("")
async def create_spec(req: Request):
    try:
        body = await req.json()
    except Exception:
        body = {}
    spec_id = f"spec_{uuid.uuid4().hex[:8]}"
    title   = (body.get("title") or "Untitled Feature")[:200]
    desc    = (body.get("description") or "")[:2000]
    ws      = body.get("workspace_id","default")

    from ..services.memory_db import get_conn
    con = get_conn()
    try:
        con.execute(
            "INSERT INTO specs(id,title,description,workspace_id) VALUES (?,?,?,?)",
            (spec_id, title, desc, ws)
        )
        con.commit()
    finally:
        con.close()
    return {"ok": True, "spec": {"id": spec_id, "title": title, "phase": "requirements", "status": "draft"}}


@router.get("/{spec_id}")
def get_spec(spec_id: str):
    spec = _get_spec(spec_id)
    if not spec:
        return {"ok": False, "error": "Spec not found"}
    spec["requirements"] = _load_artifact(spec_id, "requirements.md")
    spec["design"]       = _load_artifact(spec_id, "design.md")
    spec["tasks_md"]     = _load_artifact(spec_id, "tasks.md")
    return spec


@router.patch("/{spec_id}")
async def update_spec(spec_id: str, req: Request):
    """Update spec metadata (name, description, status)."""
    try:
        try:
            body = await req.json()
        except Exception:
            body = {}
    except Exception:
        return {"ok": False, "error": "Invalid JSON body"}
    
    allowed = {"title", "description", "status", "phase"}  # specs uses "title" not "name"
    sets, vals = [], []
    for k in allowed:
        if k in body:
            v = str(body[k])[:500] if k in ("name", "description") else str(body[k])[:32]
            sets.append(f"{k}=?")
            vals.append(v)
    
    if not sets:
        return {"ok": False, "error": "No valid fields to update"}
    
    sets.append("updated_at=CURRENT_TIMESTAMP")
    vals.append(spec_id)
    
    from ..services.memory_db import get_conn
    con = get_conn()
    try:
        cur = con.execute(
            f"UPDATE specs SET {', '.join(sets)} WHERE id=?", vals
        )
        con.commit()
        if cur.rowcount == 0:
            return {"ok": False, "error": "Spec not found"}
        row = con.execute("SELECT * FROM specs WHERE id=?", (spec_id,)).fetchone()
    finally:
        con.close()
    
    return {"ok": True, "spec": dict(row) if row else {}}


@router.delete("/{spec_id}")
def delete_spec(spec_id: str):
    from ..services.memory_db import get_conn
    con = get_conn()
    try:
        con.execute("DELETE FROM spec_tasks WHERE spec_id=?", (spec_id,))
        con.execute("DELETE FROM specs WHERE id=?", (spec_id,))
        con.commit()
    finally:
        con.close()
    import shutil
    shutil.rmtree(_spec_dir(spec_id), ignore_errors=True)
    return {"ok": True}


# ── Phase 1: Generate Requirements ────────────────────────────────────────────
@router.post("/{spec_id}/requirements")
async def generate_requirements(spec_id: str, req: Request):
    """Generate requirements.md from natural language description."""
    try:
        body  = await req.json()
    except Exception:
        body  = {}
    desc  = (body.get("description") or body.get("prompt") or "").strip()
    if not desc:
        spec = _get_spec(spec_id)
        desc = spec.get("description","") if spec else ""
    if not desc:
        return {"ok": False, "error": "description required"}

    async def _stream():
        from ..services import llm as llm_svc
        yield f"data: {json.dumps({'type':'phase_start','phase':'requirements'})}\n\n"

        system = """You are a senior product architect. Generate a comprehensive requirements document.
Use EARS (Easy Approach to Requirements Syntax) notation for each requirement:
  - UBIQUITOUS: The <system> shall <capability>
  - EVENT-DRIVEN: When <trigger>, the <system> shall <response>
  - CONDITIONAL: Where <condition>, the <system> shall <capability>
  - OPTION: Where <feature included>, the <system> shall <capability>

Output a complete requirements.md with:
## Overview
## User Stories (as [role], I want [goal] so that [benefit])
## Functional Requirements (numbered, EARS notation)  
## Non-Functional Requirements (performance, security, UX)
## Acceptance Criteria (Given/When/Then for each major requirement)
## Out of Scope (explicit exclusions)

Be specific, measurable, and unambiguous. Every requirement must be testable."""

        messages = [
            {"role": "system", "content": system},
            {"role": "user", "content": f"Generate requirements for this feature:\n\n{desc}"}
        ]

        full_text = ""
        async for chunk in llm_svc.stream(messages, agent_id="specs", max_tokens=3000, inject_steering=False):
            # FIX 4: parse actual text delta from SSE chunk
            delta = _parse_delta(chunk)
            if delta:
                full_text += delta
                yield f"data: {json.dumps({'type':'chunk','text':delta})}\n\n"

        # Save artifact
        _save_artifact(spec_id, "requirements.md", full_text)
        _update_spec(spec_id, requirements=full_text[:500], phase="requirements", status="in_progress")

        yield f"data: {json.dumps({'type':'phase_done','phase':'requirements','length':len(full_text)})}\n\n"

    return StreamingResponse(_stream(), media_type="text/event-stream",
                             headers={"Cache-Control":"no-cache","X-Accel-Buffering":"no"})


# ── Phase 2: Generate Design ──────────────────────────────────────────────────
@router.post("/{spec_id}/design")
async def generate_design(spec_id: str, req: Request):
    """Generate design.md from requirements."""
    requirements = _load_artifact(spec_id, "requirements.md")
    if not requirements:
        return {"ok": False, "error": "Generate requirements first"}

    async def _stream():
        from ..services import llm as llm_svc
        yield f"data: {json.dumps({'type':'phase_start','phase':'design'})}\n\n"

        system = """You are a senior software architect. Generate a technical design document.

Output design.md with:
## Architecture Overview (system diagram in ASCII/Mermaid)
## Component Design (each component's responsibility and interface)
## Data Models (entity definitions, relationships, SQLite/JSON schemas)
## API Contracts (endpoints, request/response shapes)
## Sequence Diagrams (key flows in Mermaid sequence diagram format)
## State Management (how state flows through the system)
## Error Handling Strategy
## Security Considerations
## Performance Considerations
## Testing Strategy (unit, integration, e2e test plan)

Be precise. Include actual field names, types, and method signatures."""

        req_summary = requirements[:4000]
        messages = [
            {"role": "system", "content": system},
            {"role": "user", "content": f"Generate technical design for:\n\n{req_summary}"}
        ]

        full_text = ""
        async for chunk in llm_svc.stream(messages, agent_id="specs", max_tokens=4000, inject_steering=False):
            # FIX 4: parse actual text delta from SSE chunk
            delta = _parse_delta(chunk)
            if delta:
                full_text += delta
                yield f"data: {json.dumps({'type':'chunk','text':delta})}\n\n"

        _save_artifact(spec_id, "design.md", full_text)
        _update_spec(spec_id, design=full_text[:500], phase="design")
        yield f"data: {json.dumps({'type':'phase_done','phase':'design','length':len(full_text)})}\n\n"

    return StreamingResponse(_stream(), media_type="text/event-stream",
                             headers={"Cache-Control":"no-cache","X-Accel-Buffering":"no"})


# ── Phase 3: Generate Tasks ───────────────────────────────────────────────────
@router.post("/{spec_id}/tasks")
async def generate_tasks(spec_id: str, req: Request):
    """Generate dependency-mapped task list from design."""
    design = _load_artifact(spec_id, "design.md")
    reqs   = _load_artifact(spec_id, "requirements.md")
    if not design:
        return {"ok": False, "error": "Generate design first"}

    async def _stream():
        from ..services import llm as llm_svc
        yield f"data: {json.dumps({'type':'phase_start','phase':'tasks'})}\n\n"

        system = """You are a senior engineering manager breaking down a design into implementation tasks.

Return a JSON array of tasks, each with:
{
  "task_no": 1,
  "title": "Short descriptive title",
  "description": "What exactly to implement",
  "agent_id": "builder|researcher|orchestrator",
  "depends_on": [],  // array of task_no that must complete first
  "wave": 1,         // compute wave based on dependencies (wave 1 = no deps)
  "estimated_min": 5,
  "file_hints": ["path/to/relevant/file.py"],
  "acceptance": "How to verify this task is done"
}

Rules:
- Tasks with no dependencies go in wave 1
- Tasks whose deps are ALL in wave N go in wave N+1
- Aim for 8-20 tasks for a medium feature
- Be specific — each task should be < 1 hour of AI work
- Return ONLY valid JSON array, no markdown wrapper"""

        context = f"REQUIREMENTS:\n{reqs[:2000]}\n\nDESIGN:\n{design[:3000]}"
        messages = [
            {"role": "system", "content": system},
            {"role": "user", "content": f"Break this into implementation tasks:\n\n{context}"}
        ]

        result = await llm_svc.complete(messages, agent_id="specs", max_tokens=3000, temperature=0.2, inject_steering=False)
        text   = (result.get("text") or "").strip()

        # Parse JSON
        import re
        m = re.search(r'\[.*\]', text, re.DOTALL)
        tasks_json = []
        if m:
            try:
                tasks_json = json.loads(m.group(0))
            except Exception:
                tasks_json = []

        # Fallback: create stub tasks
        if not tasks_json:
            tasks_json = [
                {"task_no":1,"title":"Set up data models","description":"Create database schema and models","agent_id":"builder","depends_on":[],"wave":1},
                {"task_no":2,"title":"Implement backend API","description":"Create FastAPI routes and business logic","agent_id":"builder","depends_on":[1],"wave":2},
                {"task_no":3,"title":"Build frontend UI","description":"Create user interface components","agent_id":"builder","depends_on":[2],"wave":3},
                {"task_no":4,"title":"Write tests","description":"Unit and integration tests","agent_id":"builder","depends_on":[2,3],"wave":4},
            ]

        # Save tasks
        from ..services.memory_db import get_conn
        con = get_conn()
        try:
            con.execute("DELETE FROM spec_tasks WHERE spec_id=?", (spec_id,))
            for t in tasks_json:
                tn = t.get("task_no",0)
                con.execute("""INSERT INTO spec_tasks(spec_id,task_no,title,description,wave,depends_on,agent_id)
                               VALUES (?,?,?,?,?,?,?)""",
                            (spec_id, tn, t.get("title",""),t.get("description",""),
                             t.get("wave",1), json.dumps(t.get("depends_on",[])),
                             t.get("agent_id","builder")))
            _update_spec(spec_id, tasks_json=json.dumps(tasks_json), phase="tasks")
            con.commit()
        finally:
            con.close()

        # Generate tasks.md
        tasks_md = "# Implementation Tasks\n\n"
        waves: dict[int,list] = {}
        for t in tasks_json:
            w = t.get("wave",1)
            waves.setdefault(w,[]).append(t)
        for w in sorted(waves):
            tasks_md += f"## Wave {w} (parallel)\n"
            for t in waves[w]:
                deps = ", ".join(f"#{d}" for d in t.get("depends_on",[]))
                tasks_md += f"- [ ] **Task {t.get('task_no','?')}**: {t.get('title','')} {f'(after {deps})' if deps else ''}\n"
                tasks_md += f"  - {t.get('description','')}\n"
                tasks_md += f"  - Agent: {t.get('agent_id','builder')}\n\n"
        _save_artifact(spec_id, "tasks.md", tasks_md)

        yield f"data: {json.dumps({'type':'tasks_ready','tasks':tasks_json,'wave_count':len(waves)})}\n\n"
        yield f"data: {json.dumps({'type':'phase_done','phase':'tasks','task_count':len(tasks_json)})}\n\n"

    return StreamingResponse(_stream(), media_type="text/event-stream",
                             headers={"Cache-Control":"no-cache","X-Accel-Buffering":"no"})


# ── Phase 4: Execute Tasks (wave-based parallel) ──────────────────────────────
@router.post("/{spec_id}/execute")
async def execute_spec(spec_id: str, req: Request):
    """Execute all tasks wave by wave. Tasks in same wave run in parallel."""
    try:
        body      = await req.json()
    except Exception:
        body      = {}
    dry_run   = body.get("dry_run", False)
    task_nos  = body.get("task_nos", [])  # empty = all

    spec = _get_spec(spec_id)
    if not spec:
        return {"ok": False, "error": "Spec not found"}

    from ..services.memory_db import get_conn
    con = get_conn()
    try:
        tasks = con.execute(
            "SELECT * FROM spec_tasks WHERE spec_id=? ORDER BY wave,task_no",
            (spec_id,)
        ).fetchall()
    finally:
        con.close()

    if not tasks:
        return {"ok": False, "error": "No tasks found. Generate tasks first."}

    # Group by wave
    waves: dict[int, list] = {}
    for t in tasks:
        td = dict(t)
        if task_nos and td["task_no"] not in task_nos:
            continue
        waves.setdefault(td["wave"], []).append(td)

    async def _stream():
        from ..services import llm as llm_svc
        reqs   = _load_artifact(spec_id, "requirements.md")
        design = _load_artifact(spec_id, "design.md")

        total_tasks = sum(len(v) for v in waves.values())
        yield f"data: {json.dumps({'type':'exec_start','spec_id':spec_id,'waves':len(waves),'total_tasks':total_tasks})}\n\n"

        _update_spec(spec_id, status="executing")
        completed: dict[int,str] = {}  # task_no → output

        for wave_no in sorted(waves):
            wave_tasks = waves[wave_no]
            yield f"data: {json.dumps({'type':'wave_start','wave':wave_no,'task_count':len(wave_tasks)})}\n\n"

            if dry_run:
                for t in wave_tasks:
                    yield f"data: {json.dumps({'type':'task_skip','task_no':t['task_no'],'title':t['title'],'dry_run':True})}\n\n"
                continue

            # Run tasks in this wave in parallel
            async def _run_task(task: dict) -> dict:
                tn    = task["task_no"]
                title = task["title"]
                desc  = task["description"]
                aid   = task.get("agent_id","builder")

                # Build context from completed dependencies
                dep_context = ""
                deps = json.loads(task.get("depends_on","[]") or "[]")
                for dep in deps:
                    if dep in completed:
                        dep_context += f"\n### Output from Task {dep}:\n{completed[dep][:500]}\n"

                prompt = (
                    f"You are implementing task {tn} of a spec-driven feature.\n\n"
                    f"**Task:** {title}\n**Description:** {desc}\n\n"
                    f"**Requirements context:**\n{reqs[:1000]}\n\n"
                    f"**Design context:**\n{design[:1500]}\n\n"
                    f"{dep_context}\n\n"
                    f"Implement this task. Return the complete code/content needed. "
                    f"Be specific and production-ready."
                )

                msgs   = [{"role":"user","content":prompt}]
                result = await llm_svc.complete(msgs, agent_id=aid, max_tokens=2000, inject_steering=False)
                output = result.get("text","")

                # Update DB
                from ..services.memory_db import get_conn as _gc
                c2 = _gc()
                try:
                    c2.execute("UPDATE spec_tasks SET status='done',output=? WHERE spec_id=? AND task_no=?",
                               (output[:4000], spec_id, tn))
                    c2.commit()
                finally:
                    c2.close()

                return {"task_no":tn,"title":title,"output":output}

            # Execute wave in parallel
            wave_results = await asyncio.gather(*[_run_task(t) for t in wave_tasks], return_exceptions=True)

            for res in wave_results:
                if isinstance(res, Exception):
                    yield f"data: {json.dumps({'type':'task_error','error':str(res)})}\n\n"
                else:
                    completed[res["task_no"]] = res["output"]
                    yield f"data: {json.dumps({'type':'task_done','task_no':res['task_no'],'title':res['title'],'output_len':len(res['output'])})}\n\n"

            yield f"data: {json.dumps({'type':'wave_done','wave':wave_no,'completed':len(completed)})}\n\n"

        _update_spec(spec_id, status="done", phase="code")
        yield f"data: {json.dumps({'type':'exec_done','spec_id':spec_id,'total_completed':len(completed)})}\n\n"

    return StreamingResponse(_stream(), media_type="text/event-stream",
                             headers={"Cache-Control":"no-cache","X-Accel-Buffering":"no"})


# ── Full pipeline (all 4 phases) ──────────────────────────────────────────────
@router.post("/{spec_id}/run-all")
async def run_full_pipeline(spec_id: str, req: Request):
    """Run all 4 phases sequentially: requirements → design → tasks → execute."""
    try:
        body = await req.json()
    except Exception:
        body = {}
    desc = body.get("description","")

    async def _stream():
        # FIX 5: call phase logic directly (no fake FastAPI Request)
        from ..services import llm as llm_svc

        # Phase 1: Requirements
        yield f"data: {json.dumps({'type':'pipeline_phase','phase':'requirements'})}\n\n"
        try:
            req_msgs = [
                {"role":"system","content":"You are a senior product architect. Generate structured requirements with EARS notation, user stories, and acceptance criteria."},
                {"role":"user","content":f"Generate requirements for:\n\n{desc}"}
            ]
            full_req = ""
            async for chunk in llm_svc.stream(req_msgs, agent_id="specs", max_tokens=3000, inject_steering=False):
                delta = _parse_delta(chunk)
                if delta:
                    full_req += delta
                    yield f"data: {json.dumps({'type':'chunk','text':delta})}\n\n"
            _save_artifact(spec_id, "requirements.md", full_req)
            _update_spec(spec_id, requirements=full_req[:500], phase="requirements", status="in_progress")
            yield f"data: {json.dumps({'type':'phase_done','phase':'requirements','length':len(full_req)})}\n\n"
        except Exception as ex:
            yield f"data: {json.dumps({'type':'phase_error','phase':'requirements','error':str(ex)})}\n\n"
            return

        # Phase 2: Design
        yield f"data: {json.dumps({'type':'pipeline_phase','phase':'design'})}\n\n"
        try:
            req_text = _load_artifact(spec_id, "requirements.md")[:4000]
            des_msgs = [
                {"role":"system","content":"You are a senior software architect. Generate technical design with architecture, data models, API contracts, and sequence diagrams."},
                {"role":"user","content":f"Generate technical design for:\n\n{req_text}"}
            ]
            full_des = ""
            async for chunk in llm_svc.stream(des_msgs, agent_id="specs", max_tokens=4000, inject_steering=False):
                delta = _parse_delta(chunk)
                if delta:
                    full_des += delta
                    yield f"data: {json.dumps({'type':'chunk','text':delta})}\n\n"
            _save_artifact(spec_id, "design.md", full_des)
            _update_spec(spec_id, design=full_des[:500], phase="design")
            yield f"data: {json.dumps({'type':'phase_done','phase':'design','length':len(full_des)})}\n\n"
        except Exception as ex:
            yield f"data: {json.dumps({'type':'phase_error','phase':'design','error':str(ex)})}\n\n"
            return

        # Phase 3: Tasks (uses llm.complete for structured JSON)
        yield f"data: {json.dumps({'type':'pipeline_phase','phase':'tasks'})}\n\n"
        try:
            req_text  = _load_artifact(spec_id, "requirements.md")[:2000]
            des_text  = _load_artifact(spec_id, "design.md")[:2000]
            task_system = """Break a software feature into implementation tasks. Each task should be < 1 hour.
Group into dependency waves (wave 1 = no deps, wave 2 = depends on wave 1, etc).
Return ONLY a JSON array: [{"task_no":1,"title":"...","description":"...","wave":1,"depends_on":[],"agent_id":"builder"}]"""
            task_msgs = [{"role":"system","content":task_system},
                         {"role":"user","content":f"Requirements:\n{req_text}\n\nDesign:\n{des_text}\n\nReturn ONLY JSON array."}]
            result = await llm_svc.complete(task_msgs, agent_id="specs", max_tokens=3000, temperature=0.2, inject_steering=False)
            text   = (result.get("text") or "").strip()
            import re as _re
            jm = _re.search(r"\[.*\]", text, _re.DOTALL)
            tasks_json = []
            if jm:
                try: tasks_json = json.loads(jm.group(0))
                except Exception: pass
            if not tasks_json:
                tasks_json = [
                    {"task_no":1,"title":"Set up data models","description":"Create schema","agent_id":"builder","depends_on":[],"wave":1},
                    {"task_no":2,"title":"Implement backend","description":"Create API routes","agent_id":"builder","depends_on":[1],"wave":2},
                    {"task_no":3,"title":"Build frontend","description":"Create UI","agent_id":"builder","depends_on":[2],"wave":3},
                ]
            from ..services.memory_db import get_conn
            con = get_conn()
            try:
                con.execute("DELETE FROM spec_tasks WHERE spec_id=?", (spec_id,))
                for t in tasks_json:
                    tn = t.get("task_no", 0)
                    con.execute("""INSERT INTO spec_tasks(spec_id,task_no,title,description,wave,depends_on,agent_id)
                                   VALUES (?,?,?,?,?,?,?)""",
                                (spec_id, tn, t.get("title","")[:200], t.get("description","")[:1000],
                                 t.get("wave",1), json.dumps(t.get("depends_on",[])), t.get("agent_id","builder")))
                _update_spec(spec_id, tasks_json=json.dumps(tasks_json), phase="tasks")
                con.commit()
            finally:
                con.close()
            tasks_md = f"# Tasks for {spec_id}\n\n"
            for t in tasks_json:
                tasks_md += f"- [ ] Task {t.get('task_no')}: {t.get('title')}\n"
            _save_artifact(spec_id, "tasks.md", tasks_md)
            yield f"data: {json.dumps({'type':'phase_done','phase':'tasks','task_count':len(tasks_json)})}\n\n"
        except Exception as ex:
            yield f"data: {json.dumps({'type':'phase_error','phase':'tasks','error':str(ex)})}\n\n"
            return

        yield f"data: {json.dumps({'type':'pipeline_done','spec_id':spec_id})}\n\n"

    return StreamingResponse(_stream(), media_type="text/event-stream",
                             headers={"Cache-Control":"no-cache","X-Accel-Buffering":"no"})


# ── Task management ───────────────────────────────────────────────────────────
@router.get("/{spec_id}/tasks")
def get_tasks(spec_id: str):
    from ..services.memory_db import get_conn
    con = get_conn()
    try:
        rows = con.execute(
            "SELECT * FROM spec_tasks WHERE spec_id=? ORDER BY wave,task_no",
            (spec_id,)
        ).fetchall()
    finally:
        con.close()
    tasks = [dict(r) for r in rows]
    # Group by wave
    waves: dict[int,list] = {}
    for t in tasks:
        waves.setdefault(t["wave"], []).append(t)
    return {"tasks":tasks,"waves":waves,"count":len(tasks)}


@router.patch("/{spec_id}/tasks/{task_no}")
async def update_task(spec_id: str, task_no: int, req: Request):
    try:
        body = await req.json()
    except Exception:
        body = {}
    from ..services.memory_db import get_conn
    con = get_conn()
    try:
        allowed = {"status","output","title","description"}
        sets,vals = [],[]
        for k in allowed:
            if k in body:
                sets.append(f"{k}=?"); vals.append(body[k])
        if sets:
            vals += [spec_id, task_no]
            con.execute(f"UPDATE spec_tasks SET {','.join(sets)} WHERE spec_id=? AND task_no=?", vals)
            con.commit()
    finally:
        con.close()
    return {"ok": True}


# ── Artifacts ─────────────────────────────────────────────────────────────────
@router.get("/{spec_id}/artifacts/{filename}")
def get_artifact(spec_id: str, filename: str):
    safe = filename.replace("/","").replace("..","")
    content = _load_artifact(spec_id, safe)
    return {"spec_id":spec_id,"filename":safe,"content":content,"length":len(content)}


@router.put("/{spec_id}/artifacts/{filename}")
async def save_artifact(spec_id: str, filename: str, req: Request):
    try:
        body    = await req.json()
    except Exception:
        body    = {}
    content = body.get("content","")
    safe    = filename.replace("/","").replace("..","")
    _save_artifact(spec_id, safe, content)
    return {"ok":True,"filename":safe,"length":len(content)}


@router.get("/{spec_id}/export")
def export_spec(spec_id: str):
    """Export full spec as a structured dict."""
    spec = _get_spec(spec_id)
    if not spec:
        return {"ok":False,"error":"Not found"}
    from ..services.memory_db import get_conn
    con = get_conn()
    try:
        tasks = [dict(r) for r in con.execute("SELECT * FROM spec_tasks WHERE spec_id=? ORDER BY wave,task_no",(spec_id,)).fetchall()]
    finally:
        con.close()
    return {
        "spec":         spec,
        "requirements": _load_artifact(spec_id,"requirements.md"),
        "design":       _load_artifact(spec_id,"design.md"),
        "tasks_md":     _load_artifact(spec_id,"tasks.md"),
        "tasks":        tasks,
    }
