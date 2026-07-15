"""
Agentic OS — Code Search + Project Memory + Smart Suggestions Router
Semantic search across all project files.
Per-project AI memory that learns preferences.
Contextual next-action suggestions after every action.
Auto code review on save.
"""
from __future__ import annotations
import asyncio, hashlib, json, logging, re, time
from pathlib import Path
from fastapi import APIRouter, Request
from ..services import llm, memory_db

router = APIRouter(prefix="/api/project", tags=["project"])
log    = logging.getLogger("agentic.project")

ROOT        = Path(__file__).resolve().parents[2]  # FIX 1: parents[2]=agentic-os root
PREVIEW_DIR = ROOT / "preview"


# ── Code Search ────────────────────────────────────────────────────────────────
@router.get("/search")
async def search_code(q: str = "", limit: int = 20, context_lines: int = 3):
    """
    Semantic + text search across all project files.
    Returns matching lines with surrounding context.
    """
    if not q:
        return {"results": [], "query": q, "total": 0}

    results = []
    if not PREVIEW_DIR.exists():
        return {"results": [], "query": q, "total": 0}

    # Text search across all code files
    code_exts = {".html",".css",".js",".jsx",".ts",".tsx",".py",".json",".md",".yaml",".yml",".sql",".sh"}
    for fpath in sorted(PREVIEW_DIR.rglob("*")):
        if not fpath.is_file(): continue
        if ".git" in str(fpath) or "branches" in str(fpath): continue
        if fpath.suffix.lower() not in code_exts: continue

        try:
            content = fpath.read_text(encoding="utf-8", errors="ignore")
            lines   = content.splitlines()
            for i, line in enumerate(lines):
                if q.lower() in line.lower():
                    start = max(0, i - context_lines)
                    end   = min(len(lines), i + context_lines + 1)
                    # FIX 3: score by match quality (exact word > substring)
                    q_lower = q.lower()
                    line_lower = line.lower()
                    if f" {q_lower} " in f" {line_lower} " or line_lower == q_lower:
                        score = 5  # exact word match
                    elif q_lower in line_lower:
                        score = 3  # substring match
                    else:
                        score = 1  # fallback (shouldn't reach here)
                    results.append({
                        "file":     fpath.relative_to(PREVIEW_DIR).as_posix(),
                        "line":     i + 1,
                        "match":    line.strip(),
                        "context":  lines[start:end],
                        "score":    score,
                    })
        except Exception:
            continue

    # Sort by score then line
    results.sort(key=lambda r: (-r["score"], r["file"], r["line"]))
    total = len(results)
    results = results[:min(limit, 200)]

    # AI-powered summary if few results
    summary = ""
    if total > 0 and len(results) <= 5:
        try:
            locs = ", ".join(f"{r['file']}:{r['line']}" for r in results[:3])
            msgs = [
                {"role":"system","content":"You summarize code search results briefly (1-2 sentences)."},
                {"role":"user","content":f"Query: '{q}'. Found at: {locs}. Summarize what was found."}
            ]
            res     = await llm.complete(msgs, agent_id="free", max_tokens=100, temperature=0.3, inject_steering=False)  # FIX: code ops never need steering context
            summary = res.get("text","").strip()
        except Exception:
            pass

    return {"results": results, "query": q, "total": total, "summary": summary}


@router.get("/files")
def list_project_files(include_hidden: bool = False):
    """List all files in the current project with metadata."""
    if not PREVIEW_DIR.exists():
        return {"files": [], "stats": {}}

    files = []
    ext_counts: dict[str, int] = {}

    for fpath in sorted(PREVIEW_DIR.rglob("*")):
        if not fpath.is_file(): continue
        if not include_hidden and ".git" in str(fpath): continue
        if "branches" in str(fpath): continue

        rel  = fpath.relative_to(PREVIEW_DIR).as_posix()
        ext  = fpath.suffix.lower() or ".txt"
        stat = fpath.stat()
        ext_counts[ext] = ext_counts.get(ext, 0) + 1
        files.append({
            "path":     rel,
            "size":     stat.st_size,
            "ext":      ext,
            "modified": int(stat.st_mtime),
        })

    return {
        "files": files,
        "stats": {
            "total_files": len(files),
            "total_size":  sum(f["size"] for f in files),
            "by_ext":      ext_counts,
        }
    }


# ── Per-Project AI Memory ──────────────────────────────────────────────────────
_PROJECT_MEMORY_TABLE = """
CREATE TABLE IF NOT EXISTS project_memory (
    id          INTEGER PRIMARY KEY,
    key         TEXT NOT NULL,
    value       TEXT NOT NULL,
    category    TEXT DEFAULT 'general',
    confidence  REAL DEFAULT 1.0,
    created_at  TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    updated_at  TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    UNIQUE(key)
)
"""

def _ensure_project_memory():
    con = memory_db.get_conn()
    try:
        con.execute(_PROJECT_MEMORY_TABLE)
        con.commit()
    finally:
        con.close()

_ensure_project_memory()


@router.get("/memory")
def get_project_memory(category: str = ""):
    """Get all learned preferences for this project."""
    con = memory_db.get_conn()
    try:
        if category:
            rows = con.execute(
                "SELECT * FROM project_memory WHERE category=? ORDER BY confidence DESC",
                (category,)
            ).fetchall()
        else:
            rows = con.execute("SELECT * FROM project_memory ORDER BY category, confidence DESC").fetchall()
    finally:
        con.close()
    return [dict(r) for r in rows]


@router.post("/memory")
async def set_project_memory(req: Request):
    """Store a learned preference or fact about this project."""
    try:
        body = await req.json()
    except Exception:
        body = {}
    key  = (body.get("key") or "").strip()[:120]
    val  = (body.get("value") or "").strip()[:2000]
    if not key or not val:
        return {"ok": False, "error": "key and value required"}
    con = memory_db.get_conn()
    try:
        con.execute(
            """INSERT INTO project_memory(key,value,category,confidence)
               VALUES(?,?,?,?)
               ON CONFLICT(key) DO UPDATE SET value=excluded.value,
               category=excluded.category, confidence=excluded.confidence,
               updated_at=CURRENT_TIMESTAMP""",
            (key, val, body.get("category","general")[:32], float(body.get("confidence",1.0)))
        )
        con.commit()
    finally:
        con.close()
    return {"ok": True}


@router.post("/memory/learn")
async def learn_from_interaction(req: Request):
    """
    AI analyzes a user interaction and extracts preferences to remember.
    Call this after every significant interaction.
    """
    try:
        body    = await req.json()
    except Exception:
        body    = {}
    action  = (body.get("action") or "").strip()
    context = (body.get("context") or "").strip()

    if not action:
        return {"ok": False, "error": "action required"}

    # Get existing memory
    con = memory_db.get_conn()
    try:
        existing = con.execute("SELECT key, value FROM project_memory ORDER BY updated_at DESC LIMIT 20").fetchall()
    finally:
        con.close()
    existing_str = "\n".join(f"- {r[0]}: {r[1]}" for r in existing) if existing else "none"

    messages = [
        {"role":"system","content":
            "You extract project preferences from user actions. Return JSON array of {key, value, category} objects.\n"
            "Categories: 'tech_stack'|'style'|'behavior'|'architecture'|'preference'\n"
            "Extract 0-3 preferences. Return [] if nothing to learn. Be specific and actionable.\n"
            "Example: [{\"key\":\"preferred_css\",\"value\":\"Tailwind CSS only, no plain CSS\",\"category\":\"style\"}]"},
        {"role":"user","content":
            f"Action: {action}\nContext: {context[:500]}\nExisting memory: {existing_str[:400]}\n\nExtract new preferences to remember:"}
    ]
    result = await llm.complete(messages, agent_id="free", max_tokens=300, temperature=0.2, inject_steering=False)  # FIX: learn/from-interaction
    text   = (result.get("text") or "").strip()

    # Parse JSON
    learned = []
    try:
        # Extract JSON array from response
        m = re.search(r'\[[\s\S]*?\]', text)
        if m:
            items = json.loads(m.group(0))
            for item in items[:3]:
                if item.get("key") and item.get("value"):
                    con = memory_db.get_conn()
                    try:
                        con.execute(
                            """INSERT INTO project_memory(key,value,category)
                               VALUES(?,?,?)
                               ON CONFLICT(key) DO UPDATE SET value=excluded.value,
                               category=excluded.category, updated_at=CURRENT_TIMESTAMP""",
                            (item["key"][:120], item["value"][:500], item.get("category","preference")[:32])
                        )
                        con.commit()
                    finally:
                        con.close()
                    learned.append(item)
    except Exception:
        pass

    return {"ok": True, "learned": learned, "count": len(learned)}


@router.delete("/memory/{key}")
def delete_memory(key: str):
    con = memory_db.get_conn()
    try:
        con.execute("DELETE FROM project_memory WHERE key=?", (key,))
        con.commit()
    finally:
        con.close()
    return {"ok": True}


# ── Smart Next-Action Suggestions ─────────────────────────────────────────────
_ACTION_SUGGESTIONS_CACHE: dict[str, dict] = {}
_MAX_CACHE_SIZE = 200  # FIX 5: prevent unbounded growth

@router.post("/suggestions")
async def get_suggestions(req: Request):
    """
    AI suggests 3 smart next actions based on the last action performed.
    Context-aware: considers current files, recent changes, and project memory.
    """
    try:
        body        = await req.json()
    except Exception:
        body        = {}
    last_action = (body.get("action") or "").strip()
    pane        = body.get("pane", "")
    files       = body.get("files", [])

    if not last_action:
        return {"suggestions": _default_suggestions(pane)}

    # Cache key
    cache_key = hashlib.md5(f"{last_action}{pane}".encode()).hexdigest()[:12]
    if cache_key in _ACTION_SUGGESTIONS_CACHE:
        cached = _ACTION_SUGGESTIONS_CACHE[cache_key]
        if time.time() - cached["ts"] < 60:
            return {"suggestions": cached["data"]}

    # Get project memory for context
    con = memory_db.get_conn()
    try:
        mem_rows = con.execute("SELECT key, value FROM project_memory ORDER BY updated_at DESC LIMIT 10").fetchall()
    finally:
        con.close()
    mem_context = "\n".join(f"- {r[0]}: {r[1]}" for r in mem_rows) if mem_rows else "none"

    messages = [
        {"role":"system","content":
            "You suggest 3 smart next actions for a developer using an AI OS. "
            "Return JSON array of exactly 3 objects: [{label, action, icon, reason}]\n"
            "label: short button text (max 30 chars)\n"
            "action: the nav() or function call (e.g. nav('deploy'), runScaffold(), scaffoldIntegration('stripe-payments'))\n"
            "icon: single emoji\n"
            "reason: why this is recommended (1 sentence)\n"
            "Be specific and actionable based on what was just done."},
        {"role":"user","content":
            f"Last action: {last_action}\n"
            f"Current pane: {pane}\n"
            f"Project files: {', '.join(files[:10])}\n"
            f"Project preferences: {mem_context[:300]}\n\n"
            f"Suggest 3 smart next actions:"}
    ]

    result = await llm.complete(messages, agent_id="free", max_tokens=400, temperature=0.4, inject_steering=False)  # FIX: suggestions
    text   = (result.get("text") or "").strip()

    suggestions = []
    try:
        m = re.search(r'\[[\s\S]*?\]', text)
        if m:
            items = json.loads(m.group(0))
            for item in items[:3]:
                if item.get("label") and item.get("action"):
                    suggestions.append({
                        "label":  item["label"][:30],
                        "action": item["action"][:100],
                        "icon":   item.get("icon","⚡"),
                        "reason": item.get("reason","")[:100],
                    })
    except Exception:
        pass

    if not suggestions:
        suggestions = _default_suggestions(pane)

    # FIX 5: evict oldest entry when cache is full
    if len(_ACTION_SUGGESTIONS_CACHE) >= _MAX_CACHE_SIZE:
        oldest = min(_ACTION_SUGGESTIONS_CACHE, key=lambda k: _ACTION_SUGGESTIONS_CACHE[k]["ts"])
        _ACTION_SUGGESTIONS_CACHE.pop(oldest, None)
    _ACTION_SUGGESTIONS_CACHE[cache_key] = {"ts": time.time(), "data": suggestions}
    return {"suggestions": suggestions, "context": last_action}


def _default_suggestions(pane: str) -> list[dict]:
    """Fallback suggestions when AI is unavailable."""
    defaults = {
        "chat":       [{"label":"Run Swarm","action":"nav('swarm')","icon":"🌀","reason":"Get multiple AI perspectives"},
                       {"label":"Save to Prompts","action":"","icon":"💾","reason":"Reuse this prompt later"},
                       {"label":"Open Studio","action":"nav('studio')","icon":"🎬","reason":"Build what you just discussed"}],
        "studio":     [{"label":"Run E2E Tests","action":"runE2EFull?.('web')","icon":"🧪","reason":"Verify your changes work"},
                       {"label":"Push to GitHub","action":"showGHPush?.()","icon":"🐙","reason":"Back up your code"},
                       {"label":"Deploy","action":"nav('deploy')","icon":"🚀","reason":"Share with the world"}],
        "kanban":     [{"label":"Start Pipeline","action":"nav('pipeline')","icon":"🏛️","reason":"Automate this task"},
                       {"label":"Set Loop","action":"nav('loops')","icon":"♾️","reason":"Repeat this automatically"},
                       {"label":"Check Dashboard","action":"nav('dashboard')","icon":"📊","reason":"See your progress"}],
        "default":    [{"label":"Build in Studio","action":"nav('studio')","icon":"🎬","reason":"Create something"},
                       {"label":"Chat with AI","action":"nav('chat')","icon":"💬","reason":"Get help"},
                       {"label":"View Analytics","action":"nav('dashboard')","icon":"📊","reason":"Track progress"}],
    }
    return defaults.get(pane, defaults["default"])


# ── Autonomous Code Reviewer ───────────────────────────────────────────────────
_review_cache: dict[str, dict] = {}  # filepath → {content_hash, review, ts}
_MAX_REVIEW_CACHE = 100  # FIX 5: cap review cache

@router.post("/review")
async def review_code(req: Request):
    """
    AI reviews a file for bugs, security issues, performance, and best practices.
    Returns line-level annotations. Cached per file content.
    """
    try:
        body     = await req.json()
    except Exception:
        body     = {}
    filepath = (body.get("filepath") or "").strip().lstrip("/")
    force    = bool(body.get("force", False))

    if not filepath:
        return {"ok": False, "error": "filepath required"}

    fpath = (PREVIEW_DIR / filepath).resolve()
    if not str(fpath).startswith(str(PREVIEW_DIR.resolve())) or not fpath.exists():
        return {"ok": False, "error": "File not found"}

    content = fpath.read_text(encoding="utf-8", errors="ignore")
    content_hash = hashlib.md5(content.encode()).hexdigest()[:12]

    # Return cached review if content unchanged
    if not force and filepath in _review_cache:
        cached = _review_cache[filepath]
        if cached.get("hash") == content_hash and time.time() - cached.get("ts",0) < 300:
            return {"ok": True, "cached": True, **cached["review"]}

    ext = filepath.rsplit(".", 1)[-1] if "." in filepath else "txt"
    messages = [
        {"role":"system","content":
            f"You are a senior code reviewer for {ext} files. "
            f"Return a JSON object with:\n"
            f"- issues: array of {{line:int, severity:'error'|'warning'|'info', message:str, fix:str}}\n"
            f"- summary: string (1-2 sentences on overall quality)\n"
            f"- score: int 0-100 (code quality score)\n"
            f"- highlights: array of strings (what's done well)\n"
            f"Focus on: bugs, security, performance, best practices. Max 8 issues."},
        {"role":"user","content":
            f"Review this {ext} file ({filepath}):\n\n```{ext}\n{content[:5000]}\n```"}
    ]

    result = await llm.complete(messages, agent_id="reviewer", max_tokens=1500, temperature=0.2, inject_steering=False)  # FIX: code reviewer
    text   = (result.get("text") or "").strip()

    review = {"issues":[], "summary":"", "score":75, "highlights":[]}
    try:
        m = re.search(r'\{[\s\S]*\}', text, re.DOTALL)
        if m:
            parsed = json.loads(m.group(0))
            # FIX: validate real review response, not API error JSON
            if "score" in parsed or "issues" in parsed:
                review = parsed
            else:
                review["summary"] = "Review completed (API key required for full analysis)"
    except Exception:
        review["summary"] = text[:200] if text else "Review completed"
    # FIX 5: evict oldest review cache entry when full
    if len(_review_cache) >= _MAX_REVIEW_CACHE:
        oldest = min(_review_cache, key=lambda k: _review_cache[k].get("ts", 0))
        _review_cache.pop(oldest, None)
    _review_cache[filepath] = {"hash": content_hash, "ts": time.time(), "review": review}
    memory_db.audit_log("code_review", f"{filepath}: score={review.get('score',0)}")

    return {"ok": True, "filepath": filepath, "cached": False, **review}


@router.get("/review/history")
def review_history(limit: int = 20):
    """Get recent code reviews from audit log."""
    con = memory_db.get_conn()
    try:
        rows = con.execute(
            "SELECT action, detail, datetime(created_at,'localtime') as ts FROM audit WHERE action='code_review' ORDER BY id DESC LIMIT ?",
            (limit,)
        ).fetchall()
    finally:
        con.close()
    return [dict(r) for r in rows]


# ── Share / Public URL ─────────────────────────────────────────────────────────
@router.post("/share")
async def share_project(req: Request):
    """
    Create a shareable public URL for the current project.
    Uses the LAN tunnel info or Cloudflare if available.
    """
    try:
        body    = await req.json()
    except Exception:
        body    = {}
    target  = body.get("target", "web")
    message = body.get("message", "")

    # Get tunnel info
    from ..routers.builder import _get_lan_ip
    port   = int(__import__("os").getenv("AGENTIC_OS_PORT", "8787"))
    lan_ip = _get_lan_ip()

    web_url  = f"http://{lan_ip}:{port}/preview/index.html"
    demo_url = f"http://{lan_ip}:{port}"

    import shutil, subprocess
    cf = shutil.which("cloudflared")
    public_url = ""
    if cf:
        try:
            # FIX 7: use asyncio subprocess to avoid blocking event loop
            proc = await asyncio.create_subprocess_exec(
                cf, "tunnel", "--url", f"http://localhost:{port}", "--no-autoupdate",
                stdout=asyncio.subprocess.PIPE,
                stderr=asyncio.subprocess.PIPE,
            )
            deadline = asyncio.get_event_loop().time() + 8
            while asyncio.get_event_loop().time() < deadline:
                try:
                    line_bytes = await asyncio.wait_for(proc.stderr.readline(), timeout=1.0)
                    line_text  = line_bytes.decode("utf-8", errors="ignore")
                    m2 = re.search(r'https://[a-z0-9-]+\.trycloudflare\.com', line_text)
                    if m2:
                        public_url = m2.group(0)
                        break
                except asyncio.TimeoutError:
                    continue
        except Exception:
            pass

    memory_db.audit_log("project_share", f"{'public' if public_url else 'lan'}: {public_url or web_url}")

    return {
        "ok":         True,
        "lan_url":    web_url,
        "demo_url":   demo_url,
        "public_url": public_url,
        "is_public":  bool(public_url),
        "message":    message,
        "tip":        "Share the public URL with anyone. LAN URL works only on the same Wi-Fi." if public_url
                      else "Install cloudflared for a public HTTPS URL: brew install cloudflared",
        "qr_url":     f"https://api.qrserver.com/v1/create-qr-code/?size=200x200&data={public_url or web_url}",
    }
