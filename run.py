#!/usr/bin/env python3
"""
Agentic OS Launcher
Run: python run.py
"""
import os
import sys
import signal
import shutil
import sqlite3
import subprocess
import webbrowser
import threading
import time
from pathlib import Path

ROOT = Path(__file__).parent
sys.path.insert(0, str(ROOT))

from backend.version import VERSION

# ── Load .env early ────────────────────────────────────────────────────────────
try:
    from dotenv import load_dotenv
    load_dotenv(ROOT / ".env", override=False)
except ImportError:
    pass  # dotenv not yet installed — handled below

PORT = int(os.getenv("AGENTIC_OS_PORT", "8787"))
HOST = os.getenv("AGENTIC_OS_HOST", "127.0.0.1")


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
    except Exception as exc:
        raise RuntimeError(f"Unable to initialize Agentic OS database schema: {exc}") from exc
    db_path = memory_dir / "agentic.db"
    try:
        con = sqlite3.connect(db_path)
        cur = con.cursor()
    except sqlite3.Error as exc:
        raise RuntimeError(f"Unable to open Agentic OS database at {db_path}: {exc}") from exc

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
                    ("system", f"Agentic OS {VERSION} initialized. Shared memory active. Multi-agent swarm online.", "system,init"),
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
    print(f"  ║   🧠  AGENTIC OS {VERSION} — MISSION CONTROL                 ║")
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


def reclaim_port(port: int):
    """Terminate a prior local listener without invoking a shell pipeline."""
    import socket

    with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as sock:
        if sock.connect_ex(('127.0.0.1', port)) != 0:
            return

    lsof = shutil.which('lsof')
    if not lsof:
        raise RuntimeError(f'Port {port} is already occupied and lsof is unavailable')

    try:
        result = subprocess.run(
            [lsof, '-ti', f':{port}'],
            check=False,
            capture_output=True,
            text=True,
            timeout=5,
        )
        pids = [int(value) for value in result.stdout.split() if value.isdigit()]
    except (OSError, ValueError, subprocess.SubprocessError) as exc:
        raise RuntimeError(f'Unable to inspect process on port {port}: {exc}') from exc

    if not pids:
        raise RuntimeError(f'Port {port} is occupied but no owning process could be identified')

    print(f"\n⚠️  [Agentic OS Engine] Port {port} is occupied. Reclaiming local process...")
    for pid in pids:
        if pid == os.getpid():
            continue
        try:
            os.kill(pid, signal.SIGTERM)
        except ProcessLookupError:
            continue
        except PermissionError as exc:
            raise RuntimeError(f'Permission denied terminating process {pid} on port {port}') from exc

    time.sleep(1.0)


if __name__ == "__main__":
    check_requirements()
    seed_data_dir()
    seed_db()
    reclaim_port(PORT)
    print_banner()
    if not os.environ.get("AGENTIC_OS_DATA_DIR") and not os.environ.get("TAURI_APP") and "--no-browser" not in sys.argv:
        threading.Thread(target=open_browser, daemon=True).start()

    import uvicorn
    while True:
        try:
            uvicorn.run(
                "backend.app:app",
                app_dir=str(ROOT),
                host=HOST,
                port=PORT,
                reload=os.environ.get("AGENTIC_OS_DEV", "0") == "1",
                log_level="info",
                access_log=True,
            )
            break
        except SystemExit as e:
            if e.code == 101:
                print("\n⚡ [Agentic OS Engine] Hard reboot requested (Code 101) — restarting server in fresh RAM...\n")
                time.sleep(1)
                continue
            break
