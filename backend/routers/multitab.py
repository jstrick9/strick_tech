"""
Agentic OS — Multi-Tab Preview Router
Manage multiple live preview URLs simultaneously.
Each tab has its own URL, file, title, and refresh state.
"""
from __future__ import annotations
import json, logging, time, uuid
from pathlib import Path
from fastapi import APIRouter, Request

router = APIRouter(prefix="/api/multitab", tags=["multitab"])
log    = logging.getLogger("agentic.multitab")

ROOT        = Path(__file__).resolve().parents[2]
PREVIEW_DIR = ROOT / "preview"

# ── In-memory tab state ────────────────────────────────────────────────────────
_tabs: dict[str, dict] = {}

def _default_tabs():
    """Return default tabs from preview files."""
    tabs = {}
    # Main preview tab — use index.html if it exists, otherwise first HTML file
    main_id = "tab_main"
    index_path = PREVIEW_DIR / "index.html"
    if index_path.exists():
        main_file, main_url = "index.html", "/preview/index.html"
    else:
        # Find first available HTML file
        html_files = sorted(PREVIEW_DIR.glob("*.html")) if PREVIEW_DIR.exists() else []
        if html_files:
            main_file = html_files[0].name
            main_url  = f"/preview/{main_file}"
        else:
            main_file, main_url = "index.html", "/preview/index.html"

    tabs[main_id] = {
        "id":         main_id,
        "title":      main_file,
        "url":        main_url,
        "file":       main_file,
        "pinned":     True,
        "active":     True,
        "favicon":    "🏠",
        "created_at": time.time(),
    }
    # Check for other preview files
    if PREVIEW_DIR.exists():
        for f in sorted(PREVIEW_DIR.iterdir()):
            if f.is_file() and f.suffix in (".html",".htm") and f.name != "index.html":
                tid = f"tab_{uuid.uuid4().hex[:6]}"
                tabs[tid] = {
                    "id":         tid,
                    "title":      f.name,
                    "url":        f"/preview/{f.name}",
                    "file":       f.name,
                    "pinned":     False,
                    "active":     False,
                    "favicon":    "📄",
                    "created_at": time.time(),
                }
    return tabs


def _get_tabs() -> dict:
    if not _tabs:
        # Try loading persisted state first
        persisted = _load_persisted_tabs()
        if persisted:
            _tabs.update(persisted)
        else:
            _tabs.update(_default_tabs())
    return _tabs


# ── Tab persistence ──────────────────────────────────────────────────────────
_TABS_FILE = ROOT / "workspaces" / ".multitab_state.json"

def _load_persisted_tabs():
    """Load saved tab state from disk."""
    try:
        if _TABS_FILE.exists():
            saved = json.loads(_TABS_FILE.read_text())
            return {t["id"]: t for t in saved if isinstance(t, dict) and "id" in t}
    except Exception as e:
        log.warning("Failed to load tab state: %s", e)
    return {}


def _save_tabs():
    """Persist current tab state to disk."""
    try:
        _TABS_FILE.parent.mkdir(parents=True, exist_ok=True)
        _TABS_FILE.write_text(json.dumps(list(_tabs.values()), default=str))
    except Exception as e:
        log.warning("Failed to save tab state: %s", e)


# ── REST endpoints ────────────────────────────────────────────────────────────
@router.get("/tabs")
def list_tabs():
    tabs = _get_tabs()
    return {"tabs": list(tabs.values()), "count": len(tabs)}


@router.post("/tabs")
async def create_tab(req: Request):
    try:
        body  = await req.json()
    except Exception:
        body  = {}
    tid   = f"tab_{uuid.uuid4().hex[:6]}"
    file  = (body.get("file") or "index.html").lstrip("/")
    url   = body.get("url") or f"/preview/{file}"
    title = body.get("title") or file
    
    tab = {
        "id":         tid,
        "title":      title[:80],
        "url":        url,
        "file":       file,
        "pinned":     body.get("pinned", False),
        "active":     body.get("active", True),
        "favicon":    body.get("favicon","📄"),
        "created_at": time.time(),
    }
    
    # Set as active, deactivate others if requested
    if tab["active"]:
        for t in _get_tabs().values():
            t["active"] = False
    
    _get_tabs()[tid] = tab
    _save_tabs()
    return {"ok": True, "tab": tab}


@router.patch("/tabs/{tab_id}")
async def update_tab(tab_id: str, req: Request):
    try:
        body = await req.json()
    except Exception:
        body = {}
    tabs = _get_tabs()
    if tab_id not in tabs:
        return {"ok": False, "error": "Tab not found"}
    
    tab = tabs[tab_id]
    _limits = {"title": 80, "url": 2000, "file": 200, "favicon": 8}
    for k in ("title","url","file","pinned","favicon"):
        if k in body:
            val = body[k]
            if k in _limits and isinstance(val, str):
                val = val[:_limits[k]]
            tab[k] = val
    
    if body.get("active"):
        for t in tabs.values():
            t["active"] = False
        tab["active"] = True
    
    _save_tabs()
    return {"ok": True, "tab": tab}


@router.delete("/tabs/{tab_id}")
def close_tab(tab_id: str):
    tabs = _get_tabs()
    if tab_id in tabs and tabs[tab_id].get("pinned"):
        return {"ok": False, "error": "Cannot close pinned tab"}
    tabs.pop(tab_id, None)
    # Activate first remaining tab
    if tabs:
        next_tab = next(iter(tabs.values()))
        next_tab["active"] = True
    _save_tabs()
    return {"ok": True}


@router.post("/tabs/{tab_id}/activate")
def activate_tab(tab_id: str):
    tabs = _get_tabs()
    if tab_id not in tabs:
        return {"ok": False, "error": "Tab not found"}
    for t in tabs.values():
        t["active"] = False
    tabs[tab_id]["active"] = True
    _save_tabs()
    return {"ok": True, "tab": tabs[tab_id]}


@router.post("/tabs/{tab_id}/refresh")
def refresh_tab(tab_id: str):
    tabs = _get_tabs()
    if tab_id not in tabs:
        return {"ok": False, "error": "Tab not found"}
    tabs[tab_id]["last_refresh"] = time.time()
    return {"ok": True, "tab": tabs[tab_id]}


@router.post("/tabs/refresh-all")
def refresh_all():
    ts = time.time()
    for t in _get_tabs().values():
        t["last_refresh"] = ts
    return {"ok": True, "refreshed": len(_get_tabs())}


@router.get("/files")
def list_preview_files():
    """List all available preview files."""
    files = []
    _EXCLUDE_DIRS = {".snapshots", "branches", "node_modules", ".git", "__pycache__"}
    if PREVIEW_DIR.exists():
        for f in sorted(PREVIEW_DIR.rglob("*")):
            if not f.is_file():
                continue
            if f.name.startswith("."):
                continue
            # Skip files inside excluded subdirectories
            if any(part in _EXCLUDE_DIRS for part in f.parts):
                continue
            rel = f.relative_to(PREVIEW_DIR)
            files.append({
                "name":     f.name,
                "path":     str(rel),
                "url":      f"/preview/{rel}",
                "size_kb":  round(f.stat().st_size / 1024, 2),
                "ext":      f.suffix,
            })
    return {"files": files, "count": len(files)}


@router.post("/snapshot")
async def snapshot_tab(req: Request):
    """Create a snapshot of a preview file (for tab history)."""
    try:
        body   = await req.json()
    except Exception:
        body   = {}
    tab_id = body.get("tab_id","tab_main")
    tabs   = _get_tabs()
    tab    = tabs.get(tab_id)
    if not tab:
        return {"ok": False, "error": "Tab not found"}
    
    file = tab.get("file","index.html")
    src  = (PREVIEW_DIR / file).resolve()
    # Security: ensure resolved path stays inside PREVIEW_DIR
    if not str(src).startswith(str(PREVIEW_DIR.resolve())):
        return {"ok": False, "error": "Invalid file path"}
    if not src.exists():
        return {"ok": False, "error": "Preview file not found"}
    
    # Store snapshot
    snap_dir = PREVIEW_DIR / ".snapshots"
    snap_dir.mkdir(exist_ok=True)
    ts   = int(time.time())
    snap = snap_dir / f"{tab_id}_{ts}_{file}"
    snap.write_bytes(src.read_bytes())
    
    return {
        "ok":          True,
        "snapshot":    str(snap.name),
        "file":        file,
        "timestamp":   ts,
    }
