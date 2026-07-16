#!/usr/bin/env python3
"""
Agentic OS v6.0 — Launcher
Run: python run.py
"""
import os
import sys
import sqlite3
import webbrowser
import threading
import time
from pathlib import Path

ROOT = Path(__file__).parent
sys.path.insert(0, str(ROOT))

# ── Load .env early ────────────────────────────────────────────────────────────
try:
    from dotenv import load_dotenv
    load_dotenv(ROOT / ".env", override=False)
except ImportError:
    pass  # dotenv not yet installed — handled below

PORT = int(os.getenv("AGENTIC_OS_PORT", "8787"))
HOST = os.getenv("AGENTIC_OS_HOST", "0.0.0.0")


def check_requirements():
    """Warn if critical packages are missing."""
    missing = []
    for pkg in ["fastapi", "uvicorn", "httpx", "dotenv"]:
        try:
            __import__(pkg.replace("-", "_"))
        except ImportError:
            missing.append(pkg)
    if missing:
        print(f"\n⚠️  Missing packages: {', '.join(missing)}")
        print("   Run: pip install -r requirements.txt\n")
        sys.exit(1)


def seed_db():
    """Seed initial data if DB is empty."""
    _data_dir = os.environ.get("AGENTIC_OS_DATA_DIR")
    memory_dir = Path(_data_dir) / "memory" if _data_dir else (ROOT / "memory")
    memory_dir.mkdir(parents=True, exist_ok=True)
    try:
        from backend.services.memory_db import ensure_schema
        ensure_schema()
    except Exception:
        pass
    db_path = memory_dir / "agentic.db"
    con = sqlite3.connect(db_path)
    cur = con.cursor()

    # Check if tasks table has data
    try:
        count = cur.execute("SELECT COUNT(*) FROM tasks").fetchone()[0]
    except Exception:
        count = 0

    if count == 0:
        try:
            cur.executemany(
                "INSERT OR IGNORE INTO tasks(title,status,priority,agent,layer) VALUES (?,?,?,?,?)",
                [
                    ("Wire OpenRouter API key → real chat",      "done",    "high",   "brain",      "Goals"),
                    ("Multi-agent swarm fan-out",                 "done",    "high",   "orchestrator","Execution"),
                    ("Memory Galaxy vector RAG",                  "done",    "high",   "memory",     "Memory"),
                    ("Live app builder + Monaco editor",          "done",    "high",   "builder",    "Goals"),
                    ("Playwright E2E auto-fix loop",              "doing",   "high",   "builder",    "Execution"),
                    ("Create custom agent persona",               "todo",    "medium", "brain",      "Tasks"),
                    ("MCP Tool Router — filesystem + browser",    "todo",    "high",   "builder",    "Ship"),
                    ("Voice agent — Whisper STT + TTS",           "todo",    "medium", "brain",      "Execution"),
                    ("Tauri desktop app packaging",               "todo",    "high",   "builder",    "Ship"),
                    ("One-click Vercel deploy",                   "todo",    "medium", "builder",    "Ship"),
                ]
            )
            con.commit()
        except Exception:
            pass

    try:
        mem_count = cur.execute("SELECT COUNT(*) FROM memory").fetchone()[0]
    except Exception:
        mem_count = 0

    if mem_count == 0:
        try:
            cur.executemany(
                "INSERT OR IGNORE INTO memory(source,content,tags) VALUES (?,?,?)",
                [
                    ("system", "Agentic OS v6.0 initialized. Shared memory active. Multi-agent swarm online.", "system,init"),
                    ("self",   "Local-first agentic AI OS. Monaco editor, Git time-travel, Memory Galaxy, Swarm.", "self,core"),
                    ("brain",  "OpenRouter provides access to Claude, GPT-4o, Gemini, Grok, Llama via one API key.", "brain,llm"),
                ]
            )
            con.commit()
        except Exception:
            pass

    con.close()


def open_browser():
    time.sleep(1.5)
    try:
        webbrowser.open(f"http://localhost:{PORT}")
    except Exception:
        pass


def print_banner():
    key_set = "✅ set" if os.getenv("OPENROUTER_API_KEY") else "❌ NOT SET — add to .env"
    print("\n")
    print("  ╔══════════════════════════════════════════════════════════╗")
    print("  ║                                                          ║")
    print("  ║   🧠  AGENTIC OS v6.0 — MISSION CONTROL                 ║")
    print("  ║   Local-first · Multi-agent · Memory Galaxy              ║")
    print("  ║                                                          ║")
    print("  ╚══════════════════════════════════════════════════════════╝")
    print()
    print(f"  Agents   : Orchestrator · Brain · Builder · Researcher · Reviewer")
    print(f"  Memory   : SQLite FTS5 + vector store")
    print(f"  Swarm    : Multi-model fan-out + judge")
    print(f"  API Key  : OPENROUTER_API_KEY {key_set}")
    print()
    print(f"  🌐  http://localhost:{PORT}")
    print(f"  📱  http://localhost:{PORT}/preview/mobile/index.html")
    print()
    if not os.getenv("OPENROUTER_API_KEY"):
        print("  ⚡  QUICK START: Copy .env.example → .env, add your OpenRouter key")
        print("      Get a free key: https://openrouter.ai/keys")
        print()


def seed_data_dir():
    """Copy initial templates to AGENTIC_OS_DATA_DIR on first run."""
    _data_dir = os.environ.get("AGENTIC_OS_DATA_DIR")
    if not _data_dir:
        return
    data_path = Path(_data_dir)
    import shutil
    # Copy memory/hierarchy templates if not present in data_dir
    src_hierarchy = ROOT / "memory" / "hierarchy"
    dst_hierarchy = data_path / "memory" / "hierarchy"
    if src_hierarchy.exists() and not dst_hierarchy.exists():
        dst_hierarchy.parent.mkdir(parents=True, exist_ok=True)
        try:
            shutil.copytree(src_hierarchy, dst_hierarchy, dirs_exist_ok=True)
        except Exception:
            pass
    # Copy skills if not present
    src_skills = ROOT / "skills"
    dst_skills = data_path / "skills"
    if src_skills.exists() and not dst_skills.exists():
        try:
            shutil.copytree(src_skills, dst_skills, dirs_exist_ok=True)
        except Exception:
            pass
    # Copy preview if not present
    src_preview = ROOT / "preview"
    dst_preview = data_path / "preview"
    if src_preview.exists() and not dst_preview.exists():
        try:
            shutil.copytree(src_preview, dst_preview, dirs_exist_ok=True)
        except Exception:
            pass


if __name__ == "__main__":
    check_requirements()
    seed_data_dir()
    seed_db()
    print_banner()
    if not os.environ.get("AGENTIC_OS_DATA_DIR") and not os.environ.get("TAURI_APP") and "--no-browser" not in sys.argv:
        threading.Thread(target=open_browser, daemon=True).start()

    import uvicorn
    uvicorn.run(
        "backend.app:app",
        app_dir=str(ROOT),
        host=HOST,
        port=PORT,
        reload=False,
        log_level="info",
        access_log=True,
    )
