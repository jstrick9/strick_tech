"""
Agentic OS — Multi-File Autonomous Agent
Like Cursor Composer or Windsurf Cascade:
  - Give ONE instruction → AI creates/edits ALL needed files
  - Screenshot → Code reconstruction
  - Branch deploy previews
  - Full project context awareness
"""
from __future__ import annotations
import asyncio, base64, json, logging, re, time, uuid
from pathlib import Path
from fastapi import APIRouter, Request
from fastapi.responses import StreamingResponse
from ..services import llm, memory_db

router = APIRouter(prefix="/api/composer", tags=["composer"])
log    = logging.getLogger("agentic.composer")
ROOT   = Path(__file__).resolve().parents[2]  # FIX 1: parents[2]=agentic-os root
PREV   = ROOT / "preview"


# ── Multi-file agent run ───────────────────────────────────────────────────────
@router.post("/run")
async def composer_run(req: Request):
    """
    Multi-file autonomous agent — streaming SSE.
    Give one instruction, AI plans + creates/edits all needed files.

    Body: {instruction, context?, files?, framework?, stream?}
    Stream events: plan_ready | file_start | file_chunk | file_done | done | error
    """
    try:
        body        = await req.json()
    except Exception:
        body        = {}
    instruction = (body.get("instruction") or "").strip()
    framework   = body.get("framework", "web")
    stream_out  = body.get("stream", True)
    extra_ctx   = body.get("context", "")

    if not instruction:
        return {"ok": False, "error": "instruction required"}

    run_id = f"comp_{uuid.uuid4().hex[:8]}"

    # Gather project context
    existing_files = _get_project_files()
    file_tree_str  = "\n".join(f"  - {f}" for f in existing_files[:30]) or "  (no files yet)"

    # RAG from memory
    mem_hits  = memory_db.memory_search_fts(instruction[:150], limit=3)
    mem_ctx   = "\n".join(f"- {r['content'][:120]}" for r in mem_hits) if mem_hits else ""

    system = f"""You are an expert full-stack developer with complete control over a {framework} project.
You MUST respond with a structured JSON plan followed by the complete file contents.

Project file tree:
{file_tree_str}

{f"Relevant context: {mem_ctx}" if mem_ctx else ""}
{f"Extra context: {extra_ctx}" if extra_ctx else ""}

Your response MUST follow this EXACT format:

<PLAN>
{{
  "summary": "Brief description of what you'll do",
  "files": [
    {{"path": "index.html", "action": "create|edit|delete", "reason": "why"}},
    ...
  ]
}}
</PLAN>

<FILE path="filename.ext">
... complete file content ...
</FILE>

<FILE path="styles.css">
... complete content ...
</FILE>

Rules:
- Write COMPLETE file contents, never truncate with "..." or "rest stays the same"
- For HTML: use Tailwind CDN, clean semantic structure, dark theme (#08090e bg, white text)
- For JS: modern ES6+, no frameworks unless specified
- For CSS: clean, responsive, mobile-first
- Always create index.html as the entry point if it doesn't exist
- Paths are relative to project root (e.g. "index.html", "js/app.js", "styles/main.css")
"""

    async def generate():
        full_response = ""
        t0            = time.time()

        yield f'data: {json.dumps({"type":"start","run_id":run_id,"instruction":instruction[:200]})}\n\n'

        # Stream LLM response
        async for chunk in llm.stream(
            [{"role":"system","content":system}, {"role":"user","content":instruction}],
            agent_id="builder", max_tokens=8192, temperature=0.3, inject_steering=False,  # FIX 2
        ):
            try:
                data = json.loads(chunk.split("data: ",1)[1])
                delta = data.get("delta","")
                if delta:
                    full_response += delta
            except Exception:
                pass

        # Parse the structured response
        plan     = _extract_plan(full_response)
        files    = _extract_files(full_response)

        if plan:
            yield f'data: {json.dumps({"type":"plan_ready","plan":plan})}\n\n'

        if not files:
            # Fallback: try to find any code blocks
            files = _extract_code_blocks(full_response, instruction)

        # Write all files to preview/
        written = []
        for file_info in files:
            path    = file_info["path"].lstrip("/")
            content = file_info["content"]
            if not path or not content:
                continue

            yield f'data: {json.dumps({"type":"file_start","path":path,"bytes":len(content)})}\n\n'

            try:
                target = (PREV / path).resolve()
                if not str(target).startswith(str(PREV.resolve())):
                    continue
                target.parent.mkdir(parents=True, exist_ok=True)
                target.write_text(content, encoding="utf-8")
                # Version it
                con = memory_db.get_conn()
                try:
                    con.execute(
                        "INSERT INTO file_versions(path,content,author,message) VALUES (?,?,?,?)",
                        (path, content, "composer", instruction[:80])
                    )
                    con.commit()
                finally:
                    con.close()
                written.append({"path": path, "bytes": len(content), "action": file_info.get("action","create")})
                yield f'data: {json.dumps({"type":"file_done","path":path,"bytes":len(content)})}\n\n'
            except Exception as e:
                yield f'data: {json.dumps({"type":"file_error","path":path,"error":str(e)})}\n\n'

        duration = round((time.time()-t0)*1000)
        memory_db.audit_log("composer_run", f"{run_id}: {instruction[:80]} → {len(written)} files")
        if written:
            memory_db.memory_add("composer", f"Built: {instruction[:100]} → {[w['path'] for w in written]}", "composer,multi-file")

        yield f'data: {json.dumps({"type":"done","run_id":run_id,"files_written":written,"duration_ms":duration,"preview_url":"/preview/index.html"})}\n\n'

    if stream_out:
        return StreamingResponse(generate(), media_type="text/event-stream",
                                  headers={"Cache-Control":"no-cache","X-Accel-Buffering":"no"})

    # Non-streaming: collect all
    events = []
    async for chunk in generate():
        if chunk.startswith("data:"):
            try: events.append(json.loads(chunk[5:].strip()))
            except Exception: pass
    done_ev = next((e for e in events if e.get("type")=="done"), {})
    return {"ok": True, "run_id": run_id, **done_ev, "events": events}


# ── Screenshot → Code ─────────────────────────────────────────────────────────
@router.post("/screenshot-to-code")
async def screenshot_to_code(req: Request):
    """
    Convert a screenshot/image to working HTML+CSS+JS code.
    Like v0's image input feature.

    Body: {image_b64, image_url?, framework?, filename?}
    """
    try:
        body      = await req.json()
    except Exception:
        body      = {}
    image_b64 = body.get("image_b64", "")
    image_url = body.get("image_url", "")
    framework = body.get("framework", "web")
    filename  = body.get("filename", "index.html")
    style     = body.get("style", "dark")

    if not image_b64 and not image_url:
        return {"ok": False, "error": "image_b64 or image_url required"}

    # Build prompt with image
    image_content = []
    if image_b64:
        # Strip data URL prefix if present
        if "," in image_b64:
            image_b64 = image_b64.split(",",1)[1]
        image_content = [{"type": "image_url", "image_url": {"url": f"data:image/png;base64,{image_b64}"}}]
    elif image_url:
        image_content = [{"type": "image_url", "image_url": {"url": image_url}}]

    system = f"""You are an expert UI developer. 
Analyze the screenshot and recreate it as a pixel-perfect {framework} implementation.
Use Tailwind CSS (via CDN), modern semantic HTML5.
{'Dark theme: background #08090e, text white' if style=='dark' else 'Match the screenshot colors exactly'}.
Make it responsive. Include any visible text, icons (use emoji if needed), and layout structure.
Return ONLY the complete code file, no explanation."""

    messages = [
        {"role": "system", "content": system},
        {"role": "user", "content": [
            {"type": "text", "text": f"Recreate this design as a {framework} {filename} file. Be pixel-perfect."},
            *image_content,
        ]},
    ]

    # Use vision-capable model
    result = await llm.complete(
        messages, agent_id="gpt4o", model="openai/gpt-4o",
        max_tokens=8192, temperature=0.2, inject_steering=False  # FIX 3
    )

    code = result.get("text","").strip()
    if code.startswith("```"):
        code = "\n".join(code.split("\n")[1:])
        code = code.rstrip("`").strip()

    if code:
        # Save to preview
        target = (PREV / filename).resolve()
        if str(target).startswith(str(PREV.resolve())):
            target.write_text(code, encoding="utf-8")
            con = memory_db.get_conn()
            try:
                con.execute("INSERT INTO file_versions(path,content,author,message) VALUES (?,?,?,?)",
                            (filename, code, "screenshot-to-code", "Screenshot reconstruction"))
                con.commit()
            finally:
                con.close()
            memory_db.audit_log("screenshot_to_code", filename)

    return {
        "ok":         bool(code),
        "filename":   filename,
        "code":       code,
        "preview_url": f"/preview/{filename}",
        "tokens":     result.get("tokens", 0),
        "model":      result.get("model",""),
    }


# ── Branch deploy previews ─────────────────────────────────────────────────────
_branch_previews: dict[str, dict] = {}  # branch_name → {url, files, created_at}

@router.post("/preview/branch")
async def create_branch_preview(req: Request):
    """
    Create a named preview from the current preview/ state.
    Each branch/version gets its own preview URL like /preview/branches/{name}/
    Similar to Vercel's preview URLs.
    """
    try:
        body        = await req.json()
    except Exception:
        body        = {}
    branch_name = re.sub(r"[^a-zA-Z0-9_-]", "-", body.get("name", f"preview-{int(time.time())}"))
    title       = body.get("title", branch_name)
    description = body.get("description", "")

    branch_dir = PREV / "branches" / branch_name
    branch_dir.mkdir(parents=True, exist_ok=True)

    # Copy current preview/ → branches/{name}/
    import shutil
    # FIX 5: collect file list first, then copy in thread executor to avoid blocking
    copy_pairs = []
    for f in PREV.rglob("*"):
        if f.is_file() and "branches" not in str(f) and ".git" not in str(f):
            rel  = f.relative_to(PREV)
            dest = branch_dir / rel
            copy_pairs.append((f, dest))

    def _do_copy():
        count = 0
        for src_f, dst_f in copy_pairs:
            dst_f.parent.mkdir(parents=True, exist_ok=True)
            shutil.copy2(src_f, dst_f)
            count += 1
        return count

    loop = asyncio.get_event_loop()
    copied = await loop.run_in_executor(None, _do_copy)

    preview_url  = f"/preview/branches/{branch_name}/"
    _branch_previews[branch_name] = {
        "name":        branch_name,
        "title":       title,
        "description": description,
        "url":         preview_url,
        "files":       copied,
        "created_at":  time.strftime("%Y-%m-%dT%H:%M:%S"),
    }

    memory_db.audit_log("branch_preview_create", f"{branch_name}: {copied} files")
    return {
        "ok":         True,
        "name":       branch_name,
        "title":      title,
        "url":        preview_url,
        "files":      copied,
        "share_url":  f"http://localhost:8787{preview_url}",
    }


@router.get("/preview/branches")
def list_branch_previews():
    """List all branch preview snapshots."""
    branches_dir = PREV / "branches"
    if not branches_dir.exists():
        return {"branches": []}

    result = []
    for d in sorted(branches_dir.iterdir(), key=lambda x: -x.stat().st_mtime):
        if d.is_dir():
            info = _branch_previews.get(d.name, {
                "name":        d.name,
                "title":       d.name,
                "url":         f"/preview/branches/{d.name}/",
                "files":       len(list(d.rglob("*"))),
                "created_at":  time.strftime("%Y-%m-%dT%H:%M:%S", time.localtime(d.stat().st_mtime)),
            })
            result.append(info)
    return {"branches": result}


@router.delete("/preview/branches/{branch_name}")
def delete_branch_preview(branch_name: str):
    import shutil
    branch_dir = PREV / "branches" / re.sub(r"[^a-zA-Z0-9_-]","",branch_name)
    if branch_dir.exists():
        shutil.rmtree(branch_dir)
    _branch_previews.pop(branch_name, None)
    return {"ok": True}


# ── Project context ────────────────────────────────────────────────────────────
@router.get("/context")
def get_project_context():
    """Return full project context for AI awareness."""
    files   = _get_project_files()
    preview = "/preview/index.html"

    # Read entry file if it exists
    entry_content = ""
    entry = PREV / "index.html"
    if entry.exists():
        entry_content = entry.read_text(encoding="utf-8", errors="ignore")[:3000]

    return {
        "files":         files,
        "file_count":    len(files),
        "entry_preview": entry_content,
        "preview_url":   preview,
        "has_styles":    any("css" in f for f in files),
        "has_js":        any(".js" in f for f in files),
        "has_react":     any(f.endswith((".jsx",".tsx")) for f in files),
        "branches":      list(_branch_previews.keys()),
    }


@router.get("/history")
def composer_history(limit: int = 20):
    """Return recent composer runs from audit log."""
    # FIX 13: try/except so missing audit table returns [] not 500
    try:
        con  = memory_db.get_conn()
        try:
            rows = con.execute(
                "SELECT action, detail, datetime(created_at,'localtime') as ts FROM audit WHERE action='composer_run' ORDER BY id DESC LIMIT ?",
                (limit,)
            ).fetchall()
        finally:
            con.close()
        return [dict(r) for r in rows]
    except Exception:
        return []


# ── Helpers ────────────────────────────────────────────────────────────────────
def _get_project_files() -> list[str]:
    if not PREV.exists():
        return []
    files = []
    for f in PREV.rglob("*"):
        if f.is_file() and ".git" not in str(f) and "branches" not in str(f):
            files.append(f.relative_to(PREV).as_posix())
    return sorted(files)[:50]


def _extract_plan(text: str) -> dict | None:
    m = re.search(r'<PLAN>(.*?)</PLAN>', text, re.DOTALL)
    if not m:
        return None
    try:
        return json.loads(m.group(1).strip())
    except Exception:
        return None


def _extract_files(text: str) -> list[dict]:
    files   = []
    pattern = re.compile(r'<FILE\s+path=["\']([^"\']+)["\']>(.*?)</FILE>', re.DOTALL)
    for m in pattern.finditer(text):
        path    = m.group(1).strip()
        content = m.group(2).strip()
        files.append({"path": path, "content": content, "action": "create"})
    return files


def _extract_code_blocks(text: str, instruction: str) -> list[dict]:
    """Fallback: extract code blocks and guess filenames."""
    files   = []
    pattern = re.compile(r'```(\w+)?\n(.*?)```', re.DOTALL)
    ext_map = {"html":"html","css":"css","javascript":"js","js":"js",
               "typescript":"ts","python":"py","json":"json"}

    for i, m in enumerate(pattern.finditer(text)):
        lang    = (m.group(1) or "html").lower()
        content = m.group(2).strip()
        ext     = ext_map.get(lang, lang)
        name    = "index" if i == 0 else f"file{i}"
        if "style" in instruction.lower() and ext == "css":
            name = "styles"
        elif "app" in instruction.lower() and ext == "js":
            name = "app"
        files.append({"path": f"{name}.{ext}", "content": content, "action": "create"})

    return files


# ── GET /preview/branch — list current branch info ───────────────────────────
@router.get("/preview/branch")
def get_current_branch():
    """GET the current active preview branch."""
    import subprocess
    try:
        r = subprocess.run(["git","branch","--show-current"], capture_output=True, text=True, timeout=5,
                           cwd=str(Path(__file__).resolve().parents[2]))
        branch = r.stdout.strip() or "main"
    except Exception:
        branch = "main"
    return {
        "ok": True,
        "current_branch": branch,
        "preview_url": f"/preview/index.html",
        "note": "Use POST /api/composer/preview/branch to create a new branch preview",
    }
